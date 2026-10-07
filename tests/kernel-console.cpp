#include "../kernel/console-line.hpp"
#include <cstdlib>
#include <iostream>
#include <string_view>

namespace {
using aurora::console::Event;
using aurora::console::Line;
auto need(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}
auto feed(Line& line, std::string_view bytes) -> Event {
    auto event = Event::ignored;
    for (const auto byte : bytes) { event = line.consume(static_cast<std::uint8_t>(byte)); }
    need(line.length() <= 64, "line capacity violated");
    return event;
}
}

auto main() -> int {
    using aurora::console::byte_policy;
    using aurora::console::command_policy;
    for (auto byte = std::uint64_t{0}; byte < 256; ++byte) {
        auto expected = std::uint64_t{5};
        if (byte >= 32 && byte <= 126) { expected = 2; }
        if (byte == 8 || byte == 127) { expected = 1; }
        if (byte == 10 || byte == 13) { expected = 4; }
        need(byte_policy(byte, 0, 0, 0) == expected, "byte classification mismatch");
    }
    need(byte_policy(256, 0, 0, 0) == 0, "out-of-range byte accepted");
    need(byte_policy(65, 65, 0, 0) == 0, "out-of-range length accepted");
    need(byte_policy(65, 0, 2, 0) == 0, "invalid rejection flag accepted");
    need(byte_policy(65, 0, 0, 2) == 0, "invalid CR flag accepted");
    need(byte_policy(65, 64, 0, 0) == 5, "full line accepted another byte");
    need(byte_policy(8, 64, 0, 0) == 3, "full line could not be edited");
    need(byte_policy(8, 64, 1, 0) == 1, "rejected line allowed editing");
    need(byte_policy(10, 0, 0, 1) == 1, "CRLF not suppressed");
    need(command_policy(0, 65) == 0, "oversized command accepted");
    need(command_policy(1886152040, 5) == 0, "command suffix accepted");
    need(command_policy(1886152040 | (std::uint64_t{1} << 63), 4) == 0, "hidden prefix bits accepted");
    Line line;
    need(feed(line, "help\r") == Event::help, "help failed");
    need(feed(line, "\n") == Event::ignored, "CRLF produced a second line");
    need(feed(line, "status\n") == Event::status, "status failed");
    need(feed(line, "exit\r") == Event::exit, "exit failed");
    need(feed(line, "\r") == Event::empty, "empty CR failed");
    need(feed(line, "\n") == Event::ignored, "empty CRLF failed");
    need(feed(line, "\b\177help\b\b\b\bstatus\n") == Event::status, "backspace editing failed");
    need(feed(line, "helx\177p\n") == Event::help, "DEL editing failed");
    need(feed(line, "HELP\n") == Event::unknown, "case-sensitive command changed");
    need(feed(line, "help now\n") == Event::unknown, "arguments were accepted");
    need(feed(line, "statusx\n") == Event::unknown, "command prefix was accepted");
    for (unsigned index = 0; index < 64; ++index) {
        need(line.consume('x') == Event::echo, "64-byte line truncated early");
    }
    need(line.consume('\n') == Event::unknown, "64-byte line rejected");
    for (unsigned index = 0; index < 512; ++index) { static_cast<void>(line.consume('x')); }
    need(feed(line, "\b\177exit\r") == Event::rejected, "overflow suffix escaped rejection");
    need(feed(line, "\nhelp\n") == Event::help, "overflow did not recover at CRLF");
    for (const auto bad : {0, 9, 27, 31, 128, 255}) {
        static_cast<void>(line.consume(static_cast<std::uint8_t>(bad)));
        need(feed(line, "exit\n") == Event::rejected, "invalid byte did not reject whole line");
        need(feed(line, "status\n") == Event::status, "invalid-byte recovery failed");
    }
    static_cast<void>(feed(line, "ex"));
    line.reject();
    need(feed(line, "it\n") == Event::rejected, "UART error did not reject line");
    need(feed(line, "exit\n") == Event::exit, "UART error did not recover");
    std::cout << "PASS: console policy and bounded line editor\n";
}
