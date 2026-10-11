#include "../kernel/console-line.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <string>
#include <string_view>

namespace {
using aurora::console::Event;
using aurora::console::Line;
using aurora::console::Snapshot;
auto need(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
auto cleared(const Snapshot &snapshot) -> bool {
    return !snapshot.submitted() && snapshot.length() == 0 && snapshot.bytes() == std::array<std::uint8_t, 64>{};
}
auto copied(const Snapshot &snapshot, std::string_view expected) -> void {
    need(snapshot.submitted() && snapshot.length() == expected.size(), "copied submission length");
    const auto bytes = snapshot.bytes();
    for (std::size_t index = 0; index < bytes.size(); ++index) {
        need(bytes[index] == (index < expected.size() ? static_cast<std::uint8_t>(expected[index]) : 0),
             "copied submission content or scrubbed tail");
    }
}
auto feed(Line &line, Snapshot &snapshot, std::string_view bytes) -> Event {
    auto event = Event::ignored;
    for (const auto byte : bytes) {
        event = line.consume(static_cast<std::uint8_t>(byte), &snapshot);
        need(line.length() <= 64, "editor capacity");
        if (event == Event::ignored || event == Event::echo || event == Event::erased || event == Event::rejected)
            need(cleared(snapshot), "non-submission or rejection retained copied bytes");
    }
    return event;
}
} // namespace

auto main() -> int {
    Line line;
    Snapshot snapshot;
    need(cleared(snapshot), "initial snapshot");
    need(feed(line, snapshot, "upper\r") == Event::unknown, "opt-in command changed legacy policy");
    copied(snapshot, "upper");
    need(line.length() == 0, "accepted editor storage reset");
    const auto saved = snapshot;
    need(feed(line, snapshot, "\n") == Event::ignored && cleared(snapshot), "CRLF duplicate submission");
    copied(saved, "upper");
    need(feed(line, snapshot, "\n") == Event::empty, "accepted empty LF");
    copied(snapshot, "");
    need(feed(line, snapshot, "\r") == Event::empty, "accepted empty CR");
    copied(snapshot, "");
    need(feed(line, snapshot, "\n") == Event::ignored && cleared(snapshot), "empty CRLF duplicate");

    need(feed(line, snapshot, "help\n") == Event::help, "legacy help classification");
    copied(snapshot, "help");
    need(feed(line, snapshot, "status\n") == Event::status, "legacy status classification");
    copied(snapshot, "status");
    need(feed(line, snapshot, "exit\n") == Event::exit, "legacy exit classification");
    copied(snapshot, "exit");
    need(feed(line, snapshot, "\b\177azx\b\177 Z\n") == Event::unknown, "editing classification");
    copied(snapshot, "a Z");

    const std::string maximum(64, 'm');
    need(feed(line, snapshot, maximum + "\n") == Event::unknown, "maximum accepted line");
    copied(snapshot, maximum);
    need(feed(line, snapshot, "q\n") == Event::unknown, "short following line");
    copied(snapshot, "q");
    need(feed(line, snapshot, maximum + "\bZ\n") == Event::unknown, "full line remains editable");
    copied(snapshot, std::string(63, 'm') + "Z");
    need(feed(line, snapshot, maximum + "x\b\177exit\r") == Event::rejected,
         "overlong line recovered through backspace");
    need(cleared(snapshot) && line.length() == 0, "rejected overflow snapshot");
    need(feed(line, snapshot, "\nhelp\n") == Event::help, "overflow CRLF recovery");
    copied(snapshot, "help");

    for (unsigned bad = 0; bad <= 255; ++bad) {
        if ((bad >= 32 && bad <= 126) || bad == 8 || bad == 127 || bad == 10 || bad == 13)
            continue;
        need(feed(line, snapshot, "secret") == Event::echo, "invalid-byte prefix");
        need(line.consume(static_cast<std::uint8_t>(bad), &snapshot) == Event::ignored && cleared(snapshot),
             "invalid-byte snapshot");
        need(feed(line, snapshot, "\bhelp\n") == Event::rejected && cleared(snapshot), "invalid-byte rejection");
        need(feed(line, snapshot, "ok\n") == Event::unknown, "invalid-byte recovery");
        copied(snapshot, "ok");
    }
    for (const std::string delimiter : {"\n", "\r", "\r\n"}) {
        need(feed(line, snapshot, "private") == Event::echo, "UART rejection prefix");
        line.reject();
        need(feed(line, snapshot, "\bexit") == Event::ignored && cleared(snapshot), "UART error latch");
        need(feed(line, snapshot, delimiter) == (delimiter == "\r\n" ? Event::ignored : Event::rejected) &&
                 cleared(snapshot),
             "UART error delimiter scrub");
        need(feed(line, snapshot, "new\n") == Event::unknown, "UART error recovery");
        copied(snapshot, "new");
    }

    // Old callers remain opt-out. A copied value may be intentionally retained,
    // but passing it on the next call replaces it rather than appending to it.
    const auto retained = snapshot;
    need(line.consume('h') == Event::echo && line.consume('i') == Event::echo && line.consume('\n') == Event::unknown,
         "legacy consume overload");
    copied(retained, "new");
    need(feed(line, snapshot, "later\n") == Event::unknown, "later submission");
    copied(snapshot, "later");
    snapshot.clear();
    need(cleared(snapshot), "caller-requested snapshot scrub");
    std::cout << "PASS: copied console snapshots, bounded edits, rejection scrub and CRLF\n";
}
