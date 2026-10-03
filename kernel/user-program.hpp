#pragma once
#include "protection.hpp"
#include <cstddef>
#include <cstdint>
#include <span>
#include <optional>

namespace aurora::user {
enum class ProgramEvent { rejected, returned, bounds, overflow };
class ProgramContext final {
    friend class ProgramContract;
    std::uint64_t vector, error, instruction, code, stack_selector, stack, flags, kernel_frame;
public:
    constexpr ProgramContext(std::uint64_t vector_value, std::uint64_t error_value, std::uint64_t pc,
        std::uint64_t cs, std::uint64_t ss, std::uint64_t sp, std::uint64_t rflags, std::uint64_t frame)
        : vector(vector_value), error(error_value), instruction(pc), code(cs), stack_selector(ss),
          stack(sp), flags(rflags), kernel_frame(frame) {}
    [[nodiscard]] auto origin_valid() const -> bool {
        using hardware::Protection;
        constexpr auto forbidden = (3ULL << 12) | (1ULL << 14) | (1ULL << 17)
            | (1ULL << 9) | (1ULL << 8) | (1ULL << 10);
        return code == 0x1b && stack_selector == 0x23 && (flags & 2) != 0 && (flags & forbidden) == 0
            && stack >= Protection::user_stack_bottom && stack <= Protection::user_stack_top && stack % 8 == 0
            && kernel_frame >= Protection::entry_stack_bottom
            && kernel_frame <= Protection::entry_stack_top - 176 && kernel_frame % 8 == 0;
    }
};
class ProgramContract final {
    std::uint64_t entry_, size_, return_, bounds_, overflow_;
public:
    constexpr ProgramContract(std::uint64_t entry, std::uint64_t size, std::uint64_t return_pc,
        std::uint64_t bounds, std::uint64_t overflow)
        : entry_(entry), size_(size), return_(return_pc), bounds_(bounds), overflow_(overflow) {}
    [[nodiscard]] constexpr auto entry() const -> std::uint64_t { return entry_; }
    [[nodiscard]] constexpr auto size() const -> std::uint64_t { return size_; }
    [[nodiscard]] constexpr auto return_pc() const -> std::uint64_t { return return_; }
    [[nodiscard]] constexpr auto bounds_pc() const -> std::uint64_t { return bounds_; }
    [[nodiscard]] constexpr auto overflow_pc() const -> std::uint64_t { return overflow_; }
    [[nodiscard]] auto valid() const -> bool {
        if (entry_ < 0x1b0000 || entry_ >= 0x1b3000 || entry_ % 4096 != 0 || size_ < 4 || size_ > 4096) return false;
        const auto inside = [&](std::uint64_t pc) { return pc >= entry_ && pc - entry_ <= size_ - 2; };
        return inside(return_) && return_ >= entry_ + 2 && inside(bounds_) && inside(overflow_)
            && return_ != bounds_ && return_ != overflow_ && bounds_ != overflow_;
    }
    [[nodiscard]] auto classify(const ProgramContext& context) const -> ProgramEvent {
        if (!valid() || !context.origin_valid() || context.error != 0) return ProgramEvent::rejected;
        if (context.vector == 129 && context.instruction == return_
            && context.stack == hardware::Protection::user_stack_top) return ProgramEvent::returned;
        if (context.vector != 6) return ProgramEvent::rejected;
        if (context.instruction == bounds_) return ProgramEvent::bounds;
        if (context.instruction == overflow_) return ProgramEvent::overflow;
        return ProgramEvent::rejected;
    }
};
class ProgramImage final {
    std::span<const std::byte> bytes_;
    ProgramContract contract_;
public:
    constexpr ProgramImage(std::span<const std::byte> bytes, ProgramContract contract)
        : bytes_(bytes), contract_(contract) {}
    [[nodiscard]] auto contract() const -> const ProgramContract& { return contract_; }
    [[nodiscard]] auto bytes() const -> std::span<const std::byte> { return bytes_; }
    [[nodiscard]] auto valid() const -> bool {
        if (!contract_.valid() || bytes_.size() != contract_.size()) return false;
        const auto ud2 = [&](std::uint64_t pc) {
            const auto offset = pc - contract_.entry();
            return bytes_[offset] == std::byte{0x0f} && bytes_[offset + 1] == std::byte{0x0b};
        };
        const auto ret = contract_.return_pc() - contract_.entry();
        return ud2(contract_.return_pc()) && ud2(contract_.bounds_pc()) && ud2(contract_.overflow_pc())
            && bytes_[ret - 2] == std::byte{0xcd} && bytes_[ret - 1] == std::byte{0x81};
    }
};
// Single outstanding run. Only verified metadata, never a user pointer, supplies a contract.
class ProgramRun final {
    std::optional<ProgramContract> active_{};
    ProgramEvent event_{ProgramEvent::rejected};
    std::uint64_t value_{};
public:
    ProgramRun() = default;
    ProgramRun(const ProgramRun&) = delete;
    auto operator=(const ProgramRun&) -> ProgramRun& = delete;
    [[nodiscard]] auto begin(const ProgramContract& contract) -> bool {
        if (active_.has_value() || !contract.valid()) return false;
        active_.emplace(contract); event_ = ProgramEvent::rejected; value_ = 0;
        return true;
    }
    [[nodiscard]] auto running() const -> bool { return active_.has_value(); }
    [[nodiscard]] auto accept(const ProgramContext& context, std::uint64_t scalar) -> bool {
        if (!active_.has_value()) return false;
        const auto event = active_->classify(context);
        if (event == ProgramEvent::rejected) return false;
        event_ = event;
        value_ = event == ProgramEvent::returned ? scalar : 0;
        active_.reset();
        return true;
    }
    [[nodiscard]] auto event() const -> ProgramEvent { return event_; }
    [[nodiscard]] auto value() const -> std::uint64_t { return value_; }
};
class UserPrograms final {
public:
    static constexpr std::uint64_t code_begin = 0x1b0000;
    static constexpr std::uint64_t code_end = 0x1b3000;
    [[nodiscard]] static auto install() -> bool;
    [[nodiscard]] static auto contract(std::size_t index) -> const ProgramContract*;
    [[nodiscard]] static auto scrub_stack() -> bool;
};
}
