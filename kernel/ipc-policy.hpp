#pragma once
#include "domain-policy.hpp"
#include "ipc-transition-transport.hpp"
#include <array>
#include <cstdint>
#include <limits>
#include <optional>

namespace aurora::ipc {
// The adapter selects Phase from its continuation, never from the submitted words.
enum class Phase {
    inactive,
    request,
    service,
    completion
};
enum class State {
    idle,
    pending,
    delivered,
    replied,
    cancelled,
    consumed
};
enum class Outcome {
    replied,
    cancelled
};

// These are untrusted scalar claims. Neither claim can manufacture caller identity
// or select rights: only the fixed grant table below contains that authority.
class Endpoint final {
    std::uint64_t slot_{};
    std::uint64_t generation_{};

public:
    constexpr Endpoint() = default;
    constexpr Endpoint(std::uint64_t slot, std::uint64_t generation) : slot_(slot), generation_(generation) {
    }
    [[nodiscard]] constexpr auto slot() const -> std::uint64_t {
        return slot_;
    }
    [[nodiscard]] constexpr auto generation() const -> std::uint64_t {
        return generation_;
    }
};
class Request final {
    std::uint64_t first_{};
    std::uint64_t second_{};

public:
    constexpr Request() = default;
    constexpr Request(std::uint64_t first, std::uint64_t second) : first_(first), second_(second) {
    }
    [[nodiscard]] constexpr auto first() const -> std::uint64_t {
        return first_;
    }
    [[nodiscard]] constexpr auto second() const -> std::uint64_t {
        return second_;
    }
};
class Completion final {
    Outcome outcome_;
    std::uint64_t value_;

public:
    constexpr Completion(Outcome outcome, std::uint64_t value) : outcome_(outcome), value_(value) {
    }
    [[nodiscard]] constexpr auto outcome() const -> Outcome {
        return outcome_;
    }
    [[nodiscard]] constexpr auto value() const -> std::uint64_t {
        return value_;
    }
};

namespace detail {
// A generation ceiling only withholds authority; it cannot reset or seed stamps.
// This exact checked step is shared by allocation and boundary-value tests.
[[nodiscard]] constexpr auto generation_after(std::uint64_t previous, std::uint64_t ceiling)
    -> std::optional<std::uint64_t> {
    if (previous >= ceiling)
        return std::nullopt;
    return previous + 1;
}
} // namespace detail

// Single-CPU, bounded trusted bootstrap policy. One registry must outlive the
// mailbox. No allocation, user addresses, scheduler, or cross-CPU synchronization.
// The global sequence prevents endpoint/transaction resurrection after object
// destruction or rebind, including reconstruction at the same address.
class Mailbox final {
    enum class Right {
        client,
        service
    };
    class Grant final {
    public:
        user::DomainHandle owner{};
        std::uint64_t generation{};
        Right right = Right::client;
    };
    inline static std::uint64_t next_generation_{};
    const user::DomainRegistry &registry_;
    const std::uint64_t generation_ceiling_;
    std::array<Grant, 2> grants_{};
    bool bound_{};
    State state_ = State::idle;
    Request request_{};
    std::uint64_t reply_{};
    std::uint64_t transaction_{};

    [[nodiscard]] auto mint() -> std::optional<std::uint64_t> {
        const auto next = detail::generation_after(next_generation_, generation_ceiling_);
        if (next)
            next_generation_ = *next;
        return next;
    }
    [[nodiscard]] auto owns(user::DomainHandle caller, Endpoint endpoint, Right right) const -> bool {
        if (!bound_ || endpoint.slot() >= grants_.size() || endpoint.generation() == 0)
            return false;
        const auto &grant = grants_[endpoint.slot()];
        if (grant.generation != endpoint.generation() || grant.right != right)
            return false;
        const auto actual = registry_.index(caller), owner = registry_.index(grant.owner);
        return actual && owner && *actual == *owner;
    }
    [[nodiscard]] auto participants_live() const -> bool {
        return bound_ && registry_.index(grants_[0].owner) && registry_.index(grants_[1].owner);
    }
    [[nodiscard]] auto matches(std::uint64_t transaction) const -> bool {
        return transaction != 0 && transaction_ == transaction;
    }
    auto scrub() -> void {
        request_ = Request{};
        reply_ = 0;
    }
    [[nodiscard]] auto transition(TransactionOperation operation, Phase phase) const -> TransactionTransition {
        const auto original_phase = static_cast<std::uint64_t>(phase);
        const auto original_state = static_cast<std::uint64_t>(state_);
        const std::uint64_t original_scrubbed = scrubbed() ? 1 : 0;
        auto copied_phase = original_phase;
        // Fault profiles change only local copied inputs or the actual result.
        // Decoding always uses the original trusted facts; no live state changes.
#ifdef AURORA_IPC_POLICY_REQUEST_INPUT
        if (operation == TransactionOperation::submit)
            copied_phase = std::numeric_limits<std::uint64_t>::max();
#endif
#ifdef AURORA_IPC_POLICY_CANCEL_INPUT
        if (operation == TransactionOperation::cancel)
            copied_phase = std::numeric_limits<std::uint64_t>::max();
#endif
        auto encoded = language_ipc_transition(
            static_cast<std::uint64_t>(operation), copied_phase, original_state, original_scrubbed);
#ifdef AURORA_IPC_POLICY_REQUEST_OUTPUT
        if (operation == TransactionOperation::submit) {
            const volatile std::uint64_t reserved_bit = std::uint64_t{1} << 63;
            encoded |= reserved_bit;
        }
#endif
#ifdef AURORA_IPC_POLICY_CANCEL_OUTPUT
        if (operation == TransactionOperation::cancel) {
            const volatile std::uint64_t reserved_bit = std::uint64_t{1} << 63;
            encoded |= reserved_bit;
        }
#endif
        return TransactionTransition::decode(
            encoded, static_cast<std::uint64_t>(operation), original_phase, original_state, original_scrubbed);
    }

public:
    explicit Mailbox(const user::DomainRegistry &registry,
                     std::uint64_t generation_ceiling = std::numeric_limits<std::uint64_t>::max())
        : registry_(registry), generation_ceiling_(generation_ceiling) {
    }
    Mailbox(const Mailbox &) = delete;
    auto operator=(const Mailbox &) -> Mailbox & = delete;
    Mailbox(Mailbox &&) = delete;
    auto operator=(Mailbox &&) -> Mailbox & = delete;

    [[nodiscard]] auto bind(user::DomainHandle client, user::DomainHandle service) -> bool {
        const auto client_slot = registry_.index(client), service_slot = registry_.index(service);
        if (bound_ || state_ != State::idle || !scrubbed() || !client_slot || !service_slot ||
            *client_slot == *service_slot || !registry_.ready(client) || !registry_.ready(service))
            return false;
        const auto generation = mint();
        if (!generation)
            return false;
        grants_[0] = Grant{client, *generation, Right::client};
        grants_[1] = Grant{service, *generation, Right::service};
        bound_ = true;
        return true;
    }
    // Trusted launch preparation only: caller identity still comes from the
    // adapter's current DomainHandle, never from endpoint bits in user registers.
    [[nodiscard]] auto endpoint(user::DomainHandle owner) const -> std::optional<Endpoint> {
        if (!bound_)
            return std::nullopt;
        for (std::uint64_t slot = 0; slot < grants_.size(); ++slot) {
            const Endpoint candidate{slot, grants_[slot].generation};
            if (owns(owner, candidate, grants_[slot].right))
                return candidate;
        }
        return std::nullopt;
    }
    [[nodiscard]] auto submit(user::DomainHandle caller, Phase phase, Endpoint endpoint, Request request)
        -> std::optional<std::uint64_t> {
        if (!participants_live() || !owns(caller, endpoint, Right::client))
            return std::nullopt;
        const auto decision = transition(TransactionOperation::submit, phase);
        if (!decision.accepted())
            return std::nullopt;
        // Mint only after a checked accepted effect. A refusal cannot burn a stamp.
        const auto transaction = mint();
        if (!transaction)
            return std::nullopt;
        request_ = request;
        transaction_ = *transaction;
        state_ = static_cast<State>(decision.next());
        return transaction;
    }
    [[nodiscard]] auto receive(user::DomainHandle caller, Phase phase, Endpoint endpoint, std::uint64_t transaction)
        -> std::optional<Request> {
        if (!matches(transaction) || !participants_live() || !owns(caller, endpoint, Right::service))
            return std::nullopt;
        const auto decision = transition(TransactionOperation::receive, phase);
        if (!decision.accepted())
            return std::nullopt;
        const auto delivered = request_;
        request_ = Request{};
        state_ = static_cast<State>(decision.next());
        return delivered;
    }
    [[nodiscard]] auto
    reply(user::DomainHandle caller, Phase phase, Endpoint endpoint, std::uint64_t transaction, std::uint64_t value)
        -> bool {
        if (!matches(transaction) || !participants_live() || !owns(caller, endpoint, Right::service))
            return false;
        const auto decision = transition(TransactionOperation::reply, phase);
        if (!decision.accepted())
            return false;
        reply_ = value;
        state_ = static_cast<State>(decision.next());
        return true;
    }
    [[nodiscard]] auto consume(user::DomainHandle caller, Phase phase, Endpoint endpoint, std::uint64_t transaction)
        -> std::optional<Completion> {
        if (!matches(transaction) || !owns(caller, endpoint, Right::client) ||
            (state_ == State::replied && !participants_live()))
            return std::nullopt;
        const auto decision = transition(TransactionOperation::consume, phase);
        if (!decision.accepted())
            return std::nullopt;
        const Completion result{
            decision.effect() == TransactionEffect::consume_reply ? Outcome::replied : Outcome::cancelled, reply_};
        scrub();
        transaction_ = 0;
        state_ = static_cast<State>(decision.next());
        return result;
    }
    [[nodiscard]] auto cancel(Phase phase) -> bool {
        const auto decision = transition(TransactionOperation::cancel, phase);
        if (!decision.accepted())
            return false;
        scrub();
        state_ = static_cast<State>(decision.next());
        return true;
    }
    [[nodiscard]] auto recycle(Phase phase) -> bool {
        const auto decision = transition(TransactionOperation::recycle, phase);
        if (!decision.accepted())
            return false;
        transaction_ = 0;
        state_ = static_cast<State>(decision.next());
        return true;
    }
    [[nodiscard]] auto revoke(Phase phase) -> bool {
        if (phase != Phase::inactive || !bound_ || (state_ != State::idle && state_ != State::consumed) || !scrubbed())
            return false;
        grants_ = {};
        transaction_ = 0;
        bound_ = false;
        state_ = State::idle;
        return true;
    }
    [[nodiscard]] auto state() const -> State {
        return state_;
    }
    [[nodiscard]] auto scrubbed() const -> bool {
        return request_.first() == 0 && request_.second() == 0 && reply_ == 0;
    }
};
} // namespace aurora::ipc
