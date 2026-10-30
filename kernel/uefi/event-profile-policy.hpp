#pragma once
#include "bar-policy.hpp"
#include "dma-capture-layout.hpp"
#include "framebuffer-policy.hpp"

namespace aurora::uefi {
// The closed bootstrap profiles share wire parsing, not authority. Distinct
// template instantiations cannot convert an EDU admission into NVMe authority.
enum class BootDmaEndpoint {
    edu,
    nvme,
    nvme_graphics
};
template <BootDmaEndpoint endpoint> class BootDmaIvrs;
template <BootDmaEndpoint endpoint> class BootDmaResources;
template <BootDmaEndpoint endpoint> class BootDmaAdmission;
template <BootDmaEndpoint endpoint> class BootDmaHandoff;
template <BootDmaEndpoint endpoint> class BootDmaProfile final {
public:
    static constexpr bool graphics = endpoint == BootDmaEndpoint::nvme_graphics;
    static constexpr bool nvme = endpoint != BootDmaEndpoint::edu;
    using Capture = DmaCaptureLayout<graphics>;
    static constexpr unsigned functions = Capture::functions;
    static constexpr unsigned requester = endpoint == BootDmaEndpoint::edu ? 0x20 : 0x10;
    static constexpr std::uint64_t aperture = endpoint == BootDmaEndpoint::edu ? 0x100000 : 0x4000;
    static constexpr auto requesters() {
        if constexpr (graphics)
            return std::array<unsigned, 7>{0, 8, requester, 0x18, 0xf8, 0xfa, 0xfb};
        else
            return std::array<unsigned, 6>{0, 8, requester, 0xf8, 0xfa, 0xfb};
    }
};
using EventIvrs = BootDmaIvrs<BootDmaEndpoint::edu>;
using NvmeIvrs = BootDmaIvrs<BootDmaEndpoint::nvme>;
using NvmeGraphicsIvrs = BootDmaIvrs<BootDmaEndpoint::nvme_graphics>;
using EventResources = BootDmaResources<BootDmaEndpoint::edu>;
using NvmeResources = BootDmaResources<BootDmaEndpoint::nvme>;
using NvmeGraphicsResources = BootDmaResources<BootDmaEndpoint::nvme_graphics>;
using EventAdmission = BootDmaAdmission<BootDmaEndpoint::edu>;
using NvmeAdmission = BootDmaAdmission<BootDmaEndpoint::nvme>;
using NvmeGraphicsAdmission = BootDmaAdmission<BootDmaEndpoint::nvme_graphics>;
using EventHandoff = BootDmaHandoff<BootDmaEndpoint::edu>;
using NvmeHandoff = BootDmaHandoff<BootDmaEndpoint::nvme>;
using NvmeGraphicsHandoff = BootDmaHandoff<BootDmaEndpoint::nvme_graphics>;
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
    template <BootDmaEndpoint> friend class BootDmaIvrs;
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
template <BootDmaEndpoint endpoint> class BootDmaIvrs final {
    EventIvrsUnit unit_{};
    std::array<std::uint16_t, BootDmaProfile<endpoint>::functions> requesters_{};
    unsigned physical_bits_{};
    BootDmaIvrs() = default;

public:
    static constexpr std::size_t maximum_requesters = BootDmaProfile<endpoint>::functions;
    static constexpr std::size_t maximum_table = 128 + maximum_requesters * 8;
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
        -> std::optional<BootDmaIvrs> {
        if (physical_bits < 32 || physical_bits > 52 || bytes.size() != maximum_table || !Acpi::table(bytes, "IVRS") ||
            Bytes{bytes}.get(8, 1) != 1 || Bytes{bytes}.get(36, 4) != 0x2801 || Bytes{bytes}.get(40) != 0)
            return std::nullopt;
        BootDmaIvrs result;
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
            if (unit > 255 || (unit & 7) || unit == 0 || unit == BootDmaProfile<endpoint>::requester ||
                unit == ioapic_requester || unit >= 0xf8)
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
        for (unsigned requester : {0U, BootDmaProfile<endpoint>::requester, 0xf8U, 0xfaU, 0xfbU})
            if (!result.covers(0, 0, requester >> 3, requester & 7))
                return std::nullopt;
        if constexpr (BootDmaProfile<endpoint>::graphics)
            if (!result.covers(0, 0, 3, 0) || result.unit().device_id() != 8)
                return std::nullopt;
        return result;
    }
};

// One bootstrap translation unit owns the parser body. Hosted policy tests keep
// the inline implementation; the image avoids different discarded COMDAT copies.
[[nodiscard]] auto read_event_ivrs(std::span<const std::byte> bytes, unsigned bits) -> std::optional<EventIvrs>;
[[nodiscard]] auto read_nvme_ivrs(std::span<const std::byte> bytes, unsigned bits) -> std::optional<NvmeIvrs>;
[[nodiscard]] auto read_nvme_graphics_ivrs(std::span<const std::byte> bytes, unsigned bits)
    -> std::optional<NvmeGraphicsIvrs>;

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
    [[gnu::noinline, nodiscard]] auto operator==(const EventAhciFacts &) const -> bool = default;
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

// Observation-only copied facts. Neither type can mint EventAdmission or
// authorize writes. QEMU edu.c accepts aligned 64-bit reads at DMA command 0x98;
// dma_rw(write=false, timer=false) only copies the command value.
class EventEduFact final {
public:
    std::uint64_t command{};
    std::uint32_t status{}, irq{};
    [[nodiscard]] auto operator==(const EventEduFact &) const -> bool = default;
};
class EventEduObservation final {
public:
    std::array<EventEduFact, 2> samples{};
    template <class Reader> [[nodiscard]] static auto sample(Reader &&read) -> EventEduObservation {
        EventEduObservation result;
        for (auto &fact : result.samples) {
            fact.command = read(0x98, 8);
            fact.status = static_cast<std::uint32_t>(read(0x20, 4));
            fact.irq = static_cast<std::uint32_t>(read(0x24, 4));
        }
        return result;
    }
};

class NvmeColdFact final {
public:
    std::uint64_t capability{}, submission{}, completion{};
    std::uint32_t version{}, control{}, status{}, queue_attributes{};
    [[nodiscard]] auto operator==(const NvmeColdFact &) const -> bool = default;
};
class NvmeColdObservation final {
public:
    std::array<NvmeColdFact, 2> samples{};
    template <class Reader> [[nodiscard]] static auto sample(Reader &&read) -> NvmeColdObservation {
        NvmeColdObservation result;
        for (auto &fact : result.samples) {
            fact.capability = read(0, 8);
            fact.version = static_cast<std::uint32_t>(read(8, 4));
            fact.control = static_cast<std::uint32_t>(read(0x14, 4));
            fact.status = static_cast<std::uint32_t>(read(0x1c, 4));
            fact.queue_attributes = static_cast<std::uint32_t>(read(0x24, 4));
            fact.submission = read(0x28, 8);
            fact.completion = read(0x30, 8);
        }
        return result;
    }
    [[nodiscard]] auto cold() const -> bool {
        // QEMU 10.0.13, mqes=1, no CMB/PMR; NVMe 1.4, 4 KiB pages,
        // contiguous queues, NVM command set. CAP's timeout is not our clock.
        constexpr std::uint64_t cap = (4ULL << 52) | (0x41ULL << 37) | (15ULL << 24) | (1ULL << 16) | 1;
        return samples[0] == samples[1] && samples[0] == NvmeColdFact{cap, 0, 0, 0x10400, 0, 0, 0};
    }
};

class EventBackingObservation final {
public:
    std::uint64_t page{}, type{}, begin{}, pages{}, attributes{};
    [[nodiscard]] static auto capture(std::span<const std::byte> map,
                                      std::size_t stride,
                                      std::uint64_t address,
                                      unsigned alignment,
                                      std::uint64_t arena,
                                      unsigned bits) -> std::optional<EventBackingObservation> {
        // CLB is 1 KiB-aligned/1 KiB long, FB is 256-byte-aligned/256 bytes long;
        // each fits one complete page. Inspect only copied descriptor metadata.
        if ((alignment != 1024 && alignment != 256) || !address || address % alignment || bits < 32 || bits > 52 ||
            address >= (std::uint64_t{1} << bits) || !MemoryMap{map, stride, 1}.valid())
            return std::nullopt;
        const auto page = address - address % 4096;
        if (!arena || arena > UINT64_MAX - Handoff::arena_bytes ||
            (page < arena + Handoff::arena_bytes && arena < page + 4096))
            return std::nullopt;
        for (std::size_t at = 0; at < map.size(); at += stride) {
            const Bytes entry{map.subspan(at, stride)};
            const auto begin = entry.get(8), pages = entry.get(24);
            if (page >= begin && page - begin < pages * 4096)
                return EventBackingObservation{page, entry.get(0, 4), begin, pages, entry.get(32)};
        }
        return std::nullopt;
    }
};

// Resource admission precedes AHCI register reads. A successful object is only
// bounded platform/resource evidence; EventAdmission additionally needs idle
// boot-controller facts before the fixture may be considered for activation.
template <BootDmaEndpoint endpoint> class BootDmaResources final {
    using Profile = BootDmaProfile<endpoint>;

public:
    enum class Purpose {
        admission,
        read_only_observation,
        firmware_handoff
    };

private:
    friend class BootDmaAdmission<endpoint>;
    friend class BootDmaHandoff<endpoint>;
    std::uint64_t endpoint_base_{}, ahci_base_{}, vga_base_{}, vga_registers_{};
    unsigned physical_bits_{}, iommu_requester_{}, endpoint_command_{};
    Purpose purpose_{};
    BootDmaResources() = default;
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
        if (requester == Profile::requester) {
            if constexpr (Profile::nvme)
                return h.get(0, 4) == 0x00101b36 && h.get(8, 4) == 0x01080202 && h.get(14, 1) == 0 &&
                       h.get(4, 2) == 2 && (h.get(16, 4) & 15) == 4 &&
                       ((h.get(16, 4) & ~15ULL) | (h.get(20, 4) << 32)) != 0 && h.get(24) == 0 && h.get(32) == 0;
            else
                return h.get(0, 4) == 0x11e81234 && h.get(8, 4) == 0x00ff0010 && h.get(14, 1) == 0 &&
                       (h.get(4, 2) == 2 || (observation_only && h.get(4, 2) == 7)) && (h.get(16, 4) & 15) == 0 &&
                       h.get(16, 4) != 0;
        }
        if constexpr (Profile::graphics)
            if (requester == 0x18)
                return h.get(0, 4) == 0x11111234 && h.get(8, 4) == 0x03000002 && h.get(14, 1) == 0 &&
                       (h.get(4, 2) == 3 || (observation_only && h.get(4, 2) == 7)) && (h.get(16, 4) & 15) == 8 &&
                       (h.get(16, 4) & ~15ULL) && h.get(20, 4) == 0 && (h.get(24, 4) & 15) == 0 && h.get(24, 4) &&
                       h.get(28, 4) == 0 && h.get(32) == 0;
        if (requester == 0xf8)
            return h.get(0, 4) == 0x29188086 && h.get(8, 4) == 0x06010002;
        if (requester == 0xfa)
            return h.get(0, 4) == 0x29228086 && h.get(8, 4) == 0x01060102 && (h.get(4, 2) & 2);
        return requester == 0xfb && h.get(0, 4) == 0x29308086 && h.get(8, 4) == 0x0c050002;
    }

public:
    // Observation may describe inherited BME but cannot mint EventAdmission.
    static constexpr bool graphics = Profile::graphics;
    static constexpr std::size_t maximum_functions = Profile::functions, maximum_bars = 8;
    [[nodiscard]] auto endpoint_base() const -> std::uint64_t {
        return endpoint_base_;
    }
    [[nodiscard]] auto edu_base() const -> std::uint64_t
        requires(endpoint == BootDmaEndpoint::edu)
    {
        return endpoint_base();
    }
    [[nodiscard]] auto edu_config_address() const -> std::uint64_t
        requires(endpoint == BootDmaEndpoint::edu)
    {
        return endpoint_config_address();
    }
    [[nodiscard]] auto edu_initial_command() const -> unsigned
        requires(endpoint == BootDmaEndpoint::edu)
    {
        return endpoint_initial_command();
    }
    [[nodiscard]] auto ahci_base() const -> std::uint64_t {
        return ahci_base_;
    }
    [[nodiscard]] auto iommu_base() const -> std::uint64_t {
        return 0xfed80000;
    }
    [[nodiscard]] auto endpoint_config_address() const -> std::uint64_t {
        return Q35Ecam::base + (Profile::requester << 12);
    }
    [[nodiscard]] auto endpoint_initial_command() const -> unsigned {
        return endpoint_command_;
    }
    [[nodiscard]] auto physical_bits() const -> unsigned {
        return physical_bits_;
    }
    [[nodiscard]] auto iommu_device_id() const -> unsigned {
        return iommu_requester_;
    }

    [[nodiscard]] static auto admit_qemu_default(const BootDmaIvrs<endpoint> &ivrs,
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
                                                 Purpose purpose = Purpose::admission,
                                                 const FramebufferAdmission *framebuffer = nullptr)
        -> std::optional<BootDmaResources> {
        if (copied.size() != maximum_functions || current.size() != maximum_functions || bars.empty() ||
            bars.size() > maximum_bars || root_segment != 0 || root.physical_bits() != ivrs.physical_bits() ||
            root.source() != PciResourceSource::Edk2Stable202502Root || !MemoryMap{map, stride, 1}.valid() ||
            !iommu_capabilities(copied_caps) || !iommu_capabilities(current_caps))
            return std::nullopt;
        if ((framebuffer != nullptr) != Profile::graphics || (framebuffer && framebuffer->owned_arena() != arena))
            return std::nullopt;
        const auto limit = std::uint64_t{1} << ivrs.physical_bits();
        if (!arena || arena % 4096 || arena >= limit || Handoff::arena_bytes > limit - arena || !apic || apic % 4096 ||
            apic >= limit || 4096 > limit - apic)
            return std::nullopt;
        BootDmaResources result;
        result.purpose_ = purpose;
        result.physical_bits_ = ivrs.physical_bits();
        result.iommu_requester_ = ivrs.unit().device_id();
        std::array<bool, maximum_bars> seen{};
        std::array<std::optional<PciBarReservation>, maximum_bars> ranges{};
        unsigned consumed = 0;
        for (std::size_t i = 0; i < current.size(); ++i) {
            const auto &now = current[i];
            if (!identity(now, result.iommu_requester_, result.purpose_ != Purpose::admission) ||
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
            if (now.requester() == Profile::requester)
                result.endpoint_command_ = static_cast<unsigned>(header.get(4, 2));
            for (unsigned slot = 0; slot < 6; ++slot) {
                const auto low = header.get(16 + slot * 4, 4);
                if (!low || (low & 1))
                    continue;
                // Exactly the endpoint BAR0 and AHCI BAR5. Only the NVMe
                // profile admits a 64-bit BAR, with its upper half parsed once.
                const bool edu = now.requester() == Profile::requester && slot == 0;
                const bool ahci = now.requester() == 0xfa && slot == 5;
                const bool framebuffer_bar = Profile::graphics && now.requester() == 0x18 && slot == 0;
                const bool vga_registers = Profile::graphics && now.requester() == 0x18 && slot == 2;
                if ((!edu && !ahci && !framebuffer_bar && !vga_registers) || (low & 15) != (edu && Profile::nvme ? 4U
                                                                                            : framebuffer_bar    ? 8U
                                                                                                                 : 0U))
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
                    if (!range || range->length() != (edu ? Profile::aperture : framebuffer_bar ? 0x1000000U : 0x1000U))
                        return std::nullopt;
                    ranges[index] = range;
                    seen[index] = true;
                    ++consumed;
                    if (edu)
                        result.endpoint_base_ = range->begin();
                    else if (ahci)
                        result.ahci_base_ = range->begin();
                    else if (framebuffer_bar)
                        result.vga_base_ = range->begin();
                    else
                        result.vga_registers_ = range->begin();
                }
                if (bar_matches != 1)
                    return std::nullopt;
                if (edu && Profile::nvme)
                    ++slot;
            }
        }
        if (consumed != bars.size() || consumed != (Profile::graphics ? 4U : 2U) || !result.endpoint_base_ ||
            !result.ahci_base_)
            return std::nullopt;
        if constexpr (Profile::graphics) {
            const auto &geometry = framebuffer->geometry();
            if (!result.vga_base_ || !result.vga_registers_ || geometry.base() < result.vga_base_ ||
                geometry.base() - result.vga_base_ >= 0x1000000 ||
                geometry.resource_bytes() > 0x1000000 - (geometry.base() - result.vga_base_))
                return std::nullopt;
        }
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
        for (unsigned index = 0; index < (Profile::graphics ? 5U : 3U); ++index) {
            const auto begin = index == 0   ? result.endpoint_base_
                               : index == 1 ? result.ahci_base_
                               : index == 2 ? 0xfed80000ULL
                               : index == 3 ? result.vga_base_
                                            : result.vga_registers_;
            const auto length = index == 0   ? Profile::aperture
                                : index == 2 ? 0x4000ULL
                                : index == 3 ? 0x1000000ULL
                                             : 0x1000ULL;
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

template <BootDmaEndpoint endpoint> class BootDmaAdmission final {
    BootDmaResources<endpoint> resources_;
    explicit BootDmaAdmission(const BootDmaResources<endpoint> &resources) : resources_(resources) {
    }

public:
    [[nodiscard]] static auto admit(const BootDmaResources<endpoint> &resources, const EventAhciFacts &ahci)
        -> std::optional<BootDmaAdmission>
        requires(endpoint == BootDmaEndpoint::edu)
    {
        if (resources.purpose_ != BootDmaResources<endpoint>::Purpose::admission ||
            !ahci.quiescent(resources.ahci_base()))
            return std::nullopt;
        return BootDmaAdmission{resources};
    }
    [[nodiscard]] static auto admit(const BootDmaResources<endpoint> &resources,
                                    const EventAhciFacts &ahci,
                                    const NvmeColdObservation &cold) -> std::optional<BootDmaAdmission>
        requires(endpoint != BootDmaEndpoint::edu)
    {
        if (resources.purpose_ != BootDmaResources<endpoint>::Purpose::admission ||
            !ahci.quiescent(resources.ahci_base()) || !cold.cold())
            return std::nullopt;
        return BootDmaAdmission{resources};
    }
    [[nodiscard]] auto endpoint_base() const -> std::uint64_t {
        return resources_.endpoint_base();
    }
    [[nodiscard]] auto edu_base() const -> std::uint64_t
        requires(endpoint == BootDmaEndpoint::edu)
    {
        return endpoint_base();
    }
    [[nodiscard]] auto edu_config_address() const -> std::uint64_t
        requires(endpoint == BootDmaEndpoint::edu)
    {
        return endpoint_config_address();
    }
    [[nodiscard]] auto edu_initial_command() const -> unsigned
        requires(endpoint == BootDmaEndpoint::edu)
    {
        return endpoint_initial_command();
    }
    [[nodiscard]] auto iommu_base() const -> std::uint64_t {
        return resources_.iommu_base();
    }
    [[nodiscard]] auto endpoint_config_address() const -> std::uint64_t {
        return resources_.endpoint_config_address();
    }
    [[nodiscard]] auto endpoint_initial_command() const -> unsigned {
        return resources_.endpoint_initial_command();
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
