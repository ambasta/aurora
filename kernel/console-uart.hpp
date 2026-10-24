#pragma once
#include "console.hpp"
#include <cstdint>

namespace aurora::console {
// A UART LSR read can clear receive-error bits even when performed for TX.
// Every console read of LSR, including echo/presentation, shares this sticky
// latch. next() transfers damage as a copied observation; no editor is owned here.
class Sample final {
public:
    bool present{};
    std::uint8_t byte{};
    bool damaged{};
};
enum class PutResult : std::uint8_t {
    success,
    timeout
};

enum class FifoTrigger : std::uint8_t {
    one = 0,
    fourteen = 0xc0
};

template <class Ports = hardware::Io, FifoTrigger Trigger = FifoTrigger::one>
class Uart final : public OutputFormat<Uart<Ports, Trigger>> {
    static_assert(Trigger == FifoTrigger::one || Trigger == FifoTrigger::fourteen);
    static constexpr auto fifo_trigger = static_cast<std::uint8_t>(Trigger);
    static inline bool receive_error_{};

    [[nodiscard]] static auto status() -> std::uint8_t {
        const auto value = Ports::read(0x3fd);
        if (value & 0x1e) {
            receive_error_ = true;
            // OE can describe a dropped FIFO-tail byte beyond a queued line
            // boundary. Discard RX, preserve TX, and distrust this DR sample.
            Ports::write(0x3fa, fifo_trigger | 0x03);
            return value & ~std::uint8_t{1};
        }
        return value;
    }

public:
    // Session setup only; never clear this between receive/echo operations.
    static auto initialize_input() -> void {
        receive_error_ = false;
        Ports::write(0x3fa, fifo_trigger | 0x07);
        static_cast<void>(status());
        static_cast<void>(Ports::read(0x3fa));
    }
    [[nodiscard]] static auto next() -> Sample {
        const auto before = status();
        const bool prior_damage = receive_error_;
        receive_error_ = false;
        if ((before & 1) == 0) {
            return {false, 0, prior_damage};
        }
        const auto byte = Ports::read(0x3f8);
        static_cast<void>(status());
        const bool damage = prior_damage || receive_error_;
        // A post-pop error can belong to the next FIFO byte. Keep it latched
        // across a delimiter so the next Aurora iteration poisons the new line.
        if (byte != 10 && byte != 13) {
            receive_error_ = false;
        }
        return {true, byte, damage};
    }
    // Observation only: whether a received byte waits, read through the shared latch.
    [[nodiscard]] static auto input_pending() -> bool {
        return (status() & 1) != 0;
    }
    [[nodiscard]] static auto try_put(std::uint8_t value) -> PutResult {
        for (unsigned remaining = 1000000; remaining > 0; --remaining) {
            if (status() & 0x20) {
                Ports::write(0x3f8, value);
                return PutResult::success;
            }
        }
        return PutResult::timeout;
    }
    // Native diagnostic output shares the same sticky receive-error latch.
    static auto put(std::uint8_t value) -> void {
        static_cast<void>(try_put(value));
    }
};
} // namespace aurora::console
