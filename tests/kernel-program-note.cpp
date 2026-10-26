#include "../kernel/program-note.hpp"
#include "../kernel/program-files.hpp"
#include "../kernel/file-service-transport.hpp"
#include "../kernel/program-stream.hpp"

#include <algorithm>
#include <array>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <span>
#include <string>
#include <string_view>
#include <type_traits>
#include <sys/wait.h>
#include <unistd.h>

// The supervisor graph contains the reader; note-policy calls must never use it.
extern "C" void __au_runtime_console_next(const void *, std::uint64_t, void *) {
    std::abort();
}
extern "C" std::uint64_t __au_runtime_console_put(const void *, std::uint64_t, std::uint64_t) {
    std::abort();
}

using U64 = std::uint64_t;
using I64 = std::int64_t;
using namespace aurora;
using program::Note;
extern "C" void __au_runtime_note_update(const void *, void *);
extern "C" void __au_runtime_note_project(const void *, void *);
extern "C" void note_test_initial(void *);
extern "C" void files_test_initial(void *);
extern "C" void stream_test_initial(void *);
extern "C" I64 command_stream_contract();
extern "C" U64 file_service_test_transition(U64, U64);
extern "C" void __au_runtime_files_update(const void *, void *);
extern "C" void __au_runtime_files_replace(const void *, void *);
extern "C" U64 file_call_test_service(const void *);
extern "C" U64 note_test_service(const void *);
extern "C" I64 aurora_user_main(I64, I64, I64);

namespace {
U64 checks = 0;
constexpr U64 maximum = std::numeric_limits<U64>::max();
static_assert(!std::is_copy_constructible_v<Note> && !std::is_move_constructible_v<Note>);

auto require(bool good, const char *why) -> void {
    if (!good) {
        std::fprintf(stderr, "FAIL program note: %s\n", why);
        std::exit(1);
    }
    ++checks;
}

auto put_word(std::span<std::byte> bytes, std::size_t offset, U64 value) -> void {
    for (unsigned byte = 0; byte < 8; ++byte)
        bytes[offset + byte] = std::byte(value >> (byte * 8));
}

auto update(const Note::UpdateInput &input) -> Note::Update {
    const auto before = input;
    alignas(16) std::array<std::byte, 112> storage{};
    storage.fill(std::byte{0xa5});
    __au_runtime_note_update(input.data(), storage.data() + 16);
    require(input == before, "actual update leaves copied input immutable");
    for (std::size_t index = 0; index < 16; ++index)
        require(storage[index] == std::byte{0xa5} && storage[96 + index] == std::byte{0xa5}, "update result canaries");
    Note::Update output{};
    std::copy_n(storage.begin() + 16, output.size(), output.begin());
    return output;
}

auto update(const Note &note, std::string_view command, I64 count) -> Note::Update {
    Note::UpdateInput input{};
    require(command.size() <= 64, "bounded test command");
    std::copy(note.saved().begin(), note.saved().end(), input.begin());
    for (std::size_t byte = 0; byte < command.size(); ++byte)
        input[72 + byte] = std::byte(command[byte]);
    put_word(input, 136, static_cast<U64>(count));
    return update(input);
}

auto submit(Note &note, std::string_view command, U64 expected) -> void {
    const auto result = update(note, command, static_cast<I64>(command.size()));
    require(note.commit(result) == expected, "actual SessionNote update event");
}

auto project(const Note &note) -> Note::Value {
    const auto before = note.saved();
    Note::Value result{};
    __au_runtime_note_project(note.saved().data(), result.data());
    require(note.saved() == before && result == before, "actual complete projection without saved mutation");
    return result;
}

auto bytes(std::string_view text) -> program::StreamBytes {
    program::StreamBytes result{};
    require(text.size() <= result.size(), "bounded stream fixture");
    for (std::size_t index = 0; index < text.size(); ++index)
        result[index] = static_cast<std::uint8_t>(text[index]);
    return result;
}

class Fixture final {
public:
    Note note;
    user::DomainRegistry registry;
    user::DomainHandle client, service;
    ipc::Mailbox mailbox{registry};
    program::Stream stream;
    U64 transaction{}, ordinal{};
    bool reading = true;
    bool transforming = false;
    bool appending = false;
    alignas(16) std::array<std::byte, Note::stream_record_bytes + 32> storage{};
    explicit Fixture(U64 run_ceiling = UINT64_MAX) : stream(run_ceiling) {
    }

    auto start(bool read = true, std::string_view input = {}, bool upper_note = false) -> void {
        reading = read;
        const auto a = registry.create(), b = registry.create();
        require(a && b, "fresh real participant incarnations");
        client = *a;
        service = *b;
        require(mailbox.bind(client, service), "fresh real mailbox grants");
        Note::Value projection{};
        if (reading || upper_note)
            projection = project(note);
        require(upper_note ? note.begin_upper(projection, stream)
                : reading  ? stream.begin_read()
                           : stream.begin(bytes(input), input.size()),
                "new buffered command from copied input before publication");
        if (!reading)
            projection = {}; // Upper receives only its scalar byte and a zero read placeholder.
        require(note.bind(projection, *mailbox.endpoint(service)), "frozen copied publication");
        projection.fill(std::byte{0xa5});
    }

    auto start_upper() -> void {
        const auto saved = note.saved();
        submit(note, "upper note", 4);
        require(note.saved() == saved, "uppercase selection preserves the source note");
        start(false, {}, true);
    }

    auto request() -> void {
        const auto next = stream.next_input();
        require(next.has_value() && !stream.finish(), "no partial output before request");
        ordinal = next->ordinal();
        const auto result = aurora_user_main(reading ? 12 : 0, next->byte(), static_cast<I64>(ordinal));
        require(result >= 0 && stream.accept_request(static_cast<U64>(result), ordinal), "actual client request");
        const auto ticket = mailbox.submit(
            client, ipc::Phase::request, *mailbox.endpoint(client), ipc::Request{static_cast<U64>(result), ordinal});
        require(ticket.has_value(), "real authenticated mailbox submission");
        transaction = *ticket;
        require(!stream.finish(), "no partial output after request");
    }

    auto receive(U64 phase) -> U64 {
        const auto grant = *mailbox.endpoint(service);
        const auto request = mailbox.receive(service, ipc::Phase::service, grant, transaction);
        require(request && request->second() == ordinal && mailbox.scrubbed(), "actual mailbox receive and scrub");
        storage.fill(std::byte{0xa5});
        const std::span<std::byte, Note::stream_record_bytes> record{storage.data() + 16, Note::stream_record_bytes};
        require(note.stage_stream(record, grant, phase, *request), "authenticated fixed copied record");
        if (!reading)
            for (std::size_t index = 24; index < record.size(); ++index)
                require(record[index] == std::byte{0}, "upper service receives no saved-note projection");
        const auto before = storage;
        const auto result = note_test_service(record.data());
        require(storage == before, "actual service leaves full copied input immutable");
        for (std::size_t index = 0; index < 16; ++index)
            require(storage[index] == std::byte{0xa5} &&
                        storage[Note::stream_record_bytes + 16 + index] == std::byte{0xa5},
                    "record canaries");
        return result;
    }

    auto reply(U64 result) -> void {
        require(stream.accept_reply(result, ordinal), "buffer accepts actual service reply");
        require(mailbox.reply(service, ipc::Phase::service, *mailbox.endpoint(service), transaction, result),
                "actual mailbox reply commit");
        require(!mailbox.cancel(ipc::Phase::inactive) &&
                    !mailbox.reply(service, ipc::Phase::service, *mailbox.endpoint(service), transaction, result),
                "reply is the first terminal result");
        require(!stream.finish(), "reply cannot release partial output");
    }

    auto consume() -> U64 {
        const auto result = mailbox.consume(client, ipc::Phase::completion, *mailbox.endpoint(client), transaction);
        require(result && result->outcome() == ipc::Outcome::replied && mailbox.scrubbed(),
                "real copied completion and mailbox scrub");
        return result->value();
    }

    auto acknowledge(U64 result) -> void {
        const auto accepted = aurora_user_main(transforming ? 14
                                               : reading    ? 13
                                                            : 2,
                                               static_cast<I64>(result),
                                               static_cast<I64>(ordinal));
        require(accepted >= 0 && stream.acknowledge(static_cast<U64>(accepted), ordinal),
                "actual client acknowledges actual returned bytes or EOF");
        require(mailbox.recycle(ipc::Phase::inactive), "consumed transaction recycle");
        transaction = 0;
    }

    auto round() -> void {
        request();
        reply(receive(appending ? 15 : reading ? 11 : 1));
        acknowledge(consume());
    }

    // Hosted cleanup of real adapter state, not an execution of the privileged
    // runtime continuation. Replied transactions retain their first terminal.
    auto retire(bool cancel = false) -> void {
        const auto saved = note.saved();
        const auto old_client = client, old_service = service;
        const auto grant = *mailbox.endpoint(service);
        if (cancel) {
            require(stream.cancel() && stream.scrubbed() && !stream.finish(), "abort discards every buffered byte");
            if (mailbox.state() == ipc::State::pending || mailbox.state() == ipc::State::delivered) {
                require(mailbox.cancel(ipc::Phase::inactive) && !mailbox.cancel(ipc::Phase::inactive),
                        "one cancellation terminal");
                require(!mailbox.reply(service, ipc::Phase::service, grant, transaction, 2), "late reply refused");
                const auto result =
                    mailbox.consume(client, ipc::Phase::completion, *mailbox.endpoint(client), transaction);
                require(result && result->outcome() == ipc::Outcome::cancelled && result->value() == 0,
                        "typed zero cancellation consumption");
            } else if (mailbox.state() == ipc::State::replied) {
                require(!mailbox.cancel(ipc::Phase::inactive), "cancellation cannot replace committed reply");
                static_cast<void>(consume());
            }
        }
        require(registry.ready(client) && registry.ready(service), "participants quiescent before retirement");
        note.release();
        require(mailbox.scrubbed() && mailbox.revoke(ipc::Phase::inactive) && registry.destroy(client) &&
                    registry.destroy(service),
                "real revoke, retire and scrub");
        require(!registry.index(old_client) && !registry.index(old_service) && !note.bound() && note.saved() == saved,
                "retirement preserves session note and invalidates incarnations");
        const auto before = storage;
        require(!note.stage(std::span<std::byte, Note::record_bytes>{storage.data() + 16, Note::record_bytes},
                            grant,
                            11,
                            ipc::Request{1, 0}) &&
                    storage == before,
                "retired publication cannot stage and preserves destination");
    }

    auto take(std::string_view expected, bool missing = false) -> program::Output {
        require(stream.ready_to_finish() && !stream.next_input(), "only terminal stream is ready");
        retire();
        auto output = stream.finish();
        require(output && output->length() == expected.size() && output->bytes() == bytes(expected) &&
                    output->missing() == missing && stream.scrubbed() && !stream.finish(),
                "whole actual result released once after retirement with zero tail");
        return *output;
    }

    auto finish(std::string_view expected, bool missing = false) -> void {
        auto output = take(expected, missing);
        output.scrub();
        require(output.length() == 0 && !output.missing() && output.bytes() == program::StreamBytes{},
                "released output scrub");
    }

    auto save(std::string_view expected) -> void {
        auto output = take(expected);
        const auto saved = note.saved();
        Note::UpdateInput input{};
        input.fill(std::byte{0xa5});
        require(note.replacement(output, input) && note.saved() == saved && !note.bound(),
                "post-retirement replacement preparation alone preserves storage");
        Note::UpdateInput expected_input{};
        std::copy(saved.begin(), saved.end(), expected_input.begin());
        const auto command = "write note " + std::string(expected);
        for (std::size_t index = 0; index < command.size(); ++index)
            expected_input[72 + index] = std::byte(command[index]);
        put_word(expected_input, 136, command.size());
        require(input == expected_input, "bounded prepared write carries actual output and a zero command tail");
        const auto result = update(input);
        require(note.saved() == saved && note.commit(result) == 1, "only actual Aurora replacement commits output");
        output.scrub();
        require(output.bytes() == program::StreamBytes{} && output.length() == 0, "saved output scrub");
    }

    auto upper(std::string_view expected) -> void {
        const auto saved = note.saved();
        start_upper();
        unsigned rounds = 0;
        while (stream.next_input()) {
            require(rounds++ < 53, "bounded actual uppercase stream");
            round();
            require(note.saved() == saved, "partial uppercase result never changes saved note");
        }
        require(rounds == expected.size() && note.saved() == saved, "complete uppercase remains uncommitted");
        save(expected);
    }

    auto read(std::string_view expected, bool missing = false) -> void {
        start();
        unsigned rounds = 0;
        while (stream.next_input()) {
            require(rounds++ <= 53, "bounded EOF-inclusive read");
            round();
        }
        require(rounds == expected.size() + 1, "actual EOF or missing consumes final transaction");
        finish(expected, missing);
    }
};

auto command_cases() -> void {
    Fixture f;
    Note::Value initial{};
    note_test_initial(initial.data());
    require(initial == f.note.saved(), "native Note constructor equals emitted SessionNote(empty)");
    submit(f.note, "cat note", 3);
    f.read("", true);
    submit(f.note, "write note first", 1);
    submit(f.note, "cat note", 2);
    f.read("first");
    f.read("first");
    submit(f.note, "write note x", 1);
    for (std::size_t index = 1; index < 64; ++index)
        require(f.note.saved()[index] == std::byte{0}, "short source replacement clears previous suffix");
    f.read("x");
    submit(f.note, "write note ", 1);
    submit(f.note, "cat note", 2);
    f.read("");
    std::string full;
    for (unsigned index = 0; index < 53; ++index)
        full += static_cast<char>(' ' + index);
    submit(f.note, "write note " + full, 1);
    f.read(full);
    const auto saved = f.note.saved();
    for (const auto command : {std::string_view{"unknown"},
                               std::string_view{"write note \x01", 12},
                               std::string_view{"write note \x7f", 12},
                               std::string_view{"cat note!"}}) {
        submit(f.note, command, 0);
        require(f.note.saved() == saved, "damaged and unknown commands preserve saved bytes");
    }
    for (const auto count : {I64{-1}, I64{65}, std::numeric_limits<I64>::max()}) {
        require(f.note.commit(update(f.note, "write note damaged", count)) == 0 && f.note.saved() == saved,
                "out-of-range command lengths preserve actual SessionNote");
    }
    f.read(full);
    f.note.clear();
    require(f.note.saved() == initial, "session teardown restores actual constructor representation");
    f.read("", true);
}

auto representation_controls() -> void {
    std::array<std::byte, 224> initial_stream{};
    initial_stream.fill(std::byte{0xa5});
    stream_test_initial(initial_stream.data() + 16);
    for (std::size_t index = 0; index < 16; ++index)
        require(initial_stream[index] == std::byte{0xa5} && initial_stream[208 + index] == std::byte{0xa5},
                "CommandStream constructor result canaries");
    for (std::size_t index = 16; index < 208; ++index)
        require(initial_stream[index] == std::byte{0}, "CommandStream matches native opaque initial representation");
    for (const auto operation : {U64{10}, U64{7}}) {
        std::array<std::byte, 280> input{};
        put_word(input, 192, operation);
        const auto before = input;
        std::array<std::byte, 312> result{};
        result.fill(std::byte{0xa5});
        __au_runtime_stream_update(input.data(), result.data() + 16);
        require(input == before, "stream bridge preserves complete copied input");
        for (std::size_t index = 0; index < 16; ++index)
            require(result[index] == std::byte{0xa5} && result[296 + index] == std::byte{0xa5},
                    "stream bridge result canaries");
        for (std::size_t index = 0; index < 280; ++index) {
            const auto expected = index == 272 && operation == 10 ? std::byte{1} : std::byte{0};
            require(result[16 + index] == expected, "closed stream query result");
        }
    }
    Note note;
    submit(note, "write note saved", 1);
    const auto saved = note.saved();
    const auto valid = update(note, "write note next", 15);
    for (const auto count : {U64{54}, U64{64}, U64{256}, U64{1} << 63, maximum - 1}) {
        auto malformed = valid;
        put_word(malformed, 64, count);
        require(!note.commit(malformed) && note.saved() == saved, "wide or non-closed saved length refused");
        auto projection = project(note);
        put_word(projection, 64, count);
        require(!note.bind(projection, ipc::Endpoint{1, 17}) && !note.bound(), "non-closed projection refused");
    }
    for (const auto event : {U64{5}, U64{256}, U64{1} << 63, maximum}) {
        auto malformed = valid;
        put_word(malformed, 72, event);
        require(!note.commit(malformed) && note.saved() == saved, "unknown or wide event refused");
    }
    for (const auto event : {U64{0}, U64{2}, U64{3}, U64{4}}) {
        auto malformed = valid;
        put_word(malformed, 72, event);
        require(!note.commit(malformed) && note.saved() == saved, "non-write cannot replace saved bytes");
    }
    const auto projection = project(note);
    for (const auto grant : {ipc::Endpoint{0, 17}, ipc::Endpoint{2, 17}, ipc::Endpoint{1, 0}})
        require(!note.bind(projection, grant), "invalid publication grant refused");
    require(note.bind(projection, ipc::Endpoint{1, 17}) && !note.bind(projection, ipc::Endpoint{1, 18}) &&
                !note.commit(valid) && note.saved() == saved,
            "live publication forbids replacement and rebinding");
    std::array<std::byte, Note::stream_record_bytes> record{};
    record.fill(std::byte{0xa5});
    const auto before = record;
    for (const auto grant : {ipc::Endpoint{0, 17}, ipc::Endpoint{1, 0}, ipc::Endpoint{1, 18}})
        require(!note.stage_stream(record, grant, 11, ipc::Request{1, 0}) && record == before,
                "foreign or stale stage preserves complete destination");
    note.release();
    require(note.bind(projection, ipc::Endpoint{1, 18}) && !note.matches(ipc::Endpoint{1, 17}) &&
                !note.stage_stream(record, ipc::Endpoint{1, 17}, 11, ipc::Request{1, 0}) && record == before,
            "fresh publication excludes old generation");
    for (const auto ordinal : {U64{6}, U64{54}, maximum}) {
        require(note.stage_stream(record, ipc::Endpoint{1, 18}, 11, ipc::Request{1, ordinal}) &&
                    note_test_service(record.data()) == 4,
                "actual service rejects bad ordinal");
    }
    for (const auto operation : {U64{0}, U64{2}, maximum})
        require(note.stage_stream(record, ipc::Endpoint{1, 18}, 11, ipc::Request{operation, 0}) &&
                    note_test_service(record.data()) == 4,
                "actual service rejects unknown operation");
    note.release();
    require(note.saved() == saved, "publication release preserves saved note");
}

auto reply_controls() -> void {
    for (const auto value : {I64{-1},
                             std::numeric_limits<I64>::min(),
                             I64{0},
                             I64{1},
                             I64{4},
                             I64{0x1f01},
                             I64{0x7f01},
                             I64{0xff01},
                             I64{0x10001},
                             (I64{1} << 62)})
        require(aurora_user_main(13, value, 0) == -1, "actual client rejects non-closed/nonprintable reply");
    require(aurora_user_main(13, 0x2001, 0) == 0x2001 && aurora_user_main(13, 0x7e01, 52) == 0x7e01 &&
                aurora_user_main(13, 2, 53) == 2 && aurora_user_main(13, 3, 0) == 3 &&
                aurora_user_main(13, 3, 1) == -1 && aurora_user_main(13, 0x6101, 53) == -1 &&
                aurora_user_main(13, 2, -1) == -1 && aurora_user_main(13, 2, 54) == -1 &&
                aurora_user_main(12, 1, -1) == -1 && aurora_user_main(12, 1, 54) == -1,
            "actual client byte/EOF/missing/ordinal boundaries");
    Fixture f;
    submit(f.note, "write note x", 1);
    f.start();
    f.request();
    const auto actual = f.receive(11);
    require(!f.stream.accept_reply(actual | (U64{1} << 63), 0) && !f.stream.accept_reply(actual, 1) &&
                !f.stream.acknowledge(actual, 0) && !f.stream.finish(),
            "reserved reply and reordered completion refused");
    f.reply(actual);
    const auto copied = f.consume();
    require(!f.stream.acknowledge(copied ^ 0x100, 0) && !f.stream.finish(), "changed completion cannot release bytes");
    f.retire(true);
    f.read("x");
}

auto cancellation_cases() -> void {
    Fixture f;
    submit(f.note, "write note preserved", 1);
    // Request, pending, delivered, replied, consumed, acknowledged and final EOF.
    for (unsigned stage = 0; stage < 7; ++stage) {
        f.start();
        const auto old_client = *f.mailbox.endpoint(f.client), old_service = *f.mailbox.endpoint(f.service);
        f.round();
        require(!f.stream.finish(), "acknowledged prefix remains buffered");
        U64 result = 0;
        if (stage >= 1)
            f.request();
        if (stage >= 2)
            result = f.receive(11);
        if (stage >= 3)
            f.reply(result);
        if (stage >= 4)
            result = f.consume();
        if (stage >= 5)
            f.acknowledge(result);
        if (stage == 6) {
            while (f.stream.next_input())
                f.round();
            require(f.stream.ready_to_finish(), "EOF buffered before cancellation");
        }
        f.retire(true);
        f.start();
        require(f.mailbox.endpoint(f.client)->generation() != old_client.generation() &&
                    !f.mailbox.submit(f.client, ipc::Phase::request, old_client, ipc::Request{1, 0}) &&
                    !f.note.matches(old_service),
                "fresh grants reject former client and publication");
        while (f.stream.next_input())
            f.round();
        f.finish("preserved");
    }
}

auto upper_save_cases() -> void {
    Fixture f;
    const auto missing = f.note.saved();
    submit(f.note, "upper note", 3);
    require(f.note.saved() == missing && !f.note.begin_upper(project(f.note), f.stream) && f.stream.scrubbed(),
            "missing uppercase never starts a stream or creates a note");
    f.read("", true);
    for (const auto text : {std::string_view{"az Az09!? ~"}, std::string_view{}}) {
        submit(f.note, "write note " + std::string(text), 1);
        const auto expected = text.empty() ? "" : "AZ AZ09!? ~";
        f.upper(expected);
        f.read(expected);
        f.upper(expected);
        f.read(expected);
    }
    std::string full, upper;
    for (unsigned index = 0; index < 53; ++index) {
        full += static_cast<char>('a' + index % 26);
        upper += static_cast<char>('A' + index % 26);
    }
    submit(f.note, "write note " + full, 1);
    f.upper(upper);
    f.read(upper);
    const auto saved = f.note.saved();
    for (const auto command : {std::string_view{"upper note!"},
                               std::string_view{"upper note "},
                               std::string_view{"Upper note"},
                               std::string_view{"upper Note"},
                               std::string_view{"upper  note"},
                               std::string_view{"upper not"},
                               std::string_view{"upper note\0", 11}}) {
        submit(f.note, command, 0);
        require(f.note.saved() == saved, "uppercase classification rejects every nonexact command");
    }
    for (const auto count : {I64{-1}, I64{9}, I64{11}, I64{65}, std::numeric_limits<I64>::max()})
        require(f.note.commit(update(f.note, "upper note", count)) == 0 && f.note.saved() == saved,
                "uppercase command requires exact bounded length");
}

auto replacement_controls() -> void {
    Fixture f;
    submit(f.note, "write note current", 1);
    const auto saved = f.note.saved();
    for (const auto length : {U64{54}, U64{64}, maximum}) {
        auto projection = project(f.note);
        put_word(projection, 64, length);
        require(!f.note.begin_upper(projection, f.stream) && f.stream.scrubbed() && f.note.saved() == saved,
                "uppercase rejects wide and missing projections without mutation");
    }
    auto damaged = project(f.note);
    damaged[0] = std::byte{0x1f};
    require(!f.note.begin_upper(damaged, f.stream) && f.stream.scrubbed(),
            "uppercase rejects nonprintable projected input");
    f.start(false, "value");
    while (f.stream.next_input())
        f.round();
    auto valid = f.take("VALUE");
    Note::UpdateInput input{};
    input.fill(std::byte{0xa5});
    const auto untouched = input;
    f.start();
    require(!f.note.replacement(valid, input) && input == untouched && !f.note.begin_upper(project(f.note), f.stream) &&
                f.note.saved() == saved,
            "bound note rejects save preparation and uppercase launch");
    f.retire(true);
    for (const auto length : {std::size_t{54}, std::size_t{64}}) {
        f.start(false, std::string(length, 'a'));
        while (f.stream.next_input())
            f.round();
        auto wide = f.take(std::string(length, 'A'));
        require(!f.note.replacement(wide, input) && input == untouched && f.note.saved() == saved,
                "completed over-53 output cannot prepare a note replacement");
        wide.scrub();
    }
    f.note.clear();
    f.start();
    f.round();
    auto absent = f.take("", true);
    const auto missing = f.note.saved();
    require(!f.note.replacement(absent, input) && input == untouched && f.note.saved() == missing,
            "completed missing output cannot create a note");
    absent.scrub();
    valid.scrub();
}

auto upper_cancellation_cases() -> void {
    Fixture f;
    // Request, pending, delivered, replied, consumed, acknowledged and complete.
    // Hosted retirement models cleanup; privileged recovery is a separate gate.
    for (unsigned stage = 0; stage < 7; ++stage) {
        submit(f.note, "write note preserved", 1);
        const auto saved = f.note.saved();
        f.start_upper();
        const auto old_client = *f.mailbox.endpoint(f.client), old_service = *f.mailbox.endpoint(f.service);
        f.round();
        require(!f.stream.finish(), "partial saved-uppercase output remains private");
        U64 result = 0;
        if (stage >= 1)
            f.request();
        if (stage >= 2)
            result = f.receive(1);
        if (stage >= 3)
            f.reply(result);
        if (stage >= 4)
            result = f.consume();
        if (stage >= 5)
            f.acknowledge(result);
        if (stage == 6) {
            while (f.stream.next_input())
                f.round();
            require(f.stream.ready_to_finish(), "whole uppercase can still be cancelled before retirement");
        }
        f.retire(true);
        require(f.note.saved() == saved && !f.stream.finish(), "every cancelled save preserves original note");
        f.start_upper();
        require(f.mailbox.endpoint(f.client)->generation() != old_client.generation() &&
                    f.mailbox.endpoint(f.service)->generation() != old_service.generation() &&
                    !f.mailbox.submit(f.client, ipc::Phase::request, old_client, ipc::Request{'P', 0}) &&
                    !f.note.matches(old_service),
                "healthy save receives fresh grants and rejects cancelled authority");
        while (f.stream.next_input())
            f.round();
        f.save("PRESERVED");
        f.read("PRESERVED");
    }
}

auto emitted_faults() -> void {
    // These execute actual generated UD2 sites in children. Cleanup below is a
    // separate hosted lifecycle exercise, not a claim of kernel fault recovery.
    Fixture f;
    for (const auto saving : {false, true}) {
        for (const auto phase : {I64{8}, I64{4}, I64{10}}) {
            submit(f.note, "write note fault-safe", 1);
            const auto saved = f.note.saved();
            if (saving)
                f.start_upper();
            else
                f.start();
            f.round();
            if (phase != 8)
                f.request();
            if (phase == 4)
                static_cast<void>(f.receive(saving ? 1 : 11));
            if (phase == 10) {
                f.reply(f.receive(saving ? 1 : 11));
                static_cast<void>(f.consume());
            }
            std::array<std::byte, Note::stream_record_bytes> record{};
            require(f.note.stage_stream(record, *f.mailbox.endpoint(f.service), 4, ipc::Request{1, 1}),
                    "actual fault input");
            const auto child = fork();
            require(child >= 0, "emitted fault child");
            if (child == 0) {
                if (phase == 4)
                    static_cast<void>(note_test_service(record.data()));
                else
                    static_cast<void>(aurora_user_main(phase, 1, 1));
                std::_Exit(3);
            }
            int status = 0;
            require(waitpid(child, &status, 0) == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGILL,
                    "actual emitted client/service bounds fault");
            f.retire(true);
            require(f.note.saved() == saved, "hosted cleanup after actual fault preserves original note");
            f.read("fault-safe");
            if (saving) {
                f.upper("FAULT-SAFE");
                f.read("FAULT-SAFE");
            }
        }
    }
}

auto upper_regression() -> void {
    Fixture f;
    submit(f.note, "write note unchanged", 1);
    f.start(false, "az Az09!? ~");
    while (f.stream.next_input())
        f.round();
    f.finish("AZ AZ09!? ~");
    f.read("unchanged");
}

using program::Files;
auto file_update(const Files::Value &saved, std::string_view command) -> Files::Update {
    Files::UpdateInput input{};
    require(command.size() <= 64, "bounded named command");
    std::copy(saved.begin(), saved.end(), input.begin());
    for (std::size_t i = 0; i < command.size(); ++i)
        input[272 + i] = std::byte(command[i]);
    put_word(input, 336, command.size());
    const auto before = input;
    std::array<std::byte, Files::Update{}.size() + 32> result{};
    result.fill(std::byte{0xa5});
    __au_runtime_files_update(input.data(), result.data() + 16);
    require(input == before, "file update immutable input");
    for (unsigned i = 0; i < 16; ++i)
        require(result[i] == std::byte{0xa5} && result[Files::Update{}.size() + 16 + i] == std::byte{0xa5},
                "file update canaries");
    Files::Update output{};
    std::copy_n(result.begin() + 16, output.size(), output.begin());
    return output;
}
auto file_replace(const Files::ReplaceInput &input) -> Files::Mutation {
    const auto before = input;
    std::array<std::byte, 384> result{};
    result.fill(std::byte{0xa5});
    __au_runtime_files_replace(input.data(), result.data() + 16);
    require(input == before, "file replacement immutable input");
    for (unsigned i = 0; i < 16; ++i)
        require(result[i] == std::byte{0xa5} && result[368 + i] == std::byte{0xa5}, "file replacement canaries");
    Files::Mutation output{};
    std::copy_n(result.begin() + 16, 352, output.begin());
    return output;
}
class NamedFixture final {
public:
    Files files;
    Fixture f;
    explicit NamedFixture(U64 run_ceiling = UINT64_MAX) : f(run_ceiling) {
    }
    auto submit(std::string_view command) -> Files::Update {
        const auto result = file_update(files.saved(), command);
        require(files.update(result).has_value(), "actual file policy update");
        return result;
    }
    auto start(std::string_view command, unsigned rejected_mode = 0) -> void {
        submit(command);
        require(files.selected(), "named selection");
        const auto a = f.registry.create(), b = f.registry.create();
        require(a && b, "named fresh participants");
        f.client = *a;
        f.service = *b;
        require(f.mailbox.bind(f.client, f.service), "named mailbox bind");
        f.reading = true;
        f.appending = files.appending();
        f.transforming = files.writable() && !f.appending;
        require(rejected_mode == 1 ? f.stream.begin({}, 0)
                                   : f.stream.begin_read(rejected_mode == 3 ? !f.transforming : f.transforming),
                "named starts selected stream mode");
        require(f.note.bind(files.projection(), *f.mailbox.endpoint(f.service), files.suffix()),
                "named copied service projection");
        if (rejected_mode == 2)
            f.round();
        if (rejected_mode != 0) {
            require(!files.bind(f.registry, f.mailbox, f.client, f.service, f.stream),
                    "file grant refuses scalar, wrong-mode or previously progressed read ledger");
            files.abort();
            f.retire(true);
            return;
        }
        require(files.writable() ? !files.bind_read(f.registry, f.mailbox, f.client, f.service)
                                 : !files.bind(f.registry, f.mailbox, f.client, f.service, f.stream),
                "selected read and writable bindings remain disjoint");
        require(files.writable() ? files.bind(f.registry, f.mailbox, f.client, f.service, f.stream)
                                 : files.bind_read(f.registry, f.mailbox, f.client, f.service),
                "named authenticated file binding");
    }
    auto run() -> void {
        while (f.stream.next_input())
            f.round();
    }
    auto read(std::string_view name, std::string_view expected, bool missing = false) -> void {
        start("cat " + std::string(name));
        run();
        require(!files.complete(f.registry, f.mailbox, f.client, *f.mailbox.endpoint(f.client), f.stream),
                "read-only real grant cannot authorize replacement");
        require(!files.release_read(f.registry, f.mailbox), "live read participants cannot release selection");
        f.retire();
        require(files.release_read(f.registry, f.mailbox), "read grant releases after authenticated retirement");
        require(!files.release_read(f.registry, f.mailbox), "read release cannot replay");
        auto output = f.stream.finish();
        require(output && output->missing() == missing && output->bytes() == bytes(expected) &&
                    output->length() == expected.size(),
                "exact protected named readback");
        output->scrub();
    }
    auto save(bool delivered = true) -> void {
        const auto endpoint = *f.mailbox.endpoint(f.client);
        require(!files.complete(f.registry, f.mailbox, f.service, endpoint, f.stream),
                "foreign caller cannot complete");
        require(!files.complete(f.registry, f.mailbox, f.client, ipc::Endpoint{0, endpoint.generation() + 1}, f.stream),
                "foreign generation cannot complete");
        program::Stream other;
        require(other.begin({}, 0) && !files.complete(f.registry, f.mailbox, f.client, endpoint, other),
                "foreign finished stream cannot authorize replacement");
        require(files.complete(f.registry, f.mailbox, f.client, endpoint, f.stream), "one authenticated completion");
        require(!files.complete(f.registry, f.mailbox, f.client, endpoint, f.stream), "completion cannot replay");
        user::DomainRegistry foreign_registry;
        ipc::Mailbox foreign_mailbox{foreign_registry};
        require(!files.retire(foreign_registry, foreign_mailbox),
                "foreign empty registry and revoked mailbox cannot impersonate retirement");
        require(!files.retire(f.registry, foreign_mailbox) && !files.retire(foreign_registry, f.mailbox),
                "retirement retains each original authority context");
        Files::ReplaceInput input{};
        input.fill(std::byte{0xa5});
        const auto untouched = input;
        require(!files.replacement(f.stream, input) && input == untouched, "no replacement before retirement");
        f.retire();
        require(files.retire(f.registry, f.mailbox), "named completed authority survives actual retirement");
        require(!files.replacement(other, input) && input == untouched, "foreign stream rejected after retirement");
        require(files.replacement(f.stream, input), "one retired replacement extraction");
        const auto result = file_replace(input);
        require(files.publish(result), "Aurora selected-file atomic publication");
        require(!files.publish(result) && !files.replacement(f.stream, input),
                "publication and extraction cannot replay");
        const auto committed = files.saved();
        const auto operation = files.operation();
        files.abort();
        require(files.settled() && operation != 0 && files.operation() == operation && files.saved() == committed,
                "committed outcome survives cancellation until response completion");
        require(!files.update(file_update(files.saved(), "append a duplicate")),
                "unresolved committed response prevents new command admission");
        require(files.response_complete(delivered) && !files.response_complete(delivered) && !files.settled() &&
                    files.saved() == committed,
                "response completion consumes outcome once without rolling back commit");
    }
    auto append(std::string_view name, std::string_view suffix, bool delivered = true) -> void {
        const auto old = files.saved();
        start("append " + std::string(name) + " " + std::string(suffix));
        require(files.appending() && files.saved() == old, "append preparation selects without mutation");
        while (f.stream.next_input()) {
            f.round();
            require(files.saved() == old, "append staged candidate remains private");
        }
        save(delivered);
    }
    auto upper(std::string_view name, std::string_view expected) -> void {
        const auto old = files.saved();
        start("upper " + std::string(name));
        while (f.stream.next_input()) {
            f.round();
            require(files.saved() == old, "partial named result private");
        }
        save();
        read(name, expected);
    }
};
auto file_byte_reply_cases() -> void {
    for (U64 word = 0; word <= 65536; ++word) {
        const bool valid = word == 2 || word == 3 || word == 4 || (word % 256 == 1 && word / 256 <= 255);
        require(program::Files::read_reply_valid(word) == valid, "closed file byte reply word");
        for (unsigned bit = 16; bit < 64; ++bit)
            require(!program::Files::read_reply_valid(word | (U64{1} << bit)), "reserved file reply bits");
    }
    std::array<std::byte, Note::record_bytes> input{};
    for (I64 length = -1; length <= 49; ++length) {
        for (I64 offset = -1; offset <= 50; ++offset) {
            put_word(input, 0, 11);
            put_word(input, 8, static_cast<U64>(offset));
            put_word(input, 16, 0);
            for (unsigned i = 0; i < 64; ++i)
                input[24 + i] = std::byte(i + 32);
            put_word(input, 88, static_cast<U64>(length));
            const U64 wanted = offset < 0 || offset > 49 ? 4
                               : length < 0              ? 3
                               : offset == length        ? 2
                               : offset > length         ? 4
                                                         : 1 | (static_cast<U64>(offset + 32) << 8);
            require(file_call_test_service(input.data()) == wanted, "actual file service offset and status");
            put_word(input, 16, 1);
            require(file_call_test_service(input.data()) == 4, "file service rejects reserved request");
        }
    }
}
auto named_read_lifetime_cases() -> void {
    NamedFixture n;
    n.submit("write a payload");
    const auto saved = n.files.saved();
    auto invalid = file_update(saved, "crc a");
    put_word(invalid, 352, 7);
    require(!n.files.update(invalid) && !n.files.selected() && n.files.saved() == saved,
            "unknown read action rejected without mutation");
    for (const auto command : {"cat a", "peek a", "wc a", "crc a"}) {
        for (unsigned phase = 0; phase < 6; ++phase) {
            n.start(command);
            const auto endpoint = *n.f.mailbox.endpoint(n.f.client);
            require(n.files.matches_read(n.f.registry, n.f.mailbox, n.f.client, endpoint), "matching read authority");
            user::DomainRegistry alien;
            ipc::Mailbox alien_box{alien};
            require(!n.files.matches_read(alien, n.f.mailbox, n.f.client, endpoint) &&
                        !n.files.matches_read(n.f.registry, alien_box, n.f.client, endpoint) &&
                        !n.files.matches_read(n.f.registry, n.f.mailbox, n.f.service, endpoint) &&
                        !n.files.matches_read(
                            n.f.registry, n.f.mailbox, n.f.client, ipc::Endpoint{0, endpoint.generation() + 1}),
                    "read authority rejects foreign context, owner and generation");
            require(!n.files.update(file_update(n.files.saved(), "write a changed")),
                    "bound selection freezes revision");
            require(!n.files.bind_read(n.f.registry, n.f.mailbox, n.f.client, n.f.service), "read lease cannot rebind");
            require(!n.files.bind(n.f.registry, n.f.mailbox, n.f.client, n.f.service, n.f.stream),
                    "read lease cannot become writable");
            require(!n.files.complete(n.f.registry, n.f.mailbox, n.f.client, endpoint, n.f.stream),
                    "partial read cannot mint replacement receipt");
            if (phase >= 1)
                n.f.request();
            U64 reply = 0;
            if (phase >= 2)
                reply = n.f.receive(11);
            if (phase >= 3)
                n.f.reply(reply);
            if (phase >= 4)
                reply = n.f.consume();
            if (phase >= 5)
                n.f.acknowledge(reply);
            require(!n.f.stream.ready_to_finish(), "partial read is not full-stream completion");
            user::DomainRegistry foreign;
            ipc::Mailbox other{foreign};
            require(!n.files.release_read(foreign, other) && !n.files.release_read(n.f.registry, other) &&
                        !n.files.release_read(foreign, n.f.mailbox),
                    "read release retains both authority contexts");
            require(!n.files.release_read(n.f.registry, n.f.mailbox), "read release refuses live participants");
            n.f.retire(true);
            require(n.files.release_read(n.f.registry, n.f.mailbox),
                    "cancelled partial read releases only after retirement");
            require(!n.files.release_read(n.f.registry, n.f.mailbox), "read release consumes lease once");
            require(!n.files.matches_read(n.f.registry, n.f.mailbox, n.f.client, endpoint),
                    "retired read authority cannot wake");
            require(n.files.saved() == saved, "read release preserves all file bytes and revision");
            require(!n.files.selected() && !n.files.writable() &&
                        std::all_of(n.files.projection().begin(),
                                    n.files.projection().end(),
                                    [](std::byte value) {
                                        return value == std::byte{};
                                    }),
                    "released read selection and projection are scrubbed");
            require(!n.f.stream.finish(), "retired partial read does not become a complete output");
        }
    }
    n.start("cat a");
    require(n.f.stream.cancel(), "cancel read before independent retirement controls");
    n.f.note.release();
    require(n.f.registry.destroy(n.f.client), "retire only read client");
    require(!n.files.release_read(n.f.registry, n.f.mailbox), "live read service prevents release");
    require(n.f.registry.destroy(n.f.service), "retire read service");
    require(!n.files.release_read(n.f.registry, n.f.mailbox), "dead handles do not replace grant revocation");
    require(n.f.mailbox.revoke(ipc::Phase::inactive) && n.files.release_read(n.f.registry, n.f.mailbox),
            "read grant release requires explicit revocation");
    n.start("upper a");
    require(!n.files.bind_read(n.f.registry, n.f.mailbox, n.f.client, n.f.service) &&
                !n.files.release_read(n.f.registry, n.f.mailbox),
            "writable selection cannot use read lease");
    n.files.abort();
    n.f.retire(true);
    n.read("a", "payload");
}
// Retaining a service is a distinct read-only authority, never a relaxation of
// ordinary read retirement or writable publication.
auto file_service_transition_cases() -> void {
    // Explicit table is independent of both the source policy and its decoder.
    constexpr std::array<std::array<U64, 4>, 4> expected{{
        {{0x010201, 0, 0, 0x050001}},
        {{0x020201, 0, 0, 0x040001}},
        {{0, 0x030101, 0x050301, 0}},
        {{0, 0x040001, 0x050301, 0}},
    }};
    for (U64 state = 0; state < 6; ++state) {
        for (U64 event = 0; event < 6; ++event) {
            const U64 wanted = state < 4 && event < 4 ? expected[state][event] : 0;
            const auto actual = file_service_test_transition(state, event);
            require(actual == wanted, "source lifecycle exact independent transition table");
            const auto decoded = program::FileServiceTransition::decode(actual, state, event);
            require(decoded.has_value() == (wanted != 0), "lifecycle decoder agrees only with canonical transition");
            if (decoded)
                require(decoded->next() == ((wanted >> 8) & 255) && decoded->effect() == (wanted >> 16),
                        "copied lifecycle next state and effect");
            for (U64 next = 0; next < 6; ++next)
                for (U64 effect = 0; effect < 7; ++effect) {
                    const auto proposal = 1 | (next << 8) | (effect << 16);
                    require(program::FileServiceTransition::decode(proposal, state, event).has_value() ==
                                (proposal == wanted && wanted != 0),
                            "reject forged lifecycle state/effect");
                }
            for (U64 status = 0; status < 256; ++status)
                if (status != 1)
                    require(!program::FileServiceTransition::decode((wanted & ~U64{255}) | status, state, event),
                            "lifecycle requires canonical accepted discriminant");
            if (wanted)
                for (unsigned bit = 24; bit < 64; ++bit)
                    require(!program::FileServiceTransition::decode(wanted | (U64{1} << bit), state, event),
                            "lifecycle reserved high bits rejected");
        }
    }
    for (const U64 invalid : {U64{256}, U64{UINT64_MAX}}) {
        require(file_service_test_transition(invalid, 0) == 0 && file_service_test_transition(0, invalid) == 0,
                "source lifecycle rejects wide invalid state/event");
        require(!program::FileServiceTransition::decode(0x010201, invalid, 0) &&
                    !program::FileServiceTransition::decode(0x010201, 0, invalid),
                "decoder rejects wide invalid context");
    }
    U64 state = 0;
    for (const auto event : {0, 1, 0, 2, 2, 1, 0, 1, 3}) {
        const auto decoded =
            program::FileServiceTransition::decode(file_service_test_transition(state, event), state, event);
        require(decoded.has_value(), "create reuse sticky poison recreate and exit sequence");
        state = decoded->next();
    }
    require(state == 0, "lifecycle final absent state");
}
auto retained_read_lifetime_cases() -> void {
    NamedFixture n;
    n.submit("write a payload");
    n.submit("write b other");
    const auto saved = n.files.saved();
    auto client = *n.f.registry.create();
    const auto service = *n.f.registry.create();
    const auto identity = n.f.registry.incarnation(service);
    ipc::Endpoint previous_client{}, previous_service{};
    U64 previous_ticket = 0;
    for (unsigned stage = 0; stage < 6; ++stage) {
        if (stage)
            client = *n.f.registry.create();
        n.submit(stage % 2 ? "crc b" : "wc a");
        require(n.f.mailbox.bind(client, service), "retained service fresh command mailbox");
        const auto endpoint = *n.f.mailbox.endpoint(client);
        const auto peer = *n.f.mailbox.endpoint(service);
        require(n.files.bind_read_retained(n.f.registry, n.f.mailbox, client, service), "explicit retained read bind");
        require(n.files.matches_read(n.f.registry, n.f.mailbox, client, endpoint), "retained fresh read authority");
        require(!n.files.bind_read(n.f.registry, n.f.mailbox, client, service) &&
                    !n.files.bind_read_retained(n.f.registry, n.f.mailbox, client, service),
                "retained read cannot rebind");
        require(!n.files.release_read_retained(n.f.registry, n.f.mailbox), "retained read refuses live caller");
        require(!n.files.complete(n.f.registry, n.f.mailbox, client, endpoint, n.f.stream),
                "retained read cannot authorize writable publication");
        if (stage) {
            require(endpoint.generation() > previous_client.generation() &&
                        n.f.registry.incarnation(service) == identity,
                    "fresh read generation retains exact service incarnation");
            require(!n.files.matches_read(n.f.registry, n.f.mailbox, client, previous_client) &&
                        !n.f.mailbox.submit(client, ipc::Phase::request, previous_client, ipc::Request{0, 0}) &&
                        !n.f.mailbox.receive(service, ipc::Phase::service, previous_service, previous_ticket),
                    "retained service rejects previous command grants and ticket");
        }
        U64 ticket = 0;
        if (stage >= 1) {
            const auto submitted = n.f.mailbox.submit(client, ipc::Phase::request, endpoint, ipc::Request{0, 0});
            require(submitted.has_value(), "retained copied request");
            ticket = *submitted;
        }
        if (stage >= 2)
            require(n.f.mailbox.receive(service, ipc::Phase::service, peer, ticket).has_value(), "retained delivery");
        if (stage >= 3)
            require(n.f.mailbox.reply(service, ipc::Phase::service, peer, ticket, 1 | ('o' << 8)), "retained reply");
        if (stage >= 4)
            require(n.f.mailbox.consume(client, ipc::Phase::completion, endpoint, ticket).has_value(),
                    "retained consume");
        if (stage >= 5)
            require(n.f.mailbox.recycle(ipc::Phase::inactive), "retained recycle");
        if (stage == 1 || stage == 2)
            require(n.f.mailbox.cancel(ipc::Phase::inactive), "retained partial cancellation");
        if (stage >= 1 && stage <= 3)
            require(n.f.mailbox.consume(client, ipc::Phase::completion, endpoint, ticket).has_value(),
                    "retained terminal consumption");
        require(n.f.registry.destroy(client), "retained caller retirement");
        require(!n.files.release_read_retained(n.f.registry, n.f.mailbox), "dead caller does not replace revocation");
        require(n.f.mailbox.revoke(ipc::Phase::inactive), "retained grant revocation");
        user::DomainRegistry other;
        ipc::Mailbox foreign{other};
        require(!n.files.release_read_retained(other, n.f.mailbox) &&
                    !n.files.release_read_retained(n.f.registry, foreign),
                "retained original authority contexts");
        require(n.f.registry.activate(service), "activate retained service negative control");
        require(!n.files.release_read_retained(n.f.registry, n.f.mailbox),
                "active service cannot be retained at boundary");
        require(n.f.registry.deactivate(service), "retained service returns to ready");
        require(!n.files.release_read(n.f.registry, n.f.mailbox), "ordinary retirement still requires dead service");
        require(n.files.release_read_retained(n.f.registry, n.f.mailbox),
                "retained release after caller and grants retire");
        require(!n.files.release_read_retained(n.f.registry, n.f.mailbox) &&
                    !n.files.matches_read(n.f.registry, n.f.mailbox, client, endpoint),
                "retained release consumes authority");
        require(n.files.saved() == saved && n.files.projection() == program::Note::Value{} &&
                    n.f.registry.ready(service) && n.f.mailbox.scrubbed(),
                "retained boundary preserves files and scrubs projection");
        previous_client = endpoint;
        previous_service = peer;
        previous_ticket = ticket;
    }
    client = *n.f.registry.create();
    n.submit("wc a");
    require(n.f.mailbox.bind(client, service) && n.files.bind_read_retained(n.f.registry, n.f.mailbox, client, service),
            "retained replacement setup");
    require(n.f.mailbox.revoke(ipc::Phase::inactive) && n.f.registry.destroy(service), "retire original service");
    const auto replacement = *n.f.registry.create();
    require(n.f.registry.destroy(client) && n.f.registry.incarnation(replacement) != identity,
            "replacement service has distinct incarnation");
    require(!n.files.release_read_retained(n.f.registry, n.f.mailbox),
            "same service slot is not original retained owner");
    require(n.files.release_read(n.f.registry, n.f.mailbox), "unhealthy retained read can fully retire");
    require(n.f.registry.destroy(replacement), "retire replacement control");
    n.start("cat a");
    require(n.f.stream.cancel(), "ordinary read cancellation");
    n.f.note.release();
    require(n.f.mailbox.revoke(ipc::Phase::inactive) && n.f.registry.destroy(n.f.client), "ordinary caller retired");
    require(!n.files.release_read_retained(n.f.registry, n.f.mailbox) &&
                !n.files.release_read(n.f.registry, n.f.mailbox),
            "ordinary read does not acquire retention authority");
    require(n.f.registry.destroy(n.f.service) && n.files.release_read(n.f.registry, n.f.mailbox),
            "ordinary full retirement");
    n.start("upper a");
    require(!n.files.release_read_retained(n.f.registry, n.f.mailbox), "writable binding cannot retain read service");
    n.files.abort();
    n.f.retire(true);
}
auto named_file_cases() -> void {
    NamedFixture n;
    Files::Value initial{};
    files_test_initial(initial.data());
    require(initial == n.files.saved(), "actual protected-files constructor matches native initialization");
    n.read("missing", "", true);
    n.submit("write a lower");
    n.submit("write b Keep Me");
    n.submit("write c ");
    n.submit("write d fourth");
    const auto full = n.files.saved();
    n.submit("write e rejected");
    require(n.files.saved() == full, "full store refusal preserves all bytes");
    n.append("a", "case");
    n.read("a", "lowercase");
    const auto appended = n.files.saved();
    for (const auto command : {"append missing x", "append note x", "append a", "append", "append ../a x"}) {
        n.submit(command);
        require(n.files.saved() == appended, "rejected append preserves complete store and revision");
    }
    const auto before_empty = file_update(n.files.saved(), "upper a");
    n.append("a", "");
    require(n.files.saved() != appended, "empty append advances revision");
    Files::ReplaceInput stale_append{};
    std::copy(n.files.saved().begin(), n.files.saved().end(), stale_append.begin());
    std::copy_n(before_empty.begin() + 360, Files::Selection{}.size(), stale_append.begin() + 272);
    put_word(stale_append, 496, 0);
    const auto stale_append_result = file_replace(stale_append);
    require(std::equal(n.files.saved().begin(), n.files.saved().end(), stale_append_result.begin()),
            "empty append invalidates prior replacement selection");
    n.upper("a", "LOWERCASE");
    n.read("b", "Keep Me");
    n.read("c", "");
    n.read("d", "fourth");
    n.upper("c", "");
    n.submit("rm d");
    const std::string maximum(49, 'z');
    n.submit("write abcdefgh " + maximum);
    n.upper("abcdefgh", std::string(49, 'Z'));
    const auto saved = n.files.saved();
    for (const auto command : {"write abcdefghi x", "upper a extra", "upper ../a", "rm missing", "append abcdefgh x"}) {
        n.submit(command);
        require(n.files.saved() == saved, "invalid command preserves complete store");
    }
    // A privately retained selection cannot outlive any mutation, even rm/reuse.
    const auto selection = file_update(n.files.saved(), "upper a");
    n.submit("rm a");
    n.submit("write a replacement");
    Files::ReplaceInput stale{};
    std::copy(n.files.saved().begin(), n.files.saved().end(), stale.begin());
    std::copy_n(selection.begin() + 360, Files::Selection{}.size(), stale.begin() + 272);
    stale[432] = std::byte{'X'};
    put_word(stale, 496, 1);
    const auto rejected = file_replace(stale);
    require(std::equal(n.files.saved().begin(), n.files.saved().end(), rejected.begin()),
            "stale slot selection preserves store");
    n.read("a", "replacement");
    // Exhaustion refuses writes/removal/replacement without disabling reads.
    auto exhausted = n.files.saved();
    put_word(exhausted, 264, UINT64_MAX);
    for (const auto command : {"write a x", "rm a", "write e x", "append a x", "append a "}) {
        const auto result = file_update(exhausted, command);
        require(std::equal(exhausted.begin(), exhausted.end(), result.begin()), "revision exhaustion preserves store");
    }
    const auto exhausted_selection = file_update(exhausted, "upper a");
    Files::ReplaceInput exhausted_replace{};
    std::copy(exhausted.begin(), exhausted.end(), exhausted_replace.begin());
    std::copy_n(exhausted_selection.begin() + 360, Files::Selection{}.size(), exhausted_replace.begin() + 272);
    exhausted_replace[432] = std::byte{'X'};
    put_word(exhausted_replace, 496, 1);
    const auto exhausted_result = file_replace(exhausted_replace);
    require(std::equal(exhausted.begin(), exhausted.end(), exhausted_result.begin()),
            "revision exhaustion rejects selected replacement atomically");
    const auto readable = file_update(exhausted, "cat a");
    require(std::to_integer<unsigned>(readable[352]) == 2, "revision exhaustion still permits protected read");
    // Dead owner handles alone do not prove the grant table was revoked.
    n.start("upper a");
    n.run();
    require(n.files.complete(n.f.registry, n.f.mailbox, n.f.client, *n.f.mailbox.endpoint(n.f.client), n.f.stream),
            "complete skipped-revoke probe");
    n.f.note.release();
    require(n.f.registry.destroy(n.f.client) && n.f.registry.destroy(n.f.service), "retire owners without revoke");
    require(!n.f.mailbox.revoked() && !n.files.retire(n.f.registry, n.f.mailbox),
            "dead participants do not impersonate explicit grant revocation");
    require(n.f.mailbox.revoke(ipc::Phase::inactive) && n.files.retire(n.f.registry, n.f.mailbox),
            "actual revoke admits completed retirement");
    n.files.abort();
    require(n.f.stream.cancel(), "discard skipped-revoke probe");
    // Cancelling/restarting the same ledger must not replace the bound run.
    n.start("upper a");
    require(n.f.stream.cancel() && n.f.stream.begin({}, 0), "replace live ledger run");
    require(!n.files.complete(n.f.registry, n.f.mailbox, n.f.client, *n.f.mailbox.endpoint(n.f.client), n.f.stream),
            "same-address new stream cannot use a former file grant");
    n.files.abort();
    n.f.retire(true);
    n.start("upper a");
    n.run();
    require(n.files.complete(n.f.registry, n.f.mailbox, n.f.client, *n.f.mailbox.endpoint(n.f.client), n.f.stream),
            "complete before run-reuse probe");
    n.f.retire();
    require(n.files.retire(n.f.registry, n.f.mailbox), "retired run-reuse probe");
    require(n.f.stream.cancel() && n.f.stream.begin({}, 0), "restart retired ledger");
    Files::ReplaceInput reused{};
    require(!n.files.replacement(n.f.stream, reused), "retired receipt rejects same-address new run");
    n.files.abort();
    require(n.f.stream.cancel(), "discard reused empty run");
    n.read("a", "replacement");
    n.start("upper missing");
    n.run();
    require(!n.files.writable() &&
                !n.files.complete(n.f.registry, n.f.mailbox, n.f.client, *n.f.mailbox.endpoint(n.f.client), n.f.stream),
            "Aurora missing-uppercase selection has no replacement authority");
    n.f.retire();
    n.files.abort();
    auto absent = n.f.stream.finish();
    require(absent && absent->missing() && absent->length() == 0, "missing uppercase completes a protected read");
    absent->scrub();
    n.read("missing", "", true);
    for (unsigned mode = 1; mode <= 3; ++mode) {
        n.start("upper a", mode);
        n.read("a", "replacement");
    }
    n.start("cat a", 3);
    n.read("a", "replacement");

    for (unsigned stage = 0; stage < 7; ++stage) {
        n.submit("write a fault safe");
        const auto old = n.files.saved();
        n.start("upper a");
        const auto old_client = *n.f.mailbox.endpoint(n.f.client);
        n.f.round();
        U64 reply = 0;
        if (stage >= 1)
            n.f.request();
        if (stage >= 2)
            reply = n.f.receive(11);
        if (stage >= 3)
            n.f.reply(reply);
        if (stage >= 4)
            reply = n.f.consume();
        if (stage >= 5)
            n.f.acknowledge(reply);
        if (stage == 6)
            n.run();
        n.files.abort();
        n.f.retire(true);
        require(n.files.saved() == old, "every named cancellation stage preserves complete store");
        n.start("upper a");
        require(!n.files.complete(n.f.registry, n.f.mailbox, n.f.client, old_client, n.f.stream),
                "reused domain rejects stale grant");
        n.run();
        n.save();
        n.read("a", "FAULT SAFE");
        n.read("b", "Keep Me");
    }
}
// Golden contents, actual compiled worker and existing native authority owner.
// A later worker fault is distinct from failure of a committed response turn.
auto protected_append_cases() -> void {
    NamedFixture n;
    n.submit("write a old");
    n.submit("write b Keep lower");
    n.submit("write c ");
    n.submit("write d fourth");
    n.append("a", " new");
    n.read("a", "old new");
    n.read("b", "Keep lower");
    n.append("c", "");
    n.read("c", "");
    n.append("c", " space ");
    n.read("c", " space ");
    // Every cancellation cut follows one acknowledged candidate byte and must
    // preserve the latest commit, not a stale pre-append copy of the namespace.
    for (unsigned stage = 0; stage < 7; ++stage) {
        const auto saved = n.files.saved();
        n.start("append a !");
        const auto stale = *n.f.mailbox.endpoint(n.f.client);
        n.f.round();
        U64 reply = 0;
        if (stage >= 1)
            n.f.request();
        if (stage >= 2)
            reply = n.f.receive(15);
        if (stage >= 3)
            n.f.reply(reply);
        if (stage >= 4)
            reply = n.f.consume();
        if (stage >= 5)
            n.f.acknowledge(reply);
        if (stage == 6)
            n.run();
        n.files.abort();
        n.f.retire(true);
        require(n.files.saved() == saved, "later cancelled append preserves latest complete namespace");
        n.start("append a ");
        require(!n.files.complete(n.f.registry, n.f.mailbox, n.f.client, stale, n.f.stream),
                "later append rejects stale endpoint generation");
        n.run();
        n.save();
        n.read("a", "old new");
        n.read("b", "Keep lower");
    }
    for (const auto phase : {I64{8}, I64{4}, I64{10}}) {
        const auto saved = n.files.saved();
        n.start("append a later");
        n.f.round();
        if (phase != 8)
            n.f.request();
        if (phase == 4)
            static_cast<void>(n.f.receive(15));
        if (phase == 10) {
            n.f.reply(n.f.receive(15));
            static_cast<void>(n.f.consume());
        }
        std::array<std::byte, Note::stream_record_bytes> record{};
        require(n.f.note.stage_stream(record, *n.f.mailbox.endpoint(n.f.service), 4, ipc::Request{1, 1}),
                "actual append fault input");
        const auto child = fork();
        require(child >= 0, "append emitted fault child");
        if (child == 0) {
            if (phase == 4)
                static_cast<void>(note_test_service(record.data()));
            else
                static_cast<void>(aurora_user_main(phase, 1, 1));
            std::_Exit(3);
        }
        int status = 0;
        require(waitpid(child, &status, 0) == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGILL,
                "actual later append worker emitted bounds fault");
        n.files.abort();
        n.f.retire(true);
        require(n.files.saved() == saved, "later worker fault preserves latest append commit");
        n.read("a", "old new");
    }
    // This hosted owner observes response failure without pretending a source
    // worker can fault after its retirement; the guest separately checks exit.
    n.append("a", "!", false);
    n.read("a", "old new!");
    n.read("b", "Keep lower");
    n.read("c", " space ");
    n.read("d", "fourth");
    NamedFixture exhausted(1);
    exhausted.submit("write a original");
    const auto saved = exhausted.files.saved();
    exhausted.start("append a suffix");
    exhausted.files.abort();
    exhausted.f.retire(true);
    exhausted.submit("append a suffix");
    require(!exhausted.f.stream.begin_read() && exhausted.f.stream.run() == 1 && exhausted.f.stream.scrubbed() &&
                exhausted.files.saved() == saved,
            "append run exhaustion refuses without wrap or saved mutation");
    require(!exhausted.files.bind(
                exhausted.f.registry, exhausted.f.mailbox, exhausted.f.client, exhausted.f.service, exhausted.f.stream),
            "exhausted append stream cannot mint publication authority");
    exhausted.files.abort();
}

} // namespace

auto main() -> int {
    require(command_stream_contract() == 0, "shared Aurora stream behavioral fixture");
    file_byte_reply_cases();
    named_read_lifetime_cases();
    retained_read_lifetime_cases();
    file_service_transition_cases();
    named_file_cases();
    protected_append_cases();
    command_cases();
    representation_controls();
    reply_controls();
    cancellation_cases();
    upper_save_cases();
    replacement_controls();
    upper_cancellation_cases();
    emitted_faults();
    upper_regression();
    std::printf(
        "PASS: %llu source-native note checks; real Mailbox bytes/EOF, retained note, cancellation and upper save; "
        "nine emitted SIGILL probes, hosted cleanup separately scoped\n",
        static_cast<unsigned long long>(checks));
}
