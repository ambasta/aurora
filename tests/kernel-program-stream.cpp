#include "../kernel/program-stream.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string_view>
#include <type_traits>

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

auto main() -> int {
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
    generated_model();
    std::cout << "PASS: copied-byte stream, ordered one-shot request/reply/ack, output staging and scrub; 40000 model "
                 "steps\n";
}
