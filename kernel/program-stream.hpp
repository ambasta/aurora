#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>

// Private bootstrap copied-record ABI; never callable by a protected participant.
extern "C" auto __au_runtime_stream_update(const std::byte *input, std::byte *output) -> void;

namespace aurora::program {
inline constexpr std::size_t stream_capacity = 64;
using StreamBytes = std::array<std::uint8_t, stream_capacity>;

// Copied launch data. It carries neither a pointer nor an endpoint capability.
class Input final {
    std::uint8_t byte_;
    std::uint64_t ordinal_;

public:
    constexpr Input(std::uint8_t byte, std::uint64_t ordinal) : byte_(byte), ordinal_(ordinal) {
    }
    [[nodiscard]] constexpr auto byte() const -> std::uint8_t {
        return byte_;
    }
    [[nodiscard]] constexpr auto ordinal() const -> std::uint64_t {
        return ordinal_;
    }
};

class Output final {
    friend class Stream;
    StreamBytes bytes_{};
    std::size_t length_{};
    bool missing_{};
    Output(StreamBytes bytes, std::size_t length, bool missing = false)
        : bytes_(bytes), length_(length), missing_(missing) {
    }

public:
    [[nodiscard]] auto missing() const -> bool {
        return missing_;
    }
    [[nodiscard]] auto bytes() const -> StreamBytes {
        return bytes_;
    }
    [[nodiscard]] auto length() const -> std::size_t {
        return length_;
    }
    [[nodiscard]] auto byte(std::size_t index) const -> std::optional<std::uint8_t> {
        if (index >= length_)
            return std::nullopt;
        return bytes_[index];
    }
    auto scrub() -> void {
        bytes_.fill(0);
        length_ = 0;
        missing_ = false;
    }
};

// Native identity and nonwrapping run authority surround opaque copied Aurora
// state. All byte/order/encoding/stage transitions live in console.command_stream.
// Files binds this exact noncopyable object and run; copied Aurora values cannot
// mint that receipt. The runtime still authenticates Mailbox transactions and
// retires both participants before releasing finish()'s copied output.
class Stream final {
    // Two 64-byte buffers and eight 8-byte fields, including CommandStage.
    // The all-zero private initial representation matches CommandStream(empty).
    static constexpr std::size_t state_bytes = 192;
    static constexpr std::size_t result_bytes = 280;
    using Value = std::array<std::byte, state_bytes>;
    using Update = std::array<std::byte, result_bytes>;
    // Independently checked against CommandOperation's emitted ABI enum cases.
    enum class Operation : std::uint64_t {
        begin = 0,
        begin_read = 1,
        awaiting_read = 2,
        next_input = 3,
        accept_request = 4,
        accept_reply = 5,
        acknowledge = 6,
        ready_to_finish = 7,
        finish = 8,
        cancel = 9,
        scrubbed = 10
    };
    Value saved_{};
    std::uint64_t run_{};
    const std::uint64_t run_ceiling_;

    static auto word(std::span<const std::byte> bytes, std::size_t offset) -> std::uint64_t {
        std::uint64_t value = 0;
        for (unsigned i = 0; i < 8; ++i)
            value |= std::uint64_t(std::to_integer<unsigned char>(bytes[offset + i])) << (8 * i);
        return value;
    }
    static auto put(std::span<std::byte> bytes, std::size_t offset, std::uint64_t value) -> void {
        for (unsigned i = 0; i < 8; ++i)
            bytes[offset + i] = std::byte(value >> (8 * i));
    }
    [[nodiscard]] auto evaluate(Operation operation,
                                std::uint64_t first = 0,
                                std::uint64_t second = 0,
                                const StreamBytes &bytes = {}) const -> Update {
        // [CommandStream, operation, BinaryBuffer64, first, second]. The result
        // is disjoint and stays private until the admitted Aurora call returns.
        std::array<std::byte, 280> input{};
        std::copy(saved_.begin(), saved_.end(), input.begin());
        put(input, 192, static_cast<std::uint64_t>(operation));
        for (std::size_t i = 0; i < stream_capacity; ++i)
            input[200 + i] = std::byte(bytes[i]);
        put(input, 264, first);
        put(input, 272, second);
        Update result{};
        __au_runtime_stream_update(input.data(), result.data());
        return result;
    }
    [[nodiscard]] static auto accepted(const Update &result) -> bool {
        return word(result, 272) == 1;
    }
    [[nodiscard]] auto
    apply(Operation operation, std::uint64_t first = 0, std::uint64_t second = 0, const StreamBytes &bytes = {})
        -> Update {
        const auto result = evaluate(operation, first, second, bytes);
        if (accepted(result))
            std::copy_n(result.begin(), saved_.size(), saved_.begin());
        return result;
    }

public:
    explicit constexpr Stream(std::uint64_t run_ceiling = UINT64_MAX) : run_ceiling_(run_ceiling) {
    }
    [[nodiscard]] auto run() const -> std::uint64_t {
        return run_;
    }
    Stream(const Stream &) = delete;
    auto operator=(const Stream &) -> Stream & = delete;
    Stream(Stream &&) = delete;
    auto operator=(Stream &&) -> Stream & = delete;

    [[nodiscard]] auto begin(const StreamBytes &copied_input, std::size_t length) -> bool {
        if (run_ >= run_ceiling_ || !accepted(apply(Operation::begin, length, 0, copied_input)))
            return false;
        ++run_;
        return true;
    }
    [[nodiscard]] auto begin_read(bool transforming = false) -> bool {
        if (run_ >= run_ceiling_ || !accepted(apply(Operation::begin_read, transforming)))
            return false;
        ++run_;
        return true;
    }
    [[nodiscard]] auto awaiting_read(bool transforming) const -> bool {
        return accepted(evaluate(Operation::awaiting_read, transforming));
    }
    [[nodiscard]] auto next_input() const -> std::optional<Input> {
        const auto result = evaluate(Operation::next_input);
        if (!accepted(result))
            return std::nullopt;
        return Input{static_cast<std::uint8_t>(word(result, 256)), word(result, 264)};
    }
    [[nodiscard]] auto accept_request(std::uint64_t byte, std::uint64_t ordinal) -> bool {
        return accepted(apply(Operation::accept_request, byte, ordinal));
    }
    [[nodiscard]] auto accept_reply(std::uint64_t byte, std::uint64_t ordinal) -> bool {
        return accepted(apply(Operation::accept_reply, byte, ordinal));
    }
    [[nodiscard]] auto acknowledge(std::uint64_t byte, std::uint64_t ordinal) -> bool {
        return accepted(apply(Operation::acknowledge, byte, ordinal));
    }
    [[nodiscard]] auto ready_to_finish() const -> bool {
        return accepted(evaluate(Operation::ready_to_finish));
    }
    [[nodiscard]] auto finish() -> std::optional<Output> {
        const auto result = apply(Operation::finish);
        if (!accepted(result))
            return std::nullopt;
        StreamBytes bytes{};
        for (std::size_t i = 0; i < stream_capacity; ++i)
            bytes[i] = std::to_integer<std::uint8_t>(result[192 + i]);
        return Output{bytes, static_cast<std::size_t>(word(result, 256)), word(result, 264) == 1};
    }
    [[nodiscard]] auto cancel() -> bool {
        return accepted(apply(Operation::cancel));
    }
    [[nodiscard]] auto scrubbed() const -> bool {
        return accepted(evaluate(Operation::scrubbed));
    }
};
} // namespace aurora::program
