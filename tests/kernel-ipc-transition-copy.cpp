#include <cstdint>
#include <cstdio>
auto probe() -> std::uint64_t asm("ipc_transition_copy_probe");
auto main() -> int {
    for (unsigned iteration = 0; iteration < 4096; ++iteration)
        if (probe() != 42)
            return 1;
    std::puts("PASS: 4096 independent snapshot and decision copy observations");
}
