#include "../kernel/dispatch-policy.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <optional>
#include <string_view>
#include <type_traits>

namespace kernel_client_disposal {
using namespace aurora::ipc;
using aurora::user::DomainHandle;
using aurora::user::DomainRegistry;
constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
constexpr std::uint64_t request_first = 0x18b6dfe45a2793c1ULL;
constexpr std::uint64_t request_second = 0x39c7ea8604bf521dULL;
constexpr std::uint64_t reply_word = 0x62e3ba0f17d9c485ULL;
static_assert(std::is_trivially_copyable_v<ClientDisposition>);
static_assert(!std::is_default_constructible_v<ClientDisposition>);

auto check(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
auto same(const std::optional<Endpoint> &first, const std::optional<Endpoint> &second) -> bool {
    return first.has_value() == second.has_value() &&
           (!first || (first->slot() == second->slot() && first->generation() == second->generation()));
}
using PolicyBytes = std::array<unsigned char, sizeof(Dispatcher)>;
auto bytes(const Dispatcher &dispatch) -> PolicyBytes {
    PolicyBytes result{};
    std::memcpy(result.data(), &dispatch, result.size());
    return result;
}
auto contains_word(const Dispatcher &dispatch, std::uint64_t value) -> bool {
    const auto snapshot = bytes(dispatch);
    for (std::size_t offset = 0; offset + sizeof(value) <= snapshot.size(); ++offset) {
        if (std::memcmp(snapshot.data() + offset, &value, sizeof(value)) == 0)
            return true;
    }
    return false;
}
class Fixture final {
public:
    DomainRegistry domains{}, foreign{};
    std::array<DomainHandle, 2> clients{};
    DomainHandle service{}, outsider{};
    Dispatcher dispatch;
    std::array<Endpoint, 2> client_caps{}, service_caps{};
    std::array<std::uint64_t, 2> transactions{};
    explicit Fixture(std::uint64_t ceiling = maximum) : dispatch(domains, ceiling) {
        clients[0] = *domains.create();
        service = *domains.create();
        clients[1] = *domains.create();
        outsider = *foreign.create();
        check(dispatch.bind(clients, service), "fixture binding");
        refresh(0);
        refresh(1);
    }
    auto refresh(std::size_t client) -> void {
        client_caps[client] = *dispatch.endpoint(client, clients[client]);
        service_caps[client] = *dispatch.endpoint(client, service);
    }
    auto submit(std::size_t client, Request request = Request{request_first, request_second}) -> void {
        const auto result = dispatch.submit(clients[client], Phase::request, client_caps[client], request);
        check(result.has_value(), "fixture submission");
        transactions[client] = *result;
    }
    auto select(std::size_t client) -> Work {
        const auto work = dispatch.select(Phase::inactive);
        check(work && work->client() == client && work->transaction() == transactions[client], "fixture selection");
        return *work;
    }
    auto reply(std::size_t client, std::uint64_t value = reply_word) -> void {
        check(dispatch.reply(service, Phase::service, service_caps[client], transactions[client], value),
              "fixture reply");
    }
    auto finish() -> void {
        check(dispatch.finish_selected(Phase::inactive, true), "fixture quiescent finish");
    }
    auto consume(std::size_t client, Outcome outcome = Outcome::replied, std::uint64_t value = reply_word) -> void {
        const auto result =
            dispatch.consume(clients[client], Phase::completion, client_caps[client], transactions[client]);
        check(result && result->outcome() == outcome && result->value() == value, "fixture consume");
    }
    auto rebirth(std::size_t client) -> void {
        check(domains.destroy(clients[client]), "old client retirement");
        clients[client] = *domains.create();
        check(dispatch.rebind_client(Phase::inactive, client, clients[client]), "fresh client rebind");
        refresh(client);
    }
};
class PeerSnapshot final {
    std::size_t client_;
    std::optional<State> state_;
    std::optional<std::uint64_t> transaction_;
    std::optional<Endpoint> client_cap_, service_cap_;
    std::optional<std::size_t> selected_;
    std::size_t cursor_;

public:
    PeerSnapshot(const Fixture &fixture, std::size_t client)
        : client_(client), state_(fixture.dispatch.state(client)), transaction_(fixture.dispatch.transaction(client)),
          client_cap_(fixture.dispatch.endpoint(client, fixture.clients[client])),
          service_cap_(fixture.dispatch.endpoint(client, fixture.service)), selected_(fixture.dispatch.selected()),
          cursor_(fixture.dispatch.next_client()) {
    }
    auto unchanged(const Fixture &fixture) const -> bool {
        return fixture.dispatch.bound() && state_ == fixture.dispatch.state(client_) &&
               transaction_ == fixture.dispatch.transaction(client_) &&
               same(client_cap_, fixture.dispatch.endpoint(client_, fixture.clients[client_])) &&
               same(service_cap_, fixture.dispatch.endpoint(client_, fixture.service)) &&
               selected_ == fixture.dispatch.selected() && cursor_ == fixture.dispatch.next_client();
    }
};
template <class Operation> auto rejects(Fixture &fixture, Operation operation) -> void {
    const auto before = bytes(fixture.dispatch);
    check(!operation(), "invalid operation denied");
    check(bytes(fixture.dispatch) == before, "rejected operation preserves every policy byte");
}
auto disposition(const ClientDisposition &result,
                 State state,
                 std::optional<std::uint64_t> transaction,
                 Outcome outcome = Outcome::cancelled,
                 std::uint64_t value = 0) -> void {
    check(result.prior_state() == state && result.transaction() == transaction,
          "exact disposition state and transaction");
    const auto completion = result.completion();
    check(completion.has_value() == transaction.has_value(), "idle has no fabricated terminal outcome");
    if (completion)
        check(completion->outcome() == outcome && completion->value() == value, "first terminal disposition preserved");
}
auto dispose(Fixture &fixture, std::size_t client) -> ClientDisposition {
    const PeerSnapshot peer{fixture, 1 - client};
    const auto result = fixture.dispatch.dispose_client(Phase::inactive, client, fixture.clients[client], true);
    check(result.has_value(), "valid client disposal");
    check(peer.unchanged(fixture), "disposal preserves peer state, grants, transaction, selection and cursor");
    check(fixture.dispatch.state(client) == State::idle && !fixture.dispatch.transaction(client) &&
              !fixture.dispatch.endpoint(client, fixture.clients[client]) &&
              !fixture.dispatch.endpoint(client, fixture.service),
          "disposed mailbox idle with both local grants revoked");
    return *result;
}

auto all_dispositions_and_scrub() -> void {
    for (const auto state :
         {State::idle, State::pending, State::delivered, State::replied, State::cancelled, State::consumed}) {
        for (const auto consumed_outcome : {Outcome::replied, Outcome::cancelled}) {
            Fixture fixture;
            if (state != State::idle)
                fixture.submit(0);
            if (state == State::delivered || state == State::replied ||
                (state == State::consumed && consumed_outcome == Outcome::replied)) {
                const auto work = fixture.select(0);
                check(work.request().first() == request_first && work.request().second() == request_second,
                      "copied request exact");
            }
            if (state == State::replied || (state == State::consumed && consumed_outcome == Outcome::replied)) {
                fixture.reply(0);
                fixture.finish();
            }
            if (state == State::cancelled || (state == State::consumed && consumed_outcome == Outcome::cancelled))
                check(fixture.dispatch.cancel_pending(Phase::inactive) == 1, "terminal cancellation setup");
            if (state == State::consumed)
                fixture.consume(0, consumed_outcome, consumed_outcome == Outcome::replied ? reply_word : 0);
            if (state == State::delivered) {
                rejects(fixture, [&] {
                    return fixture.dispatch.dispose_client(Phase::inactive, 0, fixture.clients[0], true).has_value();
                });
                check(fixture.dispatch.cancel_pending(Phase::inactive) == 1,
                      "selected delivery reaches terminal cancellation");
                rejects(fixture, [&] {
                    return fixture.dispatch.dispose_client(Phase::inactive, 0, fixture.clients[0], true).has_value();
                });
                rejects(fixture, [&] {
                    return fixture.dispatch.finish_selected(Phase::inactive, false);
                });
                fixture.finish();
            }
            const auto expected_state = state == State::delivered ? State::cancelled : state;
            const auto expected_outcome =
                state == State::replied || (state == State::consumed && consumed_outcome == Outcome::replied)
                    ? Outcome::replied
                    : Outcome::cancelled;
            if (expected_outcome == Outcome::replied)
                check(contains_word(fixture.dispatch, reply_word), "live completion receipt retains exact reply word");
            const auto result = dispose(fixture, 0);
            disposition(result,
                        expected_state,
                        state == State::idle ? std::nullopt : std::optional{fixture.transactions[0]},
                        expected_outcome,
                        expected_outcome == Outcome::replied ? reply_word : 0);
            check(fixture.dispatch.scrubbed() && !contains_word(fixture.dispatch, request_first) &&
                      !contains_word(fixture.dispatch, request_second) && !contains_word(fixture.dispatch, reply_word),
                  "disposal erases request, reply and retained receipt copied words");
            rejects(fixture, [&] {
                return fixture.dispatch.dispose_client(Phase::inactive, 0, fixture.clients[0], true).has_value();
            });
            rejects(fixture, [&] {
                return fixture.dispatch.rebind_client(Phase::inactive, 0, fixture.clients[0]);
            });
            fixture.rebirth(0);
            // The returned receipt owns a copy; fresh admission cannot rewrite it.
            fixture.submit(0, Request{3, 4});
            fixture.select(0);
            fixture.reply(0, 7);
            fixture.finish();
            fixture.consume(0, Outcome::replied, 7);
            disposition(result,
                        expected_state,
                        state == State::idle ? std::nullopt : result.transaction(),
                        expected_outcome,
                        expected_outcome == Outcome::replied ? reply_word : 0);
        }
    }
    Fixture recycled;
    recycled.submit(0);
    recycled.select(0);
    recycled.reply(0);
    recycled.finish();
    recycled.consume(0);
    check(recycled.dispatch.recycle(Phase::inactive, 0), "recycle consumed result");
    check(!contains_word(recycled.dispatch, reply_word), "recycle scrubs retained completion receipt");
    disposition(dispose(recycled, 0), State::idle, std::nullopt);
    Fixture revoked;
    revoked.submit(0);
    revoked.select(0);
    revoked.reply(0);
    revoked.finish();
    revoked.consume(0);
    check(revoked.dispatch.revoke(Phase::inactive) && !contains_word(revoked.dispatch, reply_word),
          "full revoke scrubs completion receipt");
}

auto identity_quiescence_and_replay() -> void {
    Fixture fixture;
    fixture.submit(0);
    fixture.submit(1, Request{9, 11});
    for (const auto phase : {Phase::request, Phase::service, Phase::completion}) {
        rejects(fixture, [&] {
            return fixture.dispatch.dispose_client(phase, 0, fixture.clients[0], true).has_value();
        });
        rejects(fixture, [&] {
            return fixture.dispatch.rebind_client(phase, 0, fixture.clients[0]);
        });
    }
    for (const auto client : {std::size_t{2}, std::size_t{maximum}})
        rejects(fixture, [&] {
            return fixture.dispatch.dispose_client(Phase::inactive, client, fixture.clients[0], true).has_value();
        });
    for (const auto actor : {DomainHandle{}, fixture.clients[1], fixture.service, fixture.outsider})
        rejects(fixture, [&] {
            return fixture.dispatch.dispose_client(Phase::inactive, 0, actor, true).has_value();
        });
    rejects(fixture, [&] {
        return fixture.dispatch.dispose_client(Phase::inactive, 0, fixture.clients[0], false).has_value();
    });
    for (const auto actor : {fixture.clients[0], fixture.clients[1], fixture.service}) {
        check(fixture.domains.activate(actor), "activate actual actor");
        rejects(fixture, [&] {
            return fixture.dispatch.dispose_client(Phase::inactive, 0, fixture.clients[0], true).has_value();
        });
        check(fixture.domains.deactivate(actor), "restore inactive registry");
    }
    const auto old_owner = fixture.clients[0];
    const auto old_client = fixture.client_caps[0], old_service = fixture.service_caps[0];
    const auto old_transaction = fixture.transactions[0];
    disposition(dispose(fixture, 0), State::pending, old_transaction);
    for (const auto actor : {DomainHandle{}, old_owner, fixture.clients[1], fixture.service, fixture.outsider})
        rejects(fixture, [&] {
            return fixture.dispatch.rebind_client(Phase::inactive, 0, actor);
        });
    check(fixture.domains.destroy(old_owner), "retire exact owner after disposal");
    fixture.clients[0] = *fixture.domains.create();
    for (const auto client : {std::size_t{2}, std::size_t{maximum}})
        rejects(fixture, [&] {
            return fixture.dispatch.rebind_client(Phase::inactive, client, fixture.clients[0]);
        });
    for (const auto actor : {DomainHandle{}, fixture.clients[1], fixture.service, fixture.outsider})
        rejects(fixture, [&] {
            return fixture.dispatch.rebind_client(Phase::inactive, 0, actor);
        });
    for (const auto phase : {Phase::request, Phase::service, Phase::completion})
        rejects(fixture, [&] {
            return fixture.dispatch.rebind_client(phase, 0, fixture.clients[0]);
        });
    rejects(fixture, [&] {
        return fixture.dispatch.dispose_client(Phase::inactive, 0, old_owner, true).has_value();
    });
    rejects(fixture, [&] {
        return fixture.dispatch.rebind_client(Phase::inactive, 0, old_owner);
    });
    for (const auto actor : {fixture.clients[0], fixture.clients[1], fixture.service}) {
        check(fixture.domains.activate(actor), "activate before rebind");
        rejects(fixture, [&] {
            return fixture.dispatch.rebind_client(Phase::inactive, 0, fixture.clients[0]);
        });
        check(fixture.domains.deactivate(actor), "restore rebind root");
    }
    const PeerSnapshot peer{fixture, 1};
    check(fixture.dispatch.rebind_client(Phase::inactive, 0, fixture.clients[0]), "new live incarnation admission");
    fixture.refresh(0);
    check(peer.unchanged(fixture), "rebind preserves peer bytes and scheduling identity");
    check(fixture.client_caps[0].generation() > old_client.generation(),
          "fresh globally increasing endpoint generation");
    rejects(fixture, [&] {
        return fixture.dispatch.submit(old_owner, Phase::request, fixture.client_caps[0], Request{1, 1}).has_value();
    });
    rejects(fixture, [&] {
        return fixture.dispatch.submit(fixture.clients[0], Phase::request, old_client, Request{1, 1}).has_value();
    });
    fixture.submit(0, Request{40, 2});
    check(fixture.transactions[0] > old_transaction, "new globally increasing transaction");
    fixture.select(0);
    rejects(fixture, [&] {
        return fixture.dispatch.reply(fixture.service, Phase::service, old_service, fixture.transactions[0], 999);
    });
    rejects(fixture, [&] {
        return fixture.dispatch.reply(fixture.service, Phase::service, fixture.service_caps[0], old_transaction, 999);
    });
    fixture.reply(0, 42);
    rejects(fixture, [&] {
        return fixture.dispatch.dispose_client(Phase::inactive, 0, fixture.clients[0], true).has_value();
    });
    fixture.finish();
    disposition(dispose(fixture, 0), State::replied, fixture.transactions[0], Outcome::replied, 42);
    const auto work = fixture.select(1);
    check(work.request().first() == 9 && work.request().second() == 11,
          "peer pending payload survives disposal and rebind byte-exactly");
    fixture.reply(1, 20);
    fixture.finish();
    fixture.consume(1, Outcome::replied, 20);
    check(fixture.dispatch.revoke(Phase::inactive), "full revoke handles already disposed mailbox");

    Fixture stale;
    stale.submit(0);
    const auto dead = stale.clients[0];
    check(stale.domains.destroy(dead), "simulate incorrectly retired orphan");
    const auto replacement = *stale.domains.create();
    rejects(stale, [&] {
        return stale.dispatch.dispose_client(Phase::inactive, 0, dead, true).has_value();
    });
    rejects(stale, [&] {
        return stale.dispatch.dispose_client(Phase::inactive, 0, replacement, true).has_value();
    });
    rejects(stale, [&] {
        return stale.dispatch.rebind_client(Phase::inactive, 0, replacement);
    });
    Fixture dead_service;
    check(dead_service.domains.destroy(dead_service.service), "retire service before invalid client disposal");
    rejects(dead_service, [&] {
        return dead_service.dispatch.dispose_client(Phase::inactive, 0, dead_service.clients[0], true).has_value();
    });
    Fixture changed_service;
    disposition(dispose(changed_service, 0), State::idle, std::nullopt);
    check(changed_service.domains.destroy(changed_service.clients[0]), "retire before changed-service rebind");
    changed_service.clients[0] = *changed_service.domains.create();
    check(changed_service.domains.destroy(changed_service.service), "retire original service binding");
    const auto new_service = *changed_service.domains.create();
    check(changed_service.domains.ready(new_service), "new service incarnation ready");
    rejects(changed_service, [&] {
        return changed_service.dispatch.rebind_client(Phase::inactive, 0, changed_service.clients[0]);
    });
    Fixture unbound;
    check(unbound.dispatch.revoke(Phase::inactive), "unbound policy setup");
    rejects(unbound, [&] {
        return unbound.dispatch.dispose_client(Phase::inactive, 0, unbound.clients[0], true).has_value();
    });
    rejects(unbound, [&] {
        return unbound.dispatch.rebind_client(Phase::inactive, 0, unbound.clients[0]);
    });
}

auto peer_terminal_and_selected() -> void {
    for (const auto peer_state :
         {State::idle, State::pending, State::delivered, State::replied, State::cancelled, State::consumed}) {
        Fixture fixture;
        if (peer_state != State::idle)
            fixture.submit(1, Request{request_first, request_second});
        if (peer_state == State::delivered || peer_state == State::replied || peer_state == State::consumed)
            fixture.select(1);
        if (peer_state == State::replied || peer_state == State::consumed) {
            fixture.reply(1);
            fixture.finish();
        }
        if (peer_state == State::cancelled)
            check(fixture.dispatch.cancel_pending(Phase::inactive) == 1, "peer cancelled setup");
        if (peer_state == State::consumed)
            fixture.consume(1);
        fixture.submit(0, Request{3, 7});
        const PeerSnapshot peer{fixture, 1};
        disposition(dispose(fixture, 0), State::pending, fixture.transactions[0]);
        fixture.rebirth(0);
        check(peer.unchanged(fixture), "each peer lifecycle survives offender retirement and rebind");
        if (peer_state == State::pending) {
            const auto work = fixture.select(1);
            check(work.request().first() == request_first && work.request().second() == request_second,
                  "pending peer copied words preserved");
        }
        if (peer_state == State::pending || peer_state == State::delivered) {
            fixture.reply(1);
            fixture.finish();
        }
        if (peer_state != State::idle && peer_state != State::consumed)
            fixture.consume(1,
                            peer_state == State::cancelled ? Outcome::cancelled : Outcome::replied,
                            peer_state == State::cancelled ? 0 : reply_word);
        if (peer_state != State::idle) {
            const auto result = dispose(fixture, 1);
            disposition(result,
                        State::consumed,
                        fixture.transactions[1],
                        peer_state == State::cancelled ? Outcome::cancelled : Outcome::replied,
                        peer_state == State::cancelled ? 0 : reply_word);
        }
    }
}

// Independent transition model: authority lifetime, request lifecycle and receipt
// outcome are separate state. It never calls a policy method to predict success.
class Model final {
public:
    enum class Stage {
        empty,
        waiting,
        working,
        success,
        failure,
        read
    };
    std::array<Stage, 2> slots{Stage::empty, Stage::empty};
    std::array<bool, 2> attached{true, true}, live{true, true}, replied{};
    std::array<std::uint64_t, 2> requests{}, answers{};
    std::optional<std::size_t> running{};
    std::size_t turn{};
    auto candidate() const -> std::optional<std::size_t> {
        if (running)
            return std::nullopt;
        for (std::size_t offset = 0; offset < 2; ++offset) {
            const auto client = (turn + offset) % 2;
            if (attached[client] && live[client] && slots[client] == Stage::waiting)
                return client;
        }
        return std::nullopt;
    }
    auto step(unsigned action, std::uint64_t serial) -> bool {
        if (action < 2) {
            if (!attached[action] || !live[action] || slots[action] != Stage::empty)
                return false;
            slots[action] = Stage::waiting;
            requests[action] = serial;
            return true;
        }
        if (action == 2) {
            const auto choice = candidate();
            if (!choice)
                return false;
            running = *choice;
            slots[*choice] = Stage::working;
            turn = (*choice + 1) % 2;
            return true;
        }
        if (action == 3) {
            if (!running || slots[*running] != Stage::working)
                return false;
            slots[*running] = Stage::success;
            answers[*running] = serial;
            replied[*running] = true;
            return true;
        }
        if (action == 4) {
            if (!running || (slots[*running] != Stage::success && slots[*running] != Stage::failure))
                return false;
            running.reset();
            return true;
        }
        if (action == 5) {
            bool result = false;
            for (std::size_t client = 0; client < 2; ++client) {
                if (slots[client] == Stage::waiting || slots[client] == Stage::working) {
                    slots[client] = Stage::failure;
                    answers[client] = 0;
                    replied[client] = false;
                    result = true;
                }
            }
            return result;
        }
        const auto client = (action - 6) % 2;
        if (action < 8) {
            if (!attached[client] || !live[client] || running == client ||
                (slots[client] != Stage::success && slots[client] != Stage::failure))
                return false;
            slots[client] = Stage::read;
            return true;
        }
        if (action < 10) {
            if (slots[client] != Stage::read || running == client)
                return false;
            slots[client] = Stage::empty;
            requests[client] = answers[client] = 0;
            replied[client] = false;
            return true;
        }
        if (action < 12) {
            if (!attached[client] || !live[client] || running == client)
                return false;
            attached[client] = false;
            slots[client] = Stage::empty;
            requests[client] = answers[client] = 0;
            replied[client] = false;
            return true;
        }
        if (action < 14) {
            if (attached[client] || !live[client])
                return false;
            live[client] = false;
            return true;
        }
        if (attached[client] || live[client])
            return false;
        live[client] = attached[client] = true;
        return true;
    }
};
auto compare(const Fixture &fixture, const Model &model) -> void {
    const std::array states{
        State::idle, State::pending, State::delivered, State::replied, State::cancelled, State::consumed};
    std::size_t queued = 0, occupied = 0;
    bool scrubbed = true, consumed = true;
    for (std::size_t client = 0; client < 2; ++client) {
        const auto stage = model.slots[client];
        const bool outstanding = stage != Model::Stage::empty && stage != Model::Stage::read;
        check(fixture.dispatch.state(client) == states[static_cast<unsigned>(stage)],
              "model independent lifecycle state");
        check(fixture.dispatch.transaction(client).has_value() == outstanding, "model transaction lifetime");
        if (outstanding)
            check(fixture.dispatch.transaction(client) == fixture.transactions[client], "model transaction identity");
        check(fixture.dispatch.endpoint(client, fixture.clients[client]).has_value() ==
                  (model.attached[client] && model.live[client]),
              "model client grant lifetime");
        check(fixture.dispatch.endpoint(client, fixture.service).has_value() == model.attached[client],
              "model per-slot service grant lifetime");
        if (stage == Model::Stage::waiting)
            ++queued;
        if (outstanding)
            ++occupied;
        if (stage == Model::Stage::waiting || stage == Model::Stage::success)
            scrubbed = false;
        if (stage != Model::Stage::read)
            consumed = false;
    }
    check(fixture.dispatch.bound() && fixture.dispatch.selected() == model.running &&
              fixture.dispatch.next_client() == model.turn,
          "model stable service binding, selection and round-robin cursor");
    check(fixture.dispatch.queued() == queued && fixture.dispatch.occupied() == occupied &&
              fixture.dispatch.scrubbed() == scrubbed && fixture.dispatch.all_consumed() == consumed,
          "model queue and mailbox scrub accounting");
}
auto model_step(Fixture &fixture, Model &model, unsigned action, std::uint64_t serial) -> void {
    const auto prior = model;
    const auto before = bytes(fixture.dispatch);
    const bool expected = model.step(action, serial);
    bool actual = false;
    if (action < 2) {
        const auto result = fixture.dispatch.submit(
            fixture.clients[action], Phase::request, fixture.client_caps[action], Request{serial, serial + 17});
        actual = result.has_value();
        if (result)
            fixture.transactions[action] = *result;
    } else if (action == 2) {
        const auto work = fixture.dispatch.select(Phase::inactive);
        actual = work.has_value();
        if (work)
            check(prior.candidate() == work->client() && work->request().first() == prior.requests[work->client()] &&
                      work->request().second() == prior.requests[work->client()] + 17,
                  "model byte-exact peer request and fair delivery");
    } else if (action == 3) {
        const auto client = prior.running.value_or(0);
        actual = fixture.dispatch.reply(
            fixture.service, Phase::service, fixture.service_caps[client], fixture.transactions[client], serial);
    } else if (action == 4) {
        actual = fixture.dispatch.finish_selected(Phase::inactive, true);
    } else if (action == 5) {
        std::size_t expected_count = 0;
        for (const auto stage : prior.slots)
            if (stage == Model::Stage::waiting || stage == Model::Stage::working)
                ++expected_count;
        const auto count = fixture.dispatch.cancel_pending(Phase::inactive);
        check(count == expected_count, "model cancellation preserves terminal outcomes");
        actual = count != 0;
    } else {
        const auto client = (action - 6) % 2;
        if (action < 8) {
            const auto result = fixture.dispatch.consume(
                fixture.clients[client], Phase::completion, fixture.client_caps[client], fixture.transactions[client]);
            actual = result.has_value();
            if (result)
                check(result->outcome() == (prior.replied[client] ? Outcome::replied : Outcome::cancelled) &&
                          result->value() == prior.answers[client],
                      "model original completion outcome and bytes");
        } else if (action < 10)
            actual = fixture.dispatch.recycle(Phase::inactive, client);
        else if (action < 12) {
            const PeerSnapshot peer{fixture, 1 - client};
            const auto result = fixture.dispatch.dispose_client(Phase::inactive, client, fixture.clients[client], true);
            actual = result.has_value();
            if (result) {
                const std::array states{
                    State::idle, State::pending, State::delivered, State::replied, State::cancelled, State::consumed};
                disposition(*result,
                            states[static_cast<unsigned>(prior.slots[client])],
                            prior.slots[client] == Model::Stage::empty ? std::nullopt
                                                                       : std::optional{fixture.transactions[client]},
                            prior.replied[client] ? Outcome::replied : Outcome::cancelled,
                            prior.answers[client]);
                check(peer.unchanged(fixture), "model disposal leaves all peer authority and cursor unchanged");
            }
        } else if (action < 14) {
            // The adapter retires registry authority only after policy disposal.
            actual = !prior.attached[client] && fixture.domains.destroy(fixture.clients[client]);
        } else {
            const PeerSnapshot peer{fixture, 1 - client};
            if (!prior.attached[client] && !prior.live[client])
                fixture.clients[client] = *fixture.domains.create();
            actual = fixture.dispatch.rebind_client(Phase::inactive, client, fixture.clients[client]);
            if (actual) {
                fixture.refresh(client);
                check(peer.unchanged(fixture), "model rebind leaves peer authority and cursor unchanged");
            }
        }
    }
    check(actual == expected, "operation matches independent lifecycle/authority model");
    if (!actual)
        check(bytes(fixture.dispatch) == before, "model refusal preserves every policy byte");
    compare(fixture, model);
}
auto sequences() -> std::uint64_t {
    constexpr std::uint64_t total = 16 * 16 * 16 * 16;
    for (std::uint64_t sequence = 0; sequence < total; ++sequence) {
        Fixture fixture;
        Model model;
        auto remaining = sequence;
        for (std::uint64_t step = 1; step <= 4; ++step) {
            model_step(fixture, model, static_cast<unsigned>(remaining % 16), step);
            remaining /= 16;
        }
    }
    std::uint64_t random = 0x7e39c4a187205db6ULL;
    for (unsigned sequence = 0; sequence < 4096; ++sequence) {
        Fixture fixture;
        Model model;
        for (std::uint64_t step = 1; step <= 128; ++step) {
            random ^= random << 13;
            random ^= random >> 7;
            random ^= random << 17;
            model_step(fixture, model, static_cast<unsigned>(random % 16), step);
        }
    }
    return total;
}

auto generation_exhaustion_and_reconstruction() -> void {
    DomainRegistry registry;
    const std::array clients{*registry.create(), *registry.create()};
    const auto service = *registry.create();
    Mailbox baseline{registry};
    check(baseline.bind(clients[0], service), "global generation baseline");
    const auto epoch = baseline.endpoint(clients[0])->generation();
    Fixture limited{epoch + 3}; // Two endpoint generations and one peer transaction.
    limited.submit(1, Request{40, 2});
    const PeerSnapshot peer{limited, 1};
    disposition(dispose(limited, 0), State::idle, std::nullopt);
    check(limited.domains.destroy(limited.clients[0]), "exhausted old owner retirement");
    limited.clients[0] = *limited.domains.create();
    for (unsigned attempt = 0; attempt < 8; ++attempt)
        rejects(limited, [&] {
            return limited.dispatch.rebind_client(Phase::inactive, 0, limited.clients[0]);
        });
    check(peer.unchanged(limited), "generation exhaustion preserves exact peer binding and pending request");
    const auto work = limited.select(1);
    check(work.request().first() == 40 && work.request().second() == 2, "exhaustion peer bytes intact");
    limited.reply(1, 42);
    limited.finish();
    limited.consume(1, Outcome::replied, 42);
    disposition(dispose(limited, 1), State::consumed, limited.transactions[1], Outcome::replied, 42);
    check(limited.dispatch.revoke(Phase::inactive) && limited.dispatch.scrubbed(),
          "exhaustion permits both disposed slots to revoke");

    std::optional<Dispatcher> dispatch;
    dispatch.emplace(registry);
    check(dispatch->bind(clients, service), "first dispatcher incarnation");
    const auto old_client = *dispatch->endpoint(0, clients[0]), old_service = *dispatch->endpoint(0, service);
    const auto old_transaction = *dispatch->submit(clients[0], Phase::request, old_client, Request{3, 4});
    check(dispatch->dispose_client(Phase::inactive, 0, clients[0], true).has_value(),
          "dispose before object reconstruction");
    dispatch.reset();
    dispatch.emplace(registry);
    check(dispatch->bind(clients, service), "same-address dispatcher reconstruction");
    const auto client = *dispatch->endpoint(0, clients[0]);
    check(client.generation() > old_client.generation(), "reconstruction cannot reset global endpoint sequence");
    check(!dispatch->submit(clients[0], Phase::request, old_client, Request{99, 99}),
          "reconstructed stale endpoint denied");
    const auto transaction = *dispatch->submit(clients[0], Phase::request, client, Request{40, 2});
    check(transaction > old_transaction, "reconstruction cannot reset transaction sequence");
    const auto selected = *dispatch->select(Phase::inactive);
    check(!dispatch->reply(service, Phase::service, old_service, transaction, 999) &&
              !dispatch->reply(service, Phase::service, selected.service_endpoint(), old_transaction, 999),
          "reconstructed stale reply denied");
    check(dispatch->reply(service, Phase::service, selected.service_endpoint(), transaction, 42) &&
              dispatch->finish_selected(Phase::inactive, true),
          "reconstructed work survives stale claims");
    const auto result = dispatch->dispose_client(Phase::inactive, 0, clients[0], true);
    check(result.has_value(), "reconstructed exact-owner disposal");
    disposition(*result, State::replied, transaction, Outcome::replied, 42);
}

auto main() -> int {
    all_dispositions_and_scrub();
    identity_quiescence_and_replay();
    peer_terminal_and_selected();
    generation_exhaustion_and_reconstruction();
    const auto total = sequences();
    std::cout << "PASS: client disposal " << total
              << " exhaustive four-operation sequences, 4096 128-operation model traces, "
                 "exact live identity and quiescence, first-terminal and consumed receipts, peer preservation, "
                 "copied-word scrub, "
                 "per-client retirement/rebind, replay and generation exhaustion\n";
    return 0;
}
} // namespace kernel_client_disposal
