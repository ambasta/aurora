#pragma once
#include "types.hpp"
#include <cctype>
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
// One scanner serves the compiler and lossless tooling. The parser consumes only
// tokens; trivia ranges retain the exact intervening source bytes for tools.
inline LexedSource
lexSource(const std::string &s, std::string path = {}, TriviaRetention retention = TriviaRetention::Keep) {
    LexedSource out;
    out.source = std::make_shared<const SourceText>(std::move(path), s);
    int line = 1;
    std::size_t lineStart = 0;
    std::size_t index = 0;
    const auto position = [&]() {
        return SourcePosition{index, line, static_cast<int>(index - lineStart + 1)};
    };
    const auto span = [&](SourcePosition begin) {
        return SourceSpan{out.source, begin, position()};
    };
    const auto trivia = [&](TriviaKind kind, SourcePosition begin) {
        if (retention == TriviaRetention::Keep)
            out.trivia.push_back({kind, span(begin)});
    };
    while (index < s.size()) {
        const auto begin = position();
        const auto byte = static_cast<unsigned char>(s[index]);
        if (std::isspace(byte)) {
            do {
                if (s[index] == '\n') {
                    ++line;
                    lineStart = index + 1;
                }
                ++index;
            } while (index < s.size() && std::isspace(static_cast<unsigned char>(s[index])));
            trivia(TriviaKind::Whitespace, begin);
            continue;
        }
        if (byte == '/' && index + 1 < s.size() && s[index + 1] == '/') {
            index += 2;
            while (index < s.size() && s[index] != '\n')
                ++index;
            trivia(TriviaKind::LineComment, begin);
            continue;
        }
        if (std::isalpha(byte) || byte == '_') {
            ++index;
            while (index < s.size() && (std::isalnum(static_cast<unsigned char>(s[index])) || s[index] == '_'))
                ++index;
            out.tokens.emplace_back(s.substr(begin.offset, index - begin.offset), span(begin));
            continue;
        }
        if (std::isdigit(byte)) {
            ++index;
            while (index < s.size() && (std::isalnum(static_cast<unsigned char>(s[index])) || s[index] == '_'))
                ++index;
            out.tokens.emplace_back(s.substr(begin.offset, index - begin.offset), span(begin));
            continue;
        }
        const auto two = s.substr(index, 2);
        if (two == "->" || two == "==" || two == "!=" || two == "<=" || two == ">=" || two == "::" || two == "<<" ||
            two == ">>" || two == "&&" || two == "||") {
            index += 2;
            out.tokens.emplace_back(two, span(begin));
            continue;
        }
        if (std::string("(){}[]:;,=+-*/%<>!.&|^~").find(byte) != std::string::npos) {
            ++index;
            out.tokens.emplace_back(std::string(1, byte), span(begin));
            continue;
        }
        ++index;
        throw Error(DiagnosticCode::UnsupportedCharacter,
                    "line " + std::to_string(line) + ": unsupported character",
                    span(begin));
    }
    out.tokens.emplace_back("<eof>", span(position()));
    return out;
}
inline std::vector<Token> lex(const std::string &s, std::string path = {}) {
    return lexSource(s, std::move(path), TriviaRetention::Discard).tokens;
}
} // namespace aurora
