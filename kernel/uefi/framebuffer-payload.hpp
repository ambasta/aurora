#pragma once
#include "tables.hpp"

namespace aurora::uefi {
// Closed trusted restoration adapter. Ordinary record decoding returns only a
// description. This path re-establishes its exact machine/owned-RO origin before
// constructing the source-bound resource, with no framebuffer leaves present.
class FramebufferPayload final {
    using U64 = std::uint64_t;
    static auto view(U64 address, std::size_t size) -> std::span<const std::byte> {
        return {reinterpret_cast<const std::byte *>(address), size};
    }

public:
    // corrupt_record is the capture fixture's controlled record negative.
    [[nodiscard]] static auto restore_fixture(U64 arena, [[maybe_unused]] bool corrupt_record = false)
        -> std::optional<FramebufferAdmission> {
        if (!RuntimeLayout::valid(arena))
            return std::nullopt;
        U64 root, cr0, cr4, flags, stack;
        asm volatile("mov %%cr3,%0; mov %%cr0,%1; mov %%cr4,%2; pushfq; pop %3; mov %%rsp,%4"
                     : "=r"(root), "=r"(cr0), "=r"(cr4), "=r"(flags), "=r"(stack));
        if (root != arena + Handoff::tables_offset || !(cr0 & (1ULL << 16)) || (flags & 0x200) ||
            (cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 17))) || stack < arena + Handoff::stack_bottom ||
            stack >= arena + Handoff::stack_top)
            return std::nullopt;
        const auto header = view(arena, Handoff::header);
        if (!Handoff::valid(header, arena))
            return std::nullopt;
        const Bytes h{header};
        if (h.get(8, 4) != 5 || h.get(88) != root || h.get(120) != arena + Handoff::framebuffer_record_offset)
            return std::nullopt;
        const PageTables tables{root, static_cast<std::size_t>(h.get(96))};
        if (!tables.verify(arena, h) || (tables.entry(arena + Handoff::framebuffer_record_offset) & ~0x60ULL) !=
                                            ((arena + Handoff::framebuffer_record_offset) | 0x8000000000000001ULL))
            return std::nullopt;
        std::uint32_t a, b, c, d;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000000U), "c"(0));
        if (a < 0x80000008U)
            return std::nullopt;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
        const auto physical_bits = a & 255;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1U), "c"(0));
        const auto features = d;
        if ((features & ((1U << 5) | (1U << 16))) != ((1U << 5) | (1U << 16)))
            return std::nullopt;
        std::uint32_t low, high;
        asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0xc0000080));
        if (!(low & (1U << 11)))
            return std::nullopt;
        asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0x277));
        const U64 pat = (U64{high} << 32) | low;
        std::array<std::byte, FramebufferRecord::bytes> record{};
        const auto source = view(arena + Handoff::framebuffer_record_offset, record.size());
        for (std::size_t index = 0; index < record.size(); ++index)
            record[index] = source[index];
        // Controlled negative after the capture gate. Corrupt only the local
        // copied record; the owned RO page and CR0.WP remain unchanged.
        if (corrupt_record)
            record[56] = std::byte{1};
        const auto copied = FramebufferRecord::parse(record, physical_bits);
        if (!copied)
            return std::nullopt;
        const FramebufferResource resource{*copied};
        return FramebufferAdmission::authorize_q35_ovmf_std_vga_fixture(resource,
                                                                        view(arena + Handoff::map_offset, h.get(32)),
                                                                        h.get(40),
                                                                        static_cast<std::uint32_t>(h.get(48, 4)),
                                                                        arena,
                                                                        physical_bits,
                                                                        features,
                                                                        pat);
    }
    // Explicitly selected combined-profile restoration. Keep restore_fixture's
    // v5 entry, negative mode and proof identity unchanged. A v6 record is only
    // a description: current owned root/stack, WP, the immutable record page and
    // the complete empty-device tree are re-established before token creation.
    [[nodiscard]] static auto restore_graphical_fixture(U64 arena) -> std::optional<FramebufferAdmission> {
        if (!RuntimeLayout::valid(arena))
            return std::nullopt;
        U64 root, cr0, cr4, flags, stack;
        asm volatile("mov %%cr3,%0; mov %%cr0,%1; mov %%cr4,%2; pushfq; pop %3; mov %%rsp,%4"
                     : "=r"(root), "=r"(cr0), "=r"(cr4), "=r"(flags), "=r"(stack));
        if (root != arena + Handoff::tables_offset || !(cr0 & (1ULL << 16)) || (flags & 0x200) ||
            (cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 17))) || stack < arena + Handoff::stack_bottom ||
            stack >= arena + Handoff::stack_top)
            return std::nullopt;
        const auto header = view(arena, Handoff::header);
        if (!Handoff::valid(header, arena))
            return std::nullopt;
        const Bytes h{header};
        if (h.get(8, 4) != 6 || !h.get(112) || h.get(88) != root ||
            h.get(120) != arena + Handoff::framebuffer_record_offset)
            return std::nullopt;
        const PageTables tables{root, static_cast<std::size_t>(h.get(96))};
        if (!tables.verify(arena, h) || !tables.window_slot() || !tables.interrupt_slot() ||
            tables.entry(PageTables::window_address) || tables.entry(LocalApicAdmission::virtual_address) ||
            (tables.entry(arena + Handoff::framebuffer_record_offset) & ~0x60ULL) !=
                ((arena + Handoff::framebuffer_record_offset) | 0x8000000000000001ULL))
            return std::nullopt;
        std::uint32_t a, b, c, d;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000000U), "c"(0));
        if (a < 0x80000008U)
            return std::nullopt;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
        const auto physical_bits = a & 255;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1U), "c"(0));
        const auto features = d;
        if ((features & ((1U << 5) | (1U << 16))) != ((1U << 5) | (1U << 16)))
            return std::nullopt;
        std::uint32_t low, high;
        asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0xc0000080));
        if (!(low & (1U << 11)))
            return std::nullopt;
        asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0x277));
        const U64 pat = (U64{high} << 32) | low;
        std::array<std::byte, FramebufferRecord::bytes> record{};
        const auto source = view(arena + Handoff::framebuffer_record_offset, record.size());
        for (std::size_t index = 0; index < record.size(); ++index)
            record[index] = source[index];
        const auto copied = FramebufferRecord::parse(record, physical_bits);
        if (!copied)
            return std::nullopt;
        const FramebufferResource resource{*copied};
        return FramebufferAdmission::authorize_q35_ovmf_std_vga_fixture(resource,
                                                                        view(arena + Handoff::map_offset, h.get(32)),
                                                                        h.get(40),
                                                                        static_cast<std::uint32_t>(h.get(48, 4)),
                                                                        arena,
                                                                        physical_bits,
                                                                        features,
                                                                        pat);
    }
#ifdef AURORA_UEFI_GRAPHICAL_TERMINAL
    // Production restoration. A v7 record is only a description: the current
    // owned root/stack, WP, NXE, the immutable record page and the complete tree
    // (owned arena plus exactly the admitted LAPIC leaf, no framebuffer leaf
    // yet) are re-established before the firmware rule rebuilds the token.
    [[nodiscard]] static auto restore_terminal(U64 arena, const LocalApicAdmission &apic)
        -> std::optional<FramebufferAdmission> {
        if (!RuntimeLayout::valid(arena) || apic.owned_arena() != arena)
            return std::nullopt;
        U64 root, cr0, cr4, flags, stack;
        asm volatile("mov %%cr3,%0; mov %%cr0,%1; mov %%cr4,%2; pushfq; pop %3; mov %%rsp,%4"
                     : "=r"(root), "=r"(cr0), "=r"(cr4), "=r"(flags), "=r"(stack));
        if (root != arena + Handoff::tables_offset || !(cr0 & (1ULL << 16)) || (flags & 0x200) ||
            (cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 17))) || stack < arena + Handoff::stack_bottom ||
            stack >= arena + Handoff::stack_top)
            return std::nullopt;
        const auto header = view(arena, Handoff::header);
        if (!Handoff::valid(header, arena))
            return std::nullopt;
        const Bytes h{header};
        if (h.get(8, 4) != 7 || !h.get(112) || h.get(88) != root ||
            h.get(120) != arena + RuntimeLayout::metadata_offset ||
            h.get(Handoff::framebuffer_word) != arena + Handoff::framebuffer_record_offset)
            return std::nullopt;
        const PageTables tables{root, static_cast<std::size_t>(h.get(96))};
        if (!tables.verify(arena, h, &apic) || !tables.window_slot() || !tables.interrupt_slot() ||
            tables.entry(PageTables::window_address) ||
            (tables.entry(LocalApicAdmission::virtual_address) & ~0x60ULL) !=
                apic.mapping(LocalApicAdmission::virtual_address) ||
            tables.entry(FramebufferAdmission::virtual_address - 4096) ||
            (tables.entry(arena + Handoff::framebuffer_record_offset) & ~0x60ULL) !=
                ((arena + Handoff::framebuffer_record_offset) | 0x8000000000000001ULL))
            return std::nullopt;
        std::uint32_t a, b, c, d;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000000U), "c"(0));
        if (a < 0x80000008U)
            return std::nullopt;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
        const auto physical_bits = a & 255;
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1U), "c"(0));
        const auto features = d;
        if ((features & ((1U << 5) | (1U << 16))) != ((1U << 5) | (1U << 16)))
            return std::nullopt;
        std::uint32_t low, high;
        asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0xc0000080));
        if (!(low & (1U << 11)))
            return std::nullopt;
        asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0x277));
        const U64 pat = (U64{high} << 32) | low;
        std::array<std::byte, FramebufferRecord::bytes> record{};
        const auto source = view(arena + Handoff::framebuffer_record_offset, record.size());
        for (std::size_t index = 0; index < record.size(); ++index)
            record[index] = source[index];
        const auto copied = FramebufferRecord::parse(record, physical_bits);
        if (!copied)
            return std::nullopt;
        const FramebufferResource resource{*copied};
        const auto admitted = FramebufferAdmission::authorize_firmware(resource,
                                                                       view(arena + Handoff::map_offset, h.get(32)),
                                                                       h.get(40),
                                                                       static_cast<std::uint32_t>(h.get(48, 4)),
                                                                       arena,
                                                                       physical_bits,
                                                                       features,
                                                                       pat);
        // No leaf may exist anywhere in the reserved framebuffer window yet.
        if (!admitted)
            return std::nullopt;
        for (U64 offset = 0; offset <= admitted->geometry().mapped_bytes(); offset += 4096)
            if (tables.entry(FramebufferAdmission::virtual_address + offset))
                return std::nullopt;
        return admitted;
    }
#endif
};
} // namespace aurora::uefi
