// Hosted full-width observation only: the linked Aurora root and production
// decoder are the subjects. The independent expected relation lives in Python.
#include "../kernel/client-disposal-transport.hpp"
#include <array>
#include <cstdio>
#include <cstring>

static_assert(aurora::ipc::DisposalTransition::decode(0x0102, 0, 0).accepted());
static_assert(!aurora::ipc::DisposalTransition::decode(0x0102, 0, 1).accepted());
static_assert(!aurora::ipc::DisposalTransition::decode(1, 4, 0).accepted());

auto main(int argc, char **argv) -> int {
    const bool decode = argc == 2 && std::strcmp(argv[1], "decode") == 0;
    if (argc != 1 && !decode)
        return 2;
    const std::size_t width = decode ? 3 : 2;
    std::array<std::uint64_t, 3> input{};
    for (;;) {
        const auto count = std::fread(input.data(), 1, width * sizeof(std::uint64_t), stdin);
        if (count == 0 && std::feof(stdin))
            return 0;
        if (count != width * sizeof(std::uint64_t))
            return 3;
        std::array<std::uint64_t, 2> output{};
        if (decode) {
            const auto result = aurora::ipc::DisposalTransition::decode(input[0], input[1], input[2]);
            switch (result.status()) {
            case aurora::ipc::DisposalStatus::malformed:
                output[0] = 0;
                break;
            case aurora::ipc::DisposalStatus::refused:
                output[0] = 1;
                break;
            case aurora::ipc::DisposalStatus::accepted:
                output[0] = 2;
                break;
            default:
                return 4;
            }
            output[1] = static_cast<std::uint64_t>(result.effect());
            if (result.accepted() != (output[0] == 2))
                return 5;
        } else {
            output[0] = aurora::ipc::language_client_disposal(input[0], input[1]);
        }
        const auto bytes = (decode ? 2 : 1) * sizeof(std::uint64_t);
        if (std::fwrite(output.data(), 1, bytes, stdout) != bytes)
            return 6;
    }
}
