#pragma once
#include "framebuffer-policy.hpp"
#include <array>

namespace aurora::uefi {
// Firmware-only adapter. Call before the final GetMemoryMap/ExitBootServices
// loop. Every QueryMode allocation is released before returning, and the only
// returned state is copied integer geometry. No GOP call belongs in the payload.
class FramebufferLoader final {
    using U64 = std::uint64_t;
    using Locate = U64(__attribute__((ms_abi)) *)(const void *, void *, void **);
    using Query = U64(__attribute__((ms_abi)) *)(void *, std::uint32_t, U64 *, void **);
    using Set = U64(__attribute__((ms_abi)) *)(void *, std::uint32_t);
    using Free = U64(__attribute__((ms_abi)) *)(void *);
    static auto view(U64 address, std::size_t size) -> std::span<const std::byte> {
        return {reinterpret_cast<const std::byte *>(address), size};
    }
    [[nodiscard]] static auto supported(const Bytes &info) -> bool {
        const auto width = info.get(4, 4), height = info.get(8, 4), pitch = info.get(32, 4);
        return info.get(0, 4) == 0 && width && width <= FramebufferGeometry::max_width && height &&
               height <= FramebufferGeometry::max_height && pitch >= width && pitch <= FramebufferGeometry::max_pitch &&
               info.get(12, 4) <= 1;
    }

public:
    [[nodiscard]] static auto capture(const Bytes &boot, unsigned physical_bits) -> std::optional<FramebufferResource> {
        if (!boot.get(320) || !boot.get(72))
            return std::nullopt;
        const std::array<std::byte, 16> guid{std::byte{0xde},
                                             std::byte{0xa9},
                                             std::byte{0x42},
                                             std::byte{0x90},
                                             std::byte{0xdc},
                                             std::byte{0x23},
                                             std::byte{0x38},
                                             std::byte{0x4a},
                                             std::byte{0x96},
                                             std::byte{0xfb},
                                             std::byte{0x7a},
                                             std::byte{0xde},
                                             std::byte{0xd0},
                                             std::byte{0x80},
                                             std::byte{0x51},
                                             std::byte{0x6a}};
        void *protocol = nullptr;
        if (reinterpret_cast<Locate>(boot.get(320))(guid.data(), nullptr, &protocol) || !protocol)
            return std::nullopt;
        const auto address = reinterpret_cast<U64>(protocol);
        if (address % 8)
            return std::nullopt;
        const Bytes gop{view(address, 32)};
        if (!gop.get(0) || !gop.get(8) || !gop.get(24) || gop.get(24) % 8)
            return std::nullopt;
        const Bytes mode{view(gop.get(24), 40)};
        const auto count = mode.get(0, 4);
        if (!count || count > 64 || mode.get(4, 4) >= count)
            return std::nullopt;
        std::optional<std::uint32_t> selected;
        // Prefer 800x600; otherwise select the first bounded mode. A successful
        // QueryMode buffer is copied/inspected synchronously and always freed.
        for (std::uint32_t index = 0; index < count; ++index) {
            U64 size = 0;
            void *info = nullptr;
            if (reinterpret_cast<Query>(gop.get(0))(protocol, index, &size, &info))
                return std::nullopt;
            if (!info)
                return std::nullopt;
            bool suitable = false, preferred = false;
            if (size >= 36 && size <= 4096) {
                const Bytes candidate{view(reinterpret_cast<U64>(info), 36)};
                suitable = supported(candidate);
                preferred = suitable && candidate.get(4, 4) == 800 && candidate.get(8, 4) == 600;
            }
            if (reinterpret_cast<Free>(boot.get(72))(info))
                return std::nullopt;
            if (suitable && (!selected || preferred))
                selected = index;
            if (preferred)
                break;
        }
        if (!selected || reinterpret_cast<Set>(gop.get(8))(protocol, *selected))
            return std::nullopt;
        // Re-read protocol and current mode after SetMode; it may replace Info.
        const Bytes after{view(address, 32)};
        if (!after.get(24) || after.get(24) % 8)
            return std::nullopt;
        const Bytes current{view(after.get(24), 40)};
        if (current.get(0, 4) != count || current.get(4, 4) != *selected || !current.get(8) || current.get(16) < 36 ||
            current.get(16) > 4096)
            return std::nullopt;
        const Bytes info{view(current.get(8), 36)};
        if (!supported(info))
            return std::nullopt;
        const auto geometry = FramebufferGeometry::parse(current.get(24),
                                                         current.get(32),
                                                         info.get(4, 4),
                                                         info.get(8, 4),
                                                         info.get(32, 4),
                                                         info.get(12, 4),
                                                         physical_bits);
        if (!geometry)
            return std::nullopt;
        return FramebufferResource{FramebufferDescription{*geometry, *selected, static_cast<std::uint32_t>(count)}};
    }
};
} // namespace aurora::uefi
