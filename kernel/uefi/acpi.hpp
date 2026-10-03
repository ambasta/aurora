#pragma once
#include "handoff.hpp"
#ifdef AURORA_UEFI_SERVICE_BUDGET
#include "acpi-policy.hpp"
#endif
namespace aurora::uefi {
#ifdef AURORA_UEFI_SERVICE_BUDGET
[[nodiscard]] auto discovered_topology() -> const std::optional<Topology>&;
#endif
[[nodiscard]] auto discover_acpi(std::uint64_t arena,const Bytes& handoff) -> bool;
}
