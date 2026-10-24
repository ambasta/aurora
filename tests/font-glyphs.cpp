// Prints the shared 5x7 font's glyph for every byte as seven visual rows of five
// columns (bit row * 5 + column), compared with the reviewed tests/font5x7.golden.
#include <cstdint>
#include <cstdio>

extern "C" std::uint64_t font_glyph(std::uint8_t);

int main() {
    for (unsigned byte = 0; byte != 256; ++byte) {
        const auto bits = font_glyph(static_cast<std::uint8_t>(byte));
        std::printf("%03u %c ", byte, byte > 32 && byte < 127 ? static_cast<char>(byte) : '.');
        for (unsigned index = 0; index != 35; ++index) {
            if (index != 0 && index % 5 == 0)
                std::putchar('/');
            std::putchar((bits >> index) & 1 ? '1' : '0');
        }
        if (bits >> 35)
            std::printf(" excess=%llx", static_cast<unsigned long long>(bits >> 35));
        std::putchar('\n');
    }
}
