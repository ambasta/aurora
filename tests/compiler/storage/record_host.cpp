// Test host for one compiled storage/filesystem driver; not an Aurora API or ABI.
// The input file holds one u64 record size, then repeated (u64 slot count, record)
// pairs. Every slot calls the driver's const `entry(i64 slot) -> u64` method on the
// borrowed record and writes the complete 64-bit result to stdout. With a case
// index argument only that record runs, under a handler that accepts nothing but
// a kernel-delivered SIGILL at the module's exact bounds-trap UD2.
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <ucontext.h>
#include <unistd.h>
#include <vector>

extern "C" std::uint64_t storage_invoke(const void *record, std::int64_t slot);
extern "C" const unsigned char storage_bounds_trap[] __attribute__((weak));

static void trapped(int signal, siginfo_t *info, void *context) {
    const auto *frame = static_cast<const ucontext_t *>(context);
    const auto *pc = reinterpret_cast<const unsigned char *>(frame->uc_mcontext.gregs[REG_RIP]);
    if (signal == SIGILL && info->si_code > 0 && pc == storage_bounds_trap && pc[0] == 0x0f && pc[1] == 0x0b) {
        constexpr char message[] = "bounds-trap\n";
        (void)!write(STDOUT_FILENO, message, sizeof(message) - 1);
        _exit(77);
    }
    _exit(78);
}

int main(int argc, char **argv) {
    if (argc != 2 && argc != 3)
        return 1;
    const bool selected = argc == 3;
    const auto wanted = selected ? std::strtoull(argv[2], nullptr, 10) : 0;
    if (selected) {
        if (storage_bounds_trap == nullptr)
            return 9;
        struct sigaction action{};
        action.sa_sigaction = trapped;
        action.sa_flags = SA_SIGINFO;
        sigemptyset(&action.sa_mask);
        if (sigaction(SIGILL, &action, nullptr) != 0)
            return 8;
    }
    auto *file = std::fopen(argv[1], "rb");
    if (file == nullptr)
        return 2;
    std::uint64_t size = 0;
    if (std::fread(&size, sizeof(size), 1, file) != 1 || size == 0 || size % 8 != 0 || size > (1u << 16))
        return 3;
    std::vector<std::uint64_t> record(size / 8);
    std::uint64_t slots = 0;
    for (std::uint64_t index = 0; std::fread(&slots, sizeof(slots), 1, file) == 1; ++index) {
        if (slots == 0 || slots > 4096 || std::fread(record.data(), 1, size, file) != size)
            return 4;
        if (selected && index != wanted)
            continue;
        for (std::uint64_t slot = 0; slot < slots; ++slot) {
            const auto value = storage_invoke(record.data(), static_cast<std::int64_t>(slot));
            if (std::fwrite(&value, sizeof(value), 1, stdout) != 1)
                return 5;
        }
    }
    const int result = std::ferror(file) ? 6 : 0;
    return std::fclose(file) != 0 ? 7 : result;
}
