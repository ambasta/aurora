#include "scheduler.hpp"
#include "schedule-policy.hpp"
#include "retained-scheduler.hpp"
#include "address-spaces.hpp"
#include "apic.hpp"
#include "console.hpp"
#include "bios-fixture.hpp"
#include <array>
auto resume_integer(const std::uint64_t *words) -> std::uint64_t asm("aurora_resume_integer");
namespace aurora::user {
namespace {
using hardware::Apic;
using hardware::Protection;
using hardware::Serial;
class Task final {
public:
    DomainHandle domain;
    IntegerContext context;
};
constinit std::array<Task, 3> tasks{};
// A physical dispatch binding, not a second task lifecycle or budget ledger.
constinit std::optional<scheduler::Binding> dispatch;
constinit bool source_irq_call = false;
auto binding_valid(const scheduler::Binding &binding) -> bool {
    return binding.slot < tasks.size() && binding.sequence != 0 && binding.stamp != 0 &&
           AddressSpaces::incarnation(tasks[binding.slot].domain) == binding.stamp;
}
class SchedulerPlatform final {
public:
    [[noreturn]] static auto fail() -> void {
        __builtin_trap();
    }
    [[gnu::noinline]] static auto quiet() -> bool {
        std::uint64_t flags;
        asm volatile("pushfq; popq %0" : "=r"(flags));
        if ((flags & (1ULL << 9)) != 0)
            return false;
        if (source_irq_call)
            return dispatch && binding_valid(*dispatch) && AddressSpaces::active(tasks[dispatch->slot].domain);
        return Protection::current_root() == Protection::kernel_root() && Protection::verify();
    }
};
constinit scheduler::Root<SchedulerPlatform> owner;
#ifdef AURORA_BIOS_FIXTURE
constinit bool owner_refusals_checked = false;
// Exercise rejection at the real authenticated interrupt boundary, after ACK.
// These probes neither manufacture a timer receipt nor perform a second effect.
auto checked_tick(const scheduler::Binding &binding) -> bool {
    if (owner_refusals_checked)
        return owner.observe_tick(binding);
    const auto phase = owner.phase(binding.slot);
    const auto used = owner.used(binding.slot);
    const auto remaining = owner.remaining(binding.slot);
    const auto reason = owner.reason(binding.slot);
    auto stale = binding;
    stale.stamp = 0;
    auto replay = binding;
    replay.sequence = 0;
    if (owner.observe_tick(stale) || owner.observe_tick(replay) || owner.ack_retired(binding) ||
        owner.phase(binding.slot) != phase || owner.used(binding.slot) != used ||
        owner.remaining(binding.slot) != remaining || owner.reason(binding.slot) != reason || remaining == 0 ||
        used == UINT64_MAX || !owner.observe_tick(binding))
        return false;
    if (owner.observe_tick(binding) || owner.phase(binding.slot) != scheduler::Phase::observed ||
        owner.used(binding.slot) != used + 1 || owner.remaining(binding.slot) != remaining - 1 ||
        owner.reason(binding.slot) != scheduler::Terminal::tick)
        return false;
    owner_refusals_checked = true;
    return true;
}
#endif
constinit bool restarted = false;
constinit unsigned probe_ticks = 0;
auto log(std::string_view kind, std::size_t task) -> void {
    Serial::text("AURORA_SCHEDULE_");
    Serial::text(kind);
    Serial::text(": task=");
    Serial::number(task + (restarted ? 3 : 0));
    Serial::text(" root=");
    Serial::number(Protection::current_root());
    Serial::text("\r\n");
}
} // namespace
auto Scheduler::interrupt(std::uint64_t vector, std::uint64_t code, std::uint64_t instruction, std::uint64_t frame)
    -> int {
    if (vector == Apic::vector && Apic::drain_interrupt(instruction, code, frame))
        return 0;
    if (!dispatch || !binding_valid(*dispatch) || source_irq_call)
        return -1;
    const auto slot = dispatch->slot;
    auto &task = tasks[slot];
    const auto *contract = UserPrograms::contract(slot);
    if (contract == nullptr || code != 0x1b || frame < Protection::entry_stack_bottom ||
        frame > Protection::entry_stack_top - 176 || frame % 8 != 0 || !AddressSpaces::active(task.domain))
        return -1;
#ifdef AURORA_BIOS_FIXTURE
    if (bios::selected(bios::Fixture::bios_schedule_root)) {
        if (vector == Apic::vector) {
            const auto root = Protection::kernel_root();
            asm volatile("mov %0, %%cr3" : : "r"(root) : "memory");
            return -1;
        }
    }
#endif
    IntegerContext captured;
    const auto *words = reinterpret_cast<const volatile std::uint64_t *>(frame);
    for (std::size_t i = 0; i < 22; ++i)
        captured.words()[i] = words[i];
#ifdef AURORA_BIOS_FIXTURE
    if (bios::selected(bios::Fixture::bios_schedule_context)) {
        if (vector == Apic::vector)
            captured.words()[18] = 8;
    }
#endif
    if (!captured.valid(*contract) || captured.words()[15] != vector || captured.words()[16] != 0 ||
        captured.words()[17] != instruction || captured.words()[18] != code)
        return -1;
    if (vector == Apic::vector) {
        if (!Apic::acknowledge())
            return -1;
        source_irq_call = true;
#ifdef AURORA_BIOS_FIXTURE
        const bool accepted = checked_tick(*dispatch);
#else
        const bool accepted = owner.observe_tick(*dispatch);
#endif
        source_irq_call = false;
        if (!accepted)
            return -1;
        const auto probe = UserPrograms::probe();
        if (slot == 0 && instruction >= probe[0] && instruction < probe[1]) {
            constexpr std::array<std::uint64_t, 15> sentinels{
                255, 238, 221, 204, 187, 170, 153, 136, 119, 102, 85, 68, 51, 34, 17};
            for (std::size_t i = 0; i < 15; ++i)
                if (captured.words()[i] != sentinels[i])
                    return -1;
            if ((captured.words()[19] & 0x400) == 0)
                return -1;
            ++probe_ticks;
        }
        task.context = captured;
        Serial::text("AURORA_TIMER_FRAME: task=");
        Serial::number(slot + (restarted ? 3 : 0));
        Serial::text(" pc=");
        Serial::number(instruction);
        Serial::text(" flags=");
        Serial::number(captured.words()[19]);
        Serial::text(" frame=");
        Serial::number(frame);
        Serial::text(" isr=1 eoi=1\r\n");
        log("TICK", slot);
        return 1;
    }
    const auto event = captured.terminal(*contract);
    if (event == ProgramEvent::rejected || !Apic::stop())
        return -1;
    scheduler::Terminal terminal = scheduler::Terminal::none;
    switch (event) {
    case ProgramEvent::returned:
        terminal = scheduler::Terminal::returned;
        break;
    case ProgramEvent::bounds:
        terminal = scheduler::Terminal::bounds;
        break;
    case ProgramEvent::overflow:
        terminal = scheduler::Terminal::overflow;
        break;
    case ProgramEvent::division_zero:
        terminal = scheduler::Terminal::division_zero;
        break;
    case ProgramEvent::shift_count:
        terminal = scheduler::Terminal::shift_count;
        break;
    case ProgramEvent::rejected:
        return -1;
    }
    source_irq_call = true;
    const bool accepted = owner.observe_terminal(*dispatch, terminal);
    source_irq_call = false;
    if (!accepted)
        return -1;
    task.context = captured;
    Serial::text("AURORA_SCHEDULE_TERMINAL: task=");
    Serial::number(slot + (restarted ? 3 : 0));
    Serial::text(" vector=");
    Serial::number(vector);
    Serial::text(" pc=");
    Serial::number(instruction);
    Serial::text(" value=");
    Serial::number(captured.words()[14]);
    Serial::text("\r\n");
    log("EVENT", slot);
    return 1;
}
auto Scheduler::run(memory::PhysicalPages &pages) -> bool {
    if (!Protection::verify() || pages.used() != 0)
        return false;
    owner.create();
    std::uint64_t cr0, cr4;
    asm volatile("mov %%cr0, %0; mov %%cr4, %1" : "=r"(cr0), "=r"(cr4));
    if ((cr4 & ((1ULL << 16) | (1ULL << 18))) != 0)
        return false; // No FSGSBASE or XSAVE user state.
    cr0 |= 1ULL << 3; // TS: unsupported x87/MMX/SIMD use faults instead of sharing state.
    asm volatile("mov %0, %%cr0" : : "r"(cr0) : "memory");
    if (!Apic::initialize()) {
        Serial::text("AURORA_APIC_UNSUPPORTED\r\n");
        return false;
    }
    Serial::text("AURORA_APIC_OK: xAPIC one-shot, uncalibrated, BSP\r\n");
    if (!Apic::pending_test())
        return false;
    Serial::text("AURORA_TIMER_DRAIN_OK: pending IRQ consumed in authorized kernel window\r\n");
    if (!AddressSpaces::initialize(pages))
        return false;
    for (std::size_t i = 0; i < tasks.size(); ++i) {
        auto domain = AddressSpaces::create(i);
        const auto *contract = UserPrograms::contract(i);
        if (!domain || contract == nullptr)
            return false;
        tasks[i].domain = *domain;
        tasks[i].context.fresh(*contract);
        const auto stamp = AddressSpaces::incarnation(*domain);
        if (!stamp || !owner.admit(i, *stamp, i == 1 ? 24U : 256U))
            return false;
    }
    const auto original_frame = AddressSpaces::stack_frame(tasks[0].domain, 0);
    unsigned switches = 0;
    for (unsigned round = 0; round < 2; ++round) {
        while (!owner.complete()) {
            const auto selected = owner.select();
            if (selected.action != scheduler::Select::selected || dispatch || !binding_valid(selected.binding))
                return false;
            const auto i = selected.binding.slot;
            auto &task = tasks[i];
            const auto *contract = UserPrograms::contract(i);
            if (contract == nullptr || !task.context.valid(*contract))
                return false;
            // No source loan or query spans activation, execution or IRQ drain.
            dispatch = selected.binding;
            if (!AddressSpaces::activate(task.domain))
                return false;
            log("ENTER", i);
            if (!Apic::arm())
                return false;
#ifdef AURORA_BIOS_FIXTURE
            if (bios::selected(bios::Fixture::bios_schedule_forged)) {
                asm volatile("int $64" : : : "memory");
            }
#endif
            if (resume_integer(task.context.words().data()) != 1 || !dispatch ||
                dispatch->slot != selected.binding.slot || dispatch->stamp != selected.binding.stamp ||
                dispatch->sequence != selected.binding.sequence || !binding_valid(*dispatch) ||
                !task.context.valid(*contract) || !AddressSpaces::active(task.domain))
                return false;
            if (!AddressSpaces::deactivate(task.domain) || !Apic::drain())
                return false;
            log("RESTORE", i);
            const auto restored = owner.finish_restore(*dispatch);
            ++switches;
            if (restored == scheduler::Finish::runnable) {
                dispatch.reset();
                continue;
            }
            if (restored != scheduler::Finish::retiring)
                return false;
            // The following expected results belong to this executable fixture,
            // not to source scheduling policy or physical retirement authority.
            const auto reason = owner.reason(i);
            if (reason == scheduler::Terminal::tick) {
                if (i != 1 || owner.used(i) != 24 || owner.remaining(i) != 0)
                    return false;
                log("CANCEL", i);
            } else if (i == 0) {
                if (reason != scheduler::Terminal::returned || task.context.words()[14] != 42 || owner.used(i) < 2)
                    return false;
                log("RESULT42", i);
            } else if (i == 2) {
                if (reason != scheduler::Terminal::bounds)
                    return false;
                log("BOUNDS", i);
            } else {
                return false;
            }
            const auto stale = task.domain;
            if (!binding_valid(*dispatch) || !AddressSpaces::destroy(task.domain) ||
                AddressSpaces::incarnation(stale) || AddressSpaces::activate(stale))
                return false;
            task.context = IntegerContext{};
            if (task.context.valid(*contract) || !owner.ack_retired(*dispatch))
                return false;
            dispatch.reset();
            log("RETIRED", i);
        }
        if (round == 0) {
            if (pages.used() != 0 || !Apic::pending_test())
                return false;
            auto fresh = AddressSpaces::create(0);
            if (!fresh || !AddressSpaces::stack_zero(*fresh) || AddressSpaces::stack_frame(*fresh, 0) != original_frame)
                return false;
            tasks[0].domain = *fresh;
            tasks[0].context.fresh(*UserPrograms::contract(0));
            const auto stamp = AddressSpaces::incarnation(*fresh);
            if (!stamp || !owner.admit(0, *stamp, 256))
                return false;
            restarted = true;
            Serial::text("AURORA_SCHEDULE_REUSE_OK: retired frames scrubbed; fresh clean task after cancellation\r\n");
        }
    }
    if (!Apic::pending_test() || pages.used() != 0 || !Protection::verify() || switches < 28 || probe_ticks < 2)
        return false;
#ifdef AURORA_BIOS_FIXTURE
    if (!owner_refusals_checked)
        return false;
    Serial::text("AURORA_SCHEDULER_OWNER_OK: invalid, premature and replayed receipts rejected\r\n");
#endif
    Serial::text("AURORA_TIMER_RETIRE_OK: no stale IRQ authority after teardown\r\n");
    Serial::text("AURORA_CONTEXT_OK: all15 GPRs and DF resumed; probe_ticks=");
    Serial::number(probe_ticks);
    Serial::text("\r\n");
    Serial::text("AURORA_SCHEDULE_OK: integer preemption, budget cancellation, fault cleanup, roots restored\r\n");
    return true;
}
} // namespace aurora::user
