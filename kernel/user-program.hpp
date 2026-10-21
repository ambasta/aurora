#pragma once
#include "program-layout.hpp"
#include "terminal-event-transport.hpp"
#include <cstddef>
#include <cstdint>
#include <span>
#include <optional>

namespace aurora::user {
class ProgramContext final {
    friend class ProgramContract;
    std::uint64_t vector, error, instruction, code, stack_selector, stack, flags, kernel_frame;

public:
    constexpr ProgramContext(std::uint64_t vector_value,
                             std::uint64_t error_value,
                             std::uint64_t pc,
                             std::uint64_t cs,
                             std::uint64_t ss,
                             std::uint64_t sp,
                             std::uint64_t rflags,
                             std::uint64_t frame)
        : vector(vector_value), error(error_value), instruction(pc), code(cs), stack_selector(ss), stack(sp),
          flags(rflags), kernel_frame(frame) {
    }
    [[nodiscard]] constexpr auto origin_valid(const ProgramLayout &layout) const -> bool {
        constexpr auto forbidden =
            (3ULL << 12) | (1ULL << 14) | (1ULL << 17) | (1ULL << 9) | (1ULL << 8) | (1ULL << 10);
        return code == 0x1b && stack_selector == 0x23 && (flags & 2) != 0 && (flags & forbidden) == 0 &&
               stack >= layout.user_stack_bottom() && stack <= layout.user_stack_top() && stack % 8 == 0 &&
               kernel_frame >= layout.entry_stack_bottom() &&
               kernel_frame <= layout.entry_stack_top() - ProgramLayout::fault_frame_size && kernel_frame % 8 == 0;
    }
    [[nodiscard]] constexpr auto origin_valid() const -> bool {
        return origin_valid(ProgramLayout::bios());
    }
};
class ProgramContract final {
    const ProgramLayout layout_;
    std::uint64_t entry_, size_, return_, bounds_, overflow_, division_zero_, shift_count_;

public:
    constexpr ProgramContract(ProgramLayout layout,
                              std::uint64_t entry,
                              std::uint64_t size,
                              std::uint64_t return_pc,
                              std::uint64_t bounds,
                              std::uint64_t overflow,
                              std::uint64_t division_zero = 0,
                              std::uint64_t shift_count = 0)
        : layout_(layout), entry_(entry), size_(size), return_(return_pc), bounds_(bounds), overflow_(overflow),
          division_zero_(division_zero), shift_count_(shift_count) {
    }
    constexpr ProgramContract(std::uint64_t entry,
                              std::uint64_t size,
                              std::uint64_t return_pc,
                              std::uint64_t bounds,
                              std::uint64_t overflow,
                              std::uint64_t division_zero = 0,
                              std::uint64_t shift_count = 0)
        : ProgramContract(ProgramLayout::bios(), entry, size, return_pc, bounds, overflow, division_zero, shift_count) {
    }
    [[nodiscard]] constexpr auto layout() const -> const ProgramLayout & {
        return layout_;
    }
    [[nodiscard]] constexpr auto entry() const -> std::uint64_t {
        return entry_;
    }
    [[nodiscard]] constexpr auto size() const -> std::uint64_t {
        return size_;
    }
    [[nodiscard]] constexpr auto return_pc() const -> std::uint64_t {
        return return_;
    }
    [[nodiscard]] constexpr auto bounds_pc() const -> std::uint64_t {
        return bounds_;
    }
    [[nodiscard]] constexpr auto overflow_pc() const -> std::uint64_t {
        return overflow_;
    }
    // Zero grants no division-fault authority to older compiler images.
    [[nodiscard]] constexpr auto division_zero_pc() const -> std::uint64_t {
        return division_zero_;
    }
    // Zero grants no shift-count authority to images without retained metadata.
    [[nodiscard]] constexpr auto shift_count_pc() const -> std::uint64_t {
        return shift_count_;
    }
    [[nodiscard]] constexpr auto valid() const -> bool {
        if (entry_ < layout_.code_begin() || entry_ >= layout_.code_end() || entry_ % ProgramLayout::page_size != 0 ||
            size_ < 4 || size_ > layout_.max_image_size() || size_ > layout_.code_end() - entry_)
            return false;
        const auto inside = [&](std::uint64_t pc) {
            return pc >= entry_ && pc - entry_ <= size_ - 2;
        };
        return inside(return_) && return_ >= entry_ + 2 && inside(bounds_) && inside(overflow_) && return_ != bounds_ &&
               return_ != overflow_ && bounds_ != overflow_ &&
               (division_zero_ == 0 || (inside(division_zero_) && division_zero_ != return_ &&
                                        division_zero_ != bounds_ && division_zero_ != overflow_)) &&
               (shift_count_ == 0 || (inside(shift_count_) && shift_count_ != return_ && shift_count_ != bounds_ &&
                                      shift_count_ != overflow_ && shift_count_ != division_zero_));
    }
    [[nodiscard]] auto classify(const ProgramContext &context) const -> ProgramEvent {
        if (!valid() || !context.origin_valid(layout_) || context.error != 0)
            return ProgramEvent::rejected;
        const std::uint64_t matched_sites =
            (context.instruction == return_ ? 1ULL : 0ULL) | (context.instruction == bounds_ ? 2ULL : 0ULL) |
            (context.instruction == overflow_ ? 4ULL : 0ULL) |
            (division_zero_ != 0 && context.instruction == division_zero_ ? 8ULL : 0ULL) |
            (shift_count_ != 0 && context.instruction == shift_count_ ? 16ULL : 0ULL);
        const std::uint64_t stack_top = context.stack == layout_.user_stack_top() ? 1 : 0;
        auto policy_vector = context.vector;
#ifdef AURORA_TERMINAL_EVENT_INPUT
        policy_vector = ~std::uint64_t{0};
#endif
        auto encoded = language_terminal_event(policy_vector, matched_sites, stack_top);
#ifdef AURORA_TERMINAL_EVENT_OUTPUT
        const volatile std::uint64_t reserved_bit = std::uint64_t{1} << 63;
        encoded |= reserved_bit;
#endif
        return decode_terminal_event(encoded, context.vector, matched_sites, stack_top);
    }
};
[[nodiscard]] constexpr auto same_layout(const ProgramLayout &a, const ProgramLayout &b) -> bool {
    return a.code_begin() == b.code_begin() && a.code_end() == b.code_end() &&
           a.max_image_pages() == b.max_image_pages() && a.user_stack_bottom() == b.user_stack_bottom() &&
           a.user_stack_top() == b.user_stack_top() && a.entry_stack_bottom() == b.entry_stack_bottom() &&
           a.entry_stack_top() == b.entry_stack_top();
}
[[nodiscard]] constexpr auto same_contract(const ProgramContract &a, const ProgramContract &b) -> bool {
    return same_layout(a.layout(), b.layout()) && a.entry() == b.entry() && a.size() == b.size() &&
           a.return_pc() == b.return_pc() && a.bounds_pc() == b.bounds_pc() && a.overflow_pc() == b.overflow_pc() &&
           a.division_zero_pc() == b.division_zero_pc() && a.shift_count_pc() == b.shift_count_pc();
}
class ProgramImage final {
    std::span<const std::byte> bytes_;
    ProgramContract contract_;

public:
    constexpr ProgramImage(std::span<const std::byte> bytes, ProgramContract contract)
        : bytes_(bytes), contract_(contract) {
    }
    [[nodiscard]] auto contract() const -> const ProgramContract & {
        return contract_;
    }
    [[nodiscard]] auto bytes() const -> std::span<const std::byte> {
        return bytes_;
    }
    [[nodiscard]] auto valid() const -> bool {
        if (!contract_.valid() || bytes_.size() != contract_.size())
            return false;
        const auto ud2 = [&](std::uint64_t pc) {
            const auto offset = pc - contract_.entry();
            return bytes_[offset] == std::byte{0x0f} && bytes_[offset + 1] == std::byte{0x0b};
        };
        const auto ret = contract_.return_pc() - contract_.entry();
        return ud2(contract_.return_pc()) && ud2(contract_.bounds_pc()) && ud2(contract_.overflow_pc()) &&
               (contract_.division_zero_pc() == 0 || ud2(contract_.division_zero_pc())) &&
               (contract_.shift_count_pc() == 0 || ud2(contract_.shift_count_pc())) &&
               bytes_[ret - 2] == std::byte{0xcd} && bytes_[ret - 1] == std::byte{0x81};
    }
};
// Single outstanding run. Only verified metadata, never a user pointer, supplies a contract.
class ProgramRun final {
    std::optional<ProgramContract> active_{};
    ProgramEvent event_{ProgramEvent::rejected};
    std::uint64_t value_{};

public:
    ProgramRun() = default;
    ProgramRun(const ProgramRun &) = delete;
    auto operator=(const ProgramRun &) -> ProgramRun & = delete;
    [[nodiscard]] auto begin(const ProgramContract &contract) -> bool {
        if (active_.has_value() || !contract.valid())
            return false;
        active_.emplace(contract);
        event_ = ProgramEvent::rejected;
        value_ = 0;
        return true;
    }
    [[nodiscard]] auto running() const -> bool {
        return active_.has_value();
    }
    [[nodiscard]] auto accept(const ProgramContext &context, std::uint64_t scalar) -> bool {
        if (!active_.has_value())
            return false;
        const auto event = active_->classify(context);
        if (event == ProgramEvent::rejected)
            return false;
        event_ = event;
        value_ = event == ProgramEvent::returned ? scalar : 0;
        active_.reset();
        return true;
    }
    // Trusted runner abort only; it grants no compiler-fault classification.
    [[nodiscard]] auto cancel() -> bool {
        if (!active_)
            return false;
        active_.reset();
        event_ = ProgramEvent::rejected;
        value_ = 0;
        return true;
    }
    [[nodiscard]] auto event() const -> ProgramEvent {
        return event_;
    }
    [[nodiscard]] auto value() const -> std::uint64_t {
        return value_;
    }
};
class UserPrograms final {
public:
    static constexpr std::uint64_t code_begin = 0x1b0000;
    static constexpr std::uint64_t code_end = 0x1b3000;
    [[nodiscard]] static auto install() -> bool;
    [[nodiscard]] static auto contract(std::size_t index) -> const ProgramContract *;
};
} // namespace aurora::user
