// Included beside the existing IPC launcher, under its same private authority.
constexpr U64 snapshot_done = ~U64{0};
constexpr U64 snapshot_cancelled = snapshot_done - 1;

auto snapshot_bind() -> void {
    require(mailbox->bind(*domains[0].handle, *domains[1].handle), "snapshot participant binding");
    const auto client = mailbox->endpoint(*domains[0].handle);
    const auto service = mailbox->endpoint(*domains[1].handle);
    require(client && service && client->generation() == service->generation() && snapshot_slot.bind(*service),
            "snapshot publication generation");
}

auto snapshot_submit(U64 offset, U64 source_phase = 0, std::optional<ipc::Endpoint> endpoint = std::nullopt) -> void {
    ipc_execute(0, ipc::Phase::request, source_phase, 0, offset, ProgramEvent::returned, std::nullopt, endpoint);
}

auto snapshot_deliver(bool fault = false) -> void {
    const auto endpoint = mailbox->endpoint(*domains[1].handle);
    require(endpoint.has_value(), "snapshot service grant");
    const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *endpoint, transaction);
    require(request && mailbox->scrubbed(), "snapshot authenticated request copy");
    ipc_record("DELIVER", request->first(), request->second());
    ipc_execute(1,
                ipc::Phase::service,
                fault ? 4 : 1,
                request->first(),
                request->second(),
                fault ? ProgramEvent::bounds : ProgramEvent::returned,
                std::nullopt);
}

auto snapshot_complete(U64 offset, bool cancelled = false, U64 phase = 2) -> U64 {
    const auto endpoint = mailbox->endpoint(*domains[0].handle);
    require(endpoint.has_value(), "snapshot completion grant");
    const auto completion = mailbox->consume(*domains[0].handle, ipc::Phase::completion, *endpoint, transaction);
    require(completion && completion->outcome() == (cancelled ? ipc::Outcome::cancelled : ipc::Outcome::replied) &&
                (!cancelled || completion->value() == 0) && mailbox->scrubbed(),
            "snapshot terminal copy/scrub");
    ipc_record("CONSUME", completion->value(), cancelled ? 1 : 0);
    ipc_execute(0,
                ipc::Phase::completion,
                cancelled ? 3 : phase,
                completion->value(),
                offset,
                ProgramEvent::returned,
                std::nullopt);
    return program.value();
}

auto snapshot_round_trip(U64 offset, bool unknown = false) -> U64 {
    snapshot_submit(offset, unknown ? 6 : 0);
    snapshot_deliver();
    require(!mailbox->cancel(ipc::Phase::inactive), "snapshot reply first terminal wins");
    const auto next = snapshot_complete(offset, false, unknown ? 7 : 2);
    require(mailbox->recycle(ipc::Phase::inactive) && mailbox->scrubbed(), "snapshot record recycle");
    return next;
}

[[maybe_unused]] auto snapshot_restart(memory::PhysicalPages &producer_pool) -> void {
    require(root() == kernel_root && active == L::domain_count, "snapshot restart root");
    const auto prior = *domains[1].handle;
    const auto endpoint = *mailbox->endpoint(*domains[1].handle);
    const auto frame = *frames.address(*domains[1].stacks[0]);
    snapshot_slot.clear();
    require(mailbox->revoke(ipc::Phase::inactive) && retire(1) && !registry.index(prior),
            "snapshot service retirement");
    require(prepare_snapshot(arena, producer_pool, snapshot_slot, SnapshotProducerCase::normal) ==
                    ipc::SnapshotPublication::ready &&
                producer_pool.used() == 0,
            "snapshot fresh closed producer");
    require(create(1) == 1 && *frames.address(*domains[1].stacks[0]) == frame, "snapshot service incarnation");
    for (const auto &lease : domains[1].stacks)
        require(zero(*frames.address(*lease)), "snapshot retired stack scrub");
    snapshot_bind();
    require(!snapshot_slot.matches(endpoint), "snapshot old generation revoked");
    Serial::text("AURORA_UEFI_SNAPSHOT_RESTART: fresh=1 scrubbed=1\r\n");
}

auto run_snapshot(memory::PhysicalPages &producer_pool) -> void {
    auto scenario = SnapshotProducerCase::normal;
#ifdef AURORA_SNAPSHOT_FIXTURE
    select_fixture(Fixture::snapshot_fault, Fixture::snapshot_reply_reserved);
    if (fixture == Fixture::snapshot_producer_selector)
        scenario = SnapshotProducerCase::invalid_selector;
    else if (fixture == Fixture::snapshot_producer_quota)
        scenario = SnapshotProducerCase::quota;
    else if (fixture == Fixture::snapshot_producer_pages)
        scenario = SnapshotProducerCase::pages;
#endif
    const auto publication = prepare_snapshot(arena, producer_pool, snapshot_slot, scenario);
    require(publication != ipc::SnapshotPublication::malformed, "snapshot producer publication");
    if (publication == ipc::SnapshotPublication::unavailable) {
        require(!snapshot_slot.ready() && !snapshot_slot.bound() && producer_pool.used() == 0 && frames.used() == 0,
                "snapshot failed producer unpublished");
        Serial::text("AURORA_UEFI_SNAPSHOT_UNAVAILABLE: unpublished=1 used=0\r\n");
        return;
    }
    require(producer_pool.used() == 0 && snapshot_slot.ready(), "snapshot producer closed before launch");
    mailbox.emplace(registry);
    require(create(0) == 0 && create(1) == 1, "snapshot owned participants");
    snapshot_bind();
#ifdef AURORA_SNAPSHOT_FIXTURE
    if (fixture == Fixture::snapshot_stale) {
        const auto stale = mailbox->endpoint(*domains[0].handle);
        snapshot_slot.clear();
        require(mailbox->revoke(ipc::Phase::inactive) &&
                    prepare_snapshot(arena, producer_pool, snapshot_slot, SnapshotProducerCase::normal) ==
                        ipc::SnapshotPublication::ready,
                "snapshot stale preparation");
        snapshot_bind();
        snapshot_submit(0, 0, stale);
    }
    if (fixture == Fixture::snapshot_revoked) {
        const auto revoked = mailbox->endpoint(*domains[0].handle);
        snapshot_slot.clear();
        require(mailbox->revoke(ipc::Phase::inactive), "snapshot revoke before request");
        snapshot_submit(0, 0, revoked);
    }
    if (fixture == Fixture::snapshot_fault || fixture == Fixture::snapshot_cancel) {
        snapshot_submit(0);
        if (fixture == Fixture::snapshot_fault)
            snapshot_deliver(true);
        require(
            root() == kernel_root && active == L::domain_count && mailbox->cancel(ipc::Phase::inactive) &&
                !mailbox->cancel(ipc::Phase::inactive) &&
                !mailbox->reply(
                    *domains[1].handle, ipc::Phase::service, *mailbox->endpoint(*domains[1].handle), transaction, 1),
            "snapshot cancellation first terminal wins");
        require(snapshot_complete(0, true) == snapshot_cancelled, "snapshot compiled cancellation");
        snapshot_restart(producer_pool);
    }
#endif
    // Native retains only the copied continuation, never a persistent file cursor.
    U64 offset = 0;
    for (unsigned step = 0; step < 65; ++step) {
        const auto next = snapshot_round_trip(offset);
        if (next == snapshot_done) {
            require(step == 64 && offset == 64, "snapshot complete client sequence");
            break;
        }
        require(next <= 64 && step < 64, "snapshot compiled client continuation");
        offset = next;
    }
    for (const auto edge : {U64{65}, snapshot_done}) {
        require(snapshot_round_trip(edge) == snapshot_done, "snapshot compiled range consumer");
    }
    require(snapshot_round_trip(0, true) == snapshot_done, "snapshot compiled operation consumer");
    snapshot_slot.clear();
    require(mailbox->revoke(ipc::Phase::inactive) && retire(0) && retire(1) && frames.used() == 0 &&
                producer_pool.used() == 0 && mailbox->scrubbed() && !snapshot_slot.ready() && !snapshot_slot.bound(),
            "snapshot final reclamation");
    transaction = 0;
    launch = {};
    mailbox.reset();
    Serial::text("AURORA_UEFI_SNAPSHOT_OK: bytes=64 eof=1 range=2 operation=1 used=0 records=0\r\n");
}
