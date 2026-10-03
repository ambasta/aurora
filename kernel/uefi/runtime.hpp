#pragma once
#include "handoff.hpp"
namespace aurora::uefi {
[[nodiscard]] auto run_protected(std::uint64_t arena,const Bytes& handoff) -> bool;
}
