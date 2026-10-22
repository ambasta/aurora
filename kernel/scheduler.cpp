#include "scheduler.hpp"
#include "schedule-policy.hpp"
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
    SliceBudget budget{256};
    bool done = false;
};
constinit std::array<Task, 3> tasks{};
constinit std::optional<std::size_t> running;
constinit ProgramEvent outcome = ProgramEvent::rejected;
constinit bool tick = false;
constinit bool started = false;
constinit bool restarted = false;
constinit unsigned probe_ticks = 0;
extern const std::array<std::uint64_t, 2> probe asm("aurora_schedule_probe");
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
    if (!running || *running >= tasks.size())
        return -1;
    auto &task = tasks[*running];
    const auto *contract = UserPrograms::contract(*running);
    if (contract == nullptr || code != 0x1b || frame < Protection::entry_stack_bottom ||
        frame > Protection::entry_stack_top - 176 || frame % 8 != 0 || !AddressSpaces::active(task.domain))
        return -1;
#ifdef AURORA_BIOS_SCHEDULE_FIXTURE
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
#ifdef AURORA_BIOS_SCHEDULE_FIXTURE
    if (bios::selected(bios::Fixture::bios_schedule_context)) {
        if (vector == Apic::vector)
            captured.words()[18] = 8;
    }
#endif
    if (!captured.valid(*contract) || captured.words()[15] != vector || captured.words()[16] != 0)
        return -1;
    if (vector == Apic::vector) {
        if (!Apic::acknowledge() || !task.budget.consume())
            return -1;
        if (*running == 0 && instruction >= probe[0] && instruction < probe[1]) {
            constexpr std::array<std::uint64_t, 15> sentinels{
                255, 238, 221, 204, 187, 170, 153, 136, 119, 102, 85, 68, 51, 34, 17};
            for (std::size_t i = 0; i < 15; ++i)
                if (captured.words()[i] != sentinels[i])
                    return -1;
            if ((captured.words()[19] & 0x400) == 0)
                return -1;
            ++probe_ticks;
        }
        tick = true;
        task.context = captured;
        Serial::text("AURORA_TIMER_FRAME: task=");
        Serial::number(*running + (restarted ? 3 : 0));
        Serial::text(" pc=");
        Serial::number(instruction);
        Serial::text(" flags=");
        Serial::number(captured.words()[19]);
        Serial::text(" frame=");
        Serial::number(frame);
        Serial::text(" isr=1 eoi=1\r\n");
        log("TICK", *running);
        return 1;
    }
    const auto event = captured.terminal(*contract);
    if (event == ProgramEvent::rejected || !Apic::stop())
        return -1;
    outcome = event;
    task.context = captured;
    Serial::text("AURORA_SCHEDULE_TERMINAL: task=");
    Serial::number(*running + (restarted ? 3 : 0));
    Serial::text(" vector=");
    Serial::number(vector);
    Serial::text(" pc=");
    Serial::number(instruction);
    Serial::text(" value=");
    Serial::number(captured.words()[14]);
    Serial::text("\r\n");
    log("EVENT", *running);
    return 1;
}
auto Scheduler::run(memory::PhysicalPages &pages) -> bool {
    if (started || !Protection::verify() || pages.used() != 0)
        return false;
    started = true;
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
        tasks[i].budget = SliceBudget{i == 1 ? 24U : 256U};
    }
    const auto original_frame = AddressSpaces::stack_frame(tasks[0].domain, 0);
    unsigned completed = 0;
    unsigned switches = 0;
    for (unsigned round = 0; round < 2; ++round) {
        while (completed < tasks.size()) {
            for (std::size_t i = 0; i < tasks.size(); ++i) {
                auto &task = tasks[i];
                if (task.done)
                    continue;
                const auto *contract = UserPrograms::contract(i);
                if (contract == nullptr || !task.context.valid(*contract) || task.budget.exhausted() ||
                    !AddressSpaces::activate(task.domain))
                    return false;
                running = i;
                tick = false;
                outcome = ProgramEvent::rejected;
                log("ENTER", i);
                if (!Apic::arm())
                    return false;
#ifdef AURORA_BIOS_SCHEDULE_FIXTURE
                if (bios::selected(bios::Fixture::bios_schedule_forged)) {
                    asm volatile("int $64" : : : "memory");
                }
#endif
                if (resume_integer(task.context.words().data()) != 1 || !AddressSpaces::active(task.domain))
                    return false;
                if (!AddressSpaces::deactivate(task.domain) || !Apic::drain())
                    return false;
                log("RESTORE", i);
                running.reset();
                ++switches;
                if (tick && !task.budget.exhausted())
                    continue;
                if (tick) {
                    if (i != 1 || task.budget.used() != 24)
                        return false;
                    log("CANCEL", i);
                } else {
                    if (i == 0) {
                        if (outcome != ProgramEvent::returned || task.context.words()[14] != 42 ||
                            task.budget.used() < 2)
                            return false;
                        log("RESULT42", i);
                    } else if (i == 2) {
                        if (outcome != ProgramEvent::bounds)
                            return false;
                        log("BOUNDS", i);
                    } else
                        return false;
                }
                const auto stale = task.domain;
                if (!AddressSpaces::destroy(task.domain) || AddressSpaces::activate(stale))
                    return false;
                task.context = IntegerContext{};
                task.done = true;
                ++completed;
                if (task.context.valid(*contract))
                    return false;
                log("RETIRED", i);
            }
        }
        if (round == 0) {
            if (pages.used() != 0 || !Apic::pending_test())
                return false;
            auto fresh = AddressSpaces::create(0);
            if (!fresh || !AddressSpaces::stack_zero(*fresh) || AddressSpaces::stack_frame(*fresh, 0) != original_frame)
                return false;
            tasks[0].domain = *fresh;
            tasks[0].context.fresh(*UserPrograms::contract(0));
            tasks[0].budget = SliceBudget{256};
            tasks[0].done = false;
            completed = 2;
            restarted = true;
            Serial::text("AURORA_SCHEDULE_REUSE_OK: retired frames scrubbed; fresh clean task after cancellation\r\n");
        }
    }
    if (!Apic::pending_test() || pages.used() != 0 || !Protection::verify() || switches < 28 || probe_ticks < 2)
        return false;
    Serial::text("AURORA_TIMER_RETIRE_OK: no stale IRQ authority after teardown\r\n");
    Serial::text("AURORA_CONTEXT_OK: all15 GPRs and DF resumed; probe_ticks=");
    Serial::number(probe_ticks);
    Serial::text("\r\n");
    Serial::text("AURORA_SCHEDULE_OK: integer preemption, budget cancellation, fault cleanup, roots restored\r\n");
    return true;
}
} // namespace aurora::user
