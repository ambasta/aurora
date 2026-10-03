#pragma once
#include "ipc-policy.hpp"
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

// Single-CPU staged dispatch: two immutable client identities, one service and
// one outstanding request per client. The registry must outlive this object.
// Mailbox generations remain the sole source of endpoint/transaction stamps.
// Round-robin bounds selection among admitted requests; client phases must still
// return cooperatively. This is neither preemptive client scheduling nor SMP.
class Dispatcher final {
public:
    static constexpr std::size_t capacity = 2;
private:
    const user::DomainRegistry& registry_;
    std::array<Mailbox, capacity> mailboxes_;
    std::array<user::DomainHandle, capacity> clients_{};
    user::DomainHandle service_{};
    std::array<std::uint64_t, capacity> transactions_{};
    std::optional<std::size_t> selected_{};
    std::size_t next_client_{};
    bool bound_{};

    [[nodiscard]] auto client_index(user::DomainHandle caller) const -> std::optional<std::size_t> {
        if (!bound_) return std::nullopt;
        const auto actual = registry_.index(caller);
        if (!actual) return std::nullopt;
        for (std::size_t index = 0; index < capacity; ++index) {
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
        for (std::size_t offset = 0; offset < capacity; ++offset) {
            const auto client = (next_client_ + offset) % capacity;
            if (mailboxes_[client].state() != State::pending) continue;
            const auto grant = mailboxes_[client].endpoint(service_);
            if (!grant) continue;
            const auto request = mailboxes_[client].receive(service_, Phase::service, *grant, transactions_[client]);
            if (!request) continue;
            selected_ = client;
            next_client_ = (client + 1) % capacity;
            return Work{client, transactions_[client], *request, *grant};
        }
        return std::nullopt;
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
        if (result) transactions_[*client] = 0;
        return result;
    }
    [[nodiscard]] auto recycle(Phase phase, std::size_t client) -> bool {
        if (!bound_ || client >= capacity || selected_ == client) return false;
        return mailboxes_[client].recycle(phase);
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
        // Preconditions establish both revocations can succeed before mutation.
        for (auto& mailbox : mailboxes_) {
            const bool revoked = mailbox.revoke(phase);
            (void)revoked;
        }
        clients_ = {};
        service_ = {};
        transactions_ = {};
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
    [[nodiscard]] auto scrubbed() const -> bool {
        return mailboxes_[0].scrubbed() && mailboxes_[1].scrubbed();
    }
};
}
