#pragma once
#include "handoff.hpp"

namespace aurora::uefi {
[[noreturn]] auto run_console(std::uint64_t arena, const Bytes& handoff) -> void;
}
