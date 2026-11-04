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

extern "C" bool __au_test_ap_worker_budget_case(bool);

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
auto observation(const ap::Plan &plan, I64 result, U64 status = 0) -> ap::Observation {
    return {1, plan.incarnation, plan.sequence, result, status};
}
auto complete(Owner &owner, const ap::Plan &plan, I64 result) -> void {
    check(plan.incarnation == 7 && plan.sequence && owner.stage() == ap::Stage::reserved);
    check(owner.published(plan.incarnation, plan.sequence));
    const auto ordinal = owner.reserve_observation(plan.incarnation, plan.sequence);
    check(ordinal && owner.observe(observation(plan, result), ordinal, 3579546));
    check(owner.stage() == ap::Stage::completion_selected && owner.result() == result);
    check(owner.acknowledged(plan.incarnation, plan.sequence));
}
auto helper_cases() -> void {
    // Published CRC32C check vector and empty CRC; no duplicate CRC algorithm.
    std::uint8_t bytes[4096]{};
    constexpr char vector[] = "123456789";
    for (unsigned i = 0; i != 9; ++i)
        bytes[i] = vector[i];
    struct Case {
        I64 offset, count, length;
        U64 status, result;
    };
    constexpr Case cases[] = {
        {0, 9, 4096, 0, 0xe3069283},
        {0, 0, 4096, 0, 0},
        {4096, 0, 4096, 0, 0},
        {4095, 1, 4096, 0, 0x527d5351},
        {-1, 1, 4096, 1, 0},
        {4097, 0, 4096, 1, 0},
        {4096, 1, 4096, 1, 0},
        {0, -1, 4096, 1, 0},
        {0, 1025, 4096, 1, 0},
        {4090, 7, 4096, 1, 0},
        {0, 0, 4095, 1, 0},
        {0, 0, -1, 1, 0},
        {0, std::numeric_limits<I64>::min(), 4096, 1, 0},
        {std::numeric_limits<I64>::min(), 1, 4096, 1, 0},
        {std::numeric_limits<I64>::max(), 1, 4096, 1, 0},
        {0, std::numeric_limits<I64>::max(), 4096, 1, 0},
    };
    for (const auto &item : cases) {
        ap::ChecksumResult result;
        ap::__au_runtime_ap_worker_crc32c(&result, bytes, item.length, item.offset, item.count);
        check(result.status == item.status && result.value == item.result);
    }
    ap::ChecksumResult maximum;
    ap::__au_runtime_ap_worker_crc32c(&maximum, bytes, 4096, 3072, 1024);
    check(maximum.status == 0 && maximum.value <= UINT32_MAX);
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
    for (const auto pair : {ap::Plan{0, 0, -1, 1},
                            ap::Plan{0, 0, 4097, 0},
                            ap::Plan{0, 0, 4096, 1},
                            ap::Plan{0, 0, 0, -1},
                            ap::Plan{0, 0, 0, 1025}})
        check(!owner.reserve(pair.start, pair.count).sequence);
    check(owner.stage() == ap::Stage::idle && owner.used() == 0 && owner.sequence() == 0);
    const auto first = owner.reserve(10, 4);
    check(first.sequence == 1 && first.start == 10 && first.count == 4);
    check(owner.used() == 4 && owner.remaining() == 4092 && owner.jobs() == 1);
    check(!owner.reserve(1, 1).sequence && !owner.reserve_observation(7, 1));
    check(!owner.acknowledged(7, 1) && !owner.published(8, 1) && !owner.published(7, 2));
    check(owner.published(7, 1) && !owner.published(7, 1));
    const auto ordinal = owner.reserve_observation(7, 1);
    check(ordinal == 1 && owner.attempts() == 1 && !owner.reserve_observation(7, 1));
    for (const auto foreign :
         {ap::Observation{2, 7, 1, 0, 0}, ap::Observation{1, 8, 1, 0, 0}, ap::Observation{1, 7, 0, 0, 0}})
        check(!owner.observe(foreign, ordinal, 0) && owner.stage() == ap::Stage::observation_reserved);
    check(!owner.observe(observation(first, 0), 0, 0));
    check(owner.observe(observation(first, 0, 1), ordinal, 17));
    check(owner.stage() == ap::Stage::running && owner.ticks() == 3579529 && owner.attempts() == 1);
    check(!owner.observe(observation(first, 0), ordinal, 0));
    const auto second_ordinal = owner.reserve_observation(7, 1);
    check(second_ordinal == 2 && !owner.observe(observation(first, 0), ordinal, 0));
    check(owner.observe(observation(first, 0), second_ordinal, 16777215));
    check(!owner.observe(observation(first, 0), second_ordinal, 0) && owner.acknowledged(7, 1));
    check(!owner.acknowledged(7, 1));
    const auto second = owner.reserve(4096, 0);
    check(second.sequence == 2 && owner.used() == 4 && owner.attempts() == 0 && owner.ticks() == 3579546);
    check(owner.published(7, 2));
    const auto third_ordinal = owner.reserve_observation(7, 2);
    check(third_ordinal == 3 && !owner.observe(observation(first, 0), second_ordinal, 0));
    check(owner.observe(observation(second, 0), third_ordinal, 0) && owner.acknowledged(7, 2));
    check(owner.stage() == ap::Stage::idle && owner.result() == 0);
}
auto exhaustion_cases() -> void {
    for (bool empty : {false, true}) {
        Owner owner;
        ready(owner);
        const U64 limit = empty ? 8 : 4;
        for (U64 sequence = 1; sequence <= limit; ++sequence)
            complete(owner, owner.reserve(empty ? 4096 : 0, empty ? 0 : 1024), 0);
        check(owner.stage() == ap::Stage::exhausted && owner.jobs() == limit && owner.used() == (empty ? 0 : 4096));
        check(!owner.reserve(0, 0).sequence && !owner.fail() && owner.stage() == ap::Stage::exhausted);
        check(!owner.begin_start(1, 8) && !owner.acknowledged(7, limit));
    }
    Owner owner;
    ready(owner);
    for (unsigned i = 0; i != 3; ++i)
        complete(owner, owner.reserve(0, 1024), 0);
    complete(owner, owner.reserve(0, 1023), 0);
    check(owner.remaining() == 1 && !owner.reserve(0, 2).sequence);
    check(owner.stage() == ap::Stage::exhausted && owner.used() == 4095 && owner.sequence() == 4);
}
auto malformed_cases() -> void {
    for (const auto bad : {ap::Observation{1, 7, 1, -1, 0},
                           ap::Observation{1, 7, 1, 4294967296, 0},
                           ap::Observation{1, 7, 1, 0, 2},
                           ap::Observation{1, 7, 2, 0, 0},
                           ap::Observation{1, 7, UINT64_MAX, 0, 0}}) {
        Owner owner;
        ready(owner);
        const auto plan = owner.reserve(10, 4);
        check(owner.published(7, 1));
        const auto ordinal = owner.reserve_observation(7, 1);
        check(!owner.observe(bad, ordinal, 0) && owner.stage() == ap::Stage::failed);
        check(owner.used() == 4 && owner.sequence() == 1 && owner.attempts() == 1);
        check(!owner.observe(observation(plan, 0), ordinal, 0) && !owner.acknowledged(7, 1));
        check(!owner.reserve(1, 1).sequence && !owner.begin_start(1, 8));
    }
    // A bound future ordinal closes even before any observation was reserved.
    Owner owner;
    ready(owner);
    const auto plan = owner.reserve(0, 0);
    check(!owner.observe(observation(plan, 0), 1, 0) && owner.stage() == ap::Stage::failed);
}
auto timing_cases() -> void {
    for (U64 delta : {U64(3579546), U64(3579547), U64(16777215), U64(16777216), U64(UINT64_MAX)}) {
        Owner owner;
        ready(owner);
        const auto plan = owner.reserve(0, 0);
        check(owner.published(7, 1));
        const auto ordinal = owner.reserve_observation(7, 1);
        check(!owner.observe(observation(plan, 0, 1), ordinal, delta));
        check(owner.stage() == ap::Stage::failed && !owner.reserve_observation(7, 1));
    }
    Owner owner;
    ready(owner);
    const auto plan = owner.reserve(0, 0);
    check(owner.published(7, 1));
    auto ordinal = owner.reserve_observation(7, 1);
    check(owner.observe(observation(plan, 0, 1), ordinal, 3579545) && owner.ticks() == 1);
    ordinal = owner.reserve_observation(7, 1);
    check(!owner.observe(observation(plan, 0, 1), ordinal, 1) && owner.stage() == ap::Stage::failed);
    check(owner.attempts() == 2 && !owner.observe(observation(plan, 0), ordinal, 0));
}
auto failure_cases() -> void {
    for (unsigned step = 0; step <= 7; ++step) {
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
            check(owner.reserve_observation(7, 1) == 1);
        if (step >= 7)
            check(owner.observe({1, 7, 1, 1, 0}, 1, 0));
        const auto used = owner.used(), sequence = owner.sequence(), attempts = owner.attempts();
        check(!owner.fail() && owner.stage() == ap::Stage::failed && !owner.fail());
        check(!owner.begin_start(1, 7) && !owner.startup_sent(1, 7) && !owner.ready(1, 7));
        check(!owner.reserve(1, 1).sequence && !owner.published(7, 1) && !owner.acknowledged(7, 1));
        check(!owner.reserve_observation(7, 1) && !owner.observe({1, 7, 1, 0, 0}, 1, 0));
        check(owner.used() == used && owner.sequence() == sequence && owner.attempts() == attempts);
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
    timing_cases();
    check(__au_test_ap_worker_budget_case(false));
    check(__au_test_ap_worker_budget_case(true));
    failure_cases();
    context_cases();
    std::printf("AP worker: %u checks passed\n", checks);
    return 0;
}
} // namespace kernel_ap_worker
