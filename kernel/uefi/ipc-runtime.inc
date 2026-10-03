// Included inside the runtime adapter's private namespace; no separate authority.
auto ipc_record(std::string_view operation,U64 first,U64 second) -> void {
    Serial::text("AURORA_UEFI_IPC_"); Serial::text(operation); Serial::text(": transaction="); Serial::number(transaction);
    Serial::text(" first="); Serial::number(first); Serial::text(" second="); Serial::number(second); Serial::text("\r\n");
}
auto ipc_execute(unsigned index,ipc::Phase phase,U64 source_phase,U64 first,U64 second,ProgramEvent expected_event,U64 expected_value,
                 std::optional<ipc::Endpoint> override_endpoint=std::nullopt) -> void {
    require(index<2 && root()==kernel_root && active==L::domain_count,"IPC launch boundary");
    auto& domain=domains[index]; require(domain.handle && verify(domain),"IPC launch domain");
    const auto endpoint=override_endpoint ? override_endpoint : mailbox->endpoint(*domain.handle);
    require(endpoint.has_value(),"IPC launch grant");
    launch={source_phase,first,endpoint->slot(),endpoint->generation(),phase==ipc::Phase::request ? 0 : transaction,second};
    selected_phase=phase;
#ifdef AURORA_UEFI_SERVICE_BUDGET
    launch[6]=phase==ipc::Phase::service ? 0x202 : 2;
#endif
    for (const auto& lease:domain.stacks) { const auto address=frames.address(*lease); require(address.has_value(),"IPC stack lease"); fill(*address,0); }
    require(program.begin(*domain.contract) && registry.activate(*domain.handle),"IPC launch state");
    active=index;
    Serial::text("AURORA_UEFI_IPC_ENTER: slot="); Serial::number(index); Serial::text(" phase="); Serial::number(source_phase);
    Serial::text(" root="); Serial::number(domain.tables->root()); Serial::text(" grant="); Serial::number(endpoint->generation());
    Serial::text(" transaction="); Serial::number(launch[4]); Serial::text("\r\n");
    const auto selected=domain.tables->root(); asm volatile("mov %0,%%cr3"::"r"(selected):"memory");
#ifdef AURORA_IPC_KERNEL_TRAP
    asm volatile("jmp *%0"::"r"(domain.contract->bounds_pc()):"memory");
#endif
#ifdef AURORA_UEFI_SERVICE_BUDGET
    if (phase==ipc::Phase::service) {
        timer_begin(index);
#ifdef AURORA_BUDGET_EPOCH
        --timer_owner_epoch;
#endif
#ifdef AURORA_BUDGET_FORGED
        require(timer_stop() && timer_quiet(0x100,false),"forged probe quiet");
        asm volatile("int $64\n.global uefi_service_forged_pc\nuefi_service_forged_pc:":::"memory");
#endif
    }
#endif
    require(enter(domain.contract->entry(),domain.contract->layout().user_stack_top(),launch.data())==1,"IPC continuation");
#ifdef AURORA_UEFI_SERVICE_BUDGET
    if (phase==ipc::Phase::service) timer_finish();
#endif
    const auto current_stack=stack();
    require(root()==kernel_root && active==L::domain_count && saved_rsp==0 && !program.running()
        && current_stack>=arena+Handoff::stack_bottom && current_stack<arena+Handoff::stack_top,"IPC restored authority");
    require(program.event()==expected_event && (expected_event!=ProgramEvent::returned || program.value()==expected_value),"IPC compiled result");
    Serial::text("AURORA_UEFI_IPC_RESTORE: slot="); Serial::number(index); Serial::text(" root="); Serial::number(root());
    Serial::text(" stack="); Serial::number(current_stack); Serial::text(" event="); Serial::text(expected_event==ProgramEvent::returned ? "returned" : expected_event==ProgramEvent::bounds ? "bounds" : "budget");
    Serial::text(" value="); Serial::number(program.value()); Serial::text("\r\n");
    launch={}; selected_phase=ipc::Phase::inactive;
}
auto ipc_complete(bool cancelled) -> void {
    const auto endpoint=mailbox->endpoint(*domains[0].handle); require(endpoint.has_value(),"IPC completion grant");
    const auto completion=mailbox->consume(*domains[0].handle,ipc::Phase::completion,*endpoint,transaction);
    require(completion && completion->outcome()==(cancelled ? ipc::Outcome::cancelled : ipc::Outcome::replied)
        && completion->value()==(cancelled ? 0 : 42) && mailbox->scrubbed(),"IPC completion copy/scrub");
    ipc_record("CONSUME",completion->value(),cancelled ? 1 : 0);
    ipc_execute(0,ipc::Phase::completion,cancelled ? 3 : 2,completion->value(),0,ProgramEvent::returned,cancelled ? 7 : 42);
}
auto ipc_deliver(bool fault) -> void {
    const auto endpoint=mailbox->endpoint(*domains[1].handle); require(endpoint.has_value(),"IPC delivery grant");
    const auto request=mailbox->receive(*domains[1].handle,ipc::Phase::service,*endpoint,transaction);
    require(request && request->first()==40 && request->second()==2 && mailbox->scrubbed(),"IPC request copy");
    ipc_record("DELIVER",request->first(),request->second());
#ifdef AURORA_UEFI_SERVICE_BUDGET
    const bool exhaust=fault;
#ifdef AURORA_BUDGET_FAULT
    const auto source_phase=exhaust ? 4 : 1;
    const auto wanted=exhaust ? ProgramEvent::bounds : ProgramEvent::returned;
#else
    const auto source_phase=exhaust ? 5 : 1;
    const auto wanted=exhaust ? ProgramEvent::rejected : ProgramEvent::returned;
#endif
    ipc_execute(1,ipc::Phase::service,source_phase,request->first(),request->second(),wanted,exhaust ? 0 : 42);
#ifdef AURORA_BUDGET_FAULT
    require(!timer_exhausted && (exhaust || timer_compiled_hits>0),"service fault outcome");
#else
    require(timer_exhausted==exhaust && timer_compiled_hits>0 && (!exhaust || (timer_ticks==3 && timer_resumes==2)),"service budget outcome");
#endif
#ifdef AURORA_BUDGET_CONTEXT
    if (!exhaust) require(timer_context_hits>0,"timer register probe delivery");
#endif
#else
    ipc_execute(1,ipc::Phase::service,fault ? 4 : 1,request->first(),request->second(),fault ? ProgramEvent::bounds : ProgramEvent::returned,fault ? 0 : 42);
#endif
}
[[maybe_unused]] auto ipc_cancel() -> void {
    require(root()==kernel_root && active==L::domain_count && mailbox->cancel(ipc::Phase::inactive) && mailbox->scrubbed(),"IPC cancel boundary");
    const auto endpoint=mailbox->endpoint(*domains[1].handle); require(endpoint.has_value(),"IPC cancelled grant");
    require(!mailbox->reply(*domains[1].handle,ipc::Phase::service,*endpoint,transaction,99)
        && !mailbox->cancel(ipc::Phase::inactive),"IPC late reply/cancel");
    ipc_record("CANCEL",0,0);
    ipc_complete(true);
}
auto run_ipc() -> void {
#ifdef AURORA_IPC_EXHAUSTED
    mailbox.emplace(registry,1);
#else
    mailbox.emplace(registry);
#endif
    require(create(0)==0 && create(1)==1 && mailbox->bind(*domains[0].handle,*domains[1].handle),"IPC participants");
    [[maybe_unused]] const auto first_service=*domains[1].handle;
    const auto old_endpoint=mailbox->endpoint(*domains[0].handle); require(old_endpoint.has_value(),"IPC initial endpoint");
#ifdef AURORA_IPC_STALE
    require(mailbox->revoke(ipc::Phase::inactive) && mailbox->bind(*domains[0].handle,*domains[1].handle),"IPC grant rebind");
    ipc_execute(0,ipc::Phase::request,0,0,2,ProgramEvent::returned,40,old_endpoint);
#else
    ipc_execute(0,ipc::Phase::request,0,0,2,ProgramEvent::returned,40);
#endif
#if defined(AURORA_IPC_FAULT) || defined(AURORA_UEFI_SERVICE_BUDGET)
    ipc_deliver(true); ipc_cancel();
    const auto frame=*frames.address(*domains[1].stacks[0]);
    require(mailbox->revoke(ipc::Phase::inactive) && retire(1) && !registry.index(first_service),"IPC service retirement");
    require(create(1)==1 && *frames.address(*domains[1].stacks[0])==frame
        && mailbox->bind(*domains[0].handle,*domains[1].handle),"IPC service restart");
    for (const auto& lease:domains[1].stacks) require(zero(*frames.address(*lease)),"IPC restart scrub");
    Serial::text("AURORA_UEFI_IPC_RESTART: frame="); Serial::number(frame); Serial::text("\r\n");
    ipc_execute(0,ipc::Phase::request,0,0,2,ProgramEvent::returned,40);
#elif defined(AURORA_IPC_CANCEL) || defined(AURORA_IPC_LATE)
    ipc_cancel();
#ifdef AURORA_IPC_LATE
    ipc_execute(1,ipc::Phase::service,1,40,2,ProgramEvent::returned,42);
#endif
    require(mailbox->recycle(ipc::Phase::inactive),"IPC cancelled recycle");
    ipc_execute(0,ipc::Phase::request,0,0,2,ProgramEvent::returned,40);
#else
    static_cast<void>(first_service);
#endif
    ipc_deliver(false);
#ifdef AURORA_IPC_DUPLICATE
    ipc_execute(1,ipc::Phase::service,1,40,2,ProgramEvent::returned,42);
#endif
    require(!mailbox->cancel(ipc::Phase::inactive),"IPC replied cancellation");
    ipc_complete(false);
    require(mailbox->recycle(ipc::Phase::inactive) && mailbox->scrubbed(),"IPC record recycle");
    ipc_record("RECYCLE",0,0);
    require(mailbox->revoke(ipc::Phase::inactive) && retire(0) && retire(1) && frames.used()==0
        && root()==kernel_root && active==L::domain_count,"IPC final cleanup");
    transaction=0; launch={}; mailbox.reset();
    Serial::text("AURORA_UEFI_IPC_CLEANUP_OK: used=0 records=0\r\nAURORA_UEFI_IPC_OK\r\n");
#ifdef AURORA_UEFI_SERVICE_BUDGET
    require(timer_stop() && timer_drain() && !timer_armed,"timer final quiescence");
    Serial::text("AURORA_UEFI_SERVICE_BUDGET_OK\r\n");
#endif
}
