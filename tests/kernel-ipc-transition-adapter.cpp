// Host-only hostile producer: link the full generated root with ONLY the IPC
// producer renamed. Every call still reaches Aurora; queued output replacements
// are the only substitutions, and Dispatcher always uses genuine round-robin.
#include "../kernel/dispatch-policy.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <initializer_list>
#include <limits>
#include <optional>

auto genuine(std::uint64_t operation, std::uint64_t phase, std::uint64_t state, std::uint64_t scrubbed)
    -> std::uint64_t asm("aurora_kernel_ipc_transition_real");

namespace {
using namespace aurora::ipc;
using aurora::user::DomainHandle;
using aurora::user::DomainRegistry;
constexpr std::uint64_t high = std::uint64_t{1} << 63;
constexpr std::uint64_t maximum = std::numeric_limits<std::uint64_t>::max();
auto need(bool good, const char* reason) -> void {
    if (!good) { std::fprintf(stderr, "FAIL: %s\n", reason); std::abort(); }
}
template<class T> auto bytes(const T& value) -> std::array<unsigned char, sizeof(T)> {
    std::array<unsigned char, sizeof(T)> result{};
    std::memcpy(result.data(), &value, result.size());
    return result;
}
class Step final {
public:
    std::uint64_t operation{};
    std::optional<std::uint64_t> replacement{};
    std::function<void()> at_boundary{};
};
std::array<Step, 4> queue{};
std::size_t queued{}, taken{};
std::uint64_t calls{}, denied_calls{}, authority_denials{}, composite_cases{};
std::array<std::uint64_t, 4> last_input{};
auto arm(std::initializer_list<Step> steps) -> void {
    need(taken == queued, "previous substitution queue fully consumed");
    need(steps.size() <= queue.size(), "bounded substitution queue");
    queued = steps.size(); taken = 0;
    std::size_t index = 0;
    for (const auto& step : steps) queue[index++] = step;
}
auto clear_uninvoked() -> void {
    need(taken == 0, "authority refusal cannot invoke producer");
    queued = taken = 0;
}
auto drained() -> void { need(taken == queued, "all intentional producer controls invoked"); }
}
namespace aurora::ipc {
auto language_ipc_transition(std::uint64_t operation, std::uint64_t phase,
                             std::uint64_t state, std::uint64_t scrubbed) -> std::uint64_t {
    ++calls; last_input = {operation, phase, state, scrubbed};
    const auto real = genuine(operation, phase, state, scrubbed);
    if (taken == queued) return real;
    const auto& step = queue[taken++];
    need(step.operation == operation, "queued substitution reached intended operation");
    if (step.at_boundary) step.at_boundary();
    return step.replacement.value_or(real);
}
}
namespace {
// Observing the next legitimate bind proves global stamp conservation. No
// private sequence, reset, seed, friend or test-only authority hook is exposed.
auto mint_probe(const DomainRegistry& registry, DomainHandle client, DomainHandle service) -> std::uint64_t {
    Mailbox observer{registry};
    need(observer.bind(client, service), "legitimate generation observation bind");
    return observer.endpoint(client)->generation();
}
class Fixture final {
public:
    DomainRegistry registry;
    DomainHandle client = *registry.create(), other = *registry.create(), service = *registry.create();
    Mailbox target{registry}, peer{registry};
    Endpoint client_cap{}, service_cap{};
    std::uint64_t transaction{};
    Request request;
    std::uint64_t answer;
    explicit Fixture(std::uint64_t first = high, std::uint64_t second = maximum, std::uint64_t reply = maximum)
        : request(first, second), answer(reply) {
        need(target.bind(client, service) && peer.bind(other, service), "bind target and peer");
        client_cap = *target.endpoint(client); service_cap = *target.endpoint(service);
        need(peer.submit(other, Phase::request, *peer.endpoint(other), Request{maximum, high}).has_value(), "pending peer setup");
    }
    auto submit() -> void {
        const auto result = target.submit(client, Phase::request, client_cap, request);
        need(result.has_value(), "genuine submit"); transaction = *result;
    }
    auto receive() -> Request {
        const auto result = target.receive(service, Phase::service, service_cap, transaction);
        need(result.has_value(), "genuine receive");
        need(result->first() == request.first() && result->second() == request.second(), "full-width request survives exact copy");
        return *result;
    }
    auto reply() -> void { need(target.reply(service, Phase::service, service_cap, transaction, answer), "genuine reply"); }
    auto consume(Outcome outcome) -> Completion {
        const auto result = target.consume(client, Phase::completion, client_cap, transaction);
        need(result.has_value() && result->outcome() == outcome, "genuine exact terminal outcome");
        need(result->value() == (outcome == Outcome::replied ? answer : 0), "full-width reply/cancelled value");
        return *result;
    }
};
enum class Path { submit, receive, reply, consume_reply, consume_cancelled, cancel_pending, cancel_delivered, recycle };
constexpr std::array paths{Path::submit, Path::receive, Path::reply, Path::consume_reply,
                          Path::consume_cancelled, Path::cancel_pending, Path::cancel_delivered, Path::recycle};
auto operation(Path path) -> std::uint64_t {
    constexpr std::array<std::uint64_t, 8> result{0,1,2,3,3,4,4,5};
    return result[static_cast<unsigned>(path)];
}
auto canonical(Path path) -> std::uint64_t {
    constexpr std::array<std::uint64_t, 8> result{0x010102,0x020202,0x030302,0x040502,0x050502,0x060402,0x060402,0x070002};
    return result[static_cast<unsigned>(path)];
}
auto prepare(Fixture& fixture, Path path) -> void {
    if (path == Path::submit) return;
    fixture.submit();
    if (path == Path::receive || path == Path::cancel_pending) return;
    if (path == Path::consume_cancelled) {
        need(fixture.target.cancel(Phase::inactive), "cancelled consumption setup"); return;
    }
    (void)fixture.receive();
    if (path == Path::reply || path == Path::cancel_delivered) return;
    fixture.reply();
    if (path == Path::recycle) (void)fixture.consume(Outcome::replied);
}
auto invoke(Fixture& f, Path path) -> bool {
    switch (path) {
    case Path::submit: return f.target.submit(f.client, Phase::request, f.client_cap, f.request).has_value();
    case Path::receive: return f.target.receive(f.service, Phase::service, f.service_cap, f.transaction).has_value();
    case Path::reply: return f.target.reply(f.service, Phase::service, f.service_cap, f.transaction, f.answer);
    case Path::consume_reply:
    case Path::consume_cancelled: return f.target.consume(f.client, Phase::completion, f.client_cap, f.transaction).has_value();
    case Path::cancel_pending:
    case Path::cancel_delivered: return f.target.cancel(Phase::inactive);
    case Path::recycle: return f.target.recycle(Phase::inactive);
    }
    std::abort();
}
template<class Action> auto refuse(Fixture& fixture, Action action, std::uint64_t op,
                                  std::uint64_t word, bool reaches_policy = true) -> void {
    const auto generation = mint_probe(fixture.registry, fixture.client, fixture.service);
    const auto before = bytes(fixture.target), peer_before = bytes(fixture.peer);
    const auto count = calls;
    arm({Step{op, word, {}}});
    need(!action(), "refused or malformed Mailbox call cannot succeed");
    need(calls == count + (reaches_policy ? 1U : 0U), "authority checks precede producer invocation");
    if (reaches_policy) { drained(); ++denied_calls; }
    else { clear_uninvoked(); ++authority_denials; }
    need(bytes(fixture.target) == before && bytes(fixture.peer) == peer_before, "each denied call preserves every target and peer byte");
    need(mint_probe(fixture.registry, fixture.client, fixture.service) == generation + 1, "denial does not consume global generation");
    need(bytes(fixture.target) == before && bytes(fixture.peer) == peer_before, "generation observation cannot mutate target or peer");
}
auto substituted_success_paths() -> void {
    for (const auto first : {std::uint64_t{0}, high, maximum})
    for (const auto second : {std::uint64_t{0}, high, maximum})
    for (const auto answer : {std::uint64_t{0}, high, maximum})
    for (const auto path : paths) {
        Fixture fixture{first, second, answer}; prepare(fixture, path);
        const auto good = canonical(path);
        const auto before_state = fixture.target.state();
        const auto before_scrubbed = fixture.target.scrubbed();
        for (const auto word : {std::uint64_t{1}, std::uint64_t{0}, good | high, good ^ 0x100U,
                              good ^ 0x10000U, good | 1U, std::uint64_t{2}, maximum}) {
            refuse(fixture, [&] { return invoke(fixture, path); }, operation(path), word);
            constexpr std::array<std::uint64_t, 8> phases{1,2,2,3,3,0,0,0};
            need(last_input == std::array<std::uint64_t, 4>{operation(path), phases[static_cast<unsigned>(path)],
                static_cast<std::uint64_t>(before_state), before_scrubbed ? 1U : 0U}, "producer sees actual copied phase/state/scrubbed only");
        }
        const auto peer_before = bytes(fixture.peer);
        need(invoke(fixture, path), "genuine producer succeeds after every substitution removed");
        need(bytes(fixture.peer) == peer_before, "genuine target transition preserves peer");
    }
}
auto payload_and_first_terminal() -> void {
    for (const auto first : {std::uint64_t{0}, high, maximum})
    for (const auto second : {std::uint64_t{0}, high, maximum})
    for (const auto answer : {std::uint64_t{0}, high, maximum}) {
        Fixture f{first, second, answer}; f.submit();
        need(f.target.scrubbed() == (first == 0 && second == 0), "all-zero request remains a pending request");
        const auto copied_request = f.receive(); f.reply();
        const auto before = bytes(f.target), peer_before = bytes(f.peer);
        need(!f.target.cancel(Phase::inactive), "reply cannot be overwritten by cancel");
        need(!f.target.reply(f.service, Phase::service, f.service_cap, f.transaction, ~answer), "first reply wins");
        need(bytes(f.target) == before && bytes(f.peer) == peer_before, "terminal refusal preserves all bytes");
        const auto copied_completion = f.consume(Outcome::replied);
        const auto consumed = bytes(f.target);
        need(!f.target.consume(f.client, Phase::completion, f.client_cap, f.transaction), "cannot consume reply twice");
        need(bytes(f.target) == consumed, "second consume byte preservation");
        need(f.target.recycle(Phase::inactive), "genuine recycle");
        need(copied_request.first() == first && copied_request.second() == second && copied_completion.value() == answer,
             "independent payload copies survive scrub and recycle");
        f.submit(); need(f.target.cancel(Phase::inactive), "genuine first cancellation");
        const auto cancelled = bytes(f.target);
        need(!f.target.receive(f.service, Phase::service, f.service_cap, f.transaction), "cancelled request cannot deliver");
        need(!f.target.reply(f.service, Phase::service, f.service_cap, f.transaction, answer), "cancelled request cannot reply");
        need(bytes(f.target) == cancelled, "cancelled terminal bytes retained");
        (void)f.consume(Outcome::cancelled);
    }
}
auto authority_gates() -> void {
    for (const auto path : {Path::submit, Path::receive, Path::reply, Path::consume_reply, Path::consume_cancelled}) {
        Fixture f; prepare(f, path);
        DomainRegistry foreign; const auto outsider = *foreign.create();
        const auto op = operation(path), good = canonical(path);
        auto call = [&](DomainHandle caller, Endpoint cap, std::uint64_t transaction) {
            switch (path) {
            case Path::submit: return f.target.submit(caller, Phase::request, cap, f.request).has_value();
            case Path::receive: return f.target.receive(caller, Phase::service, cap, transaction).has_value();
            case Path::reply: return f.target.reply(caller, Phase::service, cap, transaction, f.answer);
            default: return f.target.consume(caller, Phase::completion, cap, transaction).has_value();
            }
        };
        const bool service_action = path == Path::receive || path == Path::reply;
        const auto owner = service_action ? f.service : f.client;
        const auto proper = service_action ? f.service_cap : f.client_cap;
        const auto wrong_right = service_action ? f.client_cap : f.service_cap;
        for (const auto caller : {DomainHandle{}, f.other, outsider, service_action ? f.client : f.service})
            refuse(f, [&] { return call(caller, proper, f.transaction); }, op, good, false);
        for (const auto cap : {Endpoint{}, Endpoint{maximum, proper.generation()}, Endpoint{proper.slot(), 0},
                              Endpoint{proper.slot(), proper.generation() + 1}, wrong_right})
            refuse(f, [&] { return call(owner, cap, f.transaction); }, op, good, false);
        if (path != Path::submit)
            for (const auto transaction : {std::uint64_t{0}, f.transaction + 1, high, maximum})
                refuse(f, [&] { return call(owner, proper, transaction); }, op, good, false);
    }
}
auto generation_ceiling() -> void {
    DomainRegistry registry;
    const auto client = *registry.create(), other = *registry.create(), service = *registry.create();
    const auto epoch = mint_probe(registry, client, service);
    Mailbox limited{registry, epoch + 1}, peer{registry};
    need(limited.bind(client, service), "last available bounded endpoint stamp");
    need(peer.bind(other, service), "independent peer binding");
    need(peer.submit(other, Phase::request, *peer.endpoint(other), Request{high, maximum}).has_value(), "generation-exhaustion pending peer");
    const auto stamp = mint_probe(registry, client, service);
    const auto before = bytes(limited), peer_before = bytes(peer);
    const auto registry_before = bytes(registry);
    const auto count = calls;
    need(!limited.submit(client, Phase::request, *limited.endpoint(client), Request{0, maximum}), "accepted policy cannot bypass global generation ceiling");
    need(calls == count + 1, "submit checks real producer before attempted mint");
    need(bytes(limited) == before && bytes(peer) == peer_before && bytes(registry) == registry_before,
         "failed mint preserves complete target/peer and registry");
    need(mint_probe(registry, client, service) == stamp + 1, "failed bounded mint cannot burn global stamp");
}

auto liveness_and_delivered_prefix() -> void {
    // All probes in this test use a separate live observer registry, since the
    // actual bound participants intentionally cease to be live.
    DomainRegistry observers; const auto observer_client = *observers.create(), observer_service = *observers.create();
    for (const auto path : {Path::submit, Path::receive, Path::reply, Path::consume_reply, Path::consume_cancelled}) {
        Fixture f; prepare(f, path);
        const bool service_action = path == Path::receive || path == Path::reply;
        need(f.registry.destroy(service_action ? f.service : f.client), "retire actual operation owner");
        const auto replacement = *f.registry.create();
        need(f.registry.ready(replacement), "same-slot replacement is live");
        const auto before = bytes(f.target), peer_before = bytes(f.peer);
        const auto stamp = mint_probe(observers, observer_client, observer_service), count = calls;
        arm({Step{operation(path), canonical(path), {}}});
        need(!invoke(f, path) && calls == count, "stale caller rejected before producer even after same-slot rebirth");
        clear_uninvoked();
        need(bytes(f.target) == before && bytes(f.peer) == peer_before, "stale caller preserves complete object bytes");
        need(mint_probe(observers, observer_client, observer_service) == stamp + 1, "stale caller preserves global generation");
    }
    for (const bool delivered : {false, true}) {
        Fixture f; f.submit(); if (delivered) (void)f.receive();
        need(f.registry.destroy(f.service), "retire service");
        const auto replacement = *f.registry.create();
        need(f.registry.ready(replacement) && !f.registry.index(f.service), "new service cannot resurrect old identity");
        const auto stamp = mint_probe(observers, observer_client, observer_service);
        const auto before = bytes(f.target), peer_before = bytes(f.peer);
        const auto count = calls;
        arm({Step{delivered ? 2U : 1U, delivered ? 0x030302U : 0x020202U, {}}});
        if (delivered) need(!f.target.reply(replacement, Phase::service, f.service_cap, f.transaction, maximum), "replacement service stale grant denied");
        else need(!f.target.receive(replacement, Phase::service, f.service_cap, f.transaction), "replacement service stale receive denied");
        need(calls == count, "dead service authority failure precedes producer"); clear_uninvoked();
        need(bytes(f.target) == before && bytes(f.peer) == peer_before, "dead service refusal preserves target and peer");
        need(mint_probe(observers, observer_client, observer_service) == stamp + 1, "dead service refusal preserves generation");
        need(f.target.cancel(Phase::inactive), "trusted cancellation can outlive service");
        for (const auto word : {std::uint64_t{1}, high | 0x050502U}) {
            const auto cancelled = bytes(f.target), peer = bytes(f.peer);
            const auto generation = mint_probe(observers, observer_client, observer_service);
            arm({Step{3, word, {}}});
            need(!f.target.consume(f.client, Phase::completion, f.client_cap, f.transaction), "denied consume after accepted pending/delivered cancellation");
            drained(); need(bytes(f.target) == cancelled && bytes(f.peer) == peer, "accepted cancellation remains exact committed prefix");
            need(mint_probe(observers, observer_client, observer_service) == generation + 1, "cancel-prefix denied consumption preserves stamp");
        }
        (void)f.consume(Outcome::cancelled);
    }
    for (const bool cancelled : {false, true}) {
        Fixture f; f.submit(); (void)f.receive();
        if (cancelled) need(f.target.cancel(Phase::inactive), "dead-client cancelled setup"); else f.reply();
        need(f.registry.destroy(cancelled ? f.client : f.service), "retire required completion participant");
        const auto before = bytes(f.target), peer = bytes(f.peer);
        const auto count = calls;
        const auto generation = mint_probe(observers, observer_client, observer_service);
        arm({Step{3, cancelled ? 0x050502U : 0x040502U, {}}});
        need(!f.target.consume(f.client, Phase::completion, f.client_cap, f.transaction), "dead client or replied dead-service completion denied");
        need(calls == count, "completion liveness gate precedes producer"); clear_uninvoked();
        need(bytes(f.target) == before && bytes(f.peer) == peer, "completion liveness refusal byte preservation");
        need(mint_probe(observers, observer_client, observer_service) == generation + 1, "completion liveness refusal generation preservation");
    }
}
class DispatchFixture final {
public:
    DomainRegistry registry;
    std::array<DomainHandle, 2> clients{*registry.create(), *registry.create()};
    DomainHandle service = *registry.create();
    Dispatcher dispatch{registry};
    std::array<Endpoint, 2> client_caps{}, service_caps{};
    std::array<std::uint64_t, 2> transactions{};
    DispatchFixture() {
        need(dispatch.bind(clients, service), "dispatcher bind");
        for (std::size_t index = 0; index < 2; ++index) {
            client_caps[index] = *dispatch.endpoint(index, clients[index]);
            service_caps[index] = *dispatch.endpoint(index, service);
        }
    }
    auto submit(std::size_t index) -> void {
        const auto transaction = dispatch.submit(clients[index], Phase::request, client_caps[index], Request{high + index, maximum - index});
        need(transaction.has_value(), "dispatcher genuine submit"); transactions[index] = *transaction;
    }
    auto probe() const -> std::uint64_t { return mint_probe(registry, clients[0], service); }
};
auto disposition_prefix() -> void {
    for (const std::size_t offender : {0U, 1U})
    for (const auto word : {std::uint64_t{1}, high | 0x050502U}) {
        DispatchFixture f; f.submit(0); f.submit(1);
        const auto cursor = f.dispatch.next_client();
        const auto prior_generation = f.probe();
        const auto registry_before = bytes(f.registry);
        std::array<unsigned char, sizeof(Dispatcher)> at_consume{};
        const auto count = calls;
        arm({Step{4, std::nullopt, {}}, Step{3, word, [&] { at_consume = bytes(f.dispatch); }}});
        need(!f.dispatch.dispose_client(Phase::inactive, offender, f.clients[offender], true), "denied consume prevents disposal receipt");
        drained(); need(calls == count + 2, "dispose accepted cancel then denied consume");
        need(bytes(f.dispatch) == at_consume, "no post-denial dispatcher mutation, revoke or transaction clear");
        need(bytes(f.registry) == registry_before, "no domain retirement without disposition");
        need(f.dispatch.state(offender) == State::cancelled && f.dispatch.state(1 - offender) == State::pending,
             "cancelled committed prefix and pending peer preserved");
        need(f.dispatch.next_client() == cursor && !f.dispatch.selected(), "dispose denial preserves cursor and selection");
        for (std::size_t index = 0; index < 2; ++index) {
            need(f.dispatch.transaction(index) == f.transactions[index], "dispose denial preserves both exact transactions");
            need(f.dispatch.endpoint(index, f.clients[index])->generation() == f.client_caps[index].generation()
                && f.dispatch.endpoint(index, f.service)->generation() == f.service_caps[index].generation(), "dispose denial cannot revoke grants");
        }
        need(!f.dispatch.rebind_client(Phase::inactive, offender, f.clients[offender]), "denied disposition cannot permit rebind");
        need(f.probe() == prior_generation + 1, "disposal committed prefix does not burn generation");
        // A retry starts from CANCELLED, never an invented pre-cancel receipt.
        const auto receipt = f.dispatch.dispose_client(Phase::inactive, offender, f.clients[offender], true);
        need(receipt && receipt->prior_state() == State::cancelled && receipt->transaction() == f.transactions[offender]
             && receipt->completion()->outcome() == Outcome::cancelled, "retry reports actual committed prefix");
        ++composite_cases;
    }
    // Delivered + unselected cannot be constructed through Dispatcher APIs:
    // select sets selected_; finish_selected requires terminal state. Preserve
    // that boundary rather than forge private state to reach impossible input.
    DispatchFixture f; f.submit(0); f.submit(1);
    const auto work = f.dispatch.select(Phase::inactive); need(work && work->client() == 0, "real round-robin delivers selected offender");
    const auto before = bytes(f.dispatch);
    const auto count = calls, generation = f.probe();
    need(!f.dispatch.dispose_client(Phase::inactive, 0, f.clients[0], true), "delivered selected offender cannot be disposed");
    need(bytes(f.dispatch) == before && calls == count && f.probe() == generation + 1, "selected disposal is unchanged early refusal");
}
auto cancel_composites() -> void {
    for (const bool selected : {false, true})
    for (const std::size_t accepted_index : {0U, 1U})
    for (const auto word : {std::uint64_t{1}, high | 0x060402U}) {
        DispatchFixture f; f.submit(0); f.submit(1);
        if (selected) need(f.dispatch.select(Phase::inactive).has_value(), "selected delivered cancellation setup");
        const auto selected_before = f.dispatch.selected();
        const auto cursor = f.dispatch.next_client();
        const auto before = bytes(f.dispatch);
        const auto generation = f.probe();
        std::array<unsigned char, sizeof(Dispatcher)> at_refusal{}, after_refusal{};
        const auto count = calls;
        if (accepted_index == 0) {
            arm({Step{4, std::nullopt, {}}, Step{4, word, [&] { at_refusal = bytes(f.dispatch); }}});
        } else {
            arm({Step{4, word, [&] { at_refusal = bytes(f.dispatch); }},
                 Step{4, std::nullopt, [&] { after_refusal = bytes(f.dispatch); }}});
        }
        need(f.dispatch.cancel_pending(Phase::inactive) == 1, "cancel_pending counts exactly one accepted cancellation");
        drained(); need(calls == count + 2, "cancel_pending visits both mailboxes");
        if (accepted_index == 0) need(bytes(f.dispatch) == at_refusal, "last refused cancel changes no dispatcher byte");
        else need(at_refusal == before && after_refusal == before, "first refused cancel changes no byte before peer success");
        need(f.dispatch.state(accepted_index) == State::cancelled, "accepted peer cancellation remains committed");
        need(f.dispatch.state(1 - accepted_index) == (selected && accepted_index == 1 ? State::delivered : State::pending),
             "refused mailbox retains original pending/delivered state");
        need(f.dispatch.selected() == selected_before && f.dispatch.next_client() == cursor, "partial cancellations preserve cursor/selection");
        for (std::size_t index = 0; index < 2; ++index)
            need(f.dispatch.transaction(index) == f.transactions[index]
                && f.dispatch.endpoint(index, f.clients[index])->generation() == f.client_caps[index].generation()
                && f.dispatch.endpoint(index, f.service)->generation() == f.service_caps[index].generation(), "partial cancellation preserves transaction and grant authority");
        need(f.probe() == generation + 1, "partial cancellation preserves global generation");
        if (selected && accepted_index == 0) {
            need(f.dispatch.finish_selected(Phase::inactive, true), "terminal delivered cancellation releases selection after quiescence");
            const auto cancelled = bytes(f.dispatch);
            const auto stamp = f.probe();
            arm({Step{3, word == 1 ? 1 : high | 0x050502U, {}}});
            need(!f.dispatch.consume(f.clients[0], Phase::completion, f.client_caps[0], f.transactions[0]), "delivered cancellation prefix then denied consume");
            drained(); need(bytes(f.dispatch) == cancelled && f.probe() == stamp + 1, "delivered composite prefix retains all state on consume denial");
        }
        ++composite_cases;
    }
}
auto select_refusals() -> void {
    for (const auto word : {std::uint64_t{1}, high | 0x020202U}) {
        DispatchFixture f; f.submit(0); f.submit(1);
        for (unsigned cursor = 0; cursor < 2; ++cursor) {
            const auto before = bytes(f.dispatch);
            const auto generation = f.probe(), count = calls;
            arm({Step{1, word, {}}});
            need(!f.dispatch.select(Phase::inactive), "genuine round-robin followed denied receive has no work");
            drained(); need(calls == count + 1 && bytes(f.dispatch) == before, "denied selection preserves whole dispatcher object");
            need(f.probe() == generation + 1, "denied selection does not burn generation");
            const auto work = f.dispatch.select(Phase::inactive);
            need(work && work->client() == cursor, "real round-robin cursor unchanged by denied receive");
            need(f.dispatch.reply(f.service, Phase::service, work->service_endpoint(), work->transaction(), maximum), "complete real selection");
            need(f.dispatch.finish_selected(Phase::inactive, true), "finish real selection");
            need(f.dispatch.consume(f.clients[cursor], Phase::completion, f.client_caps[cursor], f.transactions[cursor]).has_value(), "consume real selection");
            need(f.dispatch.recycle(Phase::inactive, cursor), "recycle selected client"); f.submit(cursor);
            ++composite_cases;
        }
    }
}
}
auto main() -> int {
    substituted_success_paths();
    payload_and_first_terminal();
    authority_gates();
    generation_ceiling();
    liveness_and_delivered_prefix();
    disposition_prefix();
    cancel_composites();
    select_refusals();
    drained();
    std::printf("PASS: %llu refused/malformed successful-path controls, %llu authority-before-producer controls, %llu composite controls; genuine Aurora and round-robin, exact payloads, target/peer bytes and global stamps\n",
        static_cast<unsigned long long>(denied_calls), static_cast<unsigned long long>(authority_denials),
        static_cast<unsigned long long>(composite_cases));
}
