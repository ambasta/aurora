#pragma once
#include "bar-policy.hpp"

namespace aurora::uefi {
// Copied facts only. The readers own their completeness, acquisition order and
// freshness. None of these aggregates grants MMIO, BME or DMA authority.
class EventPciFact final {
public:
    std::uint16_t segment{};
    std::uint8_t bus{}, device{}, function{};
    std::array<std::byte, 64> header{};
    [[nodiscard]] auto requester() const -> unsigned {
        return (static_cast<unsigned>(bus) << 8) | (static_cast<unsigned>(device) << 3) | function;
    }
    [[nodiscard]] auto same(const EventPciFact &other) const -> bool {
        return segment == other.segment && bus == other.bus && device == other.device && function == other.function &&
               header == other.header;
    }
};

class EventBarFact final {
public:
    std::uint16_t requester{};
    unsigned index{};
    std::array<std::byte, 48> descriptor{};
};

class EventIvrsUnit final {
    friend class EventIvrs;
    std::uint16_t requester_{};

public:
    [[nodiscard]] auto device_id() const -> unsigned {
        return requester_;
    }
    [[nodiscard]] auto segment() const -> unsigned {
        return 0;
    }
    [[nodiscard]] auto capability_offset() const -> unsigned {
        return 0x40;
    }
    [[nodiscard]] auto base() const -> std::uint64_t {
        return 0xfed80000;
    }
    [[nodiscard]] auto length() const -> std::uint64_t {
        return 0x4000;
    }
    [[nodiscard]] auto efr() const -> std::uint64_t {
        return 0x29d3;
    }
};

// Deliberately separate from historical SELECT-only Ivrs. This parser describes
// precisely the retained event-permissions-command-stop-v1 QEMU producer, with
// default AMD-Vi options under TCG. It makes no interrupt-delivery claim.
class EventIvrs final {
    EventIvrsUnit unit_{};
    std::array<std::uint16_t, 6> requesters_{};
    unsigned physical_bits_{};
    EventIvrs() = default;

public:
    static constexpr std::size_t maximum_requesters = 6;
    static constexpr std::size_t maximum_table = 176;
    static constexpr unsigned ioapic_requester = 0xa0;
    [[nodiscard]] auto unit() const -> const EventIvrsUnit & {
        return unit_;
    }
    [[nodiscard]] auto physical_bits() const -> unsigned {
        return physical_bits_;
    }
    [[nodiscard]] auto requesters() const -> std::span<const std::uint16_t> {
        return requesters_;
    }
    [[nodiscard]] auto covers(unsigned segment, unsigned bus, unsigned device, unsigned function) const -> bool {
        if (segment != 0 || bus != 0 || device > 31 || function > 7)
            return false;
        for (auto requester : requesters_)
            if (requester == ((device << 3) | function))
                return true;
        return false;
    }
    [[nodiscard]] static auto parse_qemu_default(std::span<const std::byte> bytes, unsigned physical_bits)
        -> std::optional<EventIvrs> {
        if (physical_bits < 32 || physical_bits > 52 || bytes.size() != maximum_table || !Acpi::table(bytes, "IVRS") ||
            Bytes{bytes}.get(8, 1) != 1 || Bytes{bytes}.get(36, 4) != 0x2801 || Bytes{bytes}.get(40) != 0)
            return std::nullopt;
        EventIvrs result;
        result.physical_bits_ = physical_bits;
        std::size_t at = 48;
        for (unsigned record_index = 0; record_index < 2; ++record_index) {
            const unsigned header_size = record_index == 0 ? 24 : 40;
            const unsigned length = header_size + maximum_requesters * 4 + 8;
            const Bytes record{bytes.subspan(at, length)};
            if (record.get(0, 1) != (record_index == 0 ? 0x10U : 0x11U) ||
                record.get(1, 1) != (record_index == 0 ? 0xd1U : 0x11U) || record.get(2, 2) != length ||
                record.get(6, 2) != 0x40 || record.get(8) != 0xfed80000 || record.get(16, 4) != 0 ||
                record.get(20, 4) != (record_index == 0 ? 0x44U : 0U) ||
                (record_index == 1 && (record.get(24) != 0x29d3 || record.get(32) != 0)))
                return std::nullopt;
            const auto unit = record.get(4, 2);
            if (unit > 255 || (unit & 7) || unit == 0 || unit == 0x20 || unit == ioapic_requester || unit >= 0xf8)
                return std::nullopt;
            if (record_index == 0)
                result.unit_.requester_ = static_cast<std::uint16_t>(unit);
            else if (unit != result.unit_.device_id())
                return std::nullopt;
            for (unsigned i = 0; i < maximum_requesters; ++i) {
                const auto offset = header_size + i * 4;
                const auto requester = record.get(offset + 1, 2);
                if (record.get(offset, 1) != 2 || record.get(offset + 3, 1) != 0 || requester > 255 ||
                    requester == ioapic_requester || (i != 0 && requester <= result.requesters_[i - 1]))
                    return std::nullopt;
                if (record_index == 0)
                    result.requesters_[i] = static_cast<std::uint16_t>(requester);
                else if (requester != result.requesters_[i])
                    return std::nullopt;
            }
            // acpi-build.c build_amd_iommu(): (1ULL<<56) | (0xa0ULL<<40) | 0x48.
            // Exact wire bytes: 48 00 00 00 00 a0 00 01. Reserved fields, handle,
            // variety and synthetic southbridge requester are all checked.
            if (record.get(header_size + maximum_requesters * 4) != 0x0100a00000000048ULL)
                return std::nullopt;
            at += length;
        }
        if (!result.covers(0, 0, result.unit_.device_id() >> 3, 0))
            return std::nullopt;
        for (unsigned requester : {0U, 0x20U, 0xf8U, 0xfaU, 0xfbU})
            if (!result.covers(0, 0, requester >> 3, requester & 7))
                return std::nullopt;
        return result;
    }
};

// One bootstrap translation unit owns the parser body. Hosted policy tests keep
// the inline implementation; the image avoids different discarded COMDAT copies.
[[nodiscard]] auto read_event_ivrs(std::span<const std::byte> bytes, unsigned bits) -> std::optional<EventIvrs>;

class EventAhciPortFact final {
public:
    std::uint32_t command{}, command_issue{}, sata_active{}, task_file{};
    std::uint64_t command_list{}, received_fis{};
    [[nodiscard]] auto operator==(const EventAhciPortFact &) const -> bool = default;
};
class EventAhciFacts final {
public:
    std::uint64_t base{};
    std::uint32_t capability{}, global_control{}, implemented_ports{};
    std::array<EventAhciPortFact, 6> ports{};
    [[nodiscard]] auto operator==(const EventAhciFacts &) const -> bool = default;
    template <bool detailed, class Reader>
    [[nodiscard]] static auto sample(std::uint64_t base, Reader &&read) -> EventAhciFacts {
        EventAhciFacts result;
        result.base = base;
        result.capability = read(0);
        result.global_control = read(4);
        result.implemented_ports = read(12);
        for (unsigned port = 0; port < result.ports.size(); ++port) {
            auto &fact = result.ports[port];
            const auto at = 0x100 + port * 0x80;
            fact.command = read(at + 0x18);
            fact.sata_active = read(at + 0x34);
            fact.command_issue = read(at + 0x38);
            if constexpr (detailed) {
                fact.task_file = read(at + 0x20);
                const auto clb = read(at), clbu = read(at + 4);
                const auto fb = read(at + 8), fbu = read(at + 12);
                fact.command_list = std::uint64_t{clb} | (std::uint64_t{clbu} << 32);
                fact.received_fis = std::uint64_t{fb} | (std::uint64_t{fbu} << 32);
            }
        }
        return result;
    }
    [[nodiscard]] auto quiescent(std::uint64_t admitted_base) const -> bool {
        // Retained QEMU ahci_reg_init(): six ports, 32 command slots, Gen1,
        // AHCI-only, NCQ and 64-bit DMA. The reader obtains every port, including
        // unattached ones. No stop/reset is attempted when firmware left it busy.
        if (base != admitted_base || !base || capability != 0xc0141f05 || implemented_ports != 0x3f ||
            global_control != 0x80000000)
            return false;
        for (const auto &port : ports)
            if ((port.command & 0xc011U) || port.command_issue != 0 || port.sata_active != 0)
                return false;
        return true;
    }
};

// Resource admission precedes AHCI register reads. A successful object is only
// bounded platform/resource evidence; EventAdmission additionally needs idle
// boot-controller facts before the fixture may be considered for activation.
class EventResources final {
    friend class EventAdmission;
    std::uint64_t edu_base_{}, ahci_base_{};
    unsigned physical_bits_{}, iommu_requester_{}, edu_command_{};
    bool observation_only_{};
    EventResources() = default;
    [[nodiscard]] static auto overlaps(std::uint64_t a, std::uint64_t n, std::uint64_t b, std::uint64_t m) -> bool {
        return !n || !m || n > ~std::uint64_t{0} - a || m > ~std::uint64_t{0} - b || (a < b + m && b < a + n);
    }
    [[nodiscard]] static auto iommu_capabilities(std::span<const std::byte> bytes) -> bool {
        if (bytes.size() != 48)
            return false;
        const Bytes caps{bytes};
        return caps.get(0, 4) == 0x1f03000f && caps.get(4, 4) == 0xfed80000 && caps.get(8, 4) == 0 &&
               caps.get(12, 4) == 0xff000000 && caps.get(16, 4) == 0x00182840 && caps.get(20, 4) == 0 &&
               caps.get(24, 4) == 0x00004005 && caps.get(28, 4) == 0x00005808 && caps.get(32, 4) == 0x00805c05 &&
               caps.get(36, 4) == 0 && caps.get(40) == 0;
    }
    [[nodiscard]] static auto identity(const EventPciFact &fact, unsigned iommu, bool observation_only) -> bool {
        const Bytes h{fact.header};
        const auto requester = fact.requester();
        if (fact.segment || fact.bus || fact.device > 31 || fact.function > 7 || (h.get(14, 1) & 0x7f) ||
            (h.get(4, 2) & 0xf800) || h.get(0x30, 4) != 0)
            return false;
        // Exact default Q35 identities; no optional devices or downstream buses.
        if (requester == iommu)
            return h.get(0, 4) == 0x14191022 && h.get(4, 2) == 7 && h.get(6, 2) == 0x10 && h.get(8, 4) == 0x08060000 &&
                   h.get(14, 1) == 0 && h.get(0x34, 1) == 0x60;
        if (!observation_only && (h.get(4, 2) & 4))
            return false;
        if (requester == 0)
            return h.get(0, 4) == 0x29c08086 && h.get(8, 4) == 0x06000000;
        if (requester == 0x20)
            return h.get(0, 4) == 0x11e81234 && h.get(8, 4) == 0x00ff0010 && h.get(14, 1) == 0 &&
                   (h.get(4, 2) == 2 || (observation_only && h.get(4, 2) == 7)) && (h.get(16, 4) & 15) == 0 &&
                   h.get(16, 4) != 0;
        if (requester == 0xf8)
            return h.get(0, 4) == 0x29188086 && h.get(8, 4) == 0x06010002;
        if (requester == 0xfa)
            return h.get(0, 4) == 0x29228086 && h.get(8, 4) == 0x01060102 && (h.get(4, 2) & 2);
        return requester == 0xfb && h.get(0, 4) == 0x29308086 && h.get(8, 4) == 0x0c050002;
    }

public:
    // Observation may describe inherited BME but cannot mint EventAdmission.
    enum class Purpose {
        admission,
        read_only_observation
    };
    static constexpr std::size_t maximum_functions = 6, maximum_bars = 8;
    [[nodiscard]] auto edu_base() const -> std::uint64_t {
        return edu_base_;
    }
    [[nodiscard]] auto ahci_base() const -> std::uint64_t {
        return ahci_base_;
    }
    [[nodiscard]] auto iommu_base() const -> std::uint64_t {
        return 0xfed80000;
    }
    [[nodiscard]] auto edu_config_address() const -> std::uint64_t {
        return Q35Ecam::base + 0x20000;
    }
    [[nodiscard]] auto edu_initial_command() const -> unsigned {
        return edu_command_;
    }
    [[nodiscard]] auto physical_bits() const -> unsigned {
        return physical_bits_;
    }
    [[nodiscard]] auto iommu_device_id() const -> unsigned {
        return iommu_requester_;
    }

    [[nodiscard]] static auto admit_qemu_default(const EventIvrs &ivrs,
                                                 std::span<const EventPciFact> copied,
                                                 std::span<const EventPciFact> current,
                                                 std::span<const std::byte> copied_caps,
                                                 std::span<const std::byte> current_caps,
                                                 std::span<const EventBarFact> bars,
                                                 const PciResources &root,
                                                 unsigned root_segment,
                                                 std::span<const std::byte> map,
                                                 std::size_t stride,
                                                 std::uint64_t arena,
                                                 std::uint64_t apic,
                                                 Purpose purpose = Purpose::admission)
        -> std::optional<EventResources> {
        if (copied.size() != maximum_functions || current.size() != maximum_functions || bars.empty() ||
            bars.size() > maximum_bars || root_segment != 0 || root.physical_bits() != ivrs.physical_bits() ||
            root.source() != PciResourceSource::Edk2Stable202502Root || !MemoryMap{map, stride, 1}.valid() ||
            !iommu_capabilities(copied_caps) || !iommu_capabilities(current_caps))
            return std::nullopt;
        const auto limit = std::uint64_t{1} << ivrs.physical_bits();
        if (!arena || arena % 4096 || arena >= limit || Handoff::arena_bytes > limit - arena || !apic || apic % 4096 ||
            apic >= limit || 4096 > limit - apic)
            return std::nullopt;
        EventResources result;
        result.observation_only_ = purpose == Purpose::read_only_observation;
        result.physical_bits_ = ivrs.physical_bits();
        result.iommu_requester_ = ivrs.unit().device_id();
        std::array<bool, maximum_bars> seen{};
        std::array<std::optional<PciBarReservation>, maximum_bars> ranges{};
        unsigned consumed = 0;
        for (std::size_t i = 0; i < current.size(); ++i) {
            const auto &now = current[i];
            if (!identity(now, result.iommu_requester_, result.observation_only_) ||
                !ivrs.covers(now.segment, now.bus, now.device, now.function))
                return std::nullopt;
            for (std::size_t j = 0; j < i; ++j)
                if (current[j].requester() == now.requester())
                    return std::nullopt;
            bool matched = false;
            for (const auto &prior : copied) {
                if (!prior.same(now))
                    continue;
                if (matched)
                    return std::nullopt;
                matched = true;
            }
            if (!matched)
                return std::nullopt;
            const auto snapshot = PciBarSnapshot::parse(now.segment, now.bus, now.device, now.function, now.header);
            if (!snapshot)
                return std::nullopt;
            const Bytes header{now.header};
            if (now.requester() == 0x20)
                result.edu_command_ = static_cast<unsigned>(header.get(4, 2));
            for (unsigned slot = 0; slot < 6; ++slot) {
                const auto low = header.get(16 + slot * 4, 4);
                if (!low || (low & 1))
                    continue;
                // This exact topology has only two memory BARs, both 32-bit and
                // non-prefetchable. No size probing or 64-bit upper-half guesses.
                const bool edu = now.requester() == 0x20 && slot == 0;
                const bool ahci = now.requester() == 0xfa && slot == 5;
                if ((!edu && !ahci) || (low & 15))
                    return std::nullopt;
                unsigned bar_matches = 0;
                for (std::size_t index = 0; index < bars.size(); ++index) {
                    const auto &bar = bars[index];
                    if (bar.requester != now.requester() || bar.index != slot)
                        continue;
                    if (++bar_matches != 1 || seen[index])
                        return std::nullopt;
                    const auto range =
                        PciBarReservation::parse_edk2(*snapshot, *snapshot, slot, bar.descriptor, ivrs.physical_bits());
                    if (!range || range->length() != (edu ? 0x100000U : 0x1000U))
                        return std::nullopt;
                    ranges[index] = range;
                    seen[index] = true;
                    ++consumed;
                    if (edu)
                        result.edu_base_ = range->begin();
                    else
                        result.ahci_base_ = range->begin();
                }
                if (bar_matches != 1)
                    return std::nullopt;
            }
        }
        if (consumed != bars.size() || consumed != 2 || !result.edu_base_ || !result.ahci_base_)
            return std::nullopt;
        unsigned buses = 0;
        for (const auto &resource : root.resources())
            if (resource.type() == 2 && resource.contains(0, 1))
                ++buses;
        if (buses != 1)
            return std::nullopt;
        for (std::size_t index = 0; index < bars.size(); ++index) {
            const auto &range = *ranges[index];
            unsigned windows = 0;
            for (const auto &resource : root.resources()) {
                if (resource.type() == 0 && resource.contains(range.begin(), range.length())) {
                    if (resource.specific() != 0)
                        return std::nullopt;
                    ++windows;
                }
            }
            if (windows != 1)
                return std::nullopt;
            for (std::size_t other = 0; other < index; ++other)
                if (range.overlaps(ranges[other]->begin(), ranges[other]->length()))
                    return std::nullopt;
            if (range.overlaps(0xfed80000, 0x4000))
                return std::nullopt;
        }
        // Validate full apertures, including the pages the fixture never maps.
        for (unsigned index = 0; index < 3; ++index) {
            const auto begin = index == 0 ? result.edu_base_ : index == 1 ? result.ahci_base_ : 0xfed80000ULL;
            const auto length = index == 0 ? 0x100000ULL : index == 1 ? 0x1000ULL : 0x4000ULL;
            if (begin >= limit || length > limit - begin || overlaps(begin, length, arena, Handoff::arena_bytes) ||
                overlaps(begin, length, apic, 4096) || overlaps(begin, length, Q35Ecam::base, Q35Ecam::bytes) ||
                overlaps(begin, length, 0xfec00000, 4096) || overlaps(begin, length, 0xfee00000, 4096))
                return std::nullopt;
            for (std::size_t at = 0; at < map.size(); at += stride) {
                const Bytes entry{map.subspan(at, stride)};
                const auto start = entry.get(8), bytes = entry.get(24) * 4096;
                if (start >= limit || bytes > limit - start)
                    return std::nullopt;
                if (!overlaps(begin, length, start, bytes))
                    continue;
                if ((entry.get(0, 4) != 0 && entry.get(0, 4) != 11) || (entry.get(32) & ~0x24001ULL))
                    return std::nullopt;
            }
        }
        return result;
    }
};

class EventAdmission final {
    EventResources resources_;
    explicit EventAdmission(const EventResources &resources) : resources_(resources) {
    }

public:
    [[nodiscard]] static auto admit(const EventResources &resources, const EventAhciFacts &ahci)
        -> std::optional<EventAdmission> {
        if (resources.observation_only_ || !ahci.quiescent(resources.ahci_base()))
            return std::nullopt;
        return EventAdmission{resources};
    }
    [[nodiscard]] auto edu_base() const -> std::uint64_t {
        return resources_.edu_base();
    }
    [[nodiscard]] auto iommu_base() const -> std::uint64_t {
        return resources_.iommu_base();
    }
    [[nodiscard]] auto edu_config_address() const -> std::uint64_t {
        return resources_.edu_config_address();
    }
    [[nodiscard]] auto edu_initial_command() const -> unsigned {
        return resources_.edu_initial_command();
    }
    [[nodiscard]] auto physical_bits() const -> unsigned {
        return resources_.physical_bits();
    }
    [[nodiscard]] auto iommu_device_id() const -> unsigned {
        return resources_.iommu_device_id();
    }
};
static_assert(sizeof(EventIvrs) < 64);
static_assert(sizeof(EventAdmission) < 64);
} // namespace aurora::uefi
