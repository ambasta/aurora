// Included inside the runtime adapter's private namespace; no separate authority.
auto ipc_record(std::string_view operation, U64 first, U64 second) -> void {
    Serial::text("AURORA_UEFI_IPC_");
    Serial::text(operation);
    Serial::text(": transaction=");
    Serial::number(transaction);
    Serial::text(" first=");
    Serial::number(first);
    Serial::text(" second=");
    Serial::number(second);
    Serial::text("\r\n");
}
#ifdef AURORA_BUDGET_FIXTURE
// This family contains one exact named forged-interrupt instruction. Do not
// clone its assembler label into multiple inlined service call sites.
[[gnu::noinline]]
#endif
auto ipc_execute(unsigned index,
                 ipc::Phase phase,
                 U64 source_phase,
                 U64 first,
                 U64 second,
                 ProgramEvent expected_event,
#ifdef AURORA_UEFI_SNAPSHOT
                 std::optional<U64> expected_value,
#else
                 U64 expected_value,
#endif
                 std::optional<ipc::Endpoint> override_endpoint = std::nullopt) -> void {
    require(index < 2 && root() == kernel_root && active == L::domain_count, "IPC launch boundary");
    auto &domain = domains[index];
    require(domain.handle && verify(domain), "IPC launch domain");
    const auto endpoint = override_endpoint ? override_endpoint : mailbox->endpoint(*domain.handle);
    require(endpoint.has_value(), "IPC launch grant");
    launch = {source_phase,
              first,
              endpoint->slot(),
              endpoint->generation(),
              phase == ipc::Phase::request ? 0 : transaction,
              second};
    selected_phase = phase;
#ifdef AURORA_UEFI_SERVICE_BUDGET
    launch[6] = phase == ipc::Phase::service ? 0x202 : 2;
#endif
#ifdef AURORA_IPC_PROBES
    launch[7] = ipc_probe(index, source_phase);
#endif
    for (const auto &lease : domain.stacks) {
        const auto address = frames.address(*lease);
        require(address.has_value(), "IPC stack lease");
        fill(*address, 0);
    }
#ifdef AURORA_UEFI_SNAPSHOT
    for (const auto &lease : domain.stacks)
        require(zero(*frames.address(*lease)), "snapshot complete launch scrub");
    if (phase == ipc::Phase::service) {
        require(index == 1 && mailbox->state() == ipc::State::delivered && snapshot_slot.matches(*endpoint),
                "snapshot authenticated delivery binding");
        const auto physical = frames.address(*domain.stacks.back());
        const auto virtual_page = domain.contract->layout().user_stack_top() - L::page_size;
        require(physical && (domain.tables->entry(virtual_page) & ~0x60ULL) == (*physical | 7 | RuntimeTables::nx) &&
                    (PageTables{kernel_root, static_cast<std::size_t>(handoff->get(96))}.entry(*physical) & ~0x60ULL) ==
                        (*physical | 3 | RuntimeTables::nx),
                "snapshot exact retained stack mapping");
        auto *record = reinterpret_cast<std::byte *>(*physical + L::page_size - ipc::SnapshotSlot::stack_reservation);
        require(snapshot_slot.stage(ipc::SnapshotSlot::Record{record, ipc::SnapshotSlot::record_bytes},
                                    *endpoint,
                                    source_phase,
                                    ipc::Request{first, second}),
                "snapshot bounded stack record");
    }
#endif
    require(program.begin(*domain.contract) && registry.activate(*domain.handle), "IPC launch state");
    active = index;
    Serial::text("AURORA_UEFI_IPC_ENTER: slot=");
    Serial::number(index);
    Serial::text(" phase=");
    Serial::number(source_phase);
    Serial::text(" root=");
    Serial::number(domain.tables->root());
    Serial::text(" grant=");
    Serial::number(endpoint->generation());
    Serial::text(" transaction=");
    Serial::number(launch[4]);
    Serial::text("\r\n");
    const auto selected = domain.tables->root();
    asm volatile("mov %0,%%cr3" ::"r"(selected) : "memory");
#if defined(AURORA_IPC_FIXTURE)
    if (fixture == Fixture::ipc_kernel_trap) {
        asm volatile("jmp *%0" ::"r"(domain.contract->bounds_pc()) : "memory");
    }
#endif
#ifdef AURORA_UEFI_SERVICE_BUDGET
    if (phase == ipc::Phase::service) {
        timer_begin(index);
#if defined(AURORA_BUDGET_FIXTURE)
        if (fixture == Fixture::budget_epoch) {
            --timer_owner_epoch;
        }
#endif
#if defined(AURORA_BUDGET_FIXTURE)
        if (fixture == Fixture::budget_forged) {
            require(timer_stop() && timer_quiet(0x100, false), "forged probe quiet");
            asm volatile("int $64\n.global uefi_service_forged_pc\nuefi_service_forged_pc:" ::: "memory");
        }
#endif
    }
#endif
    require(enter(domain.contract->entry(), domain.contract->layout().user_stack_top(), launch.data()) == 1,
            "IPC continuation");
#ifdef AURORA_UEFI_SERVICE_BUDGET
    if (phase == ipc::Phase::service)
        timer_finish();
#endif
    const auto current_stack = stack();
    require(root() == kernel_root && active == L::domain_count && saved_rsp == 0 && !program.running() &&
                current_stack >= arena + Handoff::stack_bottom && current_stack < arena + Handoff::stack_top,
            "IPC restored authority");
#ifdef AURORA_UEFI_SNAPSHOT
    require(program.event() == expected_event &&
                (expected_event != ProgramEvent::returned || !expected_value || program.value() == *expected_value),
            "IPC compiled result");
#else
    require(program.event() == expected_event &&
                (expected_event != ProgramEvent::returned || program.value() == expected_value),
            "IPC compiled result");
#endif
    Serial::text("AURORA_UEFI_IPC_RESTORE: slot=");
    Serial::number(index);
    Serial::text(" root=");
    Serial::number(root());
    Serial::text(" stack=");
    Serial::number(current_stack);
    Serial::text(" event=");
    Serial::text(expected_event == ProgramEvent::returned ? "returned"
                 : expected_event == ProgramEvent::bounds ? "bounds"
                                                          : "budget");
    Serial::text(" value=");
    Serial::number(program.value());
    Serial::text("\r\n");
    launch = {};
    selected_phase = ipc::Phase::inactive;
}
#ifndef AURORA_UEFI_SNAPSHOT
auto ipc_complete(bool cancelled) -> void {
    const auto endpoint = mailbox->endpoint(*domains[0].handle);
    require(endpoint.has_value(), "IPC completion grant");
    const auto completion = mailbox->consume(*domains[0].handle, ipc::Phase::completion, *endpoint, transaction);
    require(completion && completion->outcome() == (cancelled ? ipc::Outcome::cancelled : ipc::Outcome::replied) &&
                completion->value() == (cancelled ? 0 : 42) && mailbox->scrubbed(),
            "IPC completion copy/scrub");
    ipc_record("CONSUME", completion->value(), cancelled ? 1 : 0);
    ipc_execute(0,
                ipc::Phase::completion,
                cancelled ? 3 : 2,
                completion->value(),
                0,
                ProgramEvent::returned,
                cancelled ? 7 : 42);
}
auto ipc_deliver(bool fault) -> void {
    const auto endpoint = mailbox->endpoint(*domains[1].handle);
    require(endpoint.has_value(), "IPC delivery grant");
    const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *endpoint, transaction);
    require(request && request->first() == 40 && request->second() == 2 && mailbox->scrubbed(), "IPC request copy");
    ipc_record("DELIVER", request->first(), request->second());
#ifdef AURORA_UEFI_SERVICE_BUDGET
    const bool exhaust = fault;
#ifdef AURORA_BUDGET_FIXTURE
    const bool fault_case = fixture == Fixture::budget_fault;
    const auto source_phase = exhaust ? (fault_case ? 4 : 5) : 1;
    const auto wanted = exhaust ? (fault_case ? ProgramEvent::bounds : ProgramEvent::rejected) : ProgramEvent::returned;
#else
    const auto source_phase = exhaust ? 5 : 1;
    const auto wanted = exhaust ? ProgramEvent::rejected : ProgramEvent::returned;
#endif
    ipc_execute(1, ipc::Phase::service, source_phase, request->first(), request->second(), wanted, exhaust ? 0 : 42);
#ifdef AURORA_BUDGET_FIXTURE
    if (fault_case)
        require(!timer_exhausted && (exhaust || timer_compiled_hits > 0), "service fault outcome");
    else
        require(timer_exhausted == exhaust && timer_compiled_hits > 0 &&
                    (!exhaust || (timer_ticks == 3 && timer_resumes == 2)),
                "service budget outcome");
#else
    require(timer_exhausted == exhaust && timer_compiled_hits > 0 &&
                (!exhaust || (timer_ticks == 3 && timer_resumes == 2)),
            "service budget outcome");
#endif
#if defined(AURORA_BUDGET_FIXTURE)
    if (fixture == Fixture::budget_context && !exhaust)
        require(timer_context_hits > 0, "timer register probe delivery");
#endif
#else
    ipc_execute(1,
                ipc::Phase::service,
                fault ? 4 : 1,
                request->first(),
                request->second(),
                fault ? ProgramEvent::bounds : ProgramEvent::returned,
                fault ? 0 : 42);
#endif
}
[[maybe_unused]] auto ipc_cancel() -> void {
    require(root() == kernel_root && active == L::domain_count && mailbox->cancel(ipc::Phase::inactive) &&
                mailbox->scrubbed(),
            "IPC cancel boundary");
    const auto endpoint = mailbox->endpoint(*domains[1].handle);
    require(endpoint.has_value(), "IPC cancelled grant");
    require(!mailbox->reply(*domains[1].handle, ipc::Phase::service, *endpoint, transaction, 99) &&
                !mailbox->cancel(ipc::Phase::inactive),
            "IPC late reply/cancel");
    ipc_record("CANCEL", 0, 0);
    ipc_complete(true);
}
auto run_ipc() -> void {
#ifdef AURORA_IPC_FIXTURE
    select_fixture(Fixture::ipc_baseline, Fixture::ipc_unknown);
#endif
#ifdef AURORA_IPC_FIXTURE
    if (fixture == Fixture::ipc_exhausted)
        mailbox.emplace(registry, 1);
    else
        mailbox.emplace(registry);
#else
    mailbox.emplace(registry);
#endif
    require(create(0) == 0 && create(1) == 1 && mailbox->bind(*domains[0].handle, *domains[1].handle),
            "IPC participants");
    [[maybe_unused]] const auto first_service = *domains[1].handle;
    const auto old_endpoint = mailbox->endpoint(*domains[0].handle);
    require(old_endpoint.has_value(), "IPC initial endpoint");
#ifdef AURORA_IPC_FIXTURE
    if (fixture == Fixture::ipc_stale) {
        require(mailbox->revoke(ipc::Phase::inactive) && mailbox->bind(*domains[0].handle, *domains[1].handle),
                "IPC grant rebind");
        ipc_execute(0, ipc::Phase::request, 0, 0, 2, ProgramEvent::returned, 40, old_endpoint);
    } else {
        ipc_execute(0, ipc::Phase::request, 0, 0, 2, ProgramEvent::returned, 40);
    }
#else
    ipc_execute(0, ipc::Phase::request, 0, 0, 2, ProgramEvent::returned, 40);
#endif
#if (((defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_IPC_POLICY_CANCEL_INPUT)) ||                              \
      defined(AURORA_IPC_POLICY_CANCEL_OUTPUT)) ||                                                                     \
     defined(AURORA_IPC_FIXTURE))
#ifdef AURORA_IPC_FIXTURE
    if (fixture == Fixture::ipc_fault) {
#endif
        ipc_deliver(true);
        ipc_cancel();
        const auto frame = *frames.address(*domains[1].stacks[0]);
        require(mailbox->revoke(ipc::Phase::inactive) && retire(1) && !registry.index(first_service),
                "IPC service retirement");
        require(create(1) == 1 && *frames.address(*domains[1].stacks[0]) == frame &&
                    mailbox->bind(*domains[0].handle, *domains[1].handle),
                "IPC service restart");
        for (const auto &lease : domains[1].stacks)
            require(zero(*frames.address(*lease)), "IPC restart scrub");
        Serial::text("AURORA_UEFI_IPC_RESTART: frame=");
        Serial::number(frame);
        Serial::text("\r\n");
        ipc_execute(0, ipc::Phase::request, 0, 0, 2, ProgramEvent::returned, 40);
#ifdef AURORA_IPC_FIXTURE
    } else if (fixture == Fixture::ipc_cancel || fixture == Fixture::ipc_late) {
        ipc_cancel();
        if (fixture == Fixture::ipc_late)
            ipc_execute(1, ipc::Phase::service, 1, 40, 2, ProgramEvent::returned, 42);
        require(mailbox->recycle(ipc::Phase::inactive), "IPC cancelled recycle");
        ipc_execute(0, ipc::Phase::request, 0, 0, 2, ProgramEvent::returned, 40);
    }
#endif
#else
    static_cast<void>(first_service);
#endif
    ipc_deliver(false);
#if defined(AURORA_IPC_FIXTURE)
    if (fixture == Fixture::ipc_duplicate) {
        ipc_execute(1, ipc::Phase::service, 1, 40, 2, ProgramEvent::returned, 42);
    }
#endif
    require(!mailbox->cancel(ipc::Phase::inactive), "IPC replied cancellation");
    ipc_complete(false);
    require(mailbox->recycle(ipc::Phase::inactive) && mailbox->scrubbed(), "IPC record recycle");
    ipc_record("RECYCLE", 0, 0);
    require(mailbox->revoke(ipc::Phase::inactive) && retire(0) && retire(1) && frames.used() == 0 &&
                root() == kernel_root && active == L::domain_count,
            "IPC final cleanup");
    transaction = 0;
    launch = {};
    mailbox.reset();
    Serial::text("AURORA_UEFI_IPC_CLEANUP_OK: used=0 records=0\r\nAURORA_UEFI_IPC_OK\r\n");
#ifdef AURORA_UEFI_SERVICE_BUDGET
    require(timer_stop() && timer_drain() && !timer_armed, "timer final quiescence");
    Serial::text("AURORA_UEFI_SERVICE_BUDGET_OK\r\n");
#endif
}
#endif
