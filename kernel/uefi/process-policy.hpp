#pragma once
// Trusted transport to the process image's Aurora policies (examples/kernel-process.au
// through kernel/uefi/process-entry.S). Each call passes one complete argument
// record of copied scalars and readonly spans over bytes the caller owns and has
// mapped; the build checks every record, enum and result layout against the
// compiler's ABI facts (scripts/meson_aurora_assembly.py PROCESS_POLICY_ABI).
// Decoders reject any result outside the closed encodings before it is used.
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

namespace aurora::uefi::process {
using U64 = std::uint64_t;
// The compiler's 56-byte contiguous readonly span: kind 0, backing, three
// reserved words, start and length.
class PolicySpan final {
public:
    U64 kind = 0;
    const std::byte *backing = nullptr;
    U64 reserved[3]{};
    std::int64_t start = 0;
    std::int64_t length = 0;
    PolicySpan() = default;
    explicit PolicySpan(std::span<const std::byte> bytes)
        : backing(bytes.data()), length(static_cast<std::int64_t>(bytes.size())) {
    }
};
static_assert(sizeof(PolicySpan) == 56 && alignof(PolicySpan) == 8);

enum class MapVerdict : U64 {
    valid,
    version,
    stride,
    length,
    alignment,
    range,
    overlap
};
enum class GrantVerdict : U64 {
    granted,
    map,
    bounds,
    arena,
    uncovered
};
enum class VolumeVerdict : U64 {
    valid,
    truncated,
    limit,
    magic,
    version,
    header,
    count,
    layout,
    reserved,
    checksum,
    padding,
    flags,
    name,
    path,
    order,
    data,
    nesting
};
// The Aurora copied result classes, field for field.
class FrameRange final {
public:
    U64 status = 0, first_page = 0, pages = 0;
};
class VolumeEntry final {
public:
    U64 found = 0, offset = 0, size = 0;
};
class MapArguments final {
public:
    PolicySpan map;
    U64 stride, version;
};
class GrantArguments final {
public:
    PolicySpan map;
    U64 stride, arena, volume, bytes;
};
class RangeArguments final {
public:
    PolicySpan map;
    U64 stride, index, arena, volume, bytes;
};
class VolumeArguments final {
public:
    PolicySpan volume;
};
class FindArguments final {
public:
    PolicySpan volume, path;
};
class EntryArguments final {
public:
    PolicySpan volume;
    U64 index;
};
static_assert(sizeof(MapArguments) == 72 && sizeof(GrantArguments) == 88 && sizeof(RangeArguments) == 96 &&
              sizeof(VolumeArguments) == 56 && sizeof(FindArguments) == 112 && sizeof(EntryArguments) == 64 &&
              sizeof(FrameRange) == 24 && sizeof(VolumeEntry) == 24);

namespace bridge {
auto map_admit(const MapArguments *) -> U64 asm("__au_runtime_process_map_admit") __attribute__((visibility("hidden")));
auto volume_grant(const GrantArguments *) -> U64 asm("__au_runtime_process_volume_grant")
    __attribute__((visibility("hidden")));
auto frame_range(const RangeArguments *, FrameRange *) -> void asm("__au_runtime_process_frame_range")
    __attribute__((visibility("hidden")));
auto volume_admit(const VolumeArguments *) -> U64 asm("__au_runtime_process_volume_admit")
    __attribute__((visibility("hidden")));
auto volume_find(const FindArguments *) -> U64 asm("__au_runtime_process_volume_find")
    __attribute__((visibility("hidden")));
auto volume_entry(const EntryArguments *, VolumeEntry *) -> void asm("__au_runtime_process_volume_entry")
    __attribute__((visibility("hidden")));
auto base64_group(const EntryArguments *) -> U64 asm("__au_runtime_process_base64_group")
    __attribute__((visibility("hidden")));
auto frame_transition(U64 operation, U64 record, U64 owner, U64 generation, U64 link) -> U64
    asm("aurora_kernel_frame_transition") __attribute__((visibility("hidden")));
} // namespace bridge

// A closed enum result, or nullopt for an encoding outside it.
template <class Enum, U64 Last> [[nodiscard]] inline auto verdict(U64 raw) -> std::optional<Enum> {
    if (raw > Last)
        return std::nullopt;
    return static_cast<Enum>(raw);
}
[[nodiscard]] inline auto map_admit(std::span<const std::byte> map, U64 stride, U64 version)
    -> std::optional<MapVerdict> {
    const MapArguments arguments{PolicySpan{map}, stride, version};
    return verdict<MapVerdict, 6>(bridge::map_admit(&arguments));
}
[[nodiscard]] inline auto volume_grant(std::span<const std::byte> map, U64 stride, U64 arena, U64 volume, U64 bytes)
    -> std::optional<GrantVerdict> {
    const GrantArguments arguments{PolicySpan{map}, stride, arena, volume, bytes};
    return verdict<GrantVerdict, 4>(bridge::volume_grant(&arguments));
}
// A skipped (0) or usable (1) descriptor; nullopt for a rejection or a malformed result.
[[nodiscard]] inline auto
frame_range(std::span<const std::byte> map, U64 stride, U64 index, U64 arena, U64 volume, U64 bytes)
    -> std::optional<FrameRange> {
    const RangeArguments arguments{PolicySpan{map}, stride, index, arena, volume, bytes};
    FrameRange range{~U64{0}, ~U64{0}, ~U64{0}};
    bridge::frame_range(&arguments, &range);
    if (range.status == 0 && range.first_page == 0 && range.pages == 0)
        return range;
    if (range.status != 1 || range.pages == 0 || range.first_page >= (U64{1} << 40) ||
        range.pages > (U64{1} << 40) - range.first_page)
        return std::nullopt;
    return range;
}
[[nodiscard]] inline auto volume_admit(std::span<const std::byte> volume) -> std::optional<VolumeVerdict> {
    const VolumeArguments arguments{PolicySpan{volume}};
    return verdict<VolumeVerdict, 16>(bridge::volume_admit(&arguments));
}
// The admitted volume's entry for path: its bytes inside volume, or nullopt.
[[nodiscard]] inline auto volume_lookup(std::span<const std::byte> volume, std::span<const std::byte> path)
    -> std::optional<std::span<const std::byte>> {
    const FindArguments find{PolicySpan{volume}, PolicySpan{path}};
    const auto found = bridge::volume_find(&find);
    if (found == 0 || found > 4096)
        return std::nullopt;
    const EntryArguments arguments{PolicySpan{volume}, found - 1};
    VolumeEntry entry{~U64{0}, ~U64{0}, ~U64{0}};
    bridge::volume_entry(&arguments, &entry);
    if (entry.found != 1 || entry.offset > volume.size() || entry.size > volume.size() - entry.offset)
        return std::nullopt;
    return volume.subspan(entry.offset, entry.size);
}
// Four base64 characters, first in bits 0..7, for the group at offset.
[[nodiscard]] inline auto base64_group(std::span<const std::byte> bytes, U64 offset) -> std::optional<U64> {
    const EntryArguments arguments{PolicySpan{bytes}, offset};
    const auto group = bridge::base64_group(&arguments);
    // Padding only at the end: a third '=' requires a fourth.
    for (unsigned i = 0; i < 4; ++i) {
        const auto c = (group >> (8 * i)) & 255;
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '+' || c == '/' ||
              (c == '=' && i >= 2)))
            return std::nullopt;
    }
    if (((group >> 16) & 255) == '=' && ((group >> 24) & 255) != '=')
        return std::nullopt;
    return group >> 32 ? std::nullopt : std::optional<U64>{group};
}
} // namespace aurora::uefi::process
