// One retained timer continuation per private domain. No user-provided frame,
// address, epoch or quota is accepted by this scheduler entry.
[[nodiscard]] auto resume_client(unsigned index,ProgramEvent event,U64 value) -> bool {
    if (index>=L::domain_count || root()!=kernel_root || active!=L::domain_count || !irq_off()
        || timer_armed || saved_rsp!=0 || program.running()) return false;
    auto& domain=domains[index]; auto& saved=domain.continuation;
    if (!domain.handle || !domain.contract || !saved.context || !saved.authority || !verify(domain)
        || !saved.authority->ready_owner(registry,*domain.handle,saved.authority->epoch())
        || !saved.context->timer_frame(*domain.contract) || saved.authority->root()!=domain.tables->root()
        || saved.remaining==0 || saved.ticks>=saved.authority->budget()
        || saved.remaining!=saved.authority->budget()-saved.ticks) return false;
    const auto client=saved.authority->client();
    const auto endpoint=dispatcher->endpoint(client,*domain.handle);
    if (!endpoint || endpoint->slot()!=saved.launch[2] || endpoint->generation()!=saved.launch[3]
        || saved.authority->role()!=RunAuthority::Role::client || saved.authority->phase()!=ipc::Phase::request
        || dispatcher->state(client)!=ipc::State::idle) return false;
    launch=saved.launch; selected_client=client; selected_role=saved.authority->role();
    selected_phase=saved.authority->phase(); transaction=saved.authority->transaction();
    run_authority.emplace(*saved.authority);
    timer_owner=*domain.handle; timer_owner_epoch=timer_epoch=saved.authority->epoch();
    timer_initial=saved.authority->budget();
    const auto frame=restore_parked_run(saved);
    // The shared RSP0 copy now owns the restore bytes; no reusable ticket remains.
    domain.continuation.clear();
    activate_parked_run(index);
    require(run_authority->matches_active(registry,*domain.handle,selected_role,selected_phase,selected_client,
        transaction,launch[0],arena,root(),*domain.contract,timer_owner_epoch),"resume immutable authority");
    Serial::text("AURORA_USER_RESUME: domain="); Serial::number(index); Serial::text(" epoch="); Serial::number(timer_epoch);
    Serial::text(" remaining="); Serial::number(timer_remaining); Serial::text(" ticks="); Serial::number(timer_ticks);
    Serial::text("\r\n");
    timer_armed=true; require(timer_arm(),"resume timer arm");
    require(resume(frame)==1,"resume kernel continuation");
    timer_finish();
    dispatch_observe(client,index,event,value);
    return true;
}
auto run_resumable_clients() -> void {
    constexpr U64 checksum_a=3843153995,checksum_b=2666559570;
    for (unsigned scenario=0;scenario<3;++scenario) {
        dispatcher.emplace(registry);
        require(create(0)==0 && create(1)==1 && create(2)==2,"resume participants");
        dispatch_bind();
        dispatch_execute(0,0,ipc::Phase::request,scenario==1 ? 6 : 0,40,0,ProgramEvent::returned,checksum_a);
        require(domains[0].continuation.context
            && domains[0].continuation.ticks==1,"checksum suspended");
        const auto epoch=domains[0].continuation.authority->epoch();
        const auto remaining=domains[0].continuation.remaining;
        require(!resume_client(2,ProgramEvent::returned,checksum_b),"peer cannot consume saved run");
        auto& saved=domains[0].continuation;
        ++saved.remaining;
        require(!resume_client(0,ProgramEvent::returned,checksum_a),"inconsistent continuation quota");
        --saved.remaining;
        std::destroy_at(&domains[2].continuation);
        std::construct_at(&domains[2].continuation,saved);
        require(!resume_client(2,ProgramEvent::returned,checksum_a),"foreign continuation owner");
        domains[2].continuation.clear();
        dispatch_execute(1,2,ipc::Phase::request,0,70,0,ProgramEvent::returned,checksum_b);
        require(timer_epoch>epoch && domains[0].continuation.remaining==remaining,"peer preserves run quota");
        if (scenario==2) {
            const auto old=*domains[0].handle;
            const auto frame=*frames.address(*domains[0].stacks[0]);
            require(dispatcher->dispose_client(ipc::Phase::inactive,0,old,true).has_value()
                && retire(0) && !registry.index(old) && create(0)==0
                && *frames.address(*domains[0].stacks[0])==frame,"cancel/recreate suspended owner");
            for (const auto& lease:domains[0].stacks) require(zero(*frames.address(*lease)),"cancelled stack scrub");
            require(!resume_client(0,ProgramEvent::returned,checksum_a),"retired continuation cannot resume");
            require(dispatcher->rebind_client(ipc::Phase::inactive,0,*domains[0].handle),"fresh resume client binding");
        } else {
            require(resume_client(0,scenario==1 ? ProgramEvent::rejected : ProgramEvent::returned,
                scenario==1 ? 0 : checksum_a),"owned continuation resume");
            require(!resume_client(0,ProgramEvent::returned,checksum_a),"single consumption of continuation");
            require(timer_epoch==epoch && timer_ticks>=1 && timer_initial==timer_ticks+timer_remaining,
                "original run budget preserved");
            if (scenario==1) require(timer_exhausted && timer_ticks==3 && timer_remaining==0,"resumed budget exhausts");
        }
        require(dispatcher->dispose_client(ipc::Phase::inactive,0,*domains[0].handle,true).has_value()
            && dispatcher->dispose_client(ipc::Phase::inactive,1,*domains[2].handle,true).has_value()
            && dispatcher->revoke(ipc::Phase::inactive) && dispatcher->scrubbed(),"resume IPC cancellation/revoke");
        require(retire(0) && retire(1) && retire(2) && frames.used()==0,"resume complete retirement");
        dispatcher.reset();
        Serial::text("AURORA_USER_RESUME_CASE: case="); Serial::number(scenario); Serial::text(" used=0\r\n");
    }
    Serial::text("AURORA_UEFI_USER_RESUME_OK\r\n");
}
