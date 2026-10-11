#include "../kernel/schedule-policy.hpp"
#include <cassert>
#include <iostream>
using namespace aurora::user;
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
    SliceBudget budget{24};
    for (unsigned i = 0; i < 24; ++i)
        assert(budget.consume() && budget.used() == i + 1);
    assert(budget.exhausted() && !budget.consume() && budget.used() == 24);
    SliceBudget empty{0};
    assert(empty.exhausted() && !empty.consume());
    std::cout << "PASS: integer context, privileged flags, snapshot reset, exact trap/return and bounded slices\n";
}
