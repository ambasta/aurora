#pragma once
#include <cstdint>

namespace aurora::hosted_lexer {
// Private bootstrap wire values. Keep these in sync with compiler_lexer::Event
// in lexer.au; tests/compiler/hosted_lexer.cpp exercises every generated case.
// Aurora enum cases use declaration order and do not support explicit values.
enum class Event : std::int64_t {
    Token = 0,
    Whitespace = 1,
    LineComment = 2,
    EndOfInput = 3,
    UnsupportedCharacter = 4,
    InvalidByte = 5,
    InvalidString = 6,
    InvalidCursor = 7,
};
} // namespace aurora::hosted_lexer
