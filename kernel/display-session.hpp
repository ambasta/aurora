#pragma once
#include <cstddef>
#include <cstdint>
#include <limits>

namespace aurora::display {
// Private host boundary, never a source ABI. The first two words match the
// sealed service convention; copied geometry follows in the entry-only record.
class ServiceArgument final {
public:
    const void *grant;
    std::uint64_t generation, width, height;
};
enum class Completion : std::uint64_t {
    rendered,
    output_failure
};
// Copied arithmetic helper, not authority. Zero denotes exhausted identity.
[[nodiscard]] constexpr auto next_generation(std::uint64_t current) -> std::uint64_t {
    return current == std::numeric_limits<std::uint64_t>::max() ? 0 : current + 1;
}

template <class Transport, class Platform> class Session final {
    static constexpr std::uint64_t display_kind = 0x4155524449535001ULL;
    class Grant final {
    public:
        std::uint64_t kind{}, generation{}, mapping{}, width{}, height{};
        bool active{}, operation{};
    };
    static inline Grant grant_{};
    static inline std::uint64_t generation_{};
    static auto require(bool valid) -> void {
        if (!valid)
            Platform::fail();
    }
    static auto validate(const void *grant, std::uint64_t generation, bool operation) -> void {
        // Compare the exact address before dereferencing any supplied pointer.
        require(grant == &grant_);
        require(grant_.kind == display_kind && grant_.active && grant_.operation == operation && generation != 0 &&
                generation == generation_ && generation == grant_.generation);
        require(Platform::quiet());
        require(grant_.mapping != 0 && Transport::identity() == grant_.mapping && Transport::width() == grant_.width &&
                Transport::height() == grant_.height);
    }
    static auto enter(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, false);
        grant_.operation = true;
    }
    static auto leave(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, true);
        grant_.operation = false;
    }

public:
    // Trusted host entry validation only; no source-visible operation or effects.
    static auto preflight(const void *grant, std::uint64_t generation, std::uint64_t width, std::uint64_t height) -> void {
        validate(grant, generation, false);
        require(width == grant_.width && height == grant_.height);
    }
    [[nodiscard]] static auto open() -> ServiceArgument {
        const auto next = next_generation(generation_);
        require(next != 0 && !grant_.active && !grant_.operation && Platform::quiet());
        const auto identity = Transport::identity(), width = Transport::width(), height = Transport::height();
        require(identity != 0 && width > 0 && width <= 1024 && height > 0 && height <= 768);
        generation_ = next;
        grant_ = {display_kind, generation_, identity, width, height, true, false};
        return {&grant_, generation_, width, height};
    }
    [[nodiscard]] static auto pixel(const void *grant,
                                    std::uint64_t generation,
                                    std::uint64_t x,
                                    std::uint64_t y,
                                    std::uint64_t red,
                                    std::uint64_t green,
                                    std::uint64_t blue) -> std::uint64_t {
        enter(grant, generation);
        // Validate complete raw ABI channels before any transport/store, even
        // for an out-of-bounds coordinate. No narrowing can hide forged values.
        require(red <= 255 && green <= 255 && blue <= 255);
        if (x >= grant_.width || y >= grant_.height) {
            leave(grant, generation);
            return 1;
        }
        const auto result = Transport::pixel(
            x, y, static_cast<std::uint8_t>(red), static_cast<std::uint8_t>(green), static_cast<std::uint8_t>(blue));
        require(result <= 1);
        leave(grant, generation);
        return result;
    }
    [[nodiscard]] static auto close(ServiceArgument argument, std::uint64_t result) -> Completion {
        enter(argument.grant, argument.generation);
        require(result <= 1 && argument.width == grant_.width && argument.height == grant_.height);
        leave(argument.grant, argument.generation);
        grant_.active = false;
        return static_cast<Completion>(result);
    }
};
static_assert(sizeof(ServiceArgument) == 32);
static_assert(offsetof(ServiceArgument, grant) == 0 && offsetof(ServiceArgument, generation) == 8 &&
              offsetof(ServiceArgument, width) == 16 && offsetof(ServiceArgument, height) == 24);
} // namespace aurora::display
