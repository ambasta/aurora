// Narrow Linux/x86-64 bootstrap signal observer, not an Aurora API or ABI.
// Compiled freestanding: no libc, allocation, formatting, or runtime startup.
// The Linux ucontext declaration is a host adapter dependency only.
#include <cstdint>
#include <csignal>
#include <ucontext.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error "The integer oracle signal observer requires Linux x86-64"
#endif

namespace {
constexpr std::uint64_t magic = 0x4155524f52414654ULL;
constexpr unsigned long restore_mask = 0x04000000UL; // Linux x86-64 SA_RESTORER.

// Raw kernel rt_sigaction layout, distinct from glibc's sigaction layout.
class KernelAction {
public:
    void (*handler)(int, siginfo_t *, void *);
    unsigned long flags;
    void (*restorer)();
    unsigned long mask;
};
static_assert(sizeof(KernelAction) == 32);

class FaultRecord {
public:
    std::uint64_t identity;
    std::uint64_t signal;
    std::uint64_t pc;
    std::uint64_t instruction;
    std::int64_t code;
};
static_assert(sizeof(FaultRecord) == 40);

extern "C" __attribute__((naked)) void aurora_integer_signal_return() {
    __asm__ volatile("movq $15, %rax\n\tsyscall"); // Linux rt_sigreturn.
}

void record_fault(int signal, siginfo_t *information, void *raw_context) {
    const auto *context = static_cast<const ucontext_t *>(raw_context);
    const auto pc = static_cast<std::uint64_t>(context->uc_mcontext.gregs[REG_RIP]);
    const auto *instruction = reinterpret_cast<const volatile unsigned char *>(pc);
    const FaultRecord record{magic,
                             static_cast<std::uint64_t>(signal),
                             pc,
                             static_cast<std::uint64_t>(instruction[0]) |
                                 (static_cast<std::uint64_t>(instruction[1]) << 8),
                             information->si_code};
    long written;
    __asm__ volatile("syscall"
                     : "=a"(written)
                     : "0"(1L), "D"(2L), "S"(&record), "d"(sizeof(record))
                     : "rcx", "r11", "memory");
    (void)written; // The Python side requires exactly one complete record.
    // SA_RESETHAND already restored the default action. Returning via sigreturn
    // restores the original instruction; its next fault really terminates the
    // process. No exit-code simulation or alternate injected signal is used.
}
} // namespace

extern "C" long aurora_install_integer_signal_observer() {
    const KernelAction action{record_fault,
                              static_cast<unsigned long>(SA_SIGINFO | SA_RESETHAND) | restore_mask,
                              aurora_integer_signal_return,
                              0};
    const int signals[] = {SIGILL, SIGFPE, SIGSEGV, SIGABRT};
    for (int signal : signals) {
        long result;
        register unsigned long mask_size __asm__("r10") = sizeof(action.mask);
        __asm__ volatile("syscall"
                         : "=a"(result)
                         : "0"(13L), "D"(static_cast<long>(signal)), "S"(&action), "d"(0L), "r"(mask_size)
                         : "rcx", "r11", "memory");
        if (result != 0)
            return result;
    }
    return 0;
}
