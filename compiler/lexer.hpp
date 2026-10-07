#pragma once
#include "types.hpp"
#include <cctype>
#include <vector>
namespace aurora {
inline std::vector<Token> lex(const std::string &s, std::string path = {}) {
    std::vector<Token> out;
    const auto source = std::make_shared<const SourceText>(std::move(path), s);
    int line = 1;
    std::size_t lineStart = 0;
    const auto span = [&](std::size_t begin, std::size_t end) {
        return SourceSpan{source,
                          {begin, line, static_cast<int>(begin - lineStart + 1)},
                          {end, line, static_cast<int>(end - lineStart + 1)}};
    };
    for (std::size_t i = 0; i < s.size();) {
        unsigned char c = s[i];
        if (std::isspace(c)) {
            if (c == '\n') {
                ++line;
                lineStart = i + 1;
            }
            ++i;
            continue;
        }
        if (c == '/' && i + 1 < s.size() && s[i + 1] == '/') {
            while (i < s.size() && s[i] != '\n')
                ++i;
            continue;
        }
        if (std::isalpha(c) || c == '_') {
            auto b = i++;
            while (i < s.size() && (std::isalnum(static_cast<unsigned char>(s[i])) || s[i] == '_'))
                ++i;
            out.emplace_back(s.substr(b, i - b), span(b, i));
            continue;
        }
        if (std::isdigit(c)) {
            auto b = i++;
            while (i < s.size() && (std::isalnum(static_cast<unsigned char>(s[i])) || s[i] == '_'))
                ++i;
            out.emplace_back(s.substr(b, i - b), span(b, i));
            continue;
        }
        auto two = s.substr(i, 2);
        if (two == "->" || two == "==" || two == "!=" || two == "<=" || two == ">=" || two == "::" || two == "<<" ||
            two == ">>" || two == "&&" || two == "||") {
            out.emplace_back(two, span(i, i + 2));
            i += 2;
            continue;
        }
        if (std::string("(){}[]:;,=+-*/%<>!.&|^~").find(c) != std::string::npos) {
            out.emplace_back(std::string(1, c), span(i, i + 1));
            ++i;
            continue;
        }
        throw Error(DiagnosticCode::UnsupportedCharacter,
                    "line " + std::to_string(line) + ": unsupported character",
                    span(i, i + 1));
    }
    out.emplace_back("<eof>", span(s.size(), s.size()));
    return out;
}

} // namespace aurora
