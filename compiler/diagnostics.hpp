#pragma once
#include <cstddef>
#include <memory>
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
// Diagnostic families by number (AU3001 is 3001), not message hashes. Aurora
// names the family of each diagnostic it renders; these name the host's own.
enum class DiagnosticCode {
    Unclassified = 0,
    UnsupportedCharacter = 1001,
    InvalidByteLiteral = 1002,
    InvalidByteStringLiteral = 1003,
    UnexpectedToken = 2001,
    NestingLimit = 2002,
    UnsupportedFieldType = 2003,
    Semantic = 3001,
    Module = 4001,
    CommandLine = 5001,
    UnreadLocal = 6001,
    Internal = 9001
};
// The family's name, with the tool prefix: AU for diagnostics, AUF for style findings.
inline std::string diagnosticCode(DiagnosticCode code, std::string_view prefix = "AU") {
    const auto digits = std::to_string(static_cast<int>(code));
    return std::string(prefix) + std::string(digits.size() < 4 ? 4 - digits.size() : 0, '0') + digits;
}
enum class DiagnosticSeverity {
    Error,
    Warning
};
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
} // namespace aurora
