#pragma once
#include "handoff.hpp"
namespace aurora::uefi {
// UNQUALIFIED source-only profile; separate linked image/stack admission required.
[[noreturn]] auto graphical_console_fault() -> void;
[[noreturn]] auto run_graphical_console(std::uint64_t arena, const Bytes &handoff) -> void;
} // namespace aurora::uefi
