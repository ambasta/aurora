#pragma once
// Physical frame allocator over all usable EfiConventionalMemory of the final
// memory map (kernel/uefi/process.md#frames). The Aurora policies admit the map,
// derive each descriptor's frames and decide every record transition; this
// trusted storage keeps the sorted range table, the record words (8 bytes per
// frame, in mapped metadata) and the intrusive free list, and applies only
// decisions whose encoding it has checked. It never maps or touches a frame.
#include "process-policy.hpp"
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

// Records for every inventoried frame; the first `reserved` indices are kernel
// frames (tables, then metadata), every other frame starts free, in index order.
class Table final {
    std::span<U64> records_{};
    const Ranges *ranges_ = nullptr;
    U64 head_ = 0, free_ = 0, allocated_ = 0, reserved_ = 0;
    bool poisoned_ = false;

    [[nodiscard]] auto apply(U64 index, const Decision &decision) -> Rejection {
        if (decision.rejection == Rejection::malformed)
            poisoned_ = true;
        if (decision.rejection != Rejection::none)
            return decision.rejection;
        records_[index] = decision.record;
        return Rejection::none;
    }

public:
    // Records must be zeroed, cover every frame and hold no table or metadata
    // frame other than those the caller reserves at the lowest indices.
    [[nodiscard]] auto bind(std::span<U64> records, const Ranges &ranges, U64 tables, U64 metadata) -> bool {
        if (ranges_ || records.size() != ranges.frames() || records.size() > 0xffffffffULL ||
            tables + metadata >= records.size())
            return false;
        for (const auto record : records)
            if (record)
                return false;
        records_ = records;
        ranges_ = &ranges;
        reserved_ = tables + metadata;
        for (U64 index = 0; index < reserved_; ++index)
            if (apply(index,
                      transition(
                          Operation::initialize_kernel, 0, index < tables ? owner_tables : owner_metadata, 0, 0)) !=
                Rejection::none)
                return false;
        for (auto index = records.size(); index > reserved_; --index) {
            if (apply(index - 1, transition(Operation::initialize_free, 0, 0, 0, head_)) != Rejection::none)
                return false;
            head_ = index;
        }
        free_ = records.size() - reserved_;
        return true;
    }
    [[nodiscard]] auto allocate(U64 owner) -> std::optional<Frame> {
        if (poisoned_ || head_ == 0)
            return std::nullopt;
        const auto index = head_ - 1;
        if (index >= records_.size())
            return std::nullopt;
        const auto old = records_[index];
        // The list head must name a free frame whose link stays in the table.
        if (state(old) != static_cast<U64>(State::free) || word(old) > records_.size()) {
            poisoned_ = true;
            return std::nullopt;
        }
        if (apply(index, transition(Operation::allocate, old, owner, 0, 0)) != Rejection::none)
            return std::nullopt;
        head_ = word(old);
        --free_;
        ++allocated_;
        return Frame{index, generation(old)};
    }
    [[nodiscard]] auto release(Frame frame, U64 owner) -> Rejection {
        if (poisoned_)
            return Rejection::malformed;
        if (frame.index >= records_.size())
            return Rejection::index;
        auto decision = transition(Operation::release, records_[frame.index], owner, frame.generation, head_);
        // The free list is this storage's: a freed record must link to the old head.
        if (decision.rejection == Rejection::none && state(decision.record) == static_cast<U64>(State::free) &&
            word(decision.record) != head_)
            decision = {0, Rejection::malformed};
        const auto applied = apply(frame.index, decision);
        if (applied != Rejection::none)
            return applied;
        --allocated_;
        if (state(decision.record) == static_cast<U64>(State::free)) {
            head_ = frame.index + 1;
            ++free_;
        }
        return Rejection::none;
    }
    [[nodiscard]] auto record(U64 index) const -> U64 {
        return index < records_.size() ? records_[index] : 0;
    }
    [[nodiscard]] auto address(U64 index) const -> std::optional<U64> {
        return ranges_ ? ranges_->address(index) : std::nullopt;
    }
    [[nodiscard]] auto frames() const -> U64 {
        return records_.size();
    }
    [[nodiscard]] auto reserved() const -> U64 {
        return reserved_;
    }
    [[nodiscard]] auto free() const -> U64 {
        return free_;
    }
    [[nodiscard]] auto allocated() const -> U64 {
        return allocated_;
    }
    [[nodiscard]] auto poisoned() const -> bool {
        return poisoned_;
    }
    // Complete consistency walk: canonical records, kernel frames exactly the
    // reserved prefix, the free list visiting each free frame once, and counts.
    class Audit final {
    public:
        bool consistent = false;
        U64 free = 0, allocated = 0, kernel = 0, retired = 0;
    };
    [[nodiscard]] auto audit() const -> Audit {
        Audit result;
        if (!ranges_ || poisoned_)
            return result;
        for (U64 index = 0; index < records_.size(); ++index) {
            const auto value = records_[index];
            const auto kind = state(value);
            if ((kind == static_cast<U64>(State::kernel)) != (index < reserved_))
                return result;
            result.free += kind == static_cast<U64>(State::free);
            result.allocated += kind == static_cast<U64>(State::allocated);
            result.kernel += kind == static_cast<U64>(State::kernel);
            result.retired += kind == static_cast<U64>(State::retired);
            const auto holder = word(value);
            if (kind == 0 || kind > 4 || (kind == static_cast<U64>(State::free) && holder > records_.size()) ||
                (kind == static_cast<U64>(State::allocated) && (holder < first_owner || holder > 0xffffffffULL)) ||
                (kind == static_cast<U64>(State::kernel) && (holder == 0 || holder >= first_owner)) ||
                (kind == static_cast<U64>(State::retired) && holder != 0))
                return result;
        }
        U64 walked = 0;
        for (auto link = head_; link; ++walked) {
            if (walked > result.free || link > records_.size() ||
                state(records_[link - 1]) != static_cast<U64>(State::free))
                return result;
            link = word(records_[link - 1]);
        }
        result.consistent = walked == result.free && result.free == free_ && result.allocated == allocated_ &&
                            result.kernel == reserved_;
        return result;
    }
};
} // namespace aurora::uefi::frames
