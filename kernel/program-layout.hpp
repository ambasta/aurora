#pragma once
#include "protection.hpp"
#include <cstdint>
#include <optional>

namespace aurora::user {
// Trusted mapping policy, copied into each contract. Compiler image metadata
// supplies addresses within this authority; it cannot supply or enlarge it.
class ProgramLayout final {
    const std::uint64_t code_begin_, code_end_, max_image_pages_;
    const std::uint64_t user_stack_bottom_, user_stack_top_;
    const std::uint64_t entry_stack_bottom_, entry_stack_top_;

    constexpr ProgramLayout(std::uint64_t code_begin,
                            std::uint64_t code_end,
                            std::uint64_t max_image_pages,
                            std::uint64_t user_stack_bottom,
                            std::uint64_t user_stack_top,
                            std::uint64_t entry_stack_bottom,
                            std::uint64_t entry_stack_top)
        : code_begin_(code_begin), code_end_(code_end), max_image_pages_(max_image_pages),
          user_stack_bottom_(user_stack_bottom), user_stack_top_(user_stack_top),
          entry_stack_bottom_(entry_stack_bottom), entry_stack_top_(entry_stack_top) {
    }

    [[nodiscard]] static constexpr auto lower_canonical(std::uint64_t address) -> bool {
        return address < (1ULL << 47);
    }
    [[nodiscard]] static constexpr auto canonical(std::uint64_t address) -> bool {
        return lower_canonical(address) || address >= 0xffff800000000000ULL;
    }
    [[nodiscard]] static constexpr auto interval(std::uint64_t begin, std::uint64_t end, std::uint64_t max_pages)
        -> bool {
        return begin < end && begin % page_size == 0 && end % page_size == 0 && canonical(begin) && canonical(end) &&
               lower_canonical(begin) == lower_canonical(end) && end - begin <= max_pages * page_size;
    }
    [[nodiscard]] static constexpr auto
    disjoint(std::uint64_t left_begin, std::uint64_t left_end, std::uint64_t right_begin, std::uint64_t right_end)
        -> bool {
        return left_end <= right_begin || right_end <= left_begin;
    }

public:
    static constexpr std::uint64_t page_size = 4096;
    static constexpr std::uint64_t max_code_pages = 3;
    static constexpr std::uint64_t max_stack_pages = 4;
    static constexpr std::uint64_t fault_frame_size = 176;

    // All intervals are half-open, with canonical, page-aligned endpoints. A
    // kernel entry stack may occupy either canonical half. Actual ownership,
    // physical backing and permissions remain the trusted mapper's obligations.
    [[nodiscard]] static constexpr auto create(std::uint64_t code_begin,
                                               std::uint64_t code_end,
                                               std::uint64_t max_image_pages,
                                               std::uint64_t user_stack_bottom,
                                               std::uint64_t user_stack_top,
                                               std::uint64_t entry_stack_bottom,
                                               std::uint64_t entry_stack_top) -> std::optional<ProgramLayout> {
        if (!interval(code_begin, code_end, max_code_pages) || !lower_canonical(code_begin) ||
            !lower_canonical(code_end) || max_image_pages == 0 ||
            max_image_pages > (code_end - code_begin) / page_size ||
            !interval(user_stack_bottom, user_stack_top, max_stack_pages) || !lower_canonical(user_stack_bottom) ||
            !lower_canonical(user_stack_top) || !interval(entry_stack_bottom, entry_stack_top, max_stack_pages) ||
            !disjoint(code_begin, code_end, user_stack_bottom, user_stack_top) ||
            !disjoint(code_begin, code_end, entry_stack_bottom, entry_stack_top) ||
            !disjoint(user_stack_bottom, user_stack_top, entry_stack_bottom, entry_stack_top))
            return std::nullopt;
        return ProgramLayout{code_begin,
                             code_end,
                             max_image_pages,
                             user_stack_bottom,
                             user_stack_top,
                             entry_stack_bottom,
                             entry_stack_top};
    }
    [[nodiscard]] static constexpr auto bios() -> ProgramLayout {
        return *create(0x1b0000,
                       0x1b3000,
                       1,
                       hardware::Protection::user_stack_bottom,
                       hardware::Protection::user_stack_top,
                       hardware::Protection::entry_stack_bottom,
                       hardware::Protection::entry_stack_top);
    }
    [[nodiscard]] constexpr auto code_begin() const -> std::uint64_t {
        return code_begin_;
    }
    [[nodiscard]] constexpr auto code_end() const -> std::uint64_t {
        return code_end_;
    }
    [[nodiscard]] constexpr auto max_image_pages() const -> std::uint64_t {
        return max_image_pages_;
    }
    [[nodiscard]] constexpr auto max_image_size() const -> std::uint64_t {
        return max_image_pages_ * page_size;
    }
    [[nodiscard]] constexpr auto user_stack_bottom() const -> std::uint64_t {
        return user_stack_bottom_;
    }
    [[nodiscard]] constexpr auto user_stack_top() const -> std::uint64_t {
        return user_stack_top_;
    }
    [[nodiscard]] constexpr auto entry_stack_bottom() const -> std::uint64_t {
        return entry_stack_bottom_;
    }
    [[nodiscard]] constexpr auto entry_stack_top() const -> std::uint64_t {
        return entry_stack_top_;
    }
};
} // namespace aurora::user
