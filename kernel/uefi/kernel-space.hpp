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
    static constexpr U64 process_pages = process::memory_records * sizeof(process::MemoryRecord) / frames::page;
    class Plan final {
    public:
        U64 metadata = 0, metadata_tables = 0, volume = 0, volume_tables = 0, tables = 0, records = 0, process = 0;
    };
    [[nodiscard]] static auto plan(U64 frames, U64 volume_pages, U64 process) -> std::optional<Plan> {
        Plan result;
        if (frames == 0 || frames > (U64{1} << 32) || volume_pages > 512 * 512 || (process && process != process_pages))
            return std::nullopt;
        result.records = (frames * 8 + frames::page - 1) / frames::page;
        result.process = process;
        result.metadata = 2 * result.records + process;
        result.metadata_tables = (result.metadata + 511) / 512;
        result.volume = volume_pages;
        result.volume_tables = (volume_pages + 511) / 512;
        result.tables = 2 + result.metadata_tables + (volume_pages ? 1 + result.volume_tables : 0);
        if (result.metadata_tables > 512 || result.tables > 510 || result.tables + result.metadata >= frames)
            return std::nullopt;
        return result;
    }

private:
    U64 root_ = 0;
    volatile U64 *window_ = nullptr;
    std::array<U64, 512> root_snapshot_{};
    Plan plan_{};
    U64 volume_physical_ = 0;
    bool built_ = false;

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
        if (!root_ || built_ || plan.tables + plan.metadata >= ranges.frames() || volume % frames::page)
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
    [[nodiscard]] auto metadata(U64 frames) const -> std::span<U64> {
        if (!built_ || frames * 8 > plan_.records * frames::page)
            return {};
        return {reinterpret_cast<U64 *>(metadata_base), frames};
    }
    // The mapping words: what each frame holds in a process (process-space.hpp).
    [[nodiscard]] auto mappings(U64 frames) const -> std::span<U64> {
        if (!built_ || frames * 8 > plan_.records * frames::page)
            return {};
        return {reinterpret_cast<U64 *>(metadata_base + plan_.records * frames::page), frames};
    }
    // The memory records of the one running process (process-space.hpp).
    [[nodiscard]] auto process_records() const -> std::span<process::MemoryRecord> {
        if (!built_ || plan_.process != process_pages)
            return {};
        return {reinterpret_cast<process::MemoryRecord *>(metadata_base + 2 * plan_.records * frames::page),
                process::memory_records};
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
    auto close() -> void {
        window_[0] = 0;
        invalidate(window_base);
    }
    // Every extension entry exact, every table and metadata page a kernel frame
    // of its owner, volume pages outside the frame inventory, the window closed
    // and the remaining root entries those the boot verifier admitted.
    [[nodiscard]] auto verify(const frames::Table &frames, const frames::Ranges &ranges, U64 used) const -> bool {
        if (!built_ || PageTables{root_, used}.window_slot() != window_ || window_[0])
            return false;
        for (U64 index = 0; index < 512; ++index) {
            const auto expected =
                index == extension_root ? (*ranges.address(0) | table_flags) : (root_snapshot_[index] & ~hardware_bits);
            if (entry(table(root_), index) != expected)
                return false;
        }
        const auto kernel = [&](U64 index, U64 owner) {
            const auto record = frames.record(index);
            return frames::state(record) == static_cast<U64>(frames::State::kernel) && frames::word(record) == owner;
        };
        const auto physical = [&](U64 index) {
            return *ranges.address(index);
        };
        for (U64 index = 0; index < plan_.tables; ++index)
            if (!kernel(index, frames::owner_tables))
                return false;
        for (U64 index = 0; index < plan_.metadata; ++index)
            if (!kernel(plan_.tables + index, frames::owner_metadata))
                return false;
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
};
} // namespace aurora::uefi
