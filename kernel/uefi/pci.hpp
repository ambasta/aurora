#pragma once
#include "handoff.hpp"
#include "../pages.hpp"
namespace aurora::uefi {
[[nodiscard]] auto discover_pci(std::uint64_t arena,
                                const Bytes &handoff,
                                std::span<const std::byte> mcfg,
                                unsigned physical_bits,
                                memory::PhysicalPages &pool) -> bool;
}
