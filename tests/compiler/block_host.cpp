// Native execution of the exact process INT83/op16 boundary, including hostile
// full-width raw results. This adapter is not a kernel grant/lifecycle proof.
#include <array>
#include <csignal>
#include <cstdint>
#include <cstdlib>
#include <ucontext.h>
#include <unistd.h>
namespace {
struct Window {
    std::uint64_t sectors, status;
    std::array<unsigned char, 512> bytes;
};
static_assert(sizeof(Window) == 528);
struct Entry {
    std::uint64_t grant, generation, mode;
};
Window window{128, 3, {}};
unsigned mode{}, calls{};
struct WriterWindow {
    std::uint64_t before{0x123456789abcdef0ULL};
    Window value{128, 3, {}};
    std::uint64_t staged{}, reserved{}, after{0xfedcba9876543210ULL};
} writer;
struct WriterEntry {
    std::uint64_t grant, generation, argument, byte;
};
extern "C" std::uint64_t writer_read_entry(const WriterEntry *);
extern "C" std::uint64_t writer_byte_entry(const WriterEntry *);
extern "C" std::uint64_t writer_descriptor_entry(const WriterEntry *);
extern "C" std::uint64_t writer_stage_entry(const WriterEntry *);
extern "C" std::uint64_t writer_write_entry(const WriterEntry *);
extern "C" std::uint64_t writer_flush_entry(const WriterEntry *);
extern "C" std::uint64_t writer_budget_entry(const WriterEntry *);
void writer_kernel(greg_t *r) {
    const auto op = r[REG_RAX];
    if (writer.before != 0x123456789abcdef0ULL || writer.after != 0xfedcba9876543210ULL)
        _exit(85);
    if (r[REG_RDX] != 91 || r[REG_R10] || writer.value.status != 3 || writer.staged || writer.reserved)
        _exit(80);
    if (op == 17 || op == 18) {
        if (r[REG_RDI] != reinterpret_cast<greg_t>(writer.value.bytes.data()) || r[REG_RSI] != 7)
            _exit(81);
        for (unsigned i = 0; i < 512; ++i)
            if (writer.value.bytes[i] != (op == 17 ? 0 : static_cast<unsigned char>(i)))
                _exit(82);
    } else if ((op != 19 && op != 20) || r[REG_RDI] || r[REG_RSI])
        _exit(83);
    r[REG_RAX] = 0;
    r[REG_RDX] = op == 17 ? 512 : 0;
    if (op == 17) {
        writer.value.bytes[0] = 90;
        writer.value.bytes[511] = 51;
    }
    if (op == 20)
        r[REG_RAX] = 60000;
    if (mode == 101 || mode == 102 || mode == 103) {
        r[REG_RAX] = mode - 100;
        r[REG_RDX] = 0;
        if (op == 17)
            writer.value.bytes.fill(0);
    }
    if (mode == 120 || mode == 130)
        r[REG_RAX] = 4;
    if (mode == 121 || mode == 131)
        r[REG_RAX] = 0x100000000ULL;
    if (mode == 122 || mode == 132)
        r[REG_RDX] = 1;
    if (mode == 123)
        r[REG_RAX] = 65536;
    if (mode == 124)
        r[REG_RDX] = 1;
    if (mode == 125) {
        r[REG_RAX] = 1;
        r[REG_RDX] = 0;
        writer.value.bytes[0] = 1;
    }
    if (mode == 126)
        r[REG_RDX] = 511;
    ++calls;
    r[REG_RIP] += 2;
}
int writer_test() {
    WriterEntry e{reinterpret_cast<std::uint64_t>(&writer.value), 91, 7, 0};
    if (mode == 110) {
        e.argument = 1;
        writer_stage_entry(&e);
        return 1;
    }
    if (mode == 111) {
        e.argument = 512;
        writer_stage_entry(&e);
        return 1;
    }
    if (mode == 112) {
        writer_write_entry(&e);
        return 1;
    }
    if (mode == 113) {
        e.argument = 0;
        writer_stage_entry(&e);
        writer_stage_entry(&e);
        return 1;
    }
    if (mode == 114) {
        e.argument = 0;
        e.generation = 0;
        writer_stage_entry(&e);
        return 1;
    }
    if (mode == 115) {
        e.argument = 0;
        writer_byte_entry(&e);
        return 1;
    }
    if (mode == 116) {
        e.argument = 2;
        writer_descriptor_entry(&e);
        return 1;
    }
    if (mode >= 130 && mode <= 132) {
        writer_flush_entry(&e);
        return 1;
    }
    if (mode == 123 || mode == 124) {
        writer_budget_entry(&e);
        return 1;
    }
    if (mode == 125 || mode == 126) {
        writer_read_entry(&e);
        return 1;
    }
    e.argument = 0;
    if (writer_descriptor_entry(&e) != 128)
        return 2;
    e.argument = 1;
    if (writer_descriptor_entry(&e) != 91)
        return 3;
    e.argument = 7;
    if (mode < 110) {
        const auto read = writer_read_entry(&e);
        if (read != (mode - 100))
            return 4;
        if (mode == 100) {
            e.argument = 511;
            if (writer_byte_entry(&e) != 51)
                return 5;
        }
    }
    for (unsigned i = 0; i < 512; ++i) {
        e.argument = i;
        e.byte = static_cast<unsigned char>(i);
        if (writer_stage_entry(&e))
            return 6;
    }
    e.argument = 7;
    const auto status = writer_write_entry(&e);
    if (status != (mode < 110 ? mode - 100 : 0) || writer.staged || writer.value.status != 3)
        return 7;
    if (mode == 117) {
        writer_write_entry(&e);
        return 1;
    }
    if (mode == 118) {
        e.argument = 0;
        writer_byte_entry(&e);
        return 1;
    }
    if (writer_flush_entry(&e) != (mode < 110 ? mode - 100 : 0))
        return 8;
    if (mode == 119) {
        e.argument = 1;
        writer_stage_entry(&e);
        return 1;
    }
    if (mode == 100 && writer_budget_entry(&e) != 60000)
        return 9;
    if (calls != (mode == 100 ? 4u : 3u))
        return 11;
    return writer.before == 0x123456789abcdef0ULL && writer.after == 0xfedcba9876543210ULL && !writer.reserved ? 0 : 10;
}

void kernel(int, siginfo_t *, void *raw) {
    auto &r = static_cast<ucontext_t *>(raw)->uc_mcontext.gregs;
    const auto *instruction = reinterpret_cast<const unsigned char *>(r[REG_RIP]);
    if (mode >= 100) {
        if (instruction[0] != 0xcd || instruction[1] != 0x83)
            _exit(84);
        writer_kernel(r);
        return;
    }
    if (instruction[0] != 0xcd || instruction[1] != 0x83 || r[REG_RAX] != 16 ||
        r[REG_RDI] != reinterpret_cast<greg_t>(window.bytes.data()) ||
        r[REG_RSI] != (calls == 0 ? (mode == 12 ? -1 : 7) : 128) || r[REG_RDX] != (mode == 3 ? 0 : 91) ||
        r[REG_R10] != 0 || window.sectors != (mode == 3 ? 0u : 128u) || window.status != 3 || calls > 1)
        _exit(90);
    for (auto byte : window.bytes)
        if (byte != 0)
            _exit(91);
    const bool failed = calls != 0 || mode == 1 || mode == 2 || mode == 3 || mode == 7 || mode == 9 || mode == 12;
    r[REG_RAX] = failed ? (mode == 2 || mode == 11 ? 2 : (mode == 3 ? 3 : 1)) : 0;
    r[REG_RDX] = failed ? 0 : 512;
    if (!failed) {
        window.bytes[0] = 90;
        window.bytes[511] = 51;
    }
    switch (mode) {
    case 4:
        r[REG_RAX] = 4;
        break;
    case 5:
        r[REG_RAX] = static_cast<greg_t>(0x100000000ULL);
        break;
    case 6:
        r[REG_RDX] = 511;
        break;
    case 7:
        r[REG_RDX] = 512;
        break;
    case 8:
        r[REG_RDX] = static_cast<greg_t>(0x100000000ULL);
        break;
    case 9:
        window.bytes[511] = 1;
        break;
    case 10:
        if (calls != 0)
            window.bytes[0] = 1;
        break;
    default:
        break;
    }
    ++calls;
    r[REG_RIP] += 2;
}
} // namespace
extern "C" std::uint64_t checked_group_entry(const Entry *);
extern "C" std::uint64_t block_byte_entry(const Entry *);
extern "C" std::uint64_t block_descriptor_entry(const Entry *);
int main(int argc, char **argv) {
    mode = argc == 2 ? static_cast<unsigned>(std::atoi(argv[1])) : 0;
    if (mode == 3)
        window.sectors = 0;
    struct sigaction action{};
    action.sa_sigaction = kernel;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGSEGV, &action, nullptr) != 0)
        return 92;
    if (mode >= 100)
        return writer_test();
    Entry entry{reinterpret_cast<std::uint64_t>(&window), mode == 3 ? 0u : 91u, mode};
    if (mode >= 20) {
        if (mode < 25) {
            window.status = mode == 24 ? 3 : 0;
            window.bytes[0] = 90;
            window.bytes[511] = 51;
            entry.mode = mode == 20 || mode == 24 ? 0 : (mode == 21 ? 511 : (mode == 22 ? 512 : UINT64_MAX));
            return block_byte_entry(&entry) == (mode == 21 ? 51u : 90u) && calls == 0 ? 0 : 2;
        }
        entry.mode = mode == 25 ? 2 : (mode == 26 ? 0 : 1);
        return block_descriptor_entry(&entry) == (mode == 26 ? 128u : 91u) && calls == 0 ? 0 : 3;
    }
    const unsigned expected = mode == 0 || mode == 11 ? 2 : 1;
    return checked_group_entry(&entry) == 42 && calls == expected ? 0 : 1;
}
