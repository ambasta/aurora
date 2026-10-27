// Opt-in named consumer: only the retained Serve owner holds the namespace.
// This record is one transient input/result receipt, destroyed before next input.
extern "C" void __au_runtime_namespace_input(const void *, void *);
extern "C" auto __au_runtime_namespace_response(const void *) -> U64;
using NamespaceResponse = named::Response;
using NamespaceKind = NamespaceResponse::Kind;
struct NamespaceTransfer final {
    const user::DomainHandle caller, service;
    const user::ProgramContract contract;
    const U64 caller_root, service_root, service_generation, cleanup;
    const ipc::Endpoint endpoint;
    const std::array<U64, 4> backing;
    const named::Command command;
    const U64 probe;
    named::Result result{};
    bool captured{};
};
std::optional<NamespaceTransfer> namespace_transfer;
auto namespace_discard() -> void { ram_clear(namespace_transfer); }
[[nodiscard]] auto namespace_transfer_empty() -> bool { return !namespace_transfer; }
[[gnu::noinline]] auto namespace_read_input(named::Submission &input, U64 after_cr) -> void {
    require(!scratchpad_console_owned && scratchpad_idle() && after_cr <= 1, "namespace input boundary");
    named::scrub(input);
    named::InputArgument argument{ProgramInputSession::open(), after_cr};
    scratchpad_console_owned = true;
    __au_runtime_namespace_input(&argument, &input);
    require(input.valid(), "namespace canonical submission");
    ProgramInputSession::release(argument.console);
    scratchpad_console_owned = false;
    named::scrub(argument);
    require(scratchpad_idle(), "namespace released input boundary");
}
[[nodiscard, gnu::noinline]] auto namespace_write_response(NamespaceResponse &response) -> bool {
    const bool retired = scratchpad_retired();
    require(!scratchpad_console_owned && response.valid() &&
                (scratchpad_idle() || (retired && response.kind == static_cast<U64>(NamespaceKind::unavailable))),
            "namespace settled output boundary");
    named::ResponseArgument argument{ProgramInputSession::open(), response};
    scratchpad_console_owned = true;
    named::scrub(response);
    if (namespace_probe == '7' && ram_commands == 2 && argument.response.result.event == 1)
        scratchpad_output_left = 5;
    const auto result = __au_runtime_namespace_response(&argument);
    ProgramInputSession::release(argument.console);
    scratchpad_console_owned = false;
    named::scrub(argument);
    require(result <= 1 && (retired ? scratchpad_retired() : scratchpad_idle()), "namespace released output boundary");
    return result == 1;
}
[[nodiscard]] auto namespace_caller_window() -> named::CopiedStack::Window {
    require(namespace_transfer.has_value(), "namespace transfer exists");
    return retained_caller_window<named::CopiedStack>(*namespace_transfer);
}
[[nodiscard]] auto namespace_caller_probe() -> U64 {
    if (ram_commands != 2) return 0;
    return namespace_probe == '1' ? 1 : namespace_probe == '2' ? 2 : namespace_probe == '9' ? 3 :
           namespace_probe == 'a' ? 4 : 0;
}
[[gnu::noinline]] auto namespace_stage(named::Submission &input) -> void {
    require(input.valid() && input.action == 0 && !namespace_transfer && ram_command_valid(),
            "namespace single stage admission");
    std::array<U64, 4> backing{};
    for (unsigned index = 0; index < 4; ++index) {
        require(domains[0].stacks[index].has_value(), "namespace fresh caller lease");
        const auto physical = frames.address(*domains[0].stacks[index]);
        require(physical.has_value(), "namespace fresh caller owner");
        backing[index] = *physical;
    }
    namespace_transfer.emplace(NamespaceTransfer{ram_command->caller, ram_command->service,
        *domains[0].contract, domains[0].tables->root(), ram_lifetime->root, ram_lifetime->generation,
        ram_command->cleanup_epoch, ram_command->caller_endpoint, backing, input.command,
        namespace_caller_probe(), {}, false});
    require(named::CopiedStack::stage(namespace_caller_window(), input.command), "namespace pristine command copy");
    named::scrub(input);
}
[[gnu::noinline]] auto namespace_capture_result() -> void {
    require(namespace_transfer && !namespace_transfer->captured, "namespace one candidate capture");
    if (ram_state != RamState::command || program.event() != ProgramEvent::returned || program.value() != 1 ||
        timer_exhausted || ram_command->framing.state() != RamFileFraming::State::terminal) return;
    auto &copy = *namespace_transfer;
    if (namespace_probe == '5' && ram_commands == 2)
        namespace_caller_window()[named::CopiedStack::result + offsetof(named::Result, event)] = std::byte{255};
    if (named::CopiedStack::capture(namespace_caller_window(), copy.endpoint.slot(), copy.endpoint.generation(),
                                   copy.command, copy.probe, copy.result) &&
        copy.result.terminal_for(copy.command.operation, ram_command->framing.terminal_reply(),
                                 ram_command->framing.data_count(), ram_command->framing.revision()))
        copy.captured = true;
    else named::scrub(copy.result);
}
[[gnu::noinline]] auto namespace_settle_response(NamespaceResponse &response, NamespaceKind fallback) -> void {
    require(!scratchpad_console_owned && namespace_transfer && ram_command && ram_lifetime_valid() &&
                !registry.index(namespace_transfer->caller) && !domains[0].handle && scratchpad_empty_caller() &&
                mailbox->revoked() && frames.used() == 4 && registry.index(namespace_transfer->service) == 1 &&
                namespace_transfer->service_root == ram_lifetime->root &&
                namespace_transfer->service_generation == ram_lifetime->generation &&
                namespace_transfer->cleanup == ram_command->cleanup_epoch,
            "namespace original command physically retired");
    response = NamespaceResponse{fallback};
    if (namespace_transfer->captured) {
        const auto &result = namespace_transfer->result;
        require(result.terminal_for(namespace_transfer->command.operation, ram_command->framing.terminal_reply(),
                                     ram_command->framing.data_count(), ram_command->framing.revision()),
                "namespace settled terminal relation");
        response.kind = static_cast<U64>(NamespaceKind::completed);
        response.name = namespace_transfer->command.name;
        response.submitted_size = namespace_transfer->command.value.count;
        response.result = result;
    } else if (ram_command->framing.outcome() == RamFileFraming::Outcome::rejected) {
        response.kind = static_cast<U64>(NamespaceKind::completed);
        response.name = namespace_transfer->command.name;
        response.submitted_size = namespace_transfer->command.value.count;
        response.result.event = ram_command->framing.terminal_reply() >> 8;
    }
    namespace_discard();
    ram_clear(ram_command);
    ram_state = RamState::idle;
    scratchpad_clear_inactive_accounting();
    require(response.valid() && scratchpad_idle(), "namespace one-way settled response idle");
}
[[nodiscard, gnu::noinline]] auto namespace_command_run(named::Submission &input, NamespaceResponse &response) -> bool {
    require(!scratchpad_console_owned && scratchpad_idle() && input.valid() && input.action == 0,
            "namespace protected admission boundary");
    if (ram_commands >= 64) {
        named::scrub(input);
        response = NamespaceResponse{NamespaceKind::limit};
        return false;
    }
    const auto cleanup = ram_mint_epoch(), caller_epoch = ram_mint_epoch();
    if (!cleanup || !caller_epoch || create(0) != 0) {
        named::scrub(input);
        response = NamespaceResponse{NamespaceKind::unavailable};
        return false;
    }
    if (!mailbox->bind(*domains[0].handle, *domains[1].handle)) {
        require(retire(0), "namespace refused caller reclaimed");
        named::scrub(input);
        response = NamespaceResponse{NamespaceKind::unavailable};
        return false;
    }
    ram_command.emplace(*domains[0].handle, *domains[1].handle,
        *mailbox->endpoint(*domains[0].handle), *mailbox->endpoint(*domains[1].handle), *cleanup,
        input.command.operation == 0 ? NamespaceFraming::Right::read : NamespaceFraming::Right::write,
        static_cast<unsigned>(input.command.name.count), static_cast<unsigned>(input.command.value.count));
    ++ram_commands;
    ram_state = RamState::command;
    namespace_stage(input);
    Serial::text("AURORA_NAMESPACE_BEGIN: command="); Serial::number(ram_commands);
    Serial::text(" caller="); Serial::number(*registry.incarnation(ram_command->caller));
    Serial::text(" service="); Serial::number(ram_lifetime->generation);
    Serial::text(" root="); Serial::number(ram_lifetime->root); Serial::text("\r\n");
    ram_launch(0, 0, *caller_epoch);
    ram_exchange_commands();
    if (ram_state == RamState::poisoned) {
        const bool uncertain = ram_command->framing.commit_delivered() &&
            ram_command->framing.outcome() != RamFileFraming::Outcome::committed &&
            ram_command->framing.outcome() != RamFileFraming::Outcome::rejected;
        ram_reset();
        const bool restarted = scratchpad_restart();
        response = NamespaceResponse{restarted ? (uncertain ? NamespaceKind::indeterminate_reset : NamespaceKind::reset)
                                               : NamespaceKind::unavailable};
        return restarted;
    }
    namespace_capture_result();
    const auto outcome = ram_command->framing.outcome();
    const bool terminal = ram_command->framing.state() == RamFileFraming::State::terminal;
    if (!terminal && ram_command->framing.commit_delivered()) {
        ram_state = RamState::poisoned;
        ram_reset();
        const bool restarted = scratchpad_restart();
        response = NamespaceResponse{restarted ? NamespaceKind::indeterminate_reset : NamespaceKind::unavailable};
        return restarted;
    }
    const NamespaceKind fallback = outcome == RamFileFraming::Outcome::committed ? NamespaceKind::committed_caller_failed
                                 : terminal ? NamespaceKind::read_failed : NamespaceKind::aborted;
    ram_settle_caller();
    if (namespace_probe == '6' && ram_commands == 2) ram_lifetime->backing[0] ^= L::page_size;
    if (!terminal) {
        require(ram_command->framing.begin_abort(), "namespace exclusive precommit abort");
        ram_state = RamState::aborting;
        ram_resume_service(1, 0, ram_command->cleanup_epoch);
        if (ram_state == RamState::poisoned) {
            ram_reset();
            const bool restarted = scratchpad_restart();
            response = NamespaceResponse{restarted ? NamespaceKind::reset : NamespaceKind::unavailable};
            return restarted;
        }
        require(ram_service_wait.context && ram_command->framing.state() == RamFileFraming::State::aborted,
                "namespace source acknowledged cleanup");
    }
    namespace_settle_response(response, fallback);
    Serial::text("AURORA_NAMESPACE_SETTLED: command="); Serial::number(ram_commands);
    Serial::text(" used=4 service="); Serial::number(ram_lifetime->generation); Serial::text("\r\n");
    return true;
}
[[gnu::noinline]] auto run_namespace_console() -> void {
    Serial::initialize_input();
    if (fixture == Fixture::namespace_fixture) {
        Serial::text("AURORA_NAMESPACE_FIXTURE_READY\r\n");
        while (!namespace_probe) {
            const auto sample = Serial::next();
            require(!sample.damaged, "namespace fixture selector damage");
            if (sample.present) namespace_probe = sample.byte;
        }
        require((namespace_probe >= '1' && namespace_probe <= '9') ||
                (namespace_probe >= 'a' && namespace_probe <= 'z'), "namespace fixture selector range");
    }
    mailbox.emplace(registry);
    NamespaceResponse response{NamespaceKind::ready};
    if (!scratchpad_restart()) response = NamespaceResponse{NamespaceKind::unavailable};
    bool available = ram_state == RamState::idle;
    bool output = namespace_write_response(response);
    U64 after_cr = 0;
    while (available && output) {
        named::Submission input;
        namespace_read_input(input, after_cr);
        after_cr = input.after_cr;
        if (input.action != 0) {
            output = input.action != static_cast<U64>(named::Submission::Action::output_failure);
            named::scrub(input);
            break;
        }
        available = namespace_command_run(input, response);
        output = namespace_write_response(response);
    }
    named::scrub(response);
    after_cr = 0;
    scratchpad_shutdown();
    if (output) Serial::text("AURORA_NAMESPACE_EXIT: used=0 volatile=1\r\n");
    else {
        hardware::Io::write(0xf4, 0x10);
        for (;;) asm volatile("cli; hlt");
    }
}
