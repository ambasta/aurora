#pragma once
#include "ram-file-policy.hpp"
#include <algorithm>
#include <cstdint>

namespace aurora::uefi {
// A distinct, closed framing grammar. These transient protocol facts are not a
// namespace checkpoint: names, values, lookup, capacity and mutation stay source-owned.
class NamespaceFraming final {
public:
    enum class Right {
        read,
        write
    };
    using State = RamFileFraming::State;
    using Outcome = RamFileFraming::Outcome;
    static constexpr unsigned maximum_exchanges = 51;

private:
    enum class Step {
        begin,
        name,
        value,
        prepare,
        revision,
        echo,
        commit,
        read
    };
    const Right right_;
    const unsigned name_size_, value_size_;
    State state_ = State::fresh;
    Outcome outcome_ = Outcome::none;
    Step step_ = Step::begin;
    unsigned count_{}, offset_{}, revision_offset_{}, data_count_{};
    std::uint64_t request_{}, terminal_reply_{}, revision_{};
    bool delivered_{}, commit_delivered_{}, short_data_{};
    [[nodiscard]] static constexpr auto control(unsigned tag, unsigned cursor = 0) -> std::uint64_t {
        return tag | (std::uint64_t{cursor} << 8);
    }
    [[nodiscard]] static constexpr auto chunk(std::uint64_t word, unsigned tag, unsigned cursor, unsigned count)
        -> bool {
        if (count == 0 || count > 4 || (word & 0xffffff) != (tag | (cursor << 8) | (count << 16)))
            return false;
        return (word >> (24 + count * 8)) == 0;
    }

public:
    explicit constexpr NamespaceFraming(Right right, unsigned name_size, unsigned value_size)
        : right_(right), name_size_(name_size), value_size_(value_size) {
    }
    [[nodiscard]] constexpr auto permits(std::uint64_t word) const -> bool {
        if ((right_ != Right::read && right_ != Right::write) || name_size_ < 1 || name_size_ > 8 || value_size_ > 49 ||
            (right_ == Right::read && value_size_ != 0) || count_ >= maximum_exchanges ||
            (state_ != State::fresh && state_ != State::open))
            return false;
        switch (step_) {
        case Step::begin:
            return word == ((right_ == Right::read ? 1U : 2U) | (name_size_ << 8) | (value_size_ << 16));
        case Step::name:
            return chunk(word, 3, offset_, std::min(4U, name_size_ - offset_));
        case Step::value:
            return chunk(word, 4, offset_, std::min(4U, value_size_ - offset_));
        case Step::prepare:
            return word == 5;
        case Step::revision:
            return word == control(6, revision_offset_);
        case Step::echo:
            return chunk(word, 7, revision_offset_, 4);
        case Step::commit:
            return word == 8;
        case Step::read:
            return word == control(9, data_count_);
        }
        return false;
    }
    [[nodiscard]] constexpr auto publish(std::uint64_t word) -> bool {
        if (!permits(word))
            return false;
        request_ = word;
        delivered_ = false;
        state_ = State::pending;
        ++count_;
        return true;
    }
    [[nodiscard]] constexpr auto delivered(std::uint64_t word) -> bool {
        if (state_ != State::pending || delivered_ || request_ != word)
            return false;
        delivered_ = true;
        if (step_ == Step::commit)
            commit_delivered_ = true;
        return true;
    }
    [[nodiscard]] constexpr auto reply(std::uint64_t word) -> bool {
        if (state_ != State::pending || !delivered_)
            return false;
        // FileEvent values are transported, not interpreted as naming policy.
        const auto event = word >> 8;
        if ((word & 255) == 6 && event >= 6 && event <= 8) {
            state_ = State::terminal;
            outcome_ = Outcome::rejected;
        } else {
            switch (step_) {
            case Step::begin:
                if (word != 1)
                    return false;
                step_ = Step::name;
                break;
            case Step::name:
            case Step::value: {
                if (word != 1)
                    return false;
                const auto total = step_ == Step::name ? name_size_ : value_size_;
                offset_ += std::min(4U, total - offset_);
                if (offset_ == total) {
                    const bool value = step_ == Step::name && right_ == Right::write && value_size_ != 0;
                    step_ = value ? Step::value : Step::prepare;
                    offset_ = 0;
                }
                break;
            }
            case Step::prepare:
                if (word != 1)
                    return false;
                step_ = Step::revision;
                break;
            case Step::revision:
                if (!chunk(word, 8, revision_offset_, 4))
                    return false;
                if (revision_offset_ == 4 && (revision_ | ((word >> 24) << 32)) == 0)
                    return false;
                revision_ |= (word >> 24) << (revision_offset_ * 8);
                revision_offset_ += 4;
                if (revision_offset_ == 8) {
                    revision_offset_ = 0;
                    step_ = right_ == Right::write ? Step::echo : Step::read;
                }
                break;
            case Step::echo:
                if (word != 1)
                    return false;
                revision_offset_ += 4;
                if (revision_offset_ == 8)
                    step_ = Step::commit;
                break;
            case Step::commit:
                if (word != 5 || !commit_delivered_ || revision_ == UINT64_MAX)
                    return false;
                ++revision_;
                state_ = State::terminal;
                outcome_ = Outcome::committed;
                break;
            case Step::read: {
                if (word == 3 || (word == 4 && data_count_ == 0)) {
                    state_ = State::terminal;
                    outcome_ = Outcome::completed;
                } else {
                    const unsigned count = static_cast<unsigned>((word >> 16) & 255);
                    if (short_data_ || data_count_ >= 49 || count > 49 - data_count_ ||
                        !chunk(word, 2, data_count_, count))
                        return false;
                    data_count_ += count;
                    short_data_ = count != 4;
                }
                break;
            }
            }
            if (state_ != State::terminal)
                state_ = State::open;
        }
        if (state_ == State::terminal)
            terminal_reply_ = word;
        request_ = 0;
        delivered_ = false;
        return true;
    }
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
    [[nodiscard]] constexpr auto revision() const -> std::uint64_t {
        return revision_;
    }
    [[nodiscard]] constexpr auto data_count() const -> unsigned {
        return data_count_;
    }
    [[nodiscard]] constexpr auto count() const -> unsigned {
        return count_;
    }
};

// The retained lifetime mechanism selects one of two closed grammars once at
// command admission. The existing unnamed grammar and its rights are unchanged.
class RetainedFraming final {
    const bool named_;
    RamFileFraming file_;
    NamespaceFraming namespace_;

public:
    explicit constexpr RetainedFraming(RamFileFraming::Right right, unsigned count)
        : named_(false), file_(right, count), namespace_(NamespaceFraming::Right::read, 0, 0) {
    }
    explicit constexpr RetainedFraming(NamespaceFraming::Right right, unsigned name, unsigned count)
        : named_(true), file_(RamFileFraming::Right::read), namespace_(right, name, count) {
    }
    [[nodiscard]] constexpr auto permits(std::uint64_t word) const -> bool {
        return named_ ? namespace_.permits(word) : file_.permits(word);
    }
    [[nodiscard]] constexpr auto publish(std::uint64_t word) -> bool {
        return named_ ? namespace_.publish(word) : file_.publish(word);
    }
    [[nodiscard]] constexpr auto delivered(std::uint64_t word) -> bool {
        return named_ ? namespace_.delivered(word) : file_.delivered(word);
    }
    [[nodiscard]] constexpr auto reply(std::uint64_t word) -> bool {
        return named_ ? namespace_.reply(word) : file_.reply(word);
    }
    [[nodiscard]] constexpr auto begin_abort() -> bool {
        return named_ ? namespace_.begin_abort() : file_.begin_abort();
    }
    [[nodiscard]] constexpr auto acknowledge_abort(std::uint64_t word) -> bool {
        return named_ ? namespace_.acknowledge_abort(word) : file_.acknowledge_abort(word);
    }
    [[nodiscard]] constexpr auto state() const -> RamFileFraming::State {
        return named_ ? namespace_.state() : file_.state();
    }
    [[nodiscard]] constexpr auto outcome() const -> RamFileFraming::Outcome {
        return named_ ? namespace_.outcome() : file_.outcome();
    }
    [[nodiscard]] constexpr auto commit_delivered() const -> bool {
        return named_ ? namespace_.commit_delivered() : file_.commit_delivered();
    }
    [[nodiscard]] constexpr auto request() const -> std::uint64_t {
        return named_ ? namespace_.request() : file_.request();
    }
    [[nodiscard]] constexpr auto terminal_reply() const -> std::uint64_t {
        return named_ ? namespace_.terminal_reply() : file_.terminal_reply();
    }
    [[nodiscard]] constexpr auto data_count() const -> unsigned {
        return named_ ? namespace_.data_count() : file_.data_count();
    }
    [[nodiscard]] constexpr auto count() const -> unsigned {
        return named_ ? namespace_.count() : file_.count();
    }
    [[nodiscard]] constexpr auto revision() const -> std::uint64_t {
        return named_ ? namespace_.revision() : 0;
    }
};
} // namespace aurora::uefi
