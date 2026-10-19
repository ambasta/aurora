// One private bounded allocator binding; no user descriptor conveys authority.
[[nodiscard]] auto text_retirable() -> bool {
    return !text_region.is_open() && !text_region.faulted() && !text_owner && !timer_armed && !program.running() &&
           saved_rsp == 0;
}
[[nodiscard]] auto text_active() -> bool {
    return active == 0 && domains[0].handle && domains[0].contract && text_owner && timer_owner &&
           registry.index(*text_owner) == 0 && registry.index(*timer_owner) == 0 &&
           registry.index(*domains[0].handle) == 0 && registry.active(*text_owner) && registry.active(*timer_owner) &&
           root() == domains[0].tables->root() && irq_off() && timer_armed && !timer_draining && text_epoch != 0 &&
           text_epoch == timer_epoch && timer_owner_epoch == text_epoch && timer_remaining != 0 &&
           timer_initial == timer_remaining + timer_ticks && text_region.is_open() && !text_region.faulted();
}

[[nodiscard, gnu::noinline]] auto text_trap(U64 frame) -> U64 {
    require(text_active(), "text active authority");
    auto *words = reinterpret_cast<U64 *>(frame);
#ifdef AURORA_RUNTIME_FIXTURE
    text_fixture_entry(words);
#endif
    constexpr std::array<U64, 6> sites{images::clean_bytes_allocate_pc,
                                       images::clean_bytes_borrow_length_pc,
                                       images::clean_bytes_at_pc,
                                       images::clean_bytes_set_pc,
                                       images::clean_bytes_resize_pc,
                                       images::clean_bytes_drop_pc};
    std::size_t operation = sites.size();
    for (std::size_t i = 0; i < sites.size(); ++i)
        if (words[17] == sites[i])
            operation = i;
    require(operation < sites.size(), "text exact operation site");
    const auto context =
        ServiceContext::capture_bytes(std::span<const U64>{words, 22}, frame, *domains[0].contract, sites[operation]);
    require(context.has_value(), "text integer frame authority");
    aurora::hosted::bytes::NativeOwner owner{words[8], words[9], static_cast<std::int64_t>(words[11]), words[12]};
    // Allocation has a separate grant and pristine output. A pristine drop is
    // the existing ABI no-op. All other descriptors must name this private region.
    const bool pristine = owner.region == 0 && owner.allocation == 0 && owner.length == 0 && owner.success == 0;
    require(operation == 0 ? words[6] == text_region.id()
                           : owner.region == text_region.id() || (operation == 5 && pristine),
            "text private region binding");
#ifdef AURORA_RUNTIME_FIXTURE
    text_fixture_owner(operation, owner);
#endif
    U64 result = 0;
    if (operation == 0)
        __au_runtime_bytes_allocate(words[6], static_cast<std::int64_t>(words[7]), &owner);
    else if (operation == 1)
        result = static_cast<U64>(__au_runtime_bytes_borrow_length(&owner));
    else if (operation == 2)
        result = __au_runtime_bytes_at(&owner, static_cast<std::int64_t>(words[7]));
    else if (operation == 3)
        result = __au_runtime_bytes_set(&owner, static_cast<std::int64_t>(words[7]), words[6]);
    else if (operation == 4)
        result = __au_runtime_bytes_resize(&owner, static_cast<std::int64_t>(words[7]));
    else
        __au_runtime_bytes_drop(&owner);
    words[8] = owner.region;
    words[9] = owner.allocation;
    words[11] = static_cast<U64>(owner.length);
    words[12] = owner.success;
    words[14] = result;
    // R10 is a CPL3-only address. Preserve it and every other unrelated register.
    // The running timer and original epoch are untouched across this operation.
    return 0;
}

extern "C" [[noreturn]] void __au_runtime_bytes_kernel_fault(std::uint64_t reason) noexcept {
    Serial::text("AURORA_OWNED_TEXT_FAULT: reason=");
    Serial::number(reason);
    Serial::text("\r\n");
    stop("owned text allocator invariant");
}

#ifndef AURORA_CONSOLE_REGION
auto run_owned_text(memory::PhysicalPages &pool) -> void {
#ifdef AURORA_RUNTIME_FIXTURE
    select_fixture(Fixture::text_site, Fixture::text_stale);
#endif
    require(pool.used() == 0, "text exclusive backing pool");
    constexpr std::array<U64, 5> scalars{0x1f642, 0xd800, 1114114, 1114112, 1114113};
    for (const auto scalar : scalars) {
        const auto created = create(0);
        require(created && *created == 0 && !domains[1].handle, "text single domain");
        auto &domain = domains[0];
        require(text_region.open(pool,
                                 view(arena + Handoff::pool_offset, kernel::bytes::Region::backing_bytes),
                                 arena + Handoff::pool_offset,
                                 64),
                "text private quota region");
        text_owner = *domain.handle;
        launch = {text_region.id(), scalar, 0, 0, 0, 0, 0x202};
        require(verify(domain) && program.begin(*domain.contract) && registry.activate(*domain.handle),
                "text entry authority");
        active = 0;
        const auto selected = domain.tables->root();
        asm volatile("mov %0,%%cr3" ::"r"(selected) : "memory");
        timer_begin(0);
        require(enter(domain.contract->entry(), domain.contract->layout().user_stack_top(), launch.data()) == 1,
                "text trusted continuation");
        timer_finish();
        const auto kernel_stack = stack();
        require(kernel_stack >= arena + Handoff::stack_bottom && kernel_stack < arena + Handoff::stack_top &&
                    root() == kernel_root && active == L::domain_count && saved_rsp == 0 && !program.running() &&
                    irq_off() && !timer_armed && !timer_pending() && timer_quiet(0x100, false) &&
                    registry.ready(*text_owner) && registry.index(*text_owner) == 0,
                "text quiescent reclamation boundary");
        const bool abandoned = scalar == 1114112 || scalar == 1114113;
        require(scalar == 1114113 ? timer_exhausted
                                  : !timer_exhausted &&
                                        program.event() == (abandoned ? ProgramEvent::bounds : ProgramEvent::returned),
                "text terminal event");
        require(abandoned || program.value() == (scalar == 0xd800    ? 0
                                                 : scalar == 1114114 ? 65
                                                                     : 70),
                "text live local result");
        const auto before = text_region.metrics();
        require((before.live_allocations != 0) == abandoned && before.quota == 64 && before.peak_used <= 64,
                "text live owner termination");
        require(text_region.revoke_quiescent() && pool.used() == 0 && text_region.metrics().held_pages == 0 &&
                    text_region.metrics().live_allocations == 0 && text_region.metrics().used == 0,
                "text reclaimed owners");
        text_owner.reset();
        text_epoch = 0;
        launch = {};
        require(retire(0) && frames.used() == 0, "text domain retirement");
        Serial::text("AURORA_OWNED_TEXT_CASE: scalar=");
        Serial::number(scalar);
        Serial::text(" abandoned=");
        Serial::number(abandoned);
        Serial::text(" value=");
        Serial::number(program.value());
        Serial::text(" live=");
        Serial::number(before.live_allocations);
        Serial::text(" peak=");
        Serial::number(before.peak_used);
        Serial::text(" ticks=");
        Serial::number(timer_ticks);
        Serial::text(" used=0 pages=0\r\n");
    }
    Serial::text("AURORA_OWNED_TEXT_OK\r\n");
}

#endif
