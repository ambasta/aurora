#pragma once
#include "console.hpp"
#include <array>
#include <cstdint>
#include <optional>
#include <string_view>

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

enum class FifoTrigger : std::uint8_t { one = 0, fourteen = 0xc0 };

template<class Ports = hardware::Io, FifoTrigger Trigger = FifoTrigger::one>
class Uart final {
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
    [[nodiscard]] static auto try_put(std::uint8_t value) -> PutResult {
        for (unsigned remaining = 1000000; remaining > 0; --remaining) {
            if (status() & 0x20) {
                Ports::write(0x3f8, value);
                return PutResult::success;
            }
        }
        return PutResult::timeout;
    }
    // Legacy BIOS/protected-console adapters remain explicit. The native
    // simple-UEFI service uses next()/try_put(), never these editor wrappers.
    template <class Editor> [[nodiscard]] static auto poll(Editor &line) -> std::optional<std::uint8_t> {
        const auto sample = next();
        if (sample.damaged) {
            line.reject();
        }
        if (!sample.present) {
            return std::nullopt;
        }
        return sample.byte;
    }
    static auto put(std::uint8_t value) -> void {
        static_cast<void>(try_put(value));
    }
    static auto text(std::string_view value) -> void {
        for (const auto byte : value) { put(static_cast<std::uint8_t>(byte)); }
    }
    static auto number(std::uint64_t value) -> void {
        std::array<char, 20> digits{};
        std::size_t length = 0;
        do {
            digits[length++] = static_cast<char>('0' + value % 10);
            value /= 10;
        } while (value != 0);
        while (length != 0) { put(static_cast<std::uint8_t>(digits[--length])); }
    }
};
}
