#pragma once
#include <cstdint>
namespace aurora::hardware {
// Narrow single-BSP xAPIC adapter. No frequency or physical-platform promise.
class Apic final {
public:
    static constexpr std::uint64_t base = 0xfee00000;
    static constexpr std::uint64_t vector = 64;
    [[nodiscard]] static auto mapping() -> std::uint64_t;
    [[nodiscard]] static auto mapping_valid() -> bool;
    [[nodiscard]] static auto initialize() -> bool;
    [[nodiscard]] static auto arm() -> bool;
    [[nodiscard]] static auto acknowledge() -> bool;
    [[nodiscard]] static auto stop() -> bool;
    [[nodiscard]] static auto drain() -> bool;
    [[nodiscard]] static auto pending_test() -> bool;
    [[nodiscard]] static auto drain_interrupt(std::uint64_t instruction, std::uint64_t code, std::uint64_t frame)
        -> bool;
};
} // namespace aurora::hardware
