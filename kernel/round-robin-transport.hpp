#pragma once
#include <cstdint>
#include <optional>

namespace aurora::ipc {
// Private replaceable scalar-symbol bootstrap seam. Aurora's source API is a
// copied class/enum API, not a foreign ABI. No authority or pointer crosses it.
auto language_round_robin_next(std::uint64_t cursor, std::uint64_t eligible_mask) -> std::uint64_t
    asm("aurora_kernel_round_robin_next") __attribute__((visibility("hidden")));

class RoundRobinSelection final {
    const unsigned client_, next_;
    const bool selected_;
    constexpr RoundRobinSelection(unsigned client, unsigned next, bool selected)
        : client_(client), next_(next), selected_(selected) {
    }

public:
    // action[7:0] = 1 idle or 2 selected; client[15:8], next[16], other bits zero.
    // Check canonical bounded results and membership, never choose the winner.
    // Fairness is the Aurora policy's obligation; receive still checks authority.
    [[nodiscard]] static constexpr auto decode(std::uint64_t encoded, std::uint64_t cursor, std::uint64_t eligible_mask)
        -> std::optional<RoundRobinSelection> {
        if (cursor > 1 || eligible_mask > 3 || encoded >> 17)
            return std::nullopt;
        const auto action = encoded & 255, client = (encoded >> 8) & 255, next = encoded >> 16;
        if (client > 1)
            return std::nullopt;
        if (action == 1) {
            if (eligible_mask != 0 || client != 0 || next != cursor)
                return std::nullopt;
            return RoundRobinSelection{0, static_cast<unsigned>(next), false};
        }
        if (action != 2 || (eligible_mask & (std::uint64_t{1} << client)) == 0 || next != 1 - client)
            return std::nullopt;
        return RoundRobinSelection{static_cast<unsigned>(client), static_cast<unsigned>(next), true};
    }
    [[nodiscard]] constexpr auto selected() const -> bool {
        return selected_;
    }
    [[nodiscard]] constexpr auto client() const -> unsigned {
        return client_;
    }
    [[nodiscard]] constexpr auto next() const -> unsigned {
        return next_;
    }
};
} // namespace aurora::ipc
