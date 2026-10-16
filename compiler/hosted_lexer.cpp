// Trusted hosted bootstrap import boundary; no foreign pointer constructor is
// exposed by Aurora. Immutable SourceText stays alive through every invocation.
#include "lexer.hpp"
#include "hosted_lexer_abi.hpp"
#include <cstddef>
#include <cstdint>
#include <limits>

#ifndef AURORA_HOSTED_LEXER
#error The hosted lexer adapter requires AURORA_HOSTED_LEXER
#endif

namespace aurora {
namespace {
using hosted_lexer::Event;
using Input = hosted_abi::LexerInput;
using Output = hosted_abi::compiler_lexer::Lexeme;

SourcePosition position(std::int64_t offset, std::int64_t line, std::int64_t start) {
    if (offset < 0 || start < 0 || start > offset || line < 1 || line > std::numeric_limits<int>::max() ||
        offset - start >= std::numeric_limits<int>::max())
        throw Error(DiagnosticCode::Internal, "hosted lexer returned an invalid source position");
    return {static_cast<std::size_t>(offset), static_cast<int>(line), static_cast<int>(offset - start + 1)};
}
} // namespace

LexedSource lexSource(std::shared_ptr<const SourceText> source, TriviaRetention retention) {
    if (!source)
        throw Error(DiagnosticCode::Internal, "source snapshot must not be null");
    // File I/O already limits sources to 1 MiB. Direct callers must also fit the
    // existing signed SourcePosition representation, including zero-width EOF.
    if (source->text.size() > static_cast<std::size_t>(std::numeric_limits<int>::max() - 1))
        throw Error(DiagnosticCode::Internal, "source is too large for lexer positions");
    LexedSource out;
    out.source = std::move(source);
    Input input;
    input.cursor.line = 1;
    input.source.backing = out.source->text.data();
    input.source.length = static_cast<std::int64_t>(out.source->text.size());
    for (;;) {
        const auto begin = position(input.cursor.offset, input.cursor.line, input.cursor.line_start);
        Output next;
        aurora_hosted_lexer_invoke(&input, &next);
        // Do not let malformed private results index host memory, loop forever,
        // or narrow unchecked into the public diagnostic representation.
        if (!hosted_abi::compiler_lexer::validRaw(next.event) || next.event == Event::invalid_cursor ||
            next.offset < input.cursor.offset || next.offset > input.source.length || next.line < input.cursor.line ||
            next.line - input.cursor.line > next.offset - input.cursor.offset ||
            next.line_start < input.cursor.line_start || next.line_start > next.offset ||
            (next.line == input.cursor.line && next.line_start != input.cursor.line_start) ||
            (next.line != input.cursor.line && next.line_start <= input.cursor.offset) ||
            (next.event != Event::whitespace &&
             (next.line != input.cursor.line || next.line_start != input.cursor.line_start)) ||
            (next.event == Event::end_of_input
                 ? (input.cursor.offset != input.source.length || next.offset != input.cursor.offset)
                 : next.offset == input.cursor.offset))
            throw Error(DiagnosticCode::Internal, "hosted lexer returned an invalid event");
        const SourceSpan span{out.source, begin, position(next.offset, next.line, next.line_start)};
        if (next.event == Event::unsupported_character)
            throw Error(DiagnosticCode::UnsupportedCharacter, "unsupported character", span);
        if (next.event == Event::invalid_byte)
            throw Error(DiagnosticCode::InvalidByteLiteral, "invalid byte literal", span);
        if (next.event == Event::invalid_string)
            throw Error(DiagnosticCode::InvalidByteStringLiteral, "invalid byte-string literal", span);
        if (next.event == Event::end_of_input) {
            out.tokens.emplace_back("<eof>", span);
            return out;
        }
        if (next.event == Event::token)
            out.tokens.emplace_back(out.source->text.substr(begin.offset, span.end.offset - begin.offset), span);
        else if (retention == TriviaRetention::Keep)
            out.trivia.push_back(
                {next.event == Event::whitespace ? TriviaKind::Whitespace : TriviaKind::LineComment, span});
        input.cursor.offset = next.offset;
        input.cursor.line = next.line;
        input.cursor.line_start = next.line_start;
    }
}
} // namespace aurora
