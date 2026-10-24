#pragma once
// Included only by the early-fixture image. Its loader-stage faults inject before
// ExitBootServices, while OVMF's terminal driver still owns the UART, so the
// selector arrives in a QEMU fw_cfg file read at loader entry instead of a
// serial byte. The loader copies the one admitted value into the handoff's
// fixture word; the payload rejects any handoff whose word is outside the family.
#ifndef AURORA_EARLY_FIXTURE
#error "The fw_cfg selector belongs only to the early-fixture image"
#endif
#include <cstddef>
#include <cstdint>
#include <optional>
namespace aurora::uefi::early {
enum class Fixture : unsigned char {
#define AURORA_FIXTURE(name, mode, image, value) name = value,
#include "runtime-fixtures.inc"
#undef AURORA_FIXTURE
};
inline constexpr auto first = Fixture::early_stale;
inline constexpr auto last = Fixture::early_nx;
[[nodiscard]] constexpr auto admitted(std::uint64_t value) -> bool {
    return value >= static_cast<unsigned>(first) && value <= static_cast<unsigned>(last);
}
[[nodiscard]] constexpr auto selected(std::uint64_t value, Fixture fixture) -> bool {
    return admitted(value) && value == static_cast<unsigned>(fixture);
}
// QEMU fw_cfg legacy I/O interface: 16-bit selector at 0x510, data bytes at 0x511.
class FwCfg final {
    static auto select(std::uint16_t key) -> void {
        asm volatile("outw %0, %1" : : "a"(key), "Nd"(std::uint16_t{0x510}) : "memory");
    }
    static auto byte() -> unsigned {
        unsigned char value;
        asm volatile("inb %1, %0" : "=a"(value) : "Nd"(std::uint16_t{0x511}) : "memory");
        return value;
    }
    static auto big(unsigned bytes) -> std::uint32_t {
        std::uint32_t value = 0;
        for (unsigned i = 0; i < bytes; ++i)
            value = (value << 8) | byte();
        return value;
    }

public:
    // The exact decimal selector in opt/aurora/fixture; anything else fails closed.
    [[nodiscard]] static auto read() -> std::optional<Fixture> {
        static constexpr char signature[] = "QEMU";
        static constexpr char wanted[] = "opt/aurora/fixture";
        select(0);
        for (unsigned i = 0; i < 4; ++i)
            if (byte() != static_cast<unsigned char>(signature[i]))
                return std::nullopt;
        select(0x19);
        const auto count = big(4);
        if (count > 4096)
            return std::nullopt;
        std::optional<std::uint16_t> key;
        std::uint32_t size = 0;
        for (std::uint32_t entry = 0; entry < count; ++entry) {
            const auto entry_size = big(4);
            const auto entry_key = static_cast<std::uint16_t>(big(2));
            static_cast<void>(big(2));
            bool match = true;
            for (std::size_t i = 0; i < 56; ++i) {
                const auto expected = i < sizeof(wanted) ? static_cast<unsigned char>(wanted[i]) : 0U;
                const auto actual = byte();
                match = match && (i >= sizeof(wanted) || actual == expected);
            }
            if (match) {
                if (key)
                    return std::nullopt;
                key = entry_key;
                size = entry_size;
            }
        }
        // At most three digits, optionally followed by one terminating NUL.
        if (!key || size == 0 || size > 4)
            return std::nullopt;
        select(*key);
        unsigned value = 0;
        for (std::uint32_t i = 0; i < size; ++i) {
            const auto digit = byte();
            if (digit == 0 && i > 0 && i + 1 == size)
                break;
            if (i == 3 || digit < '0' || digit > '9' || (i == 0 && digit == '0'))
                return std::nullopt;
            value = value * 10 + (digit - '0');
        }
        if (!admitted(value))
            return std::nullopt;
        return static_cast<Fixture>(value);
    }
};
} // namespace aurora::uefi::early
