#pragma once
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <span>

namespace aurora::program {
// A private transport receipt, not a second candidate builder. The live Aurora
// caller owns traversal and all partial bytes. Native transport only constrains
// the sequence and terminal framing; one authenticated final copied result is
// retained after the caller's clean return and final timer drain.
class AppendCall final {
public:
    using Value = std::array<std::byte, 72>;
    static constexpr std::size_t stack_reservation = 80;

private:
    enum class State {
        idle,
        ready,
        pending,
        terminal,
        captured,
        failed
    };
    Value result_{};
    std::uint64_t run_{}, length_{};
    const std::uint64_t run_ceiling_;
    State state_ = State::idle;

    static auto word(const Value &value) -> std::uint64_t {
        std::uint64_t result = 0;
        for (unsigned i = 0; i < 8; ++i)
            result |= std::uint64_t(std::to_integer<unsigned char>(value[64 + i])) << (8 * i);
        return result;
    }

public:
    explicit constexpr AppendCall(std::uint64_t run_ceiling = UINT64_MAX) : run_ceiling_(run_ceiling) {
    }
    AppendCall(const AppendCall &) = delete;
    auto operator=(const AppendCall &) -> AppendCall & = delete;
    AppendCall(AppendCall &&) = delete;
    auto operator=(AppendCall &&) -> AppendCall & = delete;
    [[nodiscard]] auto begin() -> bool {
        if (state_ != State::idle || run_ == run_ceiling_)
            return false;
        ++run_;
        state_ = State::ready;
        return true;
    }
    [[nodiscard]] auto run() const -> std::uint64_t {
        return run_;
    }
    [[nodiscard]] auto awaiting() const -> bool {
        return state_ == State::ready && length_ == 0;
    }
    [[nodiscard]] auto request(std::uint64_t offset) -> bool {
        if (state_ != State::ready || offset != length_ || offset > 49)
            return false;
        state_ = State::pending;
        return true;
    }
    [[nodiscard]] auto reply(std::uint64_t value) -> bool {
        if (state_ != State::pending)
            return false;
        if (value == 2) {
            state_ = State::terminal;
            return true;
        }
        const auto byte = value >> 8;
        if (length_ == 49 || (value & 255) != 1 || byte < 32 || byte > 126)
            return false;
        ++length_;
        state_ = State::ready;
        return true;
    }
    [[nodiscard]] auto terminal() const -> bool {
        return state_ == State::terminal || state_ == State::captured;
    }
    [[nodiscard]] auto length() const -> std::uint64_t {
        return length_;
    }
    [[nodiscard]] auto captured() const -> bool {
        return state_ == State::captured;
    }
    // This is a trusted runtime seam, called only after authenticating the
    // original caller's exact return, mapping/leases, root and final drain.
    // EOF alone never populates result_. A malformed copy consumes this attempt.
    [[nodiscard]] auto capture(const Value &value) -> bool {
        if (state_ != State::terminal)
            return false;
        state_ = State::failed;
        if (word(value) != length_)
            return false;
        for (std::size_t i = 0; i < 64; ++i) {
            const auto byte = std::to_integer<unsigned char>(value[i]);
            if (i < length_ ? byte < 32 || byte > 126 : byte != 0)
                return false;
        }
        result_ = value;
        state_ = State::captured;
        return true;
    }
    [[nodiscard]] auto finish(std::span<std::byte, 72> output) -> bool {
        if (!captured())
            return false;
        std::copy(result_.begin(), result_.end(), output.begin());
        cancel();
        return true;
    }
    auto cancel() -> void {
        result_ = {};
        length_ = 0;
        state_ = State::idle;
    }
    [[nodiscard]] auto scrubbed() const -> bool {
        if (state_ != State::idle || length_ != 0)
            return false;
        for (const auto byte : result_)
            if (byte != std::byte{0})
                return false;
        return true;
    }
};
} // namespace aurora::program
