#include "../kernel/uefi/runtime-layout.hpp"
#include "../kernel/uefi/runtime-tables.hpp"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <type_traits>

namespace kernel_uefi_dispatch_layout {
using namespace aurora::uefi;
using Two = RuntimeLayoutProfile<2>;
using Three = RuntimeLayoutProfile<3>;
using Tables = RuntimeTables;
using B = aurora::BootstrapLayout;
constexpr auto last_arena = 0x100000000ULL - B::arena_bytes;
constexpr auto nx = 1ULL << 63;
constexpr std::array<std::uint64_t, 3> roots{0x90000, 0xa0000, 0xd0000};
constexpr std::array<std::uint64_t, 3> images{0xb0000, 0xb3000, 0xb6000};
constexpr std::array<std::uint64_t, 3> stacks{0x10000200000ULL, 0x10000400000ULL, 0x10000600000ULL};
static_assert(Two::valid(last_arena) && Three::valid(last_arena));
#if defined(AURORA_UEFI_DISPATCH)
static_assert(std::is_same_v<RuntimeLayout, Three>);
#else
static_assert(std::is_same_v<RuntimeLayout, Two>);
#endif

class Checks final {
    std::size_t count_ = 0;

public:
    auto operator()(bool value) -> void {
        ++count_;
        if (!value) {
            std::cerr << "FAIL: dispatch layout check " << count_ << '\n';
            std::abort();
        }
    }
    [[nodiscard]] auto count() const -> std::size_t {
        return count_;
    }
};

// Frozen independent leaf authority, including the original two-domain profile.
// In particular, 0xb0000 must remain RX: a contiguous third pool is forbidden.
[[nodiscard]] constexpr auto runtime_flags(std::uint64_t offset, std::size_t domains) -> std::uint64_t {
    if (offset >= B::arena_bytes || offset % 4096 != 0)
        return 0;
    if (offset == 0x81000)
        return 1 | nx;
    if (offset == 0x82000 || (offset >= 0x84000 && offset < 0x88000) || (offset >= 0x89000 && offset < 0x8d000) ||
        (offset >= 0x90000 && offset < 0xb0000) || (offset >= 0xc0000 && offset < 0xd0000) ||
        (domains == 3 && offset >= 0xd0000 && offset < 0xe0000))
        return 3 | nx;
    if (offset >= 0xb0000 && offset < 0xb0000 + domains * 12288)
        return 1;
    return 0;
}

// A full-window loader layout: one text page, one readonly page and the
// remaining writable payload pages. No runtime helper supplies this oracle.
[[nodiscard]] constexpr auto kernel_flags(std::uint64_t offset, std::size_t domains) -> std::uint64_t {
    if (const auto flags = runtime_flags(offset, domains))
        return flags;
    if (offset < B::kernel_tables_offset || offset == B::kernel_payload_offset + B::page_size)
        return 1 | nx;
    if ((offset >= B::kernel_tables_offset && offset < B::kernel_tables_offset + B::table_pages * B::page_size) ||
        offset == B::kernel_idt_offset || (offset >= B::kernel_stack_bottom && offset < B::kernel_stack_top) ||
        (offset >= 0x50000 && offset < 0x81000) ||
        (offset >= B::kernel_payload_offset + 2 * B::page_size &&
         offset < B::kernel_payload_offset + B::kernel_payload_limit))
        return 3 | nx;
    return offset == 0x21000 || offset == B::kernel_payload_offset ? 1 : 0;
}

template <class Layout> auto inspect_layout(Checks &check) -> void {
    constexpr auto domains = Layout::domain_count;
    check(Layout::page_size == 4096 && Layout::arena_bytes % Layout::page_size == 0);
    check(Layout::metadata_offset == 0x81000 && Layout::gdt_offset == 0x82000);
    check(Layout::rsp0_guard == 0x83000 && Layout::rsp0_bottom == 0x84000 && Layout::rsp0_top == 0x88000);
    check(Layout::ist_guard == 0x88000 && Layout::ist_bottom == 0x89000 && Layout::ist_top == 0x8d000);
    check(Layout::tables_offset == 0x90000 && Layout::table_pages == 16);
    check(Layout::image_offset == 0xb0000 && Layout::image_count == domains);
    check(Layout::max_code_pages == 3 && Layout::image_slot_bytes == 12288 && Layout::code_stride == 16384);
    check(Layout::stack_frames_offset == 0xc0000 && Layout::stack_frame_count == 16 && Layout::stack_pages == 4);
    check(Layout::user_code == 0x10000000000ULL && Layout::user_stack_bottom == stacks[0]);
    check(Layout::user_stack_top == stacks[0] + 0x4000 && Layout::user_stack_guard == stacks[0] - 4096);
    check(Layout::lower_limit == 0x800000000000ULL && domains * 4 <= 16);
    for (const auto base : {0x100000ULL, 0x301000ULL, 0x3f0000ULL, 0x3ff00000ULL, last_arena})
        check(Layout::valid(base));
    for (const auto base : {0ULL,
                            0xff000ULL,
                            0x100001ULL,
                            last_arena + 1,
                            last_arena + B::page_size,
                            0x100000000ULL,
                            0x800000000000ULL,
                            0xfffffffffffff000ULL,
                            0xffffffffffffffffULL})
        check(!Layout::valid(base));
    for (const auto address : {0ULL, 4096ULL, 0x7fffffffffffULL})
        check(Layout::canonical_lower(address));
    for (const auto address : {0x800000000000ULL, 0xffff800000000000ULL, 0xffffffffffffffffULL})
        check(!Layout::canonical_lower(address));
    check(Layout::valid_interval(0, 4096));
    check(Layout::valid_interval(0, 0x800000000000ULL));
    check(Layout::valid_interval(0x7ffffffff000ULL, 4096));
    for (const auto range : std::array<std::array<std::uint64_t, 2>, 11>{{{0, 0},
                                                                          {1, 4096},
                                                                          {0, 1},
                                                                          {0, 4095},
                                                                          {0, 4097},
                                                                          {0x800000000000ULL, 4096},
                                                                          {0x7ffffffff000ULL, 8192},
                                                                          {0xfffffffffffff000ULL, 8192},
                                                                          {0, 0xffffffffffffffffULL},
                                                                          {0xffff800000000000ULL, 4096},
                                                                          {4096, 0xfffffffffffff000ULL}}})
        check(!Layout::valid_interval(range[0], range[1]));
    check(Layout::disjoint(0, 4096, 4096, 4096));
    check(Layout::disjoint(4096, 4096, 0, 4096));
    check(!Layout::disjoint(0, 8192, 4096, 4096));
    check(!Layout::disjoint(4096, 4096, 0, 8192));
    check(!Layout::disjoint(0, 4096, 0, 4096));
    check(!Layout::disjoint(0, 0, 4096, 4096));
    check(!Layout::disjoint(0, 4096, 0xfffffffffffff000ULL, 8192));
    for (std::size_t domain = 0; domain < domains; ++domain) {
        check(Layout::table_offset(domain) == roots[domain]);
        check(Layout::image_page(domain) == images[domain]);
        const auto code = 0x10000000000ULL + domain * 16384;
        check(Layout::code_begin(domain) == code && Layout::code_end(domain) == code + 12288);
        std::uint64_t limit = 4096;
#ifdef AURORA_RUNTIME_MULTIPAGE
        limit = 12288;
#endif
        check(Layout::image_limit(domain) == limit);
        for (const auto size :
             {0ULL, 1ULL, 4095ULL, 4096ULL, 4097ULL, 8192ULL, 8193ULL, 12288ULL, 12289ULL, 0xffffffffffffffffULL})
            check(Layout::code_pages(domain, size) == (size && size <= limit ? (size + 4095) / 4096 : 0));
        check(Layout::user_stack_begin(domain) == stacks[domain]);
        check(Layout::user_stack_end(domain) == stacks[domain] + 0x4000);
        check(Layout::valid_interval(stacks[domain] - 4096, 0x6000));
        check(Layout::disjoint(roots[domain], 0x10000, 0xb0000, domains * 12288));
        check(Layout::disjoint(roots[domain], 0x10000, 0xc0000, 0x10000));
        for (std::size_t other = 0; other < domain; ++other) {
            check(Layout::disjoint(roots[domain], 0x10000, roots[other], 0x10000));
            check(Layout::disjoint(stacks[domain] - 4096, 0x6000, stacks[other] - 4096, 0x6000));
        }
    }
    for (const auto index : {domains, domains + 1, std::size_t{16}, std::numeric_limits<std::size_t>::max()}) {
        check(Layout::table_offset(index) == B::arena_bytes && Layout::image_page(index) == B::arena_bytes);
        check(Layout::image_limit(index) == 0 && Layout::code_pages(index, 4096) == 0);
        check(Layout::user_stack_begin(index) == 0x800000000000ULL &&
              Layout::user_stack_end(index) == 0x800000000000ULL);
    }
    for (std::size_t index = 0; index < 16; ++index)
        check(Layout::stack_frame_offset(index) == 0xc0000 + index * 4096);
    for (const auto index : {std::size_t{16}, std::size_t{17}, std::numeric_limits<std::size_t>::max()})
        check(Layout::stack_frame_offset(index) == B::arena_bytes);
    for (std::uint64_t offset = 0; offset < B::arena_bytes; offset += 4096) {
        check(Layout::kernel_flags(offset) == runtime_flags(offset, domains));
        check(Layout::kernel_flags(offset + 1) == 0 && Layout::kernel_flags(offset + 4095) == 0);
    }
    for (const auto outside : std::array<std::uint64_t, 5>{B::arena_bytes,
                                                           B::arena_bytes + B::page_size,
                                                           B::lower_limit,
                                                           0xfffffffffffff000ULL,
                                                           0xffffffffffffffffULL})
        check(Layout::kernel_flags(outside) == 0);
    for (const auto guard :
         {0x83000ULL, 0x88000ULL, 0x8d000ULL, 0x8e000ULL, 0x8f000ULL, 0xb9000ULL, 0xbf000ULL, 0xe0000ULL, 0xff000ULL})
        check(Layout::kernel_flags(guard) == 0);
    check(Layout::valid_probe(0, 0) && Layout::valid_probe(16, 8));
    check(!Layout::valid_probe(7, 2) && !Layout::valid_probe(8, 2) && !Layout::valid_probe(16, 1) &&
          !Layout::valid_probe(16, 9) && !Layout::valid_probe(16, 0xffffffffffffffffULL));

    // Real table construction proves all selected roots fit their own 16 pages,
    // including a 1-GiB crossing, the full payload window and the explicit APIC leaf.
    for (const auto arena : {0x300000ULL, 0x3f0000ULL, 0x3ff00000ULL}) {
        for (std::size_t domain = 0; domain < domains; ++domain) {
            std::array<std::uint64_t, 16 * 512> storage{};
            Tables tables{storage, arena + roots[domain]};
            check(tables.valid() && tables.root() == arena + roots[domain] && tables.used() == 1);
            check(Layout::valid(arena));
            check(tables.verify([](auto) -> std::uint64_t {
                return 0;
            }));
            check(std::all_of(storage.begin(), storage.end(), [](auto value) {
                return value == 0;
            }));
            // Layout validation alone leaves every kernel/user/MMIO page absent.
            check(tables.entry(arena + roots[domain]) == 0 && tables.entry(stacks[domain]) == 0 &&
                  tables.entry(0x10000000000ULL + domain * 16384) == 0 && tables.entry(0xffff900000000000ULL) == 0);
            for (std::uint64_t offset = 0; offset < B::arena_bytes; offset += 4096)
                if (const auto flags = kernel_flags(offset, domains))
                    check(tables.map(arena + offset, arena + offset, flags));
            const auto code = 0x10000000000ULL + domain * 16384;
            check(tables.map(code, arena + images[domain], 5));
            for (std::size_t page = 0; page < 4; ++page)
                check(tables.map(stacks[domain] + page * 4096, arena + 0xc0000 + (domain * 4 + page) * 4096, 7 | nx));
            check(tables.map(0xffff900000000000ULL, 0xfee00000, 0x1b | nx));
            const auto expected = [&](std::uint64_t va) -> std::uint64_t {
                if (va >= arena && va - arena < B::arena_bytes) {
                    const auto flags = kernel_flags(va - arena, domains);
                    return flags ? va | flags : 0;
                }
                if (va == code)
                    return (arena + images[domain]) | 5;
                if (va >= stacks[domain] && va - stacks[domain] < 0x4000)
                    return (arena + 0xc0000 + domain * 0x4000 + va - stacks[domain]) | 7 | nx;
                return va == 0xffff900000000000ULL ? 0xfee0001bULL | nx : 0;
            };
            check(tables.verify(expected));
            check(tables.used() <= 13);
            for (std::uint64_t offset = 0; offset < B::arena_bytes; offset += 4096)
                check(tables.entry(arena + offset) == expected(arena + offset));
            check(tables.entry(code) == expected(code));
            for (std::size_t page = 0; page < 4; ++page)
                check(tables.entry(stacks[domain] + page * 4096) == expected(stacks[domain] + page * 4096));
            for (std::size_t other = 0; other < 3; ++other) {
                check(tables.entry(stacks[other] - 4096) == 0 && tables.entry(stacks[other] + 0x4000) == 0);
                if (other != domain) {
                    check(tables.entry(0x10000000000ULL + other * 16384) == 0);
                    for (std::size_t page = 0; page < 4; ++page)
                        check(tables.entry(stacks[other] + page * 4096) == 0);
                }
            }
            check(tables.entry(0xffff800000000000ULL) == 0);
            check(tables.entry(0xffff900000000000ULL) == expected(0xffff900000000000ULL));
            check(tables.reset() && tables.used() == 1 && tables.verify([](auto) -> std::uint64_t {
                return 0;
            }));
        }
    }
}

auto main() -> int {
    Checks check;
    inspect_layout<Two>(check);
    inspect_layout<Three>(check);
    std::size_t changed = 0;
    for (std::uint64_t offset = 0; offset < B::arena_bytes; offset += 4096) {
        const bool added = (offset >= 0xb6000 && offset < 0xb9000) || (offset >= 0xd0000 && offset < 0xe0000);
        check((Two::kernel_flags(offset) != Three::kernel_flags(offset)) == added);
        if (added) {
            ++changed;
            check(Two::kernel_flags(offset) == 0);
        }
    }
    check(changed == 19);
    std::cout
        << "PASS: " << check.count()
        << " independent two/three-domain UEFI layout, exact-page authority, guard, capacity and isolation checks\n";
    return 0;
}
} // namespace kernel_uefi_dispatch_layout
