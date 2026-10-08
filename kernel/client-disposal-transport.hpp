#pragma once
#include <cstdint>

namespace aurora::ipc {
// Private replaceable copied-scalar seam, never a source-language foreign ABI.
auto language_client_disposal(std::uint64_t phase, std::uint64_t state) -> std::uint64_t
    asm("aurora_kernel_client_disposal") __attribute__((visibility("hidden")));

enum class DisposalEffect : std::uint64_t {
    none,
    empty,
    retained_receipt,
    cancel_consume,
    consume_terminal
};
enum class DisposalStatus {
    malformed,
    refused,
    accepted
};

class DisposalTransition final {
    DisposalStatus status_;
    DisposalEffect effect_;
    constexpr DisposalTransition(DisposalStatus status, DisposalEffect effect) : status_(status), effect_(effect) {
    }

public:
    // action[7:0]: 1 refused, 2 accepted; effect[15:8]. Denials carry no effect.
    // Validate a proposed plan against the original copied state; never choose
    // success in the absence of the genuine Aurora producer's accepted result.
    [[nodiscard]] static constexpr auto decode(std::uint64_t encoded, std::uint64_t phase, std::uint64_t state)
        -> DisposalTransition {
        const DisposalTransition malformed{DisposalStatus::malformed, DisposalEffect::none};
        if (phase > 3 || state > 5)
            return malformed;
        if (encoded == 1)
            return {DisposalStatus::refused, DisposalEffect::none};
        if (phase != 0 || encoded >> 16 || (encoded & 255) != 2)
            return malformed;
        const auto effect = (encoded >> 8) & 255;
        if ((effect == 1 && state == 0) || (effect == 2 && state == 5) || (effect == 3 && (state == 1 || state == 2)) ||
            (effect == 4 && (state == 3 || state == 4)))
            return {DisposalStatus::accepted, static_cast<DisposalEffect>(effect)};
        return malformed;
    }
    [[nodiscard]] constexpr auto status() const -> DisposalStatus {
        return status_;
    }
    [[nodiscard]] constexpr auto accepted() const -> bool {
        return status_ == DisposalStatus::accepted;
    }
    [[nodiscard]] constexpr auto effect() const -> DisposalEffect {
        return effect_;
    }
};
} // namespace aurora::ipc
