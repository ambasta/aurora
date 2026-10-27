#pragma once
#include "console-session.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <type_traits>

namespace aurora::named {
// Raw private copied boundaries, not a namespace store. Admission checks only
// representation, enum domains and zero suffixes; naming/write policy is Aurora.
template <class T> auto scrub(T &value) -> void {
    auto *bytes = reinterpret_cast<volatile std::byte *>(&value);
    for (std::size_t index = 0; index < sizeof(T); ++index)
        bytes[index] = std::byte{0};
}
[[nodiscard]] constexpr auto
suffix(const std::array<std::uint8_t, 64> &bytes, std::uint64_t count, std::uint64_t maximum) -> bool {
    if (count > maximum)
        return false;
    for (std::size_t index = static_cast<std::size_t>(count); index < bytes.size(); ++index)
        if (bytes[index] != 0)
            return false;
    return true;
}
class Name final {
public:
    std::array<std::uint8_t, 64> bytes{};
    std::uint64_t count{};
    [[nodiscard]] constexpr auto canonical() const -> bool {
        return suffix(bytes, count, 8);
    }
};
class Value final {
public:
    std::array<std::uint8_t, 64> bytes{};
    std::uint64_t count{};
    [[nodiscard]] constexpr auto canonical() const -> bool {
        return suffix(bytes, count, 49);
    }
};
class Command final {
public:
    enum class Operation : std::uint64_t {
        read = 0,
        write = 1
    };
    Name name;
    Value value;
    std::uint64_t operation{};
    [[nodiscard]] constexpr auto valid() const -> bool {
        return name.canonical() && name.count != 0 && value.canonical() && operation <= 1 &&
               (operation != 0 || value.count == 0);
    }
    [[nodiscard]] constexpr auto empty() const -> bool {
        return name.canonical() && name.count == 0 && value.canonical() && value.count == 0 && operation == 0;
    }
};
class Result final {
public:
    // Matches the public FileEvent source enum, not an authority or wire tag.
    enum class Event : std::uint64_t {
        unknown = 0,
        written = 1,
        read = 2,
        missing = 5,
        invalid = 6,
        full = 7,
        reserved = 8
    };
    std::array<std::uint8_t, 64> bytes{};
    std::uint64_t count{}, event{}, revision{};
    [[nodiscard]] constexpr auto valid() const -> bool {
        if (!suffix(bytes, count, 49) ||
            (event != 0 && event != 1 && event != 2 && event != 5 && event != 6 && event != 7 && event != 8) ||
            (event != 2 && count != 0))
            return false;
        for (std::size_t index = 0; index < count; ++index)
            if (bytes[index] < 32 || bytes[index] > 126)
                return false;
        return (event == 1 || event == 2 || event == 5) ? revision != 0 : revision == 0;
    }
    // Copied success alone grants no authority. The adapter also authenticates
    // the exact terminal Serve receipt, caller return, drain and retirement.
    [[nodiscard]] constexpr auto terminal_for(std::uint64_t operation,
                                              std::uint64_t reply,
                                              std::uint64_t data_count,
                                              std::uint64_t framed_revision) const -> bool {
        if (!valid() || operation > 1 || data_count > 49)
            return false;
        return (operation == 0 && event == 2 && reply == 3 && count == data_count && revision == framed_revision) ||
               (operation == 0 && event == 5 && reply == 4 && data_count == 0 && revision == framed_revision) ||
               (operation == 1 && event == 1 && reply == 5 && data_count == 0 && revision == framed_revision) ||
               (event == 6 && reply == 1542) || (event == 7 && reply == 1798) || (event == 8 && reply == 2054);
    }
};
class Submission final {
public:
    enum class Action : std::uint64_t {
        command = 0,
        requested_exit = 1,
        output_failure = 2
    };
    Command command;
    std::uint64_t action{}, after_cr{};
    [[nodiscard]] constexpr auto valid() const -> bool {
        return action <= 2 && after_cr <= 1 && (action == 0 ? command.valid() : command.empty());
    }
};
class Response final {
public:
    enum class Kind : std::uint64_t {
        ready = 0,
        completed = 1,
        aborted = 2,
        read_failed = 3,
        committed_caller_failed = 4,
        indeterminate_reset = 5,
        reset = 6,
        unavailable = 7,
        limit = 8
    };
    Name name;
    std::uint64_t submitted_size{};
    Result result;
    std::uint64_t kind{};
    explicit constexpr Response(Kind selected = Kind::ready) : kind(static_cast<std::uint64_t>(selected)) {
    }
    [[nodiscard]] constexpr auto valid() const -> bool {
        if (kind > 8 || !name.canonical() || submitted_size > 49 || !result.valid())
            return false;
        if (kind == 1)
            return name.count != 0 && result.event != 0;
        return name.count == 0 && submitted_size == 0 && result.event == 0 && result.count == 0 && result.revision == 0;
    }
};
class InputArgument final {
public:
    console::ServiceArgument console;
    std::uint64_t after_cr;
};
class ResponseArgument final {
public:
    console::ServiceArgument console;
    Response response;
};
static_assert(std::is_standard_layout_v<Name> && sizeof(Name) == 72 && alignof(Name) == 8 &&
              offsetof(Name, bytes) == 0 && offsetof(Name, count) == 64);
static_assert(std::is_standard_layout_v<Value> && sizeof(Value) == 72 && alignof(Value) == 8 &&
              offsetof(Value, bytes) == 0 && offsetof(Value, count) == 64);
static_assert(std::is_standard_layout_v<Command> && sizeof(Command) == 152 && alignof(Command) == 8 &&
              offsetof(Command, name) == 0 && offsetof(Command, value) == 72 && offsetof(Command, operation) == 144);
static_assert(std::is_standard_layout_v<Result> && sizeof(Result) == 88 && alignof(Result) == 8 &&
              offsetof(Result, bytes) == 0 && offsetof(Result, count) == 64 && offsetof(Result, event) == 72 &&
              offsetof(Result, revision) == 80);
static_assert(std::is_standard_layout_v<Submission> && sizeof(Submission) == 168 && alignof(Submission) == 8 &&
              offsetof(Submission, command) == 0 && offsetof(Submission, action) == 152 &&
              offsetof(Submission, after_cr) == 160);
static_assert(std::is_standard_layout_v<Response> && sizeof(Response) == 176 && alignof(Response) == 8 &&
              offsetof(Response, name) == 0 && offsetof(Response, submitted_size) == 72 &&
              offsetof(Response, result) == 80 && offsetof(Response, kind) == 168);
static_assert(std::is_standard_layout_v<InputArgument> && sizeof(InputArgument) == 24 &&
              offsetof(InputArgument, console) == 0 && offsetof(InputArgument, after_cr) == 16);
static_assert(std::is_standard_layout_v<ResponseArgument> && sizeof(ResponseArgument) == 192 &&
              offsetof(ResponseArgument, console) == 0 && offsetof(ResponseArgument, response) == 16);

// The adapter authenticates all four original stack leases before using this
// fixed last-page window. No caller pointer chooses an input or output address.
class CopiedStack final {
public:
    static constexpr std::size_t reservation = 288, envelope = 48;
    static constexpr std::size_t prefix = 0, command = 16, probe = 168, result = 176, sentinel = 264;
    using Window = std::span<std::byte, reservation>;
    using ConstWindow = std::span<const std::byte, reservation>;
    [[nodiscard]] static auto pristine(ConstWindow bytes) -> bool {
        for (const auto byte : bytes)
            if (byte != std::byte{0})
                return false;
        return true;
    }
    [[nodiscard]] static auto stage(Window bytes, const Command &value) -> bool {
        if (!value.valid() || !pristine(bytes))
            return false;
        const auto raw = std::as_bytes(std::span{&value, 1});
        for (std::size_t index = 0; index < raw.size(); ++index)
            bytes[command + index] = raw[index];
        return true;
    }
    [[nodiscard]] static auto word(ConstWindow bytes, std::size_t offset) -> std::uint64_t {
        std::uint64_t value = 0;
        for (unsigned index = 0; index < 8; ++index)
            value |= std::uint64_t{std::to_integer<std::uint8_t>(bytes[offset + index])} << (index * 8);
        return value;
    }
    [[nodiscard]] static auto capture(ConstWindow bytes,
                                      std::uint64_t grant,
                                      std::uint64_t generation,
                                      const Command &original,
                                      std::uint64_t expected_probe,
                                      Result &output) -> bool {
        scrub(output);
        if (grant != 0 || generation == 0 || !original.valid() || word(bytes, prefix) != grant ||
            word(bytes, prefix + 8) != generation || word(bytes, probe) != expected_probe)
            return false;
        const auto raw = std::as_bytes(std::span{&original, 1});
        for (std::size_t index = 0; index < raw.size(); ++index)
            if (bytes[command + index] != raw[index])
                return false;
        for (std::size_t index = sentinel; index < reservation; ++index)
            if (bytes[index] != std::byte{0})
                return false;
        for (std::size_t index = 0; index < 64; ++index)
            output.bytes[index] = std::to_integer<std::uint8_t>(bytes[result + index]);
        output.count = word(bytes, result + 64);
        output.event = word(bytes, result + 72);
        output.revision = word(bytes, result + 80);
        if (!output.valid()) {
            scrub(output);
            return false;
        }
        return true;
    }
};
static_assert(CopiedStack::command == 16 && CopiedStack::command + sizeof(Command) == CopiedStack::probe &&
              CopiedStack::probe + 8 == CopiedStack::result &&
              CopiedStack::result + sizeof(Result) == CopiedStack::sentinel &&
              CopiedStack::sentinel + 24 == CopiedStack::reservation &&
              CopiedStack::reservation + CopiedStack::envelope == 336);
} // namespace aurora::named
