#pragma once
#include "domain-policy.hpp"
#include "pages.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <utility>

#if defined(AURORA_PIN_LEDGER_TESTING) && AURORA_PIN_LEDGER_TESTING != 1
#error "Pin test interfaces require explicit AURORA_PIN_LEDGER_TESTING=1"
#endif
#if defined(AURORA_PIN_LEDGER_TEST_GENERATION_LIMIT) && !defined(AURORA_PIN_LEDGER_TESTING)
#error "A small pin generation limit is only available in explicit test builds"
#endif

namespace aurora::memory {
class PinLedger;
// This copied intent token conveys no PageLease, address, publication or completion
// authority. Its full private binding and a live domain are checked on every use.
class PinHandle final {
    friend class PinLedger;
    const PinLedger* ledger_{};
    std::uint64_t epoch_{};
    std::uint64_t generation_{};
    std::size_t slot_ = 4;
    PinHandle(const PinLedger& ledger, std::uint64_t epoch,
              std::uint64_t generation, std::size_t slot)
        : ledger_(&ledger), epoch_(epoch), generation_(generation), slot_(slot) {}
public:
    PinHandle() = default;
    [[nodiscard]] auto epoch() const -> std::uint64_t { return epoch_; }
    [[nodiscard]] auto generation() const -> std::uint64_t { return generation_; }
    [[nodiscard]] auto slot() const -> std::size_t { return slot_; }
};

// CPU-only trusted bootstrap ownership, single CPU, no DMA publication operation.
// The kernel owns this object; services receive at most copied PinHandles. The
// registry, pool, backing arena and scrub context must outlive the ledger and any
// retained pages. In particular the pool/backing range must never be destroyed,
// reconstructed, reinitialized or assigned to another allocator while a pin or
// quarantine exists. PhysicalPages itself assumes exclusive ownership of its arena.
// The kernel keeps this ledger for the arena lifetime, including after client death.
// C++ cannot enforce those external storage lifetimes; they are trusted preconditions.
// Destruction NEVER releases a lease, even accidentally: PageLease destruction is
// deliberately non-releasing. Destroying a nonempty ledger loses bookkeeping and
// leaks its allocated frames, not permission to reuse them or recover quarantine.
class PinLedger final {
public:
    static constexpr std::size_t capacity = 4;
    static constexpr std::size_t pages_per_entry = 2;
    // Synchronous trusted CPU scrub. Return true only after zeroing and verifying
    // all bytes in exactly this owned page. The callback must not replace/mutate
    // the pool or registry, change mappings, or retain the address for later use.
    // Ledger mutation during callbacks is rejected. This is not a DMA visibility
    // or hardware completion callback, and it cannot retire uncertain publication.
    using Scrub = bool (*)(void*, std::uint64_t, std::size_t);
private:
    enum class State { empty, reserved, quarantined };
    class Entry final {
    public:
        State state = State::empty;
        std::uint64_t generation{};
        user::DomainHandle owner{};
        std::array<std::optional<PageLease>, pages_per_entry> pages{};
        std::size_t count{};
    };
    class Mutation final {
        bool& busy_;
    public:
        explicit Mutation(bool& busy) : busy_(busy) { busy_ = true; }
        ~Mutation() { busy_ = false; }
        Mutation(const Mutation&) = delete;
        auto operator=(const Mutation&) -> Mutation& = delete;
    };
    inline static std::uint64_t next_epoch_{};
#if defined(AURORA_PIN_LEDGER_TEST_GENERATION_LIMIT)
    static constexpr auto test_generation_limit_ = AURORA_PIN_LEDGER_TEST_GENERATION_LIMIT;
    static_assert(std::in_range<std::uint64_t>(test_generation_limit_) && test_generation_limit_ > 0,
                  "A generation limit must be a positive representable integer");
    static constexpr std::uint64_t generation_limit_ = static_cast<std::uint64_t>(test_generation_limit_);
#else
    static constexpr std::uint64_t generation_limit_ = UINT64_MAX;
#endif
    PhysicalPages& pool_;
    const user::DomainRegistry& registry_;
    Scrub scrub_;
    void* scrub_context_;
    std::uint64_t epoch_{};
    std::array<Entry, capacity> entries_{};
    bool busy_{};
    bool poisoned_{};

    [[nodiscard]] auto same_live_owner(user::DomainHandle first, user::DomainHandle second) const -> bool {
        const auto first_slot = registry_.index(first);
        const auto second_slot = registry_.index(second);
        return first_slot && second_slot && *first_slot == *second_slot;
    }
    [[nodiscard]] auto find(PinHandle handle, user::DomainHandle owner) -> Entry* {
        if (handle.ledger_ != this || epoch_ == 0 || handle.epoch_ != epoch_
            || handle.slot_ >= capacity) return nullptr;
        auto& entry = entries_[handle.slot_];
        if (entry.state == State::empty || handle.generation_ == 0
            || handle.generation_ != entry.generation || !same_live_owner(entry.owner, owner)) return nullptr;
        return &entry;
    }
    // PageLease acquisition is the only import path. Validate existing ownership
    // before allocating/releasing and additionally reject any duplicate address.
    // A violated pool-lifetime precondition permanently disables this ledger; it
    // does not grant the replacement pool authority to recycle the old arena.
    [[nodiscard]] auto validate_ownership() -> bool {
        if (poisoned_) return false;
        std::array<std::uint64_t, capacity * pages_per_entry> addresses{};
        std::size_t count = 0;
        for (auto& entry : entries_) {
            for (std::size_t page = 0; page < entry.count; ++page) {
                const auto address = entry.pages[page] ? pool_.address(*entry.pages[page]) : std::nullopt;
                bool duplicate = false;
                if (address) for (std::size_t previous = 0; previous < count; ++previous)
                    if (addresses[previous] == *address) duplicate = true;
                if (!address || duplicate) {
                    poisoned_ = true;
                    for (auto& retained : entries_)
                        if (retained.state != State::empty) retained.state = State::quarantined;
                    return false;
                }
                addresses[count++] = *address;
            }
        }
        return true;
    }
    [[nodiscard]] auto release_reserved(Entry& entry) -> bool {
        if (entry.state != State::reserved || !validate_ownership()) return false;
        // Scrub the complete entry before releasing even its first page. Any
        // uncertain/failed scrub leaves every lease in absorbing quarantine.
        for (std::size_t page = 0; page < entry.count; ++page) {
            const auto address = pool_.address(*entry.pages[page]);
            if (!address || !scrub_(scrub_context_, *address, PhysicalPages::page_size)) {
                entry.state = State::quarantined;
                return false;
            }
        }
        if (!validate_ownership()) return false;
        while (entry.count != 0) {
            // Under the exclusive single-CPU/callback contract, all releases
            // succeed after validation. A violation fails closed for remaining
            // pages; no different lease or allocator frame is ever released.
            const auto page = entry.count - 1;
            if (!pool_.release(*entry.pages[page])) {
                entry.state = State::quarantined;
                poisoned_ = true;
                return false;
            }
            entry.pages[page].reset();
            --entry.count;
        }
        entry.owner = user::DomainHandle{};
        entry.state = State::empty;
        return true;
    }
public:
    PinLedger(PhysicalPages& pool, const user::DomainRegistry& registry,
              Scrub scrub, void* scrub_context = nullptr)
        : pool_(pool), registry_(registry), scrub_(scrub), scrub_context_(scrub_context) {
        if (next_epoch_ != UINT64_MAX) epoch_ = ++next_epoch_;
    }
    ~PinLedger() = default; // Never release retained pages during destruction.
    PinLedger(const PinLedger&) = delete;
    auto operator=(const PinLedger&) -> PinLedger& = delete;
    PinLedger(PinLedger&&) = delete;
    auto operator=(PinLedger&&) -> PinLedger& = delete;

    [[nodiscard]] auto grant(user::DomainHandle owner, std::size_t count) -> std::optional<PinHandle> {
        if (busy_ || epoch_ == 0 || !scrub_ || count == 0 || count > pages_per_entry
            || !registry_.index(owner) || !validate_ownership()) return std::nullopt;
        const Mutation mutation(busy_);
        for (std::size_t slot = 0; slot < capacity; ++slot) {
            auto& entry = entries_[slot];
            if (entry.state != State::empty || entry.generation == generation_limit_) continue;
            ++entry.generation; // Exhausted generations are retired, never wrapped.
            entry.owner = owner;
            entry.state = State::reserved;
            for (std::size_t page = 0; page < count; ++page) {
                auto lease = pool_.acquire();
                if (!lease) {
                    // Even an unreturned partial grant is scrubbed before release.
                    // Failure retains the acquired prefix in permanent quarantine.
                    const bool released = release_reserved(entry);
                    (void)released;
                    return std::nullopt;
                }
                entry.pages[page].emplace(std::move(*lease));
                ++entry.count;
            }
            if (!validate_ownership()) return std::nullopt;
            return PinHandle(*this, epoch_, entry.generation, slot);
        }
        return std::nullopt;
    }
    [[nodiscard]] auto cancel(PinHandle handle, user::DomainHandle live_owner) -> bool {
        if (busy_ || !scrub_) return false;
        auto* entry = find(handle, live_owner);
        if (!entry || entry->state != State::reserved) return false;
        const Mutation mutation(busy_);
        return release_reserved(*entry);
    }
    // Counts only entries successfully scrubbed/released, never quarantines.
    // A failed scrub transitions to permanent quarantine and contributes zero.
    [[nodiscard]] auto borrower_dispose(user::DomainHandle live_owner) -> std::size_t {
        if (busy_ || !scrub_ || !registry_.index(live_owner)) return 0;
        const Mutation mutation(busy_);
        std::size_t released = 0;
        for (auto& entry : entries_)
            if (entry.state == State::reserved && same_live_owner(entry.owner, live_owner)
                && release_reserved(entry)) ++released;
        return released;
    }
    [[nodiscard]] auto reap_dead() -> std::size_t {
        if (busy_ || !scrub_) return 0;
        const Mutation mutation(busy_);
        std::size_t released = 0;
        for (auto& entry : entries_)
            if (entry.state == State::reserved && !registry_.index(entry.owner)
                && release_reserved(entry)) ++released;
        return released;
    }
    [[nodiscard]] auto pinned_pages() const -> std::size_t {
        std::size_t count = 0;
        for (const auto& entry : entries_) count += entry.count;
        return count;
    }
    [[nodiscard]] auto quarantined_pages() const -> std::size_t {
        std::size_t count = 0;
        for (const auto& entry : entries_)
            if (entry.state == State::quarantined) count += entry.count;
        return count;
    }
    [[nodiscard]] auto used_entries() const -> std::size_t {
        std::size_t count = 0;
        for (const auto& entry : entries_) if (entry.state != State::empty) ++count;
        return count;
    }
    [[nodiscard]] auto available_entries() const -> std::size_t {
        if (epoch_ == 0 || poisoned_ || !scrub_) return 0;
        std::size_t count = 0;
        for (const auto& entry : entries_)
            if (entry.state == State::empty && entry.generation != generation_limit_) ++count;
        return count;
    }
#if defined(AURORA_PIN_LEDGER_TESTING)
    // Explicit test-build fault injection only. Production has no operation that
    // can claim publication/completion, or move uncertainty back to reserved.
    [[nodiscard]] auto inject_uncertainty(PinHandle handle, user::DomainHandle live_owner) -> bool {
        if (busy_ || !validate_ownership()) return false;
        auto* entry = find(handle, live_owner);
        if (!entry || entry->state != State::reserved) return false;
        entry->state = State::quarantined;
        return true;
    }
#endif
};
}
