#pragma once
#include "ipc-policy.hpp"
#include "round-robin-transport.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <optional>

namespace aurora::ipc {
// A copied launch description, not authority derived from user register words.
class Work final {
    std::size_t client_;
    std::uint64_t transaction_;
    Request request_;
    Endpoint service_endpoint_;
public:
    constexpr Work(std::size_t client, std::uint64_t transaction, Request request, Endpoint endpoint)
        : client_(client), transaction_(transaction), request_(request), service_endpoint_(endpoint) {}
    [[nodiscard]] constexpr auto client() const -> std::size_t { return client_; }
    [[nodiscard]] constexpr auto transaction() const -> std::uint64_t { return transaction_; }
    [[nodiscard]] constexpr auto request() const -> Request { return request_; }
    [[nodiscard]] constexpr auto service_endpoint() const -> Endpoint { return service_endpoint_; }
};

// Copied trusted retirement receipt. An idle client has no transaction or
// completion. A consumed completion retains its original terminal result even
// if the client subsequently faults while inspecting that result.
class ClientDisposition final {
    friend class Dispatcher;
    State prior_state_;
    std::uint64_t transaction_;
    Completion completion_;
    constexpr ClientDisposition(State prior_state, std::uint64_t transaction, std::optional<Completion> completion)
        : prior_state_(prior_state), transaction_(transaction), completion_(completion.value_or(Completion{Outcome::cancelled, 0})) {}
public:
    [[nodiscard]] constexpr auto prior_state() const -> State { return prior_state_; }
    [[nodiscard]] constexpr auto transaction() const -> std::optional<std::uint64_t> {
        return transaction_ == 0 ? std::nullopt : std::optional{transaction_};
    }
    [[nodiscard]] constexpr auto completion() const -> std::optional<Completion> {
        return transaction_ == 0 ? std::nullopt : std::optional{completion_};
    }
};

// Single-CPU staged dispatch: two incarnation-bound client slots, one service and
// one outstanding request per client. The registry must outlive this object.
// Mailbox generations remain the sole source of endpoint/transaction stamps.
// Round-robin bounds selection among admitted requests; the trusted adapter must
// contain client execution and prove quiescence before disposal. This is not a
// general scheduler or SMP policy.
class Dispatcher final {
public:
    static constexpr std::size_t capacity = 2;
private:
    const user::DomainRegistry& registry_;
    std::array<Mailbox, capacity> mailboxes_;
    std::array<user::DomainHandle, capacity> clients_{};
    user::DomainHandle service_{};
    std::array<std::uint64_t, capacity> transactions_{};
    std::array<ClientDisposition, capacity> completion_receipts_{
        ClientDisposition{State::idle, 0, std::nullopt}, ClientDisposition{State::idle, 0, std::nullopt}};
    std::array<bool, capacity> disposed_{};
    std::optional<std::size_t> selected_{};
    std::size_t next_client_{};
    bool bound_{};

    auto scrub_completion_receipt(std::size_t client) -> void {
        // Keep fixed live storage so clearing an optional cannot leave the old
        // copied completion words behind after the receipt's lifetime ends.
        completion_receipts_[client] = ClientDisposition{State::idle, 0, std::nullopt};
    }
    [[nodiscard]] auto client_index(user::DomainHandle caller) const -> std::optional<std::size_t> {
        if (!bound_) return std::nullopt;
        const auto actual = registry_.index(caller);
        if (!actual) return std::nullopt;
        for (std::size_t index = 0; index < capacity; ++index) {
            if (disposed_[index]) continue;
            const auto owner = registry_.index(clients_[index]);
            if (owner && *actual == *owner) return index;
        }
        return std::nullopt;
    }
public:
    explicit Dispatcher(const user::DomainRegistry& registry,
                        std::uint64_t generation_ceiling = std::numeric_limits<std::uint64_t>::max())
        : registry_(registry), mailboxes_{Mailbox{registry, generation_ceiling},
                                        Mailbox{registry, generation_ceiling}} {}
    Dispatcher(const Dispatcher&) = delete;
    auto operator=(const Dispatcher&) -> Dispatcher& = delete;
    Dispatcher(Dispatcher&&) = delete;
    auto operator=(Dispatcher&&) -> Dispatcher& = delete;

    [[nodiscard]] auto bind(std::array<user::DomainHandle, capacity> clients, user::DomainHandle service) -> bool {
        if (bound_ || selected_ || !scrubbed()) return false;
        const auto first = registry_.index(clients[0]), second = registry_.index(clients[1]);
        const auto server = registry_.index(service);
        if (!first || !second || !server || *first == *second || *first == *server || *second == *server
            || !registry_.ready(clients[0]) || !registry_.ready(clients[1]) || !registry_.ready(service)) return false;
        if (!mailboxes_[0].bind(clients[0], service)) return false;
        if (!mailboxes_[1].bind(clients[1], service)) {
            // No request exists yet. Revoke the first grant if the global mint
            // reaches its ceiling between the two binds; no partial admission.
            const bool revoked = mailboxes_[0].revoke(Phase::inactive);
            (void)revoked;
            return false;
        }
        clients_ = clients;
        service_ = service;
        transactions_ = {};
        for (std::size_t client = 0; client < capacity; ++client) scrub_completion_receipt(client);
        disposed_ = {};
        next_client_ = 0;
        bound_ = true;
        return true;
    }
    // Trusted launch preparation. The actual actor is a DomainHandle supplied
    // by the adapter, never a client index or an endpoint claimed by userspace.
    [[nodiscard]] auto endpoint(std::size_t client, user::DomainHandle actor) const -> std::optional<Endpoint> {
        if (!bound_ || client >= capacity) return std::nullopt;
        return mailboxes_[client].endpoint(actor);
    }
    [[nodiscard]] auto submit(user::DomainHandle caller, Phase phase, Endpoint endpoint, Request request)
        -> std::optional<std::uint64_t> {
        const auto client = client_index(caller);
        if (!client) return std::nullopt;
        const auto transaction = mailboxes_[*client].submit(caller, phase, endpoint, request);
        if (transaction) transactions_[*client] = *transaction;
        return transaction;
    }
    [[nodiscard]] auto select(Phase phase) -> std::optional<Work> {
        if (phase != Phase::inactive || !bound_ || selected_ || !registry_.ready(service_)) return std::nullopt;
        static_assert(capacity == 2);
        std::array<std::optional<Endpoint>, capacity> grants{};
        std::uint64_t eligible_mask = 0;
        for (std::size_t client = 0; client < capacity; ++client) {
            if (disposed_[client] || mailboxes_[client].state() != State::pending
                || !registry_.index(clients_[client]) || transactions_[client] == 0) continue;
            grants[client] = mailboxes_[client].endpoint(service_);
            if (grants[client]) eligible_mask |= std::uint64_t{1} << client;
        }
        // Fault modes alter local copied inputs/output only, after the existing
        // launch/registry checks. No live cursor, mailbox or grant is corrupted.
        std::uint64_t policy_cursor = next_client_, policy_mask = eligible_mask;
#ifdef AURORA_DISPATCH_POLICY_CURSOR
        policy_cursor = std::numeric_limits<std::uint64_t>::max();
#endif
#ifdef AURORA_DISPATCH_POLICY_MASK
        policy_mask = std::numeric_limits<std::uint64_t>::max();
#endif
        auto encoded = language_round_robin_next(policy_cursor, policy_mask);
#ifdef AURORA_DISPATCH_POLICY_OUTPUT
        const volatile std::uint64_t reserved_bit = std::uint64_t{1} << 63;
        encoded |= reserved_bit;
#endif
        const auto selection = RoundRobinSelection::decode(encoded, next_client_, eligible_mask);
        if (!selection || !selection->selected()) return std::nullopt;
        const auto client = selection->client();
        // The pure result is only a choice. Recheck real authority and perform
        // the actual mailbox receive before committing selected state or cursor.
        if (!grants[client]) return std::nullopt;
        const auto request = mailboxes_[client].receive(service_, Phase::service, *grants[client], transactions_[client]);
        if (!request) return std::nullopt;
        selected_ = client;
        next_client_ = selection->next();
        return Work{client, transactions_[client], *request, *grants[client]};
    }
    [[nodiscard]] auto reply(user::DomainHandle caller, Phase phase, Endpoint endpoint,
                             std::uint64_t transaction, std::uint64_t value) -> bool {
        if (!selected_) return false;
        // Even a valid service grant for the other mailbox cannot route a reply.
        return mailboxes_[*selected_].reply(caller, phase, endpoint, transaction, value);
    }
    // Only the adapter can attest that its timer, pending IRQ and saved service
    // continuation are quiescent. A terminal reply alone cannot release selection.
    [[nodiscard]] auto finish_selected(Phase phase, bool adapter_quiescent) -> bool {
        if (phase != Phase::inactive || !adapter_quiescent || !selected_) return false;
        const auto state = mailboxes_[*selected_].state();
        if (state != State::replied && state != State::cancelled) return false;
        selected_.reset();
        return true;
    }
    [[nodiscard]] auto consume(user::DomainHandle caller, Phase phase, Endpoint endpoint, std::uint64_t transaction)
        -> std::optional<Completion> {
        const auto client = client_index(caller);
        if (!client || selected_ == client) return std::nullopt;
        const auto result = mailboxes_[*client].consume(caller, phase, endpoint, transaction);
        if (result) {
            completion_receipts_[*client] = ClientDisposition{State::consumed, transaction, *result};
            transactions_[*client] = 0;
        }
        return result;
    }
    [[nodiscard]] auto recycle(Phase phase, std::size_t client) -> bool {
        if (!bound_ || client >= capacity || selected_ == client) return false;
        if (!mailboxes_[client].recycle(phase)) return false;
        scrub_completion_receipt(client);
        return true;
    }
    // Kernel-only recovery after a verified fault/budget event. Phase, actual
    // offender and quiescence come from adapter authority, never user words.
    // The owner must still be live: revoke before destroying its registry entry.
    // A selected offender must first reach a terminal state and pass
    // finish_selected; peer selection, copied records and cursor are untouched.
    [[nodiscard]] auto dispose_client(Phase phase, std::size_t client, user::DomainHandle actual_offender,
                                      bool adapter_quiescent) -> std::optional<ClientDisposition> {
        if (phase != Phase::inactive || !adapter_quiescent || !bound_ || client >= capacity
            || disposed_[client] || selected_ == client || !registry_.ready(actual_offender)
            || !registry_.ready(service_)) return std::nullopt;
        const auto actual = registry_.index(actual_offender), owner = registry_.index(clients_[client]);
        if (!actual || !owner || *actual != *owner) return std::nullopt;
        auto& mailbox = mailboxes_[client];
        const auto prior_state = mailbox.state();
        auto disposition = ClientDisposition{prior_state, 0, std::nullopt};
        if (prior_state == State::consumed) {
            if (!completion_receipts_[client].transaction()) return std::nullopt;
            disposition = completion_receipts_[client];
        } else if (prior_state != State::idle) {
            const auto grant = mailbox.endpoint(actual_offender);
            if (!grant || transactions_[client] == 0) return std::nullopt;
            // First terminal state wins. cancel cannot replace a committed reply.
            if (prior_state == State::pending || prior_state == State::delivered) {
                if (!mailbox.cancel(phase)) return std::nullopt;
            }
            const auto completion = mailbox.consume(actual_offender, Phase::completion, *grant, transactions_[client]);
            if (!completion) return std::nullopt;
            disposition = ClientDisposition{prior_state, transactions_[client], *completion};
        }
        // The checked live owner/service and terminal-state path above establish
        // consumption/revocation preconditions without changing any peer record.
        if (!mailbox.revoke(phase)) return std::nullopt;
        transactions_[client] = 0;
        scrub_completion_receipt(client);
        disposed_[client] = true;
        // Keep the old handle as a tombstone until actual domain retirement.
        return disposition;
    }
    [[nodiscard]] auto rebind_client(Phase phase, std::size_t client, user::DomainHandle replacement) -> bool {
        if (phase != Phase::inactive || !bound_ || client >= capacity || !disposed_[client]
            || selected_ == client || registry_.index(clients_[client]) || !registry_.ready(replacement)
            || !registry_.ready(service_)) return false;
        const auto candidate = registry_.index(replacement), service = registry_.index(service_);
        const auto peer = registry_.index(clients_[(client + 1) % capacity]);
        if (!candidate || !service || *candidate == *service || (peer && *candidate == *peer)) return false;
        if (!mailboxes_[client].bind(replacement, service_)) return false;
        clients_[client] = replacement;
        disposed_[client] = false;
        return true;
    }
    [[nodiscard]] auto cancel_pending(Phase phase) -> std::size_t {
        if (phase != Phase::inactive || !bound_) return 0;
        std::size_t cancelled = 0;
        for (auto& mailbox : mailboxes_) {
            if (mailbox.cancel(phase)) ++cancelled;
        }
        return cancelled;
    }
    [[nodiscard]] auto revoke(Phase phase) -> bool {
        if (phase != Phase::inactive || !bound_ || selected_ || !scrubbed()) return false;
        for (const auto& mailbox : mailboxes_) {
            if (mailbox.state() != State::idle && mailbox.state() != State::consumed) return false;
        }
        // Preconditions establish every remaining grant can be revoked before
        // mutation; disposed slots have already revoked their own grants.
        for (std::size_t client = 0; client < capacity; ++client) {
            if (disposed_[client]) continue;
            const bool revoked = mailboxes_[client].revoke(phase);
            (void)revoked;
        }
        clients_ = {};
        service_ = {};
        transactions_ = {};
        for (std::size_t client = 0; client < capacity; ++client) scrub_completion_receipt(client);
        disposed_ = {};
        next_client_ = 0;
        bound_ = false;
        return true;
    }
    [[nodiscard]] auto bound() const -> bool { return bound_; }
    [[nodiscard]] auto state(std::size_t client) const -> std::optional<State> {
        if (client >= capacity) return std::nullopt;
        return mailboxes_[client].state();
    }
    [[nodiscard]] auto transaction(std::size_t client) const -> std::optional<std::uint64_t> {
        if (!bound_ || client >= capacity || transactions_[client] == 0) return std::nullopt;
        return transactions_[client];
    }
    [[nodiscard]] auto queued() const -> std::size_t {
        std::size_t count = 0;
        for (const auto& mailbox : mailboxes_) if (mailbox.state() == State::pending) ++count;
        return count;
    }
    [[nodiscard]] auto occupied() const -> std::size_t {
        std::size_t count = 0;
        for (const auto& mailbox : mailboxes_) {
            if (mailbox.state() != State::idle && mailbox.state() != State::consumed) ++count;
        }
        return count;
    }
    [[nodiscard]] auto selected() const -> std::optional<std::size_t> { return selected_; }
    [[nodiscard]] auto next_client() const -> std::size_t { return next_client_; }
    [[nodiscard]] auto all_consumed() const -> bool {
        return bound_ && mailboxes_[0].state() == State::consumed && mailboxes_[1].state() == State::consumed;
    }
    // Mailbox payloads only: trusted consumed receipts persist until recycle,
    // disposal or full revocation so a later completion fault keeps its outcome.
    [[nodiscard]] auto scrubbed() const -> bool {
        return mailboxes_[0].scrubbed() && mailboxes_[1].scrubbed();
    }
};
}
