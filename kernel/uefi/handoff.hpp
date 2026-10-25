#pragma once
#include <cstddef>
#include <cstdint>
#include <span>
#include "runtime-layout.hpp"
#if defined(AURORA_PLATFORM_FIXTURE) || defined(AURORA_DISPLAY_FIXTURE) || defined(AURORA_DEVICE_FIXTURE)
#define AURORA_LOADER_FIXTURE 1
#include "loader-fixture.hpp"
#endif
#ifdef AURORA_PLATFORM_FIXTURE
#include "platform-fixture.hpp"
#endif
namespace aurora::uefi {
class Bytes final {
    std::span<const std::byte> bytes_;

public:
    explicit constexpr Bytes(std::span<const std::byte> bytes) : bytes_(bytes) {
    }
    [[nodiscard]] auto get(std::size_t offset, unsigned width = 8) const -> std::uint64_t {
        if (width > 8 || offset > bytes_.size() || width > bytes_.size() - offset)
            return 0;
        std::uint64_t value = 0;
        for (unsigned i = 0; i < width; ++i)
            value |= std::uint64_t(std::to_integer<unsigned>(bytes_[offset + i])) << (8 * i);
        return value;
    }
};
class MemoryMap final {
    std::span<const std::byte> bytes_;
    std::size_t stride_;
    std::uint32_t version_;

public:
    static constexpr std::size_t max_bytes = 65536;
    static constexpr std::size_t max_entries = 512;
    constexpr MemoryMap(std::span<const std::byte> bytes, std::size_t stride, std::uint32_t version)
        : bytes_(bytes), stride_(stride), version_(version) {
    }
    [[nodiscard]] auto valid() const -> bool {
        if (version_ != 1 || stride_ < 40 || stride_ > 256 || stride_ % 8 != 0 || bytes_.empty() ||
            bytes_.size() > max_bytes || bytes_.size() % stride_ != 0 || bytes_.size() / stride_ > max_entries)
            return false;
        for (std::size_t i = 0; i < bytes_.size(); i += stride_) {
            const Bytes a{bytes_.subspan(i, stride_)};
            const auto start = a.get(8), pages = a.get(24);
            if (a.get(0, 4) > 15 || start % 4096 != 0 || pages == 0 || pages > (~std::uint64_t{0} - start) / 4096)
                return false;
            const auto end = start + pages * 4096;
            for (std::size_t j = 0; j < i; j += stride_) {
                const Bytes b{bytes_.subspan(j, stride_)};
                if (start < b.get(8) + b.get(24) * 4096 && b.get(8) < end)
                    return false;
            }
        }
        return true;
    }
    // Grant only pages explicitly allocated to this loader; runtime attributes always deny.
    [[nodiscard]] auto owns(std::uint64_t start, std::uint64_t size) const -> bool {
        if (!valid() || start % 4096 || size == 0 || size % 4096 || start > ~std::uint64_t{0} - size)
            return false;
        for (std::size_t i = 0; i < bytes_.size(); i += stride_) {
            const Bytes entry{bytes_.subspan(i, stride_)};
            if (entry.get(0, 4) == 1 && (entry.get(32) & (1ULL << 63)) == 0 && entry.get(8) <= start &&
                entry.get(8) + entry.get(24) * 4096 >= start + size)
                return true;
        }
        return false;
    }
};
class Handoff final {
public:
    static constexpr std::uint64_t magic = 0x41524f5255454649ULL;
#ifdef AURORA_LOADER_FIXTURE
    // A loader fixture image appends one selector word; ordinary images have none.
    static constexpr std::size_t fixture_offset = 128;
    static constexpr std::size_t header = 136;
#elif defined(AURORA_UEFI_GRAPHICAL_TERMINAL)
    // Version 7 keeps word 120 for the runtime metadata and appends word 128 for
    // the framebuffer record, so each word of this layout has one meaning.
    static constexpr std::size_t framebuffer_word = 128;
    static constexpr std::size_t header = 136;
#else
    static constexpr std::size_t header = 128;
#endif
    static constexpr std::uint64_t arena_bytes = BootstrapLayout::arena_bytes;
    static constexpr std::uint64_t map_offset = 0x1000;
    static constexpr std::uint64_t tables_offset = BootstrapLayout::kernel_tables_offset;
    static constexpr std::uint64_t table_pages = BootstrapLayout::table_pages;
    static constexpr std::uint64_t transition_offset = 0x21000;
    static constexpr std::uint64_t payload_offset = BootstrapLayout::kernel_payload_offset;
    static constexpr std::uint64_t payload_limit = BootstrapLayout::kernel_payload_limit;
    static constexpr std::uint64_t idt_offset = BootstrapLayout::kernel_idt_offset;
    static constexpr std::uint64_t stack_bottom = BootstrapLayout::kernel_stack_bottom;
    static constexpr std::uint64_t stack_top = BootstrapLayout::kernel_stack_top;
    static constexpr std::uint64_t pool_offset = 0x50000;
    static constexpr std::uint64_t bar_record_offset = 0x81000;
    static constexpr std::uint64_t framebuffer_record_offset = 0xe0000;
    [[nodiscard]] static auto valid(std::span<const std::byte> bytes, std::uint64_t actual) -> bool {
        if (bytes.size() != header)
            return false;
        const Bytes h{bytes};
#ifdef AURORA_LOADER_FIXTURE
        if (!loader_fixture::admitted(h.get(fixture_offset)))
            return false;
#endif
        // v6 requires both the copied RSDP and immutable graphics record; v7
        // requires the RSDP, the runtime metadata (word 120) and the graphics
        // record (word 128). Only the 136-byte terminal header admits v7, and it
        // admits nothing else. No version or description grants device access.
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
        if (h.get(8, 4) != 7 || h.get(framebuffer_word) != actual + framebuffer_record_offset)
            return false;
#else
        if (h.get(8, 4) == 7)
            return false;
#endif
        return h.get(0) == magic &&
               (h.get(8, 4) == 1 || h.get(8, 4) == 2 || h.get(8, 4) == 3 || h.get(8, 4) == 4 || h.get(8, 4) == 5 ||
                h.get(8, 4) == 6 || h.get(8, 4) == 7) &&
               h.get(12, 4) == header && h.get(16) == arena_bytes && h.get(24) == actual && actual >= 0x100000 &&
               actual % 4096 == 0 && actual <= 0x100000000ULL - arena_bytes && h.get(32) > 0 &&
               h.get(32) <= MemoryMap::max_bytes && h.get(40) >= 40 && h.get(40) <= 256 && h.get(48, 4) == 1 &&
               h.get(52, 4) >= 1 && h.get(52, 4) <= 3 && h.get(56) > 0 && h.get(56) <= payload_limit &&
               h.get(56) <= h.get(80) && h.get(64) > 0 && h.get(64) % 4096 == 0 && h.get(72) % 4096 == 0 &&
               h.get(80) % 4096 == 0 && h.get(64) <= h.get(72) && h.get(72) <= h.get(80) &&
               h.get(80) <= payload_limit && h.get(88) == actual + tables_offset && h.get(96) > 0 &&
               h.get(96) <= table_pages && h.get(104) == actual + payload_offset &&
               (runtime(h) ? RuntimeLayout::valid(actual) && h.get(120) == actual + RuntimeLayout::metadata_offset
                : h.get(8, 4) == 4                       ? h.get(120) == actual + bar_record_offset
                : (h.get(8, 4) == 5 || h.get(8, 4) == 6) ? h.get(120) == actual + framebuffer_record_offset
                                                         : h.get(120) == 0) &&
               ((h.get(8, 4) == 1 || h.get(8, 4) == 5) ? h.get(112) == 0 : h.get(112) > 0);
    }
    // Versions carrying the protected runtime metadata at word 120.
    [[nodiscard]] static auto runtime(const Bytes &h) -> bool {
        return h.get(8, 4) == 3 || h.get(8, 4) == 7;
    }
    // Versions carrying the immutable framebuffer record page.
    [[nodiscard]] static auto framebuffer(const Bytes &h) -> bool {
        return h.get(8, 4) == 5 || h.get(8, 4) == 6 || h.get(8, 4) == 7;
    }
};
// The graphics record page lies outside every runtime-owned kernel page, so v7
// can carry both records without one page having two owners.
static_assert(RuntimeLayoutProfile<2>::kernel_flags(Handoff::framebuffer_record_offset) == 0 &&
              RuntimeLayoutProfile<3>::kernel_flags(Handoff::framebuffer_record_offset) == 0 &&
              Handoff::framebuffer_record_offset != RuntimeLayout::metadata_offset);
inline auto put(std::span<std::byte> bytes, std::size_t at, std::uint64_t value, unsigned width = 8) -> void {
    for (unsigned i = 0; i < width; ++i)
        bytes[at + i] = std::byte(value >> (8 * i));
}
} // namespace aurora::uefi
