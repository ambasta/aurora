#pragma once
#include "user-run-policy.hpp"

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

// A separate profile-specific active-run authority. Legacy BoundedRunAuthority's
// nonzero service transaction predicate is intentionally unchanged. The adapter
// additionally verifies stable lifetime/grant/lease ownership and command state.
class RamFileRunAuthority final {
public:
    enum class Role {
        client,
        service
    };
    enum class Purpose : std::uint64_t {
        client = 0,
        startup = 1,
        exchange = 2,
        abort = 3
    };

private:
    user::DomainHandle owner_;
    Role role_;
    ipc::Phase phase_;
    Purpose purpose_;
    std::uint64_t transaction_, source_, arena_, root_, epoch_;
    user::ProgramContract contract_;
    unsigned budget_;
    constexpr RamFileRunAuthority(user::DomainHandle owner,
                                  Role role,
                                  ipc::Phase phase,
                                  Purpose purpose,
                                  std::uint64_t transaction,
                                  std::uint64_t source,
                                  std::uint64_t arena,
                                  std::uint64_t root,
                                  const user::ProgramContract &contract,
                                  std::uint64_t epoch,
                                  unsigned budget)
        : owner_(owner), role_(role), phase_(phase), purpose_(purpose), transaction_(transaction), source_(source),
          arena_(arena), root_(root), epoch_(epoch), contract_(contract), budget_(budget) {
    }

public:
    [[nodiscard]] static constexpr auto same_contract(const user::ProgramContract &a, const user::ProgramContract &b)
        -> bool {
        const auto &x = a.layout();
        const auto &y = b.layout();
        return a.entry() == b.entry() && a.size() == b.size() && a.return_pc() == b.return_pc() &&
               a.bounds_pc() == b.bounds_pc() && a.overflow_pc() == b.overflow_pc() &&
               a.division_zero_pc() == b.division_zero_pc() && a.shift_count_pc() == b.shift_count_pc() &&
               x.code_begin() == y.code_begin() && x.code_end() == y.code_end() &&
               x.max_image_pages() == y.max_image_pages() && x.user_stack_bottom() == y.user_stack_bottom() &&
               x.user_stack_top() == y.user_stack_top() && x.entry_stack_bottom() == y.entry_stack_bottom() &&
               x.entry_stack_top() == y.entry_stack_top();
    }
    [[nodiscard]] static auto authorize(const user::DomainRegistry &registry,
                                        user::DomainHandle owner,
                                        Role role,
                                        ipc::Phase phase,
                                        std::size_t client,
                                        std::uint64_t transaction,
                                        std::uint64_t source,
                                        std::uint64_t arena,
                                        std::uint64_t root,
                                        const user::ProgramContract &contract,
                                        std::uint64_t epoch,
                                        unsigned budget) -> std::optional<RamFileRunAuthority> {
        using L = RuntimeLayoutProfile<2>;
        const auto index = registry.index(owner);
        if (!index || !registry.active(owner) || client != 0 || epoch == 0 || !L::valid(arena) || !contract.valid() ||
            *index > 1 || root != arena + L::table_offset(*index))
            return std::nullopt;
        const auto layout = user::ProgramLayout::create(L::code_begin(*index),
                                                        L::code_end(*index),
                                                        L::image_limit(*index) / L::page_size,
                                                        L::user_stack_begin(*index),
                                                        L::user_stack_end(*index),
                                                        arena + L::rsp0_bottom,
                                                        arena + L::rsp0_top);
        if (!layout)
            return std::nullopt;
        const user::ProgramContract expected{*layout,
                                             contract.entry(),
                                             contract.size(),
                                             contract.return_pc(),
                                             contract.bounds_pc(),
                                             contract.overflow_pc(),
                                             contract.division_zero_pc(),
                                             contract.shift_count_pc()};
        if (!same_contract(expected, contract) || contract.entry() != L::code_begin(*index) ||
            !L::code_pages(*index, contract.size()))
            return std::nullopt;
        const auto purpose = role == Role::client ? Purpose::client : static_cast<Purpose>(source);
        const bool caller =
            role == Role::client && *index == 0 && phase == ipc::Phase::request && transaction == 0 && budget == 128;
        const bool service =
            role == Role::service && *index == 1 && phase == ipc::Phase::service &&
            ((purpose == Purpose::exchange && transaction != 0 && budget == 120) ||
             ((purpose == Purpose::startup || purpose == Purpose::abort) && transaction == 0 && budget == 8));
        if (!caller && !service)
            return std::nullopt;
        return RamFileRunAuthority{
            owner, role, phase, purpose, transaction, source, arena, root, contract, epoch, budget};
    }
    [[nodiscard]] auto matches_active(const user::DomainRegistry &registry,
                                      user::DomainHandle owner,
                                      Role role,
                                      ipc::Phase phase,
                                      std::size_t client,
                                      std::uint64_t transaction,
                                      std::uint64_t source,
                                      std::uint64_t arena,
                                      std::uint64_t root,
                                      const user::ProgramContract &contract,
                                      std::uint64_t epoch) const -> bool {
        return registry.index(owner_) && registry.index(owner_) == registry.index(owner) && registry.active(owner_) &&
               registry.active(owner) && role == role_ && phase == phase_ && client == 0 &&
               transaction == transaction_ && source == source_ && arena == arena_ && root == root_ &&
               epoch == epoch_ && same_contract(contract_, contract);
    }
    [[nodiscard]] auto
    ready_owner(const user::DomainRegistry &registry, user::DomainHandle owner, std::uint64_t epoch) const -> bool {
        return registry.index(owner_) && registry.index(owner_) == registry.index(owner) && registry.ready(owner_) &&
               registry.ready(owner) && epoch == epoch_;
    }
    [[nodiscard]] constexpr auto owner() const -> user::DomainHandle {
        return owner_;
    }
    [[nodiscard]] constexpr auto role() const -> Role {
        return role_;
    }
    [[nodiscard]] constexpr auto purpose() const -> Purpose {
        return purpose_;
    }
    [[nodiscard]] constexpr auto phase() const -> ipc::Phase {
        return phase_;
    }
    [[nodiscard]] constexpr auto client() const -> std::size_t {
        return 0;
    }
    [[nodiscard]] constexpr auto transaction() const -> std::uint64_t {
        return transaction_;
    }
    [[nodiscard]] constexpr auto source_phase() const -> std::uint64_t {
        return source_;
    }
    [[nodiscard]] constexpr auto owned_arena() const -> std::uint64_t {
        return arena_;
    }
    [[nodiscard]] constexpr auto root() const -> std::uint64_t {
        return root_;
    }
    [[nodiscard]] constexpr auto contract() const -> const user::ProgramContract & {
        return contract_;
    }
    [[nodiscard]] constexpr auto epoch() const -> std::uint64_t {
        return epoch_;
    }
    [[nodiscard]] constexpr auto budget() const -> unsigned {
        return budget_;
    }
};
} // namespace aurora::uefi
