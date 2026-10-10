#include "../kernel/program-note.hpp"
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

using U64 = std::uint64_t;
using I64 = std::int64_t;
using namespace aurora;
using program::Note;
extern "C" void __au_runtime_note_update(const void *, void *);
extern "C" void __au_runtime_note_project(const void *, void *);
extern "C" void note_test_initial(void *);
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
    alignas(16) std::array<std::byte, 128> storage{};

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
        const std::span<std::byte, Note::record_bytes> record{storage.data() + 16, Note::record_bytes};
        require(note.stage(record, grant, phase, *request), "authenticated fixed copied record");
        if (!reading)
            for (std::size_t index = 24; index < record.size(); ++index)
                require(record[index] == std::byte{0}, "upper service receives no saved-note projection");
        const auto before = storage;
        const auto result = note_test_service(record.data());
        require(storage == before, "actual service leaves full copied input immutable");
        for (std::size_t index = 0; index < 16; ++index)
            require(storage[index] == std::byte{0xa5} && storage[112 + index] == std::byte{0xa5}, "record canaries");
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
        const auto accepted = aurora_user_main(reading ? 13 : 2, static_cast<I64>(result), static_cast<I64>(ordinal));
        require(accepted >= 0 && stream.acknowledge(static_cast<U64>(accepted), ordinal),
                "actual client acknowledges actual returned bytes or EOF");
        require(mailbox.recycle(ipc::Phase::inactive), "consumed transaction recycle");
        transaction = 0;
    }

    auto round() -> void {
        request();
        reply(receive(reading ? 11 : 1));
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
    std::array<std::byte, Note::record_bytes> record{};
    record.fill(std::byte{0xa5});
    const auto before = record;
    for (const auto grant : {ipc::Endpoint{0, 17}, ipc::Endpoint{1, 0}, ipc::Endpoint{1, 18}})
        require(!note.stage(record, grant, 11, ipc::Request{1, 0}) && record == before,
                "foreign or stale stage preserves complete destination");
    note.release();
    require(note.bind(projection, ipc::Endpoint{1, 18}) && !note.matches(ipc::Endpoint{1, 17}) &&
                !note.stage(record, ipc::Endpoint{1, 17}, 11, ipc::Request{1, 0}) && record == before,
            "fresh publication excludes old generation");
    for (const auto ordinal : {U64{6}, U64{54}, maximum}) {
        require(note.stage(record, ipc::Endpoint{1, 18}, 11, ipc::Request{1, ordinal}) &&
                    note_test_service(record.data()) == 4,
                "actual service rejects bad ordinal");
    }
    for (const auto operation : {U64{0}, U64{2}, maximum})
        require(note.stage(record, ipc::Endpoint{1, 18}, 11, ipc::Request{operation, 0}) &&
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
            std::array<std::byte, Note::record_bytes> record{};
            require(f.note.stage(record, *f.mailbox.endpoint(f.service), 4, ipc::Request{1, 1}), "actual fault input");
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
} // namespace

auto main() -> int {
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
        "six emitted SIGILL probes, hosted cleanup separately scoped\n",
        static_cast<unsigned long long>(checks));
}
