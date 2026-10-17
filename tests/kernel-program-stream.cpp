#include "../kernel/program-stream.hpp"
#include "../kernel/program-input.hpp"
#include <array>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <limits>
#include <string>
#include <string_view>
#include <type_traits>
#include <vector>

extern "C" void __au_runtime_program_input(const void *, void *);
extern "C" std::uint64_t __au_runtime_program_response(const void *);

namespace {
using aurora::program::Stream;
using aurora::program::StreamBytes;
constexpr auto maximum = std::numeric_limits<std::uint64_t>::max();
static_assert(!std::is_copy_constructible_v<Stream> && !std::is_move_constructible_v<Stream>);
auto need(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

// Reuse both linked production turns and the existing grant with scripted I/O.
using aurora::program::Response;
using aurora::program::Submission;
using Action = Submission::Action;
using ResponseKind = Response::Kind;
std::vector<aurora::console::Sample> samples;
std::size_t sample_index{}, output_attempts{}, output_limit = std::numeric_limits<std::size_t>::max();
bool response_active{};
std::string transcript;
class InputPorts final {
public:
    static auto next() -> aurora::console::Sample {
        need(!response_active, "response consumed input");
        need(output_attempts <= output_limit, "Console turn consumed input after output failure");
        need(sample_index < samples.size(), "reader consumed beyond supplied input");
        return samples[sample_index++];
    }
    static auto try_put(std::uint8_t byte) -> aurora::console::PutResult {
        need(output_attempts <= output_limit, "Console turn retried after output failure");
        if (output_attempts++ == output_limit)
            return aurora::console::PutResult::timeout;
        transcript += static_cast<char>(byte);
        return aurora::console::PutResult::success;
    }
};
class InputPlatform final {
public:
    static auto quiet() -> bool {
        return true;
    }
    static auto wait() -> void {
    }
    [[noreturn]] static auto fail() -> void {
        std::abort();
    }
};
using InputSession = aurora::console::Session<InputPorts, InputPlatform>;
auto script(std::string_view text, std::size_t limit = std::numeric_limits<std::size_t>::max()) -> void {
    samples.clear();
    for (const auto byte : text)
        samples.push_back({true, static_cast<std::uint8_t>(byte), false});
    sample_index = output_attempts = 0;
    output_limit = limit;
    transcript.clear();
}
auto read_input(std::uint64_t after_cr = 0) -> Submission {
    const aurora::program::SubmissionArgument argument{InputSession::open(), after_cr};
    const auto before = argument;
    alignas(16) std::array<std::byte, 120> storage;
    storage.fill(std::byte{0xa5});
    __au_runtime_program_input(&argument, storage.data() + 16);
    InputSession::release(argument.console);
    need(std::memcmp(&argument, &before, sizeof(argument)) == 0, "reader changed its borrowed argument");
    for (std::size_t index = 0; index < 16; ++index)
        need(storage[index] == std::byte{0xa5} && storage[104 + index] == std::byte{0xa5},
             "reader result exceeded its copied record");
    Submission result;
    std::memcpy(result.data(), storage.data() + 16, sizeof(result));
    need(result.valid(), "reader returned a noncanonical submission");
    return result;
}
auto expect_input(const Submission &result, std::string_view expected, Action action, std::uint64_t carry) -> void {
    need(result.length() == expected.size() && result.action() == action && result.after_cr() == carry,
         "reader count/action/CR carry");
    for (std::size_t index = 0; index < result.bytes().size(); ++index)
        need(result.bytes()[index] == (index < expected.size() ? static_cast<std::uint8_t>(expected[index]) : 0),
             "reader copied bytes and zero suffix");
}
auto program_input() -> void {
    const std::string rejected = "\r\nLine rejected: too long, non-ASCII/control byte, or UART error.\r\naurora> ";
    struct Case {
        std::string text, expected;
        Action action;
        std::uint64_t carry;
        std::string output;
    };
    const Case cases[] = {
        {"write a x\n", "write a x", Action::command, 0, "write a x\r\n"},
        {"upperx\n", "upperx", Action::command, 0, "upperx\r\n"},
        {"\nq\n", "q", Action::command, 0, "\r\naurora> q\r\n"},
        {"upper\nhelp\n", "help", Action::upper_payload, 0, "upper\r\ntext> help\r\n"},
        {"upper\nstatus\n", "status", Action::upper_payload, 0, "upper\r\ntext> status\r\n"},
        {"upper\nexit\n", "exit", Action::upper_payload, 0, "upper\r\ntext> exit\r\n"},
        {"upper\r\n\n", "", Action::upper_payload, 0, "upper\r\ntext> \r\n"},
        {"upper\n\b\x7f"
         "abx\bcZ!\r",
         "abcZ!",
         Action::upper_payload,
         1,
         "upper\r\ntext> abx\b \bcZ!\r\n"},
        {"upper\nabx\x7fZ\n", "abZ", Action::upper_payload, 0, "upper\r\ntext> abx\b \bZ\r\n"},
        {"upper\n" + std::string(64, 'a') + "\n",
         std::string(64, 'a'),
         Action::upper_payload,
         0,
         "upper\r\ntext> " + std::string(64, 'a') + "\r\n"},
        {"upper\n" + std::string(65, 'a') + "\b\nq\n",
         "q",
         Action::command,
         0,
         "upper\r\ntext> " + std::string(64, 'a') + rejected + "q\r\n"},
        {"exit\r", "", Action::requested_exit, 1, "exit\r\nAURORA_CONSOLE_EXIT\r\n"},
    };
    for (const auto &test : cases) {
        script(test.text);
        expect_input(read_input(), test.expected, test.action, test.carry);
        need(sample_index == samples.size() && transcript == test.output, "reader exact input/output boundary");
        // Fail each actual output operation, including the pre-dispatch CRLF.
        for (std::size_t position = 0; position < test.output.size(); ++position) {
            script(test.text, position);
            const auto failed = read_input();
            need(sample_index != 0, "reader emitted output before reading input");
            expect_input(failed, "", Action::output_failure, samples[sample_index - 1].byte == '\r' ? 1 : 0);
            need(transcript == test.output.substr(0, position) && output_attempts == position + 1,
                 "reader output failure changed prefix or performed extra output");
        }
    }
    script("help\r\nstatus\nq\n");
    expect_input(read_input(), "q", Action::command, 0);
    const std::string local_output =
        "help\r\nupper   Uppercase a line in a protected Aurora program\r\n"
        "write note <text>  Replace the RAM note (53 ASCII bytes)\r\n"
        "cat note          Read the note in protected Aurora\r\n"
        "upper note        Replace the note with protected uppercase output\r\n"
        "write <name> <text>  Write one of four RAM files (8-byte name, 49-byte content)\r\n"
        "append <name> <text>  Append to an existing RAM file\r\n"
        "copy <source> <destination>  Copy a RAM file; replace destination\r\n"
        "cat <name> / upper <name>  Protected read / atomic uppercase replacement\r\n"
        "ls / rm <name>     List / remove RAM files\r\nhelp    Show commands\r\n"
        "status  Show console state\r\nexit    Close this QEMU session\r\naurora> "
        "status\r\nstatus: protected Aurora upper; two-domain copied stream; timer budgets; capacity=64\r\naurora> "
        "q\r\n";
    need(transcript == local_output, "help/status must finish locally with exactly one prompt per command");
    for (std::size_t position = 0; position < local_output.size(); ++position) {
        script("help\r\nstatus\nq\n", position);
        const auto failed = read_input();
        need(sample_index != 0, "local reader emitted output before reading input");
        expect_input(failed, "", Action::output_failure, samples[sample_index - 1].byte == '\r' ? 1 : 0);
        need(transcript == local_output.substr(0, position) && output_attempts == position + 1,
             "local presentation output failure prefix and one failed write");
    }

    // Failure of either accepted-line delimiter byte returns no command to
    // dispatch and consumes none of the following input, including a paired LF.
    for (const auto command : {"write note x", "write a x", "cat note", "upper note", "ls", "rm a", "q"}) {
        for (const bool upper : {false, true}) {
            const std::string prefix = upper ? "upper\n" : "";
            const std::string echoed = upper ? "upper\r\ntext> " : "";
            const std::string accepted = prefix + command + "\r";
            const std::string output = echoed + command;
            for (std::size_t delimiter = 0; delimiter < 2; ++delimiter) {
                script(accepted + "\nnext\n", output.size() + delimiter);
                expect_input(read_input(), "", Action::output_failure, 1);
                need(sample_index == accepted.size() && output_attempts == output.size() + delimiter + 1 &&
                         transcript == output + (delimiter == 0 ? "" : "\r"),
                     "delimiter timeout released a command, retried output or consumed later input");
            }
        }
    }

    script("one\r\nupper\r\nexit\r\nexit\n");
    const auto first = read_input();
    expect_input(first, "one", Action::command, 1);
    const auto second = read_input(first.after_cr());
    expect_input(second, "exit", Action::upper_payload, 1);
    expect_input(read_input(second.after_cr()), "", Action::requested_exit, 0);
    expect_input(first, "one", Action::command, 1);
    need(sample_index == samples.size() &&
             transcript == "one\r\nupper\r\ntext> exit\r\nexit\r\nAURORA_CONSOLE_EXIT\r\n",
         "CRLF carry or copied submission changed across invocations");

    for (const auto damaged : {aurora::console::Sample{false, 0, true}, {true, 'x', true}, {true, '\r', true}}) {
        script("upper\nbad");
        samples.push_back(damaged);
        for (const auto byte : std::string_view{"\nq\n"})
            samples.push_back({true, static_cast<std::uint8_t>(byte), false});
        expect_input(read_input(), "q", Action::command, 0);
        need(transcript == "upper\r\ntext> bad" + rejected + "q\r\n", "damage must reject and clear upper mode");
    }
    script("one\r\nupper\nq\n");
    samples[4].damaged = true;
    const auto before_damage = read_input();
    expect_input(before_damage, "one", Action::command, 1);
    expect_input(read_input(before_damage.after_cr()), "q", Action::command, 0);
    need(transcript == "one\r\n" + rejected + "q\r\n", "damaged suppressed LF must poison the next invocation");
    for (const unsigned byte : {0U, 1U, 27U, 128U, 255U}) {
        script("upper\nbad");
        samples.push_back({true, static_cast<std::uint8_t>(byte), false});
        for (const auto tail : std::string_view{"\b\nq\n"})
            samples.push_back({true, static_cast<std::uint8_t>(tail), false});
        expect_input(read_input(), "q", Action::command, 0);
        need(transcript == "upper\r\ntext> bad" + rejected + "q\r\n", "unsafe byte cannot be repaired by backspace");
    }
}
auto submission_records() -> void {
    const auto accepts = [](const Submission::Record &record) {
        Submission submission;
        std::memcpy(submission.data(), &record, sizeof(record));
        return submission.valid();
    };
    Submission::Record record{};
    for (std::uint64_t action = 0; action < 4; ++action) {
        record.action = action;
        for (std::uint64_t carry = 0; carry < 2; ++carry) {
            record.after_cr = carry;
            need(accepts(record) == (action != 0), "empty command/payload/terminal distinction");
        }
    }
    record = {};
    record.count = 1;
    record.bytes[0] = 'q';
    need(accepts(record), "ordinary copied command record");
    for (const auto count : {std::int64_t{-1},
                             std::int64_t{65},
                             std::numeric_limits<std::int64_t>::min(),
                             std::numeric_limits<std::int64_t>::max()}) {
        auto bad = record;
        bad.count = count;
        need(!accepts(bad), "copied submission signed count bounds");
    }
    for (const auto action : {std::uint64_t{2}, std::uint64_t{3}, std::uint64_t{4}, maximum}) {
        auto bad = record;
        bad.action = action;
        need(!accepts(bad), "terminal payload and unknown actions reject");
    }
    for (const auto carry : {std::uint64_t{2}, maximum}) {
        auto bad = record;
        bad.after_cr = carry;
        need(!accepts(bad), "noncanonical CR carry rejects");
    }
    for (const unsigned byte : {0U, 31U, 127U, 255U}) {
        auto bad = record;
        bad.bytes[0] = static_cast<std::uint8_t>(byte);
        need(!accepts(bad), "nonprintable copied prefix rejects");
    }
    for (const auto index : {1U, 63U}) {
        auto bad = record;
        bad.bytes[index] = 'x';
        need(!accepts(bad), "copied suffix must be all zero");
    }
    record.count = 64;
    record.bytes.fill('~');
    need(accepts(record), "exact maximum copied command");
    Submission submission;
    std::memcpy(submission.data(), &record, sizeof(record));
    submission.scrub();
    record = {};
    need(std::memcmp(submission.data(), &record, sizeof(record)) == 0, "complete submission scrub");
}

auto copied_response(const Response::Record &record) -> Response {
    Response response;
    std::memcpy(response.data(), &record, sizeof(record));
    return response;
}
auto response_record(ResponseKind kind, std::string_view text = "") -> Response::Record {
    Response::Record record{};
    need(text.size() <= record.bytes.size(), "bounded response fixture");
    record.kind = static_cast<std::uint64_t>(kind);
    record.count = static_cast<std::int64_t>(text.size());
    for (std::size_t index = 0; index < text.size(); ++index)
        record.bytes[index] = static_cast<std::uint8_t>(text[index]);
    return record;
}
auto present_response(Response response) -> std::uint64_t {
    // Malformed scalar data is safe to exercise inside Aurora; a forged enum
    // must be rejected natively before crossing its typed ABI.
    need(response.canonical_kind(), "native response enum ingress");
    struct alignas(16) Guarded {
        std::array<std::byte, 16> before;
        aurora::program::ResponseArgument argument;
        std::array<std::byte, 16> after;
    } guarded{{}, {InputSession::open(), response}, {}};
    guarded.before.fill(std::byte{0xa5});
    guarded.after.fill(std::byte{0xa5});
    const auto original = guarded.argument;
    response.scrub();
    const Response::Record zero{};
    need(std::memcmp(response.data(), &zero, sizeof(zero)) == 0, "response producer copy scrub");
    const auto input_before = sample_index;
    response_active = true;
    const auto result = __au_runtime_program_response(&guarded.argument);
    response_active = false;
    InputSession::release(guarded.argument.console);
    need(result <= 1 && sample_index == input_before, "response canonical bool and output-only boundary");
    need(std::memcmp(&guarded.argument, &original, sizeof(original)) == 0, "response changed its borrowed argument");
    guarded.argument.scrub();
    const auto *scrubbed = reinterpret_cast<const std::byte *>(&guarded.argument);
    for (std::size_t index = 0; index < sizeof(guarded.argument); ++index)
        need(scrubbed[index] == std::byte{0}, "response argument retained grant or copied bytes");
    for (std::size_t index = 0; index < guarded.before.size(); ++index)
        need(guarded.before[index] == std::byte{0xa5} && guarded.after[index] == std::byte{0xa5},
             "response argument or scrub exceeded its canaries");
    // Reopening proves release on success, rejection and timeout. Existing
    // console-session controls separately reject stale/released grant use.
    const auto reopened = InputSession::open();
    need(reopened.grant == original.console.grant && reopened.generation == original.console.generation + 1,
         "response did not release its grant");
    InputSession::release(reopened);
    return result;
}
auto program_response() -> void {
    struct Case {
        ResponseKind kind;
        std::string payload, output;
    };
    std::vector<Case> cases = {
        {ResponseKind::ready,
         "",
         "AURORA_PROGRAM_CONSOLE_READY: UEFI CPL3 upper/note, ASCII, 64-byte lines\r\naurora> "},
        {ResponseKind::output, "AZ !~", "output> AZ !~\r\naurora> "},
        {ResponseKind::output, "", "output> \r\naurora> "},
        {ResponseKind::output, std::string(64, '~'), "output> " + std::string(64, '~') + "\r\naurora> "},
        {ResponseKind::note_missing, "", "Note is missing.\r\naurora> "},
        {ResponseKind::file_missing, "", "File is missing.\r\naurora> "},
        {ResponseKind::note_saved, "", "Note saved.\r\naurora> "},
        {ResponseKind::file_saved, "", "File saved.\r\naurora> "},
        {ResponseKind::file_reply, "a b c", "a b c\r\naurora> "},
        {ResponseKind::file_reply, "", "\r\naurora> "},
        {ResponseKind::file_reply, std::string(64, ' '), std::string(64, ' ') + "\r\naurora> "},
        {ResponseKind::stopped,
         "",
         "Program stopped: checked fault or budget exhausted; output discarded.\r\naurora> "},
        {ResponseKind::unknown, "", "Unknown command. Type help.\r\naurora> "},
    };
    // The original native presenter wrote each bounded byte without imposing
    // the input editor's printable-ASCII policy. Exercise every byte through
    // both payload kinds, including NUL, controls and high bytes at full length.
    for (const auto kind : {ResponseKind::output, ResponseKind::file_reply}) {
        const std::string prefix = kind == ResponseKind::output ? "output> " : "";
        const std::string binary{"\0\1\x1b\r\n\x7f\x80\xff", 8};
        cases.push_back({kind, binary, prefix + binary + "\r\naurora> "});
        for (unsigned base = 0; base < 256; base += 64) {
            std::string payload;
            for (unsigned offset = 0; offset < 64; ++offset)
                payload += static_cast<char>(base + offset);
            cases.push_back({kind, payload, prefix + payload + "\r\naurora> "});
        }
    }
    for (const auto &test : cases) {
        const auto record = response_record(test.kind, test.payload);
        script("later\n", test.output.size());
        need(present_response(copied_response(record)) == 1 && transcript == test.output &&
                 output_attempts == test.output.size(),
             "response exact body and one complete prompt");
        for (std::size_t position = 0; position < test.output.size(); ++position) {
            script("later\n", position);
            need(present_response(copied_response(record)) == 0 && transcript == test.output.substr(0, position) &&
                     output_attempts == position + 1,
                 "response timeout prefix, one failed write and no later prompt");
        }
    }
    const auto reject = [](const Response::Record &record) {
        auto response = copied_response(record);
        script("later\n");
        need(response.canonical_kind() == (record.kind <= 8), "native response enum boundary");
        if (record.kind <= 8)
            need(present_response(response) == 0, "Aurora malformed response rejection");
        need(transcript.empty() && output_attempts == 0 && sample_index == 0,
             "malformed response had an input/output effect");
    };
    const auto record = response_record(ResponseKind::output, "q");
    Response bounded{ResponseKind::output};
    need(bounded.payload(std::span<const std::uint8_t>{record.bytes}.first(1)), "native response payload copy");
    const std::array<std::uint8_t, 65> oversized{};
    need(!bounded.payload(std::span<const std::uint8_t>{oversized}) &&
             !bounded.payload(std::as_bytes(std::span{oversized})) &&
             std::memcmp(bounded.data(), &record, sizeof(record)) == 0,
         "oversized native response copy must reject without changing the record");
    for (const auto count : {std::int64_t{-1},
                             std::int64_t{65},
                             std::numeric_limits<std::int64_t>::min(),
                             std::numeric_limits<std::int64_t>::max()}) {
        auto bad = record;
        bad.count = count;
        reject(bad);
    }
    for (std::uint64_t kind = 0; kind <= 8; ++kind) {
        if (kind == 1 || kind == 6)
            continue;
        auto bad = record;
        bad.kind = kind;
        reject(bad);
    }
    for (const auto kind : {std::uint64_t{9}, maximum}) {
        auto bad = record;
        bad.kind = kind;
        reject(bad); // Do not pass noncanonical enum bits into typed Aurora.
    }
    for (const auto index : {1U, 63U}) {
        for (const unsigned byte : {1U, 31U, 127U, 128U, 255U}) {
            auto bad = record;
            bad.bytes[index] = static_cast<std::uint8_t>(byte);
            reject(bad);
        }
    }
    auto bad_empty = response_record(ResponseKind::note_missing);
    bad_empty.bytes[63] = 'x';
    reject(bad_empty);

    // Source/native copies and turn-local Console grants do not disturb the
    // accepted CR carry or consume the next input during presentation.
    script("upper\nhi\r\nq\n");
    const auto input = read_input();
    expect_input(input, "hi", Action::upper_payload, 1);
    need(present_response(copied_response(response_record(ResponseKind::output, "HI"))) == 1,
         "response between reader turns");
    expect_input(read_input(input.after_cr()), "q", Action::command, 0);
    need(sample_index == samples.size() && transcript == "upper\r\ntext> hi\r\noutput> HI\r\naurora> q\r\n",
         "reader/response copied transcript and CRLF carry");
}

auto input(std::string_view text) -> StreamBytes {
    StreamBytes bytes{};
    need(text.size() <= bytes.size(), "test input capacity");
    for (std::size_t index = 0; index < text.size(); ++index)
        bytes[index] = static_cast<std::uint8_t>(text[index]);
    return bytes;
}
auto next(const Stream &stream, std::uint64_t ordinal, std::uint8_t byte) -> void {
    const auto offered = stream.next_input();
    need(offered && offered->ordinal() == ordinal && offered->byte() == byte, "copied input/cursor");
}
auto terminal(Stream &stream) -> void {
    need(stream.scrubbed() && !stream.next_input() && !stream.ready_to_finish() && !stream.finish() &&
             !stream.accept_request('x', 0) && !stream.accept_reply('x', 0) && !stream.acknowledge('x', 0) &&
             !stream.cancel(),
         "terminal ledger is scrubbed and inert");
}
auto byte_round(Stream &stream, std::uint64_t ordinal, std::uint8_t source, std::uint8_t output) -> void {
    next(stream, ordinal, source);
    need(!stream.ready_to_finish() && !stream.finish(), "partial output released");
    need(!stream.accept_reply(output, ordinal) && !stream.acknowledge(output, ordinal), "early service or ack");
    for (const auto invalid :
         {std::uint64_t{0}, std::uint64_t{31}, std::uint64_t{127}, std::uint64_t{255}, std::uint64_t{256}, maximum})
        need(!stream.accept_request(invalid, ordinal), "invalid request byte");
    for (const auto wrong : {ordinal + 1, ordinal + 256, maximum})
        need(!stream.accept_request(output, wrong), "invalid request ordinal");
    next(stream, ordinal, source);
    need(stream.accept_request(output, ordinal), "valid client request");
    need(!stream.next_input() && !stream.finish() && !stream.accept_request(output, ordinal) &&
             !stream.acknowledge(output, ordinal),
         "request duplicate or early acknowledgement");
    const auto wrong_byte = output == 'x' ? 'y' : 'x';
    need(!stream.accept_reply(wrong_byte, ordinal) && !stream.accept_reply(output, ordinal + 1) &&
             !stream.accept_reply(output | (std::uint64_t{1} << 63), ordinal),
         "wrong service reply");
    need(stream.accept_reply(output, ordinal), "valid service reply");
    need(!stream.accept_reply(output, ordinal) && !stream.accept_request(output, ordinal) && !stream.next_input() &&
             !stream.finish(),
         "duplicate service reply or partial exposure");
    need(!stream.acknowledge(wrong_byte, ordinal) && !stream.acknowledge(output, ordinal + 1) &&
             !stream.acknowledge(output | (std::uint64_t{1} << 63), ordinal),
         "wrong completion ack");
    need(stream.acknowledge(output, ordinal), "valid completion ack");
    need(!stream.acknowledge(output, ordinal) && !stream.accept_reply(output, ordinal) &&
             !stream.accept_request(output, ordinal),
         "completed ordinal reused");
}
auto check_output(const aurora::program::Output &output, const StreamBytes &expected, std::size_t length) -> void {
    need(output.length() == length && output.bytes() == expected, "whole copied output/tail");
}

constexpr auto read_reply(std::uint64_t source) -> std::uint64_t {
    return 1 | (source << 8);
}
constexpr auto read_ack(std::uint64_t source, std::uint64_t output, bool transforming) -> std::uint64_t {
    return read_reply(source) | (transforming ? output << 16 : 0);
}
auto read_byte_round(Stream &stream, std::uint64_t ordinal, std::uint8_t source, std::uint8_t output, bool transforming)
    -> void {
    const auto reply = read_reply(source);
    const auto acknowledgment = read_ack(source, output, transforming);
    next(stream, ordinal, 1);
    need(!stream.ready_to_finish() && !stream.finish(), "read cannot finish without acknowledged terminal");
    need(!stream.accept_reply(reply, ordinal) && !stream.acknowledge(acknowledgment, ordinal),
         "read rejects early reply or acknowledgment");
    for (const auto invalid : {std::uint64_t{0}, std::uint64_t{2}, std::uint64_t{257}, maximum})
        need(!stream.accept_request(invalid, ordinal), "read requires exact offset request marker");
    need(!stream.accept_request(1, ordinal + 1) && !stream.accept_request(1, maximum), "read request ordinal");
    need(stream.accept_request(1, ordinal), "read request");
    need(!stream.next_input() && !stream.accept_request(1, ordinal) && !stream.acknowledge(acknowledgment, ordinal) &&
             !stream.finish(),
         "read request is one shot and hides partial output");
    for (const auto invalid :
         {std::uint64_t{0}, std::uint64_t{4}, reply | 2, reply | (std::uint64_t{1} << 16), maximum})
        need(!stream.accept_reply(invalid, ordinal), "read reply closed encoding");
    need(!stream.accept_reply(reply, ordinal + 1) && !stream.accept_reply(reply, maximum), "read reply ordinal");
    need(stream.accept_reply(reply, ordinal), "read retains actual service reply");
    need(!stream.accept_reply(reply, ordinal) && !stream.accept_request(1, ordinal) && !stream.next_input() &&
             !stream.finish(),
         "read reply is one shot and hides partial output");
    const auto changed_source = source == 'x' ? 'y' : 'x';
    need(!stream.acknowledge(read_ack(changed_source, output, transforming), ordinal) &&
             !stream.acknowledge(acknowledgment ^ 1, ordinal) && !stream.acknowledge(2, ordinal) &&
             !stream.acknowledge(3, ordinal),
         "read acknowledgment must preserve exact service byte and marker");
    need(!stream.acknowledge(acknowledgment, ordinal + 1) && !stream.acknowledge(acknowledgment, maximum),
         "read acknowledgment ordinal");
    for (const auto excess : {std::uint64_t{1} << 24, std::uint64_t{1} << 32, std::uint64_t{1} << 63})
        need(!stream.acknowledge(acknowledgment | excess, ordinal), "read acknowledgment rejects excess bits");
    if (transforming) {
        for (std::uint64_t invalid = 0; invalid <= 256; ++invalid) {
            if (invalid < 32 || invalid > 126)
                need(!stream.acknowledge(read_ack(source, invalid, true), ordinal),
                     "transforming read requires bounded printable output");
        }
        need(!stream.acknowledge(reply, ordinal), "transforming read cannot omit transformed byte");
    } else {
        need(!stream.acknowledge(read_ack(source, output, true), ordinal),
             "ordinary read rejects a transforming acknowledgment");
    }
    need(stream.acknowledge(acknowledgment, ordinal), "read accepts actual client acknowledgment");
    need(!stream.acknowledge(acknowledgment, ordinal) && !stream.accept_reply(reply, ordinal) &&
             !stream.accept_request(1, ordinal),
         "read completed ordinal cannot be replayed");
}
auto read_terminal_round(Stream &stream, std::uint64_t ordinal, bool missing = false) -> void {
    const std::uint64_t reply = missing ? 3 : 2;
    next(stream, ordinal, 1);
    need(!stream.finish() && stream.accept_request(1, ordinal) && stream.accept_reply(reply, ordinal),
         "read terminal request and reply require acknowledgment");
    need(!stream.acknowledge(missing ? 2 : 3, ordinal) && !stream.acknowledge(read_reply('a'), ordinal) &&
             !stream.acknowledge(reply | (std::uint64_t{'A'} << 16), ordinal) &&
             !stream.acknowledge(reply | (std::uint64_t{1} << 8), ordinal) &&
             !stream.acknowledge(reply | (std::uint64_t{1} << 63), ordinal) &&
             !stream.acknowledge(reply, ordinal + 1) && !stream.finish(),
         "terminal acknowledgment requires exact marker without transformed byte");
    need(stream.acknowledge(reply, ordinal) && stream.ready_to_finish() && !stream.next_input(),
         "acknowledged terminal enables whole read output");
    need(!stream.accept_request(1, ordinal) && !stream.accept_reply(reply, ordinal) &&
             !stream.acknowledge(reply, ordinal),
         "read terminal cannot be repeated");
}
auto read_streams() -> void {
    Stream stream;
    for (const auto transforming : {false, true}) {
        need(stream.begin_read(transforming), "begin read mode");
        need(!stream.begin_read(!transforming) && !stream.begin(input("x"), 1), "active read cannot be replaced");
        // Deliberately not uppercase: native code authenticates the original
        // reply and bounds output, without computing the client transformation.
        read_byte_round(stream, 0, 'a', transforming ? 'q' : 'a', transforming);
        read_byte_round(stream, 1, 'z', transforming ? '!' : 'z', transforming);
        read_terminal_round(stream, 2);
        const auto output = stream.finish();
        need(output && !output->missing(), "whole read finish");
        check_output(*output, input(transforming ? "q!" : "az"), 2);
        terminal(stream);

        for (const auto missing : {false, true}) {
            need(stream.begin_read(transforming) && !stream.ready_to_finish(), "empty/missing requires terminal round");
            read_terminal_round(stream, 0, missing);
            const auto empty = stream.finish();
            need(empty && empty->missing() == missing, "empty and missing remain distinct");
            check_output(*empty, StreamBytes{}, 0);
            terminal(stream);
        }

        for (std::uint8_t source = 32; source <= 126; ++source) {
            const auto transformed = transforming ? static_cast<std::uint8_t>(158 - source) : source;
            need(stream.begin_read(transforming), "printable read byte coverage");
            read_byte_round(stream, 0, source, transformed, transforming);
            read_terminal_round(stream, 1);
            const auto output = stream.finish();
            StreamBytes expected{};
            expected[0] = transformed;
            need(output && !output->missing(), "printable read finish");
            check_output(*output, expected, 1);
            terminal(stream);
        }

        StreamBytes expected{};
        need(stream.begin_read(transforming), "maximum read begin");
        for (std::size_t index = 0; index < 53; ++index) {
            const auto source = static_cast<std::uint8_t>(' ' + index);
            const auto output = transforming ? static_cast<std::uint8_t>('~' - index) : source;
            read_byte_round(stream, index, source, output, transforming);
            expected[index] = output;
        }
        read_terminal_round(stream, 53);
        const auto maximum_output = stream.finish();
        need(maximum_output && !maximum_output->missing(), "maximum read finish");
        check_output(*maximum_output, expected, 53);
        terminal(stream);

        need(stream.begin_read(transforming), "overlong read begin");
        for (std::size_t index = 0; index < 53; ++index)
            read_byte_round(stream, index, 'x', 'x', transforming);
        need(stream.accept_request(1, 53) && stream.accept_reply(read_reply('x'), 53) &&
                 !stream.acknowledge(read_ack('x', 'x', transforming), 53) && !stream.finish() && stream.cancel(),
             "fifty-fourth byte cannot be staged or released");
        terminal(stream);

        for (unsigned stage = 0; stage < 7; ++stage) {
            need(stream.begin_read(transforming), "read cancellation fixture");
            read_byte_round(stream, 0, 'x', transforming ? 'X' : 'x', transforming);
            if (stage >= 1)
                need(stream.accept_request(1, 1), "cancel pending read request");
            if (stage >= 2)
                need(stream.accept_reply(read_reply('y'), 1), "cancel pending read reply");
            if (stage >= 3)
                need(stream.acknowledge(read_ack('y', 'y', transforming), 1), "cancel staged read prefix");
            if (stage >= 4)
                need(stream.accept_request(1, 2), "cancel pending terminal request");
            if (stage >= 5)
                need(stream.accept_reply(2, 2), "cancel pending terminal reply");
            if (stage >= 6)
                need(stream.acknowledge(2, 2), "cancel fully acknowledged read");
            need(stream.cancel(), "cancel live read discards every staged byte");
            terminal(stream);
            need(stream.begin_read(), "read cancellation recovery resets transforming mode");
            read_byte_round(stream, 0, 'n', 'n', false);
            read_terminal_round(stream, 1);
            const auto recovered = stream.finish();
            need(recovered && !recovered->missing(), "read recovery finish");
            check_output(*recovered, input("n"), 1);
            terminal(stream);
        }
    }
    need(stream.begin(input("a"), 1), "scalar stream after transforming read");
    byte_round(stream, 0, 'a', 'A');
    const auto scalar = stream.finish();
    need(scalar && !scalar->missing(), "scalar mode reset after read");
    check_output(*scalar, input("A"), 1);
    terminal(stream);
}

// Independent state model: no implementation helpers or private storage.
class Model final {
public:
    enum class Stage {
        idle,
        request,
        reply,
        ack,
        finished,
        cancelled
    };
    Stage stage = Stage::idle;
    StreamBytes source{}, output{};
    std::size_t length{}, ordinal{};
    std::uint64_t pending{};
    auto scrub() -> void {
        source = {};
        output = {};
        length = 0;
        ordinal = 0;
        pending = 0;
    }
    auto operation(unsigned operation, std::uint64_t byte, std::uint64_t cursor) -> bool {
        const auto same = byte == pending && cursor == ordinal && ordinal < length && byte >= 32 && byte <= 126;
        if (operation == 1 && stage == Stage::request && ordinal < length && cursor == ordinal && byte >= 32 &&
            byte <= 126) {
            pending = byte;
            stage = Stage::reply;
            return true;
        }
        if (operation == 2 && stage == Stage::reply && same) {
            stage = Stage::ack;
            return true;
        }
        if (operation == 3 && stage == Stage::ack && same) {
            output[ordinal] = static_cast<std::uint8_t>(pending);
            source[ordinal] = 0;
            ++ordinal;
            pending = 0;
            stage = Stage::request;
            return true;
        }
        if (operation == 4 && stage == Stage::request && ordinal == length) {
            scrub();
            stage = Stage::finished;
            return true;
        }
        if (operation == 5 && (stage == Stage::request || stage == Stage::reply || stage == Stage::ack)) {
            scrub();
            stage = Stage::cancelled;
            return true;
        }
        return false;
    }
};
auto generated_model() -> void {
    Stream stream;
    Model model;
    std::uint64_t seed = 0x31d45e77b9;
    auto random = [&]() -> std::uint64_t {
        seed ^= seed << 13;
        seed ^= seed >> 7;
        seed ^= seed << 17;
        return seed;
    };
    for (unsigned step = 0; step < 40000; ++step) {
        const auto operation = static_cast<unsigned>(random() % 6);
        auto byte = random() % 257;
        auto ordinal = random() % 67;
        if ((random() & 3) == 0) {
            byte = model.pending ? model.pending : 'Q';
            ordinal = model.ordinal;
        }
        bool expected{}, actual{};
        if (operation == 0) {
            StreamBytes source{};
            const auto length = static_cast<std::size_t>(random() % 66);
            for (std::size_t index = 0; index < source.size(); ++index)
                source[index] = static_cast<std::uint8_t>(' ' + index % 95);
            if ((random() & 3) == 0)
                source[0] = 0;
            expected = (model.stage == Model::Stage::idle || model.stage == Model::Stage::finished ||
                        model.stage == Model::Stage::cancelled) &&
                       length <= 64 && (length == 0 || source[0] != 0);
            actual = stream.begin(source, length);
            if (expected) {
                model.scrub();
                model.length = length;
                model.stage = Model::Stage::request;
                for (std::size_t index = 0; index < length; ++index)
                    model.source[index] = source[index];
            }
        } else {
            const auto prior_output = model.output;
            const auto prior_length = model.length;
            expected = model.operation(operation, byte, ordinal);
            if (operation == 1)
                actual = stream.accept_request(byte, ordinal);
            if (operation == 2)
                actual = stream.accept_reply(byte, ordinal);
            if (operation == 3)
                actual = stream.acknowledge(byte, ordinal);
            if (operation == 4) {
                const auto output = stream.finish();
                actual = output.has_value();
                if (output)
                    check_output(*output, prior_output, prior_length);
            }
            if (operation == 5)
                actual = stream.cancel();
        }
        need(actual == expected, "generated model transition disagreement");
        const auto offer = stream.next_input();
        const auto has_offer = model.stage == Model::Stage::request && model.ordinal < model.length;
        need(offer.has_value() == has_offer, "generated model input availability");
        if (offer)
            need(offer->ordinal() == model.ordinal && offer->byte() == model.source[model.ordinal],
                 "generated model copied input");
        need(stream.ready_to_finish() == (model.stage == Model::Stage::request && model.ordinal == model.length),
             "generated model completion readiness");
        need(stream.scrubbed() == (model.length == 0 && model.ordinal == 0 && model.pending == 0 &&
                                   model.source == StreamBytes{} && model.output == StreamBytes{}),
             "generated model scrub disagreement");
    }
}
} // namespace

extern "C" void
__au_runtime_console_next(const void *grant, std::uint64_t generation, aurora::console::RawSample *sample) {
    *sample = InputSession::next(grant, generation);
}
extern "C" std::uint64_t __au_runtime_console_put(const void *grant, std::uint64_t generation, std::uint64_t byte) {
    return InputSession::put(grant, generation, byte);
}

auto main() -> int {
    program_input();
    submission_records();
    program_response();
    Stream bounded{1};
    need(bounded.run() == 0 && bounded.begin({}, 0) && bounded.run() == 1, "first ledger identity minted");
    need(bounded.finish().has_value() && !bounded.begin({}, 0) && bounded.run() == 1 && bounded.scrubbed(),
         "ledger generation exhaustion cannot wrap or mutate state");

    Stream stream;
    terminal(stream);
    auto bytes = input("az");
    need(!stream.begin(bytes, 65) && !stream.begin(bytes, std::numeric_limits<std::size_t>::max()) && stream.scrubbed(),
         "overlong begin retained bytes");
    for (unsigned bad = 0; bad <= 255; ++bad) {
        if (bad >= 32 && bad <= 126)
            continue;
        bytes[1] = static_cast<std::uint8_t>(bad);
        need(!stream.begin(bytes, 2) && stream.scrubbed(), "malformed input retained bytes");
    }
    bytes = input("az");
    bytes[63] = 255;
    need(stream.begin(bytes, 2), "bounded begin ignores unused caller tail");
    bytes.fill('x');
    need(!stream.begin(bytes, 1), "active stream overwritten");
    // Deliberately not uppercase: this protocol must not implement or verify a
    // program's transformation. It checks only source admission and byte flow.
    byte_round(stream, 0, 'a', 'q');
    byte_round(stream, 1, 'z', '!');
    need(stream.ready_to_finish() && !stream.next_input(), "full stream ready");
    const auto output = stream.finish();
    need(output.has_value(), "stream finish");
    check_output(*output, input("q!"), 2);
    terminal(stream);
    auto independent = output->bytes();
    independent[0] = 0;
    check_output(*output, input("q!"), 2);

    need(stream.begin(StreamBytes{}, 0) && stream.ready_to_finish() && !stream.next_input(), "empty stream");
    const auto empty = stream.finish();
    need(empty.has_value(), "empty finish");
    check_output(*empty, StreamBytes{}, 0);
    terminal(stream);

    StreamBytes full{};
    full.fill('a');
    need(stream.begin(full, full.size()), "maximum stream");
    for (std::size_t index = 0; index < full.size(); ++index)
        byte_round(stream, index, 'a', '~');
    full.fill('~');
    const auto maximum_output = stream.finish();
    need(maximum_output.has_value(), "maximum finish");
    check_output(*maximum_output, full, full.size());
    terminal(stream);

    for (unsigned stage = 0; stage < 4; ++stage) {
        need(stream.begin(input("xy"), 2), "cancellation fixture");
        byte_round(stream, 0, 'x', 'X');
        if (stage >= 1)
            need(stream.accept_request('Y', 1), "cancel requested fixture");
        if (stage >= 2)
            need(stream.accept_reply('Y', 1), "cancel replied fixture");
        if (stage >= 3)
            need(stream.acknowledge('Y', 1), "cancel fully staged fixture");
        need(stream.cancel(), "cancel live stream");
        terminal(stream);
        need(stream.begin(input("n"), 1), "cancel recovery");
        byte_round(stream, 0, 'n', 'N');
        const auto recovered = stream.finish();
        need(recovered.has_value(), "recovery finish");
        check_output(*recovered, input("N"), 1);
        terminal(stream);
    }
    read_streams();
    generated_model();
    std::cout << "PASS: source input/response turns, copied record validation, per-byte output failure, copied-byte "
                 "and authenticated "
                 "read/transform streams, ordered one-shot request/reply/ack, output staging and scrub; "
                 "40000 scalar model steps\n";
}
