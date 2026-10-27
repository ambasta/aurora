#pragma once
#include "console-session.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <type_traits>

extern "C" void __au_runtime_program_session(const void *, void *);

namespace aurora::program {
// Only Aurora interprets the retained state. Native code executes a returned
// effect once and feeds back that operation's bounded completion fact.
class Session final {
public:
    enum class Event : std::uint64_t {
        begin,
        response,
        input,
        note,
        files
    };
    enum class Effect : std::uint64_t {
        invalid,
        ready,
        file_ready,
        input,
        note,
        files,
        upper,
        read_note,
        upper_note,
        file,
        peek,
        wc,
        crc,
        unknown,
        note_saved,
        file_reply,
        abort_file,
        exited,
        failed
    };

private:
    using State = std::array<std::uint64_t, 4>;
    class Argument final {
    public:
        State state;
        std::uint64_t event, value, carry;
    };
    class Result final {
    public:
        State state;
        std::uint64_t effect, carry, outcome;
    };
    State state_{};
    std::uint64_t carry_{}, outcome_{};
    static_assert(sizeof(Argument) == 56 && offsetof(Argument, event) == 32 && offsetof(Argument, value) == 40 &&
                  offsetof(Argument, carry) == 48);
    static_assert(sizeof(Result) == 56 && offsetof(Result, effect) == 32 && offsetof(Result, carry) == 40 &&
                  offsetof(Result, outcome) == 48);

public:
    [[nodiscard]] auto advance(Event event, std::uint64_t value = 0, std::uint64_t carry = 0) -> Effect {
        const Argument argument{state_, static_cast<std::uint64_t>(event), value, carry};
        Result result{};
        __au_runtime_program_session(&argument, &result);
        if (result.effect == 0 || result.effect > static_cast<std::uint64_t>(Effect::failed) || result.carry > 1 ||
            result.outcome > 2)
            return Effect::invalid;
        state_ = result.state;
        carry_ = result.carry;
        outcome_ = result.outcome;
        return static_cast<Effect>(result.effect);
    }
    [[nodiscard]] auto after_cr() const -> std::uint64_t {
        return carry_;
    }
    [[nodiscard]] auto outcome() const -> std::uint64_t {
        return outcome_;
    }
};

// Private supervisor bridge records. Only the argument carries a checked
// Console grant; the copied result contains no address or authority.
class SubmissionArgument final {
public:
    console::ServiceArgument console;
    std::uint64_t after_cr;
};

class Submission final {
public:
    enum class Action : std::uint64_t {
        command = 0,
        upper_payload = 1,
        requested_exit = 2,
        output_failure = 3
    };
    class Record final {
    public:
        std::array<std::uint8_t, 64> bytes{};
        std::int64_t count{};
        std::uint64_t action{}, after_cr{};
    };

private:
    Record record_{};

public:
    [[nodiscard]] auto data() -> void * {
        return &record_;
    }
    [[nodiscard]] auto bytes() const -> const std::array<std::uint8_t, 64> & {
        return record_.bytes;
    }
    [[nodiscard]] auto length() const -> std::size_t {
        return static_cast<std::size_t>(record_.count);
    }
    [[nodiscard]] auto action() const -> Action {
        return static_cast<Action>(record_.action);
    }
    [[nodiscard]] auto after_cr() const -> std::uint64_t {
        return record_.after_cr;
    }
    [[nodiscard]] auto valid() const -> bool {
        if (record_.count < 0 || record_.count > 64 || record_.action > 3 || record_.after_cr > 1)
            return false;
        if ((action() == Action::command && record_.count == 0) || (record_.action >= 2 && record_.count != 0))
            return false;
        for (std::size_t index = 0; index < record_.bytes.size(); ++index) {
            const auto byte = record_.bytes[index];
            if (index < length() ? byte < 32 || byte > 126 : byte != 0)
                return false;
        }
        return true;
    }
    auto scrub() -> void {
        auto *bytes = reinterpret_cast<volatile std::byte *>(&record_);
        for (std::size_t index = 0; index < sizeof(record_); ++index)
            bytes[index] = std::byte{0};
    }
};

// A supervisor response is ordinary copied data. Check its raw kind before
// Aurora loads a typed enum. Source policy validates the count, payload kind
// and zero suffix before any output; payload bytes retain their exact values.
class Response final {
public:
    enum class Kind : std::uint64_t {
        ready = 0,
        output = 1,
        note_missing = 2,
        file_missing = 3,
        note_saved = 4,
        file_saved = 5,
        file_reply = 6,
        stopped = 7,
        unknown = 8
    };
    class Record final {
    public:
        std::array<std::uint8_t, 64> bytes{};
        std::int64_t count{};
        std::uint64_t kind{};
    };

private:
    Record record_{};

public:
    explicit constexpr Response(Kind kind = Kind::ready) : record_{{}, 0, static_cast<std::uint64_t>(kind)} {
    }
    [[nodiscard]] auto data() -> void * {
        return &record_;
    }
    [[nodiscard]] auto canonical_kind() const -> bool {
        return record_.kind <= static_cast<std::uint64_t>(Kind::unknown);
    }
    [[nodiscard]] auto payload(std::span<const std::byte> bytes) -> bool {
        if (bytes.size() > record_.bytes.size())
            return false;
        record_.bytes.fill(0);
        record_.count = static_cast<std::int64_t>(bytes.size());
        for (std::size_t index = 0; index < bytes.size(); ++index)
            record_.bytes[index] = std::to_integer<std::uint8_t>(bytes[index]);
        return true;
    }
    [[nodiscard]] auto payload(std::span<const std::uint8_t> bytes) -> bool {
        return payload(std::as_bytes(bytes));
    }
    auto scrub() -> void {
        auto *bytes = reinterpret_cast<volatile std::byte *>(&record_);
        for (std::size_t index = 0; index < sizeof(record_); ++index)
            bytes[index] = std::byte{0};
    }
};

class ResponseArgument final {
public:
    console::ServiceArgument console;
    Response response;

    auto scrub() -> void {
        auto *bytes = reinterpret_cast<volatile std::byte *>(this);
        for (std::size_t index = 0; index < sizeof(*this); ++index)
            bytes[index] = std::byte{0};
    }
};
static_assert(std::is_standard_layout_v<console::ServiceArgument> && sizeof(console::ServiceArgument) == 16 &&
              offsetof(console::ServiceArgument, grant) == 0 && offsetof(console::ServiceArgument, generation) == 8);
static_assert(std::is_standard_layout_v<SubmissionArgument> && sizeof(SubmissionArgument) == 24 &&
              offsetof(SubmissionArgument, console) == 0 && offsetof(SubmissionArgument, after_cr) == 16);
static_assert(std::is_standard_layout_v<Submission::Record> && sizeof(Submission::Record) == 88 &&
              offsetof(Submission::Record, bytes) == 0 && offsetof(Submission::Record, count) == 64 &&
              offsetof(Submission::Record, action) == 72 && offsetof(Submission::Record, after_cr) == 80);
static_assert(std::is_standard_layout_v<Submission> && sizeof(Submission) == 88);
// These native layouts are fixed, but ProgramSubmission/ProgramResponse and
// their Console entries are not yet covered by the generated ABI admission.
static_assert(std::is_standard_layout_v<Response::Record> && sizeof(Response::Record) == 80 &&
              offsetof(Response::Record, bytes) == 0 && offsetof(Response::Record, count) == 64 &&
              offsetof(Response::Record, kind) == 72);
static_assert(std::is_standard_layout_v<Response> && sizeof(Response) == 80);
static_assert(std::is_standard_layout_v<ResponseArgument> && sizeof(ResponseArgument) == 96 &&
              offsetof(ResponseArgument, console) == 0 && offsetof(ResponseArgument, response) == 16);
} // namespace aurora::program
