#pragma once
// Test-only BIOS selection. Ordinary images have no reader or selected state.
#ifdef AURORA_BIOS_FIXTURE
#if defined(AURORA_INTERACTIVE_CONSOLE) || defined(AURORA_UEFI_RUNTIME) || defined(AURORA_UEFI_ACPI)
#error BIOS fixtures cannot share a console or UEFI image
#endif
#include "console.hpp"
#include <optional>
#include <string_view>
namespace aurora::bios {
using namespace std::string_view_literals;
#include "uefi/fixture-selector.inc"
inline constexpr auto first = Fixture::bios_division_kernel_trap;
inline constexpr auto last = Fixture::bios_schedule_fpu;
inline Fixture fixture{};
[[nodiscard]] inline auto selected(Fixture value) -> bool {
    return fixture == value;
}
[[nodiscard]] inline auto between(Fixture begin, Fixture end) -> bool {
    return fixture >= begin && fixture <= end;
}
// The scheduler family runs the scheduled tasks instead of the compiled-program self test.
[[nodiscard]] inline auto schedule() -> bool {
    return between(Fixture::bios_schedule_baseline, Fixture::bios_schedule_fpu);
}
// Transcript labels of the program-set rows; empty for every other row.
[[nodiscard]] inline auto division() -> std::string_view {
    return selected(Fixture::bios_division_zero)             ? "zero"sv
           : selected(Fixture::bios_division_remainder_zero) ? "remainder-zero"sv
           : selected(Fixture::bios_division_overflow)       ? "overflow"sv
           : selected(Fixture::bios_division_remainder_min)  ? "remainder-min"sv
                                                             : ""sv;
}
[[nodiscard]] inline auto unsigned_case() -> std::string_view {
    return selected(Fixture::bios_unsigned_valid)                 ? "valid"sv
           : selected(Fixture::bios_unsigned_shift_count)         ? "shift-count"sv
           : selected(Fixture::bios_unsigned_conversion_overflow) ? "conversion-overflow"sv
           : selected(Fixture::bios_unsigned_kernel_trap)         ? "kernel-trap"sv
                                                                  : ""sv;
}
} // namespace aurora::bios
#endif
