#pragma once
#include <algorithm>
#include <cstddef>
#include <memory>
#include <ostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace aurora {
// One immutable snapshot is shared by every token from the same lex invocation.
class SourceText {
public:
    const std::string path;
    const std::string text;
    SourceText(std::string name, std::string contents) : path(std::move(name)), text(std::move(contents)) {
    }
};
class SourcePosition {
public:
    std::size_t offset = 0;
    int line = 1;
    int column = 1;
};
class SourceSpan {
public:
    std::shared_ptr<const SourceText> source;
    SourcePosition begin;
    SourcePosition end;
};
// These are diagnostic families, not message hashes. Add narrower codes explicitly.
enum class DiagnosticCode {
    Unclassified,
    UnsupportedCharacter,
    InvalidByteLiteral,
    UnexpectedToken,
    NestingLimit,
    UnsupportedFieldType,
    Semantic,
    Module,
    CommandLine,
    Internal,
    UnreadLocal
};
inline std::string_view diagnosticCode(DiagnosticCode code) {
    switch (code) {
    case DiagnosticCode::Unclassified:
        return "AU0000";
    case DiagnosticCode::UnsupportedCharacter:
        return "AU1001";
    case DiagnosticCode::InvalidByteLiteral:
        return "AU1002";
    case DiagnosticCode::UnexpectedToken:
        return "AU2001";
    case DiagnosticCode::NestingLimit:
        return "AU2002";
    case DiagnosticCode::UnsupportedFieldType:
        return "AU2003";
    case DiagnosticCode::Semantic:
        return "AU3001";
    case DiagnosticCode::Module:
        return "AU4001";
    case DiagnosticCode::CommandLine:
        return "AU5001";
    case DiagnosticCode::UnreadLocal:
        return "AU6001";
    case DiagnosticCode::Internal:
        return "AU9001";
    }
    return "AU9001";
}
enum class DiagnosticSeverity {
    Error,
    Warning
};
inline std::string_view diagnosticSeverity(DiagnosticSeverity severity) {
    return severity == DiagnosticSeverity::Warning ? "warning" : "error";
}
class Diagnostic {
public:
    DiagnosticCode code = DiagnosticCode::Unclassified;
    // Locations belong to span; message contains only the explanation and semantic context.
    std::string message;
    SourceSpan span;
    DiagnosticSeverity severity = DiagnosticSeverity::Error;
};
class Error : public std::runtime_error {
public:
    const Diagnostic diagnostic;
    explicit Error(std::string message) : Error(Diagnostic{DiagnosticCode::Unclassified, std::move(message), {}}) {
    }
    Error(DiagnosticCode code, std::string message, SourceSpan span = {})
        : Error(Diagnostic{code, std::move(message), std::move(span)}) {
    }
    explicit Error(Diagnostic value) : std::runtime_error(value.message), diagnostic(std::move(value)) {
    }
    Error withContext(const std::string &prefix) const {
        auto result = diagnostic;
        result.message = prefix + result.message;
        return Error(std::move(result));
    }
    Error withDefaultCode(DiagnosticCode code) const {
        auto result = diagnostic;
        if (result.code == DiagnosticCode::Unclassified)
            result.code = code;
        return Error(std::move(result));
    }
};
inline void writeDiagnosticText(std::ostream &out, const Diagnostic &diagnostic, std::string_view tool) {
    if (diagnostic.span.source) {
        const auto &path = diagnostic.span.source->path;
        out << (path.empty() ? "<source>" : path) << ':' << diagnostic.span.begin.line << ':'
            << diagnostic.span.begin.column;
    } else {
        out << tool;
    }
    out << ": " << diagnosticSeverity(diagnostic.severity) << ' ' << diagnosticCode(diagnostic.code) << ": "
        << diagnostic.message << '\n';
}
inline void writeJsonString(std::ostream &out, std::string_view value) {
    constexpr char hex[] = "0123456789abcdef";
    out << '\"';
    for (std::size_t index = 0; index < value.size();) {
        const auto byte = static_cast<unsigned char>(value[index]);
        if (byte == '\"' || byte == '\\') {
            out << '\\' << static_cast<char>(byte);
            ++index;
            continue;
        }
        if (byte >= 0x20 && byte < 0x80) {
            out << static_cast<char>(byte);
            ++index;
            continue;
        }
        // Preserve valid UTF-8, including non-ASCII source paths. Ill-formed bytes
        // are escaped individually so host paths never produce invalid JSON.
        std::size_t width = byte >= 0xc2 && byte <= 0xdf   ? 2
                            : byte >= 0xe0 && byte <= 0xef ? 3
                            : byte >= 0xf0 && byte <= 0xf4 ? 4
                                                           : 0;
        bool valid = width != 0 && width <= value.size() - index;
        unsigned int scalar = width == 2 ? byte & 0x1f : width == 3 ? byte & 0x0f : byte & 0x07;
        for (std::size_t next = 1; valid && next < width; ++next) {
            const auto continuation = static_cast<unsigned char>(value[index + next]);
            valid = continuation >= 0x80 && continuation <= 0xbf;
            scalar = (scalar << 6) | (continuation & 0x3f);
        }
        valid = valid && scalar <= 0x10ffff && !(scalar >= 0xd800 && scalar <= 0xdfff) &&
                (width != 3 || scalar >= 0x800) && (width != 4 || scalar >= 0x10000);
        if (valid) {
            out.write(value.data() + index, static_cast<std::streamsize>(width));
            index += width;
        } else {
            out << "\\u00" << hex[byte >> 4] << hex[byte & 15];
            ++index;
        }
    }
    out << '\"';
}
inline void writeJsonPosition(std::ostream &out, const SourcePosition &position) {
    out << "{\"offset\":" << position.offset << ",\"line\":" << position.line << ",\"column\":" << position.column
        << '}';
}
inline void writeDiagnosticsJson(std::ostream &out, const std::vector<Diagnostic> &diagnostics) {
    const bool errors = std::any_of(diagnostics.begin(), diagnostics.end(), [](const auto &diagnostic) {
        return diagnostic.severity == DiagnosticSeverity::Error;
    });
    out << "{\"schemaVersion\":1,\"success\":" << (errors ? "false" : "true") << ",\"diagnostics\":[";
    bool first = true;
    for (const auto &diagnostic : diagnostics) {
        if (!first)
            out << ',';
        first = false;
        out << "{\"code\":";
        writeJsonString(out, diagnosticCode(diagnostic.code));
        out << ",\"severity\":";
        writeJsonString(out, diagnosticSeverity(diagnostic.severity));
        out << ",\"message\":";
        writeJsonString(out, diagnostic.message);
        out << ",\"path\":";
        if (diagnostic.span.source)
            writeJsonString(out, diagnostic.span.source->path);
        else
            out << "null";
        out << ",\"range\":";
        if (diagnostic.span.source) {
            out << "{\"start\":";
            writeJsonPosition(out, diagnostic.span.begin);
            out << ",\"end\":";
            writeJsonPosition(out, diagnostic.span.end);
            out << '}';
        } else {
            out << "null";
        }
        out << '}';
    }
    out << "]}\n";
}
} // namespace aurora
