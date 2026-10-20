#pragma once
#include "console-uart.hpp"
#include "port-range.hpp"
#include <cstddef>

namespace aurora::console {
// These are private transport records, checked against actual compiler ABI
// facts when the bridge is rendered. There is no source C ABI or guessed name.
class UartTransfer final {
public:
    std::uint64_t receive_error{}, trigger{}, value{}, present{}, damaged{}, success{};
};
class UartArguments final {
public:
    hardware::PortArgument port;
    UartTransfer state;
    std::uint64_t byte{};
};
auto uart_initialize(const UartArguments *, UartTransfer *) -> void asm("__au_runtime_uart_initialize");
auto uart_next(const UartArguments *, UartTransfer *) -> void asm("__au_runtime_uart_next");
auto uart_put(const UartArguments *, UartTransfer *) -> void asm("__au_runtime_uart_put");
static_assert(sizeof(UartTransfer) == 48 && sizeof(UartArguments) == 72);
static_assert(offsetof(UartArguments, state) == 16 && offsetof(UartArguments, byte) == 64);

template <class Ports, class Platform, FifoTrigger Trigger = FifoTrigger::one> class SourceUart final {
    static_assert(Trigger == FifoTrigger::one || Trigger == FifoTrigger::fourteen);
    static inline hardware::PortArgument port_{};
    static inline bool active_{}, operation_{};
    static inline UartTransfer state_{};
    static auto require(bool okay) -> void {
        if (!okay)
            Platform::fail();
    }
    static auto enter() -> void {
        require(active_ && !operation_ && Platform::quiet() && Platform::owns_uart());
        operation_ = true;
    }
    static auto accept(UartTransfer result) -> void {
        require(active_ && operation_ && Platform::quiet() && Platform::owns_uart());
        require(result.receive_error <= 1 && result.trigger == static_cast<std::uint8_t>(Trigger) &&
                result.value <= 255 && result.present <= 1 && result.damaged <= 1 && result.success <= 1);
        // The source owns all carry transitions. Native only stores copied data.
        state_ = result;
        operation_ = false;
    }

public:
    static auto initialize_input() -> void {
        require(!active_ && !operation_);
        port_ = Ports::open();
        active_ = true;
        state_ = {0, static_cast<std::uint8_t>(Trigger), 0, 0, 0, 1};
        enter();
        const UartArguments arguments{port_, state_, 0};
        UartTransfer result{};
        uart_initialize(&arguments, &result);
        accept(result);
    }
    static auto close() -> void {
        require(active_ && !operation_);
        Ports::revoke(port_); // Revoke before the platform transfers ownership.
        active_ = false;
        port_ = {};
        state_ = {};
    }
    [[nodiscard]] static auto next() -> Sample {
        enter();
        const UartArguments arguments{port_, state_, 0};
        UartTransfer result{};
        uart_next(&arguments, &result);
        require(result.present != 0 || result.value == 0);
        accept(result);
        return {result.present != 0, static_cast<std::uint8_t>(result.value), result.damaged != 0};
    }
    [[nodiscard]] static auto try_put(std::uint8_t byte) -> PutResult {
        enter();
        const UartArguments arguments{port_, state_, byte};
        UartTransfer result{};
        uart_put(&arguments, &result);
        accept(result);
        return result.success ? PutResult::success : PutResult::timeout;
    }
    static auto put(std::uint8_t byte) -> void {
        static_cast<void>(try_put(byte));
    }
    static auto text(std::string_view value) -> void {
        for (const auto byte : value)
            put(static_cast<std::uint8_t>(byte));
    }
    static auto number(std::uint64_t value) -> void {
        std::array<char, 20> digits{};
        std::size_t length = 0;
        do {
            digits[length++] = static_cast<char>('0' + value % 10);
            value /= 10;
        } while (value != 0);
        while (length != 0)
            put(static_cast<std::uint8_t>(digits[--length]));
    }
};
} // namespace aurora::console
