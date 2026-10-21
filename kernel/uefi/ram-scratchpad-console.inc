// Opt-in Console/Call/Serve composition. Aurora owns grammar, scalar encoding,
// file bytes and presentation; native code owns only transport and lifetimes.
extern "C" void __au_runtime_scratchpad_input(const void *, void *);
extern "C" auto __au_runtime_scratchpad_response(const void *) -> U64;
using ScratchpadResponse = scratchpad::Response;
using ScratchpadKind = ScratchpadResponse::Kind;

// The command binding survives only until successful physical retirement. It
// contains no second input copy and cannot answer a later read. A captured result
// is quarantined here, never handed to Console before one-way settlement.
struct ScratchpadTransfer final {
    const user::DomainHandle caller, service;
    const user::ProgramContract contract;
    const U64 caller_root, service_root, service_generation, cleanup, operation, count;
    const ipc::Endpoint endpoint;
    const std::array<U64, 4> backing;
    scratchpad::Result result{};
    bool captured{};
};
std::optional<ScratchpadTransfer> scratchpad_transfer;
bool scratchpad_console_owned{};
auto scratchpad_discard() -> void {
    ram_clear(scratchpad_transfer);
}
auto scratchpad_clear_inactive_accounting() -> void {
    require(!timer_armed && !timer_draining && !timer_owner && !run_authority, "scratchpad inactive accounting");
    ram_run_epoch = 0;
    selected_client = 2;
    timer_initial = timer_remaining = timer_ticks = timer_resumes = timer_drains = 0;
    timer_context_hits = timer_compiled_hits = 0;
    timer_exhausted = false;
    // Historical timer_epoch and both monotonic epoch/generation watermarks stay intact.
}
#include "console-wait.inc"

[[nodiscard]] auto scratchpad_empty_caller() -> bool {
    const auto &caller = domains[0];
    if (caller.handle || caller.contract || caller.tables || ram_caller_wait.context || ram_caller_wait.authority ||
        ram_caller_wait.service || ram_caller_wait.endpoint.slot() || ram_caller_wait.endpoint.generation() ||
        ram_caller_wait.ticket || ram_caller_wait.remaining || ram_caller_wait.ticks || ram_caller_wait.resumes ||
        ram_caller_wait.compiled || ram_caller_wait.contexts)
        return false;
    for (const auto &lease : caller.stacks)
        if (lease)
            return false;
    for (const auto word : ram_caller_wait.launch)
        if (word)
            return false;
    return true;
}
[[nodiscard]] auto scratchpad_parked_service() -> bool {
    const auto &saved = ram_service_wait;
    if (!ram_lifetime_valid() || !registry.ready(ram_lifetime->owner) || !domains[1].handle ||
        !registry.ready(*domains[1].handle) || domains[1].image != 1 || frames.used() != 4 || !saved.context ||
        saved.authority || saved.service || saved.endpoint.slot() || saved.endpoint.generation() || saved.ticket ||
        !saved.context->call_frame(ram_lifetime->contract, images::bounds_serve_pc) ||
        saved.context->words()[8] != ram_lifetime->grant || saved.context->words()[9] != ram_lifetime->generation ||
        saved.remaining == 0 || saved.remaining > 120 || saved.ticks >= 120 ||
        (saved.remaining + saved.ticks != 8 && saved.remaining + saved.ticks != 120) || saved.resumes > saved.ticks ||
        saved.compiled > saved.ticks || saved.contexts > saved.ticks)
        return false;
    for (const auto word : saved.launch)
        if (word)
            return false;
    return true;
}
// The waiting variant permits only the one expected Console timer IRQ. It does
// not stop that timer or recursively demand the nonwaiting entry predicate.
[[nodiscard]] auto scratchpad_mechanism_quiet(bool waiting) -> bool {
    const auto current = stack();
    if (current % 8 != 0 ||
        current <
            arena + Handoff::stack_bottom + ConsoleWakeContext::handler_reserve + ConsoleWakeContext::byte_count ||
        current > arena + Handoff::stack_top || root() != kernel_root || !irq_off() || active != L::domain_count ||
        saved_rsp != 0 || program.running() || timer_armed || timer_draining || timer_owner || timer_owner_epoch != 0 ||
        run_authority || selected_phase != ipc::Phase::inactive || transaction != 0 || ram_run_epoch != 0 ||
        timer_initial || timer_remaining || timer_ticks || timer_resumes || timer_drains || timer_context_hits ||
        timer_compiled_hits || timer_exhausted)
        return false;
    for (const auto word : launch)
        if (word)
            return false;
    if (waiting)
        return scratchpad_console_owned && console_waiting && console_wait_stack != 0 &&
               console_wakes < console_expected_wake && console_expected_wake - console_wakes == 1 &&
               timer_quiet(0x100, true) && timer_quiet(0x200, true);
    return !console_waiting && console_wait_stack == 0 && console_wakes == console_expected_wake && timer_stop() &&
           timer_quiet(0x100, false) && timer_quiet(0x200, false);
}
[[nodiscard]] auto scratchpad_idle(bool waiting = false) -> bool {
    return scratchpad_mechanism_quiet(waiting) && ram_state == RamState::idle && !ram_command && !scratchpad_transfer &&
           scratchpad_empty_caller() && mailbox && mailbox->revoked() && mailbox->scrubbed() &&
           scratchpad_parked_service();
}
[[nodiscard]] auto scratchpad_retired() -> bool {
    if (!scratchpad_mechanism_quiet(false) || ram_state != RamState::absent || ram_lifetime || ram_command ||
        scratchpad_transfer || !scratchpad_empty_caller() || frames.used() != 0 || (mailbox && !mailbox->revoked()) ||
        domains[1].handle || domains[1].contract || domains[1].tables || ram_service_wait.context ||
        ram_service_wait.authority || ram_service_wait.service || ram_service_wait.endpoint.slot() ||
        ram_service_wait.endpoint.generation() || ram_service_wait.ticket || ram_service_wait.remaining ||
        ram_service_wait.ticks || ram_service_wait.resumes || ram_service_wait.compiled || ram_service_wait.contexts)
        return false;
    for (const auto &lease : domains[1].stacks)
        if (lease)
            return false;
    for (const auto word : ram_service_wait.launch)
        if (word)
            return false;
    return true;
}
[[nodiscard]] auto program_boundary() -> bool {
    return scratchpad_idle();
}
[[nodiscard]] auto program_poll_policy() -> bool {
    return scratchpad_console_owned && scratchpad_idle(console_waiting);
}
class ScratchpadInputPlatform final {
public:
    [[nodiscard, gnu::noinline]] static auto quiet() -> bool {
        // The fully retired case is only for a final outcome-only output turn.
        return scratchpad_idle() || scratchpad_retired();
    }
    static auto wait() -> void {
        require(scratchpad_idle(), "scratchpad input cannot wait after shutdown");
        program_wait_sample();
    }
    [[noreturn]] static auto fail() -> void {
        stop("scratchpad Console authority");
    }
};
using ProgramInputSession = console::Session<Serial, ScratchpadInputPlatform>;
[[gnu::noinline]] auto scratchpad_read_input(scratchpad::Submission &input, U64 after_cr) -> void {
    require(!scratchpad_console_owned && scratchpad_idle() && after_cr <= 1, "scratchpad input boundary");
    scratchpad::scrub(input);
    scratchpad::InputArgument argument{ProgramInputSession::open(), after_cr};
    scratchpad_console_owned = true;
    __au_runtime_scratchpad_input(&argument, &input);
    require(input.valid(), "scratchpad canonical submission");
    ProgramInputSession::release(argument.console);
    scratchpad_console_owned = false;
    scratchpad::scrub(argument);
    require(scratchpad_idle(), "scratchpad released input boundary");
}
[[nodiscard, gnu::noinline]] auto scratchpad_write_response(ScratchpadResponse &response) -> bool {
    const bool retired = scratchpad_retired();
    require(!scratchpad_console_owned && response.valid() &&
                (scratchpad_idle() || (retired && response.kind == static_cast<U64>(ScratchpadKind::unavailable))),
            "scratchpad settled output boundary");
    scratchpad::ResponseArgument argument{ProgramInputSession::open(), response};
    scratchpad_console_owned = true;
    scratchpad::scrub(response);
#ifdef AURORA_SCRATCHPAD_FIXTURE
    if (scratchpad_probe == '8' && ram_commands == 2 &&
        argument.response.kind == static_cast<U64>(ScratchpadKind::saved))
        scratchpad_output_left = 2; // Publish "sa", then fail exactly once without a retry.
#endif
    const auto result = __au_runtime_scratchpad_response(&argument);
    ProgramInputSession::release(argument.console);
    scratchpad_console_owned = false;
    scratchpad::scrub(argument);
    require(result <= 1 && (retired ? scratchpad_retired() : scratchpad_idle()), "scratchpad released output boundary");
    return result == 1;
}
[[nodiscard]] auto scratchpad_caller_window() -> scratchpad::CopiedStack::Window {
    require(!scratchpad_console_owned && ram_state == RamState::command && ram_command_valid() && scratchpad_transfer &&
                root() == kernel_root && irq_off() && active == L::domain_count && !timer_armed && !timer_draining &&
                !timer_owner && !timer_owner_epoch && !run_authority && !program.running() && !saved_rsp &&
                domains[0].contract && domains[0].tables && registry.ready(scratchpad_transfer->caller) &&
                registry.index(scratchpad_transfer->caller) == 0 && registry.index(scratchpad_transfer->service) == 1 &&
                RamFileRunAuthority::same_contract(scratchpad_transfer->contract, *domains[0].contract) &&
                domains[0].tables->root() == scratchpad_transfer->caller_root &&
                ram_lifetime->root == scratchpad_transfer->service_root &&
                ram_lifetime->generation == scratchpad_transfer->service_generation &&
                ram_command->cleanup_epoch == scratchpad_transfer->cleanup &&
                ram_command->caller_endpoint.slot() == scratchpad_transfer->endpoint.slot() &&
                ram_command->caller_endpoint.generation() == scratchpad_transfer->endpoint.generation(),
            "scratchpad fixed-copy original identity");
    const PageTables kernel{kernel_root, static_cast<std::size_t>(handoff->get(96))};
    require(interrupt_admission && kernel.verify(arena, *handoff, &*interrupt_admission),
            "scratchpad kernel alias tree");
    const auto &layout = domains[0].contract->layout();
    const auto top = layout.user_stack_top();
    require(top % L::page_size == 0 && top >= layout.user_stack_bottom() &&
                top - layout.user_stack_bottom() >=
                    scratchpad::CopiedStack::reservation + scratchpad::CopiedStack::envelope &&
                scratchpad::CopiedStack::reservation <= L::page_size,
            "scratchpad disjoint fixed stack ranges");
    for (unsigned index = 0; index < 4; ++index) {
        require(domains[0].stacks[index].has_value(), "scratchpad original caller lease");
        const auto physical = frames.address(*domains[0].stacks[index]);
        require(physical && *physical == scratchpad_transfer->backing[index] &&
                    (kernel.entry(*physical) & ~RuntimeTables::accessed_dirty) == (*physical | 3 | RuntimeTables::nx) &&
                    (domains[0].tables->entry(layout.user_stack_bottom() + index * L::page_size) &
                     ~RuntimeTables::accessed_dirty) == (*physical | 7 | RuntimeTables::nx),
                "scratchpad exact private RW/NX stack aliases");
    }
    return scratchpad::CopiedStack::Window{reinterpret_cast<std::byte *>(scratchpad_transfer->backing.back() +
                                                                         L::page_size -
                                                                         scratchpad::CopiedStack::reservation),
                                           scratchpad::CopiedStack::reservation};
}
[[gnu::noinline]] auto scratchpad_stage(scratchpad::Submission &input) -> void {
    require(input.valid() && input.action == 0 && !scratchpad_transfer && ram_command_valid(),
            "scratchpad single stage admission");
    std::array<U64, 4> backing{};
    for (unsigned index = 0; index < 4; ++index) {
        require(domains[0].stacks[index].has_value(), "scratchpad fresh caller lease");
        const auto physical = frames.address(*domains[0].stacks[index]);
        require(physical.has_value(), "scratchpad fresh caller owner");
        backing[index] = *physical;
    }
    scratchpad_transfer.emplace(ScratchpadTransfer{ram_command->caller,
                                                   ram_command->service,
                                                   *domains[0].contract,
                                                   domains[0].tables->root(),
                                                   ram_lifetime->root,
                                                   ram_lifetime->generation,
                                                   ram_command->cleanup_epoch,
                                                   input.command.operation,
                                                   input.command.count,
                                                   ram_command->caller_endpoint,
                                                   backing,
                                                   {},
                                                   false});
    require(scratchpad::CopiedStack::stage(scratchpad_caller_window(), input.command),
            "scratchpad pristine fixed command copy");
    scratchpad::scrub(input);
}
[[gnu::noinline]] auto scratchpad_capture_result() -> void {
    require(scratchpad_transfer && !scratchpad_transfer->captured, "scratchpad one candidate capture");
    // Both fresh launch and resumed completion already ran ram_finish_execution;
    // its final timer drain must precede this exhaustion check and every copy.
    if (ram_state != RamState::command || program.event() != ProgramEvent::returned || program.value() != 1 ||
        timer_exhausted || ram_command->framing.state() != RamFileFraming::State::terminal)
        return;
    auto &copy = *scratchpad_transfer;
#ifdef AURORA_SCRATCHPAD_FIXTURE
    if (scratchpad_probe == '5' && ram_commands == 2)
        scratchpad_caller_window()[scratchpad::CopiedStack::result + offsetof(scratchpad::Result, kind)] =
            std::byte{255}; // Exact completed record, now malformed before native capture.
#endif
    if (scratchpad::CopiedStack::capture(scratchpad_caller_window(),
                                         copy.endpoint.slot(),
                                         copy.endpoint.generation(),
                                         copy.operation,
                                         copy.count,
                                         copy.result) &&
        copy.result.terminal_for(
            copy.operation, ram_command->framing.terminal_reply(), ram_command->framing.data_count()))
        copy.captured = true;
    else
        scratchpad::scrub(copy.result);
}
// No address into the retired pages survives this irreversible conversion.
// Eligibility is consumed before the command is erased or Console can open.
[[gnu::noinline]] auto scratchpad_settle_response(ScratchpadResponse &response, ScratchpadKind fallback) -> void {
    require(!scratchpad_console_owned && scratchpad_transfer && ram_command && ram_lifetime_valid() &&
                !registry.index(scratchpad_transfer->caller) && !domains[0].handle && scratchpad_empty_caller() &&
                mailbox->revoked() && frames.used() == 4 && registry.index(scratchpad_transfer->service) == 1 &&
                scratchpad_transfer->service_root == ram_lifetime->root &&
                scratchpad_transfer->service_generation == ram_lifetime->generation &&
                scratchpad_transfer->cleanup == ram_command->cleanup_epoch,
            "scratchpad original command physically retired");
    response = ScratchpadResponse{fallback};
    if (scratchpad_transfer->captured) {
        const auto &result = scratchpad_transfer->result;
        require(result.terminal_for(scratchpad_transfer->operation,
                                    ram_command->framing.terminal_reply(),
                                    ram_command->framing.data_count()),
                "scratchpad settled terminal relation");
        response.kind = result.kind; // Complete content/missing/saved/refused -> rejected ordinals are exact.
        response.count = result.count;
        response.bytes = result.bytes;
    }
    scratchpad_discard();
    ram_clear(ram_command);
    ram_state = RamState::idle;
    scratchpad_clear_inactive_accounting();
    require(response.valid() && scratchpad_idle(), "scratchpad one-way settled response idle");
}
[[nodiscard]] auto scratchpad_restart() -> bool {
    scratchpad_clear_inactive_accounting();
    const bool started = ram_start();
    scratchpad_clear_inactive_accounting();
    require(started ? scratchpad_idle() : scratchpad_retired(), "scratchpad restart complete boundary");
    return started;
}
[[nodiscard, gnu::noinline]] auto scratchpad_command_run(scratchpad::Submission &input, ScratchpadResponse &response)
    -> bool {
    require(!scratchpad_console_owned && scratchpad_idle() && input.valid() && input.action == 0,
            "scratchpad protected admission boundary");
    if (ram_commands >= 64) {
        scratchpad::scrub(input);
        response = ScratchpadResponse{ScratchpadKind::limit};
        return false;
    }
    const auto cleanup = ram_mint_epoch(), caller_epoch = ram_mint_epoch();
    if (!cleanup || !caller_epoch || create(0) != 0) {
        scratchpad::scrub(input);
        response = ScratchpadResponse{ScratchpadKind::unavailable};
        return false;
    }
    if (!mailbox->bind(*domains[0].handle, *domains[1].handle)) {
        require(retire(0), "scratchpad refused caller reclaimed");
        scratchpad::scrub(input);
        response = ScratchpadResponse{ScratchpadKind::unavailable};
        return false;
    }
    const bool replace = input.command.operation == 1;
    ram_command.emplace(*domains[0].handle,
                        *domains[1].handle,
                        *mailbox->endpoint(*domains[0].handle),
                        *mailbox->endpoint(*domains[1].handle),
                        *cleanup,
                        replace ? RamFileFraming::Right::replace : RamFileFraming::Right::read,
                        replace ? static_cast<unsigned>(input.command.count) : 50U);
    ++ram_commands;
    ram_state = RamState::command;
    scratchpad_stage(input);
    Serial::text("AURORA_SCRATCHPAD_BEGIN: command=");
    Serial::number(ram_commands);
    Serial::text(" caller=");
    Serial::number(*registry.incarnation(ram_command->caller));
    Serial::text(" service=");
    Serial::number(ram_lifetime->generation);
    Serial::text(" root=");
    Serial::number(ram_lifetime->root);
    Serial::text("\r\n");
    ram_launch(0, 0, *caller_epoch);
    ram_exchange_commands();
    if (ram_state == RamState::poisoned) {
        const bool uncertain = ram_command->framing.commit_delivered() &&
                               ram_command->framing.outcome() != RamFileFraming::Outcome::committed &&
                               ram_command->framing.outcome() != RamFileFraming::Outcome::rejected;
        ram_reset(); // Invalidates every candidate before resetting the service.
        const bool restarted = scratchpad_restart();
        response =
            ScratchpadResponse{restarted ? (uncertain ? ScratchpadKind::indeterminate_reset : ScratchpadKind::reset)
                                         : ScratchpadKind::unavailable};
        return restarted;
    }
    scratchpad_capture_result();
#ifdef AURORA_SCRATCHPAD_FIXTURE
    if (scratchpad_probe == '6' && ram_commands == 2) {
        require(scratchpad_transfer->captured, "scratchpad captured reset probe");
        ram_state = RamState::poisoned;
        ram_reset(); // The real reset invalidates captured eligibility before reclaiming anything.
        const bool restarted = scratchpad_restart();
        response = ScratchpadResponse{restarted ? ScratchpadKind::reset : ScratchpadKind::unavailable};
        return restarted;
    }
#endif
    const auto outcome = ram_command->framing.outcome();
    const bool terminal = ram_command->framing.state() == RamFileFraming::State::terminal;
    // An unresolved delivered COMMIT is never translated into an abort. Reset
    // and do not replay the operation, even when all caller bytes looked valid.
    if (!terminal && ram_command->framing.commit_delivered()) {
        ram_state = RamState::poisoned;
        ram_reset();
        const bool restarted = scratchpad_restart();
        response = ScratchpadResponse{restarted ? ScratchpadKind::indeterminate_reset : ScratchpadKind::unavailable};
        return restarted;
    }
    ScratchpadKind fallback = outcome == RamFileFraming::Outcome::committed  ? ScratchpadKind::committed_caller_failed
                              : outcome == RamFileFraming::Outcome::rejected ? ScratchpadKind::rejected
                              : terminal                                     ? ScratchpadKind::read_failed
                                                                             : ScratchpadKind::aborted;
    ram_settle_caller();
#ifdef AURORA_SCRATCHPAD_FIXTURE
    if (scratchpad_probe == '7' && ram_commands == 2)
        ram_lifetime->backing[0] ^= L::page_size; // Must fail before candidate promotion or Console.
#endif
    if (!terminal) {
        require(ram_command->framing.begin_abort(), "scratchpad exclusive precommit abort");
        ram_state = RamState::aborting;
        ram_resume_service(1, 0, ram_command->cleanup_epoch);
        if (ram_state == RamState::poisoned) {
            ram_reset();
            const bool restarted = scratchpad_restart();
            response = ScratchpadResponse{restarted ? ScratchpadKind::reset : ScratchpadKind::unavailable};
            return restarted;
        }
        require(ram_service_wait.context && ram_command->framing.state() == RamFileFraming::State::aborted,
                "scratchpad source acknowledged cleanup");
    }
    scratchpad_settle_response(response, fallback);
    Serial::text("AURORA_SCRATCHPAD_SETTLED: command=");
    Serial::number(ram_commands);
    Serial::text(" used=4 service=");
    Serial::number(ram_lifetime->generation);
    Serial::text("\r\n");
    return true;
}
auto scratchpad_shutdown() -> void {
    require(!scratchpad_console_owned && (scratchpad_idle() || scratchpad_retired()), "scratchpad shutdown boundary");
    if (ram_state == RamState::idle) {
        ram_service_wait.clear();
        ram_clear(ram_lifetime);
        require(retire(1), "scratchpad full service retirement");
        ram_state = RamState::absent;
    }
    require(scratchpad_retired(), "scratchpad session complete lease scrub");
    mailbox.reset();
    require(scratchpad_retired(), "scratchpad session transport released");
}
[[gnu::noinline]] auto run_ram_scratchpad_console() -> void {
    Serial::initialize_input();
#ifdef AURORA_SCRATCHPAD_FIXTURE
    Serial::text("AURORA_SCRATCHPAD_FIXTURE_READY\r\n");
    while (!scratchpad_probe) {
        const auto sample = Serial::next();
        require(!sample.damaged, "scratchpad fixture selector damage");
        if (sample.present)
            scratchpad_probe = sample.byte;
    }
    require(scratchpad_probe >= '1' && scratchpad_probe <= '8', "scratchpad fixture selector range");
#endif
    mailbox.emplace(registry);
    ScratchpadResponse response{ScratchpadKind::ready};
    if (!scratchpad_restart())
        response = ScratchpadResponse{ScratchpadKind::unavailable};
    bool available = ram_state == RamState::idle;
    bool output = scratchpad_write_response(response);
    U64 after_cr = 0;
    while (available && output) {
        scratchpad::Submission input;
        scratchpad_read_input(input, after_cr);
        after_cr = input.after_cr;
        if (input.action != 0) {
            output = input.action != static_cast<U64>(scratchpad::Submission::Action::output_failure);
            scratchpad::scrub(input);
            break;
        }
        available = scratchpad_command_run(input, response);
        output = scratchpad_write_response(response);
    }
    scratchpad::scrub(response);
    after_cr = 0;
    scratchpad_shutdown();
    // Output failure never retries user-facing bytes, diagnostics or operations.
    if (output)
        Serial::text("AURORA_RAM_SCRATCHPAD_EXIT: used=0 volatile=1\r\n");
    else {
        hardware::Io::write(0xf4, 0x10);
        for (;;)
            asm volatile("cli; hlt");
    }
}
