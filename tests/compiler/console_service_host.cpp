// Scripted host for the real generated Aurora editor. The separate Session
// test authenticates host grants; this seam independently checks packed ABI,
// canonical host reports and output failure propagation from generated code.
#if defined(AURORA_CONSOLE_REGION_TEST)
#include "runtime/hosted_bytes.hpp"
#endif
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace {
std::uint64_t authority = 0xC051;
struct Argument {
    const void *grant;
    std::uint64_t generation;
#if defined(AURORA_CONSOLE_REGION_TEST)
    std::uint64_t region;
#endif
};
struct Sample {
    std::uint64_t present, byte, damaged;
};
std::uint64_t output_count{}, output_limit = UINT64_MAX;
int malformed{};
void need(bool value) {
    if (!value)
        std::abort();
}
} // namespace
extern "C" std::uint64_t checked_console_entry(const Argument *);
extern "C" void __au_runtime_console_next(const void *grant, std::uint64_t generation, Sample *sample) {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
    need(grant == &authority && generation == 41);
    need(std::scanf("%lu %lu %lu", &sample->present, &sample->byte, &sample->damaged) == 3);
    if (malformed == 1)
        sample->present = 2;
    if (malformed == 2)
        sample->byte = 256;
    if (malformed == 3)
        sample->damaged = 2;
    if (malformed == 4) {
        sample->present = 0;
        sample->byte = 1;
    }
}
extern "C" std::uint64_t __au_runtime_console_put(const void *grant, std::uint64_t generation, std::uint64_t byte) {
    need(reinterpret_cast<std::uintptr_t>(__builtin_frame_address(0)) % 16 == 0);
    need(grant == &authority && generation == 41 && byte <= 255);
    if (malformed == 5)
        return 2;
    if (output_count == output_limit) {
        ++output_count;
        return 1;
    }
    need(output_count < output_limit);
    ++output_count;
    need(std::putchar(static_cast<int>(byte)) != EOF);
    return 0;
}
int main(int argc, char **argv) {
    if (argc > 1)
        output_limit = std::strtoull(argv[1], nullptr, 10);
    if (argc > 2)
        malformed = std::atoi(argv[2]);
#if defined(AURORA_CONSOLE_REGION_TEST)
    aurora::hosted::bytes::Region region(argc > 4 ? std::strtoull(argv[4], nullptr, 10) : 16);
    const Argument argument{&authority, 41, region.id()};
#else
    const Argument argument{&authority, 41};
#endif
    const int sessions = argc > 3 ? std::atoi(argv[3]) : 1;
    need(sessions == 1 || sessions == 2);
    for (int index = 0; index < sessions; ++index) {
        const auto result = checked_console_entry(&argument);
        need(result <= 1);
#if defined(AURORA_CONSOLE_REGION_TEST)
        const auto metrics = region.metrics();
        need(metrics.used == 0 && metrics.live_allocations == 0 && metrics.successful_allocations == metrics.releases);
        std::fprintf(stderr,
                     "allocations=%lu releases=%lu peak=%lu\n",
                     metrics.successful_allocations,
                     metrics.releases,
                     metrics.peak_used);
        need(region.close());
#else
        if (result == 1)
            need(output_count == output_limit + 1);
#endif
        std::fprintf(stderr, "completion=%lu attempts=%lu\n", result, output_count);
        if (result != 0)
            return static_cast<int>(result);
    }
    return 0;
}
