// Trusted hosted bootstrap import boundary; no foreign pointer constructor is
// exposed by Aurora. Immutable SourceText stays alive through every invocation.
#include "lexer.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

#ifndef AURORA_HOSTED_LEXER
#error The hosted lexer adapter requires AURORA_HOSTED_LEXER
#endif
extern "C" void aurora_hosted_lexer_invoke(const void *input, void *output);

namespace aurora {
namespace {
// Literal private ABI layout, checked separately against the emitted assembly.
// Contiguous span: kind, backing, three reserved words, start, length.
// Cursor and result are copied values, never descriptors or borrowed views.
class Input {
public:
    std::uint64_t kind = 0;
    const char *backing;
    std::array<std::uint64_t, 3> reserved{};
    std::int64_t start = 0;
    std::int64_t length;
    std::int64_t offset = 0;
    std::int64_t line = 1;
    std::int64_t lineStart = 0;
};
class Output {
public:
    std::int64_t event = -1;
    std::int64_t offset = -1;
    std::int64_t line = -1;
    std::int64_t lineStart = -1;
};
static_assert(sizeof(void *) == 8 && sizeof(Input) == 80 && sizeof(Output) == 32);
static_assert(offsetof(Input, backing) == 8 && offsetof(Input, start) == 40 && offsetof(Input, length) == 48 &&
              offsetof(Input, offset) == 56 && offsetof(Input, line) == 64 && offsetof(Input, lineStart) == 72);
static_assert(offsetof(Output, event) == 0 && offsetof(Output, offset) == 8 && offsetof(Output, line) == 16 &&
              offsetof(Output, lineStart) == 24);

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
        if (next.event < 0 || next.event > 6 || next.offset < input.offset || next.offset > input.length ||
            next.line < input.line || next.line - input.line > next.offset - input.offset ||
            next.lineStart < input.lineStart || next.lineStart > next.offset ||
            (next.line == input.line && next.lineStart != input.lineStart) ||
            (next.line != input.line && next.lineStart <= input.offset) ||
            (next.event != 1 && (next.line != input.line || next.lineStart != input.lineStart)) ||
            (next.event == 3 ? (input.offset != input.length || next.offset != input.offset)
                             : next.offset == input.offset))
            throw Error(DiagnosticCode::Internal, "hosted lexer returned an invalid event");
        const SourceSpan span{out.source, begin, position(next.offset, next.line, next.lineStart)};
        if (next.event == 4)
            throw Error(DiagnosticCode::UnsupportedCharacter, "unsupported character", span);
        if (next.event == 5)
            throw Error(DiagnosticCode::InvalidByteLiteral, "invalid byte literal", span);
        if (next.event == 6)
            throw Error(DiagnosticCode::InvalidByteStringLiteral, "invalid byte-string literal", span);
        if (next.event == 3) {
            out.tokens.emplace_back("<eof>", span);
            return out;
        }
        if (next.event == 0)
            out.tokens.emplace_back(out.source->text.substr(begin.offset, span.end.offset - begin.offset), span);
        else if (retention == TriviaRetention::Keep)
            out.trivia.push_back({next.event == 1 ? TriviaKind::Whitespace : TriviaKind::LineComment, span});
        input.offset = next.offset;
        input.line = next.line;
        input.lineStart = next.lineStart;
    }
}
} // namespace aurora
