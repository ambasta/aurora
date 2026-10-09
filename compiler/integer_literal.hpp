#pragma once
#include <cstdint>
#include <limits>
#include <optional>
#include <string_view>

namespace aurora {
// Decode an unsigned magnitude after the exact type suffix has been removed.
// Decimal spelling stays unchanged; binary permits C++ digit separators only
// between digits. The caller applies the scalar type's range (including -2^63).
inline std::optional<std::uint64_t> decodeIntegerMagnitude(std::string_view text) {
    const bool binary = text.starts_with("0b") || text.starts_with("0B");
    if (binary)
        text.remove_prefix(2);
    if (text.empty())
        return std::nullopt;
    const unsigned base = binary ? 2 : 10;
    std::uint64_t value = 0;
    bool previousDigit = false;
    for (const char byte : text) {
        if (binary && byte == '\'') {
            if (!previousDigit)
                return std::nullopt;
            previousDigit = false;
            continue;
        }
        if (byte < '0' || byte > (binary ? '1' : '9'))
            return std::nullopt;
        const unsigned digit = byte - '0';
        if (value > (std::numeric_limits<std::uint64_t>::max() - digit) / base)
            return std::nullopt;
        value = value * base + digit;
        previousDigit = true;
    }
    return previousDigit ? std::optional(value) : std::nullopt;
}
} // namespace aurora
