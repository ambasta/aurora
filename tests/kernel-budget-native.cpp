// Host-only observation adapter. No host I/O implementation is linked into the
// kernel; the real Aurora object and real C++ transport decoder are linked here.
#include "../kernel/uefi/budget-transport.hpp"
#include <array>
#include <cstdio>
#include <cstring>

int main(int argc, char **argv) {
    const bool decode = argc == 2 && std::strcmp(argv[1], "decode") == 0;
    if (argc != 1 && !decode)
        return 2;
    const std::size_t width = decode ? 4 : 3;
    std::array<std::uint64_t, 4> input{};
    for (;;) {
        const auto count = std::fread(input.data(), 1, width * 8, stdin);
        if (count == 0 && std::feof(stdin))
            return 0;
        if (count != width * 8)
            return 3;
        std::uint64_t result{};
        if (decode) {
            const auto value = aurora::uefi::BudgetTransition::decode(input[0], input[1], input[2], input[3]);
            if (value)
                result = (std::uint64_t{value->resume() ? 1U : 2U} << 16) | (std::uint64_t{value->used()} << 8) |
                         value->remaining();
        } else {
            result = aurora::uefi::language_budget_tick(input[0], input[1], input[2]);
            const auto value = aurora::uefi::BudgetTransition::decode(result, input[0], input[1], input[2]);
            if (result != 0 && !value)
                return 4;
        }
        if (std::fwrite(&result, 1, sizeof(result), stdout) != sizeof(result))
            return 5;
    }
}
