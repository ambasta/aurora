// Bounded cooperative client stages; only service executions receive a timer budget.
constexpr std::array<U64,2> request_first{40,70},request_second{2,3},reply_value{42,73},cancel_value{7,9};
std::optional<ipc::Endpoint> stale_service_endpoint;
#ifdef AURORA_UEFI_USER_BUDGET
std::optional<ipc::Endpoint> stale_client_endpoint;
#endif
auto client_domain(unsigned client) -> unsigned { require(client<2,"dispatch client index"); return client==0 ? 0 : 2; }
auto dispatch_record(std::string_view operation,unsigned client,U64 ticket,U64 first,U64 second) -> void {
    Serial::text("AURORA_UEFI_DISPATCH_"); Serial::text(operation); Serial::text(": client="); Serial::number(client);
    Serial::text(" transaction="); Serial::number(ticket); Serial::text(" first="); Serial::number(first);
    Serial::text(" second="); Serial::number(second); Serial::text(" queued="); Serial::number(dispatcher->queued()); Serial::text("\r\n");
}
auto dispatch_observe(unsigned client,unsigned index,ProgramEvent event,U64 value) -> void {
#ifdef AURORA_USER_RESUME
    if (domains[index].continuation.context) {
        require(!program.running() && root()==kernel_root && active==L::domain_count && saved_rsp==0,
            "suspended kernel continuation");
        Serial::text("AURORA_USER_SUSPEND: domain="); Serial::number(index);
        Serial::text(" epoch="); Serial::number(domains[index].continuation.authority->epoch());
        Serial::text(" remaining="); Serial::number(domains[index].continuation.remaining); Serial::text("\r\n");
        launch={}; selected_phase=ipc::Phase::inactive; selected_client=2; transaction=0;
        return;
    }
#endif
    const auto current_stack=stack();
    require(root()==kernel_root && active==L::domain_count && saved_rsp==0 && !program.running() && irq_off()
        && current_stack>=arena+Handoff::stack_bottom && current_stack<arena+Handoff::stack_top,"dispatch restored authority");
    require(program.event()==event && (event!=ProgramEvent::returned || program.value()==value),"dispatch compiled result");
    Serial::text("AURORA_UEFI_DISPATCH_RESTORE: client="); Serial::number(client); Serial::text(" domain="); Serial::number(index);
    Serial::text(" root="); Serial::number(root()); Serial::text(" stack="); Serial::number(current_stack); Serial::text(" event=");
    Serial::text(event==ProgramEvent::returned ? "returned" : event==ProgramEvent::bounds ? "bounds" : event==ProgramEvent::overflow ? "overflow" : "budget");
    Serial::text(" value="); Serial::number(program.value()); Serial::text("\r\n");
    launch={}; selected_phase=ipc::Phase::inactive; selected_client=2; transaction=0;
}
auto dispatch_execute(unsigned client,unsigned index,ipc::Phase phase,U64 source_phase,U64 first,U64 second,ProgramEvent event,U64 value,U64 completed_transaction=0) -> void {
    require(client<2 && index<L::domain_count && root()==kernel_root && active==L::domain_count && irq_off(),"dispatch launch boundary");
    auto& domain=domains[index]; require(domain.handle && verify(domain),"dispatch launch domain");
    auto endpoint=dispatcher->endpoint(client,*domain.handle); require(endpoint.has_value(),"dispatch launch grant");
#ifdef AURORA_DISPATCH_CLIENT_OWNER
    if (client==1 && phase==ipc::Phase::request) endpoint=dispatcher->endpoint(0,*domains[0].handle);
#endif
#ifdef AURORA_DISPATCH_CROSS_REPLY
    if (phase==ipc::Phase::service) endpoint=dispatcher->endpoint(1-client,*domains[1].handle);
#endif
#ifdef AURORA_DISPATCH_STALE
    if (phase==ipc::Phase::service && stale_service_endpoint) endpoint=stale_service_endpoint;
#endif
#ifdef AURORA_USER_STALE_GRANT
    if (client==0 && phase==ipc::Phase::request && stale_client_endpoint) endpoint=stale_client_endpoint;
#endif
    selected_client=client; selected_phase=phase;
    transaction=phase==ipc::Phase::request ? 0 : phase==ipc::Phase::completion ? completed_transaction : dispatcher->transaction(client).value_or(0);
    require(phase==ipc::Phase::request || transaction!=0,"dispatch launch transaction");
    launch={source_phase,first,endpoint->slot(),endpoint->generation(),transaction,second,phase==ipc::Phase::service ? 0x202ULL : 2ULL};
#ifdef AURORA_UEFI_USER_BUDGET
    selected_role=index==1 ? RunAuthority::Role::service : RunAuthority::Role::client;
    launch[6]=0x202;
#endif
    for (const auto& lease:domain.stacks) { const auto address=frames.address(*lease); require(address.has_value(),"dispatch stack lease"); fill(*address,0); }
    require(program.begin(*domain.contract) && registry.activate(*domain.handle),"dispatch launch state"); active=index;
    Serial::text("AURORA_UEFI_DISPATCH_ENTER: client="); Serial::number(client); Serial::text(" domain="); Serial::number(index);
    Serial::text(" phase="); Serial::number(source_phase); Serial::text(" root="); Serial::number(domain.tables->root());
    Serial::text(" grant="); Serial::number(endpoint->generation()); Serial::text(" transaction="); Serial::number(transaction); Serial::text("\r\n");
    const auto selected=domain.tables->root(); asm volatile("mov %0,%%cr3"::"r"(selected):"memory");
#ifdef AURORA_UEFI_USER_BUDGET
    timer_begin(index);
    if (index==0) {
#ifdef AURORA_USER_ROLE
        selected_role=RunAuthority::Role::service;
#endif
#ifdef AURORA_USER_PHASE
        selected_phase=ipc::Phase::completion;
#endif
#ifdef AURORA_USER_TRANSACTION
        ++transaction;
#endif
#ifdef AURORA_USER_EPOCH
        --timer_owner_epoch;
#endif
    }
#else
    if (phase==ipc::Phase::service) timer_begin(index);
#endif
    require(enter(domain.contract->entry(),domain.contract->layout().user_stack_top(),launch.data())==1,"dispatch continuation");
#ifdef AURORA_UEFI_USER_BUDGET
    timer_finish();
#ifdef AURORA_USER_CONTEXT
    if (index==0 && phase==ipc::Phase::request) require(timer_context_hits>0,"user register probe interrupt");
#endif
#else
    if (phase==ipc::Phase::service) timer_finish();
#endif
    dispatch_observe(client,index,event,value);
}

auto dispatch_envelope(const Bytes& captured,U64 result) -> void {
    if (program.event()!=ProgramEvent::returned) {
#ifdef AURORA_UEFI_USER_BUDGET
        require(selected_client<2 && (program.event()==ProgramEvent::bounds || program.event()==ProgramEvent::overflow)
            && ((selected_role==RunAuthority::Role::service && selected_phase==ipc::Phase::service && active==1)
                || (selected_role==RunAuthority::Role::client && active==client_domain(selected_client)
                    && (selected_phase==ipc::Phase::request || selected_phase==ipc::Phase::completion))),"user known fault phase");
        return;
#else
        require(selected_phase==ipc::Phase::service && program.event()==ProgramEvent::bounds,"dispatch fault phase"); return;
#endif
    }
    require(selected_client<2 && captured.get(64)==launch[0] && captured.get(72)==1,"dispatch phase/version authority");
    Serial::text("AURORA_UEFI_DISPATCH_ENVELOPE: client="); Serial::number(selected_client);
    Serial::text(" phase="); Serial::number(captured.get(64)); Serial::text(" version="); Serial::number(captured.get(72));
    Serial::text(" slot="); Serial::number(captured.get(88)); Serial::text(" generation="); Serial::number(captured.get(96));
    Serial::text(" transaction="); Serial::number(captured.get(56)); Serial::text(" value="); Serial::number(result);
    Serial::text(" second="); Serial::number(captured.get(48)); Serial::text("\r\n");
    const ipc::Endpoint endpoint{captured.get(88),captured.get(96)}; const auto actor=*domains[active].handle;
    if (selected_phase==ipc::Phase::request) {
        require(active==client_domain(selected_client) && captured.get(56)==0,"dispatch request origin");
        const auto ticket=dispatcher->submit(actor,selected_phase,endpoint,ipc::Request{result,captured.get(48)});
        require(ticket.has_value(),"dispatch request capability/queue");
        dispatch_record("SUBMIT",selected_client,*ticket,result,captured.get(48));
    } else if (selected_phase==ipc::Phase::service) {
        require(active==1 && dispatcher->selected()==selected_client
            && dispatcher->reply(actor,selected_phase,endpoint,captured.get(56),result),"dispatch selected reply authority");
        dispatch_record("REPLY",selected_client,captured.get(56),result,0);
    } else {
        const auto expected=dispatcher->endpoint(selected_client,actor);
        require(selected_phase==ipc::Phase::completion && active==client_domain(selected_client) && expected
            && expected->slot()==endpoint.slot() && expected->generation()==endpoint.generation()
            && captured.get(56)==transaction && dispatcher->state(selected_client)==ipc::State::consumed,"dispatch completion authority");
        dispatch_record("COMPLETE",selected_client,transaction,result,0);
    }
}
auto dispatch_finish() -> void {
    const bool quiescent=root()==kernel_root && active==L::domain_count && irq_off() && !timer_armed
        && timer_quiet(0x100,false) && timer_quiet(0x200,false);
    require(dispatcher->finish_selected(ipc::Phase::inactive,quiescent),"dispatch terminal quiescence");
}
auto dispatch_request(unsigned client) -> void {
    dispatch_execute(client,client_domain(client),ipc::Phase::request,0,0,request_second[client],ProgramEvent::returned,request_first[client]);
}
auto dispatch_service(unsigned expected_client,unsigned source_phase=1) -> void {
    const auto work=dispatcher->select(ipc::Phase::inactive);
    require(work && work->client()==expected_client && work->request().first()==request_first[expected_client]
        && work->request().second()==request_second[expected_client],"dispatch fair copied selection");
    dispatch_record("SELECT",expected_client,work->transaction(),work->request().first(),work->request().second());
    dispatch_execute(expected_client,1,ipc::Phase::service,source_phase,work->request().first(),work->request().second(),
        source_phase==1 ? ProgramEvent::returned : source_phase==4 ? ProgramEvent::bounds : ProgramEvent::rejected,
        source_phase==1 ? reply_value[expected_client] : 0);
    require((source_phase!=5 || (timer_exhausted && timer_ticks==3 && timer_resumes==2))
        && (source_phase==4 || timer_compiled_hits>0),"dispatch service interrupt outcome");
    if (source_phase==1) dispatch_finish();
}
auto dispatch_complete(unsigned client,bool cancelled) -> void {
    const auto actor=*domains[client_domain(client)].handle;
    const auto endpoint=dispatcher->endpoint(client,actor); const auto ticket=dispatcher->transaction(client);
    require(endpoint && ticket,"dispatch completion ticket");
    const auto result=dispatcher->consume(actor,ipc::Phase::completion,*endpoint,*ticket);
    require(result && result->outcome()==(cancelled ? ipc::Outcome::cancelled : ipc::Outcome::replied)
        && result->value()==(cancelled ? 0 : reply_value[client]),"dispatch copied completion");
    dispatch_record("CONSUME",client,*ticket,result->value(),cancelled ? 1 : 0);
    dispatch_execute(client,client_domain(client),ipc::Phase::completion,cancelled ? 3 : 2,result->value(),0,
        ProgramEvent::returned,cancelled ? cancel_value[client] : reply_value[client],*ticket);
}
auto dispatch_bind() -> void {
    require(dispatcher->bind(std::array<user::DomainHandle,2>{*domains[0].handle,*domains[2].handle},*domains[1].handle),"dispatch participant binding");
    for (unsigned client=0;client<2;++client) {
        const auto endpoint=dispatcher->endpoint(client,*domains[client_domain(client)].handle); require(endpoint.has_value(),"dispatch fresh endpoint");
        dispatch_record("BIND",client,0,endpoint->generation(),client_domain(client));
    }
}
[[maybe_unused]] auto run_dispatcher() -> void {
    static_assert(L::domain_count==3 && L::image_count==3);
    dispatcher.emplace(registry);
    require(create(0)==0 && create(1)==1 && create(2)==2 && frames.used()==12,"three owned dispatch domains");
    for (unsigned index=0;index<3;++index) {
        require(verify(domains[index]),"dispatch private mappings");
        Serial::text("AURORA_UEFI_DISPATCH_DOMAIN: index="); Serial::number(index); Serial::text(" root="); Serial::number(domains[index].tables->root());
        Serial::text(" entry="); Serial::number(domains[index].contract->entry()); Serial::text(" stack="); Serial::number(domains[index].contract->layout().user_stack_top());
        Serial::text(" frame="); Serial::number(*frames.address(*domains[index].stacks[0])); Serial::text("\r\n");
    }
    dispatch_bind(); dispatch_request(0);
#ifdef AURORA_DISPATCH_DUPLICATE
    dispatch_request(0);
#endif
    dispatch_request(1);
#ifdef AURORA_DISPATCH_FULL
    dispatch_request(0);
#endif
#if defined(AURORA_DISPATCH_BUDGET) || defined(AURORA_DISPATCH_FAULT) || defined(AURORA_DISPATCH_MIXED) || defined(AURORA_DISPATCH_STALE)
    const auto old_service=*domains[1].handle; const auto old_endpoint=dispatcher->endpoint(0,old_service);
#ifdef AURORA_DISPATCH_MIXED
    dispatch_service(0); dispatch_service(1,5);
    constexpr bool first_replied=true;
#elif defined(AURORA_DISPATCH_FAULT)
    dispatch_service(0,4); constexpr bool first_replied=false;
#else
    dispatch_service(0,5); constexpr bool first_replied=false;
#endif
    const auto cancelled=dispatcher->cancel_pending(ipc::Phase::inactive);
    require(cancelled==(first_replied ? 1U : 2U),"dispatch incarnation cancellation");
    dispatch_record("CANCEL",2,0,cancelled,first_replied ? 1 : 0); dispatch_finish();
    dispatch_complete(0,!first_replied); dispatch_complete(1,true);
    const auto reused=*frames.address(*domains[1].stacks[0]);
    require(dispatcher->revoke(ipc::Phase::inactive) && retire(1) && !registry.index(old_service)
        && create(1)==1 && *frames.address(*domains[1].stacks[0])==reused,"dispatch service rebirth");
    for (const auto& lease:domains[1].stacks) require(zero(*frames.address(*lease)),"dispatch rebirth scrub");
    dispatch_record("RESTART",2,0,reused,frames.used()); dispatch_bind();
#ifdef AURORA_DISPATCH_STALE
    stale_service_endpoint=old_endpoint;
#else
    static_cast<void>(old_endpoint);
#endif
    dispatch_request(0); dispatch_request(1);
#endif
    dispatch_service(0); dispatch_complete(0,false);
    require(dispatcher->recycle(ipc::Phase::inactive,0),"dispatch client recycle");
    dispatch_record("RECYCLE",0,0,0,0); dispatch_request(0);
    dispatch_service(1); dispatch_complete(1,false);
    dispatch_service(0); dispatch_complete(0,false);
    require(dispatcher->revoke(ipc::Phase::inactive) && dispatcher->scrubbed() && dispatcher->queued()==0,"dispatch record cleanup");
    require(retire(0) && retire(1) && retire(2) && frames.used()==0 && root()==kernel_root && active==L::domain_count,"dispatch domain cleanup");
    require(timer_stop() && timer_drain() && !timer_armed,"dispatch final quiescence");
    dispatcher.reset(); transaction=0; selected_client=2; launch={};
    Serial::text("AURORA_UEFI_DISPATCH_CLEANUP_OK: used=0 records=0\r\nAURORA_UEFI_DISPATCH_OK\r\n");
}
