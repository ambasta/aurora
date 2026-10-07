#pragma once
#include "check.hpp"
#include "positions.hpp"
#include <nlohmann/json.hpp>
#include <functional>
#include <limits>
#include <set>

namespace aurora::lsp {
using Json = nlohmann::json;
using Check = std::function<std::optional<Diagnostic>(const std::filesystem::path &, const Snapshots &)>;
inline constexpr std::size_t maxDocumentBytes = 1024 * 1024;
inline constexpr std::size_t maxOpenBytes = 4 * 1024 * 1024;
inline constexpr std::size_t maxDocuments = 32;

inline Json parseMessage(const std::string &payload) {
    std::size_t events = 0;
    std::vector<std::set<std::string>> objectKeys;
    return Json::parse(payload, [&](int depth, Json::parse_event_t event, Json &value) {
        if (depth > 64 || ++events > 65536)
            throw ProtocolError("JSON structure exceeds limit");
        if (event == Json::parse_event_t::object_start)
            objectKeys.emplace_back();
        if (event == Json::parse_event_t::key && !objectKeys.back().insert(value.get<std::string>()).second)
            throw ProtocolError("duplicate JSON object key");
        if (event == Json::parse_event_t::object_end)
            objectKeys.pop_back();
        return true;
    });
}
inline const Json &field(const Json &object, const char *name) {
    static const Json missing;
    if (!object.is_object())
        return missing;
    const auto found = object.find(name);
    return found == object.end() ? missing : *found;
}
inline std::string stringField(const Json &object, const char *name) {
    const auto &value = field(object, name);
    if (!value.is_string())
        throw ProtocolError("required string field is missing or invalid");
    return value.get<std::string>();
}
inline std::int32_t documentVersion(const Json &document) {
    const auto &value = field(document, "version");
    if (!value.is_number_integer() ||
        (value.is_number_unsigned() && value.get<std::uint64_t>() > std::numeric_limits<std::int32_t>::max()))
        throw ProtocolError("document version must be a signed 32-bit integer");
    const auto version = value.get<std::int64_t>();
    if (version < std::numeric_limits<std::int32_t>::min() || version > std::numeric_limits<std::int32_t>::max())
        throw ProtocolError("document version exceeds range");
    return static_cast<std::int32_t>(version);
}
inline bool validId(const Json &value) {
    if (value.is_string())
        return value.get_ref<const std::string &>().size() <= 1024;
    if (!value.is_number_integer())
        return false;
    if (value.is_number_unsigned())
        return value.get<std::uint64_t>() <= std::numeric_limits<std::int32_t>::max();
    const auto number = value.get<std::int64_t>();
    return number >= std::numeric_limits<std::int32_t>::min() && number <= std::numeric_limits<std::int32_t>::max();
}
inline Json positionJson(Position position) {
    return {{"line", position.line}, {"character", position.character}};
}
inline std::string boundedMessage(std::string message) {
    if (message.size() > 4096) {
        std::size_t end = 4096;
        while (end && (static_cast<unsigned char>(message[end]) & 0xc0) == 0x80)
            --end;
        message.resize(end);
        message += " [truncated]";
    }
    return message;
}
inline Json diagnosticJson(const Diagnostic &diagnostic) {
    Position begin, end;
    const bool known = static_cast<bool>(diagnostic.span.source);
    if (known) {
        const auto &text = diagnostic.span.source->text;
        begin = utf16Position(text, diagnostic.span.begin.offset);
        end = utf16Position(text, std::max(diagnostic.span.begin.offset, diagnostic.span.end.offset), true);
    }
    return {{"range", {{"start", positionJson(begin)}, {"end", positionJson(end)}}},
            {"severity", 1},
            {"code", diagnosticCode(diagnostic.code)},
            {"source", "aurora"},
            {"message", boundedMessage((known ? "" : "[location unavailable] ") + diagnostic.message)},
            {"data", {{"rangeKnown", known}, {"firstErrorOnly", true}}}};
}

class Session {
    class Document {
    public:
        std::string uri;
        std::int32_t version;
        std::shared_ptr<const SourceText> snapshot;
    };
    Check check;
    std::ostream &output;
    std::ostream &logs;
    bool initialized = false;
    bool shutdown = false;
    std::size_t openBytes = 0;
    std::map<std::filesystem::path, Document> documents;
    std::set<std::string> published;

    void send(const Json &message) {
        // Disk-source diagnostics may contain malformed bytes; output stays UTF-8 JSON.
        writeFrame(output, message.dump(-1, ' ', false, Json::error_handler_t::replace));
    }
    void result(const Json &id, Json value) {
        send({{"jsonrpc", "2.0"}, {"id", id}, {"result", std::move(value)}});
    }
    void error(const Json &id, int code, const char *message) {
        send({{"jsonrpc", "2.0"}, {"id", id}, {"error", {{"code", code}, {"message", message}}}});
    }
    void log(std::string_view message) {
        logs << "aurora-lsp: " << message.substr(0, 512) << '\n';
    }
    std::string sourceUri(const Diagnostic &diagnostic, const std::filesystem::path &root) const {
        const auto path =
            diagnostic.span.source ? std::filesystem::absolute(diagnostic.span.source->path).lexically_normal() : root;
        const auto document = documents.find(path);
        return document == documents.end() ? uriFromPath(path) : document->second.uri;
    }
    void refresh() {
        Snapshots snapshots;
        std::map<std::string, Json> diagnostics;
        std::map<std::string, std::int32_t> versions;
        for (const auto &[path, document] : documents) {
            snapshots.emplace(path, document.snapshot);
            diagnostics[document.uri] = Json::array();
            versions.emplace(document.uri, document.version);
        }
        for (const auto &[path, document] : documents) {
            (void)document;
            std::optional<Diagnostic> found;
            try {
                found = check(path, snapshots);
            } catch (const std::exception &) {
                log("compiler check failed internally");
                found = Diagnostic{DiagnosticCode::Internal, "compiler check failed internally", {}};
            }
            if (!found)
                continue;
            const auto uri = sourceUri(*found, path);
            auto &entries = diagnostics.try_emplace(uri, Json::array()).first->second;
            const auto value = diagnosticJson(*found);
            // Import wrappers add message context to the same source error. Its
            // compiler code and exact location identify that one publication.
            const bool duplicate = std::any_of(entries.begin(), entries.end(), [&](const auto &entry) {
                return entry["code"] == value["code"] && entry["range"] == value["range"];
            });
            if (!duplicate)
                entries.push_back(value);
        }
        for (const auto &uri : published)
            diagnostics.try_emplace(uri, Json::array());
        published.clear();
        for (auto &[uri, entries] : diagnostics) {
            Json params = {{"uri", uri}, {"diagnostics", entries}};
            if (const auto version = versions.find(uri); version != versions.end())
                params["version"] = version->second;
            send({{"jsonrpc", "2.0"}, {"method", "textDocument/publishDiagnostics"}, {"params", std::move(params)}});
            if (!entries.empty() || versions.contains(uri))
                published.insert(uri);
        }
    }
    void open(const Json &params) {
        const auto &document = field(params, "textDocument");
        const auto uri = stringField(document, "uri");
        const auto path = pathFromUri(uri);
        const auto version = documentVersion(document);
        const auto language = stringField(document, "languageId");
        const auto text = stringField(document, "text");
        if (language != "aurora")
            throw ProtocolError("document languageId must be aurora");
        if (documents.contains(path))
            throw ProtocolError("document is already open");
        if (documents.size() >= maxDocuments || text.size() > maxDocumentBytes ||
            text.size() > maxOpenBytes - openBytes)
            throw ProtocolError("open document storage exceeds limit");
        documents.emplace(path, Document{uri, version, std::make_shared<const SourceText>(path.string(), text)});
        openBytes += text.size();
        refresh();
    }
    void change(const Json &params) {
        const auto &document = field(params, "textDocument");
        const auto uri = stringField(document, "uri");
        const auto path = pathFromUri(uri);
        const auto found = documents.find(path);
        if (found == documents.end() || found->second.uri != uri)
            throw ProtocolError("change requires the open document URI");
        const auto version = documentVersion(document);
        if (version <= found->second.version) {
            log("ignored stale document version");
            return;
        }
        const auto &changes = field(params, "contentChanges");
        if (!changes.is_array() || changes.size() != 1 || !changes[0].is_object() || changes[0].contains("range") ||
            changes[0].contains("rangeLength"))
            throw ProtocolError("exactly one full-content change is required");
        const auto text = stringField(changes[0], "text");
        const auto remaining = openBytes - found->second.snapshot->text.size();
        if (text.size() > maxDocumentBytes || text.size() > maxOpenBytes - remaining)
            throw ProtocolError("changed document storage exceeds limit");
        found->second.snapshot = std::make_shared<const SourceText>(path.string(), text);
        found->second.version = version;
        openBytes = remaining + text.size();
        refresh();
    }
    void close(const Json &params) {
        const auto uri = stringField(field(params, "textDocument"), "uri");
        const auto found = documents.find(pathFromUri(uri));
        if (found == documents.end() || found->second.uri != uri)
            throw ProtocolError("close requires the open document URI");
        openBytes -= found->second.snapshot->text.size();
        documents.erase(found);
        refresh();
    }
    std::optional<int> handle(const Json &message) {
        const bool request = message.is_object() && message.contains("id");
        const auto &id = field(message, "id");
        if (!message.is_object() || field(message, "jsonrpc") != "2.0" || !field(message, "method").is_string() ||
            (request && !validId(id))) {
            error(request && validId(id) ? id : Json(), -32600, "Invalid Request");
            return {};
        }
        const auto method = field(message, "method").get<std::string>();
        const auto &params = field(message, "params");
        if (method == "exit" && !request)
            return shutdown ? 0 : 1;
        if (shutdown) {
            if (request)
                error(id, -32600, "Server has shut down");
            return {};
        }
        if (method == "initialize") {
            if (!request) {
                log("initialize requires a request ID");
                return {};
            }
            if (initialized)
                error(id, -32600, "Server is already initialized");
            else if (!params.is_object())
                error(id, -32602, "Invalid initialize parameters");
            else {
                initialized = true;
                result(id,
                       {{"capabilities",
                         {{"positionEncoding", "utf-16"}, {"textDocumentSync", {{"openClose", true}, {"change", 1}}}}},
                        {"serverInfo", {{"name", "aurora-lsp"}, {"version", "0.1"}}}});
            }
            return {};
        }
        if (!initialized) {
            if (request)
                error(id, -32002, "Server not initialized");
            return {};
        }
        if (method == "shutdown") {
            if (!request) {
                log("shutdown requires a request ID");
                return {};
            }
            if (!params.is_null()) {
                error(id, -32602, "Shutdown takes no parameters");
                return {};
            }
            shutdown = true;
            result(id, nullptr);
            return {};
        }
        if (request) {
            error(id, -32601, "Method not found");
            return {};
        }
        try {
            if (method == "textDocument/didOpen")
                open(params);
            else if (method == "textDocument/didChange")
                change(params);
            else if (method == "textDocument/didClose")
                close(params);
        } catch (const ProtocolError &failure) {
            log(failure.what());
        }
        return {};
    }

public:
    Session(Check checker, std::ostream &out, std::ostream &err) : check(std::move(checker)), output(out), logs(err) {
    }
    int run(std::istream &input) {
        try {
            while (const auto payload = readFrame(input)) {
                Json message;
                try {
                    message = parseMessage(*payload);
                } catch (const std::exception &) {
                    error(nullptr, -32700, "Parse error or JSON structure limit exceeded");
                    continue;
                }
                if (const auto status = handle(message))
                    return *status;
            }
            return shutdown ? 0 : 1;
        } catch (const ProtocolError &failure) {
            log(failure.what());
            return 1;
        }
    }
};
} // namespace aurora::lsp
