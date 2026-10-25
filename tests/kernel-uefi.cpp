#include "../kernel/uefi/handoff.hpp"
#include "../kernel/uefi/tables.hpp"
#include <array>
#include <cassert>
#include <iostream>

namespace kernel_uefi {
using namespace aurora::uefi;
alignas(4096) static std::array<std::byte, Handoff::arena_bytes> arena{};
auto main() -> int {
    unsigned cases = 0;
    std::array<std::byte, 144> raw{};
    auto descriptor = [&](std::size_t at,
                          std::uint64_t type,
                          std::uint64_t start,
                          std::uint64_t pages,
                          std::uint64_t attributes = 0) {
        put(raw, at, type, 4);
        put(raw, at + 8, start);
        put(raw, at + 24, pages);
        put(raw, at + 32, attributes);
    };
    descriptor(0, 0, 0, 256);
    descriptor(48, 1, 0x100000, 256);
    descriptor(96, 7, 0x200000, 256);
    const auto check = [&](bool value) {
        ++cases;
        assert(value);
    };
    check(MemoryMap{raw, 48, 1}.valid());
    check(MemoryMap{raw, 48, 1}.owns(0x100000, 0x100000));
    check(!MemoryMap{raw, 48, 1}.owns(0, 4096));
    check(!MemoryMap{raw, 48, 1}.owns(0x200000, 4096));
    put(raw, 32, 1ULL << 63);
    check(MemoryMap{raw, 48, 1}.owns(0x100000, 0x100000)); // Other runtime regions remain reserved.
    put(raw, 80, 1ULL << 63);
    check(!MemoryMap{raw, 48, 1}.owns(0x100000, 0x100000));
    put(raw, 80, 0);
    for (auto type : {0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}) {
        put(raw, 48, type, 4);
        check(!MemoryMap{raw, 48, 1}.owns(0x100000, 0x100000));
    }
    put(raw, 48, 1, 4);
    for (auto stride : {0U, 1U, 39U, 41U, 257U, 4096U})
        check(!MemoryMap{raw, stride, 1}.valid());
    check(!MemoryMap{raw, 48, 2}.valid());
    check(!MemoryMap{std::span{raw}.first(143), 48, 1}.valid());
    for (auto pages : {0ULL, 0xffffffffffffffffULL}) {
        put(raw, 72, pages);
        check(!MemoryMap{raw, 48, 1}.valid());
    }
    put(raw, 72, 256);
    put(raw, 56, 0x100001);
    check(!MemoryMap{raw, 48, 1}.valid());
    put(raw, 56, 0x100000);
    put(raw, 104, 0x180000);
    check(!MemoryMap{raw, 48, 1}.valid());
    put(raw, 104, 0x200000);
    put(raw, 48, 16, 4);
    check(!MemoryMap{raw, 48, 1}.valid());
    put(raw, 48, 1, 4);
    check(!MemoryMap{raw, 48, 1}.owns(0x100001, 4096));
    check(!MemoryMap{raw, 48, 1}.owns(0x100000, 1));
    check(!MemoryMap{raw, 48, 1}.owns(0xfffffffffffff000ULL, 8192));
    const auto base = reinterpret_cast<std::uint64_t>(arena.data());
    check(base >= 0x100000 && base < 0x100000000ULL - Handoff::arena_bytes);
    auto h = std::span{arena}.first(Handoff::header);
    put(h, 0, Handoff::magic);
    put(h, 8, 1, 4);
    put(h, 12, Handoff::header, 4);
    put(h, 16, Handoff::arena_bytes);
    put(h, 24, base);
    put(h, 32, 144);
    put(h, 40, 48);
    put(h, 48, 1, 4);
    put(h, 52, 1, 4);
    put(h, 56, 8192);
    put(h, 64, 4096);
    put(h, 72, 8192);
    put(h, 80, 12288);
    put(h, 88, base + Handoff::tables_offset);
    put(h, 96, 1);
    put(h, 104, base + Handoff::payload_offset);
    check(Handoff::valid(h, base));
    const auto saved = Bytes{h}.get(0);
    put(h, 0, 0);
    check(!Handoff::valid(h, base));
    put(h, 0, saved);
    for (auto field : {16U, 24U, 32U, 40U, 56U, 64U, 72U, 80U, 88U, 96U, 104U}) {
        const auto value = Bytes{h}.get(field);
        put(h, field, ~std::uint64_t{0});
        check(!Handoff::valid(h, base));
        put(h, field, value);
    }
    for (auto field : {8U, 12U, 48U, 52U}) {
        const auto value = Bytes{h}.get(field, 4);
        put(h, field, 0, 4);
        check(!Handoff::valid(h, base));
        put(h, field, value, 4);
    }
    for (auto field : {112U, 120U}) {
        put(h, field, 1);
        check(!Handoff::valid(h, base));
        put(h, field, 0);
    }
    PageTables tables{base + Handoff::tables_offset};
    for (std::uint64_t offset = 0; offset < Handoff::arena_bytes; offset += 4096) {
        const auto flags = expected_flags(offset, Bytes{h});
        if (flags)
            check(tables.map(base + offset, flags));
    }
    put(h, 96, tables.used());
    check(tables.verify(base, Bytes{h}));
    check(!tables.map(base, 3 | PageTables::nx));
    check(!tables.map(1, 1));
    check(!tables.map(0x10000, 3));
    auto *root = reinterpret_cast<std::uint64_t *>(base + Handoff::tables_offset);
    const auto link = root[0];
    root[1] = link;
    check(!tables.verify(base, Bytes{h}));
    root[1] = 0;
    root[0] = (base + Handoff::tables_offset) | 3;
    check(!tables.verify(base, Bytes{h}));
    root[0] = link;
    root[0] |= 4;
    check(!tables.verify(base, Bytes{h}));
    root[0] = link;
    check(tables.map(0x10000, 3 | PageTables::nx));
    check(!tables.verify(base, Bytes{h}));
    std::cout << "PASS: " << cases << " UEFI descriptor, ownership, bounded handoff and complete table-tree checks\n";
    return 0;
}
} // namespace kernel_uefi
