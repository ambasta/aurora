#pragma once
#include "handoff.hpp"
#include <optional>

namespace aurora::uefi {
// Copied layout describes pixels; it grants no mapping or write authority.
class FramebufferGeometry final {
    std::uint64_t base_{}, resource_bytes_{}, visible_bytes_{}, mapped_bytes_{};
    std::uint32_t width_{}, height_{}, pitch_{}, format_{};
    FramebufferGeometry() = default;

public:
    static constexpr std::uint64_t page_size = 4096;
    static constexpr std::uint32_t max_width = 1024, max_height = 768, max_pitch = 1024;
    static constexpr std::uint64_t max_mapped_bytes = 3 * 1024 * 1024;
    [[nodiscard]] static auto parse(std::uint64_t base,
                                    std::uint64_t resource_bytes,
                                    std::uint32_t width,
                                    std::uint32_t height,
                                    std::uint32_t pitch,
                                    std::uint32_t format,
                                    unsigned physical_bits) -> std::optional<FramebufferGeometry> {
        if (physical_bits < 32 || physical_bits > 52 || !base || base % page_size || !width || width > max_width ||
            !height || height > max_height || pitch < width || pitch > max_pitch || format > 1)
            return std::nullopt;
        const auto limit = std::uint64_t{1} << physical_bits;
        if (base >= limit || !resource_bytes || resource_bytes > limit - base)
            return std::nullopt;
        // Bounded factors make multiplication and round-up independently safe.
        // Full mapped pages must fit inside the exact reported resource.
        const auto visible = std::uint64_t{pitch} * 4 * height;
        const auto mapped = (visible + page_size - 1) & ~(page_size - 1);
        if (mapped > resource_bytes || mapped > max_mapped_bytes)
            return std::nullopt;
        FramebufferGeometry result;
        result.base_ = base;
        result.resource_bytes_ = resource_bytes;
        result.visible_bytes_ = visible;
        result.mapped_bytes_ = mapped;
        result.width_ = width;
        result.height_ = height;
        result.pitch_ = pitch;
        result.format_ = format;
        return result;
    }
    [[nodiscard]] auto base() const -> std::uint64_t {
        return base_;
    }
    [[nodiscard]] auto resource_bytes() const -> std::uint64_t {
        return resource_bytes_;
    }
    [[nodiscard]] auto visible_bytes() const -> std::uint64_t {
        return visible_bytes_;
    }
    [[nodiscard]] auto mapped_bytes() const -> std::uint64_t {
        return mapped_bytes_;
    }
    [[nodiscard]] auto width() const -> std::uint32_t {
        return width_;
    }
    [[nodiscard]] auto height() const -> std::uint32_t {
        return height_;
    }
    [[nodiscard]] auto pitch() const -> std::uint32_t {
        return pitch_;
    }
    [[nodiscard]] auto format() const -> std::uint32_t {
        return format_;
    }
    [[nodiscard]] auto pixel_offset(std::uint64_t x, std::uint64_t y) const -> std::optional<std::uint64_t> {
        if (x >= width_ || y >= height_)
            return std::nullopt;
        return (y * pitch_ + x) * 4;
    }
    [[nodiscard]] auto pack(std::uint8_t red, std::uint8_t green, std::uint8_t blue) const -> std::uint32_t {
        return (std::uint32_t{green} << 8) | (format_ == 0 ? std::uint32_t{red} | (std::uint32_t{blue} << 16)
                                                           : std::uint32_t{blue} | (std::uint32_t{red} << 16));
    }
};

// Copied selected-mode description; decoding it grants no mapping authority.
class FramebufferDescription final {
    friend class FramebufferLoader;
    friend class FramebufferRecord;
    FramebufferGeometry geometry_;
    std::uint32_t mode_, mode_count_;
    FramebufferDescription(const FramebufferGeometry &geometry, std::uint32_t mode, std::uint32_t count)
        : geometry_(geometry), mode_(mode), mode_count_(count) {
    }

public:
    [[nodiscard]] auto geometry() const -> const FramebufferGeometry & {
        return geometry_;
    }
    [[nodiscard]] auto mode() const -> std::uint32_t {
        return mode_;
    }
    [[nodiscard]] auto mode_count() const -> std::uint32_t {
        return mode_count_;
    }
};

// Source-bound resource. Record parsing cannot construct this type. The loader
// constructs it from the live GOP result; future payload restoration must first
// establish current-root, owned-RO record and complete-tree provenance.
class FramebufferResource final {
    friend class FramebufferLoader;
    friend class FramebufferPayload;
    FramebufferDescription description_;
    explicit FramebufferResource(const FramebufferDescription &description) : description_(description) {
    }

public:
    [[nodiscard]] auto description() const -> const FramebufferDescription & {
        return description_;
    }
    [[nodiscard]] auto geometry() const -> const FramebufferGeometry & {
        return description_.geometry();
    }
    [[nodiscard]] auto mode() const -> std::uint32_t {
        return description_.mode();
    }
    [[nodiscard]] auto mode_count() const -> std::uint32_t {
        return description_.mode_count();
    }
};

// Endian-explicit copied record, with no firmware function or protocol pointer.
class FramebufferRecord final {
public:
    static constexpr std::uint64_t magic = 0x4155524642523031ULL;
    static constexpr std::size_t bytes = 64;
    [[nodiscard]] static auto parse(std::span<const std::byte> record, unsigned physical_bits)
        -> std::optional<FramebufferDescription> {
        if (record.size() != bytes)
            return std::nullopt;
        const Bytes r{record};
        if (r.get(0) != magic || r.get(8, 4) != 1 || r.get(12, 4) != bytes || !r.get(52, 4) || r.get(52, 4) > 64 ||
            r.get(48, 4) >= r.get(52, 4) || r.get(56))
            return std::nullopt;
        const auto geometry = FramebufferGeometry::parse(
            r.get(16), r.get(24), r.get(32, 4), r.get(36, 4), r.get(40, 4), r.get(44, 4), physical_bits);
        if (!geometry)
            return std::nullopt;
        return FramebufferDescription{
            *geometry, static_cast<std::uint32_t>(r.get(48, 4)), static_cast<std::uint32_t>(r.get(52, 4))};
    }
    static auto write(std::span<std::byte> record, const FramebufferDescription &resource) -> bool {
        const auto &geometry = resource.geometry();
        if (record.size() != bytes)
            return false;
        for (auto &byte : record)
            byte = std::byte{0};
        put(record, 0, magic);
        put(record, 8, 1, 4);
        put(record, 12, bytes, 4);
        put(record, 16, geometry.base());
        put(record, 24, geometry.resource_bytes());
        put(record, 32, geometry.width(), 4);
        put(record, 36, geometry.height(), 4);
        put(record, 40, geometry.pitch(), 4);
        put(record, 44, geometry.format(), 4);
        put(record, 48, resource.mode(), 4);
        put(record, 52, resource.mode_count(), 4);
        return true;
    }
};

// Exact final-map admission. The ordinary path requires complete descriptors.
// The separately named GOP path is an exact probe-qualified fixture contract. It is never selected by a record label or by strict-parse failure.
// The firmware path admits the source-bound GOP resource as firmware describes it.
class FramebufferAdmission final {
    FramebufferGeometry geometry_;
    std::uint64_t arena_;
    FramebufferAdmission(const FramebufferGeometry &geometry, std::uint64_t arena)
        : geometry_(geometry), arena_(arena) {
    }
    // complete: every mapped byte lies in reserved/MMIO descriptors.
    // absent_or_complete: the aperture is either wholly outside the final map
    // (firmware omits PCI apertures) or wholly described; a partial
    // description is contradictory and denies. any: the exact fixture only.
    enum class Coverage : unsigned char {
        complete,
        absent_or_complete,
        any
    };
    [[nodiscard]] static auto authorize(const FramebufferGeometry &geometry,
                                        std::span<const std::byte> map,
                                        std::size_t stride,
                                        std::uint32_t version,
                                        std::uint64_t arena,
                                        unsigned physical_bits,
                                        std::uint32_t cpuid_edx,
                                        std::uint64_t pat,
                                        Coverage coverage) -> std::optional<FramebufferAdmission>;

public:
    static constexpr std::uint64_t virtual_address = 0xffffa00000001000ULL;
    static constexpr std::uint64_t leaf_flags = (1ULL << 63) | 0x1b;
    static constexpr unsigned pat_index = 3;
    [[nodiscard]] static auto authorize_described(const FramebufferGeometry &geometry,
                                                  std::span<const std::byte> map,
                                                  std::size_t stride,
                                                  std::uint32_t version,
                                                  std::uint64_t arena,
                                                  unsigned physical_bits,
                                                  std::uint32_t cpuid_edx,
                                                  std::uint64_t pat) -> std::optional<FramebufferAdmission> {
        return authorize(geometry, map, stride, version, arena, physical_bits, cpuid_edx, pat, Coverage::complete);
    }
    // Production rule: the live (loader) or restored (payload) GOP resource with
    // its own base, size, geometry and pixel format, and every check of the
    // fixture rule except the emulator identity tuple. RAM, runtime, ACPI and
    // persistent descriptors, the owned arena, LAPIC, IOAPIC and q35 ECAM deny;
    // PAT index 3 must be UC. Physical-hardware support is not established here.
    [[nodiscard]] static auto authorize_firmware(const FramebufferResource &resource,
                                                 std::span<const std::byte> map,
                                                 std::size_t stride,
                                                 std::uint32_t version,
                                                 std::uint64_t arena,
                                                 unsigned physical_bits,
                                                 std::uint32_t cpuid_edx,
                                                 std::uint64_t pat) -> std::optional<FramebufferAdmission> {
        return authorize(resource.geometry(),
                         map,
                         stride,
                         version,
                         arena,
                         physical_bits,
                         cpuid_edx,
                         pat,
                         Coverage::absent_or_complete);
    }
    // Exact probe-qualified fixture only. The external runner must additionally
    // pin q35/TCG/qemu64/one CPU/128 MiB/std VGA and the reviewed QEMU, OVMF,
    // tool-data and image identities. GOP fields cannot prove that environment.
    // Public record descriptions cannot construct the source-bound Resource.
    [[nodiscard]] static auto authorize_q35_ovmf_std_vga_fixture(const FramebufferResource &resource,
                                                                 std::span<const std::byte> map,
                                                                 std::size_t stride,
                                                                 std::uint32_t version,
                                                                 std::uint64_t arena,
                                                                 unsigned physical_bits,
                                                                 std::uint32_t cpuid_edx,
                                                                 std::uint64_t pat)
        -> std::optional<FramebufferAdmission> {
        const auto &geometry = resource.geometry();
        if (physical_bits != 40 || geometry.base() != 0x80000000ULL || geometry.resource_bytes() != 1921024 ||
            geometry.mapped_bytes() != 1921024 || geometry.width() != 800 || geometry.height() != 600 ||
            geometry.pitch() != 800 || geometry.format() != 1 || resource.mode() != 3 || resource.mode_count() != 30)
            return std::nullopt;
        return authorize(geometry, map, stride, version, arena, physical_bits, cpuid_edx, pat, Coverage::any);
    }
    [[nodiscard]] auto geometry() const -> const FramebufferGeometry & {
        return geometry_;
    }
    [[nodiscard]] auto owned_arena() const -> std::uint64_t {
        return arena_;
    }
    [[nodiscard]] auto mapping(std::uint64_t address) const -> std::uint64_t {
        if (address < virtual_address || address % 4096 || address - virtual_address >= geometry_.mapped_bytes())
            return 0;
        return (geometry_.base() + address - virtual_address) | leaf_flags;
    }
};

inline auto FramebufferAdmission::authorize(const FramebufferGeometry &geometry,
                                            std::span<const std::byte> map,
                                            std::size_t stride,
                                            std::uint32_t version,
                                            std::uint64_t arena,
                                            unsigned physical_bits,
                                            std::uint32_t cpuid_edx,
                                            std::uint64_t pat,
                                            Coverage coverage) -> std::optional<FramebufferAdmission> {
    constexpr auto required_features = (1U << 5) | (1U << 16); // MSR, PAT.
    if (physical_bits < 32 || physical_bits > 52 || !RuntimeLayout::valid(arena) ||
        (cpuid_edx & required_features) != required_features || ((pat >> (pat_index * 8)) & 255) != 0)
        return std::nullopt;
    const auto limit = std::uint64_t{1} << physical_bits;
    const auto begin = geometry.base(), bytes = geometry.mapped_bytes();
    if (begin >= limit || geometry.resource_bytes() > limit - begin || arena > limit - Handoff::arena_bytes)
        return std::nullopt;
    const auto end = begin + bytes;
    if ((begin < arena + Handoff::arena_bytes && arena < end) || (begin < 0xfee01000ULL && 0xfee00000ULL < end) ||
        (begin < 0xfec01000ULL && 0xfec00000ULL < end) || (begin < 0xf0000000ULL && 0xe0000000ULL < end))
        return std::nullopt;
    const MemoryMap final_map{map, stride, version};
    if (!final_map.owns(arena, Handoff::arena_bytes))
        return std::nullopt;
    std::uint64_t covered = 0;
    for (std::size_t at = 0; at < map.size(); at += stride) {
        const Bytes descriptor{map.subspan(at, stride)};
        const auto start = descriptor.get(8), finish = start + descriptor.get(24) * 4096;
        if (finish > limit)
            return std::nullopt;
        if (start >= end || finish <= begin)
            continue;
        const auto type = descriptor.get(0, 4), attributes = descriptor.get(32);
        // RAM (including loader/boot/conventional), runtime, ACPI and all
        // unsupported caching/protection combinations deny, even partially.
        if ((type != 0 && type != 11) || (attributes & ~(1ULL | 0x4000ULL)))
            return std::nullopt;
        const auto first = start > begin ? start : begin;
        const auto last = finish < end ? finish : end;
        covered += last - first; // The final map has already proved disjoint.
    }
    if ((coverage == Coverage::complete && covered != bytes) ||
        (coverage == Coverage::absent_or_complete && covered != 0 && covered != bytes))
        return std::nullopt;
    return FramebufferAdmission{geometry, arena};
}

} // namespace aurora::uefi
