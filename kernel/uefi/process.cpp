#include "process.hpp"
#include "acpi.hpp"
#include "apic-timer-io.hpp"
#include "console-context.hpp"
#include "../retained-budget.hpp"
#include "../retained-service.hpp"
#include "../retained-endpoint.hpp"
#include "../execution-lifecycle.hpp"
#include "execution-authority-effects.hpp"
#include "../round-robin-transport.hpp"
#include "process-space.hpp"
#include "image-snapshot.hpp"
#include "../committed-load.hpp"
#ifdef AURORA_UEFI_NVME
#include "nvme.hpp"
#endif
#include "../console.hpp"
#include "../execution-session.hpp"
#include "../execution-batch.hpp"
#include "../service-bootstrap.hpp"

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

#ifdef AURORA_PRODUCTION
auto source_resident_construct(void *, aurora::resident::Descriptor *) -> void asm("__au_runtime_resident_construct")
    __attribute__((visibility("hidden")));
auto source_resident_prepare(void *) -> U64 asm("__au_runtime_process_resident_prepare")
    __attribute__((visibility("hidden")));
auto source_resident_run(void *, aurora::execution::Result *) -> void asm("__au_runtime_process_resident_run")
    __attribute__((visibility("hidden")));
auto source_resident_console(void *) -> U64 asm("__au_runtime_process_resident_console")
    __attribute__((visibility("hidden")));
auto source_resident_reject(void *) -> U64 asm("__au_runtime_process_resident_reject")
    __attribute__((visibility("hidden")));
auto source_resident_stop(void *) -> U64 asm("__au_runtime_process_resident_stop")
    __attribute__((visibility("hidden")));
auto source_resident_finish(void *) -> U64 asm("__au_runtime_process_resident_finish")
    __attribute__((visibility("hidden")));
#endif

auto source_bootstrap_service(const aurora::bootstrap::Argument *) -> U64 asm("__au_runtime_process_bootstrap_service")
    __attribute__((visibility("hidden")));

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
constinit aurora::uefi::MemoryManager table;
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
    std::array<U64, frame_words> *continuation = nullptr, *captured = nullptr;
    U64 slice = 0, service = 0, block_generation = 0, block_sectors = 0, companion = 0;
    U64 recovery_generation = 0, recovery_sectors = 0;
    U64 mounted_generation = 0, mounted_sectors = 0;
    U64 volumes_generation = 0, volumes_count = 0;
    bool external = false;
    auto operator==(const Running &) const -> bool = default;
};
// How the process ended, copied from its last kernel entry.
class Outcome final {
public:
    bool exited = false, watchdog = false, invalid_call = false, parked = false, exchange = false, request = false,
         output = false, unavailable = false, cancelled = false, input = false;
    process::TrapClass trap = process::TrapClass::kernel;
    U64 status = 0, vector = 0, error = 0, rip = 0, cr2 = 0, operation = 0;
    U64 terminal_ticks = 0, terminal_run = 0, terminal_service = 0;
};
constinit Running running;
constinit Outcome outcome;
class ExecutionCapture final {
public:
    aurora::lifecycle::Event event = aurora::lifecycle::Event::none;
    U64 detail = 0;
    bool exhausted = false;
    process::TrapClass trap = process::TrapClass::kernel;
    U64 vector = 0, error = 0, rip = 0, cr2 = 0;
};
constinit ExecutionCapture execution_capture;
constinit U64 owned_arena = 0, kernel_root = 0, kernel_table_pages = 0, physical_bits = 0, process_volume_bytes = 0;
constinit bool draining = false;
constinit aurora::uefi::ProcessOutput output_sink = nullptr;
constinit void *output_context = nullptr;
constinit aurora::uefi::ProcessInput input_source = nullptr;
#ifdef AURORA_PRODUCTION
constinit bool runtime_initialized = false;
#endif
#if defined(AURORA_PRODUCTION) || defined(AURORA_PROCESS_FIXTURE)
constinit bool runtime_detached = false;
constinit aurora::uefi::ProcessPresentation presentation_sink = nullptr;
constinit const Bytes *presentation_handoff = nullptr;
auto present_foreground(std::size_t selected = 1) -> void;
#endif
#ifdef AURORA_PRODUCTION
enum class RunMode {
    single,
    pair
};
class ResidentArguments final {
public:
    std::span<const std::byte> volume{}, path{}, arguments{}, request{};
    std::span<std::byte> response{};
    RunMode mode = RunMode::single;
    std::span<const std::byte> second_path{}, second_arguments{};
    aurora::uefi::ConsoleOperation console = aurora::uefi::ConsoleOperation::clear;
    U64 expected = 0, revision = 0, map_count = 0;
};
class ResidentInput final {
public:
    const ResidentArguments arguments;
    aurora::uefi::ConsoleResult console_result{};
    aurora::uefi::RunPairResult pair_result{};
    U64 shutdown_generation = 0, shutdown_transaction = 0;
    bool shutdown_pending = false, shutdown_terminal = false, shutdown_failed = false;
    explicit ResidentInput(ResidentArguments value) : arguments(value) {
    }
};
class ResidentPlatform final {
public:
    static auto quiet() -> bool;
    [[noreturn]] static auto fail() -> void;
    static auto construct(void *destination, aurora::resident::Descriptor *input) -> void {
        source_resident_construct(destination, input);
    }
};
using ResidentRoot = aurora::resident::Root<ResidentInput, ResidentPlatform>;
constinit ResidentRoot resident_owner;
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
class LifecyclePlatform final {
public:
    static auto authenticate_presentation(U64 slot, aurora::lifecycle::Phase phase) -> void;
    static auto quiet() -> bool {
        return Timer::irq_off() && root() == kernel_root && !running.space && space.closed() && !Timer::read(0x390) &&
               Timer::quiet(0x100, false) && Timer::quiet(0x200, false);
    }
    [[noreturn]] static auto fail() -> void {
        ::fail("execution lifecycle authority");
    }
};
using LifecycleRoot = aurora::lifecycle::Root<LifecyclePlatform>;
constinit LifecycleRoot execution_owner;

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
        shared.upper[slot - 256] = top[slot] & ~ProcessSpace::hardware_bits;
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
    table.attach(space, shared, physical_bits, kernel_root);
    aurora::uefi::register_loader_source(table);
    table.attach_boot_volume(space.volume(process_volume_bytes));
    if (!execution_owner.created())
        execution_owner.initialize();
}

#ifdef AURORA_PROCESS_FIXTURE
constinit U64 authority_probe_pending = 0, authority_probe_armed = 0, authority_probe_opens = 0;
// Arm at the forbidden native entry, after legitimate source traversal has
// closed its windows. These observations do not authorize any effect.
auto arm_authority_probe(U64 probe) -> void {
    if (authority_probe_armed || !space.closed())
        fail("mapping authority probe setup");
    authority_probe_pending = 0;
    authority_probe_armed = probe;
    authority_probe_opens = space.fixture_opens();
    Serial::text("AURORA_MAPPING_AUTHORITY_PROBE:");
    field("case", probe);
    field("root", root());
    field("kernel", kernel_root);
    field("closed", space.closed());
    Serial::text("\r\n");
}
#endif

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
};
constinit std::array<Resident, KernelSpace::process_slots> residents;
auto clients_live() -> bool {
    return residents[1].space.has_value() || residents[2].space.has_value();
}
auto running_client_slot() -> std::size_t {
    for (std::size_t slot = 1; slot < residents.size(); ++slot) {
        const auto &resident = residents[slot];
        if (resident.space && running.space == &*resident.space && running.run == resident.state.run &&
            running.captured == &resident.continuation && running.budget == &resident.budget)
            return slot;
    }
    fail("running client identity");
}

// These are actual synchronous command-operation receipts, not slot lifecycle
// state. Only the active command transport may install a force context.
class ExecutionBinding final {
public:
    U64 client = 0, service_generation = 0;
    std::size_t slot = 1;
    bool output_pending = false, request_pending = false, input_pending = false;
    bool output_failed = false, request_failed = false;
    bool explicit_cancel_requested = false, expiry_preceded_cancel = false;
};
constinit const ExecutionBinding *forced_execution = nullptr;
constinit const bool *completed_output = nullptr;

// A single command-owned staging receipt. Source owns protocol outcomes; these
// words bind actual mappings and saved continuation, not a second lifecycle.
class InputPending final {
public:
    U64 owner = 0, sequence = 0, address = 0, generation = 0, epoch = 0, root = 0;
    bool pending = false, completing = false, quarantine = false;
    process::InputSession protocol;
    std::array<std::byte, 504> bytes{};
    std::array<U64, frame_words> frame{};
};
constinit InputPending input_read;

// Compare the complete fixed-size saved frame inside the native effect body.
// This word reduction avoids importing the separate assembly memcmp boundary.
auto input_frame_equal(const std::array<U64, frame_words> &left, const std::array<U64, frame_words> &right) -> bool {
    U64 difference = 0;
    for (std::size_t at = 0; at < frame_words; ++at)
        difference |= left[at] ^ right[at];
    return difference == 0;
}

class InputWait final {
public:
    U64 stack = 0, armed = 0, owner = 0, sequence = 0;
    bool active = false, expired = false;
};
constinit InputWait input_wait;
extern const std::byte input_wait_begin asm("uefi_process_input_wait_begin");
extern const std::byte input_wait_end asm("uefi_process_input_wait_end");
constexpr U64 input_poll_count = 1250000;
// One command's admitted count-domain allowance. Not calibrated seconds.
constexpr U64 input_wait_allowance = 1000 * input_poll_count;
#ifdef AURORA_PROCESS_FIXTURE
// Trusted boot selector only. Never selected by a client argument or syscall.
constinit U64 input_probe_case = 0, input_probe_settlements = 0;
constinit U64 input_probe_completions = 0, input_probe_samples = 0;
constinit bool input_probe_partial = false;
constinit U64 input_probe_retired = 0, input_probe_lease_generation = 0;
constinit const void *input_probe_lease = nullptr;
auto input_probe_reenter() -> void;
#endif

// A copied synchronous endpoint, not a namespace or backing store. Exactly
// one transaction is outstanding. Source/transaction never come from a client.
class Endpoint final {
public:
    static constexpr U64 capacity = 65536, window_bytes = 131136, request_offset = 64, reply_offset = 65600;
    std::array<std::byte, capacity> bytes{};
    U64 generation = 0, window = 0, count = 0;
    bool caller_cancelled = false;
    std::optional<std::size_t> caller;
    process::KernelCall call{};
    U64 written = 0, request_operation = 0, invalid_reply_operation = 0;
};
constinit Endpoint endpoint;
} // namespace

// Only this fixed-origin boot hook can register a loader source. No public API
// accepts a pointer/span to substitute another object for the endpoint buffer.
auto aurora::uefi::register_loader_source(MemoryManager &manager) -> void {
    manager.register_loader_buffer(::endpoint.bytes, owned_arena, kernel_table_pages);
}

namespace {
// Short source loans are allowed only in the quiet supervisor or the exact
// authenticated syscall scope. They never survive a copy, CR3 switch or entry.
constinit bool endpoint_trap_scope = false;
class EndpointTrapScope final {
public:
    EndpointTrapScope() {
        if (endpoint_trap_scope || !execution_owner.busy() || !running.space || root() != running.space->root())
            fail("endpoint trap scope");
        endpoint_trap_scope = true;
    }
    ~EndpointTrapScope() {
        endpoint_trap_scope = false;
    }
};
class EndpointPlatform final {
    static inline U64 saved_root = 0;
    static inline ProcessSpace *saved_space = nullptr;
    static inline bool saved_busy = false, saved_entered = false;

public:
    static auto enter() -> void {
        const auto current = root();
        if (saved_root || !Timer::irq_off() ||
            !((current == kernel_root && !running.space) ||
              (endpoint_trap_scope && execution_owner.busy() && running.space && current == running.space->root())))
            fail();
        saved_root = current;
        saved_space = running.space;
        saved_busy = execution_owner.busy();
        saved_entered = execution_owner.entered();
    }
    static auto leave() -> void {
        if (!saved_root || !Timer::irq_off() || root() != saved_root || running.space != saved_space ||
            execution_owner.busy() != saved_busy || execution_owner.entered() != saved_entered)
            fail();
        saved_root = 0;
        saved_space = nullptr;
    }
    [[noreturn]] static auto fail() -> void {
        ::fail("retained endpoint lifetime");
    }
};
using EndpointRoot = aurora::endpoint::Root<EndpointPlatform>;
constinit EndpointRoot endpoint_owner;

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
// Immutable for one service incarnation; clearing revokes the whole set.
class VolumeGrant final {
public:
    U64 generation{}, controller{}, nsid{}, sectors{};
};
constinit std::array<VolumeGrant, 2> volume_grants{};
constinit U64 volumes_service{}, volumes_owner{}, volumes_root{}, volumes_generation{}, volumes_count{};
auto revoke_volumes() -> void {
    volumes_service = volumes_owner = volumes_root = volumes_generation = volumes_count = 0;
    volume_grants = {};
}
// This separate boot role is never set by ordinary load_image/run or Serve.
// The recovery composition will mint it only after its private image is admitted.
constinit U64 recovery_owner = 0, recovery_root = 0, recovery_generation = 0, recovery_sectors = 0;
constinit U64 mounted_owner = 0, mounted_root = 0, mounted_generation = 0, mounted_sectors = 0, mounted_service = 0;
#ifdef AURORA_PROCESS_FIXTURE
constinit U64 recovery_cut_case = 0, mounted_cut_case = 0;
constinit bool frame_finish_fault = false, nested_fault_probe = false;
constinit U64 execution_probe_case = 0;
constinit bool mounted_owner_termination = false, mounted_prepared_refusal = false;
constinit bool mounted_confirmation_probe = false, mounted_confirmation_corrupted = false;
constinit bool mounted_confirmation_shutdown_failed = false;
#endif
constinit bool recovery_completed = false;
constinit std::array<std::byte, 512> block_copy{};

#ifdef AURORA_PROCESS_FIXTURE
auto execution_probe_marker(U64 probe, U64 slot) -> void {
    Serial::text("AURORA_EXECUTION_AUTHORITY_PROBE:");
    field("case", probe);
    field("slot", slot);
    field("root", root());
    field("kernel", kernel_root);
    field("closed", space.closed());
    Serial::text("\r\n");
}
#endif

auto save_frame(const volatile U64 *frame) -> void {
    if (!running.continuation)
        fail("missing process continuation");
    if (running.captured != running.continuation ||
        frame != reinterpret_cast<const volatile U64 *>(owned_arena + BootstrapLayout::rsp0_top - frame_words * 8))
        fail("process capture identity");
    if (execution_capture.event == aurora::lifecycle::Event::none)
        execution_capture.event = aurora::lifecycle::Event::timer;
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
        execution_capture.exhausted = true;
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
    if (execution_capture.exhausted) {
        execution_capture.event = aurora::lifecycle::Event::timer;
        return 1;
    }
    if (running.continuation) {
        save_frame(frame);
        return 1;
    }
    arm_slice();
    return 0;
}

// The source manager owns aggregate resident/snapshot accounting and performs
// the physical walks under its one authority scope. Native retains no quota sum.
auto audit_residents() -> bool {
    return table.audit_residents();
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
        const NvmeReadContext context(running.space->root(), running.block_generation);
        const auto sectors = nvme_sector_count(context);
        // Quarantine is absorbing. The original grant remains authenticated,
        // but conveys no usable backend and is never refreshed after failure.
        if (!sectors)
            return NvmeReadStatus::unavailable;
        if (sectors != block_sectors)
            fail("block extent changed");
        if (lba >= sectors)
            return NvmeReadStatus::out_of_range;
        const auto result = nvme_read_sector(context, lba, output);
        if (!space.closed() || root() != running.space->root())
            fail("block window restoration");
        return result;
    }
};
class ProcessBlocksBroker final {
    static auto context(unsigned slot) -> NvmeVolumeContext {
        const auto &grant = volume_grants[slot];
        return NvmeVolumeContext(volumes_root, grant.generation, grant.controller, grant.nsid, grant.sectors);
    }
    static auto authenticate() -> bool {
        if (!running.space || !running.service || running.service != volumes_service || !running.volumes_generation ||
            running.volumes_generation != volumes_generation || running.volumes_count != volumes_count ||
            !volumes_count || volumes_count > 2 || running.space->owner() != volumes_owner ||
            running.space->root() != volumes_root || root() != volumes_root || !space.closed())
            fail("volume set authority");
        U64 flags;
        asm volatile("pushfq; popq %0" : "=r"(flags));
        if (flags & (1ULL << 9))
            fail("volume set interrupt state");
        bool available = true;
        for (unsigned i = 0; i < volumes_count; ++i) {
            const auto &grant = volume_grants[i];
            if (!grant.generation || !grant.controller || !grant.nsid || !grant.sectors)
                fail("volume slot authority");
            const auto count = nvme_volume_count(context(i));
            if (count && count != grant.sectors)
                fail("volume extent changed");
            available = available && count != 0;
        }
        return available;
    }

public:
    static auto descriptor(U64 selector) -> U64 {
        if (!authenticate() || selector > 5)
            return 0;
        if (!selector)
            return volumes_count;
        if (selector == 1)
            return nvme_volume_budget(context(0));
        const auto slot = static_cast<unsigned>((selector - 2) / 2);
        if (slot >= volumes_count)
            return 0;
        return selector % 2 ? volume_grants[slot].generation : volume_grants[slot].sectors;
    }
    static auto read(U64 slot, U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
        for (auto &byte : output)
            byte = std::byte{};
        if (!authenticate() || slot >= volumes_count)
            return NvmeReadStatus::unavailable;
        const auto result = nvme_volume_read(context(static_cast<unsigned>(slot)), lba, output);
        if (!space.closed() || root() != volumes_root)
            fail("volume window restoration");
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
        const NvmeMountedContext admitted(mounted_root, mounted_generation);
        const auto sectors = nvme_mounted_sector_count(admitted);
        if (sectors && sectors != mounted_sectors)
            fail("mounted extent changed");
        return admitted;
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
        const auto admitted = context();
        const auto result = nvme_mounted_read(admitted, lba, output);
        restored();
#ifdef AURORA_PROCESS_FIXTURE
        // A real completed post-Flush read, with only its returned copy changed.
        // The physical disk, transport completion and cache remain untouched.
        if (mounted_confirmation_probe && !mounted_confirmation_corrupted && result == NvmeReadStatus::success &&
            nvme_mounted_committed(admitted) && nvme_mounted_admitted_flushes() == 5) {
            output[0] ^= std::byte{1};
            mounted_confirmation_corrupted = true;
            Serial::text("AURORA_MOUNTED_CONFIRM_CORRUPTED:");
            field("lba", lba);
            Serial::text(" returned_copy=1\r\n");
        }
#endif
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
        const NvmeRecoveryContext admitted(recovery_root, recovery_generation);
        const auto sectors = nvme_recovery_sector_count(admitted);
        if (sectors && sectors != recovery_sectors)
            fail("recovery extent changed");
        return admitted;
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

auto volumes_call(volatile U64 *frame) -> bool {
    if (frame[frame_rdx] != running.volumes_generation || (running.volumes_generation && !running.service))
        return false;
    if (frame[frame_rax] == 24) {
        if (frame[frame_rdi] || frame[frame_r10])
            return false;
        U64 value = 0;
#ifdef AURORA_UEFI_NVME
        if (running.volumes_generation)
            value = aurora::uefi::ProcessBlocksBroker::descriptor(frame[frame_rsi]);
#endif
        frame[frame_rax] = value;
        frame[frame_rdx] = 0;
        return true;
    }
    const auto destination = user_bytes(frame[frame_rdi], block_copy.size(), true);
    if (!destination)
        return false;
    for (auto &byte : block_copy)
        byte = std::byte{};
    U64 status = 3;
#ifdef AURORA_UEFI_NVME
    if (running.volumes_generation)
        status =
            static_cast<U64>(aurora::uefi::ProcessBlocksBroker::read(frame[frame_r10], frame[frame_rsi], block_copy));
#endif
    for (U64 at = 0; at < block_copy.size(); ++at) {
        (*destination)[at] = status ? std::byte{} : block_copy[at];
        block_copy[at] = std::byte{};
    }
    frame[frame_rax] = status;
    frame[frame_rdx] = status == 0 ? 512 : 0;
    return true;
}

auto endpoint_exchange(volatile U64 *frame) -> bool {
    const U64 window = frame[frame_rdi], count = frame[frame_rsi], generation = frame[frame_rdx],
              transaction = frame[frame_r10];
    if (!running.service || generation != running.service || generation != endpoint.generation ||
        count > Endpoint::capacity || (endpoint.window && endpoint.window != window))
        return false;
    const auto bytes = user_bytes(window, Endpoint::window_bytes, true);
    if (!bytes)
        return false;
    aurora::endpoint::Exchange admitted;
    {
        EndpointTrapScope scope;
        admitted = endpoint_owner.accept_exchange(generation, transaction, count);
    }
    if (admitted == aurora::endpoint::Exchange::refused)
        return false;
    if (admitted == aurora::endpoint::Exchange::reply) {
        for (U64 at = 0; at < count; ++at)
            endpoint.bytes[at] = (*bytes)[Endpoint::reply_offset + at];
        endpoint.count = count;
    }
    endpoint.window = window;
    execution_capture.event = aurora::lifecycle::Event::exchange;
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
    if (endpoint.caller || !endpoint.generation)
        return false;
    const U64 operation = action == Action::open_directory  ? 16
                          : action == Action::open_beneath  ? 17
                          : action == Action::open_file     ? 18
                          : action == Action::read          ? 19
                          : action == Action::close         ? 20
                          : action == Action::create_output ? 21
                          : action == Action::write         ? 22
                          : action == Action::commit        ? 23
                          : action == Action::next_entry    ? 25
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
    } else if (action == Action::next_entry) {
        if (!user_bytes(call.base, 256, true) || !user_bytes(call.record, 48, true) ||
            (call.base < call.record + 48 && call.record < call.base + 256))
            return false;
    } else if (action == Action::read) {
        if (!user_bytes(call.base, process::file_chunk, true))
            return false;
    } else if (action == Action::write) {
        source = user_bytes(call.base, call.length, false);
        if (!source)
            return false;
        length = call.length < Endpoint::capacity - 64 ? call.length : Endpoint::capacity - 64;
    }
    {
        EndpointTrapScope scope;
        if (!endpoint_owner.stage_client(running.run))
            return false;
    }
    message_header(operation, call.value, action == Action::read ? call.length : 0, length);
    for (U64 at = 0; at < length; ++at)
        endpoint.bytes[64 + at] = (*source)[at];
    endpoint.call = call;
    endpoint.written = length;
    endpoint.caller = running_client_slot();
    endpoint.caller_cancelled = false;
    execution_capture.event = aurora::lifecycle::Event::request;
    save_frame(frame);
    return true;
}

// One kernel call: 0 resumes the process with RAX set, 1 ends it.
auto kernel_call(volatile U64 *frame) -> U64 {
    if (frame[frame_rax] == 23 || frame[frame_rax] == 24) {
        const auto operation = frame[frame_rax];
        if (volumes_call(frame))
            return 0;
        execution_capture.event = aurora::lifecycle::Event::invalid_call;
        execution_capture.detail = operation;
        execution_capture.rip = frame[frame_rip];
        return 1;
    }
    if (frame[frame_rax] == 21) {
        if (running.external && !running.service && input_read.owner == running.run && input_read.owner &&
            frame[frame_rsi] == input_read.owner && !frame[frame_rdx] && !frame[frame_r10] && !input_read.pending &&
            input_read.sequence != UINT64_MAX && running.continuation && user_bytes(frame[frame_rdi], 520, true)) {
            input_read.address = frame[frame_rdi];
            input_read.epoch = running.space->epoch();
            input_read.root = running.space->root();
            input_read.generation = execution_owner.canonical(1, aurora::lifecycle::Field::generation);
            input_read.frame = *running.captured;
            input_read.pending = true;
            ++input_read.sequence;
            execution_capture.event = aurora::lifecycle::Event::input;
            save_frame(frame);
            return 1;
        }
        execution_capture.event = aurora::lifecycle::Event::invalid_call;
        execution_capture.detail = 21;
        execution_capture.rip = frame[frame_rip];
        return 1;
    }
    if (frame[frame_rax] >= 17 && frame[frame_rax] <= 20) {
        const auto operation = frame[frame_rax];
        if (mounted_call(frame) || recovery_call(frame)) {
#ifdef AURORA_PROCESS_FIXTURE
            if (mounted_owner_termination) {
                mounted_owner_termination = false;
                execution_capture.event = aurora::lifecycle::Event::exited;
                execution_capture.detail = 1;
                return 1;
            }
#endif
            return 0;
        }
        execution_capture.event = aurora::lifecycle::Event::invalid_call;
        execution_capture.detail = operation;
        execution_capture.rip = frame[frame_rip];
        return 1;
    }
    if (frame[frame_rax] == 16) {
        if (block_read(frame))
            return 0;
        execution_capture.event = aurora::lifecycle::Event::invalid_call;
        execution_capture.detail = 16;
        execution_capture.rip = frame[frame_rip];
        return 1;
    }
    if (frame[frame_rax] == 15) {
        if (endpoint_exchange(frame))
            return 1;
        execution_capture.event = aurora::lifecycle::Event::invalid_call;
        execution_capture.detail = 15;
        execution_capture.rip = frame[frame_rip];
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
    if ((running.flags & 1) && running.calls++ == 0) {
        Serial::text("AURORA_PROCESS_KERNEL_FAULT_PROBE: vector=14\r\n");
        static_cast<void>(*reinterpret_cast<volatile U64 *>(KernelSpace::window_base + frames::page));
    }
    const auto action = static_cast<process::CallAction>(decoded->action);
    if (action == process::CallAction::exit) {
        execution_capture.event = aurora::lifecycle::Event::exited;
        execution_capture.detail = decoded->value;
        return 1;
    }
    if (action == process::CallAction::print && !running.service) {
        if (const auto bytes = user_bytes(decoded->base, decoded->length, false)) {
            if (output_sink && running.external && !running.service) {
                for (U64 at = 0; at < decoded->length; ++at)
                    endpoint.bytes[at] = (*bytes)[at];
                endpoint.count = decoded->length;
                output_error_stream = decoded->value == 2;
                execution_capture.event = aurora::lifecycle::Event::output;
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
    execution_capture.event = aurora::lifecycle::Event::invalid_call;
    execution_capture.detail = frame[frame_rax];
    execution_capture.rip = frame[frame_rip];
    return 1;
}
} // namespace

// The assembly gate separates saved-CS origins before selecting a dispatcher.
// Kernel-origin faults and the bounded timer drain stay on the suspended
// supervisor domain; they never traverse the CPL3 process policy closure.
auto kernel_dispatch(U64, U64, U64, U64, U64, U64) -> U64 asm("uefi_process_kernel_exception_dispatch")
    __attribute__((visibility("hidden")));
auto kernel_dispatch(U64 vector, U64 error, U64 rip, U64 cs, U64 frame, U64) -> U64 {
    if (cs != 8)
        kernel_fault(vector, error, rip, cs);
    if (vector == Timer::vector && input_wait.active) {
        if (error || !Timer::irq_off() || root() != kernel_root || running.space || draining || input_wait.expired ||
            !input_wait.armed || input_wait.owner != input_read.owner || input_wait.sequence != input_read.sequence ||
            !input_read.pending || !aurora::uefi::ConsoleWakeContext::frame_valid(frame, owned_arena))
            kernel_fault(vector, error, rip, cs);
        std::array<U64, aurora::uefi::ConsoleWakeContext::word_count> words{};
        const auto *captured = reinterpret_cast<const volatile U64 *>(frame);
        for (std::size_t i = 0; i < words.size(); ++i)
            words[i] = captured[i];
        if (rip != words[17] ||
            !aurora::uefi::ConsoleWakeContext::valid(words,
                                                     frame,
                                                     owned_arena,
                                                     reinterpret_cast<U64>(&input_wait_begin),
                                                     reinterpret_cast<U64>(&input_wait_end),
                                                     input_wait.stack) ||
            !Timer::acknowledge())
            kernel_fault(vector, error, rip, cs);
        input_wait.expired = true; // Main settlement alone subtracts allowance.
        return 0;
    }
    const auto begin = reinterpret_cast<U64>(&drain_begin), end = reinterpret_cast<U64>(&drain_end);
    if (vector == 64 && cs == 8 && draining && rip >= begin && rip <= end && root() == kernel_root &&
        frame >= owned_arena + Handoff::stack_bottom && frame < owned_arena + Handoff::stack_top) {
        if (!Timer::acknowledge())
            kernel_fault(vector, error, rip, cs);
        draining = false;
        return 0;
    }
    kernel_fault(vector, error, rip, cs);
}

// CPL3 frames arrive only on the exact TSS.RSP0 frame under their admitted root.
auto dispatch(U64, U64, U64, U64, U64, U64) -> U64 asm("uefi_process_exception_dispatch")
    __attribute__((visibility("hidden")));
auto dispatch(U64 vector, U64 error, U64 rip, U64 cs, U64 frame, U64) -> U64 {
    if (!execution_owner.busy() || !running.space || !running.captured || cs != 0x1b ||
        frame != owned_arena + BootstrapLayout::rsp0_top - frame_words * 8 || root() != running.space->root())
        kernel_fault(vector, error, rip, cs);
    auto *words = reinterpret_cast<volatile U64 *>(frame);
    // Full authenticated trap capture is distinct from the tightly bounded
    // stopped-return writes and from writes to an actively executing syscall.
    for (std::size_t word = 0; word < frame_words; ++word)
        (*running.captured)[word] = words[word];
#ifdef AURORA_PROCESS_FIXTURE
    if (nested_fault_probe) {
        Serial::text("AURORA_PROCESS_NESTED_FAULT_PROBE\r\n");
        asm volatile("ud2");
    }
#endif
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
    const auto committed =
        *kind == process::TrapClass::page_fault ? running.space->fault(trap.cr2, error) : ProcessSpace::Fault::refused;
    if (committed == ProcessSpace::Fault::broken)
        fail("Aurora memory fault decision");
    if (committed == ProcessSpace::Fault::admitted) {
#ifdef AURORA_PROCESS_FIXTURE
        if (frame_finish_fault) {
            Serial::text("AURORA_FRAME_REQUIRE_PROBE: context=process");
            field("root", root());
            field("kernel", kernel_root);
            Serial::text("\r\n");
            table.admit_finish();
            fail("frame consume guard returned");
        }
#endif
        if (!running.space->commit(trap.cr2))
            fail("memory commit");
        if ((running.flags & 4) && !running.space->verify())
            fail("memory walk");
        ++running.commits;
        return 0;
    }
    execution_capture.event = aurora::lifecycle::Event::fault;
    execution_capture.detail = vector;
    execution_capture.trap = *kind;
    execution_capture.vector = vector;
    execution_capture.error = error;
    execution_capture.rip = trap.rip;
    execution_capture.cr2 = trap.cr2;
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
               after_leaf = process_space.entry(block + frames::page, 1), slot = process_space.entry(shared.slot[0], 2),
               code_parent = process_space.entry(code, 2);
    if (!code_leaf || !block_leaf || !after_leaf || !slot || !code_parent)
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
    const auto code_word = value(*code_leaf), block_word = value(*block_leaf), slot_word = value(*slot),
               parent_word = value(*code_parent);
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
    const U64 physical_bits = a & 255;
    if (physical_bits < 36 || physical_bits > 52)
        fail("walk probe physical width");
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
        {*code_leaf, code_word, code_word | (U64{1} << 8)},       // global user mapping
        {*code_leaf, code_word, code_word | (U64{1} << 62)},      // reserved flag
        {*code_parent, parent_word, parent_word | (U64{1} << 7)}, // huge-page bit
        {*code_leaf, code_word, code_word | (U64{1} << physical_bits)},
        {*code_leaf, code_word, 0}, // missing owned leaf
        {*code_leaf, code_word, (parent_word & KernelSpace::address_mask) | (code_word & ~KernelSpace::address_mask)},
        {*code_parent,
         parent_word,
         (code_word & KernelSpace::address_mask) | (parent_word & ~KernelSpace::address_mask)},
    };
    U64 rejected = 0;
    for (const auto &edit : edits) {
        set(edit.at, edit.after);
        rejected += !process_space.verify();
        set(edit.at, edit.before);
    }
    if (rejected != std::size(edits) || !process_space.verify())
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

// The existing pure parser returns bounded copied layout facts only. This
// local manifest remains bound to its immutable boot input or snapshot epoch;
// physical copying authenticates that source again after the parser pin ends.
class ImageManifest final {
public:
    std::array<process::ProcessRegion, ProcessSpace::max_regions> regions{};
    std::optional<process::ElfVerdict> elf;
    std::optional<process::LayoutVerdict> layout;
    U64 count = 0, entry = 0, charge = 0, snapshot_epoch = 0;
    bool complete = false, input_requested = false;
};
auto parse_image_manifest(std::span<const std::byte> image, U64 argument_bytes, U64 snapshot_epoch) -> ImageManifest {
    ImageManifest result;
    result.snapshot_epoch = snapshot_epoch;
    result.elf = process::elf_admit(image);
    if (result.elf != process::ElfVerdict::valid)
        return result;
    result.layout = process::layout(image, shared.reserved_first, shared.reserved_end, argument_bytes);
    if (result.layout != process::LayoutVerdict::valid)
        return result;
    for (;;) {
        const auto region = process::region(image, result.count, argument_bytes);
        if (!region)
            return result;
        if (static_cast<process::RegionKind>(region->kind) == process::RegionKind::none)
            break;
        if (result.count == result.regions.size())
            return result;
        result.regions[result.count++] = *region;
    }
    result.entry = process::elf_entry(image);
    result.input_requested = process::elf_input(image);
    result.charge = process::memory_load_charge(image, argument_bytes, shared.slots);
    result.complete = result.count != 0 && result.charge != 0;
    return result;
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
                bool grant_mounted = false,
                U64 snapshot_epoch = 0) -> bool {
    if (execution_owner.entered())
        fail("execution lifecycle reentry");
    auto &resident = residents[slot];
    if (resident.space || execution_owner.phase(slot) != aurora::lifecycle::Phase::empty)
        fail("resident slot already owned");
    // A known source incarnation refusal precedes physical allocation; it may
    // not be discovered only after a loaded address space becomes visible.
    if (!execution_owner.can_prepare(slot)) {
        refuse(run, "execution generation exhausted");
        return false;
    }
    static_cast<void>(view);
    ImageManifest manifest;
    if (snapshot_epoch) {
        if (!source.empty() || !snapshot || snapshot->epoch() != snapshot_epoch)
            fail("loader snapshot identity");
        auto input = table.snapshot_read(snapshot_epoch);
        manifest = parse_image_manifest(input.bytes(), arguments.size(), snapshot_epoch);
    } else {
        auto input = table.boot_source(source);
        manifest = parse_image_manifest(source, arguments.size(), 0);
    }
    // All parser pins end before diagnostics or manager mutations.
    if (!manifest.elf)
        fail("Aurora ELF admission");
    if (*manifest.elf != process::ElfVerdict::valid) {
        refuse(run, name(elf_names, static_cast<U64>(*manifest.elf)));
        return false;
    }
    if (!manifest.layout)
        fail("Aurora process layout");
    if (*manifest.layout != process::LayoutVerdict::valid) {
        refuse(run, name(layout_names, static_cast<U64>(*manifest.layout)));
        return false;
    }
    if (!manifest.complete || manifest.snapshot_epoch != snapshot_epoch)
        fail("Aurora process manifest");
    if (manifest.input_requested && (!external || slot != 1 || service || grant_block || grant_mounted ||
                                     !preemptible || !input_source || input_read.owner)) {
        load_refusal = RunStatus::unavailable;
        return false; // Requesting an ABI never creates an input grant.
    }
    const U64 epoch = table.prepare_load(slot, frames::first_owner + run, entry.quota, manifest.charge);
    if (!epoch) {
        refuse(run, "quota");
        return false;
    }
    auto &process_space = resident.space.emplace(table, slot, epoch);
    U64 stack_top = 0, block = 0;
    for (U64 index = 0; index < manifest.count; ++index) {
        const auto &region = manifest.regions[index];
        const auto kind = static_cast<process::RegionKind>(region.kind);
        if (kind == process::RegionKind::stack)
            stack_top = region.first + region.pages * frames::page;
        if (kind == process::RegionKind::arguments)
            block = region.first;
        bool mapped = false;
        if (!region.bytes) {
            mapped = process_space.map(region, 0);
        } else if (kind == process::RegionKind::segment) {
            if (snapshot_epoch) {
                auto input = table.snapshot_source(snapshot_epoch);
                mapped = process_space.map(region, 1);
            } else {
                auto input = table.boot_source(source);
                mapped = process_space.map(region, 1);
            }
        } else if (kind == process::RegionKind::arguments) {
            auto input = table.arguments_source(arguments);
            mapped = process_space.map(region, 2);
        }
        if (!mapped)
            fail("process mapping");
    }
    const U64 entry_point = manifest.entry, regions = manifest.count;
    if (snapshot_epoch) {
        if (!snapshot || snapshot->epoch() != snapshot_epoch || snapshot->owner() != process_space.owner() ||
            !snapshot->release())
            fail("loader snapshot release");
        snapshot.reset();
    }
    if (!process_space.finish_load() || !stack_top || !block || !process_space.executable(entry_point, 1) ||
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
    field("quota", process_space.quota() - process_space.charged());
    if (preemptible) {
        field("owner", process_space.owner());
        field("root", process_space.root());
    }
    Serial::text("\r\n");
    // Initial entry and retained continuation are both kernel-owned. A slot
    // identity is never user-provided; owners advance with the run ordinal.
    U64 read_generation = 0, read_sectors = 0, write_generation = 0, write_sectors = 0;
    U64 set_generation = 0, set_count = 0;
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
    if (grant_block && service && runtime_storage.dual() && aurora::uefi::nvme_volume_count()) {
        if (volumes_generation || read_generation || next_block_generation > ~U64{0} - 3)
            fail("volume set admission");
        set_count = aurora::uefi::nvme_volume_count();
        set_generation = ++next_block_generation;
        volumes_service = service;
        volumes_owner = process_space.owner();
        volumes_root = process_space.root();
        volumes_generation = set_generation;
        volumes_count = set_count;
        for (unsigned i = 0; i < set_count; ++i) {
            volume_grants[i] = {++next_block_generation,
                                aurora::uefi::nvme_volume_identity(i, 0),
                                aurora::uefi::nvme_volume_identity(i, 1),
                                aurora::uefi::nvme_volume_identity(i, 2)};
        }
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
                        set_generation     ? set_generation
                        : write_generation ? write_generation
                                           : read_generation,
                        set_generation     ? set_count
                        : write_generation ? write_sectors
                                           : read_sectors};
    if (manifest.input_requested) {
        input_read.owner = run;
        // Conservative ownership handoff: even clean EOF/no read requires the
        // shell's source delimiter quarantine; native never parses that line.
        input_read.quarantine = true;
        U64 allowance = input_wait_allowance;
#ifdef AURORA_PROCESS_FIXTURE
        if (input_probe_case) {
            allowance = (input_probe_case == 83 ? 4 : 2) * input_poll_count;
            if (!allowance || allowance > input_wait_allowance)
                fail("input fixture allowance");
        }
#endif
        input_read.protocol = {allowance, 0, 0, input_read.protocol.after_cr};
        resident.initial[6] = run; // Independent opaque input token in R8.
    }
    if (!resident.budget.create(entry.ticks, (entry.flags & 8) ? 1 : 0))
        fail("resident budget admission");
    resident.state = {};
    resident.state.space = &process_space;
    resident.state.budget = &resident.budget;
    resident.state.run = run;
    resident.state.flags = entry.flags;
    resident.state.continuation = preemptible ? &resident.continuation : nullptr;
    resident.state.captured = &resident.continuation;
    resident.state.service = service;
    resident.state.volumes_generation = set_generation;
    resident.state.volumes_count = set_count;
    resident.state.block_generation = read_generation;
    resident.state.block_sectors = read_sectors;
    resident.state.mounted_generation = write_generation;
    resident.state.mounted_sectors = write_sectors;
    resident.state.external = external;
    resident.state.companion = companion;
    if (!audit_residents() || !execution_owner.prepare(slot))
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
    if (execution_owner.entered())
        fail("execution lifecycle reentry");
    auto &resident = residents[slot];
    if (resident.space || execution_owner.phase(slot) != aurora::lifecycle::Phase::empty)
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

auto service_shutdown_selected() -> bool;

auto release_resident_physical(std::size_t slot) -> bool {
    using namespace aurora::lifecycle;
    if (execution_owner.canonical(slot, Field::phase) != static_cast<U64>(Phase::retiring))
        fail("execution retirement phase");
    outcome = {};
    const auto terminal = static_cast<Event>(execution_owner.canonical(slot, Field::terminal));
    const auto detail = execution_owner.canonical(slot, Field::terminal_detail);
    outcome.exited = terminal == Event::exited;
    outcome.watchdog = terminal == Event::expired;
    outcome.invalid_call = terminal == Event::invalid_call || terminal == Event::output_failed;
    outcome.cancelled = terminal == Event::cancelled;
    outcome.unavailable = terminal == Event::unavailable;
    outcome.status = detail;
    outcome.operation = detail;
    // Forced client cleanup must not consume the still-pending server's raw
    // trap observation. Only that server's natural retirement projects it.
    if (execution_owner.canonical(slot, Field::event) != static_cast<U64>(Event::forced)) {
        outcome.trap = execution_capture.trap;
        outcome.vector = execution_capture.vector;
        outcome.error = execution_capture.error;
        outcome.rip = execution_capture.rip;
        outcome.cr2 = execution_capture.cr2;
    }
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
    bool sealed_writer = false, sealed_mounted = false;
#ifdef AURORA_UEFI_NVME
    if (mounted_writer) {
        if (!resident.state.service || resident.state.service != mounted_service ||
            resident.state.mounted_generation != mounted_generation ||
            resident.state.mounted_sectors != mounted_sectors || process_space.owner() != mounted_owner ||
            process_space.root() != mounted_root || root() != kernel_root || !space.closed())
            fail("mounted retirement authority");
        const bool success = terminal == Event::exited && detail == 0 && service_shutdown_selected() &&
                             execution_owner.canonical(slot, Field::event) != static_cast<U64>(Event::forced);
        sealed_mounted = success && aurora::uefi::nvme_mounted_committed() && aurora::uefi::nvme_mounted_seal();
        if (!sealed_mounted)
            aurora::uefi::nvme_mounted_abandon();
    }
    if (writer) {
        if (resident.state.service || resident.state.recovery_generation != recovery_generation ||
            resident.state.recovery_sectors != recovery_sectors || process_space.owner() != recovery_owner ||
            process_space.root() != recovery_root || root() != kernel_root || !space.closed())
            fail("recovery retirement authority");
        const bool success = terminal == Event::exited && detail == 0;
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
    if (resident.state.service && resident.state.service == volumes_service)
        revoke_volumes();
    if (resident.state.service && resident.state.service == block_service)
        block_service = block_generation = block_sectors = 0;
    // The role remains visible throughout real address-space release and
    // continuation scrubbing. It is not cleared to bypass failure cleanup.
    const auto retired_generation = resident.state.recovery_generation;
    if (writer)
        recovery_owner = recovery_root = recovery_generation = recovery_sectors = 0;
    const auto retired_mounted_generation = resident.state.mounted_generation;
    if (mounted_writer)
        mounted_owner = mounted_root = mounted_generation = mounted_sectors = mounted_service = 0;
    resident.budget.stop();
    running.budget = nullptr;
    resident.state = {};
#ifdef AURORA_UEFI_NVME
    if (mounted_writer) {
        const bool readonly = sealed_mounted && aurora::uefi::nvme_mounted_retired();
        if (!readonly)
            aurora::uefi::nvme_mounted_abandon();
        Serial::text("AURORA_MOUNTED_RETIRED:");
        field("generation", retired_mounted_generation);
        field("writes", aurora::uefi::nvme_mounted_admitted_writes());
        field("flushes", aurora::uefi::nvme_mounted_admitted_flushes());
        Serial::text(readonly ? std::string_view{" disk=readonly\r\n"} : std::string_view{" disk=unavailable\r\n"});
    }
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
    static_cast<void>(sealed_mounted);
    static_cast<void>(retired_mounted_generation);
    static_cast<void>(sealed_writer);
    static_cast<void>(retired_generation);
#endif
    return true;
}

auto authenticate_stopped_frame(std::size_t slot, bool syscall) -> void {
    const auto &resident = residents[slot];
    const auto &frame = resident.continuation;
    if (resident.state.captured != &resident.continuation || !resident.state.continuation)
        fail("stopped frame identity");
    const process::ProcessTrap trap{
        frame[15], frame[16], frame[17], frame[18], frame[19], frame[20], frame[21], 0, 0x10000};
    const auto kind = process::trap(trap);
    if (!kind || (syscall ? *kind != process::TrapClass::call
                          : (*kind != process::TrapClass::call && *kind != process::TrapClass::timer)))
        fail("stopped frame admission");
}

// Copies run only while the supervisor owns execution. The selected root is
// already fully admitted and is restored before any other process can enter.
auto complete_resident_physical(std::size_t slot) -> void {
    using namespace aurora::lifecycle;
    const auto pending = static_cast<Event>(execution_owner.canonical(slot, Field::pending));
    authenticate_stopped_frame(slot, true);
    auto &resident = residents[slot];
    if (pending == Event::input) {
        if (slot != 1 || !input_read.pending || !input_read.completing || input_read.owner != resident.state.run ||
            input_read.epoch != resident.space->epoch() || input_read.root != resident.space->root() ||
            !input_frame_equal(input_read.frame, resident.continuation) ||
            input_read.generation != execution_owner.canonical(slot, Field::generation))
            fail("input completion identity");
        running = resident.state;
        const U64 admitted_root = table.activation_root(slot, running.space->epoch());
        asm volatile("mov %0, %%cr3" : : "r"(admitted_root) : "memory");
        const auto destination = user_bytes(input_read.address, 520, true);
        if (!destination)
            fail("input parked destination");
        const U64 count = input_read.protocol.count;
        const U64 status = count ? 0 : input_read.protocol.status;
        if (count > 504 || status > 3 || (!count && !status))
            fail("input source completion");
        for (U64 at = 0; at < 520; ++at)
            (*destination)[at] = std::byte{0};
        store(input_read.address, status, 8);
        store(input_read.address + 8, count, 8);
        for (U64 at = 0; at < count; ++at)
            (*destination)[16 + at] = input_read.bytes[at];
        asm volatile("mov %0, %%cr3" : : "r"(kernel_root) : "memory");
        running.space = nullptr;
        resident.continuation[frame_rax] = 0;
#ifdef AURORA_PROCESS_FIXTURE
        if (input_probe_case) {
            ++input_probe_completions;
            Serial::text("AURORA_INPUT_CHUNK:");
            field("case", input_probe_case);
            field("sequence", input_read.sequence);
            field("status", status);
            field("count", count);
            field("remaining", input_read.protocol.remaining);
            Serial::text(" copied=1\r\n");
        }
#endif
        input_read.protocol = process::input_update(input_read.protocol, 3);
        input_read.bytes = {};
        input_read.pending = false;
        return;
    }
    if (pending == Event::output) {
        if (!slot || slot >= residents.size() || !completed_output || !*completed_output || endpoint.caller ||
            resident.continuation[frame_rax] != 2 || resident.continuation[frame_rdx] != endpoint.count ||
            (resident.continuation[frame_rdi] == 2) != output_error_stream)
            fail("output completion evidence");
        resident.continuation[frame_rax] = 0;
        return;
    }
    const auto endpoint_observation = endpoint_owner.observe();
    if ((pending != Event::exchange || !resident.state.service || !endpoint_observation.delivery() ||
         !endpoint_observation.waiting() || endpoint.generation != resident.state.service) &&
        (pending != Event::request || !slot || slot >= residents.size() || !endpoint_observation.completion() ||
         endpoint.caller || endpoint_observation.source != resident.state.run))
        fail("stopped completion evidence");
    if (pending == Event::exchange) {
        if (resident.continuation[frame_rax] != 15 || resident.continuation[frame_rdi] != endpoint.window ||
            resident.continuation[frame_rdx] != resident.state.service || endpoint.count > Endpoint::capacity)
            fail("service delivery stopped frame");
    } else {
        const auto &frame = resident.continuation;
        const auto call =
            process::call(frame[frame_rax], frame[frame_rdi], frame[frame_rsi], frame[frame_rdx], frame[frame_r10]);
        if (!call || call->action != endpoint.call.action || call->value != endpoint.call.value ||
            call->length != endpoint.call.length || call->base != endpoint.call.base ||
            call->record != endpoint.call.record)
            fail("client completion stopped frame");
    }
    running = resident.state;
    const U64 admitted_root = table.activation_root(slot, running.space->epoch());
    asm volatile("mov %0, %%cr3" : : "r"(admitted_root) : "memory");
    if (pending == Event::exchange) {
        const auto target = user_bytes(endpoint.window, Endpoint::window_bytes, true);
        if (!target)
            fail("endpoint window changed while parked");
        for (U64 at = 0; at < 64; ++at)
            (*target)[at] = std::byte{0};
        store(endpoint.window, endpoint.count, 8);
        store(endpoint.window + 8, endpoint_observation.source, 8);
        store(endpoint.window + 16, endpoint_observation.transaction, 8);
        store(endpoint.window + 24, 1, 8);
        for (U64 at = 0; at < endpoint.count; ++at)
            (*target)[Endpoint::request_offset + at] = endpoint.bytes[at];
        residents[slot].continuation[frame_rax] = 0;
        residents[slot].continuation[frame_rdx] = endpoint.count;

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
        if (action == process::CallAction::next_entry) {
            const auto target = user_bytes(endpoint.call.base, 256, true);
            if (!target)
                fail("parked directory destination");
            for (U64 at = 0; at < 256; ++at)
                (*target)[at] = !status && at < count ? endpoint.bytes[64 + at] : std::byte{0};
        }
        if (endpoint.call.record) {
            if (!user_bytes(endpoint.call.record, 48, true))
                fail("parked file result");
            for (U64 word = 0; word < 6; ++word)
                store(endpoint.call.record + word * 8, reply.get(16 + word * 8), 8);
        }
        residents[slot].continuation[frame_rax] = status ? 0 - status : count;
    }
    asm volatile("mov %0, %%cr3" : : "r"(kernel_root) : "memory");
    running.space = nullptr;
    const bool acknowledged = pending == Event::exchange
                                  ? endpoint_owner.delivered(endpoint.generation, endpoint_observation.transaction)
                                  : endpoint_owner.complete_client(resident.state.run);
    if (!acknowledged)
        fail("endpoint physical completion acknowledgement");
}

// One entry or resumption. A timer park returns to this kernel loop before
// another process can enter, preserving the single saved kernel continuation.
auto activate_resident_physical(std::size_t slot) -> void {
#ifdef AURORA_PROCESS_FIXTURE
    if (mounted_prepared_refusal)
        fail("mounted prepared refusal entered user");
#endif
    using namespace aurora::lifecycle;
    const bool resume = execution_owner.canonical(slot, Field::mode) == 1;
    auto &resident = residents[slot];
    if (!resident.space || !resident.budget.available() || running.space || root() != kernel_root)
        fail("resident activation");
    running = resident.state;
    execution_capture = {};
    arm_slice();
    if (resume && !resident.state.external) {
        Serial::text("AURORA_PROCESS_RESUMED:");
        field("run", resident.state.run);
        field("ticks", resident.budget.used());
        Serial::text("\r\n");
    }
    const U64 admitted_root = table.activation_root(slot, resident.space->epoch());
    if (resident.initial[4] != admitted_root)
        fail("resident root generation");
    const auto result =
        resume ? process_resume(resident.continuation.data(), admitted_root) : process_enter(resident.initial.data());
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
    resident.state = running;
    running.space = nullptr;
    if (Timer::pending()) {
        draining = true;
        process_drain();
    }
    if (draining || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        fail("timer drain");
}

auto execution_incarnation(std::size_t slot) -> U64 {
    const auto &resident = residents[slot];
    return slot != 0 ? (resident.state.external ? endpoint.generation : 0) : resident.state.service;
}
auto authenticate_execution(std::size_t slot, aurora::lifecycle::Phase phase) -> void {
    using namespace aurora::lifecycle;
    if (slot >= residents.size() || !execution_owner.busy() ||
        execution_owner.canonical(slot, Field::phase) != static_cast<U64>(phase))
        fail("execution canonical phase");
    const auto &resident = residents[slot];
    if (!resident.space || !execution_owner.canonical(slot, Field::generation) ||
        execution_owner.canonical(slot, Field::epoch) != resident.space->epoch() ||
        execution_owner.canonical(slot, Field::root) != resident.space->root() ||
        execution_owner.canonical(slot, Field::incarnation) != execution_incarnation(slot) ||
        execution_owner.canonical(slot, Field::initial) != reinterpret_cast<U64>(resident.initial.data()) ||
        execution_owner.canonical(slot, Field::saved) != reinterpret_cast<U64>(resident.continuation.data()) ||
        resident.state.space != &*resident.space || resident.state.budget != &resident.budget ||
        resident.state.captured != &resident.continuation ||
        (resident.state.continuation && resident.state.continuation != &resident.continuation) ||
        resident.state.run > 0xffffffffULL - frames::first_owner ||
        resident.space->owner() != frames::first_owner + resident.state.run ||
        resident.initial[4] != table.activation_root(slot, resident.space->epoch()))
        fail("execution physical identity");
}
auto LifecyclePlatform::authenticate_presentation(U64 slot, aurora::lifecycle::Phase phase) -> void {
    using namespace aurora::lifecycle;
    if (!slot || slot >= residents.size() ||
        execution_owner.canonical(0, Field::phase) != static_cast<U64>(Phase::parked) ||
        execution_owner.canonical(0, Field::pending) != static_cast<U64>(Event::exchange))
        ::fail("presentation service source identity");
    authenticate_execution(0, Phase::parked);
    authenticate_stopped_frame(0, true);
    authenticate_execution(slot, phase);
    authenticate_stopped_frame(slot, true);
    const auto sibling = slot == 1 ? 2U : 1U;
    const auto sibling_phase = static_cast<Phase>(execution_owner.canonical(sibling, Field::phase));
    if (residents[sibling].space) {
        if (sibling_phase != Phase::prepared && sibling_phase != Phase::parked)
            ::fail("presentation sibling identity");
        authenticate_execution(sibling, sibling_phase);
        if (sibling_phase == Phase::parked)
            authenticate_stopped_frame(sibling, false);
    } else if (sibling_phase != Phase::empty) {
        ::fail("presentation empty sibling identity");
    }
}
auto authenticate_terminal_capture(std::size_t slot) -> void {
    using namespace aurora::lifecycle;
    const auto event = execution_owner.canonical(slot, Field::event);
    if (event == static_cast<U64>(Event::forced))
        return;
    if (event != static_cast<U64>(execution_capture.event) ||
        execution_owner.canonical(slot, Field::detail) != execution_capture.detail ||
        execution_owner.canonical(slot, Field::exhausted) != execution_capture.exhausted)
        fail("terminal physical capture changed");
}
auto execution_observation(std::size_t slot, aurora::lifecycle::Event event, U64 detail = 0, bool exhausted = false)
    -> aurora::lifecycle::Observation {
    const auto &resident = residents[slot];
    return {static_cast<U64>(event),
            detail,
            exhausted,
            resident.space->epoch(),
            resident.space->root(),
            execution_incarnation(slot),
            reinterpret_cast<U64>(resident.initial.data()),
            reinterpret_cast<U64>(resident.continuation.data())};
}
auto observe_forced_execution(std::size_t slot) -> aurora::lifecycle::Observation {
    using namespace aurora::lifecycle;
    const auto phase = static_cast<Phase>(execution_owner.canonical(slot, Field::phase));
    if (phase != Phase::prepared && phase != Phase::parked)
        fail("forced execution phase");
    authenticate_execution(slot, phase);
    if (phase == Phase::parked)
        authenticate_stopped_frame(slot, false);
    // Preserve the last activated slot's physical capture across a source-
    // ordered client retirement. Forced observations never overwrite it.
    // These bits capture independent physical facts, not an ordered terminal
    // decision: failed output, explicit intent, earlier expiry, cancellation,
    // service loss. Only source normalizes their precedence and final detail.
    U64 facts = endpoint.caller_cancelled ? 8 : 0;
    const auto service_phase = service_root.phase();
    if (service_phase == aurora::service::Phase::retiring) {
        if (forced_execution || snapshot || endpoint.caller || endpoint_owner.observe().completion() || loading_image ||
            (residents[slot].state.service && residents[slot].state.service != service_root.generation()))
            fail("service loss physical boundary");
        return execution_observation(slot, Event::forced, facts | 16);
    }
    if (!slot || slot >= residents.size() || service_phase != aurora::service::Phase::ready || !residents[0].space ||
        residents[0].state.service != endpoint.generation)
        fail("forced client physical boundary");
    if (forced_execution) {
        const auto &binding = *forced_execution;
        if (binding.slot != slot || !binding.client || binding.client != residents[slot].state.run ||
            !binding.service_generation || binding.service_generation != endpoint.generation ||
            binding.output_pending || binding.request_pending || binding.input_pending || binding.request_failed ||
            (binding.expiry_preceded_cancel && !binding.explicit_cancel_requested))
            fail("forced command binding");
        if (phase == Phase::prepared && (!binding.explicit_cancel_requested || binding.expiry_preceded_cancel ||
                                         binding.output_failed || execution_owner.canonical(slot, Field::pending)))
            fail("prepared cancellation evidence");
        if (binding.output_failed) {
            if (execution_owner.canonical(slot, Field::pending) != static_cast<U64>(Event::output) ||
                residents[slot].continuation[frame_rax] != 2 ||
                residents[slot].continuation[frame_rdx] != endpoint.count || endpoint.caller)
                fail("output failure stopped context");
        } else if (!endpoint.caller_cancelled || endpoint.caller || endpoint_owner.observe().completion()) {
            fail("cancelled command physical boundary");
        }
        facts |= binding.output_failed ? 1 : 0;
        facts |= binding.explicit_cancel_requested ? 2 : 0;
        facts |= binding.expiry_preceded_cancel ? 4 : 0;
    } else {
        // The nonproduction request loop has no command lease. Its real
        // endpoint cancellation is authenticated, never a supplied reason.
        if (phase != Phase::parked || !endpoint.caller_cancelled || endpoint.caller ||
            endpoint_owner.observe().completion() ||
            execution_owner.canonical(slot, Field::pending) != static_cast<U64>(Event::request))
            fail("expired endpoint physical boundary");
    }
    return execution_observation(slot, Event::forced, facts);
}

template <aurora::lifecycle::EffectKind kind>
auto execution_authority_observe(
    const void *binding, U64 epoch, const void *field, aurora::lifecycle::Observation *output, U64 slot) -> void {
    using namespace aurora::lifecycle;
#ifdef AURORA_PROCESS_FIXTURE
    if (kind == EffectKind::prepare && execution_probe_case >= 64 && execution_probe_case <= 67) {
        const U64 probe = execution_probe_case;
        execution_probe_case = 0;
        execution_probe_marker(probe, slot);
        if (probe == 64)
            field = reinterpret_cast<const void *>(reinterpret_cast<U64>(field) + 8);
        else if (probe == 65)
            binding = reinterpret_cast<const void *>(reinterpret_cast<U64>(binding) + 8);
        else if (probe == 66)
            slot ^= 1;
        else
            ++epoch;
    }
#endif
    execution_owner.enter(binding, epoch, field, kind, slot);
    if (!output || slot >= residents.size())
        fail("execution observation destination");
    if constexpr (kind == EffectKind::prepare) {
        const auto &resident = residents[slot];
        if (execution_owner.canonical(slot, Field::phase) != static_cast<U64>(Phase::empty) || !resident.space ||
            !resident.state.run || resident.state.space != &*resident.space ||
            resident.state.captured != &resident.continuation ||
            (resident.state.continuation && resident.state.continuation != &resident.continuation) ||
            resident.state.budget != &resident.budget ||
            resident.initial[4] != table.activation_root(slot, resident.space->epoch()))
            fail("execution prepare identity");
        if (slot != 0 && resident.state.external) {
            const auto generation = endpoint.generation;
            const auto &server = residents[0];
            if (!generation || service_root.phase() != aurora::service::Phase::ready ||
                service_root.generation() != generation || !server.space || server.state.service != generation ||
                server.state.space != &*server.space ||
                server.initial[4] != table.activation_root(0, server.space->epoch()))
                fail("client service incarnation admission");
        }
        *output = execution_observation(slot, Event::prepared);
    } else if constexpr (kind == EffectKind::activate) {
#ifdef AURORA_PROCESS_FIXTURE
        if (execution_probe_case == 70) {
            execution_probe_case = 0;
            execution_probe_marker(70, slot);
            residents[slot].initial[4] ^= frames::page;
        }
#endif
        authenticate_execution(slot, Phase::executing);
        const U64 mode = execution_owner.canonical(slot, Field::mode);
        if (mode > 1 || execution_owner.canonical(slot, Field::pending) ||
            (mode && !residents[slot].state.continuation))
            fail("execution entry mode");
        if (mode)
            authenticate_stopped_frame(slot, false);
        activate_resident_physical(slot);
        *output =
            execution_observation(slot, execution_capture.event, execution_capture.detail, execution_capture.exhausted);
    } else if constexpr (kind == EffectKind::complete) {
        authenticate_execution(slot, Phase::parked);
#ifdef AURORA_PROCESS_FIXTURE
        if (execution_probe_case == 68) {
            execution_probe_case = 0;
            execution_probe_marker(68, slot);
            residents[slot].continuation[18] = 8;
        }
#endif
        complete_resident_physical(slot);
        *output = execution_observation(slot, Event::completed);
    } else if constexpr (kind == EffectKind::force) {
        *output = observe_forced_execution(slot);
    } else {
        fail("execution observation kind");
    }
    execution_owner.leave();
}

auto run_resident(std::size_t slot) -> bool {
    using namespace aurora::lifecycle;
    if (execution_owner.entered() || slot >= residents.size())
        fail("execution lifecycle reentry");
    const auto completion = endpoint_owner.completion();
    if ((residents[slot].state.service && completion == aurora::endpoint::Completion::service) ||
        (slot != 0 && completion == aurora::endpoint::Completion::client &&
         endpoint_owner.observe().source == residents[slot].state.run))
        if (!execution_owner.complete(slot))
            fail("execution completion refused");
    const auto result = execution_owner.execute(slot);
    const auto event = static_cast<Event>(result.event);
    const bool parked = (event >= Event::timer && event <= Event::output) || event == Event::input;
    const bool terminal =
        event == Event::exited || event == Event::invalid_call || event == Event::fault || event == Event::expired;
    if ((!parked && !terminal) || !result.generation || execution_owner.generation(slot) != result.generation)
        fail("execution activation report");
    // These source queries verify only report consistency; no native phase or
    // eligibility ledger is retained. Source already selected and cleaned up.
    const auto phase = execution_owner.phase(slot);
    if (terminal ? (residents[slot].space.has_value() || phase != Phase::empty)
                 : (!residents[slot].space || phase != Phase::parked))
        fail("execution report cleanup mismatch");
    if (terminal)
        return true;
    outcome = {};
    outcome.parked = true;
    outcome.exchange = event == Event::exchange;
    outcome.request = event == Event::request;
    outcome.output = event == Event::output;
    outcome.input = event == Event::input;
    if (!residents[slot].state.external) {
        Serial::text("AURORA_PROCESS_PARKED:");
        field("run", residents[slot].state.run);
        field("ticks", residents[slot].budget.used());
        Serial::text("\r\n");
    }
    return false;
}
auto force_resident(std::size_t slot) -> void {
    using aurora::lifecycle::Event;
    if (execution_owner.entered())
        fail("execution forced retirement reentry");
    const auto result = execution_owner.force(slot);
    if (result.event < static_cast<U64>(Event::output_failed) || result.event > static_cast<U64>(Event::unavailable) ||
        !result.generation || execution_owner.generation(slot) != result.generation || residents[slot].space ||
        execution_owner.phase(slot) != aurora::lifecycle::Phase::empty)
        fail("execution forced retirement refused");
}

// One bounded request/reply round trip. The service budget is per operation,
// not renewed by its own timer parks. Bootstrap and teardown use the same cap.
auto begin_exchange(U64 source) -> bool {
    if (!residents[0].space || endpoint.count > Endpoint::capacity || !endpoint_owner.begin(source))
        return false;
    if (!residents[0].state.budget->restart())
        fail("service budget restart");
    return true;
}
enum class ExchangeProgress {
    pending,
    replied,
    failed
};
// Source selects eligibility; native performs just one authenticated server entry.
// A terminal may already have invalidated the endpoint inside run_resident.
auto advance_exchange() -> ExchangeProgress {
    using Step = aurora::endpoint::Step;
    if (!residents[0].space || endpoint_owner.step() != Step::resume)
        return ExchangeProgress::failed;
    static_cast<void>(run_resident(0));
    const auto progress = endpoint_owner.observe_step(residents[0].space.has_value());
    return progress == Step::replied  ? ExchangeProgress::replied
           : progress == Step::resume ? ExchangeProgress::pending
                                      : ExchangeProgress::failed;
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
    if (!endpoint_owner.consume_control(endpoint_owner.observe().transaction))
        fail("endpoint control consumption");
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
    if (action == process::CallAction::next_entry)
        return process::directory_reply_valid(std::span<const std::byte>{endpoint.bytes.data(), endpoint.count});
    if (action == process::CallAction::read) {
        for (U64 at = 16; at < 64; ++at)
            if (endpoint.bytes[at] != std::byte{0})
                return false;
        return true;
    }
    const U64 id = reply.get(16), size = reply.get(24), device = reply.get(32), inode = reply.get(40),
              directory_device = reply.get(48), directory_inode = reply.get(56), slot = id & 63;
    if (count || id < 65 || size > 0x7fffffffffffffffULL || device > (runtime_storage.dual() ? 4U : 3U))
        return false;
    if (action == process::CallAction::create_output) {
        const bool disk_output = mounted_generation && mounted_service == endpoint.generation &&
                                 residents[0].state.mounted_generation == mounted_generation && device == 3 &&
                                 slot >= 41 && slot <= 56 && !size && inode && directory_device == 3 && directory_inode;
        return disk_output || (device <= 2 && slot >= 33 && slot <= 36 && !size && ((device == 0) == (inode == 0)) &&
                               directory_device == 1 && directory_inode >= 65536);
    }
    return process::file_open_reply_valid(
        id, size, device, inode, directory_device, directory_inode, runtime_storage.dual());
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
auto advance_client_request(std::size_t slot = 1) -> ClientProgress {
    using Step = aurora::endpoint::Step;
    using Consume = aurora::endpoint::Consume;
    if (!slot || slot >= residents.size() || !residents[slot].space || !residents[0].space ||
        endpoint.count > Endpoint::capacity || endpoint.caller != std::optional<std::size_t>{slot})
        return ClientProgress::failed;
    const U64 client = residents[slot].state.run;
    const auto step = endpoint_owner.client_step(client);
    if (step == Step::launch) {
        if (!residents[0].space || endpoint.count > Endpoint::capacity)
            fail("endpoint client dispatch physical state");
        if (!residents[0].state.budget->restart())
            fail("service budget restart");
    } else if (step != Step::resume) {
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
    const bool more = !reply.get(0) && endpoint.call.action == static_cast<U64>(process::CallAction::write) &&
                      endpoint.written != endpoint.call.length;
    const auto consumed =
        endpoint_owner.consume_client(endpoint_owner.observe().transaction, endpoint.caller_cancelled, more);
    if (consumed == Consume::refused)
        return ClientProgress::failed;
    if (consumed == Consume::tail) {
        // Source selected another distinct message. Copy its already-admitted
        // tail now; no timer allowance or ordinal is renewed until dispatch.
        const U64 remaining = endpoint.call.length - endpoint.written;
        if (remaining > 64 || root() != kernel_root)
            fail("file write continuation");
        auto &client_space = *residents[slot].space;
        const auto address = endpoint.call.base + endpoint.written;
        const U64 admitted_root = table.activation_root(slot, client_space.epoch());
        asm volatile("mov %0, %%cr3" : : "r"(admitted_root) : "memory");
        if (client_space.access(address, remaining, false) != ProcessSpace::Access::granted)
            fail("parked write source");
        message_header(22, endpoint.call.value, 0, remaining);
        const auto *source = reinterpret_cast<const volatile std::byte *>(address);
        for (U64 at = 0; at < remaining; ++at)
            endpoint.bytes[64 + at] = source[at];
        asm volatile("mov %0, %%cr3" : : "r"(kernel_root) : "memory");
        endpoint.written += remaining;
        return ClientProgress::pending;
    }
    if (consumed != Consume::completion && consumed != Consume::cancelled)
        fail("endpoint client consumption result");
    endpoint.caller.reset();
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
    if (service_root.phase() == aurora::service::Phase::retiring)
        return {static_cast<ServiceFailure>(service_root.reason()), service_root.detail()};
    if (kind != ServiceFailure::observe)
        return {kind, 0};
    if (endpoint.invalid_reply_operation)
        return {ServiceFailure::invalid_reply, endpoint.invalid_reply_operation};
    if (residents[0].space)
        return {endpoint.caller_cancelled ? ServiceFailure::caller_expired : ServiceFailure::unavailable, 0};
    // A failed load has no execution-owned terminal observation. Natural
    // service terminals are already frozen by the source incarnation root.
    return {ServiceFailure::unavailable, 0};
}
auto service_lost(ServiceLoss loss, U64 generation) -> void {
    Serial::text("AURORA_FILE_SERVICE_LOST:");
    field("generation", generation);
    field("transaction", endpoint_owner.observe().transaction);
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
    revoke_volumes();
    block_service = block_generation = block_sectors = 0;
    endpoint.caller.reset();
    for (auto &byte : endpoint.bytes)
        *static_cast<volatile std::byte *>(&byte) = std::byte{0};
}

// A cleanup observation is admitted only at the actual resource boundary. The
// copied generation is not sufficient to manufacture this acknowledgement.
auto acknowledge_service_cleanup(U64 generation) -> void {
    if (const auto endpoint_observation = endpoint_owner.observe();
        residents[0].space || clients_live() || snapshot || running.space || endpoint.generation || endpoint.caller ||
        endpoint_observation.waiting() || endpoint_observation.replied() || endpoint_observation.delivery() ||
        endpoint_observation.completion() || !audit_residents() || !service_root.cleaned(generation))
        fail("file service cleanup acknowledgement");
}

auto discard_snapshot() -> void {
    if (snapshot) {
        if (!snapshot->release())
            fail("loader snapshot rollback");
        snapshot.reset();
    }
}
auto invalidate_service_physical(std::size_t slot) -> void {
    using namespace aurora::lifecycle;
    if (slot != 0 || forced_execution || completed_output)
        fail("service terminal boundary");
    authenticate_execution(0, Phase::retiring);
    authenticate_terminal_capture(0);
    const auto generation = execution_owner.canonical(0, Field::incarnation);
    const auto event = execution_owner.canonical(0, Field::terminal);
    const auto detail = execution_owner.canonical(0, Field::terminal_detail);
    if (endpoint.invalid_reply_operation > aurora::service::terminal_reply_limit)
        fail("service terminal factual bounds");
    const U64 terminal_facts = (endpoint.invalid_reply_operation << aurora::service::terminal_reply_shift) |
                               (endpoint.caller_cancelled ? aurora::service::terminal_cancelled : 0);
    if (!generation || residents[0].state.service != generation || endpoint.generation != generation ||
        execution_owner.canonical(0, Field::event) == static_cast<U64>(Event::forced) ||
        !service_root.observe_terminal(generation, event, detail, residents[0].budget.used(), terminal_facts))
        fail("service terminal incarnation");
    const bool had_snapshot = snapshot.has_value();
    const U64 client = residents[1].space ? residents[1].state.run : 0;
    loading_image = false;
    endpoint.caller.reset();
    if (generation && !endpoint_owner.invalidate(generation))
        fail("endpoint invalidation");
    discard_snapshot();
    // Incarnation remains bound until both slots have retired and the actual
    // consumer acknowledges cleanup; no late reply remains deliverable.
    Serial::text("AURORA_SERVICE_INVALIDATED:");
    field("generation", generation);
    field("server", residents[0].state.run);
    field("client", client);
    field("snapshot", had_snapshot);
    field("companion", residents[0].state.companion);
    Serial::text("\r\n");
}
auto abandon_service_observed(ServiceLoss loss) -> void {
    // The caller freezes the actual server result before forced retirement
    // replaces the shared outcome. The cause is diagnostic, never authority.
    const auto phase = service_root.phase();
    const U64 generation = phase == aurora::service::Phase::absent ? 0 : service_root.generation();
    if (generation) {
        if (endpoint.generation && endpoint.generation != generation)
            fail("file service loss incarnation");
        if (phase == aurora::service::Phase::retiring) {
            if (const auto endpoint_observation = endpoint_owner.observe();
                residents[0].space || clients_live() || snapshot || loading_image || endpoint.caller ||
                endpoint_observation.replied() || endpoint_observation.delivery() ||
                endpoint_observation.completion() || service_root.reason() == aurora::service::Reason::shutdown)
                fail("file service pending terminal cleanup");
        } else if (!service_root.lose(generation, static_cast<aurora::service::Reason>(loss.kind), loss.detail)) {
            fail("file service loss observation");
        }
    } else if (endpoint.generation || residents[0].space || clients_live() || snapshot) {
        fail("absent file service physical owner");
    }
    // No process may see a late reply or a writable staging alias after loss.
    loading_image = false;
    endpoint.caller.reset();
    // Startup may fail before it ever binds an endpoint. A service intent is
    // not the older/absent endpoint's identity; revoke only actual attachment.
    if (endpoint.generation && !endpoint_owner.invalidate(endpoint.generation))
        fail("endpoint invalidation");
    discard_snapshot();
    for (std::size_t slot : {std::size_t{1}, std::size_t{2}, std::size_t{0}}) {
        if (!residents[slot].space)
            continue;
        force_resident(slot);
    }
    const auto frozen =
        generation ? ServiceLoss{static_cast<ServiceFailure>(service_root.reason()), service_root.detail()} : loss;
    service_lost(frozen, generation);
    if (generation)
        acknowledge_service_cleanup(generation);
}

auto abandon_service(ServiceFailure failure = ServiceFailure::observe) -> void {
    abandon_service_observed(observe_service_loss(failure));
}

#ifdef AURORA_UEFI_NVME
// Shared one-way writer execution; only admitted boot compositions may call it.
auto finish_recovery(U64 baseline) -> bool {
    auto &resident = residents[0];
    if (!resident.space || execution_owner.phase(0) != aurora::lifecycle::Phase::prepared || resident.state.service ||
        resident.state.block_generation || next_block_generation == ~U64{0})
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

// One physical startup binding. These are authenticated effect receipts, not
// an alternative bootstrap phase or copy cursor; sequencing lives in Aurora.
class ServiceBootstrapTransport final {
    static inline std::span<const std::byte> volume_;
    static inline U64 generation_ = 0;
    static auto require(bool valid) -> void {
        if (!valid)
            fail("service bootstrap effect state");
    }

public:
    class Binding final {
    public:
        std::span<const std::byte> volume;
        U64 generation = 0, run = 0, owner = 0, root = 0;
        U64 pending_operation = 0, pending_transaction = 0;
        bool mounted_attempt = false, mounted_entry = false, storage_required = false;
        bool initial_receipt = false, seal_receipt = false, storage_receipt = false, disk_ready = false;
        bool failed = false;
        ServiceLoss loss{ServiceFailure::unavailable, 0};
    };
    static auto bound(const Binding &binding) -> bool {
        return binding.generation && service_root.phase() == aurora::service::Phase::starting &&
               service_root.generation() == binding.generation && endpoint.generation == binding.generation &&
               residents[0].space && residents[0].state.service == binding.generation &&
               residents[0].state.run == binding.run && residents[0].space->owner() == binding.owner &&
               residents[0].space->root() == binding.root && !clients_live() && !snapshot;
    }
    static auto failed(Binding &binding) -> void {
        if (!binding.failed) {
            binding.loss = observe_service_loss(ServiceFailure::observe);
            binding.failed = true;
        }
    }
    static auto bind(std::span<const std::byte> volume, U64 generation) -> void {
        require(volume_.empty() && !generation_ && !volume.empty() && generation &&
                service_root.phase() == aurora::service::Phase::starting && service_root.generation() == generation);
        volume_ = volume;
        generation_ = generation;
    }
    static auto unbind() -> void {
        require(generation_ && !loading_image && !clients_live() && !snapshot && !endpoint.caller);
        volume_ = {};
        generation_ = 0;
    }
    static auto begin(Binding &binding) -> aurora::bootstrap::Preparation {
        require(generation_ && !residents[0].space && !clients_live() && !snapshot &&
                service_root.phase() == aurora::service::Phase::starting && service_root.generation() == generation_);
        binding.volume = volume_;
        binding.generation = generation_;
        binding.storage_required = runtime_storage.block();
        if (next_run >= 0xffffffffULL - frames::first_owner) {
            failed(binding);
            return {};
        }
        binding.mounted_attempt = runtime_storage.claim_mounted();
#ifdef AURORA_UEFI_NVME
        binding.mounted_entry = binding.mounted_attempt && aurora::uefi::nvme_mounted_sector_count();
#endif
        const auto path = runtime_storage.dual()  ? std::string_view{"bin/file-service-dual", 21}
                          : binding.mounted_entry ? std::string_view{"bin/file-service-mounted", 24}
                                                  : std::string_view{"bin/file-service", 16};
        constexpr std::string_view arguments{"file-service\0", 13};
        reset_loader(128);
        loading_image = true;
        endpoint.generation = binding.generation;
        require(endpoint_owner.bind(endpoint.generation));
        endpoint.window = endpoint.count = 0;
        endpoint.request_operation = endpoint.invalid_reply_operation = 0;
        endpoint.caller_cancelled = false;
        const auto image = process::volume_lookup(binding.volume, bytes_of(path));
        bool bootstrap_grant_block = runtime_storage.block() && !runtime_storage.mounted();
#ifdef AURORA_UEFI_NVME
        bootstrap_grant_block =
            runtime_storage.block() && (!runtime_storage.mounted() || aurora::uefi::nvme_mounted_readonly());
#endif
        process::RunEntry entry{};
        entry.ticks = 64;
        entry.quota = 32768;
        if (!image || !load_image(binding.volume,
                                  *image,
                                  bytes_of(arguments),
                                  entry,
                                  ++next_run,
                                  0,
                                  true,
                                  true,
                                  binding.generation,
                                  bootstrap_grant_block,
                                  0,
                                  binding.mounted_entry)) {
            failed(binding);
            return {};
        }
        binding.run = residents[0].state.run;
        binding.owner = residents[0].space->owner();
        binding.root = residents[0].space->root();
#ifdef AURORA_PROCESS_FIXTURE
        if (mounted_prepared_refusal) {
            require(binding.mounted_entry && bound(binding) && !execution_owner.entered() &&
                    execution_owner.phase(0) == aurora::lifecycle::Phase::prepared && execution_owner.pending(0) == 0 &&
                    execution_owner.generation(0) != 0 && residents[0].budget.used() == 0 &&
                    residents[0].state.mounted_generation == mounted_generation && mounted_generation &&
                    binding.owner == mounted_owner && binding.root == mounted_root &&
                    binding.generation == mounted_service && residents[0].state.mounted_sectors == mounted_sectors);
            for (const auto word : residents[0].continuation)
                require(word == 0);
            Serial::text("AURORA_MOUNTED_PREPARED_REFUSAL:");
            field("owner", binding.owner);
            field("root", binding.root);
            field("generation", mounted_generation);
            field("service", binding.generation);
            field("execution", execution_owner.generation(0));
            Serial::text(" phase=prepared pending=0 entered=0 chunk=0\r\n");
            // Malformed transport capacity, not a fabricated loss observation.
            // The ordinary source plan rejects this and consumes its real lease.
            return {1, binding.volume.size(), 0, binding.storage_required ? U64{1} : U64{0}};
        }
#endif
        return {1, binding.volume.size(), Endpoint::capacity - 64, binding.storage_required ? U64{1} : U64{0}};
    }
    static auto stage(Binding &binding, U64 operation, U64 id, U64 offset, std::span<const std::byte> payload = {})
        -> aurora::bootstrap::Effect {
        using aurora::bootstrap::Effect;
        require(!binding.failed && binding.initial_receipt && !binding.pending_operation &&
                payload.size() <= Endpoint::capacity - 64);
        if (!bound(binding) || endpoint.caller_cancelled) {
            failed(binding);
            return Effect::failed;
        }
        {
            const auto endpoint_observation = endpoint_owner.observe();
            require(endpoint_observation.waiting() && !endpoint_observation.delivery() &&
                    !endpoint_observation.replied() && !endpoint.caller);
        }
        message_header(operation, id, offset, payload.size());
        for (U64 at = 0; at < payload.size(); ++at)
            endpoint.bytes[64 + at] = payload[at];
        if (!begin_exchange(0)) {
            failed(binding);
            return Effect::failed;
        }
        binding.pending_operation = operation;
        binding.pending_transaction = endpoint_owner.observe().transaction;
        return Effect::staged;
    }
    static auto begin_volume(Binding &binding) -> aurora::bootstrap::Effect {
        require(!binding.seal_receipt && !binding.storage_receipt);
        return stage(
            binding, 1, binding.volume.size(), runtime_storage.dual() ? 4 : runtime_storage.readonly_profile());
    }
    static auto copy_volume(Binding &binding, U64 offset) -> aurora::bootstrap::Effect {
        require(!binding.seal_receipt && !binding.storage_receipt && offset < binding.volume.size());
        const U64 count = least(Endpoint::capacity - 64, binding.volume.size() - offset);
        return stage(binding, 2, 0, offset, binding.volume.subspan(offset, count));
    }
    static auto seal_volume(Binding &binding) -> aurora::bootstrap::Effect {
        require(!binding.seal_receipt && !binding.storage_receipt);
        return stage(binding, 3, 0, 0);
    }
    static auto admit_storage(Binding &binding) -> aurora::bootstrap::Effect {
        require(!binding.failed && binding.storage_required && binding.seal_receipt && !binding.storage_receipt &&
                !binding.pending_operation);
        if (!bound(binding) || endpoint.caller_cancelled) {
            failed(binding);
            return aurora::bootstrap::Effect::failed;
        }
        reset_loader(16, 1);
        if (!residents[0].state.budget->configure_next(16, 1))
            fail("mounted startup budget profile");
        return stage(binding, 15, 0, 0);
    }
    static auto advance(Binding &binding) -> aurora::bootstrap::Progress {
        using aurora::bootstrap::Progress;
        require(!binding.failed);
        if (!bound(binding) || endpoint.caller_cancelled) {
            failed(binding);
            return Progress::failed;
        }
        if (!binding.initial_receipt) {
            require(!binding.pending_operation);
            if (endpoint_owner.initial_step() == aurora::endpoint::Step::resume)
                static_cast<void>(run_resident(0));
            if (!bound(binding) || endpoint.caller_cancelled) {
                failed(binding);
                return Progress::failed;
            }
            const auto initial = endpoint_owner.initial_step();
            if (initial == aurora::endpoint::Step::resume)
                return Progress::pending;
            require(initial == aurora::endpoint::Step::replied);
            {
                const auto endpoint_observation = endpoint_owner.observe();
                require(execution_owner.phase(0) == aurora::lifecycle::Phase::parked && endpoint.window &&
                        !endpoint_observation.transaction && !endpoint_observation.source &&
                        !endpoint_observation.replied() && !endpoint_observation.delivery() && !endpoint.caller);
            }
            binding.initial_receipt = true;
            return Progress::complete;
        }
        {
            const auto endpoint_observation = endpoint_owner.observe();
            require(binding.pending_operation && binding.pending_transaction &&
                    endpoint_observation.transaction == binding.pending_transaction &&
                    endpoint_observation.source == 0);
        }
        const auto progress = advance_exchange();
        if (progress == ExchangeProgress::failed || !bound(binding) || endpoint.caller_cancelled) {
            failed(binding);
            return Progress::failed;
        }
        if (progress == ExchangeProgress::pending)
            return Progress::pending;
        const U64 operation = binding.pending_operation;
        const auto endpoint_reply = endpoint_owner.observe();
        const bool authenticated = endpoint_reply.transaction == binding.pending_transaction &&
                                   endpoint_reply.source == 0 && endpoint_reply.waiting() && endpoint_reply.replied() &&
                                   !endpoint_reply.delivery() && endpoint.count == 64;
        const auto granted_count = residents[0].state.volumes_count;
        const bool valid_volume_mask =
            !runtime_storage.dual() || operation != 15 ||
            (granted_count <= 2 && !(std::to_integer<unsigned>(endpoint.bytes[24]) & ~((1U << granted_count) - 1U)));
        const auto reply =
            authenticated && valid_volume_mask
                ? aurora::bootstrap::inspect_reply(operation, {endpoint.bytes.data(), 64}, runtime_storage.dual())
                : aurora::bootstrap::Reply::invalid;
        if (reply == aurora::bootstrap::Reply::invalid) {
            if (!endpoint.invalid_reply_operation)
                endpoint.invalid_reply_operation = operation;
            failed(binding);
            return Progress::failed;
        }
        if (!endpoint_owner.consume_control(endpoint_owner.observe().transaction))
            fail("endpoint control consumption");
        binding.pending_operation = binding.pending_transaction = 0;
        if (operation == 3) {
            require(!binding.seal_receipt);
            binding.seal_receipt = true;
        }
        if (operation == 15) {
            require(binding.seal_receipt && !binding.storage_receipt);
            binding.storage_receipt = true;
            binding.disk_ready = reply == aurora::bootstrap::Reply::ready;
            if (runtime_storage.dual()) {
                Serial::text("AURORA_DUAL_STORAGE_READY:");
                field("mask", std::to_integer<unsigned>(endpoint.bytes[24]));
                Serial::text("\r\n");
            }
        }
        return Progress::complete;
    }
    static auto finish(Binding &binding, aurora::bootstrap::Finish disposition) -> aurora::bootstrap::Result {
        using namespace aurora::bootstrap;
        require(binding.generation && generation_ == binding.generation &&
                service_root.generation() == binding.generation);
        const auto phase = service_root.phase();
        if (disposition == Finish::abandon) {
            if (phase == aurora::service::Phase::retiring) {
                // A real bootstrap execution may already have revoked and
                // retired its unpublished service. Consume only this lease's
                // matching frozen observation; never revive it for publication.
                {
                    const auto endpoint_observation = endpoint_owner.observe();
                    require(binding.failed && binding.run && endpoint.generation == binding.generation &&
                            outcome.terminal_run == binding.run && outcome.terminal_service == binding.generation &&
                            service_root.reason() != aurora::service::Reason::shutdown &&
                            static_cast<U64>(service_root.reason()) == static_cast<U64>(binding.loss.kind) &&
                            service_root.detail() == binding.loss.detail && !residents[0].space && !clients_live() &&
                            !snapshot && !loading_image && !endpoint.caller && !endpoint_observation.waiting() &&
                            !endpoint_observation.replied() && !endpoint_observation.delivery() &&
                            !endpoint_observation.completion() && LifecyclePlatform::quiet() &&
                            execution_owner.phase(0) == aurora::lifecycle::Phase::empty &&
                            execution_owner.phase(1) == aurora::lifecycle::Phase::empty &&
                            execution_owner.phase(2) == aurora::lifecycle::Phase::empty);
                }
            } else {
                require(phase == aurora::service::Phase::starting);
            }
            ServiceLoss loss = binding.failed ? binding.loss : observe_service_loss(ServiceFailure::observe);
            if (!binding.failed && bound(binding) && !endpoint.caller_cancelled && !endpoint.invalid_reply_operation)
                loss = {ServiceFailure::consumer_rejected, 0};
#ifdef AURORA_UEFI_NVME
            // A granted role belongs to the execution owner even before first
            // entry. Its cleanup must follow source revocation, not precede it.
            const bool unowned_mounted_attempt = binding.mounted_attempt && (!binding.mounted_entry || !binding.run);
#endif
            abandon_service_observed(loss);
#ifdef AURORA_UEFI_NVME
            if (unowned_mounted_attempt)
                aurora::uefi::nvme_mounted_abandon();
#endif
            binding.pending_operation = binding.pending_transaction = 0;
            binding.initial_receipt = binding.seal_receipt = binding.storage_receipt = false;
            return Result::unavailable;
        }
        {
            const auto endpoint_observation = endpoint_owner.observe();
            require(disposition == Finish::publish && phase == aurora::service::Phase::starting && !binding.failed &&
                    bound(binding) && binding.initial_receipt && binding.seal_receipt &&
                    (!binding.storage_required || binding.storage_receipt) && !binding.pending_operation &&
                    !endpoint.caller_cancelled && endpoint_observation.waiting() && !endpoint_observation.replied() &&
                    !endpoint_observation.delivery() && !endpoint.caller);
        }
        // Publication consumes the actual receipts once. The mounted broker is
        // still unarmed until the normal budget is restored at this boundary.
        binding.initial_receipt = binding.seal_receipt = binding.storage_receipt = false;
        if (binding.storage_required && !residents[0].state.budget->reset(64, 0))
            fail("mounted runtime budget profile");
        loading_image = false;
#ifdef AURORA_UEFI_NVME
        if (binding.mounted_entry) {
            const auto &server = residents[0].state;
            require(server.mounted_generation == mounted_generation && server.service == mounted_service &&
                    endpoint.generation == mounted_service && !endpoint_owner.observe().source &&
                    residents[0].space->owner() == mounted_owner && residents[0].space->root() == mounted_root);
            if (!binding.disk_ready || !aurora::uefi::nvme_mounted_arm()) {
                aurora::uefi::nvme_mounted_abandon();
                binding.disk_ready = false;
            } else {
                Serial::text("AURORA_MOUNTED_ARMED:");
                field("generation", mounted_generation);
                Serial::text("\r\n");
            }
        }
#endif
        if (!service_root.mark_ready(binding.generation, binding.disk_ready))
            fail("file service readiness");
        Serial::text("AURORA_FILE_SERVICE_READY:");
        field("generation", endpoint.generation);
        if (binding.storage_required)
            Serial::text(binding.disk_ready ? std::string_view{" disk=ready", 11}
                                            : std::string_view{" disk=unavailable", 17});
        Serial::text("\r\n");
        return Result::ready;
    }
    static auto settled(const Binding &binding) -> bool {
        const auto endpoint_observation = endpoint_owner.observe();
        if (loading_image || clients_live() || snapshot || endpoint.caller || endpoint_observation.replied() ||
            endpoint_observation.delivery() || endpoint_observation.completion() || binding.pending_operation ||
            binding.initial_receipt || binding.seal_receipt || binding.storage_receipt || !audit_residents())
            return false;
        const auto phase = service_root.phase();
        if (phase == aurora::service::Phase::absent)
            return !residents[0].space && !endpoint.generation && !endpoint_observation.waiting();
        return phase == aurora::service::Phase::ready && service_root.generation() == binding.generation &&
               residents[0].space && residents[0].state.run == binding.run &&
               residents[0].state.service == binding.generation && endpoint.generation == binding.generation &&
               residents[0].space->owner() == binding.owner && residents[0].space->root() == binding.root &&
               endpoint_observation.waiting();
    }
};
class ServiceBootstrapPlatform final {
public:
#ifdef AURORA_PRODUCTION
    static auto capture_parent() -> aurora::resident::Parent {
        return resident_owner.capture_parent();
    }
    static auto parent_valid(aurora::resident::Parent parent) -> bool {
        return resident_owner.parent_valid(parent);
    }
    static auto release_parent(aurora::resident::Parent parent) -> void {
        resident_owner.release_parent(parent);
    }
#endif
    static auto quiet() -> bool {
        return Timer::irq_off() && root() == kernel_root && !running.space && !Timer::read(0x390) &&
               Timer::quiet(0x100, false) && Timer::quiet(0x200, false);
    }
    [[noreturn]] static auto fail() -> void {
        ::fail("service bootstrap grant");
    }
};
using ServiceBootstrapSession = aurora::bootstrap::Session<ServiceBootstrapTransport, ServiceBootstrapPlatform>;

auto start_file_service(std::span<const std::byte> volume, U64 generation) -> bool {
    ServiceBootstrapTransport::bind(volume, generation);
    const auto issuer = ServiceBootstrapSession::open();
    const U64 result = source_bootstrap_service(&issuer);
    ServiceBootstrapSession::release(issuer);
    ServiceBootstrapTransport::unbind();
    if (result > static_cast<U64>(aurora::bootstrap::Result::unavailable))
        fail("service bootstrap result");
    const bool ready = result == static_cast<U64>(aurora::bootstrap::Result::ready);
    const bool published = service_root.phase() == aurora::service::Phase::ready &&
                           service_root.generation() == generation && endpoint.generation == generation &&
                           residents[0].space && residents[0].state.service == generation;
    if (ready != published || (!ready && (service_root.phase() != aurora::service::Phase::absent ||
                                          residents[0].space || endpoint.generation)))
        fail("service bootstrap result disagrees with publication");
    return ready;
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

[[gnu::noinline]] auto deliver_output(std::size_t slot = 1) -> bool {
    if (execution_owner.entered() || completed_output || forced_execution)
        fail("output lifecycle scope");
    if (!output_sink || !Timer::irq_off() || root() != kernel_root || Timer::read(0x390) ||
        !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false) || endpoint.count > Endpoint::capacity)
        fail("process output ownership");
    if (!slot || slot >= residents.size() || !residents[slot].space ||
        execution_owner.phase(slot) != aurora::lifecycle::Phase::parked)
        fail("output stopped context");
    const auto generation = execution_owner.generation(slot);
    const U64 pending = execution_owner.pending(slot);
    const U64 saved_context = reinterpret_cast<U64>(residents[slot].continuation.data());
    const U64 capture_context = reinterpret_cast<U64>(residents[slot].state.captured);
    const U64 resume_context = reinterpret_cast<U64>(residents[slot].state.continuation);
    if (pending != static_cast<U64>(aurora::lifecycle::Event::output) || capture_context != saved_context ||
        resume_context != saved_context)
        fail("output pending context");
    const auto stopped_frame = residents[slot].continuation;
    const auto epoch = residents[slot].space->epoch();
    const auto physical_root = residents[slot].space->root();
    const bool delivered = output_sink(output_context, output_error_stream, {endpoint.bytes.data(), endpoint.count});
    if (execution_owner.entered() || !residents[slot].space || execution_owner.generation(slot) != generation ||
        execution_owner.pending(slot) != pending ||
        reinterpret_cast<U64>(residents[slot].continuation.data()) != saved_context ||
        reinterpret_cast<U64>(residents[slot].state.captured) != capture_context ||
        reinterpret_cast<U64>(residents[slot].state.continuation) != resume_context ||
        residents[slot].space->epoch() != epoch || residents[slot].space->root() != physical_root)
        fail("output callback lifecycle changed");
    // A different but individually well-formed frame is not the frame whose
    // output operation was delivered. Compare exact physical words, not a hash.
    if (residents[slot].continuation != stopped_frame)
        fail("output callback frame changed");
    if (delivered) {
#if defined(AURORA_PRODUCTION) || defined(AURORA_PROCESS_FIXTURE)
        present_foreground(slot);
#endif
        completed_output = &delivered;
        if (!execution_owner.complete(slot))
            fail("output completion refused");
        completed_output = nullptr;
    }
    return delivered;
}
#ifdef AURORA_PROCESS_FIXTURE
auto execution_output_probe(void *, bool, std::span<const std::byte>) -> bool {
    if ((execution_probe_case != 69 && execution_probe_case != 71) || execution_owner.entered() ||
        !residents[1].space || execution_owner.phase(1) != aurora::lifecycle::Phase::parked)
        fail("output callback probe setup");
    const U64 probe = execution_probe_case;
    execution_probe_case = 0;
    execution_probe_marker(probe, 1);
    // The external callback cannot touch the source root. Corrupt only its
    // native stopped frame; completion must reauthenticate after returning.
    if (probe == 69)
        residents[1].continuation[18] = 8;
    else
        residents[1].continuation[0] ^= 1;
    return true;
}
#endif

auto invalidate_input(U64 owner) -> void {
    if (!owner || input_read.owner != owner)
        return;
    if (input_wait.active)
        fail("input abort during synchronous wait");
    input_read.pending = input_read.completing = false;
    input_read.protocol = process::input_update(input_read.protocol, 4);
    input_read.bytes = {};
    input_read.owner = 0; // Revoke before any retirement or ownership return.
}
auto input_identity() -> bool {
    const auto &resident = residents[1];
    return input_read.pending && input_read.owner && resident.space && !running.space && !execution_owner.entered() &&
           root() == kernel_root && Timer::irq_off() && resident.state.run == input_read.owner &&
           resident.space->epoch() == input_read.epoch && resident.space->root() == input_read.root &&
           execution_owner.phase(1) == aurora::lifecycle::Phase::parked &&
           execution_owner.pending(1) == static_cast<U64>(aurora::lifecycle::Event::input) &&
           execution_owner.generation(1) == input_read.generation &&
           input_frame_equal(resident.continuation, input_read.frame) &&
           resident.state.captured == &resident.continuation && resident.state.continuation == &resident.continuation;
}
#if defined(AURORA_PRODUCTION) || defined(AURORA_PROCESS_FIXTURE)
// This is an observation receipt, never a replacement source authority. Its
// lifetime is the single synchronous excursion with both source slots frozen.
class PresentationResident final {
public:
    Running state;
    std::array<U64, frame_words> frame;
    std::array<U64, 8> initial;
    U64 generation, pending, epoch, root, used, quantum;
    aurora::lifecycle::Phase phase;
    bool live = false;
};
auto presentation_quiet(std::size_t selected) -> bool {
    const auto endpoint_state = endpoint_owner.observe();
    return LifecyclePlatform::quiet() && !execution_owner.entered() && !execution_owner.busy() &&
           (Timer::read(0x320) & 0x700ff) == (0x10000 | Timer::vector) && !runtime_detached && !draining &&
           !input_wait.active && !input_wait.stack && !input_wait.armed && !input_wait.owner && !input_wait.sequence &&
           !input_wait.expired && !snapshot && !endpoint.caller &&
           endpoint_state.phase == aurora::endpoint::Phase::waiting && !endpoint_state.client && !forced_execution &&
           !completed_output && !endpoint_trap_scope && !loading_image &&
           service_root.phase() == aurora::service::Phase::ready && endpoint.generation == service_root.generation() &&
           selected && selected < residents.size() && residents[0].space && residents[selected].space &&
           residents[0].state.service == endpoint.generation;
}
[[gnu::noinline]] auto present_foreground(std::size_t selected) -> void {
    using namespace aurora::lifecycle;
    if (!presentation_sink)
        return;
    U64 stack_pointer;
    asm volatile("mov %%rsp, %0" : "=r"(stack_pointer));
    const auto target = reinterpret_cast<U64>(presentation_sink);
    if (!presentation_handoff || !presentation_quiet(selected) || stack_pointer % 8 ||
        stack_pointer < owned_arena + Handoff::stack_bottom + 4096 ||
        stack_pointer >= owned_arena + Handoff::stack_top || target < owned_arena + Handoff::payload_offset ||
        target >= owned_arena + Handoff::payload_offset + presentation_handoff->get(64))
        fail("presentation entry boundary");
    // Probe does not borrow Display or change architecture. Clean grids consume
    // no source admission; the production target and all its data are boot-mapped.
    if (!presentation_sink(false))
        return;
    // Only deliver_output and deliver_input call here, after authenticating
    // their parked event (and exact input receipt for input). Source admission
    // rechecks eligibility and both canonical resident identities below.
    // One admission prepays every possible cell/store, even on an immediate
    // UART yield. Exhaustion is optional graphics deferral, never process failure.
    const auto ordinal = execution_owner.begin_presentation(selected);
    if (!ordinal)
        return;
    if (ordinal > 32 || execution_owner.entered() || execution_owner.busy() ||
        execution_owner.phase(selected) != Phase::presenting)
        fail("presentation admission closure");
    // Only an admitted pass pays for complete mapping/resident scans and
    // receipts. Clean or exhausted calls cannot repeat this work indefinitely.
    // Both slots are now frozen; failure here is fail-stop, never a refund.
    if (!space.verify(table, ranges, kernel_table_pages) || !audit_residents())
        fail("presentation admitted mapping");
    std::array<PresentationResident, KernelSpace::process_slots> saved{};
    for (std::size_t slot = 0; slot < residents.size(); ++slot) {
        const auto &resident = residents[slot];
        if (!resident.space) {
            if (execution_owner.phase(slot) != Phase::empty || !resident.budget.inactive())
                fail("presentation empty identity");
            saved[slot] = {resident.state,
                           resident.continuation,
                           resident.initial,
                           execution_owner.generation(slot),
                           execution_owner.pending(slot),
                           0,
                           0,
                           0,
                           0,
                           Phase::empty,
                           false};
            continue;
        }
        if (execution_owner.phase(slot) == Phase::parked || slot == selected)
            authenticate_stopped_frame(slot, slot == 0 || slot == selected);
        else if (execution_owner.phase(slot) != Phase::prepared)
            fail("presentation sibling phase");
        saved[slot] = {resident.state,
                       resident.continuation,
                       resident.initial,
                       execution_owner.generation(slot),
                       execution_owner.pending(slot),
                       resident.space->epoch(),
                       resident.space->root(),
                       resident.budget.used(),
                       resident.budget.quantum(),
                       execution_owner.phase(slot),
                       true};
    }
    const auto saved_input = input_read;
    const U64 service = endpoint.generation;
    const auto endpoint_before = endpoint_owner.observe();
    const U64 window_before = endpoint.window, count_before = endpoint.count;
    U64 previous_cr2;
    asm volatile("mov %%cr2, %0" : "=r"(previous_cr2));
    table.suspend(); // Requires no bank loan, pin, view or mapping effect.
    if (!space.detach())
        fail("presentation detach");
    // No source/MM access is possible until the exact banks are reattached.
    if (!presentation_sink(true))
        fail("presentation callback closure");
    if (!space.attach(ranges) || !space.resume_manager(table, ranges, kernel_table_pages))
        fail("presentation exact bank restoration");
    install_architecture(owned_arena);
    asm volatile("mov %0, %%cr2" : : "r"(previous_cr2) : "memory");
    const auto endpoint_after = endpoint_owner.observe();
    if (!presentation_quiet(selected) || !space.verify(table, ranges, kernel_table_pages) || !audit_residents() ||
        endpoint.generation != service || endpoint.window != window_before || endpoint.count != count_before ||
        endpoint_before.incarnation != endpoint_after.incarnation || endpoint_before.phase != endpoint_after.phase ||
        endpoint_before.next != endpoint_after.next || endpoint_before.transaction != endpoint_after.transaction ||
        endpoint_before.source != endpoint_after.source || endpoint_before.client != endpoint_after.client ||
        execution_owner.phase(selected) != Phase::presenting)
        fail("presentation restored boundary");
    for (std::size_t slot = 0; slot < residents.size(); ++slot) {
        const auto &resident = residents[slot];
        const auto &before = saved[slot];
        if (!before.live) {
            if (resident.space || execution_owner.phase(slot) != Phase::empty || !resident.budget.inactive() ||
                resident.state != before.state || resident.initial != before.initial ||
                resident.continuation != before.frame || execution_owner.generation(slot) != before.generation ||
                execution_owner.pending(slot) != before.pending)
                fail("presentation empty changed");
            continue;
        }
        if (!resident.space || resident.state != before.state || resident.initial != before.initial ||
            !input_frame_equal(resident.continuation, before.frame) ||
            execution_owner.generation(slot) != before.generation || execution_owner.pending(slot) != before.pending ||
            resident.space->epoch() != before.epoch || resident.space->root() != before.root ||
            resident.budget.used() != before.used || resident.budget.quantum() != before.quantum ||
            (slot != selected && execution_owner.phase(slot) != before.phase))
            fail("presentation resident changed");
    }
    if (input_read.owner != saved_input.owner || input_read.sequence != saved_input.sequence ||
        input_read.address != saved_input.address || input_read.generation != saved_input.generation ||
        input_read.epoch != saved_input.epoch || input_read.root != saved_input.root ||
        input_read.pending != saved_input.pending || input_read.completing != saved_input.completing ||
        input_read.quarantine != saved_input.quarantine || input_read.bytes != saved_input.bytes ||
        !input_frame_equal(input_read.frame, saved_input.frame) ||
        input_read.protocol.remaining != saved_input.protocol.remaining ||
        input_read.protocol.status != saved_input.protocol.status ||
        input_read.protocol.count != saved_input.protocol.count ||
        input_read.protocol.after_cr != saved_input.protocol.after_cr)
        fail("presentation input changed");
    if (!execution_owner.finish_presentation(selected, ordinal) || execution_owner.phase(selected) != Phase::parked ||
        (saved[selected].pending == static_cast<U64>(Event::input) && !input_identity()))
        fail("presentation source restoration");
}
#endif
#ifdef AURORA_PROCESS_FIXTURE
constinit U64 presentation_probe_case = 0, presentation_probe_passes = 0;
auto presentation_probe_output(void *, bool, std::span<const std::byte>) -> bool {
    return true;
}
[[gnu::noinline]] auto presentation_probe(bool paint) -> bool {
    if (!paint)
        return presentation_probe_passes == 0;
    if (presentation_probe_case < 99 || presentation_probe_case > 101 || space.attached() || root() != kernel_root ||
        !Timer::irq_off() || Timer::read(0x390) || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        fail("presentation fixture detached boundary");
    ++presentation_probe_passes;
    Serial::text("AURORA_PRESENTATION_PROBE:");
    field("case", presentation_probe_case);
    Serial::text(" detached=1\r\n");
    if (presentation_probe_case == 100)
        residents[1].continuation[0] ^= 1;
    if (presentation_probe_case == 101)
        reinterpret_cast<volatile U64 *>(kernel_root)[KernelSpace::extension_root] = 2;
    return true;
}
#endif
#ifdef AURORA_PROCESS_FIXTURE
auto input_probe_sample(void *) -> aurora::console::Sample {
    if (!input_identity())
        fail("input fixture callback identity");
    ++input_probe_samples;
    if (input_probe_case == 97) {
        // Two actual writer runs share this fixed bounded producer. The middle
        // and final ordinary readers receive no input grant or callback.
        if (input_read.owner != 2 && input_read.owner != 4)
            fail("source writer input owner");
        const U64 offset = input_probe_samples - 1;
        const U64 length = input_read.owner == 2 ? 16384 : 16385;
        if (offset >= length)
            return {true, 4, false};
        return {true, static_cast<std::uint8_t>(offset % 256 == 255 || offset == 16384 ? '\n' : 'x'), false};
    }
    if (input_probe_case == 94 || input_probe_case == 95) {
        Serial::text("AURORA_INPUT_AUTHORITY_PROBE:");
        field("case", input_probe_case);
        field("owner", input_read.owner);
        field("sequence", input_read.sequence);
        Serial::text(" before_copy=1\r\n");
        if (input_probe_case == 94)
            input_probe_reenter();
        else
            residents[1].continuation[frame_rax] ^= 1;
        return {true, 65, false};
    }
    if (input_probe_case == 84)
        return {true, 3, false};
    if (input_probe_case == 86 && input_read.sequence == 1 && input_probe_settlements && !input_read.protocol.count)
        return {true, 65, false};
    if (input_probe_case == 87 && input_probe_settlements >= 2)
        return {true, 4, false}; // Must not beat the already settled timeout.
    if (input_probe_case == 85 || input_probe_case == 86 || input_probe_case == 87)
        return {}; // Real settlement, not callback count, advances time.
    if (input_probe_case == 83 && input_probe_settlements < input_read.sequence)
        return {};
    if (input_read.protocol.count)
        return {}; // Deliver partial data immediately, never wait to fill it.
    if (input_probe_case == 96 || input_read.sequence <= (input_probe_case == 83 ? 2 : 1))
        return {true, 65, false};
    return {true, 4, false};
}
#endif
__attribute__((noinline)) auto wait_for_input_sample() -> void {
    if (!input_identity() || input_wait.active || !input_read.protocol.remaining || Timer::read(0x390) ||
        !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        fail("input wait boundary");
#ifdef AURORA_PROCESS_FIXTURE
    const U64 cpu_before = residents[1].budget.used();
#endif
    input_wait = {};
    input_wait.owner = input_read.owner;
    input_wait.sequence = input_read.sequence;
    input_wait.armed = least(input_poll_count, input_read.protocol.remaining);
    input_wait.active = true;
    asm volatile("mov %%rsp, %0" : "=m"(input_wait.stack) : : "memory");
    if (!Timer::arm(static_cast<std::uint32_t>(input_wait.armed)))
        fail("input wait arm");
#ifdef AURORA_PROCESS_FIXTURE
    bool early = false;
    if (input_probe_case == 86 && !input_probe_partial) {
        // Bounded genuine early relinquish, not an injected timer reading.
        for (U64 polls = 0; polls < 1000000; ++polls) {
            const U64 sample = Timer::read(0x390);
            if (sample && sample < input_wait.armed) {
                early = true;
                input_probe_partial = true;
                break;
            }
            if (!sample || Timer::pending())
                break;
        }
        if (!early)
            fail("input fixture partial sample unavailable");
    }
    if (!early)
#endif
        asm volatile(".global uefi_process_input_wait_begin\nuefi_process_input_wait_begin:\nsti\nhlt\ncli\n"
                     ".global uefi_process_input_wait_end\nuefi_process_input_wait_end:"
                     :
                     :
                     : "memory");
    const U64 current = Timer::read(0x390); // Sample before stop destroys count.
    if (current > input_wait.armed || !Timer::stop())
        fail("input wait stop");
    const bool expired = input_wait.expired, pending = Timer::pending();
    const bool full = expired || pending || current == 0;
    const U64 measured = full ? input_wait.armed : input_wait.armed - current;
    const U64 charge = measured ? measured : 1;
    input_wait.active = false; // Any remaining delivery belongs to drain only.
    if (Timer::pending()) {
        draining = true;
        process_drain();
    }
    if (draining || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        fail("input wait drain");
    input_wait.active = false;
    if (!input_identity())
        fail("input wait identity");
#ifdef AURORA_PROCESS_FIXTURE
    const U64 before = input_read.protocol.remaining;
#endif
    input_read.protocol = process::input_update(input_read.protocol, 0, charge);
#ifdef AURORA_PROCESS_FIXTURE
    if (input_probe_case) {
        if (!charge || charge > input_wait.armed || input_wait.armed > before ||
            input_read.protocol.remaining != before - charge || (early && full) ||
            residents[1].budget.used() != cpu_before)
            fail("input fixture settlement");
        ++input_probe_settlements;
        Serial::text("AURORA_INPUT_WAIT:");
        field("case", input_probe_case);
        field("sequence", input_read.sequence);
        field("settlement", input_probe_settlements);
        field("arm", input_wait.armed);
        field("current", current);
        field("expired", expired);
        field("pending", pending);
        field("early", early);
        field("charge", charge);
        field("before", before);
        field("after", input_read.protocol.remaining);
        field("cpu_before", cpu_before);
        field("cpu_after", residents[1].budget.used());
        Serial::text(" drained=1\r\n");
    }
#endif
    input_wait = {};
}
[[gnu::noinline]] auto deliver_input() -> bool {
    if (!input_read.pending || !residents[1].space)
        return false;
    if (!input_identity())
        fail("input delivery boundary");
#if defined(AURORA_PRODUCTION) || defined(AURORA_PROCESS_FIXTURE)
    present_foreground();
#endif
    while (input_read.protocol.status == 0 && input_read.protocol.count < 504) {
        if (!input_source) {
            input_read.protocol = process::input_update(input_read.protocol, 2);
            break;
        }
        const auto sample = input_source(output_context);
        if (!input_identity())
            fail("input callback identity");
        if (sample.damaged) {
            input_read.protocol = process::input_update(input_read.protocol, 2);
            break;
        }
        if (!sample.present) {
            if (input_read.protocol.count)
                break; // Never wait to fill a partial chunk.
            if (!input_read.protocol.remaining) {
                input_read.protocol = process::input_update(input_read.protocol, 0);
                break;
            }
            wait_for_input_sample();
            continue;
        }
        const U64 prior = input_read.protocol.count;
        input_read.protocol = process::input_update(input_read.protocol, 1, sample.byte);
        if (input_read.protocol.count == prior + 1)
            input_read.bytes[prior] = std::byte{sample.byte};
        else if (!input_read.protocol.count)
            input_read.bytes = {};
    }
    if (!input_identity())
        fail("input commit identity");
    input_read.completing = true;
    const bool completed = execution_owner.complete(1);
    input_read.completing = false;
    return completed;
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
    using Binding = ExecutionBinding;
    static auto bound_client(const Binding &binding) -> bool {
        return binding.slot && binding.slot < residents.size() && binding.client && residents[binding.slot].space &&
               residents[binding.slot].state.run == binding.client;
    }
    static auto bound_service(const Binding &binding) -> bool {
        return binding.service_generation && residents[0].space && endpoint.generation == binding.service_generation &&
               residents[0].state.service == binding.service_generation;
    }
    static auto advance(Binding &binding) -> aurora::execution::Observation {
        using namespace aurora::execution;
        require(bound_client(binding) && !binding.output_pending && !binding.request_pending &&
                !binding.input_pending && !binding.output_failed && !binding.request_failed &&
                !binding.explicit_cancel_requested && !endpoint.caller_cancelled);
        if (run_resident(binding.slot)) {
            // Freeze terminal facts before any later cleanup can replace outcome.
            const auto ended = outcome.exited ? Status::exited : outcome.watchdog ? Status::watchdog : Status::fault;
            return {Step::retired, ended, outcome.exited ? outcome.status : outcome.vector};
        }
        require(!(outcome.output && outcome.request) && !(outcome.input && (outcome.output || outcome.request)));
        binding.output_pending = outcome.output;
        binding.request_pending = outcome.request;
        binding.input_pending = outcome.input;
        return {binding.input_pending     ? Step::input
                : binding.output_pending  ? Step::output
                : binding.request_pending ? Step::request
                                          : Step::parked,
                Status::unavailable,
                0};
    }
    static auto input(Binding &binding) -> aurora::execution::Effect {
        require(bound_client(binding) && binding.input_pending && !binding.output_pending && !binding.request_pending &&
                !binding.explicit_cancel_requested && !endpoint.caller_cancelled);
        const bool delivered = deliver_input();
        binding.input_pending = false;
        return delivered ? aurora::execution::Effect::success : aurora::execution::Effect::failed;
    }
    static auto output(Binding &binding) -> aurora::execution::Effect {
        using namespace aurora::execution;
        require(bound_client(binding) && binding.output_pending && !binding.request_pending && !binding.input_pending &&
                !binding.explicit_cancel_requested);
        binding.output_failed = !deliver_output(binding.slot);
        binding.output_pending = false;
        return binding.output_failed ? Effect::failed : Effect::success;
    }
    static auto request(Binding &binding) -> aurora::execution::Request {
        using namespace aurora::execution;
        require(bound_client(binding) && binding.request_pending && !binding.output_pending && !binding.input_pending);
        ClientProgress progress = ClientProgress::failed;
        if (bound_service(binding)) {
            if (binding.explicit_cancel_requested && endpoint.caller_cancelled) {
                const auto cancellation = endpoint_owner.cancel(binding.client, true);
                if (cancellation == aurora::endpoint::Cancel::settled) {
                    endpoint.caller.reset();
                    progress = ClientProgress::complete;
                } else if (cancellation == aurora::endpoint::Cancel::draining) {
                    progress = advance_client_request(binding.slot);
                }
            } else {
                progress = advance_client_request(binding.slot);
            }
        }
        if (progress == ClientProgress::pending)
            return Request::pending;
        binding.request_failed = progress == ClientProgress::failed;
        binding.request_pending = false;
        if (binding.request_failed)
            return Request::service_lost;
        if (binding.explicit_cancel_requested)
            return binding.expiry_preceded_cancel ? Request::explicit_after_expiry : Request::cancel_requested;
        return endpoint.caller_cancelled ? Request::cancelled : Request::ready;
    }
    static auto cancel(Binding &binding) -> aurora::execution::Cancel {
        using namespace aurora::execution;
        invalidate_input(binding.client);
        binding.input_pending = false;
        // Inert refusals and already retired clients retain their frozen result.
        if (!binding.client || !residents[binding.slot].space) {
            require(!binding.output_pending && !binding.request_pending && !binding.input_pending);
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
        if (binding.request_pending)
            require(endpoint.caller == std::optional<std::size_t>{binding.slot});
        else
            require(!endpoint.caller);
        const auto cancellation = endpoint_owner.cancel(binding.client, true);
        require(cancellation != aurora::endpoint::Cancel::refused);
        if (cancellation == aurora::endpoint::Cancel::settled) {
            endpoint.caller.reset();
            binding.request_pending = false;
            return binding.expiry_preceded_cancel ? Cancel::settled_after_expiry : Cancel::settled;
        }
        require(binding.request_pending);
        return binding.expiry_preceded_cancel ? Cancel::draining_after_expiry : Cancel::draining;
    }
    static auto finish(Binding &binding, aurora::execution::Finish disposition) -> aurora::execution::Effect {
        using namespace aurora::execution;
        require(!binding.output_pending && !binding.request_pending && !binding.input_pending);
        if (!binding.client) {
            require(disposition == Finish::complete && !residents[binding.slot].space && !snapshot && !endpoint.caller);
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
            require(!forced_execution);
            forced_execution = &binding;
            force_resident(binding.slot);
            forced_execution = nullptr;
        } else if (disposition == Finish::cancelled) {
            require(!binding.output_failed && endpoint.caller_cancelled && bound_client(binding) &&
                    (!binding.explicit_cancel_requested || binding.expiry_preceded_cancel));
            require(!forced_execution);
            forced_execution = &binding;
            force_resident(binding.slot);
            forced_execution = nullptr;
        } else if (disposition == Finish::cancel_requested) {
            require(!binding.output_failed && binding.explicit_cancel_requested && !binding.expiry_preceded_cancel &&
                    endpoint.caller_cancelled && bound_client(binding));
            require(!forced_execution);
            forced_execution = &binding;
            force_resident(binding.slot);
            forced_execution = nullptr;
        } else {
            require(disposition == Finish::complete && !binding.output_failed && !residents[binding.slot].space);
        }
        endpoint.caller.reset();
        require(endpoint_owner.finish_client(binding.client));
        const U64 client = binding.client;
        binding.client = 0;
        if (!control_request(5, client)) {
            abandon_service();
            return Effect::failed;
        }
        return Effect::success;
    }
    static auto settled(const Binding &binding) -> bool {
        const auto endpoint_observation = endpoint_owner.observe();
        return !binding.client && !binding.output_pending && !binding.request_pending && !binding.input_pending &&
               !residents[binding.slot].space && !snapshot && !endpoint.caller && !endpoint_observation.delivery() &&
               !endpoint_observation.completion();
    }
};
class ExecutionPlatform final {
public:
#ifdef AURORA_PRODUCTION
    static auto capture_parent() -> aurora::resident::Parent {
        return resident_owner.capture_parent();
    }
    static auto parent_valid(aurora::resident::Parent parent) -> bool {
        return resident_owner.parent_valid(parent);
    }
    static auto release_parent(aurora::resident::Parent parent) -> void {
        resident_owner.release_parent(parent);
    }
#endif
    static auto quiet() -> bool {
        return Timer::irq_off() && root() == kernel_root && !running.space && !Timer::read(0x390) &&
               Timer::quiet(0x100, false) && Timer::quiet(0x200, false);
    }
    [[noreturn]] static auto fail() -> void {
        ::fail("execution grant");
    }
};

auto begin_service_shutdown() -> void {
    if (const auto endpoint_observation = endpoint_owner.observe();
        !residents[0].space || clients_live() || snapshot || endpoint.caller || endpoint_observation.replied() ||
        endpoint_observation.delivery() || endpoint_observation.completion() ||
        !service_root.begin_shutdown(endpoint.generation))
        fail("file service shutdown intent");
    // The preceding client is fully settled. This source-admitted shutdown is
    // a new caller context, not another message of the cancelled request.
    // Keep malformed-reply evidence; subsequent real expiry can set this bit.
    endpoint.caller_cancelled = false;
}
auto service_shutdown_selected() -> bool {
    return endpoint.generation && service_root.generation() == endpoint.generation &&
           service_root.phase() == aurora::service::Phase::retiring &&
           service_root.reason() == aurora::service::Reason::shutdown && service_root.detail() == 0;
}
auto finish_service_shutdown() -> void {
    const U64 generation = endpoint.generation;
    if (!generation || residents[0].space || clients_live() || !outcome.exited || outcome.status ||
        outcome.terminal_service != generation || running.service != generation ||
        outcome.terminal_run != running.run || !service_shutdown_selected())
        fail("file service normal terminal observation");
    endpoint.generation = 0;
    if (generation && !endpoint_owner.invalidate(generation))
        fail("endpoint invalidation");
    endpoint.caller.reset();
    acknowledge_service_cleanup(generation);
}

#ifndef AURORA_PRODUCTION
// Every legacy golden describes an independent namespace. Its companion is
// the same source service as production, with a fresh incarnation per case;
// only client ordinals stay stable. The admitted list has at most64 entries,
// so companion owners64+ordinal cannot alias any client owner in this boot.
auto start_companion(std::span<const std::byte> volume, U64 client) -> bool {
    if (client == 0 || client > 64 || residents[0].space || clients_live())
        return false;
    if (service_root.admit(0, true) != aurora::service::Action::start)
        return false;
    if (!endpoint_owner.reset())
        fail("endpoint fixture reset");
    endpoint = {};
    endpoint.generation = service_root.generation();
    if (!endpoint_owner.bind(endpoint.generation))
        fail("endpoint incarnation binding");
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
    while (residents[0].space && endpoint_owner.initial_step() == aurora::endpoint::Step::resume)
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
    if (!endpoint_owner.consume_control(endpoint_owner.observe().transaction))
        fail("endpoint control consumption");
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
    const auto client = residents[1].state.run;
    while (residents[1].space) {
        if (run_resident(1))
            break;
        if (outcome.output && !deliver_output())
            fail("fixture output delivery");
        if (outcome.request) {
            if (!client_request())
                return false;
            if (endpoint.caller_cancelled) {
                force_resident(1);
                break;
            }
        }
    }
    endpoint.caller.reset();
    if (!endpoint_owner.finish_client(client))
        fail("endpoint fixture client finalization");
    return true;
}
auto close_service_operation() -> void {
    if (const auto endpoint_observation = endpoint_owner.observe();
        clients_live() || snapshot || endpoint.caller || endpoint_observation.delivery() ||
        endpoint_observation.completion() || !audit_residents() || !service_root.close_operation())
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
        if (exchange_request(0) || residents[0].space || !outcome.exited || outcome.status ||
            !service_shutdown_selected()) {
            abandon_service();
            fail("companion shutdown");
        }
        finish_service_shutdown();
        if (!endpoint_owner.reset())
            fail("endpoint fixture reset");
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
        require(entry_ && !residents[1].space && !endpoint.caller && !endpoint_owner.observe().completion() &&
                !snapshot);
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

auto input_probe_reenter() -> void {
    if (!input_probe_lease || !input_probe_lease_generation)
        fail("input fixture reentry receipt");
    static_cast<void>(FixtureExecutionSession::advance(input_probe_lease, input_probe_lease_generation));
    fail("input fixture reentry returned");
}

// Drive the existing lease at real parked boundaries; no copied lifecycle.
auto execution_input_fixture(std::span<const std::byte> volume,
                             std::span<const std::byte> runs,
                             const process::RunEntry &entry,
                             U64 client) -> void {
    using namespace aurora::execution;
    using Session = FixtureExecutionSession;
    if (input_probe_case < 82 || input_probe_case > 97 || input_source || input_read.owner)
        fail("input fixture admission");
    input_read = {};
    input_probe_settlements = input_probe_completions = input_probe_samples = 0;
    input_probe_partial = false;
    input_source = input_probe_sample;
    FixtureExecutionTransport::bind(volume, runs, entry, client);
    const auto issuer = Session::open();
    const auto lease = Session::prepare(issuer.grant, issuer.generation);
    if (Session::preparation(lease.binding, lease.generation).state != Prepared::loaded)
        fail("input fixture load");
    input_probe_lease = lease.binding;
    input_probe_lease_generation = lease.generation;
    const bool raw = input_probe_case >= 89 && input_probe_case <= 93 && (input_probe_case != 90 || client == 3);
    if (raw) {
        if (input_probe_case == 90 && (input_probe_retired != client - 1 || input_probe_retired == 0))
            fail("input fixture stale epoch provenance");
        Serial::text("AURORA_INPUT_RAW:");
        field("case", input_probe_case);
        field("owner", client);
        field("prior_retired", input_probe_retired);
        Serial::text(" admitted=1\r\n");
    }
    Finish disposition = Finish::complete;
    for (;;) {
        const auto step = Session::advance(lease.binding, lease.generation);
        if (step.state == Step::retired)
            break;
        if (step.state == Step::input) {
            if (input_probe_case == 88) {
                if (!input_identity() || input_probe_completions ||
                    static_cast<Cancel>(Session::cancel(lease.binding, lease.generation)) != Cancel::settled ||
                    input_read.pending || input_read.owner || input_probe_completions)
                    fail("input fixture abort");
                disposition = Finish::cancel_requested;
                break;
            }
            if (Session::input(lease.binding, lease.generation) != static_cast<U64>(Effect::success))
                fail("input fixture delivery");
        } else if (step.state == Step::request) {
            for (;;) {
                const auto request = static_cast<Request>(Session::request(lease.binding, lease.generation));
                if (request == Request::pending)
                    continue;
                if (request != Request::ready)
                    fail("input fixture file request");
                break;
            }
        } else if (step.state != Step::parked) {
            fail("input fixture unexpected output");
        }
    }
    if (input_probe_case == 97) {
        const bool writer = client == 2 || client == 4;
        const U64 expected_status = client == 4 ? 1 : 0;
        if (client < 2 || client > 5 || !outcome.exited || outcome.status != expected_status ||
            input_probe_settlements || input_probe_partial ||
            (writer ? input_probe_samples != (client == 2 ? 16385 : 16386)
                    : input_probe_samples || input_probe_completions))
            fail("source writer boundary result");
    } else if (input_probe_case == 96) {
        if (input_probe_completions < 2 || !outcome.watchdog || outcome.terminal_ticks != 2)
            fail("input fixture original CPU budget");
    } else if (raw) {
        if (input_probe_completions || input_probe_samples || !outcome.invalid_call || outcome.operation != 21)
            fail("input fixture raw rejection");
    } else if (input_probe_case != 88 && (input_probe_completions != 4 || !outcome.exited || outcome.status))
        fail("input fixture consumer result");
    if (Session::finish(lease.binding, lease.generation, static_cast<U64>(disposition)) !=
        static_cast<U64>(Effect::success))
        fail("input fixture finish");
    Session::release(issuer);
    FixtureExecutionTransport::unbind();
    if (input_read.owner || input_read.pending || input_wait.active || residents[1].space || Timer::read(0x390) ||
        !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
        fail("input fixture cleanup");
    Serial::text("AURORA_INPUT_FINISHED:");
    field("case", input_probe_case);
    field("completed", input_probe_completions);
    field("settlements", input_probe_settlements);
    field("samples", input_probe_samples);
    field("partial", input_probe_partial);
    Serial::text(" quiet=1 retired=1\r\n");
    input_probe_retired = client;
    input_probe_lease = nullptr;
    input_probe_lease_generation = 0;
    input_source = nullptr;
    input_read = {};
}

// Fixture-only elapsed-clock gate at an authenticated, already-staged request.
// No process runs here and no effect loan survives Session::advance. Every
// charged count comes from the existing LAPIC; there is no synthetic expiry.
auto execution_expiry_gate(U64 client) -> void {
    using namespace aurora::lifecycle;
    if (const auto endpoint_observation = endpoint_owner.observe();
        execution_owner.entered() || forced_execution || completed_output || !LifecyclePlatform::quiet() ||
        !residents[0].space || !residents[1].space || residents[1].state.run != client ||
        endpoint.caller != std::optional<std::size_t>{1} || endpoint.caller_cancelled ||
        !endpoint_observation.waiting() || endpoint_observation.replied() || endpoint_observation.delivery() ||
        endpoint_observation.completion() || snapshot || loading_image ||
        service_root.phase() != aurora::service::Phase::ready || service_root.generation() != endpoint.generation ||
        residents[0].state.service != endpoint.generation || execution_owner.phase(0) != Phase::parked ||
        execution_owner.phase(1) != Phase::parked || execution_owner.pending(1) != static_cast<U64>(Event::request) ||
        endpoint.call.action != static_cast<U64>(process::CallAction::write) || endpoint.call.length != 65536 ||
        endpoint.written >= endpoint.call.length || !residents[1].budget.available())
        fail("execution expiry gate admission");
    authenticate_stopped_frame(1, true);
    if (residents[1].state.budget != &residents[1].budget || !residents[1].state.external ||
        residents[1].initial[4] != table.activation_root(1, residents[1].space->epoch()) ||
        residents[0].initial[4] != table.activation_root(0, residents[0].space->epoch()))
        fail("execution expiry physical binding");
    const auto generation = endpoint.generation, transaction = endpoint_owner.observe().transaction,
               next = endpoint_owner.observe().next;
    const auto written = endpoint.written, count = endpoint.count, source = endpoint_owner.observe().source;
    const auto client_generation = execution_owner.generation(1), server_generation = execution_owner.generation(0);
    const auto client_epoch = residents[1].space->epoch(), client_root = residents[1].space->root();
    const auto server_epoch = residents[0].space->epoch(), server_root = residents[0].space->root();
    const auto client_frame = residents[1].continuation, server_frame = residents[0].continuation;
    const auto server_used = residents[0].budget.used(), server_quantum = residents[0].budget.quantum();
    Serial::text("AURORA_EXECUTION_EXPIRY_GATE:");
    field("client", client);
    field("generation", generation);
    field("transaction", transaction);
    field("next", next);
    field("used", residents[1].budget.used());
    Serial::text(" staged=1\r\n");
    U64 quanta = 0, counts = 0;
    while (residents[1].budget.available()) {
        if (++quanta > 8 || !LifecyclePlatform::quiet())
            fail("execution expiry clock bound");
        const auto armed = residents[1].budget.quantum();
        if (!armed || armed > 0xffffffffULL || !Timer::arm(static_cast<std::uint32_t>(armed)))
            fail("execution expiry clock arm");
        // Wait for the actual clock boundary, not a fixed host-time delay.
        while (Timer::read(0x390) || !Timer::pending())
            asm volatile("pause");
        const auto remaining = Timer::read(0x390);
        if (!Timer::stop() || remaining > armed || !Timer::pending())
            fail("execution expiry clock stop");
        const auto measured = armed - remaining;
        if (!measured || counts > ~U64{0} - measured)
            fail("execution expiry measured counts");
        counts += measured;
        const bool available = charge_counts(residents[1].budget, measured, false);
        draining = true;
        process_drain();
        if (draining || !LifecyclePlatform::quiet())
            fail("execution expiry clock drain");
        if (!available)
            endpoint.caller_cancelled = true;
    }
    if (const auto endpoint_observation = endpoint_owner.observe();
        !endpoint.caller_cancelled || !residents[0].space || !residents[1].space || residents[1].state.run != client ||
        endpoint.generation != generation || endpoint_observation.transaction != transaction ||
        endpoint_observation.next != next || endpoint.written != written || endpoint.count != count ||
        endpoint_observation.source != source || endpoint.call.action != static_cast<U64>(process::CallAction::write) ||
        endpoint.call.length != 65536 || endpoint.caller != std::optional<std::size_t>{1} ||
        !endpoint_observation.waiting() || endpoint_observation.replied() || endpoint_observation.delivery() ||
        endpoint_observation.completion() || execution_owner.generation(1) != client_generation ||
        execution_owner.generation(0) != server_generation || execution_owner.phase(0) != Phase::parked ||
        execution_owner.phase(1) != Phase::parked || execution_owner.pending(1) != static_cast<U64>(Event::request) ||
        residents[1].space->epoch() != client_epoch || residents[1].space->root() != client_root ||
        residents[0].space->epoch() != server_epoch || residents[0].space->root() != server_root ||
        residents[1].continuation != client_frame || residents[0].continuation != server_frame ||
        residents[0].budget.used() != server_used || residents[0].budget.quantum() != server_quantum)
        fail("execution expiry gate preservation");
    Serial::text("AURORA_EXECUTION_EXPIRY_DRAINED:");
    field("client", client);
    field("generation", generation);
    field("transaction", transaction);
    field("next", next);
    field("quanta", quanta);
    field("counts", counts);
    field("used", residents[1].budget.used());
    Serial::text(" expired=1 drained=1 closed=1\r\n");
}

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
    bool observed = false, request = false, expiry_gated = false;
    U64 drain_transaction = 0, drain_next = 0, drain_used = 0, drain_quantum = 0;
    Finish disposition = Finish::complete;
    if (prepared.state == Prepared::loaded && point == 4) {
        if (execution_owner.phase(1) != aurora::lifecycle::Phase::prepared ||
            static_cast<Cancel>(Session::cancel(lease.binding, lease.generation)) != Cancel::settled)
            fail("execution prepared cancellation");
        observed = true;
        disposition = Finish::cancel_requested;
        Serial::text("AURORA_EXECUTION_CANCEL:");
        field("client", client);
        field("tail", point);
        field("generation", endpoint.generation);
        field("transaction", endpoint_owner.observe().transaction);
        field("next", endpoint_owner.observe().next);
        Serial::text("\r\n");
    }
    if (prepared.state == Prepared::loaded && point != 4) {
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
            const bool staged = endpoint_owner.observe().waiting() && !endpoint_owner.observe().replied() &&
                                !endpoint_owner.observe().delivery();
            const bool write =
                endpoint.call.action == static_cast<U64>(process::CallAction::write) && endpoint.call.length == 65536;
            const bool boundary = point == 2
                                      ? !endpoint_owner.observe().waiting() && !endpoint_owner.observe().replied() &&
                                            !endpoint_owner.observe().delivery()
                                      : write && staged &&
                                            (point == 1 ? endpoint.written == endpoint.call.length
                                                        : endpoint.written < endpoint.call.length);
            if (point == 3 && boundary && !expiry_gated) {
                execution_expiry_gate(client);
                expiry_gated = true;
            }
            if (point != 3 && boundary && !observed) {
                const U64 generation = endpoint.generation, transaction = endpoint_owner.observe().transaction,
                          next = endpoint_owner.observe().next;
                const U64 used = residents[0].state.budget->used();
                const U64 quantum = residents[0].state.budget->quantum();
                const bool available = residents[0].state.budget->available();
                const bool was_waiting = endpoint_owner.observe().waiting();
                const auto cancelled = static_cast<Cancel>(Session::cancel(lease.binding, lease.generation));
                if (const auto endpoint_observation = endpoint_owner.observe();
                    cancelled != (point == 2 ? Cancel::draining : Cancel::settled) ||
                    endpoint.generation != generation || endpoint_observation.transaction != transaction ||
                    endpoint_observation.next != next || endpoint_observation.waiting() != was_waiting ||
                    endpoint_observation.replied() || endpoint_observation.delivery() ||
                    (point == 2 ? endpoint.caller != std::optional<std::size_t>{1} : endpoint.caller.has_value()) ||
                    endpoint_observation.completion() || residents[0].state.budget->used() != used ||
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
                    if (const auto endpoint_observation = endpoint_owner.observe();
                        endpoint_observation.transaction != drain_transaction ||
                        endpoint_observation.next != drain_next || !consumed ||
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
            if (point == 3 && result == Request::cancelled) {
                if (!expiry_gated || !endpoint.caller_cancelled || endpoint.caller ||
                    endpoint_owner.observe().completion() || residents[1].budget.available() ||
                    static_cast<Cancel>(Session::cancel(lease.binding, lease.generation)) !=
                        Cancel::settled_after_expiry)
                    fail("execution prior expiry evidence");
                observed = true;
                Serial::text("AURORA_EXECUTION_CANCEL:");
                field("client", client);
                field("tail", point);
                field("generation", endpoint.generation);
                field("transaction", endpoint_owner.observe().transaction);
                field("next", endpoint_owner.observe().next);
                Serial::text("\r\n");
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
    // The real source-selected terminal record is checked by the guest oracle;
    // finish's later service close legitimately replaces the shared report.
    if (point == 3 && disposition != Finish::cancelled)
        fail("execution prior expiry finalization");
    if (point == 4 && disposition != Finish::cancel_requested)
        fail("execution prepared cancellation finalization");
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
    if (residents[0].space || clients_live() || !service_root.open_operation())
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
        if (!endpoint_owner.reset())
            fail("endpoint fixture reset");
        endpoint = {};
        endpoint.generation = service_root.generation();
        if (!endpoint_owner.bind(endpoint.generation))
            fail("endpoint incarnation binding");
        if (!load_one(view, runs, *service, first + 1, 0, true, true, endpoint.generation, disk))
            fail("file service load");
        while (residents[0].space && endpoint_owner.initial_step() == aurora::endpoint::Step::resume)
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
        if (input_probe_case) {
            execution_input_fixture(view, runs, *entry, count);
            continue;
        }
        const auto arguments = runs.subspan(entry->arguments, entry->argument_bytes);
        constexpr std::string_view initial_cancel{"raw-cancel-initial\0", 19};
        constexpr std::string_view tail_cancel{"raw-cancel-tail\0", 16};
        constexpr std::string_view before_cancel{"raw-cancel-before\0", 18};
        constexpr std::string_view expired_cancel{"raw-cancel-expired\0", 19};
        const auto matches = [&](std::string_view name) {
            if (arguments.size() != name.size())
                return false;
            for (U64 at = 0; at < arguments.size(); ++at)
                if (arguments[at] != std::byte(static_cast<unsigned char>(name[at])))
                    return false;
            return true;
        };
        const bool initial = matches(initial_cancel), tail = matches(tail_cancel);
        const bool before = matches(before_cancel), expired = matches(expired_cancel);
        if (initial || tail || before || expired || cancel_delivered) {
            const U64 point = before ? 4 : expired ? 3 : cancel_delivered ? 2 : tail ? 1 : 0;
            if (!execution_cancel_fixture(view, runs, *entry, count, point)) {
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
    if (exchange_request(0) || residents[0].space || !outcome.exited || outcome.status ||
        !service_shutdown_selected()) {
#ifdef AURORA_PROCESS_FIXTURE
        if (mounted_confirmation_probe) {
            if (!mounted_confirmation_corrupted || residents[0].space || !outcome.exited || !outcome.status ||
                service_shutdown_selected())
                fail("mounted confirmation shutdown failure");
            mounted_confirmation_shutdown_failed = true;
        }
#endif
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
    field("transactions", endpoint_owner.observe().next);
    Serial::text("\r\n");
    return count;
}

#ifdef AURORA_UEFI_NVME
// Only the recovery fixture cases call this private composition. Its first admitted boot
// image is the recovery program; a pathname, argv or ELF type never mints it.
auto run_recovery(std::span<const std::byte> view, std::span<const std::byte> runs) -> bool {
    const auto entry = process::run(runs, 0);
    const auto baseline = table.free();
    if (!entry || !entry->found || residents[0].space || clients_live() || endpoint.generation || recovery_generation ||
        recovery_completed || !aurora::uefi::nvme_recovery_sector_count())
        fail("recovery composition");
    if (!load_one(view, runs, *entry, 1, 0, true, true))
        return false;
    return finish_recovery(baseline);
}
#endif

#ifdef AURORA_PROCESS_FIXTURE
// Fatal admission cases share the ordinary lifecycle programs and source
// lifecycle. One-shot adapters corrupt effect operands or an actual endpoint
// source leaf, never source banks or phase fields.
[[noreturn]] auto authority_lifetime_probe(std::span<const std::byte> view, U64 probe) -> void {
    if (probe == 50 || probe == 52 || probe == 53 || probe == 54) {
        const auto runs = process::volume_lookup(view, bytes_of("runs/7"));
        if (!runs || process::runs_admit(*runs) != process::RunsVerdict::valid)
            fail("mapping authority probe runs");
        const U64 count = probe == 50 ? 2 : 1;
        for (U64 slot = 0; slot < count; ++slot) {
            const auto entry = process::run(*runs, slot);
            if (!entry || !entry->found || !load_one(view, *runs, *entry, slot + 1, slot, true))
                fail("mapping authority probe load");
        }
    }
    if (probe == 50 || probe == 54) {
        const U64 slot = probe == 50 ? 1 : 0;
        auto &resident = *residents[slot].space;
        constexpr U64 bytes = 16 * frames::page;
        const auto reservation = resident.map_memory(bytes);
        if (reservation.outcome != ProcessSpace::Outcome::resume || !resident.commit(reservation.value))
            fail("mapping authority probe commit");
        if (probe == 50) {
            const U64 admitted_root = table.activation_root(0, residents[0].space->epoch());
            asm volatile("mov %0, %%cr3" : : "r"(admitted_root) : "memory");
        }
        authority_probe_pending = probe;
        static_cast<void>(resident.unmap_memory(reservation.value, bytes));
        __builtin_trap();
    }
    if (probe == 53) {
        authority_probe_pending = probe;
        static_cast<void>(residents[0].space->verify());
        __builtin_trap();
    }
    constexpr std::array<std::byte, 16> chunk{};
    for (U64 at = 0; at < chunk.size(); ++at)
        endpoint.bytes[64 + at] = chunk[at];
    const U64 epoch = table.begin_snapshot(frames::first_owner + 2, frames::page);
    if (!epoch || !table.fill_snapshot(epoch, 0, 64, chunk.size()))
        fail("mapping authority probe snapshot");
    if (probe == 80 || probe == 81) {
        // Preserve the actual frame's address, owner and generation. Change
        // only a payload leaf permission after a successful ordinary fill.
        const U64 directory = KernelSpace::table_view(0)[2] & KernelSpace::address_mask;
        auto *words = space.open(directory);
        if (!words)
            fail("snapshot leaf probe directory");
        const U64 table_physical = reinterpret_cast<volatile U64 *>(words)[0] & KernelSpace::address_mask;
        space.close();
        words = space.open(table_physical);
        if (!words)
            fail("snapshot leaf probe table");
        auto &leaf = reinterpret_cast<volatile U64 *>(words)[0];
        leaf = leaf & ~(probe == 80 ? U64{2} : (U64{1} << 63));
        space.close();
        // From this boundary, fill must perform two authenticated table-read
        // windows, then reject before opening the third (payload) window.
        arm_authority_probe(probe);
        static_cast<void>(table.fill_snapshot(epoch, 0, 64, chunk.size()));
        __builtin_trap();
    }
    if (probe >= 73 && probe <= 79) {
        if (probe == 79) {
            // Exercise the last byte and every partial source page before
            // refusing a second registration of this same static object.
            if (!table.discard_snapshot(epoch))
                fail("loader source positive discard");
            for (U64 at = 0; at < endpoint.bytes.size(); ++at)
                endpoint.bytes[at] = std::byte((at * 13 + 7) & 255);
            const U64 whole = table.begin_snapshot(frames::first_owner + 2, endpoint.bytes.size());
            if (!whole || !table.fill_snapshot(whole, 0, 0, endpoint.bytes.size()) || !table.seal_snapshot(whole))
                fail("loader source positive fill");
            {
                auto pin = table.snapshot_read(whole);
                const auto copied = pin.bytes();
                for (U64 at = 0; at < endpoint.bytes.size(); ++at)
                    if (copied[at] != endpoint.bytes[at])
                        fail("loader source positive bytes");
            }
            if (!table.discard_snapshot(whole))
                fail("loader source positive release");
            Serial::text("AURORA_LOADER_SOURCE_COPY_OK: bytes=65536\r\n");
            arm_authority_probe(probe);
            aurora::uefi::register_loader_source(table);
            __builtin_trap();
        }
        if (probe <= 75) {
            const U64 first = probe == 73 ? endpoint.bytes.size() : probe == 74 ? ~U64{0} : 1;
            const U64 count = probe == 75 ? ~U64{0} : 1;
            arm_authority_probe(probe);
            static_cast<void>(table.fill_snapshot(epoch, 0, first, count));
            __builtin_trap();
        }
        // Corrupt only an interior endpoint-buffer page's actual leaf. The
        // requested two-byte source straddles that page boundary; checking only
        // its first page would miss this malformed last partial page.
        const U64 base = reinterpret_cast<U64>(endpoint.bytes.data());
        const U64 page = (base + 2 * frames::page) & ~U64{4095};
        U64 current = kernel_root;
        for (const unsigned shift : {39U, 30U, 21U})
            current = reinterpret_cast<volatile U64 *>(current)[(page >> shift) & 511] & KernelSpace::address_mask;
        auto &leaf = reinterpret_cast<volatile U64 *>(current)[(page >> 12) & 511];
        const auto managed = ranges.address(0);
        if (!managed)
            fail("loader source alias fixture");
        leaf = probe == 76   ? 0
               : probe == 77 ? page | KernelSpace::data_flags | 128
                             : *managed | KernelSpace::data_flags;
        asm volatile("invlpg (%0)" : : "r"(page) : "memory");
        arm_authority_probe(probe);
        static_cast<void>(table.fill_snapshot(epoch, 0, page - base - 1, 2));
        __builtin_trap();
    }
    if (probe != 57 && !table.seal_snapshot(epoch))
        fail("mapping authority probe seal");
    if (probe == 51 || probe == 52) {
        auto pin = table.snapshot_read(epoch);
        if (pin.bytes().size() != frames::page)
            fail("mapping authority probe parser pin");
        arm_authority_probe(probe);
        if (probe == 51)
            static_cast<void>(table.discard_snapshot(epoch));
        else
            static_cast<void>(table.activation_root(0, residents[0].space->epoch()));
        __builtin_trap();
    }
    if (probe == 55) {
        arm_authority_probe(probe);
        static_cast<void>(table.fill_snapshot(epoch, 0, 64, chunk.size()));
        __builtin_trap();
    }
    if (probe == 56) {
        if (!table.discard_snapshot(epoch))
            fail("mapping authority probe discard");
        const U64 next = table.begin_snapshot(frames::first_owner + 2, frames::page);
        if (next != epoch + 1 || !table.fill_snapshot(next, 0, 64, chunk.size()) || !table.seal_snapshot(next))
            fail("mapping authority probe reuse");
    }
    if (probe == 56 || probe == 57) {
        arm_authority_probe(probe);
        auto pin = table.snapshot_source(epoch);
        __builtin_trap();
    }
    if (probe == 58) {
        auto pin = table.snapshot_source(epoch);
        arm_authority_probe(probe);
        static_cast<void>(table.discard_snapshot(epoch));
        __builtin_trap();
    }
    if (probe >= 59 && probe <= 62) {
        // A copied region is only input policy data, never effect authority.
        // Use a valid building target so each refusal tests the pin boundary.
        const U64 owner = frames::first_owner + (probe == 59 ? 1 : 2);
        const U64 target_epoch = table.prepare_load(0, owner, 128, 32);
        if (!target_epoch)
            fail("mapping authority probe target");
        const process::ProcessRegion region{1, 0x400000, 1, process::leaf_read, 0x400000, 0, chunk.size()};
        if (probe == 60) {
            auto pin = table.snapshot_read(epoch);
            arm_authority_probe(probe);
            static_cast<void>(table.map_region(0, target_epoch, region, 1));
            __builtin_trap();
        }
        if (probe == 61) {
            auto pin = table.arguments_source(chunk);
            arm_authority_probe(probe);
            static_cast<void>(table.map_region(0, target_epoch, region, 1));
            __builtin_trap();
        }
        auto pin = table.snapshot_source(epoch);
        if (probe == 59)
            arm_authority_probe(probe);
        else
            authority_probe_pending = probe;
        static_cast<void>(table.map_region(0, target_epoch, region, 1));
        __builtin_trap();
    }
    fail("mapping authority probe selection");
}
#endif

// The row's run list, runs/<case> in the volume, run in order.
[[noreturn]] auto run_list(U64 arena, std::span<const std::byte> view, U64 selected) -> void {
    U64 run_case = selected;
#ifdef AURORA_PROCESS_FIXTURE
    if (selected >= 82 && selected <= 97)
        input_probe_case = selected;
    if (selected >= 99 && selected <= 101) {
        presentation_probe_case = selected;
        presentation_sink = presentation_probe;
        output_sink = presentation_probe_output;
    }
    if (selected >= 64 && selected <= 71) {
        execution_probe_case = selected;
        run_case = selected == 69 || selected == 71 ? 1 : 3;
        if (selected == 69 || selected == 71)
            output_sink = execution_output_probe;
    }
    if (selected == 63) {
        nested_fault_probe = true;
        run_case = 3;
    }
    if (selected == 43) {
        frame_finish_fault = true;
        run_case = 3;
    }
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
    if (selected == 72)
        mounted_prepared_refusal = true;
    if (selected == 98) {
        mounted_confirmation_probe = true;
        run_case = 17;
    }
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
#ifdef AURORA_PROCESS_FIXTURE
    if (selected == 72) {
        // Exercise the real bootstrap failure before it has bound an endpoint,
        // first with an absent owner and again with a prior revoked receipt.
        const auto saturated_start = [&](U64 point) {
            const auto before = endpoint_owner.observe();
            const auto free = table.free(), service = service_root.generation();
            const auto server = execution_owner.generation(0), client = execution_owner.generation(1);
            const auto saved_next = next_run;
            next_run = 0xffffffffULL - frames::first_owner;
            if (!service_root.open_operation() || ensure_file_service(view))
                fail("unbound saturated bootstrap admission");
            const auto after = endpoint_owner.observe();
            if (before.incarnation != after.incarnation || before.phase != after.phase || before.next != after.next ||
                before.transaction != after.transaction || before.source != after.source ||
                before.client != after.client || endpoint.generation || endpoint.caller || residents[0].space ||
                clients_live() || snapshot || loading_image || service_root.phase() != aurora::service::Phase::absent ||
                service_root.generation() != service + 1 || execution_owner.generation(0) != server ||
                execution_owner.generation(1) != client ||
                execution_owner.phase(0) != aurora::lifecycle::Phase::empty ||
                execution_owner.phase(1) != aurora::lifecycle::Phase::empty ||
                next_run != 0xffffffffULL - frames::first_owner || table.free() != free || !audit_residents() ||
                !LifecyclePlatform::quiet())
                fail("unbound saturated bootstrap cleanup");
            close_service_operation();
            next_run = saved_next;
            Serial::text("AURORA_ENDPOINT_UNBOUND_REFUSAL:");
            field("point", point);
            field("service", service_root.generation());
            field("endpoint", after.incarnation);
            field("phase", static_cast<U64>(after.phase));
            field("next", after.next);
            field("transaction", after.transaction);
            field("source", after.source);
            field("client", after.client);
            field("free", table.free());
            Serial::text(" unchanged=1 closed=1\r\n");
        };
        saturated_start(0);
        const auto baseline = table.free();
        const auto generation = execution_owner.generation(0);
        if (!service_root.open_operation() || !runtime_storage.select(true, 3) || ensure_file_service(view))
            fail("mounted prepared refusal startup");
        if (const auto endpoint_observation = endpoint_owner.observe();
            residents[0].space || clients_live() || snapshot || endpoint.generation || endpoint.caller ||
            endpoint_observation.waiting() || endpoint_observation.replied() || endpoint_observation.delivery() ||
            endpoint_observation.completion() || loading_image ||
            service_root.phase() != aurora::service::Phase::absent ||
            execution_owner.phase(0) != aurora::lifecycle::Phase::empty ||
            execution_owner.phase(1) != aurora::lifecycle::Phase::empty ||
            execution_owner.generation(0) != generation + 1 || mounted_owner || mounted_root || mounted_generation ||
            mounted_sectors || mounted_service || block_service || block_generation || block_sectors ||
            recovery_owner || recovery_root || recovery_generation || recovery_sectors || !LifecyclePlatform::quiet() ||
            table.free() != baseline || !audit_residents())
            fail("mounted prepared refusal cleanup");
        for (const auto &resident : residents) {
            for (const auto word : resident.initial)
                if (word)
                    fail("mounted prepared initial scrub");
            for (const auto word : resident.continuation)
                if (word)
                    fail("mounted prepared saved scrub");
        }
        close_service_operation();
        Serial::text("AURORA_MOUNTED_PREPARED_CLEANUP:");
        field("execution", execution_owner.generation(0));
        field("free", table.free());
        Serial::text(" phases=empty roles=empty scrubbed=1 audited=1 closed=1\r\n");
        saturated_start(1);
        count = 1;
    }
#endif
    if ((selected >= 1 && selected <= 6) || selected == 43 || selected == 44 || (selected >= 63 && selected <= 71))
        count = run_independent(view, *runs);
    if (selected == 8 || (selected >= 82 && selected <= 97) || (selected >= 99 && selected <= 101))
        count = run_external(view, *runs);
    if (selected == 10) {
        const auto baseline = table.free();
        count = run_external(view, *runs, true, 0, 2, true);
        if (count != 2 || residents[0].space || clients_live() || endpoint.generation || table.free() != baseline ||
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
    if ((run_case == 17 || run_case == 39) && selected != 98)
        count = run_external(view, *runs, true, 0, ~U64{0}, false, XfsReadonlyProfile::linux_6_12_x86_64_clean, true);
#if defined(AURORA_PROCESS_FIXTURE) && defined(AURORA_UEFI_NVME)
    if (selected == 98) {
        const auto baseline = table.free();
        count = run_external(view, *runs, true, 0, ~U64{0}, true, XfsReadonlyProfile::linux_6_12_x86_64_clean, true);
        if (!mounted_confirmation_corrupted || !mounted_confirmation_shutdown_failed || residents[0].space ||
            residents[1].space || endpoint.generation || mounted_generation || mounted_owner || mounted_root ||
            mounted_service || block_generation || block_service || aurora::uefi::nvme_mounted_readonly() ||
            aurora::uefi::nvme_sector_count() || service_root.phase() != aurora::service::Phase::absent ||
            table.free() != baseline || !audit_residents())
            fail("mounted confirmation failure cleanup");
        for (const auto &resident : residents) {
            for (const auto word : resident.continuation)
                if (word)
                    fail("mounted confirmation continuation scrub");
            for (const auto word : resident.initial)
                if (word)
                    fail("mounted confirmation initial scrub");
        }
        Serial::text("AURORA_MOUNTED_CONFIRM_CLEANUP: shutdown_failed=1 reclaimed=1 readonly=0 scrubbed=1\r\n");
    }
#endif
    if (selected == 40) {
        const auto baseline = table.free();
        count = run_external(view, *runs, true, 0, 2, true, XfsReadonlyProfile::linux_6_12_x86_64_clean, true);
        if (count != 2 || residents[0].space || clients_live() || endpoint.generation || mounted_generation ||
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
            if (count != end || residents[0].space || clients_live() || endpoint.generation ||
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
        const auto width = paired ? 2U : 1U; // Existing two-task fixture, not the production pair.
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
#ifdef AURORA_PROCESS_FIXTURE
    if (presentation_probe_case) {
        if (presentation_probe_case != 99 || presentation_probe_passes != 1 || residents[0].space ||
            residents[1].space || !audit_residents())
            fail("presentation fixture final restoration");
        Serial::text("AURORA_PRESENTATION_RESTORED: passes=1 reclaimed=1\r\n");
    }
#endif
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
    kernel_table_pages = h.get(96);
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
    physical_bits = width;
    const auto &last = ranges.range(ranges.count() - 1);
    if (width < 32 || width > 52 || (last.first_page + last.pages) * frames::page > (U64{1} << width) ||
        volume + volume_pages * frames::page > (U64{1} << width))
        fail("frame inventory beyond the physical width");
    const auto record_pages = KernelSpace::process_pages * KernelSpace::process_slots;
    const auto plan = KernelSpace::plan(ranges.frames(), volume_pages, record_pages);
    const PageTables tables{arena + Handoff::tables_offset, static_cast<std::size_t>(h.get(96))};
    if (!plan || !space.bind(arena + Handoff::tables_offset, tables.window_slot()) ||
        !space.build(ranges, *plan, volume))
        fail("kernel space");
    if (!space.handoff_manager(table, ranges))
        fail("memory manager bank set");
    if (!space.verify(table, ranges, h.get(96)))
        fail("kernel space walk");
    Serial::text("AURORA_PROCESS_FRAMES:");
    field("frames", table.frames());
    field("ranges", ranges.count());
    field("tables", plan->tables);
    field("metadata", plan->metadata);
    field("free", table.free());
    Serial::text("\r\n");
    const auto banks = KernelSpace::bank_layout(*plan, ranges.frames());
    if (!banks)
        fail("memory manager backing layout");
    Serial::text("AURORA_MEMORY_BANK_SET:");
    field("allocation_word", banks->word_offsets[0]);
    field("allocation_words", banks->word_counts[0]);
    field("mapping_word", banks->word_offsets[1]);
    field("mapping_words", banks->word_counts[1]);
    field("reservations_word", banks->word_offsets[2]);
    field("reservations_words", banks->word_counts[2]);
    field("scratch_word", banks->word_offsets[3]);
    field("scratch_words", banks->word_counts[3]);
    field("tail_word", banks->tail_offset);
    field("tail_words", banks->tail_words);
    field("metadata_words", banks->metadata_words);
    field("tail_pages", plan->reservation_tail);
    field("scratch_pages", plan->scratch);
    Serial::text("\r\n");
    process_volume_bytes = bytes;
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
    if (selected) {
        service_root.create();
        endpoint_owner.create();
    }
    return view;
}
} // namespace

#ifndef AURORA_PRODUCTION
auto aurora::uefi::run_process(U64 arena, const Bytes &h) -> void {
#ifdef AURORA_PROCESS_FIXTURE
    presentation_handoff = &h;
#endif
    const auto selected = h.get(Handoff::case_word);
    const auto view = initialize_process(arena, h, selected, false);
#ifdef AURORA_PROCESS_FIXTURE
    if (selected == 42) {
        install_architecture(arena);
        capture_shared(arena);
        process_kernel_root = kernel_root;
        if (!table.allocate(probe_owner))
            fail("frame require fixture allocation");
        Serial::text("AURORA_FRAME_REQUIRE_PROBE: context=kernel");
        field("root", root());
        field("kernel", kernel_root);
        Serial::text("\r\n");
        static_cast<void>(table.finish());
        fail("frame require returned");
    }
    if (selected >= 45 && selected <= 49) {
        install_architecture(arena);
        capture_shared(arena);
        process_kernel_root = kernel_root;
        Serial::text("AURORA_MAPPING_AUTHORITY_PROBE:");
        field("case", selected);
        field("root", root());
        field("kernel", kernel_root);
        field("closed", space.closed());
        Serial::text("\r\n");
        aurora::uefi::MappingAuthority::fixture_admission(selected);
        fail("mapping authority probe returned");
    }
    if ((selected >= 50 && selected <= 62) || (selected >= 73 && selected <= 81)) {
        install_architecture(arena);
        capture_shared(arena);
        process_kernel_root = kernel_root;
        authority_lifetime_probe(view, selected);
    }
#endif
    if (selected)
        run_list(arena, view, selected);
    frame_cases(h.get(96));
    space_cases(*runtime_plan, h.get(96));
    export_entry(view, exported);
    if (execution_owner.created() && !execution_owner.finish())
        fail("execution owner finalization");
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
    if (!endpoint_owner.consume_control(endpoint_owner.observe().transaction))
        fail("endpoint control consumption");
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
    if (residents[0].space || clients_live() || endpoint.generation || recovery_generation || recovery_completed)
        fail("recovery preparation ownership");
    if (!image || next_run >= 0xffffffffULL - frames::first_owner || !aurora::uefi::nvme_recovery_sector_count() ||
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
                    std::span<const std::byte> arguments,
                    std::size_t slot = 1,
                    U64 growth_quota = 0) -> RunStatus {
    using aurora::load::Action;
    using aurora::load::Result;
    reset_loader(128);
    loading_image = true;
    endpoint.caller_cancelled = false;
    aurora::load::Operation<EndpointPlatform> operation;
    for (;;) {
        const auto request = operation.next();
        bool ok = true;
        U64 status = 0, value = 0, count = 0;
        switch (request.action) {
        case Action::open:
            ok = loader_call(client, 18, 0, 0, path);
            if (ok) {
                const Bytes reply{endpoint.bytes};
                status = reply.get(0);
                value = reply.get(16);
                count = reply.get(24);
            }
            break;
        case Action::reserve: {
            const U64 epoch = table.begin_snapshot(frames::first_owner + client, request.size);
            ok = epoch != 0;
            if (ok)
                snapshot.emplace(table, epoch);
            break;
        }
        case Action::read:
            ok = loader_call(client, 19, request.id, request.offset);
            if (ok) {
                const Bytes reply{endpoint.bytes};
                status = reply.get(0);
                count = reply.get(8);
            }
            break;
        case Action::fill:
            // A copied source request is not byte or snapshot authority. Recheck
            // the current reply and exact manager-owned epoch at the copy edge.
            if (!snapshot || Bytes{endpoint.bytes}.get(0) || Bytes{endpoint.bytes}.get(8) != request.count ||
                request.count > endpoint.bytes.size() - 64 || !snapshot->fill(request.offset, 64, request.count))
                fail("loader snapshot fill");
            break;
        case Action::seal:
            if (!snapshot || !snapshot->seal())
                fail("loader snapshot seal");
            break;
        case Action::discard_close:
        case Action::discard_done:
            // Service terminal invalidation may already have discarded it.
            discard_snapshot();
            break;
        case Action::close:
            ok = loader_call(client, 20, request.id);
            if (ok) {
                status = Bytes{endpoint.bytes}.get(0);
                if (!status)
                    loading_image = false;
            }
            break;
        case Action::load: {
            if (!snapshot)
                fail("loader snapshot identity");
            process::RunEntry entry{};
            entry.ticks = 128;
            entry.quota = growth_quota;
            ok = load_image(
                volume, {}, arguments, entry, client, slot, true, true, 0, false, 0, false, snapshot->epoch());
            if (!ok) {
                status = load_refusal == RunStatus::missing ? static_cast<U64>(Result::missing)
                         : load_refusal == RunStatus::quota ? static_cast<U64>(Result::quota)
                                                            : static_cast<U64>(Result::malformed);
            }
            break;
        }
        case Action::done:
            switch (request.result) {
            case Result::loaded:
                return RunStatus::exited; // Loaded, not yet executed.
            case Result::missing:
                return RunStatus::missing;
            case Result::malformed:
                return RunStatus::malformed;
            case Result::quota:
                return RunStatus::quota;
            case Result::unavailable:
                return RunStatus::unavailable;
            }
            fail("loader result");
        default:
            fail("loader action");
        }
        if (!operation.accept(request.action, ok, status, value, count))
            fail("loader observation");
    }
}

class ExecutionTransport final : public ExecutionEffects {
    static inline std::span<const std::byte> volume_, path_, arguments_;

public:
    static auto bind(std::span<const std::byte> volume,
                     std::span<const std::byte> path,
                     std::span<const std::byte> arguments) -> void {
        require(volume_.empty() && !clients_live());
        volume_ = volume;
        path_ = path;
        arguments_ = arguments;
    }
    static auto unbind() -> void {
        require(!residents[1].space && !endpoint.caller && !endpoint_owner.observe().completion() && !snapshot);
        volume_ = path_ = arguments_ = {};
    }
    static auto prepare(Binding &binding) -> aurora::execution::Preparation {
        using namespace aurora::execution;
        require(!volume_.empty() && !binding.client && !clients_live());
        if (!ensure_file_service(volume_)) {
            if (service_root.phase() != aurora::service::Phase::absent)
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
    if (execution_owner.entered() || !Timer::irq_off() || root() != handoff.get(88) || running.space ||
        clients_live() || snapshot || Timer::read(0x390) || !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false))
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
        if (!space.resume_manager(table, ranges, handoff.get(96)))
            fail("frame metadata reattachment");
        runtime_detached = false;
        if (!space.verify(table, ranges, handoff.get(96)) || !audit_residents())
            fail("process runtime attachment audit");
    }
    install_architecture(arena);
    prepare_recovery(space.volume(handoff.get(Handoff::volume_bytes_word)));
    if (!resident_owner.created())
        resident_owner.initialize();
    if (!resident_owner.active())
        fail("retired resident owner");
    if (!service_root.open_operation())
        fail("file service operation admission");
    return true;
}
auto leave_runtime(const Bytes &handoff) -> void {
    if (const auto endpoint_observation = endpoint_owner.observe();
        execution_owner.entered() || running.space || clients_live() || snapshot || endpoint.caller ||
        endpoint_observation.delivery() || endpoint_observation.completion() || Timer::read(0x390) ||
        !Timer::quiet(0x100, false) || !Timer::quiet(0x200, false) || !audit_residents() ||
        !space.verify(table, ranges, handoff.get(96)))
        fail("process runtime return audit");
    if (!service_root.close_operation())
        fail("process runtime lifecycle return");
    table.suspend();
    if (!space.detach())
        fail("process runtime lifecycle return");
    runtime_detached = true;
}
} // namespace

namespace {
auto ResidentPlatform::quiet() -> bool {
    return Timer::irq_off() && root() == kernel_root && !running.space && !Timer::read(0x390) &&
           Timer::quiet(0x100, false) && Timer::quiet(0x200, false);
}
[[noreturn]] auto ResidentPlatform::fail() -> void {
    ::fail("resident owner authority");
}
auto resident_boundary(const ResidentInput &input) -> void {
    if (const auto endpoint_observation = endpoint_owner.observe();
        !ResidentPlatform::quiet() || clients_live() || snapshot || endpoint.caller || endpoint_observation.replied() ||
        endpoint_observation.delivery() || endpoint_observation.completion() || !audit_residents() ||
        !space.verify(table, ranges, input.arguments.map_count))
        fail("resident owner effect boundary");
}
auto resident_prepare(ResidentInput &input) -> bool {
    if (!ensure_file_service(input.arguments.volume) && service_root.phase() != aurora::service::Phase::absent)
        abandon_service();
    return service_root.disk_ready(endpoint.generation);
}
// One immutable service-owner run operation contains this bounded two-child
// batch. The source root selects every action; these bindings are physical
// receipts, not a second scheduling or terminal-result ledger.
class PairBinding final {
public:
    ResidentInput &input;
    std::array<ExecutionBinding, 2> members{};
    explicit PairBinding(ResidentInput &value) : input(value) {
        members[0].slot = 1;
        members[1].slot = 2;
    }
};
constinit PairBinding *active_pair = nullptr;
constinit aurora::uefi::ProcessPairOutput pair_output = nullptr;
constinit void *pair_output_context = nullptr;
constinit std::size_t pair_output_member = 0;
auto pair_output_adapter(void *, bool error, std::span<const std::byte> bytes) -> bool {
    if (!active_pair || !pair_output || pair_output_member >= 2)
        fail("pair output identity");
    return pair_output(pair_output_context, pair_output_member, error, bytes);
}
class BatchPlatform final {
public:
    static auto capture_parent() -> aurora::resident::Parent {
        return resident_owner.capture_parent();
    }
    static auto valid(const void *binding, aurora::resident::Parent parent) -> bool {
        if (!active_pair || binding != active_pair || !resident_owner.parent_valid(parent))
            return false;
        const auto *operation = static_cast<const ResidentRoot::Operation *>(parent.context);
        // parent_valid authenticates this exact live operation before the cast.
        if (operation->kind() != aurora::resident::OperationKind::run)
            return false;
        return &const_cast<ResidentRoot::Operation *>(operation)->input() == &active_pair->input &&
               active_pair->input.arguments.mode == RunMode::pair;
    }
    static auto enter() -> void {
        if (!ResidentPlatform::quiet() || execution_owner.entered() || execution_owner.busy())
            fail();
    }
    static auto leave() -> void {
        enter();
    }
    static auto settled(const void *binding) -> bool {
        const auto observed = endpoint_owner.observe();
        return active_pair && binding == active_pair && !clients_live() && !snapshot && !loading_image &&
               !endpoint.caller && !observed.delivery() && !observed.completion() && !active_pair->members[0].client &&
               !active_pair->members[1].client && audit_residents();
    }
    static auto release_parent(aurora::resident::Parent parent) -> void {
        resident_owner.release_parent(parent);
    }
    [[noreturn]] static auto fail() -> void {
        ::fail("batch operation authority");
    }
};
auto resident_pair(ResidentInput &input) -> aurora::execution::Result {
    using namespace aurora::batch;
    if (active_pair || clients_live() || !pair_output || input.arguments.mode != RunMode::pair)
        fail("pair admission boundary");
    PairBinding binding{input};
    active_pair = &binding;
    Root<BatchPlatform> batch{&binding};
    for (;;) {
        const auto request = batch.next();
        if (request.action == Action::done)
            break;
        batch.begin_effect(request);
        Event event = Event::success;
        U64 status = 0, value = 0;
        ExecutionBinding *member = request.child ? &binding.members[request.child - 1] : nullptr;
        switch (request.action) {
        case Action::admit:
            if (!ensure_file_service(input.arguments.volume)) {
                event = Event::service_lost;
                break;
            }
            if (next_run >= 0xffffffffULL - frames::first_owner - 1) {
                event = Event::refused;
                status = static_cast<U64>(RunStatus::unavailable);
                break;
            }
            for (auto &child : binding.members) {
                child.client = ++next_run;
                child.service_generation = endpoint.generation;
            }
            message_header(26, binding.members[0].client, binding.members[1].client, 0);
            if (!exchange_request(0)) {
                event = Event::service_lost;
            } else {
                const U64 reply = Bytes{endpoint.bytes}.get(0);
                bool valid = endpoint.count == 64 && (reply == 0 || reply == 9);
                for (U64 at = 8; valid && at < 64; ++at)
                    valid = endpoint.bytes[at] == std::byte{0};
                if (!valid) {
                    endpoint.invalid_reply_operation = 26;
                    event = Event::service_lost;
                } else {
                    if (!endpoint_owner.consume_control(endpoint_owner.observe().transaction))
                        fail("pair admission reply consumption");
                    if (reply == 9) {
                        // Both memberships were refused atomically. Incarnations
                        // stay spent, but no client resource obligation exists.
                        for (auto &child : binding.members)
                            child.client = 0;
                        event = Event::refused;
                        status = static_cast<U64>(RunStatus::unavailable);
                    }
                }
            }
            break;
        case Action::load: {
            if (!member || !ExecutionEffects::bound_service(*member) || residents[member->slot].space)
                fail("pair load binding");
            const auto loaded =
                load_committed(input.arguments.volume,
                               member->client,
                               request.child == 1 ? input.arguments.path : input.arguments.second_path,
                               request.child == 1 ? input.arguments.arguments : input.arguments.second_arguments,
                               member->slot,
                               request.quota);
            loading_image = false;
            if (loaded == RunStatus::unavailable) {
                event = Event::service_lost;
            } else if (loaded != RunStatus::exited) {
                event = Event::refused;
                status = static_cast<U64>(loaded);
            }
            break;
        }
        case Action::activate: {
            const auto result = ExecutionEffects::advance(*member);
            if (result.state == aurora::execution::Step::retired) {
                status = static_cast<U64>(result.status);
                value = result.value;
            }
            switch (result.state) {
            case aurora::execution::Step::retired:
                event = Event::terminal;
                break;
            case aurora::execution::Step::parked:
                event = Event::parked;
                break;
            case aurora::execution::Step::output:
                event = Event::output;
                break;
            case aurora::execution::Step::request:
                event = Event::request;
                break;
            default:
                fail("pair unsupported input");
            }
            break;
        }
        case Action::output:
            pair_output_member = request.child - 1;
            event = ExecutionEffects::output(*member) == aurora::execution::Effect::success ? Event::success
                                                                                            : Event::output_failed;
            break;
        case Action::request: {
            const auto progress = ExecutionEffects::request(*member);
            if (progress == aurora::execution::Request::pending) {
                event = Event::pending;
            } else if (progress == aurora::execution::Request::service_lost) {
                event = Event::service_lost;
            } else if (progress == aurora::execution::Request::ready) {
                // Finish copying the owned reply BEFORE another child can use
                // shared endpoint bytes. This does not enter the requester.
                if (!execution_owner.complete(member->slot))
                    fail("pair reply completion");
            } else {
                event = Event::cancelled;
                status = static_cast<U64>(RunStatus::watchdog);
            }
            break;
        }
        case Action::retire:
            if (!ExecutionEffects::bound_client(*member) || !ExecutionEffects::bound_service(*member) ||
                member->request_pending || member->input_pending || forced_execution)
                fail("pair retirement binding");
            if (!member->output_failed && !endpoint.caller_cancelled) {
                member->explicit_cancel_requested = true;
                endpoint.caller_cancelled = true;
            }
            member->output_pending = false;
            forced_execution = member;
            force_resident(member->slot);
            forced_execution = nullptr;
            event = Event::terminal;
            status = member->output_failed ? static_cast<U64>(RunStatus::output_failed)
                     : outcome.watchdog    ? static_cast<U64>(RunStatus::watchdog)
                                           : static_cast<U64>(RunStatus::cancelled);
            value = outcome.vector;
            break;
        case Action::close: {
            if (!member->client || residents[member->slot].space || !ExecutionEffects::bound_service(*member))
                fail("pair member close boundary");
            if (endpoint.caller) {
                // A request trap can stage bytes before stop accounting expires
                // its caller. Only this retired member's undispatched stage may
                // be withdrawn; a sibling or dispatched request is never erased.
                if (!can_withdraw_staged(member->slot,
                                         *endpoint.caller,
                                         member->client,
                                         member->service_generation,
                                         endpoint_owner.observe()) ||
                    !endpoint_owner.finish_client(member->client))
                    fail("pair staged caller retirement");
                endpoint.caller.reset();
            } else if (!endpoint_owner.finish_client(member->client)) {
                fail("pair member close endpoint");
            }
            const U64 client = member->client;
            member->client = 0;
            endpoint.caller_cancelled = false; // Requester is completely settled.
            if (!control_request(5, client))
                event = Event::service_lost;
            break;
        }
        case Action::abandon:
            abandon_service();
            for (auto &child : binding.members)
                child.client = 0;
            endpoint.caller_cancelled = false;
            break;
        default:
            fail("pair action");
        }
        if (event == Event::service_lost) {
            status = static_cast<U64>(RunStatus::unavailable);
            value = 0;
        } else if (event == Event::output_failed) {
            status = static_cast<U64>(RunStatus::output_failed);
            value = 0;
        }
        batch.accept(event, status, value);
    }
    const auto result = batch.finish();
    input.pair_result = {static_cast<RunStatus>(result.admission),
                         {{{static_cast<RunStatus>(result.status1), result.value1, false},
                           {static_cast<RunStatus>(result.status2), result.value2, false}}}};
    active_pair = nullptr;
    return {static_cast<aurora::execution::Status>(result.admission), 0};
}

auto resident_run(ResidentInput &input) -> aurora::execution::Result {
    const auto &arguments = input.arguments;
    if (arguments.mode == RunMode::pair)
        return resident_pair(input);
    if (!arguments.second_path.empty() || !arguments.second_arguments.empty())
        fail("singleton run projection");
    ExecutionTransport::bind(arguments.volume, arguments.path, arguments.arguments);
    const auto grant = ExecutionSession::open();
    aurora::execution::Result observed;
    source_execute(&grant, &observed);
    ExecutionSession::release(grant);
    ExecutionTransport::unbind();
    if (static_cast<U64>(observed.status) > static_cast<U64>(aurora::execution::Status::cancelled))
        fail("execution result");
    return observed;
}
auto resident_console(ResidentInput &input) -> aurora::uefi::ConsoleStatus {
    using namespace aurora::uefi;
    const auto &arguments = input.arguments;
    const U64 code = static_cast<U64>(arguments.console), expected_generation = arguments.expected;
    const U64 expected_note_revision = arguments.revision;
    const auto request = arguments.request;
    const auto response = arguments.response;
    const U64 output_size = response.size();
    auto &result = input.console_result;
    if (!ensure_file_service(arguments.volume, expected_generation, expected_generation == 0)) {
        if (expected_generation)
            result = {
                endpoint.generation ? ConsoleStatus::conflict : ConsoleStatus::unavailable, endpoint.generation, 0};
        else if (service_root.phase() != aurora::service::Phase::absent)
            abandon_service();
        return result.status;
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
    valid = valid && status <= (code == 16 ? 1U : 2U) && count == (status ? 0 : output_size) &&
            endpoint.count == 64 + count;
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
        if (!endpoint_owner.consume_control(endpoint_owner.observe().transaction))
            fail("endpoint control consumption");
    }
    return result.status;
}
auto resident_reject(ResidentInput &input) -> aurora::uefi::ConsoleStatus {
    using aurora::uefi::ConsoleStatus;
    auto &result = input.console_result;
    if (ensure_file_service(input.arguments.volume, input.arguments.expected, false)) {
        abandon_service(ServiceFailure::consumer_rejected);
        result.status = ConsoleStatus::success;
    } else if (endpoint.generation) {
        result.status = ConsoleStatus::conflict;
    }
    return result.status;
}
auto resident_shutdown_failed(ResidentInput &input) -> aurora::bootstrap::Progress {
    // Freeze the observed service cause before forced retirement overwrites it.
    abandon_service();
    input.shutdown_pending = false;
    input.shutdown_terminal = true;
    input.shutdown_failed = true;
    return aurora::bootstrap::Progress::failed;
}
auto resident_begin_shutdown(ResidentInput &input) -> aurora::bootstrap::Progress {
    using aurora::bootstrap::Progress;
    if (const auto endpoint_observation = endpoint_owner.observe();
        clients_live() || snapshot || endpoint.caller || endpoint_observation.replied() ||
        endpoint_observation.delivery() || endpoint_observation.completion() || input.shutdown_pending ||
        input.shutdown_terminal)
        fail("resident shutdown admission");
    if (service_root.phase() == aurora::service::Phase::absent) {
        if (residents[0].space || endpoint.generation || endpoint_owner.observe().waiting())
            fail("empty resident shutdown");
        input.shutdown_terminal = true;
        return Progress::complete;
    }
    if (service_root.phase() != aurora::service::Phase::ready)
        fail("resident shutdown phase");
    input.shutdown_generation = endpoint.generation;
    begin_service_shutdown();
    reset_loader(128);
    loading_image = true;
    message_header(6, 0, 0, 0);
    if (!begin_exchange(0)) {
        loading_image = false;
        return resident_shutdown_failed(input);
    }
    input.shutdown_transaction = endpoint_owner.observe().transaction;
    input.shutdown_pending = true;
    return Progress::pending;
}
auto resident_advance_shutdown(ResidentInput &input) -> aurora::bootstrap::Progress {
    using aurora::bootstrap::Progress;
    if (const auto endpoint_observation = endpoint_owner.observe();
        !input.shutdown_pending || input.shutdown_terminal || !input.shutdown_generation ||
        input.shutdown_generation != endpoint.generation ||
        input.shutdown_transaction != endpoint_observation.transaction || endpoint_observation.source ||
        service_root.phase() != aurora::service::Phase::stopping)
        fail("resident shutdown transaction");
    // One canonical transport step, without minting another transaction or
    // renewing either budget. The source finalizer owns the pending loop.
    const auto progress = advance_exchange();
    if (progress == ExchangeProgress::pending)
        return Progress::pending;
    loading_image = false;
    const bool clean = service_shutdown_selected() && !residents[0].space && !clients_live() && outcome.exited &&
                       !outcome.status && !outcome.watchdog && !outcome.invalid_call && !outcome.unavailable &&
                       !outcome.parked && outcome.terminal_service == input.shutdown_generation;
    if (!clean)
        return resident_shutdown_failed(input);
    finish_service_shutdown();
    input.shutdown_pending = false;
    input.shutdown_terminal = true;
    return Progress::complete;
}
auto resident_terminal_cleanup(const ResidentInput &input) -> void {
    if (!input.shutdown_terminal || input.shutdown_pending || residents[0].space || clients_live() ||
        endpoint.generation || endpoint_owner.observe().waiting() ||
        service_root.phase() != aurora::service::Phase::absent || loading_image || mounted_owner || mounted_root ||
        mounted_generation || mounted_sectors || mounted_service || block_service || block_generation ||
        block_sectors || volumes_service || volumes_generation || volumes_count || volumes_owner || volumes_root ||
        execution_owner.phase(0) != aurora::lifecycle::Phase::empty ||
        execution_owner.phase(1) != aurora::lifecycle::Phase::empty ||
        execution_owner.phase(2) != aurora::lifecycle::Phase::empty)
        fail("resident final cleanup receipt");
    for (const auto &grant : volume_grants)
        if (grant.generation || grant.controller || grant.nsid || grant.sectors)
            fail("resident volume grant cleanup receipt");
    for (const auto &resident : residents) {
        for (const auto word : resident.continuation)
            if (word)
                fail("resident continuation cleanup receipt");
        for (const auto word : resident.initial)
            if (word)
                fail("resident initial cleanup receipt");
    }
    for (auto &byte : endpoint.bytes)
        *static_cast<volatile std::byte *>(&byte) = std::byte{0};
    resident_boundary(input);
}
auto resident_arguments(const Bytes &handoff) -> ResidentArguments {
    ResidentArguments arguments;
    arguments.volume = space.volume(handoff.get(Handoff::volume_bytes_word));
    arguments.map_count = handoff.get(96);
    return arguments;
}
} // namespace

auto aurora::uefi::run_program(U64 arena,
                               const Bytes &handoff,
                               std::span<const std::byte> path,
                               std::span<const std::byte> arguments,
                               ProcessOutput output,
                               void *context,
                               ProcessInput source_input,
                               bool input_after_cr,
                               ProcessPresentation presentation) -> RunResult {
    if (!output || path.empty() || path.size() > process::file_path_limit || arguments.empty() ||
        arguments.size() > 65536 || !enter_runtime(arena, handoff))
        return {};
    output_sink = output;
    output_context = context;
    presentation_sink = presentation;
    presentation_handoff = &handoff;
    input_source = source_input;
    input_read = {};
    input_read.protocol.after_cr = input_after_cr ? 1 : 0;
    auto supplied = resident_arguments(handoff);
    supplied.path = path;
    supplied.arguments = arguments;
    ResidentInput input{supplied};
    ResidentRoot::Operation operation{aurora::resident::OperationKind::run, input};
    resident_owner.open(operation);
    aurora::execution::Result observed;
    source_resident_run(resident_owner.storage(), &observed);
    resident_owner.close(operation);
    const RunResult result{static_cast<RunStatus>(observed.status), observed.value, input_read.quarantine};
    invalidate_input(input_read.owner);
    input_source = nullptr;
    input_read = {};
    output_sink = nullptr;
    output_context = nullptr;
    presentation_sink = nullptr;
    presentation_handoff = nullptr;
    leave_runtime(handoff);
    return result;
}

auto aurora::uefi::run_program_pair(U64 arena,
                                    const Bytes &handoff,
                                    std::span<const std::byte> first_path,
                                    std::span<const std::byte> first_arguments,
                                    std::span<const std::byte> second_path,
                                    std::span<const std::byte> second_arguments,
                                    ProcessPairOutput output,
                                    void *context,
                                    ProcessPresentation presentation) -> RunPairResult {
    if (!output || first_path.empty() || second_path.empty() || first_path.size() > process::file_path_limit ||
        second_path.size() > process::file_path_limit || first_arguments.empty() || second_arguments.empty() ||
        first_arguments.size() > 65536 || second_arguments.size() > 65536 || !enter_runtime(arena, handoff))
        return {};
    if (active_pair || pair_output || output_sink || input_source)
        fail("pair command reentry");
    pair_output = output;
    pair_output_context = context;
    output_sink = pair_output_adapter;
    output_context = nullptr;
    presentation_sink = presentation;
    presentation_handoff = &handoff;
    input_read = {}; // No input source: either requested input ABI refuses admission.
    auto supplied = resident_arguments(handoff);
    supplied.mode = RunMode::pair;
    supplied.path = first_path;
    supplied.arguments = first_arguments;
    supplied.second_path = second_path;
    supplied.second_arguments = second_arguments;
    ResidentInput input{supplied};
    ResidentRoot::Operation operation{aurora::resident::OperationKind::run, input};
    resident_owner.open(operation);
    aurora::execution::Result observed;
    source_resident_run(resident_owner.storage(), &observed);
    resident_owner.close(operation);
    if (static_cast<U64>(input.pair_result.admission) != static_cast<U64>(observed.status) || observed.value)
        fail("pair copied result binding");
    const auto result = input.pair_result;
    pair_output = nullptr;
    pair_output_context = nullptr;
    pair_output_member = 0;
    output_sink = nullptr;
    output_context = nullptr;
    presentation_sink = nullptr;
    presentation_handoff = nullptr;
    input_read = {};
    leave_runtime(handoff);
    return result;
}

auto aurora::uefi::prepare_programs(U64 arena, const Bytes &handoff) -> bool {
    bool ready = false;
    if (handoff.get(Handoff::composition_word) == 4 && enter_runtime(arena, handoff)) {
        ResidentInput input{resident_arguments(handoff)};
        ResidentRoot::Operation operation{aurora::resident::OperationKind::prepare, input};
        resident_owner.open(operation);
        const U64 result = source_resident_prepare(resident_owner.storage());
        if (result > 1)
            fail("resident preparation result");
        ready = result != 0;
        resident_owner.close(operation);
        leave_runtime(handoff);
    }
    Serial::text(ready ? std::string_view{"AURORA_PROCESS_DISK: ready"}
                       : std::string_view{"AURORA_PROCESS_DISK: unavailable"});
    Serial::text(runtime_storage.mounted() ? std::string_view{" mounted\r\n"} : std::string_view{" readonly\r\n"});
    return ready;
}

auto aurora::uefi::console_request(U64 arena,
                                   const Bytes &handoff,
                                   ConsoleOperation command,
                                   U64 expected_generation,
                                   U64 expected_note_revision,
                                   std::span<const std::byte> request,
                                   std::span<std::byte> response) -> ConsoleResult {
    const U64 code = static_cast<U64>(command);
    const U64 input_size = code == 10 ? 72 : code == 11 ? 80 : code == 12 ? 72 : code == 13 ? 232 : 0;
    const U64 output_size = code == 10 ? 80 : code == 11 ? 248 : code == 13 ? 80 : 0;
    if (code < 10 || code > 14 || request.size() != input_size || response.size() != output_size ||
        (code >= 12 && !expected_generation) || (code == 12 ? !expected_note_revision : expected_note_revision != 0))
        return {ConsoleStatus::malformed, 0, 0};
    for (auto &byte : response)
        byte = std::byte{0};
    if (!enter_runtime(arena, handoff))
        return {};
    auto supplied = resident_arguments(handoff);
    supplied.console = command;
    supplied.expected = expected_generation;
    supplied.revision = expected_note_revision;
    supplied.request = request;
    supplied.response = response;
    ResidentInput input{supplied};
    ResidentRoot::Operation operation{aurora::resident::OperationKind::console, input};
    resident_owner.open(operation);
    const U64 status = source_resident_console(resident_owner.storage());
    if (status != static_cast<U64>(input.console_result.status))
        fail("resident console result");
    resident_owner.close(operation);
    leave_runtime(handoff);
    return input.console_result;
}

auto aurora::uefi::switch_storage_readonly(U64 arena, const Bytes &handoff) -> ConsoleResult {
#ifdef AURORA_UEFI_NVME
    // This is a single synchronous supervisor operation. No other RPC, runtime
    // return or foreground execution can intervene between query and stop.
    if (!enter_runtime(arena, handoff))
        return {};
    ConsoleResult result;
    const auto transition = [&]() -> void {
        if (!runtime_storage.mounted() || !nvme_mounted_committed() || !mounted_generation ||
            mounted_service != ::endpoint.generation || !residents[0].space ||
            residents[0].state.mounted_generation != mounted_generation ||
            residents[0].state.mounted_sectors != mounted_sectors || residents[0].space->owner() != mounted_owner ||
            residents[0].space->root() != mounted_root || !service_root.disk_ready(::endpoint.generation))
            return;
        auto supplied = resident_arguments(handoff);
        supplied.console = static_cast<ConsoleOperation>(16);
        supplied.expected = ::endpoint.generation;
        ResidentInput query{supplied};
        ResidentRoot::Operation console{aurora::resident::OperationKind::console, query};
        resident_owner.open(console);
        const U64 status = source_resident_console(resident_owner.storage());
        if (status != static_cast<U64>(query.console_result.status))
            fail("resident continuity query result");
        result = query.console_result;
        // Only a canonical success is authority to continue. Conflict returns
        // before begin_shutdown and keeps the source namespace/incarnation.
        if (result.status != ConsoleStatus::success) {
            resident_owner.close(console);
            if (::endpoint.generation != supplied.expected || !residents[0].space ||
                !service_root.disk_ready(supplied.expected))
                result = {ConsoleStatus::failed, 0, 0};
            return;
        }
        const auto receipt = endpoint_owner.observe();
        const U64 generation = ::endpoint.generation;
        const U64 run = residents[0].state.run;
        const U64 execution_generation = execution_owner.generation(0);
        const auto continuation = residents[0].continuation;
        const auto stopped = [&]() -> bool {
            const auto current = endpoint_owner.observe();
            return ResidentPlatform::quiet() && !execution_owner.entered() && !clients_live() && !snapshot &&
                   !::endpoint.caller && !::endpoint.caller_cancelled && !loading_image && !forced_execution &&
                   !completed_output && !input_read.pending && !input_wait.active && !output_sink && !input_source &&
                   residents[0].space && generation && generation == ::endpoint.generation &&
                   generation == result.generation && current.incarnation == generation &&
                   current.phase == aurora::endpoint::Phase::waiting && current.source == 0 && current.client == 0 &&
                   current.transaction != 0 && current.transaction == receipt.transaction &&
                   ::endpoint.request_operation == 16 && current.next == receipt.next &&
                   receipt.phase == aurora::endpoint::Phase::waiting && receipt.source == 0 && receipt.client == 0 &&
                   receipt.incarnation == generation && residents[0].state.run == run &&
                   residents[0].state.service == generation &&
                   residents[0].state.continuation == &residents[0].continuation &&
                   residents[0].state.captured == &residents[0].continuation &&
                   execution_owner.generation(0) == execution_generation &&
                   execution_owner.phase(0) == aurora::lifecycle::Phase::parked &&
                   input_frame_equal(continuation, residents[0].continuation) &&
                   service_root.phase() == aurora::service::Phase::ready && service_root.disk_ready(generation) &&
                   nvme_mounted_committed();
        };
        if (!stopped())
            fail("resident continuity query receipt");
        authenticate_stopped_frame(0, true);
        resident_owner.close(console);
        ResidentInput shutdown{resident_arguments(handoff)};
        ResidentRoot::Operation stop{aurora::resident::OperationKind::stop, shutdown};
        resident_owner.open(stop);
        if (!stopped())
            fail("resident continuity stop receipt");
        const U64 terminal = source_resident_stop(resident_owner.storage());
        const U64 expected = static_cast<U64>(shutdown.shutdown_failed ? aurora::bootstrap::Progress::failed
                                                                       : aurora::bootstrap::Progress::complete);
        if (!shutdown.shutdown_terminal || terminal != expected)
            fail("resident stop result");
        resident_terminal_cleanup(shutdown);
        resident_owner.close(stop);
        result = {ConsoleStatus::failed, 0, 0};
        Serial::text("AURORA_RESIDENT_STOPPED: clean=");
        Serial::number(shutdown.shutdown_failed ? 0 : 1);
        Serial::text(" reclaimed=1 retained=1\r\n");
        if (shutdown.shutdown_failed || !nvme_mounted_readonly())
            return;
        // Replacement is a new ordinary service operation after verified
        // reclamation, never a refund of the old operation's spent start.
        if (!service_root.close_operation() || !service_root.open_operation())
            fail("resident readonly service operation");
        ResidentInput preparation{resident_arguments(handoff)};
        ResidentRoot::Operation prepare{aurora::resident::OperationKind::prepare, preparation};
        resident_owner.open(prepare);
        const U64 ready = source_resident_prepare(resident_owner.storage());
        if (ready > 1 || (ready != 0) != service_root.disk_ready(::endpoint.generation) ||
            (ready && ::endpoint.generation == generation))
            fail("resident readonly preparation result");
        resident_owner.close(prepare);
        if (ready)
            result = {ConsoleStatus::success, ::endpoint.generation, 0};
        else {
            // Full source mount failure is absorbing for this physical boot.
            // Remove any surviving readonly process grant before revocation.
            if (service_root.phase() != aurora::service::Phase::absent)
                abandon_service();
            nvme_mounted_abandon();
        }
        Serial::text(ready ? std::string_view{"AURORA_STORAGE_READONLY: ready\r\n"}
                           : std::string_view{"AURORA_STORAGE_READONLY: unavailable\r\n"});
    };
    transition();
    leave_runtime(handoff);
    return result;
#else
    static_cast<void>(arena);
    static_cast<void>(handoff);
    return {};
#endif
}

auto aurora::uefi::reject_program_service(U64 arena, const Bytes &handoff, U64 expected_generation) -> ConsoleStatus {
    if (!expected_generation)
        return ConsoleStatus::malformed;
    if (!enter_runtime(arena, handoff))
        return ConsoleStatus::unavailable;
    auto supplied = resident_arguments(handoff);
    supplied.expected = expected_generation;
    ResidentInput input{supplied};
    ResidentRoot::Operation operation{aurora::resident::OperationKind::reject, input};
    resident_owner.open(operation);
    const U64 status = source_resident_reject(resident_owner.storage());
    if (status != static_cast<U64>(input.console_result.status))
        fail("resident rejection result");
    resident_owner.close(operation);
    leave_runtime(handoff);
    return input.console_result.status;
}

auto aurora::uefi::finish_programs(U64 arena, const Bytes &handoff) -> bool {
    if (!runtime_initialized)
        return true; // No root was ever constructed; no owner is being dropped.
    if (!enter_runtime(arena, handoff))
        fail("resident finalization entry");
    ResidentInput input{resident_arguments(handoff)};
    ResidentRoot::Operation operation{aurora::resident::OperationKind::shutdown, input};
    resident_owner.open(operation);
    const U64 result = source_resident_finish(resident_owner.storage());
    if (result > 1 || !input.shutdown_terminal || (result != 0) != input.shutdown_failed)
        fail("resident finalization result");
    resident_owner.finish(operation);
    if (!execution_owner.finish())
        fail("execution owner finalization");
    leave_runtime(handoff);
    Serial::text("AURORA_RESIDENT_OWNER_FINISHED: clean=");
    Serial::number(result == 0 ? 1 : 0);
    Serial::text(" reclaimed=1\r\n");
    return result == 0;
}

// Private transport declarations use the catalogue ABI, including the actual
// field address. There is no source-visible address or copied authority result.
auto resident_prepare_effect(const void *, U64, const void *) -> U64 asm("__au_runtime_resident_prepare")
    __attribute__((visibility("hidden")));
auto resident_prepare_effect(const void *binding, U64 epoch, const void *field) -> U64 {
    auto &operation = resident_owner.enter(binding, epoch, field, aurora::resident::OperationKind::prepare);
    const bool result = resident_prepare(operation.input());
    resident_boundary(operation.input());
    resident_owner.leave(operation);
    return result ? 1 : 0;
}
auto resident_run_effect(const void *, U64, const void *, aurora::execution::Result *)
    -> void asm("__au_runtime_resident_run") __attribute__((visibility("hidden")));
auto resident_run_effect(const void *binding, U64 epoch, const void *field, aurora::execution::Result *result) -> void {
    auto &operation = resident_owner.enter(binding, epoch, field, aurora::resident::OperationKind::run);
    *result = resident_run(operation.input());
    resident_boundary(operation.input());
    resident_owner.leave(operation);
}
auto resident_console_effect(const void *, U64, const void *) -> U64 asm("__au_runtime_resident_console")
    __attribute__((visibility("hidden")));
auto resident_console_effect(const void *binding, U64 epoch, const void *field) -> U64 {
    auto &operation = resident_owner.enter(binding, epoch, field, aurora::resident::OperationKind::console);
    const auto result = resident_console(operation.input());
    resident_boundary(operation.input());
    resident_owner.leave(operation);
    return static_cast<U64>(result);
}
auto resident_reject_effect(const void *, U64, const void *) -> U64 asm("__au_runtime_resident_reject")
    __attribute__((visibility("hidden")));
auto resident_reject_effect(const void *binding, U64 epoch, const void *field) -> U64 {
    auto &operation = resident_owner.enter(binding, epoch, field, aurora::resident::OperationKind::reject);
    const auto result = resident_reject(operation.input());
    resident_boundary(operation.input());
    resident_owner.leave(operation);
    return static_cast<U64>(result);
}
auto resident_begin_shutdown_effect(const void *, U64, const void *) -> U64 asm("__au_runtime_resident_begin_shutdown")
    __attribute__((visibility("hidden")));
auto resident_begin_shutdown_effect(const void *binding, U64 epoch, const void *field) -> U64 {
    auto &operation = resident_owner.enter_shutdown(binding, epoch, field);
    const auto result = resident_begin_shutdown(operation.input());
    resident_owner.leave(operation);
    return static_cast<U64>(result);
}
auto resident_advance_shutdown_effect(const void *, U64, const void *) -> U64
    asm("__au_runtime_resident_advance_shutdown") __attribute__((visibility("hidden")));
auto resident_advance_shutdown_effect(const void *binding, U64 epoch, const void *field) -> U64 {
    auto &operation = resident_owner.enter_shutdown(binding, epoch, field, true);
    const auto result = resident_advance_shutdown(operation.input());
    resident_owner.leave(operation);
    return static_cast<U64>(result);
}
auto resident_finish_effect(const void *, U64, const void *) -> U64 asm("__au_runtime_resident_finish")
    __attribute__((visibility("hidden")));
auto resident_finish_effect(const void *binding, U64 epoch, const void *field) -> U64 {
    auto &operation = resident_owner.enter(binding, epoch, field, aurora::resident::OperationKind::shutdown, true);
    const auto &input = operation.input();
    resident_terminal_cleanup(input);
    const U64 result = input.shutdown_failed ? 1 : 0;
    resident_owner.consume(operation);
    resident_owner.leave(operation);
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
auto execution_input(const void *, U64) -> U64 asm("__au_runtime_execution_input")
    __attribute__((visibility("hidden")));
auto execution_input(const void *grant, U64 generation) -> U64 {
    return ExecutionSession::input(grant, generation);
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

// The bootstrap issuer is distinct from ExecutionSession even during nested
// command preparation. These entry points are shared by production and the
// existing mounted process fixtures that use actual production startup.
auto service_bootstrap_begin(const void *, U64, aurora::bootstrap::Lease *)
    -> void asm("__au_runtime_service_bootstrap_begin") __attribute__((visibility("hidden")));
auto service_bootstrap_begin(const void *grant, U64 generation, aurora::bootstrap::Lease *result) -> void {
    *result = ServiceBootstrapSession::begin(grant, generation);
}
auto service_bootstrap_preparation(const void *, U64, aurora::bootstrap::Preparation *)
    -> void asm("__au_runtime_service_bootstrap_preparation") __attribute__((visibility("hidden")));
auto service_bootstrap_preparation(const void *binding, U64 generation, aurora::bootstrap::Preparation *result)
    -> void {
    *result = ServiceBootstrapSession::preparation(binding, generation);
}
auto service_bootstrap_begin_volume(const void *, U64) -> U64 asm("__au_runtime_service_bootstrap_begin_volume")
    __attribute__((visibility("hidden")));
auto service_bootstrap_begin_volume(const void *binding, U64 generation) -> U64 {
    return ServiceBootstrapSession::begin_volume(binding, generation);
}
auto service_bootstrap_copy_volume(const void *, U64, U64) -> U64 asm("__au_runtime_service_bootstrap_copy_volume")
    __attribute__((visibility("hidden")));
auto service_bootstrap_copy_volume(const void *binding, U64 generation, U64 value) -> U64 {
    return ServiceBootstrapSession::copy_volume(binding, generation, value);
}
auto service_bootstrap_seal_volume(const void *, U64) -> U64 asm("__au_runtime_service_bootstrap_seal_volume")
    __attribute__((visibility("hidden")));
auto service_bootstrap_seal_volume(const void *binding, U64 generation) -> U64 {
    return ServiceBootstrapSession::seal_volume(binding, generation);
}
auto service_bootstrap_admit_storage(const void *, U64) -> U64 asm("__au_runtime_service_bootstrap_admit_storage")
    __attribute__((visibility("hidden")));
auto service_bootstrap_admit_storage(const void *binding, U64 generation) -> U64 {
    return ServiceBootstrapSession::admit_storage(binding, generation);
}
auto service_bootstrap_advance(const void *, U64) -> U64 asm("__au_runtime_service_bootstrap_advance")
    __attribute__((visibility("hidden")));
auto service_bootstrap_advance(const void *binding, U64 generation) -> U64 {
    return ServiceBootstrapSession::advance(binding, generation);
}
auto service_bootstrap_finish(const void *, U64, U64) -> U64 asm("__au_runtime_service_bootstrap_finish")
    __attribute__((visibility("hidden")));
auto service_bootstrap_finish(const void *binding, U64 generation, U64 value) -> U64 {
    return ServiceBootstrapSession::finish(binding, generation, value);
}

// The allocator root remains in ordinary kernel storage. Admitted process roots
// share the same supervisor metadata extension captured at process creation.
namespace aurora::words {
auto accessible() -> bool {
    return Timer::irq_off() && space.attached() && (root() == kernel_root || table.accessible_root(root()));
}
[[noreturn]] auto fail() -> void {
#ifdef AURORA_PROCESS_FIXTURE
    if (authority_probe_armed) {
        Serial::text("AURORA_MAPPING_AUTHORITY_REJECT:");
        field("case", authority_probe_armed);
        field("closed", space.closed());
        field("opens", space.fixture_opens() - authority_probe_opens);
        Serial::text("\r\n");
    }
#endif
    ::fail("frame metadata authority");
}
} // namespace aurora::words
extern "C" {
__attribute__((visibility("hidden"))) auto
__au_runtime_owned_words_borrow_span(const void *binding, U64 epoch, aurora::hosted::bytes::NativeSpan *output)
    -> void {
    *output = aurora::words::Binding::borrow_span(binding, epoch);
}
__attribute__((visibility("hidden"))) auto __au_runtime_owned_words_size(const void *binding, U64 epoch) -> U64 {
    return aurora::words::Binding::size(binding, epoch);
}
__attribute__((visibility("hidden"))) auto __au_runtime_owned_words_at(const void *binding, U64 epoch, U64 index)
    -> U64 {
    return aurora::words::Binding::at(binding, epoch, index);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_owned_words_set(const void *binding, U64 epoch, U64 index, U64 value) -> U64 {
    return aurora::words::Binding::set(binding, epoch, index, value);
}
__attribute__((visibility("hidden"))) auto __au_runtime_owned_words_finish(const void *binding, U64 epoch) -> U64 {
    return aurora::words::Binding::finish(binding, epoch);
}
}

// Exact synchronous MappingAuthority effect boundary, admitted by the source ABI.
extern "C" {
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_observe_table(const void *token, U64 epoch, U64 ticket)
    -> U64 {
#ifdef AURORA_PROCESS_FIXTURE
    if (authority_probe_pending == 53) {
        arm_authority_probe(53);
        static_cast<void>(aurora::uefi::MappingAuthority::observe_table(token, epoch, ticket ^ (U64{1} << 32)));
        __builtin_trap();
    }
#endif
    return aurora::uefi::MappingAuthority::observe_table(token, epoch, ticket);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_observe_next_present(const void *token, U64 epoch, U64 ticket, U64 first) -> U64 {
    return aurora::uefi::MappingAuthority::observe_next_present(token, epoch, ticket, first);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_publish_empty_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 value, U64 child)
    -> U64 {
    return aurora::uefi::MappingAuthority::publish_empty_entry(token, epoch, ticket, slot, value, child);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_clear_expected_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 expected, U64 child)
    -> U64 {
#ifdef AURORA_PROCESS_FIXTURE
    if (authority_probe_pending == 50 || authority_probe_pending == 54) {
        const U64 probe = authority_probe_pending;
        arm_authority_probe(probe);
        static_cast<void>(aurora::uefi::MappingAuthority::clear_expected_entry(
            token, epoch, ticket, slot, expected, probe == 54 ? child ^ (U64{1} << 32) : child));
        __builtin_trap();
    }
#endif
    return aurora::uefi::MappingAuthority::clear_expected_entry(token, epoch, ticket, slot, expected, child);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_scrub_unpublished_frame(const void *token, U64 epoch, U64 ticket) -> U64 {
    return aurora::uefi::MappingAuthority::scrub_unpublished_frame(token, epoch, ticket);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_downgrade_snapshot_entry(
    const void *token, U64 epoch, U64 ticket, U64 slot, U64 expected, U64 child) -> U64 {
    return aurora::uefi::MappingAuthority::downgrade_snapshot_entry(token, epoch, ticket, slot, expected, child);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_snapshot_anchor_publish(const void *token, U64 epoch, U64 ticket) -> U64 {
    return aurora::uefi::MappingAuthority::snapshot_anchor_publish(token, epoch, ticket);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_snapshot_anchor_clear(const void *token, U64 epoch, U64 ticket) -> U64 {
    return aurora::uefi::MappingAuthority::snapshot_anchor_clear(token, epoch, ticket);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_frame_address(const void *token, U64 epoch, U64 index)
    -> U64 {
    return aurora::uefi::MappingAuthority::frame_address(token, epoch, index);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_frame_index(const void *token, U64 epoch, U64 physical)
    -> U64 {
    return aurora::uefi::MappingAuthority::frame_index(token, epoch, physical);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_shared_slots(const void *token, U64 epoch) -> U64 {
    return aurora::uefi::MappingAuthority::shared_slots(token, epoch);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_shared_slot(const void *token, U64 epoch, U64 index)
    -> U64 {
    return aurora::uefi::MappingAuthority::shared_slot(token, epoch, index);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_shared_value(const void *token, U64 epoch, U64 index)
    -> U64 {
    return aurora::uefi::MappingAuthority::shared_value(token, epoch, index);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_shared_upper(const void *token, U64 epoch, U64 slot)
    -> U64 {
    return aurora::uefi::MappingAuthority::shared_upper(token, epoch, slot);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_reserved_first(const void *token, U64 epoch) -> U64 {
    return aurora::uefi::MappingAuthority::reserved_first(token, epoch);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_reserved_end(const void *token, U64 epoch) -> U64 {
    return aurora::uefi::MappingAuthority::reserved_end(token, epoch);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_initialize_shared_upper(const void *token, U64 epoch, U64 ticket) -> U64 {
    return aurora::uefi::MappingAuthority::initialize_shared_upper(token, epoch, ticket);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_publish_shared_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 shared) -> U64 {
    return aurora::uefi::MappingAuthority::publish_shared_entry(token, epoch, ticket, slot, shared);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_copy_source_frame(const void *token, U64 epoch, U64 ticket, U64 destination, U64 source, U64 count)
    -> U64 {
#ifdef AURORA_PROCESS_FIXTURE
    if (authority_probe_pending == 62) {
        // Simulated native reentry at a real copy boundary. No callback is
        // retained or introduced into the production authority interface.
        arm_authority_probe(62);
        static_cast<void>(table.audit_residents());
        __builtin_trap();
    }
#endif
    return aurora::uefi::MappingAuthority::copy_source_frame(token, epoch, ticket, destination, source, count);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_fill_snapshot_chunk(
    const void *token, U64 epoch, U64 snapshot_epoch, U64 destination, U64 source, U64 count) -> U64 {
    return aurora::uefi::MappingAuthority::fill_snapshot_chunk(
        token, epoch, snapshot_epoch, destination, source, count);
}
__attribute__((visibility("hidden"))) auto
__au_runtime_mapping_clear_shared_entry(const void *token, U64 epoch, U64 ticket, U64 slot, U64 shared) -> U64 {
    return aurora::uefi::MappingAuthority::clear_shared_entry(token, epoch, ticket, slot, shared);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_revoke_root(const void *token, U64 epoch, U64 ticket)
    -> U64 {
    return aurora::uefi::MappingAuthority::revoke_root(token, epoch, ticket);
}
__attribute__((visibility("hidden"))) auto __au_runtime_mapping_finish(const void *token, U64 epoch) -> U64 {
    return aurora::uefi::MappingAuthority::finish(token, epoch);
}
}

extern "C" __attribute__((visibility("hidden"))) auto
__au_runtime_mapping_observe_snapshot_anchor(const void *token, U64 epoch, U64 ticket) -> U64 {
    return aurora::uefi::MappingAuthority::observe_snapshot_anchor(token, epoch, ticket);
}

// The compiler admits these exact retained-field effects. No source pointer or
// copied observation can mint an issuer, change slots, or bypass busy scope.
// Source boolean effects use a canonical full-word result, not the C++ AL-only
// bool return convention. Keep the private ABI distinct from native helpers.
extern "C" {
__attribute__((visibility("hidden"))) void __au_runtime_execution_authority_prepare(
    const void *binding, U64 epoch, const void *field, aurora::lifecycle::Observation *output, U64 slot) {
    execution_authority_observe<aurora::lifecycle::EffectKind::prepare>(binding, epoch, field, output, slot);
}
__attribute__((visibility("hidden"))) void __au_runtime_execution_authority_activate(
    const void *binding, U64 epoch, const void *field, aurora::lifecycle::Observation *output, U64 slot) {
    execution_authority_observe<aurora::lifecycle::EffectKind::activate>(binding, epoch, field, output, slot);
}
__attribute__((visibility("hidden"))) void __au_runtime_execution_authority_complete(
    const void *binding, U64 epoch, const void *field, aurora::lifecycle::Observation *output, U64 slot) {
    execution_authority_observe<aurora::lifecycle::EffectKind::complete>(binding, epoch, field, output, slot);
}
__attribute__((visibility("hidden"))) void __au_runtime_execution_authority_force(
    const void *binding, U64 epoch, const void *field, aurora::lifecycle::Observation *output, U64 slot) {
    execution_authority_observe<aurora::lifecycle::EffectKind::force>(binding, epoch, field, output, slot);
}
__attribute__((visibility("hidden"))) U64 __au_runtime_execution_authority_retire(const void *binding,
                                                                                  U64 epoch,
                                                                                  const void *field,
                                                                                  U64 slot) {
    using namespace aurora::lifecycle;
    execution_owner.enter(binding, epoch, field, EffectKind::retire, slot);
    authenticate_execution(slot, Phase::retiring);
    authenticate_terminal_capture(slot);
    if (slot == 0 && residents[0].state.service) {
        const auto endpoint_observation = endpoint_owner.observe();
        if (service_root.phase() != aurora::service::Phase::retiring ||
            service_root.generation() != residents[0].state.service ||
            endpoint.generation != residents[0].state.service || clients_live() || snapshot || loading_image ||
            endpoint.caller || endpoint_observation.waiting() || endpoint_observation.replied() ||
            endpoint_observation.delivery() || endpoint_observation.completion())
            fail("service retirement invalidation boundary");
    }
    invalidate_input(residents[slot].state.run);
    const bool result = release_resident_physical(slot);
    execution_owner.leave();
    return result ? 1 : 0;
}
__attribute__((visibility("hidden"))) U64 __au_runtime_execution_authority_invalidate_service(const void *binding,
                                                                                              U64 epoch,
                                                                                              const void *field,
                                                                                              U64 slot) {
    using namespace aurora::lifecycle;
    execution_owner.enter(binding, epoch, field, EffectKind::invalidate_service, slot);
    invalidate_service_physical(slot);
    execution_owner.leave();
    return 1;
}
__attribute__((visibility("hidden"))) U64 __au_runtime_execution_authority_finish(const void *binding,
                                                                                  U64 epoch,
                                                                                  const void *field) {
    using namespace aurora::lifecycle;
    execution_owner.enter(binding, epoch, field, EffectKind::finish, 0);
    if (const auto endpoint_observation = endpoint_owner.observe();
        execution_owner.canonical(0, Field::phase) != static_cast<U64>(Phase::empty) ||
        execution_owner.canonical(1, Field::phase) != static_cast<U64>(Phase::empty) ||
        execution_owner.canonical(2, Field::phase) != static_cast<U64>(Phase::empty) || residents[0].space ||
        clients_live() || snapshot || endpoint.caller || endpoint_observation.delivery() ||
        endpoint_observation.completion() || !audit_residents())
        fail("execution owner cleanup");
    execution_owner.consume();
    execution_owner.leave();
    return 1;
}
}
