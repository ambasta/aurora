#pragma once
#include <cstdint>
#include <optional>

namespace aurora::uefi {
// Disposable trusted scalar-symbol seam, not a source-language foreign ABI.
// All arguments/results are copied u64 values. No pointer, class record, domain
// handle or hardware capability crosses this boundary.
auto language_budget_tick(std::uint64_t initial, std::uint64_t remaining, std::uint64_t used)
    -> std::uint64_t asm("aurora_kernel_budget_tick") __attribute__((visibility("hidden")));

class BudgetTransition final {
    const unsigned remaining_, used_;
    const bool resume_;
    constexpr BudgetTransition(unsigned remaining, unsigned used, bool resume)
        : remaining_(remaining), used_(used), resume_(resume) {}
public:
    // Private transport: remaining[7:0], used[15:8], action[17:16].
    // Action 1 resumes, 2 exhausts; zero and all other encodings deny.
    // This decoder does not generate next state. It checks canonical encoding,
    // bounded conservation and strict progress before the adapter commits it.
    [[nodiscard]] static constexpr auto decode(std::uint64_t encoded,
        std::uint64_t initial, std::uint64_t prior_remaining, std::uint64_t prior_used)
        -> std::optional<BudgetTransition> {
        if (initial == 0 || initial > 128 || encoded >> 18) return std::nullopt;
        const auto remaining = encoded & 255, used = (encoded >> 8) & 255, action = encoded >> 16;
        if (used == 0 || used > initial || remaining >= initial || used + remaining != initial
            || remaining >= prior_remaining || used <= prior_used) return std::nullopt;
        if ((action != 1 && action != 2) || (action == 1) != (remaining != 0)) return std::nullopt;
        return BudgetTransition{static_cast<unsigned>(remaining), static_cast<unsigned>(used), action == 1};
    }
    [[nodiscard]] constexpr auto remaining() const -> unsigned { return remaining_; }
    [[nodiscard]] constexpr auto used() const -> unsigned { return used_; }
    [[nodiscard]] constexpr auto resume() const -> bool { return resume_; }
};
}
