// CPU-only lease ownership gate. No DMA publication or completion adapter.
// Selected at boot by the runtime fixture image's pin rows.
namespace pin_supervisor {
constinit std::optional<memory::PinLedger> pin_ledger;
std::optional<memory::PinHandle> stale_pin;
U64 old_service_incarnation{};
auto pin_scrub(void *, U64 address, std::size_t bytes) -> bool {
    if (root() != kernel_root || active != L::domain_count || bytes != 4096 ||
        address < arena + L::stack_frames_offset || address >= arena + L::stack_frames_offset + 16 * 4096 ||
        address % 4096)
        return false;
    fill(address, 0);
    return zero(address);
}
auto pin_retained() -> std::size_t {
    return pin_ledger ? pin_ledger->quarantined_pages() : 0;
}
auto pin_record(std::string_view event) -> void {
    Serial::text("AURORA_PIN_STATE: event=");
    Serial::text(event);
    Serial::text(" pool=");
    Serial::number(frames.used());
    Serial::text(" pinned=");
    Serial::number(pin_ledger->pinned_pages());
    Serial::text(" quarantine=");
    Serial::number(pin_ledger->quarantined_pages());
    Serial::text(" entries=");
    Serial::number(pin_ledger->used_entries());
    Serial::text(" root=");
    Serial::number(root());
    Serial::text("\r\n");
}
auto pin_request() -> void {
    require(root() == kernel_root && active == L::domain_count && !program.running() &&
                program.event() == ProgramEvent::returned && program.value() == 42 && frames.used() == 8 &&
                domains[0].handle && domains[1].handle && registry.ready(*domains[0].handle) &&
                registry.ready(*domains[1].handle) && !pin_ledger,
            "pin request authority");
    pin_ledger.emplace(frames, registry, pin_scrub, nullptr);
    pin_record("begin");
    if (fixture == Fixture::runtime_pin_fault) {
        auto token = pin_ledger->grant(*domains[1].handle, 2);
        require(token.has_value(), "fault loan");
        stale_pin = *token;
        old_service_incarnation = *registry.incarnation(*domains[1].handle);
        Serial::text("AURORA_PIN_OWNER: slot=1 incarnation=");
        Serial::number(old_service_incarnation);
        Serial::text("\r\n");
        fill(arena + L::stack_frames_offset + 8 * 4096, 0xa5);
        fill(arena + L::stack_frames_offset + 9 * 4096, 0xa5);
        require(pin_ledger->inject_uncertainty(*token, *domains[1].handle), "test uncertainty authority");
        require(!pin_ledger->cancel(*token, *domains[1].handle), "uncertain loan cancelled");
        pin_record("uncertainty");
    } else if (fixture == Fixture::runtime_pin_cancel) {
        auto token = pin_ledger->grant(*domains[0].handle, 2);
        require(token.has_value(), "clean loan");
        fill(arena + L::stack_frames_offset + 8 * 4096, 0xa5);
        fill(arena + L::stack_frames_offset + 9 * 4096, 0xa5);
        pin_record("loan");
        require(pin_ledger->cancel(*token, *domains[0].handle), "clean cancellation");
        std::array<std::optional<memory::PageLease>, 2> reassigned{};
        for (std::size_t i = 0; i < 2; ++i) {
            auto lease = frames.acquire();
            require(lease.has_value(), "scrub reacquisition");
            require(*frames.address(*lease) == arena + L::stack_frames_offset + (8 + i) * 4096 &&
                        zero(*frames.address(*lease)),
                    "scrub before reassignment");
            reassigned[i].emplace(std::move(*lease));
        }
        for (auto &lease : reassigned)
            require(frames.release(*lease), "scrub lease release");
        pin_record("cancelled");
    } else if (fixture == Fixture::runtime_pin_stale) {
        auto token = pin_ledger->grant(*domains[0].handle, 1);
        require(token.has_value(), "first stale loan");
        stale_pin = *token;
        require(pin_ledger->cancel(*token, *domains[0].handle), "first stale cancellation");
        auto fresh = pin_ledger->grant(*domains[0].handle, 1);
        require(fresh.has_value(), "reused ledger slot");
        require(!pin_ledger->cancel(*stale_pin, *domains[0].handle) && !pin_ledger->cancel(*fresh, *domains[1].handle),
                "stale or foreign cancellation");
        require(pin_ledger->cancel(*fresh, *domains[0].handle), "fresh cancellation");
        pin_record("stale-rejected");
    } else if (fixture == Fixture::runtime_pin_exhaust) {
        std::array<std::optional<memory::PinHandle>, 4> grants{};
        for (auto &grant : grants) {
            grant = pin_ledger->grant(*domains[0].handle, 1);
            require(grant.has_value(), "entry reservation");
        }
        require(!pin_ledger->grant(*domains[0].handle, 1) && frames.used() == 12, "entry exhaustion");
        pin_record("entries-full");
        for (const auto &grant : grants)
            require(pin_ledger->cancel(*grant, *domains[0].handle), "entry cleanup");
        std::array<std::optional<memory::PageLease>, 7> held{};
        for (auto &lease : held) {
            auto next = frames.acquire();
            require(next.has_value(), "pool reservation");
            lease.emplace(std::move(*next));
        }
        fill(arena + L::stack_frames_offset + 15 * 4096, 0xa5);
        require(!pin_ledger->grant(*domains[0].handle, 2) && frames.used() == 15 && pin_ledger->used_entries() == 0 &&
                    zero(arena + L::stack_frames_offset + 15 * 4096),
                "partial pin rollback");
        pin_record("pool-full");
        for (auto &lease : held)
            require(frames.release(*lease), "pool reservation release");
        auto dying = pin_ledger->grant(*domains[1].handle, 2);
        require(dying.has_value(), "borrower disposal loan");
        fill(arena + L::stack_frames_offset + 8 * 4096, 0xa5);
        fill(arena + L::stack_frames_offset + 9 * 4096, 0xa5);
        pin_record("borrower-loan");
    }
    require(verify(domains[0]) && verify(domains[1]), "pin changed domain mappings");
}
auto pin_fault_returned() -> void {
    require(root() == kernel_root && active == L::domain_count && !program.running() &&
                program.event() == ProgramEvent::bounds && registry.ready(*domains[1].handle),
            "pin fault authority");
    if (fixture == Fixture::runtime_pin_exhaust) {
        require(pin_ledger->borrower_dispose(*domains[1].handle) == 1 && frames.used() == 8 &&
                    zero(arena + L::stack_frames_offset + 8 * 4096) && zero(arena + L::stack_frames_offset + 9 * 4096),
                "unpublished borrower disposal");
    } else if (fixture == Fixture::runtime_pin_fault) {
        require(pin_ledger->borrower_dispose(*domains[1].handle) == 0 && frames.used() == 10 &&
                    pin_ledger->quarantined_pages() == 2,
                "uncertain borrower disposal");
    }
    pin_record("fault-restored");
}
auto pin_retired() -> bool {
    return pin_ledger->reap_dead() == 0 && frames.used() == pin_retained();
}
auto pin_reborn(user::DomainHandle old_owner) -> void {
    require(root() == kernel_root && active == L::domain_count && program.event() == ProgramEvent::returned &&
                program.value() == 42 && !registry.index(old_owner),
            "pin rebirth authority");
    if (fixture == Fixture::runtime_pin_stale) {
        auto fresh = pin_ledger->grant(*domains[0].handle, 1);
        require(fresh.has_value(), "reborn owner loan");
        require(!pin_ledger->cancel(*fresh, old_owner) && !pin_ledger->cancel(*stale_pin, *domains[0].handle),
                "old incarnation accepted");
        require(pin_ledger->cancel(*fresh, *domains[0].handle), "reborn owner cancellation");
    }
    if (fixture == Fixture::runtime_pin_fault) {
        require(registry.ready(*domains[1].handle) && verify(domains[0]) && verify(domains[1]),
                "restarted service mappings");
        auto fresh = pin_ledger->grant(*domains[1].handle, 2);
        require(fresh.has_value(), "restarted service loan");
        require(!pin_ledger->cancel(*stale_pin, *domains[1].handle) && !pin_ledger->cancel(*fresh, old_owner),
                "quarantine incarnation rebound");
        require(pin_ledger->cancel(*fresh, *domains[1].handle) && pin_retained() == 2, "fresh service cancellation");
        const auto fresh_incarnation = registry.incarnation(*domains[1].handle);
        require(fresh_incarnation && *fresh_incarnation != old_service_incarnation && !registry.incarnation(old_owner),
                "service incarnation freshness");
        Serial::text("AURORA_PIN_RESTART: slot=1 old=");
        Serial::number(old_service_incarnation);
        Serial::text(" current=");
        Serial::number(*fresh_incarnation);
        Serial::text(" stale_owner=1 stale_token=1 retained=2\r\n");
        pin_record("service-reborn");
    } else {
        pin_record("reborn");
    }
}
auto pin_final() -> void {
    require(pin_ledger->reap_dead() == 0 && pin_ledger->pinned_pages() == pin_retained() &&
                frames.used() == pin_retained(),
            "persistent pin ledger final state");
    if (fixture == Fixture::runtime_pin_fault) {
        require(!zero(arena + L::stack_frames_offset + 8 * 4096) && !zero(arena + L::stack_frames_offset + 9 * 4096) &&
                    pin_retained() == 2,
                "quarantined frame scrubbed or released");
    }
    pin_record("final");
    Serial::text("AURORA_PIN_OK\r\n");
}
} // namespace pin_supervisor
