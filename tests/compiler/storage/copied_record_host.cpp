// Observes a copied resource record only after the host region has closed.
#include "runtime/hosted_bytes.hpp"
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace aurora::hosted::bytes;
extern "C" void __au_runtime_bytes_test_produce(void *, void *);
static void check(bool value, const char *message) {
    if (!value) {
        std::fprintf(stderr, "copied record failure: %s\n", message);
        std::exit(90);
    }
}
struct Trace {
    std::int64_t remaining;
    std::array<void *, 2> allocations{};
    std::array<std::size_t, 2> sizes{};
    std::array<std::size_t, 2> released{};
    std::size_t allocated_count = 0, released_count = 0;
    static void *allocate(void *context, std::size_t size) noexcept {
        auto &self = *static_cast<Trace *>(context);
        if (self.remaining == 0)
            return nullptr;
        if (self.remaining > 0)
            --self.remaining;
        check(self.allocated_count < 2, "bounded producer allocations");
        void *memory = std::malloc(size);
        if (memory != nullptr) {
            self.allocations[self.allocated_count] = memory;
            self.sizes[self.allocated_count++] = size;
        }
        return memory;
    }
    static void release(void *context, void *memory) noexcept {
        auto &self = *static_cast<Trace *>(context);
        for (std::size_t i = 0; i < self.allocated_count; ++i) {
            if (self.allocations[i] == memory) {
                check(self.released_count < 2, "no duplicate releases");
                self.released[self.released_count++] = i + 1;
                std::memset(memory, 0xdd, self.sizes[i]);
                self.allocations[i] = nullptr;
                std::free(memory);
                return;
            }
        }
        check(false, "release matches a live allocation");
    }
};
int main(int argc, char **argv) {
    check(argc == 3, "failure countdown and sector count");
    const std::int64_t fail_after = std::strtoll(argv[1], nullptr, 10);
    const std::uint64_t count = std::strtoull(argv[2], nullptr, 10);
    Trace trace{fail_after};
    Region region(count * 512 + 1, Allocator{&trace, Trace::allocate, Trace::release});
    alignas(16) std::array<std::uint64_t, 2> input{region.id(), count};
    const auto input_before = input;
    alignas(16) std::array<unsigned char, 96> output;
    output.fill(0xa5);
    auto *result = output.data() + 8;
    __au_runtime_bytes_test_produce(input.data(), result);
    const std::size_t allocations = fail_after < 0 ? 2 : static_cast<std::size_t>(fail_after);
    const auto metrics = region.metrics();
    check(metrics.used == 0 && metrics.live_allocations == 0, "producer closes all owners before return");
    check(metrics.successful_allocations == allocations && metrics.releases == allocations &&
              trace.allocated_count == allocations && trace.released_count == allocations,
          "exact allocation and release counts before region close");
    for (std::size_t i = 0; i < allocations; ++i)
        check(trace.released[i] == allocations - i, "exact reverse release order");
    check(region.close(), "host region closes before reading copied output");
    // No returned field was inspected before the authority and all its owners closed.
    check(input == input_before, "region and scalar argument record unchanged");
    std::uint64_t status = 99;
    std::memcpy(&status, result, sizeof(status));
    check(status == (fail_after < 0 ? 0u : 3u), "success or invalid_source status survives region close");
    for (std::size_t i = 0; i < 64; ++i) {
        const auto expected = fail_after < 0 ? static_cast<unsigned char>((i * 53 + 7) % 256) : 0;
        check(result[8 + i] == expected, "every copied record byte survives region close");
    }
    // The canonical report is 8 status bytes plus 64 payload bytes, with no internal padding.
    for (std::size_t i = 0; i < output.size(); ++i)
        if (i < 8 || i >= 80)
            check(output[i] == 0xa5, "both result-buffer canaries preserved");
    auto independent = output;
    independent[16] ^= 255;
    check(independent[16] != output[16], "independent snapshot can change after region close");
    std::printf("PASS copied resource record after region.close: fail_after=%lld sectors=%llu releases=%zu\n",
                static_cast<long long>(fail_after),
                static_cast<unsigned long long>(count),
                allocations);
}
