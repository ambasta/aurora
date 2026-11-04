#pragma once
#include <cstddef>
#include <cstdint>

namespace aurora::scheduler {
using U64 = std::uint64_t;
enum class Phase : U64 {
    empty,
    runnable,
    dispatched,
    observed,
    retiring,
    retired
};
enum class Select : U64 {
    rejected,
    idle,
    selected
};
enum class Finish : U64 {
    rejected,
    runnable,
    retiring
};
enum class Terminal : U64 {
    none,
    tick,
    returned,
    bounds,
    overflow,
    division_zero,
    shift_count
};
// Copied identity observations, not physical domain authority.
struct Binding final {
    U64 slot = 3, stamp = 0, sequence = 0;
    auto operator==(const Binding &) const -> bool = default;
};
struct Selection final {
    Select action = Select::rejected;
    Binding binding{};
};
extern "C" {
void __au_runtime_scheduler_create(void *);
bool __au_runtime_scheduler_admit(void *, U64, U64, U64);
Select __au_runtime_scheduler_select(void *);
bool __au_runtime_scheduler_observe_tick(void *, U64, U64, U64);
bool __au_runtime_scheduler_observe_terminal(void *, U64, U64, U64, Terminal);
Finish __au_runtime_scheduler_finish_restore(void *, U64, U64, U64);
bool __au_runtime_scheduler_ack_retired(void *, U64, U64, U64);
U64 __au_runtime_scheduler_active_slot(const void *);
U64 __au_runtime_scheduler_active_stamp(const void *);
U64 __au_runtime_scheduler_sequence(const void *);
Phase __au_runtime_scheduler_phase(const void *, U64);
U64 __au_runtime_scheduler_used(const void *, U64);
U64 __au_runtime_scheduler_remaining(const void *, U64);
Terminal __au_runtime_scheduler_reason(const void *, U64);
bool __au_runtime_scheduler_complete(const void *);
}

// Only object lifetime and synchronous exclusion live here. The source root
// alone owns scheduling policy. No borrow spans a context switch or IRQ drain.
template <class Platform> class Root final {
    alignas(16) std::byte storage_[256]{};
    bool live_ = false;
    mutable bool borrowed_ = false;
    static void require(bool valid) {
        if (!valid)
            Platform::fail();
    }
    [[gnu::noinline]] void enter(bool live) const {
        require(live_ == live && !borrowed_);
        borrowed_ = true;
        require(Platform::quiet());
    }
    [[gnu::noinline]] void leave() const {
        require(borrowed_ && Platform::quiet());
        borrowed_ = false;
    }

public:
    constexpr Root() = default;
    Root(const Root &) = delete;
    Root(Root &&) = delete;
    auto operator=(const Root &) -> Root & = delete;
    auto operator=(Root &&) -> Root & = delete;
    void create() {
        enter(false);
        __au_runtime_scheduler_create(storage_);
        live_ = true;
        leave();
    }
    auto admit(U64 slot, U64 stamp, U64 limit) -> bool {
        enter(true);
        const auto result = __au_runtime_scheduler_admit(storage_, slot, stamp, limit);
        leave();
        return result;
    }
    auto select() -> Selection {
        enter(true);
        Selection result;
        result.action = __au_runtime_scheduler_select(storage_);
        require(result.action == Select::rejected || result.action == Select::idle ||
                result.action == Select::selected);
        if (result.action == Select::selected) {
            result.binding = {__au_runtime_scheduler_active_slot(storage_),
                              __au_runtime_scheduler_active_stamp(storage_),
                              __au_runtime_scheduler_sequence(storage_)};
            require(result.binding.slot < 3 && result.binding.stamp != 0 && result.binding.sequence != 0);
        }
        leave();
        return result;
    }
    auto observe_tick(Binding binding) -> bool {
        enter(true);
        const auto result =
            __au_runtime_scheduler_observe_tick(storage_, binding.slot, binding.stamp, binding.sequence);
        leave();
        return result;
    }
    auto observe_terminal(Binding binding, Terminal terminal) -> bool {
        enter(true);
        const auto result =
            __au_runtime_scheduler_observe_terminal(storage_, binding.slot, binding.stamp, binding.sequence, terminal);
        leave();
        return result;
    }
    auto finish_restore(Binding binding) -> Finish {
        enter(true);
        const auto result =
            __au_runtime_scheduler_finish_restore(storage_, binding.slot, binding.stamp, binding.sequence);
        require(result == Finish::rejected || result == Finish::runnable || result == Finish::retiring);
        leave();
        return result;
    }
    auto ack_retired(Binding binding) -> bool {
        enter(true);
        const auto result = __au_runtime_scheduler_ack_retired(storage_, binding.slot, binding.stamp, binding.sequence);
        leave();
        return result;
    }
    auto phase(U64 slot) const -> Phase {
        enter(true);
        const auto result = __au_runtime_scheduler_phase(storage_, slot);
        require(result == Phase::empty || result == Phase::runnable || result == Phase::dispatched ||
                result == Phase::observed || result == Phase::retiring || result == Phase::retired);
        leave();
        return result;
    }
    auto used(U64 slot) const -> U64 {
        enter(true);
        const auto result = __au_runtime_scheduler_used(storage_, slot);
        leave();
        return result;
    }
    auto remaining(U64 slot) const -> U64 {
        enter(true);
        const auto result = __au_runtime_scheduler_remaining(storage_, slot);
        leave();
        return result;
    }
    auto reason(U64 slot) const -> Terminal {
        enter(true);
        const auto result = __au_runtime_scheduler_reason(storage_, slot);
        require(result == Terminal::none || result == Terminal::tick || result == Terminal::returned ||
                result == Terminal::bounds || result == Terminal::overflow || result == Terminal::division_zero ||
                result == Terminal::shift_count);
        leave();
        return result;
    }
    auto complete() const -> bool {
        enter(true);
        const auto result = __au_runtime_scheduler_complete(storage_);
        leave();
        return result;
    }
};
} // namespace aurora::scheduler
