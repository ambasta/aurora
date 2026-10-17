// Selection has already returned and unwound its copied records. Each command
// owns a fresh two-domain incarnation; this is a partial read, never a Stream.
[[nodiscard]] [[gnu::noinline]] auto program_file_call(program::Submission &input) -> bool {
    require(!command_owned && program_boundary() && !mailbox && frames.used() == 0 &&
                command_files.selected() && !command_files.writable(), "file call boundary");
    input.scrub();
    command_owned = true;
    mailbox.emplace(registry);
    require(create(0) == 0 && create(1) == 1 && mailbox->bind(*domains[0].handle, *domains[1].handle) &&
                command_files.bind_read(registry, *mailbox, *domains[0].handle, *domains[1].handle),
            "file call participants");
    const auto endpoint = mailbox->endpoint(*domains[1].handle);
    require(endpoint && command_note.bind(command_files.projection(), *endpoint), "file call frozen projection");
    U64 phase = 0;
#ifdef AURORA_FILE_CALL_FAULT
    if (!console_probe_used) phase = 1;
#endif
#ifdef AURORA_FILE_CALL_BUDGET
    if (!console_probe_used) phase = 8;
#endif
    console_probe_used = true;
    Serial::text("AURORA_FILE_CALL_BEGIN: generation=");
    Serial::number(endpoint->generation());
    Serial::text("\r\n");
    call_execute(0, phase + 16, 0, 0);
    require(call_wait.context && call_wait.authority && call_wait.ticket && call_wait.ticks > 0,
            "file caller live suspension");
    const auto ticket = call_wait.ticket, epoch = call_wait.authority->epoch();
    const auto ticks = call_wait.ticks, remaining = call_wait.remaining;
    const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *endpoint, ticket);
    require(request && request->first() == 0 && request->second() == 0, "file copied offset");
    call_execute(1, phase == 1 ? 4 : 11, request->first(), request->second());
    require(timer_epoch > epoch && call_wait.ticks == ticks && call_wait.remaining == remaining,
            "file isolated service budget");
    if (phase == 1) {
        require(program.event() == ProgramEvent::bounds && mailbox->cancel(ipc::Phase::inactive),
                "file checked service cancellation");
    } else {
        require(program.event() == ProgramEvent::returned && !mailbox->cancel(ipc::Phase::inactive),
                "file durable service reply");
    }
    require(call_resume(ticket), "file exactly once resume");
    require(timer_epoch == epoch && timer_ticks >= ticks && timer_initial == timer_ticks + timer_remaining,
            "file original caller budget");
    U64 result = 0;
    if (phase == 8) {
        require(timer_exhausted && timer_remaining == 0 && timer_ticks == timer_initial,
                "file resumed budget exhaustion");
    } else {
        require(program.event() == ProgramEvent::returned, "file retained caller locals");
        result = program.value() - 40;
        require(phase == 1 ? result == 0 : program::Files::read_reply_valid(result), "file copied caller result");
    }
    require(mailbox->revoke(ipc::Phase::inactive) && retire(0) && retire(1) && frames.used() == 0 &&
                command_files.release_read(registry, *mailbox), "file call authenticated retirement");
    require(!call_wait.context && !call_wait.ticket && !command_note.bound(), "file call scrubbed");
    mailbox.reset();
    selected_client = 2;
    command_owned = false;
    require(program_boundary(), "file call quiescent result");
    Serial::text("AURORA_FILE_CALL_END: result=");
    Serial::number(result);
    Serial::text(" used=0\r\n");
    program::Response response{program::Response::Kind::stopped};
    if (phase == 0) {
        response = program::Response{result == 3 ? program::Response::Kind::file_missing : program::Response::Kind::file_reply};
        if (result == 2) {
            constexpr std::array<std::uint8_t, 3> text{'E', 'O', 'F'};
            require(response.payload(text), "file EOF presentation");
        } else if ((result & 255) == 1) {
            const std::array<std::uint8_t, 7> text{'b', 'y', 't', 'e', '>', ' ', static_cast<std::uint8_t>(result >> 8)};
            require(response.payload(text), "file byte presentation");
        } else require(result == 3, "file command supported result");
    }
    return program_write_response(response);
}
