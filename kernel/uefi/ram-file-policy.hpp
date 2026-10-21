#pragma once
#include <cstdint>

namespace aurora::uefi {
// Transport framing only. There are deliberately no file bytes, existence bit or
// committed length here. Those belong exclusively to the retained source local.
class RamFileFraming final {
public:
    enum class Right {
        read,
        replace
    };
    enum class State {
        fresh,
        open,
        pending,
        terminal,
        aborting,
        aborted
    };
    enum class Outcome {
        none,
        completed,
        committed,
        rejected,
        aborted,
        indeterminate,
        reset
    };
    static constexpr unsigned maximum_exchanges = 51;

private:
    const Right right_;
    // 50 leaves the legacy binary fixture length unbound. Console admission
    // supplies an exact 0..49 length; this is framing, never committed state.
    const unsigned expected_replace_count_;
    State state_ = State::fresh;
    Outcome outcome_ = Outcome::none;
    unsigned count_{}, offset_{}, target_{};
    std::uint64_t request_{}, terminal_reply_{};
    bool commit_delivered_{}, delivered_{};

public:
    explicit constexpr RamFileFraming(Right right, unsigned expected_replace_count = 50)
        : right_(right), expected_replace_count_(expected_replace_count) {
    }
    [[nodiscard]] constexpr auto permits(std::uint64_t word) const -> bool {
        if (expected_replace_count_ > 50 || count_ >= maximum_exchanges ||
            (state_ != State::fresh && state_ != State::open))
            return false;
        if (state_ == State::fresh)
            return right_ == Right::read ? word == 1
                                         : right_ == Right::replace && (word & 255) == 3 && word <= (49U << 8 | 3U) &&
                                               (expected_replace_count_ == 50 || word >> 8 == expected_replace_count_);
        if (right_ == Right::read)
            return word == (std::uint64_t{offset_} << 8 | 2U) && offset_ <= 49;
        if (right_ != Right::replace)
            return false;
        return offset_ == target_ ? word == 5
                                  : offset_ < target_ && word <= 0xffffff && (word & 0xffff) == (offset_ << 8 | 4U);
    }
    [[nodiscard]] constexpr auto publish(std::uint64_t word) -> bool {
        if (!permits(word))
            return false;
        request_ = word;
        if (state_ == State::fresh && right_ == Right::replace)
            target_ = static_cast<unsigned>(word >> 8);
        state_ = State::pending;
        delivered_ = false;
        ++count_;
        return true;
    }
    [[nodiscard]] constexpr auto delivered(std::uint64_t word) -> bool {
        if (state_ != State::pending || delivered_ || request_ != word)
            return false;
        delivered_ = true;
        if (word == 5)
            commit_delivered_ = true;
        return true;
    }
    [[nodiscard]] constexpr auto reply(std::uint64_t word) -> bool {
        if (state_ != State::pending || !delivered_)
            return false;
        const auto tag = request_ & 255;
        if (word == 6) {
            state_ = State::terminal;
            outcome_ = Outcome::rejected;
        } else if (tag == 1 || tag == 3 || tag == 4) {
            if (word != 1)
                return false;
            if (tag == 4)
                ++offset_;
            state_ = State::open;
        } else if (tag == 2) {
            if (word == 3 || (word == 4 && offset_ == 0)) {
                state_ = State::terminal;
                outcome_ = Outcome::completed;
            } else if (word <= 0xff02 && (word & 255) == 2 && offset_ < 49) {
                ++offset_;
                state_ = State::open;
            } else
                return false;
        } else if (tag == 5 && word == 5 && commit_delivered_) {
            state_ = State::terminal;
            outcome_ = Outcome::committed;
        } else
            return false;
        if (state_ == State::terminal)
            terminal_reply_ = word;
        request_ = 0;
        delivered_ = false;
        return true;
    }
    // The adapter must first settle/revoke the old transport and disable caller
    // execution. The private acknowledgement never goes through Mailbox.reply.
    [[nodiscard]] constexpr auto begin_abort() -> bool {
        if (commit_delivered_ || state_ == State::terminal || state_ == State::aborting || state_ == State::aborted)
            return false;
        request_ = 0;
        delivered_ = false;
        state_ = State::aborting;
        return true;
    }
    [[nodiscard]] constexpr auto acknowledge_abort(std::uint64_t word) -> bool {
        if (state_ != State::aborting || word != 7)
            return false;
        state_ = State::aborted;
        outcome_ = Outcome::aborted;
        return true;
    }
    [[nodiscard]] constexpr auto state() const -> State {
        return state_;
    }
    [[nodiscard]] constexpr auto outcome() const -> Outcome {
        return outcome_;
    }
    [[nodiscard]] constexpr auto commit_delivered() const -> bool {
        return commit_delivered_;
    }
    [[nodiscard]] constexpr auto request() const -> std::uint64_t {
        return request_;
    }
    [[nodiscard]] constexpr auto terminal_reply() const -> std::uint64_t {
        return terminal_reply_;
    }
    [[nodiscard]] constexpr auto data_count() const -> unsigned {
        return right_ == Right::read ? offset_ : 0;
    }
    [[nodiscard]] constexpr auto count() const -> unsigned {
        return count_;
    }
};

} // namespace aurora::uefi
