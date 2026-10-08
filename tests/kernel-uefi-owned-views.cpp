// Exact UEFI Aurora source linked to the real kernel adapter on the host.
// No guest is executed and generated Aurora assembly is not instrumented.
#include "../kernel/owned-bytes.hpp"

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
extern "C" std::int64_t __au_runtime_bytes_kernel_entry(std::uint64_t, std::int64_t, std::int64_t);

namespace {
constexpr std::size_t page_bytes = Region::page_bytes;
constexpr std::size_t page_count = Region::pool_pages;
constexpr std::uint64_t base = 0x200000;
std::uint64_t checks = 0;
void require(bool condition, const char *message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL UEFI owner-view fixture: %s\n", message);
        std::exit(1);
    }
    ++checks;
}
std::byte sentinel(std::size_t index) {
    return std::byte{static_cast<unsigned char>(0xa0 + index)};
}
struct Fixture {
    PhysicalPages pool;
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
        require(region.open(pool, backing, base, 8194), "open kernel authority");
    }
    std::span<std::byte> page(std::size_t index) {
        return std::span{backing}.subspan(index * page_bytes, page_bytes);
    }
    bool pages_match(bool allocated) {
        for (std::size_t index = 0; index < page_count; ++index) {
            const bool payload = allocated && (index == 1 || index == 3 || index == 5 || index == 7);
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
} // namespace
extern "C" [[noreturn]] void __au_runtime_bytes_kernel_fault(std::uint64_t reason) noexcept {
    std::fprintf(
        stderr, "FAIL UEFI owner-view fixture: unexpected fault %llu\n", static_cast<unsigned long long>(reason));
    std::_Exit(90);
}
int main(int argc, char **argv) {
    require(argc == 2 && argv[1][0] >= '0' && argv[1][0] <= '2' && argv[1][1] == '\0', "exact mode");
    const std::int64_t mode = argv[1][0] - '0';
    const std::int64_t length = mode == 0 ? 4097 : mode == 1 ? 0 : -1;
    Fixture fixture;
    const auto result = __au_runtime_bytes_kernel_entry(fixture.region.id(), length, 0);
    require(result == (mode == 2 ? -1 : 42), "unexpected result for independently supplied length");
    Metrics expected;
    expected.quota = 8194;
    expected.successful_allocations = mode == 0 ? 2 : mode == 1 ? 1 : 0;
    expected.releases = expected.successful_allocations;
    expected.peak_live_allocations = expected.successful_allocations;
    expected.peak_used = mode == 0 ? 8194 : 0;
    expected.last_allocation_id = expected.successful_allocations;
    expected.last_released_id = expected.successful_allocations;
    expected.peak_held_pages = mode == 0 ? 4 : 0;
    require(fixture.region.metrics() == expected, "exact metrics including no view-induced allocations/releases");
    require(fixture.pool.used() == 8 && fixture.pages_match(mode == 0), "all pages and foreign leases preserved");
    require(fixture.region.close(), "explicit grant close");
    for (std::size_t index = 0; index < page_count; index += 2) {
        require(fixture.pool.release(*fixture.holders[index]), "release original holder");
    }
    require(fixture.pool.used() == 0, "zero final pool use");
    std::printf("PASS UEFI owner-view host fixture: mode=%lld checks=%llu exact metrics/pages/leases\n",
                static_cast<long long>(mode),
                static_cast<unsigned long long>(checks));
}
#ifdef AURORA_OWNED_VIEW_ZERO_LENGTH_CONTROL
// Deliberately corrupted host executable only, never admitted to a guest.
extern "C" std::int64_t __real___au_runtime_bytes_borrow_length(const aurora::hosted::bytes::NativeOwner *) noexcept;
extern "C" std::int64_t
__wrap___au_runtime_bytes_borrow_length(const aurora::hosted::bytes::NativeOwner *owner) noexcept {
    static_cast<void>(__real___au_runtime_bytes_borrow_length(owner));
    return 0;
}
#endif
