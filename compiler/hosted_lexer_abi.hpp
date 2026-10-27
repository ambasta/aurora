#pragma once
#include "diagnostics.hpp"
#include "hosted_frontend_abi.hpp"

namespace aurora::hosted_lexer {
using hosted_abi::compiler_lexer::Event;
// The public diagnostic for a lexical rejection event; any other event returns.
inline void rejectLexical(Event event, const SourceSpan &span) {
    if (event == Event::unsupported_character)
        throw Error(DiagnosticCode::UnsupportedCharacter, "unsupported character", span);
    if (event == Event::invalid_byte)
        throw Error(DiagnosticCode::InvalidByteLiteral, "invalid byte literal", span);
    if (event == Event::invalid_string)
        throw Error(DiagnosticCode::InvalidByteStringLiteral, "invalid byte-string literal", span);
}
} // namespace aurora::hosted_lexer
