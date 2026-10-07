#pragma once

#include "../pages.hpp"

#include <cstdint>

namespace aurora::uefi {
[[nodiscard]] bool run_owned_bytes(std::uint64_t arena, memory::PhysicalPages &pool) noexcept;
}
