#include <cstdint>
#include <cstdio>
#include <cstdlib>
namespace {
std::uint64_t authority = 0xD151;
struct Argument {
    const void *grant;
    std::uint64_t generation, width, height;
};
unsigned calls{}, stores{};
bool malformed{};
void need(bool okay) {
    if (!okay)
        std::abort();
}
} // namespace
extern "C" std::uint64_t checked_display_entry(const Argument *);
extern "C" std::uint64_t __au_runtime_display_pixel(const void *grant,
                                                    std::uint64_t generation,
                                                    std::uint64_t x,
                                                    std::uint64_t y,
                                                    std::uint64_t red,
                                                    std::uint64_t green,
                                                    std::uint64_t blue) {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
    need(grant == &authority && generation == 41 && red == 11 && green == 13 && blue == 17);
    ++calls;
    if (malformed)
        return 2;
    if (x >= 19 || y >= 23)
        return 1;
    need(x == 7 && y == 9);
    ++stores;
    return 0;
}
int main(int argc, char **) {
    malformed = argc > 1;
    const Argument argument{&authority, 41, 19, 23};
    const auto result = checked_display_entry(&argument);
    need(result == 0 && calls == 4 && stores == 2);
    std::puts("PASS display private ABI: four calls, two successful stores, two bounded misses");
}
