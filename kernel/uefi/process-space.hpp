#pragma once
// A process's address space (kernel/uefi/process.md#address-space): a 4-level
// root and tables taken from the frame allocator, the regions the Aurora
// layout policy decided, and the checks that the hardware tables are exactly
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
    static constexpr std::size_t max_regions = 10;
    static constexpr U64 table_flags = 7, address_mask = KernelSpace::address_mask, hardware_bits = 0x60;
    static constexpr U64 user_limit = U64{1} << 47, slot_bytes = U64{1} << 21;
    // Mapping words: a user page is its address | 1; a table of level 1 (PT)
    // to 4 (root) is the first address it translates | (8 + level).
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

private:
    KernelSpace &space_;
    frames::Table &frames_;
    const frames::Ranges &ranges_;
    std::span<U64> mappings_;
    const Shared &shared_;
    U64 owner_ = 0, root_ = 0, tables_ = 0, leaves_ = 0;
    std::array<Region, max_regions> regions_{};
    std::size_t count_ = 0;
    bool failed_ = false;

    [[nodiscard]] static constexpr auto shift(unsigned level) -> unsigned {
        return 12 + 9 * (level - 1);
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
    // A frame of the owner, zeroed (or filled by fill) through the window
    // before anything maps it, with its mapping word.
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
    // The table at level under table's slot, made if absent; an existing link
    // must be this process's own table.
    [[nodiscard]] auto child(U64 table, U64 slot, U64 prefix, unsigned level) -> std::optional<U64> {
        const auto link = read(table, slot);
        if (!link)
            return std::nullopt;
        if (*link) {
            const auto physical = *link & address_mask;
            const auto index = ranges_.index(physical);
            if ((*link & ~address_mask & ~hardware_bits) != table_flags || !index ||
                mappings_[*index] != table_word(prefix, level))
                return std::nullopt;
            return physical;
        }
        const auto made = frame(table_word(prefix, level), [](volatile std::uint8_t *) {
        });
        if (!made || !write(table, slot, *made | table_flags))
            return std::nullopt;
        ++tables_;
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
    // A frame of this process holding exactly word.
    [[nodiscard]] auto owned(U64 physical, U64 word) const -> bool {
        const auto index = ranges_.index(physical);
        if (!index)
            return false;
        const auto record = frames_.record(*index);
        return frames::state(record) == static_cast<U64>(frames::State::allocated) && frames::word(record) == owner_ &&
               mappings_[*index] == word;
    }
    class Walk final {
    public:
        U64 tables = 0, leaves = 0, shared = 0;
    };
    // Every entry of one table: the shared kernel entries, links to this
    // process's own tables and leaves of its regions with their exact flags.
    [[nodiscard]] auto scan(U64 table, U64 prefix, unsigned level, Walk &walk) -> bool {
        auto *raw = space_.open(table);
        if (!raw)
            return false;
        const auto *words = reinterpret_cast<volatile U64 *>(raw);
        bool good = true;
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
            if (level == 2 && shared_.find(address)) {
                good = value == (*shared_.find(address) & ~hardware_bits);
                ++walk.shared;
                continue;
            }
            const auto physical = value & address_mask;
            if (level > 1) {
                good = (value & ~address_mask) == table_flags && owned(physical, table_word(address, level - 1));
                ++walk.tables;
                continue;
            }
            const auto *region = region_of(address);
            good = region && (value & ~address_mask) == region->flags && owned(physical, page_word(address));
            ++walk.leaves;
        }
        space_.close();
        return good;
    }

public:
    ProcessSpace(KernelSpace &space,
                 frames::Table &table,
                 const frames::Ranges &ranges,
                 std::span<U64> mappings,
                 const Shared &shared,
                 U64 owner)
        : space_(space), frames_(table), ranges_(ranges), mappings_(mappings), shared_(shared), owner_(owner) {
    }
    ProcessSpace(const ProcessSpace &) = delete;
    auto operator=(const ProcessSpace &) -> ProcessSpace & = delete;
    [[nodiscard]] auto root() const -> U64 {
        return root_;
    }
    [[nodiscard]] auto tables() const -> U64 {
        return tables_;
    }
    [[nodiscard]] auto leaves() const -> U64 {
        return leaves_;
    }
    [[nodiscard]] auto regions() const -> std::span<const Region> {
        return {regions_.data(), count_};
    }
    // The root with the shared kernel entries.
    [[nodiscard]] auto begin() -> bool {
        if (root_ || failed_ || owner_ < frames::first_owner || shared_.slots == 0)
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
            if (!directory || !write(*directory, (shared_.slot[index] >> 21) & 511, shared_.entry[index])) {
                failed_ = true;
                return false;
            }
        }
        return true;
    }
    // Map a region, each page filled from source[offset..) over [vaddr, vaddr
    // + bytes) and zero elsewhere. Regions are disjoint from each other and
    // from the shared slots.
    [[nodiscard]] auto map(const Region &region, std::span<const std::byte> source) -> bool {
        if (!root_ || count_ == max_regions || region.offset > source.size() ||
            region.bytes > source.size() - region.offset)
            return false;
        const auto end = region.first + region.pages * frames::page;
        for (std::size_t index = 0; index < count_; ++index)
            if (region.first < regions_[index].first + regions_[index].pages * frames::page &&
                regions_[index].first < end)
                return false;
        if (region.first < shared_.reserved_end && shared_.reserved_first < end)
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
            if (!made || !leaf || !write(*leaf, (page >> 12) & 511, *made | region.flags))
                return false;
            ++leaves_;
        }
        return true;
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
            const auto link = read(current, (address >> shift(at)) & 511);
            if (!link || !*link)
                return std::nullopt;
            current = *link & address_mask;
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
    // The complete walk: every entry of every table reachable from the root
    // checked against the records, every region page mapped exactly once, and
    // no other frame of the owner.
    [[nodiscard]] auto verify() -> bool {
        class Level final {
        public:
            U64 table = 0, prefix = 0, next = 0;
            unsigned level = 0;
        };
        if (!root_ || failed_ || !owned(root_, table_word(0, 4)))
            return false;
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
            std::optional<U64> link;
            U64 slot = 0;
            while (at.level > 1 && !link && at.next < (at.level == 4 ? 256 : 512)) {
                slot = at.next++;
                const auto value = read(at.table, slot);
                if (!value)
                    return false;
                const auto address = at.prefix | (slot << shift(at.level));
                if (*value && !(at.level == 2 && shared_.find(address)))
                    link = *value & address_mask;
            }
            if (link) {
                if (depth + 1 == path.size())
                    return false;
                path[++depth] = {*link, at.prefix | (slot << shift(at.level)), 0, at.level - 1};
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
        U64 owned_frames = 0;
        for (U64 index = 0; index < frames_.frames(); ++index) {
            const auto record = frames_.record(index);
            owned_frames +=
                frames::state(record) == static_cast<U64>(frames::State::allocated) && frames::word(record) == owner_;
        }
        return walk.tables == tables_ && walk.leaves == leaves_ && leaves_ == pages && walk.shared == shared_.slots &&
               owned_frames == tables_ + leaves_;
    }
    // Release every frame of the owner after the process ended (its root no
    // longer live); returns the count, or nullopt when a release is refused.
    [[nodiscard]] auto release() -> std::optional<U64> {
        U64 released = 0;
        for (U64 index = 0; index < frames_.frames(); ++index) {
            const auto record = frames_.record(index);
            if (frames::state(record) != static_cast<U64>(frames::State::allocated) || frames::word(record) != owner_)
                continue;
            mappings_[index] = 0;
            if (frames_.release({index, frames::generation(record)}, owner_) != frames::Rejection::none)
                return std::nullopt;
            ++released;
        }
        root_ = 0;
        count_ = 0;
        return released;
    }
};
} // namespace aurora::uefi
