#include "process.hpp"
#include "kernel-space.hpp"
#include "../console.hpp"

using aurora::hardware::Serial;
using U64 = std::uint64_t;
namespace frames = aurora::uefi::frames;
namespace process = aurora::uefi::process;

namespace {
// Each table is far larger than the kernel stack; one boot owns one of each.
constinit frames::Ranges ranges;
constinit aurora::uefi::KernelSpace space;
constinit frames::Table table;
// The probe's owner; owners below frames::first_owner are kernel uses.
constexpr U64 probe_owner = frames::first_owner;
constexpr std::string_view exported = "examples/host-sort.au";

// Verdict names, space separated in enum order: plain characters, so the
// position-independent payload needs no absolute address relocation.
constexpr char map_names[] = "valid version stride length alignment range overlap";
constexpr char grant_names[] = "granted map bounds arena uncovered";
constexpr char volume_names[] =
    "valid truncated limit magic version header count layout reserved checksum padding flags name path order data "
    "nesting";
auto name(std::string_view names, U64 index) -> std::string_view {
    std::size_t begin = 0, end = 0;
    for (U64 word = 0; word <= index; ++word) {
        if (end > names.size())
            return "malformed";
        begin = end;
        while (end < names.size() && names[end] != ' ')
            ++end;
        ++end;
    }
    return {names.data() + begin, end - begin - 1};
}

[[noreturn]] auto fail(std::string_view reason) -> void {
    Serial::text("AURORA_PROCESS_FAIL: ");
    Serial::text(reason);
    Serial::text("\r\n");
    aurora::hardware::Io::write(0xf4, 0x11);
    for (;;)
        asm volatile("cli; hlt");
}
auto field(std::string_view name, U64 value) -> void {
    Serial::text(" ");
    Serial::text(name);
    Serial::text("=");
    Serial::number(value);
}
auto bytes_of(std::string_view text) -> std::span<const std::byte> {
    return {reinterpret_cast<const std::byte *>(text.data()), text.size()};
}

// Every free frame through the transient window: a distinct pattern written and
// read back, then zero written and read back. Returns the frames scrubbed.
auto scrub_all() -> U64 {
    U64 count = 0;
    while (const auto frame = table.allocate(probe_owner)) {
        const auto physical = table.address(frame->index);
        auto *words = physical ? space.open(*physical) : nullptr;
        if (!words || frame->generation != 0)
            fail("frame window");
        const auto pattern = 0x9e3779b97f4a7c15ULL * (frame->index + 1);
        for (U64 i = 0; i < frames::page / 8; ++i)
            reinterpret_cast<volatile U64 *>(words)[i] = pattern ^ i;
        for (U64 i = 0; i < frames::page / 8; ++i)
            if (reinterpret_cast<volatile U64 *>(words)[i] != (pattern ^ i))
                fail("frame pattern readback");
        for (U64 i = 0; i < frames::page / 8; ++i)
            reinterpret_cast<volatile U64 *>(words)[i] = 0;
        for (U64 i = 0; i < frames::page / 8; ++i)
            if (reinterpret_cast<volatile U64 *>(words)[i] != 0)
                fail("frame scrub readback");
        space.close();
        ++count;
    }
    return count;
}

// Misuse is rejected with its exact reason and leaves the record unchanged.
auto rejected(frames::Frame frame, U64 owner, frames::Rejection expected) -> U64 {
    const auto before = table.record(frame.index);
    if (table.release(frame, owner) != expected || table.record(frame.index) != before || table.poisoned())
        fail("frame misuse admitted");
    return 1;
}

auto frame_cases(U64 used) -> void {
    const auto initial = table.free(), reserved = table.reserved();
    const auto scrubbed = scrub_all();
    if (scrubbed != initial || table.free() != 0 || table.allocate(probe_owner) || table.poisoned())
        fail("frame exhaustion");
    const frames::Frame held{reserved, 0};
    U64 misuse = rejected({held.index, 1}, probe_owner, frames::Rejection::stale);
    misuse += rejected(held, probe_owner + 1, frames::Rejection::wrong_owner);
    misuse += rejected(held, frames::owner_tables, frames::Rejection::owner);
    misuse += rejected({0, 0}, probe_owner, frames::Rejection::kernel);
    misuse += rejected({table.frames(), 0}, probe_owner, frames::Rejection::index);
    U64 released = 0;
    for (U64 index = reserved; index < table.frames(); ++index) {
        if (table.release({index, frames::generation(table.record(index))}, probe_owner) != frames::Rejection::none)
            fail("frame release");
        ++released;
    }
    misuse += rejected(held, probe_owner, frames::Rejection::not_allocated);
    const auto audit = table.audit();
    if (!audit.consistent || audit.free != initial || audit.allocated || audit.retired || released != scrubbed)
        fail("frame audit");
    for (U64 index = reserved; index < table.frames(); ++index)
        if (frames::generation(table.record(index)) != 1)
            fail("frame generation");
    if (!space.verify(table, ranges, used))
        fail("kernel space exit walk");
    Serial::text("AURORA_PROCESS_FRAMES_OK:");
    field("allocated", scrubbed);
    field("scrubbed", scrubbed);
    field("released", released);
    field("rejected", misuse);
    field("leaks", table.free() + table.reserved() - table.frames());
    Serial::text("\r\n");
}

// The exit walk rejects each single-entry change of the extension: a user
// bit on a table link, an executable metadata leaf, a writable volume leaf and
// an open frame window. Each change is undone before the next.
auto space_cases(const aurora::uefi::KernelSpace::Plan &plan, U64 used) -> void {
    using aurora::uefi::KernelSpace;
    class Edit final {
    public:
        U64 table, index, bits;
    };
    const Edit edits[] = {{0, 0, 4}, {2, 0, aurora::uefi::PageTables::nx}, {3 + plan.metadata_tables, 0, 2}};
    U64 rejected = 0;
    for (const auto &edit : edits) {
        auto *entry = KernelSpace::table_view(edit.table) + edit.index;
        const auto before = *entry;
        *entry = before ^ edit.bits;
        rejected += !space.verify(table, ranges, used);
        *entry = before;
    }
    if (const auto frame = table.allocate(probe_owner)) {
        const auto physical = table.address(frame->index);
        if (!physical || !space.open(*physical))
            fail("frame window");
        rejected += !space.verify(table, ranges, used);
        space.close();
        if (table.release(*frame, probe_owner) != frames::Rejection::none)
            fail("frame release");
    }
    U64 cr3;
    asm volatile("mov %%cr3, %0; mov %0, %%cr3" : "=r"(cr3) : : "memory");
    if (rejected != 4 || !space.verify(table, ranges, used))
        fail("kernel space edit admitted");
    Serial::text("AURORA_PROCESS_SPACE_OK:");
    field("rejected", rejected);
    Serial::text("\r\n");
}

// Framed base64 export records of one volume entry (process.md#export).
auto export_entry(std::span<const std::byte> volume, std::string_view path) -> void {
    const auto entry = process::volume_lookup(volume, bytes_of(path));
    if (!entry)
        fail("boot volume lookup");
    Serial::text("AURORA_EXPORT_BEGIN: path=");
    Serial::text(path);
    field("bytes", entry->size());
    Serial::text("\r\n");
    U64 lines = 0;
    for (U64 line = 0; line < entry->size(); line += 57) {
        Serial::text("AURORA_EXPORT_DATA: ");
        for (U64 offset = line; offset < entry->size() && offset < line + 57; offset += 3) {
            const auto group = process::base64_group(*entry, offset);
            if (!group)
                fail("export encoding");
            for (unsigned i = 0; i < 4; ++i)
                Serial::put(static_cast<std::uint8_t>(*group >> (8 * i)));
        }
        Serial::text("\r\n");
        ++lines;
    }
    Serial::text("AURORA_EXPORT_END: path=");
    Serial::text(path);
    field("lines", lines);
    Serial::text("\r\n");
}
} // namespace

auto aurora::uefi::run_process(U64 arena, const Bytes &h) -> void {
    const auto map =
        std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + Handoff::map_offset), h.get(32)};
    const auto volume = h.get(Handoff::volume_word), bytes = h.get(Handoff::volume_bytes_word);
    const auto found = frames::inventory(map, h.get(40), h.get(48, 4), arena, volume, bytes, ranges);
    if (found.map != process::MapVerdict::valid) {
        Serial::text("AURORA_PROCESS_MAP_REJECTED: reason=");
        Serial::text(name(map_names, static_cast<U64>(found.map)));
        Serial::text("\r\n");
        fail("memory map admission");
    }
    if (found.grant != process::GrantVerdict::granted) {
        Serial::text("AURORA_PROCESS_GRANT_REJECTED: reason=");
        Serial::text(found.grant ? name(grant_names, static_cast<U64>(*found.grant)) : "malformed");
        Serial::text("\r\n");
        fail("boot volume map ownership");
    }
    if (!found.ranges)
        fail("frame inventory");
    const auto volume_pages = (bytes + frames::page - 1) / frames::page;
    // Every mapped frame and volume page lies below the CPU's physical width,
    // so no leaf this kernel writes can set a reserved address bit.
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000000U), "c"(0));
    if (a < 0x80000008U)
        fail("physical address width unavailable");
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
    const auto width = a & 255;
    const auto &last = ranges.range(ranges.count() - 1);
    if (width < 32 || width > 52 || (last.first_page + last.pages) * frames::page > (U64{1} << width) ||
        volume + volume_pages * frames::page > (U64{1} << width))
        fail("frame inventory beyond the physical width");
    const auto plan = KernelSpace::plan(ranges.frames(), volume_pages);
    const PageTables tables{arena + Handoff::tables_offset, static_cast<std::size_t>(h.get(96))};
    if (!plan || !space.bind(arena + Handoff::tables_offset, tables.window_slot()) ||
        !space.build(ranges, *plan, volume))
        fail("kernel space");
    const auto records = space.metadata(ranges.frames());
    for (auto &record : records)
        record = 0;
    if (records.empty() || !table.bind(records, ranges, plan->tables, plan->metadata))
        fail("frame table");
    if (!space.verify(table, ranges, h.get(96)))
        fail("kernel space walk");
    Serial::text("AURORA_PROCESS_FRAMES:");
    field("frames", table.frames());
    field("ranges", ranges.count());
    field("tables", plan->tables);
    field("metadata", plan->metadata);
    field("free", table.free());
    Serial::text("\r\n");
    const auto view = space.volume(bytes);
    const auto verdict = process::volume_admit(view);
    if (verdict != process::VolumeVerdict::valid) {
        Serial::text("AURORA_PROCESS_VOLUME_REJECTED: reason=");
        Serial::text(verdict ? name(volume_names, static_cast<U64>(*verdict)) : "malformed");
        Serial::text("\r\n");
        fail("boot volume admission");
    }
    Serial::text("AURORA_PROCESS_VOLUME_OK:");
    field("bytes", bytes);
    field("pages", volume_pages);
    Serial::text("\r\n");
    frame_cases(h.get(96));
    space_cases(*plan, h.get(96));
    export_entry(view, exported);
    Serial::text("AURORA_PROCESS_OK\r\n");
    aurora::hardware::Io::write(0xf4, 0x10);
    for (;;)
        asm volatile("cli; hlt");
}
