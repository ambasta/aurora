#pragma once
#include <cstdint>

namespace aurora::user {
enum class ProgramEvent {
    rejected,
    returned,
    bounds,
    overflow,
    division_zero,
    shift_count
};
// Replaceable copied scalar bootstrap seam, not a source-language foreign ABI.
auto language_terminal_event(std::uint64_t vector, std::uint64_t matched_sites, std::uint64_t stack_top)
    -> std::uint64_t asm("aurora_kernel_terminal_event") __attribute__((visibility("hidden")));

// Zero is producer refusal. A positive proposal must match original facts;
// this decoder never synthesizes acceptance when the native producer refuses.
[[nodiscard]] constexpr auto
decode_terminal_event(std::uint64_t encoded, std::uint64_t vector, std::uint64_t sites, std::uint64_t stack_top)
    -> ProgramEvent {
    if (vector > 255 || sites > 31 || stack_top > 1 || sites == 0 || (sites & (sites - 1)) != 0)
        return ProgramEvent::rejected;
    switch (encoded) {
    case 1:
        if (vector == 129 && sites == 1 && stack_top == 1)
            return ProgramEvent::returned;
        break;
    case 2:
        if (vector == 6 && sites == 2)
            return ProgramEvent::bounds;
        break;
    case 3:
        if (vector == 6 && sites == 4)
            return ProgramEvent::overflow;
        break;
    case 4:
        if (vector == 6 && sites == 8)
            return ProgramEvent::division_zero;
        break;
    case 5:
        if (vector == 6 && sites == 16)
            return ProgramEvent::shift_count;
        break;
    default:
        break;
    }
    return ProgramEvent::rejected;
}
} // namespace aurora::user
