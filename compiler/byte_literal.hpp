#pragma once
#include <optional>
#include <string_view>

namespace aurora {
// A byte spelling always denotes u8. Keep decoding shared by the scanner and
// semantic constants; source tokens retain their exact spelling and byte span.
inline std::optional<unsigned char> decodeByteLiteral(std::string_view text) {
    if (text.size() < 3 || text.front() != '\'' || text.back() != '\'')
        return std::nullopt;
    const auto body = text.substr(1, text.size() - 2);
    if (body.size() == 1) {
        const auto value = static_cast<unsigned char>(body[0]);
        if (value >= 0x20 && value <= 0x7e && value != '\'' && value != '\\')
            return value;
        return std::nullopt;
    }
    if (body.front() != '\\')
        return std::nullopt;
    if (body.size() == 2) {
        switch (body[1]) {
        case '\'':
            return '\'';
        case '\\':
            return '\\';
        case '0':
            return 0;
        case 'a':
            return 7;
        case 'b':
            return 8;
        case 'f':
            return 12;
        case 'n':
            return 10;
        case 'r':
            return 13;
        case 't':
            return 9;
        case 'v':
            return 11;
        default:
            return std::nullopt;
        }
    }
    if (body.size() != 4 || body[1] != 'x')
        return std::nullopt;
    const auto hex = [](char c) -> int {
        if (c >= '0' && c <= '9')
            return c - '0';
        if (c >= 'a' && c <= 'f')
            return c - 'a' + 10;
        if (c >= 'A' && c <= 'F')
            return c - 'A' + 10;
        return -1;
    };
    const auto high = hex(body[2]), low = hex(body[3]);
    if (high < 0 || low < 0)
        return std::nullopt;
    return static_cast<unsigned char>(high * 16 + low);
}
} // namespace aurora
