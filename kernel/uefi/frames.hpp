#pragma once
// Physical frame allocator over all usable EfiConventionalMemory of the final
// memory map (kernel/uefi/process.md#frames). Aurora owns the allocation
// records, intrusive free list, counts, poisoning and audit. Native code keeps
// immutable admitted address ranges and an opaque root/backing authority gate.
// It never maps or touches an allocated frame.
#include "process-policy.hpp"
#include "../owned-words.hpp"
#include <array>

namespace aurora::uefi::frames {
using U64 = std::uint64_t;
inline constexpr U64 page = 4096;
// Owners 1..15 are kernel uses; 1 kernel tables, 2 frame metadata.
inline constexpr U64 owner_tables = 1, owner_metadata = 2, first_owner = 16;
enum class State : U64 {
    free = 1,
    allocated = 2,
    kernel = 3,
    retired = 4
};
enum class Operation : U64 {
    initialize_free = 1,
    initialize_kernel = 2,
    allocate = 3,
    release = 4
};
// The policy's rejection reasons (kernel.frames FrameRejection), plus the
// supervisor's own: a malformed decision or an index outside the table.
enum class Rejection : U64 {
    none,
    operation,
    record,
    owner,
    link,
    not_free,
    not_allocated,
    kernel,
    retired,
    wrong_owner,
    stale,
    malformed = 64,
    index,
    exhausted
};
[[nodiscard]] constexpr auto state(U64 record) -> U64 {
    return record & 15;
}
[[nodiscard]] constexpr auto generation(U64 record) -> U64 {
    return (record >> 4) & 0x0fffffff;
}
[[nodiscard]] constexpr auto word(U64 record) -> U64 {
    return record >> 32;
}
// A copied frame identity; release also names the owner that holds it.
class Frame final {
public:
    U64 index = 0, generation = 0;
};
class Decision final {
public:
    U64 record = 0;
    Rejection rejection = Rejection::none;
};
// One policy transition, checked against the closed record encoding before use.
[[nodiscard]] inline auto transition(Operation operation, U64 record, U64 owner, U64 generation_value, U64 link)
    -> Decision {
    const auto next =
        process::bridge::frame_transition(static_cast<U64>(operation), record, owner, generation_value, link);
    if (state(next) == 0) {
        const auto reason = next >> 4;
        if (reason == 0 || reason > static_cast<U64>(Rejection::stale))
            return {0, Rejection::malformed};
        return {0, static_cast<Rejection>(reason)};
    }
    const auto expected = operation == Operation::initialize_free           ? State::free
                          : operation == Operation::initialize_kernel       ? State::kernel
                          : operation == Operation::allocate                ? State::allocated
                          : state(next) == static_cast<U64>(State::retired) ? State::retired
                                                                            : State::free;
    if (state(next) != static_cast<U64>(expected) || (expected == State::retired && word(next) != 0) ||
        (expected == State::kernel && (word(next) == 0 || word(next) >= first_owner)) ||
        (expected == State::allocated && word(next) < first_owner))
        return {0, Rejection::malformed};
    return {next, Rejection::none};
}

// Sorted, disjoint usable ranges in frame-index order.
class Ranges final {
public:
    static constexpr std::size_t capacity = 512;
    class Range final {
    public:
        U64 first_page = 0, pages = 0, first_index = 0;
    };

private:
    std::array<Range, capacity> ranges_{};
    std::size_t count_ = 0;
    U64 frames_ = 0;

public:
    // Insert in address order; overlapping or excess ranges reject.
    [[nodiscard]] auto add(U64 first_page, U64 pages) -> bool {
        if (count_ == capacity || pages == 0)
            return false;
        std::size_t at = count_;
        while (at > 0 && ranges_[at - 1].first_page > first_page)
            --at;
        if ((at > 0 && ranges_[at - 1].first_page + ranges_[at - 1].pages > first_page) ||
            (at < count_ && first_page + pages > ranges_[at].first_page))
            return false;
        for (auto i = count_; i > at; --i)
            ranges_[i] = ranges_[i - 1];
        ranges_[at] = {first_page, pages, 0};
        ++count_;
        frames_ = 0;
        for (std::size_t i = 0; i < count_; ++i) {
            ranges_[i].first_index = frames_;
            frames_ += ranges_[i].pages;
        }
        return true;
    }
    [[nodiscard]] auto count() const -> std::size_t {
        return count_;
    }
    [[nodiscard]] auto frames() const -> U64 {
        return frames_;
    }
    [[nodiscard]] auto range(std::size_t index) const -> const Range & {
        return ranges_[index];
    }
    [[nodiscard]] auto address(U64 index) const -> std::optional<U64> {
        std::size_t low = 0, high = count_;
        while (low < high) {
            const auto middle = low + (high - low) / 2;
            const auto &candidate = ranges_[middle];
            if (index < candidate.first_index)
                high = middle;
            else if (index >= candidate.first_index + candidate.pages)
                low = middle + 1;
            else
                return (candidate.first_page + index - candidate.first_index) * page;
        }
        return std::nullopt;
    }
    [[nodiscard]] auto index(U64 physical) const -> std::optional<U64> {
        if (physical % page)
            return std::nullopt;
        const auto target = physical / page;
        std::size_t low = 0, high = count_;
        while (low < high) {
            const auto middle = low + (high - low) / 2;
            const auto &candidate = ranges_[middle];
            if (target < candidate.first_page)
                high = middle;
            else if (target >= candidate.first_page + candidate.pages)
                low = middle + 1;
            else
                return candidate.first_index + target - candidate.first_page;
        }
        return std::nullopt;
    }
};

// The usable frames of an admitted final map, minus the arena and boot volume.
class Inventory final {
public:
    process::MapVerdict map = process::MapVerdict::valid;
    std::optional<process::GrantVerdict> grant;
    bool ranges = false;
};
[[nodiscard]] inline auto
inventory(std::span<const std::byte> map, U64 stride, U64 version, U64 arena, U64 volume, U64 bytes, Ranges &ranges)
    -> Inventory {
    Inventory result;
    const auto admitted = process::map_admit(map, stride, version);
    if (!admitted || *admitted != process::MapVerdict::valid) {
        result.map = admitted.value_or(process::MapVerdict::length);
        return result;
    }
    if (bytes) {
        result.grant = process::volume_grant(map, stride, arena, volume, bytes);
        if (result.grant != process::GrantVerdict::granted)
            return result;
    }
    for (U64 index = 0; index < map.size() / stride; ++index) {
        const auto range = process::frame_range(map, stride, index, arena, volume, bytes);
        if (!range || (range->status == 1 && !ranges.add(range->first_page, range->pages)))
            return result;
    }
    result.ranges = ranges.frames() != 0;
    return result;
}

// Only opaque source storage and its native backing grant remain here. Aurora
// owns all record/free-list/count/poison state and complete allocation audits.
class FrameAllocation final {
public:
    U64 index = 0, generation = 0, valid = 0;
};
class FrameAudit final {
public:
    U64 consistent = 0, free = 0, allocated = 0, kernel = 0, retired = 0;
};
extern "C" {
void __au_runtime_frame_construct(void *, words::Descriptor *);
bool __au_runtime_frame_initialize(void *, U64, U64);
void __au_runtime_frame_allocate(void *, U64, FrameAllocation *);
U64 __au_runtime_frame_release(void *, U64, U64, U64);
U64 __au_runtime_frame_record(const void *, U64);
U64 __au_runtime_frame_frames(const void *);
U64 __au_runtime_frame_reserved(const void *);
U64 __au_runtime_frame_free(const void *);
U64 __au_runtime_frame_allocated(const void *);
U64 __au_runtime_frame_owner_allocated(const void *, U64);
bool __au_runtime_frame_poisoned(const void *);
void __au_runtime_frame_audit(const void *, FrameAudit *);
bool __au_runtime_frame_finish(void *);
}
class Table final {
    alignas(16) std::array<std::byte, 96> storage_{};
    mutable words::Binding binding_;
    const Ranges *ranges_ = nullptr;
    static void require(bool condition) {
        if (!condition)
            words::fail();
    }

public:
    using Audit = FrameAudit;
    Table() = default;
    Table(const Table &) = delete;
    auto operator=(const Table &) -> Table & = delete;
    Table(Table &&) = delete;
    auto operator=(Table &&) -> Table & = delete;
    [[nodiscard]] auto bind(std::span<U64> records, const Ranges &ranges, U64 tables, U64 metadata) -> bool {
        if (binding_.created() || records.size() != ranges.frames() || records.empty() ||
            records.size() > 0xffffffffULL || tables >= records.size() || metadata >= records.size() - tables)
            return false;
        auto input = binding_.bind(records, storage_.data(), storage_.size());
        __au_runtime_frame_construct(storage_.data(), &input);
        require(!input.binding && !input.epoch);
        words::Binding::Scope scope(binding_, words::Access::write);
        require(__au_runtime_frame_initialize(storage_.data(), tables, metadata));
        ranges_ = &ranges;
        return true;
    }
    [[nodiscard]] auto allocate(U64 owner) -> std::optional<Frame> {
        words::Binding::Scope scope(binding_, words::Access::write);
        FrameAllocation result;
        __au_runtime_frame_allocate(storage_.data(), owner, &result);
        require(result.valid <= 1);
        if (!result.valid)
            return std::nullopt;
        require(ranges_ && result.index < ranges_->frames() && result.generation <= 0x0fffffffULL);
        return Frame{result.index, result.generation};
    }
    [[nodiscard]] auto release(Frame frame, U64 owner) -> Rejection {
        words::Binding::Scope scope(binding_, words::Access::write);
        const auto result = __au_runtime_frame_release(storage_.data(), frame.index, frame.generation, owner);
        require(result <= static_cast<U64>(Rejection::stale) ||
                (result >= static_cast<U64>(Rejection::malformed) && result <= static_cast<U64>(Rejection::exhausted)));
        return static_cast<Rejection>(result);
    }
    [[nodiscard]] auto record(U64 index) const -> U64 {
        words::Binding::Scope scope(binding_, words::Access::read);
        return __au_runtime_frame_record(storage_.data(), index);
    }
    [[nodiscard]] auto address(U64 index) const -> std::optional<U64> {
        return ranges_ ? ranges_->address(index) : std::nullopt;
    }
    [[nodiscard]] auto frames() const -> U64 {
        words::Binding::Scope scope(binding_, words::Access::read);
        return __au_runtime_frame_frames(storage_.data());
    }
    [[nodiscard]] auto reserved() const -> U64 {
        words::Binding::Scope scope(binding_, words::Access::read);
        return __au_runtime_frame_reserved(storage_.data());
    }
    [[nodiscard]] auto free() const -> U64 {
        words::Binding::Scope scope(binding_, words::Access::read);
        return __au_runtime_frame_free(storage_.data());
    }
    [[nodiscard]] auto allocated() const -> U64 {
        words::Binding::Scope scope(binding_, words::Access::read);
        return __au_runtime_frame_allocated(storage_.data());
    }
    [[nodiscard]] auto allocated(U64 owner) const -> U64 {
        words::Binding::Scope scope(binding_, words::Access::read);
        return __au_runtime_frame_owner_allocated(storage_.data(), owner);
    }
    [[nodiscard]] auto poisoned() const -> bool {
        words::Binding::Scope scope(binding_, words::Access::read);
        return __au_runtime_frame_poisoned(storage_.data());
    }
    [[nodiscard]] auto audit() const -> Audit {
        words::Binding::Scope scope(binding_, words::Access::read);
        Audit result;
        __au_runtime_frame_audit(storage_.data(), &result);
        require(result.consistent <= 1);
        return result;
    }
    auto suspend() -> void {
        binding_.suspend();
    }
    auto resume(const U64 *backing, U64 count) -> void {
        binding_.resume(backing, count);
    }
    [[nodiscard]] auto finish() -> bool {
        words::Binding::Scope scope(binding_, words::Access::consume);
        require(__au_runtime_frame_finish(storage_.data()) && !binding_.live());
        return true;
    }
};
} // namespace aurora::uefi::frames
