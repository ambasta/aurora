#pragma once
#include "framebuffer-policy.hpp"

namespace aurora::uefi {
enum class FramebufferPixelResult : std::uint64_t {
    success,
    out_of_bounds
};

// The authenticated service supplies its immutable admission. The reusable
// checked operation knows no strings, glyphs, colors, cursor or layout policy.
// Store is a closed host adapter, never a source-selected callback or symbol.
template <class Store> class FramebufferPixels final {
public:
    [[nodiscard]] static auto pixel(const FramebufferAdmission &admission,
                                    std::uint64_t x,
                                    std::uint64_t y,
                                    std::uint8_t red,
                                    std::uint8_t green,
                                    std::uint8_t blue) -> FramebufferPixelResult {
        const auto &geometry = admission.geometry();
        const auto offset = geometry.pixel_offset(x, y);
        if (!offset || *offset > geometry.mapped_bytes() - 4)
            return FramebufferPixelResult::out_of_bounds;
        Store::write(*offset, geometry.pack(red, green, blue));
        return FramebufferPixelResult::success;
    }
};

// Only the service's authenticated operation calls this fixed-window adapter.
// Exact leaf permissions and absence of aliases are proved before opening the
// session; quiet single-threaded execution preserves them until close/recheck.
class FramebufferMmio final {
    template <class Store> friend class FramebufferPixels;
    static auto write(std::uint64_t offset, std::uint32_t packed) -> void {
        *reinterpret_cast<volatile std::uint32_t *>(FramebufferAdmission::virtual_address + offset) = packed;
    }

public:
    static auto complete() -> void {
        // Orders CPU stores before the completion marker/capture boundary. This
        // is not a display-device fence, vblank or tear-free presentation claim.
        asm volatile("mfence" : : : "memory");
    }
};
} // namespace aurora::uefi
