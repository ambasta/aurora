#pragma once
#include "handoff.hpp"
namespace aurora::uefi {
[[nodiscard]] auto discover_acpi(std::uint64_t arena,const Bytes& handoff) -> bool;
}
