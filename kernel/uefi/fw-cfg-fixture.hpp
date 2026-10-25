#pragma once
// QEMU fw_cfg selector for fixture images whose harness cannot send a serial
// byte: the platform fixture (firmware still owns the UART) and the IOMMU Event
// image (its serial output goes to a file). The harness adds
// -fw_cfg name=opt/aurora/fixture,string=N; the value must lie in the image's
// interval of runtime-fixtures.inc, or the read fails closed.
#include <cstddef>
#include <cstdint>
#include <optional>
namespace aurora::uefi::fw_cfg {
enum class Fixture : unsigned char {
#define AURORA_FIXTURE(name, mode, image, value) name = value,
#include "runtime-fixtures.inc"
#undef AURORA_FIXTURE
};
// Legacy I/O interface: 16-bit selector at 0x510, data bytes at 0x511.
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
    // The exact decimal selector in opt/aurora/fixture within [first, last].
    [[nodiscard]] static auto read(Fixture first, Fixture last) -> std::optional<Fixture> {
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
        if (value < static_cast<unsigned>(first) || value > static_cast<unsigned>(last))
            return std::nullopt;
        return static_cast<Fixture>(value);
    }
};
} // namespace aurora::uefi::fw_cfg
