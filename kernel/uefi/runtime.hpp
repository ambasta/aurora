#pragma once
#include "handoff.hpp"
#if defined(AURORA_UEFI_SNAPSHOT) || (defined(AURORA_BLOCKING_CALL) && !defined(AURORA_FILE_CALL))
#include "../pages.hpp"
#endif
namespace aurora::uefi {
#if defined(AURORA_UEFI_SNAPSHOT) || (defined(AURORA_BLOCKING_CALL) && !defined(AURORA_FILE_CALL))
[[nodiscard]] auto run_protected(std::uint64_t arena, const Bytes &handoff, memory::PhysicalPages &producer_pool)
    -> bool;
#else
[[nodiscard]] auto run_protected(std::uint64_t arena, const Bytes &handoff) -> bool;
#endif
} // namespace aurora::uefi
