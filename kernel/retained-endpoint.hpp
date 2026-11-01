#pragma once
#include <cstddef>
#include <cstdint>

namespace aurora::endpoint {
using U64 = std::uint64_t;
enum class Phase : U64 {
    absent,
    initial,
    waiting,
    staged,
    delivery,
    processing,
    replied,
    completion,
    revoked
};
enum class Exchange : U64 {
    refused,
    initial,
    reply
};
enum class Step : U64 {
    failed,
    launch,
    resume,
    replied
};
enum class Consume : U64 {
    refused,
    completion,
    cancelled,
    tail
};
enum class Cancel : U64 {
    refused,
    settled,
    draining
};
enum class Completion : U64 {
    none,
    service,
    client
};
class Observation final {
public:
    U64 incarnation;
    Phase phase;
    U64 next, transaction, source, client;
    // Read-only projections for physical assertions and existing diagnostics.
    // Orchestration dispatches the source owner's semantic action results.
    auto waiting() const -> bool {
        return phase == Phase::waiting || phase == Phase::staged || phase == Phase::delivery ||
               phase == Phase::replied || phase == Phase::completion;
    }
    auto replied() const -> bool {
        return phase == Phase::replied;
    }
    auto delivery() const -> bool {
        return phase == Phase::delivery;
    }
    auto completion() const -> bool {
        return phase == Phase::completion;
    }
};
static_assert(sizeof(Observation) == 48);
extern "C" {
void __au_runtime_endpoint_create(void *, U64);
bool __au_runtime_endpoint_bind(void *, U64);
bool __au_runtime_endpoint_reset(void *);
void __au_runtime_endpoint_observe(const void *, Observation *);
Exchange __au_runtime_endpoint_accept_exchange(void *, U64, U64, U64);
bool __au_runtime_endpoint_stage_client(void *, U64);
bool __au_runtime_endpoint_begin(void *, U64);
Step __au_runtime_endpoint_client_step(void *, U64);
Step __au_runtime_endpoint_step(const void *);
Step __au_runtime_endpoint_initial_step(const void *);
Step __au_runtime_endpoint_observe_step(const void *, bool);
Completion __au_runtime_endpoint_completion(const void *);
bool __au_runtime_endpoint_delivered(void *, U64, U64);
bool __au_runtime_endpoint_consume_control(void *, U64);
Consume __au_runtime_endpoint_consume_client(void *, U64, bool, bool);
bool __au_runtime_endpoint_complete_client(void *, U64);
Cancel __au_runtime_endpoint_cancel(void *, U64, bool);
bool __au_runtime_endpoint_finish_client(void *, U64);
bool __au_runtime_endpoint_invalidate(void *, U64);
}

// One stable source object owns the policy. The native object holds only opaque
// storage and loan exclusion, and is never moved, copied or reentered.
template <class Platform> class Root final {
    alignas(16) std::byte storage_[48]{};
    bool live_ = false;
    mutable bool borrowed_ = false;
    static void require(bool valid) {
        if (!valid)
            Platform::fail();
    }
    void enter(bool live) const {
        require(live_ == live && !borrowed_);
        borrowed_ = true;
        Platform::enter();
    }
    void leave() const {
        require(borrowed_);
        Platform::leave();
        borrowed_ = false;
    }

public:
    constexpr Root() = default;
    Root(const Root &) = delete;
    Root(Root &&) = delete;
    auto operator=(const Root &) -> Root & = delete;
    auto operator=(Root &&) -> Root & = delete;
    void create(U64 previous = 0) {
        enter(false);
        __au_runtime_endpoint_create(storage_, previous);
        live_ = true;
        leave();
    }
    auto bind(U64 incarnation) -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_bind(storage_, incarnation);
        leave();
        return result;
    }
    auto reset() -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_reset(storage_);
        leave();
        return result;
    }
    auto observe() const -> Observation {
        enter(true);
        Observation result{};
        __au_runtime_endpoint_observe(storage_, &result);
        leave();
        return result;
    }
    auto accept_exchange(U64 incarnation, U64 transaction, U64 count) -> Exchange {
        enter(true);
        const auto result = __au_runtime_endpoint_accept_exchange(storage_, incarnation, transaction, count);
        leave();
        return result;
    }
    auto stage_client(U64 client) -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_stage_client(storage_, client);
        leave();
        return result;
    }
    auto begin(U64 source) -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_begin(storage_, source);
        leave();
        return result;
    }
    auto client_step(U64 client) -> Step {
        enter(true);
        const auto result = __au_runtime_endpoint_client_step(storage_, client);
        leave();
        return result;
    }
    auto initial_step() const -> Step {
        enter(true);
        const auto result = __au_runtime_endpoint_initial_step(storage_);
        leave();
        return result;
    }
    auto step() const -> Step {
        enter(true);
        const auto result = __au_runtime_endpoint_step(storage_);
        leave();
        return result;
    }
    auto observe_step(bool service_alive) const -> Step {
        enter(true);
        const auto result = __au_runtime_endpoint_observe_step(storage_, service_alive);
        leave();
        return result;
    }
    auto completion() const -> Completion {
        enter(true);
        const auto result = __au_runtime_endpoint_completion(storage_);
        leave();
        return result;
    }
    auto delivered(U64 incarnation, U64 transaction) -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_delivered(storage_, incarnation, transaction);
        leave();
        return result;
    }
    auto consume_control(U64 transaction) -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_consume_control(storage_, transaction);
        leave();
        return result;
    }
    auto consume_client(U64 transaction, bool cancelled, bool more) -> Consume {
        enter(true);
        const auto result = __au_runtime_endpoint_consume_client(storage_, transaction, cancelled, more);
        leave();
        return result;
    }
    auto complete_client(U64 client) -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_complete_client(storage_, client);
        leave();
        return result;
    }
    auto cancel(U64 client, bool cancelled) -> Cancel {
        enter(true);
        const auto result = __au_runtime_endpoint_cancel(storage_, client, cancelled);
        leave();
        return result;
    }
    auto finish_client(U64 client) -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_finish_client(storage_, client);
        leave();
        return result;
    }
    auto invalidate(U64 incarnation) -> bool {
        enter(true);
        const auto result = __au_runtime_endpoint_invalidate(storage_, incarnation);
        leave();
        return result;
    }
};
} // namespace aurora::endpoint
