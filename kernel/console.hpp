#pragma once
#include "output-format.hpp"
#ifdef AURORA_INTERACTIVE_CONSOLE
#include "interactive-console.hpp"
#endif
namespace aurora::hardware {
using Byte = unsigned char;
using Port = unsigned short;
class Io final {
public:
    static auto write(Port port, Byte value) -> void {
        asm volatile("outb %0, %1" : : "a"(value), "Nd"(port) : "memory");
    }
    static auto read(Port port) -> Byte {
        Byte result;
        asm volatile("inb %1, %0" : "=a"(result) : "Nd"(port) : "memory");
        return result;
    }
};
class Serial final {
public:
    static auto initialize() -> void {
        Io::write(0x3f9, 0);
        Io::write(0x3fb, 0x80);
        Io::write(0x3f8, 1);
        Io::write(0x3f9, 0);
        Io::write(0x3fb, 3);
        Io::write(0x3fa, 0xc7);
        Io::write(0x3fc, 0x0b);
    }
#ifdef AURORA_INTERACTIVE_CONSOLE
    // Keep one BIOS diagnostic routing boundary instead of cloning the owner
    // check and boot UART poll into every literal output loop. The fixed BIOS
    // image budget and mixed-stack gate still apply to the resulting graph.
    [[gnu::noinline, gnu::noclone, gnu::noipa]]
#endif
    static auto put(Byte value) -> void {
#ifdef AURORA_INTERACTIVE_CONSOLE
        // Every active BIOS diagnostic shares the Aurora receive-error carry.
        if (console::Interactive::owns_uart()) {
            console::Interactive::put(value);
            return;
        }
#endif
        // A broken serial device must not permanently stall kernel boot.
        for (auto remaining = 1000000; remaining > 0; --remaining) {
            if ((Io::read(0x3fd) & 0x20) != 0) {
                Io::write(0x3f8, value);
                return;
            }
        }
    }
#ifdef AURORA_INTERACTIVE_CONSOLE
    [[gnu::noinline, gnu::noclone, gnu::noipa]]
#endif
    static auto text(std::string_view value) -> void {
        console::OutputFormat<Serial, unsigned long long>::text(value);
    }
#ifdef AURORA_INTERACTIVE_CONSOLE
    [[gnu::noinline, gnu::noclone, gnu::noipa]]
#endif
    static auto number(unsigned long long value) -> void {
        console::OutputFormat<Serial, unsigned long long>::number(value);
    }
};
} // namespace aurora::hardware
