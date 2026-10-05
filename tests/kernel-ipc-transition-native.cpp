// Host-only binary observation of the genuine Aurora root and production decoder.
// Explicit classified records keep ordinary refusal distinct from malformed data.
#include "../kernel/ipc-transition-transport.hpp"
#include <array>
#include <cstdio>
#include <cstring>

auto main(int argc, char** argv) -> int {
    const bool decode = argc == 2 && std::strcmp(argv[1], "decode") == 0;
    if (argc != 1 && !decode) return 2;
    const std::size_t width = decode ? 5 : 4;
    std::array<std::uint64_t, 5> input{};
    for (;;) {
        const auto count = std::fread(input.data(), 1, width * 8, stdin);
        if (count == 0 && std::feof(stdin)) return 0;
        if (count != width * 8) return 3;
        std::array<std::uint64_t, 3> output{};
        if (decode) {
            const auto result = aurora::ipc::TransactionTransition::decode(input[0], input[1], input[2], input[3], input[4]);
            switch (result.status()) {
            case aurora::ipc::TransactionStatus::malformed: output[0] = 0; break;
            case aurora::ipc::TransactionStatus::refused: output[0] = 1; break;
            case aurora::ipc::TransactionStatus::accepted: output[0] = 2; break;
            default: return 4;
            }
            output[1] = result.next();
            output[2] = static_cast<std::uint64_t>(result.effect());
            if (result.accepted() != (output[0] == 2)) return 5;
        } else {
            output[0] = aurora::ipc::language_ipc_transition(input[0], input[1], input[2], input[3]);
        }
        const auto bytes = (decode ? 3 : 1) * sizeof(std::uint64_t);
        if (std::fwrite(output.data(), 1, bytes, stdout) != bytes) return 6;
    }
}
