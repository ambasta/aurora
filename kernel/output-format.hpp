#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace aurora::console {
// Byte formatting only: the sink retains all transport and ownership policy.
template <class Sink, class Number = std::uint64_t> class OutputFormat {
public:
    static auto text(std::string_view value) -> void {
        for (const auto byte : value)
            Sink::put(static_cast<std::uint8_t>(byte));
    }
    static auto number(Number value) -> void {
        std::array<char, 20> digits{};
        std::size_t length = 0;
        do {
            digits[length++] = static_cast<char>('0' + value % 10);
            value /= 10;
        } while (value != 0);
        while (length != 0)
            Sink::put(static_cast<std::uint8_t>(digits[--length]));
    }
};
} // namespace aurora::console
