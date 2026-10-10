#pragma once
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace aurora {
inline constexpr std::size_t maxByteStringBytes = 4096;
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
// Strings initialize bounded byte arrays or immutable readonly call arguments,
// not a new string value type. Raw text is UTF-8; escapes can denote arbitrary bytes.
inline std::optional<std::vector<unsigned char>> decodeByteStringLiteral(std::string_view text) {
    if (text.size() < 2 || text.front() != '"' || text.back() != '"')
        return std::nullopt;
    const auto body = text.substr(1, text.size() - 2);
    std::vector<unsigned char> bytes;
    for (std::size_t at = 0; at < body.size();) {
        const auto first = static_cast<unsigned char>(body[at]);
        if (first == '\\') {
            if (at + 1 == body.size())
                return std::nullopt;
            const std::size_t width = body[at + 1] == 'x' ? 4 : 2;
            if (width > body.size() - at)
                return std::nullopt;
            const auto value = body[at + 1] == '"' ? std::optional<unsigned char>('"')
                                                   : decodeByteLiteral("'" + std::string(body.substr(at, width)) + "'");
            if (!value)
                return std::nullopt;
            bytes.push_back(*value);
            at += width;
        } else if (first < 0x80) {
            if (first < 0x20 || first == 0x7f || first == '"')
                return std::nullopt;
            bytes.push_back(first);
            ++at;
        } else {
            const std::size_t width = first >= 0xc2 && first <= 0xdf   ? 2
                                      : first >= 0xe0 && first <= 0xef ? 3
                                      : first >= 0xf0 && first <= 0xf4 ? 4
                                                                       : 0;
            if (!width || width > body.size() - at)
                return std::nullopt;
            unsigned scalar = first & (width == 2 ? 0x1f : width == 3 ? 0x0f : 0x07);
            for (std::size_t index = 1; index < width; ++index) {
                const auto next = static_cast<unsigned char>(body[at + index]);
                if (next < 0x80 || next > 0xbf)
                    return std::nullopt;
                scalar = (scalar << 6) | (next & 0x3f);
            }
            if ((width == 3 && scalar < 0x800) || (width == 4 && scalar < 0x10000) || scalar > 0x10ffff ||
                (scalar >= 0xd800 && scalar <= 0xdfff))
                return std::nullopt;
            bytes.insert(bytes.end(), body.begin() + at, body.begin() + at + width);
            at += width;
        }
        if (bytes.size() > maxByteStringBytes)
            return std::nullopt;
    }
    return bytes;
}
} // namespace aurora
