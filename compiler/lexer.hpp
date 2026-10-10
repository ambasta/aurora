#pragma once
#include "lexer_types.hpp"
#include "byte_literal.hpp"
#ifndef AURORA_HOSTED_LEXER
#include "lexer_reference.hpp"
#endif

namespace aurora {
#ifdef AURORA_HOSTED_LEXER
LexedSource lexSource(std::shared_ptr<const SourceText> source, TriviaRetention retention = TriviaRetention::Keep);
#else
// Only stage 0 and explicitly selected C++ reference fixtures use this branch.
inline LexedSource lexSource(std::shared_ptr<const SourceText> source,
                             TriviaRetention retention = TriviaRetention::Keep) {
    return lexSourceReference(std::move(source), retention);
}
#endif
inline LexedSource
lexSource(const std::string &s, std::string path = {}, TriviaRetention retention = TriviaRetention::Keep) {
    return lexSource(std::make_shared<const SourceText>(std::move(path), s), retention);
}
inline std::vector<Token> lex(std::shared_ptr<const SourceText> source) {
    return lexSource(std::move(source), TriviaRetention::Discard).tokens;
}
inline std::vector<Token> lex(const std::string &s, std::string path = {}) {
    return lexSource(s, std::move(path), TriviaRetention::Discard).tokens;
}
} // namespace aurora
