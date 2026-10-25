// Host-only observation adapter. No host I/O implementation is linked into the
// kernel; the real Aurora object and real C++ transport decoder are linked here.
// Fixed full-width vector families are compared with tests/kernel-budget-native.golden.
#include "../kernel/uefi/budget-transport.hpp"
#include "policy-vectors.hpp"
#include <array>
#include <cstdio>
#include <cstring>
#include <limits>

namespace kernel_budget_native {
namespace {
// The guest policy faults change only copied first-tick inputs or the returned
// word. Decode against the untouched trusted context, not those invalid copies.
// Real interrupt delivery, CPL3 context and timer cleanup remain guest tests.
auto copied_first_tick_faults() -> bool {
    constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
    for (const std::uint64_t initial : {3U, 128U}) {
        const auto genuine = aurora::uefi::language_budget_tick(initial, initial, 0);
        if (!aurora::uefi::BudgetTransition::decode(genuine, initial, initial, 0))
            return false;
        const std::array invalid_inputs{aurora::uefi::language_budget_tick(0, initial, 0),
                                        aurora::uefi::language_budget_tick(initial, initial, 1),
                                        aurora::uefi::language_budget_tick(initial, maximum, maximum)};
        for (const auto encoded : invalid_inputs)
            if (encoded != 0 || aurora::uefi::BudgetTransition::decode(encoded, initial, initial, 0))
                return false;
        if (aurora::uefi::BudgetTransition::decode(genuine | (std::uint64_t{1} << 63), initial, initial, 0))
            return false;
    }
    return true;
}
} // namespace

using namespace policy_vectors;

namespace {
auto policy(Family &family, U64 initial, U64 remaining, U64 used) -> void {
    const auto result = aurora::uefi::language_budget_tick(initial, remaining, used);
    // Every nonzero word the policy produces must decode in its own context.
    if (result != 0 && !aurora::uefi::BudgetTransition::decode(result, initial, remaining, used))
        std::exit(4);
    family.observe({initial, remaining, used}, {result});
}
auto decoder(Family &family, U64 encoded, U64 initial, U64 remaining, U64 used) -> void {
    U64 result{};
    if (const auto value = aurora::uefi::BudgetTransition::decode(encoded, initial, remaining, used))
        result = (U64{value->resume() ? 1U : 2U} << 16) | (U64{value->used()} << 8) | value->remaining();
    family.observe({encoded, initial, remaining, used}, {result});
}
} // namespace

int main() {
    if (!copied_first_tick_faults()) {
        std::fputs("FAIL: copied first-tick policy faults must reject against original context\n", stderr);
        return 7;
    }
    {
        // Every reachable state: initial in [1, 128], used below it, remaining conserved.
        Family family("policy-states");
        for (U64 initial = 1; initial <= 128; ++initial)
            for (U64 used = 0; used < initial; ++used)
                policy(family, initial, initial - used, used);
    }
    {
        Family family("policy-edges");
        const U64 values[] = {0, 1, 2, 3, 63, 64, 127, 128, 129, 255, 256, (U64{1} << 63) - 1, U64{1} << 63, maximum};
        for (const auto a : values)
            for (const auto b : values)
                for (const auto c : values)
                    policy(family, a, b, c);
    }
    {
        // Near-conserving and wide counts around every initial budget.
        Family family("policy-near");
        for (U64 initial = 1; initial <= 128; ++initial) {
            for (U64 remaining = 0; remaining < 131; ++remaining) {
                for (int offset = -2; offset <= 2; ++offset) {
                    const auto used = static_cast<std::int64_t>(initial) - static_cast<std::int64_t>(remaining) + offset;
                    if (used >= 0)
                        policy(family, initial, remaining, static_cast<U64>(used));
                }
                for (const U64 used : {U64{1} << 63, maximum})
                    policy(family, initial, remaining, used);
            }
            for (const U64 remaining : {U64{1} << 63, maximum})
                for (const U64 used : {U64{0}, U64{1}, initial - 1, initial, maximum})
                    policy(family, initial, remaining, used);
        }
    }
    {
        Family family("policy-random");
        Random random(20261004);
        for (unsigned i = 0; i < 16384; ++i) {
            const auto initial = random();
            const auto remaining = random();
            policy(family, initial, remaining, random());
        }
    }
    {
        // All 18-bit encodings against the only possible conserved total.
        Family family("decoder-compact");
        for (U64 encoded = 0; encoded < (U64{1} << 18); ++encoded) {
            const auto total = (encoded & 255) + ((encoded >> 8) & 255);
            decoder(family, encoded, total, total, 0);
        }
    }
    {
        // Every valid output and every one-bit mutation at every valid source state.
        Family family("decoder-states");
        for (U64 initial = 1; initial <= 128; ++initial)
            for (U64 used = 0; used < initial; ++used) {
                const auto remaining = initial - used;
                const auto word = aurora::uefi::language_budget_tick(initial, remaining, used);
                decoder(family, word, initial, remaining, used);
                for (unsigned bit = 0; bit < 64; ++bit)
                    decoder(family, word ^ (U64{1} << bit), initial, remaining, used);
                decoder(family, word, initial, remaining - 1, used);
                decoder(family, word, initial, remaining, used + 1);
            }
        const auto first = aurora::uefi::language_budget_tick(3, 3, 0);
        for (const U64 value : {U64{0}, U64{129}, U64{255}, U64{1} << 63, maximum})
            decoder(family, first, value, 3, 0);
    }
    return 0;
}
} // namespace kernel_budget_native
