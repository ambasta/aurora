// Selection has already returned and unwound its copied records. Each command
// owns a fresh caller/read grant; a healthy scrubbed service incarnation is reused.
[[nodiscard]] [[gnu::noinline]] auto program_file_call(program::Submission &input, bool count_words, bool checksum)
    -> bool {
    require(ProgramInputPlatform::quiet() && command_files.selected() && !command_files.writable(),
            "file call boundary");
    require(!checksum || count_words, "CRC sequential selection");
    file_wc = count_words;
    file_closed = false;
    file_call_count = file_service_used = 0;
    input.scrub();
    const auto begin_effect = file_service_transition(0);
    require(begin_effect == 1 || begin_effect == 2, "file service begin effect");
    const bool reused = begin_effect == 2;
    command_owned = true;
    mailbox.emplace(registry);
    require(create(0) == 0 && (reused ? domains[1].handle.has_value() : create(1) == 1) &&
                mailbox->bind(*domains[0].handle, *domains[1].handle) &&
                command_files.bind_read_retained(registry, *mailbox, *domains[0].handle, *domains[1].handle),
            "file call participants");
    const auto endpoint = mailbox->endpoint(*domains[1].handle);
    require(endpoint && command_note.bind(command_files.projection(), *endpoint), "file call frozen projection");
    Serial::text(checksum  ? std::string_view{"AURORA_CRC_BEGIN: generation="}
                 : file_wc ? std::string_view{"AURORA_WC_BEGIN: generation="}
                           : std::string_view{"AURORA_FILE_CALL_BEGIN: generation="});
    Serial::number(endpoint->generation());
    Serial::text("\r\n");
    const auto service_identity = registry.incarnation(*domains[1].handle);
    const auto caller_identity = registry.incarnation(*domains[0].handle);
    require(service_identity && caller_identity && frames.used() == 8, "file service diagnostic identities");
    const auto service_root = domains[1].tables->root();
    Serial::text("AURORA_FILE_SERVICE_BEGIN: service=");
    Serial::number(*service_identity);
    Serial::text(" caller=");
    Serial::number(*caller_identity);
    Serial::text(" generation=");
    Serial::number(endpoint->generation());
    Serial::text(" root=");
    Serial::number(service_root);
    Serial::text(" used=8 reused=");
    Serial::number(reused ? 1 : 0);
    Serial::text("\r\n");
    U64 result = 0;
    if (file_wc) {
        call_execute(0, checksum ? 48 : 32, 0, 0);
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
            call_execute(1, 11, request->first(), request->second());
            require(timer_epoch > epoch && call_wait.ticks == ticks && call_wait.remaining == remaining,
                    "wc isolated cumulative allowance");
            if (timer_exhausted || program.event() != ProgramEvent::returned) {
                file_service_poison();
                file_closed = true;
                require(mailbox->cancel(ipc::Phase::inactive), "wc partial cancellation");
            } else
                require(mailbox->state() == ipc::State::replied && !mailbox->cancel(ipc::Phase::inactive),
                        "wc durable reply");
            require(!call_resume(previous), "wc stale wake preserves readiness");
            require(call_resume(ticket) && !call_resume(ticket), "wc exactly once resume");
            require(timer_epoch == epoch && timer_ticks >= ticks && timer_initial == timer_ticks + timer_remaining,
                    "wc original caller allowance");
            previous = ticket;
        }
        if (!timer_exhausted && program.event() == ProgramEvent::returned)
            result = program.value();
        require(
            result == 0 || result == 3 ||
                ((result & 255) == 1 && (checksum ? (result >> 40) == 0
                                                  : (result >> 32) == 0 && ((result >> 8) & 255) <= 49 &&
                                                        ((result >> 16) & 255) <= 49 && ((result >> 24) & 255) <= 49)),
            "wc bounded copied counts");
        Serial::text(checksum ? std::string_view{"AURORA_CRC_TOTAL: calls="}
                              : std::string_view{"AURORA_WC_TOTAL: calls="});
        Serial::number(file_call_count);
        Serial::text(" caller=");
        Serial::number(timer_ticks);
        Serial::text(" service=");
        Serial::number(file_service_used);
        Serial::text("\r\n");
    } else {
        call_execute(0, 16, 0, 0);
        require(call_wait.context && call_wait.authority && call_wait.ticket && call_wait.ticks > 0,
                "file caller live suspension");
        const auto ticket = call_wait.ticket, epoch = call_wait.authority->epoch();
        const auto ticks = call_wait.ticks, remaining = call_wait.remaining;
        const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *endpoint, ticket);
        require(request && request->first() == 0 && request->second() == 0, "file copied offset");
        call_execute(1, 11, request->first(), request->second());
        require(timer_epoch > epoch && call_wait.ticks == ticks && call_wait.remaining == remaining,
                "file isolated service budget");
        if (timer_exhausted || program.event() != ProgramEvent::returned) {
            file_service_poison();
            require(mailbox->cancel(ipc::Phase::inactive), "file service cancellation");
        } else {
            require(mailbox->state() == ipc::State::replied && !mailbox->cancel(ipc::Phase::inactive),
                    "file durable service reply");
        }
        require(call_resume(ticket), "file exactly once resume");
        require(timer_epoch == epoch && timer_ticks >= ticks && timer_initial == timer_ticks + timer_remaining,
                "file original caller budget");
        if (!timer_exhausted && program.event() == ProgramEvent::returned) {
            require(program.value() >= 40, "file caller result envelope");
            result = program.value() - 40;
            require(result == 0 || program::Files::read_reply_valid(result), "file copied caller result");
        }
    }
    if (result == 0 || timer_exhausted || program.event() != ProgramEvent::returned)
        file_service_poison();
    const auto finish_effect = file_service_transition(1);
    const bool retained = finish_effect == 3;
    require(retained || finish_effect == 4, "file service finish effect");
    if (!retained)
        result = 0; // A later caller return cannot publish a poisoned command.
    require(mailbox->revoke(ipc::Phase::inactive) && retire(0), "file call caller and grant retirement");
    if (retained) {
        file_service_scrub();
        require(command_files.release_read_retained(registry, *mailbox), "file retained read release");
    } else
        require(retire(1) && frames.used() == 0 && command_files.release_read(registry, *mailbox),
                "file call authenticated retirement");
    require(!call_wait.context && !call_wait.ticket && !command_note.bound(), "file call scrubbed");
    mailbox.reset();
    selected_client = 2;
    command_owned = false;
    require(ProgramInputPlatform::quiet(), "file call quiescent result");
    Serial::text("AURORA_FILE_SERVICE_END: service=");
    Serial::number(*service_identity);
    Serial::text(" caller=");
    Serial::number(*caller_identity);
    Serial::text(" generation=");
    Serial::number(endpoint->generation());
    Serial::text(" root=");
    Serial::number(service_root);
    Serial::text(" retained=");
    Serial::number(retained ? 1 : 0);
    Serial::text(" used=");
    Serial::number(frames.used());
    Serial::text(" scrubbed=1\r\n");
    Serial::text(checksum  ? std::string_view{"AURORA_CRC_END: result="}
                 : file_wc ? std::string_view{"AURORA_WC_END: result="}
                           : std::string_view{"AURORA_FILE_CALL_END: result="});
    Serial::number(result);
    Serial::text(" used=");
    Serial::number(frames.used());
    Serial::text("\r\n");
    program::Response response{program::Response::Kind::stopped};
    if (file_wc && result != 0) {
        response = program::Response{result == 3 ? program::Response::Kind::file_missing
                                                 : program::Response::Kind::file_reply};
        if (result != 3) {
            std::array<std::uint8_t, 8> text{};
            unsigned size = 0;
            if (checksum) {
                constexpr std::string_view digits{"0123456789abcdef"};
                for (unsigned i = 0; i < 8; ++i)
                    text[size++] = static_cast<std::uint8_t>(digits[(result >> (36 - 4 * i)) & 15]);
            } else
                for (unsigned shift : {8U, 16U, 24U}) {
                    const auto count = (result >> shift) & 255;
                    if (count >= 10)
                        text[size++] = static_cast<std::uint8_t>('0' + count / 10);
                    text[size++] = static_cast<std::uint8_t>('0' + count % 10);
                    if (shift != 24)
                        text[size++] = ' ';
                }
            require(response.payload(std::span<const std::uint8_t>{text.data(), size}), "wc counts presentation");
        }
    } else if (!file_wc && result != 0) {
        response = program::Response{result == 3 ? program::Response::Kind::file_missing
                                                 : program::Response::Kind::file_reply};
        if (result == 2) {
            constexpr std::array<std::uint8_t, 3> text{'E', 'O', 'F'};
            require(response.payload(text), "file EOF presentation");
        } else if ((result & 255) == 1) {
            const std::array<std::uint8_t, 7> text{
                'b', 'y', 't', 'e', '>', ' ', static_cast<std::uint8_t>(result >> 8)};
            require(response.payload(text), "file byte presentation");
        } else
            require(result == 3, "file command supported result");
    }
    file_wc = file_closed = false;
    file_call_count = file_service_used = 0;
    return program_write_response(response);
}
