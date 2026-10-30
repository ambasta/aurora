#pragma once
// A process's address space (kernel/uefi/process.md#address-space): a 4-level
// root and tables taken from the frame allocator, the regions the Aurora
// layout policy decided, the mappings the Aurora memory policy decided
// (process.md#memory), and the checks that the hardware tables are exactly
// those records. Every table and page frame is allocated to the process's
// owner and carries a mapping word (KernelSpace::mappings) naming the one
// place it is mapped, so the complete walk detects a missing, extra, aliased,
// misplaced or wrongly flagged entry and a leaked frame. Tables are written
// through the kernel's transient frame window; a page is filled through that
// window and the window is closed before the page's own leaf exists, so no
// frame is ever reachable writable and executable at once. The process root
// shares the kernel's entries: the upper half's root entries and the
// supervisor-only page tables of the arena's 2 MiB slots, the only lower-half
// kernel mappings (the kernel runs traps and calls under the process root).
#include "kernel-space.hpp"

namespace aurora::uefi {
class ProcessSpace final {
public:
    using U64 = std::uint64_t;
    using Region = process::ProcessRegion;
    using Record = process::MemoryRecord;
    static constexpr std::size_t max_regions = 10;
    static constexpr U64 table_flags = 7, address_mask = KernelSpace::address_mask, hardware_bits = 0x60;
    static constexpr U64 user_limit = U64{1} << 47, slot_bytes = U64{1} << 21;
    // Mapping words: a user page is its address | 1; a table of level 1 (PT)
    // to 4 (root) is the first address it translates | (8 + level), with a
    // table below the root's count of present entries in bits 4..13 (empty
    // tables are released, process.md#memory).
    static constexpr U64 count_mask = U64{1023} << 4;
    [[nodiscard]] static constexpr auto page_word(U64 address) -> U64 {
        return address | 1;
    }
    [[nodiscard]] static constexpr auto table_word(U64 prefix, unsigned level) -> U64 {
        return prefix | (8 + level);
    }
    // The kernel's shared entries, captured from the boot-verified root before
    // any process exists: root entries 256..511 and the page-directory
    // entries of the arena's slots that hold mapped arena pages. Every slot
    // the arena spans, [reserved_first, reserved_end), is closed to regions.
    class Shared final {
    public:
        std::array<U64, 256> upper{};
        std::array<U64, 2> slot{}, entry{};
        unsigned slots = 0;
        U64 reserved_first = 0, reserved_end = 0;
        [[nodiscard]] auto find(U64 address) const -> std::optional<U64> {
            for (unsigned index = 0; index < slots; ++index)
                if (slot[index] == address)
                    return entry[index];
            return std::nullopt;
        }
    };
    // A memory call's outcome: resume the process with RAX = value, end it
    // for a refused call, or a broken kernel invariant (the machine stops).
    enum class Outcome {
        resume,
        refuse,
        broken
    };
    class Result final {
    public:
        Outcome outcome = Outcome::broken;
        U64 value = 0;
    };

private:
    KernelSpace &space_;
    frames::Table &frames_;
    const frames::Ranges &ranges_;
    std::span<U64> mappings_;
    const Shared &shared_;
    std::span<Record> records_;
    U64 owner_ = 0, root_ = 0, tables_ = 0, leaves_ = 0, heap_ = 0, heap_tables_ = 0;
    process::MemoryState state_{};
    std::array<Region, max_regions> regions_{};
    std::size_t count_ = 0;
    bool failed_ = false;

    [[nodiscard]] static constexpr auto shift(unsigned level) -> unsigned {
        return 12 + 9 * (level - 1);
    }
    [[nodiscard]] static constexpr auto heap(U64 address) -> bool {
        return address >= process::memory_base && address < process::memory_limit;
    }
    // A cleared leaf or a released table under the live root no longer
    // translates: INVLPG drops the page's TLB entry and the paging-structure
    // cache entries of its path (every one on Intel, the address's on AMD),
    // before the process runs again. Harmless under another root.
    static auto invalidate(U64 address) -> void {
        asm volatile("invlpg (%0)" : : "r"(address) : "memory");
    }
    // One table entry through the transient window.
    [[nodiscard]] auto read(U64 table, U64 slot) -> std::optional<U64> {
        auto *words = space_.open(table);
        if (!words)
            return std::nullopt;
        const auto value = reinterpret_cast<volatile U64 *>(words)[slot];
        space_.close();
        return value;
    }
    [[nodiscard]] auto write(U64 table, U64 slot, U64 value) -> bool {
        auto *words = space_.open(table);
        if (!words)
            return false;
        reinterpret_cast<volatile U64 *>(words)[slot] = value;
        space_.close();
        return true;
    }
    // The present-entry count of a table below the root, moved by one.
    [[nodiscard]] auto counted(U64 table, bool up) -> std::optional<U64> {
        const auto index = ranges_.index(table);
        if (!index)
            return std::nullopt;
        auto &word = mappings_[*index];
        const auto count = (word & count_mask) >> 4;
        if ((word & 15) < 9 || (word & 15) > 11 || (up ? count == 512 : count == 0))
            return std::nullopt;
        const auto next = up ? count + 1 : count - 1;
        word = (word & ~count_mask) | (next << 4);
        return next;
    }
    // An entry written into an empty slot of a table at level; a present
    // slot refuses (no entry ever changes from one present value to another).
    [[nodiscard]] auto link(U64 table, unsigned level, U64 slot, U64 value) -> bool {
        auto *words = space_.open(table);
        if (!words)
            return false;
        auto &entry = reinterpret_cast<volatile U64 *>(words)[slot];
        const auto empty = entry == 0 && (level == 4 || counted(table, true));
        if (empty)
            entry = value;
        space_.close();
        return empty;
    }
    // A frame of the owner, zeroed (or filled by fill) through the window
    // before anything maps it, with its mapping word. Zeroing every frame
    // before it is mapped is the scrub: no frame reaches a process (or a table)
    // with bytes an earlier holder left.
    template <class Fill> [[nodiscard]] auto frame(U64 word, Fill fill) -> std::optional<U64> {
        const auto taken = frames_.allocate(owner_);
        if (!taken)
            return std::nullopt;
        const auto physical = frames_.address(taken->index);
        auto *words = physical ? space_.open(*physical) : nullptr;
        if (!words || mappings_[taken->index]) {
            if (words)
                space_.close();
            static_cast<void>(frames_.release(*taken, owner_));
            return std::nullopt;
        }
        for (U64 index = 0; index < frames::page / 8; ++index)
            reinterpret_cast<volatile U64 *>(words)[index] = 0;
        fill(reinterpret_cast<volatile std::uint8_t *>(words));
        space_.close();
        mappings_[taken->index] = word;
        return *physical;
    }
    // A frame of this process holding exactly word (a table's count aside).
    [[nodiscard]] auto owned(U64 physical, U64 word) const -> std::optional<U64> {
        const auto index = ranges_.index(physical);
        if (!index)
            return std::nullopt;
        const auto record = frames_.record(*index);
        const auto mask = (word & 8) ? ~count_mask : ~U64{0};
        if (frames::state(record) != static_cast<U64>(frames::State::allocated) || frames::word(record) != owner_ ||
            (mappings_[*index] & mask) != word)
            return std::nullopt;
        return index;
    }
    // Releases a frame of the process, holding word.
    [[nodiscard]] auto drop(U64 physical, U64 word) -> bool {
        const auto index = owned(physical, word);
        if (!index)
            return false;
        mappings_[*index] = 0;
        return frames_.release({*index, frames::generation(frames_.record(*index))}, owner_) == frames::Rejection::none;
    }
    // The table at level under table's slot, made if absent; an existing link
    // must be this process's own table.
    [[nodiscard]] auto child(U64 table, U64 slot, U64 prefix, unsigned level) -> std::optional<U64> {
        const auto link_value = read(table, slot);
        if (!link_value)
            return std::nullopt;
        if (*link_value) {
            const auto physical = *link_value & address_mask;
            if ((*link_value & ~address_mask & ~hardware_bits) != table_flags ||
                !owned(physical, table_word(prefix, level)))
                return std::nullopt;
            return physical;
        }
        const auto made = frame(table_word(prefix, level), [](volatile std::uint8_t *) {
        });
        if (!made || !link(table, level + 1, slot, *made | table_flags))
            return std::nullopt;
        ++tables_;
        heap_tables_ += heap(prefix);
        return made;
    }
    // The page table translating address, made along the path if absent.
    [[nodiscard]] auto table(U64 address, unsigned level) -> std::optional<U64> {
        auto current = std::optional<U64>{root_};
        for (unsigned at = 4; at > level && current; --at) {
            const auto prefix = address & ~((U64{1} << shift(at - 1) << 9) - 1);
            current = child(*current, (address >> shift(at)) & 511, prefix, at - 1);
        }
        return current;
    }
    [[nodiscard]] auto region_of(U64 address) const -> const Region * {
        for (std::size_t index = 0; index < count_; ++index) {
            const auto &region = regions_[index];
            if (address >= region.first && address - region.first < region.pages * frames::page)
                return &region;
        }
        return nullptr;
    }
    // The mapping holding address (records are sorted by first).
    [[nodiscard]] auto mapping_of(U64 address) const -> const Record * {
        std::size_t low = 0, high = state_.count;
        while (low < high) {
            const auto middle = low + (high - low) / 2;
            if (records_[middle].first <= address)
                low = middle + 1;
            else
                high = middle;
        }
        if (low == 0)
            return nullptr;
        const auto &record = records_[low - 1];
        return address - record.first < record.pages * frames::page ? &record : nullptr;
    }
    class Walk final {
    public:
        U64 tables = 0, leaves = 0, heap = 0, heap_tables = 0, shared = 0;
    };
    // Every entry of one table: the shared kernel entries, links to this
    // process's own tables, leaves of its regions and mappings with their exact
    // flags, and below the root the count its mapping word keeps.
    [[nodiscard]] auto scan(U64 table, U64 prefix, unsigned level, Walk &walk) -> bool {
        const auto self = ranges_.index(table);
        auto *raw = self ? space_.open(table) : nullptr;
        if (!raw)
            return false;
        const auto *words = reinterpret_cast<volatile U64 *>(raw);
        bool good = true;
        U64 present = 0;
        for (U64 slot = 0; slot < 512 && good; ++slot) {
            const auto value = words[slot] ? words[slot] & ~hardware_bits : 0;
            const auto address = prefix | (slot << shift(level));
            if (level == 4 && slot >= 256) {
                const auto kernel = shared_.upper[slot - 256];
                good = value == (kernel ? kernel & ~hardware_bits : 0);
                continue;
            }
            if (!value)
                continue;
            ++present;
            if (level == 2 && shared_.find(address)) {
                good = value == (*shared_.find(address) & ~hardware_bits);
                ++walk.shared;
                continue;
            }
            const auto physical = value & address_mask;
            if (level > 1) {
                good = (value & ~address_mask) == table_flags && owned(physical, table_word(address, level - 1));
                ++walk.tables;
                walk.heap_tables += heap(address);
                continue;
            }
            if (heap(address)) {
                good = mapping_of(address) && (value & ~address_mask) == process::leaf_write &&
                       owned(physical, page_word(address));
                ++walk.heap;
                continue;
            }
            const auto *region = region_of(address);
            good = region && (value & ~address_mask) == region->flags && owned(physical, page_word(address));
            ++walk.leaves;
        }
        space_.close();
        return good && (level == 4 || (mappings_[*self] & count_mask) >> 4 == present);
    }
    // The next present link of a table (not a shared slot) at or after slot
    // next and before end, with one window opening; 512 when there is none.
    [[nodiscard]] auto next_link(U64 table, unsigned level, U64 prefix, U64 next, U64 end, U64 &value)
        -> std::optional<U64> {
        auto *raw = space_.open(table);
        if (!raw)
            return std::nullopt;
        const auto *words = reinterpret_cast<volatile U64 *>(raw);
        U64 found = 512;
        for (U64 slot = next; slot < end && found == 512; ++slot)
            if (words[slot] && !(level == 2 && shared_.find(prefix | (slot << shift(level))))) {
                found = slot;
                value = words[slot];
            }
        space_.close();
        return found;
    }
    // The first present unshared entry of table in slots [next, end), cleared
    // when it is a leaf, with one window opening; 512 when there is none.
    [[nodiscard]] auto take(U64 table, unsigned level, U64 prefix, U64 next, U64 end, U64 &value)
        -> std::optional<U64> {
        auto *raw = space_.open(table);
        if (!raw)
            return std::nullopt;
        auto *words = reinterpret_cast<volatile U64 *>(raw);
        U64 found = 512;
        for (U64 slot = next; slot < end && found == 512; ++slot)
            if (words[slot] && !(level == 2 && shared_.find(prefix | (slot << shift(level))))) {
                found = slot;
                value = words[slot];
                if (level == 1)
                    words[slot] = 0;
            }
        space_.close();
        return found;
    }
    // Every present leaf of [first, end) is cleared and handed to
    // leaf(address, value); a table left empty is unlinked and released. With
    // all, every table met is released (the process's end: the root's lower
    // half, all of it).
    template <class Leaf> [[nodiscard]] auto sweep(U64 first, U64 end, bool all, Leaf leaf) -> bool {
        class Level final {
        public:
            U64 table = 0, prefix = 0, next = 0, end = 0, parent = 0;
            unsigned level = 0;
        };
        if (first >= end || end > user_limit || first % frames::page || end % frames::page)
            return false;
        // The slots of a table at level with first address prefix that [first, end) touches.
        const auto bounds = [&](U64 prefix, unsigned level, U64 &from, U64 &to) {
            const auto low = first > prefix ? first : prefix;
            from = (low - prefix) >> shift(level);
            to = ((end - 1 - prefix) >> shift(level)) + 1;
            if (to > (level == 4 ? 256 : 512))
                to = level == 4 ? 256 : 512;
        };
        std::array<Level, 4> path{};
        path[0] = {root_, 0, 0, 0, 0, 4};
        bounds(0, 4, path[0].next, path[0].end);
        std::size_t depth = 0;
        for (;;) {
            auto &at = path[depth];
            U64 value = 0;
            const auto slot = take(at.table, at.level, at.prefix, at.next, at.end, value);
            if (!slot)
                return false;
            if (*slot < 512) {
                at.next = *slot + 1;
                const auto address = at.prefix | (*slot << shift(at.level));
                if (at.level == 1) {
                    invalidate(address);
                    if (!counted(at.table, false) || !leaf(address, value & ~hardware_bits))
                        return false;
                    continue;
                }
                if ((value & ~address_mask & ~hardware_bits) != table_flags || depth + 1 == path.size())
                    return false;
                auto &below = path[++depth];
                below = {value & address_mask, address, 0, 0, *slot, at.level - 1};
                bounds(address, below.level, below.next, below.end);
                continue;
            }
            if (depth == 0)
                return true;
            const auto done = path[depth--];
            const auto index = ranges_.index(done.table);
            if (!index)
                return false;
            if (!all && mappings_[*index] & count_mask)
                continue;
            if ((!all && (!write(path[depth].table, done.parent, 0) ||
                          (path[depth].level < 4 && !counted(path[depth].table, false)))) ||
                !drop(done.table, table_word(done.prefix, done.level)))
                return false;
            invalidate(done.prefix);
            --tables_;
            heap_tables_ -= heap(done.prefix);
        }
    }
    // Releases a cleared leaf's page.
    [[nodiscard]] auto release_leaf(U64 address, U64 value) -> bool {
        if (!drop(value & address_mask, page_word(address)))
            return false;
        if (heap(address))
            --heap_;
        else
            --leaves_;
        return true;
    }
    // The frames the process holds never exceed its charge.
    [[nodiscard]] auto accounted() const -> bool {
        return !failed_ && tables_ + leaves_ + heap_ <= state_.charged && state_.charged <= state_.quota;
    }
    auto remove(std::size_t index) -> void {
        for (auto at = index; at + 1 < state_.count; ++at)
            records_[at] = records_[at + 1];
        --state_.count;
    }
    [[nodiscard]] static auto resume(U64 value) -> Result {
        return {Outcome::resume, value};
    }
    // The negative HostStatus exhausted (-6) of a refused allocation.
    static constexpr U64 exhausted = ~U64{0} - 5;

public:
    ProcessSpace(KernelSpace &space,
                 frames::Table &table,
                 const frames::Ranges &ranges,
                 std::span<U64> mappings,
                 const Shared &shared,
                 std::span<Record> records,
                 U64 owner)
        : space_(space), frames_(table), ranges_(ranges), mappings_(mappings), shared_(shared), records_(records),
          owner_(owner) {
    }
    ProcessSpace(const ProcessSpace &) = delete;
    auto operator=(const ProcessSpace &) -> ProcessSpace & = delete;
    [[nodiscard]] auto owner() const -> U64 {
        return owner_;
    }
    [[nodiscard]] auto held() const -> U64 {
        return tables_ + leaves_ + heap_;
    }
    [[nodiscard]] auto root() const -> U64 {
        return root_;
    }
    [[nodiscard]] auto tables() const -> U64 {
        return tables_;
    }
    [[nodiscard]] auto leaves() const -> U64 {
        return leaves_;
    }
    // The memory service's frames: committed pages and their page tables.
    [[nodiscard]] auto memory() const -> U64 {
        return heap_ + heap_tables_;
    }
    [[nodiscard]] auto regions() const -> std::span<const Region> {
        return {regions_.data(), count_};
    }
    [[nodiscard]] auto records() const -> std::span<const Record> {
        return {records_.data(), static_cast<std::size_t>(state_.count)};
    }
    [[nodiscard]] auto state() const -> const process::MemoryState & {
        return state_;
    }
    // The root with the shared kernel entries.
    [[nodiscard]] auto begin() -> bool {
        if (root_ || failed_ || owner_ < frames::first_owner || shared_.slots == 0 ||
            records_.size() != process::memory_records)
            return false;
        const auto made = frame(table_word(0, 4), [&](volatile std::uint8_t *bytes) {
            auto *words = reinterpret_cast<volatile U64 *>(bytes);
            for (U64 slot = 256; slot < 512; ++slot)
                words[slot] = shared_.upper[slot - 256];
        });
        if (!made)
            return false;
        root_ = *made;
        tables_ = 1;
        for (unsigned index = 0; index < shared_.slots; ++index) {
            const auto directory = table(shared_.slot[index], 2);
            if (!directory || !link(*directory, 2, (shared_.slot[index] >> 21) & 511, shared_.entry[index])) {
                failed_ = true;
                return false;
            }
        }
        return true;
    }
    // The memory service starts with the load's charge and the quota the
    // Aurora budget decided.
    [[nodiscard]] auto budget(const process::MemoryBudget &budget) -> bool {
        if (!root_ || state_.quota || budget.charged > budget.quota)
            return false;
        state_ = {process::memory_base, budget.charged, budget.quota, 0};
        return accounted();
    }
    // Map a region, each page filled from source[offset..) over [vaddr, vaddr
    // + bytes) and zero elsewhere. Regions are disjoint from each other, from
    // the shared slots and from the memory area.
    [[nodiscard]] auto map(const Region &region, std::span<const std::byte> source) -> bool {
        if (!root_ || count_ == max_regions || region.offset > source.size() ||
            region.bytes > source.size() - region.offset)
            return false;
        const auto end = region.first + region.pages * frames::page;
        for (std::size_t index = 0; index < count_; ++index)
            if (region.first < regions_[index].first + regions_[index].pages * frames::page &&
                regions_[index].first < end)
                return false;
        if ((region.first < shared_.reserved_end && shared_.reserved_first < end) ||
            (region.first < process::memory_limit && process::memory_base < end))
            return false;
        regions_[count_++] = region;
        for (U64 page = region.first; page < end; page += frames::page) {
            const auto made = frame(page_word(page), [&](volatile std::uint8_t *bytes) {
                // The part of [vaddr, vaddr + bytes) on this page.
                const auto copy_begin = region.vaddr > page ? region.vaddr : page;
                const auto copy_end = region.vaddr + region.bytes < page + frames::page ? region.vaddr + region.bytes
                                                                                        : page + frames::page;
                for (auto at = copy_begin; at < copy_end; ++at)
                    bytes[at - page] = std::to_integer<std::uint8_t>(source[region.offset + (at - region.vaddr)]);
            });
            const auto leaf = table(page, 1);
            if (!made || !leaf || !link(*leaf, 1, (page >> 12) & 511, *made | region.flags))
                return false;
            ++leaves_;
        }
        return true;
    }
    // map(bytes): a new mapping, committed on first touch.
    [[nodiscard]] auto map_memory(U64 bytes) -> Result {
        const auto decided = process::memory_map(state_, bytes);
        if (!decided || !accounted())
            return {};
        const auto verdict = static_cast<process::MemoryVerdict>(decided->verdict);
        if (verdict == process::MemoryVerdict::length)
            return {Outcome::refuse, 0};
        if (verdict == process::MemoryVerdict::malformed)
            return {};
        if (verdict != process::MemoryVerdict::mapped)
            return resume(exhausted);
        if (state_.count == records_.size())
            return {};
        records_[state_.count] = {decided->first, decided->reserved, decided->pages};
        state_ = {decided->next, decided->charged, state_.quota, state_.count + 1};
        return accounted() ? resume(decided->first) : Result{};
    }
    // remap(base, bytes, target): in place within the reservation (a shrink
    // releases the pages past the new end), or the committed pages' entries
    // move to a fresh reservation.
    [[nodiscard]] auto remap_memory(U64 base, U64 bytes, U64 target) -> Result {
        const auto found = process::memory_find(records(), base);
        if (found.malformed)
            return {};
        const auto index = found.index;
        if (!index)
            return {Outcome::refuse, 0};
        const auto record = records_[*index];
        const auto decided = process::memory_remap(state_, record, bytes, target);
        if (!decided || !accounted())
            return {};
        const auto verdict = static_cast<process::MemoryVerdict>(decided->verdict);
        if (verdict == process::MemoryVerdict::length)
            return {Outcome::refuse, 0};
        if (verdict == process::MemoryVerdict::malformed)
            return {};
        if (verdict != process::MemoryVerdict::resized && verdict != process::MemoryVerdict::moved)
            return resume(exhausted);
        const auto old_end = record.first + record.pages * frames::page;
        if (verdict == process::MemoryVerdict::resized) {
            const auto end = record.first + decided->pages * frames::page;
            if (end < old_end && !sweep(
                                     end,
                                     old_end,
                                     false,
                                     [&](U64 address, U64 value) {
                                         return release_leaf(address, value);
                                     }))
                return {};
            records_[*index].pages = decided->pages;
            state_.charged = decided->charged;
            return accounted() ? resume(record.first) : Result{};
        }
        // The Aurora decision admitted the new range's tables beside the old
        // ones while the entries move.
        const auto moved = sweep(record.first, old_end, false, [&](U64 address, U64 value) {
            const auto target_address = decided->first + (address - record.first);
            const auto index = owned(value & address_mask, page_word(address));
            if (!index || (value & ~address_mask) != process::leaf_write)
                return false;
            const auto leaf = table(target_address, 1);
            if (!leaf || !link(*leaf, 1, (target_address >> 12) & 511, value))
                return false;
            mappings_[*index] = page_word(target_address);
            return true;
        });
        if (!moved)
            return {};
        remove(*index);
        records_[state_.count] = {decided->first, decided->reserved, decided->pages};
        state_ = {decided->next, decided->charged, state_.quota, state_.count + 1};
        return accounted() ? resume(decided->first) : Result{};
    }
    // unmap(base, bytes): every committed page and emptied table released.
    [[nodiscard]] auto unmap_memory(U64 base, U64 bytes) -> Result {
        const auto found = process::memory_find(records(), base);
        if (found.malformed)
            return {};
        const auto index = found.index;
        if (!index)
            return {Outcome::refuse, 0};
        const auto record = records_[*index];
        const auto decided = process::memory_unmap(state_, record, bytes);
        if (!decided || !accounted())
            return {};
        const auto verdict = static_cast<process::MemoryVerdict>(decided->verdict);
        if (verdict == process::MemoryVerdict::length)
            return {Outcome::refuse, 0};
        if (verdict != process::MemoryVerdict::unmapped ||
            !sweep(record.first, record.first + record.pages * frames::page, false, [&](U64 address, U64 value) {
                return release_leaf(address, value);
            }))
            return {};
        remove(*index);
        state_.charged = decided->charged;
        return accounted() ? resume(0) : Result{};
    }
    // Commits the page of a fault the Aurora policy admitted, and the other
    // absent pages of its aligned 64 KiB block inside the same mapping (the
    // programs this serves write what they map, so one fault commits a block):
    // zeroed frames of the charge, so it cannot fail unless an invariant broke.
    static constexpr U64 commit_block = 16;
    [[nodiscard]] auto commit(U64 address) -> bool {
        const auto page = address & ~(frames::page - 1);
        const auto *record = heap(page) ? mapping_of(page) : nullptr;
        if (!record)
            return false;
        const auto block = page & ~(commit_block * frames::page - 1);
        const auto first = block > record->first ? block : record->first;
        const auto mapped_end = record->first + record->pages * frames::page;
        const auto end =
            block + commit_block * frames::page < mapped_end ? block + commit_block * frames::page : mapped_end;
        const auto leaf = table(page, 1);
        if (!leaf)
            return false;
        // The block lies in one page table; its absent slots, the fault's among them.
        std::array<bool, commit_block> present{};
        auto *raw = space_.open(*leaf);
        if (!raw)
            return false;
        bool absent = false;
        for (auto at = first; at < end; at += frames::page) {
            const auto value = reinterpret_cast<volatile U64 *>(raw)[(at >> 12) & 511];
            present[(at - block) / frames::page] = value != 0;
            absent |= at == page && !value;
        }
        space_.close();
        if (!absent)
            return false;
        for (auto at = first; at < end; at += frames::page) {
            if (present[(at - block) / frames::page])
                continue;
            const auto made = frame(page_word(at), [](volatile std::uint8_t *) {
            });
            if (!made || !link(*leaf, 1, (at >> 12) & 511, *made | process::leaf_write))
                return false;
            ++heap_;
        }
        return accounted();
    }
    // The table and slot of the existing entry at level translating address
    // (fixture probes edit the tables through them).
    class Slot final {
    public:
        U64 table = 0, slot = 0;
    };
    [[nodiscard]] auto entry(U64 address, unsigned level) -> std::optional<Slot> {
        U64 current = root_;
        for (unsigned at = 4; at > level; --at) {
            const auto link_value = read(current, (address >> shift(at)) & 511);
            if (!link_value || !*link_value)
                return std::nullopt;
            current = *link_value & address_mask;
        }
        return Slot{current, (address >> shift(level)) & 511};
    }
    // Whether [address, address + length) lies in one region.
    [[nodiscard]] auto contains(U64 address, U64 length) const -> bool {
        const auto *region = region_of(address);
        return region && length <= region->first + region->pages * frames::page - address;
    }
    [[nodiscard]] auto executable(U64 address, U64 length) const -> bool {
        const auto *region = region_of(address);
        return contains(address, length) && region->flags == process::leaf_execute;
    }
    // Kernel access to the process's bytes [address, address + length) under
    // its root (process.md#user-memory): they must lie in one region (to
    // write, a read-write one) or in one memory mapping's pages, whose absent
    // pages the Aurora fault policy admits and commit() commits first, with
    // frames the mapping's charge already holds. A refusal ends the process
    // as an invalid call; broken means an invariant failed.
    enum class Access {
        granted,
        refused,
        broken
    };
    [[nodiscard]] auto access(U64 address, U64 length, bool write) -> Access {
        if (const auto *region = region_of(address))
            return length <= region->first + region->pages * frames::page - address &&
                           (!write || region->flags == process::leaf_write)
                       ? Access::granted
                       : Access::refused;
        const auto *record = heap(address) ? mapping_of(address) : nullptr;
        if (!record || length > record->first + record->pages * frames::page - address)
            return Access::refused;
        for (auto page = address & ~(frames::page - 1); page < address + length; page += frames::page) {
            const auto leaf = entry(page, 1);
            const auto value = leaf ? read(leaf->table, leaf->slot) : std::optional<U64>{0};
            if (!value)
                return Access::broken;
            if (*value)
                continue;
            const auto admitted = process::memory_fault(records(), page, write ? 6 : 4);
            if (admitted.malformed || !admitted.index || !commit(page))
                return Access::broken;
        }
        return accounted() ? Access::granted : Access::broken;
    }
    [[nodiscard]] auto charged() const -> U64 {
        return state_.charged;
    }
    [[nodiscard]] auto quota() const -> U64 {
        return state_.quota;
    }
    // The complete walk: every entry of every table reachable from the root
    // checked against the records, every region page mapped exactly once, every
    // mapping record inside its reservation in address order below the bump
    // address, and every frame of this owner among the ones walked, within its charge. The supervisor also audits all live
    // owners against the complete frame inventory at lifecycle boundaries.
    [[nodiscard]] auto verify() -> bool {
        class Level final {
        public:
            U64 table = 0, prefix = 0, next = 0;
            unsigned level = 0;
        };
        if (!root_ || failed_ || !owned(root_, table_word(0, 4)) || state_.count > records_.size() ||
            state_.next < process::memory_base || state_.next > process::memory_limit)
            return false;
        for (U64 index = 0; index < state_.count; ++index) {
            const auto &record = records_[index];
            if (record.pages == 0 || record.pages > record.reserved ||
                record.reserved > process::memory_reservation_limit || (record.reserved & (record.reserved - 1)) ||
                record.first % frames::page ||
                record.first < (index ? records_[index - 1].first + records_[index - 1].reserved * frames::page
                                      : process::memory_base) ||
                record.first >= state_.next || record.reserved * frames::page > state_.next - record.first)
                return false;
        }
        std::array<Level, 4> path{};
        path[0] = {root_, 0, 0, 4};
        std::size_t depth = 0;
        Walk walk;
        walk.tables = 1;
        bool fresh = true;
        for (;;) {
            auto &at = path[depth];
            if (fresh && !scan(at.table, at.prefix, at.level, walk))
                return false;
            fresh = false;
            U64 value = 0;
            const auto slot = at.level > 1
                                  ? next_link(at.table, at.level, at.prefix, at.next, at.level == 4 ? 256 : 512, value)
                                  : std::optional<U64>{512};
            if (!slot)
                return false;
            if (*slot < 512) {
                if (depth + 1 == path.size())
                    return false;
                at.next = *slot + 1;
                path[++depth] = {value & address_mask, at.prefix | (*slot << shift(at.level)), 0, at.level - 1};
                fresh = true;
                continue;
            }
            if (depth == 0)
                break;
            --depth;
        }
        U64 pages = 0;
        for (std::size_t index = 0; index < count_; ++index)
            pages += regions_[index].pages;
        return walk.tables == tables_ && walk.heap_tables == heap_tables_ && walk.leaves == leaves_ &&
               leaves_ == pages && walk.heap == heap_ && walk.shared == shared_.slots &&
               frames_.allocated(owner_) == held() && accounted();
    }
    // Release every frame after the process ended (its root no longer live),
    // walking its tables; returns the count, or nullopt when a release is
    // refused or a frame stays held.
    [[nodiscard]] auto release() -> std::optional<U64> {
        const auto held = tables_ + leaves_ + heap_;
        if (!root_ ||
            !sweep(0,
                   user_limit,
                   true,
                   [&](U64 address, U64 value) {
                       return release_leaf(address, value);
                   }) ||
            !drop(root_, table_word(0, 4)))
            return std::nullopt;
        --tables_;
        if (tables_ || leaves_ || heap_ || heap_tables_)
            return std::nullopt;
        root_ = 0;
        count_ = 0;
        state_ = {};
        return held;
    }
};
} // namespace aurora::uefi
