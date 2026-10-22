#pragma once
// Test-only BIOS selection. Ordinary images have no reader or selected state.
#ifdef AURORA_BIOS_FIXTURE
#if defined(AURORA_INTERACTIVE_CONSOLE) || defined(AURORA_UEFI_RUNTIME) || defined(AURORA_UEFI_ACPI)
#error BIOS fixtures cannot share a console or UEFI image
#endif
#if defined(AURORA_BIOS_FAULT_FIXTURE) == defined(AURORA_BIOS_SCHEDULE_FIXTURE)
#error BIOS fixtures require exactly one closed family
#endif
#if defined(AURORA_BIOS_SCHEDULE_FIXTURE) != defined(AURORA_TEST_SCHEDULE)
#error BIOS fixture family must match the scheduling payload
#endif
#if defined(AURORA_DIVISION_FIXTURE) || defined(AURORA_UNSIGNED_FIXTURE) || AURORA_USER_PROBE_MODE != 0
#error BIOS fixtures require the unmodified family payload and probe
#endif
#include "console.hpp"
#include <optional>
namespace aurora::bios {
#include "uefi/fixture-selector.inc"
inline Fixture fixture{};
[[nodiscard]] inline auto selected(Fixture value) -> bool {
    return fixture == value;
}
} // namespace aurora::bios
#endif
#if !defined(AURORA_BIOS_FIXTURE) && (defined(AURORA_BIOS_FAULT_FIXTURE) || defined(AURORA_BIOS_SCHEDULE_FIXTURE))
#error BIOS fixture family requires the fixture image
#endif
