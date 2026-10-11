#pragma once
#include <cstdint>

namespace aurora::hosted_lexer {
// Private bootstrap wire values generated from compiler_lexer::Event in lexer.au.
// The independent raw-record fixture checks every current numeric wire value.
enum class Event : std::int64_t {
#include "hosted_lexer_events.inc"
};
} // namespace aurora::hosted_lexer
