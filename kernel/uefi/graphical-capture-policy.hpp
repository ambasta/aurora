#pragma once
#include <cstdint>
#include <string_view>

// Pure closed diagnostic policy. Native state and effects exist only in the
// exact graphical capture profile; these values are never a source service ABI.
namespace aurora::uefi::graphical_capture {
enum class Scenario : std::uint8_t {
    invalid,
    normal,
    cross_console,
    cross_display,
    stale_console,
    stale_display,
    first_pixel_error,
    interior_pixel_error
};
[[nodiscard]] constexpr auto select(std::uint8_t byte) -> Scenario {
    if (byte == 'G')
        return Scenario::normal;
    if (byte == 'C')
        return Scenario::cross_console;
    if (byte == 'D')
        return Scenario::cross_display;
    if (byte == 'c')
        return Scenario::stale_console;
    if (byte == 'd')
        return Scenario::stale_display;
    if (byte == 'F')
        return Scenario::first_pixel_error;
    if (byte == 'I')
        return Scenario::interior_pixel_error;
    return Scenario::invalid;
}
[[nodiscard]] constexpr auto name(Scenario scenario) -> std::string_view {
    if (scenario == Scenario::normal)
        return "normal";
    if (scenario == Scenario::cross_console)
        return "cross-console";
    if (scenario == Scenario::cross_display)
        return "cross-display";
    if (scenario == Scenario::stale_console)
        return "stale-console";
    if (scenario == Scenario::stale_display)
        return "stale-display";
    if (scenario == Scenario::first_pixel_error)
        return "first-pixel-error";
    if (scenario == Scenario::interior_pixel_error)
        return "interior-pixel-error";
    return "invalid";
}
[[nodiscard]] constexpr auto fail_pixel(Scenario scenario, std::uint64_t successful_stores) -> bool {
    return (scenario == Scenario::first_pixel_error && successful_stores == 0) ||
           (scenario == Scenario::interior_pixel_error && successful_stores == 55);
}
} // namespace aurora::uefi::graphical_capture
