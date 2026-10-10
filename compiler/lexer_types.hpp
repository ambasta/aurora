#pragma once
#include "types.hpp"
#include <vector>

namespace aurora {
enum class TriviaKind {
    Whitespace,
    LineComment
};
enum class TriviaRetention {
    Discard,
    Keep
};
class Trivia {
public:
    TriviaKind kind;
    SourceSpan span;
};
class LexedSource {
public:
    std::shared_ptr<const SourceText> source;
    std::vector<Token> tokens;
    std::vector<Trivia> trivia;
};
} // namespace aurora
