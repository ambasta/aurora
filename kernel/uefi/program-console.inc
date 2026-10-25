// Included only by the opt-in two-domain program-console adapter.
// One shared timer mapping and one IDT gate; ownership is selected only at a
// fully quiescent private-kernel boundary. No source-language pointer ABI.
using ProgramSerial = Serial; // One shared sticky receive-error latch, including runtime traces.
#ifndef AURORA_FILE_CALL
program::Stream command_stream;
#endif
program::Note command_note;
program::Files command_files;
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
    const auto &caller = domains[0];
    if (caller.handle || caller.contract || caller.tables || caller.call_count || caller.call_limit != 1 ||
        caller.call_service_used || caller.call_closed || call_wait.context || call_wait.authority ||
        call_wait.service || call_wait.ticket || call_wait.endpoint.slot() || call_wait.endpoint.generation() ||
        call_wait.remaining || call_wait.ticks)
        return false;
    for (const auto &lease : caller.stacks)
        if (lease)
            return false;
    for (const auto word : call_wait.launch)
        if (word)
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
[[nodiscard]] auto program_execute(unsigned index, ipc::Phase phase, U64 source, U64 byte, U64 ordinal) -> bool {
    require(command_owned && program_boundary() && index < 2 && selected_client == 0, "program launch boundary");
    auto &domain = domains[index];
    require(domain.handle && domain.contract && verify(domain), "program launch domain");
    const auto endpoint = mailbox->endpoint(*domain.handle);
    require(endpoint.has_value(), "program launch grant");
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
        require(index == 1 && mailbox->state() == ipc::State::delivered && command_note.matches(*endpoint),
                "note authenticated publication");
        const auto physical = frames.address(*domain.stacks.back());
        const auto virtual_page = domain.contract->layout().user_stack_top() - L::page_size;
        require(physical && (domain.tables->entry(virtual_page) & ~0x60ULL) == (*physical | 7 | RuntimeTables::nx) &&
                    (PageTables{kernel_root, static_cast<std::size_t>(handoff->get(96))}.entry(*physical) & ~0x60ULL) ==
                        (*physical | 3 | RuntimeTables::nx),
                "note exact retained stack mapping");
        auto *record = reinterpret_cast<std::byte *>(*physical + L::page_size - program::Note::stack_reservation);
        require(
            command_note.stage(std::span<std::byte, program::Note::record_bytes>{record, program::Note::record_bytes},
                               *endpoint,
                               source,
                               ipc::Request{byte, ordinal}),
            "note fixed copied record");
    }
    require(launch_domain(index, *domain.handle), "program continuation");
    timer_finish();
    require(root() == kernel_root && saved_rsp == 0 && active == L::domain_count && !program.running(),
            "program restored authority");
    const auto okay = program.event() == ProgramEvent::returned;
    require(okay || recoverable_program_event(), "program terminal outcome");
    launch = {};
    selected_phase = ipc::Phase::inactive;
    require(program_boundary(), "program post-run quiescence");
    return okay;
}
// Inject only after one byte was fully acknowledged. A note read includes its
// final EOF round; only an actual injection makes later commands healthy.
[[nodiscard]] auto program_source(ipc::Phase phase, U64 ordinal) -> U64 {
    const U64 normal = command_reading ? (phase == ipc::Phase::request   ? 12
                                          : phase == ipc::Phase::service ? 11
                                          : command_transform            ? 14
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
auto program_cleanup(bool success) -> void {
    require(command_owned && program_boundary() && mailbox, "program cleanup boundary");
    if (!success) {
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
    command_note.release();
    if (!success && command_file && command_transform)
        command_files.abort();
    require(mailbox->scrubbed() && mailbox->revoke(ipc::Phase::inactive) && retire(0) && retire(1) &&
                frames.used() == 0,
            "program revoke/retire/scrub");
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
    ProgramSerial::text("AURORA_PROGRAM_COMMAND_END: success=");
    ProgramSerial::number(success ? 1 : 0);
    ProgramSerial::text(" used=0 epoch=");
    ProgramSerial::number(timer_epoch);
    ProgramSerial::text("\r\n");
}
// Keep copied preparation records out of the domain creation/retirement stack.
__attribute__((noinline)) auto program_begin_upper_note() -> U64 {
    program::Note::Value projection{};
    __au_runtime_note_project(command_note.saved().data(), projection.data());
    require(command_note.begin_upper(projection, command_stream), "note upper input");
    return Bytes{projection}.get(64);
}
[[nodiscard]] __attribute__((noinline)) auto program_note_apply(const program::Note::UpdateInput &copied) -> U64 {
    require(!command_owned && !mailbox && frames.used() == 0 && program_boundary() && !command_note.bound(),
            "note quiescent update");
    program::Note::Update update{};
    __au_runtime_note_update(copied.data(), update.data());
    const auto event = command_note.commit(update);
    require(event.has_value(), "note closed update");
    return *event;
}
__attribute__((noinline)) auto program_save_note(program::Output &output) -> void {
    program::Note::UpdateInput copied{};
    require(command_note.replacement(output, copied), "note complete replacement input");
    output.scrub();
    require(program_note_apply(copied) == 1, "note replacement accepted");
}
__attribute__((noinline)) auto program_save_file() -> void {
    require(!command_owned && !mailbox && frames.used() == 0 && program_boundary(), "file quiescent replacement");
    program::Files::ReplaceInput copied{};
    require(command_files.replacement(command_stream, copied), "file one-shot complete replacement");
    program::Files::Mutation result{};
    __au_runtime_files_replace(copied.data(), result.data());
    require(command_files.publish(result), "file Aurora replacement accepted");
}
[[nodiscard]] auto
program_command(program::Submission &input, bool reading = false, bool saving = false, bool file = false) -> bool {
    using namespace std::literals::string_view_literals;
    require(!command_owned && program_boundary() && !mailbox && frames.used() == 0 && !(reading && saving),
            "program command boundary");
    command_file = file;
    command_transform = file && command_files.writable();
    const auto input_length = file ? input.length() : saving ? program_begin_upper_note() : input.length();
    require(saving || (reading ? command_stream.begin_read(command_transform)
                               : command_stream.begin(input.bytes(), input.length())),
            "program command admission");
    input.scrub(); // The stream now owns the only retained command-input copy.
    command_owned = true;
    command_reading = reading;
    selected_client = 0;
    mailbox.emplace(registry);
    require(create(0) == 0 && create(1) == 1 && mailbox->bind(*domains[0].handle, *domains[1].handle),
            "program participants");
    program::Note::Value projection{};
    // Upper ignores the read field and receives only its zero placeholder.
    if (file)
        projection = command_files.projection();
    else if (reading)
        __au_runtime_note_project(command_note.saved().data(), projection.data());
    const auto service_grant = mailbox->endpoint(*domains[1].handle);
    require(service_grant && command_note.bind(projection, *service_grant), "note frozen publication");
    if (file)
        require(command_transform
                    ? command_files.bind(registry, *mailbox, *domains[0].handle, *domains[1].handle, command_stream)
                    : command_files.bind_read(registry, *mailbox, *domains[0].handle, *domains[1].handle),
                "file command grants");
    projection = {};
    const auto grant = mailbox->endpoint(*domains[0].handle);
    require(grant.has_value(), "program command grant");
    ProgramSerial::text("AURORA_PROGRAM_COMMAND_BEGIN: grant=");
    ProgramSerial::number(grant->generation());
    ProgramSerial::text(" length=");
    ProgramSerial::number(input_length);
    ProgramSerial::text(file ? (command_transform ? " domains=2 kind=upper-file\r\n"sv : " domains=2 kind=file\r\n"sv)
                        : reading ? " domains=2 kind=note\r\n"sv
                        : saving  ? " domains=2 kind=upper-note\r\n"sv
                                  : " domains=2 kind=upper\r\n"sv);
    bool success = true;
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
    if (success && command_transform) {
        const auto endpoint = mailbox->endpoint(*domains[0].handle);
        require(endpoint && command_files.complete(registry, *mailbox, *domains[0].handle, *endpoint, command_stream),
                "file complete replacement authority");
    }
    program_cleanup(success);
    program::Response response{program::Response::Kind::stopped};
    if (success && command_transform) {
        program_save_file();
        response = program::Response{program::Response::Kind::file_saved};
    } else if (success) {
        auto output = command_stream.finish();
        require(output && command_stream.scrubbed(), "program complete output");
        if (saving) {
            program_save_note(*output);
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
        require(command_stream.scrubbed(), "program cancelled output scrub");
    }
    // A replacement may already be committed. A failed acknowledgment never
    // retries the command or claims to roll that replacement back.
    return program_write_response(response);
}
[[nodiscard]] auto program_note_update(const program::Submission &input) -> U64 {
    program::Note::UpdateInput copied{};
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
[[nodiscard]] __attribute__((noinline)) auto program_files_update(const program::Submission &input,
                                                                  program::Response &response) -> U64 {
    require(ProgramInputPlatform::quiet(), "file storage mutation boundary");
    program::Files::UpdateInput copied{};
    const auto &saved = command_files.saved();
    for (std::size_t i = 0; i < saved.size(); ++i)
        copied[i] = saved[i];
    for (std::size_t i = 0; i < input.bytes().size(); ++i)
        copied[272 + i] = std::byte(input.bytes()[i]);
    for (unsigned i = 0; i < 8; ++i)
        copied[336 + i] = std::byte(input.length() >> (8 * i));
    program::Files::Update result{};
    __au_runtime_files_update(copied.data(), result.data());
    const auto action = command_files.update(result);
    require(action.has_value(), "file closed update");
    if (*action == 1) {
        response = program::Response{program::Response::Kind::file_reply};
        const auto count = Bytes{result}.get(336);
        require(count <= 64 && response.payload(std::span<const std::byte>{result}.subspan(272, count)),
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
    if (!program::Files::read_reply_valid(reply))
        return false;
    if (domains[0].call_limit > 1 && (reply & 255) != 1)
        domains[0].call_closed = true;
    return true;
}
#include "blocking-call.inc"
#include "file-call.inc"
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
    program::Response ready{program::Response::Kind::ready};
#ifdef AURORA_FILE_CALL
    ready = program::Response{program::Response::Kind::file_reply};
    constexpr std::string_view banner = "AURORA_FILE_CALL_READY: file storage, peek/wc/crc <name>";
    require(ready.payload(std::as_bytes(std::span{banner.data(), banner.size()})), "file call banner");
#endif
    bool okay = program_write_response(ready);
    program::Submission copied;
    U64 after_cr = 0;
    while (okay) {
        program_read_input(copied, after_cr);
        after_cr = copied.after_cr(); // Carry a submitted CR across protected execution.
        const auto action = copied.action();
        if (action == program::Submission::Action::upper_payload) {
#ifdef AURORA_FILE_CALL
            program::Response unsupported{program::Response::Kind::unknown};
            copied.scrub();
            okay = program_write_response(unsupported);
            continue;
#else
            okay = program_command(copied);
            continue;
#endif
        }
        if (action == program::Submission::Action::requested_exit ||
            action == program::Submission::Action::output_failure) {
            okay = action != program::Submission::Action::output_failure;
            break;
        }
#ifndef AURORA_FILE_CALL
        const auto note_event = program_note_update(copied);
        if (note_event != 0) {
            if (note_event == 1) {
                program::Response response{program::Response::Kind::note_saved};
                copied.scrub();
                okay = program_write_response(response);
            } else
                okay = program_command(copied, note_event != 4, note_event == 4);
            copied.scrub();
            continue;
        }
#endif
        program::Response response{program::Response::Kind::unknown};
        const auto file_event = program_files_update(copied, response);
        if (file_event != 0) {
#ifdef AURORA_FILE_CALL
            if (file_event >= 4 && file_event <= 6)
                okay = program_file_call(copied, file_event != 4, file_event == 6);
            else if (file_event >= 2) {
                command_files.abort();
                copied.scrub();
                okay = program_write_response(response);
            }
#else
            if (file_event >= 4 && file_event <= 6) {
                command_files.abort();
                copied.scrub();
                okay = program_write_response(response);
            } else if (file_event >= 2)
                okay = program_command(copied, true, false, true);
#endif
            else {
                copied.scrub();
                okay = program_write_response(response);
            }
            response.scrub();
            copied.scrub();
            continue;
        }
        copied.scrub();
        okay = program_write_response(response);
    }
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
    command_note.clear();
    command_files.clear();
    if (!okay) {
        // A partial response cannot be rolled back or replayed. Leave through
        // the existing failure device without using the failed channel.
        hardware::Io::write(0xf4, 0x11);
        for (;;)
            asm volatile("cli; hlt");
    }
    ProgramSerial::text("AURORA_PROGRAM_CONSOLE_QUIET: timer=masked isr=0 irr=0 domains=0\r\n");
}
