// Paired paging host model; registration is not linked-image or guest qualification.
// Build with -no-pie: all dereferences address this model's own backing array.
#include "../kernel/uefi/tables.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <string_view>
#include <type_traits>
#include <vector>

namespace {
using namespace aurora::uefi;
using U64 = std::uint64_t;
using Buffer = std::vector<std::byte>;
alignas(4096) std::array<std::byte, Handoff::arena_bytes> storage{};
unsigned checks{};
auto need(bool value, std::string_view why) -> void {
    ++checks;
    if (!value) {
        std::cerr << "FAIL: " << why << '\n';
        std::abort();
    }
}
auto paired_storage_cases() -> void {
    // These are integer intervals only. Never forge an overlapping PageTables,
    // bitmap or closure object, and never dereference a hostile test address.
    const auto check = [](U64 a, U64 size_a, U64 b, U64 size_b, bool expected, std::string_view why) {
        need(PageTables::paired_graphical_storage_disjoint(a, size_a, b, size_b) == expected, why);
        need(PageTables::paired_graphical_storage_disjoint(b, size_b, a, size_a) == expected, why);
    };
    constexpr U64 begin = 0x1000, maximum = ~U64{0};
    constexpr U64 descriptor_bytes = sizeof(PageTables);
    constexpr U64 bitmap_bytes = sizeof(std::array<bool, Handoff::table_pages>);
    check(begin, descriptor_bytes, begin, descriptor_bytes, false, "identical descriptor ranges overlap");
    check(begin, descriptor_bytes, begin, bitmap_bytes, false, "bitmap shares descriptor start");
    check(begin, descriptor_bytes, begin + 1, bitmap_bytes, false, "bitmap is contained in descriptor");
    check(begin, descriptor_bytes, begin - 1, descriptor_bytes + 2, false, "descriptor is strictly contained");
    check(begin,
          descriptor_bytes,
          begin + descriptor_bytes - 1,
          bitmap_bytes,
          false,
          "one-byte overlap at descriptor end");
    check(
        begin, descriptor_bytes, begin - bitmap_bytes + 1, bitmap_bytes, false, "one-byte overlap at descriptor start");
    check(begin, descriptor_bytes, begin + descriptor_bytes, bitmap_bytes, true, "bitmap follows adjacently");
    check(begin, descriptor_bytes, begin - bitmap_bytes, bitmap_bytes, true, "bitmap precedes adjacently");
    check(begin, descriptor_bytes, begin + descriptor_bytes + 1, bitmap_bytes, true, "one-byte gap after descriptor");
    check(begin, descriptor_bytes, begin - bitmap_bytes - 1, bitmap_bytes, true, "one-byte gap before descriptor");
    check(maximum - descriptor_bytes - bitmap_bytes,
          descriptor_bytes,
          maximum - bitmap_bytes,
          bitmap_bytes,
          true,
          "adjacent ranges may end exactly at the maximum endpoint");
    check(maximum - descriptor_bytes + 1,
          descriptor_bytes,
          begin,
          bitmap_bytes,
          false,
          "descriptor endpoint overflow fails closed");
    check(begin,
          descriptor_bytes,
          maximum - bitmap_bytes + 1,
          bitmap_bytes,
          false,
          "bitmap endpoint overflow fails closed");
    check(maximum - descriptor_bytes + 1,
          descriptor_bytes,
          maximum - bitmap_bytes + 1,
          bitmap_bytes,
          false,
          "both endpoints overflowing fail closed");
    check(maximum, 1, 0, bitmap_bytes, false, "single-byte interval cannot wrap through zero");
}
auto descriptor(Buffer &map, U64 begin, U64 pages, unsigned type) -> void {
    const auto at = map.size();
    map.resize(at + 40);
    put(map, at, type, 4);
    put(map, at + 8, begin);
    put(map, at + 24, pages);
    put(map, at + 32, type == 11 ? 1 : 8);
}
auto cpus() -> Topology {
    Buffer bytes(52);
    for (unsigned i = 0; i < 4; ++i)
        bytes[i] = std::byte(std::string_view{"APIC"}[i]);
    put(bytes, 4, bytes.size(), 4);
    put(bytes, 8, 1, 1);
    put(bytes, 36, 0xfee00000, 4);
    put(bytes, 40, 1, 4);
    put(bytes, 44, 0, 1);
    put(bytes, 45, 8, 1);
    put(bytes, 47, 7, 1);
    put(bytes, 48, 1, 4);
    unsigned sum{};
    for (auto byte : bytes)
        sum += std::to_integer<unsigned>(byte);
    bytes[9] = std::byte(0U - sum);
    auto parsed = Topology::parse(bytes, 40);
    need(parsed.has_value(), "topology fixture");
    return *parsed;
}
auto apic_grant(U64 arena) -> std::optional<LocalApicAdmission> {
    Buffer map;
    descriptor(map, arena, 256, 1);
    return LocalApicAdmission::authorize(cpus(),
                                         map,
                                         40,
                                         1,
                                         arena,
                                         40,
                                         (1U << 5) | (1U << 9) | (1U << 16),
                                         (7U << 24) | (1U << 16),
                                         0xfee00900,
                                         0x0007040600070406ULL);
}
auto graphics_grant(U64 arena, U64 physical = 0xc0000000) -> std::optional<FramebufferAdmission> {
    auto geometry = FramebufferGeometry::parse(physical, 0x300000, 1024, 768, 1024, 0, 40);
    need(geometry.has_value(), "geometry fixture");
    Buffer map;
    descriptor(map, arena, 256, 1);
    descriptor(map, physical, 768, 11);
    return FramebufferAdmission::authorize_described(
        *geometry, map, 40, 1, arena, 40, (1U << 5) | (1U << 16), 0x0007040600070406ULL);
}
auto slot(U64 root, U64 address, unsigned level = 0) -> U64 & {
    for (unsigned current = 3; current > level; --current)
        root = reinterpret_cast<U64 *>(root)[(address >> (12 + 9 * current)) & 511] & 0x000ffffffffff000ULL;
    return reinterpret_cast<U64 *>(root)[(address >> (12 + 9 * level)) & 511];
}
} // namespace
int main() {
    static_assert(!std::is_default_constructible_v<LocalApicAdmission>);
    static_assert(!std::is_default_constructible_v<FramebufferAdmission>);
    paired_storage_cases();
    const auto arena = reinterpret_cast<U64>(storage.data());
    need(RuntimeLayout::valid(arena), "model requires below-4-GiB non-PIE arena");
    auto h = std::span{storage}.first(Handoff::header);
    put(h, 0, Handoff::magic);
    put(h, 8, 6, 4);
    put(h, 12, 128, 4);
    put(h, 16, 0x100000);
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
    put(h, 104, arena + 0x22000);
    put(h, 112, arena + 0x60000);
    put(h, 120, arena + 0xe0000);
    auto apic = apic_grant(arena), foreign_apic = apic_grant(0x20000000);
    auto graphics = graphics_grant(arena), foreign_graphics = graphics_grant(0x20000000);
    need(apic && graphics && foreign_apic && foreign_graphics, "independently parsed source-bound grants");
    const U64 root = arena + Handoff::tables_offset;
    PageTables tables{root};
    for (U64 offset = 0; offset < Handoff::arena_bytes; offset += 4096)
        if (auto flags = expected_flags(offset, Bytes{h}))
            need(tables.map(arena + offset, flags), "identity mapping");
    need(tables.prepare_window() && tables.prepare_interrupts() && tables.prepare_framebuffer(graphics->geometry()),
         "fixed table pool fits paired paths");
    put(h, 96, tables.used());
    const auto valid = [&]() {
        return tables.verify_graphical(arena, Bytes{h}, &*apic, &*graphics);
    };
    need(!valid(), "no device leaves is not a complete pair");
    *tables.interrupt_slot() = apic->mapping(0xffff900000000000ULL);
    need(!valid(), "APIC-only partial pair");
    need(tables.install_framebuffer(*graphics), "install admitted framebuffer");
    need(valid(), "complete exact paired model");
    need(!tables.verify(arena, Bytes{h}, &*apic, &*graphics), "legacy overload must not widen authority");
    for (auto a :
         {static_cast<const LocalApicAdmission *>(nullptr), static_cast<const LocalApicAdmission *>(&*foreign_apic)})
        need(!tables.verify_graphical(arena, Bytes{h}, a, &*graphics), "absent or foreign APIC token");
    for (auto g : {static_cast<const FramebufferAdmission *>(nullptr),
                   static_cast<const FramebufferAdmission *>(&*foreign_graphics)})
        need(!tables.verify_graphical(arena, Bytes{h}, &*apic, g), "absent or foreign graphics token");
    for (U64 version : {0ULL, 1ULL, 2ULL, 3ULL, 4ULL, 5ULL, 7ULL, 0xffffffffULL}) {
        put(h, 8, version, 4);
        need(!valid(), "version cannot imply a paired grant");
    }
    put(h, 8, 6, 4);
    for (auto offset : {0U, 12U, 16U, 24U, 48U, 88U, 96U, 104U, 112U, 120U}) {
        const auto saved = Bytes{h}.get(offset, offset == 12 || offset == 48 ? 4 : 8);
        put(h, offset, 0, offset == 12 || offset == 48 ? 4 : 8);
        need(!valid(), "header authority binding mutation");
        put(h, offset, saved, offset == 12 || offset == 48 ? 4 : 8);
    }
    const std::vector<std::array<U64, 2>> invalid_header{
        {32, 0},
        {32, MemoryMap::max_bytes + 1},
        {40, 39},
        {40, 257},
        {52, 0},
        {52, 4},
        {56, 0},
        {56, Handoff::payload_limit + 1},
        {56, 12289},
        {64, 0},
        {64, 4097},
        {64, 12288},
        {72, 8193},
        {72, 0},
        {80, 12289},
        {80, 4096},
        {80, Handoff::payload_limit + 4096},
    };
    for (const auto &bad : invalid_header) {
        const unsigned width = bad[0] == 52 ? 4 : 8;
        const auto saved = Bytes{h}.get(bad[0], width);
        put(h, bad[0], bad[1], width);
        need(!valid(), "header range, extent, alignment or order rejected");
        put(h, bad[0], saved, width);
        need(valid(), "header mutation restores exact valid model");
    }
    need(!PageTables{root, 0}.verify_graphical(arena, Bytes{h}, &*apic, &*graphics), "zero table inventory");
    need(!PageTables{root, 17}.verify_graphical(arena, Bytes{h}, &*apic, &*graphics), "excess table inventory");
    for (U64 bad_root : {U64{0}, root - 1, root + 4096, ~U64{0}})
        need(!PageTables{bad_root, tables.used()}.verify_graphical(arena, Bytes{h}, &*apic, &*graphics),
             "captured base must match the bounded owned table arena before dereference");
    need(!tables.verify_graphical(arena + 4096, Bytes{h}, &*apic, &*graphics), "wrong caller arena");
    constexpr U64 first = 0xffffa00000001000ULL, end = first + 0x300000;
    for (U64 address :
         {U64{0xffff900000000000ULL}, first, first + 510 * 4096, first + 511 * 4096, end - 4096, arena + 0x22000}) {
        auto &entry = slot(root, address);
        const auto saved = entry;
        for (unsigned bit = 0; bit < 64; ++bit) {
            entry = saved ^ (U64{1} << bit);
            need(valid() == (bit == 5 || bit == 6), "every leaf bit except A/D must be exact");
        }
        entry = 0;
        need(!valid(), "missing required leaf");
        entry = saved;
    }
    for (U64 address : {first - 4096, end, U64{0xffff800000000000ULL}, arena + 0xe1000}) {
        auto &entry = slot(root, address);
        need(entry == 0, "guard/window/alias starts absent");
        for (U64 bad : {U64{0x20},
                        U64{0x40},
                        U64{0xc0000000ULL | 0x800000000000001bULL},
                        U64{0xfee00000ULL | 0x800000000000001bULL}}) {
            entry = bad;
            need(!valid(), "no A/D-only guard or physical alias");
        }
        entry = 0;
    }
    for (unsigned level : {1U, 2U, 3U}) {
        auto &entry = slot(root, first, level);
        const auto saved = entry;
        entry = saved | 0x60;
        need(valid(), "present intermediate hardware A/D bits are ignored");
        for (U64 bad : {root | 3,
                        (root - 4096) | 3,
                        (root + tables.used() * 4096) | 3,
                        saved | 4,
                        saved | 0x80,
                        saved | (U64{1} << 63),
                        U64{0x20},
                        U64{0x40}}) {
            entry = bad;
            need(!valid(), "cycle, out-of-pool, user, huge or NX intermediate");
        }
        entry = saved;
    }
    // Both PT paths are required: rejection must reach visited-table detection,
    // rather than reject an unrelated virtual aperture before following the link.
    auto &second_pt = slot(root, first + 511 * 4096, 1);
    const auto second_saved = second_pt;
    second_pt = slot(root, first, 1);
    need(!valid(), "duplicate table on two required framebuffer paths");
    second_pt = second_saved;
    auto &window_path = slot(root, PageTables::window_address, 3);
    const auto window_saved = window_path;
    window_path = 0;
    need(!valid(), "missing required ACPI window path");
    window_path = window_saved;
    need(tables.used() < Handoff::table_pages, "one spare model table for inventory controls");
    const auto spare = root + tables.used() * 4096;
    PageTables counted{root, tables.used() + 1};
    put(h, 96, counted.used());
    need(!counted.verify_graphical(arena, Bytes{h}, &*apic, &*graphics), "disconnected counted table");
    auto &extra = slot(root, 0xffffb00000000000ULL, 3);
    need(extra == 0, "unrequired root aperture starts empty");
    extra = spare | 3;
    need(!counted.verify_graphical(arena, Bytes{h}, &*apic, &*graphics), "counted empty unrequired subtree");
    extra = 0;
    put(h, 96, tables.used());
    need(extra == 0, "unused high root slot");
    extra = slot(root, first, 3);
    need(!valid(), "shared subtree alias");
    extra = 0;
    need(valid(), "all mutations restore exact paired model");
    // Constructors must deny framebuffer resource overlap before any mapping.
    for (U64 physical : {arena, U64{0xfee00000}, U64{0xfec00000}, U64{0xe0000000}})
        need(!graphics_grant(arena, physical), "owned arena/APIC/IOAPIC/ECAM resource overlap");
    std::cout << "PASS: graphical paired paging model " << checks << " checks\n";
}
