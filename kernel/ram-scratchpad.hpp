#pragma once
#include "console-session.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>
#include <type_traits>

namespace aurora::scratchpad {
// Private, pointer-free transport copies, not a file store. Validate the complete
// raw representation before an Aurora enum/class crosses the typed boundary.
template <class T> auto scrub(T &value) -> void {
    auto *bytes = reinterpret_cast<volatile std::byte *>(&value);
    for (std::size_t index = 0; index < sizeof(T); ++index)
        bytes[index] = std::byte{0};
}
[[nodiscard]] constexpr auto payload(const std::array<std::uint8_t, 64> &bytes, std::uint64_t count) -> bool {
    if (count > 49)
        return false;
    for (std::size_t index = 0; index < bytes.size(); ++index)
        if (index < count ? bytes[index] < 32 || bytes[index] > 126 : bytes[index] != 0)
            return false;
    return true;
}
class Command final {
public:
    enum class Operation : std::uint64_t {
        get = 0,
        put = 1
    };
    std::array<std::uint8_t, 64> bytes{};
    std::uint64_t count{}, operation{};
    [[nodiscard]] constexpr auto valid() const -> bool {
        return operation <= 1 && (operation == 1 || count == 0) && payload(bytes, count);
    }
};
class Result final {
public:
    enum class Kind : std::uint64_t {
        incomplete = 0,
        content = 1,
        missing = 2,
        saved = 3,
        refused = 4
    };
    std::array<std::uint8_t, 64> bytes{};
    std::uint64_t count{}, kind{};
    [[nodiscard]] constexpr auto valid() const -> bool {
        return kind <= 4 && (kind == 1 || count == 0) && payload(bytes, count);
    }
    // Eligibility additionally requires an authenticated clean caller return and
    // retirement. These are only the exhaustive copied/protocol terminal pairs.
    [[nodiscard]] constexpr auto
    terminal_for(std::uint64_t operation, std::uint64_t reply, std::uint64_t data_count) const -> bool {
        if (!valid() || operation > 1 || data_count > 49)
            return false;
        return (operation == 0 && kind == 1 && reply == 3 && count == data_count) ||
               (operation == 0 && kind == 2 && reply == 4 && data_count == 0) ||
               (operation == 1 && kind == 3 && reply == 5 && data_count == 0) || (kind == 4 && reply == 6);
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
        return action <= 2 && after_cr <= 1 && command.valid() &&
               (action == 0 || (command.operation == 0 && command.count == 0));
    }
};
class Response final {
public:
    enum class Kind : std::uint64_t {
        ready = 0,
        content = 1,
        missing = 2,
        saved = 3,
        rejected = 4,
        aborted = 5,
        read_failed = 6,
        committed_caller_failed = 7,
        indeterminate_reset = 8,
        reset = 9,
        unavailable = 10,
        limit = 11
    };
    std::array<std::uint8_t, 64> bytes{};
    std::uint64_t count{}, kind{};
    explicit constexpr Response(Kind selected = Kind::ready) : kind(static_cast<std::uint64_t>(selected)) {
    }
    [[nodiscard]] constexpr auto valid() const -> bool {
        return kind <= 11 && (kind == 1 || count == 0) && payload(bytes, count);
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
static_assert(std::is_standard_layout_v<Command> && sizeof(Command) == 80 && alignof(Command) == 8 &&
              offsetof(Command, bytes) == 0 && offsetof(Command, count) == 64 && offsetof(Command, operation) == 72);
static_assert(std::is_standard_layout_v<Result> && sizeof(Result) == 80 && alignof(Result) == 8 &&
              offsetof(Result, bytes) == 0 && offsetof(Result, count) == 64 && offsetof(Result, kind) == 72);
static_assert(std::is_standard_layout_v<Submission> && sizeof(Submission) == 96 && alignof(Submission) == 8 &&
              offsetof(Submission, command) == 0 && offsetof(Submission, action) == 80 &&
              offsetof(Submission, after_cr) == 88);
static_assert(std::is_standard_layout_v<Response> && sizeof(Response) == 80 && alignof(Response) == 8 &&
              offsetof(Response, bytes) == 0 && offsetof(Response, count) == 64 && offsetof(Response, kind) == 72);
static_assert(std::is_standard_layout_v<InputArgument> && sizeof(InputArgument) == 24 &&
              offsetof(InputArgument, console) == 0 && offsetof(InputArgument, after_cr) == 16);
static_assert(std::is_standard_layout_v<ResponseArgument> && sizeof(ResponseArgument) == 96 &&
              offsetof(ResponseArgument, console) == 0 && offsetof(ResponseArgument, response) == 16);

// The adapter authenticates the owner's complete mapping/lease set before
// supplying this exact fixed window from its last stack page. No user pointer is
// accepted. The wrapper alone writes the private prefix during launch.
class CopiedStack final {
public:
    static constexpr std::size_t reservation = 192, envelope = 48;
    static constexpr std::size_t prefix = 0, command = 16, result = 96, sentinel = 176;
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
                                      std::uint64_t operation,
                                      std::uint64_t count,
                                      Result &output) -> bool {
        scrub(output);
        if (grant != 0 || !generation || operation > 1 || count > 49 || (operation == 0 && count != 0) ||
            word(bytes, prefix) != grant || word(bytes, prefix + 8) != generation ||
            word(bytes, command + 64) != count || word(bytes, command + 72) != operation)
            return false;
        // Recheck the staged canonical command and the entire zero sentinel.
        for (std::size_t index = 0; index < 64; ++index) {
            const auto byte = std::to_integer<std::uint8_t>(bytes[command + index]);
            if (index < count ? byte < 32 || byte > 126 : byte != 0)
                return false;
        }
        for (std::size_t index = sentinel; index < reservation; ++index)
            if (bytes[index] != std::byte{0})
                return false;
        for (std::size_t index = 0; index < 64; ++index)
            output.bytes[index] = std::to_integer<std::uint8_t>(bytes[result + index]);
        output.count = word(bytes, result + 64);
        output.kind = word(bytes, result + 72);
        if (!output.valid()) {
            scrub(output);
            return false;
        }
        return true;
    }
};
static_assert(CopiedStack::command == 16 && CopiedStack::command + sizeof(Command) == CopiedStack::result &&
              CopiedStack::result + sizeof(Result) == CopiedStack::sentinel &&
              CopiedStack::sentinel + 16 == CopiedStack::reservation &&
              CopiedStack::reservation + CopiedStack::envelope == 240);
} // namespace aurora::scratchpad
