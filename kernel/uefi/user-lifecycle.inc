// Controlled client failures are disposed only after an authenticated user exit.
[[maybe_unused]] auto user_dispose_and_rebind(bool replied) -> void {
    require(root() == kernel_root && active == L::domain_count && irq_off() && !timer_armed && !run_authority &&
                saved_rsp == 0 && timer_quiet(0x100, false) && timer_quiet(0x200, false),
            "user disposal quiescence");
    const auto offender = *domains[0].handle, peer = *domains[2].handle;
    const auto peer_endpoint = dispatcher->endpoint(1, peer), old_endpoint = dispatcher->endpoint(0, offender);
    const auto peer_transaction = dispatcher->transaction(1);
    const auto peer_state = dispatcher->state(1);
    require(peer_endpoint && old_endpoint && peer_transaction && peer_state == ipc::State::pending,
            "user peer recovery snapshot");
    const auto disposition = dispatcher->dispose_client(ipc::Phase::inactive, 0, offender, true);
    require(disposition &&
                (replied ? disposition->prior_state() == ipc::State::consumed
                         : disposition->prior_state() == ipc::State::idle) &&
                (replied ? disposition->completion() && disposition->completion()->outcome() == ipc::Outcome::replied &&
                               disposition->completion()->value() == 42 && disposition->transaction().has_value()
                         : !disposition->completion() && !disposition->transaction()),
            "user terminal disposition");
    Serial::text("AURORA_UEFI_USER_DISPOSE: client=0 disposition=");
    Serial::text(replied ? "replied" : "idle");
    Serial::text(" transaction=");
    Serial::number(disposition->transaction().value_or(0));
    Serial::text(" value=");
    Serial::number(disposition->completion() ? disposition->completion()->value() : 0);
    Serial::text("\r\n");
    require(!dispatcher->rebind_client(ipc::Phase::inactive, 0, offender), "user live incarnation rebound");
    const auto old_root = domains[0].tables->root(), old_frame = *frames.address(*domains[0].stacks[0]);
    require(root() != old_root && retire(0) && !registry.index(offender) && frames.used() == 8, "user root retirement");
    for (unsigned page = 0; page < L::table_pages; ++page)
        require(zero(old_root + page * 4096), "user old table authority retained");
    for (unsigned page = 0; page < 4; ++page)
        require(zero(old_frame + page * 4096), "user retired stack residue");
    require(root() == kernel_root, "user root changed during scrub");
    Serial::text("AURORA_UEFI_USER_REVOKE: root=");
    Serial::number(old_root);
    Serial::text(" kernel=");
    Serial::number(root());
    Serial::text(" tables=16 frames=4 used=8\r\n");
    require(create(0) == 0 && *frames.address(*domains[0].stacks[0]) == old_frame &&
                dispatcher->rebind_client(ipc::Phase::inactive, 0, *domains[0].handle),
            "user fresh incarnation binding");
    for (const auto &lease : domains[0].stacks)
        require(zero(*frames.address(*lease)), "user reused stack residue");
    const auto fresh = dispatcher->endpoint(0, *domains[0].handle), still_peer = dispatcher->endpoint(1, peer);
    require(fresh && fresh->generation() != old_endpoint->generation() && still_peer &&
                still_peer->generation() == peer_endpoint->generation() &&
                still_peer->slot() == peer_endpoint->slot() && dispatcher->transaction(1) == peer_transaction &&
                dispatcher->state(1) == peer_state,
            "user peer state changed");
    Serial::text("AURORA_UEFI_USER_REBIND: client=0 old=");
    Serial::number(old_endpoint->generation());
    Serial::text(" fresh=");
    Serial::number(fresh->generation());
    Serial::text(" peer=");
    Serial::number(still_peer->generation());
    Serial::text(" transaction=");
    Serial::number(*peer_transaction);
    Serial::text(" frame=");
    Serial::number(old_frame);
    Serial::text("\r\n");
#if defined(AURORA_USER_FIXTURE)
    if (fixture == Fixture::user_stale_grant) {
        stale_client_endpoint = old_endpoint;
    }
#endif
}
auto run_user_lifecycle() -> void {
#ifdef AURORA_USER_FIXTURE
    // The baseline runs the ordinary user-phases flow of the former user-phases image.
    if (fixture == Fixture::user_phases_baseline || fixture == Fixture::user_pending ||
        fixture == Fixture::user_context || fixture == Fixture::user_unknown) {
        run_dispatcher();
        Serial::text("AURORA_UEFI_USER_PHASES_OK\r\n");
        return;
    }
#endif
    dispatcher.emplace(registry);
    require(create(0) == 0 && create(1) == 1 && create(2) == 2 && frames.used() == 12, "user three owned domains");
    dispatch_bind();
    dispatch_request(1);
#ifdef AURORA_USER_FIXTURE
    const bool replied = fixture == Fixture::user_completion_budget || fixture == Fixture::user_completion_bounds ||
                         fixture == Fixture::user_completion_overflow || fixture == Fixture::user_retire_pending;
    if (replied) {
        dispatch_request(0);
        dispatch_service(0);
        const auto actor = *domains[0].handle;
        const auto endpoint = dispatcher->endpoint(0, actor);
        const auto ticket = dispatcher->transaction(0);
        require(endpoint && ticket, "user completion ticket");
        const auto completion = dispatcher->consume(actor, ipc::Phase::completion, *endpoint, *ticket);
        require(completion && completion->outcome() == ipc::Outcome::replied && completion->value() == 42,
                "user committed reply copy");
        dispatch_record("CONSUME", 0, *ticket, 42, 0);
        if (fixture == Fixture::user_completion_bounds || fixture == Fixture::user_retire_pending)
            dispatch_execute(0, 0, ipc::Phase::completion, 10, 42, 0, ProgramEvent::bounds, 0, *ticket);
        else if (fixture == Fixture::user_completion_overflow)
            dispatch_execute(0, 0, ipc::Phase::completion, 11, 42, 0, ProgramEvent::overflow, 0, *ticket);
        else
            dispatch_execute(0, 0, ipc::Phase::completion, 7, 42, 0, ProgramEvent::rejected, 0, *ticket);
    } else {
        if (fixture == Fixture::user_request_bounds)
            dispatch_execute(0, 0, ipc::Phase::request, 8, 0, 2, ProgramEvent::bounds, 0);
        else if (fixture == Fixture::user_request_overflow)
            dispatch_execute(0, 0, ipc::Phase::request, 9, 0, 2, ProgramEvent::overflow, 0);
        else
            dispatch_execute(0, 0, ipc::Phase::request, 6, 0, 2, ProgramEvent::rejected, 0);
    }
#else
    dispatch_execute(0, 0, ipc::Phase::request, 6, 0, 2, ProgramEvent::rejected, 0);
    constexpr bool replied = false;
#endif
#if defined(AURORA_USER_FIXTURE)
    if (fixture == Fixture::user_request_budget || fixture == Fixture::user_completion_budget ||
        fixture == Fixture::user_stale_grant)
        require(timer_exhausted && timer_ticks == 3 && timer_resumes == 2 && timer_compiled_hits > 0,
                "user compiled client budget");
#endif
    user_dispose_and_rebind(replied);
    dispatch_service(1);
    dispatch_complete(1, false);
    dispatch_request(0);
    dispatch_service(0);
    dispatch_complete(0, false);
    require(dispatcher->revoke(ipc::Phase::inactive) && dispatcher->scrubbed() && retire(0) && retire(1) && retire(2) &&
                frames.used() == 0 && root() == kernel_root && active == L::domain_count && !run_authority,
            "user final cleanup");
    require(timer_stop() && timer_drain() && !timer_armed, "user final timer quiescence");
    dispatcher.reset();
    selected_client = 2;
    transaction = 0;
    launch = {};
    Serial::text("AURORA_UEFI_DISPATCH_CLEANUP_OK: used=0 records=0\r\nAURORA_UEFI_DISPATCH_OK\r\n");
    Serial::text("AURORA_UEFI_USER_PHASES_OK\r\n");
}
