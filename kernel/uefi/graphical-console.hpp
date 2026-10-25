#pragma once
#include "handoff.hpp"
namespace aurora::uefi {
// UNQUALIFIED source-only profile; separate linked image/stack admission required.
// `capture` is the display fixture row's mode, which decides the fault's exit.
[[noreturn]] auto graphical_console_fault(bool capture) -> void;
[[noreturn]] auto run_graphical_console(std::uint64_t arena, const Bytes &handoff) -> void;
} // namespace aurora::uefi
