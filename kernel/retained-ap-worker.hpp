#pragma once
#include <cstddef>
#include <cstdint>

namespace aurora::ap {
using U64 = std::uint64_t;
using I64 = std::int64_t;
enum class Stage : U64 {
    fresh,
    startup_reserved,
    starting,
    idle,
    reserved,
    running,
    observation_reserved,
    completion_selected,
    failed,
    exhausted
};
struct Plan final {
    U64 incarnation{}, sequence{};
    I64 start{}, count{};
};
struct Observation final {
    U64 apic, incarnation, sequence;
    I64 result;
    U64 status;
};
static_assert(sizeof(Observation) == 40 && offsetof(Observation, result) == 24);
struct ChecksumResult final {
    U64 status{}, value{};
};
static_assert(sizeof(ChecksumResult) == 16 && offsetof(ChecksumResult, value) == 8);
extern "C" {
void __au_runtime_ap_worker_create(void *);
bool __au_runtime_ap_worker_begin_start(void *, U64, U64);
bool __au_runtime_ap_worker_startup_sent(void *, U64, U64);
bool __au_runtime_ap_worker_ready(void *, U64, U64);
bool __au_runtime_ap_worker_reserve(void *, I64, I64);
bool __au_runtime_ap_worker_published(void *, U64, U64);
U64 __au_runtime_ap_worker_reserve_observation(void *, U64, U64);
bool __au_runtime_ap_worker_observe(void *, const Observation *, U64, U64);
U64 __au_runtime_ap_worker_ordinal(const void *);
U64 __au_runtime_ap_worker_attempts(const void *);
U64 __au_runtime_ap_worker_ticks(const void *);
bool __au_runtime_ap_worker_acknowledged(void *, U64, U64);
bool __au_runtime_ap_worker_fail(void *);
Stage __au_runtime_ap_worker_stage(const void *);
U64 __au_runtime_ap_worker_sequence(const void *);
U64 __au_runtime_ap_worker_used(const void *);
U64 __au_runtime_ap_worker_remaining(const void *);
U64 __au_runtime_ap_worker_jobs(const void *);
I64 __au_runtime_ap_worker_result(const void *);
U64 __au_runtime_ap_worker_incarnation(const void *);
U64 __au_runtime_ap_worker_target(const void *);
I64 __au_runtime_ap_worker_start(const void *);
I64 __au_runtime_ap_worker_count(const void *);
void __au_runtime_ap_worker_crc32c(ChecksumResult *, const std::uint8_t *, I64, I64, I64);
}

// Bootstrap storage and synchronous exclusion, not a second lifecycle policy.
// The platform authenticates this exact root, BSP identity, CR3 and quiet IRQ
// context on both sides of every loan. Copied observation fields confer no
// authority. There is no source borrow across mailbox/MMIO/poll/AP execution.
// A trap does not unwind this loan or prove source fail() ran: the native
// fault path must close the physical worker forever and retain all AP backing.
template <class Platform> class Root final {
    alignas(16) std::byte storage_[128]{};
    bool live_{};
    mutable bool borrowed_{};
    mutable U64 entered_context_{};

    static void require(bool condition) {
        if (!condition)
            Platform::fail();
    }
    [[gnu::noinline]] void enter(bool live) const {
        require(live_ == live && !borrowed_ && Platform::authenticates(this) && Platform::quiet());
        entered_context_ = Platform::context();
        borrowed_ = true;
        require(entered_context_ && Platform::authenticates(this) && Platform::quiet());
    }
    [[gnu::noinline]] void leave() const {
        require(borrowed_ && Platform::authenticates(this) && Platform::quiet() &&
                Platform::context() == entered_context_);
        borrowed_ = false;
        entered_context_ = 0;
    }
    template <auto Entry, class... Arguments> auto transition(Arguments... arguments) -> bool {
        enter(true);
        const auto accepted = Entry(storage_, arguments...);
        leave();
        return accepted;
    }
    template <auto Entry> auto query() const {
        enter(true);
        const auto value = Entry(storage_);
        leave();
        return value;
    }

public:
    constexpr Root() = default;
    Root(const Root &) = delete;
    Root(Root &&) = delete;
    auto operator=(const Root &) -> Root & = delete;
    auto operator=(Root &&) -> Root & = delete;
    auto created() const -> bool {
        return live_;
    }
    void create() {
        enter(false);
        __au_runtime_ap_worker_create(storage_);
        require(__au_runtime_ap_worker_stage(storage_) == Stage::fresh);
        live_ = true;
        leave();
    }
    auto begin_start(U64 apic, U64 incarnation) -> bool {
        return transition<__au_runtime_ap_worker_begin_start>(apic, incarnation);
    }
    auto startup_sent(U64 apic, U64 incarnation) -> bool {
        return transition<__au_runtime_ap_worker_startup_sent>(apic, incarnation);
    }
    auto ready(U64 apic, U64 incarnation) -> bool {
        return transition<__au_runtime_ap_worker_ready>(apic, incarnation);
    }
    auto reserve(I64 start, I64 count) -> Plan {
        enter(true);
        Plan plan;
        if (__au_runtime_ap_worker_reserve(storage_, start, count)) {
            plan = {__au_runtime_ap_worker_incarnation(storage_),
                    __au_runtime_ap_worker_sequence(storage_),
                    __au_runtime_ap_worker_start(storage_),
                    __au_runtime_ap_worker_count(storage_)};
            require(__au_runtime_ap_worker_stage(storage_) == Stage::reserved && plan.incarnation && plan.sequence &&
                    plan.sequence <= 8 && plan.start == start && plan.count == count && plan.start >= 0 &&
                    plan.start <= 4096 && plan.count >= 0 && plan.count <= 1024 && plan.count <= 4096 - plan.start);
        }
        leave();
        return plan;
    }
    auto published(U64 incarnation, U64 sequence) -> bool {
        return transition<__au_runtime_ap_worker_published>(incarnation, sequence);
    }
    auto reserve_observation(U64 incarnation, U64 sequence) -> U64 {
        enter(true);
        const auto ordinal = __au_runtime_ap_worker_reserve_observation(storage_, incarnation, sequence);
        leave();
        return ordinal;
    }
    auto observe(Observation observed, U64 ordinal, U64 ticks) -> bool {
        return transition<__au_runtime_ap_worker_observe>(&observed, ordinal, ticks);
    }
    auto ordinal() const -> U64 {
        return query<__au_runtime_ap_worker_ordinal>();
    }
    auto attempts() const -> U64 {
        return query<__au_runtime_ap_worker_attempts>();
    }
    auto ticks() const -> U64 {
        return query<__au_runtime_ap_worker_ticks>();
    }
    auto acknowledged(U64 incarnation, U64 sequence) -> bool {
        return transition<__au_runtime_ap_worker_acknowledged>(incarnation, sequence);
    }
    auto fail() -> bool {
        return transition<__au_runtime_ap_worker_fail>();
    }
    auto stage() const -> Stage {
        return query<__au_runtime_ap_worker_stage>();
    }
    auto sequence() const -> U64 {
        return query<__au_runtime_ap_worker_sequence>();
    }
    auto used() const -> U64 {
        return query<__au_runtime_ap_worker_used>();
    }
    auto remaining() const -> U64 {
        return query<__au_runtime_ap_worker_remaining>();
    }
    auto jobs() const -> U64 {
        return query<__au_runtime_ap_worker_jobs>();
    }
    auto result() const -> I64 {
        return query<__au_runtime_ap_worker_result>();
    }
    auto incarnation() const -> U64 {
        return query<__au_runtime_ap_worker_incarnation>();
    }
    auto target() const -> U64 {
        return query<__au_runtime_ap_worker_target>();
    }
    auto start() const -> I64 {
        return query<__au_runtime_ap_worker_start>();
    }
    auto count() const -> I64 {
        return query<__au_runtime_ap_worker_count>();
    }
};
} // namespace aurora::ap
