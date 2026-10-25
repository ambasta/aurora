#include "../kernel/dispatch-policy.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <optional>
#include <string_view>
#include <type_traits>

namespace kernel_dispatch {
using namespace aurora::ipc;
using aurora::user::DomainHandle;
using aurora::user::DomainRegistry;
constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
static_assert(Dispatcher::capacity == 2);
static_assert(!std::is_copy_constructible_v<Dispatcher> && !std::is_move_constructible_v<Dispatcher>);
static_assert(!std::is_copy_assignable_v<Dispatcher> && !std::is_move_assignable_v<Dispatcher>);
static_assert(std::is_trivially_copyable_v<Work>);
static_assert(std::is_trivially_copyable_v<Request> && sizeof(Request) == 2 * sizeof(std::uint64_t));

auto check(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
auto same(Endpoint first, Endpoint second) -> bool {
    return first.slot() == second.slot() && first.generation() == second.generation();
}
class Fixture final {
public:
    DomainRegistry domains{}, foreign{};
    std::array<DomainHandle, 2> clients{};
    DomainHandle service{}, outsider{};
    Dispatcher dispatch{domains};
    std::array<Endpoint, 2> client_caps{}, service_caps{};
    std::array<std::uint64_t, 2> transactions{};
    Fixture() {
        clients[0] = *domains.create();
        service = *domains.create();
        clients[1] = *domains.create();
        outsider = *foreign.create();
        check(dispatch.bind(clients, service), "fixture bind");
        refresh();
    }
    auto refresh() -> void {
        for (std::size_t index = 0; index < 2; ++index) {
            client_caps[index] = *dispatch.endpoint(index, clients[index]);
            service_caps[index] = *dispatch.endpoint(index, service);
        }
    }
    auto submit(std::size_t index, Request request = Request{40, 2}) -> std::uint64_t {
        const auto transaction = dispatch.submit(clients[index], Phase::request, client_caps[index], request);
        check(transaction.has_value(), "valid submit");
        transactions[index] = *transaction;
        return *transaction;
    }
    auto select(std::size_t expected) -> Work {
        const auto work = dispatch.select(Phase::inactive);
        check(work && work->client() == expected && work->transaction() == transactions[expected],
              "expected round-robin work");
        check(same(work->service_endpoint(), service_caps[expected]), "work carries selected service grant");
        return *work;
    }
    auto reply(std::size_t index, std::uint64_t value = 42) -> void {
        check(dispatch.reply(service, Phase::service, service_caps[index], transactions[index], value), "valid reply");
    }
    auto finish() -> void {
        check(dispatch.finish_selected(Phase::inactive, true), "finish quiescent terminal work");
    }
    auto consume(std::size_t index, Outcome outcome = Outcome::replied, std::uint64_t value = 42) -> Completion {
        const auto completion =
            dispatch.consume(clients[index], Phase::completion, client_caps[index], transactions[index]);
        check(completion && completion->outcome() == outcome && completion->value() == value,
              "exact client completion");
        return *completion;
    }
};
class Snapshot final {
    std::array<std::optional<State>, 2> states_{};
    std::array<std::optional<std::uint64_t>, 2> transactions_{};
    std::array<std::optional<Endpoint>, 4> endpoints_{};
    std::optional<std::size_t> selected_{};
    std::size_t queued_{}, occupied_{}, next_{};
    bool bound_{}, scrubbed_{}, consumed_{};

public:
    explicit Snapshot(const Fixture &fixture)
        : selected_(fixture.dispatch.selected()), queued_(fixture.dispatch.queued()),
          occupied_(fixture.dispatch.occupied()), next_(fixture.dispatch.next_client()),
          bound_(fixture.dispatch.bound()), scrubbed_(fixture.dispatch.scrubbed()),
          consumed_(fixture.dispatch.all_consumed()) {
        for (std::size_t index = 0; index < 2; ++index) {
            states_[index] = fixture.dispatch.state(index);
            transactions_[index] = fixture.dispatch.transaction(index);
            endpoints_[index * 2] = fixture.dispatch.endpoint(index, fixture.clients[index]);
            endpoints_[index * 2 + 1] = fixture.dispatch.endpoint(index, fixture.service);
        }
    }
    auto unchanged(const Fixture &fixture) const -> bool {
        const Snapshot now{fixture};
        if (states_ != now.states_ || transactions_ != now.transactions_ || selected_ != now.selected_ ||
            queued_ != now.queued_ || occupied_ != now.occupied_ || next_ != now.next_ || bound_ != now.bound_ ||
            scrubbed_ != now.scrubbed_ || consumed_ != now.consumed_)
            return false;
        for (std::size_t index = 0; index < endpoints_.size(); ++index) {
            if (endpoints_[index].has_value() != now.endpoints_[index].has_value())
                return false;
            if (endpoints_[index] && !same(*endpoints_[index], *now.endpoints_[index]))
                return false;
        }
        return true;
    }
};
template <class Operation> auto rejects(Fixture &fixture, Operation operation) -> void {
    const Snapshot before{fixture};
    check(!operation(), "untrusted operation denied");
    check(before.unchanged(fixture),
          "rejection preserves queues, selection, grants, transactions and payload occupancy");
}

auto admission_and_fairness() -> void {
    Fixture fixture;
    check(!fixture.dispatch.state(2) && !fixture.dispatch.state(maximum), "state bounds");
    check(!fixture.dispatch.transaction(2) && !fixture.dispatch.transaction(maximum), "transaction bounds");
    check(!fixture.dispatch.endpoint(2, fixture.service) && !fixture.dispatch.endpoint(maximum, fixture.service),
          "endpoint bounds");
    check(!fixture.dispatch.endpoint(0, fixture.clients[1]) && !fixture.dispatch.endpoint(1, fixture.clients[0]),
          "client grants not interchangeable");
    check(!fixture.dispatch.endpoint(0, fixture.outsider) && !fixture.dispatch.endpoint(1, DomainHandle{}),
          "foreign and absent grants");
    rejects(fixture, [&] {
        return fixture.dispatch.bind(fixture.clients, fixture.service);
    });
    rejects(fixture, [&] {
        return fixture.dispatch.recycle(Phase::inactive, maximum);
    });
    rejects(fixture, [&] {
        return fixture.dispatch.select(Phase::inactive).has_value();
    });
    fixture.submit(1, Request{21, 22});
    fixture.submit(0, Request{11, 12});
    check(fixture.dispatch.queued() == 2 && fixture.dispatch.occupied() == 2, "capacity-two admission");
    for (unsigned repetition = 0; repetition < 4; ++repetition) {
        for (std::size_t client = 0; client < 2; ++client) {
            rejects(fixture, [&] {
                return fixture.dispatch
                    .submit(fixture.clients[client], Phase::request, fixture.client_caps[client], Request{99, 99})
                    .has_value();
            });
        }
        rejects(fixture, [&] {
            return fixture.dispatch.submit(fixture.service, Phase::request, fixture.service_caps[0], Request{99, 99})
                .has_value();
        });
        rejects(fixture, [&] {
            return fixture.dispatch.submit(fixture.outsider, Phase::request, fixture.client_caps[0], Request{99, 99})
                .has_value();
        });
    }
    const auto first = fixture.select(0);
    check(first.request().first() == 11 && first.request().second() == 12, "duplicates preserve first payload");
    check(fixture.dispatch.queued() == 1 && fixture.dispatch.occupied() == 2, "selection retains occupied slot");
    rejects(fixture, [&] {
        return fixture.dispatch.select(Phase::inactive).has_value();
    });
    rejects(fixture, [&] {
        return fixture.dispatch.finish_selected(Phase::inactive, true);
    });
    fixture.reply(0);
    fixture.finish();
    fixture.consume(0);
    check(fixture.dispatch.recycle(Phase::inactive, 0), "client slot recycle");
    fixture.submit(0, Request{31, 32});
    const auto second = fixture.select(1);
    check(second.request().first() == 21 && second.request().second() == 22, "waiting peer survives refilling client");
    fixture.reply(1);
    fixture.finish();
    fixture.consume(1);
    check(fixture.dispatch.recycle(Phase::inactive, 1), "second client recycle");
    // Both clients are always pending before each selection. A fresh submit by
    // the last serviced client cannot jump ahead of the waiting peer.
    fixture.submit(1);
    for (std::size_t round = 0; round < 128; ++round) {
        const auto expected = round % 2;
        fixture.select(expected);
        fixture.reply(expected);
        fixture.finish();
        fixture.consume(expected);
        check(fixture.dispatch.recycle(Phase::inactive, expected), "repeated independent recycle");
        fixture.submit(expected);
    }
    check(fixture.dispatch.cancel_pending(Phase::inactive) == 2, "cleanup both queued requests");
    fixture.consume(0, Outcome::cancelled, 0);
    fixture.consume(1, Outcome::cancelled, 0);
    check(fixture.dispatch.all_consumed() && fixture.dispatch.revoke(Phase::inactive), "all-consumed revoke");
    check(fixture.dispatch.scrubbed() && !fixture.dispatch.bound() && !fixture.dispatch.selected(),
          "revoke clears policy state");
}

auto terminal_orders_and_copies() -> void {
    Fixture fixture;
    Request source{maximum, std::uint64_t{1} << 63};
    fixture.submit(0, source);
    fixture.submit(1, Request{3, 4});
    source = Request{};
    const auto work = fixture.select(0);
    check(work.request().first() == maximum && work.request().second() == (std::uint64_t{1} << 63),
          "request copied at admission");
    fixture.reply(0, maximum);
    rejects(fixture, [&] {
        return fixture.dispatch
            .consume(fixture.clients[0], Phase::completion, fixture.client_caps[0], fixture.transactions[0])
            .has_value();
    });
    rejects(fixture, [&] {
        return fixture.dispatch.finish_selected(Phase::inactive, false);
    });
    rejects(fixture, [&] {
        return fixture.dispatch.finish_selected(Phase::service, true);
    });
    fixture.finish();
    fixture.select(1);
    check(fixture.dispatch.cancel_pending(Phase::inactive) == 1,
          "cancel selected request preserves other unconsumed reply");
    check(fixture.dispatch.state(0) == State::replied && fixture.dispatch.state(1) == State::cancelled,
          "first terminal state wins independently");
    check(fixture.dispatch.selected() == 1 && fixture.dispatch.queued() == 0, "cancellation retains selected ticket");
    rejects(fixture, [&] {
        return fixture.dispatch.reply(
            fixture.service, Phase::service, fixture.service_caps[1], fixture.transactions[1], 999);
    });
    rejects(fixture, [&] {
        return fixture.dispatch.finish_selected(Phase::inactive, false);
    });
    rejects(fixture, [&] {
        return fixture.dispatch.select(Phase::inactive).has_value();
    });
    const auto completed = fixture.consume(0, Outcome::replied, maximum);
    check(fixture.dispatch.scrubbed(), "completion and cancellation scrub storage");
    fixture.finish();
    fixture.consume(1, Outcome::cancelled, 0);
    check(fixture.dispatch.cancel_pending(Phase::inactive) == 0, "repeat cancellation changes no terminal outcome");
    check(fixture.dispatch.revoke(Phase::inactive), "terminal revoke");
    check(work.request().first() == maximum && completed.value() == maximum, "returned copies survive revoke");
    check(fixture.dispatch.bind(fixture.clients, fixture.service), "fresh binding after terminal revoke");
    fixture.refresh();
    fixture.submit(0, Request{});
    fixture.submit(1, Request{});
    check(fixture.dispatch.scrubbed() && fixture.dispatch.queued() == 2, "zero words still occupy queue");
    fixture.select(0);
    fixture.reply(0, 0);
    check(fixture.dispatch.cancel_pending(Phase::inactive) == 1, "reply-before-cancel retains selected reply");
    check(fixture.dispatch.selected() == 0, "reply-before-cancel still requires finish");
    fixture.finish();
    fixture.consume(0, Outcome::replied, 0);
    fixture.consume(1, Outcome::cancelled, 0);
    check(fixture.dispatch.recycle(Phase::inactive, 0) && fixture.dispatch.recycle(Phase::inactive, 1),
          "both consumed slots recycle");
    check(fixture.dispatch.revoke(Phase::inactive), "both idle revoke");
    check(fixture.dispatch.bind(fixture.clients, fixture.service) && fixture.dispatch.revoke(Phase::inactive),
          "never-submitted bind/revoke lifecycle");
}

auto adversarial_envelopes() -> std::uint64_t {
    std::uint64_t rejected = 0;
    const std::array phases{Phase::inactive, Phase::request, Phase::service, Phase::completion, static_cast<Phase>(99)};
    for (const auto target :
         {State::idle, State::pending, State::delivered, State::replied, State::cancelled, State::consumed}) {
        Fixture fixture;
        if (target != State::idle) {
            fixture.submit(0);
            fixture.submit(1);
            if (target != State::pending)
                fixture.select(0);
            if (target == State::replied || target == State::consumed)
                fixture.reply(0);
            if (target == State::cancelled)
                check(fixture.dispatch.cancel_pending(Phase::inactive) == 2, "adversarial cancelled setup");
            if (target == State::replied || target == State::cancelled || target == State::consumed)
                fixture.finish();
            if (target == State::consumed)
                fixture.consume(0);
        }
        const std::array callers{
            fixture.clients[0], fixture.clients[1], fixture.service, fixture.outsider, DomainHandle{}};
        const std::array endpoints{fixture.client_caps[0],
                                   fixture.client_caps[1],
                                   fixture.service_caps[0],
                                   fixture.service_caps[1],
                                   Endpoint{},
                                   Endpoint{maximum, fixture.client_caps[0].generation()},
                                   Endpoint{fixture.client_caps[0].slot(), maximum}};
        const std::array transactions{std::uint64_t{0}, fixture.transactions[0], fixture.transactions[1], maximum};
        for (std::size_t caller = 0; caller < callers.size(); ++caller) {
            for (const auto phase : phases) {
                for (std::size_t endpoint = 0; endpoint < endpoints.size(); ++endpoint) {
                    const bool accepted_submit = target == State::idle && phase == Phase::request &&
                                                 ((caller == 0 && endpoint == 0) || (caller == 1 && endpoint == 1));
                    if (!accepted_submit) {
                        rejects(fixture, [&] {
                            return fixture.dispatch.submit(callers[caller], phase, endpoints[endpoint], Request{91, 92})
                                .has_value();
                        });
                        ++rejected;
                    }
                    for (const auto transaction : transactions) {
                        const bool accepted_reply = target == State::delivered && caller == 2 &&
                                                    phase == Phase::service && endpoint == 2 &&
                                                    transaction == fixture.transactions[0];
                        if (!accepted_reply) {
                            rejects(fixture, [&] {
                                return fixture.dispatch.reply(
                                    callers[caller], phase, endpoints[endpoint], transaction, 999);
                            });
                            ++rejected;
                        }
                        const bool accepted_consume =
                            phase == Phase::completion &&
                            (((target == State::replied || target == State::cancelled) && caller == 0 &&
                              endpoint == 0 && transaction == fixture.transactions[0]) ||
                             (target == State::cancelled && caller == 1 && endpoint == 1 &&
                              transaction == fixture.transactions[1]));
                        if (!accepted_consume) {
                            rejects(fixture, [&] {
                                return fixture.dispatch
                                    .consume(callers[caller], phase, endpoints[endpoint], transaction)
                                    .has_value();
                            });
                            ++rejected;
                        }
                    }
                }
            }
        }
        for (const auto phase : phases) {
            if (phase == Phase::inactive)
                continue;
            rejects(fixture, [&] {
                return fixture.dispatch.select(phase).has_value();
            });
            rejects(fixture, [&] {
                return fixture.dispatch.cancel_pending(phase) != 0;
            });
            rejects(fixture, [&] {
                return fixture.dispatch.recycle(phase, 0);
            });
            rejects(fixture, [&] {
                return fixture.dispatch.revoke(phase);
            });
            rejected += 4;
        }
    }
    return rejected;
}

// A separate slot lifecycle model. It stores abstract ownership and expected
// payloads, not Mailboxes, Endpoint stamps, DomainHandles or policy helpers.
class Model final {
public:
    enum class Stage {
        empty,
        waiting,
        working,
        success,
        stopped,
        retired
    };
    std::array<Stage, 2> slots{Stage::empty, Stage::empty};
    std::array<std::uint64_t, 2> serials{}, answers{};
    std::optional<std::size_t> running{};
    std::size_t turn{};
    bool bound = true;
    [[nodiscard]] auto select_candidate() const -> std::optional<std::size_t> {
        if (!bound || running)
            return std::nullopt;
        if (slots[turn] == Stage::waiting)
            return turn;
        if (slots[1 - turn] == Stage::waiting)
            return 1 - turn;
        return std::nullopt;
    }
    auto step(unsigned action, std::uint64_t serial) -> bool {
        if (action <= 1) {
            if (!bound || slots[action] != Stage::empty)
                return false;
            slots[action] = Stage::waiting;
            serials[action] = serial;
            return true;
        }
        if (action == 2) {
            const auto candidate = select_candidate();
            if (!candidate)
                return false;
            running = candidate;
            slots[*candidate] = Stage::working;
            turn = 1 - *candidate;
            return true;
        }
        if (action == 3) {
            if (!running || slots[*running] != Stage::working)
                return false;
            slots[*running] = Stage::success;
            answers[*running] = serial;
            return true;
        }
        if (action == 4) {
            if (!running || (slots[*running] != Stage::success && slots[*running] != Stage::stopped))
                return false;
            running.reset();
            return true;
        }
        if (action == 5 || action == 6) {
            const auto client = action - 5;
            if (!bound || running == client || (slots[client] != Stage::success && slots[client] != Stage::stopped))
                return false;
            slots[client] = Stage::retired;
            return true;
        }
        if (action == 7) {
            bool changed = false;
            for (auto &slot : slots) {
                if (slot == Stage::waiting || slot == Stage::working) {
                    slot = Stage::stopped;
                    changed = true;
                }
            }
            return changed;
        }
        if (action == 8 || action == 9) {
            const auto client = action - 8;
            if (!bound || slots[client] != Stage::retired)
                return false;
            slots[client] = Stage::empty;
            return true;
        }
        if (action == 10) {
            if (!bound || running)
                return false;
            for (const auto slot : slots)
                if (slot != Stage::empty && slot != Stage::retired)
                    return false;
            bound = false;
            slots = {Stage::empty, Stage::empty};
            turn = 0;
            return true;
        }
        if (bound)
            return false;
        bound = true;
        turn = 0;
        return true;
    }
};
auto compare_model(const Fixture &fixture, const Model &model) -> void {
    const std::array states{
        State::idle, State::pending, State::delivered, State::replied, State::cancelled, State::consumed};
    std::size_t queued = 0, occupied = 0;
    bool scrubbed = true, all_consumed = model.bound;
    for (std::size_t client = 0; client < 2; ++client) {
        const auto slot = model.slots[client];
        check(fixture.dispatch.state(client) == states[static_cast<unsigned>(slot)], "independent model slot state");
        const bool outstanding = slot != Model::Stage::empty && slot != Model::Stage::retired;
        check(fixture.dispatch.transaction(client).has_value() == outstanding, "model transaction lifetime");
        if (outstanding)
            check(fixture.dispatch.transaction(client) == fixture.transactions[client],
                  "model immutable transaction identity");
        if (slot == Model::Stage::waiting)
            ++queued;
        if (outstanding)
            ++occupied;
        if (slot == Model::Stage::waiting || slot == Model::Stage::success)
            scrubbed = false;
        if (slot != Model::Stage::retired)
            all_consumed = false;
        check(fixture.dispatch.endpoint(client, fixture.clients[client]).has_value() == model.bound,
              "model client grant lifetime");
        check(fixture.dispatch.endpoint(client, fixture.service).has_value() == model.bound,
              "model service grant lifetime");
    }
    check(fixture.dispatch.bound() == model.bound && fixture.dispatch.selected() == model.running,
          "model binding/selected state");
    check(fixture.dispatch.queued() == queued && fixture.dispatch.occupied() == occupied, "model queue accounting");
    check(fixture.dispatch.next_client() == model.turn && fixture.dispatch.scrubbed() == scrubbed,
          "model cursor and scrub invariant");
    check(fixture.dispatch.all_consumed() == all_consumed, "model all consumed");
}
auto model_step(Fixture &fixture, Model &model, unsigned action, std::uint64_t serial) -> void {
    const Snapshot before{fixture};
    const auto prior = model;
    const bool expected = model.step(action, serial);
    bool actual = false;
    if (action <= 1) {
        const auto result = fixture.dispatch.submit(
            fixture.clients[action], Phase::request, fixture.client_caps[action], Request{serial, serial + 1});
        actual = result.has_value();
        if (actual)
            fixture.transactions[action] = *result;
    } else if (action == 2) {
        const auto work = fixture.dispatch.select(Phase::inactive);
        actual = work.has_value();
        if (work) {
            check(prior.select_candidate() == work->client(), "model round-robin selection");
            check(work->request().first() == prior.serials[work->client()] &&
                      work->request().second() == prior.serials[work->client()] + 1,
                  "model exact independent request delivery");
            check(work->transaction() == fixture.transactions[work->client()], "model exact work transaction");
        }
    } else if (action == 3) {
        const auto client = prior.running.value_or(0);
        actual = fixture.dispatch.reply(
            fixture.service, Phase::service, fixture.service_caps[client], fixture.transactions[client], serial);
    } else if (action == 4) {
        actual = fixture.dispatch.finish_selected(Phase::inactive, true);
    } else if (action == 5 || action == 6) {
        const auto client = action - 5;
        const auto result = fixture.dispatch.consume(
            fixture.clients[client], Phase::completion, fixture.client_caps[client], fixture.transactions[client]);
        actual = result.has_value();
        if (result) {
            const auto success = prior.slots[client] == Model::Stage::success;
            check(result->outcome() == (success ? Outcome::replied : Outcome::cancelled), "model terminal outcome");
            check(result->value() == (success ? prior.answers[client] : 0), "model exact completion payload");
        }
    } else if (action == 7) {
        std::size_t count = 0;
        for (const auto state : prior.slots)
            if (state == Model::Stage::waiting || state == Model::Stage::working)
                ++count;
        const auto cancelled = fixture.dispatch.cancel_pending(Phase::inactive);
        check(cancelled == count, "model cancellation cardinality");
        actual = cancelled != 0;
    } else if (action == 8 || action == 9) {
        actual = fixture.dispatch.recycle(Phase::inactive, action - 8);
    } else if (action == 10) {
        actual = fixture.dispatch.revoke(Phase::inactive);
    } else {
        actual = fixture.dispatch.bind(fixture.clients, fixture.service);
        if (actual)
            fixture.refresh();
    }
    check(actual == expected, "operation agrees with independent bounded model");
    if (!actual)
        check(before.unchanged(fixture), "model refusal is atomic");
    compare_model(fixture, model);
}
auto transition_sequences() -> std::uint64_t {
    constexpr std::uint64_t sequences = 12 * 12 * 12 * 12 * 12;
    for (std::uint64_t sequence = 0; sequence < sequences; ++sequence) {
        Fixture fixture;
        Model model;
        auto remaining = sequence;
        for (std::uint64_t step = 1; step <= 5; ++step) {
            model_step(fixture, model, static_cast<unsigned>(remaining % 12), step);
            remaining /= 12;
        }
    }
    // Longer deterministic traces add repeated retirement/rebind and consumption
    // interleavings that the exhaustive five-operation prefix cannot reach.
    std::uint64_t random = 0x9e3779b97f4a7c15ULL;
    for (unsigned sequence = 0; sequence < 4096; ++sequence) {
        Fixture fixture;
        Model model;
        for (std::uint64_t step = 1; step <= 128; ++step) {
            random ^= random << 13;
            random ^= random >> 7;
            random ^= random << 17;
            model_step(fixture, model, static_cast<unsigned>(random % 12), step);
        }
    }
    return sequences;
}

auto identity_and_rebinding() -> void {
    Fixture fixture;
    const auto old_clients = fixture.client_caps, old_services = fixture.service_caps;
    fixture.submit(0);
    fixture.submit(1);
    const auto old_transactions = fixture.transactions;
    fixture.select(0);
    fixture.reply(0);
    fixture.finish();
    fixture.consume(0);
    fixture.select(1);
    fixture.reply(1);
    fixture.finish();
    fixture.consume(1);
    check(fixture.dispatch.revoke(Phase::inactive) && fixture.dispatch.bind(fixture.clients, fixture.service),
          "rebind after both clients consume");
    fixture.refresh();
    for (std::size_t client = 0; client < 2; ++client) {
        check(!same(old_clients[client], fixture.client_caps[client]) &&
                  !same(old_services[client], fixture.service_caps[client]),
              "rebind grants fresh");
        rejects(fixture, [&] {
            return fixture.dispatch
                .submit(fixture.clients[client], Phase::request, old_clients[client], Request{91, 92})
                .has_value();
        });
        fixture.submit(client);
        check(fixture.transactions[client] != old_transactions[client], "rebind transactions fresh");
    }
    fixture.select(0);
    rejects(fixture, [&] {
        return fixture.dispatch.reply(fixture.service, Phase::service, old_services[0], fixture.transactions[0], 999);
    });
    rejects(fixture, [&] {
        return fixture.dispatch.reply(
            fixture.service, Phase::service, fixture.service_caps[0], old_transactions[0], 999);
    });
    rejects(fixture, [&] {
        return fixture.dispatch.reply(
            fixture.service, Phase::service, fixture.service_caps[1], fixture.transactions[1], 999);
    });
    fixture.reply(0);
    fixture.finish();
    fixture.consume(0);
    fixture.select(1);
    check(fixture.domains.destroy(fixture.service), "destroy selected service");
    const auto replacement = *fixture.domains.create();
    check(!fixture.dispatch.endpoint(0, replacement) && !fixture.dispatch.endpoint(1, replacement),
          "replacement cannot inherit either service grant");
    rejects(fixture, [&] {
        return fixture.dispatch.reply(
            replacement, Phase::service, fixture.service_caps[1], fixture.transactions[1], 999);
    });
    check(fixture.dispatch.cancel_pending(Phase::inactive) == 1, "cancel dead selected service");
    fixture.finish();
    fixture.consume(1, Outcome::cancelled, 0);
    check(fixture.dispatch.revoke(Phase::inactive), "retire dead service grant");
    fixture.service = replacement;
    check(fixture.dispatch.bind(fixture.clients, fixture.service), "fresh service rebind");
    fixture.refresh();
    fixture.submit(0);
    fixture.select(0);
    fixture.reply(0);
    fixture.finish();
    fixture.consume(0);

    Fixture dead_client;
    dead_client.submit(0);
    dead_client.submit(1);
    const auto stale_client = dead_client.clients[0];
    check(dead_client.domains.destroy(stale_client), "destroy queued client");
    const auto fresh_client = *dead_client.domains.create();
    rejects(dead_client, [&] {
        return dead_client.dispatch.submit(fresh_client, Phase::request, dead_client.client_caps[0], Request{9, 9})
            .has_value();
    });
    check(!dead_client.dispatch.endpoint(0, fresh_client), "new client incarnation cannot inherit grant");
    dead_client.select(1);
    dead_client.reply(1);
    dead_client.finish();
    dead_client.consume(1);
    check(dead_client.dispatch.cancel_pending(Phase::inactive) == 1, "dead queued client can be cancelled");
    check(!dead_client.dispatch.consume(
              stale_client, Phase::completion, dead_client.client_caps[0], dead_client.transactions[0]),
          "dead client cannot consume");
    check(!dead_client.dispatch.consume(
              fresh_client, Phase::completion, dead_client.client_caps[0], dead_client.transactions[0]),
          "replacement cannot consume stale result");
    check(!dead_client.dispatch.revoke(Phase::inactive), "unconsumed orphan remains fail closed");

    DomainRegistry registry;
    const std::array clients{*registry.create(), *registry.create()};
    const auto service = *registry.create();
    std::optional<Dispatcher> incarnation;
    incarnation.emplace(registry);
    check(incarnation->bind(clients, service), "first dispatcher incarnation");
    const auto old_cap = *incarnation->endpoint(0, clients[0]);
    const auto old_server = *incarnation->endpoint(0, service);
    const auto old_tx = *incarnation->submit(clients[0], Phase::request, old_cap, Request{1, 2});
    incarnation.reset();
    incarnation.emplace(registry);
    check(incarnation->bind(clients, service), "same-address dispatcher reconstruction");
    check(!incarnation->submit(clients[0], Phase::request, old_cap, Request{9, 9}),
          "reconstruction rejects old endpoint");
    const auto new_cap = *incarnation->endpoint(0, clients[0]);
    const auto new_tx = *incarnation->submit(clients[0], Phase::request, new_cap, Request{40, 2});
    check(new_tx != old_tx && !same(new_cap, old_cap), "reconstruction epochs globally unique");
    const auto work = incarnation->select(Phase::inactive);
    check(work.has_value(), "reconstruction valid selection");
    check(!incarnation->reply(service, Phase::service, old_server, new_tx, 999),
          "reconstruction rejects old service grant");
    check(!incarnation->reply(service, Phase::service, work->service_endpoint(), old_tx, 999),
          "reconstruction rejects old transaction");
    Dispatcher parallel{registry};
    check(parallel.bind(clients, service), "parallel dispatcher");
    const auto other = *parallel.endpoint(0, clients[0]);
    check(!parallel.submit(clients[0], Phase::request, new_cap, Request{9, 9}), "parallel endpoint replay denied");
    const auto other_tx = *parallel.submit(clients[0], Phase::request, other, Request{3, 4});
    check(other_tx != new_tx && !incarnation->reply(service, Phase::service, work->service_endpoint(), other_tx, 999),
          "parallel transaction replay denied");
    check(incarnation->reply(service, Phase::service, work->service_endpoint(), new_tx, 42),
          "replay attempts preserve valid work");

    Fixture active;
    check(active.domains.activate(active.clients[0]), "activate actual client");
    active.submit(0);
    rejects(active, [&] {
        return active.dispatch.select(Phase::inactive).has_value();
    });
    check(active.domains.deactivate(active.clients[0]), "restore kernel root for selection");
    active.select(0);
    check(active.domains.activate(active.service), "activate actual service");
    active.reply(0);
    check(active.domains.deactivate(active.service), "restore kernel root for completion");
    active.finish();
    active.consume(0);
}

auto generation_exhaustion() -> void {
    DomainRegistry registry, foreign;
    const std::array clients{*registry.create(), *registry.create()};
    const auto service = *registry.create(), outsider = *foreign.create();
    Mailbox baseline{registry};
    check(baseline.bind(clients[0], service), "generation baseline");
    const auto epoch = baseline.endpoint(clients[0])->generation();
    Dispatcher partial{registry, epoch + 1};
    check(!partial.bind({clients[0], clients[0]}, service) && !partial.bind({clients[0], service}, service),
          "duplicate identities rejected");
    check(!partial.bind({clients[0], outsider}, service) && !partial.bind({DomainHandle{}, clients[1]}, service),
          "invalid identities rejected");
    check(registry.activate(clients[0]), "active-root bind setup");
    check(!partial.bind(clients, service), "active-root binding denied");
    check(registry.deactivate(clients[0]), "bind return to root");
    check(!partial.bind(clients, service), "partial bind exhaustion rolls back first mailbox");
    check(!partial.bound() && partial.scrubbed() && partial.occupied() == 0 && partial.queued() == 0,
          "partial bind exposes no occupancy");
    for (std::size_t client = 0; client < 2; ++client) {
        check(!partial.endpoint(client, clients[client]) && !partial.endpoint(client, service),
              "partial bind exposes no grant");
        check(partial.state(client) == State::idle && !partial.transaction(client), "partial bind leaves idle storage");
    }
    check(!partial.bind(clients, service), "exhausted rebind fails closed");
    Dispatcher limited{registry, epoch + 4};
    check(limited.bind(clients, service), "two grants below reduced ceiling");
    const auto first = *limited.endpoint(0, clients[0]), second = *limited.endpoint(1, clients[1]);
    check(first.generation() == epoch + 2 && second.generation() == epoch + 3,
          "invalid binds do not consume generations");
    const auto final = limited.submit(clients[0], Phase::request, first, Request{maximum, 1});
    check(final && *final == epoch + 4, "final permitted transaction");
    for (unsigned attempt = 0; attempt < 8; ++attempt) {
        check(!limited.submit(clients[1], Phase::request, second, Request{9, 9}), "exhausted admission rejected");
        check(limited.queued() == 1 && limited.occupied() == 1 && limited.state(1) == State::idle &&
                  limited.transaction(0) == final && same(*limited.endpoint(1, clients[1]), second),
              "exhaustion preserves existing request and second grant");
    }
    const auto work = limited.select(Phase::inactive);
    check(work && work->request().first() == maximum, "exhaustion leaves admitted payload intact");
    check(limited.reply(service, Phase::service, work->service_endpoint(), *final, 42),
          "exhaustion permits existing reply");
    check(limited.finish_selected(Phase::inactive, true), "exhaustion permits quiescent finish");
    check(limited.consume(clients[0], Phase::completion, first, *final).has_value(),
          "exhaustion permits existing completion");
    check(limited.recycle(Phase::inactive, 0) && limited.revoke(Phase::inactive),
          "exhaustion permits scrubbed retirement");
    check(!limited.bind(clients, service) && !limited.bound() && limited.scrubbed(),
          "exhaustion cannot resurrect grants");
    Dispatcher closed{registry, 0};
    check(!closed.bind(clients, service) && closed.scrubbed(), "zero ceiling is closed");
}

auto continuous_fairness_and_idle() -> void {
    Fixture fixture;
    const Snapshot empty{fixture};
    for (unsigned repeat = 0; repeat < 8; ++repeat)
        check(!fixture.dispatch.select(Phase::inactive) && empty.unchanged(fixture),
              "idle preserves empty cursor and records");
    fixture.submit(0);
    fixture.submit(1);
    for (std::size_t step = 0; step < 128; ++step) {
        const auto chosen = step % 2;
        fixture.select(chosen);
        fixture.reply(chosen);
        fixture.finish();
        fixture.consume(chosen);
        check(fixture.dispatch.recycle(Phase::inactive, chosen), "continuous pending client recycle");
        fixture.submit(chosen);
    }
    check(fixture.dispatch.cancel_pending(Phase::inactive) == 2, "continuous trace cancellation");
    fixture.consume(0, Outcome::cancelled, 0);
    fixture.consume(1, Outcome::cancelled, 0);
    const Snapshot cursor_zero{fixture};
    check(!fixture.dispatch.select(Phase::inactive) && cursor_zero.unchanged(fixture),
          "idle preserves retained zero cursor");
    check(fixture.dispatch.recycle(Phase::inactive, 0), "isolated slot recycle");
    fixture.submit(0);
    fixture.select(0);
    fixture.reply(0);
    fixture.finish();
    fixture.consume(0);
    check(fixture.dispatch.next_client() == 1, "isolated selection advances cursor");
    const Snapshot cursor_one{fixture};
    for (unsigned repeat = 0; repeat < 8; ++repeat)
        check(!fixture.dispatch.select(Phase::inactive) && cursor_one.unchanged(fixture),
              "idle preserves retained one cursor");
}

auto main() -> int {
    admission_and_fairness();
    continuous_fairness_and_idle();
    terminal_orders_and_copies();
    identity_and_rebinding();
    generation_exhaustion();
    const auto envelopes = adversarial_envelopes();
    const auto sequences = transition_sequences();
    std::cout << "PASS: dispatch " << envelopes << " rejected envelopes, " << sequences
              << " exhaustive five-operation sequences, 4096 128-operation model traces, round-robin bounded "
                 "admission, selected-only replies,"
                 " terminal/quiescence ordering, copied/scrubbed payloads, stale/rebound identity and generation "
                 "exhaustion\n";
    return 0;
}
} // namespace kernel_dispatch
