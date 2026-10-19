// Trusted single-BSP xAPIC adapter. All addresses come from validated admission.
constexpr U64 timer_vector = 64;
bool timer_ready{}, timer_armed{}, timer_draining{}, timer_exhausted{};
U64 timer_epoch{}, timer_owner_epoch{};
#if defined(AURORA_USER_RESUME) || defined(AURORA_BLOCKING_CALL)
U64 timer_epoch_watermark{};
#endif
unsigned timer_initial{}, timer_remaining{}, timer_ticks{}, timer_resumes{}, timer_drains{}, timer_context_hits{},
    timer_compiled_hits{};
std::optional<user::DomainHandle> timer_owner;
#if defined(AURORA_USER_RESUME) || defined(AURORA_BLOCKING_CALL) || defined(AURORA_CONSOLE_REGION)
auto save_parked_run(ParkedRun &saved, const ServiceContext &context) -> void {
    saved.context.emplace(context);
    saved.remaining = timer_remaining;
    saved.ticks = timer_ticks;
    saved.resumes = timer_resumes;
    saved.compiled = timer_compiled_hits;
    saved.contexts = timer_context_hits;
}
// Mechanism-specific authority and frame checks precede this common restore.
[[nodiscard]] auto restore_parked_run(const ParkedRun &saved) -> U64 {
    timer_remaining = saved.remaining;
    timer_ticks = saved.ticks;
    timer_resumes = saved.resumes;
    timer_compiled_hits = saved.compiled;
    timer_context_hits = saved.contexts;
    timer_drains = 0;
    timer_exhausted = false;
    const auto frame = saved.context->frame();
    auto *words = reinterpret_cast<U64 *>(frame);
    for (std::size_t i = 0; i < ServiceContext::word_count; ++i)
        words[i] = saved.context->words()[i];
    return frame;
}
auto park_run(const user::DomainHandle &owner) -> void {
    require(program.cancel(), "park active tracker");
    asm volatile("mov %0,%%cr3" ::"r"(kernel_root) : "memory");
    require(registry.deactivate(owner), "park owner deactivation");
    active = L::domain_count;
}
auto activate_parked_run(unsigned index) -> void {
    auto &domain = domains[index];
    require(program.begin(*domain.contract) && registry.activate(*domain.handle), "resume active owner");
    active = index;
    const auto selected = domain.tables->root();
    asm volatile("mov %0,%%cr3" ::"r"(selected) : "memory");
}
#endif
auto timer_read(unsigned offset) -> std::uint32_t {
    return LocalApicTimerIo::read(offset);
}
auto read_msr(std::uint32_t index) -> U64 {
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(index));
    return (U64{high} << 32) | low;
}
auto irq_off() -> bool {
    return LocalApicTimerIo::irq_off();
}
auto timer_quiet(unsigned bank, bool permit) -> bool {
    return LocalApicTimerIo::quiet(bank, permit);
}
auto timer_pending() -> bool {
    return LocalApicTimerIo::pending();
}
auto timer_stop() -> bool {
    return timer_ready && LocalApicTimerIo::stop();
}
auto timer_arm() -> bool {
    return timer_ready && !timer_draining && LocalApicTimerIo::arm(20000);
}
auto timer_acknowledge() -> bool {
    return timer_ready && LocalApicTimerIo::acknowledge();
}
extern const std::byte service_drain_begin asm("uefi_service_drain_begin");
extern const std::byte service_drain_end asm("uefi_service_drain_end");
__attribute__((noinline)) auto timer_drain() -> bool {
    if (root() != kernel_root || !irq_off() || !timer_stop() || !timer_quiet(0x100, false) || !timer_quiet(0x200, true))
        return false;
    if (timer_pending() &&
        (!timer_armed || !timer_owner || timer_owner_epoch != timer_epoch || !registry.index(*timer_owner)))
        return false;
    timer_draining = true;
    for (unsigned count = 0; timer_pending() && count < 10000; ++count)
        asm volatile(".global uefi_service_drain_begin\nuefi_service_drain_begin:\nsti\nnop\nnop\ncli\n.global "
                     "uefi_service_drain_end\nuefi_service_drain_end:" ::
                         : "memory");
    timer_draining = false;
    return irq_off() && timer_quiet(0x100, false) && timer_quiet(0x200, false);
}
[[maybe_unused]] auto force_timer_pending() -> void {
    bool seen = timer_pending();
    if (!seen) {
        require(timer_arm(), "pending probe arm");
        for (unsigned count = 0; count < 1000000; ++count)
            if (timer_pending()) {
                seen = true;
                break;
            }
    }
    require(seen && timer_stop() && timer_pending(), "pending probe latch");
    Serial::text("AURORA_UEFI_TIMER_PENDING: epoch=");
    Serial::number(timer_owner_epoch);
    Serial::text("\r\n");
}
auto timer_finish() -> void {
    require(root() == kernel_root && active == L::domain_count && timer_armed && timer_drain(), "timer terminal drain");
    Serial::text("AURORA_UEFI_TIMER_QUIET: epoch=");
    Serial::number(timer_owner_epoch);
    Serial::text(" ticks=");
    Serial::number(timer_ticks);
    Serial::text(" drains=");
    Serial::number(timer_drains);
    Serial::text(" compiled=");
    Serial::number(timer_compiled_hits);
    Serial::text(" context=");
    Serial::number(timer_context_hits);
    Serial::text(" root=");
    Serial::number(root());
    Serial::text("\r\n");
    timer_armed = false;
    timer_owner.reset();
    timer_owner_epoch = 0;
#ifdef AURORA_UEFI_USER_BUDGET
    run_authority.reset();
#endif
}
auto initialize_service_timer() -> void {
    require(root() == kernel_root && irq_off() && discovered_topology().has_value(), "timer discovery boundary");
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    const auto leaf_ebx = b;
#ifdef AURORA_BUDGET_NOAPIC
    d &= ~(1U << 9);
#endif
    const auto leaf_edx = d;
    require((leaf_edx & ((1U << 5) | (1U << 9) | (1U << 16))) == ((1U << 5) | (1U << 9) | (1U << 16)),
            "timer aperture admission");
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
    auto control = read_msr(0x1b), pat = read_msr(0x277);
#ifdef AURORA_BUDGET_DISCOVERY
    control ^= 0x1000;
#endif
#ifdef AURORA_BUDGET_CACHE
    pat ^= 6ULL << 24;
#endif
    const auto admitted = LocalApicAdmission::authorize(*discovered_topology(),
                                                        view(arena + Handoff::map_offset, handoff->get(32)),
                                                        handoff->get(40),
                                                        static_cast<std::uint32_t>(handoff->get(48, 4)),
                                                        arena,
                                                        a & 255,
                                                        leaf_edx,
                                                        leaf_ebx,
                                                        control,
                                                        pat);
    require(admitted.has_value(), "timer aperture admission");
    interrupt_admission.emplace(*admitted);
    const PageTables tables{kernel_root, static_cast<std::size_t>(handoff->get(96))};
    const auto slot = tables.interrupt_slot();
    require(slot && *slot == 0, "timer empty mapping");
    *slot = LocalApicAdmission::physical_address | LocalApicAdmission::leaf_flags;
    asm volatile("invlpg (%0)" ::"r"(LocalApicAdmission::virtual_address) : "memory");
#ifdef AURORA_BUDGET_ALIAS
    slot[1] = *slot;
#endif
    require(tables.verify(arena, *handoff, &*interrupt_admission), "timer mapping tree");
    require(interrupt_admission->matches_registers(timer_read(0x20), timer_read(0x30)), "timer hardware identity");
    require(LocalApicTimerIo::initialize(timer_read(0x30)), "timer initial quiescence");
    timer_ready = true;
    Serial::text("AURORA_UEFI_TIMER_READY: physical=");
    Serial::number(LocalApicAdmission::physical_address);
    Serial::text(" virtual=");
    Serial::number(LocalApicAdmission::virtual_address);
    Serial::text(" id=");
    Serial::number(timer_read(0x20) >> 24);
    Serial::text(" root=");
    Serial::number(root());
    Serial::text("\r\n");
}
auto timer_begin(unsigned index) -> void {
    using namespace std::literals::string_view_literals;
#if defined(AURORA_USER_RESUME) || defined(AURORA_BLOCKING_CALL)
    require(timer_epoch_watermark != UINT64_MAX, "run epoch exhaustion");
    const auto next_epoch = ++timer_epoch_watermark;
#else
    const auto next_epoch = timer_epoch + 1;
#endif
#ifdef AURORA_OWNED_TEXT
    require(index == 0 && domains[0].handle && text_owner && registry.index(*text_owner) == 0 &&
                registry.active(*text_owner) && root() == domains[0].tables->root() && !timer_armed &&
                timer_epoch != UINT64_MAX && text_region.is_open() && !text_region.faulted(),
            "text run authority");
    text_epoch = next_epoch;
#elif defined(AURORA_UEFI_USER_BUDGET)
    require(index < L::domain_count && domains[index].handle && selected_client < 2 && !timer_armed &&
                timer_epoch != UINT64_MAX,
            "user timer run boundary");
    const auto budget =
#ifdef AURORA_FILE_CALL
        file_wc ? 128U :
#endif
        (launch[0] == 5 || launch[0] == 6 || launch[0] == 7) ? 3U
                                                             : 128U;
    auto authorization = SelectedRunAuthority::authorize(registry,
                                                         *domains[index].handle,
                                                         selected_role,
                                                         selected_phase,
                                                         selected_client,
                                                         transaction,
                                                         launch[0],
                                                         arena,
                                                         root(),
                                                         *domains[index].contract,
                                                         next_epoch,
                                                         budget);
    require(authorization.has_value(), "user timer immutable authority");
    run_authority.emplace(*authorization);
    require(selected_role != SelectedRunAuthority::Role::service || service_delivered(), "user service selection");
#else
    require(index == 1 && selected_phase == ipc::Phase::service && service_delivered() &&
                registry.active(*domains[index].handle) && !timer_armed && timer_epoch != UINT64_MAX,
            "timer run authority");
#endif
    timer_owner = *domains[index].handle;
    timer_owner_epoch = timer_epoch = next_epoch;
    timer_ticks = 0;
    timer_resumes = 0;
    timer_drains = 0;
    timer_context_hits = 0;
    timer_compiled_hits = 0;
    timer_exhausted = false;
#ifdef AURORA_OWNED_TEXT
    timer_remaining = 128;
#elif defined(AURORA_UEFI_USER_BUDGET)
    timer_remaining = run_authority->budget();
#else
    timer_remaining = launch[0] == 5 ? 3 : 128;
#endif
    timer_initial = timer_remaining;
#ifdef AURORA_FILE_CALL
    if (file_wc && index == 1) {
        require(file_service_used < timer_initial, "wc cumulative service allowance");
        timer_ticks = file_service_used;
        timer_remaining = timer_initial - timer_ticks;
    }
#endif
    timer_armed = true;
    require(timer_arm(), "timer arm");
#ifdef AURORA_UEFI_USER_BUDGET
    Serial::text("AURORA_UEFI_USER_RUN: epoch=");
    Serial::number(run_authority->epoch());
    Serial::text(" role=");
    Serial::text(run_authority->role() == SelectedRunAuthority::Role::client ? "client"sv : "service"sv);
    Serial::text(" phase=");
    Serial::text(run_authority->phase() == ipc::Phase::request   ? "request"sv
                 : run_authority->phase() == ipc::Phase::service ? "service"sv
                                                                 : "completion"sv);
    Serial::text(" client=");
    Serial::number(run_authority->client());
    Serial::text(" transaction=");
    Serial::number(run_authority->transaction());
    Serial::text(" source=");
    Serial::number(run_authority->source_phase());
    Serial::text(" root=");
    Serial::number(run_authority->root());
    Serial::text("\r\n");
#endif
    Serial::text("AURORA_UEFI_TIMER_ARM: epoch=");
    Serial::number(timer_owner_epoch);
    Serial::text(" budget=");
    Serial::number(timer_remaining);
    Serial::text(" root=");
    Serial::number(root());
    Serial::text("\r\n");
}
#ifdef AURORA_FILE_CALL
// Conservatively charge the discarded partial timer interval before publication.
// Hardware IRQs and boundary charges share the same checked 128-unit allowance.
[[nodiscard]] auto file_boundary_debit() -> bool {
    require(file_wc && timer_armed && !timer_exhausted && timer_remaining && timer_initial == 128 &&
                timer_ticks + timer_remaining == 128,
            "wc boundary allowance");
#ifdef AURORA_FILE_CALL_BUDGET
    // Test-only conservative charging, never a quota reset or simulated IRQ.
    // Exercise exhaustion at the actual pre-publication boundaries after two bytes.
    if ((file_budget_probe == 36 && active == 0 && file_call_count == 2) ||
        (file_budget_probe == 37 && active == 1 && file_call_count == 3)) {
        Serial::text(active == 0 ? std::string_view{"AURORA_WC_BOUNDARY_PROBE: role=client\r\n"}
                                 : std::string_view{"AURORA_WC_BOUNDARY_PROBE: role=service\r\n"});
        while (timer_ticks < 127) {
            const auto injected =
                BudgetTransition::decode(language_budget_tick(timer_initial, timer_remaining, timer_ticks),
                                         timer_initial,
                                         timer_remaining,
                                         timer_ticks);
            require(injected && injected->resume(), "wc probe conservative charge");
            timer_ticks = injected->used();
            timer_remaining = injected->remaining();
            Serial::text("AURORA_WC_DEBIT: epoch=");
            Serial::number(timer_epoch);
            Serial::text(" used=");
            Serial::number(timer_ticks);
            Serial::text(" remaining=");
            Serial::number(timer_remaining);
            Serial::text("\r\n");
        }
    }
#endif
    const auto encoded = language_budget_tick(timer_initial, timer_remaining, timer_ticks);
    const auto next = BudgetTransition::decode(encoded, timer_initial, timer_remaining, timer_ticks);
    require(next.has_value(), "wc boundary policy");
    timer_ticks = next->used();
    timer_remaining = next->remaining();
    Serial::text("AURORA_WC_DEBIT: epoch=");
    Serial::number(timer_epoch);
    Serial::text(" used=");
    Serial::number(timer_ticks);
    Serial::text(" remaining=");
    Serial::number(timer_remaining);
    Serial::text("\r\n");
    timer_exhausted = !next->resume();
    return !timer_exhausted;
}
#endif
auto service_timer_interrupt(U64 vector, U64 error, U64 pc, U64 cs, U64 frame) -> std::optional<U64> {
    if (vector != timer_vector)
        return std::nullopt;
    if (timer_draining) {
        require(error == 0 && cs == 8 && root() == kernel_root && active == L::domain_count && irq_off() &&
                    timer_armed && timer_owner && timer_owner_epoch == timer_epoch && registry.ready(*timer_owner) &&
                    frame >= arena + Handoff::stack_bottom && frame <= arena + Handoff::stack_top - 176 &&
                    frame % 8 == 0 && pc >= reinterpret_cast<U64>(&service_drain_begin) &&
                    pc <= reinterpret_cast<U64>(&service_drain_end),
                "timer drain interrupt authority");
#ifdef AURORA_OWNED_TEXT
        require(text_owner && registry.index(*text_owner) == 0 && registry.index(*timer_owner) == 0 &&
                    text_epoch == timer_epoch,
                "text drain owner epoch");
#endif
#ifdef AURORA_UEFI_USER_BUDGET
        require(run_authority && run_authority->ready_owner(registry, *timer_owner, timer_owner_epoch),
                "user drain owner epoch");
#endif
        const Bytes captured{view(frame, 176)};
        const auto saved_flags = captured.get(152), saved_stack = captured.get(160);
        require(captured.get(168) == 0x10 && saved_stack >= arena + Handoff::stack_bottom &&
                    saved_stack <= arena + Handoff::stack_top && saved_stack % 8 == 0 &&
                    (saved_flags & 0x202) == 0x202 &&
                    (saved_flags & ((3ULL << 12) | (1ULL << 14) | (1ULL << 17) | (1ULL << 8) | (1ULL << 10))) == 0 &&
                    timer_acknowledge(),
                "timer drain frame/ISR authority");
        ++timer_drains;
        Serial::text("AURORA_UEFI_TIMER_DRAIN: epoch=");
        Serial::number(timer_owner_epoch);
        Serial::text(" root=");
        Serial::number(root());
        Serial::text(" ss=");
        Serial::number(captured.get(168));
        Serial::text("\r\n");
        return 0;
    }
#ifdef AURORA_OWNED_TEXT
    require(text_active() && saved_rsp % 8 == 0 && saved_rsp >= arena + Handoff::stack_bottom &&
                saved_rsp <= arena + Handoff::stack_top - 56,
            "text timer authority");
    const auto &interrupted_contract = *domains[0].contract;
#elif defined(AURORA_UEFI_USER_BUDGET)
    require(active < L::domain_count && domains[active].handle && timer_owner && run_authority &&
                run_authority->matches_active(registry,
                                              *domains[active].handle,
                                              selected_role,
                                              selected_phase,
                                              selected_client,
                                              transaction,
                                              launch[0],
                                              arena,
                                              root(),
                                              *domains[active].contract,
                                              timer_owner_epoch) &&
                registry.active(*timer_owner) && timer_armed && timer_owner_epoch == timer_epoch &&
                timer_remaining != 0 && (selected_role != SelectedRunAuthority::Role::service || service_delivered()) &&
                saved_rsp % 8 == 0 && saved_rsp >= arena + Handoff::stack_bottom &&
                saved_rsp <= arena + Handoff::stack_top - 56 && frame >= arena + L::rsp0_bottom &&
                frame <= arena + L::rsp0_top - 176 && frame % 8 == 0,
            "user timer active authority");
    const auto &interrupted_contract = run_authority->contract();
#else
    require(active == 1 && domains[1].handle && timer_owner && registry.active(*timer_owner) &&
                registry.active(*domains[1].handle) && root() == domains[1].tables->root() &&
                selected_phase == ipc::Phase::service && service_delivered() && timer_armed &&
                timer_owner_epoch == timer_epoch && timer_owner_epoch != 0 && timer_remaining != 0 &&
                saved_rsp % 8 == 0 && saved_rsp >= arena + Handoff::stack_bottom &&
                saved_rsp <= arena + Handoff::stack_top - 56 && frame >= arena + L::rsp0_bottom &&
                frame <= arena + L::rsp0_top - 176 && frame % 8 == 0,
            "timer active origin");
    const auto &interrupted_contract = *domains[1].contract;
#endif
    const auto context = ServiceContext::capture(
        std::span<const U64>{reinterpret_cast<const U64 *>(frame), 22}, frame, interrupted_contract);
    require(context && context->timer_frame(interrupted_contract) && error == 0 && pc == context->words()[17] &&
                cs == context->words()[18] && timer_acknowledge(),
            "timer frame/ISR authority");
    bool context_sample = false;
#ifdef AURORA_UEFI_USER_BUDGET
#if defined(AURORA_UEFI_PROGRAM_CONSOLE) || defined(AURORA_BLOCKING_CALL)
    const std::array<U64, 2> compiled_begin{images::clean_compiled_begin, images::bounds_compiled_begin};
    const std::array<U64, 2> compiled_end{images::clean_compiled_end, images::bounds_compiled_end};
#else
    const std::array<U64, 3> compiled_begin{
        images::clean_compiled_begin, images::bounds_compiled_begin, images::peer_compiled_begin};
    const std::array<U64, 3> compiled_end{
        images::clean_compiled_end, images::bounds_compiled_end, images::peer_compiled_end};
#endif
    if (pc >= compiled_begin[active] && pc < compiled_end[active])
        ++timer_compiled_hits;
#elif defined(AURORA_OWNED_TEXT)
    if (pc >= images::clean_compiled_begin && pc < images::clean_compiled_end)
        ++timer_compiled_hits;
#else
    if (pc >= images::bounds_compiled_begin && pc < images::bounds_compiled_end)
        ++timer_compiled_hits;
#endif
#ifdef AURORA_USER_CONTEXT
    if (active == 0 && images::clean_context_begin && pc >= images::clean_context_begin &&
        pc <= images::clean_context_end) {
        constexpr std::array<U64, 15> sentinels{255, 238, 221, 204, 187, 170, 153, 136, 119, 102, 85, 68, 51, 34, 17};
        for (unsigned index = 0; index < 15; ++index)
            require(context->words()[index] == sentinels[index], "user timer GPR preservation");
        require((context->words()[19] & 0x400) != 0, "user timer DF preservation");
        ++timer_context_hits;
        context_sample = true;
    }
#endif
#ifdef AURORA_BUDGET_CONTEXT
    if (pc >= images::bounds_context_begin && pc <= images::bounds_context_end) {
        constexpr std::array<U64, 15> sentinels{255, 238, 221, 204, 187, 170, 153, 136, 119, 102, 85, 68, 51, 34, 17};
        for (unsigned index = 0; index < 15; ++index)
            require(context->words()[index] == sentinels[index], "timer GPR preservation");
        require((context->words()[19] & 0x400) != 0, "timer DF preservation");
        ++timer_context_hits;
        context_sample = true;
    }
#endif
    U64 policy_initial = timer_initial, policy_remaining = timer_remaining, policy_used = timer_ticks;
#ifdef AURORA_BUDGET_POLICY_ZERO
    policy_initial = 0;
#endif
#ifdef AURORA_BUDGET_POLICY_COUNTS
    policy_used = 1; // First accepted frame has remaining==initial and used==0.
#endif
#ifdef AURORA_BUDGET_POLICY_WIDE
    policy_remaining = UINT64_MAX;
    policy_used = UINT64_MAX;
#endif
    auto encoded = language_budget_tick(policy_initial, policy_remaining, policy_used);
#ifdef AURORA_BUDGET_POLICY_OUTPUT
    // Test-only owned local input keeps the ordinary decoder branch dynamic.
    const volatile U64 policy_output_reserved_mask = 1ULL << 63;
    encoded |= policy_output_reserved_mask;
#endif
    const auto transition = BudgetTransition::decode(encoded, timer_initial, timer_remaining, timer_ticks);
    require(transition.has_value(), "Aurora budget transition");
    timer_remaining = transition->remaining();
    timer_ticks = transition->used();
    Serial::text("AURORA_UEFI_TIMER_TICK: epoch=");
    Serial::number(timer_owner_epoch);
    Serial::text(" used=");
    Serial::number(timer_ticks);
    Serial::text(" remaining=");
    Serial::number(timer_remaining);
    Serial::text(" pc=");
    Serial::number(pc);
    Serial::text(" flags=");
    Serial::number(context->words()[19]);
    Serial::text("\r\n");
    if (context_sample) {
        Serial::text("AURORA_UEFI_TIMER_CONTEXT: epoch=");
        Serial::number(timer_owner_epoch);
        Serial::text(" tick=");
        Serial::number(timer_ticks);
        Serial::text(" registers=15 df=1\r\n");
    }
    if (transition->resume()) {
#ifdef AURORA_USER_RESUME
        if (active == 0 && timer_ticks == 1) {
            auto &saved = domains[active].continuation;
            require(!saved.context && !saved.authority && run_authority && timer_stop(), "single suspended run");
            save_parked_run(saved, *context);
            saved.authority.emplace(*run_authority);
            saved.launch = launch;
            park_run(*domains[active].handle);
            return 1;
        }
#endif
        ++timer_resumes;
        require(timer_arm(), "timer resume arm");
        return 0;
    }
    require(program.cancel(), "timer run cancellation");
    timer_exhausted = true;
    const auto interrupted = active;
    asm volatile("mov %0,%%cr3" ::"r"(kernel_root) : "memory");
    require(root() == kernel_root && registry.deactivate(*domains[interrupted].handle), "timer kernel restoration");
    active = L::domain_count;
    return 1;
}
