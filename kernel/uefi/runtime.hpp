#pragma once
#include "handoff.hpp"
#ifdef AURORA_UEFI_SNAPSHOT
#include "../pages.hpp"
#endif
namespace aurora::uefi {
#ifdef AURORA_UEFI_SNAPSHOT
[[nodiscard]] auto run_protected(std::uint64_t arena, const Bytes &handoff, memory::PhysicalPages &producer_pool)
    -> bool;
#else
[[nodiscard]] auto run_protected(std::uint64_t arena, const Bytes &handoff) -> bool;
#endif
} // namespace aurora::uefi
