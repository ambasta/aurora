#pragma once
#include "handoff.hpp"
#if defined(AURORA_SNAPSHOT_FIXTURE) || defined(AURORA_TEXT_FIXTURE)
#include "../pages.hpp"
#endif
namespace aurora::uefi {
#if defined(AURORA_SNAPSHOT_FIXTURE) || defined(AURORA_TEXT_FIXTURE)
[[nodiscard]] auto run_protected(std::uint64_t arena, const Bytes &handoff, memory::PhysicalPages &producer_pool)
    -> bool;
#else
[[nodiscard]] auto run_protected(std::uint64_t arena, const Bytes &handoff) -> bool;
#endif
} // namespace aurora::uefi
