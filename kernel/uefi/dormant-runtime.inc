// CPU-only guest harness. These owned bytes are never published to any device.
constinit std::optional<memory::PinLedger> table_ledger;
constinit std::optional<memory::DormantTables> dormant_tables;
std::array<U64,2> table_quarantine_pages{};
#ifdef AURORA_TABLE_QUARANTINE
bool table_scrub_failure_armed{};
U64 table_old_incarnation{};
#endif
[[gnu::noinline]] auto table_scrub(void*,U64 address,std::size_t bytes) -> bool {
    if(root()!=kernel_root || active!=L::domain_count || bytes!=4096 || address%4096
        || address<arena+L::stack_frames_offset || address>=arena+L::stack_frames_offset+16*4096) return false;
#ifdef AURORA_TABLE_QUARANTINE
    // Exact test-only failure before any byte is scrubbed; no publication API exists.
    if(table_scrub_failure_armed && address==table_quarantine_pages[0]) return false;
#endif
    fill(address,0);return zero(address);
}
auto pin_retained() -> std::size_t {return table_ledger ? table_ledger->quarantined_pages() : 0;}
auto table_record(std::string_view event) -> void {
    Serial::text("AURORA_TABLE_STATE: event=");Serial::text(event);
    Serial::text(" pool=");Serial::number(frames.used());
    Serial::text(" pinned=");Serial::number(table_ledger->pinned_pages());
    Serial::text(" quarantine=");Serial::number(table_ledger->quarantined_pages());
    Serial::text(" entries=");Serial::number(table_ledger->used_entries());
    Serial::text(" root=");Serial::number(root());Serial::text(" publication=never\r\n");
}
[[gnu::noinline]] auto table_prepare(memory::DormantTables& tables,user::DomainHandle owner) -> bool {
    const std::array<U64,2> iovas{0x1000,0x1ff000};const std::array<bool,2> writable{false,true};
    // Owned arena is below4GiB;32 is this dormant profile's chosen address bound,
    // not an assertion about the capabilities of an active IOMMU.
    return tables.prepare(owner,32,iovas,writable);
}
[[gnu::noinline]] auto table_readback(user::DomainHandle owner) -> void {
    require(dormant_tables->validate(owner),"CPU table seal");
    const auto snapshot=memory::DormantTableTestAccess::snapshot(*dormant_tables);
    require(independent::validate(snapshot),"independent CPU table bytes");
    table_quarantine_pages={snapshot.pages[0],snapshot.pages[1]};
    require(independent::permits(snapshot,16,0x1000,4096,false)
        && !independent::permits(snapshot,16,0x1000,1,true)
        && independent::permits(snapshot,16,0x1ff000,4096,true)
        && !independent::permits(snapshot,16,0x201000,1,false),"software translation model");
    for(U64 rid=0;rid<65536;++rid) if(rid!=16)
        require(!independent::permits(snapshot,static_cast<std::uint16_t>(rid),0x1000,1,false),"software requester model");
    Serial::text("AURORA_TABLE_CPU_BYTES: dtes=256 leaves=512 pages=5 domain=1 valid=1\r\n");
    Serial::text("AURORA_TABLE_SOFTWARE_MODEL: requester_denied=65535 high_iova_denied=1 read=1 write_denied=1\r\n");
}
#ifdef AURORA_TABLE_REJECT
[[gnu::noinline]] auto table_corruption(user::DomainHandle owner) -> void {
    const auto snapshot=memory::DormantTableTestAccess::snapshot(*dormant_tables);
    // Zero a denied DTE; alter domain/root; clear leaf PR; add write/reserved bit.
    constexpr std::array<std::size_t,6> roles{0,0,0,2,2,2};
    constexpr std::array<std::size_t,6> offsets{0,16*32+8,16*32+1,8,15,14};
    constexpr std::array<unsigned,6> masks{3,1,0x10,1,0x40,0x10};
    for(std::size_t i=0;i<roles.size();++i) {
        require(memory::DormantTableTestAccess::flip(*dormant_tables,roles[i],offsets[i],masks[i]),"bounded test corruption");
        require(!dormant_tables->validate(owner) && !independent::validate(snapshot),"corrupt bytes accepted");
        Serial::text("AURORA_TABLE_CASE: index=");Serial::number(i);
        Serial::text(" state=rejected constructor=0 decoder=0\r\n");
        require(memory::DormantTableTestAccess::flip(*dormant_tables,roles[i],offsets[i],masks[i]),"test restoration");
        require(dormant_tables->validate(owner) && independent::validate(snapshot),"restored bytes rejected");
        Serial::text("AURORA_TABLE_CASE: index=");Serial::number(i);
        Serial::text(" state=restored constructor=1 decoder=1\r\n");
    }
    memory::DormantTables refused(*table_ledger,
        std::span<std::byte>{reinterpret_cast<std::byte*>(arena+L::stack_frames_offset),16*4096},arena+L::stack_frames_offset);
    const std::array<bool,2> rights{false,true};
    for(const auto bad:std::array<std::array<U64,2>,3>{{{0,0},{1,4096},{0,0x200000}}})
        require(!refused.prepare(owner,32,bad,rights),"malformed construction request");
    const std::array<U64,2> good{0,4096};
    require(!refused.prepare(owner,53,good,rights) && !refused.prepare(user::DomainHandle{},32,good,rights)
        && frames.used()==13 && table_ledger->pinned_pages()==5,"invalid profile/owner mutated ledger");
    Serial::text("AURORA_TABLE_CORRUPTION: rejected=6 requests=5 restored=1\r\n");table_record("rejected");
}
#endif
#ifdef AURORA_TABLE_EXHAUST
[[gnu::noinline]] auto table_exhaustion(user::DomainHandle owner) -> void {
    auto first=frames.acquire(),held=frames.acquire();require(first && held,"fragmentation reservations");
    require(frames.release(*first),"fragment gap");
    require(!table_prepare(*dormant_tables,owner) && frames.used()==9 && table_ledger->pinned_pages()==0,"fragmented DTE pair");
    table_record("fragmented");require(frames.release(*held),"fragment reservation cleanup");
    std::array<std::optional<memory::PageLease>,4> reservations{};
    for(auto& item:reservations){auto p=frames.acquire();require(p.has_value(),"pool pressure");item.emplace(std::move(*p));}
    require(!table_prepare(*dormant_tables,owner) && frames.used()==12 && table_ledger->pinned_pages()==0,"table pool exhaustion");
    table_record("pool-full");for(auto& item:reservations)require(frames.release(*item),"pool pressure cleanup");
    const auto one=table_ledger->grant(*domains[0].handle,1),two=table_ledger->grant(*domains[0].handle,1);
    require(one && two && !table_prepare(*dormant_tables,owner) && frames.used()==10
        && table_ledger->pinned_pages()==2 && table_ledger->used_entries()==2,"table entry exhaustion");
    table_record("entries-full");require(table_ledger->cancel(*one,*domains[0].handle)
        && table_ledger->cancel(*two,*domains[0].handle),"unrelated entry cleanup");
}
#endif
[[gnu::noinline]] auto pin_request() -> void {
    require(root()==kernel_root && active==L::domain_count && !program.running()
        && program.event()==ProgramEvent::returned && program.value()==42 && frames.used()==8
        && registry.ready(*domains[0].handle) && registry.ready(*domains[1].handle) && !table_ledger,"table request authority");
    table_ledger.emplace(frames,registry,table_scrub,nullptr);
    dormant_tables.emplace(*table_ledger,std::span<std::byte>{reinterpret_cast<std::byte*>(arena+L::stack_frames_offset),16*4096},arena+L::stack_frames_offset);
    table_record("begin");
#ifdef AURORA_TABLE_QUARANTINE
    const auto owner=*domains[1].handle;table_old_incarnation=*registry.incarnation(owner);
    Serial::text("AURORA_TABLE_OWNER: slot=1 incarnation=");Serial::number(table_old_incarnation);Serial::text("\r\n");
#else
    const auto owner=*domains[0].handle;
#endif
#ifdef AURORA_TABLE_EXHAUST
    table_exhaustion(owner);
#endif
    require(table_prepare(*dormant_tables,owner) && frames.used()==13 && table_ledger->used_entries()==3,"dormant construction");
    table_record("sealed");table_readback(owner);
#ifdef AURORA_TABLE_REJECT
    table_corruption(owner);
#endif
#ifndef AURORA_TABLE_QUARANTINE
    const auto snapshot=memory::DormantTableTestAccess::snapshot(*dormant_tables);
    require(dormant_tables->cancel(owner) && frames.used()==8,"never-published table cancellation");
    std::array<std::optional<memory::PageLease>,5> reassigned{};
    for(std::size_t i=0;i<5;++i){auto p=frames.acquire();require(p && *frames.address(*p)==snapshot.pages[i]
        && zero(*frames.address(*p)),"table scrub/reassignment");reassigned[i].emplace(std::move(*p));}
    for(auto& p:reassigned)require(frames.release(*p),"table reassign cleanup");
    table_record("cancelled");
#endif
    require(verify(domains[0]) && verify(domains[1]),"table construction changed domain mappings");
}
[[gnu::noinline]] auto pin_fault_returned() -> void {
    require(root()==kernel_root && active==L::domain_count && !program.running()
        && program.event()==ProgramEvent::bounds && registry.ready(*domains[1].handle),"table fault origin");
#ifdef AURORA_TABLE_QUARANTINE
    table_scrub_failure_armed=true;
    require(!dormant_tables->cancel(*domains[1].handle) && frames.used()==10
        && table_ledger->quarantined_pages()==2 && table_ledger->used_entries()==1,"never-published scrub quarantine");
    require(table_ledger->borrower_dispose(*domains[1].handle)==0,"quarantine released on service fault");
#endif
    table_record("fault-restored");
}
auto pin_retired() -> bool {return table_ledger->reap_dead()==0 && frames.used()==pin_retained();}
[[gnu::noinline]] auto pin_reborn(user::DomainHandle old_owner) -> void {
    require(root()==kernel_root && active==L::domain_count && program.event()==ProgramEvent::returned
        && program.value()==42 && !registry.index(old_owner),"table rebirth authority");
#ifdef AURORA_TABLE_QUARANTINE
    const auto owner=*domains[1].handle;const auto current=registry.incarnation(owner);
    require(current && *current>table_old_incarnation && !dormant_tables->validate(owner)
        && !dormant_tables->cancel(old_owner) && !dormant_tables->cancel(owner) && pin_retained()==2,"old table owner rebound");
    const auto fresh=table_ledger->grant(owner,1);
    require(fresh && frames.used()==11 && table_ledger->cancel(*fresh,owner)
        && frames.used()==10 && pin_retained()==2,"fresh incarnation loan cancellation");
    Serial::text("AURORA_TABLE_RESTART: slot=1 old=");Serial::number(table_old_incarnation);
    Serial::text(" current=");Serial::number(*current);Serial::text(" stale_owner=1 fresh_cancel=1 retained=2\r\n");
    table_record("service-reborn");
#else
    require(!dormant_tables->validate(old_owner),"old table seal rebound");table_record("reborn");
#endif
}
auto pin_final() -> void {
    require(table_ledger->reap_dead()==0 && frames.used()==pin_retained()
        && table_ledger->pinned_pages()==pin_retained(),"table final accounting");
#ifdef AURORA_TABLE_QUARANTINE
    require(pin_retained()==2 && !zero(table_quarantine_pages[0]) && !zero(table_quarantine_pages[1]),"quarantined table bytes lost");
#endif
    table_record("final");Serial::text("AURORA_TABLE_OK: scope=cpu-only\r\n");
}
