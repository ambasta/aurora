#pragma once
#include "bar-policy.hpp"
namespace aurora::uefi {
// Independent firmware facts. Neither an IVRS record nor requester coverage is
// permission to access registers, create translations, enable BME, or perform DMA.
class IvrsUnit final {
    friend class Ivrs;
    std::uint16_t segment_{}, device_id_{}, capability_offset_{};
    std::uint64_t base_{};

public:
    [[nodiscard]] auto segment() const -> unsigned {
        return segment_;
    }
    [[nodiscard]] auto device_id() const -> unsigned {
        return device_id_;
    }
    [[nodiscard]] auto capability_offset() const -> unsigned {
        return capability_offset_;
    }
    [[nodiscard]] auto base() const -> std::uint64_t {
        return base_;
    }
    [[nodiscard]] auto length() const -> std::uint64_t {
        return 0x4000;
    }
    [[nodiscard]] auto flags10() const -> unsigned {
        return 0xd1;
    }
    [[nodiscard]] auto flags11() const -> unsigned {
        return 0x11;
    }
    [[nodiscard]] auto feature10() const -> std::uint32_t {
        return 0x44;
    }
    [[nodiscard]] auto attributes() const -> std::uint32_t {
        return 0;
    }
    [[nodiscard]] auto efr() const -> std::uint64_t {
        return 0x29d3;
    }
};
class Ivrs final {
    IvrsUnit unit_{};
    std::array<std::uint16_t, 256> requesters_{};
    std::size_t requester_count_{};
    unsigned physical_bits_{};
    Ivrs() = default;

public:
    static constexpr std::size_t maximum_requesters = 256, maximum_records = 2;
    static constexpr std::size_t maximum_table = 48 + 24 + 40 + maximum_requesters * 8;
    [[nodiscard]] auto count() const -> std::size_t {
        return 1;
    }
    [[nodiscard]] auto record_count() const -> std::size_t {
        return 2;
    }
    [[nodiscard]] auto info() const -> std::uint32_t {
        return 0x2801;
    }
    [[nodiscard]] auto physical_bits() const -> unsigned {
        return physical_bits_;
    }
    [[nodiscard]] auto unit() const -> const IvrsUnit & {
        return unit_;
    }
    [[nodiscard]] auto requesters() const -> std::span<const std::uint16_t> {
        return {requesters_.data(), requester_count_};
    }
    [[nodiscard]] auto covers(unsigned segment, unsigned bus, unsigned device, unsigned function) const -> bool {
        if (segment != unit_.segment() || bus > 255 || device > 31 || function > 7)
            return false;
        const auto id = (bus << 8) | (device << 3) | function;
        for (auto requester : requesters())
            if (requester == id)
                return true;
        return false;
    }
    // Scope equality is stronger than merely finding the chosen endpoint. This
    // catches missing, extra and duplicate inventory entries and scopes. The
    // caller supplies the complete independent PCI inventory, not a subset.
    [[nodiscard]] auto matches_inventory(std::span<const PciFunction> functions,
                                         unsigned segment,
                                         unsigned bus,
                                         unsigned device,
                                         unsigned function) const -> bool {
        if (functions.size() != requester_count_ || !covers(segment, bus, device, function))
            return false;
        bool found_unit = false;
        for (std::size_t i = 0; i < functions.size(); ++i) {
            const auto &candidate = functions[i];
            if (!covers(candidate.segment, candidate.bus, candidate.device, candidate.function))
                return false;
            const auto id = (static_cast<unsigned>(candidate.bus) << 8) |
                            (static_cast<unsigned>(candidate.device) << 3) | candidate.function;
            for (std::size_t j = 0; j < i; ++j) {
                const auto &previous = functions[j];
                if (candidate.segment == previous.segment && candidate.bus == previous.bus &&
                    candidate.device == previous.device && candidate.function == previous.function)
                    return false;
            }
            if (id == unit_.device_id()) {
                if (candidate.vendor != 0x1022 || candidate.device_id != 0x1419 || candidate.class_code != 8 ||
                    candidate.subclass != 6 || candidate.programming_interface != 0 || candidate.header_type != 0)
                    return false;
                found_unit = true;
            }
        }
        return found_unit;
    }
    // Selected only by the trusted platform build. This is the QEMU 10.0.13
    // q35 AMD-Vi profile with pt, intremap, device-iotlb and xtsup all off.
    // Producer: qemu/qemu commit 98f88efe8f07067667b8d9b1a5ce9551d34036c1,
    // hw/i386/acpi-build.c build_amd_iommu(), hw/i386/amd_iommu.{c,h}.
    // Exact feature values deliberately reject unimplemented variants, including
    // reserved bits; these constants are not general AMD hardware masks.
    // QEMU emits 0x10 and 0x11 descriptions of the SAME IOMMU. Both are required,
    // with identical identity and SELECT sets. Their different feature encodings
    // are checked against the same pinned producer profile before coalescing.
    [[nodiscard]] static auto parse_qemu_10_0_13(std::span<const std::byte> bytes, unsigned physical_bits)
        -> std::optional<Ivrs> {
        if (physical_bits < 32 || physical_bits > 52 || bytes.size() < 120 || bytes.size() > maximum_table ||
            !Acpi::table(bytes, "IVRS") || Bytes{bytes}.get(8, 1) != 1 || Bytes{bytes}.get(36, 4) != 0x2801 ||
            Bytes{bytes}.get(40) != 0)
            return std::nullopt;
        Ivrs result;
        result.physical_bits_ = physical_bits;
        unsigned seen = 0;
        for (std::size_t at = 48; at < bytes.size();) {
            if (bytes.size() - at < 4)
                return std::nullopt;
            const auto type = Bytes{bytes}.get(at, 1), length = Bytes{bytes}.get(at + 2, 2);
            // No unknown blocks are skipped: IVMD reserved-memory claims and
            // all other IVHD forms require separate supported semantics.
            if (type != 0x10 && type != 0x11)
                return std::nullopt;
            const auto header = type == 0x10 ? 24U : 40U, bit = type == 0x10 ? 1U : 2U;
            if ((seen & bit) || length < header + 4 || length > bytes.size() - at || (length - header) % 4 ||
                (length - header) / 4 > maximum_requesters)
                return std::nullopt;
            const Bytes record{bytes.subspan(at, length)};
            if (record.get(1, 1) != (type == 0x10 ? 0xd1U : 0x11U) || record.get(6, 2) != 0x40 ||
                record.get(18, 2) != 0 || record.get(20, 4) != (type == 0x10 ? 0x44U : 0U) ||
                (type == 0x11 && (record.get(24) != 0x29d3 || record.get(32) != 0)))
                return std::nullopt;
            const auto base = record.get(8);
            const auto limit = 1ULL << physical_bits;
            if (!base || base % 0x4000 || base >= limit || 0x4000 > limit - base)
                return std::nullopt;
            if (!seen) {
                result.unit_.segment_ = static_cast<std::uint16_t>(record.get(16, 2));
                result.unit_.device_id_ = static_cast<std::uint16_t>(record.get(4, 2));
                result.unit_.capability_offset_ = static_cast<std::uint16_t>(record.get(6, 2));
                result.unit_.base_ = base;
            } else if (record.get(16, 2) != result.unit_.segment() || record.get(4, 2) != result.unit_.device_id() ||
                       record.get(6, 2) != result.unit_.capability_offset() || base != result.unit_.base())
                return std::nullopt;
            std::array<std::uint16_t, maximum_requesters> scopes{};
            const auto count = static_cast<std::size_t>((length - header) / 4);
            for (std::size_t i = 0; i < count; ++i) {
                const auto offset = header + i * 4;
                // Only SELECT with zero device settings is supported. ALL,
                // START/END ranges, aliases, extended and special entries are
                // rejected rather than losing routing or interrupt semantics.
                if (record.get(offset, 1) != 2 || record.get(offset + 3, 1) != 0)
                    return std::nullopt;
                const auto id = static_cast<std::uint16_t>(record.get(offset + 1, 2));
                for (std::size_t j = 0; j < i; ++j)
                    if (scopes[j] == id)
                        return std::nullopt;
                scopes[i] = id;
            }
            if (!seen) {
                result.requester_count_ = count;
                for (std::size_t i = 0; i < count; ++i)
                    result.requesters_[i] = scopes[i];
            } else {
                if (count != result.requester_count_)
                    return std::nullopt;
                for (std::size_t i = 0; i < count; ++i) {
                    bool matched = false;
                    for (auto requester : result.requesters())
                        if (requester == scopes[i])
                            matched = true;
                    if (!matched)
                        return std::nullopt;
                }
            }
            seen |= bit;
            at += static_cast<std::size_t>(length);
        }
        if (seen != 3 || !result.covers(result.unit_.segment(),
                                        result.unit_.device_id() >> 8,
                                        (result.unit_.device_id() >> 3) & 31,
                                        result.unit_.device_id() & 7))
            return std::nullopt;
        return result;
    }
};
// Copies exactly the conventional header and [0x40,0x70) capability bytes.
// The AMD capability is 24 bytes; the rest proves the bounded conventional
// capability chain reaches it. No config address or writable view is retained.
class Q35IommuSnapshot final {
    std::array<std::byte, 64> header_{};
    std::array<std::byte, 48> capabilities_{};
    Q35IommuSnapshot() = default;

public:
    [[nodiscard]] static auto parse(unsigned segment,
                                    unsigned bus,
                                    unsigned device,
                                    unsigned function,
                                    std::span<const std::byte> header,
                                    std::span<const std::byte> capabilities) -> std::optional<Q35IommuSnapshot> {
        if (segment != 0 || bus != 0 || device != 3 || function != 0 || header.size() != 64 ||
            capabilities.size() != 48)
            return std::nullopt;
        const Bytes h{header}, c{capabilities};
        if (h.get(0, 4) != 0x14191022 || h.get(4, 2) != 7 || h.get(6, 2) != 0x10 || h.get(8, 1) != 0 ||
            h.get(9, 3) != 0x080600 || h.get(14, 1) != 0 || h.get(0x34, 1) != 0x60 || c.get(0, 4) != 0x1f03000f ||
            (c.get(4, 4) & ~1ULL) != 0xfed80000 || c.get(8, 4) != 0 || c.get(12, 4) != 0xff000000 ||
            c.get(16, 4) != 0x00182840 || c.get(20, 4) != 0 || c.get(24, 4) != 0x00004005 ||
            c.get(28, 4) != 0x00005808 || c.get(32, 4) != 0x00805c05 || c.get(36, 4) != 0 || c.get(40) != 0)
            return std::nullopt;
        // Exact supported chain: MSI -> HT -> MSI stub -> AMD. Restrict every
        // link before following it; no untrusted link can escape this snapshot.
        constexpr std::array<unsigned, 4> pointers{0x60, 0x5c, 0x58, 0x40};
        constexpr std::array<unsigned, 4> types{5, 8, 5, 15};
        auto pointer = static_cast<unsigned>(h.get(0x34, 1));
        for (std::size_t i = 0; i < pointers.size(); ++i) {
            if (pointer != pointers[i] || c.get(pointer - 0x40, 1) != types[i])
                return std::nullopt;
            pointer = static_cast<unsigned>(c.get(pointer - 0x40 + 1, 1));
        }
        if (pointer != 0)
            return std::nullopt;
        Q35IommuSnapshot result;
        for (std::size_t i = 0; i < header.size(); ++i)
            result.header_[i] = header[i];
        for (std::size_t i = 0; i < capabilities.size(); ++i)
            result.capabilities_[i] = capabilities[i];
        return result;
    }
    [[nodiscard]] auto same(const Q35IommuSnapshot &other) const -> bool {
        return header_ == other.header_ && capabilities_ == other.capabilities_;
    }
    [[nodiscard]] auto mmio_enabled() const -> bool {
        return (Bytes{capabilities_}.get(4, 4) & 1) != 0;
    }
    [[nodiscard]] auto base() const -> std::uint64_t {
        return Bytes{capabilities_}.get(4, 4) & ~1ULL;
    }
};
enum class IommuReadSource {
    ArchitecturalEnable,
    Qemu10_0_13AmdViCold
};
class Q35IommuReadPolicy final {
    Q35IommuSnapshot snapshot_;
    WindowTicket ticket_;
    IommuReadSource source_;
    Q35IommuReadPolicy(const Q35IommuSnapshot &snapshot, WindowTicket ticket, IommuReadSource source)
        : snapshot_(snapshot), ticket_(ticket), source_(source) {
    }
    [[nodiscard]] static auto overlaps(std::uint64_t other, std::uint64_t length) -> bool {
        return other < end && base < other + length;
    }
    [[nodiscard]] static auto authorize_as(const Ivrs &ivrs,
                                           const Q35IommuSnapshot &copied,
                                           const Q35IommuSnapshot &current,
                                           std::span<const std::byte> map,
                                           std::size_t stride,
                                           std::uint64_t arena,
                                           std::uint64_t apic_page,
                                           std::span<const std::optional<PciBarReservation>> reservations,
                                           const WindowAuthority &authority,
                                           WindowTicket ticket,
                                           IommuReadSource source) -> std::optional<Q35IommuReadPolicy> {
        const auto &unit = ivrs.unit();
        if (!authority.accepts(ticket) || !copied.same(current) || !MemoryMap{map, stride, 1}.valid() ||
            unit.segment() != 0 || unit.device_id() != 24 || unit.capability_offset() != 0x40 || unit.base() != base ||
            unit.length() != bytes || current.base() != base || !ivrs.covers(0, 0, 2, 0) || reservations.empty() ||
            reservations.size() > 9 || current.mmio_enabled() != (source == IommuReadSource::ArchitecturalEnable))
            return std::nullopt;
        const auto limit = 1ULL << ivrs.physical_bits();
        if (base >= limit || bytes > limit - base || arena % 4096 || arena >= limit ||
            Handoff::arena_bytes > limit - arena || !apic_page || apic_page % 4096 || apic_page >= limit ||
            4096 > limit - apic_page || overlaps(arena, Handoff::arena_bytes) || overlaps(apic_page, 4096) ||
            overlaps(Q35Ecam::base, Q35Ecam::bytes) || overlaps(0xfee00000, 4096) || overlaps(0xfec00000, 4096))
            return std::nullopt;
        for (const auto &reservation : reservations)
            if (!reservation || reservation->overlaps(base, bytes))
                return std::nullopt;
        for (std::size_t at = 0; at < map.size(); at += stride) {
            const Bytes entry{map.subspan(at, stride)};
            const auto begin = entry.get(8), after = begin + entry.get(24) * 4096;
            if (after > limit)
                return std::nullopt;
            if (begin >= end || after <= base)
                continue;
            // A described page may only be reserved or MMIO with UC, XP, RO.
            // Runtime, RAM, NV, RP, conflicting cache and unknown attributes
            // deny. Absent pages rely on the explicit fixed platform contract.
            if ((entry.get(0, 4) != 0 && entry.get(0, 4) != 11) || (entry.get(32) & ~0x24001ULL))
                return std::nullopt;
        }
        return Q35IommuReadPolicy{current, ticket, source};
    }

public:
    static constexpr std::uint64_t base = 0xfed80000, bytes = 0x4000, end = base + bytes;
    [[nodiscard]] auto source() const -> IommuReadSource {
        return source_;
    }
    // The adapter must first prove complete IVRS/inventory equality and fresh,
    // complete assigned-memory-BAR reservations, including the target NVMe BAR.
    // The span is denial evidence only; it never substitutes for BAR ownership.
    // Architectural default: cap+04h Enable=0 yields no read lease.
    [[nodiscard]] static auto authorize(const Ivrs &ivrs,
                                        const Q35IommuSnapshot &copied,
                                        const Q35IommuSnapshot &current,
                                        std::span<const std::byte> map,
                                        std::size_t stride,
                                        std::uint64_t arena,
                                        std::uint64_t apic_page,
                                        std::span<const std::optional<PciBarReservation>> reservations,
                                        const WindowAuthority &authority,
                                        WindowTicket ticket) -> std::optional<Q35IommuReadPolicy> {
        return authorize_as(ivrs,
                            copied,
                            current,
                            map,
                            stride,
                            arena,
                            apic_page,
                            reservations,
                            authority,
                            ticket,
                            IommuReadSource::ArchitecturalEnable);
    }
    // Explicit trusted profile selection, NEVER an automatic fallback. QEMU
    // 98f88efe8f07067667b8d9b1a5ce9551d34036c1 maps this 16KiB aperture
    // unconditionally although cap+04h Enable resets to zero. Physical hardware
    // must not inherit this exception. This lease admits three read addresses;
    // no config/MMIO writes, IOMMU activation or DMA authority are provided.
    [[nodiscard]] static auto
    authorize_qemu_10_0_13_cold(const Ivrs &ivrs,
                                const Q35IommuSnapshot &copied,
                                const Q35IommuSnapshot &current,
                                std::span<const std::byte> map,
                                std::size_t stride,
                                std::uint64_t arena,
                                std::uint64_t apic_page,
                                std::span<const std::optional<PciBarReservation>> reservations,
                                const WindowAuthority &authority,
                                WindowTicket ticket) -> std::optional<Q35IommuReadPolicy> {
        return authorize_as(ivrs,
                            copied,
                            current,
                            map,
                            stride,
                            arena,
                            apic_page,
                            reservations,
                            authority,
                            ticket,
                            IommuReadSource::Qemu10_0_13AmdViCold);
    }
    [[nodiscard]] auto page(const WindowAuthority &authority, std::uint64_t offset) const
        -> std::optional<std::uint64_t> {
        if (!authority.accepts(ticket_) || (offset != 0 && offset != 0x2000))
            return std::nullopt;
        return base + offset;
    }
    [[nodiscard]] auto read_address(const WindowAuthority &authority,
                                    const Q35IommuSnapshot &current,
                                    std::uint64_t offset,
                                    unsigned width) const -> std::optional<std::uint64_t> {
        if (!authority.accepts(ticket_) || !snapshot_.same(current) || width != 8 ||
            (offset != 0x18 && offset != 0x30 && offset != 0x2020))
            return std::nullopt;
        return base + offset;
    }
    [[nodiscard]] auto finish(const WindowAuthority &authority,
                              const Q35IommuSnapshot &current,
                              std::uint64_t control,
                              std::uint64_t efr,
                              std::uint64_t status) const -> bool {
        return read_address(authority, current, 0x18, 8).has_value() && control == 0 && efr == 0x29d3 && status == 0;
    }
};
static_assert(sizeof(Ivrs) < 1024);
static_assert(sizeof(Q35IommuReadPolicy) < 160);
} // namespace aurora::uefi
