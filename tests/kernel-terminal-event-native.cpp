// Host-only observation of the real Aurora terminal-event producer and decoder over
// fixed full-width vector families (compared with tests/kernel-terminal-event-native.golden),
// or, with TERMINAL_SUBSTITUTE, of ProgramRun against hostile producer proposals.
#include "../kernel/user-program.hpp"
#include "policy-vectors.hpp"
#include <set>
#include <vector>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>

namespace kernel_terminal_event_native {
using namespace aurora::user;
[[maybe_unused]] static void require(bool value) {
    if (!value)
        std::abort();
}
#ifdef TERMINAL_SUBSTITUTE
static std::uint64_t proposal, calls;
static bool genuine;
auto real_terminal_event(std::uint64_t, std::uint64_t, std::uint64_t) -> std::uint64_t
    asm("aurora_kernel_terminal_event_real");
} // namespace kernel_terminal_event_native
auto aurora::user::language_terminal_event(std::uint64_t v, std::uint64_t m, std::uint64_t t) -> std::uint64_t {
    namespace observed = kernel_terminal_event_native;
    ++observed::calls;
    return observed::genuine ? observed::real_terminal_event(v, m, t) : observed::proposal;
}
namespace kernel_terminal_event_native {
#endif
static auto wire(ProgramEvent e) -> std::uint64_t {
    switch (e) {
    case ProgramEvent::returned:
        return 1;
    case ProgramEvent::bounds:
        return 2;
    case ProgramEvent::overflow:
        return 3;
    case ProgramEvent::division_zero:
        return 4;
    case ProgramEvent::shift_count:
        return 5;
    default:
        return 0;
    }
}
// Every compact result and high-bit mutation of every positive result.
static auto proposals() -> std::vector<std::uint64_t> {
    std::set<std::uint64_t> words{~std::uint64_t{0}};
    for (std::uint64_t word = 0; word < 9; ++word)
        words.insert(word);
    for (std::uint64_t event = 0; event < 6; ++event)
        for (unsigned bit = 3; bit < 64; ++bit)
            words.insert(event | (std::uint64_t{1} << bit));
    return {words.begin(), words.end()};
}
auto main() -> int {
    const auto words = proposals();
#ifdef TERMINAL_SUBSTITUTE
    std::size_t count = 0;
    for (const auto encoded : words) {
        for (const auto layout :
             {ProgramLayout::bios(),
              *ProgramLayout::create(0x400000, 0x403000, 1, 0x500000, 0x504000, 0x600000, 0x604000)}) {
            const auto base = layout.code_begin();
            const ProgramContract contract{layout, base, 128, base + 32, base + 64, base + 66, base + 68, base + 70};
            const std::array<std::uint64_t, 5> pcs{base + 32, base + 64, base + 66, base + 68, base + 70};
            for (std::size_t i = 0; i < pcs.size(); ++i) {
                ProgramRun run;
                require(run.begin(contract));
                const ProgramContext context{i == 0 ? 129ULL : 6ULL,
                                             0,
                                             pcs[i],
                                             0x1b,
                                             0x23,
                                             layout.user_stack_top(),
                                             2,
                                             layout.entry_stack_bottom()};
                std::array<unsigned char, sizeof(run)> before{};
                std::memcpy(before.data(), &run, sizeof(run));
                genuine = false;
                proposal = encoded;
                calls = 0;
                const bool accepted = run.accept(context, 73);
                require(calls == 1);
                require(accepted == (encoded == i + 1));
                if (!accepted) {
                    require(std::memcmp(before.data(), &run, sizeof(run)) == 0);
                    genuine = true;
                    require(run.accept(context, 73));
                }
                require(!run.running() && wire(run.event()) == i + 1 && run.value() == (i == 0 ? 73 : 0));
                const auto old_calls = calls;
                require(!run.accept(context, 99) && calls == old_calls);
                ++count;
            }
            // Invalid origin/error/metadata rejects before consulting any proposal.
            const auto top = layout.user_stack_top(), frame = layout.entry_stack_bottom();
            const std::array<ProgramContext, 8> invalid{
                ProgramContext{129, 1, base + 32, 0x1b, 0x23, top, 2, frame},
                ProgramContext{129, 0, base + 32, 8, 0x23, top, 2, frame},
                ProgramContext{129, 0, base + 32, 0x1b, 0x10, top, 2, frame},
                ProgramContext{129, 0, base + 32, 0x1b, 0x23, top + 8, 2, frame},
                ProgramContext{129, 0, base + 32, 0x1b, 0x23, top - 1, 2, frame},
                ProgramContext{129, 0, base + 32, 0x1b, 0x23, top, 0, frame},
                ProgramContext{129, 0, base + 32, 0x1b, 0x23, top, 514, frame},
                ProgramContext{129, 0, base + 32, 0x1b, 0x23, top, 2, frame - 8}};
            for (const auto &context : invalid) {
                ProgramRun run;
                require(run.begin(contract));
                calls = 0;
                std::array<unsigned char, sizeof(run)> before{};
                std::memcpy(before.data(), &run, sizeof(run));
                require(!run.accept(context, 73) && calls == 0);
                require(std::memcmp(before.data(), &run, sizeof(run)) == 0);
            }
            const ProgramContract malformed{layout, base, 128, base + 32, base + 32, base + 66};
            calls = 0;
            require(malformed.classify(ProgramContext{129, 0, base + 32, 0x1b, 0x23, top, 2, frame}) ==
                    ProgramEvent::rejected);
            require(calls == 0);
        }
    }
    require(count == words.size() * 10);
    std::cout << "PASS: " << count << " hostile terminal proposals against ProgramRun\n";
#else
    using namespace policy_vectors;
    std::vector<std::array<U64, 3>> finite, hostile;
    for (U64 v = 0; v < 256; ++v)
        for (U64 m = 0; m < 32; ++m)
            for (U64 t = 0; t < 2; ++t)
                finite.push_back({v, m, t});
    std::vector<U64> edges;
    for (U64 value = 0; value < 34; ++value)
        edges.push_back(value);
    for (const U64 value : {U64{127}, U64{128}, U64{129}, U64{130}, U64{254}, U64{255}, U64{256}, U64{257},
                            U64{65535}, U64{65536}, (U64{1} << 32) - 1, U64{1} << 32, (U64{1} << 63) - 1,
                            U64{1} << 63, maximum})
        edges.push_back(value);
    for (const auto v : edges)
        for (const auto m : edges)
            for (const U64 t : {U64{0}, U64{1}, U64{2}, U64{255}, U64{256}, U64{1} << 32, U64{1} << 63, maximum})
                hostile.push_back({v, m, t});
    Random random(0x7465726D);
    for (unsigned i = 0; i < 4096; ++i) {
        std::array<U64, 3> row{};
        for (auto &word : row)
            word = random();
        hostile.push_back(row);
    }
    const auto policy = [](Family &family, const std::array<U64, 3> &r) {
        family.observe({r[0], r[1], r[2]}, {language_terminal_event(r[0], r[1], r[2])});
    };
    const auto decoder = [](Family &family, const std::array<U64, 3> &r, U64 e) {
        family.observe({r[0], r[1], r[2], e}, {wire(decode_terminal_event(e, r[0], r[1], r[2]))});
    };
    {
        Family family("policy-finite", Rows::nonzero);
        for (const auto &row : finite)
            policy(family, row);
    }
    {
        Family family("policy-hostile");
        for (const auto &row : hostile)
            policy(family, row);
    }
    {
        Family family("decoder-finite", Rows::nonzero);
        for (const auto &row : finite)
            for (U64 e = 0; e < 8; ++e)
                decoder(family, row, e);
    }
    {
        // Every accepted tuple and near misses against every proposal word.
        Family family("decoder-proposals");
        const std::array<U64, 3> rows[] = {{129, 1, 1}, {6, 2, 0},  {6, 2, 1},   {6, 4, 0},  {6, 4, 1},
                                           {6, 8, 0},   {6, 8, 1},  {6, 16, 0},  {6, 16, 1}, {256, 1, 1},
                                           {129, 33, 1}, {129, 1, 2}, {6, 3, 1}};
        for (const auto &row : rows)
            for (const auto e : words)
                decoder(family, row, e);
    }
    {
        Family family("decoder-hostile");
        for (std::size_t i = 0; i < hostile.size(); ++i)
            decoder(family, hostile[i], words[i % words.size()]);
    }
#endif
    return 0;
}
} // namespace kernel_terminal_event_native
