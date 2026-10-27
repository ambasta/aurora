#include "../kernel/uefi/framebuffer-pixels.hpp"
#include <array>
#include <cstdlib>
#include <iostream>

namespace {
using namespace aurora::uefi;
using U64 = std::uint64_t;
std::array<std::byte, 4096 + 64> memory{};
unsigned checks{}, writes{};
auto need(bool value) -> void {
    ++checks;
    if (!value)
        std::abort();
}
class Store final {
public:
    static auto write(U64 offset, std::uint32_t value) -> void {
        need(offset % 4 == 0 && offset <= 4092);
        ++writes;
        for (unsigned byte = 0; byte < 4; ++byte)
            memory[32 + offset + byte] = std::byte(value >> (8 * byte));
    }
};
} // namespace
int main() {
    std::array<std::byte, 80> map{};
    put(map, 0, 1, 4);
    put(map, 8, 0x1000000);
    put(map, 24, Handoff::arena_bytes / 4096);
    put(map, 40, 11, 4);
    put(map, 48, 0xc0000000);
    put(map, 64, 1);
    put(map, 72, 1);
    for (unsigned format : {0U, 1U}) {
        const auto geometry = FramebufferGeometry::parse(0xc0000000, 4096, 7, 5, 11, format, 36);
        need(geometry.has_value());
        const auto grant = FramebufferAdmission::authorize_described(
            *geometry, map, 40, 1, 0x1000000, 36, (1U << 5) | (1U << 16), 0x0007040600070406ULL);
        need(grant.has_value());
        memory.fill(std::byte{0xa5});
        writes = 0;
        for (U64 y = 0; y < 5; ++y) {
            for (U64 x = 0; x < 7; ++x) {
                const auto red = static_cast<std::uint8_t>(x * 19), green = static_cast<std::uint8_t>(y * 37);
                const auto blue = static_cast<std::uint8_t>((x + y) * 11);
                need(FramebufferPixels<Store>::pixel(*grant, x, y, red, green, blue) ==
                     FramebufferPixelResult::success);
            }
        }
        need(writes == 35);
        // Independent byte oracle: no production geometry/packing helpers.
        for (unsigned at = 0; at < memory.size(); ++at) {
            std::byte expected{0xa5};
            if (at >= 32 && at < 32 + 5 * 11 * 4) {
                const unsigned offset = at - 32, x = (offset / 4) % 11, y = offset / (11 * 4), channel = offset % 4;
                if (x < 7) {
                    const auto red = x * 19, green = y * 37, blue = (x + y) * 11;
                    expected = std::byte(channel == 3                      ? 0
                                         : channel == 1                    ? green
                                         : (channel == 0) == (format == 0) ? red
                                                                           : blue);
                }
            }
            need(memory[at] == expected);
        }
        const auto before = memory;
        for (const auto point : {std::array<U64, 2>{7, 0}, {0, 5}, {UINT64_MAX, 0}, {0, UINT64_MAX}})
            need(FramebufferPixels<Store>::pixel(*grant, point[0], point[1], 1, 2, 3) ==
                 FramebufferPixelResult::out_of_bounds);
        need(memory == before && writes == 35);
    }
    std::cout << "PASS: framebuffer independent RGB/BGR bytes and guard/padding " << checks << " checks\n";
}
