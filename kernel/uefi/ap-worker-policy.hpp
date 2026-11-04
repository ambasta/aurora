#pragma once
#include "acpi-policy.hpp"

namespace aurora::uefi {
// This inventory outlives the parsing window and Topology. It contains copied
// firmware facts only, not a selected BSP, an AP start permit, or an MMIO view.
class ApWorkerTopology final {
    const std::array<Processor, 2> processors_;
    const std::uint64_t apic_;

    constexpr ApWorkerTopology(const Processor &first, const Processor &second, std::uint64_t apic)
        : processors_{first, second}, apic_(apic) {
    }

public:
    [[nodiscard]] static auto copy(const Topology &topology) -> std::optional<ApWorkerTopology> {
        if (topology.count() != 2)
            return std::nullopt;
        const auto cpus = topology.processors();
        for (const auto &cpu : cpus)
            if (!cpu.enabled || cpu.online_capable || cpu.extended || cpu.id >= 255)
                return std::nullopt;
        if (cpus[0].id == cpus[1].id || cpus[0].uid == cpus[1].uid)
            return std::nullopt;
        return ApWorkerTopology{cpus[0], cpus[1], topology.apic()};
    }
    [[nodiscard]] constexpr auto processors() const -> std::span<const Processor> {
        return processors_;
    }
    [[nodiscard]] constexpr auto apic() const -> std::uint64_t {
        return apic_;
    }
};

// Read-only 32-bit PIO admission, never general firmware I/O authority. The
// supported QEMU v10.0.13 q35 / OVMF edk2-stable202502 contract is PMBASE 0x600
// plus timer offset 8. Sources: QEMU hw/i386/acpi-build.c init_common_fadt_data,
// hw/acpi/core.c acpi_pm_tmr_init/get; OVMF OvmfPkg/Include/OvmfPlatforms.h and
// OvmfPkg/Library/PlatformInitLib/Platform.c PlatformMiscInitialization.
class PmTimerAdmission final {
    const unsigned counter_bits_;
    explicit constexpr PmTimerAdmission(unsigned bits) : counter_bits_(bits) {
    }

public:
    static constexpr std::uint16_t supported_port = 0x608;
    static constexpr std::uint32_t frequency = 3579545;
    // One extra tick covers an initial read immediately before a tick edge.
    static constexpr std::uint32_t ticks_10ms = 35797;
    static constexpr std::uint32_t ticks_200us = 717;

    [[nodiscard]] static auto parse_q35(std::span<const std::byte> fadt) -> std::optional<PmTimerAdmission> {
        if (!Acpi::table(fadt, "FACP") || fadt.size() < 116 || fadt.size() > 276)
            return std::nullopt;
        const Bytes fields{fadt};
        const auto revision = fields.get(8, 1);
        // Rev1 has no GAS. Later revisions must contain the entire original
        // extended block, not a truncated XPmTmrBlk that falls back to legacy.
        if ((revision == 1 && fadt.size() != 116) ||
            (revision != 1 && (revision < 3 || revision > 6 || fadt.size() < 244)) || fields.get(91, 1) != 4 ||
            (fields.get(112, 4) & (1ULL << 20)))
            return std::nullopt;
        const auto legacy = fields.get(76, 4);
        auto selected = legacy;
        if (revision >= 3) {
            const auto address = fields.get(212);
            if (address) {
                // GAS describes a 32-bit register even for a 24-bit counter.
                // Undefined access size is unambiguous with PM_TMR_LEN=4.
                if (fields.get(208, 1) != 1 || fields.get(209, 1) != 32 || fields.get(210, 1) != 0 ||
                    (fields.get(211, 1) != 0 && fields.get(211, 1) != 3) || (legacy && legacy != address))
                    return std::nullopt;
                selected = address; // Extended GAS takes precedence, without alias disagreement.
            } else if (fields.get(208, 4) != 0) {
                return std::nullopt; // No partly populated/ambiguous extended descriptor.
            }
        }
        if (selected != supported_port)
            return std::nullopt;
        return PmTimerAdmission{(fields.get(112, 4) & (1ULL << 8)) ? 32U : 24U};
    }
    [[nodiscard]] constexpr auto port() const -> std::uint16_t {
        return supported_port;
    }
    [[nodiscard]] constexpr auto counter_bits() const -> unsigned {
        return counter_bits_;
    }
    [[nodiscard]] constexpr auto counter_mask() const -> std::uint32_t {
        return counter_bits_ == 32 ? 0xffffffffU : 0xffffffU;
    }
    [[nodiscard]] constexpr auto delta(std::uint32_t start, std::uint32_t current) const -> std::uint32_t {
        return (current - start) & counter_mask();
    }
    [[nodiscard]] constexpr auto bounded_ticks(std::uint32_t ticks) const -> bool {
        return ticks != 0 && ticks <= (counter_mask() >> 1);
    }
};

// Separate from the production single-CPU LocalApicAdmission. Creation binds the
// copied inventory and timer to actual BSP CPU evidence and the owned kernel
// root. The caller still verifies the live APIC ID/version before sending IPIs.
class ApWorkerAdmission final {
    const std::uint64_t arena_, root_;
    const unsigned physical_bits_;
    const std::uint32_t bsp_id_, ap_id_;
    const PmTimerAdmission timer_;

    constexpr ApWorkerAdmission(std::uint64_t arena,
                                std::uint64_t root,
                                unsigned bits,
                                std::uint32_t bsp,
                                std::uint32_t ap,
                                const PmTimerAdmission &timer)
        : arena_(arena), root_(root), physical_bits_(bits), bsp_id_(bsp), ap_id_(ap), timer_(timer) {
    }

public:
    static constexpr std::uint64_t physical_address = 0xfee00000;
    static constexpr std::uint64_t virtual_address = 0xffff900000000000ULL;
    static constexpr std::uint64_t page_size = 4096;
    static constexpr std::uint64_t leaf_flags = (1ULL << 63) | 0x1b;
    static constexpr unsigned pat_index = 3;

    [[nodiscard]] static auto authorize(const ApWorkerTopology &topology,
                                        const PmTimerAdmission &timer,
                                        std::span<const std::byte> map,
                                        std::size_t stride,
                                        std::uint32_t version,
                                        std::uint64_t arena,
                                        std::uint64_t kernel_root,
                                        unsigned physical_bits,
                                        std::uint32_t vendor_ebx,
                                        std::uint32_t vendor_edx,
                                        std::uint32_t vendor_ecx,
                                        std::uint32_t cpuid_edx,
                                        std::uint32_t cpuid_ebx,
                                        std::uint32_t extended_edx,
                                        std::uint64_t apic_base,
                                        std::uint64_t pat) -> std::optional<ApWorkerAdmission> {
        constexpr auto required = (1U << 5) | (1U << 6) | (1U << 9) | (1U << 16); // MSR/PAE/APIC/PAT.
        constexpr auto extended_required = (1U << 20) | (1U << 29);               // NX and long mode.
        if (physical_bits < 32 || physical_bits > 52 || !RuntimeLayout::valid(arena) ||
            kernel_root != arena + Handoff::tables_offset ||
            // Explicit -cpu qemu64,vendor=GenuineIntel emulator contract. This
            // is not an Intel hardware qualification or an AMD startup claim.
            vendor_ebx != 0x756e6547U || vendor_edx != 0x49656e69U || vendor_ecx != 0x6c65746eU ||
            (cpuid_edx & required) != required || ((cpuid_ebx >> 16) & 255) != 2 ||
            (extended_edx & extended_required) != extended_required || topology.apic() != physical_address ||
            apic_base != (physical_address | 0x900) || ((pat >> (pat_index * 8)) & 255) != 0 ||
            // QEMU's actual PM counter wraps at 24 bits. A claimed 32-bit
            // counter would make that wrap look like a long elapsed delay.
            timer.counter_bits() != 24)
            return std::nullopt;
        const auto limit = 1ULL << physical_bits;
        if (physical_address > limit - page_size || arena > limit - Handoff::arena_bytes ||
            (arena < physical_address + page_size && physical_address < arena + Handoff::arena_bytes) ||
            !MemoryMap{map, stride, version}.owns(arena, Handoff::arena_bytes))
            return std::nullopt;
        const auto bsp_id = cpuid_ebx >> 24;
        const auto cpus = topology.processors();
        const bool first_bsp = cpus[0].id == bsp_id, second_bsp = cpus[1].id == bsp_id;
        if (first_bsp == second_bsp)
            return std::nullopt;
        for (std::size_t at = 0; at < map.size(); at += stride) {
            const Bytes descriptor{map.subspan(at, stride)};
            const auto begin = descriptor.get(8), end = begin + descriptor.get(24) * page_size;
            if (end > limit)
                return std::nullopt;
            if (begin >= physical_address + page_size || end <= physical_address)
                continue;
            const auto type = descriptor.get(0, 4), attributes = descriptor.get(32);
            // q35 may omit a LAPIC descriptor. Any described overlap must be
            // reserved/MMIO with UC/XP only, never RAM, runtime, or another cache policy.
            if ((type != 0 && type != 11) || (attributes & ~(1ULL | 0x4000ULL)))
                return std::nullopt;
        }
        return ApWorkerAdmission{arena, kernel_root, physical_bits, bsp_id, cpus[first_bsp ? 1 : 0].id, timer};
    }
    [[nodiscard]] constexpr auto owned_arena() const -> std::uint64_t {
        return arena_;
    }
    [[nodiscard]] constexpr auto kernel_root() const -> std::uint64_t {
        return root_;
    }
    [[nodiscard]] constexpr auto physical_bits() const -> unsigned {
        return physical_bits_;
    }
    [[nodiscard]] constexpr auto bsp_id() const -> std::uint32_t {
        return bsp_id_;
    }
    [[nodiscard]] constexpr auto ap_id() const -> std::uint32_t {
        return ap_id_;
    }
    [[nodiscard]] constexpr auto pm_timer() const -> const PmTimerAdmission & {
        return timer_;
    }
    [[nodiscard]] constexpr auto
    admits(std::uint64_t va, std::uint64_t pa, std::uint64_t bytes, std::uint64_t flags) const -> bool {
        return va == virtual_address && pa == physical_address && bytes == page_size && flags == leaf_flags;
    }
    [[nodiscard]] constexpr auto mapping(std::uint64_t va) const -> std::uint64_t {
        return va == virtual_address ? physical_address | leaf_flags : 0;
    }
    [[nodiscard]] constexpr auto matches_registers(std::uint32_t id, std::uint32_t version) const -> bool {
        const auto revision = version & 255, max_lvt = (version >> 16) & 255;
        return id == (bsp_id_ << 24) && (version & ~0x01ff00ffU) == 0 && revision >= 0x10 && revision <= 0x15 &&
               max_lvt >= 5 && max_lvt <= 6;
    }
};
} // namespace aurora::uefi
