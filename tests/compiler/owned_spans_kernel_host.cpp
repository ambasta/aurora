// Generated owner-backed logical spans linked to the real kernel adapter.
// No guest is executed and generated Aurora assembly is not instrumented.
#include "../../kernel/owned-bytes.hpp"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <optional>
#include <span>
#include <utility>

using aurora::kernel::bytes::Metrics;
using aurora::kernel::bytes::Region;
using aurora::memory::PageLease;
using aurora::memory::PhysicalPages;
extern "C" std::int64_t __au_runtime_owned_spans_kernel_entry(std::uint64_t, std::int64_t, std::int64_t);

namespace {
constexpr std::size_t page_bytes = Region::page_bytes;
constexpr std::size_t page_count = Region::pool_pages;
constexpr std::uint64_t base = 0x200000;
std::uint64_t checks = 0;
void require(bool condition, const char *message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL generated kernel owned spans: %s\n", message);
        std::exit(1);
    }
    ++checks;
}
std::byte sentinel(std::size_t index) {
    return std::byte{static_cast<unsigned char>(0xa0 + index)};
}
struct Fixture {
    aurora::memory::PhysicalPagePool<> pool;
    alignas(page_bytes) std::array<std::byte, page_count * page_bytes> backing;
    std::array<std::optional<PageLease>, page_count> holders;
    Region region;
    Fixture() {
        require(pool.initialize(base, page_count), "initialize real pool");
        for (std::size_t index = 0; index < page_count; ++index) {
            std::fill(page(index).begin(), page(index).end(), sentinel(index));
            auto lease = pool.acquire();
            require(lease.has_value() && pool.address(*lease) == base + index * page_bytes, "real holder address");
            holders[index].emplace(std::move(*lease));
        }
        for (std::size_t index = 1; index < page_count; index += 2) {
            require(pool.release(*holders[index]), "release odd holder");
        }
        require(pool.used() == 8, "eight real holders");
        require(region.open(pool, backing, base, backing.size()), "open kernel authority");
    }
    std::span<std::byte> page(std::size_t index) {
        return std::span{backing}.subspan(index * page_bytes, page_bytes);
    }
    // Allocations take the released odd pages in order; released payload is zeroed.
    bool pages_match(std::size_t payload_pages) {
        for (std::size_t index = 0; index < page_count; ++index) {
            const bool payload = index % 2 == 1 && index < 2 * payload_pages;
            const auto expected = payload ? std::byte{0} : sentinel(index);
            if (!std::all_of(page(index).begin(), page(index).end(), [expected](std::byte value) {
                    return value == expected;
                })) {
                return false;
            }
            if (index % 2 == 0 && pool.address(*holders[index]) != base + index * page_bytes) {
                return false;
            }
            if (index % 2 == 1 && (holders[index]->valid() || pool.address(*holders[index]).has_value())) {
                return false;
            }
        }
        return true;
    }
};
Fixture *active = nullptr;
Metrics fault_metrics{};
bool expect_failed_borrow = false;
} // namespace
extern "C" [[noreturn]] void __au_runtime_bytes_kernel_fault(std::uint64_t reason) noexcept {
    if (!expect_failed_borrow || reason != 2 || active == nullptr || active->region.metrics() != fault_metrics ||
        !active->region.is_open() || active->region.faulted() || active->pool.used() != 8 || !active->pages_match(0)) {
        std::fputs("FAIL generated kernel owned spans: unexpected fault or changed failure state\n", stderr);
        std::_Exit(90);
    }
    std::puts("PASS generated kernel owned spans: failed borrow, exact fault 2, unchanged metrics/pages/leases");
    std::fflush(stdout);
    std::_Exit(82);
}
int main(int argc, char **argv) {
    require(argc == 2 && argv[1][0] >= '0' && argv[1][0] <= '3' && argv[1][1] == '\0', "exact mode");
    const std::int64_t mode = argv[1][0] - '0';
    // Mode 3 is a typed owner of 341 24-byte elements viewed through a typed span.
    const std::int64_t length = mode == 0 ? 8193 : mode == 1 ? 0 : mode == 3 ? 341 : -1;
    const std::size_t payload_pages = mode == 0 ? 3 : mode == 3 ? 2 : 0;
    Fixture fixture;
    active = &fixture;
    fault_metrics = fixture.region.metrics();
    expect_failed_borrow = mode == 2;
    const auto result = __au_runtime_owned_spans_kernel_entry(fixture.region.id(), length, mode);
    require(mode != 2 && result == 42, "actual consumers must return expected result; failed borrow cannot return");
    Metrics expected;
    expected.quota = fixture.backing.size();
    expected.successful_allocations = 1;
    expected.releases = expected.successful_allocations;
    expected.peak_live_allocations = expected.successful_allocations;
    expected.peak_used = mode == 0 ? 8193 : mode == 3 ? 8184 : 0;
    expected.last_allocation_id = expected.successful_allocations;
    expected.last_released_id = expected.successful_allocations;
    expected.peak_held_pages = payload_pages;
    require(fixture.region.metrics() == expected, "exact metrics including no view-induced allocations/releases");
    require(fixture.pool.used() == 8 && fixture.pages_match(payload_pages), "all pages and foreign leases preserved");
    require(fixture.region.close(), "explicit grant close");
    for (std::size_t index = 0; index < page_count; index += 2) {
        require(fixture.pool.release(*fixture.holders[index]), "release original holder");
    }
    require(fixture.pool.used() == 0, "zero final pool use");
    std::printf("PASS generated kernel owned spans: mode=%lld checks=%llu exact metrics/pages/leases\n",
                static_cast<long long>(mode),
                static_cast<unsigned long long>(checks));
}
