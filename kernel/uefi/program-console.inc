// Included only by the opt-in two-domain program-console adapter.
// One shared timer mapping and one IDT gate; ownership is selected only at a
// fully quiescent private-kernel boundary. No source-language pointer ABI.
using ProgramSerial = Serial; // One shared sticky receive-error latch, including runtime traces.
#ifndef AURORA_FILE_CALL
program::Stream command_stream;
#endif
#ifdef AURORA_PRODUCTION
using ConsoleNote = program::ExternalNote;
using ConsoleFiles = program::ExternalFiles;
U64 console_selection_generation{}, console_note_revision{}, console_last_generation{};
#else
using ConsoleNote = program::Note;
using ConsoleFiles = program::Files;
#endif
ConsoleNote command_note;
ConsoleFiles command_files;
#ifdef AURORA_PROGRAM_APPEND_CALL
program::AppendCall command_append;
// Captured once at the original caller's first suspension, before a service
// activation. Later exchanges cannot replace its identity or backing receipt.
std::optional<ProgramRunAuthority> append_origin;
std::array<U64, 8> append_backing{};
U64 append_operation{};
#endif
#ifdef AURORA_PROGRAM_FIXTURE
// Retained test-image evidence, never an additional production store or stack copy.
ConsoleFiles::Value program_append_checkpoint{};
U64 program_append_operation{}, program_append_revision{};
#endif
#ifndef AURORA_FILE_CALL
bool command_file{}, command_transform{};
bool command_reading{};
#endif
extern "C" void __au_runtime_program_input(const void *, void *);
extern "C" auto __au_runtime_program_response(const void *) -> U64;
extern "C" void __au_runtime_note_update(const void *, void *);
extern "C" void __au_runtime_note_project(const void *, void *);
extern "C" void __au_runtime_files_update(const void *, void *);
extern "C" void __au_runtime_files_replace(const void *, void *);

bool command_owned{};
#ifndef AURORA_FILE_CALL
bool console_probe_used{};
#endif
#ifdef AURORA_TEXT_FIXTURE
// The console-region rows' poll wait (console-region.inc) shares the one
// wake mechanism; owned-text rows never wait. The file-call rows keep their own.
[[nodiscard]] auto program_poll_policy() -> bool {
    if (owned_rows())
        return console_rows() && console_poll_policy();
    return !command_owned && !run_authority;
}
[[nodiscard]] auto program_boundary() -> bool {
    if (owned_rows())
        return console_rows() && console_boundary();
    const auto current_stack = stack();
#else
#include "console-wait.inc"
[[nodiscard]] auto program_poll_policy() -> bool {
    return !command_owned && !run_authority;
}
[[nodiscard]] auto program_boundary() -> bool {
    const auto current_stack = stack();
#endif
    return current_stack % 8 == 0 &&
           current_stack >=
               arena + Handoff::stack_bottom + ConsoleWakeContext::handler_reserve + ConsoleWakeContext::byte_count &&
           current_stack <= arena + Handoff::stack_top && root() == kernel_root && irq_off() &&
           active == L::domain_count && saved_rsp == 0 && !program.running() && !timer_armed && !timer_draining &&
           !timer_owner && !run_authority && selected_phase == ipc::Phase::inactive && !console_waiting &&
           console_wait_stack == 0 && timer_stop() && timer_quiet(0x100, false) && timer_quiet(0x200, false);
}
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
#include "graphical-terminal.inc"
#endif
#ifdef AURORA_FILE_CALL
// Opaque copied state belongs to the Aurora lifecycle; only native code owns
// the domains, verified address spaces, leases and authenticated read grants.
U64 file_lifecycle{};
[[nodiscard]] auto file_service_transition(U64 event) -> U64 {
    const auto decision = program::FileServiceTransition::decode(
        program::language_file_service_transition(file_lifecycle, event), file_lifecycle, event);
    require(decision.has_value(), "file service lifecycle proposal");
    file_lifecycle = decision->next();
    return decision->effect();
}
auto file_service_poison() -> void {
    require(file_service_transition(2) == 5, "file service poisoned lifecycle");
}
[[nodiscard]] auto file_service_quiet() -> bool {
    if (!caller_continuation.ordinary_empty())
        return false;
    const auto &caller = domains[0];
    if (caller.handle || caller.contract || caller.tables || caller.call_count || caller.call_limit != 1 ||
        caller.call_service_used || caller.call_closed)
        return false;
    for (const auto &lease : caller.stacks)
        if (lease)
            return false;
    const auto &service = domains[1];
    if (!service.handle) {
        if (file_lifecycle != 0 || service.contract || service.tables || service.call_count ||
            service.call_limit != 1 || service.call_service_used || service.call_closed || frames.used() != 0)
            return false;
        for (const auto &lease : service.stacks)
            if (lease)
                return false;
        return true;
    }
    if (file_lifecycle != 1 || !registry.ready(*service.handle) || registry.index(*service.handle) != 1 ||
        service.image != 1 || !service.contract || !service.tables || service.call_count || service.call_limit != 1 ||
        service.call_service_used || service.call_closed || frames.used() != service.stacks.size() || !verify(service))
        return false;
    for (const auto &lease : service.stacks) {
        if (!lease)
            return false;
        const auto physical = frames.address(*lease);
        if (!physical || !zero(*physical))
            return false;
    }
    return true;
}
auto file_service_scrub() -> void {
    auto &service = domains[1];
    require(program_boundary() && service.handle && registry.ready(*service.handle) && verify(service),
            "file service scrub authority");
    for (const auto &lease : service.stacks) {
        require(lease.has_value(), "file service retained lease");
        const auto physical = frames.address(*lease);
        require(physical.has_value(), "file service retained address");
        fill(*physical, 0);
        require(zero(*physical), "file service complete stack scrub");
    }
}
#endif
class ProgramInputPlatform final {
public:
    [[nodiscard]] static auto quiet() -> bool {
        return !command_owned && !mailbox &&
#ifdef AURORA_FILE_CALL
               file_service_quiet() &&
#else
               frames.used() == 0 &&
#ifdef AURORA_PROGRAM_APPEND_CALL
               caller_continuation.ordinary_empty() && !append_origin && !append_operation &&
               !append_service_wait.context && !append_service_wait.authority && !append_service_wait.ticket &&
               !command_appending &&
#endif
#endif
               !command_note.bound() && program_boundary();
    }
    static auto wait() -> void {
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
        // Render pending Console output before idling; no input is consumed
        // here. A byte that arrived meanwhile is sampled without idling.
        if (terminal_present())
            return;
#endif
        program_wait_sample();
    }
    [[noreturn]] static auto fail() -> void {
        stop("program console input authority");
    }
};
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
// The one COM1 transport. Bytes the Console session actually delivered are also
// copied into the terminal grid; diagnostics written by native code are not.
class ProgramConsoleTransport final {
public:
    static auto next() -> console::Sample {
        return ProgramSerial::next();
    }
    static auto try_put(std::uint8_t byte) -> console::PutResult {
        const auto result = ProgramSerial::try_put(byte);
        if (result == console::PutResult::success)
            terminal_grid.apply(byte);
        return result;
    }
};
using ProgramInputSession = console::Session<ProgramConsoleTransport, ProgramInputPlatform>;
#else
using ProgramInputSession = console::Session<ProgramSerial, ProgramInputPlatform>;
#endif
// The only native submission storage is the caller's result. Revoke the grant
// before returning it to any command mutation or protected execution path.
__attribute__((noinline)) auto program_read_input(program::Submission &input, U64 after_cr) -> void {
    require(ProgramInputPlatform::quiet() && after_cr <= 1, "program input entry boundary");
    input.scrub();
    const program::SubmissionArgument argument{ProgramInputSession::open(), after_cr};
    __au_runtime_program_input(&argument, input.data());
    require(input.valid(), "program closed input submission");
    ProgramInputSession::release(argument.console);
    require(ProgramInputPlatform::quiet(), "program released input boundary");
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
    // A closing session reads no more input: render its final frame completely.
    static_cast<void>(terminal_present(input.action() != program::Submission::Action::command &&
                                       input.action() != program::Submission::Action::upper_payload));
#endif
}
// One complete response, including the next prompt, uses the existing Console
// operations only after native mutation or protected retirement is complete.
// No submission, stream receipt or publication authority crosses this boundary.
[[nodiscard]] __attribute__((noinline)) auto program_write_response(program::Response &response) -> bool {
    require(ProgramInputPlatform::quiet() && response.canonical_kind(), "program response entry boundary");
    program::ResponseArgument argument{ProgramInputSession::open(), response};
    response.scrub();
    const auto result = __au_runtime_program_response(&argument);
    const bool canonical = result <= 1;
    ProgramInputSession::release(argument.console);
    argument.scrub();
    require(canonical && ProgramInputPlatform::quiet(), "program released response boundary");
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
    static_cast<void>(terminal_present());
#endif
    return result == 1;
}
template <class T> auto program_scrub_copy(T &value) -> void {
    auto *bytes = reinterpret_cast<volatile std::byte *>(&value);
    for (std::size_t index = 0; index < sizeof(value); ++index)
        bytes[index] = std::byte{0};
}
#ifndef AURORA_FILE_CALL
[[nodiscard]] auto recoverable_program_event() -> bool {
    const auto event = program.event();
    return (event == ProgramEvent::rejected && timer_exhausted) || event == ProgramEvent::bounds ||
           event == ProgramEvent::overflow || event == ProgramEvent::division_zero ||
           event == ProgramEvent::shift_count;
}
auto program_console_envelope(const Bytes &captured, U64 result) -> void {
    require(command_owned && active < 2 && run_authority, "program envelope owner");
    if (program.event() != ProgramEvent::returned) {
        require(recoverable_program_event(), "program recoverable emitted event");
        return;
    }
    require(captured.get(64) == launch[0] && captured.get(72) == 1 && captured.get(48) == launch[5],
            "program phase/version/ordinal");
    const ipc::Endpoint endpoint{captured.get(88), captured.get(96)};
    const auto actor = *domains[active].handle;
    if (selected_phase == ipc::Phase::request) {
        require(active == 0 && captured.get(56) == 0 && command_stream.accept_request(result, launch[5]),
                "program request byte/ordinal");
        const auto ticket = mailbox->submit(actor, selected_phase, endpoint, ipc::Request{result, launch[5]});
        require(ticket.has_value(), "program request capability/state");
        transaction = *ticket;
    } else if (selected_phase == ipc::Phase::service) {
        require(active == 1 && command_stream.accept_reply(result, launch[5]) &&
                    mailbox->reply(actor, selected_phase, endpoint, captured.get(56), result),
                "program service capability/byte");
    } else {
        const auto expected_endpoint = mailbox->endpoint(actor);
        require(active == 0 && selected_phase == ipc::Phase::completion && expected_endpoint &&
                    expected_endpoint->slot() == endpoint.slot() &&
                    expected_endpoint->generation() == endpoint.generation() && captured.get(56) == transaction &&
                    mailbox->state() == ipc::State::consumed && command_stream.acknowledge(result, launch[5]),
                "program completion authority/ack");
    }
}
#ifdef AURORA_PROGRAM_APPEND_CALL
[[nodiscard]] auto append_call_authority() -> bool {
    if (!command_appending || !command_owned || !domains[0].handle || !mailbox)
        return false;
    const auto endpoint = mailbox->endpoint(*domains[0].handle);
    return endpoint && command_files.matches_append(registry, *mailbox, *domains[0].handle, *endpoint, command_append);
}
[[nodiscard]] auto append_call_reply(U64 result) -> bool {
    if (!append_call_authority() || !command_append.reply(result))
        return false;
    domains[0].call_closed = command_append.terminal();
    return true;
}
#endif
// One exact final-page lease check shared by copied service input and caller
// output. A physical address alone is never permission to read the kernel alias.
[[nodiscard]] [[gnu::noinline]] auto program_stack_tail(unsigned index) -> U64 {
    const auto &domain = domains[index];
    const auto physical = frames.address(*domain.stacks.back());
    const auto virtual_page = domain.contract->layout().user_stack_top() - L::page_size;
    require(physical && (domain.tables->entry(virtual_page) & ~0x60ULL) == (*physical | 7 | RuntimeTables::nx) &&
                (PageTables{kernel_root, static_cast<std::size_t>(handoff->get(96))}.entry(*physical) & ~0x60ULL) ==
                    (*physical | 3 | RuntimeTables::nx),
            "program copied stack");
    return *physical + L::page_size;
}
[[gnu::noinline]] auto program_stage_note(U64 source, U64 byte, U64 ordinal) -> void {
    const auto endpoint = mailbox->endpoint(*domains[1].handle);
    require(endpoint && mailbox->state() == ipc::State::delivered && command_note.matches(*endpoint),
            "note authenticated publication");
    auto *record = reinterpret_cast<std::byte *>(program_stack_tail(1) - ConsoleNote::stream_stack_reservation);
    require(command_note.stage_stream(
                std::span<std::byte, ConsoleNote::stream_record_bytes>{record, ConsoleNote::stream_record_bytes},
                *endpoint,
                source,
                ipc::Request{byte, ordinal}),
            "note fixed copied record");
}
#ifdef AURORA_PROGRAM_APPEND_CALL
#include "blocking-call.inc"
#include "append-service.inc"
#endif
[[nodiscard]] auto program_execute(unsigned index, ipc::Phase phase, U64 source, U64 byte, U64 ordinal) -> bool {
    if (!caller_continuation.ordinary())
        return false;
    require(command_owned && program_boundary() && index < 2 && selected_client == 0, "program launch boundary");
    auto &domain = domains[index];
    require(domain.handle && domain.contract && verify(domain), "program launch domain");
    const auto endpoint = mailbox->endpoint(*domain.handle);
    require(endpoint.has_value(), "program launch grant");
    if (command_appending)
        transaction = index == 1 ? caller_continuation.ordinary()->ticket : 0;
    launch = {source,
              byte,
              endpoint->slot(),
              endpoint->generation(),
              phase == ipc::Phase::request ? 0 : transaction,
              ordinal,
              0x202};
    selected_phase = phase;
    selected_role = index == 0 ? SelectedRunAuthority::Role::client : SelectedRunAuthority::Role::service;
    for (const auto &lease : domain.stacks) {
        const auto address = frames.address(*lease);
        require(address.has_value(), "program stack lease");
        fill(*address, 0);
    }
    if (phase == ipc::Phase::service) {
        require(index == 1, "note service role");
        program_stage_note(source, byte, ordinal);
    }
    require(launch_domain(index, *domain.handle), "program continuation");
    timer_finish();
    require(root() == kernel_root && saved_rsp == 0 && active == L::domain_count && !program.running(),
            "program restored authority");
    const auto okay = program.event() == ProgramEvent::returned;
    require(okay || recoverable_program_event() ||
                (command_appending && (index == 0 ? caller_continuation.ordinary()->context.has_value()
                                                  : append_service_wait.context.has_value())),
            "program terminal outcome");
    if (command_appending) {
        if (index == 1) {
            domains[0].call_service_used = timer_ticks;
        }
        transaction = 0;
    }
    launch = {};
    selected_phase = ipc::Phase::inactive;
    require(program_boundary(), "program post-run quiescence");
    return okay;
}
// Inject only after one byte was fully acknowledged. A note read includes its
// final EOF round; only an actual injection makes later commands healthy.
[[nodiscard]] auto program_source(ipc::Phase phase, U64 ordinal) -> U64 {
    const U64 normal = command_reading
                           ? (phase == ipc::Phase::request   ? 12
                              : phase == ipc::Phase::service ? (command_file && command_files.appending() ? 15 : 11)
                              : command_transform && !command_files.appending() ? 14
                                                                                : 13)
                           : (phase == ipc::Phase::request   ? 0
                              : phase == ipc::Phase::service ? 1
                                                             : 2);
    if (console_probe_used || ordinal != 1)
        return normal;
#ifdef AURORA_PROGRAM_FIXTURE
    if (fixture == Fixture::program_request_fault && phase == ipc::Phase::request) {
        console_probe_used = true;
        return 8;
    }
    if (fixture == Fixture::program_service_fault && phase == ipc::Phase::service) {
        console_probe_used = true;
        return 4;
    }
    if (fixture == Fixture::program_completion_fault && phase == ipc::Phase::completion) {
        console_probe_used = true;
        return 10;
    }
    if (fixture == Fixture::program_request_budget && phase == ipc::Phase::request) {
        console_probe_used = true;
        return 6;
    }
    if (fixture == Fixture::program_service_budget && phase == ipc::Phase::service) {
        console_probe_used = true;
        return 5;
    }
    if (fixture == Fixture::program_completion_budget && phase == ipc::Phase::completion) {
        console_probe_used = true;
        return 7;
    }
#endif
    return normal;
}
// A fixed two-role scheduler only. Aurora owns traversal and accumulation;
// the supervisor authenticates each copied exchange and the final return.
[[nodiscard]] [[gnu::noinline]] auto program_append_call() -> bool {
    if (!caller_continuation.ordinary_empty())
        return false;
    require(append_call_authority() && program_boundary(), "append authority");
    auto &caller = domains[0];
    caller.call_limit = 50;
    U64 probe = 0;
#ifdef AURORA_PROGRAM_FIXTURE
    if (!console_probe_used) {
        if (fixture == Fixture::program_request_fault)
            probe = 8;
        if (fixture == Fixture::program_completion_fault)
            probe = 10;
        if (fixture == Fixture::program_request_budget)
            probe = 6;
        if (fixture == Fixture::program_completion_budget)
            probe = 7;
        if (fixture == Fixture::program_append_before_fault)
            probe = 20;
        if (fixture == Fixture::program_append_before_budget)
            probe = 21;
        if (fixture == Fixture::program_append_eof_fault)
            probe = 18;
        if (fixture == Fixture::program_append_eof_budget)
            probe = 19;
    }
#endif
    require(!append_origin && !append_operation, "call owner");
    append_operation = command_append.run();
    for (unsigned role = 0; role < 2; ++role)
        for (unsigned page = 0; page < 4; ++page) {
            const auto physical = frames.address(*domains[role].stacks[page]);
            require(physical.has_value(), "append backing");
            append_backing[role * 4 + page] = *physical;
        }
    bool success = true;
    // The only caller entry: later work resumes its live source locals.
    static_cast<void>(program_execute(0, ipc::Phase::request, 16, probe, 0));
    if (caller_continuation.ordinary()->context) {
        require(caller_continuation.ordinary()->authority && !append_origin, "call owner");
        append_origin.emplace(*caller_continuation.ordinary()->authority);
    }
#ifdef AURORA_PROGRAM_FIXTURE
    U64 previous = 0;
#endif
    while (caller_continuation.ordinary()->context) {
        U64 ticket, epoch;
        unsigned ticks, remaining;
        {
            const auto &saved = caller_continuation.ordinary_checked();
            require(append_call_authority() && saved.authority && saved.ticket && caller.call_count &&
                        caller.call_count <= 50,
                    "append authority");
            ticket = saved.ticket;
            epoch = saved.authority->epoch();
            ticks = saved.ticks;
            remaining = saved.remaining;
        }
#ifdef AURORA_PROGRAM_FIXTURE
        require(!call_resume(previous) && !call_resume(ticket) && !append_service_resume(ticket, caller.call_count - 1),
                "append stale/unready wake");
        if (!console_probe_used && fixture == Fixture::program_append_cancel_pending && caller.call_count == 2) {
            console_probe_used = true;
            success = false;
            break;
        }
#endif
        const auto endpoint = mailbox->endpoint(*domains[1].handle);
        require(endpoint.has_value(), "append authority");
        const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *endpoint, ticket);
        require(request && request->first() == caller.call_count - 1 && request->second() == 0, "append request");
#ifdef AURORA_PROGRAM_FIXTURE
        if (!console_probe_used && fixture == Fixture::program_append_cancel_delivered && caller.call_count == 2) {
            console_probe_used = true;
            success = false;
            break;
        }
        if (request->first() != 0)
            append_service_wake_controls(ticket, request->first());
#endif
        if (request->first() == 0) {
            require(!append_service_wait.context, "append one producer");
            U64 service_probe = 0;
#ifdef AURORA_PROGRAM_FIXTURE
            if (!console_probe_used) {
                if (fixture == Fixture::program_service_fault)
                    service_probe = 4;
                if (fixture == Fixture::program_service_budget)
                    service_probe = 5;
                if (fixture == Fixture::program_append_construct_fault)
                    service_probe = 22;
                if (fixture == Fixture::program_append_construct_budget)
                    service_probe = 23;
                if (fixture == Fixture::program_append_producer_return)
                    service_probe = 24;
            }
#endif
            Serial::text("AURORA_APPEND_LAUNCH: operation=");
            Serial::number(append_operation);
            Serial::text("\r\n");
            static_cast<void>(program_execute(1, ipc::Phase::service, 17, service_probe, 0));
        } else
            require(append_service_resume(ticket, request->first()), "append service wake");
        {
            const auto &saved = caller_continuation.ordinary_checked();
            require(timer_epoch > epoch && saved.ticks == ticks && saved.remaining == remaining, "append allowance");
        }
        // Latch failure before a resume can restore the caller's timer state.
        if (timer_exhausted || !append_service_wait.context || program.event() == ProgramEvent::returned) {
            success = false;
            break;
        }
        require(mailbox->state() == ipc::State::replied, "append authority");
#ifdef AURORA_PROGRAM_FIXTURE
        require(!call_resume(previous) && !append_service_resume(ticket, request->first()) &&
                    (!command_append.terminal() || !append_service_resume(ticket + 1, request->first() + 1)),
                "append stale ready wake");
        if (!console_probe_used &&
            ((fixture == Fixture::program_append_cancel_replied && caller.call_count == 2) ||
             (fixture == Fixture::program_append_cancel_terminal && command_append.terminal()))) {
            console_probe_used = true;
            success = false;
            break;
        }
#endif
        require(call_resume(ticket), "append authority");
#ifdef AURORA_PROGRAM_FIXTURE
        require(!call_resume(ticket), "append duplicate wake");
#endif
        require(timer_epoch == epoch && timer_ticks >= ticks && timer_initial == timer_ticks + timer_remaining,
                "append allowance");
#ifdef AURORA_PROGRAM_FIXTURE
        previous = ticket;
#endif
    }
    success = success && !timer_exhausted && program.event() == ProgramEvent::returned && program.value() == 1 &&
              !caller_continuation.ordinary()->context && command_append.terminal() && append_service_wait.context;
#ifdef AURORA_PROGRAM_FIXTURE
    if (!success &&
        (probe || fixture == Fixture::program_service_fault || fixture == Fixture::program_service_budget ||
         fixture == Fixture::program_append_construct_fault || fixture == Fixture::program_append_construct_budget ||
         fixture == Fixture::program_append_producer_return))
        console_probe_used = true;
#endif
    require(program_boundary(), "append return");
    if (!success)
        return false;
    require(append_call_authority() && append_origin && append_operation == command_append.run() && caller.handle &&
                caller.contract && verify(caller) && verify(domains[1]) &&
                append_origin->ready_owner(registry, *caller.handle, timer_epoch) &&
                append_origin->root() == caller.tables->root() &&
                user::same_contract(append_origin->contract(), *caller.contract) && registry.ready(*domains[1].handle),
            "call owner");
#ifdef AURORA_PROGRAM_FIXTURE
    if (fixture == Fixture::program_append_backing)
        append_backing[0] += L::page_size;
#endif
    require(append_backings_valid(), "append backing");
    const Bytes result{
        view(program_stack_tail(0) - program::AppendCall::stack_reservation, program::AppendCall::stack_reservation)};
    if (result.get(72) != 0)
        return false;
    program::AppendCall::Value copied{};
    for (std::size_t index = 0; index < copied.size(); ++index)
        copied[index] = std::byte(result.get(index, 1));
#ifdef AURORA_PROGRAM_FIXTURE
    if (fixture == Fixture::program_append_copy && !console_probe_used) {
        copied[64] = std::byte{50};
        console_probe_used = true;
    }
#endif
    const bool captured = command_append.capture(copied);
    program_scrub_copy(copied);
    if (!captured)
        return false;
    const auto endpoint = mailbox->endpoint(*caller.handle);
    require(endpoint && mailbox->recycle(ipc::Phase::inactive) &&
                command_files.complete_append(registry, *mailbox, *caller.handle, *endpoint, command_append),
            "append return");
    Serial::text("AURORA_PROGRAM_APPEND_CALLER: operation=");
    Serial::number(command_append.run());
    Serial::text(" calls=");
    Serial::number(caller.call_count);
    Serial::text(" launches=1 producer_launches=1 terminal_park=1 eof=1 clean=1\r\n");
    return true;
}
auto program_cleanup(bool success) -> void {
    static_cast<void>(caller_continuation.ordinary_checked());
    require(command_owned && program_boundary() && mailbox, "program cleanup boundary");
    if (!success) {
        if (command_appending) {
            command_append.cancel();
            require(call_retire(0), "append cancellation");
        } else
            require(command_stream.cancel(), "program stream cancellation");
        if (mailbox->state() == ipc::State::pending || mailbox->state() == ipc::State::delivered) {
            require(mailbox->cancel(ipc::Phase::inactive), "program fault cancel");
            const auto endpoint = mailbox->endpoint(*domains[0].handle);
            require(endpoint.has_value(), "program cancelled grant");
            const auto cancelled = mailbox->consume(*domains[0].handle, ipc::Phase::completion, *endpoint, transaction);
            require(cancelled && cancelled->outcome() == ipc::Outcome::cancelled && cancelled->value() == 0,
                    "program cancellation consumption");
        }
    }
    // EOF is a terminal park, never a request for a cleanup continuation.
    // Both wait records are invalidated while the original domains still live.
#ifdef AURORA_PROGRAM_FIXTURE
    const auto retired_ticket = append_service_wait.ticket;
#endif
    append_service_wait.clear();
    command_note.release();
    if (!success && command_file && command_transform)
        command_files.abort();
    require(mailbox->scrubbed() && mailbox->revoke(ipc::Phase::inactive) && retire(0) && retire(1) &&
                frames.used() == 0,
            "program revoke/retire/scrub");
#ifdef AURORA_PROGRAM_FIXTURE
    if (command_appending)
        require(!append_service_resume(retired_ticket, 0) && !call_resume(retired_ticket) &&
                    !append_service_wait.context && !append_service_wait.authority && !append_service_wait.service &&
                    !append_service_wait.ticket && caller_continuation.ordinary_empty(),
                "append retired incarnations cannot wake");
#endif
    if (command_file) {
        if (command_transform) {
            if (success)
                require(command_files.retire(registry, *mailbox), "file authenticated retirement");
        } else
            require(command_files.release_read(registry, *mailbox), "file read authenticated retirement");
    }
    mailbox.reset();
    transaction = 0;
    launch = {};
    selected_client = 2;
    require(program_boundary(), "program retirement quiescence");
    command_owned = false;
    command_appending = false;
    append_origin.reset();
    program_scrub_copy(append_backing);
    append_operation = 0;
    ProgramSerial::text("AURORA_PROGRAM_COMMAND_END: success=");
    ProgramSerial::number(success ? 1 : 0);
    ProgramSerial::text(" used=0 epoch=");
    ProgramSerial::number(timer_epoch);
    ProgramSerial::text("\r\n");
}
#ifdef AURORA_PRODUCTION
// Both external-file commands and run transfer only from an exact quiescent
// console boundary. The process runtime returns with its retained owner parked
// and every extension/window mapping detached; the old architecture owns input
// and Display again only after these checks.
[[nodiscard]] auto production_process_enter() -> U64 {
    require(ProgramInputPlatform::quiet() && terminal_mapping() && !mailbox && frames.used() == 0,
            "production service entry ownership");
    U64 previous_cr2;
    asm volatile("mov %%cr2, %0" : "=r"(previous_cr2));
    command_owned = true;
    return previous_cr2;
}
auto production_process_leave(U64 previous_cr2) -> void {
    install_architecture();
    // Child fault handling is complete. Preserve the prior diagnostic context,
    // rather than clearing or concealing any live child's fault address.
    asm volatile("mov %0, %%cr2" : : "r"(previous_cr2) : "memory");
    command_owned = false;
    require(ProgramInputPlatform::quiet() && terminal_mapping(), "production service return ownership");
}
[[nodiscard]] auto production_console_request(ConsoleOperation operation,
                                              U64 generation,
                                              U64 revision,
                                              std::span<const std::byte> request,
                                              std::span<std::byte> response) -> ConsoleResult {
    const auto previous_cr2 = production_process_enter();
    const auto result = console_request(arena, *handoff, operation, generation, revision, request, response);
    production_process_leave(previous_cr2);
    if (result.status == ConsoleStatus::success) {
        require(result.generation != 0, "console source generation");
        console_last_generation = result.generation;
    }
    return result;
}
auto production_store_failure(ConsoleStatus status, program::Response &response) -> void {
    using namespace std::literals::string_view_literals;
    response = program::Response{program::Response::Kind::file_reply};
    const std::string_view message = status == ConsoleStatus::conflict ? "File changed; output discarded."sv
                                     : status == ConsoleStatus::malformed
                                         ? "File service rejected the request."sv
                                         : "File service unavailable; result unknown."sv;
    require(response.payload(std::as_bytes(std::span{message.data(), message.size()})), "console service failure");
}
auto production_selection_clear() -> void {
    console_selection_generation = console_note_revision = 0;
    command_note.release();
}
// The inner policy reply is copied from an untrusted service too. A malformed
// reply revokes only that observed incarnation; a possibly committed operation
// is not replayed and its result is reported as unknown.
auto production_bad_store_reply(U64 generation, program::Response &response) -> void {
    const auto previous_cr2 = production_process_enter();
    const auto rejected = reject_program_service(arena, *handoff, generation);
    production_process_leave(previous_cr2);
    require(rejected != ConsoleStatus::malformed, "console observed generation");
    command_files.abort();
    production_selection_clear();
    if (console_last_generation == generation)
        console_last_generation = 0;
    production_store_failure(ConsoleStatus::unavailable, response);
}
#endif
// Keep copied preparation records out of the domain creation/retirement stack.
__attribute__((noinline)) auto program_begin_upper_note() -> U64 {
    ConsoleNote::Value projection{};
#ifdef AURORA_PRODUCTION
    projection = command_note.projection();
#else
    __au_runtime_note_project(command_note.saved().data(), projection.data());
#endif
    require(command_note.begin_upper(projection, command_stream), "note upper input");
    const auto length = Bytes{projection}.get(64);
    program_scrub_copy(projection);
    return length;
}
#ifdef AURORA_PRODUCTION
[[nodiscard]] __attribute__((noinline)) auto program_save_note(program::Output &output, program::Response &response)
    -> bool {
    require(!command_note.bound() && !output.missing() && output.length() <= 53 && console_selection_generation &&
                console_note_revision,
            "note one-shot replacement");
    ConsoleNote::Value copied{};
    for (std::size_t index = 0; index < output.length(); ++index)
        copied[index] = std::byte(*output.byte(index));
    put(copied, 64, output.length());
    output.scrub();
    const auto result = production_console_request(
        ConsoleOperation::note_replace, console_selection_generation, console_note_revision, copied, {});
    program_scrub_copy(copied);
    if (result.status != ConsoleStatus::success) {
        production_store_failure(result.status, response);
        return false;
    }
    require(result.generation == console_selection_generation && console_note_revision != ~U64{0} &&
                result.revision != 0 && result.revision == console_note_revision + 1,
            "note committed revision");
    return true;
}
#else
[[nodiscard]] __attribute__((noinline)) auto program_note_apply(const ConsoleNote::UpdateInput &copied) -> U64 {
    require(!command_owned && !mailbox && frames.used() == 0 && program_boundary() && !command_note.bound(),
            "note quiescent update");
    ConsoleNote::Update update{};
    __au_runtime_note_update(copied.data(), update.data());
    const auto event = command_note.commit(update);
    require(event.has_value(), "note closed update");
    return *event;
}
__attribute__((noinline)) auto program_save_note(program::Output &output, program::Response &) -> bool {
    ConsoleNote::UpdateInput copied{};
    require(command_note.replacement(output, copied), "note complete replacement input");
    output.scrub();
    require(program_note_apply(copied) == 1, "note replacement accepted");
    return true;
}
#endif
[[nodiscard]] __attribute__((noinline)) auto program_save_file(program::Response &response) -> bool {
    require(!command_owned && !mailbox && frames.used() == 0 && program_boundary(), "file quiescent replacement");
    ConsoleFiles::ReplaceInput copied{};
    require(command_files.appending() ? command_files.replacement(command_append, copied)
                                      : command_files.replacement(command_stream, copied),
            "file one-shot complete replacement");
    ConsoleFiles::Mutation result{};
#ifdef AURORA_PRODUCTION
    require(console_selection_generation != 0, "file selected service incarnation");
    const auto committed =
        production_console_request(ConsoleOperation::files_replace, console_selection_generation, 0, copied, result);
    if (committed.status != ConsoleStatus::success) {
        command_files.abort();
        production_store_failure(committed.status, response);
        program_scrub_copy(copied);
        program_scrub_copy(result);
        return false;
    }
    require(committed.generation == console_selection_generation, "file committed service incarnation");
#else
    __au_runtime_files_replace(copied.data(), result.data());
#endif
#ifdef AURORA_PRODUCTION
    if (!command_files.publish(result)) {
        production_bad_store_reply(committed.generation, response);
        program_scrub_copy(copied);
        program_scrub_copy(result);
        return false;
    }
#else
    require(command_files.publish(result), "file Aurora replacement accepted");
#endif
    if (command_files.appending()) {
        response = program::Response{program::Response::Kind::file_reply};
        const auto count = Bytes{result}.get(ConsoleFiles::namespace_bytes + 64);
        require(count <= 64 &&
                    response.payload(std::span<const std::byte>{result}.subspan(ConsoleFiles::namespace_bytes, count)),
                "append response");
    } else
        response = program::Response{program::Response::Kind::file_saved};
    program_scrub_copy(copied);
    program_scrub_copy(result);
#ifdef AURORA_PROGRAM_FIXTURE
    if (fixture == Fixture::program_append_response && command_files.appending()) {
        require(command_files.settled() && !command_owned && !mailbox && frames.used() == 0 && program_boundary(),
                "append response cut after settled retirement");
        program_append_checkpoint = command_files.saved();
        program_append_operation = command_files.operation();
        program_append_revision = Bytes{command_files.saved()}.get(264);
        ProgramSerial::text("AURORA_PROGRAM_APPEND_SETTLED: operation=");
        ProgramSerial::number(command_files.operation());
        ProgramSerial::text(" revision=");
        ProgramSerial::number(Bytes{command_files.saved()}.get(264));
        ProgramSerial::text("\r\n");
        program_output_left = 5;
    }
#endif
    return true;
}
[[nodiscard]] auto
program_command(program::Submission &input, bool reading = false, bool saving = false, bool file = false) -> bool {
    using namespace std::literals::string_view_literals;
    require(!command_owned && program_boundary() && !mailbox && frames.used() == 0 && !(reading && saving),
            "program command boundary");
    command_file = file;
    command_transform = file && command_files.writable();
    const auto input_length = file ? input.length() : saving ? program_begin_upper_note() : input.length();
    command_appending = file && command_files.appending();
    require(command_appending ? command_append.begin()
                              : saving || (reading ? command_stream.begin_read(command_transform)
                                                   : command_stream.begin(input.bytes(), input.length())),
            "program command admission");
    input.scrub(); // The stream now owns the only retained command-input copy.
    command_owned = true;
    command_reading = reading;
    selected_client = 0;
    mailbox.emplace(registry);
    require(create(0) == 0 && create(1) == 1 && mailbox->bind(*domains[0].handle, *domains[1].handle),
            "program participants");
    ConsoleNote::Value projection{};
    // Upper ignores the read field and receives only its zero placeholder.
    if (file)
        projection = command_files.projection();
    else if (reading) {
#ifdef AURORA_PRODUCTION
        projection = command_note.projection();
#else
        __au_runtime_note_project(command_note.saved().data(), projection.data());
#endif
    }
    const auto service_grant = mailbox->endpoint(*domains[1].handle);
    require(service_grant &&
                command_note.bind(projection, *service_grant, file ? command_files.suffix() : ConsoleNote::Value{}),
            "note frozen publication");
    if (file)
        require(command_appending ? command_files.bind_append(
                                        registry, *mailbox, *domains[0].handle, *domains[1].handle, command_append)
                : command_transform
                    ? command_files.bind(registry, *mailbox, *domains[0].handle, *domains[1].handle, command_stream)
                    : command_files.bind_read(registry, *mailbox, *domains[0].handle, *domains[1].handle),
                "file command grants");
    program_scrub_copy(projection);
    const auto grant = mailbox->endpoint(*domains[0].handle);
    require(grant.has_value(), "program command grant");
    ProgramSerial::text("AURORA_PROGRAM_COMMAND_BEGIN: grant=");
    ProgramSerial::number(grant->generation());
    ProgramSerial::text(" length=");
    ProgramSerial::number(input_length);
    ProgramSerial::text(file      ? (command_files.appending() ? " domains=2 kind=append-file\r\n"sv
                                     : command_transform       ? " domains=2 kind=upper-file\r\n"sv
                                                               : " domains=2 kind=file\r\n"sv)
                        : reading ? " domains=2 kind=note\r\n"sv
                        : saving  ? " domains=2 kind=upper-note\r\n"sv
                                  : " domains=2 kind=upper\r\n"sv);
    bool success = true;
    if (command_appending)
        success = program_append_call();
    else
        while (const auto next = command_stream.next_input()) {
            const auto ordinal = next->ordinal();
            if (!program_execute(
                    0, ipc::Phase::request, program_source(ipc::Phase::request, ordinal), next->byte(), ordinal)) {
                success = false;
                break;
            }
            const auto service = mailbox->endpoint(*domains[1].handle);
            require(service.has_value(), "program service endpoint");
            const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *service, transaction);
            require(request && request->second() == ordinal && mailbox->scrubbed(), "program copied request");
            if (!program_execute(
                    1, ipc::Phase::service, program_source(ipc::Phase::service, ordinal), request->first(), ordinal)) {
                success = false;
                break;
            }
            const auto client = mailbox->endpoint(*domains[0].handle);
            require(client.has_value(), "program completion endpoint");
            const auto completion = mailbox->consume(*domains[0].handle, ipc::Phase::completion, *client, transaction);
            require(completion && completion->outcome() == ipc::Outcome::replied && mailbox->scrubbed(),
                    "program copied completion");
            if (!program_execute(0,
                                 ipc::Phase::completion,
                                 program_source(ipc::Phase::completion, ordinal),
                                 completion->value(),
                                 ordinal)) {
                success = false;
                break;
            }
            require(mailbox->recycle(ipc::Phase::inactive), "program consumed recycle");
            transaction = 0;
        }
    if (success && command_transform && !command_appending) {
        const auto endpoint = mailbox->endpoint(*domains[0].handle);
        require(endpoint && command_files.complete(registry, *mailbox, *domains[0].handle, *endpoint, command_stream),
                "file complete replacement authority");
    }
    program_cleanup(success);
    program::Response response{program::Response::Kind::stopped};
    if (success && command_transform) {
        success = program_save_file(response);
    } else if (success) {
        auto output = command_stream.finish();
        require(output && command_stream.scrubbed(), "program complete output");
        if (saving) {
            success = program_save_note(*output, response);
            if (success)
                response = program::Response{program::Response::Kind::note_saved};
        } else {
            response = program::Response{output->missing() ? (file ? program::Response::Kind::file_missing
                                                                   : program::Response::Kind::note_missing)
                                                           : program::Response::Kind::output};
            if (!output->missing()) {
                auto bytes = output->bytes();
                require(output->length() <= bytes.size() &&
                            response.payload(std::span<const std::uint8_t>{bytes}.first(output->length())),
                        "program copied response bytes");
                program_scrub_copy(bytes);
            }
            output->scrub();
        }
    } else {
        require(command_append.scrubbed() && command_stream.scrubbed(), "program cancelled output scrub");
    }
    // A replacement may already be committed. A failed acknowledgment never
    // retries the command or claims to roll that replacement back.
    const bool delivered = program_write_response(response);
#ifdef AURORA_PROGRAM_FIXTURE
    if (fixture == Fixture::program_append_response && command_files.appending()) {
        require(!delivered && program_output_left == 0 && command_files.settled() &&
                    command_files.operation() == program_append_operation &&
                    Bytes{command_files.saved()}.get(264) == program_append_revision &&
                    command_files.saved() == program_append_checkpoint && !command_owned && !mailbox &&
                    frames.used() == 0 && ProgramInputPlatform::quiet(),
                "append committed store survives actual response failure");
        program_scrub_copy(program_append_checkpoint);
        program_append_operation = 0;
        program_append_revision = 0;
        ProgramSerial::text("\r\nAURORA_PROGRAM_APPEND_RESPONSE_FAILED: committed=1 preserved=1\r\n");
    }
#endif
    if (success && command_transform)
        require(command_files.response_complete(delivered), "file settled response completion");
#ifdef AURORA_PRODUCTION
    production_selection_clear();
#endif
    return delivered;
}
#ifdef AURORA_PRODUCTION
[[nodiscard]] auto program_note_update(const program::Submission &input, program::Response &response) -> U64 {
    production_selection_clear();
    std::array<std::byte, 72> request{};
    for (std::size_t index = 0; index < input.length(); ++index)
        request[index] = std::byte(input.bytes()[index]);
    put(request, 64, input.length());
    ConsoleNote::Update result{};
    const auto reply = production_console_request(ConsoleOperation::note_command, 0, 0, request, result);
    program_scrub_copy(request);
    if (reply.status != ConsoleStatus::success) {
        production_store_failure(reply.status, response);
        program_scrub_copy(result);
        return 5; // Source session's production-only controlled failure response.
    }
    const auto action = command_note.select(result);
    if (!action) {
        production_bad_store_reply(reply.generation, response);
        program_scrub_copy(result);
        return 5;
    }
    if (*action >= 2) {
        console_selection_generation = reply.generation;
        console_note_revision = reply.revision;
    }
    program_scrub_copy(result);
    return *action;
}
#else
[[nodiscard]] auto program_note_update(const program::Submission &input, program::Response &) -> U64 {
    ConsoleNote::UpdateInput copied{};
    const auto &saved = command_note.saved();
    for (std::size_t index = 0; index < saved.size(); ++index) {
        copied[index] = saved[index];
    }
    for (std::size_t index = 0; index < input.bytes().size(); ++index) {
        copied[72 + index] = std::byte(input.bytes()[index]);
    }
    for (unsigned byte = 0; byte < 8; ++byte) {
        copied[136 + byte] = std::byte(input.length() >> (8 * byte));
    }
    return program_note_apply(copied);
}
#endif
#endif
[[nodiscard]] __attribute__((noinline)) auto program_files_update(const program::Submission &input,
                                                                  program::Response &response) -> U64 {
    require(ProgramInputPlatform::quiet(), "file storage mutation boundary");
    ConsoleFiles::UpdateInput copied{};
#ifndef AURORA_PRODUCTION
    const auto &saved = command_files.saved();
    std::copy(saved.begin(), saved.end(), copied.begin());
#endif
    for (std::size_t i = 0; i < input.length(); ++i)
        copied[ConsoleFiles::namespace_bytes + i] = std::byte(input.bytes()[i]);
    put(copied, ConsoleFiles::namespace_bytes + 64, input.length());
#ifdef AURORA_FILE_CALL
    copied[ConsoleFiles::namespace_bytes + 72] = std::byte{1};
#endif
    ConsoleFiles::Update result{};
#ifdef AURORA_PRODUCTION
    production_selection_clear();
    const auto reply = production_console_request(ConsoleOperation::files_command, 0, 0, copied, result);
    if (reply.status != ConsoleStatus::success) {
        production_store_failure(reply.status, response);
        program_scrub_copy(copied);
        program_scrub_copy(result);
        return 1;
    }
#else
    __au_runtime_files_update(copied.data(), result.data());
#endif
    const auto action = command_files.update(result);
#ifdef AURORA_PRODUCTION
    if (!action) {
        production_bad_store_reply(reply.generation, response);
        program_scrub_copy(copied);
        program_scrub_copy(result);
        return 1;
    }
    if (*action >= 2)
        console_selection_generation = reply.generation;
#else
    require(action.has_value(), "file closed update");
#endif
    if (*action == 1) {
        response = program::Response{program::Response::Kind::file_reply};
        const auto count = Bytes{result}.get(ConsoleFiles::namespace_bytes + 64);
        require(count <= 64 &&
                    response.payload(std::span<const std::byte>{result}.subspan(ConsoleFiles::namespace_bytes, count)),
                "file copied response bytes");
    }
    program_scrub_copy(copied);
    program_scrub_copy(result);
    return *action;
}
#ifdef AURORA_FILE_CALL
// File protocol policy stays outside the call transport and timer accounting.
auto file_call_offset(U64 offset) -> void {
    const auto &caller = domains[0];
    require(offset == caller.call_count, "file bounded sequential offset");
}
[[nodiscard]] auto file_call_reply(U64 reply) -> bool {
    if (!ConsoleFiles::read_reply_valid(reply))
        return false;
    if (domains[0].call_limit > 1 && (reply & 255) != 1)
        domains[0].call_closed = true;
    return true;
}
#include "blocking-call.inc"
#include "file-call.inc"
#endif
#ifdef AURORA_PRODUCTION
// Child output crosses only as bounded copied bytes at the supervisor root.
// There is no Console/Display grant while the process owns the architecture;
// the grid is painted after exact root/window and interrupt-owner restoration.
auto production_output(void *, bool, std::span<const std::byte> bytes) -> bool {
    if (root() != kernel_root || !irq_off() || !command_owned || saved_rsp || active != L::domain_count ||
        program.running() || timer_armed || timer_draining || timer_owner || run_authority || console_waiting ||
        LocalApicTimerIo::read(0x390) != 0 ||
        (LocalApicTimerIo::read(0x320) & 0x700ff) != (0x10000 | LocalApicTimerIo::vector) ||
        !LocalApicTimerIo::quiet(0x100, false) || !LocalApicTimerIo::quiet(0x200, false))
        stop("production output ownership");
    for (const auto byte : bytes)
        if (ProgramConsoleTransport::try_put(std::to_integer<std::uint8_t>(byte)) != console::PutResult::success)
            return false;
    return true;
}
[[nodiscard]] __attribute__((noinline)) auto production_run(const program::Submission &input) -> bool {
    require(ProgramInputPlatform::quiet() && terminal_mapping(), "production run entry ownership");
    program::RunArguments arguments;
    program::Response response{program::Response::Kind::file_reply};
    if (!arguments.parse(input)) {
        constexpr std::string_view usage = "Usage: run PATH [args]; no quotes/escapes; at most 16 words.";
        require(response.payload(std::as_bytes(std::span{usage.data(), usage.size()})), "run usage");
        return program_write_response(response);
    }
    const auto previous_cr2 = production_process_enter();
    const auto result =
        run_program(arena, *handoff, arguments.path(), arguments.arguments(), production_output, nullptr);
    production_process_leave(previous_cr2);
    if (result.status == RunStatus::output_failed)
        return false; // Never retry output or print a prompt after transport failure.
    std::array<std::byte, 64> message{};
    std::size_t size = 0;
    const auto append = [&](std::string_view text) {
        for (const auto byte : text) {
            require(size < message.size(), "run response bounds");
            message[size++] = std::byte{static_cast<unsigned char>(byte)};
        }
    };
    append("\r\nrun: ");
    switch (result.status) {
    case RunStatus::exited:
        append("exited status=");
        break;
    case RunStatus::fault:
        append("fault vector=");
        break;
    case RunStatus::watchdog:
        append("watchdog");
        break;
    case RunStatus::cancelled:
        append("cancelled");
        break;
    case RunStatus::missing:
        append("program not found");
        break;
    case RunStatus::malformed:
        append("invalid executable or arguments");
        break;
    case RunStatus::quota:
        append("resource quota exceeded");
        break;
    case RunStatus::unavailable:
        append("file service unavailable");
        break;
    default:
        stop("production run result");
    }
    if (result.status == RunStatus::exited || result.status == RunStatus::fault) {
        U64 divisor = 1;
        while (divisor <= result.value / 10)
            divisor *= 10;
        do {
            const char digit = static_cast<char>('0' + result.value / divisor % 10);
            append({&digit, 1});
            divisor /= 10;
        } while (divisor);
    }
    require(response.payload(std::span<const std::byte>{message}.first(size)), "run result response");
    return program_write_response(response);
}
#endif
__attribute__((noinline)) auto run_program_console() -> void {
    require(program_boundary() && !command_owned && L::domain_count == 2, "program console initial ownership");
    const auto begin = reinterpret_cast<U64>(&program_poll_begin), end = reinterpret_cast<U64>(&program_poll_end);
    require(begin >= arena + Handoff::payload_offset && end > begin && end - begin == 3 &&
                end < arena + Handoff::payload_offset + handoff->get(64),
            "program console wake RX interval");
    require((hardware::Io::read(0x3fb) & 0x80) == 0, "program UART register bank");
    hardware::Io::write(0x3f9, 0);
    require(hardware::Io::read(0x3f9) == 0, "program UART IRQ disabled");
    ProgramSerial::initialize_input();
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
    terminal_install();
#endif
#if defined(AURORA_PRODUCTION) && defined(AURORA_UEFI_NVME)
    if (Handoff::bar(*handoff)) {
        // Only admitted production tag 4 starts storage before the first prompt.
        // Readiness (or controlled unavailability) is reported by the source-owner
        // boundary; the default RAM composition remains lazy and never probes NVMe.
        const auto previous_cr2 = production_process_enter();
        static_cast<void>(prepare_programs(arena, *handoff));
        production_process_leave(previous_cr2);
    }
#endif
    using Event = program::Session::Event;
    using Effect = program::Session::Effect;
    program::Session session;
#ifdef AURORA_PRODUCTION
    auto effect = session.advance(Event::begin, 2);
#elif defined(AURORA_FILE_CALL)
    auto effect = session.advance(Event::begin, 1);
#else
    auto effect = session.advance(Event::begin, 0);
#endif
    program::Submission copied;
    program::Response response;
    while (effect != Effect::exited && effect != Effect::failed) {
        switch (effect) {
        case Effect::input:
            program_read_input(copied, session.after_cr());
            effect = session.advance(Event::input, static_cast<U64>(copied.action()), copied.after_cr());
            continue;
#ifdef AURORA_PRODUCTION
        case Effect::run:
            effect = session.advance(Event::response, production_run(copied));
            copied.scrub();
            continue;
#endif
        case Effect::files:
            response = program::Response{program::Response::Kind::unknown};
            effect = session.advance(Event::files, program_files_update(copied, response));
            continue;
#ifndef AURORA_FILE_CALL
        case Effect::ready:
            response = program::Response{program::Response::Kind::ready};
            break;
        case Effect::note:
            effect = session.advance(Event::note, program_note_update(copied, response));
            continue;
        case Effect::upper:
            effect = session.advance(Event::response, program_command(copied));
            continue;
        case Effect::read_note:
            effect = session.advance(Event::response, program_command(copied, true));
            continue;
        case Effect::upper_note:
            effect = session.advance(Event::response, program_command(copied, false, true));
            continue;
        case Effect::file:
            effect = session.advance(Event::response, program_command(copied, true, false, true));
            continue;
        case Effect::note_saved:
            response = program::Response{program::Response::Kind::note_saved};
            break;
#else
        case Effect::file_ready: {
            response = program::Response{program::Response::Kind::file_reply};
            constexpr std::string_view banner = "AURORA_FILE_CALL_READY: file storage, peek/wc/crc <name>";
            require(response.payload(std::as_bytes(std::span{banner.data(), banner.size()})), "file call banner");
            break;
        }
        case Effect::peek:
            effect = session.advance(Event::response, program_file_call(copied, false, false));
            continue;
        case Effect::wc:
            effect = session.advance(Event::response, program_file_call(copied, true, false));
            continue;
        case Effect::crc:
            effect = session.advance(Event::response, program_file_call(copied, true, true));
            continue;
#endif
        case Effect::abort_file:
            command_files.abort();
#ifdef AURORA_PRODUCTION
            production_selection_clear();
#endif
            [[fallthrough]];
        case Effect::unknown:
            response = program::Response{program::Response::Kind::unknown};
            break;
        case Effect::file_reply:
            break; // The store already supplied the copied response.
        default:
            stop("program session effect");
        }
        copied.scrub();
        effect = session.advance(Event::response, program_write_response(response));
    }
    response.scrub();
    copied.scrub();
    require(ProgramInputPlatform::quiet(), "program console exit boundary");
#ifdef AURORA_FILE_CALL
    const auto exiting_service = domains[1].handle ? registry.incarnation(*domains[1].handle).value_or(0) : 0;
    const auto exit_effect = file_service_transition(3);
    require((exit_effect == 5 && !domains[1].handle) || (exit_effect == 4 && retire(1)),
            "file service exit retirement");
    require(ProgramInputPlatform::quiet() && frames.used() == 0, "file service exit all leases released");
    Serial::text("AURORA_FILE_SERVICE_EXIT: service=");
    Serial::number(exiting_service);
    Serial::text(" used=0 scrubbed=1\r\n");
#endif
#ifdef AURORA_PRODUCTION
    production_selection_clear();
    if (console_last_generation) {
        const auto cleared = production_console_request(ConsoleOperation::clear, console_last_generation, 0, {}, {});
        // A refused clear can also mean source revision exhaustion. Revoke the
        // exact old owner on every non-success; never affect another incarnation,
        // start an owner or retry a possibly completed clear on exit.
        if (cleared.status != ConsoleStatus::success) {
            production_bad_store_reply(console_last_generation, response);
            response.scrub();
        }
        console_last_generation = 0;
    }
    require(finish_programs(arena, *handoff), "resident owner shutdown result");
#endif
    command_note.clear();
    command_files.clear();
#ifdef AURORA_PROGRAM_FIXTURE
    if (fixture == Fixture::program_append_response) {
        require(session.outcome() == 2 && program_output_left == 0 && frames.used() == 0 &&
                    ProgramInputPlatform::quiet() && !command_files.settled() && command_files.operation() == 0,
                "append failed response terminal cleanup");
        for (std::size_t index = 0; index < command_files.saved().size(); ++index)
            require(command_files.saved()[index] == std::byte(index == 264 ? 1 : 0) &&
                        program_append_checkpoint[index] == std::byte{0},
                    "append session store and checkpoint cleared");
        ProgramSerial::text("AURORA_PROGRAM_APPEND_CLEARED: saved=0 revision=1 domains=0 leases=0\r\n");
    }
#endif
    if (session.outcome() == 2) {
        // A partial response cannot be rolled back or replayed. Leave through
        // the existing failure device without using the failed channel.
        hardware::Io::write(0xf4, 0x11);
        for (;;)
            asm volatile("cli; hlt");
    }
    ProgramSerial::text("AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0\r\n");
}
