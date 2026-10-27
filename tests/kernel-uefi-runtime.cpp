#include "kernel-table-recursive-reference.hpp"
#include <vector>
#include "../kernel/uefi/runtime-layout.hpp"
#include "../kernel/uefi/runtime-tables.hpp"
#include "../kernel/uefi/tables.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <iostream>
#include <type_traits>

namespace kernel_uefi_runtime {
using namespace aurora::uefi;
using Layout = RuntimeLayout;
using Tables = RuntimeTables;
static_assert(!std::is_copy_constructible_v<Tables> && !std::is_move_constructible_v<Tables>);
static_assert(Layout::valid(0x100000000ULL - Layout::arena_bytes));
static_assert(!Layout::valid(0x100000000ULL - Layout::arena_bytes + Layout::page_size));

class Expected final {
    std::array<std::array<std::uint64_t, 2>, 512> pages_{};
    std::size_t size_ = 0;

public:
    auto add(std::uint64_t va, std::uint64_t pa, std::uint64_t flags) -> void {
        assert(size_ < pages_.size() && (*this)(va) == 0);
        pages_[size_++] = {va, pa | flags};
    }
    [[nodiscard]] auto operator()(std::uint64_t va) const -> std::uint64_t {
        for (std::size_t i = 0; i < size_; ++i)
            if (pages_[i][0] == va)
                return pages_[i][1];
        return 0;
    }
    [[nodiscard]] auto complete(const Tables &tables) const -> bool {
        if (!tables.verify(*this))
            return false;
        for (std::size_t i = 0; i < size_; ++i)
            if ((tables.entry(pages_[i][0]) & ~Tables::accessed_dirty) != pages_[i][1])
                return false;
        return true;
    }
};

auto main() -> int {
    unsigned cases = 0;
    const auto check = [&](bool value) {
        ++cases;
        assert(value);
    };
    for (unsigned size = 0; size < 8; ++size)
        check(!RuntimeLayout::valid_probe(size, 1));
    check(!RuntimeLayout::valid_probe(4, 1));
    check(!RuntimeLayout::valid_probe(8, 1));
    check(RuntimeLayout::valid_probe(16, 8));
    check(!RuntimeLayout::valid_probe(16, 9));
    check(!RuntimeLayout::valid_probe(16, ~std::uint64_t{0}));

    constexpr std::uint64_t arena = 0x300000;
    constexpr auto words = Tables::max_pages * Tables::words_per_page;
    constexpr auto absent = [](std::uint64_t) -> std::uint64_t {
        return 0;
    };
    for (auto base : {0x100000ULL, 0x301000ULL, (0x100000000ULL - Layout::arena_bytes)})
        check(Layout::valid(base));
    for (auto base : {0ULL,
                      0xff000ULL,
                      0x100001ULL,
                      (0x100000000ULL - Layout::arena_bytes + Layout::page_size),
                      0x100000000ULL,
                      0xffffffffff000000ULL})
        check(!Layout::valid(base));
    check(Layout::valid_interval(0, 4096));
    check(Layout::valid_interval(Layout::lower_limit - 4096, 4096));
    for (const auto range : std::array<std::array<std::uint64_t, 2>, 8>{{{0, 0},
                                                                         {1, 4096},
                                                                         {0, 4095},
                                                                         {Layout::lower_limit, 4096},
                                                                         {Layout::lower_limit - 4096, 8192},
                                                                         {0xfffffffffffff000ULL, 8192},
                                                                         {0, ~std::uint64_t{0}},
                                                                         {0xffff800000000000ULL, 4096}}})
        check(!Layout::valid_interval(range[0], range[1]));
    check(Layout::disjoint(0, 4096, 4096, 4096));
    check(!Layout::disjoint(0, 8192, 4096, 4096));
    check(!Layout::disjoint(0, 0, 4096, 4096));
    check(Layout::table_offset(0) == 0x90000 && Layout::table_offset(1) == 0xa0000);
    check(Layout::table_offset(2) == Layout::arena_bytes);
    check(Layout::image_page(0) == 0xb0000 && Layout::image_page(1) == 0xb3000);
    check(Layout::image_page(2) == Layout::arena_bytes);
    for (unsigned image = 0; image < 2; ++image) {
        std::uint64_t limit = 4096;
#ifdef AURORA_RUNTIME_MULTIPAGE
        limit = 12288;
#endif
        check(Layout::image_limit(image) == limit);
        for (std::uint64_t size : {0ULL, 1ULL, 4096ULL, 4097ULL, 8192ULL, 8193ULL, 12288ULL, 12289ULL, ~0ULL})
            check(Layout::code_pages(image, size) == (size && size <= limit ? (size - 1) / 4096 + 1 : 0));
    }
    check(Layout::image_limit(2) == 0 && Layout::code_pages(2, 1) == 0);
    // The runtime fixture's five-slot bank fills the gap before the stack frames;
    // its slots are kernel-read-only like the two-slot layout's, and a sixth overlaps.
    using Bank = aurora::uefi::RuntimeLayoutProfile<2, 5>;
    check(Bank::valid(0x100000) && !aurora::uefi::RuntimeLayoutProfile<2, 6>::valid(0x100000));
    check(Bank::slot_page(4) == 0xbc000 && Bank::slot_page(5) == Bank::arena_bytes &&
          Bank::image_page(2) == Bank::arena_bytes);
    check(Bank::kernel_flags(0xbe000) == 1 && Bank::kernel_flags(0xbf000) == 0 && Layout::kernel_flags(0xb6000) == 0);
    check(Layout::slot_page(1) == Layout::image_page(1) && Layout::slot_page(2) == Layout::arena_bytes);
#ifndef AURORA_RUNTIME_MULTIPAGE
    // The service fixture's eleven one-page slots pack one page apart before the
    // stack frames, beside its three domains' pools; a seventeenth slot overlaps them.
    using OnePageBank = aurora::uefi::RuntimeLayoutProfile<3, 11, 1>;
    check(OnePageBank::valid(0x100000) && aurora::uefi::RuntimeLayoutProfile<3, 16, 1>::valid(0x100000) &&
          !aurora::uefi::RuntimeLayoutProfile<3, 17, 1>::valid(0x100000));
    check(OnePageBank::slot_page(1) == 0xb1000 && OnePageBank::slot_page(10) == 0xba000 &&
          OnePageBank::slot_page(11) == OnePageBank::arena_bytes && OnePageBank::image_page(2) == 0xb6000);
    check(OnePageBank::kernel_flags(0xba000) == 1 && OnePageBank::kernel_flags(0xbb000) == 0 &&
          OnePageBank::table_offset(2) == 0xd0000);
#endif
    // Storage reserves twelve pages for seven slots, including the namespace.
    // The separate snapshot/Call bank keeps four one-page slots; text stays twelve pages.
    // Only the reserved bank is kernel-read-only; a seventeenth page overlaps stacks.
    using Storage = aurora::uefi::RuntimeLayoutProfile<2, 7, 3, 12>;
    using SnapshotCall = aurora::uefi::RuntimeLayoutProfile<2, 4, 3, 4>;
    using Text = aurora::uefi::RuntimeLayoutProfile<2, 6, 3, 12>;
    check(Storage::valid(0x100000) && SnapshotCall::valid(0x100000) && Text::valid(0x100000) &&
          aurora::uefi::RuntimeLayoutProfile<2, 6, 3, 16>::valid(0x100000) &&
          !aurora::uefi::RuntimeLayoutProfile<2, 9, 3, 17>::valid(0x100000));
    check(Storage::kernel_flags(0xbb000) == 1 && Storage::kernel_flags(0xbc000) == 0 && Storage::bank_bytes == 0xc000);
    check(SnapshotCall::kernel_flags(0xb3000) == 1 && SnapshotCall::kernel_flags(0xb4000) == 0 &&
          SnapshotCall::bank_bytes == 0x4000);
    check(Text::kernel_flags(0xbb000) == 1 && Text::kernel_flags(0xbc000) == 0 && Text::bank_bytes == 0xc000);
    check(Layout::stack_frame_offset(15) == 0xcf000 && Layout::stack_frame_offset(16) == Layout::arena_bytes);
    check(Layout::user_stack_begin(0) == 0x10000200000ULL && Layout::user_stack_begin(1) == 0x10000400000ULL);
    check(Layout::user_stack_end(1) == 0x10000404000ULL);
    check(!Layout::canonical_lower(Layout::user_stack_begin(2)));
    check(Layout::kernel_flags(Layout::metadata_offset) == (1 | Tables::nx));
    check(Layout::kernel_flags(Layout::gdt_offset) == (3 | Tables::nx));
    for (auto guard : std::array<std::uint64_t, 9>{Layout::rsp0_guard,
                                                   Layout::ist_guard,
                                                   Layout::ist_top,
                                                   0x8e000ULL,
                                                   0x8f000ULL,
                                                   0xb6000ULL,
                                                   0xbf000ULL,
                                                   0xd0000ULL,
                                                   0xff000ULL})
        check(Layout::kernel_flags(guard) == 0);
    check(Layout::kernel_flags(Layout::metadata_offset + 1) == 0);

    // Deliberately unaligned in host memory and unrelated to the physical base.
    // Table indexing must use the supplied span, never dereference a physical PA.
    std::array<std::uint64_t, words + 2> storage0{}, storage1{};
    storage0.fill(~std::uint64_t{0});
    storage1.fill(~std::uint64_t{0});
    auto backing0 = std::span{storage0}.subspan(1, words);
    auto backing1 = std::span{storage1}.subspan(1, words);
    const auto root0 = arena + Layout::table_offset(0), root1 = arena + Layout::table_offset(1);
    Tables domain0{backing0, root0}, domain1{backing1, root1};
    check(domain0.valid() && domain0.used() == 1 && domain0.root() == root0);
    check(domain1.valid() && domain1.used() == 1 && domain1.root() == root1);
    check(domain0.verify(absent) && domain1.verify(absent));
    const auto parity = [&](const Tables &tables, std::span<std::uint64_t> backing, const auto &expected) {
        unsigned accepted = 0, rejected = 0;
        const auto compare = [&] {
            std::vector<std::uint64_t> old_order, new_order;
            const auto reference = table_reference::runtime_verify(tables, backing, [&](auto address) {
                old_order.push_back(address);
                return expected(address);
            });
            const auto actual = tables.verify([&](auto address) {
                new_order.push_back(address);
                return expected(address);
            });
            check(actual == reference && old_order == new_order);
            (reference ? accepted : rejected)++;
        };
        compare();
        for (std::size_t page = 0; page < tables.used(); ++page) {
            std::array<std::size_t, 3> indices{page * 512, page * 512 + 511, page * 512};
            for (std::size_t i = page * 512; i < (page + 1) * 512; ++i)
                if (backing[i]) {
                    indices[2] = i;
                    break;
                }
            for (auto index : indices) {
                const auto saved = backing[index];
                for (auto changed : std::array<std::uint64_t, 12>{0,
                                                                  0x20,
                                                                  0x40,
                                                                  0x60,
                                                                  tables.root() | 3,
                                                                  (tables.root() + tables.used() * 4096) | 3,
                                                                  saved ^ Tables::user,
                                                                  saved ^ Tables::nx,
                                                                  saved ^ Tables::writable,
                                                                  saved ^ 0x80,
                                                                  saved ^ 0x1000,
                                                                  saved | Tables::accessed_dirty}) {
                    backing[index] = changed;
                    compare();
                }
                backing[index] = saved;
            }
        }
        // Dedicated postorder cases: user-bit mismatch after visiting leaves,
        // empty child, root/shared-table alias, and stale unallocated storage.
        for (std::size_t slot = 0; slot < 512; ++slot) {
            if (!backing[slot])
                continue;
            const auto parent = backing[slot];
            backing[slot] ^= Tables::user;
            compare();
            backing[slot] = tables.root() | 3;
            compare();
            backing[slot] = parent;
            const auto child = ((parent & Tables::address_mask) - tables.root()) / 4096;
            std::array<std::uint64_t, 512> saved{};
            std::copy_n(backing.begin() + child * 512, 512, saved.begin());
            std::fill_n(backing.begin() + child * 512, 512, 0);
            compare();
            std::copy(saved.begin(), saved.end(), backing.begin() + child * 512);
            const auto other = (slot + 1) % 512;
            const auto old_other = backing[other];
            backing[other] = parent;
            compare();
            backing[other] = old_other;
            break;
        }
        if (tables.used() * 512 < backing.size()) {
            const auto index = tables.used() * 512;
            const auto saved = backing[index];
            backing[index] = 1;
            compare();
            backing[index] = saved;
        }
        compare();
        check(accepted && rejected);
    };
    parity(domain0, backing0, absent);

    check(std::all_of(backing0.begin(), backing0.end(), [](auto value) {
        return value == 0;
    }));
    check(storage0.front() == ~std::uint64_t{0} && storage0.back() == ~std::uint64_t{0});
    std::array<std::byte, Handoff::header> header{};
    put(header, 8, 3, 4);
    put(header, 64, 4096);
    put(header, 72, 8192);
    put(header, 80, 12288);
    Expected expected0, expected1;
    const auto build = [&](Tables &tables, Expected &expected, std::size_t domain) {
        for (std::uint64_t offset = 0; offset < Layout::arena_bytes; offset += 4096) {
            const auto runtime = Layout::kernel_flags(offset);
            const auto flags = runtime ? runtime : expected_flags(offset, Bytes{header});
            if (flags) {
                check(tables.map(arena + offset, arena + offset, flags));
                expected.add(arena + offset, arena + offset, flags);
            }
        }
        const auto code = Layout::user_code + domain * 16384;
        check(tables.map(code, arena + Layout::image_page(domain), Tables::present | Tables::user));
        expected.add(code, arena + Layout::image_page(domain), Tables::present | Tables::user);
        for (std::size_t page = 0; page < 4; ++page) {
            const auto va = Layout::user_stack_begin(domain) + page * 4096;
            const auto pa = arena + Layout::stack_frame_offset(domain * 4 + page);
            check(tables.map(va, pa, Tables::present | Tables::writable | Tables::user | Tables::nx));
            expected.add(va, pa, Tables::present | Tables::writable | Tables::user | Tables::nx);
        }
        check(expected.complete(tables));
        for (std::uint64_t offset = 0; offset < Layout::arena_bytes; offset += 4096)
            check(tables.entry(arena + offset) == expected(arena + offset));
        check(tables.entry(Layout::user_code + (1 - domain) * 16384) == 0);
        check(tables.entry(Layout::user_stack_begin(1 - domain)) == 0);
        check(tables.entry(Layout::user_stack_begin(domain) - 4096) == 0);
        check(tables.entry(Layout::user_stack_end(domain)) == 0);
        check(tables.entry(0xffff800000000000ULL) == 0);
    };
    build(domain0, expected0, 0);
    build(domain1, expected1, 1);
    parity(domain0, backing0, expected0);
    parity(domain1, backing1, expected1);
    check(domain0.entry(Layout::user_stack_begin(0)) != domain1.entry(Layout::user_stack_begin(1)));
    check(domain0.used() <= 16 && domain1.used() <= 16);
    const auto saved0 = storage0;
    const auto saved_used = domain0.used();
    const auto restore = [&]() {
        storage0 = saved0;
        check(expected0.complete(domain0));
    };
    const auto index_at = [&](std::uint64_t va, unsigned wanted_level) {
        std::size_t table = 0;
        for (unsigned level = 3; level > wanted_level; --level) {
            const auto link = backing0[table * 512 + ((va >> (12 + 9 * level)) & 511)];
            table = static_cast<std::size_t>(((link & Tables::address_mask) - root0) / 4096);
        }
        return table * 512 + ((va >> (12 + 9 * wanted_level)) & 511);
    };
    const auto code_leaf = index_at(Layout::user_code, 0);
    const auto stack_leaf = index_at(Layout::user_stack_begin(0), 0);
    const auto kernel_leaf = index_at(arena, 0);
    // Permission, reserved-bit, foreign-frame and missing-leaf corruption.
    for (const auto at : {code_leaf, stack_leaf, kernel_leaf}) {
        for (auto bit : {1ULL, 2ULL, 4ULL, 8ULL, 16ULL, 128ULL, 256ULL, 512ULL, 1ULL << 52, 1ULL << 62, 1ULL << 63}) {
            backing0[at] ^= bit;
            check(!expected0.complete(domain0));
            restore();
        }
        backing0[at] = (arena + Layout::image_page(1)) | (backing0[at] & ~Tables::address_mask);
        check(!expected0.complete(domain0));
        restore();
        backing0[at] = 0;
        check(!expected0.complete(domain0));
        restore();
        backing0[at] = Tables::accessed_dirty;
        check(!expected0.complete(domain0));
        restore();
    }
    for (unsigned level = 1; level <= 3; ++level) {
        for (auto va : {arena, Layout::user_code}) {
            const auto at = index_at(va, level);
            for (auto bit : {1ULL, 2ULL, 4ULL, 8ULL, 16ULL, 128ULL, 256ULL, 512ULL, 1ULL << 52, 1ULL << 63}) {
                backing0[at] ^= bit;
                check(!expected0.complete(domain0));
                restore();
            }
            for (auto outside :
                 std::array<std::uint64_t, 4>{root0 - 4096, root0 + saved_used * 4096, root1, 0x10000000000000ULL}) {
                backing0[at] = outside | 3;
                check(!expected0.complete(domain0));
                restore();
            }
            backing0[at] = root0 | 3;
            check(!expected0.complete(domain0));
            restore();
            backing0[at] = 0;
            check(!expected0.complete(domain0));
            restore();
        }
    }
    // Aliased table parents, including aliases on an otherwise unused branch.
    backing0[1] = backing0[0];
    check(!expected0.complete(domain0));
    restore();
    const auto branch = index_at(Layout::user_stack_begin(0), 1);
    backing0[branch] = backing0[index_at(Layout::user_code, 1)];
    check(!expected0.complete(domain0));
    restore();
    // A reachable, newly empty branch must fail even if a permissive callback is used.
    const auto stack_table = ((backing0[branch] & Tables::address_mask) - root0) / 4096;
    std::fill(backing0.begin() + stack_table * 512, backing0.begin() + (stack_table + 1) * 512, 0);
    check(!domain0.verify([&](auto va) {
        return expected0(va);
    }));
    restore();
    // An unused table page containing data is never silently accepted.
    check(saved_used < Tables::max_pages);
    backing0[saved_used * 512] = 3;
    check(!expected0.complete(domain0));
    restore();
    // Hardware Accessed/Dirty writes do not change authority.
    for (auto &word : backing0)
        if (word)
            word |= Tables::accessed_dirty;
    check(expected0.complete(domain0));
    check((domain0.entry(Layout::user_code) & Tables::accessed_dirty) == Tables::accessed_dirty);
    restore();

    // Invalid requests and duplicate leaves are atomic failures.
    const auto reject = [&](std::uint64_t va, std::uint64_t pa, std::uint64_t flags) {
        check(!domain0.map(va, pa, flags));
        check(storage0 == saved0 && domain0.used() == saved_used);
    };
    reject(Layout::user_code, arena, 1);
    reject(arena, arena, 5 | Tables::nx);
    for (auto va : std::array<std::uint64_t, 6>{1ULL,
                                                Layout::user_code + 1,
                                                0x0000800000000000ULL,
                                                0x0000fffffffff000ULL,
                                                0xffff7ffffffff000ULL,
                                                0xffffffffffffffffULL})
        reject(va, arena, 1);
    for (auto pa : std::array<std::uint64_t, 4>{1ULL, arena + 1, 0x0010000000000000ULL, 0xfffffffffffff000ULL})
        reject(0x20000000000ULL, pa, 1);
    for (auto flags : {0ULL, 2ULL, 4ULL, 5ULL | 128, 1ULL | 256, 1ULL | Tables::accessed_dirty, 1ULL << 63})
        reject(0x20000000000ULL, arena, flags);
    // map() refuses corrupted existing ownership before touching any storage.
    backing0[1] = backing0[0];
    const auto corrupt = storage0;
    check(!domain0.map(0x20000000000ULL, arena, 1));
    check(storage0 == corrupt);
    restore();

    // The root starts from clean storage and reset scrubs every former mapping.
    check(domain0.reset() && domain0.used() == 1 && domain0.root() == root0);
    check(domain0.verify(absent) && domain0.entry(Layout::user_code) == 0);
    check(std::all_of(backing0.begin(), backing0.end(), [](auto value) {
        return value == 0;
    }));
    check(expected1.complete(domain1));
    check(domain0.map(0xffff800000000000ULL, (1ULL << 52) - 4096, 5 | Tables::nx));
    check(domain0.entry(0xffff800000000000ULL) == (((1ULL << 52) - 4096) | 5 | Tables::nx));
    check(domain0.verify([](auto va) -> std::uint64_t {
        return va == 0xffff800000000000ULL ? ((1ULL << 52) - 4096) | 5 | Tables::nx : 0;
    }));
    check(domain0.map(0xfffffffffffff000ULL, 0, 1 | Tables::nx));
    check(domain0.entry(0xfffffffffffff000ULL) == (1 | Tables::nx));

    // Exact capacity, insufficient capacity, and 52-bit physical interval bounds.
    std::array<std::uint64_t, words + 512> limited{};
    for (std::size_t pages = 1; pages <= 4; ++pages) {
        Tables small{std::span{limited}.first(pages * 512), 0x200000};
        const auto initial = limited;
        const bool mapped = small.map(0x20000000000ULL, 0x100000, 1);
        check(mapped == (pages == 4));
        if (!mapped)
            check(limited == initial && small.used() == 1 && small.verify(absent));
        else {
            check(small.used() == 4);
            check(small.map(0x20000001000ULL, 0x101000, 3 | Tables::nx));
            const auto full = limited;
            check(!small.map(0x20000200000ULL, 0x102000, 5));
            check(limited == full && small.used() == 4);
        }
    }
    for (auto base : {1ULL, 0x0010000000000000ULL, 0xfffffffffffff000ULL, (1ULL << 52) - 4096}) {
        Tables invalid{std::span{limited}.first(2 * 512), base};
        check(!invalid.valid() && invalid.used() == 0 && invalid.root() == 0);
        check(!invalid.map(0, 0, 1) && !invalid.verify(absent) && invalid.entry(0) == 0);
    }
    for (auto count : {0U, 1U, 511U, 513U, static_cast<unsigned>(words + 512)}) {
        limited.fill(0x1234);
        Tables invalid{std::span{limited}.first(count), 0x200000};
        check(!invalid.valid() && invalid.used() == 0 && !invalid.reset());
        check(std::all_of(limited.begin(), limited.begin() + count, [](auto value) {
            return value == 0;
        }));
    }
    Tables edge{std::span{limited}.first(512), (1ULL << 52) - 4096};
    check(edge.valid() && edge.verify(absent));
    check(!edge.map(0, 0, 1) && edge.used() == 1);
    // Mixed supervisor/user leaves share links but retain leaf-level isolation.
    Tables mixed{std::span{limited}.first(4 * 512), 0x200000};
    check(mixed.map(0, 0x300000, 3 | Tables::nx));
    check((limited[0] & Tables::user) == 0);
    check(mixed.map(4096, 0x301000, 5));
    check((limited[0] & Tables::user) != 0);
    check((mixed.entry(0) & Tables::user) == 0 && (mixed.entry(4096) & Tables::user) != 0);
    check(mixed.map(8192, 0x302000, 1 | Tables::nx));
    check(mixed.verify([](auto va) -> std::uint64_t {
        if (va == 0)
            return 0x300003 | Tables::nx;
        if (va == 4096)
            return 0x301005;
        return va == 8192 ? 0x302001 | Tables::nx : 0;
    }));
    // Independent exact image extent: mapping validity alone does not establish
    // that every required page exists. Missing leaves need explicit completeness.
    for (unsigned pages = 1; pages <= 3; ++pages) {
        constexpr std::uint64_t code = 0x10000000000ULL, physical = arena + 0xb0000;
        Expected expected;
        for (unsigned page = 0; page < pages; ++page)
            expected.add(code + page * 4096, physical + page * 4096, 5);
        for (unsigned prefix = 0; prefix <= pages; ++prefix) {
            std::array<std::uint64_t, words> storage{};
            Tables tables{storage, arena + 0x90000};
            for (unsigned page = 0; page < prefix; ++page)
                check(tables.map(code + page * 4096, physical + page * 4096, 5));
            check(expected.complete(tables) == (prefix == pages));
            if (prefix != 0) {
                check(!tables.map(code, physical, 5));
                check(expected.complete(tables) == (prefix == pages));
            }
            check(tables.reset() && tables.used() == 1 && tables.verify(absent));
            check(std::all_of(storage.begin(), storage.end(), [](auto value) {
                return value == 0;
            }));
            for (unsigned page = 0; page < pages; ++page)
                check(tables.map(code + page * 4096, physical + page * 4096, 5));
            check(expected.complete(tables));
            for (unsigned page = 0; page < pages; ++page) {
                const auto leaf = (physical + page * 4096) | 5;
                const auto at = std::find(storage.begin(), storage.end(), leaf);
                check(at != storage.end());
                for (const auto wrong : {std::uint64_t{0},
                                         leaf ^ 4096,
                                         leaf | Tables::writable,
                                         leaf | Tables::nx,
                                         leaf & ~Tables::user}) {
                    *at = wrong;
                    check(!expected.complete(tables));
                }
                *at = leaf;
                check(expected.complete(tables));
            }
            for (unsigned page = pages; page <= 4; ++page) {
                check(tables.entry(code + page * 4096) == 0);
                check(tables.map(code + page * 4096, physical, 5));
                check(!expected.complete(tables));
                check(tables.reset());
                for (unsigned present = 0; present < pages; ++present)
                    check(tables.map(code + present * 4096, physical + present * 4096, 5));
            }
            check(expected.complete(tables) && tables.used() <= 16);
        }
    }
    // Insufficient parent-table capacity must fail before publishing any link;
    // reset remains valid after this allocation refusal.
    std::array<std::uint64_t, 3 * 512> partial_storage{};
    Tables partial{partial_storage, arena + 0x90000};
    check(!partial.map(0x10000000000ULL, arena + 0xb0000, 5) && partial.used() == 1);
    check(partial.reset() && partial.used() == 1 && partial.verify(absent));
    check(std::all_of(partial_storage.begin(), partial_storage.end(), [](auto value) {
        return value == 0;
    }));
    std::cout << "PASS: " << cases
              << " UEFI runtime layout, owned table, permission, isolation, corruption and reuse checks\n";
    return 0;
}
} // namespace kernel_uefi_runtime
