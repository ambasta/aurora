#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

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

// One fixed, one-shot command batch for the Event guest's requester/domain.
// The caller owns an aligned boot-lifetime command page, proves its physical
// identity and keeps it retained on *every* outcome. This is not DMA authority
// or permission to reclaim memory. prepare() never publishes; the trusted guest
// writes the one tail only after it has revoked the two leaf permissions.
// Wire commands match the reviewed transport-import-v1.py invalidate sequence.
template <unsigned requester> class BootInvalidation final {
    static_assert(requester == 0x20 || requester == 0x10);

public:
    enum class Result {
        pending,
        complete,
        failed
    };
    static constexpr std::uint64_t command_bytes = 48, completion_offset = 0x100;
    static constexpr std::uint64_t poison = 0x3759bed12468acf0ULL, nonce = 0xdb1937456280acefULL;

private:
    std::span<std::byte> page_;
    std::uint64_t physical_, head_{};
    bool attempted_{};
    Result result_ = Result::pending;

    auto store(std::size_t offset, std::uint64_t value) -> void {
        *reinterpret_cast<volatile std::uint64_t *>(page_.data() + offset) = value;
    }
    [[nodiscard]] auto word(std::size_t offset) const -> std::uint64_t {
        return *reinterpret_cast<volatile const std::uint64_t *>(page_.data() + offset);
    }
    [[nodiscard]] auto guards() const -> bool {
        const volatile std::byte *bytes = page_.data();
        for (unsigned i = 0; i < 16; ++i)
            if (bytes[completion_offset - 16 + i] != std::byte(0xa0 + i) ||
                bytes[completion_offset + 8 + i] != std::byte(0x50 + i))
                return false;
        return true;
    }

public:
    BootInvalidation(std::span<std::byte> page, std::uint64_t physical) : page_(page), physical_(physical) {
    }
    BootInvalidation(const BootInvalidation &) = delete;
    auto operator=(const BootInvalidation &) -> BootInvalidation & = delete;
    BootInvalidation(BootInvalidation &&) = delete;
    auto operator=(BootInvalidation &&) -> BootInvalidation & = delete;

    [[nodiscard]] auto prepare(std::uint64_t head, std::uint64_t tail, std::uint64_t status) -> bool {
        if (attempted_)
            return false;
        attempted_ = true;
        if (page_.size() != 4096 || reinterpret_cast<std::uintptr_t>(page_.data()) % 4096 || !physical_ ||
            physical_ % 4096 || physical_ >= (1ULL << 40) || head || tail || status != 0x18) {
            result_ = Result::failed;
            return false;
        }
        // The initial register observation is cold; a previous command engine
        // must never be rebound to this page or this one-shot owner reconstructed.
        for (unsigned i = 0; i < 16; ++i) {
            page_[completion_offset - 16 + i] = std::byte(0xa0 + i);
            page_[completion_offset + 8 + i] = std::byte(0x50 + i);
        }
        store(completion_offset, poison);
        store(0, (2ULL << 60) | requester);
        store(8, 0);
        store(16, (3ULL << 60) | (EventBackingPolicy::domain << 32));
        store(24, 0x7ffffffffffff001ULL);
        store(32, (1ULL << 60) | (physical_ + completion_offset) | 5);
        store(40, nonce);
        asm volatile("mfence" : : : "memory");
        if (word(completion_offset) != poison || !guards()) {
            result_ = Result::failed;
            return false;
        }
        return true;
    }

    // A stopped/error command engine, any event, changed tail, backwards or
    // malformed head, unexpected store or overwritten guard is absorbing.
    // Pending is not success; caller must expire on its bounded polling limit.
    [[nodiscard]] auto observe(std::uint64_t head,
                               std::uint64_t tail,
                               std::uint64_t status,
                               std::uint64_t event_head,
                               std::uint64_t event_tail) -> Result {
        if (!attempted_ || result_ != Result::pending)
            return expire();
        if (head < head_ || head > command_bytes || head % 16 || tail != command_bytes || status != 0x18 ||
            event_head || event_tail || !guards())
            return expire();
        head_ = head;
        asm volatile("lfence" : : : "memory");
        const auto value = word(completion_offset);
        if (value != poison && value != nonce)
            return expire();
        if (head == command_bytes && value == nonce)
            result_ = Result::complete;
        return result_;
    }
    auto expire() -> Result {
        attempted_ = true;
        result_ = Result::failed;
        return result_;
    }
};

using EventInvalidation = BootInvalidation<0x20>;
using NvmeInvalidation = BootInvalidation<0x10>;

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

    // V=TV=1, Mode0 and no IR/IW is deny, not the V=0 identity bypass.
    // The one permitted requester gets the separately owned Mode1 root.
    [[nodiscard]] auto initialize_device_table(std::uint64_t root) -> bool {
        if (!root || root % 4096 || root >= (1ULL << 40))
            return false;
        device_table.fill(std::byte{0});
        for (unsigned requester = 0; requester < 256; ++requester)
            device_table[requester * 32] = std::byte{3};
        const auto control = root | 0x203 | EventBackingPolicy::read_permission | EventBackingPolicy::write_permission;
        for (unsigned i = 0; i < 8; ++i) {
            device_table[EventBackingPolicy::requester * 32 + i] = std::byte(control >> (8 * i));
            device_table[EventBackingPolicy::requester * 32 + 8 + i] = std::byte(EventBackingPolicy::domain >> (8 * i));
        }
        return true;
    }
};
static_assert(sizeof(EventBacking) == 32768 && alignof(EventBacking) == 4096);
static_assert(offsetof(EventBacking, page_table) == 8192 && offsetof(EventBacking, command_ring) == 12288 &&
              offsetof(EventBacking, secret) == 16384 && offsetof(EventBacking, target) == 20480 &&
              offsetof(EventBacking, helper) == 24576 && offsetof(EventBacking, sink) == 28672);
} // namespace aurora::uefi
