#pragma once
#include "check.hpp"
#include "positions.hpp"
#include <nlohmann/json.hpp>
#include <functional>
#include <limits>
#include <set>

namespace aurora::lsp {
using Json = nlohmann::json;
using Check = std::function<std::vector<Diagnostic>(const std::filesystem::path &, const Snapshots &, bool)>;
inline constexpr std::size_t maxDocumentBytes = 1024 * 1024;
inline constexpr std::size_t maxOpenBytes = 4 * 1024 * 1024;
inline constexpr std::size_t maxDocuments = 32;
inline constexpr std::size_t maxPublishedDiagnostics = 128;
static_assert(maxDocuments < maxPublishedDiagnostics);

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
    const bool warning = diagnostic.severity == DiagnosticSeverity::Warning;
    if (known) {
        const auto &text = diagnostic.span.source->text;
        begin = utf16Position(text, diagnostic.span.begin.offset);
        end = utf16Position(text, std::max(diagnostic.span.begin.offset, diagnostic.span.end.offset), true);
    }
    return {{"range", {{"start", positionJson(begin)}, {"end", positionJson(end)}}},
            {"severity", warning ? 2 : 1},
            {"code", diagnosticCode(diagnostic.code)},
            {"source", "aurora"},
            {"message", boundedMessage((known ? "" : "[location unavailable] ") + diagnostic.message)},
            {"data", {{"rangeKnown", known}, {"firstErrorOnly", !warning}}}};
}

inline bool lintOption(const Json &params) {
    const auto &options = field(params, "initializationOptions");
    if (options.is_null())
        return false;
    if (!options.is_object() || options.size() > 1 ||
        (!options.empty() && (!options.contains("lint") || !options["lint"].is_boolean())))
        throw ProtocolError("initializationOptions supports only a boolean lint option");
    return !options.empty() && options["lint"].get<bool>();
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
    bool lint = false;
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
        std::map<std::string, std::size_t> warningCounts, omittedWarnings;
        for (const auto &[path, document] : documents) {
            snapshots.emplace(path, document.snapshot);
            diagnostics[document.uri] = Json::array();
            versions.emplace(document.uri, document.version);
        }
        for (const auto &[path, document] : documents) {
            (void)document;
            std::vector<Diagnostic> found;
            try {
                found = check(path, snapshots, lint);
            } catch (const std::exception &) {
                log("compiler check failed internally");
                found = {{DiagnosticCode::Internal, "compiler check failed internally", {}}};
            }
            for (const auto &diagnostic : found) {
                const auto uri = sourceUri(diagnostic, path);
                auto &entries = diagnostics.try_emplace(uri, Json::array()).first->second;
                const bool warning = diagnostic.severity == DiagnosticSeverity::Warning;
                // Compiler lint findings belong only to their independently
                // checked root, so omitted root warnings cannot be duplicates
                // projected by other importers. Avoid converting excess spans.
                if (warning && warningCounts[uri] >= maxPublishedDiagnostics) {
                    ++omittedWarnings[uri];
                    continue;
                }
                const auto value = diagnosticJson(diagnostic);
                // Import wrappers add message context to the same source error.
                // Compiler identity and exact location identify one publication.
                const bool duplicate = std::any_of(entries.begin(), entries.end(), [&](const auto &entry) {
                    return entry["code"] == value["code"] && entry["range"] == value["range"] &&
                           entry["severity"] == value["severity"];
                });
                if (!duplicate) {
                    entries.push_back(value);
                    if (warning)
                        ++warningCounts[uri];
                }
            }
        }
        for (const auto &uri : published)
            diagnostics.try_emplace(uri, Json::array());
        published.clear();
        for (auto &[uri, entries] : diagnostics) {
            Json bounded = Json::array();
            // At most one error per open root, at most 32 roots. Errors always
            // survive the warning budget, including errors discovered later.
            for (const auto &entry : entries)
                if (entry["severity"] == 1)
                    bounded.push_back(entry);
            auto omitted = omittedWarnings[uri];
            const bool truncated = omitted || entries.size() > maxPublishedDiagnostics;
            const auto limit = maxPublishedDiagnostics - static_cast<std::size_t>(truncated);
            for (const auto &entry : entries) {
                if (entry["severity"] != 2)
                    continue;
                if (bounded.size() < limit)
                    bounded.push_back(entry);
                else
                    ++omitted;
            }
            if (omitted)
                bounded.push_back(
                    {{"range", {{"start", positionJson({})}, {"end", positionJson({})}}},
                     {"severity", 2},
                     {"code", "aurora-lsp-diagnostics-limit"},
                     {"source", "aurora-lsp"},
                     {"message",
                      "[location unavailable] Diagnostic publication truncated; " + std::to_string(omitted) +
                          " warnings omitted."},
                     {"data", {{"rangeKnown", false}, {"firstErrorOnly", false}, {"omittedWarnings", omitted}}}});
            Json params = {{"uri", uri}, {"diagnostics", std::move(bounded)}};
            if (const auto version = versions.find(uri); version != versions.end())
                params["version"] = version->second;
            const Json message = {
                {"jsonrpc", "2.0"}, {"method", "textDocument/publishDiagnostics"}, {"params", std::move(params)}};
            const auto payload = message.dump(-1, ' ', false, Json::error_handler_t::replace);
            // Count encoded UTF-8 bytes, not characters. This also checks
            // generated closed-import URIs outside the incoming URI bound.
            if (payload.size() > maxMessageBytes)
                throw std::length_error("diagnostic publication exceeds wire limit");
            writeFrame(output, payload);
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
    void formatting(const Json &id, const Json &params) {
        try {
            const auto &identifier = field(params, "textDocument");
            const auto uri = stringField(identifier, "uri");
            const auto found = documents.find(pathFromUri(uri));
            if (found == documents.end() || found->second.uri != uri)
                throw ProtocolError("formatting requires the open document URI");
            const auto &options = field(params, "options");
            const auto &tabSize = field(options, "tabSize");
            if (!options.is_object() || options.size() != 2 || !tabSize.is_number_integer() || tabSize != 4 ||
                !field(options, "insertSpaces").is_boolean() || field(options, "insertSpaces") != true)
                throw ProtocolError("formatting supports only tabSize=4 and insertSpaces=true options");
            // LSP FormattingParams has no version field. Sequential dispatch
            // pins this current version throughout formatting and its response.
            const auto &document = found->second;
            try {
                auto text = formatDocument(found->first, *document.snapshot);
                Json edits = Json::array();
                if (text != document.snapshot->text) {
                    const auto end = utf16Position(document.snapshot->text, document.snapshot->text.size(), true);
                    edits.push_back({{"range", {{"start", positionJson({})}, {"end", positionJson(end)}}},
                                     {"newText", std::move(text)}});
                }
                result(id, std::move(edits));
            } catch (const Error &failure) {
                send({{"jsonrpc", "2.0"},
                      {"id", id},
                      {"error",
                       {{"code", -32803},
                        {"message", "Aurora formatting failed"},
                        {"data",
                         {{"uri", document.uri},
                          {"version", document.version},
                          {"diagnostic", diagnosticJson(failure.diagnostic)}}}}}});
            }
        } catch (const ProtocolError &failure) {
            error(id, -32602, failure.what());
        } catch (const std::exception &) {
            error(id, -32603, "Formatter failed internally");
        }
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
                try {
                    lint = lintOption(params);
                } catch (const ProtocolError &failure) {
                    error(id, -32602, failure.what());
                    return {};
                }
                initialized = true;
                result(id,
                       {{"capabilities",
                         {{"positionEncoding", "utf-16"},
                          {"textDocumentSync", {{"openClose", true}, {"change", 1}}},
                          {"documentFormattingProvider", true}}},
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
        if (request && method == "textDocument/formatting") {
            formatting(id, params);
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
