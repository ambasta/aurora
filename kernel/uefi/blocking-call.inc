// One fixed client/service pair and one accepted call per client incarnation.
// This private record is never addressed by user code. The request run retains
// transaction zero; only this record binds the separately minted mailbox ticket.
auto release_call_source() -> void {
#ifdef AURORA_FILE_CALL
    command_note.release();
#else
    snapshot_slot.clear();
#endif
}
[[nodiscard]] auto call_retire(unsigned index) -> bool {
    if (!call_wait.context) {
        release_call_source();
        return true;
    }
    if (!mailbox || !call_wait.authority || !call_wait.ticket)
        return false;
    if (mailbox->state() == ipc::State::pending || mailbox->state() == ipc::State::delivered)
        if (!mailbox->cancel(ipc::Phase::inactive))
            return false;
    // A committed reply must be consumed while both incarnations remain live.
    if (index == 1) {
        if (mailbox->state() != ipc::State::cancelled)
            return false;
        release_call_source();
        return true;
    }
    if (index != 0 || !domains[0].handle ||
        !mailbox->consume(*domains[0].handle, ipc::Phase::completion, call_wait.endpoint, call_wait.ticket))
        return false;
    call_wait.clear();
    release_call_source();
    return true;
}
[[nodiscard]] auto call_trap(U64 frame) -> U64 {
#ifdef AURORA_FILE_CALL
    require(command_owned && domains[0].handle && mailbox &&
                command_files.matches_read(registry, *mailbox, *domains[0].handle, ipc::Endpoint{launch[2], launch[3]}),
            "call selected read authority");
#endif
    require(active == 0 && irq_off() && mailbox && run_authority && timer_armed &&
                selected_role == SelectedRunAuthority::Role::client && selected_phase == ipc::Phase::request &&
                transaction == 0 && timer_remaining && timer_ticks < timer_initial &&
                timer_initial == timer_remaining + timer_ticks && timer_initial == run_authority->budget() &&
                timer_owner && registry.active(*timer_owner) && timer_owner_epoch == timer_epoch &&
                run_authority->matches_active(registry,
                                              *domains[0].handle,
                                              selected_role,
                                              selected_phase,
                                              selected_client,
                                              transaction,
                                              launch[0],
                                              arena,
                                              root(),
                                              *domains[0].contract,
                                              timer_owner_epoch),
            "call active run authority");
#ifdef AURORA_RUNTIME_FIXTURE
    call_fixture_entry(reinterpret_cast<U64 *>(frame));
#endif
    const auto context = ServiceContext::capture_call(std::span<const U64>{reinterpret_cast<const U64 *>(frame), 22},
                                                      frame,
                                                      *domains[0].contract,
                                                      images::clean_call_pc);
    const auto endpoint = mailbox->endpoint(*domains[0].handle);
    const auto site = images::clean_call_pc - domains[0].contract->entry();
    const Bytes code{view(arena + L::image_page(0), domains[0].contract->size())};
    require(context && endpoint && context->words()[8] == endpoint->slot() &&
                context->words()[9] == endpoint->generation() && site >= 2 && site < domains[0].contract->size() &&
                code.get(site - 2, 1) == 0xcd && code.get(site - 1, 1) == 0x82 && code.get(site, 1) == 0xc3,
            "call exact site and endpoint");
    if (domains[0].call_used
#ifdef AURORA_FILE_CALL
        && (!file_wc || file_closed || file_call_count >= 50)
#endif
    ) {
        require(!call_wait.context && mailbox->state() == ipc::State::consumed, "call repeated state");
        auto *restored = reinterpret_cast<U64 *>(frame);
        restored[14] = 2;
        restored[11] = 0;
        return 0;
    }
#ifdef AURORA_FILE_CALL
    if (file_wc) {
        require(!file_closed && file_call_count < 50 && context->words()[11] == file_call_count,
                "wc bounded sequential offset");
        if (domains[0].call_used)
            require(mailbox->state() == ipc::State::consumed && mailbox->scrubbed() &&
                        mailbox->recycle(ipc::Phase::inactive),
                    "wc consumed recycle");
    }
#endif
    require(!call_wait.context && !call_wait.authority && !call_wait.ticket && domains[1].handle &&
                registry.index(*domains[1].handle) == 1 && !registry.active(*domains[1].handle) &&
                mailbox->state() == ipc::State::idle && timer_stop(),
            "call reserve and stop");
#ifdef AURORA_FILE_CALL
    if (file_wc && !file_boundary_debit()) {
        file_closed = true;
        require(program.cancel(), "wc caller boundary exhaustion");
        asm volatile("mov %0,%%cr3" ::"r"(kernel_root) : "memory");
        require(registry.deactivate(*domains[0].handle), "wc caller exhausted owner");
        active = L::domain_count;
        return 1;
    }
#endif
    save_parked_run(call_wait, *context);
    call_wait.authority.emplace(*run_authority);
    call_wait.service = *domains[1].handle;
    call_wait.endpoint = *endpoint;
    call_wait.launch = launch;
    const auto ticket =
        mailbox->submit(*domains[0].handle, ipc::Phase::request, *endpoint, ipc::Request{context->words()[11], 0});
    require(ticket.has_value(), "call atomic publication");
    call_wait.ticket = *ticket;
    domains[0].call_used = true;
#ifdef AURORA_FILE_CALL
    if (file_wc)
        ++file_call_count;
#endif
#ifdef AURORA_RUNTIME_FIXTURE
    if (fixture == Fixture::call_pending)
        force_timer_pending();
#endif
    park_run(*domains[0].handle);
    Serial::text("AURORA_CALL_PARK: ticket=");
    Serial::number(*ticket);
    Serial::text(" epoch=");
    Serial::number(timer_epoch);
    Serial::text(" ticks=");
    Serial::number(timer_ticks);
    Serial::text(" remaining=");
    Serial::number(timer_remaining);
    Serial::text("\r\n");
    return 1;
}
auto call_envelope(const Bytes &captured, U64 result) -> void {
#ifdef AURORA_FILE_CALL
    if (file_wc && active == 1 && !file_boundary_debit()) {
        file_closed = true;
        return; // Delivered transaction is cancelled by the quiescent driver.
    }
#endif
    if (program.event() != ProgramEvent::returned)
        return;
    require(captured.get(64) == launch[0] && captured.get(72) == 1 && captured.get(88) == launch[2] &&
                captured.get(96) == launch[3] && captured.get(56) == launch[4] && captured.get(48) == launch[5],
            "call terminal envelope");
    if (active == 1) {
        require(selected_phase == ipc::Phase::service && call_wait.ticket == transaction &&
#ifdef AURORA_FILE_CALL
                    program::Files::read_reply_valid(result) &&
#else
                    ipc::snapshot_crc_reply_valid(result) &&
#endif
                    mailbox->reply(
                        *domains[1].handle, selected_phase, ipc::Endpoint{launch[2], launch[3]}, transaction, result),
                "call service reply");
#ifdef AURORA_FILE_CALL
        if (file_wc && (result & 255) != 1)
            file_closed = true;
#endif
    } else {
        require(active == 0 && selected_phase == ipc::Phase::request && transaction == 0 && domains[0].call_used &&
                    !call_wait.context && mailbox->state() == ipc::State::consumed,
                "call completed caller terminal");
#ifdef AURORA_FILE_CALL
        if (file_wc)
            require(file_closed, "wc terminal completion");
#endif
    }
}
auto call_execute(unsigned index, U64 source_phase, U64 first, U64 second) -> void {
    require(index < 2 && irq_off() && root() == kernel_root && active == L::domain_count && !timer_armed &&
                !program.running() && saved_rsp == 0,
            "call launch boundary");
    auto &domain = domains[index];
    require(domain.handle && domain.contract && verify(domain), "call launch domain");
    const auto endpoint = mailbox->endpoint(*domain.handle);
    require(endpoint.has_value(), "call launch grant");
    selected_client = 0;
    selected_role = index == 0 ? SelectedRunAuthority::Role::client : SelectedRunAuthority::Role::service;
    selected_phase = index == 0 ? ipc::Phase::request : ipc::Phase::service;
    transaction = index == 0 ? 0 : call_wait.ticket;
    launch = {source_phase, first, endpoint->slot(), endpoint->generation(), transaction, second, 0x202};
    for (const auto &lease : domain.stacks)
        fill(*frames.address(*lease), 0);
    if (index == 1) {
#ifdef AURORA_FILE_CALL
        auto &read = command_note;
        using Read = program::Note;
#else
        auto &read = snapshot_slot;
        using Read = ipc::SnapshotSlot;
#endif
        require(mailbox->state() == ipc::State::delivered && read.matches(*endpoint), "call snapshot delivery binding");
        const auto physical = frames.address(*domain.stacks.back());
        const auto virtual_page = domain.contract->layout().user_stack_top() - L::page_size;
        require(physical && (domain.tables->entry(virtual_page) & ~0x60ULL) == (*physical | 7 | RuntimeTables::nx) &&
                    (PageTables{kernel_root, static_cast<std::size_t>(handoff->get(96))}.entry(*physical) & ~0x60ULL) ==
                        (*physical | 3 | RuntimeTables::nx),
                "call snapshot retained stack mapping");
        auto *record = reinterpret_cast<std::byte *>(*physical + L::page_size - Read::stack_reservation);
        require(read.stage(std::span<std::byte, Read::record_bytes>{record, Read::record_bytes},
                           *endpoint,
                           source_phase,
                           ipc::Request{first, second}),
                "call snapshot copied record");
    }
    require(program.begin(*domain.contract) && registry.activate(*domain.handle), "call launch activation");
    active = index;
    const auto selected = domain.tables->root();
    asm volatile("mov %0,%%cr3" ::"r"(selected) : "memory");
    timer_begin(index);
    require(enter(domain.contract->entry(), domain.contract->layout().user_stack_top(), launch.data()) == 1,
            "call launch continuation");
    // The old kernel entry stack has unwound before any service can execute.
    timer_finish();
#ifdef AURORA_FILE_CALL
    if (file_wc && index == 1)
        file_service_used = timer_ticks;
#endif
    const auto current_stack = stack();
    require(root() == kernel_root && active == L::domain_count && saved_rsp == 0 && !program.running() &&
                current_stack >= arena + Handoff::stack_bottom && current_stack < arena + Handoff::stack_top,
            "call launch restoration");
    if (index == 1) {
        Serial::text("AURORA_CALL_SERVICE: epoch=");
        Serial::number(timer_epoch);
        Serial::text(" event=");
        Serial::text(program.event() == ProgramEvent::returned ? std::string_view{"returned"}
                                                               : std::string_view{"bounds"});
        Serial::text(" value=");
        Serial::number(program.value());
        Serial::text("\r\n");
    }
    launch = {};
    selected_phase = ipc::Phase::inactive;
    transaction = 0;
}
[[nodiscard]] auto call_resume(U64 ticket) -> bool {
    auto &saved = call_wait;
    auto &domain = domains[0];
    if (root() != kernel_root || active != L::domain_count || !irq_off() || timer_armed || saved_rsp ||
        program.running() || !saved.context || !saved.authority || !saved.service || ticket == 0 ||
        ticket != saved.ticket || !domain.handle || !domain.contract || !domain.call_used || !verify(domain) ||
        !saved.authority->ready_owner(registry, *domain.handle, saved.authority->epoch()) ||
        saved.authority->role() != SelectedRunAuthority::Role::client ||
        saved.authority->phase() != ipc::Phase::request || saved.authority->transaction() != 0 ||
        saved.authority->client() != 0 || saved.authority->root() != domain.tables->root() ||
        saved.authority->owned_arena() != arena ||
        !saved.context->call_frame(*domain.contract, images::clean_call_pc) ||
        !saved.context->call_frame(saved.authority->contract(), images::clean_call_pc) || saved.remaining == 0 ||
        saved.ticks >= saved.authority->budget() || saved.remaining != saved.authority->budget() - saved.ticks)
        return false;
    const auto endpoint = mailbox->endpoint(*domain.handle);
    if (!endpoint || endpoint->slot() != saved.endpoint.slot() ||
        endpoint->generation() != saved.endpoint.generation() || saved.launch[2] != endpoint->slot() ||
        saved.launch[3] != endpoint->generation() || saved.launch[4] != 0 ||
        saved.launch[0] != saved.authority->source_phase() ||
        (mailbox->state() == ipc::State::replied && registry.index(*saved.service) != 1))
        return false;
#ifdef AURORA_FILE_CALL
    if (!command_owned || !command_files.matches_read(registry, *mailbox, *domain.handle, saved.endpoint))
        return false;
#endif
    const auto completion = mailbox->consume(*domain.handle, ipc::Phase::completion, saved.endpoint, ticket);
    if (!completion)
        return false;
    launch = saved.launch;
    selected_client = 0;
    selected_role = saved.authority->role();
    selected_phase = saved.authority->phase();
    transaction = 0;
    run_authority.emplace(*saved.authority);
    timer_owner = *domain.handle;
    timer_owner_epoch = timer_epoch = saved.authority->epoch();
    timer_initial = saved.authority->budget();
    const auto frame = restore_parked_run(saved);
    auto *restored = reinterpret_cast<U64 *>(frame);
    restored[14] = completion->outcome() == ipc::Outcome::replied ? 0 : 1;
    restored[11] = completion->value();
    call_wait.clear();
    activate_parked_run(0);
    require(run_authority->matches_active(registry,
                                          *domain.handle,
                                          selected_role,
                                          selected_phase,
                                          selected_client,
                                          transaction,
                                          launch[0],
                                          arena,
                                          root(),
                                          *domain.contract,
                                          timer_owner_epoch),
            "call resume original authority");
    Serial::text("AURORA_CALL_RESUME: epoch=");
    Serial::number(timer_epoch);
    Serial::text(" ticks=");
    Serial::number(timer_ticks);
    Serial::text(" remaining=");
    Serial::number(timer_remaining);
    Serial::text("\r\n");
    timer_armed = true;
    require(timer_arm(), "call resume remaining budget");
    require(resume(frame) == 1, "call fresh kernel continuation");
    timer_finish();
    Serial::text("AURORA_CALL_COMPLETE: epoch=");
    Serial::number(timer_epoch);
    Serial::text(" event=");
    Serial::text(timer_exhausted     ? std::string_view{"budget"}
                 : call_wait.context ? std::string_view{"parked"}
                                     : std::string_view{"returned"});
    Serial::text(" value=");
    Serial::number(program.value());
    Serial::text("\r\n");
    launch = {};
    selected_phase = ipc::Phase::inactive;
    transaction = 0;
    return true;
}
#ifndef AURORA_FILE_CALL
auto call_completion_controls(U64 ticket) -> void {
    const auto original = *call_wait.authority;
    const auto &contract = *domains[0].contract;
    const user::ProgramContract changed{contract.layout(),
                                        contract.entry(),
                                        contract.size() + 1,
                                        contract.return_pc(),
                                        contract.bounds_pc(),
                                        contract.overflow_pc(),
                                        contract.division_zero_pc(),
                                        contract.shift_count_pc()};
    require(registry.activate(*domains[0].handle), "call hostile authority fixture activation");
    const auto hostile = SelectedRunAuthority::authorize(registry,
                                                         *domains[0].handle,
                                                         original.role(),
                                                         original.phase(),
                                                         original.client(),
                                                         original.transaction(),
                                                         original.source_phase(),
                                                         arena,
                                                         original.root(),
                                                         changed,
                                                         original.epoch(),
                                                         original.budget());
    require(registry.deactivate(*domains[0].handle) && hostile, "call hostile authority fixture");
    call_wait.authority.emplace(*hostile);
    require(!call_resume(ticket) && mailbox->state() == ipc::State::replied, "call changed contract preserves reply");
    call_wait.authority.emplace(original);
    ++call_wait.launch[3];
    require(!call_resume(ticket) && mailbox->state() == ipc::State::replied, "call changed launch preserves reply");
    --call_wait.launch[3];
}
auto run_blocking_calls(memory::PhysicalPages &producer_pool) -> void {
#ifdef AURORA_RUNTIME_FIXTURE
    select_fixture(Fixture::call_pending, Fixture::call_site);
#endif
    for (unsigned scenario = 0; scenario < 4; ++scenario) {
        require(prepare_snapshot(arena, producer_pool, snapshot_slot, SnapshotProducerCase::normal) ==
                        ipc::SnapshotPublication::ready &&
                    producer_pool.used() == 0,
                "call snapshot closed producer");
        mailbox.emplace(registry);
        require(create(0) == 0 && create(1) == 1 && mailbox->bind(*domains[0].handle, *domains[1].handle),
                "call participants");
        require(snapshot_slot.bind(*mailbox->endpoint(*domains[1].handle)), "call snapshot incarnation binding");
        call_execute(0, scenario == 1 ? 1 : scenario == 2 ? 8 : 0, 16384, 0);
        require(call_wait.context && call_wait.authority && call_wait.ticket && call_wait.ticks > 0,
                "call live source suspended");
        const auto ticket = call_wait.ticket, epoch = call_wait.authority->epoch();
        const auto ticks = call_wait.ticks, remaining = call_wait.remaining;
        require(!call_resume(ticket + 1) && !call_resume(ticket), "call stale and unready wake");
        ++call_wait.remaining;
        require(!call_resume(ticket), "call quota forgery");
        --call_wait.remaining;
        if (scenario == 3) {
            const auto owner = *domains[0].handle;
            require(retire(0) && !registry.index(owner) && !call_resume(ticket), "call retired waiter rejection");
            require(mailbox->revoke(ipc::Phase::inactive) && retire(1), "call cancelled retirement");
            require(create(0) == 0 && !domains[0].call_used && !call_resume(ticket), "call fresh incarnation");
            for (const auto &lease : domains[0].stacks)
                require(zero(*frames.address(*lease)), "call reused stack scrub");
            require(retire(0), "call reused retirement");
        } else {
            const auto endpoint = mailbox->endpoint(*domains[1].handle);
            require(endpoint.has_value(), "call service grant");
            const auto request = mailbox->receive(*domains[1].handle, ipc::Phase::service, *endpoint, ticket);
            require(request && request->first() == 16384 && request->second() == 0, "call copied delivery");
            call_execute(1, scenario == 1 ? 4 : 1, request->first(), request->second());
            require(timer_epoch > epoch && call_wait.ticks == ticks && call_wait.remaining == remaining,
                    "call isolated budgets");
            if (scenario == 1) {
                require(program.event() == ProgramEvent::bounds && mailbox->cancel(ipc::Phase::inactive) && retire(1),
                        "call fault cancellation retirement");
            } else
                require(program.event() == ProgramEvent::returned && !mailbox->cancel(ipc::Phase::inactive),
                        "call durable reply");
            if (scenario != 1)
                call_completion_controls(ticket);
            require(call_resume(ticket) && !call_resume(ticket), "call consume exactly once");
            require(timer_epoch == epoch && timer_ticks >= ticks && timer_initial == timer_ticks + timer_remaining,
                    "call original quota");
            if (scenario == 2)
                require(timer_exhausted && timer_remaining == 0 && timer_ticks == timer_initial,
                        "call resumed exhaustion");
            else
                require(program.event() == ProgramEvent::returned &&
                            program.value() == (scenario == 1 ? 40 : 1210602268ULL),
                        "call live locals result");
            require(mailbox->revoke(ipc::Phase::inactive) && retire(0) && (scenario == 1 || retire(1)),
                    "call final retirement");
        }
        release_call_source();
        require(producer_pool.used() == 0 && !snapshot_slot.ready() && !snapshot_slot.bound(),
                "call snapshot reclamation");
        require(frames.used() == 0 && !call_wait.context && !call_wait.ticket, "call complete scrub");
        mailbox.reset();
        Serial::text("AURORA_CALL_CASE: case=");
        Serial::number(scenario);
        Serial::text(" used=0\r\n");
    }
    Serial::text("AURORA_UEFI_CALL_OK\r\n");
}

#endif
