// The linked production BIOS service owns editing, command recognition and
// presentation. This host supplies only copied transport observations and bytes.
#include "../kernel/console-session.hpp"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

extern "C" std::uint64_t __au_runtime_console_entry(const aurora::console::ServiceArgument *);

namespace {
using aurora::console::Completion;
using aurora::console::Sample;
const std::string ready = "AURORA_CONSOLE_READY: BIOS, ASCII, 64-byte lines\r\naurora> ";
const std::string help = "\r\nhelp    Show commands\r\nstatus  Show boot state\r\n"
                         "exit    Close this QEMU session\r\naurora> ";
const std::string status = "\r\nstatus: boot self-tests passed; BIOS serial console; line capacity=64\r\naurora> ";
const std::string unknown = "\r\nUnknown command. Type help.\r\naurora> ";
const std::string rejected = "\r\nLine rejected: too long, non-ASCII/control byte, or UART error.\r\naurora> ";
const std::string exited = "\r\nAURORA_CONSOLE_EXIT\r\n";
constexpr auto unlimited = std::numeric_limits<std::size_t>::max();
std::vector<Sample> samples;
std::vector<std::size_t> input_at_write;
std::size_t input_index{}, output_attempts{}, output_limit{unlimited}, waits{}, observations{};
std::string transcript;

auto need(bool condition, std::string_view message) -> void {
    ++observations;
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
class Transport final {
public:
    static auto next() -> Sample {
        need(output_attempts <= output_limit, "session consumed input after output failure");
        need(input_index < samples.size(), "session consumed beyond supplied input");
        return samples[input_index++];
    }
    static auto try_put(std::uint8_t byte) -> aurora::console::PutResult {
        need(output_attempts <= output_limit, "session retried after output failure");
        input_at_write.push_back(input_index);
        if (output_attempts++ == output_limit)
            return aurora::console::PutResult::timeout;
        transcript += static_cast<char>(byte);
        return aurora::console::PutResult::success;
    }
};
class Platform final {
public:
    static auto quiet() -> bool {
        return true;
    }
    static auto wait() -> void {
        ++waits;
    }
    [[noreturn]] static auto fail() -> void {
        std::abort();
    }
};
using Session = aurora::console::Session<Transport, Platform>;

auto append(std::string_view text) -> void {
    for (const auto byte : text)
        samples.push_back({true, static_cast<std::uint8_t>(byte), false});
}
auto script(std::string_view text, std::size_t limit = unlimited) -> void {
    samples.clear();
    input_at_write.clear();
    input_index = output_attempts = waits = 0;
    output_limit = limit;
    transcript.clear();
    append(text);
}
auto run() -> Completion {
    const auto argument = Session::open();
    const auto before = argument;
    const auto result = __au_runtime_console_entry(&argument);
    need(argument.grant == before.grant && argument.generation == before.generation,
         "service changed its borrowed argument");
    return Session::close(argument, result);
}
auto expect(std::string_view text, const std::string &expected) -> void {
    script(text);
    need(run() == Completion::requested_exit, "session did not request exit");
    need(transcript == ready + expected, "exact BIOS transcript");
    need(input_index == samples.size() && output_attempts == transcript.size(), "session input/output boundary");
}
} // namespace

extern "C" void
__au_runtime_console_next(const void *grant, std::uint64_t generation, aurora::console::RawSample *result) {
    *result = Session::next(grant, generation);
}
extern "C" std::uint64_t __au_runtime_console_put(const void *grant, std::uint64_t generation, std::uint64_t byte) {
    return Session::put(grant, generation, byte);
}

auto main() -> int {
    expect("help\r\nstatus\nexit\n", "help" + help + "status" + status + "exit" + exited);
    expect("\b\177\r\n\nexit\r", "\r\naurora> \r\naurora> exit" + exited);
    expect("helx\177p\nexit\n", "helx\b \bp" + help + "exit" + exited);
    expect("help\b\b\b\bstatus\nexit\n", "help\b \b\b \b\b \b\b \bstatus" + status + "exit" + exited);
    expect("HELP\nhelp now\nstatusx\nexit \nexit\n",
           "HELP" + unknown + "help now" + unknown + "statusx" + unknown + "exit " + unknown + "exit" + exited);
    // This checks the BIOS consumer's exact echo. Shared Line64's exhaustive
    // invalid-byte and copied-submission cases remain in console_service.py and
    // kernel-program-stream.cpp; no native editor/snapshot implementation remains.
    for (unsigned byte = 32; byte <= 126; ++byte) {
        const std::string character(1, static_cast<char>(byte));
        expect(character + "\nexit\n", character + unknown + "exit" + exited);
    }
    const std::string maximum(64, 'x');
    expect(maximum + "\nq\nexit\n", maximum + unknown + "q" + unknown + "exit" + exited);
    expect(maximum + "\bZ\nexit\n", maximum + "\b \bZ" + unknown + "exit" + exited);
    expect(std::string(512, 'x') + "\b\177exit\r\nhelp\nexit\n", maximum + rejected + "help" + help + "exit" + exited);
    for (const unsigned byte : {0U, 9U, 27U, 31U, 128U, 255U}) {
        const auto input = "ex" + std::string(1, static_cast<char>(byte)) + "\b\177it\r\nstatus\nexit\n";
        expect(input, "ex" + rejected + "status" + status + "exit" + exited);
    }
    for (const Sample damage : {Sample{false, 0, true}, {true, 'x', true}}) {
        script("ex");
        samples.push_back(damage);
        append("\b\177it\nstatus\nexit\n");
        need(run() == Completion::requested_exit &&
                 transcript == ready + "ex" + rejected + "status" + status + "exit" + exited,
             "copied damage did not reject the complete line");
    }
    for (const auto delimiter : {'\r', '\n'}) {
        script("exit");
        samples.push_back({true, static_cast<std::uint8_t>(delimiter), true});
        samples.push_back({false, 0, true});
        append("exit\nexit\n");
        need(run() == Completion::requested_exit &&
                 transcript == ready + "exit" + rejected + rejected + "exit" + exited,
             "delimiter damage did not poison both lines");
    }
    script("help\r");
    samples.push_back({true, '\n', true});
    append("exit\nexit\n");
    need(run() == Completion::requested_exit && transcript == ready + "help" + help + rejected + "exit" + exited,
         "damaged suppressed LF lost rejection");
    script("");
    samples.insert(samples.end(), 3, {false, 0, false});
    append("exit\n");
    need(run() == Completion::requested_exit && waits == 3 && transcript == ready + "exit" + exited,
         "idle samples changed presentation or bypassed the session wait");
    expect("exit\r", "exit" + exited);
    expect("\nexit\n", "\r\naurora> exit" + exited);

    // Every output position of every BIOS event is a failure point. Compare
    // independent exact output and input boundaries, rather than replaying state.
    const std::string input = "\nhelx\bp\r\nstatus\nx\n" + std::string(1, '\0') + "exit\nexit\n";
    const std::string expected =
        ready + "\r\naurora> helx\b \bp" + help + "status" + status + "x" + unknown + rejected + "exit" + exited;
    script(input);
    need(run() == Completion::requested_exit && transcript == expected, "output-failure baseline");
    const auto consumed_at_write = input_at_write;
    for (std::size_t position = 0; position < expected.size(); ++position) {
        script(input, position);
        need(run() == Completion::output_failure, "timeout did not close the session");
        need(transcript == expected.substr(0, position) && output_attempts == position + 1,
             "timeout changed its prefix or attempted another output byte");
        need(input_index == consumed_at_write[position], "timeout consumed input beyond the failed write");
    }
    // An output failure also releases the native grant and all Aurora editor state.
    expect("exit\n", "exit" + exited);
    std::cout << "PASS: generated BIOS console transcript, editing, damage and " << expected.size()
              << " timeout prefixes; " << observations << " observations\n";
}
