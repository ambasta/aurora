#pragma once
#include "handoff.hpp"
#include <array>

namespace aurora::uefi {
// Copied supervisor-frame facts for the opt-in console wake phase. The adapter
// establishes the private kernel root and validates frame storage before reading.
// This grants no mapping, interrupt-controller or user-domain authority.
class ConsoleWakeContext final {
public:
    static constexpr std::size_t word_count = 22;
    static constexpr std::uint64_t byte_count = word_count * sizeof(std::uint64_t);
    static constexpr std::uint64_t handler_reserve = 4096;
    // Exact QEMU 10.0.13 inserts RF in a hardware timer's saved frame. Retain
    // that bounded observation like ServiceContext; TF/DF/IOPL and other bits deny.
    static constexpr std::uint64_t allowed_flags = 0x10ad7; // Arithmetic, bit 1, IF and RF only.

    [[nodiscard]] static constexpr auto frame_valid(std::uint64_t frame, std::uint64_t arena) -> bool {
        return RuntimeLayout::valid(arena) && frame % 8 == 0
            && frame >= arena + Handoff::stack_bottom + handler_reserve
            && frame <= arena + Handoff::stack_top - byte_count;
    }

    [[nodiscard]] static constexpr auto valid(const std::array<std::uint64_t, word_count>& words,
        std::uint64_t frame, std::uint64_t arena, std::uint64_t wait_begin, std::uint64_t wait_end,
        std::uint64_t expected_stack) -> bool {
        if (!frame_valid(frame, arena) || expected_stack % 8 != 0
            || expected_stack < arena + Handoff::stack_bottom + handler_reserve + byte_count
            || expected_stack > arena + Handoff::stack_top
            || frame != (expected_stack & ~std::uint64_t{15}) - byte_count
            || wait_begin < arena + Handoff::payload_offset || wait_begin >= wait_end
            || wait_end - wait_begin != 3 || wait_end > arena + Handoff::payload_offset + Handoff::payload_limit) {
            return false;
        }
        // The interrupt shadow covers HLT, so the only admitted continuation is
        // its following CLI. No kernel/user fault or arbitrary resume PC is valid.
        return words[15] == 64 && words[16] == 0 && words[17] == wait_begin + 2
            && words[18] == 8 && (words[19] & 0x202) == 0x202 && (words[19] & ~allowed_flags) == 0
            && words[20] == expected_stack && words[21] == 0x10;
    }
};
}
