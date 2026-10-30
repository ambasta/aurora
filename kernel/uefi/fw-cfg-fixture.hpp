#pragma once
// QEMU fw_cfg selector for fixture images whose harness cannot send a serial
// byte: the loader fixture images (loader-fixture.hpp; firmware still owns the
// UART, and console sessions are interactive) and the IOMMU Event image (its
// serial output goes to a file). The harness adds
// -fw_cfg name=opt/aurora/fixture,string=N; the value must lie in the image's
// interval of runtime-fixtures.inc, or the read fails closed.
#include <cstddef>
#include <cstdint>
#include <optional>
#include <array>
#include <span>
#include <string_view>
namespace aurora::uefi::fw_cfg {
enum class Fixture : unsigned char {
#define AURORA_FIXTURE(name, mode, image, value) name = value,
#include "runtime-fixtures.inc"
#undef AURORA_FIXTURE
};
// Legacy I/O interface: 16-bit selector at 0x510, data bytes at 0x511.
enum class Storage {
    ram,
    nvme,
    nvme_linux_6_12_clean,
    nvme_linux_6_12_recover,
    nvme_linux_6_12_write
};
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
    [[nodiscard]] static auto storage_word(std::span<const std::byte> value) -> std::optional<Storage> {
        // QEMU system/vl.c parse_fw_cfg uses strlen: the CLI string excludes NUL.
        if (value.size() != 4 && value.size() != 21 && value.size() != 23)
            return std::nullopt;
        constexpr std::string_view names[] = {
            "nvme", "nvme-linux-6.12-clean", "nvme-linux-6.12-recover", "nvme-linux-6.12-write"};
        for (unsigned kind = 0; kind < 4; ++kind) {
            const auto name = names[kind];
            if (value.size() != name.size())
                continue;
            bool same = true;
            for (std::size_t i = 0; same && i < value.size(); ++i)
                same = value[i] == static_cast<std::byte>(name[i]);
            if (same)
                return static_cast<Storage>(kind + 1);
        }
        return std::nullopt;
    }
#if defined(AURORA_PRODUCTION) && defined(AURORA_UEFI_NVME)
    // Explicit production opt-in, independent of fixture/case selectors. No
    // fw_cfg provider or an absent file keeps the ordinary RAM composition.
    [[nodiscard]] static auto read_storage() -> std::optional<Storage> {
        select(0);
        bool provider = true;
        for (unsigned i = 0; i < 4; ++i)
            provider = (byte() == static_cast<unsigned char>("QEMU"[i])) && provider;
        if (!provider)
            return Storage::ram;
        static constexpr char wanted[] = "opt/aurora/storage";
        select(0x19);
        const auto count = big(4);
        if (count > 4096)
            return std::nullopt;
        std::optional<std::uint16_t> key;
        std::uint32_t selected_size{};
        for (std::uint32_t entry = 0; entry < count; ++entry) {
            const auto size = big(4);
            const auto selector = static_cast<std::uint16_t>(big(2));
            const auto reserved = big(2);
            bool match = true, padded = true;
            for (std::size_t i = 0; i < 56; ++i) {
                const auto value = byte();
                if (i < sizeof(wanted))
                    match = (value == static_cast<unsigned char>(wanted[i])) && match;
                else
                    padded = (value == 0) && padded;
            }
            if (match) {
                if (!padded || key || reserved || (size != 4 && size != 21 && size != 23) || selector < 0x20 ||
                    selector >= 0x4000)
                    return std::nullopt;
                key = selector;
                selected_size = size;
            }
        }
        if (!key)
            return Storage::ram;
        select(*key);
        std::array<std::byte, 23> value{};
        for (std::uint32_t i = 0; i < selected_size; ++i)
            value[i] = static_cast<std::byte>(byte());
        return storage_word(std::span{value}.first(selected_size));
    }
#endif
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
#if defined(AURORA_PROCESS_FIXTURE) || defined(AURORA_UEFI_NVME)
    // The image's case word: the decimal 1..255 in opt/aurora/case,
    // 0 when the file is absent (process.md#guest-rows), nullopt otherwise.
    [[nodiscard]] static auto read_case() -> std::optional<unsigned> {
        static constexpr char wanted[] = "opt/aurora/case";
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
        if (!key)
            return 0U;
        if (size == 0 || size > 4)
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
        if (value == 0 || value > 255)
            return std::nullopt;
        return value;
    }
#endif
};
} // namespace aurora::uefi::fw_cfg
