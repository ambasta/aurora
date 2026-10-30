#pragma once
#include "event-profile-policy.hpp"
#include <utility>
#include <type_traits>

namespace aurora::uefi {
// One attempt for the freshly observed Q35 firmware state. It cannot stop a
// running command engine, reset a device, reclaim backing or retry a failure.
template <BootDmaEndpoint endpoint> class BootDmaHandoff final {
    using Profile = BootDmaProfile<endpoint>;
    using Resources = BootDmaResources<endpoint>;
    using Admission = BootDmaAdmission<endpoint>;
    using Observation = std::conditional_t<endpoint == BootDmaEndpoint::edu, EventEduObservation, NvmeColdObservation>;
    Resources resources_;
    std::array<EventPciFact, Profile::functions> before_{};
    EventAhciFacts expected_{};
    std::span<const std::byte> map_;
    std::size_t stride_{};
    std::uint64_t arena_{};
    bool attempted_{};
    BootDmaHandoff(const Resources &resources) : resources_(resources) {
    }
    [[gnu::noinline, nodiscard]] auto backing() const -> bool {
        const auto clb = expected_.ports[0].command_list;
        const auto fb = expected_.ports[0].received_fis;
        if (fb % 4096 || clb / 4096 == fb / 4096)
            return false;
        for (unsigned port = 0; port < 6; ++port) {
            if (expected_.ports[port].command_list != clb || expected_.ports[port].received_fis != fb + port * 256)
                return false;
        }
        for (unsigned kind = 0; kind < 2; ++kind) {
            const auto fact = EventBackingObservation::capture(
                map_, stride_, kind ? fb : clb, kind ? 256 : 1024, arena_, resources_.physical_bits());
            // This tuple's complete pages are BootServicesData with WB/WT/WC/UC
            // capability attributes, no runtime/protection/unknown attributes.
            if (!fact || fact->type != 4 || fact->attributes != 15)
                return false;
            if (Resources::overlaps(fact->page, 4096, resources_.endpoint_base(), Profile::aperture) ||
                Resources::overlaps(fact->page, 4096, resources_.ahci_base(), 4096) ||
                (Profile::graphics && (Resources::overlaps(fact->page, 4096, resources_.vga_base_, 0x1000000) ||
                                       Resources::overlaps(fact->page, 4096, resources_.vga_registers_, 4096))))
                return false;
            static constexpr std::array<std::pair<std::uint64_t, std::uint64_t>, 4> reserved{
                {{0xfed80000, 0x4000}, {Q35Ecam::base, Q35Ecam::bytes}, {0xfec00000, 4096}, {0xfee00000, 4096}}};
            for (const auto &range : reserved)
                if (Resources::overlaps(fact->page, 4096, range.first, range.second))
                    return false;
        }
        // The adapter only allocates inside its arena. These outside pages are
        // never enrolled in its pool, mapped as CPU data, cleared or released,
        // on success or partial failure. This is retention, not DMA drain.
        return true;
    }
    [[gnu::noinline, nodiscard]] static auto endpoint_idle(const Observation &edu) -> bool {
        if constexpr (endpoint == BootDmaEndpoint::edu)
            return edu.samples[0] == EventEduFact{} && edu.samples[1] == EventEduFact{};
        else
            return edu.cold();
    }

    // One bounded policy operation, separate from PCI reduction state. Every
    // poll observes the full controller; only the selected read-only FR bit may
    // change, and timeout leaves the whole boot attempt consumed.
    template <class AhciRead>
    [[gnu::noinline, nodiscard]] auto wait_fis_stopped(unsigned port, unsigned command, AhciRead &&read) -> bool {
        for (unsigned poll = 0; poll < attempts; ++poll) {
            auto now = read();
            if (!now)
                return false;
            const auto observed = now->ports[port].command;
            if (observed != command && observed != (command & ~0x4000U))
                return false;
            now->ports[port].command = command;
            if (*now != expected_)
                return false;
            if (!(observed & 0x4000)) {
                expected_.ports[port].command = observed;
                return true;
            }
        }
        return false;
    }

public:
    static constexpr unsigned attempts = 1024; // Poll attempts, not elapsed time.
    BootDmaHandoff(const BootDmaHandoff &) = delete;
    auto operator=(const BootDmaHandoff &) -> BootDmaHandoff & = delete;
    auto operator=(BootDmaHandoff &&) -> BootDmaHandoff & = delete;
    BootDmaHandoff(BootDmaHandoff &&other)
        : resources_(other.resources_), before_(other.before_), expected_(other.expected_), map_(other.map_),
          stride_(other.stride_), arena_(other.arena_), attempted_(std::exchange(other.attempted_, true)) {
    }
    [[gnu::noinline, nodiscard]] static auto prepare(const Resources &resources,
                                                     std::span<const EventPciFact> before,
                                                     const EventAhciFacts &first,
                                                     const EventAhciFacts &second,
                                                     const Observation &edu,
                                                     std::span<const std::byte> map,
                                                     std::size_t stride,
                                                     std::uint64_t arena) -> std::optional<BootDmaHandoff> {
        if (resources.purpose_ != Resources::Purpose::firmware_handoff || before.size() != Profile::functions ||
            first != second || first.base != resources.ahci_base() || first.capability != 0xc0141f05 ||
            first.global_control != 0x80000000 || first.implemented_ports != 63 || !endpoint_idle(edu))
            return std::nullopt;
        BootDmaHandoff result{resources};
        result.expected_ = first;
        result.map_ = map;
        result.stride_ = stride;
        result.arena_ = arena;
        constexpr auto requesters = Profile::requesters();
        if (resources.iommu_device_id() != 8)
            return std::nullopt;
        for (unsigned i = 0; i < 6; ++i) {
            const auto &port = first.ports[i];
            // ST/CR are already zero: reject active command engines outright.
            // 6 is the stopped boot port, 0x4014 has only FRE/FR still active.
            if ((port.command != 6 && port.command != 0x4014) || port.command_issue || port.sata_active ||
                port.task_file != 0x50)
                return std::nullopt;
        }
        for (unsigned i = 0; i < Profile::functions; ++i) {
            if (before[i].requester() != requesters[i] ||
                Bytes{before[i].header}.get(4, 2) != (Profile::nvme && i == 2 ? 2U : 7U) ||
                !Resources::identity(before[i], resources.iommu_device_id(), true))
                return std::nullopt;
            result.before_[i] = before[i];
        }
        const auto endpoint_bar = (Bytes{before[2].header}.get(16, 4) & ~15ULL) |
                                  (Profile::nvme ? Bytes{before[2].header}.get(20, 4) << 32 : 0);
        if (endpoint_bar != resources.endpoint_base() ||
            Bytes{before[Profile::graphics ? 5 : 4].header}.get(36, 4) != resources.ahci_base() || !result.backing())
            return std::nullopt;
        return result;
    }
    template <class AhciRead, class AhciWrite, class EndpointRead, class PciReduce>
    [[gnu::noinline, nodiscard]] auto complete(bool &boot_attempted,
                                               AhciRead &&ahci_read,
                                               AhciWrite &&ahci_write,
                                               EndpointRead &&endpoint_read,
                                               PciReduce &&pci_reduce) -> std::optional<Admission> {
        if (std::exchange(attempted_, true) || std::exchange(boot_attempted, true) || !backing())
            return std::nullopt;
        const auto edu = endpoint_read();
        if (!edu || !endpoint_idle(*edu))
            return std::nullopt;
        for (unsigned port = 0; port < 6; ++port) {
            const auto before = ahci_read();
            if (!before || *before != expected_)
                return std::nullopt;
            if (!(expected_.ports[port].command & 0x10))
                continue;
            // Every current ST/CR is still zero. Preserve all other bits and
            // clear only FRE; FR is read-only and must subsequently read zero.
            const auto command = expected_.ports[port].command & ~0x10U;
            if (!ahci_write(port, command))
                return std::nullopt;
            expected_.ports[port].command = command;
            if (!wait_fis_stopped(port, command, ahci_read))
                return std::nullopt;
        }
        if (!backing())
            return std::nullopt;
        // Each exact command reduction has complete header readback. Original
        // firmware facts are immutable; no post-state is passed off as a copy.
        for (const auto &fact : before_) {
            const auto rid = fact.requester();
            unsigned command = 0;
            switch (rid) {
            case 0:
            case 0xf8:
            case 0xfa:
            case 0xfb:
                command = 3;
                break;
            case Profile::requester:
                command = 2;
                break;
            case 8:
                command = 7;
                break; // Readback only; no IOMMU command write.
            default:
                if constexpr (Profile::graphics) {
                    if (rid != 0x18)
                        return std::nullopt;
                    command = 3;
                } else {
                    return std::nullopt;
                }
            }
            if (rid == Profile::requester) {
                const auto idle = endpoint_read();
                if (!idle || !endpoint_idle(*idle))
                    return std::nullopt;
            }
            const auto after = pci_reduce(fact, command);
            auto expected = fact.header;
            put(expected, 4, command, 2);
            if (!after || *after != expected)
                return std::nullopt;
            if (rid == Profile::requester) {
                const auto idle = endpoint_read();
                if (!idle || !endpoint_idle(*idle))
                    return std::nullopt;
            }
        }
        const auto final_edu = endpoint_read();
        if (!final_edu || !endpoint_idle(*final_edu))
            return std::nullopt;
        for (unsigned pass = 0; pass < 2; ++pass) {
            const auto final_ahci = ahci_read();
            if (!final_ahci || *final_ahci != expected_)
                return std::nullopt;
        }
        if (!backing())
            return std::nullopt;
        resources_.purpose_ = Resources::Purpose::admission;
        resources_.endpoint_command_ = 2;
        if constexpr (endpoint == BootDmaEndpoint::edu)
            return Admission::admit(resources_, expected_);
        else
            return Admission::admit(resources_, expected_, *final_edu);
    }
};
} // namespace aurora::uefi
