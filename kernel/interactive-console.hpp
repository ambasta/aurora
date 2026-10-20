#pragma once
#include <cstdint>

namespace aurora::console {
// QEMU PC/16550/PIC transport only. The source session owns editing and output.
class Interactive final {
public:
    [[noreturn]] static auto run() -> void;
    [[nodiscard]] static auto owns_uart() -> bool;
    static auto put(std::uint8_t byte) -> void;
    [[noreturn]] static auto fail() -> void;
};
} // namespace aurora::console
