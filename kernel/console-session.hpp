#pragma once
#include "console-uart.hpp"
#include <cstdint>
#include <limits>

namespace aurora::console {
// Private host contract, never a source ABI. Source receives no address value.
// Incoming pointers are compared with the one exact live grant before dereference.
class RawSample final {
public:
    std::uint64_t byte_present{}, byte{}, damaged{};
};
class ServiceArgument final {
public:
    const void *grant;
    std::uint64_t generation;
};
enum class Completion : std::uint64_t {
    requested_exit,
    output_failure
};

template <class Transport, class Platform> class Session final {
    static constexpr std::uint64_t console_kind = 0x415552434f4e5301ULL;
    class Grant final {
    public:
        std::uint64_t kind{}, generation{};
        bool active{}, operation{};
    };
    static inline Grant grant_{};
    static inline std::uint64_t generation_{};
    static auto require(bool valid) -> void {
        if (!valid) {
            Platform::fail();
        }
    }
#ifdef AURORA_UEFI_GRAPHICAL_CONSOLE
    // Preserve two independently bound bootstrap authority frames in the paired profile.
    [[gnu::noinline, gnu::noclone, gnu::noipa]]
#endif
    static auto validate(const void *grant, std::uint64_t generation, bool operation) -> void {
        require(grant == &grant_);
        require(grant_.kind == console_kind && grant_.active && grant_.operation == operation && generation != 0 &&
                generation == generation_ && generation == grant_.generation);
        require(Platform::quiet());
    }
    static auto enter(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, false);
        grant_.operation = true;
    }
    static auto leave(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, true);
        grant_.operation = false;
    }
    static auto finish(ServiceArgument argument) -> void {
        leave(argument.grant, argument.generation);
        grant_.active = false;
    }

public:
    // Trusted host entry validation only; no source-visible operation or effects.
    static auto preflight(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, false);
    }
    [[nodiscard]] static auto open() -> ServiceArgument {
        // Reject exhausted identity before even a platform quiescence hook,
        // which may itself stop an admitted timer.
        require(generation_ != std::numeric_limits<std::uint64_t>::max() && !grant_.active && !grant_.operation &&
                Platform::quiet());
        ++generation_;
        grant_ = {console_kind, generation_, true, false};
        return {&grant_, generation_};
    }
    [[nodiscard]] static auto next(const void *grant, std::uint64_t generation) -> RawSample {
        enter(grant, generation);
        for (;;) {
            validate(grant, generation, true);
            const auto sample = Transport::next();
            if (sample.present || sample.damaged) {
                const RawSample result{sample.present ? 1ULL : 0ULL,
                                       sample.present ? static_cast<std::uint64_t>(sample.byte) : 0ULL,
                                       sample.damaged ? 1ULL : 0ULL};
                leave(grant, generation);
                return result;
            }
            // The trusted interrupt handler only wakes this same synchronous
            // frame. It cannot run Aurora, invoke a callback or mutate its editor.
            Platform::wait();
        }
    }
    [[nodiscard]] static auto put(const void *grant, std::uint64_t generation, std::uint64_t byte) -> std::uint64_t {
        enter(grant, generation);
        require(byte <= 255);
        const auto result = Transport::try_put(static_cast<std::uint8_t>(byte));
        require(result == PutResult::success || result == PutResult::timeout);
        leave(grant, generation);
        return result == PutResult::success ? 0 : 1;
    }
    // A supervisor reader turn may return copied input without closing the
    // console. Revoke its grant before native mutation or protected execution.
    static auto release(ServiceArgument argument) -> void {
        enter(argument.grant, argument.generation);
        finish(argument);
    }
    [[nodiscard]] static auto close(ServiceArgument argument, std::uint64_t result) -> Completion {
        enter(argument.grant, argument.generation);
        require(result <= 1);
        finish(argument);
        return static_cast<Completion>(result);
    }
};
static_assert(sizeof(RawSample) == 24 && sizeof(ServiceArgument) == 16);
} // namespace aurora::console
