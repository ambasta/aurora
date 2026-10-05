#pragma once
#include <array>
#include <cstdint>

namespace aurora::ipc {
// Private replaceable scalar-symbol seam. No capability or payload crosses it.
auto language_ipc_transition(std::uint64_t operation, std::uint64_t phase,
    std::uint64_t state, std::uint64_t scrubbed) -> std::uint64_t
    asm("aurora_kernel_ipc_transition") __attribute__((visibility("hidden")));

enum class TransactionOperation : std::uint64_t { submit, receive, reply, consume, cancel, recycle };
enum class TransactionEffect : std::uint64_t {
    none, submit_request, deliver_request, store_reply,
    consume_reply, consume_cancelled, cancel_request, recycle_record
};
enum class TransactionStatus { malformed, refused, accepted };

class TransactionTransition final {
    TransactionStatus status_;
    std::uint64_t next_;
    TransactionEffect effect_;
    constexpr TransactionTransition(TransactionStatus status, std::uint64_t next, TransactionEffect effect)
        : status_(status), next_(next), effect_(effect) {}
    class Invariant final {
    public:
        std::uint64_t operation, phase, source_mask, next;
        bool needs_scrubbed;
    };
    // Indexed only after validating the returned effect. These restrict a
    // proposed effect; they never choose success when the producer refuses.
    inline static constexpr std::array<Invariant, 7> invariants_{{
        {0, 1, 1U << 0, 1, false}, // submit: idle -> pending, store request
        {1, 2, 1U << 1, 2, false}, // receive: pending -> delivered, copy/clear request
        {2, 2, 1U << 2, 3, false}, // reply: delivered -> replied, store reply
        {3, 3, 1U << 3, 5, false}, // consume replied -> consumed, copy reply/scrub
        {3, 3, 1U << 4, 5, false}, // consume cancelled -> consumed, copy cancellation/scrub
        {4, 0, (1U << 1) | (1U << 2), 4, false}, // cancel only unterminated requests
        {5, 0, 1U << 5, 0, true}, // recycle only consumed scrubbed storage
    }};
public:
    // action[7:0]=1 refused or 2 accepted; next[15:8]; effect[23:16].
    // Zero denotes invalid copied producer input, hence malformed to the host.
    // Both denial classes expose zero next/effect facts and mint no authority.
    [[nodiscard]] static constexpr auto decode(std::uint64_t encoded, std::uint64_t operation,
        std::uint64_t phase, std::uint64_t state, std::uint64_t scrubbed) -> TransactionTransition {
        const TransactionTransition malformed{TransactionStatus::malformed, 0, TransactionEffect::none};
        if (operation > 5 || phase > 3 || state > 5 || scrubbed > 1) return malformed;
        if (encoded == 1) return {TransactionStatus::refused, 0, TransactionEffect::none};
        if (encoded >> 24 || (encoded & 255) != 2) return malformed;
        const auto next = (encoded >> 8) & 255, effect = (encoded >> 16) & 255;
        if (next > 5 || effect == 0 || effect > invariants_.size()) return malformed;
        const auto& rule = invariants_[effect - 1];
        if (operation != rule.operation || phase != rule.phase || next != rule.next
            || (rule.source_mask & (std::uint64_t{1} << state)) == 0
            || (rule.needs_scrubbed && scrubbed != 1)) return malformed;
        return {TransactionStatus::accepted, next, static_cast<TransactionEffect>(effect)};
    }
    [[nodiscard]] constexpr auto status() const -> TransactionStatus { return status_; }
    [[nodiscard]] constexpr auto accepted() const -> bool { return status_ == TransactionStatus::accepted; }
    [[nodiscard]] constexpr auto next() const -> std::uint64_t { return next_; }
    [[nodiscard]] constexpr auto effect() const -> TransactionEffect { return effect_; }
};
}
