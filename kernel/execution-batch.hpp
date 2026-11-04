#pragma once
#include "resident-owner.hpp"
#include "retained-endpoint.hpp"
#include <cstddef>
#include <cstdint>

namespace aurora::batch {
using U64 = std::uint64_t;
// A staged request has not reached the service. The caller's exact identity and
// endpoint incarnation permit withdrawal after its execution budget expires.
// source may still identify an earlier operation; it is not the staged client.
inline auto
can_withdraw_staged(U64 slot, U64 caller, U64 client, U64 generation, const aurora::endpoint::Observation &observation)
    -> bool {
    return (slot == 1 || slot == 2) && caller == slot && client != 0 && generation != 0 &&
           observation.phase == aurora::endpoint::Phase::staged && observation.client == client &&
           observation.incarnation == generation;
}

enum class Action : U64 {
    admit,
    load,
    activate,
    output,
    request,
    retire,
    close,
    abandon,
    done,
    input_poll,
    input_wait
};
enum class Event : U64 {
    success,
    refused,
    parked,
    output,
    request,
    terminal,
    pending,
    service_lost,
    output_failed,
    cancelled,
    input
};
class Request final {
public:
    Action action = Action::done;
    U64 child = 0, ordinal = 0, status = 0, value = 0, quota = 0;
    auto operator==(const Request &) const -> bool = default;
};
class Result final {
public:
    U64 admission = 6, status1 = 8, value1 = 0, status2 = 8, value2 = 0;
};
static_assert(sizeof(Request) == 48 && sizeof(Result) == 40);
extern "C" {
void __au_runtime_batch_create(void *);
void __au_runtime_batch_next(void *, Request *);
bool __au_runtime_batch_accept(void *, U64, Event, U64, U64);
void __au_runtime_batch_result(const void *, Result *);
}

// One lexical native operation pins its enclosing immutable resident context.
// Only source owns the action/cursor/lifecycle/result ledger. A Request is copied
// observation, not authority: begin_effect authenticates it against this exact
// root before native authenticates the selected slot and physical resources.
// Platform supplies capture_parent, valid(binding,parent), enter/leave,
// settled(binding), release_parent and fail. No source loan crosses an effect.
template <class Platform> class Root final {
    alignas(16) std::byte storage_[160]{};
    const void *const binding_;
    const resident::Parent parent_;
    Request receipt_{};
    bool borrowed_ = false, pending_ = false, in_flight_ = false, finished_ = false;
    static auto require(bool valid) -> void {
        if (!valid)
            Platform::fail();
    }
    auto enter() -> void {
        require(!finished_ && !borrowed_ && Platform::valid(binding_, parent_));
        borrowed_ = true;
        Platform::enter();
    }
    auto leave() -> void {
        require(borrowed_ && Platform::valid(binding_, parent_));
        Platform::leave();
        borrowed_ = false;
    }
    static auto valid(const Request &request) -> bool {
        if (static_cast<U64>(request.action) > static_cast<U64>(Action::input_wait) || request.status > 8)
            return false;
        if (request.quota != (request.action == Action::load ? 4096 : 0))
            return false;
        if ((request.action == Action::input_poll || request.action == Action::input_wait) &&
            (request.child != 1 || request.status != 8 || request.value != 0))
            return false;
        const bool global =
            request.action == Action::admit || request.action == Action::abandon || request.action == Action::done;
        return (global ? request.child == 0 : request.child == 1 || request.child == 2) &&
               (request.action == Action::done || request.ordinal != 0);
    }

public:
    explicit Root(const void *binding) : binding_(binding), parent_(Platform::capture_parent()) {
        require(binding_ != nullptr);
        enter();
        __au_runtime_batch_create(storage_);
        leave();
    }
    Root(const Root &) = delete;
    Root(Root &&) = delete;
    auto operator=(const Root &) -> Root & = delete;
    auto operator=(Root &&) -> Root & = delete;
    ~Root() {
        require(finished_ && !borrowed_ && !pending_ && !in_flight_);
    }
    auto next() -> Request {
        require(!pending_ && !in_flight_);
        enter();
        Request request;
        __au_runtime_batch_next(storage_, &request);
        require(valid(request));
        leave();
        if (request.action != Action::done) {
            receipt_ = request;
            pending_ = true;
        }
        return request;
    }
    auto begin_effect(const Request &request) -> void {
        require(pending_ && !in_flight_ && request == receipt_);
        enter();
        Request canonical;
        __au_runtime_batch_next(storage_, &canonical);
        require(valid(canonical) && canonical == receipt_);
        leave();
        in_flight_ = true;
    }
    auto accept(Event event, U64 status = 0, U64 value = 0) -> void {
        require(pending_ && in_flight_ && static_cast<U64>(event) <= static_cast<U64>(Event::input) && status <= 8);
        enter();
        require(__au_runtime_batch_accept(storage_, receipt_.ordinal, event, status, value));
        leave();
        in_flight_ = false;
        pending_ = false;
        receipt_ = {};
    }
    auto finish() -> Result {
        require(!pending_ && !in_flight_ && Platform::valid(binding_, parent_) && Platform::settled(binding_));
        enter();
        Request canonical;
        __au_runtime_batch_next(storage_, &canonical);
        require(valid(canonical) && canonical.action == Action::done);
        Result result;
        __au_runtime_batch_result(storage_, &result);
        require(result.admission <= 8 && result.status1 <= 8 && result.status2 <= 8);
        leave();
        Platform::release_parent(parent_);
        for (auto &byte : storage_)
            *static_cast<volatile std::byte *>(&byte) = std::byte{};
        finished_ = true;
        return result;
    }
};
} // namespace aurora::batch
