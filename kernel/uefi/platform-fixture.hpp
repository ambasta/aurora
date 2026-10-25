#pragma once
// Included only by the platform-fixture image, which carries every loader
// handoff, ACPI, PCI, BAR, NVMe-preparation and IVRS case. The loader-stage faults
// inject before ExitBootServices, while OVMF's terminal driver still owns the
// UART, so the selector arrives in a QEMU fw_cfg file (fw-cfg-fixture.hpp) read
// at loader entry instead of a serial byte. The loader copies the one admitted
// value into the handoff's fixture word; the payload rejects any handoff whose
// word is outside the image's interval and branches on it in each phase.
#ifndef AURORA_PLATFORM_FIXTURE
#error "The fw_cfg platform selector belongs only to the platform-fixture image"
#endif
#include "fw-cfg-fixture.hpp"
#include <cstdint>
#include <optional>
namespace aurora::uefi::platform {
using Fixture = fw_cfg::Fixture;
inline constexpr auto first = Fixture::early_stale;
inline constexpr auto last = Fixture::ivrs_missing;
// Each family is one run of rows; the predicates below rely on this order.
static_assert(static_cast<unsigned>(Fixture::early_nx) + 1 == static_cast<unsigned>(Fixture::acpi_baseline) &&
              static_cast<unsigned>(Fixture::acpi_revoked) + 1 == static_cast<unsigned>(Fixture::pci_baseline) &&
              static_cast<unsigned>(Fixture::pci_revoked) + 1 == static_cast<unsigned>(Fixture::bar_state) &&
              static_cast<unsigned>(Fixture::bar_state) + 1 == static_cast<unsigned>(Fixture::bar_capture) &&
              static_cast<unsigned>(Fixture::bar_alias) + 1 == static_cast<unsigned>(Fixture::bar_prepare) &&
              static_cast<unsigned>(Fixture::bar_prepare) + 1 == static_cast<unsigned>(Fixture::ivrs_write) &&
              static_cast<unsigned>(Fixture::ivrs_read) + 1 == static_cast<unsigned>(Fixture::ivrs_missing));
[[nodiscard]] constexpr auto admitted(std::uint64_t value) -> bool {
    return value >= static_cast<unsigned>(first) && value <= static_cast<unsigned>(last);
}
[[nodiscard]] constexpr auto selected(std::uint64_t value, Fixture fixture) -> bool {
    return admitted(value) && value == static_cast<unsigned>(fixture);
}
// The copied row of an already validated handoff word.
[[nodiscard]] constexpr auto row(std::uint64_t value) -> Fixture {
    return admitted(value) ? static_cast<Fixture>(value) : Fixture{};
}
// Rows from PCI onward require MCFG and scan PCI; early and ACPI rows stop after ACPI.
[[nodiscard]] constexpr auto pci(Fixture fixture) -> bool {
    return fixture >= Fixture::pci_baseline && fixture <= last;
}
// BAR rows after bar-state, and every IVRS row, capture the firmware BAR record (handoff v4).
[[nodiscard]] constexpr auto capture(Fixture fixture) -> bool {
    return fixture >= Fixture::bar_capture && fixture <= last;
}
// IVRS rows require the IVRS table and the q35 LAPIC, and observe the IOMMU after the BAR.
[[nodiscard]] constexpr auto ivrs(Fixture fixture) -> bool {
    return fixture >= Fixture::ivrs_write && fixture <= last;
}
class FwCfg final {
public:
    [[nodiscard]] static auto read() -> std::optional<Fixture> {
        return fw_cfg::FwCfg::read(first, last);
    }
};
} // namespace aurora::uefi::platform
