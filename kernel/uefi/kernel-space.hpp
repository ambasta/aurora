#pragma once
// Kernel mappings beyond the arena's sixteen fixed table pages
// (kernel/uefi/process.md#kernel-space). The loader reserves the arena-owned
// window path at PageTables::window_address; its 512-entry table maps slot 0
// as the transient frame window, leaves slot 1 absent as a guard, and maps
// slots 2.. as RW/NX views of dynamic table pages taken from the frame inventory. Those tables map, under one extension
// root slot, the frame metadata RW/NX and the boot volume read-only/NX. The
// complete walk in verify() checks every entry of this extension and the
// unchanged remainder of the boot-verified root.
#include "frames.hpp"
#include "tables.hpp"

namespace aurora::uefi {
class KernelSpace final {
public:
    using U64 = std::uint64_t;
    static constexpr U64 window_base = PageTables::window_address;
    static constexpr U64 extension = 0xffffc00000000000ULL;
    static constexpr U64 metadata_base = extension;
    static constexpr U64 volume_base = extension + (U64{1} << 30);
    static constexpr std::size_t window_root = (window_base >> 39) & 511, extension_root = (extension >> 39) & 511;
    static constexpr U64 table_flags = 3, data_flags = 3 | PageTables::nx, read_flags = 1 | PageTables::nx;
    static constexpr U64 address_mask = 0x000ffffffffff000ULL, hardware_bits = 0x60;
    // Frame count, pages and tables of one extension: PDPT, metadata PD and
    // PTs, then (with a volume) volume PD and PTs, at frame indices 0..tables-1.
    // The metadata is one 8-byte record per frame, then from the next page one
    // 8-byte mapping word per frame (process-space.hpp), then process pages:
    // the running process's memory records when the image runs processes
    // (process_pages, process::memory_records of them), none otherwise.
    static constexpr U64 process_slots = 2;
    static constexpr U64 process_pages = process::memory_records * sizeof(process::MemoryRecord) / frames::page;
    static constexpr U64 reservation_tail_pages = 1, observation_pages = 1, words_per_page = frames::page / sizeof(U64);
    class Plan final {
    public:
        U64 metadata = 0, metadata_tables = 0, volume = 0, volume_tables = 0, tables = 0, records = 0, process = 0;
        U64 reservation_tail = 0, scratch = 0;
    };
    class BankLayout final {
    public:
        std::array<U64, 4> word_offsets{}, word_counts{};
        U64 tail_offset = 0, tail_words = 0, metadata_words = 0;
    };
    [[nodiscard]] static auto plan(U64 frames, U64 volume_pages, U64 process) -> std::optional<Plan> {
        Plan result;
        if (frames == 0 || frames > (U64{1} << 32) || volume_pages > 512 * 512 ||
            process > process_slots * process_pages || process % process_pages)
            return std::nullopt;
        result.records = (frames * 8 + frames::page - 1) / frames::page;
        result.process = process;
        // Process ownership retains one page of region/shared/staging metadata
        // after the fixed reservation records, plus a disjoint observation page.
        result.reservation_tail = process ? reservation_tail_pages : 0;
        result.scratch = process ? observation_pages : 0;
        result.metadata = 2 * result.records + process + result.reservation_tail + result.scratch;
        result.metadata_tables = (result.metadata + 511) / 512;
        result.volume = volume_pages;
        result.volume_tables = (volume_pages + 511) / 512;
        result.tables = 2 + result.metadata_tables + (volume_pages ? 1 + result.volume_tables : 0);
        if (result.metadata_tables > 512 || result.tables > 510 || result.tables + result.metadata >= frames)
            return std::nullopt;
        return result;
    }

    // Runtime backing extents depend on the admitted inventory. Compiler facts
    // authenticate root fields; this checked plan authenticates their backing.
    [[nodiscard]] static auto bank_layout(const Plan &value, U64 frame_count) -> std::optional<BankLayout> {
        const auto expected = plan(frame_count, value.volume, value.process);
        if (!expected || expected->metadata != value.metadata || expected->metadata_tables != value.metadata_tables ||
            expected->volume_tables != value.volume_tables || expected->tables != value.tables ||
            expected->records != value.records || expected->reservation_tail != value.reservation_tail ||
            expected->scratch != value.scratch)
            return std::nullopt;
        BankLayout result;
        result.word_offsets = {0,
                               value.records * words_per_page,
                               2 * value.records * words_per_page,
                               (2 * value.records + value.process + value.reservation_tail) * words_per_page};
        result.word_counts = {frame_count,
                              frame_count,
                              (value.process + value.reservation_tail) * words_per_page,
                              value.scratch * words_per_page};
        result.tail_offset = (2 * value.records + value.process) * words_per_page;
        result.tail_words = value.reservation_tail * words_per_page;
        result.metadata_words = value.metadata * words_per_page;
        for (std::size_t index = 0; index < result.word_offsets.size(); ++index)
            if (result.word_offsets[index] > result.metadata_words ||
                result.word_counts[index] > result.metadata_words - result.word_offsets[index] ||
                (index && result.word_offsets[index - 1] + result.word_counts[index - 1] > result.word_offsets[index]))
                return std::nullopt;
        return result;
    }

private:
    U64 root_ = 0;
    volatile U64 *window_ = nullptr;
    std::array<U64, 512> root_snapshot_{};
    Plan plan_{};
    U64 volume_physical_ = 0;
    bool built_ = false, detached_ = false, banks_handed_ = false;
    U64 saved_extension_ = 0;

    [[nodiscard]] static auto table(U64 address) -> volatile U64 * {
        return reinterpret_cast<volatile U64 *>(address);
    }
    // Table i (frame index i) is view i + 1, in window slot i + 2.
    static constexpr U64 first_view_slot = 2;
    [[nodiscard]] static auto view(U64 view) -> volatile U64 * {
        return table(window_base + (view + 1) * frames::page);
    }
    static auto invalidate(U64 address) -> void {
        asm volatile("invlpg (%0)" : : "r"(address) : "memory");
    }
    [[nodiscard]] auto pd_volume() const -> U64 {
        return 3 + plan_.metadata_tables;
    }
    // A present entry with hardware accessed/dirty bits normalized.
    [[nodiscard]] static auto entry(volatile U64 *page, U64 index) -> U64 {
        const auto value = page[index];
        return value ? value & ~hardware_bits : 0;
    }
    [[nodiscard]] static auto exact(volatile U64 *page, U64 used, auto expected) -> bool {
        for (U64 index = 0; index < 512; ++index)
            if (entry(page, index) != (index < used ? expected(index) : 0))
                return false;
        return true;
    }

public:
    // The live view of dynamic table i (fixture probes edit through it).
    [[nodiscard]] static auto table_view(U64 index) -> volatile U64 * {
        return view(index + 1);
    }
    // Bind the boot-verified root and the loader's still-empty window table.
    [[nodiscard]] auto bind(U64 root, volatile U64 *window) -> bool {
        if (root_ || !root || root % frames::page || !window || table(root)[extension_root])
            return false;
        for (U64 index = 0; index < 512; ++index)
            if (window[index])
                return false;
        root_ = root;
        window_ = window;
        for (U64 index = 0; index < 512; ++index)
            root_snapshot_[index] = table(root)[index];
        return true;
    }
    // Map the planned tables' views, zero them, link the extension and map the
    // metadata and volume pages. Frame indices 0.. are the planned tables, then
    // the metadata pages; the volume is the loader's separate grant.
    [[nodiscard]] auto build(const frames::Ranges &ranges, const Plan &plan, U64 volume) -> bool {
        if (!root_ || built_ || !bank_layout(plan, ranges.frames()) || volume % frames::page)
            return false;
        plan_ = plan;
        volume_physical_ = volume;
        for (U64 index = 0; index < plan.tables; ++index) {
            const auto physical = ranges.address(index);
            if (!physical)
                return false;
            window_[first_view_slot + index] = *physical | data_flags;
            invalidate(window_base + (first_view_slot + index) * frames::page);
            for (U64 slot = 0; slot < 512; ++slot)
                view(index + 1)[slot] = 0;
        }
        const auto physical = [&](U64 index) {
            return *ranges.address(index);
        };
        view(1)[0] = physical(1) | table_flags;
        for (U64 index = 0; index < plan.metadata_tables; ++index)
            view(2)[index] = physical(2 + index) | table_flags;
        for (U64 page = 0; page < plan.metadata; ++page)
            view(3 + page / 512)[page % 512] = physical(plan.tables + page) | data_flags;
        if (plan.volume) {
            view(1)[1] = physical(pd_volume() - 1) | table_flags;
            for (U64 index = 0; index < plan.volume_tables; ++index)
                view(pd_volume())[index] = physical(pd_volume() + index) | table_flags;
            for (U64 page = 0; page < plan.volume; ++page)
                view(pd_volume() + 1 + page / 512)[page % 512] = (volume + page * frames::page) | read_flags;
        }
        table(root_)[extension_root] = physical(0) | table_flags;
        U64 cr3;
        asm volatile("mov %%cr3, %0; mov %0, %%cr3" : "=r"(cr3) : : "memory");
        built_ = true;
        return true;
    }
    // One atomic issuer receives allocation, mapping, both resident reservation
    // banks and their private tail, and a disjoint table-observation page. Native
    // mutable aliases are scoped to this one-shot inactive constructor handoff.
    template <class Owner> [[nodiscard]] auto handoff_manager(Owner &owner, const frames::Ranges &ranges) -> bool {
        if (!built_ || detached_ || banks_handed_ || !ranges.frames() ||
            ranges.frames() > plan_.records * frames::page / sizeof(U64) ||
            plan_.process != process_slots * process_pages)
            return false;
        const auto layout = bank_layout(plan_, ranges.frames());
        if (!layout)
            return false;
        const auto bank = [&](std::size_t index) {
            return std::span<U64>{reinterpret_cast<U64 *>(metadata_base + layout->word_offsets[index] * sizeof(U64)),
                                  layout->word_counts[index]};
        };
        const auto allocation = bank(0), mapping = bank(1), reservations = bank(2), scratch = bank(3);
        for (auto span : {allocation, mapping, reservations, scratch})
            for (auto &word : span)
                word = 0;
        banks_handed_ = true;
        return owner.bind(allocation, mapping, reservations, scratch, ranges, plan_.tables, plan_.metadata);
    }
    template <class Owner>
    [[nodiscard]] auto resume_manager(Owner &owner, const frames::Ranges &ranges, U64 used) const -> bool {
        if (!banks_handed_ || plan_.process != process_slots * process_pages || !verify_mapping(ranges, used))
            return false;
        const auto layout = bank_layout(plan_, ranges.frames());
        if (!layout)
            return false;
        std::array<words::Binding::Backing, 4> banks{};
        for (std::size_t index = 0; index < banks.size(); ++index)
            banks[index] = {reinterpret_cast<const U64 *>(metadata_base + layout->word_offsets[index] * sizeof(U64)),
                            layout->word_counts[index]};
        owner.resume_set(banks);
        return true;
    }
    // Hardware authority binds the same boot-admitted extents as the source
    // issuer, not merely another disjoint bank set with matching lengths.
    [[nodiscard]] auto owns_banks(std::span<const words::Binding::Backing> banks, U64 frame_count) const -> bool {
        if (!built_ || detached_ || !banks_handed_ || banks.size() != 4 ||
            plan_.process != process_slots * process_pages)
            return false;
        const auto layout = bank_layout(plan_, frame_count);
        if (!layout)
            return false;
        for (std::size_t index = 0; index < banks.size(); ++index)
            if (banks[index].words !=
                    reinterpret_cast<const U64 *>(metadata_base + layout->word_offsets[index] * sizeof(U64)) ||
                banks[index].count != layout->word_counts[index])
                return false;
        return true;
    }
    [[nodiscard]] auto attached() const -> bool {
        return built_ && !detached_;
    }
    [[nodiscard]] auto volume(U64 bytes) const -> std::span<const std::byte> {
        if (!built_ || bytes > plan_.volume * frames::page)
            return {};
        return {reinterpret_cast<const std::byte *>(volume_base), bytes};
    }
    // The transient frame window: one frame at a time, unmapped before reuse.
    [[nodiscard]] auto open(U64 physical) -> std::uint64_t * {
        if (!built_ || window_[0] || physical % frames::page)
            return nullptr;
        window_[0] = physical | data_flags;
        invalidate(window_base);
        return reinterpret_cast<std::uint64_t *>(window_base);
    }
    [[nodiscard]] auto closed() const -> bool {
        return built_ && !detached_ && window_ && window_[0] == 0;
    }
    auto close() -> void {
        window_[0] = 0;
        invalidate(window_base);
    }
    // Return the boot root to its exact pre-extension shape while a retained
    // process is parked. Ownership/contents stay in the frame inventory; no
    // page becomes firmware or another allocator's free memory.
    [[nodiscard]] auto detach() -> bool {
        if (!built_ || detached_ || window_[0] || !table(root_)[extension_root])
            return false;
        saved_extension_ = table(root_)[extension_root] & ~hardware_bits;
        table(root_)[extension_root] = root_snapshot_[extension_root];
        for (U64 slot = first_view_slot; slot < 512; ++slot)
            window_[slot] = 0;
        asm volatile("mov %0, %%cr3" : : "r"(root_) : "memory");
        detached_ = true;
        return true;
    }
    [[nodiscard]] auto attach(const frames::Ranges &ranges) -> bool {
        if (!built_ || !detached_ || !saved_extension_)
            return false;
        for (U64 slot = 0; slot < 512; ++slot)
            if (window_[slot] || (table(root_)[slot] & ~hardware_bits) != (root_snapshot_[slot] & ~hardware_bits))
                return false;
        for (U64 index = 0; index < plan_.tables; ++index) {
            const auto physical = ranges.address(index);
            if (!physical)
                return false;
            window_[first_view_slot + index] = *physical | data_flags;
        }
        table(root_)[extension_root] = saved_extension_;
        asm volatile("mov %0, %%cr3" : : "r"(root_) : "memory");
        detached_ = false;
        return true;
    }
    // Every extension entry exact, every table and metadata page a kernel frame
    // of its owner, volume pages outside the frame inventory, the window closed
    // and the remaining root entries those the boot verifier admitted.
    [[nodiscard]] auto verify_mapping(const frames::Ranges &ranges, U64 used) const -> bool {
        if (!built_ || detached_ || PageTables{root_, used}.window_slot() != window_ || window_[0])
            return false;
        for (U64 index = 0; index < 512; ++index) {
            const auto expected =
                index == extension_root ? (*ranges.address(0) | table_flags) : (root_snapshot_[index] & ~hardware_bits);
            if (entry(table(root_), index) != expected)
                return false;
        }
        const auto physical = [&](U64 index) {
            return *ranges.address(index);
        };
        if (!exact(window_, first_view_slot + plan_.tables, [&](U64 slot) {
                return slot >= first_view_slot ? physical(slot - first_view_slot) | data_flags : 0;
            }))
            return false;
        if (!exact(view(1), plan_.volume ? 2 : 1, [&](U64 slot) {
                return physical(slot ? pd_volume() - 1 : 1) | table_flags;
            }))
            return false;
        if (!exact(view(2), plan_.metadata_tables, [&](U64 slot) {
                return physical(2 + slot) | table_flags;
            }))
            return false;
        for (U64 index = 0; index < plan_.metadata_tables; ++index)
            if (!exact(view(3 + index),
                       plan_.metadata - index * 512 < 512 ? plan_.metadata - index * 512 : 512,
                       [&](U64 slot) {
                           return physical(plan_.tables + index * 512 + slot) | data_flags;
                       }))
                return false;
        if (!plan_.volume)
            return true;
        if (!exact(view(pd_volume()), plan_.volume_tables, [&](U64 slot) {
                return physical(pd_volume() + slot) | table_flags;
            }))
            return false;
        for (U64 index = 0; index < plan_.volume_tables; ++index)
            if (!exact(view(pd_volume() + 1 + index),
                       plan_.volume - index * 512 < 512 ? plan_.volume - index * 512 : 512,
                       [&](U64 slot) {
                           return (volume_physical_ + (index * 512 + slot) * frames::page) | read_flags;
                       }))
                return false;
        for (U64 page = 0; page < plan_.volume; ++page)
            if (ranges.index(volume_physical_ + page * frames::page))
                return false;
        return true;
    }
    template <class Owner>
    [[nodiscard]] auto verify(const Owner &frames, const frames::Ranges &ranges, U64 used) const -> bool {
        if (!verify_mapping(ranges, used))
            return false;
        const auto kernel = [&](U64 index, U64 owner) {
            const auto record = frames.record(index);
            return frames::state(record) == static_cast<U64>(frames::State::kernel) && frames::word(record) == owner;
        };
        for (U64 index = 0; index < plan_.tables; ++index)
            if (!kernel(index, frames::owner_tables))
                return false;
        for (U64 index = 0; index < plan_.metadata; ++index)
            if (!kernel(plan_.tables + index, frames::owner_metadata))
                return false;
        return true;
    }
};
} // namespace aurora::uefi
