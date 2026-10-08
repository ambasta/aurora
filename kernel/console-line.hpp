#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace aurora::console {
auto byte_policy(std::uint64_t byte, std::uint64_t length, std::uint64_t rejected, std::uint64_t after_cr)
    -> std::uint64_t asm("aurora_console_byte");
auto command_policy(std::uint64_t prefix, std::uint64_t length) -> std::uint64_t asm("aurora_console_command");

enum class Event {
    ignored,
    echo,
    erased,
    empty,
    unknown,
    help,
    status,
    exit,
    rejected
};

// An opt-in copied submission, never a view into the editor's live storage.
// The caller may retain this value, and must pass it on each consume if it wants
// a current-only result. Each supplied snapshot is scrubbed before processing a
// byte, including ignored CRLF, rejected submissions and partial later lines.
class Snapshot final {
    friend class Line;
    std::array<std::uint8_t, 64> bytes_{};
    std::size_t length_{};
    bool submitted_{};

public:
    auto clear() -> void {
        bytes_.fill(0);
        length_ = 0;
        submitted_ = false;
    }
    [[nodiscard]] auto submitted() const -> bool {
        return submitted_;
    }
    [[nodiscard]] auto length() const -> std::size_t {
        return length_;
    }
    [[nodiscard]] auto bytes() const -> std::array<std::uint8_t, 64> {
        return bytes_;
    }
};

// Trusted fixed storage. A rejected line stays rejected until its delimiter;
// backspace cannot turn an overlong or malformed line into a valid command.
class Line final {
    std::array<std::uint8_t, 64> bytes_{};
    std::size_t length_{};
    bool rejected_{};
    bool after_cr_{};

    auto finish(Snapshot *snapshot) -> Event {
        auto prefix = std::uint64_t{0};
        for (std::size_t index = 0; index < length_ && index < 6; ++index) {
            prefix |= std::uint64_t{bytes_[index]} << (index * 8);
        }
        const auto command = rejected_ ? 0 : command_policy(prefix, length_);
        const auto rejected = rejected_;
        if (snapshot && !rejected) {
            snapshot->bytes_ = bytes_;
            snapshot->length_ = length_;
            snapshot->submitted_ = true;
        }
        bytes_.fill(0);
        length_ = 0;
        rejected_ = false;
        if (rejected) {
            return Event::rejected;
        }
        switch (command) {
        case 1:
            return Event::empty;
        case 2:
            return Event::help;
        case 3:
            return Event::status;
        case 4:
            return Event::exit;
        default:
            return Event::unknown;
        }
    }

public:
    auto reject() -> void {
        rejected_ = true;
    }
    [[nodiscard]] auto length() const -> std::size_t {
        return length_;
    }
    [[nodiscard]] auto consume(std::uint8_t byte, Snapshot *snapshot = nullptr) -> Event {
        if (snapshot) {
            snapshot->clear();
        }
        const auto action = byte_policy(byte, length_, rejected_, after_cr_);
        const auto suppressed_lf = after_cr_ && byte == 10;
        after_cr_ = byte == 13;
        // Independently constrain every storage access and line submission.
        if (action == 4 && (byte == 13 || byte == 10) && !suppressed_lf) {
            return finish(snapshot);
        }
        if (action == 2 && !rejected_ && length_ < bytes_.size() && byte >= 32 && byte <= 126) {
            bytes_[length_] = byte;
            ++length_;
            return Event::echo;
        }
        if (action == 3 && !rejected_ && length_ > 0 && (byte == 8 || byte == 127)) {
            --length_;
            bytes_[length_] = 0;
            return Event::erased;
        }
        if (action != 1) {
            rejected_ = true;
        }
        return Event::ignored;
    }
};
} // namespace aurora::console
