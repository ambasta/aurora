// Genuine Dispatcher and Aurora IPC/round-robin. ONLY the disposal producer is
// renamed at link time. Replacements test that a plan cannot mint authority and
// that a valid ordinary refusal remains a refusal before any mailbox mutation.
#include "../kernel/dispatch-policy.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <optional>

auto genuine(std::uint64_t phase, std::uint64_t state) -> std::uint64_t asm("aurora_kernel_client_disposal_real");

namespace {
using namespace aurora::ipc;
using aurora::user::DomainHandle;
using aurora::user::DomainRegistry;
constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
constexpr std::uint64_t high = std::uint64_t{1} << 63;
std::optional<std::uint64_t> replacement;
std::array<std::uint64_t, 2> last_input{};
std::uint64_t calls{}, substituted{}, early_refusals{}, successful{};
auto need(bool condition, const char *reason) -> void {
    if (!condition) {
        std::fprintf(stderr, "FAIL: %s\n", reason);
        std::abort();
    }
}
template <class T> auto bytes(const T &object) -> std::array<unsigned char, sizeof(T)> {
    std::array<unsigned char, sizeof(T)> result{};
    std::memcpy(result.data(), &object, result.size());
    return result;
}
// Observe real fresh grants rather than exposing a private sequence or reset.
class StampProbe final {
    DomainRegistry registry_;
    DomainHandle client_ = *registry_.create(), service_ = *registry_.create();

public:
    auto mint() const -> std::uint64_t {
        Mailbox observer{registry_};
        need(observer.bind(client_, service_), "legitimate observer bind");
        return observer.endpoint(client_)->generation();
    }
};
} // namespace
namespace aurora::ipc {
auto language_client_disposal(std::uint64_t phase, std::uint64_t state) -> std::uint64_t {
    ++calls;
    last_input = {phase, state};
    const auto real = genuine(phase, state);
    return replacement.value_or(real);
}
} // namespace aurora::ipc
namespace {
enum class Path {
    idle,
    pending,
    delivered,
    replied,
    cancelled,
    consumed_reply,
    consumed_cancelled
};
constexpr std::array targets{
    Path::idle, Path::pending, Path::replied, Path::cancelled, Path::consumed_reply, Path::consumed_cancelled};
constexpr std::array peers{Path::idle,
                           Path::pending,
                           Path::delivered,
                           Path::replied,
                           Path::cancelled,
                           Path::consumed_reply,
                           Path::consumed_cancelled};
auto state(Path path) -> State {
    constexpr std::array values{State::idle,
                                State::pending,
                                State::delivered,
                                State::replied,
                                State::cancelled,
                                State::consumed,
                                State::consumed};
    return values[static_cast<unsigned>(path)];
}
auto plan(Path path) -> std::uint64_t {
    constexpr std::array<std::uint64_t, 7> values{0x0102, 0x0302, 0x0302, 0x0402, 0x0402, 0x0202, 0x0202};
    return values[static_cast<unsigned>(path)];
}
auto replied(Path path) -> bool {
    return path == Path::replied || path == Path::consumed_reply;
}
class Fixture final {
public:
    DomainRegistry registry;
    std::array<DomainHandle, 2> clients{*registry.create(), *registry.create()};
    DomainHandle service = *registry.create();
    Dispatcher dispatch{registry};
    std::array<Endpoint, 2> client_caps{}, service_caps{};
    std::array<std::uint64_t, 2> transactions{};
    std::uint64_t first, second, answer;
    explicit Fixture(std::uint64_t first_word = high,
                     std::uint64_t second_word = maximum,
                     std::uint64_t reply_word = high + 17)
        : first(first_word), second(second_word), answer(reply_word) {
        need(dispatch.bind(clients, service), "bind real dispatcher");
        for (std::size_t slot = 0; slot < 2; ++slot) {
            client_caps[slot] = *dispatch.endpoint(slot, clients[slot]);
            service_caps[slot] = *dispatch.endpoint(slot, service);
        }
    }
    auto submit(std::size_t slot) -> void {
        const auto transaction =
            dispatch.submit(clients[slot], Phase::request, client_caps[slot], Request{first, second});
        need(transaction.has_value(), "real submit");
        transactions[slot] = *transaction;
    }
    auto select(std::size_t slot) -> void {
        const auto work = dispatch.select(Phase::inactive);
        need(work && work->client() == slot && work->transaction() == transactions[slot], "real select exact peer");
        need(work->request().first() == first && work->request().second() == second, "full-width copied peer payload");
    }
    auto reply(std::size_t slot) -> void {
        need(dispatch.reply(service, Phase::service, service_caps[slot], transactions[slot], answer), "real reply");
        need(dispatch.finish_selected(Phase::inactive, true), "quiescent service finish");
    }
    auto consume(std::size_t slot, bool is_reply) -> void {
        const auto completion =
            dispatch.consume(clients[slot], Phase::completion, client_caps[slot], transactions[slot]);
        need(completion && completion->outcome() == (is_reply ? Outcome::replied : Outcome::cancelled) &&
                 completion->value() == (is_reply ? answer : 0),
             "exact first terminal outcome");
    }
    auto prepare(std::size_t slot, Path path) -> void {
        if (path == Path::idle)
            return;
        submit(slot);
        if (path == Path::pending)
            return;
        if (path == Path::cancelled || path == Path::consumed_cancelled) {
            need(dispatch.cancel_pending(Phase::inactive) == 1, "only prepared mailbox cancelled");
            if (path == Path::consumed_cancelled)
                consume(slot, false);
            return;
        }
        select(slot);
        if (path == Path::delivered)
            return;
        reply(slot);
        if (path == Path::consumed_reply)
            consume(slot, true);
    }
};
auto same(const std::optional<Endpoint> &left, const std::optional<Endpoint> &right) -> bool {
    return left.has_value() == right.has_value() &&
           (!left || (left->slot() == right->slot() && left->generation() == right->generation()));
}
class PeerSnapshot final {
    std::size_t slot_;
    std::optional<State> state_;
    std::optional<std::uint64_t> transaction_;
    std::optional<Endpoint> client_, service_;
    std::optional<std::size_t> selected_;
    std::size_t cursor_;

public:
    PeerSnapshot(const Fixture &f, std::size_t slot)
        : slot_(slot), state_(f.dispatch.state(slot)), transaction_(f.dispatch.transaction(slot)),
          client_(f.dispatch.endpoint(slot, f.clients[slot])), service_(f.dispatch.endpoint(slot, f.service)),
          selected_(f.dispatch.selected()), cursor_(f.dispatch.next_client()) {
    }
    auto unchanged(const Fixture &f) const -> bool {
        return f.dispatch.bound() && f.dispatch.state(slot_) == state_ &&
               f.dispatch.transaction(slot_) == transaction_ &&
               same(f.dispatch.endpoint(slot_, f.clients[slot_]), client_) &&
               same(f.dispatch.endpoint(slot_, f.service), service_) && f.dispatch.selected() == selected_ &&
               f.dispatch.next_client() == cursor_;
    }
};
template <class Action>
auto deny(Fixture &f, StampProbe &probe, Action action, std::uint64_t word, bool reaches_producer) -> void {
    need(!replacement.has_value(), "no nested replacement");
    const auto before = bytes(f.dispatch);
    const auto registry_before = bytes(f.registry);
    const auto stamp = probe.mint(), count = calls;
    replacement = word;
    need(!action(), "malformed or refused plan cannot dispose client");
    replacement.reset();
    need(calls == count + (reaches_producer ? 1U : 0U), "caller and quiescence gates precede disposal producer");
    need(bytes(f.dispatch) == before, "denial preserves every dispatcher byte, including peer and receipts");
    need(bytes(f.registry) == registry_before, "denial preserves registry and owner liveness");
    need(probe.mint() == stamp + 1, "denial consumes no global generation");
    if (reaches_producer)
        ++substituted;
    else
        ++early_refusals;
}
auto receipt(const ClientDisposition &result, const Fixture &f, std::size_t slot, Path path) -> void {
    need(result.prior_state() == state(path), "receipt records actual prior lifecycle");
    const bool has_transaction = path != Path::idle;
    need(result.transaction().has_value() == has_transaction && result.completion().has_value() == has_transaction,
         "idle has no invented transaction or completion");
    if (!has_transaction)
        return;
    need(result.transaction() == f.transactions[slot], "retained original transaction identity");
    need(result.completion()->outcome() == (replied(path) ? Outcome::replied : Outcome::cancelled) &&
             result.completion()->value() == (replied(path) ? f.answer : 0),
         "retained exact first terminal word");
}
auto prepare_pair(Fixture &f, std::size_t offender, Path target, Path peer) -> void {
    // Resolve terminal setup before leaving any request pending: cancellation is
    // intentionally a real dispatcher-wide operation, never private-state edits.
    if (target != Path::pending)
        f.prepare(offender, target);
    if (peer != Path::pending && peer != Path::delivered)
        f.prepare(1 - offender, peer);
    if (target == Path::pending)
        f.prepare(offender, target);
    if (peer == Path::pending || peer == Path::delivered) {
        f.submit(1 - offender);
        if (peer == Path::delivered) {
            // A pending offender could be first in the fair queue. Deliver the
            // peer before submitting it instead of forging the dispatcher cursor.
            need(target != Path::pending, "selected-peer setup must precede pending offender");
            f.select(1 - offender);
        }
    }
}
auto producer_controls() -> void {
    StampProbe probe;
    constexpr std::array<std::array<std::uint64_t, 3>, 3> payloads{
        {{0, 0, 0}, {high, maximum, high + 17}, {maximum, high, maximum}}};
    for (const auto &words : payloads)
        for (const std::size_t offender : {0U, 1U})
            for (const auto target : targets)
                for (const auto peer : peers) {
                    Fixture f{words[0], words[1], words[2]};
                    if (target == Path::pending && peer == Path::delivered) {
                        f.prepare(1 - offender, peer);
                        f.prepare(offender, target);
                    } else {
                        prepare_pair(f, offender, target, peer);
                    }
                    const auto action = [&] {
                        return f.dispatch.dispose_client(Phase::inactive, offender, f.clients[offender], true)
                            .has_value();
                    };
                    const auto good = plan(target);
                    for (const auto word : {std::uint64_t{0},
                                            std::uint64_t{1},
                                            std::uint64_t{2},
                                            std::uint64_t{0x0101},
                                            std::uint64_t{0x0102},
                                            std::uint64_t{0x0202},
                                            std::uint64_t{0x0302},
                                            std::uint64_t{0x0402},
                                            std::uint64_t{0x0502},
                                            maximum}) {
                        if (word != good)
                            deny(f, probe, action, word, true);
                    }
                    for (unsigned bit = 0; bit < 64; ++bit)
                        deny(f, probe, action, good ^ (std::uint64_t{1} << bit), true);
                    need(last_input == std::array<std::uint64_t, 2>{0, static_cast<std::uint64_t>(state(target))},
                         "producer receives only actual copied phase and mailbox state");
                    const PeerSnapshot before{f, 1 - offender};
                    const auto registry_before = bytes(f.registry);
                    const auto stamp = probe.mint(), count = calls;
                    const auto result = f.dispatch.dispose_client(Phase::inactive, offender, f.clients[offender], true);
                    need(result.has_value() && calls == count + 1, "genuine producer restores valid disposal");
                    receipt(*result, f, offender, target);
                    need(before.unchanged(f) && bytes(f.registry) == registry_before,
                         "success preserves peer authority and registry");
                    need(probe.mint() == stamp + 1, "successful disposal consumes no global generation");
                    need(f.dispatch.state(offender) == State::idle && !f.dispatch.transaction(offender) &&
                             !f.dispatch.endpoint(offender, f.clients[offender]) &&
                             !f.dispatch.endpoint(offender, f.service),
                         "success revokes only offender grants and clears only offender transaction");
                    deny(f, probe, action, good, false);
                    // Exercise the peer after the offender is gone, observing copied request
                    // words and terminal receipt words that accessors alone cannot expose.
                    auto final_peer = peer;
                    if (peer == Path::pending || peer == Path::delivered) {
                        if (peer == Path::pending)
                            f.select(1 - offender);
                        f.reply(1 - offender);
                        final_peer = Path::replied;
                    }
                    const auto peer_result =
                        f.dispatch.dispose_client(Phase::inactive, 1 - offender, f.clients[1 - offender], true);
                    need(peer_result.has_value(), "peer remains recoverable after offender removal");
                    receipt(*peer_result, f, 1 - offender, final_peer);
                    receipt(*result, f, offender, target);
                    ++successful;
                }
}
auto authority_controls() -> void {
    StampProbe probe;
    for (const auto target : targets) {
        Fixture f;
        f.prepare(0, target);
        DomainRegistry foreign;
        const auto outsider = *foreign.create();
        const auto good = plan(target);
        for (const auto phase : {Phase::request, Phase::service, Phase::completion})
            deny(
                f,
                probe,
                [&] {
                    return f.dispatch.dispose_client(phase, 0, f.clients[0], true).has_value();
                },
                good,
                false);
        for (const auto slot : {std::size_t{2}, std::numeric_limits<std::size_t>::max()})
            deny(
                f,
                probe,
                [&] {
                    return f.dispatch.dispose_client(Phase::inactive, slot, f.clients[0], true).has_value();
                },
                good,
                false);
        for (const auto offender : {DomainHandle{}, f.clients[1], f.service, outsider})
            deny(
                f,
                probe,
                [&] {
                    return f.dispatch.dispose_client(Phase::inactive, 0, offender, true).has_value();
                },
                good,
                false);
        deny(
            f,
            probe,
            [&] {
                return f.dispatch.dispose_client(Phase::inactive, 0, f.clients[0], false).has_value();
            },
            good,
            false);
        for (const auto actor : {f.clients[0], f.clients[1], f.service}) {
            need(f.registry.activate(actor), "active-domain authority fixture");
            deny(
                f,
                probe,
                [&] {
                    return f.dispatch.dispose_client(Phase::inactive, 0, f.clients[0], true).has_value();
                },
                good,
                false);
            need(f.registry.deactivate(actor), "restore inactive authority fixture");
        }
    }
    for (const bool retire_service : {false, true}) {
        Fixture f;
        f.submit(0);
        const auto dead = retire_service ? f.service : f.clients[0];
        need(f.registry.destroy(dead), "retire bound authority");
        const auto fresh = *f.registry.create();
        for (const auto offender : {f.clients[0], fresh})
            deny(
                f,
                probe,
                [&] {
                    return f.dispatch.dispose_client(Phase::inactive, 0, offender, true).has_value();
                },
                0x0302,
                false);
    }
    for (const auto target : {Path::delivered, Path::replied, Path::cancelled}) {
        Fixture f;
        f.prepare(0, Path::delivered);
        if (target == Path::replied)
            need(f.dispatch.reply(f.service, Phase::service, f.service_caps[0], f.transactions[0], f.answer),
                 "selected reply fixture");
        if (target == Path::cancelled)
            need(f.dispatch.cancel_pending(Phase::inactive) == 1, "selected cancellation fixture");
        deny(
            f,
            probe,
            [&] {
                return f.dispatch.dispose_client(Phase::inactive, 0, f.clients[0], true).has_value();
            },
            plan(target),
            false);
    }
    Fixture unbound;
    need(unbound.dispatch.revoke(Phase::inactive), "unbound dispatcher fixture");
    deny(
        unbound,
        probe,
        [&] {
            return unbound.dispatch.dispose_client(Phase::inactive, 0, unbound.clients[0], true).has_value();
        },
        0x0102,
        false);
}
} // namespace
auto main() -> int {
    producer_controls();
    authority_controls();
    std::printf(
        "PASS: %llu malformed/refused disposal controls, %llu authority-before-producer controls, "
        "%llu genuine disposal/peer lifecycle cases; complete dispatcher/registry bytes and global generations\n",
        static_cast<unsigned long long>(substituted),
        static_cast<unsigned long long>(early_refusals),
        static_cast<unsigned long long>(successful));
}
