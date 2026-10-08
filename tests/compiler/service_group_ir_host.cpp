// Executed independent IR fixture: lexical code order differs from loan order.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>
namespace {
std::uint64_t consoleGrant = 0xC061, displayGrant = 0xD162;
struct Arguments {
    const void *console;
    std::uint64_t consoleGeneration;
    const void *display;
    std::uint64_t displayGeneration;
};
std::string trace;
void need(bool okay) { if (!okay) std::abort(); }
}
extern "C" std::uint64_t checked_group_entry(const Arguments *);
extern "C" std::uint64_t __au_runtime_console_put(const void *grant, std::uint64_t generation, std::uint64_t byte) {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
    need(grant == &consoleGrant && generation == 43 && byte == 65);
    trace += 'W';
    return 0;
}
extern "C" std::uint64_t __au_runtime_display_pixel(const void *grant, std::uint64_t generation,
    std::uint64_t x, std::uint64_t y, std::uint64_t red, std::uint64_t green, std::uint64_t blue) {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
    need(grant == &displayGrant && generation == 101 && x == 7 && y == 9 && red == 11 && green == 13 && blue == 17);
    trace += 'P';
    return 0;
}
int main() {
    const Arguments arguments{&consoleGrant, 43, &displayGrant, 101};
    need(checked_group_entry(&arguments) == 0 && trace == "WPWP");
    std::puts("PASS executed nonlexical service IR: reversed pair, distinct grants/generations and released-ID reuse");
}
