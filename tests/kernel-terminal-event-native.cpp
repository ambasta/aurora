#include "../kernel/user-program.hpp"
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string_view>
using namespace aurora::user;
static void require(bool value) {
    if (!value)
        std::abort();
}
#ifdef TERMINAL_SUBSTITUTE
static std::uint64_t proposal, calls;
static bool genuine;
auto real_terminal_event(std::uint64_t, std::uint64_t, std::uint64_t) -> std::uint64_t
    asm("aurora_kernel_terminal_event_real");
auto aurora::user::language_terminal_event(std::uint64_t v, std::uint64_t m, std::uint64_t t) -> std::uint64_t {
    ++calls;
    return genuine ? real_terminal_event(v, m, t) : proposal;
}
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
auto main(int argc, char **argv) -> int {
    require(argc == 2);
    const std::string_view mode{argv[1]};
#ifdef TERMINAL_SUBSTITUTE
    require(mode == "adapter");
    std::uint64_t encoded;
    std::size_t count = 0;
    while (std::cin >> encoded) {
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
    std::cout << count << '\n';
#else
    std::uint64_t v, m, t, e;
    while (std::cin >> v >> m >> t >> e) {
        if (mode == "policy")
            std::cout << language_terminal_event(v, m, t) << '\n';
        else {
            require(mode == "decoder");
            std::cout << wire(decode_terminal_event(e, v, m, t)) << '\n';
        }
    }
#endif
}
