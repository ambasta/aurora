#include "process.hpp"
#include "acpi.hpp"
#include "apic-timer-io.hpp"
#include "../retained-budget.hpp"
#include "../retained-service.hpp"
#include "../round-robin-transport.hpp"
#include "process-space.hpp"
#include "image-snapshot.hpp"
#ifdef AURORA_UEFI_NVME
#include "nvme.hpp"
#endif
#include "../console.hpp"
#include "../execution-session.hpp"

#ifdef AURORA_PRODUCTION
#include "../console-uart.hpp"
using Serial = aurora::console::Uart<aurora::hardware::Io, aurora::console::FifoTrigger::fourteen>;
#else
using aurora::hardware::Serial;
#endif
using U64 = std::uint64_t;
namespace frames = aurora::uefi::frames;
namespace process = aurora::uefi::process;
using aurora::BootstrapLayout;
using aurora::uefi::Bytes;
using aurora::uefi::Handoff;
using aurora::uefi::KernelSpace;
using aurora::uefi::PageTables;
using aurora::uefi::ProcessSpace;
using aurora::uefi::RunResult;
using aurora::uefi::RunStatus;
using Timer = aurora::uefi::LocalApicTimerIo;
#ifdef AURORA_PRODUCTION
auto source_execute(const aurora::execution::Argument *, aurora::execution::Result *)
    -> void asm("__au_runtime_process_execute_command") __attribute__((visibility("hidden")));
#endif

namespace {
enum class XfsReadonlyProfile : U64 {
    fresh_format,
    linux_6_12_x86_64_clean
};
constexpr auto least(U64 a, U64 b) -> U64 {
    return a < b ? a : b;
}
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

#ifndef AURORA_PRODUCTION
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
#endif

} // namespace

// The process entry, exit and drain (process-user.S).
extern U64 process_kernel_root asm("uefi_process_kernel_root") __attribute__((visibility("hidden")));
extern const std::byte drain_begin asm("uefi_process_drain_begin") __attribute__((visibility("hidden")));
extern const std::byte drain_end asm("uefi_process_drain_end") __attribute__((visibility("hidden")));
auto process_enter(const U64 *) -> U64 asm("uefi_process_enter") __attribute__((visibility("hidden")));
auto process_resume(const U64 *, U64) -> U64 asm("uefi_process_resume") __attribute__((visibility("hidden")));
auto process_handler(U64) -> U64 asm("uefi_process_handler") __attribute__((visibility("hidden")));
auto process_drain() -> void asm("uefi_process_drain") __attribute__((visibility("hidden")));

// Processes (process.md#processes). One process runs at a time; the dispatcher
// below reaches it through these words, which only the kernel writes.
namespace {
// A watchdog tick: 2^24 LAPIC counts, or 2^31 for a run with flag 8.
class BudgetPlatform final {
public:
    static auto quiet() -> bool {
        return Timer::irq_off();
    }
    [[noreturn]] static auto fail() -> void {
        ::fail("retained budget lifetime");
    }
};
using BudgetRoot = aurora::budget::Root<BudgetPlatform>;
// The interrupt frame: 15 saved registers (R15 first, RAX last), the vector and
// error code, then the CPU's RIP, CS, RFLAGS, RSP and SS.
constexpr std::size_t frame_words = BootstrapLayout::fault_frame_words, frame_rax = 14, frame_rdi = 8, frame_rsi = 9,
                      frame_rdx = 11, frame_r10 = 5, frame_rip = 17;
class Running final {
public:
    ProcessSpace *space = nullptr;
    BudgetRoot *budget = nullptr;
    U64 run = 0, flags = 0, calls = 0, memory_calls = 0, commits = 0, peak = 0;
    std::array<U64, frame_words> *continuation = nullptr;
    U64 slice = 0, service = 0, block_generation = 0, block_sectors = 0, companion = 0;
    U64 recovery_generation = 0, recovery_sectors = 0;
    U64 mounted_generation = 0, mounted_sectors = 0;
    bool external = false;
};
// How the process ended, copied from its last kernel entry.
class Outcome final {
public:
    bool exited = false, watchdog = false, invalid_call = false, parked = false, exchange = false, request = false,
         output = false, unavailable = false, cancelled = false;
    process::TrapClass trap = process::TrapClass::kernel;
    U64 status = 0, vector = 0, error = 0, rip = 0, cr2 = 0, operation = 0;
    U64 terminal_ticks = 0, terminal_run = 0, terminal_service = 0;
};
constinit Running running;
constinit Outcome outcome;
constinit U64 owned_arena = 0, kernel_root = 0;
constinit bool draining = false;
constinit aurora::uefi::ProcessOutput output_sink = nullptr;
constinit void *output_context = nullptr;
#ifdef AURORA_PRODUCTION
constinit bool runtime_initialized = false, runtime_detached = false;
#endif
constinit aurora::uefi::BootStorageSelection runtime_storage;
constinit U64 next_run = 0;
constinit bool output_error_stream = false;
constinit RunStatus load_refusal = RunStatus::malformed;
auto root() -> U64;
class ServicePlatform final {
public:
    static auto quiet() -> bool {
        return Timer::irq_off() && root() == kernel_root && !running.space;
    }
    [[noreturn]] static auto fail() -> void {
        ::fail("retained service lifetime");
    }
};
using ServiceRoot = aurora::service::Root<ServicePlatform>;
constinit ServiceRoot service_root;

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

#ifndef AURORA_PRODUCTION
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

#endif

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

#ifndef AURORA_PRODUCTION
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

#endif

auto charge_tick(U64 vector, U64 error, U64 rip, U64 cs, const volatile U64 *frame) -> U64;

class Resident final {
public:
    std::optional<ProcessSpace> space;
    Running state;
    BudgetRoot budget;
    std::array<U64, frame_words> continuation{};
    std::array<U64, 8> initial{};
    bool started = false;
};
constinit std::array<Resident, KernelSpace::process_slots> residents;

// A copied synchronous endpoint, not a namespace or backing store. Exactly
// one transaction is outstanding. Source/transaction never come from a client.
class Endpoint final {
public:
    static constexpr U64 capacity = 65536, window_bytes = 131136, request_offset = 64, reply_offset = 65600;
    std::array<std::byte, capacity> bytes{};
    U64 generation = 0, window = 0, transaction = 0, next = 0, source = 0, count = 0;
    bool waiting = false, replied = false, delivery = false, completion = false, caller_cancelled = false;
    std::optional<std::size_t> caller;
    process::KernelCall call{};
    U64 written = 0, request_operation = 0, invalid_reply_operation = 0;
};
constinit Endpoint endpoint;
constinit std::optional<aurora::uefi::ImageSnapshot> snapshot;
constinit BudgetRoot loader_budget;
#ifndef AURORA_PRODUCTION
constinit U64 export_armed = 0;
#endif
auto reset_loader(U64 limit, U64 scale = 0) -> void {
    if (!loader_budget.initialize_or_reset(limit, scale))
        fail("loader budget configuration");
}
constinit bool loading_image = false;
#ifdef AURORA_UEFI_NVME
constinit U64 next_block_generation = 0;
#endif
constinit U64 block_service = 0, block_generation = 0, block_sectors = 0;
// This separate boot role is never set by ordinary load_image/run or Serve.
// The recovery composition will mint it only after its private image is admitted.
constinit U64 recovery_owner = 0, recovery_root = 0, recovery_generation = 0, recovery_sectors = 0;
constinit U64 mounted_owner = 0, mounted_root = 0, mounted_generation = 0, mounted_sectors = 0, mounted_service = 0;
#ifdef AURORA_PROCESS_FIXTURE
constinit U64 recovery_cut_case = 0, mounted_cut_case = 0;
constinit bool mounted_owner_termination = false;
#endif
constinit bool recovery_completed = false;
constinit std::array<std::byte, 512> block_copy{};

auto save_frame(const volatile U64 *frame) -> void {
    if (!running.continuation)
        fail("missing process continuation");
    for (std::size_t word = 0; word < frame_words; ++word)
        (*running.continuation)[word] = frame[word];
    outcome.parked = true;
}

// Partial LAPIC counts belong to the outgoing process. Voluntary exchanges
// never renew a quantum; even a zero-count handoff consumes at least one count.
auto charge_counts(BudgetRoot &state, U64 count, bool progress) -> bool {
    const auto result = progress ? state.progress(count) : state.charge(count);
    if (result == aurora::budget::Charge::rejected)
        fail("Aurora budget charge");
    return result == aurora::budget::Charge::available;
}
auto elapsed(U64 count, bool progress = false) -> void {
    if (running.service && (endpoint.caller || loading_image) && !endpoint.caller_cancelled) {
        auto &caller = endpoint.caller ? residents[*endpoint.caller].budget : loader_budget;
        if (!charge_counts(caller, count, progress))
            endpoint.caller_cancelled = true;
    }
    if (!charge_counts(*running.budget, count, progress)) {
        outcome.watchdog = true;
        outcome.parked = false;
        outcome.exited = false;
    }
}
auto arm_slice() -> void {
    U64 count = running.budget->quantum();
    if (running.service && (endpoint.caller || loading_image) && !endpoint.caller_cancelled) {
        const auto caller = endpoint.caller ? residents[*endpoint.caller].budget.quantum() : loader_budget.quantum();
        if (caller < count)
            count = caller;
    }
    running.slice = count;
    if (!Timer::arm(static_cast<std::uint32_t>(count)))
        fail("watchdog arm");
}
auto charge_tick(U64 vector, U64 error, U64 rip, U64 cs, const volatile U64 *frame) -> U64 {
    if (!running.slice || !Timer::acknowledge())
        kernel_fault(vector, error, rip, cs);
    elapsed(running.slice);
    running.slice = 0;
    if (outcome.watchdog)
        return 1;
    if (running.continuation) {
        save_frame(frame);
        return 1;
    }
    arm_slice();
    return 0;
}

// Every resident's unallocated quota stays reserved, including mappings that
// have never been touched. Physical free frames alone would overcommit them.
auto available_frames() -> U64 {
    U64 available = table.free();
    for (const auto &resident : residents) {
        if (!resident.space)
            continue;
        const auto &held = *resident.space;
        if (held.held() > held.quota() || held.quota() - held.held() > available)
            fail("resident quota accounting");
        available -= held.quota() - held.held();
    }
    return available;
}

// Complete lifecycle audit, not a per-call whole-RAM scan. The table checks its
// per-owner counters against every frame; the aggregate must equal precisely
// the resident owners. Each root's own walk checks all its mappings.
auto audit_residents() -> bool {
    U64 allocated = 0;
    if (snapshot) {
        if (!snapshot->verify() || snapshot->held() != table.allocated(snapshot->owner()))
            return false;
        allocated = snapshot->held();
    }
    for (auto &resident : residents) {
        if (!resident.space)
            continue;
        if (!resident.space->verify() || resident.space->held() > table.allocated() - allocated)
            return false;
        allocated += resident.space->held();
    }
    const auto audit = table.audit();
    return audit.consistent && audit.allocated == allocated;
}
// The kernel's copy of a call's path, read from the process before any
// decision sees it.

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

// The only constructor of a DMA read context sits behind authenticated process
// state, not behind a caller-selected generation/root. Cache hits pass this
// same boundary. The broker receives no user pointer.
} // namespace
#ifdef AURORA_UEFI_NVME
namespace aurora::uefi {
class ProcessBlockBroker final {
public:
    static auto read(U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
        if (!running.space || !running.service || running.service != block_service || !running.block_generation ||
            running.block_generation != block_generation || running.block_sectors != block_sectors ||
            root() != running.space->root() || !space.closed())
            fail("block authority");
        U64 flags;
        asm volatile("pushfq; popq %0" : "=r"(flags));
        if (flags & (1ULL << 9))
            fail("block interrupt state");
        const auto sectors = nvme_sector_count();
        // Quarantine is absorbing. The original grant remains authenticated,
        // but conveys no usable backend and is never refreshed after failure.
        if (!sectors)
            return NvmeReadStatus::unavailable;
        if (sectors != block_sectors)
            fail("block extent changed");
        if (lba >= sectors)
            return NvmeReadStatus::out_of_range;
        const NvmeReadContext context(running.space->root(), running.block_generation);
        const auto result = nvme_read_sector(context, lba, output);
        if (!space.closed() || root() != running.space->root())
            fail("block window restoration");
        return result;
    }
};
class ProcessMountedBroker final {
    [[nodiscard]] static auto context() -> NvmeMountedContext {
        if (!running.space || !running.service || running.service != mounted_service || !running.mounted_generation ||
            running.mounted_generation != mounted_generation || running.mounted_sectors != mounted_sectors ||
            running.space->owner() != mounted_owner || running.space->root() != mounted_root ||
            root() != mounted_root || !space.closed())
            fail("mounted authority");
        U64 flags;
        asm volatile("pushfq; popq %0" : "=r"(flags));
        if (flags & (1ULL << 9))
            fail("mounted interrupt state");
        const auto sectors = nvme_mounted_sector_count();
        if (sectors && sectors != mounted_sectors)
            fail("mounted extent changed");
        return NvmeMountedContext(mounted_root, mounted_generation);
    }
    static auto restored() -> void {
        if (!space.closed() || root() != mounted_root)
            fail("mounted window restoration");
    }

#ifdef AURORA_PROCESS_FIXTURE
    static auto cut(NvmeReadStatus status, U64 operation, U64 lba = 0) -> void {
        if (status != NvmeReadStatus::success || !mounted_cut_case)
            return;
        const auto ordinal = operation == 18 ? nvme_mounted_admitted_writes() : nvme_mounted_admitted_flushes();
        if (mounted_cut_case == 40 && operation == 19 && ordinal == 5) {
            Serial::text("AURORA_MOUNTED_OWNER_LOSS:");
            field("generation", mounted_generation);
            field("writes", nvme_mounted_admitted_writes());
            field("flushes", nvme_mounted_admitted_flushes());
            Serial::text("\r\n");
            mounted_owner_termination = true;
            return;
        }
        const bool selected =
            (mounted_cut_case >= 18 && mounted_cut_case <= 33 && operation == 18 && ordinal == mounted_cut_case - 17) ||
            (mounted_cut_case >= 34 && mounted_cut_case <= 38 && operation == 19 && ordinal == mounted_cut_case - 33);
        if (!selected)
            return;
        // Suspend only this closed fixture after acknowledged backend completion
        // and restored mappings. This does not model torn writes or power loss.
        Serial::text("AURORA_MOUNTED_CUT:");
        field("case", mounted_cut_case);
        field("operation", operation);
        field("ordinal", ordinal);
        field("lba", lba);
        field("generation", mounted_generation);
        field("writes", nvme_mounted_admitted_writes());
        field("flushes", nvme_mounted_admitted_flushes());
        Serial::text("\r\n");
        aurora::hardware::Io::write(0xf4, 0x12);
        for (;;)
            asm volatile("cli; hlt");
    }
#endif

public:
    [[nodiscard]] static auto read(U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
        const auto result = nvme_mounted_read(context(), lba, output);
        restored();
        return result;
    }
    [[nodiscard]] static auto write(U64 lba, std::span<const std::byte, 512> input) -> NvmeReadStatus {
        const auto result = nvme_mounted_write(context(), lba, input);
        restored();
#ifdef AURORA_PROCESS_FIXTURE
        cut(result, 18, lba);
#endif
        return result;
    }
    [[nodiscard]] static auto flush() -> NvmeReadStatus {
        const auto result = nvme_mounted_flush(context());
        restored();
#ifdef AURORA_PROCESS_FIXTURE
        cut(result, 19);
#endif
        if (result == NvmeReadStatus::success) {
            Serial::text("AURORA_MOUNTED_FENCE:");
            field("generation", mounted_generation);
            field("writes", nvme_mounted_admitted_writes());
            field("flushes", nvme_mounted_admitted_flushes());
            Serial::text("\r\n");
        }
        return result;
    }
    [[nodiscard]] static auto budget() -> unsigned {
        const auto result = nvme_mounted_budget(context());
        restored();
        return result;
    }
};
class ProcessRecoveryBroker final {
    [[nodiscard]] static auto context() -> NvmeRecoveryContext {
        if (!running.space || running.service || !running.recovery_generation ||
            running.recovery_generation != recovery_generation || running.recovery_sectors != recovery_sectors ||
            running.space->owner() != recovery_owner || running.space->root() != recovery_root ||
            root() != recovery_root || !space.closed())
            fail("recovery authority");
        U64 flags;
        asm volatile("pushfq; popq %0" : "=r"(flags));
        if (flags & (1ULL << 9))
            fail("recovery interrupt state");
        const auto sectors = nvme_recovery_sector_count();
        if (sectors && sectors != recovery_sectors)
            fail("recovery extent changed");
        return NvmeRecoveryContext(recovery_root, recovery_generation);
    }
    static auto restored() -> void {
        if (!space.closed() || root() != recovery_root)
            fail("recovery window restoration");
    }

#ifdef AURORA_PROCESS_FIXTURE
    static auto cut(NvmeReadStatus status, U64 operation, U64 lba = 0) -> void {
        if (status != NvmeReadStatus::success || !recovery_cut_case)
            return;
        const auto ordinal = operation == 18 ? nvme_recovery_admitted_writes() : nvme_recovery_admitted_flushes();
        const bool selected = (recovery_cut_case >= 13 && recovery_cut_case <= 15 && operation == 19 &&
                               ordinal == recovery_cut_case - 12) ||
                              (recovery_cut_case == 16 && operation == 18 && ordinal == 1);
        if (!selected)
            return;
        // The real source program is suspended only after acknowledged backend
        // completion and restoration. This is not a physical power-loss model.
        Serial::text("AURORA_RECOVERY_CUT:");
        field("case", recovery_cut_case);
        field("operation", operation);
        field("ordinal", ordinal);
        field("lba", lba);
        field("generation", recovery_generation);
        field("writes", nvme_recovery_admitted_writes());
        field("flushes", nvme_recovery_admitted_flushes());
        Serial::text("\r\n");
        aurora::hardware::Io::write(0xf4, 0x12);
        for (;;)
            asm volatile("cli; hlt");
    }
#endif

public:
    [[nodiscard]] static auto read(U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
        const auto result = nvme_recovery_read(context(), lba, output);
        restored();
        return result;
    }
    [[nodiscard]] static auto write(U64 lba, std::span<const std::byte, 512> input) -> NvmeReadStatus {
        const auto result = nvme_recovery_write(context(), lba, input);
        restored();
#ifdef AURORA_PROCESS_FIXTURE
        cut(result, 18, lba);
#endif
        return result;
    }
    [[nodiscard]] static auto flush() -> NvmeReadStatus {
        const auto result = nvme_recovery_flush(context());
        restored();
#ifdef AURORA_PROCESS_FIXTURE
        cut(result, 19);
#endif
        return result;
    }
    [[nodiscard]] static auto budget() -> unsigned {
        const auto result = nvme_recovery_budget(context());
        restored();
        return result;
    }
};
} // namespace aurora::uefi
#endif
namespace {
auto writable_block_call(volatile U64 *frame, bool mounted) -> bool {
    const auto operation = frame[frame_rax];
#ifndef AURORA_UEFI_NVME
    static_cast<void>(mounted);
#endif
    // Copy the complete sector through the normal checked user range. The
    // wrapper's stage count is not inspected or trusted by this boundary.
    if (operation == 17 || operation == 18) {
        const auto bytes = user_bytes(frame[frame_rdi], block_copy.size(), operation == 17);
        if (!bytes)
            return false;
        for (U64 at = 0; at < block_copy.size(); ++at)
            block_copy[at] = operation == 18 ? (*bytes)[at] : std::byte{};
        U64 status = 3;
#ifdef AURORA_UEFI_NVME
        status = mounted
                     ? static_cast<U64>(operation == 17
                                            ? aurora::uefi::ProcessMountedBroker::read(frame[frame_rsi], block_copy)
                                            : aurora::uefi::ProcessMountedBroker::write(frame[frame_rsi], block_copy))
                     : static_cast<U64>(operation == 17
                                            ? aurora::uefi::ProcessRecoveryBroker::read(frame[frame_rsi], block_copy)
                                            : aurora::uefi::ProcessRecoveryBroker::write(frame[frame_rsi], block_copy));
#endif
        if (operation == 17) {
            for (U64 at = 0; at < block_copy.size(); ++at)
                (*bytes)[at] = status ? std::byte{} : block_copy[at];
        }
        for (auto &byte : block_copy)
            byte = std::byte{};
        frame[frame_rax] = status;
        frame[frame_rdx] = operation == 17 && status == 0 ? 512 : 0;
    } else {
        U64 result = operation == 20 ? 0 : 3;
#ifdef AURORA_UEFI_NVME
        result = mounted ? (operation == 20 ? aurora::uefi::ProcessMountedBroker::budget()
                                            : static_cast<U64>(aurora::uefi::ProcessMountedBroker::flush()))
                         : (operation == 20 ? aurora::uefi::ProcessRecoveryBroker::budget()
                                            : static_cast<U64>(aurora::uefi::ProcessRecoveryBroker::flush()));
#endif
        frame[frame_rax] = result;
        frame[frame_rdx] = 0;
    }
    return true;
}
auto recovery_call(volatile U64 *frame) -> bool {
    const auto operation = frame[frame_rax];
    if (!running.recovery_generation || running.service || frame[frame_rdx] != running.recovery_generation ||
        frame[frame_r10] || (operation >= 19 && (frame[frame_rdi] || frame[frame_rsi])))
        return false;
    return writable_block_call(frame, false);
}
auto mounted_call(volatile U64 *frame) -> bool {
    const auto operation = frame[frame_rax];
    if (!running.mounted_generation || !running.service || frame[frame_rdx] != running.mounted_generation ||
        frame[frame_r10] || (operation >= 19 && (frame[frame_rdi] || frame[frame_rsi])))
        return false;
    return writable_block_call(frame, true);
}
auto block_read(volatile U64 *frame) -> bool {
    if (frame[frame_r10] || frame[frame_rdx] != running.block_generation ||
        (running.block_generation && !running.service))
        return false;
    const auto destination = user_bytes(frame[frame_rdi], block_copy.size(), true);
    if (!destination)
        return false;
    for (auto &byte : block_copy)
        byte = std::byte{0};
    U64 status = 3;
#ifdef AURORA_UEFI_NVME
    if (running.block_generation)
        status = static_cast<U64>(aurora::uefi::ProcessBlockBroker::read(frame[frame_rsi], block_copy));
#endif
    if (status)
        for (auto &byte : block_copy)
            byte = std::byte{0};
    for (U64 at = 0; at < block_copy.size(); ++at)
        (*destination)[at] = block_copy[at];
    frame[frame_rax] = status;
    frame[frame_rdx] = status == 0 ? block_copy.size() : 0;
    return true;
}

auto endpoint_exchange(volatile U64 *frame) -> bool {
    const U64 window = frame[frame_rdi], count = frame[frame_rsi], generation = frame[frame_rdx],
              transaction = frame[frame_r10];
    if (!running.service || generation != running.service || generation != endpoint.generation ||
        count > Endpoint::capacity || endpoint.waiting || endpoint.replied ||
        (endpoint.window && endpoint.window != window) || transaction != endpoint.transaction ||
        (!transaction && count))
        return false;
    const auto bytes = user_bytes(window, Endpoint::window_bytes, true);
    if (!bytes)
        return false;
    if (transaction) {
        for (U64 at = 0; at < count; ++at)
            endpoint.bytes[at] = (*bytes)[Endpoint::reply_offset + at];
        endpoint.count = count;
        endpoint.replied = true;
    }
    endpoint.window = window;
    endpoint.waiting = true;
    outcome.exchange = true;
    save_frame(frame);
    return true;
}
auto message_header(U64 operation, U64 id, U64 offset, U64 count) -> void {
    endpoint.request_operation = operation;
    for (U64 at = 0; at < 64; ++at)
        endpoint.bytes[at] = std::byte{0};
    aurora::uefi::put(endpoint.bytes, 0, operation);
    aurora::uefi::put(endpoint.bytes, 8, id);
    aurora::uefi::put(endpoint.bytes, 16, offset);
    aurora::uefi::put(endpoint.bytes, 24, count);
    endpoint.count = 64 + count;
}
// Copy and validate all caller authority before parking. Neither this decoded
// call nor any message field can choose the endpoint or reply destination.
auto file_request(const process::KernelCall &call, volatile U64 *frame) -> bool {
    using Action = process::CallAction;
    const auto action = static_cast<Action>(call.action);
    const bool path = action == Action::open_directory || action == Action::open_beneath ||
                      action == Action::open_file || action == Action::create_output;
    if (endpoint.caller || !endpoint.generation || !endpoint.waiting || endpoint.replied)
        return false;
    const U64 operation = action == Action::open_directory  ? 16
                          : action == Action::open_beneath  ? 17
                          : action == Action::open_file     ? 18
                          : action == Action::read          ? 19
                          : action == Action::close         ? 20
                          : action == Action::create_output ? 21
                          : action == Action::write         ? 22
                          : action == Action::commit        ? 23
                                                            : 24;
    U64 length = 0;
    std::optional<std::byte *> source;
    if (path) {
        if (!user_bytes(call.record, 48, true))
            return false;
        if (call.length <= process::file_path_limit) {
            source = user_bytes(call.base, call.length, false);
            if (!source)
                return false;
            length = call.length;
        }
    } else if (action == Action::read) {
        if (!user_bytes(call.base, process::file_chunk, true))
            return false;
    } else if (action == Action::write) {
        source = user_bytes(call.base, call.length, false);
        if (!source)
            return false;
        length = call.length < Endpoint::capacity - 64 ? call.length : Endpoint::capacity - 64;
    }
    message_header(operation, call.value, action == Action::read ? call.length : 0, length);
    for (U64 at = 0; at < length; ++at)
        endpoint.bytes[64 + at] = (*source)[at];
    endpoint.call = call;
    endpoint.written = length;
    endpoint.caller = 1;
    endpoint.caller_cancelled = false;
    outcome.request = true;
    save_frame(frame);
    return true;
}

// One kernel call: 0 resumes the process with RAX set, 1 ends it.
auto kernel_call(volatile U64 *frame) -> U64 {
    if (frame[frame_rax] >= 17 && frame[frame_rax] <= 20) {
        const auto operation = frame[frame_rax];
        if (mounted_call(frame) || recovery_call(frame)) {
#ifdef AURORA_PROCESS_FIXTURE
            if (mounted_owner_termination) {
                mounted_owner_termination = false;
                outcome.exited = true;
                outcome.status = 1;
                return 1;
            }
#endif
            return 0;
        }
        outcome.invalid_call = true;
        outcome.operation = operation;
        outcome.rip = frame[frame_rip];
        return 1;
    }
    if (frame[frame_rax] == 16) {
        if (block_read(frame))
            return 0;
        outcome.invalid_call = true;
        outcome.operation = 16;
        outcome.rip = frame[frame_rip];
        return 1;
    }
    if (frame[frame_rax] == 15) {
        if (endpoint_exchange(frame))
            return 1;
        outcome.invalid_call = true;
        outcome.operation = 15;
        outcome.rip = frame[frame_rip];
        return 1;
    }
    const auto decoded =
        process::call(frame[frame_rax], frame[frame_rdi], frame[frame_rsi], frame[frame_rdx], frame[frame_r10]);
    if (!decoded)
        fail("Aurora kernel call decision");
    // The largest charge the run reached, as of each call.
    if (running.space->charged() > running.peak)
        running.peak = running.space->charged();
    // Fixture: fault in the kernel during the run's first call (process.md#guest-rows).
    if ((running.flags & 1) && running.calls++ == 0)
        static_cast<void>(*reinterpret_cast<volatile U64 *>(KernelSpace::window_base + frames::page));
    const auto action = static_cast<process::CallAction>(decoded->action);
    if (action == process::CallAction::exit) {
        outcome.exited = true;
        outcome.status = decoded->value;
        return 1;
    }
    if (action == process::CallAction::print && !running.service) {
        if (const auto bytes = user_bytes(decoded->base, decoded->length, false)) {
            if (output_sink && running.external && !running.service) {
                for (U64 at = 0; at < decoded->length; ++at)
                    endpoint.bytes[at] = (*bytes)[at];
                endpoint.count = decoded->length;
                output_error_stream = decoded->value == 2;
                outcome.output = true;
                save_frame(frame);
                return 1;
            }
#ifndef AURORA_PRODUCTION
            print_stream(decoded->value, reinterpret_cast<U64>(*bytes), decoded->length);
            frame[frame_rax] = 0;
            return 0;
#endif
        }
    }
    if (action == process::CallAction::read || action >= process::CallAction::open_directory) {
        if (!running.service) {
            if (running.external) {
                if (file_request(*decoded, frame))
                    return 1;
            }
        }
    }
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
auto dispatch(U64, U64, U64, U64, U64, U64) -> U64 asm("uefi_process_exception_dispatch")
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
        return charge_tick(vector, error, rip, cs, words);
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
#ifdef AURORA_PRODUCTION
    if (!running.recovery_generation && !running.mounted_generation)
        return;
#endif
    Serial::text(running.companion ? std::string_view{"AURORA_FILE_SERVICE_END:"}
                                   : std::string_view{"AURORA_PROCESS_END:"});
    field("run", running.companion ? running.companion : run);
    if (running.companion)
        field("generation", running.service);
    if (outcome.exited) {
        Serial::text(" reason=exit");
        field("status", outcome.status);
    } else if (outcome.watchdog) {
        Serial::text(" reason=watchdog");
        field("ticks", outcome.terminal_ticks);
    } else if (outcome.cancelled) {
        Serial::text(" reason=cancelled");
    } else if (outcome.unavailable) {
        Serial::text(" reason=service_lost");
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

#ifndef AURORA_PRODUCTION
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

#endif

auto refuse(U64 run, std::string_view reason) -> void {
    load_refusal = reason == "quota"     ? RunStatus::quota
                   : reason == "missing" ? RunStatus::missing
                                         : RunStatus::malformed;
    Serial::text("AURORA_PROCESS_REJECTED:");
    field("run", run);
    Serial::text(" reason=");
    Serial::text(reason);
    Serial::text("\r\n");
}

// Map a complete immutable admitted source. A transient loader snapshot, if
// present, is released before this root becomes an auditable resident.
auto load_image(std::span<const std::byte> view,
                std::span<const std::byte> source,
                std::span<const std::byte> arguments,
                const process::RunEntry &entry,
                U64 run,
                std::size_t slot,
                bool preemptible,
                bool external = false,
                U64 service = 0,
                bool grant_block = false,
                U64 companion = 0,
                bool grant_mounted = false) -> bool {
    auto &resident = residents[slot];
    if (resident.space || resident.started)
        fail("resident slot already owned");
    static_cast<void>(view);
    const auto image = std::optional<std::span<const std::byte>>{source};
    const auto admitted = process::elf_admit(*image);
    if (!admitted)
        fail("Aurora ELF admission");
    if (*admitted != process::ElfVerdict::valid) {
        refuse(run, name(elf_names, static_cast<U64>(*admitted)));
        return false;
    }
    const auto layout = process::layout(*image, shared.reserved_first, shared.reserved_end, arguments.size());
    if (!layout)
        fail("Aurora process layout");
    if (*layout != process::LayoutVerdict::valid) {
        refuse(run, name(layout_names, static_cast<U64>(*layout)));
        return false;
    }
    // The load and the memory service are charged against frames free now.
    const auto budget = process::memory_budget(*image, arguments.size(), shared.slots, entry.quota, available_frames());
    if (!budget)
        fail("Aurora memory budget");
    if (budget->verdict != static_cast<U64>(process::BudgetVerdict::valid)) {
        refuse(run, "quota");
        return false;
    }
    auto &process_space = resident.space.emplace(space,
                                                 table,
                                                 ranges,
                                                 space.mappings(ranges.frames()),
                                                 shared,
                                                 space.process_records(slot),
                                                 frames::first_owner + run);
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
    if (snapshot) {
        if (snapshot->owner() != process_space.owner() || !snapshot->release())
            fail("loader snapshot release");
        snapshot.reset();
    }
    if (!process_space.budget(*budget) || !stack_top || !block || !process_space.executable(entry_point, 1) ||
        !process_space.verify())
        fail("process load walk");
#ifndef AURORA_PRODUCTION
    if (entry.flags & 2)
        walk_cases(process_space, entry_point, block, run);
#endif
    Serial::text(companion ? "AURORA_FILE_SERVICE_LOADED:" : "AURORA_PROCESS_LOADED:");
    field("run", companion ? companion : run);
    if (companion)
        field("generation", service);
    field("regions", regions);
    field("pages", process_space.leaves());
    field("tables", process_space.tables());
    field("quota", budget->quota - budget->charged);
    if (preemptible) {
        field("owner", process_space.owner());
        field("root", process_space.root());
    }
    Serial::text("\r\n");
    // Initial entry and retained continuation are both kernel-owned. A slot
    // identity is never user-provided; owners advance with the run ordinal.
    U64 read_generation = 0, read_sectors = 0, write_generation = 0, write_sectors = 0;
#ifdef AURORA_UEFI_NVME
    if (grant_block && service && aurora::uefi::nvme_sector_count()) {
        if (next_block_generation == ~U64{0})
            fail("block generation exhausted");
        read_generation = ++next_block_generation;
        read_sectors = aurora::uefi::nvme_sector_count();
        block_service = service;
        block_generation = read_generation;
        block_sectors = read_sectors;
    }
    if (grant_mounted) {
        if (!service || grant_block || mounted_generation || next_block_generation == ~U64{0} ||
            !aurora::uefi::nvme_mounted_sector_count())
            fail("mounted grant admission");
        write_generation = ++next_block_generation;
        write_sectors = aurora::uefi::nvme_mounted_sector_count();
        mounted_owner = process_space.owner();
        mounted_root = process_space.root();
        mounted_generation = write_generation;
        mounted_sectors = write_sectors;
        mounted_service = service;
        Serial::text("AURORA_MOUNTED_GRANTED:");
        field("owner", mounted_owner);
        field("root", mounted_root);
        field("generation", mounted_generation);
        field("service", mounted_service);
        field("sectors", mounted_sectors);
        Serial::text("\r\n");
    }
#else
    static_cast<void>(grant_block);
    static_cast<void>(grant_mounted);
#endif
    resident.initial = {entry_point,
                        stack_top - 16,
                        block,
                        arguments.size(),
                        process_space.root(),
                        service,
                        write_generation ? write_generation : read_generation,
                        write_generation ? write_sectors : read_sectors};
    if (!resident.budget.create(entry.ticks, (entry.flags & 8) ? 1 : 0))
        fail("resident budget admission");
    resident.state = {};
    resident.state.space = &process_space;
    resident.state.budget = &resident.budget;
    resident.state.run = run;
    resident.state.flags = entry.flags;
    resident.state.continuation = preemptible ? &resident.continuation : nullptr;
    resident.state.service = service;
    resident.state.block_generation = read_generation;
    resident.state.block_sectors = read_sectors;
    resident.state.mounted_generation = write_generation;
    resident.state.mounted_sectors = write_sectors;
    resident.state.external = external;
    resident.state.companion = companion;
    if (!audit_residents())
        fail("resident admission audit");
    return true;
}

#ifndef AURORA_PRODUCTION
// Load a boot-volume program without changing its current fixture interface.
auto load_one(std::span<const std::byte> view,
              std::span<const std::byte> runs,
              const process::RunEntry &entry,
              U64 run,
              std::size_t slot,
              bool preemptible,
              bool external = false,
              U64 service = 0,
              bool grant_block = false) -> bool {
    auto &resident = residents[slot];
    if (resident.space || resident.started)
        fail("resident slot already owned");
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
    if (!image) {
        refuse(run, "missing");
        return false;
    }
    return load_image(view, *image, arguments, entry, run, slot, preemptible, external, service, grant_block);
}

#endif

auto retire_resident(std::size_t slot) -> bool {
    auto &resident = residents[slot];
    running = resident.state;
    running.space = nullptr;
    outcome.terminal_ticks = resident.budget.used();
    outcome.terminal_run = resident.state.run;
    outcome.terminal_service = resident.state.service;
    end_record(resident.state.run);
    auto &process_space = *resident.space;
    const bool writer = resident.state.recovery_generation != 0;
    const bool mounted_writer = resident.state.mounted_generation != 0;
    bool sealed_writer = false;
#ifdef AURORA_UEFI_NVME
    if (mounted_writer) {
        aurora::uefi::nvme_mounted_abandon();
        if (!resident.state.service || resident.state.service != mounted_service ||
            resident.state.mounted_generation != mounted_generation ||
            resident.state.mounted_sectors != mounted_sectors || process_space.owner() != mounted_owner ||
            process_space.root() != mounted_root || root() != kernel_root || !space.closed())
            fail("mounted retirement authority");
    }
    if (writer) {
        if (resident.state.service || resident.state.recovery_generation != recovery_generation ||
            resident.state.recovery_sectors != recovery_sectors || process_space.owner() != recovery_owner ||
            process_space.root() != recovery_root || root() != kernel_root || !space.closed()) {
            aurora::uefi::nvme_recovery_abandon();
            fail("recovery retirement authority");
        }
        const bool success = outcome.exited && !outcome.status && !outcome.watchdog && !outcome.invalid_call &&
                             !outcome.unavailable && !outcome.parked;
        sealed_writer = success && aurora::uefi::nvme_recovery_seal();
        if (!sealed_writer)
            aurora::uefi::nvme_recovery_abandon();
    }
#endif
    const auto cleanup_failure = [&](std::string_view reason) {
#ifdef AURORA_UEFI_NVME
        if (mounted_writer)
            aurora::uefi::nvme_mounted_abandon();
        if (writer)
            aurora::uefi::nvme_recovery_abandon();
#endif
        fail(reason);
    };
    if (!process_space.verify())
        cleanup_failure("process exit walk");
    const auto memory = process_space.memory();
    const auto peak = process_space.charged() > running.peak ? process_space.charged() : running.peak;
    const auto released = process_space.release();
    if (!released)
        cleanup_failure("process release");
    resident.space.reset();
    if (!audit_residents())
        cleanup_failure("resident release audit");
#ifdef AURORA_PRODUCTION
    if (writer || mounted_writer) {
#endif
        Serial::text(running.companion ? std::string_view{"AURORA_FILE_SERVICE_RELEASED:"}
                                       : std::string_view{"AURORA_PROCESS_RELEASED:"});
        field("run", running.companion ? running.companion : resident.state.run);
        if (running.companion)
            field("generation", running.service);
        field("frames", *released);
        field("memory", memory);
        field("calls", running.memory_calls);
        field("commits", running.commits);
        field("peak", peak);
        Serial::text("\r\n");
#ifdef AURORA_PRODUCTION
    }
#endif
    // Volatile scrubbing prevents continuation authority or arguments from
    // surviving slot reuse, even when ordinary dead stores are optimized out.
    for (auto &word : resident.continuation)
        *static_cast<volatile U64 *>(&word) = 0;
    for (auto &word : resident.initial)
        *static_cast<volatile U64 *>(&word) = 0;
    if (resident.state.service && resident.state.service == block_service)
        block_service = block_generation = block_sectors = 0;
    // The role remains visible throughout real address-space release and
    // continuation scrubbing. It is not cleared to bypass failure cleanup.
    const auto retired_generation = resident.state.recovery_generation;
    if (writer)
        recovery_owner = recovery_root = recovery_generation = recovery_sectors = 0;
    if (mounted_writer) {
#ifdef AURORA_UEFI_NVME
        Serial::text("AURORA_MOUNTED_RETIRED:");
        field("generation", mounted_generation);
        field("writes", aurora::uefi::nvme_mounted_admitted_writes());
        field("flushes", aurora::uefi::nvme_mounted_admitted_flushes());
        Serial::text(" disk=unavailable\r\n");
#endif
        mounted_owner = mounted_root = mounted_generation = mounted_sectors = mounted_service = 0;
    }
    resident.budget.stop();
    running.budget = nullptr;
    resident.state = {};
    resident.started = false;
#ifdef AURORA_UEFI_NVME
    if (writer) {
        recovery_completed = sealed_writer && aurora::uefi::nvme_recovery_retired();
        if (!recovery_completed)
            aurora::uefi::nvme_recovery_abandon();
        Serial::text("AURORA_RECOVERY_RETIRED:");
        field("generation", retired_generation);
        field("sealed", sealed_writer);
        field("readonly", recovery_completed);
        // On sealed success every admitted operation completed: submission,
        // completion, guard or Flush failure is absorbing before promotion.
        field("admitted_writes", aurora::uefi::nvme_recovery_admitted_writes());
        field("admitted_flushes", aurora::uefi::nvme_recovery_admitted_flushes());
        Serial::text("\r\n");
    }
#else
    static_cast<void>(sealed_writer);
    static_cast<void>(retired_generation);
#endif
    return true;
}

// Copies run only while the supervisor owns execution. The selected root is
// already fully admitted and is restored before any other process can enter.
auto deliver_before_enter(std::size_t slot) -> void {
    if (!(running.service && endpoint.delivery) && !(slot == 1 && endpoint.completion))
        return;
    asm volatile("mov %0, %%cr3" : : "r"(running.space->root()) : "memory");
    if (running.service && endpoint.delivery) {
        const auto target = user_bytes(endpoint.window, Endpoint::window_bytes, true);
        if (!target)
            fail("endpoint window changed while parked");
        for (U64 at = 0; at < 64; ++at)
            (*target)[at] = std::byte{0};
        store(endpoint.window, endpoint.count, 8);
        store(endpoint.window + 8, endpoint.source, 8);
        store(endpoint.window + 16, endpoint.transaction, 8);
        store(endpoint.window + 24, 1, 8);
        for (U64 at = 0; at < endpoint.count; ++at)
            (*target)[Endpoint::request_offset + at] = endpoint.bytes[at];
        residents[slot].continuation[frame_rax] = 0;
        residents[slot].continuation[frame_rdx] = endpoint.count;
        endpoint.delivery = false;
        endpoint.waiting = false;
    } else {
        const Bytes reply{endpoint.bytes};
        const auto status = reply.get(0), count = reply.get(8);
        const auto action = static_cast<process::CallAction>(endpoint.call.action);
        if (action == process::CallAction::read && !status) {
            const auto target = user_bytes(endpoint.call.base, process::file_chunk, true);
            if (!target)
                fail("parked read destination");
            for (U64 at = 0; at < count; ++at)
                (*target)[at] = endpoint.bytes[64 + at];
        }
        if (endpoint.call.record) {
            if (!user_bytes(endpoint.call.record, 48, true))
                fail("parked file result");
            for (U64 word = 0; word < 6; ++word)
                store(endpoint.call.record + word * 8, reply.get(16 + word * 8), 8);
        }
        residents[slot].continuation[frame_rax] = status ? 0 - status : count;
        endpoint.completion = false;
    }
    asm volatile("mov %0, %%cr3" : : "r"(kernel_root) : "memory");
}

// One entry or resumption. A timer park returns to this kernel loop before
// another process can enter, preserving the single saved kernel continuation.
auto run_resident(std::size_t slot) -> bool {
    auto &resident = residents[slot];
    if (!resident.space || !resident.budget.available() || running.space || root() != kernel_root)
        fail("resident activation");
    running = resident.state;
    outcome = Outcome{};
    arm_slice();
    deliver_before_enter(slot);
    if (resident.started && !resident.state.external) {
        Serial::text("AURORA_PROCESS_RESUMED:");
        field("run", resident.state.run);
        field("ticks", resident.budget.used());
        Serial::text("\r\n");
    }
    const auto result = resident.started ? process_resume(resident.continuation.data(), resident.space->root())
                                         : process_enter(resident.initial.data());
    if (result != 1 || root() != kernel_root)
        fail("process exit");
    const U64 current = running.slice ? Timer::read(0x390) : 0;
    if (!Timer::stop())
        fail("process timer stop");
    if (running.slice) {
        if (current > running.slice)
            fail("watchdog current count");
        // An expiration latched between the sample and stop belongs to this
        // outgoing slice. Its later drain acknowledges only, never charges twice.
        const U64 consumed = Timer::pending() ? running.slice : running.slice - current;
        elapsed(consumed, true);
        running.slice = 0;
    }
    resident.started = true;
    resident.state = running;
    running.space = nullptr;
    if (Timer::pending()) {
        draining = true;
        process_drain();
    }
    if (draining || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        fail("timer drain");
    if (outcome.parked) {
        if (!resident.state.external) {
            Serial::text("AURORA_PROCESS_PARKED:");
            field("run", resident.state.run);
            field("ticks", resident.budget.used());
            Serial::text("\r\n");
        }
        return false;
    }
    return retire_resident(slot);
}

// One bounded request/reply round trip. The service budget is per operation,
// not renewed by its own timer parks. Bootstrap and teardown use the same cap.
auto begin_exchange(U64 source) -> bool {
    if (!residents[0].space || !endpoint.waiting || endpoint.delivery || endpoint.count > Endpoint::capacity ||
        endpoint.next == ~U64{0})
        return false;
    endpoint.source = source;
    endpoint.transaction = ++endpoint.next;
    endpoint.replied = false;
    endpoint.delivery = true;
    auto &server = residents[0].state;
    if (!server.budget->restart())
        fail("service budget restart");
    return true;
}
enum class ExchangeProgress {
    pending,
    replied,
    failed
};
// A single authenticated server entry. Timer parks retain the same transaction
// and remaining allowance; only begin_exchange renews a new message's cap.
auto advance_exchange() -> ExchangeProgress {
    if (!residents[0].space || !endpoint.transaction || endpoint.replied || (endpoint.waiting && !endpoint.delivery))
        return ExchangeProgress::failed;
    static_cast<void>(run_resident(0));
    if (!residents[0].space)
        return ExchangeProgress::failed;
    if (!endpoint.replied)
        return ExchangeProgress::pending;
    return endpoint.waiting ? ExchangeProgress::replied : ExchangeProgress::failed;
}
// Loader/control consumers still synchronously pump these same primitives.
// Production caller requests instead return each pending observation to Aurora.
auto exchange_request(U64 source) -> bool {
    if (!begin_exchange(source))
        return false;
    ExchangeProgress progress;
    do {
        progress = advance_exchange();
    } while (progress == ExchangeProgress::pending);
    return progress == ExchangeProgress::replied;
}
auto control_request(U64 operation, U64 id = 0, U64 offset = 0, std::span<const std::byte> payload = {}) -> bool {
    if (endpoint.caller || (loading_image && endpoint.caller_cancelled) || payload.size() > Endpoint::capacity - 64)
        return false;
    message_header(operation, id, offset, payload.size());
    for (U64 at = 0; at < payload.size(); ++at)
        endpoint.bytes[64 + at] = payload[at];
    if (!exchange_request(0) || (loading_image && endpoint.caller_cancelled))
        return false;
    bool valid = endpoint.count == 64;
    for (U64 at = 0; valid && at < 64; ++at)
        valid = endpoint.bytes[at] == std::byte{0};
    if (!valid) {
        if (!endpoint.invalid_reply_operation)
            endpoint.invalid_reply_operation = operation;
        return false;
    }
    endpoint.replied = false;
    return true;
}
// The external service is not trusted to write a caller's memory. Admit its
// copied result shape before selecting the kernel-owned original destination.
auto file_reply_valid() -> bool {
    if (endpoint.count < 64 || endpoint.count > 64 + process::file_chunk)
        return false;
    const Bytes reply{endpoint.bytes};
    const U64 status = reply.get(0), count = reply.get(8);
    if (status > 9 || count > process::file_chunk || endpoint.count != 64 + count)
        return false;
    const auto action = static_cast<process::CallAction>(endpoint.call.action);
    if (status || action == process::CallAction::close || action == process::CallAction::write ||
        action == process::CallAction::commit || action == process::CallAction::discard) {
        for (U64 at = 8; at < 64; ++at)
            if (endpoint.bytes[at] != std::byte{0})
                return false;
        return endpoint.count == 64;
    }
    if (action == process::CallAction::read) {
        for (U64 at = 16; at < 64; ++at)
            if (endpoint.bytes[at] != std::byte{0})
                return false;
        return true;
    }
    const U64 id = reply.get(16), size = reply.get(24), device = reply.get(32), inode = reply.get(40),
              directory_device = reply.get(48), directory_inode = reply.get(56), slot = id & 63;
    if (count || id < 65 || size > 0x7fffffffffffffffULL || device > 3)
        return false;
    if (action == process::CallAction::create_output) {
        const bool disk_output = mounted_generation && mounted_service == endpoint.generation &&
                                 residents[0].state.mounted_generation == mounted_generation && device == 3 &&
                                 slot >= 41 && slot <= 56 && !size && inode && directory_device == 3 && directory_inode;
        return disk_output || (device <= 2 && slot >= 33 && slot <= 36 && !size && ((device == 0) == (inode == 0)) &&
                               directory_device == 1 && directory_inode >= 65536);
    }
    return ((device == 3 && slot >= 41 && slot <= 56) || (device >= 1 && device <= 2 && slot >= 1 && slot <= 32)) &&
           inode && !directory_device && !directory_inode;
}
// Preserve the first checked malformed response through best-effort close.
// This records a kernel-selected operation, never a reply-supplied identity.
auto admit_file_reply() -> bool {
    if (file_reply_valid())
        return true;
    if (!endpoint.invalid_reply_operation)
        endpoint.invalid_reply_operation = endpoint.request_operation;
    return false;
}
// The client stays parked across every pending result, retaining the original
// copied call and its validated source pages. No source-supplied token chooses
// the transaction or its destination.
enum class ClientProgress {
    pending,
    complete,
    failed
};
// Only an authenticated, still-undispatched request can be withdrawn. This
// changes no server continuation, transaction ordinal or budget.
auto settle_staged_cancellation(U64 client, U64 service) -> bool {
    if (!client || !service || !residents[1].space || residents[1].state.run != client || !residents[0].space ||
        residents[0].state.service != service || endpoint.generation != service ||
        endpoint.caller != std::optional<std::size_t>{1} || !endpoint.caller_cancelled || !endpoint.waiting ||
        endpoint.replied || endpoint.delivery)
        return false;
    endpoint.caller.reset();
    endpoint.replied = endpoint.completion = false;
    return true;
}
auto advance_client_request(bool cancel_staged = false) -> ClientProgress {
    if (!residents[1].space || endpoint.caller != std::optional<std::size_t>{1})
        return ClientProgress::failed;
    const U64 client = residents[1].state.run;
    if (cancel_staged && endpoint.caller_cancelled && endpoint.waiting && !endpoint.replied && !endpoint.delivery) {
        return settle_staged_cancellation(client, endpoint.generation) ? ClientProgress::complete
                                                                       : ClientProgress::failed;
    }
    if (endpoint.waiting && !endpoint.replied) {
        if (!begin_exchange(client))
            return ClientProgress::failed;
    } else if (endpoint.source != client) {
        return ClientProgress::failed;
    }
    const auto progress = advance_exchange();
    if (progress == ExchangeProgress::failed)
        return ClientProgress::failed;
    if (progress == ExchangeProgress::pending)
        return ClientProgress::pending;
    if (!admit_file_reply())
        return ClientProgress::failed;
    const Bytes reply{endpoint.bytes};
    if (!endpoint.caller_cancelled && !reply.get(0) &&
        endpoint.call.action == static_cast<U64>(process::CallAction::write) &&
        endpoint.written != endpoint.call.length) {
        // A raw 64 KiB write needs two bounded messages. Stage the final bytes
        // only after the first authenticated successful reply. The next source
        // turn begins that distinct transaction; this turn never runs twice.
        const U64 remaining = endpoint.call.length - endpoint.written;
        if (remaining > 64 || root() != kernel_root)
            fail("file write continuation");
        auto &client_space = *residents[1].space;
        const auto address = endpoint.call.base + endpoint.written;
        asm volatile("mov %0, %%cr3" : : "r"(client_space.root()) : "memory");
        if (client_space.access(address, remaining, false) != ProcessSpace::Access::granted)
            fail("parked write source");
        message_header(22, endpoint.call.value, 0, remaining);
        const auto *source = reinterpret_cast<const volatile std::byte *>(address);
        for (U64 at = 0; at < remaining; ++at)
            endpoint.bytes[64 + at] = source[at];
        asm volatile("mov %0, %%cr3" : : "r"(kernel_root) : "memory");
        endpoint.written += remaining;
        endpoint.replied = false;
        return ClientProgress::pending;
    }
    // Caller expiry does not abort an already delivered operation: the server
    // reached a reply or terminal state under its own bounded allowance first.
    endpoint.replied = false;
    endpoint.caller.reset();
    endpoint.completion = !endpoint.caller_cancelled;
    return ClientProgress::complete;
}
#ifndef AURORA_PRODUCTION
// Existing fixture dispatcher; production's request phase is owned by Aurora.
auto client_request() -> bool {
    ClientProgress progress;
    do {
        progress = advance_client_request();
    } while (progress == ClientProgress::pending);
    return progress == ClientProgress::complete;
}
#endif

enum class ServiceFailure {
    observe,
    invalid_reply,
    consumer_rejected,
    exited,
    watchdog,
    invalid_call,
    fault,
    caller_expired,
    unavailable
};
class ServiceLoss final {
public:
    ServiceFailure kind;
    U64 detail;
};
auto observe_service_loss(ServiceFailure kind) -> ServiceLoss {
    if (kind != ServiceFailure::observe)
        return {kind, 0};
    if (endpoint.invalid_reply_operation)
        return {ServiceFailure::invalid_reply, endpoint.invalid_reply_operation};
    if (residents[0].space)
        return {endpoint.caller_cancelled ? ServiceFailure::caller_expired : ServiceFailure::unavailable, 0};
    // A naturally retired server leaves its authenticated running identity and
    // terminal outcome here. A failed load has no such execution evidence.
    if (!endpoint.generation || running.service != endpoint.generation ||
        outcome.terminal_service != endpoint.generation || outcome.terminal_run != running.run)
        return {ServiceFailure::unavailable, 0};
    if (outcome.exited)
        return {ServiceFailure::exited, outcome.status};
    if (outcome.watchdog)
        return {ServiceFailure::watchdog, outcome.terminal_ticks};
    if (outcome.invalid_call)
        return {ServiceFailure::invalid_call, outcome.operation};
    if (!outcome.parked && !outcome.unavailable)
        return {ServiceFailure::fault, outcome.vector};
    return {ServiceFailure::unavailable, 0};
}
auto service_lost(ServiceLoss loss, U64 generation) -> void {
    Serial::text("AURORA_FILE_SERVICE_LOST:");
    field("generation", generation);
    field("transaction", endpoint.transaction);
    switch (loss.kind) {
    case ServiceFailure::invalid_reply:
        Serial::text(" cause=invalid_reply");
        field("operation", loss.detail);
        break;
    case ServiceFailure::consumer_rejected:
        Serial::text(" cause=consumer_rejected");
        break;
    case ServiceFailure::exited:
        Serial::text(" cause=exit");
        field("status", loss.detail);
        break;
    case ServiceFailure::watchdog:
        Serial::text(" cause=watchdog");
        field("ticks", loss.detail);
        break;
    case ServiceFailure::invalid_call:
        Serial::text(" cause=call");
        field("operation", loss.detail);
        break;
    case ServiceFailure::fault:
        Serial::text(" cause=fault");
        field("vector", loss.detail);
        break;
    case ServiceFailure::caller_expired:
        Serial::text(" cause=caller_expired");
        break;
    default:
        Serial::text(" cause=unavailable");
        break;
    }
    Serial::text(" volatile_data=lost\r\n");
    endpoint.generation = 0;
    endpoint.invalid_reply_operation = 0;
    block_service = block_generation = block_sectors = 0;
    endpoint.waiting = endpoint.replied = endpoint.delivery = endpoint.completion = false;
    endpoint.caller.reset();
    for (auto &byte : endpoint.bytes)
        *static_cast<volatile std::byte *>(&byte) = std::byte{0};
}

// A cleanup observation is admitted only at the actual resource boundary. The
// copied generation is not sufficient to manufacture this acknowledgement.
auto acknowledge_service_cleanup(U64 generation) -> void {
    if (residents[0].space || residents[1].space || snapshot || running.space || endpoint.generation ||
        endpoint.caller || endpoint.waiting || endpoint.replied || endpoint.delivery || endpoint.completion ||
        !audit_residents() || !service_root.cleaned(generation))
        fail("file service cleanup acknowledgement");
}

auto discard_snapshot() -> void {
    if (snapshot) {
        if (!snapshot->release())
            fail("loader snapshot rollback");
        snapshot.reset();
    }
}
auto abandon_service(ServiceFailure failure = ServiceFailure::observe) -> void {
    // Capture the actual server result before forced client/server retirement
    // replaces the shared outcome. The cause is diagnostic, never authority.
    const auto loss = observe_service_loss(failure);
    const auto phase = service_root.phase();
    const U64 generation = phase == aurora::service::Phase::absent ? 0 : service_root.generation();
    if (generation) {
        if ((endpoint.generation && endpoint.generation != generation) ||
            !service_root.lose(generation, static_cast<aurora::service::Reason>(loss.kind), loss.detail))
            fail("file service loss observation");
    } else if (endpoint.generation || residents[0].space || residents[1].space || snapshot) {
        fail("absent file service physical owner");
    }
    // No process may see a late reply or a writable staging alias after loss.
    loading_image = false;
    endpoint.caller.reset();
    endpoint.completion = false;
    discard_snapshot();
    for (std::size_t slot : {std::size_t{1}, std::size_t{0}}) {
        if (!residents[slot].space)
            continue;
        outcome = {};
        outcome.unavailable = true;
        static_cast<void>(retire_resident(slot));
    }
    const auto frozen =
        generation ? ServiceLoss{static_cast<ServiceFailure>(service_root.reason()), service_root.detail()} : loss;
    service_lost(frozen, generation);
    if (generation)
        acknowledge_service_cleanup(generation);
}

#ifdef AURORA_UEFI_NVME
// Shared one-way writer execution; only admitted boot compositions may call it.
auto finish_recovery(U64 baseline) -> bool {
    auto &resident = residents[0];
    if (!resident.space || resident.started || resident.state.service || resident.state.block_generation ||
        next_block_generation == ~U64{0})
        fail("recovery mint state");
    recovery_owner = resident.space->owner();
    recovery_root = resident.space->root();
    recovery_generation = ++next_block_generation;
    recovery_sectors = aurora::uefi::nvme_recovery_sector_count();
    resident.state.recovery_generation = recovery_generation;
    resident.state.recovery_sectors = recovery_sectors;
    resident.initial[6] = recovery_generation;
    resident.initial[7] = recovery_sectors;
    Serial::text("AURORA_RECOVERY_GRANTED:");
    field("owner", recovery_owner);
    field("root", recovery_root);
    field("generation", recovery_generation);
    field("sectors", recovery_sectors);
    Serial::text("\r\n");
    while (resident.space)
        static_cast<void>(run_resident(0));
    if (table.free() != baseline || recovery_owner || recovery_root || recovery_generation || recovery_sectors ||
        !audit_residents()) {
        aurora::uefi::nvme_recovery_abandon();
        fail("recovery cleanup");
    }
    Serial::text("AURORA_RECOVERY_CLEANUP:");
    field("free", table.free());
    Serial::text("\r\n");
    return recovery_completed && aurora::uefi::nvme_sector_count();
}
#endif

auto file_start_refused(bool mounted_attempt) -> bool {
#ifdef AURORA_UEFI_NVME
    if (mounted_attempt)
        aurora::uefi::nvme_mounted_abandon();
#else
    static_cast<void>(mounted_attempt);
#endif
    return false;
}
auto start_file_service(std::span<const std::byte> volume, U64 generation) -> bool {
    constexpr std::string_view arguments{"file-service\0", 13};
    if (residents[0].space || residents[1].space || snapshot || !generation ||
        service_root.phase() != aurora::service::Phase::starting || service_root.generation() != generation ||
        next_run >= 0xffffffffULL - frames::first_owner)
        return false;
    // The attempt is consumed before image lookup or admission. A failed or
    // retired owner can restart RAM service, never reacquire this writer.
    const bool mounted_attempt = runtime_storage.claim_mounted();
    bool mounted_entry = false;
    bool disk_ready = false;
#ifdef AURORA_UEFI_NVME
    mounted_entry = mounted_attempt && aurora::uefi::nvme_mounted_sector_count();
#else
    static_cast<void>(mounted_attempt);
#endif
    const auto path =
        mounted_entry ? std::string_view{"bin/file-service-mounted", 24} : std::string_view{"bin/file-service", 16};
    reset_loader(128);
    loading_image = true;
    endpoint.generation = generation;
    endpoint.window = endpoint.transaction = endpoint.source = endpoint.count = 0;
    endpoint.request_operation = endpoint.invalid_reply_operation = 0;
    endpoint.waiting = endpoint.replied = endpoint.delivery = endpoint.completion = endpoint.caller_cancelled = false;
    const auto image = process::volume_lookup(volume, bytes_of(path));
    process::RunEntry entry{};
    entry.ticks = 64;
    entry.quota = 32768;
    if (!image || !load_image(volume,
                              *image,
                              bytes_of(arguments),
                              entry,
                              ++next_run,
                              0,
                              true,
                              true,
                              endpoint.generation,
                              runtime_storage.block() && !runtime_storage.mounted(),
                              0,
                              mounted_entry)) {
        return file_start_refused(mounted_attempt);
    }
    while (residents[0].space && !endpoint.waiting)
        static_cast<void>(run_resident(0));
    if (!residents[0].space || !control_request(1, volume.size(), runtime_storage.readonly_profile()))
        return file_start_refused(mounted_attempt);
    for (U64 offset = 0; offset < volume.size();) {
        const U64 count = least(Endpoint::capacity - 64, volume.size() - offset);
        if (!control_request(2, 0, offset, volume.subspan(offset, count)))
            return file_start_refused(mounted_attempt);
        offset += count;
    }
    if (!control_request(3))
        return file_start_refused(mounted_attempt);
    if (runtime_storage.block()) {
        // One bounded startup admission scans the complete supported log. It
        // is not charged to a future client or renewed by sector reads. Normal
        // runtime budgets are restored exactly once after the copied result.
        reset_loader(16, 1);
        auto &server = residents[0].state;
        if (!server.budget->configure_next(16, 1))
            fail("mounted startup budget profile");
        message_header(15, 0, 0, 0);
        const bool received = exchange_request(0) && !endpoint.caller_cancelled;
        bool valid = received && endpoint.count == 64;
        const U64 status = valid ? Bytes{endpoint.bytes}.get(0) : 3;
        valid = valid && (status == 0 || status == 2);
        for (U64 at = 8; valid && at < 64; ++at)
            valid = endpoint.bytes[at] == std::byte{0};
        if (!valid) {
            if (received && !endpoint.invalid_reply_operation)
                endpoint.invalid_reply_operation = 15;
            return file_start_refused(mounted_attempt);
        }
        endpoint.replied = false;
        disk_ready = status == 0;
#ifdef AURORA_UEFI_NVME
        if (mounted_entry) {
            if (server.mounted_generation != mounted_generation || server.service != mounted_service ||
                endpoint.generation != mounted_service || endpoint.source ||
                residents[0].space->owner() != mounted_owner || residents[0].space->root() != mounted_root)
                fail("mounted startup authority");
            if (!disk_ready || !aurora::uefi::nvme_mounted_arm()) {
                aurora::uefi::nvme_mounted_abandon();
                disk_ready = false;
            } else {
                Serial::text("AURORA_MOUNTED_ARMED:");
                field("generation", mounted_generation);
                Serial::text("\r\n");
            }
        }
#endif
        if (!server.budget->reset(64, 0))
            fail("mounted runtime budget profile");
    }
    loading_image = false;
    if (!service_root.mark_ready(generation, disk_ready))
        fail("file service readiness");
    Serial::text("AURORA_FILE_SERVICE_READY:");
    field("generation", endpoint.generation);
    if (runtime_storage.block())
        Serial::text(disk_ready ? std::string_view{" disk=ready", 11} : std::string_view{" disk=unavailable", 17});
    Serial::text("\r\n");
    return true;
}

// Source alone selects reuse/start/refusal. Native checks only the physical
// binding and executes the selected one-shot startup, without a retry loop.
auto ensure_file_service(std::span<const std::byte> volume, U64 expected = 0, bool permit_start = true) -> bool {
    const auto action = service_root.admit(expected, permit_start);
    if (action == aurora::service::Action::refused)
        return false;
    const U64 generation = service_root.generation();
    if (action == aurora::service::Action::reuse) {
        if (!residents[0].space || endpoint.generation != generation || residents[0].state.service != generation)
            fail("file service retained binding");
        return true;
    }
    if (action != aurora::service::Action::start)
        fail("file service admission action");
    return start_file_service(volume, generation);
}

[[gnu::noinline]] auto deliver_output() -> bool {
    if (!output_sink || !Timer::irq_off() || root() != kernel_root || Timer::read(0x390) ||
        !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false) || endpoint.count > Endpoint::capacity)
        fail("process output ownership");
    const bool delivered = output_sink(output_context, output_error_stream, {endpoint.bytes.data(), endpoint.count});
    if (delivered)
        residents[1].continuation[frame_rax] = 0;
    return delivered;
}
// Actual resources/effect evidence belong to the private authenticated lease
// binding. Aurora owns command sequencing; there is no native command loop.
class ExecutionEffects {
protected:
    static auto require(bool valid) -> void {
        if (!valid)
            fail("execution effect state");
    }
    static auto status(RunStatus value) -> aurora::execution::Status {
        return static_cast<aurora::execution::Status>(value);
    }

public:
    class Binding final {
    public:
        U64 client = 0, service_generation = 0;
        bool output_pending = false, request_pending = false;
        bool output_failed = false, request_failed = false;
        bool explicit_cancel_requested = false, expiry_preceded_cancel = false;
    };
    static auto bound_client(const Binding &binding) -> bool {
        return binding.client && residents[1].space && residents[1].state.run == binding.client;
    }
    static auto bound_service(const Binding &binding) -> bool {
        return binding.service_generation && residents[0].space && endpoint.generation == binding.service_generation &&
               residents[0].state.service == binding.service_generation;
    }
    static auto advance(Binding &binding) -> aurora::execution::Observation {
        using namespace aurora::execution;
        require(bound_client(binding) && !binding.output_pending && !binding.request_pending &&
                !binding.output_failed && !binding.request_failed && !binding.explicit_cancel_requested &&
                !endpoint.caller_cancelled);
        if (run_resident(1)) {
            // Freeze terminal facts before any later cleanup can replace outcome.
            const auto ended = outcome.exited ? Status::exited : outcome.watchdog ? Status::watchdog : Status::fault;
            return {Step::retired, ended, outcome.exited ? outcome.status : outcome.vector};
        }
        require(!(outcome.output && outcome.request));
        binding.output_pending = outcome.output;
        binding.request_pending = outcome.request;
        return {binding.output_pending    ? Step::output
                : binding.request_pending ? Step::request
                                          : Step::parked,
                Status::unavailable,
                0};
    }
    static auto output(Binding &binding) -> aurora::execution::Effect {
        using namespace aurora::execution;
        require(bound_client(binding) && binding.output_pending && !binding.request_pending &&
                !binding.explicit_cancel_requested);
        binding.output_failed = !deliver_output();
        binding.output_pending = false;
        return binding.output_failed ? Effect::failed : Effect::success;
    }
    static auto request(Binding &binding) -> aurora::execution::Request {
        using namespace aurora::execution;
        require(bound_client(binding) && binding.request_pending && !binding.output_pending);
        const auto progress =
            bound_service(binding) ? advance_client_request(binding.explicit_cancel_requested) : ClientProgress::failed;
        if (progress == ClientProgress::pending)
            return Request::pending;
        binding.request_failed = progress == ClientProgress::failed;
        binding.request_pending = false;
        if (binding.request_failed)
            return Request::service_lost;
        if (binding.explicit_cancel_requested && !binding.expiry_preceded_cancel)
            return Request::cancel_requested;
        return endpoint.caller_cancelled ? Request::cancelled : Request::ready;
    }
    static auto cancel(Binding &binding) -> aurora::execution::Cancel {
        using namespace aurora::execution;
        // Inert refusals and already retired clients retain their frozen result.
        if (!binding.client || !residents[1].space) {
            require(!binding.output_pending && !binding.request_pending);
            return Cancel::settled;
        }
        require(bound_client(binding));
        if (binding.request_failed || !bound_service(binding)) {
            binding.request_failed = true;
            binding.output_pending = binding.request_pending = false;
            return Cancel::service_lost;
        }
        if (!binding.explicit_cancel_requested) {
            binding.expiry_preceded_cancel = endpoint.caller_cancelled;
            binding.explicit_cancel_requested = true;
        }
        endpoint.caller_cancelled = true;
        // Withdrawing undelivered output does not manufacture delivery failure.
        binding.output_pending = false;
        if (!binding.request_pending) {
            require(!endpoint.caller);
            endpoint.completion = false;
            return Cancel::settled;
        }
        require(endpoint.caller == std::optional<std::size_t>{1});
        // Preserve an earlier expiry through the request observation. The
        // settled cancel result alone cannot communicate its watchdog cause.
        if (binding.expiry_preceded_cancel)
            return Cancel::draining;
        if (endpoint.waiting && !endpoint.replied && !endpoint.delivery) {
            // An initial message or raw-write tail has not been dispatched.
            // Preserve server waiting/transaction/next and its existing budget.
            require(settle_staged_cancellation(binding.client, binding.service_generation));
            binding.request_pending = false;
            return Cancel::settled;
        }
        return Cancel::draining;
    }
    static auto finish(Binding &binding, aurora::execution::Finish disposition) -> aurora::execution::Effect {
        using namespace aurora::execution;
        require(!binding.output_pending && !binding.request_pending);
        if (!binding.client) {
            require(disposition == Finish::complete && !residents[1].space && !snapshot && !endpoint.caller);
            return Effect::success;
        }
        // Source disposition is a request, never evidence for retirement.
        if (disposition == Finish::service_lost) {
            require(binding.request_failed);
            abandon_service();
            binding.client = 0;
            return Effect::success;
        }
        require(!binding.request_failed && bound_service(binding));
        if (disposition == Finish::output_failed) {
            require(binding.output_failed && bound_client(binding));
            outcome = {};
            outcome.invalid_call = true;
            outcome.operation = 2;
            static_cast<void>(retire_resident(1));
        } else if (disposition == Finish::cancelled) {
            require(!binding.output_failed && endpoint.caller_cancelled && bound_client(binding) &&
                    (!binding.explicit_cancel_requested || binding.expiry_preceded_cancel));
            outcome = {};
            outcome.watchdog = true;
            static_cast<void>(retire_resident(1));
        } else if (disposition == Finish::cancel_requested) {
            require(!binding.output_failed && binding.explicit_cancel_requested && !binding.expiry_preceded_cancel &&
                    endpoint.caller_cancelled && bound_client(binding));
            outcome = {};
            outcome.cancelled = true;
            static_cast<void>(retire_resident(1));
        } else {
            require(disposition == Finish::complete && !binding.output_failed && !residents[1].space);
        }
        endpoint.caller.reset();
        endpoint.completion = endpoint.replied = false;
        const U64 client = binding.client;
        binding.client = 0;
        if (!control_request(5, client)) {
            abandon_service();
            return Effect::failed;
        }
        return Effect::success;
    }
    static auto settled(const Binding &binding) -> bool {
        return !binding.client && !binding.output_pending && !binding.request_pending && !residents[1].space &&
               !snapshot && !endpoint.caller && !endpoint.delivery && !endpoint.completion;
    }
};
class ExecutionPlatform final {
public:
    static auto quiet() -> bool {
        return Timer::irq_off() && root() == kernel_root && !running.space && !Timer::read(0x390) &&
               Timer::quiet(0x100, false) && Timer::quiet(0x200, false);
    }
    [[noreturn]] static auto fail() -> void {
        ::fail("execution grant");
    }
};

#ifndef AURORA_PRODUCTION
// Every legacy golden describes an independent namespace. Its companion is
// the same source service as production, with a fresh incarnation per case;
// only client ordinals stay stable. The admitted list has at most64 entries,
// so companion owners64+ordinal cannot alias any client owner in this boot.
auto start_companion(std::span<const std::byte> volume, U64 client) -> bool {
    if (client == 0 || client > 64 || residents[0].space || residents[1].space)
        return false;
    if (service_root.admit(0, true) != aurora::service::Action::start)
        return false;
    endpoint = {};
    endpoint.generation = service_root.generation();
    reset_loader(128);
    loading_image = true;
    constexpr std::string_view path = "bin/file-service", arguments{"file-service\0", 13};
    const auto image = process::volume_lookup(volume, bytes_of(path));
    process::RunEntry entry{};
    entry.ticks = 64;
    entry.quota = 32768;
    if (!image ||
        !load_image(
            volume, *image, bytes_of(arguments), entry, 64 + client, 0, true, true, endpoint.generation, false, client))
        return false;
    while (residents[0].space && !endpoint.waiting)
        static_cast<void>(run_resident(0));
    if (!residents[0].space || !control_request(1, volume.size()))
        return false;
    for (U64 offset = 0; offset < volume.size();) {
        const auto count = least(Endpoint::capacity - 64, volume.size() - offset);
        if (!control_request(2, 0, offset, volume.subspan(offset, count)))
            return false;
        offset += count;
    }
    if (!control_request(3))
        return false;
    loading_image = false;
    if (!service_root.mark_ready(endpoint.generation, false))
        fail("companion readiness");
    return true;
}

// The bounded supervisor export grant selects one immutable committed record
// only after authenticated client cleanup. The service owns all metadata;
// kernel validation admits a copied wire shape, never an overlay namespace.
constinit std::array<std::byte, process::file_path_limit + 1> export_name{};
auto export_request(U64 operation, U64 record, U64 offset) -> std::optional<U64> {
    if (endpoint.caller || endpoint.caller_cancelled)
        return std::nullopt;
    message_header(operation, record, offset, 0);
    if (!exchange_request(0) || endpoint.caller_cancelled || endpoint.count < 64 || endpoint.count > 568)
        return std::nullopt;
    const Bytes reply{endpoint.bytes};
    const auto status = reply.get(0), count = reply.get(8);
    if (count > 504 || endpoint.count != 64 + count || (status && (status != 2 || operation != 7 || count)))
        return std::nullopt;
    for (U64 at = 16; at < 64; ++at)
        if (endpoint.bytes[at] != std::byte{0})
            return std::nullopt;
    endpoint.replied = false;
    return status ? ~U64{0} : count;
}
auto export_clock_begin() -> bool {
    if (!loader_budget.available())
        return false;
    export_armed = loader_budget.quantum();
    return export_armed && Timer::arm(static_cast<std::uint32_t>(export_armed));
}
auto export_clock_end() -> bool {
    const auto remaining = Timer::read(0x390);
    if (!Timer::stop() || remaining > export_armed)
        fail("export timer stop");
    const auto charged = Timer::pending() ? export_armed : export_armed - remaining;
    const auto verdict = loader_budget.progress(charged);
    export_armed = 0;
    if (verdict == aurora::budget::Charge::rejected)
        fail("export budget charge");
    const bool available = verdict == aurora::budget::Charge::available;
    if (Timer::pending()) {
        draining = true;
        process_drain();
    }
    if (draining || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        fail("export timer drain");
    return available;
}
auto export_path(U64 length) -> bool {
    for (U64 at = 0; at < length; ++at) {
        const auto text = process::path_text(std::to_integer<std::uint8_t>(export_name[at]));
        if (!text)
            return false;
        for (unsigned i = 0; i < text->count; ++i)
            Serial::put(static_cast<std::uint8_t>(text->characters[i]));
    }
    return true;
}
auto export_committed() -> bool {
    // The prior client is already retired and its authenticated cleanup has
    // completed; this supervisor-only export has an independent finite budget.
    endpoint.caller_cancelled = false;
    reset_loader(16, 1);
    loading_image = true;
    for (U64 record = 0; record < 64; ++record) {
        const auto selected = export_request(7, record, 0);
        if (!selected)
            return false;
        if (*selected == ~U64{0})
            continue;
        if (*selected != 16)
            return false;
        const Bytes metadata{endpoint.bytes};
        const auto length = metadata.get(64), size = metadata.get(72);
        if (!length || length > process::file_path_limit || size > process::file_output_limit)
            return false;
        for (U64 offset = 0; offset < length;) {
            const auto count = export_request(8, 0, offset);
            if (!count || *count != least(504, length - offset))
                return false;
            for (U64 at = 0; at < *count; ++at) {
                const auto byte = endpoint.bytes[64 + at];
                if (byte == std::byte{0})
                    return false;
                export_name[offset + at] = byte;
            }
            offset += *count;
        }
        if (!export_clock_begin())
            return false;
        Serial::text("AURORA_EXPORT_BEGIN: path=");
        if (!export_path(length))
            fail("export path encoding");
        field("bytes", size);
        Serial::text("\r\n");
        if (!export_clock_end())
            return false;
        U64 lines = 0, filled = 0;
        std::array<std::byte, 57> line{};
        for (U64 offset = 0; offset < size;) {
            const auto count = export_request(9, 0, offset);
            if (!count || *count != least(504, size - offset) || !export_clock_begin())
                return false;
            for (U64 at = 0; at < *count; ++at) {
                line[filled++] = endpoint.bytes[64 + at];
                if (filled == line.size() || offset + at + 1 == size) {
                    Serial::text("AURORA_EXPORT_DATA: ");
                    for (U64 first = 0; first < filled; first += 3) {
                        const auto group = process::base64_group({line.data(), filled}, first);
                        if (!group)
                            fail("export data encoding");
                        for (unsigned i = 0; i < 4; ++i)
                            Serial::put(static_cast<std::uint8_t>(*group >> (8 * i)));
                    }
                    Serial::text("\r\n");
                    filled = 0;
                    ++lines;
                }
            }
            offset += *count;
            if (!export_clock_end())
                return false;
        }
        if (filled || !export_clock_begin())
            return false;
        Serial::text("AURORA_EXPORT_END: path=");
        if (!export_path(length))
            fail("export path encoding");
        field("lines", lines);
        Serial::text("\r\n");
        if (!export_clock_end())
            return false;
    }
    loading_image = false;
    return true;
}
auto run_file_client() -> bool {
    while (residents[1].space) {
        if (run_resident(1))
            break;
        if (outcome.request) {
            if (!client_request())
                return false;
            if (endpoint.caller_cancelled) {
                outcome = {};
                outcome.watchdog = true;
                static_cast<void>(retire_resident(1));
                break;
            }
        }
    }
    endpoint.caller.reset();
    endpoint.completion = endpoint.replied = false;
    return true;
}
auto begin_service_shutdown() -> void {
    if (!residents[0].space || residents[1].space || snapshot || !service_root.begin_shutdown(endpoint.generation))
        fail("file service shutdown intent");
}
auto finish_service_shutdown() -> void {
    const U64 generation = endpoint.generation;
    if (!generation || residents[0].space || residents[1].space || !outcome.exited || outcome.status ||
        outcome.terminal_service != generation || running.service != generation ||
        outcome.terminal_run != running.run || !service_root.normal_exit(generation))
        fail("file service normal terminal observation");
    endpoint.generation = 0;
    endpoint.waiting = endpoint.replied = endpoint.delivery = endpoint.completion = false;
    endpoint.caller.reset();
    acknowledge_service_cleanup(generation);
}
auto close_service_operation() -> void {
    if (residents[1].space || snapshot || endpoint.caller || endpoint.delivery || endpoint.completion ||
        !audit_residents() || !service_root.close_operation())
        fail("file service operation cleanup");
}
auto run_independent(std::span<const std::byte> view, std::span<const std::byte> runs) -> U64 {
    U64 count = 0;
    for (;;) {
        const auto entry = process::run(runs, count);
        if (!entry)
            fail("independent client entry");
        if (!entry->found)
            break;
        ++count;
        if (!service_root.open_operation())
            fail("companion operation admission");
        if (!start_companion(view, count) || !control_request(4, count)) {
            abandon_service();
            fail("companion startup");
        }
        if (load_one(view, runs, *entry, count, 1, true, true) && !run_file_client()) {
            abandon_service();
            fail("companion request");
        }
        if (!control_request(5, count) || !export_committed()) {
            abandon_service();
            fail("companion cleanup/export");
        }
        begin_service_shutdown();
        message_header(6, 0, 0, 0);
        if (exchange_request(0) || residents[0].space || !outcome.exited || outcome.status) {
            abandon_service();
            fail("companion shutdown");
        }
        finish_service_shutdown();
        endpoint = {};
        close_service_operation();
        if (!audit_residents())
            fail("companion final audit");
    }
    return count;
}

#ifdef AURORA_PROCESS_FIXTURE
// This preparation adapter uses the real run-list load and client admission.
// All later effects and binding authentication are the production implementation.
class FixtureExecutionTransport final : public ExecutionEffects {
    static inline std::span<const std::byte> volume_, runs_;
    static inline const process::RunEntry *entry_ = nullptr;
    static inline U64 client_ = 0;

public:
    static auto
    bind(std::span<const std::byte> volume, std::span<const std::byte> runs, const process::RunEntry &entry, U64 client)
        -> void {
        require(!entry_ && !residents[1].space);
        volume_ = volume;
        runs_ = runs;
        entry_ = &entry;
        client_ = client;
    }
    static auto unbind() -> void {
        require(entry_ && !residents[1].space && !endpoint.caller && !endpoint.completion && !snapshot);
        volume_ = runs_ = {};
        entry_ = nullptr;
        client_ = 0;
    }
    static auto prepare(Binding &binding) -> aurora::execution::Preparation {
        using namespace aurora::execution;
        require(entry_ && client_ && !binding.client && !residents[1].space && residents[0].space);
        binding.client = client_;
        binding.service_generation = endpoint.generation;
        require(bound_service(binding));
        if (!control_request(4, binding.client)) {
            abandon_service();
            binding.client = 0;
            return {Prepared::service_lost, Status::unavailable};
        }
        // A newly admitted client does not inherit the prior client's terminal
        // cancellation observation; production load_committed does the same.
        endpoint.caller_cancelled = false;
        const bool loaded = load_one(volume_, runs_, *entry_, binding.client, 1, true, true);
        return {loaded ? Prepared::loaded : Prepared::refused, loaded ? Status::exited : status(load_refusal)};
    }
};
using FixtureExecutionSession = aurora::execution::Session<FixtureExecutionTransport, ExecutionPlatform>;

auto execution_cancel_fixture(std::span<const std::byte> volume,
                              std::span<const std::byte> runs,
                              const process::RunEntry &entry,
                              U64 client,
                              U64 point) -> bool {
    using namespace aurora::execution;
    using Session = FixtureExecutionSession;
    FixtureExecutionTransport::bind(volume, runs, entry, client);
    const auto issuer = Session::open();
    const auto lease = Session::prepare(issuer.grant, issuer.generation);
    const auto prepared = Session::preparation(lease.binding, lease.generation);
    bool observed = false, request = false;
    U64 drain_transaction = 0, drain_next = 0, drain_used = 0, drain_quantum = 0;
    Finish disposition = Finish::complete;
    if (prepared.state == Prepared::loaded) {
        for (;;) {
            if (!request) {
                const auto step = Session::advance(lease.binding, lease.generation);
                if (step.state == Step::retired)
                    break;
                if (step.state == Step::output)
                    fail("unexpected fixture output effect");
                request = step.state == Step::request;
                if (!request)
                    continue;
            }
            // The observer selects a real initial or final raw-write message;
            // it never alters endpoint state or manufactures a service reply.
            const bool staged = endpoint.waiting && !endpoint.replied && !endpoint.delivery;
            const bool write =
                endpoint.call.action == static_cast<U64>(process::CallAction::write) && endpoint.call.length == 65536;
            const bool boundary = point == 2 ? !endpoint.waiting && !endpoint.replied && !endpoint.delivery
                                             : write && staged &&
                                                   (point == 1 ? endpoint.written == endpoint.call.length
                                                               : endpoint.written < endpoint.call.length);
            if (boundary && !observed) {
                const U64 generation = endpoint.generation, transaction = endpoint.transaction, next = endpoint.next;
                const U64 used = residents[0].state.budget->used();
                const U64 quantum = residents[0].state.budget->quantum();
                const bool available = residents[0].state.budget->available();
                const bool was_waiting = endpoint.waiting;
                const auto cancelled = static_cast<Cancel>(Session::cancel(lease.binding, lease.generation));
                if (cancelled != (point == 2 ? Cancel::draining : Cancel::settled) ||
                    endpoint.generation != generation || endpoint.transaction != transaction || endpoint.next != next ||
                    endpoint.waiting != was_waiting || endpoint.replied || endpoint.delivery ||
                    (point == 2 ? endpoint.caller != std::optional<std::size_t>{1} : endpoint.caller.has_value()) ||
                    endpoint.completion || residents[0].state.budget->used() != used ||
                    residents[0].state.budget->quantum() != quantum ||
                    residents[0].state.budget->available() != available)
                    fail("execution staged cancellation preservation");
                observed = true;
                drain_transaction = transaction;
                drain_next = next;
                drain_used = used;
                drain_quantum = quantum;
                disposition = Finish::cancel_requested;
                Serial::text("AURORA_EXECUTION_CANCEL:");
                field("client", client);
                field("tail", point);
                field("generation", generation);
                field("transaction", transaction);
                field("next", next);
                Serial::text("\r\n");
                if (point != 2)
                    break;
            }
            const auto result = static_cast<Request>(Session::request(lease.binding, lease.generation));
            if (result == Request::pending) {
                if (point == 2 && observed) {
                    const U64 used = residents[0].state.budget->used();
                    const U64 quantum = residents[0].state.budget->quantum();
                    const U64 ceiling = U64{1} << ((residents[0].state.flags & 8) ? 31 : 24);
                    // quantum is the remainder of the current tick, not its
                    // profile size. Crossing a tick increments used and may
                    // reload quantum; every actual server step consumes counts.
                    const bool consumed = used > drain_used || (used == drain_used && quantum < drain_quantum);
                    if (endpoint.transaction != drain_transaction || endpoint.next != drain_next || !consumed ||
                        !residents[0].state.budget->available() || !quantum || quantum > ceiling)
                        fail("execution cancellation drain renewed transaction or budget");
                    drain_used = used;
                    drain_quantum = quantum;
                }
                continue;
            }
            if (result == Request::ready) {
                request = false;
                continue;
            }
            disposition = result == Request::service_lost ? Finish::service_lost : Finish::cancelled;
            break;
        }
    }
    const bool finished = Session::finish(lease.binding, lease.generation, static_cast<U64>(disposition)) ==
                          static_cast<U64>(Effect::success);
    Session::release(issuer);
    FixtureExecutionTransport::unbind();
    if (!observed || !finished)
        fail("execution cancellation boundary not observed");
    if (point == 2 && disposition != Finish::service_lost)
        fail("execution delivered cancellation did not observe service loss");
    return disposition != Finish::service_lost;
}
#endif

// The first run is a kernel-designated server, never a role selected by its
// argv or exported symbols. The remaining entries are ordinary HostFiles
// clients. Committed files live only in that server's private ByteRegion.
auto run_external(std::span<const std::byte> view,
                  std::span<const std::byte> runs,
                  bool disk = false,
                  U64 first = 0,
                  U64 limit = ~U64{0},
                  bool recover = false,
                  XfsReadonlyProfile profile = XfsReadonlyProfile::fresh_format,
                  bool mounted = false,
                  bool cancel_delivered = false) -> U64 {
    static_cast<void>(cancel_delivered);
    if (residents[0].space || residents[1].space || !service_root.open_operation())
        fail("file service restart state");
    const auto service = process::run(runs, first);
    if (!service || !service->found)
        fail("file service run entry");
    if (mounted) {
        if (next_run < first)
            next_run = first;
        if (!runtime_storage.select(true, 3) || !ensure_file_service(view))
            fail("mounted file service startup");
    } else {
        if (service_root.admit(0, true) != aurora::service::Action::start)
            fail("file service incarnation admission");
        endpoint = {};
        endpoint.generation = service_root.generation();
        if (!load_one(view, runs, *service, first + 1, 0, true, true, endpoint.generation, disk))
            fail("file service load");
        while (residents[0].space && !endpoint.waiting)
            static_cast<void>(run_resident(0));
        if (!residents[0].space || !control_request(1, view.size(), static_cast<U64>(profile)))
            fail("file service startup");
        for (U64 offset = 0; offset < view.size();) {
            const auto count = least(Endpoint::capacity - 64, view.size() - offset);
            if (!control_request(2, 0, offset, view.subspan(offset, count)))
                fail("file service boot copy");
            offset += count;
        }
        if (!control_request(3))
            fail("file service volume admission");
        if (!service_root.mark_ready(endpoint.generation, false))
            fail("file service fixture readiness");
        Serial::text("AURORA_FILE_SERVICE_READY:");
        field("generation", endpoint.generation);
        field("owner", residents[0].space->owner());
        field("block_generation", residents[0].state.block_generation);
        field("block_sectors", residents[0].state.block_sectors);
        Serial::text("\r\n");
    }
    U64 count = first + 1;
    for (; count < limit;) {
        const auto entry = process::run(runs, count);
        if (!entry)
            fail("external client entry");
        if (!entry->found)
            break;
        ++count;
#ifdef AURORA_PROCESS_FIXTURE
        const auto arguments = runs.subspan(entry->arguments, entry->argument_bytes);
        constexpr std::string_view initial_cancel{"raw-cancel-initial\0", 19};
        constexpr std::string_view tail_cancel{"raw-cancel-tail\0", 16};
        const auto matches = [&](std::string_view name) {
            if (arguments.size() != name.size())
                return false;
            for (U64 at = 0; at < arguments.size(); ++at)
                if (arguments[at] != std::byte(static_cast<unsigned char>(name[at])))
                    return false;
            return true;
        };
        const bool initial = matches(initial_cancel), tail = matches(tail_cancel);
        if (initial || tail || cancel_delivered) {
            if (!execution_cancel_fixture(view, runs, *entry, count, cancel_delivered ? 2 : tail ? 1 : 0)) {
                if (!recover)
                    fail("execution fixture service loss");
                close_service_operation();
                return count;
            }
            continue;
        }
#endif
        if (!load_one(view, runs, *entry, count, 1, true, true))
            continue;
        if (!control_request(4, count)) {
            abandon_service();
            if (recover) {
                close_service_operation();
                return count;
            }
            fail("file service client admission");
        }
        if (!run_file_client()) {
            abandon_service();
            if (recover) {
                close_service_operation();
                return count;
            }
            fail("external file service terminated");
        }
        if (!control_request(5, count)) {
            abandon_service();
            if (recover) {
                close_service_operation();
                return count;
            }
            fail("file service client cleanup");
        }
    }
    begin_service_shutdown();
    message_header(6, 0, 0, 0);
    if (exchange_request(0) || residents[0].space || !outcome.exited || outcome.status) {
        abandon_service();
        if (recover) {
            close_service_operation();
            return count;
        }
        fail("file service shutdown");
    }
    finish_service_shutdown();
    close_service_operation();
    if (!audit_residents())
        fail("file service final audit");
    Serial::text("AURORA_FILE_SERVICE_OK:");
    field("clients", count - first - 1);
    field("transactions", endpoint.next);
    Serial::text("\r\n");
    return count;
}

#ifdef AURORA_UEFI_NVME
// Only the recovery fixture cases call this private composition. Its first admitted boot
// image is the recovery program; a pathname, argv or ELF type never mints it.
auto run_recovery(std::span<const std::byte> view, std::span<const std::byte> runs) -> bool {
    const auto entry = process::run(runs, 0);
    const auto baseline = table.free();
    if (!entry || !entry->found || residents[0].space || residents[1].space || endpoint.generation ||
        recovery_generation || recovery_completed || !aurora::uefi::nvme_recovery_sector_count())
        fail("recovery composition");
    if (!load_one(view, runs, *entry, 1, 0, true, true))
        return false;
    return finish_recovery(baseline);
}
#endif

// The row's run list, runs/<case> in the volume, run in order.
[[noreturn]] auto run_list(U64 arena, std::span<const std::byte> view, U64 selected) -> void {
    U64 run_case = selected;
#ifdef AURORA_PROCESS_FIXTURE
    if (selected >= 13 && selected <= 16) {
        recovery_cut_case = selected;
        run_case = 12; // Exactly the ordinary recovery program and run list.
    }
    if (selected >= 18 && selected <= 38) {
        mounted_cut_case = selected;
        run_case = 17; // The same mounted service and ordinary client.
    }
    if (selected == 40)
        mounted_cut_case = selected;
#endif
    char path[] = "runs/000";
    std::size_t length = 5;
    for (U64 scale = 100; scale; scale /= 10)
        if (run_case >= scale || scale == 1)
            path[length++] = static_cast<char>('0' + run_case / scale % 10);
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
    const bool paired = selected == 7;
    U64 count = 0;
    if (selected >= 1 && selected <= 6)
        count = run_independent(view, *runs);
    if (selected == 8)
        count = run_external(view, *runs);
    if (selected == 10) {
        const auto baseline = table.free();
        count = run_external(view, *runs, true, 0, 2, true);
        if (count != 2 || residents[0].space || residents[1].space || endpoint.generation || table.free() != baseline ||
            !audit_residents())
            fail("block grant loss cleanup");
        count = run_external(view, *runs, true, count);
    }
    if (selected == 11)
        count = run_external(view, *runs, true, 0, ~U64{0}, false, XfsReadonlyProfile::linux_6_12_x86_64_clean);
#ifdef AURORA_UEFI_NVME
    if (run_case == 12 || run_case == 41) {
        if (!run_recovery(view, *runs))
            fail("recovery not completed");
        // A successful exit and flush do not establish a filesystem mount.
        // A fresh Serve process independently performs the unchanged RO gate.
        count = run_external(view, *runs, true, 1, ~U64{0}, false, XfsReadonlyProfile::linux_6_12_x86_64_clean);
    }
#endif
    if (run_case == 17 || run_case == 39)
        count = run_external(view, *runs, true, 0, ~U64{0}, false, XfsReadonlyProfile::linux_6_12_x86_64_clean, true);
    if (selected == 40) {
        const auto baseline = table.free();
        count = run_external(view, *runs, true, 0, 2, true, XfsReadonlyProfile::linux_6_12_x86_64_clean, true);
        if (count != 2 || residents[0].space || residents[1].space || endpoint.generation || mounted_generation ||
            table.free() != baseline || !audit_residents())
            fail("mounted owner loss cleanup");
        count =
            run_external(view, *runs, true, count, ~U64{0}, false, XfsReadonlyProfile::linux_6_12_x86_64_clean, true);
    }
    if (selected == 9) {
        const auto baseline = table.free();
        // Each closed pair deliberately loses a designated raw endpoint. Its
        // next pair starts a new incarnation, never replays the failed request.
        for (; count < 20;) {
            const auto end = count + 2;
            count = run_external(
                view, *runs, false, count, end, true, XfsReadonlyProfile::fresh_format, false, count == 16);
            if (count != end || residents[0].space || residents[1].space || endpoint.generation ||
                table.free() != baseline || !audit_residents())
                fail("file service loss cleanup");
        }
        count = run_external(view, *runs, false, count);
    }
    for (; selected == 7;) {
        const auto entry = process::run(*runs, count);
        if (!entry)
            fail("Aurora run entry");
        if (!entry->found)
            break;
        const auto width = paired ? KernelSpace::process_slots : 1;
        for (std::size_t slot = 0; slot < width; ++slot) {
            const auto next = slot == 0 ? entry : process::run(*runs, count);
            if (!next)
                fail("Aurora run entry");
            if (!next->found)
                break;
            ++count;
            static_cast<void>(load_one(view, *runs, *next, count, slot, paired));
        }
        U64 cursor = 0;
        for (;;) {
            const U64 eligible = (residents[0].space ? 1 : 0) | (residents[1].space ? 2 : 0);
            const auto encoded = aurora::ipc::language_round_robin_next(cursor, eligible);
            const auto selected = aurora::ipc::RoundRobinSelection::decode(encoded, cursor, eligible);
            if (!selected)
                fail("Aurora resident selection");
            if (!selected->selected())
                break;
            cursor = selected->next();
            static_cast<void>(run_resident(selected->client()));
        }
    }
    Serial::text("AURORA_PROCESS_RUNS_OK:");
    field("runs", count);
    field("free", table.free());
    Serial::text("\r\n");
    aurora::hardware::Io::write(0xf4, 0x10);
    for (;;)
        asm volatile("cli; hlt");
}
#endif

} // namespace

namespace {
constinit std::optional<KernelSpace::Plan> runtime_plan;
auto initialize_process(U64 arena, const Bytes &h, U64 selected, bool timer_ready) -> std::span<const std::byte> {
    owned_arena = arena;
    kernel_root = h.get(88);
#ifndef AURORA_PRODUCTION
    if (selected && !timer_ready)
        establish_timer(arena, h);
#else
    if (!timer_ready)
        fail("production timer was not admitted");
#endif
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
    const auto record_pages = KernelSpace::process_pages * (selected ? KernelSpace::process_slots : 1);
    const auto plan = KernelSpace::plan(ranges.frames(), volume_pages, record_pages);
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
    runtime_plan = *plan;
    if (selected)
        service_root.create();
    return view;
}
} // namespace

#ifndef AURORA_PRODUCTION
auto aurora::uefi::run_process(U64 arena, const Bytes &h) -> void {
    const auto selected = h.get(Handoff::case_word);
    const auto view = initialize_process(arena, h, selected, false);
    if (selected)
        run_list(arena, view, selected);
    frame_cases(h.get(96));
    space_cases(*runtime_plan, h.get(96));
    export_entry(view, exported);
    Serial::text("AURORA_PROCESS_OK\r\n");
    aurora::hardware::Io::write(0xf4, 0x10);
    for (;;)
        asm volatile("cli; hlt");
}
#endif
#ifdef AURORA_PRODUCTION
namespace {
auto loader_call(U64 client, U64 operation, U64 id = 0, U64 offset = 0, std::span<const std::byte> payload = {})
    -> bool {
    if (payload.size() > Endpoint::capacity - 64 || endpoint.caller || endpoint.caller_cancelled)
        return false;
    message_header(operation, id, offset, payload.size());
    for (U64 at = 0; at < payload.size(); ++at)
        endpoint.bytes[64 + at] = payload[at];
    endpoint.call = {};
    endpoint.call.action = operation == 18   ? static_cast<U64>(process::CallAction::open_file)
                           : operation == 19 ? static_cast<U64>(process::CallAction::read)
                                             : static_cast<U64>(process::CallAction::close);
    if (!exchange_request(client) || !admit_file_reply())
        return false;
    endpoint.replied = false;
    return !endpoint.caller_cancelled;
}
// This boot-global attempt is independent of the source file owner's lifetime.
// No service restart or ordinary run path may select or reload the writer.
auto prepare_recovery(std::span<const std::byte> volume) -> void {
    if (!runtime_storage.claim_recovery())
        return;
#ifdef AURORA_UEFI_NVME
    constexpr std::string_view path = "bin/xfs-recover", arguments{"xfs-recover\0", 12};
    const auto baseline = table.free();
    const auto image = process::volume_lookup(volume, bytes_of(path));
    process::RunEntry entry{};
    entry.ticks = 16;
    entry.flags = 8;
    entry.quota = 16384;
    if (residents[0].space || residents[1].space || endpoint.generation || recovery_generation || recovery_completed ||
        !image || next_run >= 0xffffffffULL - frames::first_owner || !aurora::uefi::nvme_recovery_sector_count() ||
        !load_image(volume, *image, bytes_of(arguments), entry, ++next_run, 0, true, true) ||
        !finish_recovery(baseline)) {
        aurora::uefi::nvme_recovery_abandon();
        Serial::text("AURORA_PROCESS_RECOVERY: refused disk=unavailable\r\n");
    } else {
        Serial::text("AURORA_PROCESS_RECOVERY: complete readonly\r\n");
    }
#else
    static_cast<void>(volume);
#endif
}
auto load_committed(std::span<const std::byte> volume,
                    U64 client,
                    std::span<const std::byte> path,
                    std::span<const std::byte> arguments) -> RunStatus {
    reset_loader(128);
    loading_image = true;
    endpoint.caller_cancelled = false;
    if (!loader_call(client, 18, 0, 0, path))
        return RunStatus::unavailable;
    const Bytes opened{endpoint.bytes};
    if (opened.get(0))
        return opened.get(0) == 2 ? RunStatus::missing : RunStatus::unavailable;
    const U64 id = opened.get(16), size = opened.get(24);
    RunStatus status = RunStatus::malformed;
    if (size && size <= aurora::uefi::ImageSnapshot::limit) {
        const U64 cost = aurora::uefi::ImageSnapshot::cost(size);
        if (cost > available_frames()) {
            status = RunStatus::quota;
        } else {
            snapshot.emplace(space, table, ranges, space.mappings(ranges.frames()), frames::first_owner + client, size);
            if (!snapshot->begin())
                fail("loader snapshot allocation");
            auto target = snapshot->writable();
            U64 offset = 0;
            while (offset < size) {
                if (!loader_call(client, 19, id, offset)) {
                    status = RunStatus::unavailable;
                    break;
                }
                const Bytes reply{endpoint.bytes};
                const U64 count = reply.get(8);
                if (reply.get(0) || !count || count > size - offset) {
                    status = RunStatus::unavailable;
                    break;
                }
                for (U64 at = 0; at < count; ++at)
                    target[offset + at] = endpoint.bytes[64 + at];
                offset += count;
            }
            if (offset == size && !snapshot->seal())
                fail("loader snapshot seal");
            if (offset != size) {
                discard_snapshot();
            }
        }
    }
    if (!loader_call(client, 20, id))
        return RunStatus::unavailable;
    if (Bytes{endpoint.bytes}.get(0))
        return RunStatus::unavailable;
    loading_image = false;
    if (!snapshot)
        return status;
    process::RunEntry entry{};
    entry.ticks = 128;
    if (!load_image(volume, snapshot->bytes(), arguments, entry, client, 1, true, true)) {
        discard_snapshot();
        return load_refusal;
    }
    return RunStatus::exited; // Loaded, not yet executed.
}
class ExecutionTransport final : public ExecutionEffects {
    static inline std::span<const std::byte> volume_, path_, arguments_;

public:
    static auto bind(std::span<const std::byte> volume,
                     std::span<const std::byte> path,
                     std::span<const std::byte> arguments) -> void {
        require(volume_.empty() && !residents[1].space);
        volume_ = volume;
        path_ = path;
        arguments_ = arguments;
    }
    static auto unbind() -> void {
        require(!residents[1].space && !endpoint.caller && !endpoint.completion && !snapshot);
        volume_ = path_ = arguments_ = {};
    }
    static auto prepare(Binding &binding) -> aurora::execution::Preparation {
        using namespace aurora::execution;
        require(!volume_.empty() && !binding.client && !residents[1].space);
        if (!ensure_file_service(volume_)) {
            abandon_service();
            return {Prepared::service_lost, Status::unavailable};
        }
        if (next_run >= 0xffffffffULL - frames::first_owner)
            return {Prepared::refused, Status::unavailable};
        binding.client = ++next_run;
        binding.service_generation = endpoint.generation;
        if (!control_request(4, binding.client)) {
            abandon_service();
            binding.client = 0;
            return {Prepared::service_lost, Status::unavailable};
        }
        const auto loaded = load_committed(volume_, binding.client, path_, arguments_);
        loading_image = false;
        if (loaded == RunStatus::unavailable) {
            abandon_service();
            binding.client = 0;
            return {Prepared::service_lost, Status::unavailable};
        }
        require((loaded == RunStatus::exited) == residents[1].space.has_value());
        return {residents[1].space ? Prepared::loaded : Prepared::refused, status(loaded)};
    }
};
using ExecutionSession = aurora::execution::Session<ExecutionTransport, ExecutionPlatform>;

} // namespace

namespace {
auto enter_runtime(U64 arena, const Bytes &handoff) -> bool {
    if (!Timer::irq_off() || root() != handoff.get(88) || running.space || residents[1].space || snapshot ||
        Timer::read(0x390) || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        return false;
#ifdef AURORA_UEFI_NVME
    const bool selected_block = handoff.get(Handoff::composition_word) == 4;
#else
    constexpr bool selected_block = false;
#endif
    const auto profile_word = handoff.get(Handoff::readonly_profile_word);
    if (!runtime_storage.select(selected_block, profile_word))
        return false;
    if (!runtime_initialized) {
        // This selection belongs to the admitted boot, not the current service
        // incarnation. Owner loss cannot reset or silently change its profile.
        static_cast<void>(initialize_process(arena, handoff, 8, true));
        runtime_initialized = true;
        capture_shared(arena);
        process_kernel_root = kernel_root;
    } else {
        if (!runtime_detached || arena != owned_arena || root() != kernel_root || !space.attach(ranges))
            fail("process runtime reattach");
        runtime_detached = false;
        if (!space.verify(table, ranges, handoff.get(96)) || !audit_residents())
            fail("process runtime attachment audit");
    }
    install_architecture(arena);
    prepare_recovery(space.volume(handoff.get(Handoff::volume_bytes_word)));
    if (!service_root.open_operation())
        fail("file service operation admission");
    return true;
}
auto leave_runtime(const Bytes &handoff) -> void {
    if (running.space || residents[1].space || snapshot || endpoint.caller || endpoint.delivery ||
        endpoint.completion || Timer::read(0x390) || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false) ||
        !audit_residents() || !space.verify(table, ranges, handoff.get(96)))
        fail("process runtime return audit");
    if (!service_root.close_operation() || !space.detach())
        fail("process runtime lifecycle return");
    runtime_detached = true;
}
} // namespace

auto aurora::uefi::run_program(U64 arena,
                               const Bytes &handoff,
                               std::span<const std::byte> path,
                               std::span<const std::byte> arguments,
                               ProcessOutput output,
                               void *context) -> RunResult {
    if (!output || path.empty() || path.size() > process::file_path_limit || arguments.empty() ||
        arguments.size() > 65536 || !enter_runtime(arena, handoff))
        return {};
    output_sink = output;
    output_context = context;
    ExecutionTransport::bind(space.volume(handoff.get(Handoff::volume_bytes_word)), path, arguments);
    const auto grant = ExecutionSession::open();
    aurora::execution::Result observed;
    source_execute(&grant, &observed);
    ExecutionSession::release(grant);
    ExecutionTransport::unbind();
    if (static_cast<U64>(observed.status) > static_cast<U64>(aurora::execution::Status::cancelled))
        fail("execution result");
    const RunResult result{static_cast<RunStatus>(observed.status), observed.value};
    output_sink = nullptr;
    output_context = nullptr;
    leave_runtime(handoff);
    return result;
}

auto aurora::uefi::prepare_programs(U64 arena, const Bytes &handoff) -> bool {
    bool ready = false;
    if (handoff.get(Handoff::composition_word) == 4 && enter_runtime(arena, handoff)) {
        if (!ensure_file_service(space.volume(handoff.get(Handoff::volume_bytes_word))))
            abandon_service();
        ready = service_root.disk_ready(endpoint.generation);
        leave_runtime(handoff);
    }
    Serial::text(ready ? std::string_view{"AURORA_PROCESS_DISK: ready"}
                       : std::string_view{"AURORA_PROCESS_DISK: unavailable"});
    Serial::text(runtime_storage.mounted() ? std::string_view{" mounted\r\n"} : std::string_view{" readonly\r\n"});
    return ready;
}

auto aurora::uefi::console_request(U64 arena,
                                   const Bytes &handoff,
                                   ConsoleOperation operation,
                                   U64 expected_generation,
                                   U64 expected_note_revision,
                                   std::span<const std::byte> request,
                                   std::span<std::byte> response) -> ConsoleResult {
    const auto code = static_cast<U64>(operation);
    const U64 input_size = code == 10 ? 72 : code == 11 ? 80 : code == 12 ? 72 : code == 13 ? 232 : 0;
    const U64 output_size = code == 10 ? 80 : code == 11 ? 248 : code == 13 ? 80 : 0;
    if (code < 10 || code > 14 || request.size() != input_size || response.size() != output_size ||
        (code >= 12 && !expected_generation) || (code == 12 ? !expected_note_revision : expected_note_revision != 0))
        return {ConsoleStatus::malformed, 0, 0};
    for (auto &byte : response)
        byte = std::byte{0};
    if (!enter_runtime(arena, handoff))
        return {};
    ConsoleResult result;
    if (!ensure_file_service(
            space.volume(handoff.get(Handoff::volume_bytes_word)), expected_generation, expected_generation == 0)) {
        if (expected_generation) {
            // The source refused this pinned incarnation; the endpoint ordinal
            // is only the current physical binding reported to the consumer.
            result = {
                endpoint.generation ? ConsoleStatus::conflict : ConsoleStatus::unavailable, endpoint.generation, 0};
        } else {
            abandon_service();
        }
        leave_runtime(handoff);
        return result;
    }
    reset_loader(128);
    loading_image = true;
    endpoint.caller_cancelled = false;
    message_header(code, expected_note_revision, 0, request.size());
    for (U64 at = 0; at < request.size(); ++at)
        endpoint.bytes[64 + at] = request[at];
    const bool received = exchange_request(0) && !endpoint.caller_cancelled;
    bool valid = received && endpoint.count >= 64;
    const Bytes reply{endpoint.bytes};
    const U64 status = valid ? reply.get(0) : 3, count = valid ? reply.get(8) : 0, revision = valid ? reply.get(16) : 0;
    valid = valid && status <= 2 && count == (status ? 0 : output_size) && endpoint.count == 64 + count;
    for (U64 at = 24; valid && at < 64; ++at)
        valid = endpoint.bytes[at] == std::byte{0};
    if (status)
        valid = valid && revision == 0;
    else if (code == 10)
        valid = valid && revision != 0;
    else if (code == 12)
        valid = valid && expected_note_revision != ~U64{0} && revision == expected_note_revision + 1;
    else
        valid = valid && revision == 0;
    loading_image = false;
    if (!valid) {
        if (received && !endpoint.invalid_reply_operation)
            endpoint.invalid_reply_operation = code;
        abandon_service();
    } else {
        result = {status == 0   ? ConsoleStatus::success
                  : status == 1 ? ConsoleStatus::conflict
                                : ConsoleStatus::malformed,
                  endpoint.generation,
                  revision};
        for (U64 at = 0; at < count; ++at)
            response[at] = endpoint.bytes[64 + at];
        endpoint.replied = false;
    }
    leave_runtime(handoff);
    return result;
}

auto aurora::uefi::reject_program_service(U64 arena, const Bytes &handoff, U64 expected_generation) -> ConsoleStatus {
    if (!expected_generation)
        return ConsoleStatus::malformed;
    if (!enter_runtime(arena, handoff))
        return ConsoleStatus::unavailable;
    ConsoleStatus result = ConsoleStatus::unavailable;
    if (ensure_file_service(space.volume(handoff.get(Handoff::volume_bytes_word)), expected_generation, false)) {
        abandon_service(ServiceFailure::consumer_rejected);
        result = ConsoleStatus::success;
    } else if (endpoint.generation) {
        result = ConsoleStatus::conflict;
    }
    leave_runtime(handoff);
    return result;
}

auto execution_prepare(const void *, U64, aurora::execution::Lease *) -> void asm("__au_runtime_execution_prepare")
    __attribute__((visibility("hidden")));
auto execution_prepare(const void *grant, U64 generation, aurora::execution::Lease *result) -> void {
    *result = ExecutionSession::prepare(grant, generation);
}
auto execution_preparation(const void *, U64, aurora::execution::Preparation *)
    -> void asm("__au_runtime_execution_preparation") __attribute__((visibility("hidden")));
auto execution_preparation(const void *binding, U64 generation, aurora::execution::Preparation *result) -> void {
    *result = ExecutionSession::preparation(binding, generation);
}
auto execution_advance(const void *, U64, aurora::execution::Observation *)
    -> void asm("__au_runtime_execution_advance") __attribute__((visibility("hidden")));
auto execution_advance(const void *grant, U64 generation, aurora::execution::Observation *result) -> void {
    *result = ExecutionSession::advance(grant, generation);
}
auto execution_output(const void *, U64) -> U64 asm("__au_runtime_execution_output")
    __attribute__((visibility("hidden")));
auto execution_output(const void *grant, U64 generation) -> U64 {
    return ExecutionSession::output(grant, generation);
}
auto execution_request(const void *, U64) -> U64 asm("__au_runtime_execution_request")
    __attribute__((visibility("hidden")));
auto execution_request(const void *grant, U64 generation) -> U64 {
    return ExecutionSession::request(grant, generation);
}
auto execution_cancel(const void *, U64) -> U64 asm("__au_runtime_execution_cancel")
    __attribute__((visibility("hidden")));
auto execution_cancel(const void *binding, U64 generation) -> U64 {
    return ExecutionSession::cancel(binding, generation);
}
auto execution_finish(const void *, U64, U64) -> U64 asm("__au_runtime_execution_finish")
    __attribute__((visibility("hidden")));
auto execution_finish(const void *grant, U64 generation, U64 disposition) -> U64 {
    return ExecutionSession::finish(grant, generation, disposition);
}

#endif
