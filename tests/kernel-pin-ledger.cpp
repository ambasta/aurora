#include "../kernel/pin-ledger.hpp"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>
#include <optional>
#include <string_view>
#include <type_traits>

using aurora::memory::PageLease;
using aurora::memory::PhysicalPages;
using aurora::memory::PinHandle;
using aurora::memory::PinLedger;
using aurora::user::DomainHandle;
using aurora::user::DomainRegistry;

static_assert(!std::is_copy_constructible_v<PinLedger>);
static_assert(!std::is_move_constructible_v<PinLedger>);
static_assert(!std::is_copy_assignable_v<PinLedger>);
static_assert(!std::is_move_assignable_v<PinLedger>);
static_assert(std::is_copy_constructible_v<PinHandle>);
static_assert(!std::is_constructible_v<PinHandle, PinLedger&, std::uint64_t, std::uint64_t, std::size_t>);
template <class T> concept HasPublish = requires(T& value, PinHandle pin) { value.publish(pin); };
template <class T> concept HasComplete = requires(T& value, PinHandle pin) { value.complete(pin); };
template <class T> concept HasLeaseImport = requires(T& value, PageLease& lease) { value.grant(std::move(lease)); };
static_assert(!HasPublish<PinLedger> && !HasComplete<PinLedger> && !HasLeaseImport<PinLedger>);

std::size_t checks{};
auto check(bool condition, std::string_view message) -> void {
    ++checks;
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}

class Arena final {
public:
    static constexpr std::size_t page_count = 16;
    alignas(4096) std::array<unsigned char, page_count * 4096> bytes{};
    [[nodiscard]] auto base() const -> std::uint64_t {
        return static_cast<std::uint64_t>(reinterpret_cast<std::uintptr_t>(bytes.data()));
    }
    auto fill(unsigned char value) -> void { bytes.fill(value); }
    [[nodiscard]] auto page_is(std::size_t page, unsigned char value) const -> bool {
        return std::all_of(bytes.begin() + static_cast<std::ptrdiff_t>(page * 4096),
                           bytes.begin() + static_cast<std::ptrdiff_t>((page + 1) * 4096),
                           [value](auto byte) { return byte == value; });
    }
};

class Scrubber final {
public:
    Arena& arena;
    PhysicalPages& pool;
    std::size_t calls{};
    std::size_t fail_call{};
    std::size_t last_used{};
    std::array<std::uint64_t, 64> recent{};
    PinLedger* reenter{};
    DomainHandle owner{};
    PinHandle handle{};
    Scrubber(Arena& backing, PhysicalPages& pages) : arena(backing), pool(pages) {}
    static auto run(void* context, std::uint64_t address, std::size_t bytes) -> bool {
        auto& self = *static_cast<Scrubber*>(context);
        ++self.calls;
        check(bytes == PhysicalPages::page_size, "scrub exact whole-page extent");
        check(address >= self.arena.base() && address - self.arena.base() <= self.arena.bytes.size() - bytes
              && (address - self.arena.base()) % 4096 == 0, "scrub only actual bounded arena page");
        self.recent[(self.calls - 1) % self.recent.size()] = address;
        self.last_used = self.pool.used();
        if (self.reenter) {
            check(!self.reenter->grant(self.owner, 1), "scrub cannot reenter grant");
            check(!self.reenter->cancel(self.handle, self.owner), "scrub cannot reenter cancel");
            check(self.reenter->borrower_dispose(self.owner) == 0 && self.reenter->reap_dead() == 0,
                  "scrub cannot reenter owner cleanup");
            check(!self.reenter->inject_uncertainty(self.handle, self.owner), "scrub cannot inject uncertainty reentrantly");
        }
        if (self.calls == self.fail_call) return false;
        auto* start = self.arena.bytes.data() + (address - self.arena.base());
        std::fill(start, start + bytes, 0);
        return std::all_of(start, start + bytes, [](auto byte) { return byte == 0; });
    }
};

auto ownership_and_cancellation() -> void {
    Arena arena;
    arena.fill(0xa5);
    PhysicalPages pool;
    DomainRegistry registry, foreign_registry;
    Scrubber scrub(arena, pool);
    PinLedger ledger(pool, registry, Scrubber::run, &scrub);
    const auto owner = registry.create(), peer = registry.create(), foreign = foreign_registry.create();
    check(owner && peer && foreign, "create owner identities");
    check(!ledger.grant(*owner, 1) && pool.used() == 0, "ledger never initializes the pool");
    check(pool.initialize(arena.base(), Arena::page_count), "initialize actual backing pages explicitly");
    auto stack = pool.acquire();
    check(stack && pool.address(*stack) == arena.base(), "shared pool external stack lease");
    check(!ledger.grant(DomainHandle{}, 1) && !ledger.grant(*foreign, 1)
          && !ledger.grant(*owner, 0) && !ledger.grant(*owner, 3), "invalid owners and page counts rejected");
    const auto pin = ledger.grant(*owner, 2);
    check(pin && pin->epoch() != 0 && pin->generation() != 0 && pin->slot() < PinLedger::capacity,
          "opaque bound grant with diagnostics");
    check(pool.used() == 3 && ledger.pinned_pages() == 2 && ledger.used_entries() == 1
          && ledger.quarantined_pages() == 0, "grant owns actual two PageLeases");
    check(!ledger.cancel(PinHandle{}, *owner) && !ledger.cancel(*pin, *peer)
          && !ledger.cancel(*pin, *foreign), "default, foreign, and other-domain cancellation denied");
    PinLedger other(pool, registry, Scrubber::run, &scrub);
    const auto other_pin = other.grant(*owner, 1);
    check(other_pin && other_pin->epoch() != pin->epoch() && pool.used() == 4,
          "shared-pool ledgers receive disjoint actual leases");
    check(!other.cancel(*pin, *owner) && !ledger.cancel(*other_pin, *owner), "cross-ledger handle denied");
    check(other.cancel(*other_pin, *owner), "other ledger releases only its page");
    scrub.calls = 0;
    scrub.reenter = &ledger;
    scrub.owner = *owner;
    scrub.handle = *pin;
    const auto copied = *pin;
    check(ledger.cancel(*pin, *owner), "clean cancellation");
    check(scrub.calls == 2 && scrub.last_used == 3 && scrub.recent[0] == arena.base() + 4096
          && scrub.recent[1] == arena.base() + 8192, "all pages scrubbed while still pinned before first release");
    check(arena.page_is(0, 0xa5) && arena.page_is(1, 0) && arena.page_is(2, 0)
          && arena.page_is(4, 0xa5), "zero actual frame bytes without touching external or unowned frames");
    check(pool.used() == 1 && ledger.pinned_pages() == 0 && !ledger.cancel(copied, *owner),
          "copied token cannot double release");
    scrub.reenter = nullptr;
    const auto fresh = ledger.grant(*owner, 1);
    check(fresh && !ledger.cancel(copied, *owner) && ledger.cancel(*fresh, *owner), "stale generation rejected");
    auto reclaimed = pool.acquire();
    check(reclaimed && pool.address(*reclaimed) == arena.base() + 4096 && arena.page_is(1, 0),
          "allocator reassignment observes scrubbed original frame");
    check(pool.release(*reclaimed) && pool.release(*stack) && pool.used() == 0, "shared ownership cleanup");
    PinLedger unusable(pool, registry, nullptr);
    check(!unusable.grant(*owner, 1) && unusable.available_entries() == 0, "missing trusted scrub disables grants");
}

auto client_lifetimes() -> void {
    Arena arena;
    arena.fill(0x72);
    PhysicalPages pool;
    check(pool.initialize(arena.base(), Arena::page_count), "lifetime pool");
    DomainRegistry registry;
    const auto owner = registry.create(), peer = registry.create();
    check(owner && peer, "lifetime domains");
    Scrubber scrub(arena, pool);
    PinLedger ledger(pool, registry, Scrubber::run, &scrub);
    const auto old_pin = ledger.grant(*owner, 2), peer_pin = ledger.grant(*peer, 1);
    check(old_pin && peer_pin, "lifetime loans");
    check(registry.destroy(*owner), "client dies without cancellation");
    const auto new_owner = registry.create();
    check(new_owner && !registry.index(*owner), "domain slot reused with new incarnation");
    check(!ledger.cancel(*old_pin, *owner) && !ledger.cancel(*old_pin, *new_owner),
          "dead and replacement domains cannot wield old pin");
    check(ledger.reap_dead() == 1 && pool.used() == 1 && ledger.pinned_pages() == 1
          && scrub.calls == 2 && arena.page_is(0, 0) && arena.page_is(1, 0),
          "dead never-published entry reaped only after complete real scrub");
    check(ledger.reap_dead() == 0 && !ledger.cancel(*old_pin, *new_owner), "reaping and stale cancellation are idempotent");
    check(ledger.cancel(*peer_pin, *peer), "peer lease survives another client's disposal");
    const auto first = ledger.grant(*new_owner, 1), second = ledger.grant(*new_owner, 2);
    check(first && second && ledger.borrower_dispose(*new_owner) == 2 && pool.used() == 0,
          "live borrower disposal counts entries rather than pages");
    check(!ledger.cancel(*first, *new_owner) && !ledger.cancel(*second, *new_owner), "disposed entry handles stale");
}

auto permanent_quarantine() -> void {
    Arena arena;
    arena.fill(0xc1);
    PhysicalPages pool;
    check(pool.initialize(arena.base(), Arena::page_count), "quarantine pool");
    DomainRegistry registry;
    const auto owner = registry.create(), peer = registry.create();
    check(owner && peer, "quarantine owners");
    Scrubber scrub(arena, pool);
    {
        PinLedger ledger(pool, registry, Scrubber::run, &scrub);
        const auto pin = ledger.grant(*owner, 2);
        check(pin && !ledger.inject_uncertainty(*pin, *peer)
              && ledger.inject_uncertainty(*pin, *owner), "explicit test uncertainty needs exact live owner");
        check(ledger.pinned_pages() == 2 && ledger.quarantined_pages() == 2 && pool.used() == 2,
              "uncertainty retains actual page leases");
        check(!ledger.inject_uncertainty(*pin, *owner) && !ledger.cancel(*pin, *owner)
              && ledger.borrower_dispose(*owner) == 0 && scrub.calls == 0,
              "quarantine absorbing for replay, cancel, and borrower disposal");
        check(registry.destroy(*owner), "quarantined client death");
        const auto replacement = registry.create();
        check(replacement && ledger.reap_dead() == 0 && !ledger.cancel(*pin, *replacement)
              && pool.used() == 2 && scrub.calls == 0, "death and replacement cannot retire uncertainty");
        const auto peer_pin = ledger.grant(*peer, 1);
        check(peer_pin && ledger.cancel(*peer_pin, *peer) && scrub.recent[0] == arena.base() + 8192,
              "peer uses only distinct nonquarantined frame");
        check(arena.page_is(0, 0xc1) && arena.page_is(1, 0xc1), "uncertain frames are neither scrubbed nor released");
    }
    // Deliberate ledger-lifetime violation demonstrates fail-leaking, not recovery.
    check(pool.used() == 2, "ledger destructor never releases quarantine");
    auto remaining = pool.acquire();
    check(remaining && pool.address(*remaining) == arena.base() + 8192 && pool.release(*remaining),
          "destroyed ledger cannot make its allocated frames reusable");
}

auto scrub_failure() -> void {
    Arena arena;
    arena.fill(0x39);
    PhysicalPages pool;
    check(pool.initialize(arena.base(), Arena::page_count), "scrub-failure pool");
    DomainRegistry registry;
    const auto owner = registry.create();
    check(owner.has_value(), "scrub-failure owner");
    Scrubber scrub(arena, pool);
    PinLedger ledger(pool, registry, Scrubber::run, &scrub);
    const auto pin = ledger.grant(*owner, 2);
    check(pin.has_value(), "scrub-failure grant");
    scrub.fail_call = 2;
    check(!ledger.cancel(*pin, *owner) && pool.used() == 2 && ledger.quarantined_pages() == 2,
          "second scrub failure retains even the first already-zeroed lease");
    check(arena.page_is(0, 0) && arena.page_is(1, 0x39), "scrub failure actual byte evidence");
    scrub.fail_call = 0;
    check(!ledger.cancel(*pin, *owner) && scrub.calls == 2 && registry.destroy(*owner)
          && ledger.reap_dead() == 0 && pool.used() == 2, "late scrub success cannot resurrect quarantine");
}

auto disposal_failure_and_full_quarantine() -> void {
    Arena arena;
    arena.fill(0x85);
    PhysicalPages pool;
    check(pool.initialize(arena.base(), Arena::page_count), "disposal-failure pool");
    DomainRegistry registry;
    const auto first = registry.create(), second = registry.create();
    check(first && second, "disposal-failure domains");
    Scrubber scrub(arena, pool);
    PinLedger ledger(pool, registry, Scrubber::run, &scrub);
    const auto first_pin = ledger.grant(*first, 2);
    check(first_pin.has_value(), "dead-owner scrub-failure loan");
    check(registry.destroy(*first), "dead owner awaiting reap");
    scrub.fail_call = 1;
    check(ledger.reap_dead() == 0 && ledger.quarantined_pages() == 2 && pool.used() == 2,
          "dead-owner cleanup failure becomes absorbing quarantine");
    scrub.fail_call = 0;
    check(ledger.reap_dead() == 0 && scrub.calls == 1, "dead-owner quarantine never retries scrub");
    const auto second_pin = ledger.grant(*second, 2);
    check(second_pin.has_value(), "live-owner disposal-failure loan");
    scrub.fail_call = 2;
    check(ledger.borrower_dispose(*second) == 0 && ledger.quarantined_pages() == 4 && pool.used() == 4,
          "live-owner disposal failure becomes absorbing quarantine");
    for (std::size_t index = 2; index < PinLedger::capacity; ++index) {
        const auto pin = ledger.grant(*second, 2);
        check(pin && ledger.inject_uncertainty(*pin, *second), "fill remaining quarantine slots");
    }
    check(ledger.used_entries() == 4 && ledger.quarantined_pages() == 8 && ledger.pinned_pages() == 8
          && ledger.available_entries() == 0 && !ledger.grant(*second, 1) && pool.used() == 8,
          "all four quarantines exhaust ledger permanently with pool space remaining");
    check(registry.destroy(*second) && ledger.reap_dead() == 0 && pool.used() == 8
          && ledger.quarantined_pages() == 8 && scrub.calls == 2,
          "all-owner death cannot reclaim any quarantine or call its scrubber");
}

auto exhaustion_and_rollback() -> void {
    Arena arena;
    arena.fill(0x63);
    PhysicalPages pool;
    check(pool.initialize(arena.base(), Arena::page_count), "capacity pool");
    DomainRegistry registry;
    const auto owner = registry.create();
    check(owner.has_value(), "capacity owner");
    Scrubber scrub(arena, pool);
    PinLedger ledger(pool, registry, Scrubber::run, &scrub);
    std::array<std::optional<PinHandle>, PinLedger::capacity> handles;
    for (auto& handle : handles) handle = ledger.grant(*owner, 2);
    check(std::all_of(handles.begin(), handles.end(), [](auto& handle) { return handle.has_value(); })
          && pool.used() == 8 && ledger.used_entries() == 4 && ledger.available_entries() == 0,
          "four actual entries consume eight distinct pages");
    check(!ledger.grant(*owner, 1) && pool.used() == 8, "ledger exhaustion does not acquire an extra page");
    auto spare = pool.acquire();
    check(spare && pool.address(*spare) == arena.base() + 8 * 4096, "pool still has capacity beyond ledger bound");
    check(pool.release(*spare), "external spare release");
    for (auto& handle : handles) check(ledger.cancel(*handle, *owner), "capacity cleanup");
    check(pool.used() == 0, "capacity cleanup accounting");

    Arena small;
    small.fill(0xdd);
    PhysicalPages small_pool;
    check(small_pool.initialize(small.base(), 2), "partial pool");
    auto stack = small_pool.acquire();
    check(stack.has_value(), "partial external stack");
    Scrubber partial_scrub(small, small_pool);
    PinLedger partial(small_pool, registry, Scrubber::run, &partial_scrub);
    check(!partial.grant(*owner, 2) && small_pool.used() == 1 && partial.pinned_pages() == 0
          && partial.used_entries() == 0 && partial_scrub.calls == 1,
          "partial acquisition failure scrubs and rolls back owned prefix");
    check(small.page_is(0, 0xdd) && small.page_is(1, 0), "partial rollback cannot touch shared stack lease");
    const auto complete = partial.grant(*owner, 1);
    check(complete && !partial.grant(*owner, 1) && small_pool.used() == 2 && partial.pinned_pages() == 1,
          "empty pool failure leaves existing ownership unchanged");
    check(partial.cancel(*complete, *owner) && small_pool.release(*stack), "partial cleanup");

    Arena failed;
    failed.fill(0xbe);
    PhysicalPages failed_pool;
    check(failed_pool.initialize(failed.base(), 1), "rollback-failure pool");
    Scrubber fail_scrub(failed, failed_pool);
    fail_scrub.fail_call = 1;
    PinLedger fail_ledger(failed_pool, registry, Scrubber::run, &fail_scrub);
    check(!fail_ledger.grant(*owner, 2) && failed_pool.used() == 1 && fail_ledger.pinned_pages() == 1
          && fail_ledger.quarantined_pages() == 1 && fail_ledger.used_entries() == 1,
          "unreturned partial loan retained when rollback scrub fails");
    check(!fail_ledger.grant(*owner, 1) && fail_ledger.borrower_dispose(*owner) == 0
          && registry.destroy(*owner) && fail_ledger.reap_dead() == 0 && failed_pool.used() == 1,
          "partial quarantine survives retries and owner death");
}

auto reconstruction_guards() -> void {
    Arena arena;
    arena.fill(0x91);
    PhysicalPages pool;
    check(pool.initialize(arena.base(), Arena::page_count), "rebirth pool");
    DomainRegistry registry;
    const auto owner = registry.create();
    check(owner.has_value(), "rebirth owner");
    Scrubber scrub(arena, pool);
    std::optional<PinLedger> ledger;
    ledger.emplace(pool, registry, Scrubber::run, &scrub);
    const auto old = ledger->grant(*owner, 1);
    check(old && ledger->cancel(*old, *owner), "clean ledger before reconstruction");
    ledger.reset();
    ledger.emplace(pool, registry, Scrubber::run, &scrub);
    const auto fresh = ledger->grant(*owner, 1);
    check(fresh && fresh->epoch() != old->epoch() && fresh->slot() == old->slot()
          && fresh->generation() == old->generation() && !ledger->cancel(*old, *owner),
          "same-address ledger reconstruction rejects previous epoch");
    check(ledger->cancel(*fresh, *owner), "reborn clean ledger cleanup");
    const auto orphan = ledger->grant(*owner, 1);
    check(orphan.has_value(), "outstanding loan before deliberately dropped ledger");
    ledger.reset();
    check(pool.used() == 1, "destroyed reserved owner also fails leaking");
    ledger.emplace(pool, registry, Scrubber::run, &scrub);
    const auto later = ledger->grant(*owner, 1);
    check(later && !ledger->cancel(*orphan, *owner) && ledger->cancel(*later, *owner)
          && pool.used() == 1 && scrub.recent[(scrub.calls - 1) % scrub.recent.size()] == arena.base() + 4096,
          "ledger rebirth cannot recover dropped lease or reuse its frame");

    // This deliberately violates the required pool lifetime. A replacement
    // allocator can reuse its claimed arena, so callers MUST forbid it. The
    // ledger additionally refuses to release any new lease on the stale token.
    Arena replaced_arena;
    std::optional<PhysicalPages> replaced_pool;
    replaced_pool.emplace();
    check(replaced_pool->initialize(replaced_arena.base(), 2), "original lifetime-violation pool");
    Scrubber replaced_scrub(replaced_arena, *replaced_pool);
    PinLedger stale_ledger(*replaced_pool, registry, Scrubber::run, &replaced_scrub);
    const auto stale = stale_ledger.grant(*owner, 1);
    check(stale.has_value(), "original lifetime-violation grant");
    replaced_pool.reset();
    replaced_pool.emplace();
    check(replaced_pool->initialize(replaced_arena.base(), 2), "forbidden replacement pool");
    auto unrelated = replaced_pool->acquire();
    check(unrelated && !stale_ledger.cancel(*stale, *owner) && replaced_pool->used() == 1
          && stale_ledger.quarantined_pages() == 1 && stale_ledger.available_entries() == 0
          && !stale_ledger.grant(*owner, 1) && replaced_scrub.calls == 0,
          "pool replacement detected and cannot release replacement allocation");
    check(replaced_pool->release(*unrelated), "replacement still owns its independent generation");
}

auto generation_exhaustion() -> void {
#if defined(AURORA_PIN_LEDGER_TEST_GENERATION_LIMIT)
    Arena arena;
    PhysicalPages pool;
    check(pool.initialize(arena.base(), Arena::page_count), "generation pool");
    DomainRegistry registry;
    const auto owner = registry.create();
    check(owner.has_value(), "generation owner");
    Scrubber scrub(arena, pool);
    PinLedger ledger(pool, registry, Scrubber::run, &scrub);
    std::array<PinHandle, PinLedger::capacity * AURORA_PIN_LEDGER_TEST_GENERATION_LIMIT> old;
    std::size_t index = 0;
    for (std::size_t slot = 0; slot < PinLedger::capacity; ++slot) {
        for (std::uint64_t generation = 1; generation <= AURORA_PIN_LEDGER_TEST_GENERATION_LIMIT; ++generation) {
            const auto pin = ledger.grant(*owner, 1);
            check(pin && pin->slot() == slot && pin->generation() == generation, "bounded generation increases without wrap");
            for (std::size_t previous = 0; previous < index; ++previous)
                check(!ledger.cancel(old[previous], *owner), "all historical handles rejected on every generation");
            old[index++] = *pin;
            check(ledger.cancel(*pin, *owner), "bounded generation release");
        }
    }
    check(!ledger.grant(*owner, 1) && ledger.available_entries() == 0 && ledger.used_entries() == 0
          && ledger.pinned_pages() == 0 && pool.used() == 0, "all generation-exhausted entries retired permanently");
    for (const auto previous : old) check(!ledger.cancel(previous, *owner), "no stale resurrection after exhaustion");
#endif
}

auto incarnation_observation() -> void {
    DomainRegistry first, second;
    const auto owner = first.create(), foreign = second.create();
    check(owner && foreign, "incarnation owners");
    const auto old = first.incarnation(*owner);
    check(old && *old != 0, "live incarnation observed");
    check(!first.incarnation(DomainHandle{}) && !first.incarnation(*foreign)
          && !second.incarnation(*owner), "invalid and foreign incarnations hidden");
    check(first.activate(*owner) && first.incarnation(*owner) == old
          && first.deactivate(*owner), "active identity stays stable");
    check(first.destroy(*owner) && !first.incarnation(*owner), "dead incarnation hidden");
    const auto replacement = first.create();
    check(replacement && first.index(*replacement) == 0, "same registry slot reused");
    const auto current = first.incarnation(*replacement);
    check(current && *current > *old && !first.incarnation(*owner), "fresh incarnation rejects stale handle");
}

auto main() -> int {
    incarnation_observation();
    ownership_and_cancellation();
    client_lifetimes();
    permanent_quarantine();
    scrub_failure();
    disposal_failure_and_full_quarantine();
    exhaustion_and_rollback();
    reconstruction_guards();
    generation_exhaustion();
    std::cout << "PASS: actual PageLease pin ownership, whole-frame scrub, live/stale domains, shared pool, bounded exhaustion, partial rollback, permanent quarantine and reconstruction guards";
#if defined(AURORA_PIN_LEDGER_TEST_GENERATION_LIMIT)
    std::cout << ", generation bound " << AURORA_PIN_LEDGER_TEST_GENERATION_LIMIT;
#endif
    std::cout << " (" << checks << " checks)\n";
}
