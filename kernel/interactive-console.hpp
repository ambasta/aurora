#pragma once
#include "console.hpp"
#include "console-line.hpp"

namespace aurora::console {
// QEMU PC/16550/PIC transport only. No general device discovery or hardware claim.
class Interactive final {
    static auto initialize_input() -> void {
        using hardware::Io;
        asm volatile("cli" : : : "memory");
        Io::write(0x3f9, 0);
        Io::write(0x21, 0xff);
        Io::write(0xa1, 0xff);
        Io::write(0x20, 0x11);
        Io::write(0xa0, 0x11);
        Io::write(0x21, 32);
        Io::write(0xa1, 40);
        Io::write(0x21, 4);
        Io::write(0xa1, 2);
        Io::write(0x21, 1);
        Io::write(0xa1, 1);
        Io::write(0x21, 0xef);
        Io::write(0xa1, 0xff);
        Io::write(0x3fa, 0x07); // Clear FIFOs; receive interrupt threshold is one byte.
        static_cast<void>(Io::read(0x3fd));
        static_cast<void>(Io::read(0x3fa));
        Io::write(0x3f9, 1); // Received-data interrupt only; no transmit IRQ.
    }

public:
    [[noreturn]] static auto run() -> void {
        using hardware::Io;
        using hardware::Serial;
        Line line;
        initialize_input();
        Serial::text("AURORA_CONSOLE_READY: BIOS, ASCII, 64-byte lines\r\naurora> ");
        for (;;) {
            const auto status = Io::read(0x3fd);
            if ((status & 0x1e) != 0) { line.reject(); }
            if ((status & 1) == 0) {
                // IF is clear at the receive check. STI's interrupt shadow makes
                // HLT atomic with enabling IRQ4, avoiding a lost-wakeup window.
                asm volatile("sti; hlt; cli" : : : "memory");
                continue;
            }
            const auto byte = Io::read(0x3f8);
            const auto event = line.consume(byte);
            if (event == Event::ignored) { continue; }
            if (event == Event::echo) {
                Serial::put(byte);
                continue;
            }
            if (event == Event::erased) {
                Serial::text("\b \b");
                continue;
            }
            Serial::text("\r\n");
            switch (event) {
            case Event::help:
                Serial::text("help    Show commands\r\nstatus  Show boot state\r\nexit    Close this QEMU session\r\n");
                break;
            case Event::status:
                Serial::text("status: boot self-tests passed; BIOS serial console; line capacity=64\r\n");
                break;
            case Event::unknown:
                Serial::text("Unknown command. Type help.\r\n");
                break;
            case Event::rejected:
                Serial::text("Line rejected: too long, non-ASCII/control byte, or UART error.\r\n");
                break;
            case Event::exit:
                Serial::text("AURORA_CONSOLE_EXIT\r\n");
                Io::write(0x3f9, 0);
                Io::write(0x21, 0xff);
                Io::write(0xf4, 0x10);
                for (;;) { asm volatile("cli; hlt"); }
            default:
                break;
            }
            Serial::text("aurora> ");
        }
    }
};
}
