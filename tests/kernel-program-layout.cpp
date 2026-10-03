#include "../kernel/user-program.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <string_view>
#include <type_traits>

using namespace aurora::user;
static_assert(!std::is_default_constructible_v<ProgramLayout>);
static_assert(!std::is_aggregate_v<ProgramLayout>);
static_assert(!std::is_constructible_v<ProgramLayout, std::uint64_t, std::uint64_t,
    std::uint64_t, std::uint64_t, std::uint64_t, std::uint64_t, std::uint64_t>);
static_assert(std::is_copy_constructible_v<ProgramLayout>);
static_assert(!std::is_copy_assignable_v<ProgramLayout>);
static_assert(!std::is_move_assignable_v<ProgramLayout>);
static_assert(std::is_copy_constructible_v<ProgramContract>);
static_assert(!std::is_copy_assignable_v<ProgramContract>);
static_assert(std::is_same_v<decltype(std::declval<ProgramContract&>().layout()), const ProgramLayout&>);

constexpr std::uint64_t page = ProgramLayout::page_size;
constexpr std::uint64_t code = 0x10000000000ULL;
constexpr std::uint64_t stack = 0x10000200000ULL;
constexpr std::uint64_t arena = 0x2000000;
constexpr std::uint64_t entry_bottom = arena + 0x84000;
constexpr std::uint64_t entry_top = arena + 0x88000;
constexpr auto uefi = ProgramLayout::create(code, code + 2 * page, 1,
    stack, stack + 4 * page, entry_bottom, entry_top);
static_assert(uefi.has_value());
static_assert(uefi->code_begin() == code && uefi->code_end() == code + 2 * page);
static_assert(uefi->max_image_pages() == 1 && uefi->max_image_size() == page);
static_assert(ProgramLayout::bios().code_begin() == 0x1b0000);
static_assert(ProgramLayout::bios().code_end() == 0x1b3000);
static_assert(ProgramLayout::bios().max_image_size() == page);
static_assert(ProgramLayout::bios().user_stack_bottom() == 0x1e0000);
static_assert(ProgramLayout::bios().user_stack_top() == 0x1e4000);
static_assert(ProgramLayout::bios().entry_stack_bottom() == 0x82000);
static_assert(ProgramLayout::bios().entry_stack_top() == 0x86000);

auto check(bool condition, std::string_view message) -> void {
    if (!condition) { std::cerr << "FAIL: " << message << '\n'; std::exit(1); }
}
auto context(std::uint64_t pc, std::uint64_t vector = 129,
    std::uint64_t sp = stack + 4 * page, std::uint64_t frame = entry_top - ProgramLayout::fault_frame_size)
    -> ProgramContext {
    return ProgramContext{vector, 0, pc, 0x1b, 0x23, sp, 2, frame};
}
auto contract(ProgramLayout layout, std::uint64_t base = code, std::uint64_t size = 128) -> ProgramContract {
    return ProgramContract{layout, base, size, base + 32, base + 64, base + 66, base + 68, base + 70};
}
auto main() -> int {
    const auto layout = *uefi;
    constexpr auto hole = std::uint64_t{1} << 47;
    constexpr auto high = std::uint64_t{0xffff800000000000ULL};
    constexpr auto last_page = UINT64_MAX - page + 1;
    const auto code_layout = [&](std::uint64_t begin, std::uint64_t end, std::uint64_t max_pages = 1) {
        return ProgramLayout::create(begin, end, max_pages, stack, stack + 4 * page, entry_bottom, entry_top);
    };
    const auto stack_layout = [&](std::uint64_t begin, std::uint64_t end) {
        return ProgramLayout::create(code, code + 2 * page, 1, begin, end, entry_bottom, entry_top);
    };
    const auto entry_layout = [&](std::uint64_t begin, std::uint64_t end) {
        return ProgramLayout::create(code, code + 2 * page, 1, stack, stack + 4 * page, begin, end);
    };
    for (const auto& bad : std::array{
        code_layout(code, code), code_layout(code + page, code),
        code_layout(code + 1, code + page), code_layout(code, code + page + 1),
        code_layout(code, code + 4 * page), code_layout(code, code + 2 * page, 0),
        code_layout(code, code + 2 * page, 3), code_layout(code, code + 2 * page, UINT64_MAX),
        code_layout(hole, hole + page), code_layout(hole - page, hole),
        code_layout(high, high + page), code_layout(last_page, 0),
        stack_layout(stack, stack), stack_layout(stack + page, stack),
        stack_layout(stack + 1, stack + page), stack_layout(stack, stack + page + 1),
        stack_layout(stack, stack + 5 * page), stack_layout(hole, hole + page),
        stack_layout(hole - page, hole), stack_layout(high, high + page), stack_layout(last_page, 0),
        entry_layout(entry_bottom, entry_bottom), entry_layout(entry_top, entry_bottom),
        entry_layout(entry_bottom + 1, entry_top), entry_layout(entry_bottom, entry_top + 1),
        entry_layout(entry_bottom, entry_bottom + 5 * page), entry_layout(hole, hole + page),
        entry_layout(hole - page, hole), entry_layout(high - page, high),
        entry_layout(hole - page, high + page), entry_layout(last_page, 0)})
        check(!bad.has_value(), "invalid interval, canonical endpoint, overflow or page budget");
    check(code_layout(code, code + 3 * page, 3).has_value(), "hard code page ceiling inclusive");
    check(stack_layout(stack, stack + page).has_value(), "one-page user stack");
    check(entry_layout(entry_bottom, entry_bottom + page).has_value(), "one-page entry stack");
    const auto upper_entry = entry_layout(high, high + 4 * page);
    check(upper_entry.has_value(), "canonical supervisor entry stack");
    check(context(code + 32, 129, stack + 4 * page, high).origin_valid(*upper_entry),
        "origin accepts validated high-half entry stack");
    for (const auto& bad : std::array{
        stack_layout(code, code + page), stack_layout(code - page, code + page),
        stack_layout(code + page, code + 3 * page), stack_layout(code, code + 2 * page),
        entry_layout(code, code + page), entry_layout(code - page, code + page),
        entry_layout(code + page, code + 3 * page), entry_layout(code, code + 2 * page),
        entry_layout(stack, stack + 4 * page), entry_layout(stack - page, stack + page),
        entry_layout(stack + 3 * page, stack + 5 * page),
        stack_layout(entry_bottom - page, entry_bottom + page),
        stack_layout(entry_top - page, entry_top + page)})
        check(!bad.has_value(), "all code/user/entry overlap pairs rejected");
    check(stack_layout(code + 2 * page, code + 3 * page).has_value(), "adjacent code/user intervals");
    check(entry_layout(code + 2 * page, code + 3 * page).has_value(), "adjacent code/entry intervals");
    check(entry_layout(stack + 4 * page, stack + 5 * page).has_value(), "adjacent user/entry intervals");

    const auto first = contract(layout);
    const auto second = contract(layout, code + page);
    check(first.valid() && second.valid(), "both authorized UEFI image pages");
    check(first.classify(context(code + 32)) == ProgramEvent::returned, "UEFI scalar return");
    check(second.classify(context(code + page + 32)) == ProgramEvent::returned, "second UEFI scalar return");
    for (const auto& candidate : std::array{
        contract(layout, code - page), contract(layout, code + 2 * page), contract(layout, code + 1),
        contract(layout, 0x1b0000), contract(layout, hole), contract(layout, high),
        contract(layout, code, 0), contract(layout, code, 3), contract(layout, code, page + 1),
        contract(layout, code, UINT64_MAX), contract(layout, code + page, page + 1),
        ProgramContract{code, 128, code + 32, code + 64, code + 66}})
        check(!candidate.valid(), "metadata cannot enlarge or replace the layout authority");
    check(contract(layout, code, page).valid(), "exact image size limit");
    const auto wider = code_layout(code, code + 2 * page, 2);
    check(contract(*wider, code, 2 * page).valid(), "trusted policy may authorize a two-page image");
    check(!contract(*wider, code + page, page + 1).valid(), "image must fit exact code interval");
    check(!contract(*wider, code + page, 2 * page).valid(), "per-image limit cannot extend code interval");
    check(context(code + 32).origin_valid(layout) && !context(code + 32).origin_valid(),
        "UEFI origin does not gain legacy BIOS authority");
    check(first.classify(ProgramContext{129, 0, code + 32, 0x1b, 0x23, 0x1e4000, 2, 0x85f00})
        == ProgramEvent::rejected, "BIOS stack cannot satisfy UEFI contract");
    check(first.classify(context(code + 32, 129, stack + 4 * page - 8)) == ProgramEvent::rejected,
        "scalar return requires exact layout stack top");
    for (const auto sp : {stack, stack + 8, stack + 4 * page})
        check(first.classify(context(code + 64, 6, sp)) == ProgramEvent::bounds, "fault user stack endpoints inclusive");
    for (const auto sp : {stack - 8, stack + 1, stack + 4 * page + 8, UINT64_MAX})
        check(first.classify(context(code + 64, 6, sp)) == ProgramEvent::rejected, "fault user stack bounds/alignment");
    for (const auto frame : {entry_bottom, entry_top - ProgramLayout::fault_frame_size})
        check(first.classify(context(code + 64, 6, stack, frame)) == ProgramEvent::bounds,
            "complete fault frame fits entry stack endpoints");
    for (const auto frame : {entry_bottom - 8, entry_bottom + 1,
        entry_top - ProgramLayout::fault_frame_size + 8, entry_top, UINT64_MAX})
        check(first.classify(context(code + 64, 6, stack, frame)) == ProgramEvent::rejected,
            "incomplete, out-of-range or misaligned kernel fault frame");
    for (const auto pc : {code - 1, code + 127, code + page, UINT64_MAX}) {
        check(!ProgramContract{layout, code, 128, pc, code + 64, code + 66}.valid(), "return metadata bounds");
        check(!ProgramContract{layout, code, 128, code + 32, pc, code + 66}.valid(), "bounds metadata bounds");
        check(!ProgramContract{layout, code, 128, code + 32, code + 64, pc}.valid(), "overflow metadata bounds");
        check(!ProgramContract{layout, code, 128, code + 32, code + 64, code + 66, pc}.valid(),
            "division metadata bounds");
        check(!ProgramContract{layout, code, 128, code + 32, code + 64, code + 66, 0, pc}.valid(),
            "shift metadata bounds");
    }
    const auto legacy = ProgramContract{layout, code, 128, code + 32, code + 64, code + 66};
    const auto shift_only = ProgramContract{layout, code, 128, code + 32, code + 64, code + 66, 0, code + 70};
    check(legacy.valid() && shift_only.valid(), "UEFI optional fault sites remain independent");
    check(first.classify(context(code + 66, 6)) == ProgramEvent::overflow
        && first.classify(context(code + 68, 6)) == ProgramEvent::division_zero
        && first.classify(context(code + 70, 6)) == ProgramEvent::shift_count, "distinct UEFI compiler traps");
    check(legacy.classify(context(code + 68, 6)) == ProgramEvent::rejected
        && legacy.classify(context(code + 70, 6)) == ProgramEvent::rejected
        && legacy.classify(context(0, 6)) == ProgramEvent::rejected, "missing optional sites grant no authority");
    check(shift_only.classify(context(code + 70, 6)) == ProgramEvent::shift_count
        && shift_only.classify(context(code + 68, 6)) == ProgramEvent::rejected, "shift-only UEFI fault authority");

    auto source = ProgramLayout::create(code, code + 2 * page, 1,
        stack, stack + 4 * page, entry_bottom, entry_top);
    const auto copied = *source;
    const auto snapshot = contract(*source);
    source.reset();
    source.emplace(ProgramLayout::bios());
    check(copied.code_begin() == code && snapshot.layout().code_begin() == code
        && snapshot.classify(context(code + 32)) == ProgramEvent::returned,
        "layout and contract copies retain immutable authority after source replacement");
    ProgramRun run;
    { const auto temporary = contract(copied); check(run.begin(temporary), "run copies temporary UEFI contract"); }
    check(!run.accept(context(code + page + 32), 42) && run.running(), "foreign image does not consume UEFI run");
    check(run.accept(context(code + 32), 42) && run.value() == 42 && !run.running(), "UEFI run snapshot and return");
    check(!run.accept(context(code + 32), 42), "UEFI return replay rejection");
    check(run.begin(snapshot) && run.accept(context(code + 70, 6), UINT64_MAX)
        && run.event() == ProgramEvent::shift_count && run.value() == 0, "UEFI fault clears prior scalar");

    std::array<std::byte, 128> bytes{};
    bytes[30] = std::byte{0xcd}; bytes[31] = std::byte{0x81};
    for (const auto offset : {32, 64, 66, 68, 70}) { bytes[offset] = std::byte{0x0f}; bytes[offset + 1] = std::byte{0x0b}; }
    const auto image = ProgramImage{bytes, snapshot};
    check(image.valid(), "UEFI image uses same opcode checks");
    bytes[70] = std::byte{0x90};
    check(!image.valid(), "UEFI metadata still requires exact optional trap opcode");
    std::cout << "PASS: immutable validated BIOS/UEFI program layout, interval and canonical checks, exact code/stack/frame authority\n";
}
