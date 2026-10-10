#pragma once
#include "console.hpp"
#include "console-line.hpp"
#include "console-presentation.hpp"
#include "console-uart.hpp"

namespace aurora::console {
// QEMU PC/16550/PIC transport only. No general device discovery or hardware claim.
class Interactive final {
    using Transport = Uart<>;
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
        Transport::initialize_input(); // Clear FIFOs; receive threshold is one byte.
        Io::write(0x3f9, 1);           // Received-data interrupt only; no transmit IRQ.
    }

public:
    [[noreturn]] static auto run() -> void {
        using hardware::Io;
        Line line;
        initialize_input();
        Presentation<Transport>::ready(Platform::bios);
        for (;;) {
            const auto byte = Transport::poll(line);
            if (!byte) {
                // IF is clear at the receive check. STI's interrupt shadow makes
                // HLT atomic with enabling IRQ4, avoiding a lost-wakeup window.
                asm volatile("sti; hlt; cli" : : : "memory");
                continue;
            }
            if (!Presentation<Transport>::render(line.consume(*byte), *byte, Platform::bios)) {
                Io::write(0x3f9, 0);
                Io::write(0x21, 0xff);
                Io::write(0xf4, 0x10);
                for (;;) {
                    asm volatile("cli; hlt");
                }
            }
        }
    }
};
} // namespace aurora::console
