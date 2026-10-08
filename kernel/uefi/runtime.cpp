#include "runtime.hpp"
#ifdef AURORA_UEFI_RUNTIME
#include "runtime-tables.hpp"
#include "tables.hpp"
#include "../user-program.hpp"
#include "../domain-policy.hpp"
#include "../pages.hpp"
#ifdef AURORA_UEFI_PINS
#include "../pin-ledger.hpp"
#ifdef AURORA_UEFI_TABLES
#include "dormant-inspector.hpp"
#endif
#endif
#include "../console.hpp"
#ifdef AURORA_UEFI_IPC
#include "../ipc-policy.hpp"
#ifdef AURORA_UEFI_DISPATCH
#include "../dispatch-policy.hpp"
#endif
#ifdef AURORA_UEFI_USER_BUDGET
#include "user-run-policy.hpp"
#endif
#ifdef AURORA_UEFI_SERVICE_BUDGET
#include "acpi.hpp"
#include "budget-transport.hpp"
#include "apic-timer-io.hpp"
#include "uefi-user-images.hpp"
#endif
#endif
#include <array>
#include <optional>
#ifdef AURORA_UEFI_PROGRAM_CONSOLE
#include "console-context.hpp"
#include "../console-presentation.hpp"
#include "../console-uart.hpp"
#include "../program-stream.hpp"
#endif
namespace aurora::uefi {
extern std::uint64_t saved_rsp asm("uefi_runtime_saved_rsp") __attribute__((visibility("hidden")));
#ifdef AURORA_UEFI_IPC
auto enter(std::uint64_t, std::uint64_t, const std::uint64_t *) -> std::uint64_t asm("uefi_runtime_enter")
    __attribute__((visibility("hidden")));
#else
auto enter(std::uint64_t, std::uint64_t) -> std::uint64_t asm("uefi_runtime_enter")
    __attribute__((visibility("hidden")));
#endif
auto handler(unsigned) -> std::uint64_t asm("uefi_runtime_handler") __attribute__((visibility("hidden")));
namespace {
using U64 = std::uint64_t;
#ifdef AURORA_UEFI_PROGRAM_CONSOLE
// Runtime diagnostics and input share the same sticky LSR error latch. A raw
// hardware::Serial read during a protected command would otherwise erase OE.
using Serial = console::Uart<hardware::Io, console::FifoTrigger::fourteen>;
#else
using hardware::Serial;
#endif
using user::ProgramEvent;
using L = RuntimeLayout;
class Domain final {
public:
    std::optional<user::DomainHandle> handle{};
    std::array<std::optional<memory::PageLease>, 4> stacks{};
    std::optional<user::ProgramContract> contract{};
    std::optional<RuntimeTables> tables{};
    unsigned image{};
};
constinit std::array<Domain, L::domain_count> domains;
constinit memory::PhysicalPages frames;
constinit user::DomainRegistry registry;
constinit user::ProgramRun program;
#ifdef AURORA_UEFI_IPC
#ifdef AURORA_UEFI_DISPATCH
constinit std::optional<ipc::Dispatcher> dispatcher;
#else
constinit std::optional<ipc::Mailbox> mailbox;
#endif
#if defined(AURORA_UEFI_DISPATCH) || defined(AURORA_UEFI_PROGRAM_CONSOLE)
unsigned selected_client = 2;
#endif
#ifdef AURORA_UEFI_USER_BUDGET
#ifdef AURORA_UEFI_PROGRAM_CONSOLE
using SelectedRunAuthority = ProgramRunAuthority;
#else
using SelectedRunAuthority = RunAuthority;
#endif
std::optional<SelectedRunAuthority> run_authority;
SelectedRunAuthority::Role selected_role = SelectedRunAuthority::Role::client;
#endif
#ifdef AURORA_UEFI_SERVICE_BUDGET
std::array<U64, 7> launch{};
std::optional<LocalApicAdmission> interrupt_admission;
#else
std::array<U64, 6> launch{};
#endif
U64 transaction{};
ipc::Phase selected_phase = ipc::Phase::inactive;
#endif
#ifdef AURORA_UEFI_SERVICE_BUDGET
auto service_delivered() -> bool {
#ifdef AURORA_UEFI_DISPATCH
    return dispatcher && dispatcher->selected() == selected_client &&
           dispatcher->state(selected_client) == ipc::State::delivered;
#else
    return mailbox && mailbox->state() == ipc::State::delivered;
#endif
}
#endif
U64 arena{}, kernel_root{};
std::optional<Bytes> handoff{};
unsigned active = L::domain_count;
[[nodiscard]] auto view(U64 address, std::size_t count) -> std::span<std::byte> {
    return {reinterpret_cast<std::byte *>(address), count};
}
[[nodiscard]] auto root() -> U64 {
    U64 result;
    asm volatile("mov %%cr3,%0" : "=r"(result));
    return result;
}
[[nodiscard]] auto stack() -> U64 {
    U64 result;
    asm volatile("mov %%rsp,%0" : "=r"(result));
    return result;
}
[[noreturn]] auto stop(std::string_view reason) -> void {
    Serial::text("AURORA_UEFI_RUNTIME_FAIL: ");
    Serial::text(reason);
    Serial::text("\r\n");
    hardware::Io::write(0xf4, 0x11);
    for (;;)
        asm volatile("cli; hlt");
}
auto require(bool okay, std::string_view reason) -> void {
    if (!okay)
        stop(reason);
}
auto fill(U64 physical, std::uint8_t value) -> void {
    for (auto &byte : view(physical, 4096))
        byte = std::byte{value};
}
[[nodiscard]] auto zero(U64 physical) -> bool {
    for (const auto byte : view(physical, 4096))
        if (byte != std::byte{0})
            return false;
    return true;
}
[[nodiscard]] auto expected(const Domain &domain, U64 address) -> U64 {
#ifdef AURORA_UEFI_SERVICE_BUDGET
    if (interrupt_admission && address == LocalApicAdmission::virtual_address)
        return LocalApicAdmission::physical_address | LocalApicAdmission::leaf_flags;
#endif
    if (address >= arena && address < arena + L::arena_bytes) {
        const auto flags = expected_flags(address - arena, *handoff);
        return flags ? address | flags : 0;
    }
    if (!domain.contract)
        return 0;
    if (address == domain.contract->entry())
        return (arena + L::image_offset + domain.image * 4096) | 5;
    const auto bottom = domain.contract->layout().user_stack_bottom();
    if (address >= bottom && address < bottom + 0x4000 && address % 4096 == 0) {
        const auto slot = (address - bottom) / 4096;
        if (!domain.stacks[slot])
            return 0;
        const auto physical = frames.address(*domain.stacks[slot]);
        return physical ? *physical | 7 | RuntimeTables::nx : 0;
    }
    return 0;
}
[[nodiscard]] auto verify(const Domain &domain) -> bool {
    if (!domain.tables || !domain.contract || !domain.tables->verify([&](U64 va) {
            return expected(domain, va);
        }))
        return false;
    for (U64 offset = 0; offset < L::arena_bytes; offset += 4096)
        if ((domain.tables->entry(arena + offset) & ~0x60ULL) != expected(domain, arena + offset))
            return false;
    if ((domain.tables->entry(domain.contract->entry()) & ~0x60ULL) != expected(domain, domain.contract->entry()))
        return false;
    for (U64 offset = 0; offset < 0x4000; offset += 4096) {
        const auto va = domain.contract->layout().user_stack_bottom() + offset;
        if ((domain.tables->entry(va) & ~0x60ULL) != expected(domain, va))
            return false;
    }
#ifdef AURORA_UEFI_SERVICE_BUDGET
    if (!interrupt_admission || (domain.tables->entry(LocalApicAdmission::virtual_address) & ~0x60ULL) !=
                                    expected(domain, LocalApicAdmission::virtual_address))
        return false;
#endif
    return domain.tables->entry(PageTables::window_address) == 0;
}
[[nodiscard]] auto retire(unsigned index) -> bool {
    if (index >= L::domain_count || root() != kernel_root || active != L::domain_count)
        return false;
    auto &domain = domains[index];
    if (!domain.handle || !registry.ready(*domain.handle))
        return false;
    for (auto &lease : domain.stacks)
        if (lease) {
            const auto physical = frames.address(*lease);
            if (!physical)
                return false;
            fill(*physical, 0);
            if (!zero(*physical))
                return false;
        }
    if (domain.tables && !domain.tables->reset())
        return false;
    if (!registry.destroy(*domain.handle))
        return false;
    for (auto &lease : domain.stacks)
        if (lease) {
            if (!frames.release(*lease))
                return false;
            lease.reset();
        }
    domain.tables.reset();
    domain.contract.reset();
    domain.handle.reset();
    return true;
}
[[nodiscard]] auto create(unsigned image) -> std::optional<unsigned> {
    if (root() != kernel_root || active != L::domain_count || image >= L::image_pages)
        return std::nullopt;
    auto token = registry.create();
    if (!token)
        return std::nullopt;
    const auto index = registry.index(*token);
    if (!index || *index >= L::domain_count) {
        static_cast<void>(registry.destroy(*token));
        return std::nullopt;
    }
    auto &domain = domains[*index];
    domain.handle = *token;
    domain.image = image;
    const auto layout = user::ProgramLayout::create(L::user_code,
                                                    L::user_code + L::image_pages * L::page_size,
                                                    1,
                                                    L::user_stack_begin(*index),
                                                    L::user_stack_end(*index),
                                                    arena + L::rsp0_bottom,
                                                    arena + L::rsp0_top);
    if (!layout) {
        static_cast<void>(retire(*index));
        return std::nullopt;
    }
    const Bytes descriptor{view(arena + L::metadata_offset + image * 64, 64)};
    domain.contract.emplace(*layout,
                            descriptor.get(0),
                            descriptor.get(8),
                            descriptor.get(16),
                            descriptor.get(24),
                            descriptor.get(32),
                            descriptor.get(40),
                            descriptor.get(48));
    if (domain.contract->entry() != L::user_code + image * 4096 || domain.contract->size() > 4096 ||
        !user::ProgramImage{view(arena + L::image_offset + image * 4096, domain.contract->size()), *domain.contract}
             .valid()) {
        static_cast<void>(retire(*index));
        return std::nullopt;
    }
    for (auto &lease : domain.stacks) {
        auto acquired = frames.acquire();
        if (acquired)
            lease.emplace(std::move(*acquired));
        if (!lease) {
            static_cast<void>(retire(*index));
            return std::nullopt;
        }
        const auto physical = frames.address(*lease);
        if (!physical) {
            static_cast<void>(retire(*index));
            return std::nullopt;
        }
        fill(*physical, 0);
    }
    const auto table_base = arena + L::table_offset(*index);
    domain.tables.emplace(std::span<U64>{reinterpret_cast<U64 *>(table_base), 16 * 512}, table_base);
    bool good = domain.tables->valid();
    for (U64 offset = 0; offset < L::arena_bytes && good; offset += 4096) {
        const auto flags = expected_flags(offset, *handoff);
        if (flags)
            good = domain.tables->map(arena + offset, arena + offset, flags);
    }
    good = good && domain.tables->map(domain.contract->entry(), arena + L::image_offset + image * 4096, 5);
    for (unsigned page = 0; page < 4 && good; ++page)
        good = domain.tables->map(
            layout->user_stack_bottom() + page * 4096, *frames.address(*domain.stacks[page]), 7 | RuntimeTables::nx);
#ifdef AURORA_UEFI_SERVICE_BUDGET
    good = good && interrupt_admission &&
           domain.tables->map(LocalApicAdmission::virtual_address,
                              LocalApicAdmission::physical_address,
                              LocalApicAdmission::leaf_flags);
#endif
    if (!good || !verify(domain)) {
        static_cast<void>(retire(*index));
        return std::nullopt;
    }
    return static_cast<unsigned>(*index);
}
auto install_architecture() -> void {
    const auto gdt = arena + L::gdt_offset, tss = gdt + 256;
    const std::array<U64, 5> entries{
        0, 0x00af9b000000ffffULL, 0x00cf93000000ffffULL, 0x00affb000000ffffULL, 0x00cff3000000ffffULL};
    for (unsigned i = 0; i < 5; ++i)
        put(view(gdt + i * 8, 8), 0, entries[i]);
    const auto low = 103ULL | ((tss & 0xffffff) << 16) | (0x89ULL << 40) | (((tss >> 24) & 255) << 56);
    put(view(gdt + 40, 16), 0, low);
    put(view(gdt + 40, 16), 8, tss >> 32);
    put(view(tss, 104), 4, arena + L::rsp0_top);
    put(view(tss, 104), 36, arena + L::ist_top);
    put(view(tss, 104), 102, 104, 2);
    std::array<std::byte, 10> gdtr{};
    put(gdtr, 0, 55, 2);
    put(gdtr, 2, gdt);
    asm volatile("lgdt %0" : : "m"(gdtr) : "memory");
    const std::uint16_t selector = 0x28;
    asm volatile("ltr %0" : : "r"(selector) : "memory");
    for (unsigned vector = 0; vector < 256; ++vector) {
        auto gate = view(arena + Handoff::idt_offset + vector * 16, 16);
        const auto target = handler(vector);
        require(target >= arena + Handoff::payload_offset &&
                    target < arena + Handoff::payload_offset + handoff->get(64),
                "IDT target");
        put(gate, 0, target, 2);
        put(gate, 2, 8, 2);
        put(gate, 4, vector == 8 ? 1 : 0, 1);
        put(gate, 5, vector == 129 ? 0xee : 0x8e, 1);
        put(gate, 6, target >> 16, 2);
        put(gate, 8, target >> 32, 4);
        put(gate, 12, 0, 4);
    }
    U64 cr4;
    asm volatile("mov %%cr4,%0" : "=r"(cr4));
    require((cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 16) | (1ULL << 17) | (1ULL << 18) | (1ULL << 20))) == 0,
            "integer paging profile");
    U64 cr0;
    asm volatile("mov %%cr0,%0" : "=r"(cr0));
    cr0 |= 8;
    asm volatile("mov %0,%%cr0" ::"r"(cr0) : "memory");
    std::uint32_t msr_low, msr_high;
    asm volatile("rdmsr" : "=a"(msr_low), "=d"(msr_high) : "c"(0xc0000080));
    msr_low &= ~1U;
    asm volatile("wrmsr" ::"a"(msr_low), "d"(msr_high), "c"(0xc0000080) : "memory");
    asm volatile("rdmsr" : "=a"(msr_low), "=d"(msr_high) : "c"(0xc0000080));
    require((msr_low & 1) == 0, "inherited syscall entry");
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    if (d & (1U << 11)) {
        for (const std::uint32_t msr : {0x174U, 0x175U, 0x176U}) {
            asm volatile("wrmsr" ::"c"(msr), "a"(0), "d"(0) : "memory");
            asm volatile("rdmsr" : "=a"(msr_low), "=d"(msr_high) : "c"(msr));
            require(msr_low == 0 && msr_high == 0, "inherited sysenter entry");
        }
    }
    // Null FS/GS selectors and bases prevent inherited firmware TLS authority.
    const std::uint16_t null_selector = 0;
    asm volatile("mov %0,%%fs; mov %0,%%gs" ::"r"(null_selector) : "memory");
    for (const std::uint32_t msr : {0xc0000100U, 0xc0000101U, 0xc0000102U})
        asm volatile("wrmsr" ::"c"(msr), "a"(0), "d"(0) : "memory");
}
#ifdef AURORA_UEFI_PINS
#ifdef AURORA_UEFI_TABLES
#include "dormant-runtime.inc"
#else
#include "pin-runtime.inc"
#endif
#endif
#ifndef AURORA_UEFI_PINS
constexpr auto pin_retained() -> std::size_t {
    return 0;
}
#endif
#ifndef AURORA_UEFI_IPC
auto execute(unsigned index, ProgramEvent wanted) -> void {
    auto &domain = domains[index];
    require(root() == kernel_root && active == L::domain_count && verify(domain), "entry root/tree");
    for (const auto &lease : domain.stacks) {
        const auto physical = frames.address(*lease);
        require(physical.has_value(), "entry stack lease");
        fill(*physical, 0);
    }
    require(program.begin(*domain.contract) && registry.activate(*domain.handle), "entry authority");
    active = index;
    const auto selected = domain.tables->root();
    Serial::text("AURORA_UEFI_DOMAIN_ENTER: slot=");
    Serial::number(index);
    Serial::text(" root=");
    Serial::number(selected);
    Serial::text(" entry=");
    Serial::number(domain.contract->entry());
    Serial::text(" stack=");
    Serial::number(domain.contract->layout().user_stack_top());
    Serial::text("\r\n");
    asm volatile("mov %0,%%cr3" ::"r"(selected) : "memory");
    require(!retire(index), "active teardown accepted");
#ifdef AURORA_RUNTIME_KERNEL_TRAP
    asm volatile("jmp *%0" ::"r"(domain.contract->bounds_pc()) : "memory");
#endif
#ifdef AURORA_RUNTIME_ENTRY_STACK
    put(view(arena + L::gdt_offset + 256, 104), 4, arena + L::rsp0_bottom);
#endif
    require(enter(domain.contract->entry(), domain.contract->layout().user_stack_top()) == 1, "trusted continuation");
    const auto current_stack = stack();
    require(root() == kernel_root && active == L::domain_count && saved_rsp == 0 && !program.running() &&
                current_stack >= arena + Handoff::stack_bottom && current_stack < arena + Handoff::stack_top,
            "restored kernel authority");
    require(program.event() == wanted && (wanted != ProgramEvent::returned || program.value() == 42), "typed result");
    Serial::text("AURORA_UEFI_DOMAIN_RESTORE: slot=");
    Serial::number(index);
    Serial::text(" root=");
    Serial::number(root());
    Serial::text(" stack=");
    Serial::number(current_stack);
    Serial::text(" event=");
    Serial::text(wanted == ProgramEvent::returned ? "returned" : "bounds");
    Serial::text(" value=");
    Serial::number(program.value());
    Serial::text("\r\n");
}
#endif
#ifdef AURORA_UEFI_SERVICE_BUDGET
#include "service-timer.inc"
#endif
#ifdef AURORA_UEFI_IPC
#ifdef AURORA_UEFI_DISPATCH
#include "dispatch-runtime.inc"
#ifdef AURORA_UEFI_USER_BUDGET
#include "user-lifecycle.inc"
#endif
#elif defined(AURORA_UEFI_PROGRAM_CONSOLE)
#include "program-console.inc"
#else
#include "ipc-runtime.inc"
#endif
#endif
} // namespace
auto dispatch(U64, U64, U64, U64, U64, U64) -> U64 asm("aurora_exception_dispatch")
    __attribute__((visibility("hidden")));
auto dispatch(U64 vector, U64 error, U64 pc, U64 cs, U64 frame, U64 result) -> U64 {
#ifdef AURORA_UEFI_PROGRAM_CONSOLE
    if (program_console_interrupt(vector, error, pc, cs, frame))
        return 0;
#endif
    U64 cr2;
    asm volatile("mov %%cr2,%0" : "=r"(cr2));
    Serial::text("AURORA_UEFI_DOMAIN_EVENT: vector=");
    Serial::number(vector);
    Serial::text(" error=");
    Serial::number(error);
    Serial::text(" pc=");
    Serial::number(pc);
    Serial::text(" cpl=");
    Serial::number(cs & 3);
    Serial::text(" root=");
    Serial::number(root());
    Serial::text(" frame=");
    Serial::number(frame);
    Serial::text(" cr2=");
    Serial::number(cr2);
    Serial::text("\r\n");
#ifdef AURORA_UEFI_SERVICE_BUDGET
#if defined(AURORA_BUDGET_ROOT) || defined(AURORA_DISPATCH_ROOT) || defined(AURORA_USER_ROOT)
    if (vector == 64 && !timer_draining
#ifdef AURORA_USER_ROOT
        && active == 0
#endif
    ) {
        asm volatile("mov %0,%%cr3" ::"r"(kernel_root) : "memory");
        Serial::text("AURORA_UEFI_RUNTIME_ROOT_PROBE: root=");
        Serial::number(root());
        Serial::text("\r\n");
    }
#endif
    if (const auto interrupt = service_timer_interrupt(vector, error, pc, cs, frame))
        return *interrupt;
#endif
    if (vector == 8) {
        require(frame >= arena + L::ist_bottom && frame <= arena + L::ist_top - 176, "double fault IST authority");
        Serial::text("AURORA_UEFI_RUNTIME_IST_OK\r\n");
        stop("double fault");
    }
#if defined(AURORA_RUNTIME_ROOT) || defined(AURORA_IPC_ROOT)
    asm volatile("mov %0,%%cr3" ::"r"(kernel_root) : "memory");
    Serial::text("AURORA_UEFI_RUNTIME_ROOT_PROBE: root=");
    Serial::number(root());
    Serial::text("\r\n");
#endif
    require(active < L::domain_count && domains[active].handle && registry.active(*domains[active].handle) &&
                root() == domains[active].tables->root(),
            "exception root authority");
    require((cs & 3) == 3 && frame >= arena + L::rsp0_bottom && frame <= arena + L::rsp0_top - 176 && frame % 8 == 0 &&
                saved_rsp >= arena + Handoff::stack_bottom && saved_rsp <= arena + Handoff::stack_top - 56 &&
                saved_rsp % 8 == 0,
            "exception origin/stack");
    const Bytes captured{view(frame, 176)};
    auto saved_flags = captured.get(152);
#ifdef AURORA_UEFI_SERVICE_BUDGET
    if (selected_phase == ipc::Phase::service
#ifdef AURORA_UEFI_USER_BUDGET
        || selected_phase == ipc::Phase::request || selected_phase == ipc::Phase::completion
#endif
    ) {
#ifdef AURORA_UEFI_USER_BUDGET
        require(active < L::domain_count && run_authority &&
                    run_authority->matches_active(registry,
                                                  *domains[active].handle,
                                                  selected_role,
                                                  selected_phase,
                                                  selected_client,
                                                  transaction,
                                                  launch[0],
                                                  arena,
                                                  root(),
                                                  *domains[active].contract,
                                                  timer_owner_epoch),
                "user terminal run authority");
#endif
        const auto integer = ServiceContext::capture(
            std::span<const U64>{reinterpret_cast<const U64 *>(frame), 22}, frame, *domains[active].contract);
        require(timer_armed && integer && integer->terminal_context(*domains[active].contract) && timer_stop(),
                "timer terminal context");
#if defined(AURORA_BUDGET_PENDING) || defined(AURORA_DISPATCH_PENDING) || defined(AURORA_USER_PENDING) ||              \
    defined(AURORA_PROGRAM_PENDING)
        force_timer_pending();
#endif
#ifdef AURORA_USER_RETIRE_PENDING
        if (active == 0 && selected_phase == ipc::Phase::completion && vector == 6)
            force_timer_pending();
#endif
        saved_flags &= ~0x200ULL;
    }
#endif
    const user::ProgramContext context{vector, error, pc, cs, captured.get(168), captured.get(160), saved_flags, frame};
    require(program.accept(context, result), "exception site authority");
#ifdef AURORA_UEFI_IPC
#ifdef AURORA_UEFI_PROGRAM_CONSOLE
    program_console_envelope(captured, result);
#elif defined(AURORA_UEFI_DISPATCH)
    dispatch_envelope(captured, result);
#else
    if (program.event() == ProgramEvent::returned) {
        Serial::text("AURORA_UEFI_IPC_ENVELOPE: phase=");
        Serial::number(captured.get(64));
        Serial::text(" version=");
        Serial::number(captured.get(72));
        Serial::text(" slot=");
        Serial::number(captured.get(88));
        Serial::text(" generation=");
        Serial::number(captured.get(96));
        Serial::text(" transaction=");
        Serial::number(captured.get(56));
        Serial::text(" first=");
        Serial::number(result);
        Serial::text(" second=");
        Serial::number(captured.get(48));
        Serial::text("\r\n");
        require(captured.get(64) == launch[0] && captured.get(72) == 1, "IPC phase/version authority");
        const ipc::Endpoint endpoint{captured.get(88), captured.get(96)};
        const auto actor = *domains[active].handle;
        if (selected_phase == ipc::Phase::request) {
            require(captured.get(56) == 0, "IPC request transaction");
            const auto ticket =
                mailbox->submit(actor, selected_phase, endpoint, ipc::Request{result, captured.get(48)});
            require(ticket.has_value(), "IPC request capability/state");
            transaction = *ticket;
            ipc_record("SUBMIT", result, captured.get(48));
        } else if (selected_phase == ipc::Phase::service) {
            require(mailbox->reply(actor, selected_phase, endpoint, captured.get(56), result),
                    "IPC reply capability/transaction/state");
            ipc_record("REPLY", result, 0);
        } else {
            const auto expected_endpoint = mailbox->endpoint(actor);
            require(selected_phase == ipc::Phase::completion && expected_endpoint &&
                        expected_endpoint->slot() == endpoint.slot() &&
                        expected_endpoint->generation() == endpoint.generation() && captured.get(56) == transaction &&
                        mailbox->state() == ipc::State::consumed,
                    "IPC completion authority");
            ipc_record("COMPLETE", result, 0);
        }
    } else
        require(selected_phase == ipc::Phase::service && program.event() == ProgramEvent::bounds, "IPC fault phase");
#endif
#endif
    const auto index = active;
    asm volatile("mov %0,%%cr3" ::"r"(kernel_root) : "memory");
    require(root() == kernel_root && registry.deactivate(*domains[index].handle), "kernel root restoration");
    active = L::domain_count;
    return 1;
}
auto run_protected(U64 owned_arena, const Bytes &h) -> bool {
    if (h.get(8, 4) != 3 || !L::valid(owned_arena) || root() != h.get(88))
        return false;
    arena = owned_arena;
    kernel_root = h.get(88);
    handoff.emplace(h);
    if (!PageTables{kernel_root, static_cast<std::size_t>(h.get(96))}.verify(arena, h))
        return false;
    if (!frames.initialize(arena + L::stack_frames_offset, 16))
        return false;
    install_architecture();
#ifdef AURORA_UEFI_SERVICE_BUDGET
    initialize_service_timer();
#endif
#ifdef AURORA_UEFI_IPC
#ifdef AURORA_UEFI_DISPATCH
#ifdef AURORA_UEFI_USER_BUDGET
    run_user_lifecycle();
#else
    run_dispatcher();
#endif
#elif defined(AURORA_UEFI_PROGRAM_CONSOLE)
    run_program_console();
#else
    run_ipc();
#endif
    return true;
#else
    const auto first = create(0), second = create(1);
    require(first && second && *first == 0 && *second == 1, "two owned domains");
    const auto original = *frames.address(*domains[0].stacks[0]);
    execute(0, ProgramEvent::returned);
#ifdef AURORA_UEFI_PINS
    pin_request();
#endif
    execute(1, ProgramEvent::bounds);
#ifdef AURORA_UEFI_PINS
    pin_fault_returned();
#endif
    execute(0, ProgramEvent::returned);
    const auto stale = *domains[0].handle;
#ifdef AURORA_PIN_FAULT
    const auto old_service = *domains[1].handle;
#endif
    for (auto &domain : domains)
        for (auto &lease : domain.stacks)
            fill(*frames.address(*lease), 0xa5);
    require(retire(0) && retire(1)
#ifdef AURORA_UEFI_PINS
                && pin_retired()
#endif
                && frames.used() == pin_retained() && !registry.index(stale) && !registry.activate(stale) &&
                !registry.destroy(stale),
            "retire/stale authority");
    const auto reused = create(
#ifdef AURORA_PIN_FAULT
        1
#else
        0
#endif
    );
    require(reused && *reused == 0 && *frames.address(*domains[0].stacks[0]) == original, "frame reuse");
    for (const auto &lease : domains[0].stacks)
        require(zero(*frames.address(*lease)), "reused frame scrub");
    Serial::text("AURORA_UEFI_DOMAIN_REUSE_OK: frame=");
    Serial::number(original);
    Serial::text("\r\n");
#ifdef AURORA_PIN_FAULT
    const auto restarted = create(0);
    require(restarted && *restarted == 1, "same service slot restart");
    execute(1, ProgramEvent::returned);
    pin_reborn(old_service);
    require(retire(1), "restarted service retirement");
#else
    execute(0, ProgramEvent::returned);
#ifdef AURORA_UEFI_PINS
    pin_reborn(stale);
#endif
#endif
    require(retire(0) && frames.used() == pin_retained(), "final retirement");
    std::array<std::optional<memory::PageLease>, 14> reserved{};
    for (std::size_t i = 0; i < 14 - pin_retained(); ++i) {
        auto acquired = frames.acquire();
        require(acquired.has_value(), "rollback reservation");
        reserved[i].emplace(std::move(*acquired));
    }
    fill(arena + L::stack_frames_offset + 14 * 4096, 0xa5);
    fill(arena + L::stack_frames_offset + 15 * 4096, 0xa5);
    require(!create(0) && frames.used() == 14 && zero(arena + L::stack_frames_offset + 14 * 4096) &&
                zero(arena + L::stack_frames_offset + 15 * 4096),
            "partial creation rollback");
    for (auto &lease : reserved)
        if (lease)
            require(frames.release(*lease), "reservation release");
    require(root() == kernel_root && frames.used() == pin_retained() && active == L::domain_count && !program.running(),
            "final root/lease state");
#ifdef AURORA_UEFI_PINS
    pin_final();
    Serial::text("AURORA_UEFI_DOMAIN_CLEANUP_OK: used=");
    Serial::number(pin_retained());
    Serial::text("\r\nAURORA_UEFI_RUNTIME_OK\r\n");
#else
    Serial::text("AURORA_UEFI_DOMAIN_CLEANUP_OK: used=0\r\nAURORA_UEFI_RUNTIME_OK\r\n");
#endif
    return true;
#endif
}
} // namespace aurora::uefi
#endif
