// Exercise the real generated BIOS service over the native Session/Uart path.
// Ports model the device only; Aurora owns every editor and presentation step.
#include "../kernel/console-session.hpp"
#ifdef AURORA_GENERATED_UART
#include "../kernel/source-uart.hpp"
#endif
#include <cstdlib>
#include <deque>
#include <functional>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

extern "C" std::uint64_t __au_runtime_console_entry(const aurora::console::ServiceArgument *);

namespace {
using aurora::console::Completion;
using aurora::console::RawSample;
const std::string ready = "AURORA_CONSOLE_READY: BIOS, ASCII, 64-byte lines\r\naurora> ";
const std::string help = "\r\nhelp    Show commands\r\nstatus  Show boot state\r\n"
                         "exit    Close this QEMU session\r\naurora> ";
const std::string status = "\r\nstatus: boot self-tests passed; BIOS serial console; line capacity=64\r\naurora> ";
const std::string rejected = "\r\nLine rejected: too long, non-ASCII/control byte, or UART error.\r\naurora> ";
const std::string exited = "\r\nAURORA_CONSOLE_EXIT\r\n";
std::deque<std::function<void()>> arrivals;
RawSample (*next_sample)(const void *, std::uint64_t);
std::uint64_t (*put_byte)(const void *, std::uint64_t, std::uint64_t);
std::size_t observations{}, output_attempts{}, input_attempts{};
bool output_failed{};

auto need(bool condition, std::string_view message) -> void {
    ++observations;
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
struct Operation {
    bool write;
    unsigned port;
    std::uint8_t byte;
    auto operator==(const Operation &) const -> bool = default;
};
struct Ports {
    static inline std::vector<Operation> trace;
    static inline std::size_t operations{};
    static auto record(bool write, unsigned port, std::uint8_t byte = 0) -> void {
        ++operations;
        if (trace.size() < 64)
            trace.push_back({write, port, byte});
    }
    static auto clear_trace() -> void {
        trace.clear();
        operations = 0;
    }
    static auto expect_trace(std::initializer_list<Operation> expected) -> void {
        need(operations == expected.size() && trace == std::vector<Operation>(expected),
             "UART exact register operation sequence");
    }
    static inline std::deque<std::uint8_t> input;
    static inline std::string output;
    static inline std::uint8_t error{}, error_after_read{}, error_after_write{};
    static inline bool transmit_ready{true};
    static inline std::size_t writes{}, inject_at{}, reads{}, inject_read_at{}, lsr_reads{}, rx_flushes{};
    static inline std::size_t stop_after{std::numeric_limits<std::size_t>::max()};
    static inline std::uint8_t last_fcr{}, expected_trigger{};
    static auto read(unsigned port) -> std::uint8_t {
        record(false, port);
        need(port == 0x3f8 || port == 0x3fa || port == 0x3fd, "unexpected UART register read");
        if (port == 0x3fd) {
            ++lsr_reads;
            const auto value =
                static_cast<std::uint8_t>((transmit_ready ? 0x20 : 0) | (!input.empty() ? 1 : 0) | error);
            error = 0;
            return value;
        }
        if (port == 0x3f8) {
            need(!input.empty(), "UART read beyond its receive FIFO");
            const auto byte = input.front();
            input.pop_front();
            if (++reads == inject_read_at)
                error |= error_after_read;
            return byte;
        }
        return 0;
    }
    static auto write(unsigned port, std::uint8_t value) -> void {
        record(true, port, value);
        need(port == 0x3f8 || port == 0x3fa, "unexpected UART register write");
        if (port == 0x3fa) {
            need(value == (expected_trigger | 3) || value == (expected_trigger | 7), "UART FIFO trigger changed");
            last_fcr = value;
            if (value & 2) {
                input.clear();
                ++rx_flushes;
            }
        }
        if (port == 0x3f8) {
            need(transmit_ready, "UART wrote without transmitter readiness");
            output += static_cast<char>(value);
            if (++writes == inject_at)
                error |= error_after_write;
            if (writes == stop_after)
                transmit_ready = false;
        }
    }
};
class Platform final {
public:
    static auto owns_uart() -> bool {
        return true;
    }
    static auto quiet() -> bool {
        return true;
    }
    static auto wait() -> void {
        need(!arrivals.empty(), "session waited beyond its scripted arrivals");
        auto arrive = std::move(arrivals.front());
        arrivals.pop_front();
        arrive();
    }
    [[noreturn]] static auto fail() -> void {
        std::abort();
    }
};
#ifdef AURORA_GENERATED_UART
using PortService = aurora::hardware::PortRange<Platform, Ports>;
#endif
auto queue(std::string_view bytes) -> void {
    for (const auto byte : bytes)
        Ports::input.push_back(static_cast<std::uint8_t>(byte));
}
auto arrive(std::string text) -> void {
    arrivals.emplace_back([text] {
        queue(text);
    });
}

template <class Device> struct Suite {
    using Uart = Device;
    using Session = aurora::console::Session<Uart, Platform>;
    static inline bool uart_active{};
    static auto reset(std::uint8_t initial_error = 0) -> void {
        if constexpr (requires { Uart::close(); }) {
            if (uart_active)
                Uart::close();
        }
        arrivals.clear();
        Ports::input.clear();
        Ports::output.clear();
        Ports::error_after_read = Ports::error_after_write = 0;
        Ports::error = initial_error;
        Ports::writes = Ports::inject_at = Ports::reads = Ports::inject_read_at = 0;
        Ports::lsr_reads = Ports::rx_flushes = 0;
        Ports::stop_after = std::numeric_limits<std::size_t>::max();
        Ports::transmit_ready = true;
        output_attempts = input_attempts = 0;
        output_failed = false;
        next_sample = Session::next;
        put_byte = Session::put;
        Ports::clear_trace();
        Uart::initialize_input();
        uart_active = true;
        if (initial_error) {
            Ports::expect_trace({{true, 0x3fa, static_cast<std::uint8_t>(Ports::expected_trigger | 7)},
                                 {false, 0x3fd, 0},
                                 {true, 0x3fa, static_cast<std::uint8_t>(Ports::expected_trigger | 3)},
                                 {false, 0x3fa, 0}});
        } else {
            Ports::expect_trace({{true, 0x3fa, static_cast<std::uint8_t>(Ports::expected_trigger | 7)},
                                 {false, 0x3fd, 0},
                                 {false, 0x3fa, 0}});
            need(Ports::last_fcr == (Ports::expected_trigger | 7), "UART session setup did not reset both FIFOs");
        }
    }
    static auto invoke() -> Completion {
        const auto argument = Session::open();
        return Session::close(argument, __au_runtime_console_entry(&argument));
    }
    static auto expect(const std::string &output) -> void {
        need(invoke() == Completion::requested_exit, "UART-backed session did not request exit");
        need(Ports::output == ready + output, "UART-backed exact BIOS transcript");
        need(Ports::input.empty() && arrivals.empty(), "session left unexpected scripted input");
        need(!output_failed && output_attempts <= Ports::output.size(), "successful output accounting");
    }
    static auto run(std::uint8_t trigger) -> void {
        Ports::expected_trigger = trigger;
        for (const auto error : {2, 4, 8, 16, 30}) {
            // The destructive initialization LSR read must preserve copied carry.
            reset(error);
            const auto initialized_damage = Uart::next();
            need(!initialized_damage.present && initialized_damage.byte == 0 && initialized_damage.damaged,
                 "initialization discarded receive damage");
            const auto initialized_clean = Uart::next();
            need(!initialized_clean.present && initialized_clean.byte == 0 && !initialized_clean.damaged,
                 "initialization damage was delivered twice");
            // An echo's TX status polling must not lose a receive error.
            reset();
            arrive("e");
            Ports::inject_at = ready.size() + 1;
            Ports::error_after_write = error;
            arrive("xit\nstatus\nexit\n");
            expect("e" + rejected + "status" + status + "exit" + exited);
            need(Ports::error == 0 && Ports::rx_flushes == 2, "echo damage was not latched and flushed");

            // Multi-byte generated presentation uses the same sticky UART latch.
            reset();
            arrive("help\n");
            Ports::inject_at = ready.size() + 4 + 2 + 2;
            Ports::error_after_write = error;
            arrive("exit\nhelp\nexit\n");
            expect("help" + help + rejected + "help" + help + "exit" + exited);
            need(Ports::error == 0 && Ports::rx_flushes == 2, "presentation damage was lost");

            // Damage discovered after popping a byte discards the queued suffix.
            reset();
            arrive("exit\n");
            Ports::inject_read_at = 1;
            Ports::error_after_read = error;
            arrive("\nexit\n");
            expect(rejected + "exit" + exited);
            need(Ports::rx_flushes == 2, "post-pop error did not flush the receive suffix");

            // Error-only samples reject a partial line even with no RX byte.
            reset();
            arrive("ex");
            arrivals.emplace_back([error] {
                Ports::error = error;
                Uart::text("ex");
            });
            arrive("\nstatus\nexit\n");
            expect("exex" + rejected + "status" + status + "exit" + exited);

            reset();
            arrivals.emplace_back([error] {
                queue("exit\n");
                Ports::error = error;
            });
            arrive("\nstatus\nexit\n");
            expect(rejected + "status" + status + "exit" + exited);
            need(Ports::rx_flushes == 2, "pre-pop error did not discard the untrusted FIFO");

            // Runtime diagnostic output and generated source share one transport.
            // Actual copied-submission/scrub checks live in kernel-program-stream.
            reset();
            arrive("upper");
            arrivals.emplace_back([error] {
                queue(" silently truncated");
                Ports::inject_at = Ports::writes + 3;
                Ports::error_after_write = error;
                Uart::text("AURORA_UEFI_DOMAIN_EVENT: vector=");
                Uart::number(129);
                Uart::text("\r\nAURORA_UEFI_TIMER_QUIET: epoch=1\r\n");
                need(Ports::error == 0 && Ports::input.empty() && Ports::rx_flushes == 2,
                     "diagnostic output lost receive damage or retained unsafe input");
            });
            arrive("\nhelp\nexit\n");
            expect("upperAURORA_UEFI_DOMAIN_EVENT: vector=129\r\nAURORA_UEFI_TIMER_QUIET: epoch=1\r\n" + rejected +
                   "help" + help + "exit" + exited);

            for (const std::string delimiter : {"\n", "\r", "\r\n"}) {
                reset();
                arrive("help" + delimiter + "exit\n");
                Ports::inject_read_at = 5;
                Ports::error_after_read = error;
                arrive(delimiter == "\r\n" ? "\nexit\n" : "exit\n");
                arrive("status\nexit\n");
                expect("help" + rejected + rejected + "status" + status + "exit" + exited);
                need(Ports::rx_flushes == 2, "delimiter damage did not flush the queued next command");
            }
        }

        // Transport observations remain canonical without owning editor state.
        reset();
        Ports::clear_trace();
        auto sample = Uart::next();
        Ports::expect_trace({{false, 0x3fd, 0}});
        need(!sample.present && sample.byte == 0 && !sample.damaged, "empty transport observation");
        Ports::error = 2;
        Ports::clear_trace();
        sample = Uart::next();
        Ports::expect_trace({{false, 0x3fd, 0}, {true, 0x3fa, static_cast<std::uint8_t>(trigger | 3)}});
        need(!sample.present && sample.byte == 0 && sample.damaged, "error-only transport observation");
        sample = Uart::next();
        need(!sample.present && sample.byte == 0 && !sample.damaged, "error-only observation did not clear");
        for (const auto delimiter : {'\r', '\n'}) {
            reset();
            Ports::input.push_back(delimiter);
            Ports::inject_read_at = 1;
            Ports::error_after_read = 8;
            sample = Uart::next();
            need(sample.present && sample.byte == delimiter && sample.damaged, "damaged delimiter observation");
            sample = Uart::next();
            need(!sample.present && sample.byte == 0 && sample.damaged, "damage did not cross delimiter boundary");
            sample = Uart::next();
            need(!sample.present && sample.byte == 0 && !sample.damaged, "delimiter latch did not clear");
        }
        // A non-delimiter consumes post-pop damage rather than poisoning a new line.
        reset();
        queue("ab");
        Ports::inject_read_at = 1;
        Ports::error_after_read = 16;
        Ports::clear_trace();
        sample = Uart::next();
        Ports::expect_trace({{false, 0x3fd, 0},
                             {false, 0x3f8, 0},
                             {false, 0x3fd, 0},
                             {true, 0x3fa, static_cast<std::uint8_t>(trigger | 3)}});
        need(sample.present && sample.byte == 'a' && sample.damaged && Ports::input.empty(),
             "post-pop damage must discard RX only");
        sample = Uart::next();
        need(!sample.present && !sample.damaged && sample.byte == 0, "non-delimiter damage carried twice");
        Ports::clear_trace();
        need(Uart::try_put(255) == aurora::console::PutResult::success, "ready transmitter rejected byte");
        Ports::expect_trace({{false, 0x3fd, 0}, {true, 0x3f8, 255}});
        reset();
        Ports::transmit_ready = false;
        Ports::error = 4;
        need(Uart::try_put('x') == aurora::console::PutResult::timeout, "UART timeout result");
        need(Ports::output.empty() && Ports::lsr_reads == 1000001, "UART bounded transmit polling");
        sample = Uart::next();
        need(!sample.present && sample.byte == 0 && sample.damaged, "timeout polling lost RX damage");
        Ports::transmit_ready = true;
        need(Uart::try_put('y') == aurora::console::PutResult::success && Ports::output == "y",
             "UART transport did not recover after timeout");
        reset();
        Uart::number(UINT64_MAX);
        need(Ports::output == "18446744073709551615" && Ports::lsr_reads >= 20, "maximum diagnostic number");

        const auto successful = ready + "help" + help + "exit" + exited;
        for (const auto stop : {std::size_t{0}, ready.size() + 5}) {
            reset();
            Ports::stop_after = stop;
            Ports::transmit_ready = stop != 0;
            arrive("help\nexit\n");
            need(invoke() == Completion::output_failure, "UART timeout did not stop generated session");
            need(output_failed && output_attempts == stop + 1 && Ports::output == successful.substr(0, stop),
                 "UART timeout retried or changed the successful output prefix");
            need(stop != 0 || input_attempts == 0, "ready timeout consumed input");
        }
        reset();
        arrive("exit\n");
        expect("exit" + exited);
    }
};
} // namespace

extern "C" void __au_runtime_console_next(const void *grant, std::uint64_t generation, RawSample *result) {
    need(!output_failed, "generated session consumed input after UART timeout");
    ++input_attempts;
    *result = next_sample(grant, generation);
}
extern "C" std::uint64_t __au_runtime_console_put(const void *grant, std::uint64_t generation, std::uint64_t byte) {
    need(!output_failed, "generated session retried after UART timeout");
    ++output_attempts;
    const auto result = put_byte(grant, generation, byte);
    output_failed = result == 1;
    return result;
}

#ifdef AURORA_GENERATED_UART
extern "C" std::uint64_t __au_runtime_port_read8(const void *grant, std::uint64_t generation, std::uint64_t offset) {
    return PortService::read8(grant, generation, offset);
}
extern "C" std::uint64_t
__au_runtime_port_write8(const void *grant, std::uint64_t generation, std::uint64_t offset, std::uint64_t byte) {
    return PortService::write8(grant, generation, offset, byte);
}
#endif

auto main() -> int {
#ifdef AURORA_GENERATED_UART
    using One = aurora::console::SourceUart<PortService, Platform>;
    using Fourteen = aurora::console::SourceUart<PortService, Platform, aurora::console::FifoTrigger::fourteen>;
    Suite<One>::run(0);
    One::close();
    Suite<Fourteen>::run(0xc0);
    Fourteen::close();
#else
    Suite<aurora::console::Uart<Ports>>::run(0);
    Suite<aurora::console::Uart<Ports, aurora::console::FifoTrigger::fourteen>>::run(0xc0);
#endif
    std::cout << "PASS: generated BIOS session and shared UART damage/timeout, both FIFO triggers; " << observations
              << " observations\n";
}
