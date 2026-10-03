#pragma once
#include <cstdint>
namespace aurora::hardware {
class Protection final {
public:
    static constexpr std::uint64_t main_stack_bottom = 0x88000;
    static constexpr std::uint64_t main_stack_top = 0x90000;
    static constexpr std::uint64_t entry_stack_bottom = 0x82000;
    static constexpr std::uint64_t entry_stack_top = 0x86000;
    static constexpr std::uint64_t emergency_stack_bottom = 0x7c000;
    static constexpr std::uint64_t emergency_stack_top = 0x80000;
    static constexpr std::uint64_t user_code = 0x1d0000;
    static constexpr std::uint64_t user_stack_bottom = 0x1e0000;
    static constexpr std::uint64_t user_stack_top = 0x1e4000;
    [[nodiscard]] static auto activate() -> bool;
    [[nodiscard]] static auto kernel_root() -> std::uint64_t;
    [[nodiscard]] static auto current_root() -> std::uint64_t;
    [[nodiscard]] static auto kernel_entry(std::uint64_t address) -> std::uint64_t;
    [[nodiscard]] static auto verify() -> bool;
};
}
