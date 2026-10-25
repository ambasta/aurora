#include "../kernel/ipc-policy.hpp"
#include "../kernel/ram-scratchpad.hpp"
#include "../kernel/uefi/ram-file-policy.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <optional>
#include <string_view>
#include <type_traits>

// The direct program-console source link imports I/O; this IPC fixture grants none.
extern "C" void __au_runtime_console_next(const void *, std::uint64_t, void *) {
    std::abort();
}
extern "C" std::uint64_t __au_runtime_console_put(const void *, std::uint64_t, std::uint64_t) {
    std::abort();
}

using namespace aurora::ipc;
using aurora::user::DomainHandle;
using aurora::user::DomainRegistry;
constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
static_assert(!std::is_copy_constructible_v<Mailbox> && !std::is_move_constructible_v<Mailbox>);
static_assert(!std::is_constructible_v<DomainHandle, std::size_t, std::uint64_t>);
static_assert(std::is_trivially_copyable_v<Request> && sizeof(Request) == 2 * sizeof(std::uint64_t));
static_assert(detail::generation_after(0, maximum) == 1);
static_assert(detail::generation_after(maximum - 1, maximum) == maximum);
static_assert(!detail::generation_after(maximum, maximum));
static_assert(!detail::generation_after(4, 3));
static_assert(!detail::generation_after(0, 0));

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
    DomainHandle client{}, service{}, stranger{}, outsider{};
    Mailbox mailbox{domains};
    Endpoint client_cap{}, service_cap{};
    std::uint64_t transaction{};
    Fixture() {
        client = *domains.create();
        service = *domains.create();
        stranger = *domains.create();
        outsider = *foreign.create();
        check(mailbox.bind(client, service), "fixture bind");
        client_cap = *mailbox.endpoint(client);
        service_cap = *mailbox.endpoint(service);
    }
    auto submit() -> void {
        const auto result = mailbox.submit(client, Phase::request, client_cap, Request{40, 2});
        check(result.has_value(), "valid request");
        transaction = *result;
    }
    auto receive() -> void {
        const auto result = mailbox.receive(service, Phase::service, service_cap, transaction);
        check(result && result->first() == 40 && result->second() == 2, "exact copied request");
    }
    auto reply() -> void {
        check(mailbox.reply(service, Phase::service, service_cap, transaction, 42), "valid reply");
    }
    auto consume(Outcome outcome = Outcome::replied) -> void {
        const auto result = mailbox.consume(client, Phase::completion, client_cap, transaction);
        check(result && result->outcome() == outcome && result->value() == (outcome == Outcome::replied ? 42 : 0),
              "exact completion");
    }
    auto advance(State state) -> void {
        if (state == State::idle)
            return;
        submit();
        if (state == State::pending)
            return;
        if (state == State::cancelled) {
            check(mailbox.cancel(Phase::inactive), "cancel pending");
            return;
        }
        receive();
        if (state == State::delivered)
            return;
        reply();
        if (state == State::replied)
            return;
        consume();
    }
};
class Snapshot final {
    State state_;
    bool scrubbed_;
    std::optional<Endpoint> client_, service_;

public:
    explicit Snapshot(const Fixture &fixture)
        : state_(fixture.mailbox.state()), scrubbed_(fixture.mailbox.scrubbed()),
          client_(fixture.mailbox.endpoint(fixture.client)), service_(fixture.mailbox.endpoint(fixture.service)) {
    }
    auto unchanged(const Fixture &fixture) const -> bool {
        const auto client = fixture.mailbox.endpoint(fixture.client),
                   service = fixture.mailbox.endpoint(fixture.service);
        return state_ == fixture.mailbox.state() && scrubbed_ == fixture.mailbox.scrubbed() &&
               client.has_value() == client_.has_value() && service.has_value() == service_.has_value() &&
               (!client || same(*client, *client_)) && (!service || same(*service, *service_));
    }
};
template <class Operation> auto rejects(Fixture &fixture, Operation operation) -> void {
    const Snapshot before{fixture};
    check(!operation(), "untrusted operation denied");
    check(before.unchanged(fixture), "rejection preserves state, payload occupancy and grants");
}

auto adversarial_envelopes() -> std::uint64_t {
    std::uint64_t checked = 0;
    for (const auto state :
         {State::idle, State::pending, State::delivered, State::replied, State::cancelled, State::consumed}) {
        Fixture fixture;
        Fixture other_mailbox;
        fixture.advance(state);
        const std::array callers{fixture.client, fixture.service, fixture.stranger, fixture.outsider, DomainHandle{}};
        const std::array caps{fixture.client_cap,
                              fixture.service_cap,
                              Endpoint{},
                              Endpoint{2, fixture.client_cap.generation()},
                              Endpoint{maximum, fixture.client_cap.generation()},
                              Endpoint{0, 0},
                              Endpoint{1, 0},
                              Endpoint{0, maximum},
                              Endpoint{1, maximum},
                              other_mailbox.client_cap,
                              other_mailbox.service_cap};
        const std::array phases{
            Phase::inactive, Phase::request, Phase::service, Phase::completion, static_cast<Phase>(99)};
        const std::array transactions{std::uint64_t{0}, fixture.transaction, fixture.transaction + 1, maximum};
        for (std::size_t actor = 0; actor < callers.size(); ++actor) {
            for (const auto cap : caps) {
                for (const auto phase : phases) {
                    if (!(state == State::idle && actor == 0 && same(cap, fixture.client_cap) &&
                          phase == Phase::request)) {
                        rejects(fixture, [&] {
                            return fixture.mailbox.submit(callers[actor], phase, cap, Request{91, 92}).has_value();
                        });
                        ++checked;
                    }
                    for (const auto transaction : transactions) {
                        const bool exact = transaction != 0 && transaction == fixture.transaction;
                        if (!(state == State::pending && actor == 1 && same(cap, fixture.service_cap) &&
                              phase == Phase::service && exact)) {
                            rejects(fixture, [&] {
                                return fixture.mailbox.receive(callers[actor], phase, cap, transaction).has_value();
                            });
                            ++checked;
                        }
                        if (!(state == State::delivered && actor == 1 && same(cap, fixture.service_cap) &&
                              phase == Phase::service && exact)) {
                            rejects(fixture, [&] {
                                return fixture.mailbox.reply(callers[actor], phase, cap, transaction, 999);
                            });
                            ++checked;
                        }
                        if (!((state == State::replied || state == State::cancelled) && actor == 0 &&
                              same(cap, fixture.client_cap) && phase == Phase::completion && exact)) {
                            rejects(fixture, [&] {
                                return fixture.mailbox.consume(callers[actor], phase, cap, transaction).has_value();
                            });
                            ++checked;
                        }
                    }
                    if (phase != Phase::inactive || (state != State::pending && state != State::delivered)) {
                        rejects(fixture, [&] {
                            return fixture.mailbox.cancel(phase);
                        });
                        ++checked;
                    }
                    if (phase != Phase::inactive || state != State::consumed) {
                        rejects(fixture, [&] {
                            return fixture.mailbox.recycle(phase);
                        });
                        ++checked;
                    }
                    if (phase != Phase::inactive || (state != State::idle && state != State::consumed)) {
                        rejects(fixture, [&] {
                            return fixture.mailbox.revoke(phase);
                        });
                        ++checked;
                    }
                }
            }
        }
        // Drain each attacked state through its real successful path: rejecting
        // an envelope must not corrupt a still-pending request or retained reply.
        if (state == State::idle)
            fixture.submit();
        if (state == State::idle || state == State::pending)
            fixture.receive();
        if (state == State::idle || state == State::pending || state == State::delivered)
            fixture.reply();
        if (state != State::consumed)
            fixture.consume(state == State::cancelled ? Outcome::cancelled : Outcome::replied);
        check(fixture.mailbox.scrubbed(), "attacked state drained and scrubbed");
    }
    return checked;
}

// Independent transition model over every sequence of six kernel operations.
// The model contains no endpoint-validation implementation or generation allocator.
auto transition_sequences() -> std::uint64_t {
    constexpr unsigned operation_count = 8, depth = 6;
    std::uint64_t sequences = 1;
    for (unsigned index = 0; index < depth; ++index)
        sequences *= operation_count;
    for (std::uint64_t encoded = 0; encoded < sequences; ++encoded) {
        Fixture fixture;
        State expected_state = State::idle;
        bool bound = true;
        std::uint64_t path = encoded;
        for (unsigned step = 0; step < depth; ++step) {
            const auto operation = path % operation_count;
            path /= operation_count;
            const Snapshot before{fixture};
            bool expected = false, actual = false;
            switch (operation) {
            case 0: {
                expected = bound && expected_state == State::idle;
                const auto result =
                    fixture.mailbox.submit(fixture.client, Phase::request, fixture.client_cap, Request{40, 2});
                actual = result.has_value();
                if (actual) {
                    fixture.transaction = *result;
                    expected_state = State::pending;
                }
                break;
            }
            case 1: {
                expected = bound && expected_state == State::pending;
                const auto result =
                    fixture.mailbox.receive(fixture.service, Phase::service, fixture.service_cap, fixture.transaction);
                actual = result.has_value();
                if (actual) {
                    check(result->first() == 40 && result->second() == 2, "model request payload");
                    expected_state = State::delivered;
                }
                break;
            }
            case 2:
                expected = bound && expected_state == State::delivered;
                actual = fixture.mailbox.reply(
                    fixture.service, Phase::service, fixture.service_cap, fixture.transaction, 42);
                if (actual)
                    expected_state = State::replied;
                break;
            case 3: {
                expected = bound && (expected_state == State::replied || expected_state == State::cancelled);
                const auto result =
                    fixture.mailbox.consume(fixture.client, Phase::completion, fixture.client_cap, fixture.transaction);
                actual = result.has_value();
                if (actual) {
                    check(result->outcome() ==
                              (expected_state == State::replied ? Outcome::replied : Outcome::cancelled),
                          "model completion outcome");
                    check(result->value() == (expected_state == State::replied ? 42 : 0), "model completion payload");
                    expected_state = State::consumed;
                }
                break;
            }
            case 4:
                expected = expected_state == State::pending || expected_state == State::delivered;
                actual = fixture.mailbox.cancel(Phase::inactive);
                if (actual)
                    expected_state = State::cancelled;
                break;
            case 5:
                expected = expected_state == State::consumed;
                actual = fixture.mailbox.recycle(Phase::inactive);
                if (actual)
                    expected_state = State::idle;
                break;
            case 6:
                expected = bound && (expected_state == State::idle || expected_state == State::consumed);
                actual = fixture.mailbox.revoke(Phase::inactive);
                if (actual) {
                    bound = false;
                    expected_state = State::idle;
                }
                break;
            case 7:
                expected = !bound && expected_state == State::idle;
                actual = fixture.mailbox.bind(fixture.client, fixture.service);
                if (actual) {
                    bound = true;
                    fixture.client_cap = *fixture.mailbox.endpoint(fixture.client);
                    fixture.service_cap = *fixture.mailbox.endpoint(fixture.service);
                }
                break;
            default:
                check(false, "model operation bound");
            }
            check(actual == expected, "transition agrees with independent model");
            check(fixture.mailbox.state() == expected_state, "exact model state");
            check(fixture.mailbox.scrubbed() == (expected_state != State::pending && expected_state != State::replied),
                  "model scrub invariant");
            check(fixture.mailbox.endpoint(fixture.client).has_value() == bound, "model grant lifetime");
            if (!actual)
                check(before.unchanged(fixture), "model rejection atomicity");
        }
    }
    return sequences;
}

auto lifecycle_and_copies() -> void {
    Fixture fixture;
    check(fixture.client_cap.slot() == 0 && fixture.service_cap.slot() == 1, "fixed distinct rights slots");
    check(!fixture.mailbox.endpoint(fixture.stranger) && !fixture.mailbox.endpoint(fixture.outsider),
          "no ambient grants");
    Request source{maximum, std::uint64_t{1} << 63};
    const auto transaction = fixture.mailbox.submit(fixture.client, Phase::request, fixture.client_cap, source);
    check(transaction.has_value(), "full-width request accepted");
    source = Request{0, 0};
    const auto delivered = fixture.mailbox.receive(fixture.service, Phase::service, fixture.service_cap, *transaction);
    check(delivered && delivered->first() == maximum && delivered->second() == (std::uint64_t{1} << 63),
          "independent request snapshot");
    check(fixture.mailbox.scrubbed(), "copied request erased on delivery");
    check(fixture.mailbox.reply(fixture.service, Phase::service, fixture.service_cap, *transaction, maximum),
          "full-width reply");
    rejects(fixture, [&] {
        return fixture.mailbox.cancel(Phase::inactive);
    });
    const auto result = fixture.mailbox.consume(fixture.client, Phase::completion, fixture.client_cap, *transaction);
    check(result && result->outcome() == Outcome::replied && result->value() == maximum && fixture.mailbox.scrubbed(),
          "full-width completion and scrub");
    check(fixture.mailbox.recycle(Phase::inactive), "recycle completed storage");
    fixture.submit();
    check(fixture.transaction != *transaction, "transaction does not repeat");
    rejects(fixture, [&] {
        return fixture.mailbox.receive(fixture.service, Phase::service, fixture.service_cap, *transaction).has_value();
    });
    fixture.receive();
    rejects(fixture, [&] {
        return fixture.mailbox.reply(fixture.service, Phase::service, fixture.service_cap, *transaction, 999);
    });
    check(fixture.mailbox.cancel(Phase::inactive) && fixture.mailbox.scrubbed(), "cancel delivered request");
    rejects(fixture, [&] {
        return fixture.mailbox.reply(fixture.service, Phase::service, fixture.service_cap, fixture.transaction, 999);
    });
    fixture.consume(Outcome::cancelled);
    const auto old_client = fixture.client_cap, old_service = fixture.service_cap;
    check(fixture.mailbox.revoke(Phase::inactive) && fixture.mailbox.scrubbed(), "revoke terminal grants");
    check(fixture.mailbox.bind(fixture.client, fixture.service), "rebind original participants");
    fixture.client_cap = *fixture.mailbox.endpoint(fixture.client);
    fixture.service_cap = *fixture.mailbox.endpoint(fixture.service);
    check(!same(old_client, fixture.client_cap) && !same(old_service, fixture.service_cap), "fresh bind epoch");
    rejects(fixture, [&] {
        return fixture.mailbox.submit(fixture.client, Phase::request, old_client, Request{91, 92}).has_value();
    });
    fixture.submit();
    rejects(fixture, [&] {
        return fixture.mailbox.receive(fixture.service, Phase::service, old_service, fixture.transaction).has_value();
    });
    fixture.receive();
    fixture.reply();
    fixture.consume();
    check(delivered->first() == maximum && result->value() == maximum,
          "returned values survive storage reuse independently");

    // Exact zero is a payload too; clearing does not make a terminal reply idle.
    check(fixture.mailbox.recycle(Phase::inactive), "zero payload reuse");
    const auto zero = fixture.mailbox.submit(fixture.client, Phase::request, fixture.client_cap, Request{});
    check(zero && fixture.mailbox.state() == State::pending && fixture.mailbox.scrubbed(),
          "zero request occupancy uses state");
    check(fixture.mailbox.receive(fixture.service, Phase::service, fixture.service_cap, *zero).has_value(),
          "zero request delivery");
    check(fixture.mailbox.reply(fixture.service, Phase::service, fixture.service_cap, *zero, 0), "zero reply");
    check(!fixture.mailbox.cancel(Phase::inactive), "zero reply wins terminal race");
    const auto zero_result = fixture.mailbox.consume(fixture.client, Phase::completion, fixture.client_cap, *zero);
    check(zero_result && zero_result->outcome() == Outcome::replied && zero_result->value() == 0,
          "zero success differs from cancellation");
}

auto domain_incarnations() -> void {
    for (const auto state : {State::pending, State::delivered}) {
        Fixture fixture;
        fixture.advance(state);
        const auto previous = fixture.service;
        check(fixture.domains.destroy(previous), "retire service domain");
        const auto replacement = fixture.domains.create();
        check(replacement.has_value(), "recreate service slot");
        check(!fixture.mailbox.endpoint(previous) && !fixture.mailbox.endpoint(*replacement),
              "domain incarnation cannot inherit grant");
        rejects(fixture, [&] {
            return fixture.mailbox.receive(*replacement, Phase::service, fixture.service_cap, fixture.transaction)
                .has_value();
        });
        rejects(fixture, [&] {
            return fixture.mailbox.reply(*replacement, Phase::service, fixture.service_cap, fixture.transaction, 999);
        });
        check(fixture.mailbox.cancel(Phase::inactive), "kernel cancellation with dead service");
        fixture.consume(Outcome::cancelled);
        check(fixture.mailbox.revoke(Phase::inactive), "retire invalid service grant after completion");
        check(fixture.mailbox.bind(fixture.client, *replacement), "bind replacement service");
        fixture.service = *replacement;
        fixture.client_cap = *fixture.mailbox.endpoint(fixture.client);
        fixture.service_cap = *fixture.mailbox.endpoint(fixture.service);
        fixture.submit();
        fixture.receive();
        fixture.reply();
        fixture.consume();
    }
    Fixture dead_client;
    dead_client.advance(State::delivered);
    check(dead_client.domains.destroy(dead_client.client), "retire client domain");
    check(!dead_client.mailbox.reply(
              dead_client.service, Phase::service, dead_client.service_cap, dead_client.transaction, 42),
          "reply requires live client");
    check(dead_client.mailbox.cancel(Phase::inactive), "kernel cancels orphaned transaction");
    check(!dead_client.mailbox.consume(
              dead_client.client, Phase::completion, dead_client.client_cap, dead_client.transaction),
          "dead client cannot consume");

    DomainRegistry registry;
    const auto client = *registry.create(), service = *registry.create();
    std::optional<Mailbox> mailbox;
    mailbox.emplace(registry);
    check(mailbox->bind(client, service), "first mailbox incarnation");
    const auto old_cap = *mailbox->endpoint(client), old_server = *mailbox->endpoint(service);
    const auto old_transaction = *mailbox->submit(client, Phase::request, old_cap, Request{1, 2});
    mailbox.reset();
    mailbox.emplace(registry);
    check(mailbox->bind(client, service), "same-address mailbox rebirth");
    const auto new_cap = *mailbox->endpoint(client), new_server = *mailbox->endpoint(service);
    check(!same(old_cap, new_cap), "rebirth epoch differs");
    check(!mailbox->submit(client, Phase::request, old_cap, Request{9, 9}), "rebirth stale cap rejected");
    const auto new_transaction = mailbox->submit(client, Phase::request, new_cap, Request{40, 2});
    check(new_transaction && *new_transaction != old_transaction, "rebirth transaction differs");
    check(!mailbox->receive(service, Phase::service, old_server, *new_transaction), "rebirth old service cap rejected");
    check(!mailbox->receive(service, Phase::service, new_server, old_transaction), "rebirth old transaction rejected");
    check(mailbox->receive(service, Phase::service, new_server, *new_transaction).has_value(),
          "rebirth valid request remains");

    Mailbox parallel{registry};
    check(parallel.bind(client, service), "parallel same-owner mailbox");
    const auto parallel_cap = *parallel.endpoint(client);
    check(!parallel.submit(client, Phase::request, new_cap, Request{9, 9}), "live cross-mailbox grant denied");
    const auto parallel_transaction = parallel.submit(client, Phase::request, parallel_cap, Request{40, 2});
    check(parallel_transaction && *parallel_transaction != *new_transaction, "parallel transaction uniqueness");
    check(!mailbox->reply(service, Phase::service, new_server, *parallel_transaction, 999),
          "live cross-mailbox transaction denied");
    check(mailbox->reply(service, Phase::service, new_server, *new_transaction, 42),
          "cross-mailbox attack preserves own reply");

    // A live mailbox must also reject old owners after the registry itself is
    // reconstructed at the same storage address with fresh domain incarnations.
    std::optional<DomainRegistry> reincarnated;
    reincarnated.emplace();
    const auto prior_client = *reincarnated->create(), prior_service = *reincarnated->create();
    Mailbox survivor{*reincarnated};
    check(survivor.bind(prior_client, prior_service), "registry rebirth fixture");
    const auto prior_cap = *survivor.endpoint(prior_client);
    reincarnated.reset();
    reincarnated.emplace();
    const auto fresh_client = *reincarnated->create(), fresh_service = *reincarnated->create();
    check(!survivor.endpoint(prior_client) && !survivor.endpoint(fresh_client),
          "registry rebirth invalidates old grants");
    check(!survivor.submit(fresh_client, Phase::request, prior_cap, Request{9, 9}),
          "registry rebirth cannot impersonate owner");
    check(survivor.revoke(Phase::inactive) && survivor.bind(fresh_client, fresh_service),
          "registry rebirth explicit fresh bind");

    // Active-root checks belong to the entry adapter. Policy operates identically
    // on a valid caller snapshot while active or inactive.
    Fixture active;
    check(active.domains.activate(active.client), "activate client");
    active.submit();
    check(active.domains.deactivate(active.client) && active.domains.activate(active.service), "switch trusted caller");
    active.receive();
    active.reply();
    check(active.domains.deactivate(active.service), "return to kernel root");
    active.consume();
}

auto generation_exhaustion() -> void {
    DomainRegistry registry, foreign;
    const auto client = *registry.create(), service = *registry.create(), outsider = *foreign.create();
    Mailbox baseline{registry};
    check(baseline.bind(client, service), "generation baseline");
    const auto epoch = baseline.endpoint(client)->generation();
    // The next successful bind reaches its configured ceiling. Every subsequent
    // allocation must fail without wrapping, clearing grants, or changing state.
    Mailbox limited{registry, epoch + 1};
    check(!limited.bind(client, client) && !limited.bind(client, outsider) && !limited.bind(DomainHandle{}, service),
          "invalid bind is atomic");
    check(registry.activate(client), "bind active-root fixture");
    check(!limited.bind(client, service), "binding requires inactive participants");
    check(registry.deactivate(client), "restore root");
    check(limited.bind(client, service), "last available bind epoch");
    const auto cap = *limited.endpoint(client);
    check(cap.generation() == epoch + 1, "rejected binds did not burn generations");
    for (unsigned attempt = 0; attempt < 5; ++attempt) {
        check(!limited.submit(client, Phase::request, cap, Request{40, 2}), "generation exhausted request");
        check(limited.state() == State::idle && limited.scrubbed() && same(*limited.endpoint(client), cap),
              "exhaustion atomicity");
    }
    check(limited.revoke(Phase::inactive) && !limited.bind(client, service), "exhausted grant cannot be recreated");
    check(limited.state() == State::idle && limited.scrubbed() && !limited.endpoint(client),
          "failed rebind keeps zero grants");
    Mailbox transaction_limit{registry, epoch + 3};
    check(transaction_limit.bind(client, service), "transaction limit bind");
    const auto client_cap = *transaction_limit.endpoint(client), server_cap = *transaction_limit.endpoint(service);
    const auto final = transaction_limit.submit(client, Phase::request, client_cap, Request{40, 2});
    check(final && *final == epoch + 3, "last available transaction generation");
    check(transaction_limit.receive(service, Phase::service, server_cap, *final).has_value(),
          "exhausted source allows existing delivery");
    check(transaction_limit.reply(service, Phase::service, server_cap, *final, 42),
          "exhausted source allows existing reply");
    check(transaction_limit.consume(client, Phase::completion, client_cap, *final).has_value(),
          "exhausted source allows completion");
    check(transaction_limit.recycle(Phase::inactive), "exhausted source allows scrubbed recycle");
    check(!transaction_limit.submit(client, Phase::request, client_cap, Request{9, 9}),
          "no transaction wrap after reuse");
    Mailbox closed{registry, 0};
    check(!closed.bind(client, service) && closed.scrubbed() && !closed.endpoint(client),
          "zero generation ceiling fails closed");
    // Exhaust every boundary of a reduced ceiling through the same uint64_t
    // successor, and separately exercise its actual maximum above at compile time.
    for (std::uint64_t ceiling = 0; ceiling <= 255; ++ceiling) {
        for (std::uint64_t previous = 0; previous <= 256; ++previous) {
            const auto next = detail::generation_after(previous, ceiling);
            check(next.has_value() == (previous < ceiling), "generation boundary model");
            if (next)
                check(*next == previous + 1 && *next != 0, "strict nonzero successor");
        }
    }
}

auto retained_file_framing() -> void {
    using F = aurora::uefi::RamFileFraming;
    for (const auto right : {F::Right::replace, F::Right::append}) {
        const unsigned tag = right == F::Right::replace ? 3 : 8;
        for (unsigned length = 0; length <= 49; ++length) {
            F fixed{right, length};
            for (unsigned other = 0; other <= 50; ++other)
                check(fixed.permits((other << 8) | tag) == (other == length), "scratchpad exact admitted BEGIN length");
            F write{right};
            check(!write.permits(1) && !write.permits(5) && !write.permits(tag == 3 ? 8 : 3),
                  "RAM write immutable right and begin order");
            check(write.publish((length << 8) | tag), "RAM bounded replace begin");
            check(!write.reply(1), "RAM reply requires delivery");
            check(write.delivered((length << 8) | tag) && !write.delivered((length << 8) | tag),
                  "RAM one-shot delivery");
            check(write.reply(1) && !write.reply(1), "RAM one-shot begin reply");
            for (unsigned offset = 0; offset < length; ++offset) {
                for (unsigned byte = 0; byte < 256; ++byte)
                    check(write.permits((byte << 16) | (offset << 8) | 4), "RAM every binary byte admitted");
                const auto word = (255U << 16) | (offset << 8) | 4;
                check(!write.permits(word | (1ULL << 24)) && !write.permits(word + 256),
                      "RAM reserved/order rejection");
                check(!write.permits(5), "RAM no premature COMMIT");
                check(write.publish(word) && write.delivered(word) && write.reply(1), "RAM sequential staging framing");
            }
            check(write.publish(5) && !write.commit_delivered(), "RAM COMMIT publication not delivery");
            check(write.delivered(5) && write.commit_delivered() && !write.begin_abort(), "RAM no post-COMMIT abort");
            check(!write.reply(1) && !write.reply(5 | (1ULL << 63)) && write.reply(5), "RAM exact committed reply");
            check(write.outcome() == F::Outcome::committed && write.count() == length + 2 && !write.permits(1),
                  "RAM terminal command cannot renew allowance");
            check(write.terminal_reply() == 5 && write.data_count() == 0, "RAM committed terminal evidence");
            F read{F::Right::read};
            check(!read.permits(3) && !read.permits(8) && read.publish(1) && read.delivered(1) && read.reply(1),
                  "RAM read right");
            for (unsigned offset = 0; offset < length; ++offset) {
                check(read.publish((offset << 8) | 2) && read.delivered((offset << 8) | 2), "RAM read offset");
                check(!read.reply(0x10002) && !read.reply(7) && read.reply(0xff02), "RAM bounded binary reply");
            }
            check(read.publish((length << 8) | 2) && read.delivered((length << 8) | 2) && read.reply(3),
                  "RAM EOF framing");
            check(read.count() == length + 2 && read.state() == F::State::terminal, "RAM maximum51 exchanges");
            check(read.terminal_reply() == 3 && read.data_count() == length, "RAM exact EOF/data-count evidence");
        }
    }
    for (const auto word : std::array<std::uint64_t, 6>{0, 6, 50U << 8 | 3U, 1ULL << 63 | 3, 0x10003, UINT64_MAX}) {
        F bad{F::Right::replace};
        check(!bad.publish(word) && bad.state() == F::State::fresh && bad.count() == 0, "RAM malformed nonmutation");
    }
    for (const auto right :
         {F::Right::read, F::Right::replace, F::Right::append, static_cast<F::Right>(3), static_cast<F::Right>(-1)}) {
        F framing{right};
        check(framing.permits(1) == (right == F::Right::read) && framing.permits(3) == (right == F::Right::replace) &&
                  framing.permits(8) == (right == F::Right::append),
              "RAM exact closed right dispatch");
    }
    for (const auto word : std::array<std::uint64_t, 3>{50U << 8 | 8U, 1ULL << 63 | 8, 0x10008}) {
        F bad{F::Right::append};
        check(!bad.publish(word) && bad.count() == 0, "RAM malformed append nonmutation");
    }
    F append_rejected{F::Right::append};
    check(append_rejected.publish(8) && append_rejected.delivered(8) && append_rejected.reply(6) &&
              append_rejected.outcome() == F::Outcome::rejected,
          "RAM append semantic refusal terminal");
    F missing{F::Right::read};
    check(missing.publish(1) && missing.delivered(1) && missing.reply(1) && missing.publish(2) &&
              missing.delivered(2) && missing.reply(4),
          "RAM missing permitted only offsetzero");
    check(missing.terminal_reply() == 4 && missing.data_count() == 0, "RAM missing terminal distinct from empty EOF");
    F invalid_length{F::Right::replace, 51};
    check(!invalid_length.permits(3), "RAM invalid fixed length closed");
    F rejected{F::Right::read};
    check(rejected.publish(1) && rejected.delivered(1) && rejected.reply(6) && rejected.terminal_reply() == 6,
          "RAM exact rejected terminal");
    for (const auto right : {F::Right::replace, F::Right::append}) {
        const unsigned tag = right == F::Right::replace ? 3 : 8;
        F abort{right};
        check(abort.publish((256U | tag)) && abort.delivered((256U | tag)) && abort.reply(1) && abort.begin_abort(),
              "RAM precommit abort");
        check(!abort.permits(tag) && !abort.publish(tag) && !abort.delivered(tag) && !abort.reply(7) &&
                  !abort.acknowledge_abort(0) && !abort.acknowledge_abort(7 | (1ULL << 63)),
              "RAM abort exclusive private acknowledgement");
        check(abort.acknowledge_abort(7) && !abort.acknowledge_abort(7) && abort.outcome() == F::Outcome::aborted,
              "RAM exact ABORTED once");
        F pending_commit{right};
        check(pending_commit.publish(tag) && pending_commit.delivered(tag) && pending_commit.reply(1) &&
                  pending_commit.publish(5) && pending_commit.begin_abort(),
              "RAM undelivered COMMIT can abort");
    }
}
auto retained_file_settlement() -> void {
    DomainRegistry registry;
    const auto caller = registry.create(), service = registry.create();
    check(caller && service, "RAM settlement original owners");
    Mailbox mailbox{registry};
    check(mailbox.bind(*caller, *service), "RAM settlement binding");
    const auto ce = *mailbox.endpoint(*caller), se = *mailbox.endpoint(*service);
    const auto ticket = mailbox.submit(*caller, Phase::request, ce, Request{5, 0});
    check(ticket && mailbox.receive(*service, Phase::service, se, *ticket), "RAM COMMIT delivered");
    bool execution_disabled = true;
    check(execution_disabled && registry.ready(*caller), "RAM logical disposal retains original handle");
    check(mailbox.reply(*service, Phase::service, se, *ticket, 5), "RAM committed after caller disposal");
    check(!mailbox.cancel(Phase::inactive) && !mailbox.consume(*caller, Phase::completion, ce, *ticket + 1),
          "RAM stale cancellation preserves committed receipt");
    const auto receipt = mailbox.consume(*caller, Phase::completion, ce, *ticket);
    check(receipt && receipt->outcome() == Outcome::replied && receipt->value() == 5,
          "RAM original caller settlement not false cancelled");
    check(!mailbox.consume(*caller, Phase::completion, ce, *ticket) && mailbox.revoke(Phase::inactive),
          "RAM settlement once then revoke");
    check(registry.destroy(*caller) && registry.ready(*service),
          "RAM physical retirement after settlement preserves service");
    const auto fresh = registry.create();
    check(fresh && mailbox.bind(*fresh, *service) && !mailbox.submit(*fresh, Phase::request, ce, Request{1, 0}),
          "RAM fresh caller cannot inherit revoked endpoint");
}

auto scratchpad_copied_records() -> void {
    using namespace aurora::scratchpad;
    using S = CopiedStack;
    std::array<std::byte, S::reservation> bytes{};
    const auto put_word = [&](std::size_t at, std::uint64_t value) {
        for (unsigned i = 0; i < 8; ++i)
            bytes[at + i] = std::byte{static_cast<unsigned char>(value >> (8 * i))};
    };
    Command command;
    Result result;
    check(command.valid() && result.valid(), "scratchpad pristine get/incomplete");
    for (std::uint64_t operation = 0; operation < 4; ++operation)
        for (std::uint64_t kind = 0; kind < 6; ++kind)
            for (std::uint64_t reply = 0; reply < 8; ++reply)
                for (std::uint64_t count = 0; count < 3; ++count) {
                    scrub(result);
                    result.kind = kind;
                    const bool accepted =
                        operation <= 2 &&
                        ((operation == 0 && kind == 1 && reply == 3 && count == 0) ||
                         (operation == 0 && kind == 2 && reply == 4 && count == 0) ||
                         ((operation == 1 || operation == 2) && kind == 3 && reply == 5 && count == 0) ||
                         (kind == 4 && reply == 6));
                    check(result.terminal_for(operation, reply, count) == accepted,
                          "scratchpad exhaustive operation/result/terminal relation");
                }
    result.kind = 1;
    result.count = 1;
    result.bytes[0] = 'P';
    check(result.terminal_for(0, 3, 1) && !result.terminal_for(0, 3, 0) && !result.terminal_for(0, 3, 2),
          "scratchpad complete content must match every accepted DATA reply");
    scrub(result);
    for (std::uint64_t operation = 0; operation <= 3; ++operation)
        for (std::uint64_t length = 0; length <= 50; ++length) {
            scrub(command);
            command.operation = operation;
            command.count = length;
            for (std::size_t i = 0; i < length; ++i)
                command.bytes[i] = 32;
            check(command.valid() ==
                      (operation <= 2 && length <= 49 && (operation == 1 || operation == 2 || length == 0)),
                  "scratchpad closed raw operation/count");
        }
    scrub(command);
    command.operation = 1;
    command.count = 1;
    for (unsigned byte = 0; byte <= 255; ++byte) {
        command.bytes[0] = static_cast<std::uint8_t>(byte);
        check(command.valid() == (byte >= 32 && byte <= 126), "scratchpad exact printable-byte boundary");
    }
    command.bytes[0] = 'X';
    for (std::size_t suffix = 1; suffix < 64; ++suffix) {
        command.bytes[suffix] = 1;
        check(!command.valid(), "scratchpad every hidden command suffix denied");
        command.bytes[suffix] = 0;
    }
    check(S::stage(bytes, command) && !S::stage(bytes, command), "scratchpad pristine fixed-window stage once");
    put_word(8, 23); // Caller endpoint slot zero is valid, generation must not be zero.
    put_word(S::result + 72, 3);
    check(S::capture(bytes, 0, 23, 1, 1, result) && result.kind == 3 && result.count == 0,
          "scratchpad slotzero canonical saved result");
    for (const auto slot : std::array<std::uint64_t, 2>{1, UINT64_MAX})
        check(!S::capture(bytes, slot, 23, 1, 1, result), "scratchpad foreign caller slot denied");
    check(!S::capture(bytes, 0, 0, 1, 1, result) && !S::capture(bytes, 0, 24, 1, 1, result),
          "scratchpad zero/stale generation denied");
    check(!S::capture(bytes, 0, 23, 0, 0, result) && !S::capture(bytes, 0, 23, 1, 2, result),
          "scratchpad operation/count cannot change admitted authority");
    for (std::size_t at = S::sentinel; at < S::reservation; ++at) {
        bytes[at] = std::byte{1};
        check(!S::capture(bytes, 0, 23, 1, 1, result), "scratchpad entire sentinel verified");
        bytes[at] = std::byte{0};
    }
    for (const auto kind : std::array<std::uint64_t, 2>{5, UINT64_MAX}) {
        put_word(S::result + 72, kind);
        check(!S::capture(bytes, 0, 23, 1, 1, result) && result.kind == 0,
              "scratchpad malformed result scrubs partial copy");
    }
    put_word(S::result + 72, 1);
    put_word(S::result + 64, 1);
    bytes[S::result] = std::byte{'Y'};
    check(S::capture(bytes, 0, 23, 1, 1, result) && result.bytes[0] == 'Y',
          "scratchpad copies actual complete result bytes, not the command bytes");
    for (std::size_t suffix = 1; suffix < 64; ++suffix) {
        bytes[S::result + suffix] = std::byte{1};
        check(!S::capture(bytes, 0, 23, 1, 1, result) && result.count == 0 && result.bytes[0] == 0,
              "scratchpad malformed result suffix cannot leak a prefix");
        bytes[S::result + suffix] = std::byte{0};
    }
    for (std::size_t at = 0; at < S::reservation; ++at) {
        bytes.fill(std::byte{0});
        bytes[at] = std::byte{1};
        check(!S::stage(bytes, command), "scratchpad every nonpristine window byte refused");
    }
    Submission submission;
    for (std::uint64_t action = 0; action < 4; ++action)
        for (std::uint64_t carry = 0; carry < 3; ++carry) {
            submission.action = action;
            submission.after_cr = carry;
            check(submission.valid() == (action <= 2 && carry <= 1), "scratchpad closed submission action/carry");
        }
    submission.action = 1;
    submission.after_cr = 0;
    submission.command = command;
    check(!submission.valid(), "scratchpad exit cannot hide a put");
    for (std::uint64_t kind = 0; kind < 13; ++kind) {
        Response response;
        response.kind = kind;
        check(response.valid() == (kind <= 11), "scratchpad closed output kind");
        response.count = 1;
        response.bytes[0] = 'Q';
        check(response.valid() == (kind == 1), "scratchpad outcome-only cannot carry content");
    }
}

auto main() -> int {
    scratchpad_copied_records();
    retained_file_framing();
    retained_file_settlement();
    lifecycle_and_copies();
    domain_incarnations();
    generation_exhaustion();
    const auto invalid = adversarial_envelopes();
    const auto sequences = transition_sequences();
    std::cout << "PASS: IPC " << invalid << " rejected envelopes, " << sequences
              << " six-operation transition sequences, copy/scrub, rights, stale/foreign/rebirth, terminal races, "
                 "generation limits and overflow boundaries\n";
}
