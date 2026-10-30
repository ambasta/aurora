// Selection has already returned and unwound its copied records. Each command
// owns a fresh caller/read grant; a healthy scrubbed service incarnation is reused.
[[nodiscard]] [[gnu::noinline]] auto program_file_call(program::Submission &input, bool count_words, bool checksum)
    -> bool {
    static_cast<void>(caller_continuation.ordinary_checked());
    require(ProgramInputPlatform::quiet() && command_files.selected() && !command_files.writable(),
            "file call boundary");
    require(!checksum || count_words, "CRC sequential selection");
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
    auto &caller = domains[0];
    caller.call_limit = count_words ? 50 : 1;
    const auto endpoint = mailbox->endpoint(*domains[1].handle);
    require(endpoint && command_note.bind(command_files.projection(), *endpoint), "file call frozen projection");
    Serial::text(checksum      ? std::string_view{"AURORA_CRC_BEGIN: generation="}
                 : count_words ? std::string_view{"AURORA_WC_BEGIN: generation="}
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
    call_execute(0, checksum ? 48 : count_words ? 32 : 16, 0, 0);
    require(count_words || caller_continuation.ordinary()->context, "file caller live suspension");
    U64 previous = 0;
    while (caller_continuation.ordinary()->context) {
        U64 ticket, epoch;
        unsigned ticks, remaining;
        {
            const auto &saved = caller_continuation.ordinary_checked();
            require(saved.authority && saved.ticket && caller.call_count > 0 && caller.call_count <= caller.call_limit,
                    "file bounded live suspension");
            ticket = saved.ticket;
            epoch = saved.authority->epoch();
            ticks = saved.ticks;
            remaining = saved.remaining;
        }
        require(!call_resume(previous) && !call_resume(ticket), "file stale and unready wake");
        const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *endpoint, ticket);
        require(request && request->first() == caller.call_count - 1 && request->second() == 0,
                "file sequential copied offset");
        call_execute(1, 11, request->first(), request->second());
        {
            const auto &saved = caller_continuation.ordinary_checked();
            require(timer_epoch > epoch && saved.ticks == ticks && saved.remaining == remaining,
                    "file isolated cumulative allowance");
        }
        if (timer_exhausted || program.event() != ProgramEvent::returned) {
            file_service_poison();
            caller.call_closed = true;
            require(mailbox->cancel(ipc::Phase::inactive), "file partial cancellation");
        } else
            require(mailbox->state() == ipc::State::replied && !mailbox->cancel(ipc::Phase::inactive),
                    "file durable reply");
        require(!call_resume(previous), "file stale wake preserves readiness");
        require(call_resume(ticket) && !call_resume(ticket), "file exactly once resume");
        require(timer_epoch == epoch && timer_ticks >= ticks && timer_initial == timer_ticks + timer_remaining,
                "file original caller allowance");
        previous = ticket;
    }
    if (count_words) {
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
        Serial::number(caller.call_count);
        Serial::text(" caller=");
        Serial::number(timer_ticks);
        Serial::text(" service=");
        Serial::number(caller.call_service_used);
        Serial::text("\r\n");
    } else {
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
    require(caller_continuation.ordinary_empty() && !command_note.bound(), "file call scrubbed");
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
    Serial::text(checksum      ? std::string_view{"AURORA_CRC_END: result="}
                 : count_words ? std::string_view{"AURORA_WC_END: result="}
                               : std::string_view{"AURORA_FILE_CALL_END: result="});
    Serial::number(result);
    Serial::text(" used=");
    Serial::number(frames.used());
    Serial::text("\r\n");
    program::Response response{program::Response::Kind::stopped};
    if (count_words && result != 0) {
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
    } else if (!count_words && result != 0) {
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
    return program_write_response(response);
}
