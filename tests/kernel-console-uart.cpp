#include "../kernel/console-uart.hpp"
#include "../kernel/console-presentation.hpp"
#include <cstdlib>
#include <deque>
#include <iostream>
#include <string>

namespace {
using aurora::console::Event;
using aurora::console::Line;
struct Ports {
    static inline std::deque<std::uint8_t> input;
    static inline std::string output;
    static inline std::uint8_t error{}, error_after_read{}, error_after_write{};
    static inline unsigned writes{}, inject_at{}, lsr_reads{}, rx_flushes{};
    static inline std::uint8_t last_fcr{}, expected_trigger{};
    static auto read(unsigned port) -> std::uint8_t {
        if (port == 0x3fd) {
            ++lsr_reads;
            const auto value = static_cast<std::uint8_t>(0x20 | (!input.empty() ? 1 : 0) | error);
            error = 0;
            return value;
        }
        if (port == 0x3f8) {
            if (input.empty()) { std::abort(); }
            const auto byte = input.front(); input.pop_front();
            error |= error_after_read; error_after_read = 0;
            return byte;
        }
        return 0;
    }
    static auto write(unsigned port, std::uint8_t value) -> void {
        if (port == 0x3fa) {
            if (value != (expected_trigger | 3) && value != (expected_trigger | 7)) { std::abort(); }
            last_fcr = value;
            if (value & 2) { input.clear(); ++rx_flushes; }
        }
        if (port == 0x3f8) {
            output += static_cast<char>(value);
            if (++writes == inject_at) { error |= error_after_write; }
        }
    }
};
template<class Device>
struct Suite {
    using Uart = Device;
    using Display = aurora::console::Presentation<Uart>;
    static inline unsigned observations{};
    static auto need(bool condition) -> void { ++observations; if (!condition) { std::abort(); } }
    static auto reset() -> void {
        Ports::input.clear(); Ports::output.clear(); Ports::error = 0; Ports::error_after_read = 0;
        Ports::error_after_write = 0; Ports::writes = 0; Ports::inject_at = 0;
        Ports::lsr_reads = 0; Ports::rx_flushes = 0;
        Uart::initialize_input(); need(Ports::last_fcr == (Ports::expected_trigger | 7));
    }
    static auto queue(std::string_view bytes) -> void {
        for (const auto byte : bytes) { Ports::input.push_back(static_cast<std::uint8_t>(byte)); }
    }
    static auto prefix(Line& line, std::string_view bytes) -> void {
        for (const auto byte : bytes) { static_cast<void>(line.consume(static_cast<std::uint8_t>(byte))); }
    }
    static auto drain(Line& line) -> Event {
        auto result = Event::ignored;
        while (const auto byte = Uart::poll(line)) { result = line.consume(*byte); }
        return result;
    }
    static auto command(Line& line, std::string_view text, Event expected) -> void {
        queue(text); need(drain(line) == expected);
    }

    static auto run(std::uint8_t expected_trigger) -> unsigned {
        Ports::expected_trigger = expected_trigger;
        for (const auto error : {2, 4, 8, 16, 30}) {
            {
                reset(); Line line; prefix(line, "e"); Ports::error = error; Uart::put('e');
                need(Ports::error == 0 && Ports::output == "e");
                command(line, "xit\n", Event::rejected); command(line, "status\n", Event::status);
            }
            {
                reset(); Line line; Ports::inject_at = 2; Ports::error_after_write = error;
                need(Display::render(Event::help, 0, aurora::console::Platform::uefi));
                need(Ports::error == 0);
                command(line, "exit\n", Event::rejected); command(line, "help\n", Event::help);
            }
            {
                reset(); Line line; queue("exit\n"); Ports::error_after_read = error;
                need(drain(line) == Event::ignored); need(Ports::input.empty() && Ports::rx_flushes == 2);
                command(line, "\n", Event::rejected); command(line, "exit\n", Event::exit);
            }
            {
                reset(); Line line; prefix(line, "ex"); Ports::error = error; Uart::text("ex");
                need(!Uart::poll(line)); command(line, "\n", Event::rejected); command(line, "status\n", Event::status);
            }
            {
                reset(); Line line; queue("exit\n"); Ports::error = error;
                need(!Uart::poll(line)); need(Ports::input.empty() && Ports::rx_flushes == 2);
                command(line, "\n", Event::rejected); command(line, "status\n", Event::status);
            }
            {
                // Runtime trace TX can observe and clear a receive error while
                // a protected command owns the CPU. The next copied submission
                // must still reject; input and diagnostics share one instance.
                using RuntimeTrace = Uart;
                using ProgramInput = Uart;
                reset(); Line line; aurora::console::Snapshot snapshot;
                prefix(line, "upper"); queue(" silently truncated");
                Ports::inject_at = 3; Ports::error_after_write = error;
                RuntimeTrace::text("AURORA_UEFI_DOMAIN_EVENT: vector="); RuntimeTrace::number(129);
                RuntimeTrace::text("\r\nAURORA_UEFI_TIMER_QUIET: epoch=1\r\n");
                need(Ports::error == 0 && Ports::input.empty() && Ports::rx_flushes == 2);
                need(!ProgramInput::poll(line));
                queue("\n"); const auto delimiter = ProgramInput::poll(line);
                need(delimiter && line.consume(*delimiter, &snapshot) == Event::rejected);
                need(!snapshot.submitted() && snapshot.length() == 0);
                for (const auto byte : snapshot.bytes()) need(byte == 0);
                command(line, "help\n", Event::help);
            }
            for (const std::string delimiter : {"\n", "\r", "\r\n"}) {
                reset(); Line line; prefix(line, "help"); queue(delimiter + "exit\n"); Ports::error_after_read = error;
                const auto byte = Uart::poll(line);
                need(byte && *byte == static_cast<std::uint8_t>(delimiter.front()));
                need(Ports::input.empty()); need(line.consume(*byte) == Event::rejected);
                need(!Uart::poll(line));
                command(line, (delimiter == "\r\n" ? "\nexit\n" : "exit\n"), Event::rejected);
                command(line, "status\n", Event::status);
            }
        }
        reset(); Line line; command(line, "status\n", Event::status);
        Uart::number(UINT64_MAX); need(Ports::output == "18446744073709551615"); need(Ports::lsr_reads >= 20);
        return observations;
    }

};
}

int main() {
    using One = aurora::console::Uart<Ports>;
    using Fourteen = aurora::console::Uart<Ports, aurora::console::FifoTrigger::fourteen>;
    const auto one = Suite<One>::run(0);
    const auto fourteen = Suite<Fourteen>::run(0xc0);
    std::cout << "PASS: shared console UART " << one << "+" << fourteen << " observations\n";
}
