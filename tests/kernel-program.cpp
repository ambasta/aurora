#include "../kernel/user-program.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <string_view>
#include <type_traits>
using namespace aurora::user;
using aurora::hardware::Protection;
static_assert(!std::is_copy_constructible_v<ProgramRun>);
auto check(bool condition, std::string_view message) -> void {
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}
auto context(std::uint64_t pc, std::uint64_t vector = 129, std::uint64_t error = 0,
    std::uint64_t cs = 0x1b, std::uint64_t ss = 0x23, std::uint64_t sp = Protection::user_stack_top,
    std::uint64_t flags = 2, std::uint64_t frame = 0x85f00) -> ProgramContext {
    return ProgramContext{vector, error, pc, cs, ss, sp, flags, frame};
}
auto main() -> int {
    constexpr auto base = std::uint64_t{0x1b0000};
    constexpr auto ret = base + 32, bounds = base + 64, overflow = base + 66, division = base + 68, shift = base + 70;
    const auto contract = ProgramContract{base, 128, ret, bounds, overflow, division, shift};
    const auto legacy = ProgramContract{base, 128, ret, bounds, overflow};
    const auto division_only = ProgramContract{base, 128, ret, bounds, overflow, division};
    const auto shift_only = ProgramContract{base, 128, ret, bounds, overflow, 0, shift};
    check(contract.valid(), "valid contract");
    check(contract.classify(context(ret)) == ProgramEvent::returned, "typed return");
    check(contract.classify(context(bounds, 6, 0, 0x1b, 0x23, Protection::user_stack_top - 32, 0x10002))
        == ProgramEvent::bounds, "bounds label with CPU resume flag");
    check(contract.classify(context(overflow, 6)) == ProgramEvent::overflow, "overflow label");
    check(contract.classify(context(division, 6)) == ProgramEvent::division_zero, "division-zero label");
    check(contract.classify(context(shift, 6)) == ProgramEvent::shift_count, "shift-count label");
    check(shift_only.valid() && shift_only.classify(context(shift, 6)) == ProgramEvent::shift_count,
        "shift metadata is independent of division metadata");
    check(legacy.valid() && legacy.division_zero_pc() == 0
        && legacy.classify(context(division, 6)) == ProgramEvent::rejected
        && legacy.classify(context(0, 6)) == ProgramEvent::rejected, "absent division site grants no authority");
    check(legacy.shift_count_pc() == 0 && division_only.valid() && division_only.shift_count_pc() == 0
        && legacy.classify(context(shift, 6)) == ProgramEvent::rejected
        && division_only.classify(context(shift, 6)) == ProgramEvent::rejected
        && division_only.classify(context(0, 6)) == ProgramEvent::rejected, "absent shift site grants no authority");
    const std::array invalid{
        context(ret + 1), context(ret + 4096), context(ret, 128), context(ret, 129, 1),
        context(ret, 129, 0, 8), context(ret, 129, 0, 0x3b), context(ret, 129, 0, 0x1b, 0x10),
        context(ret, 129, 0, 0x1b, 0x43),
        context(ret, 129, 0, 0x1b, 0x23, Protection::user_stack_top - 8),
        context(bounds, 6, 0, 0x1b, 0x23, Protection::user_stack_top + 8),
        context(bounds, 6, 0, 0x1b, 0x23, Protection::user_stack_bottom - 8),
        context(bounds, 6, 0, 0x1b, 0x23, Protection::user_stack_bottom + 1),
        context(ret, 129, 0, 0x1b, 0x23, Protection::user_stack_top, 0),
        context(ret, 129, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0),
        context(ret, 129, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0x85fff),
        context(ret, 129, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0x82001),
        context(ret, 6), context(bounds, 129), context(bounds + 1, 6), context(overflow + 4096, 6),
        context(bounds, 6, 0, 8, 0x10), // Exact known trap address is insufficient at kernel privilege.
        context(division, 0), context(division, 129), context(division, 6, 1), context(division + 1, 6),
        context(division, 6, 0, 8, 0x10), context(division, 6, 0, 0x1b, 0x10),
        context(division, 6, 0, 0x1b, 0x23, Protection::user_stack_bottom - 8),
        context(division, 6, 0, 0x1b, 0x23, Protection::user_stack_top + 8),
        context(division, 6, 0, 0x1b, 0x23, Protection::user_stack_top - 1),
        context(division, 6, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0),
        context(division, 6, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0x85ff8),
        context(division, 6, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0x82001),
        context(shift, 0), context(shift, 129), context(shift, 6, 1), context(shift + 1, 6),
        context(shift, 6, 0, 8, 0x10), context(shift, 6, 0, 0x3b), context(shift, 6, 0, 0x1b, 0x10),
        context(shift, 6, 0, 0x1b, 0x23, Protection::user_stack_bottom - 8),
        context(shift, 6, 0, 0x1b, 0x23, Protection::user_stack_top + 8),
        context(shift, 6, 0, 0x1b, 0x23, Protection::user_stack_top - 1),
        context(shift, 6, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0),
        context(shift, 6, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0x85ff8),
        context(shift, 6, 0, 0x1b, 0x23, Protection::user_stack_top, 2, 0x82001),
    };
    for (const auto& candidate : invalid) check(contract.classify(candidate) == ProgramEvent::rejected, "forged context");
    for (const auto flag : {8, 9, 10, 12, 13, 14, 17}) {
        check(contract.classify(context(ret, 129, 0, 0x1b, 0x23, Protection::user_stack_top, 2 | (1ULL << flag)))
            == ProgramEvent::rejected, "privileged/unsafe return flags");
        check(contract.classify(context(division, 6, 0, 0x1b, 0x23, Protection::user_stack_top, 2 | (1ULL << flag)))
            == ProgramEvent::rejected, "privileged/unsafe division fault flags");
        check(contract.classify(context(shift, 6, 0, 0x1b, 0x23, Protection::user_stack_top, 2 | (1ULL << flag)))
            == ProgramEvent::rejected, "privileged/unsafe shift fault flags");
    }
    for (const auto& bad : std::array{
        ProgramContract{base + 1, 128, ret, bounds, overflow}, ProgramContract{UINT64_MAX, 128, ret, bounds, overflow},
        ProgramContract{base, 0, ret, bounds, overflow}, ProgramContract{base, 4097, ret, bounds, overflow},
        ProgramContract{base, 128, base + 1, bounds, overflow}, ProgramContract{base, 128, ret, ret, overflow},
        ProgramContract{base, 128, ret, bounds, base + 128},
        ProgramContract{base, 128, ret, bounds, overflow, ret},
        ProgramContract{base, 128, ret, bounds, overflow, bounds},
        ProgramContract{base, 128, ret, bounds, overflow, overflow},
        ProgramContract{base, 128, ret, bounds, overflow, base - 1},
        ProgramContract{base, 128, ret, bounds, overflow, base + 127},
        ProgramContract{base, 128, ret, bounds, overflow, UINT64_MAX}}) check(!bad.valid(), "invalid metadata");
    for (const auto site : {ret, bounds, overflow, division, base - 1, base + 127, UINT64_MAX})
        check(!ProgramContract{base, 128, ret, bounds, overflow, division, site}.valid(), "invalid shift metadata");
    std::array<std::byte, 128> bytes{};
    bytes[30] = std::byte{0xcd}; bytes[31] = std::byte{0x81};
    for (const auto offset : {32, 64, 66, 68, 70}) { bytes[offset] = std::byte{0x0f}; bytes[offset + 1] = std::byte{0x0b}; }
    const auto image = ProgramImage{bytes, contract};
    check(image.valid(), "exact image opcodes");
    bytes[68] = std::byte{0x90}; check(!image.valid(), "non-UD2 division metadata");
    check(ProgramImage{bytes, legacy}.valid(), "legacy image needs no division opcode"); bytes[68] = std::byte{0x0f};
    bytes[69] = std::byte{0x90}; check(!image.valid(), "incomplete division UD2"); bytes[69] = std::byte{0x0b};
    bytes[70] = std::byte{0x90}; check(!image.valid(), "non-UD2 shift metadata");
    check(ProgramImage{bytes, division_only}.valid(), "division-only image needs no shift opcode"); bytes[70] = std::byte{0x0f};
    bytes[71] = std::byte{0x90}; check(!image.valid(), "incomplete shift UD2"); bytes[71] = std::byte{0x0b};
    bytes[64] = std::byte{0x90}; check(!image.valid(), "non-UD2 metadata"); bytes[64] = std::byte{0x0f};
    bytes[31] = std::byte{0x80}; check(!image.valid(), "wrong return gate"); bytes[31] = std::byte{0x81};
    check(!ProgramImage{std::span(bytes).first(127), contract}.valid(), "truncated image");
    ProgramRun run;
    check(!run.accept(context(ret), 42), "return without active authority");
    { const auto short_lived = contract; check(run.begin(short_lived), "snapshot start"); }
    check(!run.begin(contract), "nested authority");
    check(!run.accept(context(ret + 1), 42) && run.running(), "invalid event consumed authority");
    check(run.accept(context(ret), UINT64_MAX) && run.value() == UINT64_MAX && !run.running(), "full i64 bit-pattern result");
    check(!run.accept(context(ret), 42), "replayed return");
    check(run.begin(contract) && run.accept(context(bounds, 6), 999), "next fault run");
    check(run.event() == ProgramEvent::bounds && run.value() == 0, "fault retained stale result");
    check(run.begin(contract) && run.accept(context(ret), 42) && run.value() == 42, "clean run after fault");
    check(!run.accept(context(division, 6), 99), "division without active authority");
    check(run.begin(contract) && !run.begin(contract), "single division authority");
    check(!run.accept(context(division, 0), 99) && run.running(), "hardware divide fault consumed authority");
    check(!run.accept(context(division, 6, 0, 8, 0x10), 99) && run.running(), "kernel division fault consumed authority");
    check(run.accept(context(division, 6), UINT64_MAX) && !run.running()
        && run.event() == ProgramEvent::division_zero && run.value() == 0, "typed division cleared scalar result");
    check(!run.accept(context(division, 6), 99), "replayed division fault");
    check(run.begin(contract) && run.accept(context(ret), 42) && run.value() == 42, "clean run after division fault");
    check(!run.accept(context(shift, 6), 99), "shift without active authority");
    check(run.begin(contract) && !run.begin(contract), "single shift authority");
    check(!run.accept(context(shift, 0), 99) && run.running(), "wrong vector consumed shift authority");
    check(!run.accept(context(shift, 6, 0, 8, 0x10), 99) && run.running(), "kernel shift fault consumed authority");
    check(run.accept(context(shift, 6), UINT64_MAX) && !run.running()
        && run.event() == ProgramEvent::shift_count && run.value() == 0, "typed shift cleared scalar result");
    check(!run.accept(context(shift, 6), 99), "replayed shift fault");
    check(run.begin(contract) && run.accept(context(ret), 42) && run.value() == 42, "clean run after shift fault");
    std::cout << "PASS: scalar return authority, bounds/overflow/division/shift metadata, origin/stack/flags rejection, replay/lifetime/reset policy\n";
}
