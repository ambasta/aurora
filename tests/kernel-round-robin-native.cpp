// Host-only observation of the real Aurora round-robin policy and the real C++
// decoder over fixed full-width vector families; compared with
// tests/kernel-round-robin-native.golden. No host I/O is linked into the kernel.
#include "../kernel/round-robin-transport.hpp"
#include "policy-vectors.hpp"
#include <cstdlib>

namespace kernel_round_robin_native {
using namespace policy_vectors;

namespace {
auto policy(Family &family, U64 cursor, U64 mask) -> void {
    const auto result = aurora::ipc::language_round_robin_next(cursor, mask);
    // Every nonzero word the policy produces must decode in its own context.
    if (result != 0 && !aurora::ipc::RoundRobinSelection::decode(result, cursor, mask))
        std::exit(4);
    family.observe({cursor, mask}, {result});
}
auto decoder(Family &family, U64 word, U64 cursor, U64 mask) -> void {
    U64 result{};
    if (const auto selected = aurora::ipc::RoundRobinSelection::decode(word, cursor, mask))
        result = (selected->selected() ? 2ULL : 1ULL) | (U64{selected->client()} << 8) | (U64{selected->next()} << 16);
    family.observe({word, cursor, mask}, {result});
}
} // namespace

auto main() -> int {
    {
        Family family("policy-table", Rows::all);
        for (U64 cursor = 0; cursor < 2; ++cursor)
            for (U64 mask = 0; mask < 4; ++mask)
                policy(family, cursor, mask);
    }
    {
        Family family("policy-edges");
        const U64 values[] = {0, 1, 2, 3, 4, 7, 15, 127, 128, 255, 256, (U64{1} << 32) - 1, U64{1} << 32,
                              (U64{1} << 63) - 1, U64{1} << 63, maximum};
        for (const auto cursor : values)
            for (const auto mask : values)
                policy(family, cursor, mask);
        for (unsigned bit = 0; bit < 64; ++bit)
            for (U64 cursor = 0; cursor < 2; ++cursor)
                for (U64 mask = 0; mask < 4; ++mask) {
                    policy(family, cursor ^ (U64{1} << bit), mask);
                    policy(family, cursor, mask ^ (U64{1} << bit));
                }
    }
    {
        Family family("policy-random");
        Random random(20261005);
        for (unsigned i = 0; i < 16384; ++i) {
            const auto cursor = random();
            policy(family, cursor, random());
        }
    }
    {
        // Every word below the highest allocated transport bit in each context.
        Family family("decoder-compact");
        for (U64 cursor = 0; cursor < 2; ++cursor)
            for (U64 mask = 0; mask < 4; ++mask)
                for (U64 word = 0; word < (U64{1} << 17); ++word)
                    decoder(family, word, cursor, mask);
    }
    {
        Family family("decoder-mutations");
        for (U64 cursor = 0; cursor < 2; ++cursor)
            for (U64 mask = 0; mask < 4; ++mask)
                for (const U64 word : {U64{1}, U64{0x10001}, U64{0x10002}, U64{0x102}})
                    for (unsigned bit = 0; bit < 64; ++bit)
                        decoder(family, word ^ (U64{1} << bit), cursor, mask);
        const U64 contexts[] = {0, 1, 2, 3, 4, U64{1} << 63, maximum};
        for (const auto cursor : contexts)
            for (const auto mask : contexts)
                for (const U64 word : {U64{0}, U64{1}, U64{2}, U64{0x10001}, U64{0x10002}, U64{0x102}, U64{1} << 63,
                                       maximum})
                    decoder(family, word, cursor, mask);
    }
    return 0;
}
} // namespace kernel_round_robin_native
