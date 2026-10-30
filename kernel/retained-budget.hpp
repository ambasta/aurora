#pragma once
#include <cstddef>
#include <cstdint>

namespace aurora::budget {
using U64 = std::uint64_t;
enum class Charge : U64 {
    rejected,
    available,
    exhausted
};
// Private bridge signatures admitted against the compiler's nominal root facts.
extern "C" {
void __au_runtime_budget_create(void *, U64, U64);
bool __au_runtime_budget_reset(void *, U64, U64);
bool __au_runtime_budget_configure_next(void *, U64, U64);
bool __au_runtime_budget_restart(void *);
Charge __au_runtime_budget_charge(void *, U64);
Charge __au_runtime_budget_progress(void *, U64);
bool __au_runtime_budget_admitted(const void *);
bool __au_runtime_budget_available(const void *);
U64 __au_runtime_budget_quantum(const void *);
U64 __au_runtime_budget_used(const void *);
}

// Storage identity, lifetime and exclusion are native obligations. The opaque
// source object alone owns allowance policy; copied observations grant no timer
// authority. No borrow survives a hardware operation or an interrupt return.
template <class Platform> class Root final {
    alignas(16) std::byte storage_[128]{};
    bool live_ = false;
    mutable bool borrowed_ = false;
    static void require(bool condition) {
        if (!condition)
            Platform::fail();
    }
    void enter(bool live) const {
        require(live_ == live && !borrowed_);
        borrowed_ = true;
        require(Platform::quiet());
    }
    void leave() const {
        require(borrowed_ && Platform::quiet());
        borrowed_ = false;
    }
    void scrub() {
        for (auto &byte : storage_)
            *static_cast<volatile std::byte *>(&byte) = std::byte{};
    }

public:
    constexpr Root() = default;
    Root(const Root &) = delete;
    Root(Root &&) = delete;
    auto operator=(const Root &) -> Root & = delete;
    auto operator=(Root &&) -> Root & = delete;
    auto create(U64 limit, U64 scale) -> bool {
        enter(false);
        // Factory placement initializes the complete value before its first
        // borrowed call; identity begins here, not at the factory's local.
        __au_runtime_budget_create(storage_, limit, scale);
        live_ = __au_runtime_budget_admitted(storage_);
        if (!live_)
            scrub();
        leave();
        return live_;
    }
    // Loader storage can be reused without retaining a second lifetime flag.
    auto initialize_or_reset(U64 limit, U64 scale) -> bool {
        return live_ ? reset(limit, scale) : create(limit, scale);
    }
    auto reset(U64 limit, U64 scale) -> bool {
        enter(true);
        const bool result = __au_runtime_budget_reset(storage_, limit, scale);
        leave();
        return result;
    }
    auto configure_next(U64 limit, U64 scale) -> bool {
        enter(true);
        const bool result = __au_runtime_budget_configure_next(storage_, limit, scale);
        leave();
        return result;
    }
    auto restart() -> bool {
        enter(true);
        const bool result = __au_runtime_budget_restart(storage_);
        leave();
        return result;
    }
    auto charge(U64 count) -> Charge {
        enter(true);
        const auto result = __au_runtime_budget_charge(storage_, count);
        leave();
        return result;
    }
    auto progress(U64 measured) -> Charge {
        enter(true);
        const auto result = __au_runtime_budget_progress(storage_, measured);
        leave();
        return result;
    }
    auto available() const -> bool {
        enter(true);
        const bool result = __au_runtime_budget_available(storage_);
        leave();
        return result;
    }
    auto quantum() const -> U64 {
        enter(true);
        const auto result = __au_runtime_budget_quantum(storage_);
        leave();
        return result;
    }
    auto used() const -> U64 {
        enter(true);
        const auto result = __au_runtime_budget_used(storage_);
        leave();
        return result;
    }
    void stop() {
        enter(true);
        scrub();
        live_ = false;
        leave();
    }
};
} // namespace aurora::budget
