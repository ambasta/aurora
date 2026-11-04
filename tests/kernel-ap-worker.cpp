// Actual compiled Aurora helper and retained owner, through their production
// native bridges. Hosted identities test adapter refusal, not physical AP proof.
#include "../kernel/retained-ap-worker.hpp"
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <initializer_list>
#include <type_traits>
#include <sys/wait.h>
#include <unistd.h>

namespace kernel_ap_worker {
namespace ap = aurora::ap;
using ap::I64;
using ap::U64;
unsigned checks{};
auto check(bool accepted) -> void {
    ++checks;
    if (!accepted) {
        std::fprintf(stderr, "AP worker failure %u\n", checks);
        std::abort();
    }
}
class Platform final {
public:
    static inline const void *root{};
    static inline U64 current_root = 0x1000, expected_root = 0x1000, flags = 2, cpu = 0, bsp = 0;
    static inline unsigned reads = 0, change_after = 0;
    static auto authenticates(const void *owner) -> bool {
        return owner == root;
    }
    static auto quiet() -> bool {
        return current_root == expected_root && flags == 2 && cpu == bsp;
    }
    static auto context() -> U64 {
        ++reads;
        return change_after && reads >= change_after ? current_root + 4096 : current_root;
    }
    [[noreturn]] static void fail() {
        _exit(96);
    }
};
using Owner = ap::Root<Platform>;
static_assert(!std::is_copy_constructible_v<Owner> && !std::is_move_constructible_v<Owner>);
auto create(Owner &owner) -> void {
    Platform::root = &owner;
    owner.create();
    check(owner.created() && owner.stage() == ap::Stage::fresh && owner.sequence() == 0);
}
auto ready(Owner &owner) -> void {
    create(owner);
    check(owner.begin_start(1, 7));
    check(owner.startup_sent(1, 7));
    check(owner.ready(1, 7));
}
auto observation(const ap::Plan &plan, I64 result) -> ap::Observation {
    return {1, plan.incarnation, plan.sequence, result, 0};
}
auto complete(Owner &owner, const ap::Plan &plan, I64 result) -> void {
    check(plan.incarnation == 7 && plan.sequence && owner.stage() == ap::Stage::reserved);
    check(owner.published(plan.incarnation, plan.sequence));
    check(owner.observe(observation(plan, result)));
    check(owner.stage() == ap::Stage::completion_selected && owner.result() == result);
    check(owner.acknowledged(plan.incarnation, plan.sequence));
}
auto helper_cases() -> void {
    // Reviewed golden sums. The 1024-term endpoints use n(n+1)(2n+1)/6,
    // independently of the helper's iterative implementation.
    struct Case {
        I64 start, count, result;
    };
    constexpr Case cases[] = {
        {0, 1, 0},
        {1, 1, 1},
        {1, 3, 14},
        {2, 4, 54},
        {5, 3, 110},
        {10, 4, 534},
        {65535, 1, 4294836225},
        {65535, 2, 8589803521},
        {65535, 1024, 4466921004544},
        {0, 1024, 357389824},
        {1, 1024, 358438400},
        {-1, 1, -1},
        {65536, 1, -1},
        {0, 0, -1},
        {0, -1, -1},
        {0, 1025, -1},
        {std::numeric_limits<I64>::min(), 1, -1},
        {std::numeric_limits<I64>::max(), 1, -1},
        {0, std::numeric_limits<I64>::min(), -1},
        {0, std::numeric_limits<I64>::max(), -1},
    };
    for (const auto &item : cases)
        check(ap::__au_runtime_ap_worker_sum_squares(item.start, item.count) == item.result);
}
auto startup_cases() -> void {
    Owner owner;
    create(owner);
    check(!owner.begin_start(256, 7) && !owner.begin_start(1, 0));
    check(owner.stage() == ap::Stage::fresh && !owner.ready(1, 7) && !owner.startup_sent(1, 7));
    check(!owner.reserve(1, 1).sequence && owner.used() == 0);
    check(owner.begin_start(1, 7));
    check(owner.stage() == ap::Stage::startup_reserved && owner.target() == 1 && owner.incarnation() == 7);
    check(!owner.begin_start(1, 7) && !owner.begin_start(2, 8));
    check(!owner.ready(1, 7) && !owner.startup_sent(2, 7) && !owner.startup_sent(1, 8));
    check(owner.stage() == ap::Stage::startup_reserved && owner.startup_sent(1, 7));
    check(!owner.startup_sent(1, 7) && !owner.ready(2, 7) && !owner.ready(1, 8));
    check(owner.stage() == ap::Stage::starting && owner.ready(1, 7));
    check(!owner.ready(1, 7) && !owner.begin_start(1, 7));
    check(owner.stage() == ap::Stage::idle && owner.remaining() == 4096);
}
auto receipt_cases() -> void {
    Owner owner;
    ready(owner);
    for (const auto pair :
         {ap::Plan{0, 0, -1, 1}, ap::Plan{0, 0, 65536, 1}, ap::Plan{0, 0, 0, 0}, ap::Plan{0, 0, 0, 1025}})
        check(!owner.reserve(pair.start, pair.count).sequence);
    check(owner.stage() == ap::Stage::idle && owner.used() == 0 && owner.sequence() == 0);
    const auto first = owner.reserve(10, 4);
    check(first.sequence == 1 && first.start == 10 && first.count == 4);
    check(owner.used() == 4 && owner.remaining() == 4092 && owner.jobs() == 1);
    check(!owner.reserve(1, 1).sequence && !owner.observe(observation(first, 534)));
    check(!owner.acknowledged(7, 1) && !owner.published(8, 1) && !owner.published(7, 2));
    check(owner.stage() == ap::Stage::reserved && owner.used() == 4 && owner.published(7, 1));
    check(!owner.published(7, 1) && !owner.acknowledged(7, 1));
    for (const auto foreign :
         {ap::Observation{2, 7, 1, 534, 0}, ap::Observation{1, 8, 1, 534, 0}, ap::Observation{1, 7, 0, 534, 0}})
        check(!owner.observe(foreign) && owner.stage() == ap::Stage::running && owner.used() == 4);
    check(owner.observe(observation(first, 534)) && !owner.observe(observation(first, 534)));
    check(owner.stage() == ap::Stage::completion_selected && owner.acknowledged(7, 1));
    check(!owner.acknowledged(7, 1) && !owner.observe(observation(first, 534)));
    const auto second = owner.reserve(5, 3);
    check(second.sequence == 2 && owner.used() == 7 && owner.jobs() == 2);
    check(owner.published(7, 2));
    check(!owner.observe(observation(first, 534)) && owner.stage() == ap::Stage::running);
    check(owner.observe(observation(second, 110)) && owner.acknowledged(7, 2));
    check(owner.stage() == ap::Stage::idle && owner.sequence() == 2 && owner.result() == 110);
}
auto exhaustion_cases() -> void {
    {
        Owner owner;
        ready(owner);
        for (U64 sequence = 1; sequence <= 8; ++sequence) {
            const auto plan = owner.reserve(1, 1);
            check(plan.sequence == sequence);
            complete(owner, plan, 1);
        }
        check(owner.stage() == ap::Stage::exhausted && owner.jobs() == 8 && owner.used() == 8);
        check(!owner.reserve(1, 1).sequence && !owner.fail() && owner.stage() == ap::Stage::exhausted);
        check(!owner.begin_start(1, 8) && !owner.acknowledged(7, 8) && owner.sequence() == 8);
    }
    {
        Owner owner;
        ready(owner);
        for (U64 sequence = 1; sequence <= 4; ++sequence)
            complete(owner, owner.reserve(0, 1024), 357389824);
        check(owner.stage() == ap::Stage::exhausted && owner.used() == 4096 && owner.remaining() == 0);
        check(!owner.reserve(0, 1).sequence && owner.jobs() == 4);
    }
    {
        Owner owner;
        ready(owner);
        for (U64 sequence = 1; sequence <= 3; ++sequence)
            complete(owner, owner.reserve(0, 1024), 357389824);
        complete(owner, owner.reserve(0, 1023), 356343295);
        check(owner.remaining() == 1 && !owner.reserve(0, 2).sequence);
        check(owner.stage() == ap::Stage::exhausted && owner.used() == 4095 && owner.sequence() == 4);
    }
}
auto malformed_cases() -> void {
    for (const auto bad : {ap::Observation{1, 7, 1, -1, 0},
                           ap::Observation{1, 7, 1, 677, 0},
                           ap::Observation{1, 7, 1, 534, 1},
                           ap::Observation{1, 7, 2, 534, 0},
                           ap::Observation{1, 7, UINT64_MAX, 534, 0}}) {
        Owner owner;
        ready(owner);
        const auto plan = owner.reserve(10, 4);
        check(owner.published(7, 1) && !owner.observe(bad));
        check(owner.stage() == ap::Stage::failed && owner.used() == 4 && owner.sequence() == 1);
        check(!owner.observe(observation(plan, 534)) && !owner.acknowledged(7, 1));
        check(!owner.reserve(1, 1).sequence && !owner.begin_start(1, 8));
        check(owner.stage() == ap::Stage::failed && owner.result() == 0);
    }
}
auto failure_cases() -> void {
    for (unsigned step = 0; step <= 6; ++step) {
        Owner owner;
        create(owner);
        if (step >= 1)
            check(owner.begin_start(1, 7));
        if (step >= 2)
            check(owner.startup_sent(1, 7));
        if (step >= 3)
            check(owner.ready(1, 7));
        if (step >= 4)
            check(owner.reserve(1, 1).sequence == 1);
        if (step >= 5)
            check(owner.published(7, 1));
        if (step >= 6)
            check(owner.observe({1, 7, 1, 1, 0}));
        const auto used = owner.used(), sequence = owner.sequence();
        check(!owner.fail() && owner.stage() == ap::Stage::failed && !owner.fail());
        check(!owner.begin_start(1, 7) && !owner.startup_sent(1, 7) && !owner.ready(1, 7));
        check(!owner.reserve(1, 1).sequence && !owner.published(7, 1) && !owner.acknowledged(7, 1));
        check(owner.used() == used && owner.sequence() == sequence && owner.stage() == ap::Stage::failed);
    }
}
auto context_cases() -> void {
    for (unsigned mode = 0; mode < 7; ++mode) {
        const auto child = fork();
        check(child >= 0);
        if (!child) {
            Owner owner;
            create(owner);
            if (mode == 0)
                Platform::root = nullptr;
            if (mode == 1)
                Platform::cpu = 1;
            if (mode == 2)
                Platform::flags = 0x202;
            if (mode == 3)
                Platform::current_root = 0x2000;
            if (mode == 4) {
                Platform::reads = 0;
                Platform::change_after = 2;
            }
            if (mode == 5) {
                owner.create();
                _exit(0);
            }
            if (mode == 6) {
                Owner foreign;
                foreign.create();
                _exit(0);
            }
            (void)owner.begin_start(1, 7);
            _exit(0);
        }
        int status{};
        check(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 96);
    }
}
auto main() -> int {
    helper_cases();
    startup_cases();
    receipt_cases();
    exhaustion_cases();
    malformed_cases();
    failure_cases();
    context_cases();
    std::printf("AP worker: %u checks passed\n", checks);
    return 0;
}
} // namespace kernel_ap_worker
