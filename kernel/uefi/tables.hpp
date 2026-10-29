#pragma once
#include "handoff.hpp"
#include "service-budget-policy.hpp"
#include "framebuffer-policy.hpp"
#include <array>
// Share large helpers only inside the existing Event build family.
#ifdef AURORA_UEFI_IOMMU_EVENT
#define AURORA_UEFI_EVENT_OUTLINE [[gnu::noinline]]
#else
#define AURORA_UEFI_EVENT_OUTLINE
#endif
namespace aurora::uefi {
inline auto expected_flags(std::uint64_t offset, const Bytes &h) -> std::uint64_t;
class PageTables final {
    static_assert(Handoff::arena_bytes <= (1ULL << 21)); // Bound the identity-table inventory below.
    std::uint64_t base_;
    std::size_t used_ = 1;
    const FramebufferAdmission *framebuffer_ = nullptr;
    PageTables(std::uint64_t base, std::size_t used, const FramebufferAdmission *framebuffer)
        : base_(base), used_(used), framebuffer_(framebuffer) {
    }
    [[nodiscard]] auto table(std::uint64_t physical) const -> std::uint64_t * {
        return reinterpret_cast<std::uint64_t *>(physical);
    }

public:
    static constexpr std::uint64_t nx = 1ULL << 63;
    explicit PageTables(std::uint64_t base, std::size_t used = 1) : base_(base), used_(used) {
    }
    [[nodiscard]] auto used() const -> std::size_t {
        return used_;
    }
    [[nodiscard]] auto map(std::uint64_t page, std::uint64_t flags) -> bool {
        if (page % 4096 || page >= 0x100000000ULL || (flags != 1 && flags != (1 | nx) && flags != (3 | nx)))
            return false;
        auto current = base_;
        for (const auto shift : {39U, 30U, 21U}) {
            auto &entry = table(current)[(page >> shift) & 511];
            if (entry == 0) {
                if (used_ == Handoff::table_pages)
                    return false;
                entry = (base_ + used_++ * 4096) | 3;
            }
            current = entry & 0x000ffffffffff000ULL;
            if (current < base_ || current >= base_ + used_ * 4096)
                return false;
        }
        auto &leaf = table(current)[(page >> 12) & 511];
        if (leaf != 0)
            return false;
        leaf = page | flags;
        return true;
    }
    static constexpr std::uint64_t window_address = 0xffff800000000000ULL;
    [[nodiscard]] auto prepare_window() -> bool {
        auto current = base_;
        for (const auto shift : {39U, 30U, 21U}) {
            auto &entry = table(current)[(window_address >> shift) & 511];
            if (entry == 0) {
                if (used_ == Handoff::table_pages)
                    return false;
                entry = (base_ + used_++ * 4096) | 3;
            }
            current = entry & 0x000ffffffffff000ULL;
            if (current < base_ || current >= base_ + used_ * 4096)
                return false;
        }
        return table(current)[0] == 0;
    }
    [[nodiscard]] auto window_slot() const -> volatile std::uint64_t * {
        auto current = base_;
        for (const auto shift : {39U, 30U, 21U}) {
            const auto link = table(current)[(window_address >> shift) & 511];
            if ((link & ~0x000ffffffffff060ULL) != 3)
                return nullptr;
            current = link & 0x000ffffffffff000ULL;
            if (current < base_ || current >= base_ + used_ * 4096)
                return nullptr;
        }
        return table(current);
    }
    static constexpr std::uint64_t interrupt_address = 0xffff900000000000ULL;
    [[nodiscard]] auto prepare_interrupts() -> bool {
        auto current = base_;
        for (const auto shift : {39U, 30U, 21U}) {
            auto &entry = table(current)[(interrupt_address >> shift) & 511];
            if (entry == 0) {
                if (used_ == Handoff::table_pages)
                    return false;
                entry = (base_ + used_++ * 4096) | 3;
            }
            current = entry & 0x000ffffffffff000ULL;
            if (current < base_ || current >= base_ + used_ * 4096)
                return false;
        }
        return table(current)[0] == 0;
    }
    [[nodiscard]] auto interrupt_slot() const -> volatile std::uint64_t * {
        auto current = base_;
        for (const auto shift : {39U, 30U, 21U}) {
            const auto link = table(current)[(interrupt_address >> shift) & 511];
            if ((link & ~0x000ffffffffff060ULL) != 3)
                return nullptr;
            current = link & 0x000ffffffffff000ULL;
            if (current < base_ || current >= base_ + used_ * 4096)
                return nullptr;
        }
        return table(current);
    }
    // Reserve only the exact intermediate paths, leaving all leaves absent.
    // The existing fixed table arena is unchanged; no firmware allocation occurs.
    [[nodiscard]] auto prepare_framebuffer(const FramebufferGeometry &geometry) -> bool {
        if (used_ == 0 || used_ > Handoff::table_pages || base_ < Handoff::tables_offset ||
            !RuntimeLayout::valid(base_ - Handoff::tables_offset))
            return false;
        for (std::uint64_t offset = 0; offset < geometry.mapped_bytes(); offset += 4096) {
            const auto page = FramebufferAdmission::virtual_address + offset;
            auto current = base_;
            for (const auto shift : {39U, 30U, 21U}) {
                auto &link = table(current)[(page >> shift) & 511];
                if (!link) {
                    if (used_ >= Handoff::table_pages)
                        return false;
                    link = (base_ + used_++ * 4096) | 3;
                }
                if ((link & ~0x000ffffffffff060ULL) != 3)
                    return false;
                current = link & 0x000ffffffffff000ULL;
                if (current < base_ || current >= base_ + used_ * 4096)
                    return false;
            }
            if (table(current)[(page >> 12) & 511])
                return false;
        }
        return true;
    }
    [[nodiscard]] auto install_framebuffer(const FramebufferAdmission &admission) -> bool {
        if (base_ != admission.owned_arena() + Handoff::tables_offset || used_ == 0 || used_ > Handoff::table_pages)
            return false;
        // Preflight every target before changing any leaf. This method cannot
        // allocate tables, accept arbitrary physical pages, or replace a leaf.
        for (unsigned pass = 0; pass < 2; ++pass) {
            for (std::uint64_t offset = 0; offset < admission.geometry().mapped_bytes(); offset += 4096) {
                const auto page = FramebufferAdmission::virtual_address + offset;
                auto current = base_;
                for (const auto shift : {39U, 30U, 21U}) {
                    const auto link = table(current)[(page >> shift) & 511];
                    if ((link & ~0x000ffffffffff060ULL) != 3)
                        return false;
                    current = link & 0x000ffffffffff000ULL;
                    if (current < base_ || current >= base_ + used_ * 4096)
                        return false;
                }
                auto &leaf = table(current)[(page >> 12) & 511];
                if (leaf)
                    return false;
                if (pass)
                    leaf = admission.mapping(page);
            }
        }
        return true;
    }
    // Keep one verifier body in every profile. Only the explicit
    // four-argument overload below creates an authorized framebuffer view.
    AURORA_UEFI_EVENT_OUTLINE [[nodiscard]] auto
    verify(std::uint64_t arena, const Bytes &h, const LocalApicAdmission *apic = nullptr) const -> bool {
        const auto *framebuffer = framebuffer_;
        if (used_ == 0 || used_ > Handoff::table_pages || base_ != arena + Handoff::tables_offset ||
            (apic && apic->owned_arena() != arena) ||
            (framebuffer && (framebuffer->owned_arena() != arena || h.get(8, 4) != 5 || apic)))
            return false;
        std::array<bool, Handoff::table_pages> visited{};
        // The same fixed-slot traversal as verify_graphical, preserving this
        // overload's narrower authority and its historical A/D normalization.
        // Four levels need four slots; each descent initializes all child state.
        class Frame final {
        public:
            std::uint64_t physical, prefix, next;
        };
        std::array<Frame, 4> traversal;
        traversal[0] = {base_, 0, 0};
        unsigned depth = 0;
        for (;;) {
            if (depth >= traversal.size())
                return false;
            auto &frame = traversal[depth];
            const auto physical = frame.physical, prefix = frame.prefix;
            if (frame.next == 0) {
                if (physical < base_ || physical >= base_ + used_ * 4096 || physical % 4096)
                    return false;
                const auto slot = (physical - base_) / 4096;
                if (visited[slot])
                    return false;
                visited[slot] = true;
            }
            if (frame.next == 512) {
                if (depth == 0)
                    break;
                --depth;
                continue;
            }
            const auto index = frame.next++;
            const auto value = table(physical)[index] & ~0x60ULL;
            if (!value)
                continue;
            const auto level = 3 - depth;
            const auto address = prefix | (index << (12 + 9 * level));
            if (level != 0) {
                if (depth + 1 >= traversal.size() || (value & ~0x000ffffffffff000ULL) != 3)
                    return false;
                traversal[++depth] = {value & 0x000ffffffffff000ULL, address, 0};
            } else {
                const auto canonical = (address & (1ULL << 47)) ? address | 0xffff000000000000ULL : address;
                if (apic && canonical == LocalApicAdmission::virtual_address) {
                    if (value != (LocalApicAdmission::physical_address | LocalApicAdmission::leaf_flags))
                        return false;
                    continue;
                }
                if (framebuffer && framebuffer->mapping(canonical)) {
                    if (value != framebuffer->mapping(canonical))
                        return false;
                    continue;
                }
                if (address < arena || address >= arena + Handoff::arena_bytes)
                    return false;
                const auto flags = expected_flags(address - arena, h);
                if (!flags || value != (address | flags))
                    return false;
            }
        }
        for (std::size_t i = 0; i < used_; ++i)
            if (!visited[i])
                return false;
        for (std::uint64_t offset = 0; offset < Handoff::arena_bytes; offset += 4096) {
            const auto flags = expected_flags(offset, h);
            const auto expected = flags ? (arena + offset) | flags : 0;
            if ((entry(arena + offset) & ~0x60ULL) != expected)
                return false;
        }
        if (apic && (entry(LocalApicAdmission::virtual_address) & ~0x60ULL) !=
                        (LocalApicAdmission::physical_address | LocalApicAdmission::leaf_flags))
            return false;
        if (framebuffer) {
            for (std::uint64_t offset = 0; offset < framebuffer->geometry().mapped_bytes(); offset += 4096) {
                const auto page = FramebufferAdmission::virtual_address + offset;
                if ((entry(page) & ~0x60ULL) != framebuffer->mapping(page))
                    return false;
            }
            if (entry(FramebufferAdmission::virtual_address - 4096) ||
                entry(FramebufferAdmission::virtual_address + framebuffer->geometry().mapped_bytes()))
                return false;
        }
        return true;
    }
    [[nodiscard]] auto verify(std::uint64_t arena,
                              const Bytes &h,
                              const LocalApicAdmission *apic,
                              const FramebufferAdmission *framebuffer) const -> bool {
        return PageTables{base_, used_, framebuffer}.verify(arena, h, apic);
    }
    // Integer-only storage check for the paired verifier. Checked half-open
    // endpoints reject wrapping intervals; exactly adjacent objects are disjoint.
    // Keep the complete paired guard and its compiler stack record together.
    // Admission still checks actual output; attributes are not frame evidence.
    [[nodiscard, gnu::noinline, gnu::noclone, gnu::noipa]] static constexpr auto
    paired_graphical_storage_disjoint(std::uint64_t a, std::uint64_t size_a, std::uint64_t b, std::uint64_t size_b)
        -> bool {
        return size_a <= ~std::uint64_t{0} - a && size_b <= ~std::uint64_t{0} - b &&
               (a + size_a <= b || b + size_b <= a);
    }
    // v6 places the graphics record at word 120. v7 keeps word 120 for the
    // runtime metadata and places the record at word 128; nothing else pairs.
    [[nodiscard]] static auto paired_records(const Bytes &h, std::uint64_t arena) -> bool {
        if (h.get(8, 4) == 6)
            return h.get(120) == arena + Handoff::framebuffer_record_offset;
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
        return h.get(8, 4) == 7 && h.get(120) == arena + RuntimeLayout::metadata_offset &&
               h.get(Handoff::framebuffer_word) == arena + Handoff::framebuffer_record_offset;
#else
        return false;
#endif
    }
    // An explicitly paired boundary, never an extension of legacy verify's
    // device authority. Empty v6 staging still uses verify(arena, h); the caller
    // must additionally establish that base_ is the live CR3 before using this
    // proof to open either service. Both source-bound admissions are mandatory.
    // A page-aligned below-4-GiB arena of at most 2 MiB crosses at most two
    // 2-MiB regions and two 1-GiB regions: root + PDPT + 2 PD + 2 PT <=6 pages.
    // Source reasoning for the loader's allocation order: +3 ACPI-window pages,
    // +3 LAPIC pages, then +3 fixture or +4 maximum-geometry graphics pages.
    // Separate high PML4 slots give <=15 fixture / <=16 maximum total pages.
    // The walk checks actual inventory; these bounds are not measured receipts.
    [[nodiscard]] auto verify_graphical(std::uint64_t arena,
                                        const Bytes &h,
                                        const LocalApicAdmission *apic,
                                        const FramebufferAdmission *framebuffer) const -> bool {
        // Capture every descriptor field before any snapshot construction write.
        // This ordering and local storage independence rely on reviewed C++
        // source and trusted compilation. All later fields use snapshot.
        const PageTables snapshot{base_, used_, framebuffer_};
        if (!apic || !framebuffer || snapshot.framebuffer_ || !RuntimeLayout::valid(arena) || snapshot.used_ == 0 ||
            snapshot.used_ > Handoff::table_pages || snapshot.base_ != arena + Handoff::tables_offset ||
            h.get(0) != Handoff::magic || !paired_records(h, arena) || h.get(12, 4) != Handoff::header ||
            h.get(16) != Handoff::arena_bytes || h.get(24) != arena || !h.get(32) || h.get(32) > MemoryMap::max_bytes ||
            h.get(40) < 40 || h.get(40) > 256 || h.get(48, 4) != 1 || h.get(52, 4) < 1 || h.get(52, 4) > 3 ||
            !h.get(56) || h.get(56) > Handoff::payload_limit || h.get(56) > h.get(80) || !h.get(64) ||
            h.get(64) % 4096 || h.get(72) % 4096 || h.get(80) % 4096 || h.get(64) > h.get(72) ||
            h.get(72) > h.get(80) || h.get(80) > Handoff::payload_limit || h.get(88) != snapshot.base_ ||
            h.get(96) != snapshot.used_ || h.get(104) != arena + Handoff::payload_offset || !h.get(112) ||
            apic->owned_arena() != arena || framebuffer->owned_arena() != arena)
            return false;
        const auto &geometry = framebuffer->geometry();
        const auto physical = geometry.base(), bytes = geometry.mapped_bytes();
        const auto bits = apic->physical_bits();
        if (bits < 32 || bits > 52 || !physical || physical % 4096 || !bytes || bytes % 4096 ||
            bytes > FramebufferGeometry::max_mapped_bytes || bytes > geometry.resource_bytes())
            return false;
        const auto limit = std::uint64_t{1} << bits;
        if (physical >= limit || geometry.resource_bytes() > limit - physical)
            return false;
        // Check the relationship independently of each admission's creation.
        // All ends below are bounded before addition; guards belong to the
        // framebuffer's virtual reservation but never receive a leaf.
        const auto disjoint = [](std::uint64_t a, std::uint64_t size_a, std::uint64_t b, std::uint64_t size_b) {
            return size_a <= ~std::uint64_t{0} - a && size_b <= ~std::uint64_t{0} - b &&
                   (a + size_a <= b || b + size_b <= a);
        };
        constexpr auto graphics_guard = FramebufferAdmission::virtual_address - 4096;
        const auto graphics_span = bytes + 8192;
        if (!disjoint(physical, bytes, arena, Handoff::arena_bytes) ||
            !disjoint(physical, bytes, LocalApicAdmission::physical_address, LocalApicAdmission::page_size) ||
            !disjoint(physical, bytes, 0xfec00000ULL, 4096) ||
            !disjoint(physical, bytes, 0xe0000000ULL, 0x10000000ULL) ||
            !disjoint(
                LocalApicAdmission::physical_address, LocalApicAdmission::page_size, arena, Handoff::arena_bytes) ||
            !disjoint(graphics_guard, graphics_span, arena, Handoff::arena_bytes) ||
            !disjoint(graphics_guard, graphics_span, window_address, 4096) ||
            !disjoint(
                graphics_guard, graphics_span, LocalApicAdmission::virtual_address, LocalApicAdmission::page_size) ||
            !disjoint(LocalApicAdmission::virtual_address, LocalApicAdmission::page_size, window_address, 4096) ||
            !apic->admits(interrupt_address,
                          LocalApicAdmission::physical_address,
                          LocalApicAdmission::page_size,
                          LocalApicAdmission::leaf_flags))
            return false;
        // Admit only intermediate paths needed by exact arena leaves or the
        // three reserved device/window apertures. This also rejects extra empty
        // subtrees, not merely extra leaves. The ACPI window itself stays closed.
        const auto path_required = [&](std::uint64_t address, unsigned level) {
            const auto mask = ~((std::uint64_t{1} << (12 + 9 * level)) - 1);
            if ((window_address & mask) == address || (LocalApicAdmission::virtual_address & mask) == address)
                return true;
            const auto first = FramebufferAdmission::virtual_address & mask;
            const auto last = (FramebufferAdmission::virtual_address + bytes - 4096) & mask;
            if (address >= first && address <= last)
                return true;
            for (std::uint64_t offset = 0; offset < Handoff::arena_bytes; offset += 4096)
                if (expected_flags(offset, h) && ((arena + offset) & mask) == address)
                    return true;
            return false;
        };
        // Four paging levels need four local traversal slots, never recursive calls.
        // Each slot is {table address, virtual prefix, next entry}; only active
        // slots are read, and every push initializes the complete child slot.
        std::array<bool, Handoff::table_pages> visited;
        std::array<std::array<std::uint64_t, 3>, 4> traversal;
        const auto descriptor_begin = reinterpret_cast<std::uint64_t>(this);
        const auto snapshot_begin = reinterpret_cast<std::uint64_t>(&snapshot);
        const auto bitmap_begin = reinterpret_cast<std::uint64_t>(&visited);
        const auto traversal_begin = reinterpret_cast<std::uint64_t>(&traversal);
        if (!paired_graphical_storage_disjoint(descriptor_begin, sizeof(*this), bitmap_begin, sizeof(visited)) ||
            !paired_graphical_storage_disjoint(descriptor_begin, sizeof(*this), snapshot_begin, sizeof(snapshot)) ||
            !paired_graphical_storage_disjoint(descriptor_begin, sizeof(*this), traversal_begin, sizeof(traversal)) ||
            !paired_graphical_storage_disjoint(snapshot_begin, sizeof(snapshot), bitmap_begin, sizeof(visited)) ||
            !paired_graphical_storage_disjoint(snapshot_begin, sizeof(snapshot), traversal_begin, sizeof(traversal)) ||
            !paired_graphical_storage_disjoint(bitmap_begin, sizeof(visited), traversal_begin, sizeof(traversal)))
            return false;
        visited.fill(false);
        traversal[0] = {snapshot.base_, 0, 0};
        unsigned depth = 0;
        for (;;) {
            if (depth >= traversal.size())
                return false;
            auto &frame = traversal[depth];
            const auto table_address = frame[0], prefix = frame[1];
            if (frame[2] == 0) {
                if (table_address < snapshot.base_ || table_address >= snapshot.base_ + snapshot.used_ * 4096 ||
                    table_address % 4096)
                    return false;
                const auto slot = (table_address - snapshot.base_) / 4096;
                if (visited[slot])
                    return false;
                visited[slot] = true;
            }
            if (frame[2] == 512) {
                if (depth == 0)
                    break;
                --depth;
                continue;
            }
            const auto index = frame[2]++;
            const auto raw = snapshot.table(table_address)[index];
            // Only present entries may have hardware A/D normalization.
            // A non-present slot, including a guard, must be exactly zero.
            if (!raw)
                continue;
            const auto level = 3 - depth;
            const auto value = raw & ~0x60ULL;
            const auto address = prefix | (index << (12 + 9 * level));
            const auto canonical = (address & (1ULL << 47)) ? address | 0xffff000000000000ULL : address;
            if (level != 0) {
                if (depth + 1 >= traversal.size() || (value & ~0x000ffffffffff000ULL) != 3 ||
                    !path_required(canonical, level))
                    return false;
                traversal[++depth] = {value & 0x000ffffffffff000ULL, address, 0};
            } else if (canonical == LocalApicAdmission::virtual_address) {
                if (value != apic->mapping(canonical))
                    return false;
            } else if (const auto mapping = framebuffer->mapping(canonical)) {
                if (value != mapping)
                    return false;
            } else {
                if (address < arena || address >= arena + Handoff::arena_bytes)
                    return false;
                const auto flags = expected_flags(address - arena, h);
                if (!flags || value != (address | flags))
                    return false;
            }
        }
        for (std::size_t index = 0; index < snapshot.used_; ++index)
            if (!visited[index])
                return false;
        for (std::uint64_t offset = 0; offset < Handoff::arena_bytes; offset += 4096) {
            const auto flags = expected_flags(offset, h);
            const auto expected = flags ? (arena + offset) | flags : 0;
            const auto actual = snapshot.entry(arena + offset);
            if ((flags ? actual & ~0x60ULL : actual) != expected)
                return false;
        }
        if (!snapshot.window_slot() || snapshot.entry(window_address) ||
            (snapshot.entry(LocalApicAdmission::virtual_address) & ~0x60ULL) !=
                apic->mapping(LocalApicAdmission::virtual_address))
            return false;
        for (std::uint64_t offset = 0; offset < bytes; offset += 4096) {
            const auto page = FramebufferAdmission::virtual_address + offset;
            if ((snapshot.entry(page) & ~0x60ULL) != framebuffer->mapping(page))
                return false;
        }
        return !snapshot.entry(graphics_guard) && !snapshot.entry(FramebufferAdmission::virtual_address + bytes);
    }
    // Keep one exact object/link identity for the trusted lookup. Local IPA
    // clones with identical names in separate translation units are not admitted
    // by the complete mixed-stack/object proof.
    [[nodiscard, gnu::noinline, gnu::noclone]] auto entry(std::uint64_t page) const -> std::uint64_t {
        auto current = base_;
        for (const auto shift : {39U, 30U, 21U}) {
            const auto link = table(current)[(page >> shift) & 511];
            if ((link & ~0x000ffffffffff060ULL) != 3)
                return 0;
            current = link & 0x000ffffffffff000ULL;
            if (current < base_ || current >= base_ + used_ * 4096)
                return 0;
        }
        return table(current)[(page >> 12) & 511];
    }
};
inline auto expected_flags(std::uint64_t offset, const Bytes &h) -> std::uint64_t {
    if (Handoff::framebuffer(h) && offset == Handoff::framebuffer_record_offset)
        return 1 | PageTables::nx;
    if (h.get(8, 4) == 4 && offset == Handoff::bar_record_offset)
        return 1 | PageTables::nx;
    if (Handoff::runtime(h)) {
        const auto flags = RuntimeLayout::kernel_flags(offset);
        if (flags)
            return flags;
    }
#ifdef AURORA_PROCESS_FIXTURE
    // Version 8 carries no ACPI snapshots.
    if (h.get(8, 4) >= 2 && h.get(8, 4) != 8 && offset >= 0x60000 && offset < 0x81000)
#else
    if (h.get(8, 4) >= 2 && offset >= 0x60000 && offset < 0x81000)
#endif
        return 3 | PageTables::nx;
    if (offset == 0 || (offset >= Handoff::map_offset && offset < Handoff::tables_offset))
        return 1 | PageTables::nx;
    if ((offset >= Handoff::tables_offset && offset < Handoff::tables_offset + Handoff::table_pages * 4096) ||
        offset == Handoff::idt_offset || (offset >= Handoff::stack_bottom && offset < Handoff::stack_top) ||
        (offset >= Handoff::pool_offset && offset < Handoff::pool_offset + 16 * 4096))
        return 3 | PageTables::nx;
    if (offset == Handoff::transition_offset)
        return 1;
    if (offset >= Handoff::payload_offset && offset < Handoff::payload_offset + h.get(80)) {
        const auto relative = offset - Handoff::payload_offset;
        return relative < h.get(64) ? 1 : relative < h.get(72) ? 1 | PageTables::nx : 3 | PageTables::nx;
    }
    return 0;
}
} // namespace aurora::uefi
