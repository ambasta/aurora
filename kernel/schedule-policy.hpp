#pragma once
#include "user-program.hpp"
#include <array>
namespace aurora::user {
// Exact private assembly snapshot, copied by value, never located in user memory.
class IntegerContext final {
    std::array<std::uint64_t, 22> words_{};

public:
    [[nodiscard]] auto words() -> std::array<std::uint64_t, 22> & {
        return words_;
    }
    [[nodiscard]] auto words() const -> const std::array<std::uint64_t, 22> & {
        return words_;
    }
    [[nodiscard]] auto valid(const ProgramContract &contract) const -> bool {
        constexpr auto allowed =
            BootstrapLayout::allowed_user_flags; // arithmetic flags, IF, DF, RF, architectural bit1.
        const auto pc = words_[17], flags = words_[19], sp = words_[20];
        return contract.valid() && pc >= contract.entry() && pc < contract.entry() + contract.size() &&
               words_[18] == 0x1b && words_[21] == 0x23 && (flags & 0x202) == 0x202 && (flags & ~allowed) == 0 &&
               sp >= hardware::Protection::user_stack_bottom && sp <= hardware::Protection::user_stack_top &&
               sp % 8 == 0;
    }
    auto fresh(const ProgramContract &contract) -> void {
        words_.fill(0);
        words_[17] = contract.entry();
        words_[18] = 0x1b;
        words_[19] = 0x202;
        words_[20] = hardware::Protection::user_stack_top;
        words_[21] = 0x23;
    }
    [[nodiscard]] auto terminal(const ProgramContract &contract) const -> ProgramEvent {
        if (!valid(contract))
            return ProgramEvent::rejected;
        // Existing scalar authority accepts the same frame with IF normalized away.
        const ProgramContext context{words_[15],
                                     words_[16],
                                     words_[17],
                                     words_[18],
                                     words_[21],
                                     words_[20],
                                     words_[19] & ~(1ULL << 9),
                                     hardware::Protection::entry_stack_top - 176};
        return contract.classify(context);
    }
};
class SliceBudget final {
    unsigned remaining_{};
    unsigned used_{};

public:
    explicit constexpr SliceBudget(unsigned ticks) : remaining_(ticks) {
    }
    [[nodiscard]] auto consume() -> bool {
        if (remaining_ == 0)
            return false;
        --remaining_;
        ++used_;
        return true;
    }
    [[nodiscard]] auto exhausted() const -> bool {
        return remaining_ == 0;
    }
    [[nodiscard]] auto used() const -> unsigned {
        return used_;
    }
};
} // namespace aurora::user
