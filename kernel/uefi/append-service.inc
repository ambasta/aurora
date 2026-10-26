// Private append producer continuation. This retains execution, not a namespace
// or publication authority. The dormant identity authenticates the old frame;
// only the next delivered Mailbox transaction authorizes a new activation.
[[nodiscard]] auto append_backings_valid() -> bool {
    if (!append_operation || append_operation != command_append.run())
        return false;
    for (unsigned role = 0; role < 2; ++role) {
        if (!domains[role].handle || !domains[role].contract || !verify(domains[role]))
            return false;
        for (unsigned page = 0; page < 4; ++page)
            if (!domains[role].stacks[page] ||
                frames.address(*domains[role].stacks[page]) != append_backing[role * 4 + page])
                return false;
    }
    return true;
}
[[nodiscard]] auto append_service_trap(U64 frame) -> U64 {
#ifdef AURORA_PROGRAM_FIXTURE
    if (fixture == Fixture::program_transaction)
        ++launch[4];
    if (fixture == Fixture::program_append_service_site)
        ++reinterpret_cast<U64 *>(frame)[17];
    if (fixture == Fixture::program_append_service_backing)
        append_backing[4] += L::page_size;
#endif
    require(append_call_authority() && append_backings_valid() && active == 1 && irq_off() && run_authority &&
                timer_armed && selected_role == SelectedRunAuthority::Role::service &&
                selected_phase == ipc::Phase::service && launch[0] == 17 && transaction != 0 &&
                transaction == call_wait.ticket && call_wait.context && call_wait.service &&
                registry.index(*call_wait.service) == 1 && mailbox->state() == ipc::State::delivered &&
                launch[4] == transaction && launch[5] == domains[0].call_count - 1 && !append_service_wait.context &&
                !append_service_wait.authority && !append_service_wait.ticket && timer_remaining &&
                timer_ticks < timer_initial && timer_initial == 128 && timer_initial == timer_remaining + timer_ticks &&
                timer_initial == run_authority->budget() && timer_owner && registry.active(*timer_owner) &&
                timer_owner_epoch == timer_epoch && current_run_identity(),
            "append service authority");
    const auto context = capture_exchange(1, frame, images::bounds_serve_pc);
    const auto endpoint = mailbox->endpoint(*domains[1].handle);
    require(context && endpoint && context->words()[8] == endpoint->slot() &&
                context->words()[9] == endpoint->generation() && launch[2] == endpoint->slot() &&
                launch[3] == endpoint->generation() && timer_stop(),
            "append Serve site");
#ifdef AURORA_PROGRAM_FIXTURE
    if (!console_probe_used && fixture == Fixture::program_append_terminal_budget && context->words()[11] == 2) {
        console_probe_used = true;
        while (timer_remaining > 1)
            require(call_boundary_debit(), "append terminal conservative debit");
    }
#endif
    if (!call_boundary_debit()) {
        domains[0].call_closed = true;
        park_run(*domains[1].handle);
        return 1;
    }
    auto &saved = append_service_wait;
    save_parked_run(saved, *context);
    saved.authority.emplace(*run_authority);
    saved.service = *domains[1].handle;
    saved.endpoint = *endpoint;
    saved.ticket = transaction;
    saved.launch = launch;
    require(append_call_reply(context->words()[11]) &&
                mailbox->reply(*domains[1].handle, ipc::Phase::service, *endpoint, transaction, context->words()[11]),
            "append Serve reply");
#ifdef AURORA_PROGRAM_FIXTURE
    if (fixture == Fixture::program_pending)
        force_timer_pending();
#endif
    park_run(*domains[1].handle);
    Serial::text("AURORA_APPEND_PARK: ticket=");
    Serial::number(saved.ticket);
    Serial::text(" terminal=");
    Serial::number(command_append.terminal() ? 1 : 0);
    Serial::text("\r\n");
    return 1;
}
[[nodiscard]] auto append_service_resume(U64 ticket, U64 offset) -> bool {
    auto &saved = append_service_wait;
    auto &domain = domains[1];
    if (!program_boundary() || !append_call_authority() || !append_backings_valid() || command_append.terminal() ||
        timer_epoch_watermark == UINT64_MAX || !saved.context || !saved.authority || !saved.service || !saved.ticket ||
        ticket <= saved.ticket || ticket != call_wait.ticket || !call_wait.context || !call_wait.service ||
        registry.index(*call_wait.service) != 1 || registry.index(*saved.service) != 1 ||
        mailbox->state() != ipc::State::delivered || offset != domains[0].call_count - 1 ||
        offset != command_append.length() || offset == 0 || offset > 49 ||
        !saved.authority->ready_owner(registry, *domain.handle, saved.authority->epoch()) ||
        saved.authority->role() != SelectedRunAuthority::Role::service ||
        saved.authority->phase() != ipc::Phase::service || saved.authority->client() != 0 ||
        saved.authority->transaction() != saved.ticket || saved.authority->source_phase() != 17 ||
        saved.authority->root() != domain.tables->root() || saved.authority->owned_arena() != arena ||
        !user::same_contract(saved.authority->contract(), *domain.contract) ||
        !saved.context->call_frame(*domain.contract, images::bounds_serve_pc) ||
        !saved.context->call_frame(saved.authority->contract(), images::bounds_serve_pc) ||
        saved.authority->budget() != 128 || saved.ticks != domains[0].call_service_used || saved.ticks >= 128 ||
        saved.remaining != 128 - saved.ticks || saved.launch[0] != 17 || saved.launch[4] != saved.ticket ||
        saved.launch[5] + 1 != offset)
        return false;
    const auto endpoint = mailbox->endpoint(*domain.handle);
    if (!endpoint || endpoint->slot() != saved.endpoint.slot() ||
        endpoint->generation() != saved.endpoint.generation() || saved.launch[2] != endpoint->slot() ||
        saved.launch[3] != endpoint->generation())
        return false;
    launch = saved.launch;
    launch[4] = ticket;
    launch[5] = offset;
    selected_client = 0;
    selected_role = SelectedRunAuthority::Role::service;
    selected_phase = ipc::Phase::service;
    transaction = ticket;
    const auto frame = restore_parked_run(saved);
    auto *words = reinterpret_cast<U64 *>(frame);
    words[14] = 0;
    words[11] = offset;
    saved.clear(); // The frame is consumed before a new transaction can execute.
    activate_parked_run(1);
    timer_begin(1); // Fresh watermark epoch, with the producer's cumulative quota.
    Serial::text("AURORA_APPEND_RESUME: ticket=");
    Serial::number(ticket);
    Serial::text("\r\n");
    require(current_run_identity() && resume(frame) == 1, "append service continuation");
    timer_finish(); // Drain the outgoing owner before any peer or retirement.
    domains[0].call_service_used = timer_ticks;
    launch = {};
    selected_phase = ipc::Phase::inactive;
    transaction = 0;
    require(program_boundary(), "append service unwind");
    return true;
}

#ifdef AURORA_PROGRAM_FIXTURE
// These controls call the real wake admission while the real next transaction
// is delivered. They do not manufacture a successful reply or run a peer.
auto append_service_wake_controls(U64 ticket, U64 offset) -> void {
    auto &saved = append_service_wait;
    require(!append_service_resume(0, offset) && !append_service_resume(saved.ticket, offset) &&
                !append_service_resume(ticket + 1, offset) && !append_service_resume(ticket, offset + 1),
            "append service ticket/order rejection");
    ++append_operation;
    require(!append_service_resume(ticket, offset), "append service operation rejection");
    --append_operation;
    ++saved.launch[3];
    require(!append_service_resume(ticket, offset), "append service generation rejection");
    --saved.launch[3];
    ++saved.ticket;
    require(!append_service_resume(ticket, offset), "append dormant transaction rejection");
    --saved.ticket;
    saved.service = *domains[0].handle;
    require(!append_service_resume(ticket, offset), "append foreign producer rejection");
    saved.service = *domains[1].handle;
    ++append_backing[4];
    require(!append_service_resume(ticket, offset), "append original backing rejection");
    --append_backing[4];
    ++saved.remaining;
    require(!append_service_resume(ticket, offset), "append quota rejection");
    --saved.remaining;
    const auto &contract = saved.authority->contract();
    domains[1].contract.emplace(contract.layout(),
                                contract.entry(),
                                contract.size() + 1,
                                contract.return_pc(),
                                contract.bounds_pc(),
                                contract.overflow_pc(),
                                contract.division_zero_pc(),
                                contract.shift_count_pc());
    require(!append_service_resume(ticket, offset), "append original contract rejection");
    domains[1].contract.emplace(contract);
    require(mailbox->state() == ipc::State::delivered && saved.context && saved.ticket != ticket,
            "append rejected wake preserves authority");
}
#endif
