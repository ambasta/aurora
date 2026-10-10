// Test-only C++ seed/reference oracle for the bounded std.token_scan library.
// Production hosted tools select compiler/lexer.au through AURORA_HOSTED_LEXER.
#include "lexer.hpp"
#include <clocale>
#include <fstream>
#include <iostream>
#include <string>

namespace {
int nibble(char c) {
    if (c >= '0' && c <= '9')
        return c - '0';
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    return -1;
}
std::string hex(const std::string &text) {
    constexpr char digits[] = "0123456789abcdef";
    std::string out;
    out.reserve(text.size() * 2);
    for (unsigned char c : text) {
        out += digits[c >> 4];
        out += digits[c & 15];
    }
    return out;
}
} // namespace

int main(int argc, char **argv) {
    if (argc != 2 || std::setlocale(LC_ALL, "C") == nullptr)
        return 2;
    std::ifstream input(argv[1], std::ios::binary);
    if (!input)
        return 2;
    std::string encoded;
    std::size_t index = 0, total = 0;
    while (std::getline(input, encoded)) {
        total += encoded.size() + 1;
        if (++index > 4096 || total > (1U << 20) || encoded.size() > 8192 || encoded.size() % 2)
            return 2;
        std::string source;
        source.reserve(encoded.size() / 2);
        for (std::size_t i = 0; i < encoded.size(); i += 2) {
            const int high = nibble(encoded[i]), low = nibble(encoded[i + 1]);
            if (high < 0 || low < 0)
                return 2;
            source += static_cast<char>((high << 4) | low);
        }
        try {
            const auto tokens = aurora::lex(source);
            std::cout << "valid " << index - 1 << ' ' << tokens.size() << '\n';
            for (const auto &token : tokens)
                std::cout << token.line << ' ' << hex(token.text) << '\n';
        } catch (const aurora::Error &) {
            // Recovery and invalid-byte progress belong to the Aurora library;
            // the unchanged host lexer throws instead, and that is tested apart.
            std::cout << "invalid " << index - 1 << '\n';
        }
    }
    if (!input.eof() || !std::cout)
        return 2;
    return 0;
}
