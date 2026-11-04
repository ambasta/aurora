#pragma once
#include "handoff.hpp"
#include "../pages.hpp"
namespace aurora::uefi {
[[nodiscard]] auto run_ap_worker(std::uint64_t arena, const Bytes &handoff, memory::PhysicalPages &pool) -> bool;
}
