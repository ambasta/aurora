#pragma once
// The Aurora lexer's events for a whole source, read through its private bridge
// entry. Test drivers derive tokens, trivia and positions from these rows.
#include "hosted_frontend_abi.hpp"
#include <cstdint>
#include <stdexcept>
#include <string_view>
#include <vector>

namespace aurora::lexemes {
using Event = hosted_abi::compiler_lexer::Event;
class Lexeme {
public:
    Event event;
    // Byte offsets and one-based line/byte-column coordinates.
    std::int64_t begin, end, line, column, endLine, endColumn;
    bool trivia() const {
        return event == Event::whitespace || event == Event::line_comment;
    }
};
// Every event through end of input or the first rejection, which comes last.
inline std::vector<Lexeme> scan(std::string_view text) {
    hosted_abi::LexerInput input;
    input.source.backing = text.data();
    input.source.length = static_cast<std::int64_t>(text.size());
    input.cursor.line = 1;
    std::vector<Lexeme> out;
    for (;;) {
        hosted_abi::compiler_lexer::Lexeme next;
        aurora_hosted_lexer_invoke(&input, &next);
        const auto &at = input.cursor;
        out.push_back({next.event,
                       at.offset,
                       next.offset,
                       at.line,
                       at.offset - at.line_start + 1,
                       next.line,
                       next.offset - next.line_start + 1});
        if (next.event != Event::token && !out.back().trivia())
            return out;
        if (next.offset <= at.offset)
            throw std::runtime_error("lexer event consumed no bytes");
        input.cursor = {next.offset, next.line, next.line_start};
    }
}
// The tokens alone, ending with the zero-width end of input.
inline std::vector<Lexeme> tokens(std::string_view text) {
    std::vector<Lexeme> out;
    for (const auto &lexeme : scan(text))
        if (!lexeme.trivia())
            out.push_back(lexeme);
    if (out.empty() || out.back().event != Event::end_of_input)
        throw std::runtime_error("source does not lex");
    return out;
}
} // namespace aurora::lexemes
