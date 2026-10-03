#pragma once
#include "types.hpp"
#include <cctype>
#include <vector>
namespace aurora {
inline std::vector<Token> lex(const std::string &s) {
    std::vector<Token> out;
    int line = 1;
    for (std::size_t i = 0; i < s.size();) {
        unsigned char c = s[i];
        if (std::isspace(c)) {
            if (c == '\n')
                ++line;
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
            out.emplace_back(s.substr(b, i - b), line);
            continue;
        }
        if (std::isdigit(c)) {
            auto b = i++;
            while (i < s.size() && std::isdigit(static_cast<unsigned char>(s[i])))
                ++i;
            out.emplace_back(s.substr(b, i - b), line);
            continue;
        }
        auto two = s.substr(i, 2);
        if (two == "->" || two == "==" || two == "!=" || two == "<=" || two == ">=" ||
            two == "::") {
            out.emplace_back(two, line);
            i += 2;
            continue;
        }
        if (std::string("(){}[]:;,=+-*<>!.").find(c) != std::string::npos) {
            out.emplace_back(std::string(1, c), line);
            ++i;
            continue;
        }
        throw Error("line " + std::to_string(line) + ": unsupported character");
    }
    out.emplace_back("<eof>", line);
    return out;
}

} // namespace aurora
