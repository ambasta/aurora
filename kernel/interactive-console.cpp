#include "interactive-console.hpp"
#include "console-session.hpp"
#include "source-uart.hpp"
#include "console.hpp"

namespace aurora::console {
namespace {
using hardware::Io;
bool ready{}, waiting{}, owned{};

[[nodiscard]] auto irq_off() -> bool {
    std::uint64_t flags;
    asm volatile("pushfq; popq %0" : "=r"(flags));
    return (flags & 0x200) == 0;
}

[[noreturn]] auto stop(std::uint8_t result) -> void {
    asm volatile("cli" : : : "memory");
    // Authority failure must perform no target-UART I/O.
    Io::write(0x21, 0xff);
    ready = false;
    Io::write(0xf4, result);
    for (;;) {
        asm volatile("cli; hlt");
    }
}

class Platform final {
public:
    [[nodiscard]] static auto quiet() -> bool {
        return ready && !waiting && irq_off();
    }
    [[nodiscard]] static auto owns_uart() -> bool {
        return owned;
    }
    static auto wait() -> void {
        if (!quiet()) {
            fail();
        }
        waiting = true;
        // IF is clear at the receive check. STI's interrupt shadow makes HLT
        // atomic with enabling IRQ4. The IRQ only acknowledges the PIC and
        // resumes this exact synchronous frame; it never calls the source session.
        asm volatile("sti; hlt; cli" : : : "memory");
        waiting = false;
        if (!quiet()) {
            fail();
        }
    }
    [[noreturn]] static auto fail() -> void {
        // A transport/authority failure cannot depend on the failed UART.
        stop(0x11);
    }
};
using PortService = hardware::Com1UartGrant<Platform>;
using Transport = SourceUart<PortService, Platform>;
using Service = Session<Transport, Platform>;

auto initialize_input() -> void {
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
    Io::write(0x3f9, 1); // Trusted boot transport enables RX only, while IF remains clear.
    ready = true;
    owned = true; // Exclusive fixed COM1 admission follows trusted setup.
    Transport::initialize_input();
}
} // namespace

auto port_read(const void *, std::uint64_t, std::uint64_t) -> std::uint64_t asm("__au_runtime_port_read8");
auto port_read(const void *grant, std::uint64_t generation, std::uint64_t offset) -> std::uint64_t {
    return PortService::read8(grant, generation, offset);
}
auto port_write(const void *, std::uint64_t, std::uint64_t, std::uint64_t) -> std::uint64_t
    asm("__au_runtime_port_write8");
auto port_write(const void *grant, std::uint64_t generation, std::uint64_t offset, std::uint64_t value)
    -> std::uint64_t {
    return PortService::write8(grant, generation, offset, value);
}
auto Interactive::owns_uart() -> bool {
    return owned;
}
auto Interactive::put(std::uint8_t byte) -> void {
    Transport::put(byte);
}
[[noreturn]] auto Interactive::fail() -> void {
    Platform::fail();
}

auto service_entry(const ServiceArgument *) -> std::uint64_t asm("__au_runtime_console_entry");
auto service_next(const void *, std::uint64_t, RawSample *) -> void asm("__au_runtime_console_next");
auto service_next(const void *grant, std::uint64_t generation, RawSample *output) -> void {
    *output = Service::next(grant, generation);
}
auto service_put(const void *, std::uint64_t, std::uint64_t) -> std::uint64_t asm("__au_runtime_console_put");
auto service_put(const void *grant, std::uint64_t generation, std::uint64_t byte) -> std::uint64_t {
    return Service::put(grant, generation, byte);
}

[[noreturn]] auto Interactive::run() -> void {
    initialize_input();
    const auto argument = Service::open();
    const auto completion = Service::close(argument, service_entry(&argument));
    if (!Platform::quiet()) {
        Platform::fail();
    }
    Transport::close();
    owned = false; // Port authority was revoked before native transport teardown.
    Io::write(0x3f9, 0);
    stop(completion == Completion::requested_exit ? 0x10 : 0x11);
}
} // namespace aurora::console
