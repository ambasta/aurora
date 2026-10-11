#include "../kernel/console-presentation.hpp"
#include <cstdlib>
#include <iostream>
#include <string>

namespace {
struct Output {
    static inline std::string text_value;
    static auto text(std::string_view value) -> void {
        text_value += value;
    }
    static auto put(std::uint8_t byte) -> void {
        text_value += static_cast<char>(byte);
    }
};
using Display = aurora::console::Presentation<Output>;
using aurora::console::Event;
using aurora::console::Platform;
unsigned observations{};
auto need(bool condition) -> void {
    ++observations;
    if (!condition) {
        std::abort();
    }
}
auto render(Event event, std::uint8_t byte = 0) -> std::string {
    Output::text_value.clear();
    need(Display::render(event, byte, Platform::bios));
    return Output::text_value;
}
} // namespace
int main() {
    for (auto platform : {Platform::bios, Platform::uefi}) {
        Output::text_value.clear();
        Display::ready(platform);
        need(Output::text_value == (platform == Platform::bios
                                        ? "AURORA_CONSOLE_READY: BIOS, ASCII, 64-byte lines\r\naurora> "
                                        : "AURORA_CONSOLE_READY: UEFI, ASCII, 64-byte lines\r\naurora> "));
        Output::text_value.clear();
        need(Display::render(Event::status, 0, platform));
        need(Output::text_value ==
             (platform == Platform::bios
                  ? "\r\nstatus: boot self-tests passed; BIOS serial console; line capacity=64\r\naurora> "
                  : "\r\nstatus: boot self-tests passed; UEFI serial console; timer-woken polling; "
                    "line capacity=64\r\naurora> "));
        Output::text_value.clear();
        need(!Display::render(Event::exit, 0, platform));
        need(Output::text_value == "\r\nAURORA_CONSOLE_EXIT\r\n");
    }
    need(render(Event::ignored).empty());
    need(render(Event::erased) == "\b \b");
    need(render(Event::empty) == "\r\naurora> ");
    need(render(Event::unknown) == "\r\nUnknown command. Type help.\r\naurora> ");
    need(render(Event::rejected) == "\r\nLine rejected: too long, non-ASCII/control byte, or UART error.\r\naurora> ");
    need(render(Event::help) == "\r\nhelp    Show commands\r\nstatus  Show boot state\r\n"
                                "exit    Close this QEMU session\r\naurora> ");
    for (unsigned byte = 32; byte <= 126; ++byte) {
        need(render(Event::echo, byte) == std::string(1, static_cast<char>(byte)));
    }
    std::cout << "PASS: shared console presentation " << observations << " observations\n";
}
