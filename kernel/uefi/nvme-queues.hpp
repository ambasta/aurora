#pragma once
#include "bar-policy.hpp"
#include "../pages.hpp"

#if defined(AURORA_NVME_QUEUE_TESTING) && AURORA_NVME_QUEUE_TESTING != 1
#error "Queue test interfaces require explicit AURORA_NVME_QUEUE_TESTING=1"
#endif
#if defined(AURORA_NVME_QUEUE_GENERATION_LIMIT) && !defined(AURORA_NVME_QUEUE_TESTING)
#error "A small queue generation limit is only available in explicit test builds"
#endif

namespace aurora::uefi {
class NvmeQueueBundle;

// Copied CPU preparation identity, never a page address, device grant or completion.
class NvmeQueueHandle final {
    friend class NvmeQueueBundle;
    const NvmeQueueBundle *owner_{};
    std::uint64_t epoch_{};
    std::uint64_t generation_{};

    NvmeQueueHandle(const NvmeQueueBundle &owner, std::uint64_t epoch, std::uint64_t generation)
        : owner_(&owner), epoch_(epoch), generation_(generation) {}

public:
    NvmeQueueHandle() = default;
    [[nodiscard]] auto generation() const -> std::uint64_t { return generation_; }
};

// Single-CPU, fixed five-page preparation over the existing allocator, not a
// second allocator or a DMA pin ledger. The trusted caller proves this span is
// the exclusive CPU mapping of the pool's exact physical range. Pool and backing
// storage must outlive the bundle, including any retained leases. Destruction
// leaks retained allocation bookkeeping; PageLease destruction never releases.
// No address, view, lease import, publication, command or completion API exists.
class NvmeQueueBundle final {
public:
    static constexpr std::size_t page_count = 5;
    static constexpr std::size_t pool_pages = 16;
    static constexpr std::size_t page_bytes = memory::PhysicalPages::page_size;
    static constexpr std::size_t queue_entries = 2;
    enum class Role { admin_submission, admin_completion, io_submission, io_completion, data };
    enum class Direction { device_reads, device_writes };

private:
    enum class State { empty, preparing, prepared, retained };
    inline static std::uint64_t next_epoch_{};
    memory::PhysicalPages &pool_;
    std::span<std::byte> backing_;
    std::uint64_t base_;
    std::uint64_t epoch_{};
    std::uint64_t generation_{};
    State state_ = State::empty;
    std::array<std::optional<memory::PageLease>, page_count> leases_{};
    std::size_t count_{};
    // This copied receipt is usable only with its still-live WindowAuthority.
    // Cancellation deliberately needs no BAR authority: nothing was published.
    std::optional<NvmeBarGrant> session_{};
#ifdef AURORA_NVME_QUEUE_TESTING
    std::size_t failed_scrub_ = page_count;
#endif
#ifdef AURORA_NVME_QUEUE_GENERATION_LIMIT
    static_assert(AURORA_NVME_QUEUE_GENERATION_LIMIT > 0
                  && AURORA_NVME_QUEUE_GENERATION_LIMIT <= UINT64_MAX,
                  "A generation limit must be a positive representable integer");
    static constexpr std::uint64_t generation_limit = AURORA_NVME_QUEUE_GENERATION_LIMIT;
#else
    static constexpr std::uint64_t generation_limit = UINT64_MAX;
#endif

    [[nodiscard]] auto backing_valid() const -> bool {
        return epoch_ && base_ % page_bytes == 0 && backing_.size() == pool_pages * page_bytes
            && reinterpret_cast<std::uintptr_t>(backing_.data()) % page_bytes == 0
            && pool_.arena_matches(base_, pool_pages);
    }

    [[nodiscard]] auto page(std::size_t index) const -> std::optional<std::span<std::byte>> {
        if (!backing_valid() || index >= count_ || !leases_[index])
            return std::nullopt;
        const auto address = pool_.address(*leases_[index]);
        if (!address || *address % page_bytes || *address < base_
            || *address - base_ > backing_.size() - page_bytes)
            return std::nullopt;
        return backing_.subspan(static_cast<std::size_t>(*address - base_), page_bytes);
    }

    [[nodiscard]] auto scrub_all() -> bool {
        // Check every lease before touching any bytes, then scrub/read back every
        // page before releasing any lease. A failed readback retains the prefix.
        for (std::size_t index = 0; index < count_; ++index)
            if (!page(index))
                return false;
        for (std::size_t index = 0; index < count_; ++index) {
            const auto bytes = *page(index);
            volatile std::byte *data = bytes.data();
            for (std::size_t at = 0; at < page_bytes; ++at)
                data[at] = std::byte{0};
#ifdef AURORA_NVME_QUEUE_TESTING
            // Hosted-only CPU readback failure, never simulated DMA completion.
            if (index == failed_scrub_)
                data[page_bytes - 1] = std::byte{1};
#endif
            for (std::size_t at = 0; at < page_bytes; ++at)
                if (data[at] != std::byte{0})
                    return false;
        }
        return true;
    }

    [[nodiscard]] auto discard_unpublished() -> bool {
        if (!scrub_all()) {
            state_ = State::retained;
            return false;
        }
        // After preflight and without callbacks/concurrency these releases
        // cannot fail under PhysicalPages' exclusive-lifetime contract.
        for (std::size_t index = 0; index < count_; ++index) {
            if (!pool_.release(*leases_[index])) {
                state_ = State::retained;
                return false;
            }
            leases_[index].reset();
        }
        count_ = 0;
        session_.reset();
        state_ = State::empty;
        return true;
    }

    [[nodiscard]] auto matches(NvmeQueueHandle handle) const -> bool {
        return state_ == State::prepared && handle.owner_ == this && handle.epoch_ == epoch_
            && handle.generation_ == generation_ && count_ == page_count;
    }

    [[nodiscard]] static auto role_index(Role role, Direction direction) -> std::optional<std::size_t> {
        switch (role) {
        case Role::admin_submission:
            if (direction == Direction::device_reads)
                return 0;
            break;
        case Role::admin_completion:
            if (direction == Direction::device_writes)
                return 1;
            break;
        case Role::io_submission:
            if (direction == Direction::device_reads)
                return 2;
            break;
        case Role::io_completion:
            if (direction == Direction::device_writes)
                return 3;
            break;
        case Role::data:
            if (direction == Direction::device_writes)
                return 4;
            break;
        }
        return std::nullopt;
    }

public:
    NvmeQueueBundle(memory::PhysicalPages &pool, std::span<std::byte> backing, std::uint64_t base)
        : pool_(pool), backing_(backing), base_(base) {
        if (next_epoch_ != UINT64_MAX)
            epoch_ = ++next_epoch_;
    }
    ~NvmeQueueBundle() = default;
    NvmeQueueBundle(const NvmeQueueBundle &) = delete;
    auto operator=(const NvmeQueueBundle &) -> NvmeQueueBundle & = delete;
    NvmeQueueBundle(NvmeQueueBundle &&) = delete;
    auto operator=(NvmeQueueBundle &&) -> NvmeQueueBundle & = delete;

    [[nodiscard]] auto prepare(const NvmeBarGrant &grant, const WindowAuthority &authority,
                               const PciBarSnapshot &current) -> std::optional<NvmeQueueHandle> {
        const auto cap = grant.capabilities();
        // The two-entry SQ/CQ shapes fit one page each. This bounded profile
        // requires 4 KiB pages; nothing here programs CC.MPS or a queue register.
        if (state_ != State::empty || !backing_valid() || generation_ == generation_limit
            || current.segment() != 0 || current.bus() != 0 || current.device() != 2 || current.function() != 0
            || !grant.read_address(authority, current, 0, 8) || ((cap >> 48) & 15) != 0
            || (cap & 0xffff) + 1 < queue_entries)
            return std::nullopt;
        ++generation_;
        state_ = State::preparing;
        session_.emplace(grant);
        while (count_ < page_count) {
            auto lease = pool_.acquire();
            if (!lease) {
                static_cast<void>(discard_unpublished());
                return std::nullopt;
            }
            leases_[count_++].emplace(std::move(*lease));
        }
        if (!scrub_all()) {
            state_ = State::retained;
            return std::nullopt;
        }
        state_ = State::prepared;
        return NvmeQueueHandle{*this, epoch_, generation_};
    }

    // A CPU preparation check only. The BAR ticket and complete copied endpoint
    // snapshot are rechecked on every query. No pointer/address leaves the bundle.
    [[nodiscard]] auto ready(NvmeQueueHandle handle, const WindowAuthority &authority,
                             const PciBarSnapshot &current, Role role, Direction direction) const -> bool {
        const auto index = role_index(role, direction);
        return matches(handle) && session_ && session_->read_address(authority, current, 0, 8)
            && index && page(*index).has_value();
    }

    [[nodiscard]] auto cancel(NvmeQueueHandle handle) -> bool {
        return matches(handle) && discard_unpublished();
    }

    [[nodiscard]] auto held_pages() const -> std::size_t { return count_; }
    [[nodiscard]] auto retained() const -> bool { return state_ == State::retained; }

#ifdef AURORA_NVME_QUEUE_TESTING
    auto fail_scrub_for_test(std::size_t index) -> void { failed_scrub_ = index; }
#endif
};

static_assert(NvmeQueueBundle::queue_entries * 64 <= NvmeQueueBundle::page_bytes);
static_assert(NvmeQueueBundle::queue_entries * 16 <= NvmeQueueBundle::page_bytes);
static_assert(sizeof(NvmeQueueBundle) < 512);
}
