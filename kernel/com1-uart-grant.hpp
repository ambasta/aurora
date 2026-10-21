#pragma once
#include "console.hpp"
#include <cstdint>
#include <limits>

namespace aurora::hardware {
class PortArgument final {
public:
    const void *grant{};
    std::uint64_t generation{};
};

// One fixed COM1 admission, not a port allocator. Only trusted setup can open
// this grant. The UART policy may read RBR/IIR/LSR and write THR/FCR, never change
// baud, interrupt enables or PIC ownership. Platform owns the quiescence proof.
template <class Platform, class Ports = Io, std::uint64_t GenerationLimit = std::numeric_limits<std::uint64_t>::max()>
class Com1UartGrant final {
    static constexpr std::uint64_t kind = 0x415552504f525404ULL;
    static constexpr std::uint64_t base = 0x3f8, length = 8;
    class Grant final {
    public:
        std::uint64_t type{}, generation{};
        bool active{}, operation{};
    };
    static inline Grant grant_{};
    static inline std::uint64_t generation_{};
    static auto require(bool okay) -> void {
        if (!okay)
            Platform::fail();
    }
    static auto validate(const void *grant, std::uint64_t generation, bool operation) -> void {
        // No dereference of the caller-supplied pointer, even on failure.
        require(grant == &grant_);
        require(grant_.type == kind && grant_.active && grant_.operation == operation && generation != 0 &&
                generation == generation_ && generation == grant_.generation);
        require(Platform::quiet() && Platform::owns_uart());
    }
    static auto enter(const void *grant, std::uint64_t generation, std::uint64_t offset, bool write) -> std::uint16_t {
        validate(grant, generation, false);
        require(offset < length && offset <= std::numeric_limits<std::uint16_t>::max() - base);
        require(write ? (offset == 0 || offset == 2) : (offset == 0 || offset == 2 || offset == 5));
        grant_.operation = true;
        return static_cast<std::uint16_t>(base + offset);
    }
    static auto leave(const void *grant, std::uint64_t generation) -> void {
        validate(grant, generation, true);
        grant_.operation = false;
    }

public:
    [[nodiscard]] static auto open() -> PortArgument {
        require(generation_ < GenerationLimit && !grant_.active && !grant_.operation);
        require(Platform::quiet() && Platform::owns_uart());
        ++generation_;
        grant_ = {kind, generation_, true, false};
        return {&grant_, generation_};
    }
    static auto revoke(PortArgument argument) -> void {
        validate(argument.grant, argument.generation, false);
        grant_.active = false;
    }
    [[nodiscard]] static auto read8(const void *grant, std::uint64_t generation, std::uint64_t offset)
        -> std::uint64_t {
        const auto port = enter(grant, generation, offset, false);
        const auto value = Ports::read(port); // Exactly one byte IN after all admission checks.
        leave(grant, generation);
        return value;
    }
    [[nodiscard]] static auto
    write8(const void *grant, std::uint64_t generation, std::uint64_t offset, std::uint64_t value) -> std::uint64_t {
        require(value <= 255); // Validate the full host channel before narrowing.
        const auto port = enter(grant, generation, offset, true);
        Ports::write(port, static_cast<std::uint8_t>(value)); // Exactly one OUT; no retry or device acknowledgement.
        leave(grant, generation);
        return 0;
    }
};
static_assert(sizeof(PortArgument) == 16);
} // namespace aurora::hardware
