#pragma once
#include <cstdint>
#include <optional>

namespace aurora::program {
// Private copied-scalar seam. The Aurora lifecycle chooses the effect; the
// native decoder rejects proposals inconsistent with the supplied facts.
auto language_file_service_transition(std::uint64_t state, std::uint64_t event) -> std::uint64_t
    asm("aurora_kernel_file_service_transition") __attribute__((visibility("hidden")));
class FileServiceTransition final {
    std::uint64_t next_, effect_;
    constexpr FileServiceTransition(std::uint64_t next, std::uint64_t effect) : next_(next), effect_(effect) {
    }

public:
    [[nodiscard]] static constexpr auto decode(std::uint64_t encoded, std::uint64_t state, std::uint64_t event)
        -> std::optional<FileServiceTransition> {
        if (state > 3 || event > 3 || encoded >> 24 || (encoded & 255) != 1)
            return std::nullopt;
        const auto next = (encoded >> 8) & 255, effect = (encoded >> 16) & 255;
        if ((event == 0 && next == 2 && ((state == 0 && effect == 1) || (state == 1 && effect == 2))) ||
            (event == 2 && state >= 2 && next == 3 && effect == 5) ||
            (event == 1 && ((state == 2 && next == 1 && effect == 3) || (state == 3 && next == 0 && effect == 4))) ||
            (event == 3 && next == 0 && ((state == 0 && effect == 5) || (state == 1 && effect == 4))))
            return FileServiceTransition{next, effect};
        return std::nullopt;
    }
    [[nodiscard]] constexpr auto next() const -> std::uint64_t {
        return next_;
    }
    [[nodiscard]] constexpr auto effect() const -> std::uint64_t {
        return effect_;
    }
};
} // namespace aurora::program
