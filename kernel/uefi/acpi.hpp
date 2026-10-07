#pragma once
#include "handoff.hpp"
#include "../pages.hpp"
#if defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_CONSOLE)
#include "acpi-policy.hpp"
#endif
namespace aurora::uefi {
#if defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_CONSOLE)
[[nodiscard]] auto discovered_topology() -> const std::optional<Topology>&;
#endif
[[nodiscard]] auto discover_acpi(std::uint64_t arena, const Bytes &handoff, memory::PhysicalPages &pool) -> bool;
}
