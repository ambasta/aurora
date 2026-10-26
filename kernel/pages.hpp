#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <utility>

namespace aurora::memory {
class PhysicalPages;
template <std::size_t Capacity> class PhysicalPagePool;
// Single-owner token. Explicit release avoids destructor dependencies in bootstrap.
// A dropped token leaks its page; it cannot make that page available to an alias.
class PageLease final {
    friend class PhysicalPages;
    PhysicalPages *owner_;
    std::size_t index_;
    std::uint64_t generation_;
    std::uint64_t epoch_;
    PageLease(PhysicalPages &owner, std::size_t index, std::uint64_t generation, std::uint64_t epoch)
        : owner_(&owner), index_(index), generation_(generation), epoch_(epoch) {
    }

public:
    PageLease(const PageLease &) = delete;
    auto operator=(const PageLease &) -> PageLease & = delete;
    auto operator=(PageLease &&) -> PageLease & = delete;
    PageLease(PageLease &&other) noexcept
        : owner_(std::exchange(other.owner_, nullptr)), index_(other.index_), generation_(other.generation_),
          epoch_(other.epoch_) {
    }
    // Local move/release state only; allocator.address validates current ownership.
    [[nodiscard]] auto valid() const -> bool {
        return owner_ != nullptr;
    }
};

// Single CPU only. No concurrency or hardware memory isolation is implied.
class PhysicalPages final {
    friend class PhysicalPagePool<16>;
    friend class PhysicalPagePool<128>;

public:
    static constexpr std::size_t max_capacity = 128;
    static constexpr std::uint64_t page_size = 4096;

private:
    inline static std::uint64_t next_epoch_{};
    std::uint64_t epoch_{};
    std::span<bool> allocated_{};
    std::span<std::uint64_t> generations_{};
    std::uint64_t base_{};
    std::size_t count_{};
    std::size_t used_{};
    [[nodiscard]] auto owns(const PageLease &lease) const -> bool {
        return lease.owner_ == this && lease.epoch_ == epoch_ && lease.index_ < count_ && allocated_[lease.index_] &&
               generations_[lease.index_] == lease.generation_;
    }

    PhysicalPages() = default;
    // Only the fixed owner can bind its own zero-initialized metadata. No stored
    // self pointers or dynamic initialization are needed for static owners.
    [[nodiscard]] auto initialize_owned(std::uint64_t base,
                                        std::size_t count,
                                        std::span<bool> allocated,
                                        std::span<std::uint64_t> generations) -> bool {
        if (next_epoch_ == UINT64_MAX || count_ != 0 || count == 0 || count > allocated.size() ||
            base % page_size != 0 || base > UINT64_MAX - count * page_size)
            return false;
        allocated_ = allocated;
        generations_ = generations;
        epoch_ = ++next_epoch_;
        base_ = base;
        count_ = count;
        return true;
    }

    ~PhysicalPages() = default;

public:
    PhysicalPages(const PhysicalPages &) = delete;
    auto operator=(const PhysicalPages &) -> PhysicalPages & = delete;
    [[nodiscard]] auto acquire() -> std::optional<PageLease> {
        for (std::size_t index = 0; index < count_; ++index) {
            // A wrapped generation is retired forever, never reused.
            if (!allocated_[index] && generations_[index] != UINT64_MAX) {
                allocated_[index] = true;
                ++generations_[index];
                ++used_;
                return PageLease(*this, index, generations_[index], epoch_);
            }
        }
        return std::nullopt;
    }
    [[nodiscard]] auto address(const PageLease &lease) const -> std::optional<std::uint64_t> {
        if (!owns(lease))
            return std::nullopt;
        return base_ + lease.index_ * page_size;
    }
    [[nodiscard]] auto release(PageLease &lease) -> bool {
        if (!owns(lease))
            return false;
        allocated_[lease.index_] = false;
        --used_;
        lease.owner_ = nullptr;
        return true;
    }
    [[nodiscard]] auto arena_matches(std::uint64_t base, std::size_t count) const -> bool {
        return count_ != 0 && base_ == base && count_ == count;
    }
    [[nodiscard]] auto used() const -> std::size_t {
        return used_;
    }
};
// Private fixed storage and its ordinary core member share one nonmoving owner
// lifetime. Consumers use PhysicalPages references, sharing one lease algorithm.
// Unlike a base subobject, the ordinary member is transparently replaced when a
// same-type owner is reconstructed; its new epoch still rejects old leases.
template <std::size_t Capacity = PhysicalPages::max_capacity> class PhysicalPagePool final {
    static_assert(Capacity == 16 || Capacity == PhysicalPages::max_capacity);
    PhysicalPages core_{};
    std::array<bool, Capacity> allocated_{};
    std::array<std::uint64_t, Capacity> generations_{};

public:
    static constexpr std::size_t capacity = Capacity;
    PhysicalPagePool() = default;
    PhysicalPagePool(const PhysicalPagePool &) = delete;
    auto operator=(const PhysicalPagePool &) -> PhysicalPagePool & = delete;
    // Caller must prove exclusive ownership of a usable physical range first.
    [[nodiscard]] auto initialize(std::uint64_t base, std::size_t count) -> bool {
        return core_.initialize_owned(base, count, allocated_, generations_);
    }
    operator PhysicalPages &() & {
        return core_;
    }
    [[nodiscard]] auto acquire() -> std::optional<PageLease> {
        return core_.acquire();
    }
    [[nodiscard]] auto address(const PageLease &lease) const -> std::optional<std::uint64_t> {
        return core_.address(lease);
    }
    [[nodiscard]] auto release(PageLease &lease) -> bool {
        return core_.release(lease);
    }
    [[nodiscard]] auto arena_matches(std::uint64_t base, std::size_t count) const -> bool {
        return core_.arena_matches(base, count);
    }
    [[nodiscard]] auto used() const -> std::size_t {
        return core_.used();
    }
};
// Instantiate both closed owner types here: downstream explicit specializations
// must not acquire the private core-construction or storage-binding authority.
static_assert(sizeof(PhysicalPagePool<16>) < sizeof(PhysicalPagePool<128>));
} // namespace aurora::memory
