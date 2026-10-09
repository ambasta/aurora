#include "../kernel/uefi/event-backing.hpp"
#include <cstdio>
#include <cstdlib>

namespace {
using Policy = aurora::uefi::EventBackingPolicy;
unsigned checked{};
auto need(bool condition, const char *name) -> void {
    ++checked;
    if (!condition) {
        std::fprintf(stderr, "event backing failed: %s\n", name);
        std::exit(1);
    }
}
} // namespace

auto main() -> int {
    constexpr std::uint64_t begin = 0x140000, bytes = 0x10000;
    need(Policy::page_extent(begin, bytes, begin, bytes), "exact owned writable interval");
    need(Policy::page_extent(begin, bytes, begin + 8192, 4096), "interior page");
    need(!Policy::page_extent(begin, bytes, begin - 4096, 8192), "cross left boundary");
    need(!Policy::page_extent(begin, bytes, begin + bytes - 4096, 8192), "cross right boundary");
    need(!Policy::page_extent(begin, bytes, begin + bytes, 4096), "end is not storage");
    need(!Policy::page_extent(begin, bytes, begin + 1, 4096), "unaligned published base");
    need(!Policy::page_extent(begin, bytes, begin, 4095), "partial published page");
    need(!Policy::page_extent(begin, bytes, begin, 0), "zero allocation");
    need(!Policy::page_extent(0, 4096, 0, 4096), "zero physical address");
    need(Policy::page_extent((1ULL << 40) - 4096, 4096, (1ULL << 40) - 4096, 4096), "last 40-bit page");
    need(!Policy::page_extent((1ULL << 40) - 4096, 8192, (1ULL << 40) - 4096, 8192), "cross 40-bit boundary");
    need(!Policy::page_extent(1ULL << 40, 4096, 1ULL << 40, 4096), "high address");
    need(!Policy::contains(UINT64_MAX - 7, 16, UINT64_MAX - 3, 4), "wrapping owner interval");
    need(!Policy::contains(begin, bytes, UINT64_MAX - 1, 8), "wrapping object interval");
    need(Policy::contains(begin, bytes, begin + bytes - 1, 1), "last byte");
    need(!Policy::contains(begin, bytes, begin + bytes, 1), "one-past final byte");
    need(Policy::disjoint(begin, 4096, begin + 4096, 4096), "adjacent backing pages");
    need(Policy::disjoint(begin + 4096, 4096, begin, 4096), "adjacency reversed");
    need(!Policy::disjoint(begin, 4096, begin + 4095, 4096), "one-byte overlap");
    need(!Policy::disjoint(begin, 8192, begin + 4096, 4096), "contained allocation");
    need(!Policy::disjoint(UINT64_MAX - 4095, 4096, begin, 4096), "wrapping allocation");
    need(!Policy::disjoint(begin, 0, begin, 4096), "empty disjointness cannot admit owner");

    for (std::uint64_t old = 0; old < 4096; old += 16) {
        const auto next = (old + 16) % 4096;
        need(Policy::head_step(old, next), "every single head step including wrap");
        need(!Policy::head_step(old, old), "repeated head cannot commit");
        need(!Policy::head_step(old, (next + 16) % 4096), "skipping pending record");
        need(!Policy::head_step(old, next + 1), "unaligned head");
    }
    need(!Policy::head_step(UINT64_MAX - 15, 0), "wrapping forged old head");
    need(!Policy::head_step(4080, 4096), "ring end must wrap to zero");

    constexpr std::uint64_t admitted[] = {0, 8, 16, 24, 48, 8192, 8200, 8208, 8216, 8224};
    unsigned count{};
    for (std::uint64_t offset = 0; offset < 0x4000; ++offset) {
        bool expected = false;
        for (const auto allowed : admitted)
            expected = expected || allowed == offset;
        need(Policy::iommu_read(offset) == expected, "complete aperture read allowlist");
        if (Policy::iommu_read(offset))
            ++count;
    }
    need(count == 10 && !Policy::iommu_read(UINT64_MAX), "no hidden register authority");
    for (bool write : {false, true}) {
        need(!Policy::producer_iova(0, write), "zero producer address");
        need(!Policy::producer_iova(begin, write), "physical address is not an IOVA");
        need(!Policy::producer_iova(UINT64_MAX, write), "unbounded producer address");
        for (const auto candidate : {0x3100ULL, 0x4100ULL, 0x5100ULL, 0x6100ULL}) {
            need(Policy::producer_iova(candidate, write) ==
                     (write ? candidate == 0x4100 || candidate == 0x6100 : candidate == 0x3100 || candidate == 0x5100),
                 "direction-bound finite producer address");
            need(!Policy::producer_iova(candidate + 4, write), "producer subrange is not generic DMA authority");
        }
    }
    const std::array<std::uint64_t, 12> fixed = {
        0x140001, 0, (8ULL << 56) | 0x145000, 5, 0x29d3, 0, 0, 0, 32, 10, 2, 4};
    auto observed = fixed;
    need(Policy::frozen_registers_match(observed, fixed), "stable real-profile register binding");
    observed[9] |= 1;
    need(Policy::frozen_registers_match(observed, fixed), "supported overflow remains readable for session");
    observed[9] |= 1ULL << 63;
    need(!Policy::frozen_registers_match(observed, fixed), "unknown full-width status remains denied");
    for (unsigned index = 0; index < fixed.size(); ++index) {
        if (index == 7 || index == 9)
            continue;
        observed = fixed;
        observed[index] ^= 1;
        need(!Policy::frozen_registers_match(observed, fixed), "fixed producer/configuration drift");
    }
    observed = fixed;
    observed[7] = 16;
    need(Policy::frozen_registers_match(observed, fixed), "head classification delegated to session");
    observed[7] = 17;
    need(!Policy::frozen_registers_match(observed, fixed), "unaligned observed head denied");
    observed[7] = 4096;
    need(!Policy::frozen_registers_match(observed, fixed), "out-of-ring observed head denied");
    need(sizeof(aurora::uefi::EventBacking) + 3 * 4096 <= 128 * 1024, "backing alone fits reservation");
    // This is only layout/policy accounting; the final linked image, actual BSS
    // mapping, mixed-language stack, and guest require separate admission.
    std::printf("event backing policy: %u checks passed\n", checked);
}
