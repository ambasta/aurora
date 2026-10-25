// Host-only binary observation of the genuine Aurora root and production decoder.
// Explicit classified records keep ordinary refusal distinct from malformed data.
// Fixed full-width vector families are compared with tests/kernel-ipc-transition-native.golden.
#include "../kernel/ipc-transition-transport.hpp"
#include "policy-vectors.hpp"
#include <array>
#include <cstdlib>
#include <vector>

namespace kernel_ipc_transition_native {
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
constexpr U64 valid_words[] = {1, 0x010102, 0x020202, 0x030302, 0x040502, 0x050502, 0x060402, 0x070002};
using Context = std::array<U64, 4>;
auto contexts() -> std::vector<Context> {
    std::vector<Context> result;
    for (U64 operation = 0; operation < 6; ++operation)
        for (U64 phase = 0; phase < 4; ++phase)
            for (U64 state = 0; state < 6; ++state)
                for (U64 scrubbed = 0; scrubbed < 2; ++scrubbed)
                    result.push_back({operation, phase, state, scrubbed});
    return result;
}
auto policy(Family &family, const Context &c) -> void {
    family.observe({c[0], c[1], c[2], c[3]}, {aurora::ipc::language_ipc_transition(c[0], c[1], c[2], c[3])});
}
auto decoder(Family &family, U64 word, const Context &c) -> void {
    const auto result = aurora::ipc::TransactionTransition::decode(word, c[0], c[1], c[2], c[3]);
    U64 status{};
    switch (result.status()) {
    case aurora::ipc::TransactionStatus::malformed:
        status = 0;
        break;
    case aurora::ipc::TransactionStatus::refused:
        status = 1;
        break;
    case aurora::ipc::TransactionStatus::accepted:
        status = 2;
        break;
    default:
        std::exit(4);
    }
    if (result.accepted() != (status == 2))
        std::exit(5);
    family.observe({word, c[0], c[1], c[2], c[3]}, {status, result.next(), static_cast<U64>(result.effect())});
}
} // namespace

auto main() -> int {
    const auto valid = contexts();
    {
        Family family("policy-table", Rows::all);
        for (const auto &context : valid)
            policy(family, context);
    }
    {
        // Every raw field independently, then simultaneous invalid fields.
        Family family("policy-fields");
        for (const auto &context : valid)
            for (unsigned field = 0; field < 4; ++field) {
                for (const auto value : edges) {
                    auto changed = context;
                    changed[field] = value;
                    policy(family, changed);
                }
                for (unsigned bit = 0; bit < 64; ++bit) {
                    auto changed = context;
                    changed[field] ^= U64{1} << bit;
                    policy(family, changed);
                }
            }
        for (const auto value : edges)
            policy(family, {value, value, value, value});
    }
    {
        Family family("policy-random");
        Random random(202610051);
        for (unsigned i = 0; i < 16384; ++i) {
            Context context;
            for (auto &word : context)
                word = random();
            policy(family, context);
        }
    }
    {
        // 288 contexts * 4 actions * 8 states * 8 effects compact classified words.
        Family family("decoder-compact");
        for (const auto &context : valid)
            for (U64 action = 0; action < 4; ++action)
                for (U64 state = 0; state < 8; ++state)
                    for (U64 effect = 0; effect < 8; ++effect)
                        decoder(family, action | (state << 8) | (effect << 16), context);
    }
    {
        Family family("decoder-mutations");
        for (const auto &context : valid) {
            for (const auto word : valid_words) {
                for (unsigned bit = 0; bit < 64; ++bit)
                    decoder(family, word ^ (U64{1} << bit), context);
                // Full byte boundaries, field overflow and upper reserved bits.
                for (const unsigned shift : {0U, 8U, 16U, 24U, 32U, 56U})
                    for (const U64 edge : {0, 1, 2, 3, 7, 8, 127, 128, 254, 255, 256})
                        decoder(family, word | (edge << shift), context);
            }
            for (const auto word : edges)
                decoder(family, word, context);
        }
    }
    {
        // Invalid original contexts must reject even refusal or a plausible success.
        Family family("decoder-invalid-context");
        const U64 limits[] = {5, 3, 5, 1};
        const Context bases[] = {{0, 1, 0, 1},
                                 {1, 2, 1, 0},
                                 {2, 2, 2, 1},
                                 {3, 3, 3, 0},
                                 {3, 3, 4, 1},
                                 {4, 0, 1, 0},
                                 {4, 0, 2, 1},
                                 {5, 0, 5, 1}};
        for (unsigned field = 0; field < 4; ++field)
            for (const auto value : edges) {
                if (value <= limits[field])
                    continue;
                for (const auto &base : bases) {
                    auto changed = base;
                    changed[field] = value;
                    decoder(family, 0, changed);
                    for (const auto word : valid_words)
                        decoder(family, word, changed);
                    decoder(family, U64{1} << 63, changed);
                    decoder(family, maximum, changed);
                }
            }
    }
    {
        Family family("decoder-random");
        Random random(202610052);
        for (unsigned i = 0; i < 16384; ++i) {
            Context context;
            if (i % 2)
                context = valid[i % valid.size()];
            else
                for (auto &word : context)
                    word = random();
            decoder(family, random(), context);
        }
    }
    return 0;
}
} // namespace kernel_ipc_transition_native
