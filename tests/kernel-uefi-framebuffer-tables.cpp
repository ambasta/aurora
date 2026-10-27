#include "kernel-table-recursive-reference.hpp"
#include "../kernel/uefi/tables.hpp"
#include <array>
#include <cstdlib>
#include <iostream>

namespace {
using namespace aurora::uefi;
using U64 = std::uint64_t;
alignas(4096) std::array<std::byte, Handoff::arena_bytes> storage{};
unsigned checks{};
auto need(bool value) -> void {
    ++checks;
    if (!value)
        std::abort();
}
auto leaf(U64 root, U64 address) -> U64 & {
    for (unsigned shift : {39U, 30U, 21U})
        root = reinterpret_cast<U64 *>(root)[(address >> shift) & 511] & 0x000ffffffffff000ULL;
    return reinterpret_cast<U64 *>(root)[(address >> 12) & 511];
}
} // namespace
int main() {
    const auto arena = reinterpret_cast<U64>(storage.data());
    need(RuntimeLayout::valid(arena)); // Build this hosted model with -no-pie.
    auto h = std::span{storage}.first(Handoff::header);
    put(h, 0, Handoff::magic);
    put(h, 8, 5, 4);
    put(h, 12, 128, 4);
    put(h, 16, Handoff::arena_bytes);
    put(h, 24, arena);
    put(h, 32, 80);
    put(h, 40, 40);
    put(h, 48, 1, 4);
    put(h, 52, 1, 4);
    put(h, 56, 8192);
    put(h, 64, 4096);
    put(h, 72, 8192);
    put(h, 80, 12288);
    put(h, 88, arena + 0x11000);
    put(h, 96, 1);
    put(h, 104, arena + Handoff::payload_offset);
    put(h, 120, arena + 0xe0000);
    need(Handoff::valid(h, arena));
    for (U64 version : {1ULL, 2ULL, 3ULL, 4ULL}) {
        put(h, 8, version, 4);
        need(!Handoff::valid(h, arena));
        need(expected_flags(0xe0000, Bytes{h}) == 0);
    }
    put(h, 8, 5, 4);
    need(expected_flags(0xe0000, Bytes{h}) == 0x8000000000000001ULL);
    const auto geometry = FramebufferGeometry::parse(0xc0000000, 0x300000, 1024, 768, 1024, 0, 36);
    need(geometry.has_value());
    std::array<std::byte, 80> map{};
    put(map, 0, 1, 4);
    put(map, 8, arena);
    put(map, 24, Handoff::arena_bytes / 4096);
    put(map, 40, 11, 4);
    put(map, 48, 0xc0000000);
    put(map, 64, 768);
    put(map, 72, 1);
    const auto grant = FramebufferAdmission::authorize_described(
        *geometry, map, 40, 1, arena, 36, (1U << 5) | (1U << 16), 0x0007040600070406ULL);
    need(grant.has_value());
    const auto root = arena + Handoff::tables_offset;
    PageTables tables{root};
    for (U64 offset = 0; offset < Handoff::arena_bytes; offset += 4096) {
        const auto flags = expected_flags(offset, Bytes{h});
        if (flags)
            need(tables.map(arena + offset, flags));
    }
    const auto before = tables.used();
    const auto unchanged = storage;
    need(!PageTables{root, 0}.prepare_framebuffer(*geometry));
    need(!PageTables{root, 17}.prepare_framebuffer(*geometry));
    need(!PageTables{root + 1, tables.used()}.prepare_framebuffer(*geometry));
    // Runtime-invalid addresses exercise the guard instead of folding away the
    // rejection call (and diagnosing its unreachable table access at address 0).
    const volatile U64 invalid_bases[] = {0, UINT64_MAX};
    for (const auto invalid_base : invalid_bases)
        need(!PageTables{invalid_base, tables.used()}.prepare_framebuffer(*geometry));
    need(storage == unchanged);
    need(tables.prepare_framebuffer(*geometry));
    need(tables.used() == before + 4 && tables.used() <= 16);
    put(h, 96, tables.used());
    need(tables.verify(arena, Bytes{h})); // Empty reserved paths confer no access.
    need(!tables.verify(arena, Bytes{h}, nullptr, &*grant));
    need(!PageTables{root + 4096, tables.used()}.install_framebuffer(*grant));
    need(!PageTables{root, 0}.install_framebuffer(*grant));
    need(!PageTables{root, 17}.install_framebuffer(*grant));
    need(tables.install_framebuffer(*grant));
    need(!tables.install_framebuffer(*grant));
    need(tables.verify(arena, Bytes{h}, nullptr, &*grant));
    need(!tables.verify(arena, Bytes{h})); // v5 alone never widens authority.
    constexpr U64 first = 0xffffa00000001000ULL, end = 0xffffa00000301000ULL;
    for (U64 address : {first, first + 511 * 4096, end - 4096}) {
        auto &slot = leaf(root, address);
        const auto saved = slot;
        for (unsigned bit : {1U, 2U, 3U, 4U, 7U, 12U, 63U}) {
            slot = saved ^ (U64{1} << bit);
            need(!tables.verify(arena, Bytes{h}, nullptr, &*grant));
        }
        slot = 0;
        need(!tables.verify(arena, Bytes{h}, nullptr, &*grant));
        slot = saved;
    }
    for (U64 guard : {first - 4096, end}) {
        auto &slot = leaf(root, guard);
        need(slot == 0);
        slot = 0xc0000000ULL | 0x800000000000001bULL;
        need(!tables.verify(arena, Bytes{h}, nullptr, &*grant));
        slot = 0;
    }
    auto &alias = leaf(root, arena + 0xe1000);
    need(alias == 0);
    alias = 0xc0000000ULL | 0x800000000000001bULL;
    need(!tables.verify(arena, Bytes{h}, nullptr, &*grant));
    alias = 0;
    need(tables.verify(arena, Bytes{h}, nullptr, &*grant));
    // Compare the old recursive reference with the fixed-slot production walk
    // over exact/absent authority, every allocated table and hostile link/leaf bits.
    unsigned accepted = 0, rejected = 0;
    const auto compare = [&](const FramebufferAdmission *authority) {
        const auto expected = table_reference::page_verify(root, tables.used(), arena, Bytes{h}, nullptr, authority);
        need(tables.verify(arena, Bytes{h}, nullptr, authority) == expected);
        (expected ? accepted : rejected)++;
    };
    compare(&*grant);
    compare(nullptr);
    auto words = std::span{reinterpret_cast<U64 *>(root), tables.used() * 512};
    for (std::size_t page = 0; page < tables.used(); ++page) {
        // Exercise first/last entries and an actually populated entry at each level.
        std::array<std::size_t, 3> indices{page * 512, page * 512 + 511, page * 512};
        for (std::size_t i = page * 512; i < (page + 1) * 512; ++i)
            if (words[i]) {
                indices[2] = i;
                break;
            }
        for (auto index : indices) {
            const auto saved = words[index];
            for (auto changed : std::array<U64, 10>{0,
                                                    0x20,
                                                    0x40,
                                                    0x60,
                                                    root | 3,
                                                    (root + tables.used() * 4096) | 3,
                                                    saved ^ 4,
                                                    saved ^ 0x80,
                                                    saved ^ PageTables::nx,
                                                    saved ^ 0x1000}) {
                words[index] = changed;
                compare(&*grant);
                compare(nullptr);
            }
            words[index] = saved;
        }
    }
    compare(&*grant);
    need(accepted && rejected);
    std::cout << "PASS: framebuffer guarded complete-tree model " << checks << " checks\n";
}
