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

using aurora::hosted::bytes::NativeOwner;
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
    std::int64_t mode;
    std::size_t held;
    explicit Fixture(std::int64_t input)
        : mode(input), held(input == 4 || input == 9   ? 14
                            : input == 5               ? 13
                            : input == 6 || input == 7 ? 0
                                                       : 8) {
        require(pool.initialize(base, page_count), "initialize real pool");
        for (std::size_t index = 0; index < page_count; ++index) {
            std::fill(page(index).begin(), page(index).end(), sentinel(index));
            auto lease = pool.acquire();
            require(lease.has_value() && pool.address(*lease) == base + index * page_bytes, "real holder address");
            holders[index].emplace(std::move(*lease));
        }
        for (std::size_t index = 0; index < page_count; ++index) {
            const bool available = mode >= 7 ? (mode == 7 || (mode == 9 ? index == 1 || index == 3 : index % 2 == 1))
                                             : (mode >= 4 ? index >= held : index % 2 == 1);
            if (available) {
                require(pool.release(*holders[index]), "release available holder");
            }
        }
        require(pool.used() == held, "exact real holders");
        require(region.open(pool, backing, base, 8194), "open kernel authority");
    }
    std::span<std::byte> page(std::size_t index) {
        return std::span{backing}.subspan(index * page_bytes, page_bytes);
    }
    bool pages_match(bool allocated) {
        for (std::size_t index = 0; index < page_count; ++index) {
            const bool payload =
                allocated && (mode >= 7 ? (mode == 7 ? index < 2 : index == 1 || index == 3)
                                        : (mode >= 4 ? (mode == 6 ? index < 4 : index >= held)
                                                     : (index == 1 || index == 3 || index == 5 || index == 7)));
            const auto expected = payload ? std::byte{0} : sentinel(index);
            if (!std::all_of(page(index).begin(), page(index).end(), [expected](std::byte value) {
                    return value == expected;
                })) {
                return false;
            }
            if (holders[index]->valid() && pool.address(*holders[index]) != base + index * page_bytes) {
                return false;
            }
            if (!holders[index]->valid() && pool.address(*holders[index]).has_value()) {
                return false;
            }
        }
        return true;
    }
    bool storage_matches() {
        for (std::size_t index = 0; index < 8192; ++index) {
            const std::size_t sector = index / 512;
            const std::size_t offset = index % 512;
            const std::size_t seed = sector == 8 ? 61 : sector;
            const auto expected =
                mode != 10 && (sector == 0 || sector == 7 || sector == 8 || sector == 15)
                    ? std::byte{static_cast<unsigned char>((offset * 53 + offset / 256 * 31 + seed * 17 + 7) % 256)}
                    : std::byte{0};
            const std::size_t page = mode == 7 ? index / page_bytes : 1 + 2 * (index / page_bytes);
            if (backing[page * page_bytes + index % page_bytes] != expected) {
                return false;
            }
        }
        return true;
    }
};
Fixture *active = nullptr;
std::size_t failed_allocations_checked = 0;
std::size_t storage_releases_checked = 0;
} // namespace

extern "C" void __real___au_runtime_bytes_allocate(std::uint64_t, std::int64_t, NativeOwner *) noexcept;
extern "C" void
__wrap___au_runtime_bytes_allocate(std::uint64_t region, std::int64_t length, NativeOwner *output) noexcept {
    if (active != nullptr && active->mode >= 7 && active->mode <= 9 && length <= 3) {
        const auto metrics = active->region.metrics();
        const auto pages = active->pool.used();
        const auto bytes = active->backing;
        __real___au_runtime_bytes_allocate(region, length, output);
        require(output->region == region && output->allocation == 0 && output->length == 0 && output->success == 0,
                "canonical failed allocation");
        require(active->region.metrics() == metrics && active->pool.used() == pages && active->backing == bytes,
                "failed allocation preserves complete metrics, physical bytes and leases");
        ++failed_allocations_checked;
    } else {
        __real___au_runtime_bytes_allocate(region, length, output);
    }
}

extern "C" void __real___au_runtime_bytes_drop(NativeOwner *) noexcept;
extern "C" void __wrap___au_runtime_bytes_drop(NativeOwner *owner) noexcept {
    if (active != nullptr && active->mode >= 7 && owner->success != 0 && owner->length == 8192) {
        require(active->storage_matches(), "independent complete storage byte pattern");
        ++storage_releases_checked;
    }
    __real___au_runtime_bytes_drop(owner);
}

#ifdef AURORA_RAM_SECTOR_ALIAS_CONTROL
extern "C" std::uint64_t __real___au_runtime_bytes_set(NativeOwner *, std::int64_t, std::uint64_t) noexcept;
extern "C" std::uint64_t
__wrap___au_runtime_bytes_set(NativeOwner *owner, std::int64_t index, std::uint64_t value) noexcept {
    // Deliberately alias logical page two onto page one in this hosted control.
    if (owner->success != 0 && owner->length == 8192 && index >= 4096) {
        index -= 4096;
    }
    return __real___au_runtime_bytes_set(owner, index, value);
}
#endif

extern "C" [[noreturn]] void __au_runtime_bytes_kernel_fault(std::uint64_t reason) noexcept {
    std::fprintf(
        stderr, "FAIL UEFI owner-view fixture: unexpected fault %llu\n", static_cast<unsigned long long>(reason));
    std::_Exit(90);
}
int main(int argc, char **argv) {
    require(argc == 2 && ((argv[1][0] >= '0' && argv[1][0] <= '9' && argv[1][1] == '\0') ||
                          (argv[1][0] == '1' && argv[1][1] == '0' && argv[1][2] == '\0')),
            "exact mode");
    const std::int64_t mode = argv[1][1] == '\0' ? argv[1][0] - '0' : 10;
    const std::int64_t length = mode >= 7 ? 16 : mode == 1 ? 0 : mode == 2 ? -1 : 4097;
    Fixture fixture(mode);
    active = &fixture;
    const std::int64_t selector = mode >= 7                ? (mode == 10 ? 4 : mode - 2)
                                  : mode == 3 || mode == 6 ? 1
                                  : mode == 4              ? 2
                                  : mode == 5              ? 3
                                                           : 0;
    const auto result = __au_runtime_bytes_kernel_entry(fixture.region.id(), length, selector);
    require(result == (mode == 2 ? -1 : 42), "unexpected result for independently supplied length");
    Metrics expected;
    expected.quota = 8194;
    expected.successful_allocations = mode == 0 ? 2 : mode == 1 ? 1 : mode == 2 ? 0 : mode == 3 || mode == 6 ? 6 : 1;
    expected.releases = expected.successful_allocations;
    expected.peak_live_allocations = mode >= 3 ? 1 : expected.successful_allocations;
    expected.peak_used = mode >= 7 ? 8192 : mode == 0 ? 8194 : mode < 3 ? 0 : mode == 3 || mode == 6 ? 4098 : 4097;
    expected.last_allocation_id = expected.successful_allocations;
    expected.last_released_id = expected.successful_allocations;
    expected.peak_held_pages = mode == 0 || mode == 3 || mode == 6 ? 4 : mode >= 4 ? 2 : 0;
    require(fixture.region.metrics() == expected, "exact metrics including no view-induced allocations/releases");
    require(failed_allocations_checked == (mode >= 7 && mode <= 9 ? 1u : 0u) &&
                storage_releases_checked == (mode >= 7 ? 1u : 0u),
            "exact independent storage observations");
    require(fixture.pool.used() == fixture.held && fixture.pages_match(mode == 0 || mode >= 3),
            "all pages and foreign leases preserved");
    require(fixture.region.close(), "explicit grant close");
    for (std::size_t index = 0; index < page_count; ++index) {
        if (fixture.holders[index]->valid()) {
            require(fixture.pool.release(*fixture.holders[index]), "release original holder");
        }
    }
    require(fixture.pool.used() == 0, "zero final pool use");
    active = nullptr;
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
