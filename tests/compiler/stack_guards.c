// Linux/x86-64 host test adapter only. Never changes the process's real stack
// mapping, host limits, or kernel settings. Every generated call runs in a
// disposable fork child; negative children exit from an alternate-stack handler.
#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <ucontext.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__)
#error "stack guard fixtures require x86-64 Linux"
#endif

enum { PAGE_BYTES = 4096, ALT_BYTES = 65536, FAIL = 91, HANDLER_FAIL = 92 };
#define RECORD_MAGIC UINT64_C(0x4755415244505242)

typedef long (*generated_function)(long);
#define FRAME_DECL(bytes) \
    extern long guard_frame_##bytes(long); \
    extern const unsigned char guard_probe_guard_frame_##bytes##_1[]
FRAME_DECL(4080);
FRAME_DECL(4096);
FRAME_DECL(4112);
FRAME_DECL(8192);
FRAME_DECL(65536);
extern const unsigned char guard_probe_guard_frame_4112_2[];
extern const unsigned char guard_probe_guard_frame_65536_16[];
extern long guard_call_even(long);
extern long guard_call_odd(long);
extern long guard_recursive(long);
extern const unsigned char guard_probe_guard_call_even_2[];
extern const unsigned char guard_probe_guard_call_odd_2[];
extern const unsigned char guard_probe_guard_recursive_1[];

// Offsets 0..80 match stack_guards.S. All generated scalar entrypoints below are
// reached through the reviewed assembly adapter, not a new Aurora foreign ABI.
struct observation {
    uint64_t expected_top, actual_top, result;
    uint64_t rbp, rbx, r12, r13, r14, r15;
    uint64_t saved_rsp, restored_rsp;
};
struct observation guard_observed;
_Static_assert(sizeof(struct observation) == 88, "assembly observation size");
_Static_assert(offsetof(struct observation, saved_rsp) == 72, "assembly scratch offset");
_Static_assert(offsetof(struct observation, restored_rsp) == 80, "assembly restore offset");
extern void guard_switch(generated_function function, void *top, long argument);

struct fault_record {
    uint64_t magic;
    int32_t signal_number, signal_code;
    uintptr_t address, rip, rsp, handler_sp;
};
_Static_assert(sizeof(struct fault_record) == 48, "one small atomic pipe record");
static volatile sig_atomic_t fault_fd = -1;
static uintptr_t alt_low, alt_high;

static void fault_handler(int signal_number, siginfo_t *info, void *context) {
    struct fault_record record;
    const uintptr_t handler_sp = (uintptr_t)&record;
    // Plain bounds checks happen on the alternate stack before using libc.
    // No formatting, allocation, unwinding, recovery, or second generated call.
    if (handler_sp < alt_low || handler_sp > alt_high - sizeof(record))
        _exit(HANDLER_FAIL);
    const ucontext_t *machine = (const ucontext_t *)context;
    record.magic = RECORD_MAGIC;
    record.signal_number = signal_number;
    record.signal_code = info->si_code;
    record.address = (uintptr_t)info->si_addr;
    record.rip = (uintptr_t)machine->uc_mcontext.gregs[REG_RIP];
    record.rsp = (uintptr_t)machine->uc_mcontext.gregs[REG_RSP];
    record.handler_sp = handler_sp;
    if (write(fault_fd, &record, sizeof(record)) != (ssize_t)sizeof(record))
        _exit(HANDLER_FAIL);
    _exit(128 + signal_number);
}

struct guard_case {
    const char *name;
    generated_function function;
    size_t top_offset;
    long argument, expected_result;
    const unsigned char *fault_pc; // NULL means a successful return is required.
    ptrdiff_t fault_offset;        // Exact expected RSP/si_addr from writable base.
};

static const struct guard_case cases[] = {
    {"fit-subpage", guard_frame_4080, 4096, 0, 42, NULL, 0},
    {"fit-page", guard_frame_4096, 4112, 0, 42, NULL, 0},
    {"fit-tail", guard_frame_4112, 4128, 0, 42, NULL, 0},
    {"fit-two-page", guard_frame_8192, 8208, 0, 42, NULL, 0},
    {"fit-max", guard_frame_65536, 65552, 0, 42, NULL, 0},
    {"guard-page", guard_frame_4096, 4096, 0, 0, guard_probe_guard_frame_4096_1, -16},
    // The full-page probe reaches the writable boundary; its tail then faults.
    {"guard-tail", guard_frame_4112, 4112, 0, 0, guard_probe_guard_frame_4112_2, -16},
    // First actual probe faults. A skipped 8192-byte reservation would put the
    // bottom-slot store 16 bytes before the end of the writable landing page.
    {"guard-two-page", guard_frame_8192, 4096, 0, 0, guard_probe_guard_frame_8192_1, -16},
    {"guard-max", guard_frame_65536, 65536, 0, 0, guard_probe_guard_frame_65536_16, -16},
    // Independent byte accounting: entry call+RBP 16, local frame 32, record 16,
    // nested call+RBP 16, target frame 32. Odd adds live operand 8 + alignment 8.
    {"fit-cumulative-even", guard_call_even, 112, 0, 42, NULL, 0},
    {"fit-cumulative-odd", guard_call_odd, 128, 0, 43, NULL, 0},
    {"guard-cumulative-even", guard_call_even, 48, 0, 0, guard_probe_guard_call_even_2, -16},
    {"guard-cumulative-odd", guard_call_odd, 64, 0, 0, guard_probe_guard_call_odd_2, -8},
    // Each level reserves 512 plus return/RBP 16. At level 8, 4096 - 8*528 = -128.
    // The previous level still has 400 bytes, so no call/push is the guard fault.
    {"fit-recursion", guard_recursive, 2128, 3, 42, NULL, 0},
    {"guard-recursion", guard_recursive, 4096, 64, 0, guard_probe_guard_recursive_1, -128},
};

static unsigned char canary(size_t index) {
    return (unsigned char)((index * 37U + 0xa5U) & 255U);
}

static int check_return(const struct guard_case *test) {
    return guard_observed.actual_top == guard_observed.expected_top &&
           guard_observed.result == (uint64_t)test->expected_result &&
           guard_observed.rbp == UINT64_C(0x1122334455667788) &&
           guard_observed.rbx == UINT64_C(0x2233445566778899) &&
           guard_observed.r12 == UINT64_C(0x33445566778899aa) &&
           guard_observed.r13 == UINT64_C(0x445566778899aabb) &&
           guard_observed.r14 == UINT64_C(0x5566778899aabbcc) &&
           guard_observed.r15 == UINT64_C(0x66778899aabbccdd) &&
           guard_observed.saved_rsp == guard_observed.restored_rsp;
}

static void child_case(const struct guard_case *test, unsigned char *writable,
                       size_t writable_bytes, void *alternate, int write_fd) {
    // A stuck target must terminate before run()'s 60-second harness timeout.
    // Alarm state/default disposition is child-local; no new process group or
    // supervisor is created, and the parent waits/reaps this exact child.
    struct sigaction timeout_action = {0};
    timeout_action.sa_handler = SIG_DFL;
    sigset_t unblock_alarm;
    if (sigemptyset(&timeout_action.sa_mask) != 0 ||
        sigaction(SIGALRM, &timeout_action, NULL) != 0 ||
        sigemptyset(&unblock_alarm) != 0 || sigaddset(&unblock_alarm, SIGALRM) != 0 ||
        sigprocmask(SIG_UNBLOCK, &unblock_alarm, NULL) != 0)
        _exit(FAIL);
    alarm(5);
    // Handler-visible statics are initialized before sigaction and never changed
    // afterward in this single-threaded child.
    fault_fd = write_fd;
    alt_low = (uintptr_t)alternate;
    alt_high = alt_low + ALT_BYTES;
    if (mprotect(writable, writable_bytes, PROT_READ | PROT_WRITE) != 0 ||
        mprotect(alternate, ALT_BYTES, PROT_READ | PROT_WRITE) != 0)
        _exit(FAIL);
    stack_t stack = {.ss_sp = alternate, .ss_flags = 0, .ss_size = ALT_BYTES};
    if (sigaltstack(&stack, NULL) != 0)
        _exit(FAIL);
    struct sigaction action = {0};
    action.sa_sigaction = fault_handler;
    action.sa_flags = SA_SIGINFO | SA_ONSTACK;
    if (sigemptyset(&action.sa_mask) != 0 || sigaction(SIGSEGV, &action, NULL) != 0)
        _exit(FAIL);
    sigset_t unblock;
    if (sigemptyset(&unblock) != 0 || sigaddset(&unblock, SIGSEGV) != 0 ||
        sigprocmask(SIG_UNBLOCK, &unblock, NULL) != 0)
        _exit(FAIL);
    guard_switch(test->function, writable + test->top_offset, test->argument);
    // No faulting child attempts restoration. Reaching here in a negative case
    // is a hard failure, even if the emitted body returned its expected value.
    if (test->fault_pc != NULL || !check_return(test))
        _exit(FAIL);
    _exit(0);
}

static int test_case(const struct guard_case *test) {
    // Parent maps only inside this disposable ABI subprocess. Its view has just
    // one writable shared landing page. The stack and separate alternate mapping
    // become writable only in the fork child, never in the observing parent.
    const size_t writable_bytes = (test->top_offset + PAGE_BYTES - 1) / PAGE_BYTES * PAGE_BYTES;
    const size_t mapping_bytes = 2 * PAGE_BYTES + writable_bytes;
    unsigned char *mapping = mmap(NULL, mapping_bytes, PROT_NONE,
                                  MAP_SHARED | MAP_ANONYMOUS, -1, 0);
    if (mapping == MAP_FAILED) {
        perror("mmap test region");
        return FAIL;
    }
    void *alternate = mmap(NULL, ALT_BYTES, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (alternate == MAP_FAILED || mprotect(mapping, PAGE_BYTES, PROT_READ | PROT_WRITE) != 0) {
        perror("map landing/alternate");
        if (alternate != MAP_FAILED)
            munmap(alternate, ALT_BYTES);
        munmap(mapping, mapping_bytes);
        return FAIL;
    }
    for (size_t index = 0; index < PAGE_BYTES; ++index)
        mapping[index] = canary(index);
    int descriptors[2];
    if (pipe(descriptors) != 0) {
        perror("pipe");
        munmap(alternate, ALT_BYTES);
        munmap(mapping, mapping_bytes);
        return FAIL;
    }
    const pid_t child = fork();
    if (child == 0) {
        close(descriptors[0]);
        child_case(test, mapping + 2 * PAGE_BYTES, writable_bytes, alternate, descriptors[1]);
        _exit(FAIL);
    }
    close(descriptors[1]);
    int status = 0;
    pid_t waited = -1;
    if (child > 0) {
        do {
            waited = waitpid(child, &status, 0);
        } while (waited == -1 && errno == EINTR);
    }
    struct fault_record record = {0};
    // Child sends at most one 48-byte record, below PIPE_BUF; waiting before
    // reading cannot fill the pipe. EOF is also checked; no partial/extra record.
    ssize_t received;
    do {
        received = read(descriptors[0], &record, sizeof(record));
    } while (received == -1 && errno == EINTR);
    unsigned char extra;
    ssize_t trailing;
    do {
        trailing = read(descriptors[0], &extra, 1);
    } while (trailing == -1 && errno == EINTR);
    close(descriptors[0]);
    int okay = waited == child && child > 0 && WIFEXITED(status) && trailing == 0;
    for (size_t index = 0; index < PAGE_BYTES; ++index)
        if (mapping[index] != canary(index))
            okay = 0;
    if (test->fault_pc == NULL) {
        okay = okay && WEXITSTATUS(status) == 0 && received == 0;
    } else {
        const uintptr_t writable = (uintptr_t)mapping + 2 * PAGE_BYTES;
        const uintptr_t expected_address = writable - (uintptr_t)(-test->fault_offset);
        okay = okay && WEXITSTATUS(status) == 128 + SIGSEGV && received == (ssize_t)sizeof(record) &&
               record.magic == RECORD_MAGIC && record.signal_number == SIGSEGV &&
               record.signal_code == SEGV_ACCERR && record.address == expected_address &&
               record.rsp == expected_address && record.address >= writable - PAGE_BYTES &&
               record.address < writable && record.rip == (uintptr_t)test->fault_pc &&
               record.handler_sp >= (uintptr_t)alternate &&
               record.handler_sp <= (uintptr_t)alternate + ALT_BYTES - sizeof(record);
    }
    if (!okay)
        fprintf(stderr, "%s failed: wait=%ld status=%d bytes=%ld pc=%" PRIxPTR
                        " address=%" PRIxPTR " rsp=%" PRIxPTR "\n",
                test->name, (long)waited, status, (long)received, record.rip, record.address, record.rsp);
    if (munmap(alternate, ALT_BYTES) != 0 || munmap(mapping, mapping_bytes) != 0)
        okay = 0;
    return okay ? 0 : FAIL;
}

int main(int argc, char **argv) {
    struct rlimit core;
    if (sysconf(_SC_PAGESIZE) != PAGE_BYTES || sizeof(void *) != 8 ||
        getrlimit(RLIMIT_CORE, &core) != 0 || core.rlim_cur != 0 || core.rlim_max != 0) {
        fputs("requires x86-64 Linux, 4096-byte pages and inherited core0 soft/hard limits\n", stderr);
        return FAIL;
    }
    if (argc != 2) {
        fputs("usage: stack-guards CASE\n", stderr);
        return FAIL;
    }
    for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); ++index)
        if (strcmp(argv[1], cases[index].name) == 0)
            return test_case(&cases[index]);
    fputs("unknown guard fixture\n", stderr);
    return FAIL;
}
