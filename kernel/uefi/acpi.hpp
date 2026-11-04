#pragma once
#include "handoff.hpp"
#include "../pages.hpp"
#ifdef AURORA_UEFI_AP_WORKER
#include "ap-worker-policy.hpp"
#endif
#if defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_GRAPHICAL_CONSOLE) ||   \
    defined(AURORA_PROCESS_FIXTURE)
#include "acpi-policy.hpp"
#endif
namespace aurora::uefi {
#ifdef AURORA_UEFI_AP_WORKER
[[nodiscard]] auto discovered_ap_worker_topology() -> const std::optional<ApWorkerTopology> &;
[[nodiscard]] auto discovered_ap_worker_timer() -> const std::optional<PmTimerAdmission> &;
#endif
#if defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_GRAPHICAL_CONSOLE) ||   \
    defined(AURORA_PROCESS_FIXTURE)
[[nodiscard]] auto discovered_timer_topology() -> const std::optional<TimerTopology> &;
#endif
[[nodiscard]] auto discover_acpi(std::uint64_t arena, const Bytes &handoff, memory::PhysicalPages &pool) -> bool;
} // namespace aurora::uefi
