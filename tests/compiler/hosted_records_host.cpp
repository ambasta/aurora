// Generic host for tests/compiler/hosted_records.py: one linked binary holds
// every program of a hosted-bytes test. Usage: program <rows.bin>.
// Each row is six little-endian i64: program, quota, n, flag, fail_after, once.
// For each row the host creates a fresh Region with a tracing allocator, calls
// the selected entry(region, n, flag) and prints one line:
// `result allocations releases peak | released-indices | attempted-sizes`.
// fail_after >= 0 lets that many allocations succeed; `once` then fails one
// allocation and allows retries. A region that cannot close fails the run.
#include "runtime/hosted_bytes.hpp"
#include <cstdint>
#include <cstdio>
#include <cstdlib>

extern "C" std::uint64_t aurora_hosted_entry(std::uint64_t region, std::int64_t n, std::int64_t flag);
extern "C" std::uint64_t aurora_hosted_program;
extern "C" const std::uint64_t aurora_hosted_programs;

namespace {
// Bounded observation storage belongs to this test host, not the allocation API.
struct Trace {
    std::int64_t remaining = -1;
    bool once = false;
    std::size_t attempted_sizes[128]{};
    std::size_t attempted_count = 0;
    void *allocations[128]{};
    bool live[128]{};
    std::size_t released[128]{};
    std::size_t allocated_count = 0;
    std::size_t released_count = 0;
};

void *allocate(void *context, std::size_t size) noexcept {
    auto &trace = *static_cast<Trace *>(context);
    if (trace.attempted_count == 128)
        std::abort();
    trace.attempted_sizes[trace.attempted_count++] = size;
    if (trace.remaining == 0) {
        if (trace.once)
            trace.remaining = -1;
        return nullptr;
    }
    if (trace.remaining > 0)
        --trace.remaining;
    if (trace.allocated_count == 128)
        std::abort();
    void *memory = std::malloc(size);
    if (memory != nullptr) {
        trace.allocations[trace.allocated_count] = memory;
        trace.live[trace.allocated_count++] = true;
    }
    return memory;
}

void deallocate(void *context, void *address) noexcept {
    auto &trace = *static_cast<Trace *>(context);
    for (std::size_t index = 0; index < trace.allocated_count; ++index) {
        if (trace.live[index] && trace.allocations[index] == address) {
            trace.live[index] = false;
            trace.released[trace.released_count++] = index + 1;
            std::free(address);
            return;
        }
    }
    std::abort();
}
} // namespace

int main(int argc, char **argv) {
    if (argc != 2)
        return 80;
    std::FILE *file = std::fopen(argv[1], "rb");
    if (file == nullptr)
        return 81;
    std::int64_t row[6];
    for (std::uint64_t number = 0;; ++number) {
        const std::size_t count = std::fread(row, 1, sizeof(row), file);
        if (count == 0)
            break;
        if (count != sizeof(row) || row[0] < 0 || static_cast<std::uint64_t>(row[0]) >= aurora_hosted_programs ||
            row[1] < 0)
            return 82;
        aurora_hosted_program = static_cast<std::uint64_t>(row[0]);
        Trace trace;
        trace.remaining = row[4];
        trace.once = row[5] != 0;
        const aurora::hosted::bytes::Allocator allocator{&trace, allocate, deallocate};
        std::uint64_t result = 0;
        aurora::hosted::bytes::Metrics state{};
        {
            aurora::hosted::bytes::Region region(static_cast<std::uint64_t>(row[1]), allocator);
            result = aurora_hosted_entry(region.id(), row[2], row[3]);
            state = region.metrics();
            if (state.used != 0 || state.live_allocations != 0 || !region.close()) {
                std::fprintf(stderr, "row %llu: region did not close\n", static_cast<unsigned long long>(number));
                return 83;
            }
        }
        if (trace.allocated_count != state.successful_allocations || trace.released_count != state.releases) {
            std::fprintf(stderr, "row %llu: allocator trace mismatch\n", static_cast<unsigned long long>(number));
            return 84;
        }
        std::printf("%llu %llu %llu %llu |",
                    static_cast<unsigned long long>(result),
                    static_cast<unsigned long long>(state.successful_allocations),
                    static_cast<unsigned long long>(state.releases),
                    static_cast<unsigned long long>(state.peak_live_allocations));
        for (std::size_t index = 0; index < trace.released_count; ++index)
            std::printf(" %zu", trace.released[index]);
        std::printf(" |");
        for (std::size_t index = 0; index < trace.attempted_count; ++index)
            std::printf(" %zu", trace.attempted_sizes[index]);
        std::printf("\n");
    }
    const int status = std::ferror(file) ? 85 : 0;
    if (std::fclose(file) != 0 || std::fflush(stdout) != 0)
        return 86;
    return status;
}
