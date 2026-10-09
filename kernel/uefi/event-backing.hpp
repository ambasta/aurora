#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace aurora::uefi {
// Integer-only checks used by the opt-in bootstrap owner. Passing these checks
// does not grant MMIO access or establish hardware DMA/coherence support.
class EventBackingPolicy final {
public:
    static constexpr std::uint64_t page_bytes = 4096;
    static constexpr std::uint64_t requester = 0x20, domain = 0x1234;
    static constexpr std::uint64_t data_offset = 0x100, transfer_bytes = 4;
    static constexpr std::uint64_t secret_iova = 0x3100, target_iova = 0x4100;
    static constexpr std::uint64_t helper_iova = 0x5100, sink_iova = 0x6100;
    static constexpr std::uint64_t read_permission = 1ULL << 61, write_permission = 1ULL << 62;
    static constexpr std::uint64_t poison_word0 = 0xf5a55a5adead0000ULL;
    static constexpr std::uint64_t poison_word1 = 0xbad0000000000000ULL;
    // An attempt budget, deliberately not a wall-clock or physical-drain claim.
    static constexpr std::uint64_t readiness_attempts = 1ULL << 24;

    [[nodiscard]] static constexpr auto
    contains(std::uint64_t begin, std::uint64_t bytes, std::uint64_t object, std::uint64_t count) -> bool {
        return bytes != 0 && count != 0 && bytes <= UINT64_MAX - begin && object >= begin && object - begin <= bytes &&
               count <= bytes - (object - begin);
    }
    [[nodiscard]] static constexpr auto
    disjoint(std::uint64_t a, std::uint64_t size_a, std::uint64_t b, std::uint64_t size_b) -> bool {
        return size_a != 0 && size_b != 0 && size_a <= UINT64_MAX - a && size_b <= UINT64_MAX - b &&
               (a + size_a <= b || b + size_b <= a);
    }
    [[nodiscard]] static constexpr auto
    page_extent(std::uint64_t begin, std::uint64_t bytes, std::uint64_t object, std::uint64_t count) -> bool {
        return object != 0 && object % page_bytes == 0 && count % page_bytes == 0 &&
               contains(begin, bytes, object, count) && object < (1ULL << 40) && count <= (1ULL << 40) - object;
    }
    [[nodiscard]] static constexpr auto head_step(std::uint64_t old, std::uint64_t next) -> bool {
        return old < page_bytes && old % 16 == 0 && next < page_bytes && next % 16 == 0 &&
               next == (old + 16) % page_bytes;
    }
    [[nodiscard]] static constexpr auto iommu_read(std::uint64_t offset) -> bool {
        return offset == 0 || offset == 8 || offset == 0x10 || offset == 0x18 || offset == 0x30 || offset == 0x2000 ||
               offset == 0x2008 || offset == 0x2010 || offset == 0x2018 || offset == 0x2020;
    }
    [[nodiscard]] static constexpr auto producer_iova(std::uint64_t address, bool write) -> bool {
        return write ? address == target_iova || address == sink_iova
                     : address == secret_iova || address == helper_iova;
    }
    [[nodiscard]] static constexpr auto fault_word(bool write) -> std::uint64_t {
        return (2ULL << 60) | (1ULL << 54) | (std::uint64_t{write} << 53) | (1ULL << 52) | (domain << 32) | requester;
    }
    [[nodiscard]] static constexpr auto frozen_registers_match(const std::array<std::uint64_t, 12> &observed,
                                                               const std::array<std::uint64_t, 12> &fixed) -> bool {
        if ((observed[9] & ~0x1fULL) || observed[7] >= page_bytes || observed[7] % 16)
            return false;
        for (unsigned index = 0; index < observed.size(); ++index)
            if (index != 7 && index != 9 && observed[index] != fixed[index])
                return false;
        // The session validates the exact expected head and interprets supported
        // status, including newly observed overflow. Never hide loss by turning
        // a supported status transition into an unreadable transport sample.
        return true;
    }
};

// No arena pool, pin-ledger storage, free operation, or reset operation exists.
// Complete pages are retained even if publication, production or intake fails.
class alignas(4096) EventBacking final {
public:
    std::array<std::byte, 8192> device_table{};
    std::array<std::byte, 4096> page_table{};
    std::array<std::byte, 4096> command_ring{};
    std::array<std::byte, 4096> secret{};
    std::array<std::byte, 4096> target{};
    std::array<std::byte, 4096> helper{};
    std::array<std::byte, 4096> sink{};
};
static_assert(sizeof(EventBacking) == 32768 && alignof(EventBacking) == 4096);
static_assert(offsetof(EventBacking, page_table) == 8192 && offsetof(EventBacking, command_ring) == 12288 &&
              offsetof(EventBacking, secret) == 16384 && offsetof(EventBacking, target) == 20480 &&
              offsetof(EventBacking, helper) == 24576 && offsetof(EventBacking, sink) == 28672);
} // namespace aurora::uefi
