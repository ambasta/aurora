// One reusable protected application contract; no command or text policy here.
constinit ParkedRun console_read;
console::ServiceArgument console_grant{};
U64 console_ticket{};
bool console_setup{};
[[nodiscard]] auto console_quiescent() -> bool {
    return root() == kernel_root && irq_off() && active == L::domain_count && saved_rsp == 0 && !program.running() &&
           !timer_armed && !timer_owner && !timer_draining && text_owner && domains[0].handle &&
           registry.ready(*text_owner) && registry.index(*text_owner) == 0 && registry.index(*domains[0].handle) == 0 &&
           text_region.is_open() && !text_region.faulted();
}
[[nodiscard]] auto console_launch(U64 generation, U64 region) -> std::array<U64, 7> {
    U64 argument = 0;
#ifdef AURORA_RUNTIME_FIXTURE
    argument = static_cast<U64>(fixture == Fixture::console_fault);
#endif
    return {1, generation, region, argument, 0, 0, 0x202};
}
[[nodiscard]] auto console_parked() -> bool {
    return console_quiescent() && console_read.context && console_read.owner && domains[0].contract &&
           registry.index(*console_read.owner) == 0 && registry.ready(*console_read.owner) &&
           console_read.root == domains[0].tables->root() && console_read.region == text_region.id() &&
           console_read.generation == console_grant.generation && console_read.epoch == text_epoch &&
           console_read.epoch == timer_epoch && console_read.ticket != 0 && console_read.ticket == console_ticket &&
           console_grant.grant && launch == console_launch(console_read.generation, console_read.region) &&
           console_read.initial == 128 && console_read.remaining > 0 &&
           console_read.remaining + console_read.ticks == console_read.initial &&
           console_read.context->call_frame(*domains[0].contract, images::clean_console_next_pc) && verify(domains[0]);
}
class ProtectedConsolePlatform final {
public:
    static auto quiet() -> bool {
        return text_active() || console_parked() || (console_setup && console_quiescent());
    }
    [[noreturn]] static auto fail() -> void {
        stop("protected console grant");
    }
};
class ProtectedConsoleTransport final {
public:
    static auto next() -> console::Sample {
        return Serial::next();
    }
    static auto try_put(std::uint8_t byte) -> console::PutResult {
#ifdef AURORA_RUNTIME_FIXTURE
        if (fixture == Fixture::console_output) {
            static unsigned written{};
            if (written++ == 2)
                return console::PutResult::timeout;
        }
#endif
        return Serial::try_put(byte);
    }
};
using ProtectedConsole = console::Session<ProtectedConsoleTransport, ProtectedConsolePlatform>;
#include "console-wait.inc"
[[nodiscard]] auto console_retirable() -> bool {
    return !console_read.context && !console_read.owner && !console_read.ready && !console_read.ticket &&
           !console_grant.grant && !console_grant.generation && !console_setup && !console_waiting &&
           !console_wait_stack && console_wakes == console_expected_wake;
}
[[nodiscard]] auto program_poll_policy() -> bool {
    return console_parked();
}
[[nodiscard]] auto program_boundary() -> bool {
    const auto current = stack();
    return console_parked() && !console_waiting && console_wait_stack == 0 && current % 8 == 0 &&
           current >=
               arena + Handoff::stack_bottom + ConsoleWakeContext::handler_reserve + ConsoleWakeContext::byte_count &&
           current <= arena + Handoff::stack_top && timer_stop() && timer_quiet(0x100, false) &&
           timer_quiet(0x200, false);
}
auto console_result(U64 *words, console::RawSample sample) -> void {
    require(sample.byte_present <= 1 && sample.damaged <= 1 && sample.byte <= 255 &&
                (sample.byte_present || sample.byte == 0),
            "console canonical sample");
    words[14] = sample.byte_present;
    words[11] = sample.byte;
    words[12] = sample.damaged;
}
[[nodiscard, gnu::noinline]] auto console_region_trap(U64 frame) -> U64 {
    require(text_active(), "console application active");
    auto *words = reinterpret_cast<U64 *>(frame);
    const auto site = words[17];
    if (site != images::clean_console_next_pc && site != images::clean_console_put_pc)
        return text_trap(frame);
    const auto context =
        ServiceContext::capture_bytes(std::span<const U64>{words, 22}, frame, *domains[0].contract, site);
    require(context && words[8] == 1 && words[9] == console_grant.generation && !console_read.context,
            "console exact site and private grant");
    if (site == images::clean_console_put_pc) {
        words[14] = ProtectedConsole::put(console_grant.grant, console_grant.generation, words[11]);
        return 0;
    }
    const auto sample = ProtectedConsole::poll(console_grant.grant, console_grant.generation);
    if (sample.byte_present || sample.damaged) {
        console_result(words, sample);
        return 0;
    }
    require(timer_stop() && console_ticket != UINT64_MAX, "console stop and ticket");
    const auto prior_ticks = timer_ticks;
    // Charge the discarded partial quantum; resumption never renews the budget.
#ifdef AURORA_RUNTIME_FIXTURE
    if (fixture == Fixture::console_budget) {
        while (timer_remaining > 1) {
            const auto debit =
                BudgetTransition::decode(language_budget_tick(timer_initial, timer_remaining, timer_ticks),
                                         timer_initial,
                                         timer_remaining,
                                         timer_ticks);
            require(debit && debit->resume(), "console cumulative exhaustion fixture");
            timer_ticks = debit->used();
            timer_remaining = debit->remaining();
        }
    }
#endif
    const auto transition = BudgetTransition::decode(
        language_budget_tick(timer_initial, timer_remaining, timer_ticks), timer_initial, timer_remaining, timer_ticks);
    require(transition.has_value(), "console boundary debit");
    timer_ticks = transition->used();
    timer_remaining = transition->remaining();
    timer_exhausted = !transition->resume();
    Serial::text("AURORA_CONSOLE_DEBIT: epoch=");
    Serial::number(timer_epoch);
    Serial::text(" count=");
    Serial::number(timer_ticks - prior_ticks);
    Serial::text(" used=");
    Serial::number(timer_ticks);
    Serial::text(" remaining=");
    Serial::number(timer_remaining);
    Serial::text("\r\n");
    if (!timer_exhausted) {
        save_parked_run(console_read, *context);
        console_read.owner = *text_owner;
        console_read.root = root();
        console_read.region = text_region.id();
        console_read.generation = console_grant.generation;
        console_read.epoch = text_epoch;
        console_read.ticket = ++console_ticket;
        console_read.initial = timer_initial;
    }
    park_run(*text_owner);
    return 1;
}
[[nodiscard]] auto console_resume(U64 ticket) -> bool {
    if (!console_parked() || ticket != console_read.ticket || !console_read.ready)
        return false;
    timer_owner = *console_read.owner;
    timer_owner_epoch = timer_epoch = console_read.epoch;
    timer_initial = console_read.initial;
    const auto frame = restore_parked_run(console_read);
    console_result(reinterpret_cast<U64 *>(frame), *console_read.ready);
    Serial::text("AURORA_CONSOLE_RESUME: ticket=");
    Serial::number(ticket);
    Serial::text(" epoch=");
    Serial::number(timer_epoch);
    Serial::text(" used=");
    Serial::number(timer_ticks);
    Serial::text(" remaining=");
    Serial::number(timer_remaining);
    Serial::text("\r\n");
    console_read.clear();
    activate_parked_run(0);
    timer_armed = true;
    require(text_active() && timer_arm(), "console resume original budget");
    require(resume(frame) == 1, "console fresh continuation");
    timer_finish();
    return true;
}
[[nodiscard]] auto console_cancel(U64 ticket) -> bool {
    if (!console_parked() || ticket != console_read.ticket || console_waiting || console_wait_stack)
        return false;
    require(timer_stop() && timer_quiet(0x100, false) && timer_quiet(0x200, false), "console cancel quiet");
    console_read.clear();
    console_setup = true;
    ProtectedConsole::release(console_grant);
    console_setup = false;
    console_grant = {};
    return true;
}
[[gnu::noinline]] auto run_console_application(memory::PhysicalPages &pool) -> void {
    require(pool.used() == 0 && create(0) == 0 && !domains[1].handle, "console single application");
    auto &domain = domains[0];
    require(text_region.open(pool,
                             view(arena + Handoff::pool_offset, kernel::bytes::Region::backing_bytes),
                             arena + Handoff::pool_offset,
                             64),
            "console private region");
    text_owner = *domain.handle;
    Serial::initialize_input();
    console_setup = true;
    console_grant = ProtectedConsole::open();
    console_setup = false;
    launch = console_launch(console_grant.generation, text_region.id());
    require(verify(domain) && launch_domain(0, *text_owner), "console entry continuation");
    timer_finish();
    while (console_read.context) {
        require(console_parked(), "console parked authority");
        const auto ticket = console_read.ticket;
        Serial::text("AURORA_CONSOLE_PARK: ticket=");
        Serial::number(ticket);
        Serial::text(" live=");
        Serial::number(text_region.metrics().live_allocations);
        Serial::text(" used=");
        Serial::number(text_region.metrics().used);
        Serial::text(" epoch=");
        Serial::number(text_epoch);
        Serial::text(" ticks=");
        Serial::number(console_read.ticks);
        Serial::text(" remaining=");
        Serial::number(console_read.remaining);
        Serial::text("\r\n");
        require(!console_resume(ticket) && !console_resume(ticket - 1) && !console_cancel(ticket - 1) &&
                    !console_cancel(ticket + 1) && !retire(0),
                "console pending authority");
#ifdef AURORA_RUNTIME_FIXTURE
        if (fixture == Fixture::console_cancel) {
            require(console_cancel(ticket) && !console_resume(ticket) && !console_cancel(ticket),
                    "console cancelled ticket");
            break;
        }
#endif
        while (!console_read.ready) {
            auto sample = ProtectedConsole::poll(console_grant.grant, console_grant.generation);
#ifdef AURORA_RUNTIME_FIXTURE
            if (fixture == Fixture::console_input)
                sample = {0, 0, 1};
#endif
            if (sample.byte_present || sample.damaged)
                console_read.ready = sample;
            else
                program_wait_sample();
        }
        require(!console_resume(ticket + 1) && !console_cancel(ticket + 1), "console stale ticket preserves sample");
#ifdef AURORA_RUNTIME_FIXTURE
        if (fixture == Fixture::console_cancel_ready) {
            require(console_read.ready && console_cancel(ticket) && !console_resume(ticket),
                    "console ready cancellation");
            break;
        }
#endif
        require(console_resume(ticket) && !console_resume(ticket), "console exactly once resume");
    }
    require(console_quiescent(), "console terminal boundary");
    // Revoke the grant before reclaiming any abandoned user owner.
    if (console_grant.grant) {
        console_setup = true;
        ProtectedConsole::release(console_grant);
        console_setup = false;
        console_grant = {};
    }
    console_read.clear();
    const auto before = text_region.metrics();
    require(text_region.revoke_quiescent() && pool.used() == 0 && text_region.metrics().live_allocations == 0 &&
                text_region.metrics().held_pages == 0,
            "console reclaim");
    text_owner.reset();
    text_epoch = 0;
    launch = {};
    require(retire(0) && frames.used() == 0 && !console_resume(console_ticket) && !console_cancel(console_ticket),
            "console retirement rejects stale ticket");
    Serial::text("AURORA_CONSOLE_REGION_DONE: value=");
    Serial::number(program.value());
    Serial::text(" event=");
    Serial::number(static_cast<U64>(program.event()));
    Serial::text(" exhausted=");
    Serial::number(timer_exhausted);
    Serial::text(" ticks=");
    Serial::number(timer_ticks);
    Serial::text(" remaining=");
    Serial::number(timer_remaining);
    Serial::text(" abandoned=");
    Serial::number(before.live_allocations);
    Serial::text(" peak=");
    Serial::number(before.peak_used);
    Serial::text(" used=0 pages=0\r\n");
}
