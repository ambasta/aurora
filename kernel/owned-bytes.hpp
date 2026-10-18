#pragma once

#include "../runtime/bytes_abi.hpp"
#include "pages.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <type_traits>

#if defined(AURORA_KERNEL_BYTES_TESTING) && AURORA_KERNEL_BYTES_TESTING != 1
#error "Kernel byte test interfaces require explicit AURORA_KERNEL_BYTES_TESTING=1"
#endif

namespace aurora::kernel::bytes {

struct Metrics {
    std::uint64_t quota = 0;
    std::uint64_t used = 0;
    std::uint64_t live_allocations = 0;
    std::uint64_t successful_allocations = 0;
    std::uint64_t releases = 0;
    std::uint64_t peak_live_allocations = 0;
    std::uint64_t peak_used = 0;
    std::uint64_t last_allocation_id = 0;
    std::uint64_t last_released_id = 0;
    std::uint64_t held_pages = 0;
    std::uint64_t peak_held_pages = 0;
    std::uint64_t retained_pages = 0;

    bool operator==(const Metrics &) const = default;
};

class RuntimeAccess;

// Trusted, synchronous, single-CPU grant over the existing physical allocator.
// The caller proves backing is the exclusive CPU mapping of the exact pool range.
// Pool, backing and this object's storage outlive every registered/retained owner.
// Destruction releases nothing: explicit close must precede storage reclamation.
// There is no user mapping, address/view export, lease import or device operation.
class Region final {
public:
    static constexpr std::size_t max_allocations = 4;
    static constexpr std::size_t pool_pages = 16;
    static constexpr std::size_t page_bytes = memory::PhysicalPages::page_size;
    static constexpr std::size_t backing_bytes = pool_pages * page_bytes;

    constexpr Region() noexcept = default;
    ~Region() = default;
    Region(const Region &) = delete;
    Region &operator=(const Region &) = delete;
    Region(Region &&) = delete;
    Region &operator=(Region &&) = delete;

    [[nodiscard]] bool open(memory::PhysicalPages &pool,
                            std::span<std::byte> backing,
                            std::uint64_t base,
                            std::uint64_t payload_quota) noexcept;
    [[nodiscard]] bool close() noexcept;
    // Trusted teardown only: the caller has stopped the owning domain, restored
    // kernel authority and drained interrupts. No descriptor or continuation can
    // execute again. Scrub failure retains leases and never returns.
    [[nodiscard]] bool revoke_quiescent() noexcept;
    [[nodiscard]] std::uint64_t id() const noexcept {
        return id_;
    }
    [[nodiscard]] bool is_open() const noexcept {
        return open_;
    }
    [[nodiscard]] bool faulted() const noexcept {
        return faulted_;
    }
    [[nodiscard]] Metrics metrics() const noexcept {
        return metrics_;
    }

#ifdef AURORA_KERNEL_BYTES_TESTING
    // A hosted-only CPU readback corruption, never a hardware completion signal.
    void fail_scrub_for_test(std::size_t page_ordinal, std::size_t successful_scrubs = 0) noexcept {
        failed_scrub_ = page_ordinal;
        scrub_skip_ = successful_scrubs;
    }
    [[nodiscard]] std::size_t retained_records_for_test() const noexcept;
    [[nodiscard]] std::size_t preparing_records_for_test() const noexcept;
    [[nodiscard]] bool inactive_records_clean_for_test() const noexcept;
    [[nodiscard]] bool advance_counters_for_test(std::uint64_t allocations, std::uint64_t releases) noexcept;

#endif

private:
    enum class State {
        empty,
        preparing,
        live,
        retained
    };
    struct Allocation {
        std::array<std::optional<memory::PageLease>, pool_pages> pages{};
        std::uint64_t id = 0;
        std::int64_t length = 0;
        std::size_t count = 0;
        State state = State::empty;
    };

    friend class RuntimeAccess;
    memory::PhysicalPages *pool_ = nullptr;
    std::span<std::byte> backing_{};
    std::uint64_t base_ = 0;
    std::uint64_t id_ = 0;
    bool open_ = false;
    bool faulted_ = false;
    Metrics metrics_{};
    std::array<Allocation, max_allocations> allocations_{};
    Region *next_ = nullptr;
#ifdef AURORA_KERNEL_BYTES_TESTING
    std::size_t failed_scrub_ = pool_pages;
    std::size_t scrub_skip_ = 0;
#endif

    [[nodiscard]] bool backing_valid() const noexcept;
    [[nodiscard]] std::optional<std::span<std::byte>> page(Allocation &allocation, std::size_t index) noexcept;
    [[nodiscard]] bool scrub(Allocation &allocation) noexcept;
    void release_pages(Allocation &allocation, Allocation *transaction_peer = nullptr) noexcept;
    void release_live(Allocation &allocation) noexcept;
    [[noreturn]] void retain(Allocation &allocation) noexcept;
};

static_assert(std::is_trivially_destructible_v<Region>);
static_assert(sizeof(Region) <= 3072, "Kernel byte metadata must remain in its reviewed static bound");

#ifdef AURORA_KERNEL_BYTES_TESTING
namespace testing {
// Only skip forward with no registered region; never revive an exhausted ID.
void advance_next_ids(std::uint64_t region, std::uint64_t allocation) noexcept;
} // namespace testing
#endif

} // namespace aurora::kernel::bytes

// The profile supplies the fail-stop endpoint; hosted tests supply an isolated
// observer instead. It must never return, unwind, reenter or release resources.
// 1 = descriptor/authority invariant, 2 = bounds, 3 = retained CPU page failure.
extern "C" [[noreturn]] void __au_runtime_bytes_kernel_fault(std::uint64_t reason) noexcept;
