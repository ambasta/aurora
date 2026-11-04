#pragma once
#include <cstdint>
namespace aurora::uefi::ap_worker {
// One compiled standalone worker image. The existing fw_cfg case word selects
// only these closed qualification scenarios; it never supplies an address.
enum class Case : std::uint64_t {
    normal,
    fault,
    withheld,
    late,
    wrong_identity,
    wrong_root,
    stagnant_timer,
    invalid_low_ownership,
    malformed_topology,
    unsupported_timer,
    malformed_completion
};
[[nodiscard]] constexpr auto admitted_case(std::uint64_t value) -> bool {
    return value <= static_cast<std::uint64_t>(Case::malformed_completion);
}
} // namespace aurora::uefi::ap_worker
