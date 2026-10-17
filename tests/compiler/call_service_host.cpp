// Native compiler ABI probe only; protected blocking is tested by the guest.
#include <cstdint>
#include <cstdlib>
struct Argument {
    std::uint64_t grant, generation, value, expected;
};
struct Result {
    std::uint64_t status, value;
};
unsigned mode;
extern "C" std::uint64_t checked_group_entry(const Argument *);
extern "C" Result __au_runtime_call(std::uint64_t grant, std::uint64_t generation, std::uint64_t value) {
    if (grant != 0xC011 || generation != 91 || value != 42)
        std::abort();
    if (mode == 3)
        return {3, 0};
    if (mode == 4)
        return {0x100000000ULL, 0};
    if (mode == 5)
        return {1, 1};
    if (mode == 6)
        return {2, 0x100000000ULL};
    return {mode, mode == 0 ? UINT64_MAX : 0};
}
int main(int argc, char **argv) {
    mode = argc == 2 ? std::atoi(argv[1]) : 0;
    const Argument argument{0xC011, 91, 40, mode};
    return checked_group_entry(&argument) == 42 ? 0 : 1;
}
