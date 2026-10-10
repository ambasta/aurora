#pragma once
#include "pages.hpp"
#include <cstdint>
namespace aurora::user {
class Scheduler final {
public:
    [[nodiscard]] static auto run(memory::PhysicalPages &pages) -> bool;
    // -1: unclaimed; 0: validated drain IRET; 1: return to privileged continuation.
    [[nodiscard]] static auto
    interrupt(std::uint64_t vector, std::uint64_t code, std::uint64_t instruction, std::uint64_t frame) -> int;
};
} // namespace aurora::user
