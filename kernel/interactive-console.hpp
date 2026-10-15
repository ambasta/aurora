#pragma once

namespace aurora::console {
// QEMU PC/16550/PIC transport only. The source session owns editing and output.
class Interactive final {
public:
    [[noreturn]] static auto run() -> void;
};
} // namespace aurora::console
