// Hosted full-width observation only: the linked Aurora root and production
// decoder are the subjects, over fixed full-width vector families compared with
// tests/kernel-client-disposal-native.golden.
#include "../kernel/client-disposal-transport.hpp"
#include "policy-vectors.hpp"
#include <cstdlib>

namespace kernel_client_disposal_native {
static_assert(aurora::ipc::DisposalTransition::decode(0x0102, 0, 0).accepted());
static_assert(!aurora::ipc::DisposalTransition::decode(0x0102, 0, 1).accepted());
static_assert(!aurora::ipc::DisposalTransition::decode(1, 4, 0).accepted());

using namespace policy_vectors;

namespace {
constexpr U64 edges[] = {0,
                         1,
                         2,
                         3,
                         4,
                         5,
                         6,
                         7,
                         8,
                         15,
                         127,
                         128,
                         255,
                         256,
                         65535,
                         65536,
                         (U64{1} << 32) - 1,
                         U64{1} << 32,
                         (U64{1} << 63) - 1,
                         U64{1} << 63,
                         maximum};
constexpr U64 words[] = {1, 0x0102, 0x0202, 0x0302, 0x0402};
auto policy(Family &family, U64 phase, U64 state) -> void {
    family.observe({phase, state}, {aurora::ipc::language_client_disposal(phase, state)});
}
auto decoder(Family &family, U64 word, U64 phase, U64 state) -> void {
    const auto result = aurora::ipc::DisposalTransition::decode(word, phase, state);
    U64 status{};
    switch (result.status()) {
    case aurora::ipc::DisposalStatus::malformed:
        status = 0;
        break;
    case aurora::ipc::DisposalStatus::refused:
        status = 1;
        break;
    case aurora::ipc::DisposalStatus::accepted:
        status = 2;
        break;
    default:
        std::exit(4);
    }
    if (result.accepted() != (status == 2))
        std::exit(5);
    family.observe({word, phase, state}, {status, static_cast<U64>(result.effect())});
}
} // namespace

auto main() -> int {
    {
        Family family("policy-table", Rows::all);
        for (U64 phase = 0; phase < 4; ++phase)
            for (U64 state = 0; state < 6; ++state)
                policy(family, phase, state);
    }
    {
        Family family("policy-fields");
        for (U64 phase = 0; phase < 4; ++phase)
            for (U64 state = 0; state < 6; ++state) {
                for (const auto value : edges)
                    policy(family, value, state);
                for (unsigned bit = 0; bit < 64; ++bit)
                    policy(family, phase ^ (U64{1} << bit), state);
                for (const auto value : edges)
                    policy(family, phase, value);
                for (unsigned bit = 0; bit < 64; ++bit)
                    policy(family, phase, state ^ (U64{1} << bit));
            }
        for (const auto phase : edges)
            for (const auto state : edges)
                policy(family, phase, state);
    }
    {
        Family family("policy-random");
        Random random(202610081);
        for (unsigned i = 0; i < 8192; ++i) {
            const auto phase = random();
            policy(family, phase, random());
        }
    }
    {
        Family family("decoder-compact");
        for (U64 phase = 0; phase < 4; ++phase)
            for (U64 state = 0; state < 6; ++state) {
                // All compact action/effect combinations in every finite context.
                for (U64 action = 0; action < 4; ++action)
                    for (U64 effect = 0; effect < 8; ++effect)
                        decoder(family, action | (effect << 8), phase, state);
                for (const auto word : words) {
                    for (unsigned bit = 0; bit < 64; ++bit)
                        decoder(family, word ^ (U64{1} << bit), phase, state);
                    // Every possible byte in each returned field, preserving its peer.
                    for (U64 byte = 0; byte < 256; ++byte) {
                        decoder(family, (word & ~U64{255}) | byte, phase, state);
                        decoder(family, (word & 255) | (byte << 8), phase, state);
                    }
                    // Nonzero unused upper fields can never be silently truncated.
                    for (const unsigned shift : {16U, 24U, 32U, 48U, 56U})
                        for (const U64 byte : {1, 127, 128, 255})
                            decoder(family, word | (byte << shift), phase, state);
                }
                for (const auto word : edges)
                    decoder(family, word, phase, state);
            }
    }
    {
        // The original full-width context must be valid even for a refusal.
        Family family("decoder-invalid-context");
        for (U64 phase = 0; phase < 4; ++phase)
            for (U64 state = 0; state < 6; ++state)
                for (unsigned field = 0; field < 2; ++field)
                    for (const auto value : edges) {
                        if (value <= (field == 0 ? 3U : 5U))
                            continue;
                        const auto changed_phase = field == 0 ? value : phase;
                        const auto changed_state = field == 1 ? value : state;
                        decoder(family, 0, changed_phase, changed_state);
                        for (const auto word : words)
                            decoder(family, word, changed_phase, changed_state);
                        decoder(family, U64{1} << 63, changed_phase, changed_state);
                        decoder(family, maximum, changed_phase, changed_state);
                    }
    }
    {
        Family family("decoder-random");
        Random random(202610082);
        for (unsigned i = 0; i < 8192; ++i) {
            U64 phase = (i % 24) / 6, state = i % 6;
            if (i % 2 == 0) {
                phase = random();
                state = random();
            }
            decoder(family, random(), phase, state);
        }
    }
    return 0;
}
} // namespace kernel_client_disposal_native
