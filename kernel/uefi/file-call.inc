// Selection has already returned and unwound its copied records. Each command
// owns a fresh two-domain incarnation; the read is bounded and never grants a writable Stream.
[[nodiscard]] [[gnu::noinline]] auto program_file_call(program::Submission &input, bool count_words, bool checksum) -> bool {
    require(!command_owned && program_boundary() && !mailbox && frames.used() == 0 &&
                command_files.selected() && !command_files.writable(), "file call boundary");
    require(!checksum || count_words, "CRC sequential selection");
    auto &probes = checksum ? file_crc_probes : file_wc_probes;
    file_wc = count_words;
    file_closed = false;
    file_call_count = file_service_used = 0;
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
    if (!console_probe_used && !file_wc) phase = 1;
    if (file_wc && probes == 0) phase = 33;
#endif
#ifdef AURORA_FILE_CALL_BUDGET
    if (!console_probe_used && !file_wc) phase = 8;
    if (file_wc && probes < 4) phase = 34 + probes;
#endif
    if (file_wc) {
        if (probes < 4) ++probes;
        if (phase == 0) phase = 32;
    } else console_probe_used = true;
    Serial::text(checksum ? std::string_view{"AURORA_CRC_BEGIN: generation="} : file_wc ? std::string_view{"AURORA_WC_BEGIN: generation="} : std::string_view{"AURORA_FILE_CALL_BEGIN: generation="});
    Serial::number(endpoint->generation());
    Serial::text("\r\n");
#ifdef AURORA_FILE_CALL_BUDGET
    file_budget_probe = phase;
#endif
    U64 result = 0;
    if (file_wc) {
        call_execute(0, phase + (checksum ? 16 : 0), 0, 0);
        U64 previous = 0;
        while (call_wait.context) {
            require(call_wait.authority && call_wait.ticket && file_call_count > 0 && file_call_count <= 50,
                    "wc bounded live suspension");
            const auto ticket = call_wait.ticket, epoch = call_wait.authority->epoch();
            const auto ticks = call_wait.ticks, remaining = call_wait.remaining;
            require(!call_resume(previous) && !call_resume(ticket), "wc stale and unready wake");
            const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *endpoint, ticket);
            require(request && request->first() == file_call_count - 1 && request->second() == 0,
                    "wc sequential copied offset");
            const bool midpoint = request->first() == 2;
            call_execute(1, midpoint && phase == 33 ? 4 : midpoint && phase == 35 ? 5 : 11,
                         request->first(), request->second());
            require(timer_epoch > epoch && call_wait.ticks == ticks && call_wait.remaining == remaining,
                    "wc isolated cumulative allowance");
            if (timer_exhausted || program.event() != ProgramEvent::returned) {
                file_closed = true;
                require(mailbox->cancel(ipc::Phase::inactive), "wc partial cancellation");
            } else require(mailbox->state() == ipc::State::replied && !mailbox->cancel(ipc::Phase::inactive),
                           "wc durable reply");
            require(!call_resume(previous), "wc stale wake preserves readiness");
            require(call_resume(ticket) && !call_resume(ticket), "wc exactly once resume");
            require(timer_epoch == epoch && timer_ticks >= ticks && timer_initial == timer_ticks + timer_remaining,
                    "wc original caller allowance");
            previous = ticket;
        }
        if (!timer_exhausted && program.event() == ProgramEvent::returned) result = program.value();
        require(result == 0 || result == 3 || ((result & 255) == 1 && (checksum ? (result >> 40) == 0 : (result >> 32) == 0 &&
                    ((result >> 8) & 255) <= 49 && ((result >> 16) & 255) <= 49 &&
                    ((result >> 24) & 255) <= 49)), "wc bounded copied counts");
        Serial::text(checksum ? std::string_view{"AURORA_CRC_TOTAL: calls="} : std::string_view{"AURORA_WC_TOTAL: calls="}); Serial::number(file_call_count);
        Serial::text(" caller="); Serial::number(timer_ticks);
        Serial::text(" service="); Serial::number(file_service_used); Serial::text("\r\n");
    } else {
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
        if (phase == 8) {
            require(timer_exhausted && timer_remaining == 0 && timer_ticks == timer_initial,
                    "file resumed budget exhaustion");
        } else {
            require(program.event() == ProgramEvent::returned, "file retained caller locals");
            result = program.value() - 40;
            require(phase == 1 ? result == 0 : program::Files::read_reply_valid(result), "file copied caller result");
        }
    }
    require(mailbox->revoke(ipc::Phase::inactive) && retire(0) && retire(1) && frames.used() == 0 &&
                command_files.release_read(registry, *mailbox), "file call authenticated retirement");
    require(!call_wait.context && !call_wait.ticket && !command_note.bound(), "file call scrubbed");
    mailbox.reset();
    selected_client = 2;
    command_owned = false;
    require(program_boundary(), "file call quiescent result");
    Serial::text(checksum ? std::string_view{"AURORA_CRC_END: result="} : file_wc ? std::string_view{"AURORA_WC_END: result="} : std::string_view{"AURORA_FILE_CALL_END: result="});
    Serial::number(result);
    Serial::text(" used=0\r\n");
    program::Response response{program::Response::Kind::stopped};
    if (file_wc && result != 0) {
        response = program::Response{result == 3 ? program::Response::Kind::file_missing : program::Response::Kind::file_reply};
        if (result != 3) {
            std::array<std::uint8_t, 8> text{};
            unsigned size = 0;
            if (checksum) {
                constexpr std::string_view digits{"0123456789abcdef"};
                for (unsigned i = 0; i < 8; ++i)
                    text[size++] = static_cast<std::uint8_t>(digits[(result >> (36 - 4 * i)) & 15]);
            } else for (unsigned shift : {8U, 16U, 24U}) {
                const auto count = (result >> shift) & 255;
                if (count >= 10) text[size++] = static_cast<std::uint8_t>('0' + count / 10);
                text[size++] = static_cast<std::uint8_t>('0' + count % 10);
                if (shift != 24) text[size++] = ' ';
            }
            require(response.payload(std::span<const std::uint8_t>{text.data(), size}), "wc counts presentation");
        }
    } else if (!file_wc && phase == 0) {
        response = program::Response{result == 3 ? program::Response::Kind::file_missing : program::Response::Kind::file_reply};
        if (result == 2) {
            constexpr std::array<std::uint8_t, 3> text{'E', 'O', 'F'};
            require(response.payload(text), "file EOF presentation");
        } else if ((result & 255) == 1) {
            const std::array<std::uint8_t, 7> text{'b', 'y', 't', 'e', '>', ' ', static_cast<std::uint8_t>(result >> 8)};
            require(response.payload(text), "file byte presentation");
        } else require(result == 3, "file command supported result");
    }
#ifdef AURORA_FILE_CALL_BUDGET
    file_budget_probe = 0;
#endif
    file_wc = file_closed = false;
    file_call_count = file_service_used = 0;
    return program_write_response(response);
}
