#pragma once
#include "handoff.hpp"
namespace aurora::uefi {
// The process image's phase after the payload's own checks: admit the final map
// and boot volume, build the frame allocator and its kernel mappings, run the
// row's frame and export cases, and stop the guest (process.md).
[[noreturn]] auto run_process(std::uint64_t arena, const Bytes &h) -> void;
} // namespace aurora::uefi
