// Mutation control for the actual Dispatcher adapter. This binary substitutes
// ONLY the scalar producer; production and ordinary hosted tests link Aurora.
#include "../kernel/dispatch-policy.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>

namespace {
std::uint64_t produced{}, observed_cursor{}, observed_mask{}, calls{};
auto need(bool value) -> void { if (!value) std::abort(); }
}
namespace aurora::ipc {
auto language_round_robin_next(std::uint64_t cursor, std::uint64_t mask) -> std::uint64_t {
    observed_cursor = cursor; observed_mask = mask; ++calls; return produced;
}
}
namespace {
using namespace aurora::ipc;
class Fixture final {
public:
    aurora::user::DomainRegistry registry;
    std::array<aurora::user::DomainHandle, 2> clients{*registry.create(), *registry.create()};
    aurora::user::DomainHandle service = *registry.create();
    Dispatcher dispatch{registry};
    Fixture(unsigned cursor, unsigned mask) {
        need(dispatch.bind(clients, service));
        if (cursor == 1) {
            need(dispatch.submit(clients[0], Phase::request, *dispatch.endpoint(0, clients[0]), Request{11, 12}).has_value());
            produced = 0x10002;
            const auto work = dispatch.select(Phase::inactive); need(work.has_value());
            need(dispatch.reply(service, Phase::service, work->service_endpoint(), work->transaction(), 23));
            need(dispatch.finish_selected(Phase::inactive, true));
            need(dispatch.consume(clients[0], Phase::completion, *dispatch.endpoint(0, clients[0]), work->transaction()).has_value());
            need(dispatch.recycle(Phase::inactive, 0));
        }
        for (unsigned client = 0; client < 2; ++client) if (mask & (1U << client))
            need(dispatch.submit(clients[client], Phase::request, *dispatch.endpoint(client, clients[client]), Request{40 + client, 2 + client}).has_value());
        need(dispatch.next_client() == cursor);
    }
};
auto allowed(std::uint64_t word, unsigned cursor, unsigned mask) -> bool {
    if (mask == 0) return word == (cursor == 0 ? 1U : 0x10001U);
    if (mask == 1) return word == 0x10002;
    if (mask == 2) return word == 0x102;
    return word == 0x10002 || word == 0x102;
}
auto rejected_word(std::uint64_t word, unsigned cursor, unsigned mask) -> void {
    if (allowed(word, cursor, mask)) return;
    Fixture fixture{cursor, mask};
    std::array<unsigned char, sizeof(Dispatcher)> before{}, after{};
    std::memcpy(before.data(), &fixture.dispatch, before.size());
    produced = word; calls = 0;
    need(!fixture.dispatch.select(Phase::inactive));
    std::memcpy(after.data(), &fixture.dispatch, after.size());
    need(calls == 1 && observed_cursor == cursor && observed_mask == mask && before == after);
}
}
auto main() -> int {
    std::uint64_t observations = 0;
    for (unsigned cursor = 0; cursor < 2; ++cursor) for (unsigned mask = 0; mask < 4; ++mask) {
        for (const auto word : {0ULL, 1ULL, 2ULL, 0x10001ULL, 0x10002ULL, 0x102ULL, 0xffffffffffffffffULL}) {
            rejected_word(word, cursor, mask); ++observations;
            for (unsigned bit = 0; bit < 64; ++bit) {
                rejected_word(word ^ (std::uint64_t{1} << bit), cursor, mask); ++observations;
            }
        }
        // Both eligible choices are authority-safe at mask3. This deliberate
        // mutation demonstrates that fairness is NOT duplicated by the decoder.
        if (mask == 3) for (const auto word : {0x10002ULL, 0x102ULL}) {
            Fixture fixture{cursor, mask}; produced = word; calls = 0;
            const auto work = fixture.dispatch.select(Phase::inactive);
            const auto chosen = word == 0x10002 ? 0U : 1U;
            need(work && work->client() == chosen && fixture.dispatch.selected() == chosen
                && fixture.dispatch.next_client() == 1 - chosen && calls == 1
                && work->request().first() == 40 + chosen && fixture.dispatch.queued() == 1);
        }
    }
    std::printf("PASS: %llu adapter output-mutation candidates; rejected outputs preserve every object byte; copied eligibility and authority-safe unfair choices checked\n", static_cast<unsigned long long>(observations));
}
