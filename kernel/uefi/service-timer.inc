// Trusted single-BSP xAPIC adapter. All addresses come from validated admission.
constexpr U64 timer_vector=64;
bool timer_ready{},timer_armed{},timer_draining{},timer_exhausted{};
U64 timer_epoch{},timer_owner_epoch{};
unsigned timer_remaining{},timer_ticks{},timer_resumes{},timer_drains{},timer_context_hits{},timer_compiled_hits{};
std::optional<user::DomainHandle> timer_owner;
auto timer_read(unsigned offset) -> std::uint32_t { return *reinterpret_cast<volatile std::uint32_t*>(LocalApicAdmission::virtual_address+offset); }
auto timer_write(unsigned offset,std::uint32_t value) -> void {
    *reinterpret_cast<volatile std::uint32_t*>(LocalApicAdmission::virtual_address+offset)=value;
    static_cast<void>(timer_read(0x20));
}
auto read_msr(std::uint32_t index) -> U64 { std::uint32_t low,high; asm volatile("rdmsr":"=a"(low),"=d"(high):"c"(index)); return (U64{high}<<32)|low; }
auto irq_off() -> bool { U64 flags; asm volatile("pushfq; pop %0":"=r"(flags)); return (flags&0x200)==0; }
auto timer_quiet(unsigned bank,bool permit) -> bool {
    for (unsigned part=0;part<8;++part) {
        const auto allowed=permit && part==timer_vector/32 ? 1U<<(timer_vector%32) : 0;
        if (timer_read(bank+part*16)&~allowed) return false;
    }
    return true;
}
auto timer_pending() -> bool { return (timer_read(0x200+(timer_vector/32)*16)&(1U<<(timer_vector%32)))!=0; }
auto timer_stop() -> bool {
    if (!timer_ready || !irq_off()) return false;
    timer_write(0x320,0x10000|timer_vector); timer_write(0x380,0);
    return timer_read(0x390)==0 && (timer_read(0x320)&0x700ff)==(0x10000|timer_vector);
}
auto timer_arm() -> bool {
    if (!timer_ready || !irq_off() || timer_draining || !timer_quiet(0x100,false) || !timer_quiet(0x200,false)) return false;
    timer_write(0x320,timer_vector); timer_write(0x380,20000);
    return (timer_read(0x320)&0x700ff)==timer_vector;
}
auto timer_acknowledge() -> bool {
    if (!timer_ready || !irq_off() || !(timer_read(0x100+(timer_vector/32)*16)&(1U<<(timer_vector%32)))
        || !timer_quiet(0x100,true) || !timer_quiet(0x200,true) || !timer_stop()) return false;
    timer_write(0xb0,0);
    return timer_quiet(0x100,false);
}
extern const std::byte service_drain_begin asm("uefi_service_drain_begin");
extern const std::byte service_drain_end asm("uefi_service_drain_end");
__attribute__((noinline)) auto timer_drain() -> bool {
    if (root()!=kernel_root || !irq_off() || !timer_stop() || !timer_quiet(0x100,false) || !timer_quiet(0x200,true)) return false;
    if (timer_pending() && (!timer_armed || !timer_owner || timer_owner_epoch!=timer_epoch || !registry.index(*timer_owner))) return false;
    timer_draining=true;
    for (unsigned count=0;timer_pending() && count<10000;++count)
        asm volatile(".global uefi_service_drain_begin\nuefi_service_drain_begin:\nsti\nnop\nnop\ncli\n.global uefi_service_drain_end\nuefi_service_drain_end:":::"memory");
    timer_draining=false;
    return irq_off() && timer_quiet(0x100,false) && timer_quiet(0x200,false);
}
[[maybe_unused]] auto force_timer_pending() -> void {
    bool seen=timer_pending();
    if (!seen) {
        require(timer_arm(),"pending probe arm");
        for (unsigned count=0;count<1000000;++count) if (timer_pending()) { seen=true; break; }
    }
    require(seen && timer_stop() && timer_pending(),"pending probe latch");
    Serial::text("AURORA_UEFI_TIMER_PENDING: epoch="); Serial::number(timer_owner_epoch); Serial::text("\r\n");
}
auto timer_finish() -> void {
    require(root()==kernel_root && active==2 && timer_armed && timer_drain(),"timer terminal drain");
    Serial::text("AURORA_UEFI_TIMER_QUIET: epoch="); Serial::number(timer_owner_epoch); Serial::text(" ticks="); Serial::number(timer_ticks);
    Serial::text(" drains="); Serial::number(timer_drains); Serial::text(" compiled="); Serial::number(timer_compiled_hits); Serial::text(" context="); Serial::number(timer_context_hits); Serial::text(" root="); Serial::number(root()); Serial::text("\r\n");
    timer_armed=false; timer_owner.reset(); timer_owner_epoch=0;
}
auto initialize_service_timer() -> void {
    require(root()==kernel_root && irq_off() && discovered_topology().has_value(),"timer discovery boundary");
    std::uint32_t a,b,c,d; asm volatile("cpuid":"=a"(a),"=b"(b),"=c"(c),"=d"(d):"a"(1),"c"(0));
    const auto leaf_ebx=b;
#ifdef AURORA_BUDGET_NOAPIC
    d&=~(1U<<9);
#endif
    const auto leaf_edx=d;
    require((leaf_edx&((1U<<5)|(1U<<9)|(1U<<16)))==((1U<<5)|(1U<<9)|(1U<<16)),"timer aperture admission");
    asm volatile("cpuid":"=a"(a),"=b"(b),"=c"(c),"=d"(d):"a"(0x80000008U),"c"(0));
    auto control=read_msr(0x1b),pat=read_msr(0x277);
#ifdef AURORA_BUDGET_DISCOVERY
    control^=0x1000;
#endif
#ifdef AURORA_BUDGET_CACHE
    pat^=6ULL<<24;
#endif
    const auto admitted=LocalApicAdmission::authorize(*discovered_topology(),view(arena+Handoff::map_offset,handoff->get(32)),handoff->get(40),static_cast<std::uint32_t>(handoff->get(48,4)),arena,a&255,leaf_edx,leaf_ebx,control,pat);
    require(admitted.has_value(),"timer aperture admission");
    interrupt_admission.emplace(*admitted);
    const PageTables tables{kernel_root,static_cast<std::size_t>(handoff->get(96))};
    const auto slot=tables.interrupt_slot(); require(slot && *slot==0,"timer empty mapping");
    *slot=LocalApicAdmission::physical_address|LocalApicAdmission::leaf_flags;
    asm volatile("invlpg (%0)"::"r"(LocalApicAdmission::virtual_address):"memory");
#ifdef AURORA_BUDGET_ALIAS
    slot[1]=*slot;
#endif
    require(tables.verify(arena,*handoff,&*interrupt_admission),"timer mapping tree");
    require(interrupt_admission->matches_registers(timer_read(0x20),timer_read(0x30)),"timer hardware identity");
    const auto version=timer_read(0x30);
    asm volatile("outb %0,$0x21; outb %0,$0xa1"::"a"(std::uint8_t{0xff}):"memory");
    timer_write(0x320,0x10000|timer_vector); timer_write(0x380,0);
    for (const unsigned offset:{0x330U,0x340U,0x350U,0x360U,0x370U}) timer_write(offset,0x10000);
    if (((version>>16)&255)>=6) timer_write(0x2f0,0x10000);
    timer_write(0x80,0); timer_write(0xf0,0x1ff); timer_write(0x3e0,3);
    require(timer_read(0x80)==0 && (timer_read(0xf0)&0x1ff)==0x1ff && (timer_read(0x3e0)&0xb)==3
        && timer_quiet(0x100,false) && timer_quiet(0x200,false),"timer initial quiescence");
    timer_ready=true;
    Serial::text("AURORA_UEFI_TIMER_READY: physical="); Serial::number(LocalApicAdmission::physical_address);
    Serial::text(" virtual="); Serial::number(LocalApicAdmission::virtual_address); Serial::text(" id="); Serial::number(timer_read(0x20)>>24);
    Serial::text(" root="); Serial::number(root()); Serial::text("\r\n");
}
auto timer_begin(unsigned index) -> void {
    require(index==1 && selected_phase==ipc::Phase::service && mailbox->state()==ipc::State::delivered
        && registry.active(*domains[index].handle) && !timer_armed && timer_epoch!=UINT64_MAX,"timer run authority");
    timer_owner=*domains[index].handle; timer_owner_epoch=++timer_epoch; timer_ticks=0; timer_resumes=0; timer_drains=0; timer_context_hits=0; timer_compiled_hits=0;
    timer_exhausted=false; timer_remaining=launch[0]==5 ? 3 : 128; timer_armed=true;
    require(timer_arm(),"timer arm");
    Serial::text("AURORA_UEFI_TIMER_ARM: epoch="); Serial::number(timer_owner_epoch); Serial::text(" budget="); Serial::number(timer_remaining);
    Serial::text(" root="); Serial::number(root()); Serial::text("\r\n");
}
auto service_timer_interrupt(U64 vector,U64 error,U64 pc,U64 cs,U64 frame) -> std::optional<U64> {
    if (vector!=timer_vector) return std::nullopt;
    if (timer_draining) {
        require(error==0 && cs==8 && root()==kernel_root && active==2 && irq_off()
            && timer_armed && timer_owner && timer_owner_epoch==timer_epoch && registry.ready(*timer_owner)
            && frame>=arena+Handoff::stack_bottom && frame<=arena+Handoff::stack_top-176 && frame%8==0
            && pc>=reinterpret_cast<U64>(&service_drain_begin) && pc<=reinterpret_cast<U64>(&service_drain_end),"timer drain interrupt authority");
        const Bytes captured{view(frame,176)};
        const auto saved_flags=captured.get(152),saved_stack=captured.get(160);
        require(captured.get(168)==0x10 && saved_stack>=arena+Handoff::stack_bottom && saved_stack<=arena+Handoff::stack_top
            && saved_stack%8==0 && (saved_flags&0x202)==0x202
            && (saved_flags&((3ULL<<12)|(1ULL<<14)|(1ULL<<17)|(1ULL<<8)|(1ULL<<10)))==0
            && timer_acknowledge(),"timer drain frame/ISR authority");
        ++timer_drains;
        Serial::text("AURORA_UEFI_TIMER_DRAIN: epoch="); Serial::number(timer_owner_epoch); Serial::text(" root="); Serial::number(root()); Serial::text(" ss="); Serial::number(captured.get(168)); Serial::text("\r\n");
        return 0;
    }
    require(active==1 && domains[1].handle && timer_owner && registry.active(*timer_owner)
        && registry.active(*domains[1].handle) && root()==domains[1].tables->root() && selected_phase==ipc::Phase::service
        && mailbox->state()==ipc::State::delivered && timer_armed && timer_owner_epoch==timer_epoch && timer_owner_epoch!=0
        && timer_remaining!=0 && saved_rsp%8==0 && saved_rsp>=arena+Handoff::stack_bottom && saved_rsp<=arena+Handoff::stack_top-56
        && frame>=arena+L::rsp0_bottom && frame<=arena+L::rsp0_top-176 && frame%8==0,"timer active origin");
    const auto context=ServiceContext::capture(std::span<const U64>{reinterpret_cast<const U64*>(frame),22},frame,*domains[1].contract);
    require(context && context->timer_frame(*domains[1].contract) && error==0 && pc==context->words()[17]
        && cs==context->words()[18] && timer_acknowledge(),"timer frame/ISR authority");
    bool context_sample=false;
    if (pc>=images::bounds_compiled_begin && pc<images::bounds_compiled_end) ++timer_compiled_hits;
#ifdef AURORA_BUDGET_CONTEXT
    if (pc>=images::bounds_context_begin && pc<=images::bounds_context_end) {
        constexpr std::array<U64,15> sentinels{255,238,221,204,187,170,153,136,119,102,85,68,51,34,17};
        for (unsigned index=0;index<15;++index) require(context->words()[index]==sentinels[index],"timer GPR preservation");
        require((context->words()[19]&0x400)!=0,"timer DF preservation"); ++timer_context_hits; context_sample=true;
    }
#endif
    --timer_remaining; ++timer_ticks;
    Serial::text("AURORA_UEFI_TIMER_TICK: epoch="); Serial::number(timer_owner_epoch); Serial::text(" used="); Serial::number(timer_ticks);
    Serial::text(" remaining="); Serial::number(timer_remaining); Serial::text(" pc="); Serial::number(pc);
    Serial::text(" flags="); Serial::number(context->words()[19]); Serial::text("\r\n");
    if (context_sample) {
        Serial::text("AURORA_UEFI_TIMER_CONTEXT: epoch="); Serial::number(timer_owner_epoch); Serial::text(" tick="); Serial::number(timer_ticks);
        Serial::text(" registers=15 df=1\r\n");
    }
    if (timer_remaining!=0) {
        ++timer_resumes; require(timer_arm(),"timer resume arm"); return 0;
    }
    require(program.cancel(),"timer run cancellation"); timer_exhausted=true;
    asm volatile("mov %0,%%cr3"::"r"(kernel_root):"memory");
    require(root()==kernel_root && registry.deactivate(*domains[1].handle),"timer kernel restoration");
    active=2;
    return 1;
}
