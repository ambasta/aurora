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
extern "C" void aurora_hosted_lexer_invoke(const void *input, void *output);

namespace aurora {
namespace {
using hosted_lexer::Event;
using Input = hosted_abi::LexerInput;
using Output = hosted_abi::Lexeme;

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
    input.backing = out.source->text.data();
    input.length = static_cast<std::int64_t>(out.source->text.size());
    for (;;) {
        const auto begin = position(input.offset, input.line, input.lineStart);
        Output next;
        aurora_hosted_lexer_invoke(&input, &next);
        // Do not let malformed private results index host memory, loop forever,
        // or narrow unchecked into the public diagnostic representation.
        if (next.event < Event::Token || next.event >= Event::InvalidCursor || next.offset < input.offset ||
            next.offset > input.length || next.line < input.line ||
            next.line - input.line > next.offset - input.offset || next.lineStart < input.lineStart ||
            next.lineStart > next.offset || (next.line == input.line && next.lineStart != input.lineStart) ||
            (next.line != input.line && next.lineStart <= input.offset) ||
            (next.event != Event::Whitespace && (next.line != input.line || next.lineStart != input.lineStart)) ||
            (next.event == Event::EndOfInput ? (input.offset != input.length || next.offset != input.offset)
                                             : next.offset == input.offset))
            throw Error(DiagnosticCode::Internal, "hosted lexer returned an invalid event");
        const SourceSpan span{out.source, begin, position(next.offset, next.line, next.lineStart)};
        if (next.event == Event::UnsupportedCharacter)
            throw Error(DiagnosticCode::UnsupportedCharacter, "unsupported character", span);
        if (next.event == Event::InvalidByte)
            throw Error(DiagnosticCode::InvalidByteLiteral, "invalid byte literal", span);
        if (next.event == Event::InvalidString)
            throw Error(DiagnosticCode::InvalidByteStringLiteral, "invalid byte-string literal", span);
        if (next.event == Event::EndOfInput) {
            out.tokens.emplace_back("<eof>", span);
            return out;
        }
        if (next.event == Event::Token)
            out.tokens.emplace_back(out.source->text.substr(begin.offset, span.end.offset - begin.offset), span);
        else if (retention == TriviaRetention::Keep)
            out.trivia.push_back(
                {next.event == Event::Whitespace ? TriviaKind::Whitespace : TriviaKind::LineComment, span});
        input.offset = next.offset;
        input.line = next.line;
        input.lineStart = next.lineStart;
    }
}
} // namespace aurora
