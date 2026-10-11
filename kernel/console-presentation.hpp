#pragma once
#include "console-line.hpp"
#include "console.hpp"

namespace aurora::console {
enum class Platform {
    bios,
    uefi
};

// Shared presentation only. Input classification remains the existing Aurora
// policy and Line adapter; transport and shutdown authority stay with callers.
template <class Output = hardware::Serial> class Presentation final {
public:
    static auto ready(Platform platform) -> void {
        Output::text(platform == Platform::bios ? "AURORA_CONSOLE_READY: BIOS, ASCII, 64-byte lines\r\naurora> "
                                                : "AURORA_CONSOLE_READY: UEFI, ASCII, 64-byte lines\r\naurora> ");
    }
    [[nodiscard]] static auto render(Event event, std::uint8_t byte, Platform platform) -> bool {
        if (event == Event::ignored) {
            return true;
        }
        if (event == Event::echo) {
            Output::put(byte);
            return true;
        }
        if (event == Event::erased) {
            Output::text("\b \b");
            return true;
        }
        Output::text("\r\n");
        switch (event) {
        case Event::help:
            Output::text("help    Show commands\r\nstatus  Show boot state\r\nexit    Close this QEMU session\r\n");
            break;
        case Event::status:
            Output::text(
                platform == Platform::bios
                    ? "status: boot self-tests passed; BIOS serial console; line capacity=64\r\n"
                    : "status: boot self-tests passed; UEFI serial console; timer-woken polling; line capacity=64\r\n");
            break;
        case Event::unknown:
            Output::text("Unknown command. Type help.\r\n");
            break;
        case Event::rejected:
            Output::text("Line rejected: too long, non-ASCII/control byte, or UART error.\r\n");
            break;
        case Event::exit:
            Output::text("AURORA_CONSOLE_EXIT\r\n");
            return false;
        default:
            break;
        }
        Output::text("aurora> ");
        return true;
    }
};
} // namespace aurora::console
