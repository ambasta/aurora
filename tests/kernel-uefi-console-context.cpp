#include "../kernel/uefi/console-context.hpp"
#include <cstdlib>
#include <iostream>

namespace kernel_uefi_console_context {
namespace {
using Context = aurora::uefi::ConsoleWakeContext;
using U64 = std::uint64_t;
constexpr U64 arena = 0x1000000, stack = arena + 0x4de08, frame = (stack & ~U64{15}) - 176;
constexpr U64 begin = arena + 0x22100;
constexpr U64 expected_flags = 0x10ad7; // Independent test oracle, not the production constant.
unsigned observations{};
auto need(bool value) -> void {
    ++observations;
    if (!value) {
        std::abort();
    }
}
auto valid(const std::array<U64, 22> &words, U64 location = frame, U64 saved = stack) -> bool {
    return Context::valid(words, location, arena, begin, begin + 3, saved);
}
} // namespace
int main() {
    static_assert(Context::word_count == 22 && Context::byte_count == 176);
    std::array<U64, 22> words{};
    for (unsigned i = 0; i < 15; ++i) {
        words[i] = 0x1000 + i;
    }
    words[15] = 64;
    words[17] = begin + 2;
    words[18] = 8;
    words[19] = 0x246;
    words[20] = stack;
    words[21] = 16;
    need(valid(words));
    auto rf = words;
    rf[19] |= 0x10000;
    need(valid(rf));
    for (const auto bit : {8, 10, 12, 13, 14, 17, 18, 19, 20, 21, 63}) {
        auto bad = rf;
        bad[19] |= U64{1} << bit;
        need(!valid(bad));
    }
    for (unsigned index = 0; index < 22; ++index) {
        for (unsigned bit = 0; bit < 64; ++bit) {
            auto changed = words;
            changed[index] ^= U64{1} << bit;
            const auto flags_ok = (changed[19] & 0x202) == 0x202 && (changed[19] & ~expected_flags) == 0;
            need(valid(changed) == (index < 15 || (index == 19 && flags_ok)));
        }
    }
    for (U64 flags = 0; flags < 65536; ++flags) {
        auto changed = words;
        changed[19] = flags;
        need(valid(changed) == ((flags & 0x202) == 0x202 && (flags & ~expected_flags) == 0));
    }
    for (const auto location : {U64{0}, frame - 8, frame + 8, UINT64_MAX, arena + 0x4a000}) {
        need(!valid(words, location));
    }
    for (const auto saved : {U64{0}, stack - 8, stack + 8, UINT64_MAX}) {
        need(!valid(words, frame, saved));
    }
    auto aligned = words;
    aligned[20] = stack - 8;
    need(valid(aligned, frame, stack - 8));
    need(!Context::valid(words, frame, arena, begin, begin + 4, stack));
    need(!Context::valid(words, frame, arena, begin + 1, begin + 4, stack));
    need(!Context::valid(words, frame, arena + 1, begin, begin + 3, stack));
    need(!Context::valid(words, frame, arena, arena, arena + 3, stack));
    std::cout << "PASS: UEFI console copied frame " << observations << " observations\n";
    return 0;
}
} // namespace kernel_uefi_console_context
