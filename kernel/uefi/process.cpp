#include "process.hpp"
#include "acpi.hpp"
#include "apic-timer-io.hpp"
#include "budget-transport.hpp"
#include "process-files.hpp"
#include "process-space.hpp"
#include "../console.hpp"

using aurora::hardware::Serial;
using U64 = std::uint64_t;
namespace frames = aurora::uefi::frames;
namespace process = aurora::uefi::process;
using aurora::BootstrapLayout;
using aurora::uefi::Bytes;
using aurora::uefi::Handoff;
using aurora::uefi::KernelSpace;
using aurora::uefi::PageTables;
using aurora::uefi::ProcessSpace;
using Timer = aurora::uefi::LocalApicTimerIo;

namespace {
// Each table is far larger than the kernel stack; one boot owns one of each.
constinit frames::Ranges ranges;
constinit aurora::uefi::KernelSpace space;
constinit frames::Table table;
constinit ProcessSpace::Shared shared;
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
constexpr char elf_names[] = "valid truncated magic format type machine header segment interpreter dynamic tls stack "
                             "permissions writable_executable alignment file memory address overlap entry empty";
constexpr char layout_names[] = "valid image kernel arguments";
constexpr char trap_names[] = "kernel timer call system_call invalid_opcode stack_guard page_fault protection divide "
                              "debug breakpoint overflow bound fpu alignment simd";
constexpr char runs_names[] = "valid truncated magic version count ticks path arguments flags padding trailing";
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

// The process entry, exit and drain (process-user.S).
extern U64 process_kernel_root asm("uefi_process_kernel_root") __attribute__((visibility("hidden")));
extern const std::byte drain_begin asm("uefi_process_drain_begin") __attribute__((visibility("hidden")));
extern const std::byte drain_end asm("uefi_process_drain_end") __attribute__((visibility("hidden")));
auto process_enter(const U64 *) -> U64 asm("uefi_process_enter") __attribute__((visibility("hidden")));
auto process_handler(U64) -> U64 asm("uefi_process_handler") __attribute__((visibility("hidden")));
auto process_drain() -> void asm("uefi_process_drain") __attribute__((visibility("hidden")));

// Processes (process.md#processes). One process runs at a time; the dispatcher
// below reaches it through these words, which only the kernel writes.
namespace {
constexpr U64 tick_count = U64{1} << 24;
// The interrupt frame: 15 saved registers (R15 first, RAX last), the vector and
// error code, then the CPU's RIP, CS, RFLAGS, RSP and SS.
constexpr std::size_t frame_words = BootstrapLayout::fault_frame_words, frame_rax = 14, frame_rdi = 8, frame_rsi = 9,
                      frame_rdx = 11, frame_r10 = 5, frame_rip = 17;
class Running final {
public:
    ProcessSpace *space = nullptr;
    U64 run = 0, flags = 0, initial = 0, remaining = 0, used = 0, calls = 0, memory_calls = 0, commits = 0;
};
// How the process ended, copied from its last kernel entry.
class Outcome final {
public:
    bool exited = false, watchdog = false, invalid_call = false;
    process::TrapClass trap = process::TrapClass::kernel;
    U64 status = 0, vector = 0, error = 0, rip = 0, cr2 = 0, operation = 0;
};
constinit Running running;
constinit Outcome outcome;
constinit U64 owned_arena = 0, kernel_root = 0;
constinit bool draining = false;

auto root() -> U64 {
    U64 value;
    asm volatile("mov %%cr3, %0" : "=r"(value));
    return value;
}
auto read_msr(std::uint32_t index) -> U64 {
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(index));
    return (U64{high} << 32) | low;
}
auto write_msr(std::uint32_t index, U64 value) -> void {
    asm volatile("wrmsr"
                 :
                 : "a"(static_cast<std::uint32_t>(value)), "d"(static_cast<std::uint32_t>(value >> 32)), "c"(index)
                 : "memory");
}
auto store(U64 address, U64 value, unsigned width) -> void {
    for (unsigned i = 0; i < width; ++i)
        *reinterpret_cast<volatile std::uint8_t *>(address + i) = static_cast<std::uint8_t>(value >> (8 * i));
}

// A fault without a verified process frame stops the machine.
[[noreturn]] auto kernel_fault(U64 vector, U64 error, U64 rip, U64 cs) -> void {
    U64 cr2;
    asm volatile("mov %%cr2, %0" : "=r"(cr2));
    Serial::text("AURORA_PROCESS_KERNEL_FAULT:");
    field("vector", vector);
    field("error", error);
    field("rip", rip);
    field("cs", cs);
    field("cr2", cr2);
    Serial::text("\r\n");
    fail("kernel fault");
}

// The LAPIC one-shot timer the watchdog charges, admitted against the copied
// MADT, the final map and the CPU like the other timed images (console.cpp),
// while the boot verifier still covers the whole kernel tree.
auto establish_timer(U64 arena, const Bytes &h) -> void {
    if (!Timer::irq_off() || root() != h.get(88) || !aurora::uefi::discovered_timer_topology())
        fail("timer discovery");
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    const auto leaf_ebx = b, leaf_edx = d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
    const auto admitted = aurora::uefi::LocalApicAdmission::authorize(
        *aurora::uefi::discovered_timer_topology(),
        std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + Handoff::map_offset), h.get(32)},
        h.get(40),
        static_cast<std::uint32_t>(h.get(48, 4)),
        arena,
        a & 255,
        leaf_edx,
        leaf_ebx,
        read_msr(0x1b),
        read_msr(0x277));
    if (!admitted)
        fail("timer aperture admission");
    const PageTables tables{h.get(88), static_cast<std::size_t>(h.get(96))};
    const auto slot = tables.interrupt_slot();
    if (!slot || *slot)
        fail("empty timer aperture");
    *slot = aurora::uefi::LocalApicAdmission::physical_address | aurora::uefi::LocalApicAdmission::leaf_flags;
    asm volatile("invlpg (%0)" : : "r"(aurora::uefi::LocalApicAdmission::virtual_address) : "memory");
    if (!tables.verify(arena, h, &*admitted) || !admitted->matches_registers(Timer::read(0x20), Timer::read(0x30)) ||
        !Timer::initialize(Timer::read(0x30)))
        fail("private timer mapping");
}

// GDT with user segments, the TSS (RSP0 and the double-fault IST stack), the
// process IDT (INT 0x83 alone at DPL 3), SYSCALL disabled and FPU use trapping.
auto install_architecture(U64 arena) -> void {
    const auto gdt = arena + BootstrapLayout::gdt_offset, tss = gdt + 256;
    const U64 entries[] = {
        0, 0x00af9b000000ffffULL, 0x00cf93000000ffffULL, 0x00affb000000ffffULL, 0x00cff3000000ffffULL};
    for (unsigned i = 0; i < 5; ++i)
        store(gdt + i * 8, entries[i], 8);
    store(gdt + 40, 103ULL | ((tss & 0xffffff) << 16) | (0x89ULL << 40) | (((tss >> 24) & 255) << 56), 8);
    store(gdt + 48, tss >> 32, 8);
    for (U64 i = 0; i < 104; ++i)
        store(tss + i, 0, 1);
    store(tss + 4, arena + BootstrapLayout::rsp0_top, 8);
    store(tss + 36, arena + BootstrapLayout::ist_top, 8);
    store(tss + 102, 104, 2);
    std::array<std::byte, 10> gdtr{};
    aurora::uefi::put(gdtr, 0, 55, 2);
    aurora::uefi::put(gdtr, 2, gdt);
    asm volatile("lgdt %0" : : "m"(gdtr) : "memory");
    const std::uint16_t selector = 0x28;
    asm volatile("ltr %0" : : "r"(selector) : "memory");
    for (unsigned vector = 0; vector < 256; ++vector) {
        const auto target = process_handler(vector);
        if (target < arena + Handoff::payload_offset ||
            target >= arena + Handoff::payload_offset + Handoff::payload_limit)
            fail("IDT target");
        const auto gate = arena + Handoff::idt_offset + vector * 16;
        store(gate, target, 2);
        store(gate + 2, 8, 2);
        store(gate + 4, vector == 8 ? 1 : 0, 1);
        store(gate + 5, vector == 131 ? 0xee : 0x8e, 1);
        store(gate + 6, target >> 16, 2);
        store(gate + 8, target >> 32, 4);
        store(gate + 12, 0, 4);
    }
    U64 cr0, cr4;
    asm volatile("mov %%cr0, %0; mov %%cr4, %1" : "=r"(cr0), "=r"(cr4));
    if (cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 16) | (1ULL << 17) | (1ULL << 18) | (1ULL << 20)))
        fail("integer paging profile");
    asm volatile("mov %0, %%cr0" : : "r"(cr0 | 8) : "memory");
    // SYSCALL stays disabled (EFER.SCE clear), so a process's SYSCALL is #UD.
    write_msr(0xc0000080, read_msr(0xc0000080) & ~U64{1});
    for (const std::uint32_t base : {0xc0000100U, 0xc0000101U, 0xc0000102U})
        write_msr(base, 0);
    // SYSENTER (legal at CPL 3 on Intel-vendor CPUs) enters nowhere: its
    // MSRs are zero, so it faults through the IDT like every other entry.
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    if (d & (1U << 11))
        for (const std::uint32_t msr : {0x174U, 0x175U, 0x176U}) {
            write_msr(msr, 0);
            if (read_msr(msr))
                fail("inherited sysenter entry");
        }
    // No firmware breakpoint survives into a process.
    asm volatile("mov %0, %%dr7" : : "r"(U64{0x400}) : "memory");
    const auto efer = read_msr(0xc0000080);
    if ((efer & 1) || !(efer & (1ULL << 11)) || (efer & (5ULL << 8)) != (5ULL << 8))
        fail("process machine state");
}

// Root entries 256..511 and the page-directory entries of the arena's 2 MiB
// slots in the boot-verified root, shared by every process root.
auto capture_shared(U64 arena) -> void {
    const auto *top = reinterpret_cast<const volatile U64 *>(kernel_root);
    for (U64 slot = 256; slot < 512; ++slot)
        shared.upper[slot - 256] = top[slot];
    // Every slot the arena spans is reserved; only those holding mapped
    // arena pages have a page table to share.
    const U64 first = arena & ~(ProcessSpace::slot_bytes - 1);
    const U64 last = (arena + Handoff::arena_bytes - 1) & ~(ProcessSpace::slot_bytes - 1);
    shared.reserved_first = first;
    shared.reserved_end = last + ProcessSpace::slot_bytes;
    for (auto slot = first; slot <= last; slot += ProcessSpace::slot_bytes) {
        U64 table_page = kernel_root, entry = 0;
        for (const unsigned at : {39U, 30U, 21U}) {
            entry = reinterpret_cast<const volatile U64 *>(table_page)[(slot >> at) & 511];
            if (!entry)
                break;
            if ((entry & ~KernelSpace::address_mask & ~ProcessSpace::hardware_bits) != 3)
                fail("shared kernel slots");
            table_page = entry & KernelSpace::address_mask;
        }
        if (!entry)
            continue;
        shared.slot[shared.slots] = slot;
        shared.entry[shared.slots++] = entry & ~ProcessSpace::hardware_bits;
    }
    if (!shared.slots)
        fail("shared kernel slots");
}

// Base64 records of one print, read under the process root (process.md#output).
auto print_stream(U64 stream, U64 buffer, U64 length) -> void {
    Serial::text(stream == 1 ? "AURORA_STDOUT:" : "AURORA_STDERR:");
    field("run", running.run);
    Serial::text(" ");
    const std::span<const std::byte> bytes{reinterpret_cast<const std::byte *>(buffer), length};
    for (U64 offset = 0; offset < length; offset += 3) {
        const auto group = process::base64_group(bytes, offset);
        if (!group)
            fail("output encoding");
        for (unsigned i = 0; i < 4; ++i)
            Serial::put(static_cast<std::uint8_t>(*group >> (8 * i)));
    }
    Serial::text("\r\n");
}

// The watchdog budget after one charged interrupt: resume, or end the process.
auto charge_tick(U64 vector, U64 error, U64 rip, U64 cs) -> U64 {
    if (!Timer::acknowledge())
        kernel_fault(vector, error, rip, cs);
    const auto encoded = aurora::uefi::language_budget_tick(running.initial, running.remaining, running.used);
    const auto next = aurora::uefi::BudgetTransition::decode(encoded, running.initial, running.remaining, running.used);
    if (!next)
        fail("Aurora budget transition");
    running.remaining = next->remaining();
    running.used = next->used();
    if (next->resume()) {
        if (!Timer::arm(tick_count))
            fail("watchdog rearm");
        return 0;
    }
    outcome.watchdog = true;
    return 1;
}

// The file service's storage: the running process's frames (charged to its
// quota) through the kernel's transient window.
class KernelStore final {
public:
    ProcessSpace *process = nullptr;
    [[nodiscard]] auto take() -> std::optional<U64> {
        return process->file_frame();
    }
    [[nodiscard]] auto give(U64 frame) -> bool {
        return process->drop_file_frame(frame);
    }
    [[nodiscard]] auto charge(U64 count) -> bool {
        return process->charge_files(count);
    }
    [[nodiscard]] auto uncharge(U64 count) -> bool {
        return process->uncharge_files(count);
    }
    [[nodiscard]] auto charged() const -> U64 {
        return process->charged();
    }
    [[nodiscard]] auto quota() const -> U64 {
        return process->quota();
    }
    [[nodiscard]] auto charged_files() const -> U64 {
        return process->file_charge();
    }
    [[nodiscard]] auto read_word(U64 frame, U64 index) -> U64 {
        auto *words = index < 512 ? space.open(frame) : nullptr;
        if (!words)
            return 0;
        const auto value = reinterpret_cast<volatile U64 *>(words)[index];
        space.close();
        return value;
    }
    [[nodiscard]] auto write_word(U64 frame, U64 index, U64 value) -> bool {
        auto *words = index < 512 ? space.open(frame) : nullptr;
        if (!words)
            return false;
        reinterpret_cast<volatile U64 *>(words)[index] = value;
        space.close();
        return true;
    }
    [[nodiscard]] auto copy_in(U64 frame, U64 offset, std::span<const std::byte> bytes) -> bool {
        auto *words = offset <= frames::page && bytes.size() <= frames::page - offset ? space.open(frame) : nullptr;
        if (!words)
            return false;
        auto *target = reinterpret_cast<volatile std::byte *>(words) + offset;
        for (std::size_t at = 0; at < bytes.size(); ++at)
            target[at] = bytes[at];
        space.close();
        return true;
    }
    [[nodiscard]] auto copy_out(U64 frame, U64 offset, std::span<std::byte> bytes) -> bool {
        auto *words = offset <= frames::page && bytes.size() <= frames::page - offset ? space.open(frame) : nullptr;
        if (!words)
            return false;
        const auto *source = reinterpret_cast<volatile const std::byte *>(words) + offset;
        for (std::size_t at = 0; at < bytes.size(); ++at)
            bytes[at] = source[at];
        space.close();
        return true;
    }
};
constinit KernelStore file_store;
constinit aurora::uefi::FileService<KernelStore> files;
// The kernel's copy of a call's path, read from the process before any
// decision sees it.
constinit std::array<std::byte, process::file_path_limit + 1> path_copy{};

// A process buffer the call reads (or writes) under its root
// (ProcessSpace::access): nullopt ends the process as an invalid call.
auto user_bytes(U64 address, U64 length, bool write) -> std::optional<std::byte *> {
    const auto access = running.space->access(address, length, write);
    if (access == ProcessSpace::Access::broken)
        fail("process memory access");
    if (access == ProcessSpace::Access::refused)
        return std::nullopt;
    // Fixture: the whole space verifies after each access (it may commit).
    if ((running.flags & 4) && !running.space->verify())
        fail("memory walk");
    return reinterpret_cast<std::byte *>(address);
}

// A file call (process.md#files): RAX becomes 0, a count or a negative
// HostStatus; the result record is written for the opens and create_output.
// False for a path or buffer the process cannot lend: the process ends as an
// invalid call.
auto file_call(const process::KernelCall &call, volatile U64 *frame) -> bool {
    using Action = process::CallAction;
    const auto action = static_cast<Action>(call.action);
    const auto path_call = action == Action::open_directory || action == Action::open_beneath ||
                           action == Action::open_file || action == Action::create_output;
    std::optional<std::byte *> record;
    std::span<const std::byte> path;
    if (path_call) {
        record = user_bytes(call.record, 48, true);
        // A path above the limit is never read: it arrives empty, which the
        // policy refuses as invalid_path in the same order.
        const auto readable = call.length <= process::file_path_limit;
        const auto source = readable ? user_bytes(call.base, call.length, false) : std::optional<std::byte *>{nullptr};
        if (!record || !source)
            return false;
        if (readable) {
            for (U64 at = 0; at < call.length; ++at)
                path_copy[at] = (*source)[at];
            path = {path_copy.data(), call.length};
        }
    }
    aurora::uefi::FileService<KernelStore>::Result result;
    if (action == Action::read) {
        const auto chunk = user_bytes(call.base, process::file_chunk, true);
        if (!chunk)
            return false;
        result = files.read(call.value, call.length, std::span<std::byte, process::file_chunk>{*chunk, process::file_chunk});
    } else if (action == Action::write) {
        const auto bytes = user_bytes(call.base, call.length, false);
        if (!bytes)
            return false;
        result = files.write(call.value, {*bytes, call.length});
    } else if (action == Action::create_output) {
        result = files.create(path);
    } else if (action == Action::close) {
        result = files.close(call.value);
    } else if (action == Action::commit) {
        result = files.commit(call.value);
    } else if (action == Action::discard) {
        result = files.discard(call.value);
    } else {
        result = files.open(action == Action::open_directory ? 0 : action == Action::open_beneath ? 1 : 2, call.value,
                            path);
    }
    if (result.broken)
        fail("file service");
    if (record)
        for (U64 word = 0; word < 6; ++word)
            store(reinterpret_cast<U64>(*record) + 8 * word, result.record[word], 8);
    frame[frame_rax] = result.value;
    return true;
}

// One kernel call: 0 resumes the process with RAX set, 1 ends it.
auto kernel_call(volatile U64 *frame) -> U64 {
    const auto decoded =
        process::call(frame[frame_rax], frame[frame_rdi], frame[frame_rsi], frame[frame_rdx], frame[frame_r10]);
    if (!decoded)
        fail("Aurora kernel call decision");
    // Fixture: fault in the kernel during the run's first call (process.md#guest-rows).
    if ((running.flags & 1) && running.calls++ == 0)
        static_cast<void>(*reinterpret_cast<volatile U64 *>(KernelSpace::window_base + frames::page));
    const auto action = static_cast<process::CallAction>(decoded->action);
    if (action == process::CallAction::exit) {
        outcome.exited = true;
        outcome.status = decoded->value;
        return 1;
    }
    if (action == process::CallAction::print) {
        if (const auto bytes = user_bytes(decoded->base, decoded->length, false)) {
            print_stream(decoded->value, reinterpret_cast<U64>(*bytes), decoded->length);
            frame[frame_rax] = 0;
            return 0;
        }
    }
    if ((action == process::CallAction::read || action >= process::CallAction::open_directory) &&
        file_call(*decoded, frame))
        return 0;
    // The memory service (process.md#memory); a call naming no mapping, or
    // one whose length differs, ends the process like any invalid call.
    if (action == process::CallAction::map || action == process::CallAction::remap ||
        action == process::CallAction::unmap) {
        auto &memory = *running.space;
        const auto result = action == process::CallAction::map ? memory.map_memory(decoded->length)
                            : action == process::CallAction::remap
                                ? memory.remap_memory(decoded->base, decoded->value, decoded->length)
                                : memory.unmap_memory(decoded->base, decoded->length);
        if (result.outcome == ProcessSpace::Outcome::broken)
            fail("memory service");
        if (result.outcome == ProcessSpace::Outcome::resume) {
            // Fixture: the whole space verifies after every memory call.
            if ((running.flags & 4) && !memory.verify())
                fail("memory walk");
            ++running.memory_calls;
            frame[frame_rax] = result.value;
            return 0;
        }
    }
    outcome.invalid_call = true;
    outcome.operation = frame[frame_rax];
    outcome.rip = frame[frame_rip];
    return 1;
}
} // namespace

// Every trap, interrupt and kernel call (kernel/exceptions.S). A process's own
// frame is the exact RSP0 frame under its root, which the Aurora policy then
// verifies; it ends only that process (result 1) or resumes it (0). The timer
// drain is the one kernel-mode interrupt admitted; anything else stops.
auto dispatch(U64, U64, U64, U64, U64, U64) -> U64 asm("aurora_exception_dispatch")
    __attribute__((visibility("hidden")));
auto dispatch(U64 vector, U64 error, U64 rip, U64 cs, U64 frame, U64) -> U64 {
    const auto begin = reinterpret_cast<U64>(&drain_begin), end = reinterpret_cast<U64>(&drain_end);
    if (vector == 64 && cs == 8 && draining && rip >= begin && rip <= end && root() == kernel_root &&
        frame >= owned_arena + Handoff::stack_bottom && frame < owned_arena + Handoff::stack_top) {
        if (!Timer::acknowledge())
            kernel_fault(vector, error, rip, cs);
        draining = false;
        return 0;
    }
    if (!running.space || (cs & 3) != 3 || frame != owned_arena + BootstrapLayout::rsp0_top - frame_words * 8 ||
        root() != running.space->root())
        kernel_fault(vector, error, rip, cs);
    auto *words = reinterpret_cast<volatile U64 *>(frame);
    process::ProcessTrap trap{vector, error, words[17], words[18], words[19], words[20], words[21], 0, 0x10000};
    if (vector == 14)
        asm volatile("mov %%cr2, %0" : "=r"(trap.cr2));
    if (vector == 6 && running.space->executable(trap.rip, 2))
        trap.opcode = *reinterpret_cast<const volatile std::uint8_t *>(trap.rip) |
                      (U64{*reinterpret_cast<const volatile std::uint8_t *>(trap.rip + 1)} << 8);
    const auto kind = process::trap(trap);
    if (!kind || *kind == process::TrapClass::kernel)
        kernel_fault(vector, error, rip, cs);
    if (*kind == process::TrapClass::timer)
        return charge_tick(vector, error, rip, cs);
    if (*kind == process::TrapClass::call)
        return kernel_call(words);
    // A first touch of a mapping's absent page commits a zeroed, already
    // charged frame (process.md#memory).
    const auto committed = *kind == process::TrapClass::page_fault
                               ? process::memory_fault(running.space->records(), trap.cr2, error)
                               : process::MemoryLookup{};
    if (committed.malformed)
        fail("Aurora memory fault decision");
    if (committed.index) {
        if (!running.space->commit(trap.cr2))
            fail("memory commit");
        if ((running.flags & 4) && !running.space->verify())
            fail("memory walk");
        ++running.commits;
        return 0;
    }
    outcome.trap = *kind;
    outcome.vector = vector;
    outcome.error = error;
    outcome.rip = trap.rip;
    outcome.cr2 = trap.cr2;
    return 1;
}

namespace {
auto end_record(U64 run) -> void {
    Serial::text("AURORA_PROCESS_END:");
    field("run", run);
    if (outcome.exited) {
        Serial::text(" reason=exit");
        field("status", outcome.status);
    } else if (outcome.watchdog) {
        Serial::text(" reason=watchdog");
        field("ticks", running.used);
    } else if (outcome.invalid_call) {
        Serial::text(" reason=call");
        field("operation", outcome.operation);
        field("rip", outcome.rip);
    } else {
        Serial::text(" reason=");
        Serial::text(name(trap_names, static_cast<U64>(outcome.trap)));
        field("vector", outcome.vector);
        field("error", outcome.error);
        field("rip", outcome.rip);
        field("cr2", outcome.cr2);
    }
    Serial::text("\r\n");
}

// Fixture: the load walk rejects each single-entry edit, each undone before
// the next: a no-execute code leaf, a code leaf aliasing the argument page's
// frame, an extra leaf after the argument block and a user bit on the shared
// arena slot's entry.
auto walk_cases(ProcessSpace &process_space, U64 code, U64 block, U64 run) -> void {
    const auto code_leaf = process_space.entry(code, 1), block_leaf = process_space.entry(block, 1),
               after_leaf = process_space.entry(block + frames::page, 1), slot = process_space.entry(shared.slot[0], 2);
    if (!code_leaf || !block_leaf || !after_leaf || !slot)
        fail("walk probe entries");
    const auto value = [&](const ProcessSpace::Slot &at) {
        auto *words = space.open(at.table);
        const auto result = words ? reinterpret_cast<volatile U64 *>(words)[at.slot] : 0;
        if (words)
            space.close();
        return result;
    };
    const auto set = [&](const ProcessSpace::Slot &at, U64 word) {
        auto *words = space.open(at.table);
        if (!words)
            fail("walk probe window");
        reinterpret_cast<volatile U64 *>(words)[at.slot] = word;
        space.close();
    };
    const auto code_word = value(*code_leaf), block_word = value(*block_leaf), slot_word = value(*slot);
    class Edit final {
    public:
        ProcessSpace::Slot at;
        U64 before, after;
    };
    const Edit edits[] = {
        {*code_leaf, code_word, code_word | PageTables::nx},
        {*code_leaf, code_word, (block_word & KernelSpace::address_mask) | (code_word & ~KernelSpace::address_mask)},
        {*after_leaf, value(*after_leaf), block_word},
        {*slot, slot_word, slot_word | 4},
    };
    U64 rejected = 0;
    for (const auto &edit : edits) {
        set(edit.at, edit.after);
        rejected += !process_space.verify();
        set(edit.at, edit.before);
    }
    if (rejected != 4 || !process_space.verify())
        fail("process walk edit admitted");
    Serial::text("AURORA_PROCESS_WALK_OK:");
    field("run", run);
    field("rejected", rejected);
    Serial::text("\r\n");
}

// Framed base64 export records of one committed overlay file
// (process.md#export), its path encoded byte by byte (process.md#files).
auto export_file(U64 record) -> bool {
    const auto size = files.record(record).size;
    bool encoded = true;
    const auto path = [&]() {
        return files.path(record, [&](std::uint8_t byte) {
            const auto text = process::path_text(byte);
            encoded = encoded && text;
            for (unsigned i = 0; text && i < text->count; ++i)
                Serial::put(static_cast<std::uint8_t>(text->characters[i]));
        });
    };
    Serial::text("AURORA_EXPORT_BEGIN: path=");
    if (!path() || !encoded)
        return false;
    field("bytes", size);
    Serial::text("\r\n");
    U64 lines = 0;
    std::array<std::byte, 57> line{};
    for (U64 offset = 0; offset < size; offset += line.size()) {
        const auto count = aurora::uefi::least(line.size(), size - offset);
        if (!files.bytes(record, offset, {line.data(), count}))
            return false;
        Serial::text("AURORA_EXPORT_DATA: ");
        for (U64 at = 0; at < count; at += 3) {
            const auto group = process::base64_group({line.data(), count}, at);
            if (!group)
                return false;
            for (unsigned i = 0; i < 4; ++i)
                Serial::put(static_cast<std::uint8_t>(*group >> (8 * i)));
        }
        Serial::text("\r\n");
        ++lines;
    }
    Serial::text("AURORA_EXPORT_END: path=");
    if (!path() || !encoded)
        return false;
    field("lines", lines);
    Serial::text("\r\n");
    return true;
}

auto refuse(U64 run, std::string_view reason) -> void {
    Serial::text("AURORA_PROCESS_REJECTED:");
    field("run", run);
    Serial::text(" reason=");
    Serial::text(reason);
    Serial::text("\r\n");
}

// Load, run and release one process of the run list.
auto run_one(std::span<const std::byte> view, std::span<const std::byte> runs, const process::RunEntry &entry, U64 run)
    -> void {
    const auto path = runs.subspan(entry.path, entry.path_bytes);
    const auto arguments = runs.subspan(entry.arguments, entry.argument_bytes);
    Serial::text("AURORA_PROCESS_RUN:");
    field("run", run);
    Serial::text(" path=");
    for (const auto byte : path)
        Serial::put(std::to_integer<std::uint8_t>(byte));
    field("ticks", entry.ticks);
    Serial::text("\r\n");
    const auto image = process::volume_lookup(view, path);
    if (!image)
        return refuse(run, "missing");
    const auto admitted = process::elf_admit(*image);
    if (!admitted)
        fail("Aurora ELF admission");
    if (*admitted != process::ElfVerdict::valid)
        return refuse(run, name(elf_names, static_cast<U64>(*admitted)));
    const auto layout = process::layout(*image, shared.reserved_first, shared.reserved_end, arguments.size());
    if (!layout)
        fail("Aurora process layout");
    if (*layout != process::LayoutVerdict::valid)
        return refuse(run, name(layout_names, static_cast<U64>(*layout)));
    // The load and the memory service are charged against frames free now.
    const auto budget = process::memory_budget(*image, arguments.size(), shared.slots, entry.quota, table.free());
    if (!budget)
        fail("Aurora memory budget");
    if (budget->verdict != static_cast<U64>(process::BudgetVerdict::valid))
        return refuse(run, "quota");
    ProcessSpace process_space{space,
                               table,
                               ranges,
                               space.mappings(ranges.frames()),
                               shared,
                               space.process_records(),
                               frames::first_owner + run};
    if (!process_space.begin())
        fail("process root");
    U64 regions = 0, stack_top = 0, block = 0;
    for (;; ++regions) {
        const auto region = process::region(*image, regions, arguments.size());
        if (!region)
            fail("Aurora process region");
        const auto kind = static_cast<process::RegionKind>(region->kind);
        if (kind == process::RegionKind::none)
            break;
        if (kind == process::RegionKind::stack)
            stack_top = region->first + region->pages * frames::page;
        if (kind == process::RegionKind::arguments)
            block = region->first;
        if (!process_space.map(*region,
                               kind == process::RegionKind::segment     ? *image
                               : kind == process::RegionKind::arguments ? arguments
                                                                        : std::span<const std::byte>{}))
            fail("process mapping");
    }
    const auto entry_point = process::elf_entry(*image);
    if (!process_space.budget(*budget) || !stack_top || !block || !process_space.executable(entry_point, 1) ||
        !process_space.verify())
        fail("process load walk");
    if (entry.flags & 2)
        walk_cases(process_space, entry_point, block, run);
    Serial::text("AURORA_PROCESS_LOADED:");
    field("run", run);
    field("regions", regions);
    field("pages", process_space.leaves());
    field("tables", process_space.tables());
    field("quota", budget->quota - budget->charged);
    Serial::text("\r\n");
    // The initial stack ends in a zero qword for programs that read one.
    const U64 context[] = {entry_point, stack_top - 16, block, arguments.size(), process_space.root()};
    running = Running{&process_space, run, entry.flags, entry.ticks, entry.ticks, 0, 0, 0, 0};
    outcome = Outcome{};
    file_store.process = &process_space;
    if (!files.begin(view, file_store))
        fail("file service start");
    if (!Timer::arm(tick_count))
        fail("watchdog arm");
    if (process_enter(context) != 1 || root() != kernel_root || !Timer::stop())
        fail("process exit");
    running.space = nullptr;
    if (Timer::pending()) {
        draining = true;
        process_drain();
    }
    if (draining || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        fail("timer drain");
    end_record(run);
    if (!process_space.verify())
        fail("process exit walk");
    // The run's committed files leave over serial; then the overlay is gone.
    if (!files.finish([&](U64 record) {
            return export_file(record);
        }))
        fail("file service finish");
    file_store.process = nullptr;
    const auto memory = process_space.memory();
    const auto released = process_space.release();
    const auto audit = table.audit();
    if (!released || !audit.consistent || audit.allocated)
        fail("process release");
    Serial::text("AURORA_PROCESS_RELEASED:");
    field("run", run);
    field("frames", *released);
    field("memory", memory);
    field("calls", running.memory_calls);
    field("commits", running.commits);
    Serial::text("\r\n");
}

// The row's run list, runs/<case> in the volume, run in order.
[[noreturn]] auto run_list(U64 arena, std::span<const std::byte> view, U64 selected) -> void {
    char path[] = "runs/000";
    std::size_t length = 5;
    for (U64 scale = 100; scale; scale /= 10)
        if (selected >= scale || scale == 1)
            path[length++] = static_cast<char>('0' + selected / scale % 10);
    const auto runs = process::volume_lookup(view, bytes_of({path, length}));
    if (!runs)
        fail("run list lookup");
    const auto verdict = process::runs_admit(*runs);
    if (verdict != process::RunsVerdict::valid) {
        Serial::text("AURORA_PROCESS_RUNS_REJECTED: reason=");
        Serial::text(verdict ? name(runs_names, static_cast<U64>(*verdict)) : "malformed");
        Serial::text("\r\n");
        fail("run list admission");
    }
    install_architecture(arena);
    capture_shared(arena);
    process_kernel_root = kernel_root;
    U64 count = 0;
    for (;; ++count) {
        const auto entry = process::run(*runs, count);
        if (!entry)
            fail("Aurora run entry");
        if (!entry->found)
            break;
        run_one(view, *runs, *entry, count + 1);
    }
    Serial::text("AURORA_PROCESS_RUNS_OK:");
    field("runs", count);
    field("free", table.free());
    Serial::text("\r\n");
    aurora::hardware::Io::write(0xf4, 0x10);
    for (;;)
        asm volatile("cli; hlt");
}
} // namespace

auto aurora::uefi::run_process(U64 arena, const Bytes &h) -> void {
    owned_arena = arena;
    kernel_root = h.get(88);
    const auto selected = h.get(Handoff::case_word);
    if (selected)
        establish_timer(arena, h);
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
    const auto plan = KernelSpace::plan(ranges.frames(), volume_pages, KernelSpace::process_pages);
    const PageTables tables{arena + Handoff::tables_offset, static_cast<std::size_t>(h.get(96))};
    if (!plan || !space.bind(arena + Handoff::tables_offset, tables.window_slot()) ||
        !space.build(ranges, *plan, volume))
        fail("kernel space");
    const auto records = space.metadata(ranges.frames()), mappings = space.mappings(ranges.frames());
    for (auto &record : records)
        record = 0;
    for (auto &mapping : mappings)
        mapping = 0;
    if (records.empty() || mappings.empty() || !table.bind(records, ranges, plan->tables, plan->metadata))
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
    if (selected)
        run_list(arena, view, selected);
    frame_cases(h.get(96));
    space_cases(*plan, h.get(96));
    export_entry(view, exported);
    Serial::text("AURORA_PROCESS_OK\r\n");
    aurora::hardware::Io::write(0xf4, 0x10);
    for (;;)
        asm volatile("cli; hlt");
}
