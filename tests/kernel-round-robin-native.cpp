// Host-only binary observation. The real Aurora object and real C++ decoder are
// linked; no host I/O or testing implementation is linked into the kernel.
#include "../kernel/round-robin-transport.hpp"
#include <array>
#include <cstdio>
#include <cstring>

auto main(int argc, char** argv) -> int {
    const bool decode = argc == 2 && std::strcmp(argv[1], "decode") == 0;
    if (argc != 1 && !decode) return 2;
    const std::size_t width = decode ? 3 : 2;
    std::array<std::uint64_t, 3> input{};
    for (;;) {
        const auto count = std::fread(input.data(), 1, width * 8, stdin);
        if (count == 0 && std::feof(stdin)) return 0;
        if (count != width * 8) return 3;
        std::uint64_t result{};
        if (decode) {
            const auto selected = aurora::ipc::RoundRobinSelection::decode(input[0], input[1], input[2]);
            if (selected) result = (selected->selected() ? 2ULL : 1ULL)
                | (std::uint64_t{selected->client()} << 8) | (std::uint64_t{selected->next()} << 16);
        } else {
            result = aurora::ipc::language_round_robin_next(input[0], input[1]);
            const auto selected = aurora::ipc::RoundRobinSelection::decode(result, input[0], input[1]);
            if (result != 0 && !selected) return 4;
        }
        if (std::fwrite(&result, 1, sizeof(result), stdout) != sizeof(result)) return 5;
    }
}
