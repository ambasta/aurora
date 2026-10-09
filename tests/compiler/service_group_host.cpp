// Host ABI seam only. This does not implement native combined grant admission.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
namespace {
std::uint64_t consoleAuthority = 0xC051, displayAuthority = 0xD151;
struct Argument {
    const void *input;
    std::uint64_t inputGeneration;
    const void *display;
    std::uint64_t displayGeneration;
    std::uint64_t width, height;
};
struct Sample {
    std::uint64_t present, byte, damaged;
};
unsigned nexts{}, putCount{}, pixels{};
int mode{};
std::string trace;
void need(bool okay) {
    if (!okay)
        std::abort();
}
void aligned() {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
}
} // namespace
extern "C" std::uint64_t checked_group_entry(const Argument *);
extern "C" void __au_runtime_console_next(const void *grant, std::uint64_t generation, Sample *sample) {
    aligned();
    need(grant == &consoleAuthority && generation == 41);
    trace += 'N';
    ++nexts;
    *sample = mode == 1 ? Sample{0, 0, 0} : Sample{1, 'Q', mode == 2 ? 1u : 0u};
}
extern "C" std::uint64_t __au_runtime_console_put(const void *grant, std::uint64_t generation, std::uint64_t byte) {
    aligned();
    need(grant == &consoleAuthority && generation == 41 && byte == 'Q');
    trace += 'W';
    ++putCount;
    return 0;
}
extern "C" std::uint64_t __au_runtime_display_pixel(const void *grant,
                                                    std::uint64_t generation,
                                                    std::uint64_t x,
                                                    std::uint64_t y,
                                                    std::uint64_t r,
                                                    std::uint64_t g,
                                                    std::uint64_t b) {
    aligned();
    const std::uint64_t reds[] = {'Q', 11, 'Q', 11, 11, 11, 11};
    need(grant == &displayAuthority && generation == 97 && x == 7 && y == 9 && pixels < 7 && r == reds[pixels] &&
         g == 13 && b == 17);
    trace += 'P';
    ++pixels;
    return mode == 3 ? 1 : 0;
}
int main(int argc, char **argv) {
    mode = argc > 1 ? std::atoi(argv[1]) : 0;
    const Argument argument{&consoleAuthority, 41, &displayAuthority, 97, 19, 23};
    const auto result = static_cast<std::int64_t>(checked_group_entry(&argument));
    if (mode == 0)
        need(result == 42 && nexts == 2 && putCount == 5 && pixels == 7 && trace == "NPPWNPPWWPWPWP");
    else
        need(result == -2 && nexts == 1 && putCount == 0 && pixels == (mode == 3 ? 1u : 0u) &&
             trace == (mode == 3 ? "NP" : "N"));
    std::puts(
        "PASS distinct service ABI: reordered pair, singleton subsets, independent generations and span forwarding");
}
