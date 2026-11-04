#include "../kernel/schedule-policy.hpp"
#include "../kernel/retained-scheduler.hpp"
#include <cstdlib>
#include <limits>
#include <cassert>
#include <iostream>

namespace kernel_schedule {
using namespace aurora::user;
using namespace aurora::scheduler;
class OwnerPlatform final {
public:
    static auto quiet() -> bool {
        return true;
    }
    [[noreturn]] static auto fail() -> void {
        std::abort();
    }
};
using Owner = Root<OwnerPlatform>;

auto retire(Owner &owner, Binding binding) -> void {
    assert(owner.phase(binding.slot) == Phase::retiring);
    assert(owner.select().action == Select::rejected);
    assert(!owner.admit(binding.slot, binding.stamp + 10, 24));
    assert(!owner.observe_tick(binding));
    assert(owner.finish_restore(binding) == Finish::rejected);
    assert(!owner.ack_retired({binding.slot, binding.stamp, binding.sequence + 1}));
    assert(owner.ack_retired(binding));
    assert(owner.phase(binding.slot) == Phase::retired);
    assert(!owner.ack_retired(binding));
}

auto owner_cases() -> void {
    Owner owner;
    owner.create();
    assert(owner.select().action == Select::idle && !owner.complete());
    assert(!owner.admit(3, 1, 24) && !owner.admit(0, 0, 24) && !owner.admit(0, 1, 0));
    assert(owner.admit(0, 101, 256));
    assert(!owner.admit(0, 102, 24) && !owner.admit(1, 101, 24));
    assert(owner.admit(1, 102, 24) && owner.admit(2, 103, 256));
    Binding first;
    for (U64 round = 0; round < 24; ++round) {
        for (U64 slot = 0; slot < 3; ++slot) {
            const auto selected = owner.select();
            const auto binding = selected.binding;
            assert(selected.action == Select::selected && binding.slot == slot && binding.stamp == 101 + slot);
            assert(binding.sequence == round * 3 + slot + 1);
            if (round == 0 && slot == 0)
                first = binding;
            assert(owner.phase(slot) == Phase::dispatched && owner.used(slot) == round);
            assert(owner.select().action == Select::rejected);
            assert(owner.finish_restore(binding) == Finish::rejected && !owner.ack_retired(binding));
            assert(!owner.observe_tick({3, binding.stamp, binding.sequence}));
            assert(!owner.observe_tick({slot, binding.stamp + 1, binding.sequence}));
            assert(!owner.observe_tick({slot, binding.stamp, binding.sequence + 1}));
            for (const auto invalid : {Terminal::none, Terminal::tick, static_cast<Terminal>(255)})
                assert(!owner.observe_terminal(binding, invalid));
            assert(owner.used(slot) == round && owner.phase(slot) == Phase::dispatched);
            assert(owner.observe_tick(binding));
            const U64 limit = slot == 1 ? 24 : 256;
            assert(owner.used(slot) == round + 1 && owner.remaining(slot) == limit - round - 1);
            assert(owner.reason(slot) == Terminal::tick && owner.phase(slot) == Phase::observed);
            assert(!owner.observe_tick(binding) && !owner.observe_terminal(binding, Terminal::returned));
            assert(!owner.ack_retired(binding));
            const bool exhausted = slot == 1 && round == 23;
            assert(owner.finish_restore(binding) == (exhausted ? Finish::retiring : Finish::runnable));
            assert(owner.finish_restore(binding) == Finish::rejected);
            if (exhausted)
                retire(owner, binding);
            else
                assert(owner.reason(slot) == Terminal::none);
        }
    }
    assert(owner.used(1) == 24 && owner.remaining(1) == 0);
    for (const U64 slot : {0ULL, 2ULL}) {
        const auto selected = owner.select();
        assert(selected.action == Select::selected && selected.binding.slot == slot);
        const auto terminal = slot == 0 ? Terminal::returned : Terminal::bounds;
        assert(owner.observe_terminal(selected.binding, terminal));
        assert(owner.reason(slot) == terminal && owner.used(slot) == 24 && owner.remaining(slot) == 232);
        assert(owner.finish_restore(selected.binding) == Finish::retiring);
        retire(owner, selected.binding);
    }
    assert(owner.complete() && owner.select().action == Select::idle);
    assert(!owner.admit(0, 103, 2));
    assert(owner.admit(0, 104, 2) && !owner.complete());
    assert(owner.used(0) == 0 && owner.remaining(0) == 2);
    for (U64 tick = 0; tick < 2; ++tick) {
        const auto selected = owner.select();
        assert(selected.action == Select::selected && selected.binding.slot == 0 && selected.binding.stamp == 104);
        assert(!owner.observe_tick(first) && !owner.ack_retired(first));
        assert(owner.observe_tick(selected.binding));
        assert(owner.finish_restore(selected.binding) == (tick == 0 ? Finish::runnable : Finish::retiring));
        if (tick == 1)
            retire(owner, selected.binding);
    }
    assert(owner.complete());
    for (const auto terminal :
         {Terminal::returned, Terminal::bounds, Terminal::overflow, Terminal::division_zero, Terminal::shift_count}) {
        Owner single;
        single.create();
        assert(single.admit(0, 1, std::numeric_limits<U64>::max()));
        auto selected = single.select();
        assert(selected.action == Select::selected && single.observe_tick(selected.binding));
        assert(single.used(0) == 1 && single.remaining(0) == std::numeric_limits<U64>::max() - 1);
        assert(single.finish_restore(selected.binding) == Finish::runnable);
        selected = single.select();
        assert(single.observe_terminal(selected.binding, terminal));
        assert(single.reason(0) == terminal && single.used(0) == 1);
        assert(single.finish_restore(selected.binding) == Finish::retiring);
        retire(single, selected.binding);
    }
}
auto main() -> int {
    const ProgramContract contract{0x1b0000, 1024, 0x1b0100, 0x1b0200, 0x1b0300};
    IntegerContext context;
    context.fresh(contract);
    assert(context.valid(contract));
    for (std::size_t i = 0; i < 15; ++i)
        assert(context.words()[i] == 0);
    for (const auto bit : {8U, 12U, 13U, 14U, 17U, 18U, 19U, 20U, 21U, 63U}) {
        auto invalid = context;
        invalid.words()[19] |= 1ULL << bit;
        assert(!invalid.valid(contract));
    }
    for (const auto bit : {1U, 9U}) {
        auto invalid = context;
        invalid.words()[19] &= ~(1ULL << bit);
        assert(!invalid.valid(contract));
    }
    for (const auto index : {18U, 21U}) {
        auto invalid = context;
        invalid.words()[index] = 8;
        assert(!invalid.valid(contract));
    }
    for (const auto sp : {0ULL, 0x1dffffULL, 0x1e0001ULL, 0x1e4008ULL}) {
        auto invalid = context;
        invalid.words()[20] = sp;
        assert(!invalid.valid(contract));
    }
    for (const auto pc : {0ULL, 0x1affffULL, 0x1b0400ULL, 0xffffffffffffffffULL}) {
        auto invalid = context;
        invalid.words()[17] = pc;
        assert(!invalid.valid(contract));
    }
    context.words()[15] = 129;
    context.words()[17] = contract.return_pc();
    assert(context.terminal(contract) == ProgramEvent::returned);
    context.words()[19] |= 0x400;
    assert(context.valid(contract));
    assert(context.terminal(contract) == ProgramEvent::rejected); // DF forbidden at scalar return.
    context.words()[19] &= ~0x400ULL;
    context.words()[15] = 6;
    context.words()[17] = contract.bounds_pc();
    assert(context.terminal(contract) == ProgramEvent::bounds);
    context.words()[17]++;
    assert(context.terminal(contract) == ProgramEvent::rejected);
    context = IntegerContext{};
    assert(!context.valid(contract));
    owner_cases();
    std::cout << "PASS: integer context, privileged flags, snapshot reset, exact trap/return and bounded slices\n";
    return 0;
}
} // namespace kernel_schedule
