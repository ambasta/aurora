// Execute the emitted INT 0x83 endpoint boundary in a native process. The
// signal adapter supplies hostile raw kernel channels, never typed values.
#include <array>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ucontext.h>
#include <unistd.h>

namespace {
constexpr std::size_t payload = 65536;
struct Window {
    std::uint64_t count, source, transaction, active;
    std::array<std::uint64_t, 4> reserved;
    std::array<unsigned char, payload> request, reply;
};
static_assert(sizeof(Window) == 131136);
struct Entry {
    std::uint64_t grant, generation;
    std::uint64_t owner, address, descriptor[4], length;
};
static_assert(sizeof(Entry) == 72);
Window window{};
std::array<unsigned char, payload + 1> reply{};
unsigned mode{}, calls{};

void kernel(int, siginfo_t *, void *raw) {
    auto &registers = static_cast<ucontext_t *>(raw)->uc_mcontext.gregs;
    const auto *instruction = reinterpret_cast<const unsigned char *>(registers[REG_RIP]);
    // INT 0x83 is the fixed process ABI, not a generated instruction recipe.
    if (instruction[0] != 0xcd || instruction[1] != 0x83 || registers[REG_RAX] != 15 ||
        registers[REG_RDI] != reinterpret_cast<greg_t>(&window) || registers[REG_RSI] != 3 ||
        registers[REG_RDX] != 91 || registers[REG_R10] != 0 || calls++ != 0 ||
        std::memcmp(window.reply.data(), "abc", 3) != 0) {
        _exit(90);
    }
    window.count = 3;
    window.source = 7;
    window.transaction = 91;
    window.active = 1;
    std::memcpy(window.request.data(), "xyz", 3);
    registers[REG_RAX] = 0;
    registers[REG_RDX] = 3;
    if (mode == 1 || (mode >= 4 && mode <= 6)) {
        window.count = window.source = window.transaction = window.active = 0;
        registers[REG_RAX] = 1;
        registers[REG_RDX] = 0;
    }
    switch (mode) {
    case 2:
        registers[REG_RAX] = 2;
        break;
    case 3:
        registers[REG_RDX] = payload + 1;
        break;
    case 4:
        registers[REG_RDX] = 1;
        break;
    case 5:
        window.source = 1;
        break;
    case 6:
        window.transaction = 1;
        break;
    case 7:
        window.transaction = 0;
        break;
    case 8:
        window.active = 2;
        break;
    case 9:
        window.count = 2;
        break;
    case 10:
        window.reserved[3] = 1;
        break;
    case 11:
        registers[REG_RAX] = static_cast<greg_t>(0x100000000ULL);
        break;
    case 16:
        registers[REG_RDX] = static_cast<greg_t>(0x100000000ULL);
        break;
    case 12:
    case 13:
    case 14:
        window.source = mode;
        break;
    default:
        break;
    }
    registers[REG_RIP] += 2;
}
} // namespace

extern "C" std::uint64_t checked_group_entry(const Entry *);
int main(int argc, char **argv) {
    mode = argc == 2 ? static_cast<unsigned>(std::atoi(argv[1])) : 0;
    struct sigaction action{};
    action.sa_sigaction = kernel;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGSEGV, &action, nullptr) != 0) {
        return 91;
    }
    std::memcpy(reply.data(), "abc", 3);
    const Entry entry{reinterpret_cast<std::uint64_t>(&window),
                      91,
                      0,
                      reinterpret_cast<std::uint64_t>(reply.data()),
                      {},
                      mode == 15 ? payload + 1 : 3};
    return checked_group_entry(&entry) == 42 && calls == 1 ? 0 : 1;
}
