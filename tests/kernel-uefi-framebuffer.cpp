#include "../kernel/uefi/framebuffer-policy.hpp"
#include <array>
#include <cstdlib>
#include <iostream>

namespace {
using namespace aurora::uefi;
using U64 = std::uint64_t;
unsigned checks{};
auto need(bool value) -> void {
    ++checks;
    if (!value)
        std::abort();
}
auto geometry(U64 base = 0xc0000000,
              U64 bytes = 0x300000,
              unsigned width = 1024,
              unsigned height = 768,
              unsigned pitch = 1024,
              unsigned format = 0,
              unsigned bits = 36) {
    return FramebufferGeometry::parse(base, bytes, width, height, pitch, format, bits);
}
} // namespace
int main() {
    const auto rgb = geometry(), bgr = geometry(0xc0000000, 0x300000, 1024, 768, 1024, 1);
    need(rgb.has_value() && bgr.has_value());
    need(rgb->pack(0x12, 0x34, 0x56) == 0x00563412);
    need(bgr->pack(0x12, 0x34, 0x56) == 0x00123456);
    need(rgb->pixel_offset(1023, 767) == 3145724);
    need(!rgb->pixel_offset(1024, 0) && !rgb->pixel_offset(0, 768));
    need(!rgb->pixel_offset(UINT64_MAX, 0) && !rgb->pixel_offset(0, UINT64_MAX));
    for (U64 base : {U64{0}, U64{1}, U64{0xc0000001}, UINT64_MAX, U64{1} << 36})
        need(!geometry(base));
    for (U64 size : {U64{0}, U64{1}, U64{0x2fffff}, UINT64_MAX})
        need(!geometry(0xc0000000, size));
    for (unsigned format : {2U, 3U, UINT32_MAX})
        need(!geometry(0xc0000000, 0x300000, 1024, 768, 1024, format));
    for (unsigned bits : {0U, 31U, 53U, UINT32_MAX})
        need(!geometry(0xc0000000, 0x300000, 1024, 768, 1024, 0, bits));
    need(!geometry(0xc0000000, 0x300000, 1025));
    need(!geometry(0xc0000000, 0x300000, 1024, 769));
    need(!geometry(0xc0000000, 0x300000, 1024, 768, 1023));
    need(!geometry(0xc0000000, 4, 1, 1, 1)); // rounded page lacks resource authority
    const auto small = geometry(0xc0000000, 4096, 1, 1, 1);
    need(small && small->mapped_bytes() == 4096 && small->visible_bytes() == 4);
    std::array<std::byte, 64> record{};
    put(record, 0, FramebufferRecord::magic);
    put(record, 8, 1, 4);
    put(record, 12, 64, 4);
    put(record, 16, 0xc0000000);
    put(record, 24, 0x300000);
    put(record, 32, 1024, 4);
    put(record, 36, 768, 4);
    put(record, 40, 1024, 4);
    put(record, 48, 0, 4);
    put(record, 52, 1, 4);
    const auto copied = FramebufferRecord::parse(record, 36);
    need(copied.has_value());
    std::array<std::byte, 64> roundtrip{};
    need(FramebufferRecord::write(roundtrip, *copied));
    need(roundtrip == record);
    need(FramebufferRecord::parse(record, 36).has_value());
    for (unsigned at : {0U, 8U, 12U, 48U, 56U}) {
        auto bad = record;
        bad[at] ^= std::byte{1};
        need(!FramebufferRecord::parse(bad, 36));
    }
    std::array<std::byte, 80> map{};
    put(map, 0, 1, 4);
    put(map, 8, 0x1000000);
    put(map, 24, Handoff::arena_bytes / 4096);
    put(map, 40, 11, 4);
    put(map, 48, 0xc0000000);
    put(map, 64, 768);
    put(map, 72, 1);
    const auto grant = [&](std::span<const std::byte> bytes) {
        return FramebufferAdmission::authorize_described(
            *rgb, bytes, 40, 1, 0x1000000, 36, (1U << 5) | (1U << 16), 0x0007040600070406ULL);
    };
    const auto admitted = grant(map);
    need(admitted.has_value());
    need(admitted->mapping(0xffffa00000001000ULL) == (0xc0000000ULL | 0x800000000000001bULL));
    need(admitted->mapping(0xffffa00000000000ULL) == 0);
    need(admitted->mapping(0xffffa00000301000ULL) == 0);
    need(admitted->mapping(0xffffa00000001001ULL) == 0);
    need(!grant(std::span<const std::byte>{map}.first(40))); // omitted aperture denies
    for (unsigned type = 0; type <= 15; ++type) {
        auto bad = map;
        put(bad, 40, type, 4);
        need(grant(bad).has_value() == (type == 0 || type == 11));
    }
    for (unsigned bit = 0; bit < 64; ++bit) {
        auto bad = map;
        put(bad, 72, U64{1} << bit);
        need(grant(bad).has_value() == (bit == 0 || bit == 14));
    }
    const auto custom_grant = [&](const FramebufferGeometry &g,
                                  std::span<const std::byte> bytes,
                                  unsigned bits = 36,
                                  U64 pat = 0x0007040600070406ULL) {
        return FramebufferAdmission::authorize_described(g, bytes, 40, 1, 0x1000000, bits, (1U << 5) | (1U << 16), pat);
    };
    // Regressions for the review finding: these described MMIO resources must
    // never become pixel authority, including one-page partial intersections.
    for (U64 forbidden : {U64{0xfec00000}, U64{0xfee00000}, U64{0xe0000000}, U64{0xeffff000}}) {
        for (U64 start : {forbidden, forbidden - 4096}) {
            const auto g = geometry(start, 8192, 1024, 2, 1024);
            need(g.has_value());
            auto conflict = map;
            put(conflict, 48, start);
            put(conflict, 64, 2);
            need(!custom_grant(*g, conflict));
        }
    }
    for (U64 base : {U64{0x1000000}, U64{0x1000000 + Handoff::arena_bytes - 4096}, U64{0xfff000}}) {
        const auto g = geometry(base, 8192, 1024, 2, 1024);
        need(g.has_value());
        need(!custom_grant(*g, map));
    }
    need(!custom_grant(*rgb, map, 31));
    need(!custom_grant(*rgb, map, 53));
    for (unsigned value = 1; value < 256; ++value)
        need(!custom_grant(*rgb, map, 36, U64{value} << 24));
    // A split descriptor set covers all pages; removing one page is not enough.
    std::array<std::byte, 120> split{};
    for (unsigned at = 0; at < 80; ++at)
        split[at] = map[at];
    put(split, 64, 384);
    put(split, 80, 11, 4);
    put(split, 88, 0xc0180000);
    put(split, 104, 384);
    put(split, 112, 1);
    need(custom_grant(*rgb, split).has_value());
    auto hole = split;
    put(hole, 64, 383);
    need(!custom_grant(*rgb, hole));
    auto overlap = split;
    put(overlap, 88, 0xc017f000);
    need(!custom_grant(*rgb, overlap));
    for (unsigned type : {1U, 2U, 3U, 4U, 7U, 9U, 10U, 14U}) {
        auto conflict = split;
        put(conflict, 80, type, 4);
        need(!custom_grant(*rgb, conflict));
    }
    auto runtime = split;
    put(runtime, 112, U64{1} << 63);
    need(!custom_grant(*rgb, runtime));
    // Odd widths and padded rows retain exact visible coordinate bounds.
    for (unsigned width : {1U, 7U, 31U, 799U, 1023U}) {
        const auto padded = geometry(0xc0000000, 0x300000, width, 3, 1024);
        need(padded && padded->pixel_offset(width - 1, 2) == (2048 + width - 1) * 4);
        need(!padded->pixel_offset(width, 2));
    }
    std::cout << "PASS: framebuffer copied geometry and strict admission " << checks << " checks\n";
}
