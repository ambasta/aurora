#pragma once
// The test images whose loader reads one QEMU fw_cfg row at entry
// (fw-cfg-fixture.hpp), echoes it as AURORA_FIXTURE_SELECTED and copies it into
// one extra handoff word that the payload admits only within the image's
// interval: platform-fixture (loader and device-discovery faults),
// display-fixture (the framebuffer cases and the standalone graphical console),
// device-fixture (the UEFI console, its service faults and owned bytes),
// storage-fixture (the RAM file service, RAM scratchpad console, blocking
// snapshot call and snapshot producer) and text-fixture (the protected file-call
// console, owned text and the console region). Every later phase of those images
// branches on the copied row.
#if defined(AURORA_PLATFORM_FIXTURE) + defined(AURORA_DISPLAY_FIXTURE) + defined(AURORA_DEVICE_FIXTURE) +              \
        defined(AURORA_STORAGE_FIXTURE) + defined(AURORA_TEXT_FIXTURE) !=                                              \
    1
#error "The fw_cfg loader selector belongs only to the platform, display, device, storage and text fixture images"
#endif
#include "fw-cfg-fixture.hpp"
#include <cstdint>
#include <optional>
namespace aurora::uefi::loader_fixture {
using Fixture = fw_cfg::Fixture;
#if defined(AURORA_PLATFORM_FIXTURE)
inline constexpr auto first = Fixture::early_stale;
inline constexpr auto last = Fixture::ivrs_missing;
#elif defined(AURORA_DISPLAY_FIXTURE)
inline constexpr auto first = Fixture::framebuffer_baseline;
inline constexpr auto last = Fixture::graphical_capture;
// Framebuffer rows, then the two graphical-console rows; the predicates rely on this order.
static_assert(static_cast<unsigned>(Fixture::framebuffer_stale) + 1 ==
                  static_cast<unsigned>(Fixture::graphical_baseline) &&
              static_cast<unsigned>(Fixture::graphical_baseline) + 1 == static_cast<unsigned>(last));
#elif defined(AURORA_STORAGE_FIXTURE)
inline constexpr auto first = Fixture::ram_baseline;
inline constexpr auto last = Fixture::snapshot_reply_reserved;
#elif defined(AURORA_TEXT_FIXTURE)
inline constexpr auto first = Fixture::text_baseline;
inline constexpr auto last = Fixture::file_budget;
#else
inline constexpr auto first = Fixture::console_service_baseline;
inline constexpr auto last = Fixture::owned_bytes_baseline;
// Console rows, then owned bytes; the predicates rely on this order.
static_assert(static_cast<unsigned>(Fixture::console_service_report) + 1 == static_cast<unsigned>(last));
#endif
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
[[nodiscard]] inline auto read() -> std::optional<Fixture> {
    return fw_cfg::FwCfg::read(first, last);
}
#if defined(AURORA_DISPLAY_FIXTURE)
// The framebuffer rows hand over v5 without ACPI; the graphical console needs ACPI (v6).
[[nodiscard]] constexpr auto framebuffer(Fixture fixture) -> bool {
    return fixture >= first && fixture < Fixture::graphical_baseline;
}
[[nodiscard]] constexpr auto graphical(Fixture fixture) -> bool {
    return fixture >= Fixture::graphical_baseline && fixture <= last;
}
// Only the capture row waits at the capture gate and selects a capture scenario.
[[nodiscard]] constexpr auto graphical_capture(Fixture fixture) -> bool {
    return fixture == Fixture::graphical_capture;
}
[[nodiscard]] constexpr auto acpi(Fixture fixture) -> bool {
    return graphical(fixture);
}
#elif defined(AURORA_DEVICE_FIXTURE)
// The console rows need ACPI (v2); owned bytes hands over v1 without it.
[[nodiscard]] constexpr auto console(Fixture fixture) -> bool {
    return fixture >= first && fixture < Fixture::owned_bytes_baseline;
}
[[nodiscard]] constexpr auto owned_bytes(Fixture fixture) -> bool {
    return fixture == Fixture::owned_bytes_baseline;
}
[[nodiscard]] constexpr auto acpi(Fixture fixture) -> bool {
    return console(fixture);
}
#else
[[nodiscard]] constexpr auto acpi(Fixture) -> bool {
    return true;
}
#endif
} // namespace aurora::uefi::loader_fixture
