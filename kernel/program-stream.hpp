#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

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

// Bounded copied-byte ledger, not IPC authority. A real ipc::Mailbox must still
// authorize every endpoint, owner, transaction and completion in the runtime.
// Per ordinal, the client submits {transformed byte, ordinal}; the service and
// completion client each return that same byte with the original ordinal. This
// adapter validates only printable ASCII, order and equality across those three
// results. It must never compute the transformation or compare it with input.
// A note read instead requests successive offsets, retains each actual encoded
// service reply, and stages a byte or terminal marker only when the compiled
// client acknowledges that exact reply. EOF is an extra round, including for an
// empty note; missing is a distinct terminal marker. No native payload oracle.
// A transforming read carries the original reply in the low 16 bits and a
// separately validated printable output byte above it. The compiled client owns
// the transformation; terminal acknowledgments retain their exact encoding.
// The runtime may release finish()'s copied output only after both participants
// are quiescent and retired. No partial output is exposed by this class.
class Stream final {
    enum class Stage {
        idle,
        request,
        reply,
        acknowledgment,
        finished,
        cancelled
    };
    StreamBytes input_{};
    StreamBytes output_{};
    std::size_t length_{};
    std::size_t ordinal_{};
    std::uint64_t requested_{};
    std::uint64_t run_{};
    const std::uint64_t run_ceiling_;
    bool reading_{}, transforming_{}, terminal_{}, missing_{};
    Stage stage_ = Stage::idle;

    [[nodiscard]] static constexpr auto printable(std::uint64_t byte) -> bool {
        return byte >= 32 && byte <= 126;
    }
    [[nodiscard]] auto matches(std::uint64_t byte, std::uint64_t ordinal) const -> bool {
        return ordinal_ < length_ && ordinal == ordinal_ && printable(byte) && byte == requested_;
    }
    [[gnu::noinline]] auto scrub() -> void {
        input_.fill(0);
        output_.fill(0);
        length_ = 0;
        ordinal_ = 0;
        requested_ = 0;
        reading_ = transforming_ = terminal_ = missing_ = false;
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
        if ((stage_ != Stage::idle && stage_ != Stage::finished && stage_ != Stage::cancelled) || !scrubbed() ||
            length > stream_capacity || run_ >= run_ceiling_)
            return false;
        for (std::size_t index = 0; index < length; ++index) {
            if (!printable(copied_input[index]))
                return false;
        }
        for (std::size_t index = 0; index < length; ++index)
            input_[index] = copied_input[index];
        length_ = length;
        ++run_;
        stage_ = Stage::request;
        return true;
    }
    [[nodiscard]] auto begin_read(bool transforming = false) -> bool {
        const StreamBytes empty{};
        if (!begin(empty, 0))
            return false;
        reading_ = true;
        transforming_ = transforming;
        return true;
    }
    [[nodiscard]] auto awaiting_read(bool transforming) const -> bool {
        return stage_ == Stage::request && reading_ && transforming_ == transforming && ordinal_ == 0 && length_ == 0 &&
               requested_ == 0 && !terminal_ && !missing_;
    }
    [[nodiscard]] auto next_input() const -> std::optional<Input> {
        if (reading_) {
            if (stage_ == Stage::request && !terminal_ && ordinal_ <= 53)
                return Input{1, ordinal_};
            return std::nullopt;
        }
        if (stage_ != Stage::request || ordinal_ >= length_)
            return std::nullopt;
        return Input{input_[ordinal_], ordinal_};
    }
    [[nodiscard]] auto accept_request(std::uint64_t byte, std::uint64_t ordinal) -> bool {
        if (stage_ != Stage::request || ordinal != ordinal_ ||
            (reading_ ? terminal_ || ordinal_ > 53 || byte != 1 : ordinal_ >= length_ || !printable(byte)))
            return false;
        requested_ = static_cast<std::uint8_t>(byte);
        stage_ = Stage::reply;
        return true;
    }
    [[nodiscard]] auto accept_reply(std::uint64_t byte, std::uint64_t ordinal) -> bool {
        if (reading_) {
            if (stage_ != Stage::reply || ordinal != ordinal_ || terminal_ || ordinal_ > 53 ||
                !(byte == 2 || byte == 3 || (byte & ~std::uint64_t{0xff00}) == 1))
                return false;
            requested_ = byte;
            stage_ = Stage::acknowledgment;
            return true;
        }
        if (stage_ != Stage::reply || !matches(byte, ordinal))
            return false;
        stage_ = Stage::acknowledgment;
        return true;
    }
    [[nodiscard]] auto acknowledge(std::uint64_t byte, std::uint64_t ordinal) -> bool {
        if (reading_) {
            if (stage_ != Stage::acknowledgment || ordinal != ordinal_)
                return false;
            if (requested_ == 2 || requested_ == 3) {
                if (byte != requested_)
                    return false;
                terminal_ = true;
                missing_ = byte == 3;
            } else {
                if (ordinal_ >= 53)
                    return false;
                // Checking the whole shifted value also rejects excess high bits.
                if (transforming_ ? (byte & std::uint64_t{0xffff}) != requested_ || !printable(byte >> 16)
                                  : byte != requested_)
                    return false;
                output_[ordinal_++] = static_cast<std::uint8_t>(byte >> (transforming_ ? 16 : 8));
                length_ = ordinal_;
            }
            requested_ = 0;
            stage_ = Stage::request;
            return true;
        }
        if (stage_ != Stage::acknowledgment || !matches(byte, ordinal))
            return false;
        output_[ordinal_] = requested_;
        input_[ordinal_] = 0;
        requested_ = 0;
        ++ordinal_;
        stage_ = Stage::request;
        return true;
    }
    [[nodiscard]] auto ready_to_finish() const -> bool {
        return stage_ == Stage::request && (reading_ ? terminal_ : ordinal_ == length_);
    }
    [[nodiscard]] auto finish() -> std::optional<Output> {
        if (!ready_to_finish())
            return std::nullopt;
        const Output copied{output_, length_, missing_};
        scrub();
        stage_ = Stage::finished;
        return copied;
    }
    [[nodiscard]] auto cancel() -> bool {
        if (stage_ != Stage::request && stage_ != Stage::reply && stage_ != Stage::acknowledgment)
            return false;
        scrub();
        stage_ = Stage::cancelled;
        return true;
    }
    [[nodiscard]] auto scrubbed() const -> bool {
        if (length_ != 0 || ordinal_ != 0 || requested_ != 0 || reading_ || transforming_ || terminal_ || missing_)
            return false;
        for (std::size_t index = 0; index < stream_capacity; ++index) {
            if (input_[index] != 0 || output_[index] != 0)
                return false;
        }
        return true;
    }
};
} // namespace aurora::program
