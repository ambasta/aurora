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

// Programs and processes (process.md#programs, #entries, #run-lists).
enum class ElfVerdict : U64 {
    valid,
    truncated,
    magic,
    format,
    type,
    machine,
    header,
    segment,
    interpreter,
    dynamic,
    tls,
    stack,
    permissions,
    writable_executable,
    alignment,
    file,
    memory,
    address,
    overlap,
    entry,
    empty
};
enum class LayoutVerdict : U64 {
    valid,
    image,
    kernel,
    arguments
};
enum class TrapClass : U64 {
    kernel,
    timer,
    call,
    system_call,
    invalid_opcode,
    stack_guard,
    page_fault,
    protection,
    divide,
    debug,
    breakpoint,
    overflow,
    bound,
    fpu,
    alignment,
    simd
};
enum class CallAction : U64 {
    invalid,
    exit,
    print,
    read
};
enum class RunsVerdict : U64 {
    valid,
    truncated,
    magic,
    version,
    count,
    ticks,
    path,
    arguments,
    flags,
    padding,
    trailing
};
// Region kinds of kernel.process_space and its exact leaf flags.
enum class RegionKind : U64 {
    none,
    segment,
    stack,
    arguments
};
inline constexpr U64 leaf_read = (U64{1} << 63) | 5, leaf_execute = 5, leaf_write = (U64{1} << 63) | 7;
class ProcessRegion final {
public:
    U64 kind = 0, first = 0, pages = 0, flags = 0, vaddr = 0, offset = 0, bytes = 0;
};
class ProcessTrap final {
public:
    U64 vector = 0, error = 0, rip = 0, cs = 0, flags = 0, rsp = 0, ss = 0, cr2 = 0, opcode = 0;
};
class KernelCall final {
public:
    U64 action = 0, value = 0, length = 0;
};
class RunEntry final {
public:
    U64 found = 0, ticks = 0, flags = 0, path = 0, path_bytes = 0, arguments = 0, argument_bytes = 0;
};
class LayoutArguments final {
public:
    PolicySpan image;
    U64 reserved_first, reserved_end, arguments;
};
class RegionArguments final {
public:
    PolicySpan image;
    U64 index, arguments;
};
class CallArguments final {
public:
    U64 operation, first, second, third;
};
static_assert(sizeof(ProcessRegion) == 56 && sizeof(ProcessTrap) == 72 && sizeof(KernelCall) == 24 &&
              sizeof(RunEntry) == 56 && sizeof(LayoutArguments) == 80 && sizeof(RegionArguments) == 72 &&
              sizeof(CallArguments) == 32);

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
auto elf_admit(const VolumeArguments *) -> U64 asm("__au_runtime_process_elf_admit")
    __attribute__((visibility("hidden")));
auto layout(const LayoutArguments *) -> U64 asm("__au_runtime_process_layout") __attribute__((visibility("hidden")));
auto region(const RegionArguments *, ProcessRegion *) -> void asm("__au_runtime_process_region")
    __attribute__((visibility("hidden")));
auto elf_entry(const VolumeArguments *) -> U64 asm("__au_runtime_process_elf_entry")
    __attribute__((visibility("hidden")));
auto trap(const ProcessTrap *) -> U64 asm("__au_runtime_process_trap") __attribute__((visibility("hidden")));
auto call(const CallArguments *, KernelCall *) -> void asm("__au_runtime_process_call")
    __attribute__((visibility("hidden")));
auto runs_admit(const VolumeArguments *) -> U64 asm("__au_runtime_process_runs_admit")
    __attribute__((visibility("hidden")));
auto run(const EntryArguments *, RunEntry *) -> void asm("__au_runtime_process_run")
    __attribute__((visibility("hidden")));
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

// Program admission, layout and regions. A region outside its closed shape is
// nullopt: pages within the 47-bit user half, its exact leaf flags, the copy
// extent inside its pages (and for segments inside the image).
[[nodiscard]] inline auto elf_admit(std::span<const std::byte> image) -> std::optional<ElfVerdict> {
    const VolumeArguments arguments{PolicySpan{image}};
    return verdict<ElfVerdict, 20>(bridge::elf_admit(&arguments));
}
[[nodiscard]] inline auto layout(std::span<const std::byte> image, U64 reserved_first, U64 reserved_end, U64 bytes)
    -> std::optional<LayoutVerdict> {
    const LayoutArguments arguments{PolicySpan{image}, reserved_first, reserved_end, bytes};
    return verdict<LayoutVerdict, 3>(bridge::layout(&arguments));
}
[[nodiscard]] inline auto region(std::span<const std::byte> image, U64 index, U64 bytes)
    -> std::optional<ProcessRegion> {
    const RegionArguments arguments{PolicySpan{image}, index, bytes};
    ProcessRegion result{~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}};
    bridge::region(&arguments, &result);
    if (result.kind == 0)
        return result.first || result.pages || result.flags || result.vaddr || result.offset || result.bytes
                   ? std::nullopt
                   : std::optional<ProcessRegion>{result};
    constexpr U64 user_limit = U64{1} << 47;
    if (result.kind > 3 || result.pages == 0 || result.first % 4096 || result.first >= user_limit ||
        result.pages > (user_limit - result.first) / 4096 || result.vaddr < result.first ||
        result.vaddr - result.first >= 4096 || result.bytes > result.pages * 4096 - (result.vaddr - result.first))
        return std::nullopt;
    const auto kind = static_cast<RegionKind>(result.kind);
    if (kind == RegionKind::segment)
        return (result.flags == leaf_read || result.flags == leaf_execute || result.flags == leaf_write) &&
                       result.offset <= image.size() && result.bytes <= image.size() - result.offset
                   ? std::optional<ProcessRegion>{result}
                   : std::nullopt;
    if (result.vaddr != result.first || result.offset != 0)
        return std::nullopt;
    if (kind == RegionKind::stack)
        return result.flags == leaf_write && result.bytes == 0 ? std::optional<ProcessRegion>{result} : std::nullopt;
    return result.flags == leaf_read && result.bytes == bytes ? std::optional<ProcessRegion>{result} : std::nullopt;
}
[[nodiscard]] inline auto elf_entry(std::span<const std::byte> image) -> U64 {
    const VolumeArguments arguments{PolicySpan{image}};
    return bridge::elf_entry(&arguments);
}
[[nodiscard]] inline auto trap(const ProcessTrap &frame) -> std::optional<TrapClass> {
    return verdict<TrapClass, 15>(bridge::trap(&frame));
}
// A decoded kernel call in its closed encoding, or nullopt.
[[nodiscard]] inline auto call(U64 operation, U64 first, U64 second, U64 third) -> std::optional<KernelCall> {
    const CallArguments arguments{operation, first, second, third};
    KernelCall result{~U64{0}, ~U64{0}, ~U64{0}};
    bridge::call(&arguments, &result);
    const auto action = static_cast<CallAction>(result.action);
    if ((action == CallAction::invalid && result.value == 0 && result.length == 0) ||
        (action == CallAction::exit && result.value <= 255 && result.length == 0) ||
        (action == CallAction::print && (result.value == 1 || result.value == 2) && result.length <= 65536) ||
        (action == CallAction::read && result.value == ~U64{0} && result.length == 0))
        return result;
    return std::nullopt;
}
[[nodiscard]] inline auto runs_admit(std::span<const std::byte> runs) -> std::optional<RunsVerdict> {
    const VolumeArguments arguments{PolicySpan{runs}};
    return verdict<RunsVerdict, 10>(bridge::runs_admit(&arguments));
}
// The index-th run of an admitted list (found 0 past the last), or nullopt.
[[nodiscard]] inline auto run(std::span<const std::byte> runs, U64 index) -> std::optional<RunEntry> {
    const EntryArguments arguments{PolicySpan{runs}, index};
    RunEntry result{~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}, ~U64{0}};
    bridge::run(&arguments, &result);
    if (result.found == 0)
        return result.ticks || result.flags || result.path || result.path_bytes || result.arguments ||
                       result.argument_bytes
                   ? std::nullopt
                   : std::optional<RunEntry>{result};
    if (result.found != 1 || result.ticks == 0 || result.ticks > 128 || result.flags > 3 || result.path_bytes == 0 ||
        result.path_bytes > 255 || result.argument_bytes == 0 || result.argument_bytes > 65536 ||
        result.path > runs.size() || result.path_bytes > runs.size() - result.path ||
        result.arguments != result.path + result.path_bytes || result.argument_bytes > runs.size() - result.arguments)
        return std::nullopt;
    return result;
}
} // namespace aurora::uefi::process
