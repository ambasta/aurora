#pragma once
#include <cstddef>
#include <cstdint>
#include <span>

namespace aurora::memory {
// Bounded decoder for the disposable BIOS handoff, not a native firmware ABI.
class FirmwareMemory final {
    static auto little(std::span<const std::byte> bytes, std::size_t offset, unsigned width) -> std::uint64_t {
        auto value = std::uint64_t{0};
        for (auto index = 0U; index < width; ++index)
            value |= std::to_integer<std::uint64_t>(bytes[offset + index]) << (index * 8);
        return value;
    }

public:
    [[nodiscard]] static auto grants(std::span<const std::byte> bytes, std::uint64_t start, std::uint64_t end) -> bool {
        if (start >= end || bytes.size() < 8)
            return false;
        const auto count = little(bytes, 0, 2);
        if (count == 0 || count > 32 || bytes.size() < 8 + count * 24)
            return false;
        auto covered = false;
        for (std::size_t index = 0; index < count; ++index) {
            const auto entry = 8 + index * 24;
            const auto base = little(bytes, entry, 8);
            const auto length = little(bytes, entry + 8, 8);
            const auto type = little(bytes, entry + 16, 4);
            const auto attributes = little(bytes, entry + 20, 4);
            if ((attributes & 1) == 0 || length == 0)
                continue;
            if (base > UINT64_MAX - length)
                return false;
            if (base < end && base + length > start && type != 1)
                return false;
            if (type == 1 && base <= start && base + length >= end)
                covered = true;
        }
        return covered;
    }
};
} // namespace aurora::memory
