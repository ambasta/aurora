#include "../kernel/pages.hpp"
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string_view>
#include <type_traits>

namespace kernel_pages {
using aurora::memory::PageLease;
using aurora::memory::PhysicalPagePool;
using aurora::memory::PhysicalPages;
static_assert(!std::is_copy_constructible_v<PageLease>);
static_assert(!std::is_copy_assignable_v<PageLease>);
static_assert(std::is_move_constructible_v<PageLease>);
static_assert(!std::is_move_assignable_v<PageLease>);
static_assert(!std::is_default_constructible_v<PhysicalPages>);
static_assert(!std::is_copy_constructible_v<PhysicalPages>);
static_assert(!std::is_destructible_v<PhysicalPages>);
static_assert(std::is_convertible_v<PhysicalPagePool<16> &, PhysicalPages &>);
static_assert(!std::is_convertible_v<PhysicalPagePool<16>, PhysicalPages &>);
template <std::size_t Capacity>
constexpr bool fixed_owner =
    std::is_final_v<PhysicalPagePool<Capacity>> && !std::is_copy_constructible_v<PhysicalPagePool<Capacity>> &&
    !std::is_copy_assignable_v<PhysicalPagePool<Capacity>> &&
    !std::is_move_constructible_v<PhysicalPagePool<Capacity>> && !std::is_move_assignable_v<PhysicalPagePool<Capacity>>;
static_assert(fixed_owner<16> && fixed_owner<128>);

auto check(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}

auto exercise(PhysicalPages &pool, PhysicalPages &foreign, std::size_t count) -> void {
    std::array<std::optional<PageLease>, PhysicalPagePool<>::capacity> storage;
    const std::span leases{storage.data(), count};
    for (std::size_t index = 0; index < leases.size(); ++index) {
        auto page = pool.acquire();
        check(page.has_value(), "capacity allocation");
        check(pool.address(*page) == 0x100000 + index * 4096, "unique frame");
        check(!foreign.address(*page) && !foreign.release(*page), "foreign ownership");
        leases[index].emplace(std::move(*page));
        check(!page->valid() && !pool.address(*page) && !pool.release(*page), "move invalidation");
    }
    check(pool.used() == count && !pool.acquire(), "exhaustion");
    for (std::size_t index = 0; index < leases.size(); index += 2) {
        check(pool.release(*leases[index]), "release");
        check(!pool.release(*leases[index]), "double free");
    }
    check(pool.used() == count / 2, "partial accounting");
    for (std::size_t index = 0; index < leases.size(); index += 2) {
        auto fresh = pool.acquire();
        check(fresh.has_value() && pool.address(*fresh) == 0x100000 + index * 4096, "reuse");
        check(!pool.release(*leases[index]), "retired lease against recycled generation");
        leases[index].emplace(std::move(*fresh));
    }
    for (auto &lease : leases)
        check(pool.release(*lease), "cleanup");
    check(pool.used() == 0, "cleanup count");
    // Deterministic state-machine stress against an independent live-slot count.
    auto random = std::uint32_t{0x12345678};
    auto live = std::size_t{0};
    for (auto step = 0; step < 10000; ++step) {
        random = random * 1664525U + 1013904223U;
        const auto index = (random >> 16) % leases.size();
        if (leases[index]->valid()) {
            check(pool.release(*leases[index]), "stress release");
            --live;
        } else {
            auto page = pool.acquire();
            check(page.has_value(), "stress acquisition");
            leases[index].emplace(std::move(*page));
            ++live;
        }
        check(pool.used() == live, "stress accounting");
        for (std::size_t a = 0; a < leases.size(); ++a) {
            if (!leases[a]->valid())
                continue;
            for (std::size_t b = a + 1; b < leases.size(); ++b)
                if (leases[b]->valid())
                    check(pool.address(*leases[a]) != pool.address(*leases[b]), "stress alias");
        }
    }
    for (auto &lease : leases)
        if (lease->valid())
            check(pool.release(*lease), "stress cleanup");
    check(pool.used() == 0, "stress leak");
}

template <std::size_t Capacity> auto owner_cases() -> void {
    PhysicalPagePool<Capacity> pool;
    PhysicalPagePool<> foreign;
    check(!pool.acquire(), "uninitialized acquisition");
    check(!pool.arena_matches(0, 0), "uninitialized arena metadata");
    class Input final {
    public:
        std::uint64_t base;
        std::size_t count;
    };
    constexpr std::array invalid{
        Input{1, 1},
        Input{0x100000, 0},
        Input{0x100000, Capacity + 1},
        Input{0x100000, SIZE_MAX},
        Input{UINT64_MAX - 4095, 1},
        Input{UINT64_MAX - Capacity * PhysicalPages::page_size + 1, Capacity},
    };
    for (const auto &input : invalid)
        check(!pool.initialize(input.base, input.count) && !pool.acquire() && pool.used() == 0,
              "invalid initialization leaves metadata unbound");
    check(pool.initialize(0x100000, Capacity), "initialization");
    check(pool.arena_matches(0x100000, Capacity) && !pool.arena_matches(0x200000, Capacity) &&
              !pool.arena_matches(0x100000, Capacity - 1),
          "arena identity restriction");
    check(!pool.initialize(0x200000, 1), "reinitialization");
    check(foreign.initialize(0x200000, 1), "foreign initialization");
    exercise(pool, foreign, Capacity);

    PhysicalPagePool<Capacity> single;
    check(single.initialize(UINT64_MAX - PhysicalPages::page_size * 2 + 1, 1), "last representable arena");
    auto last = single.acquire();
    check(last && !single.acquire() && single.address(*last) == UINT64_MAX - PhysicalPages::page_size * 2 + 1 &&
              single.release(*last),
          "initialized count restricts private backing capacity");

    // Same-address allocator replacement must not resurrect previous ownership.
    std::optional<PhysicalPagePool<Capacity>> incarnation;
    incarnation.emplace();
    check(incarnation->initialize(0x300000, 1), "first incarnation");
    auto stale = incarnation->acquire();
    check(stale.has_value(), "old incarnation lease");
    incarnation.reset();
    incarnation.emplace();
    check(incarnation->initialize(0x400000, 1), "second incarnation");
    auto current = incarnation->acquire();
    check(current.has_value(), "new incarnation lease");
    check(!incarnation->address(*stale) && !incarnation->release(*stale), "incarnation resurrection");
    check(incarnation->address(*current) == 0x400000 && incarnation->release(*current), "new incarnation ownership");
}

auto cross_capacity_incarnation() -> void {
    // A shared epoch sequence must reject a live lease even when a differently
    // sized owner reuses the very same core address and page generation.
    alignas(PhysicalPagePool<>) std::array<std::byte, sizeof(PhysicalPagePool<>)> storage{};
    auto *small = std::construct_at(reinterpret_cast<PhysicalPagePool<16> *>(storage.data()));
    check(small->initialize(0x300000, 1), "small incarnation");
    auto small_lease = small->acquire();
    check(small_lease.has_value(), "small incarnation lease");
    auto *old_core = &static_cast<PhysicalPages &>(*small);
    std::destroy_at(small);
    auto *large = std::construct_at(reinterpret_cast<PhysicalPagePool<> *>(storage.data()));
    check(&static_cast<PhysicalPages &>(*large) == old_core, "same core address across capacities");
    check(large->initialize(0x300000, 1), "large incarnation");
    auto large_lease = large->acquire();
    check(large_lease && !large->address(*small_lease) && !large->release(*small_lease),
          "shared epoch rejects small lease");
    std::destroy_at(large);
    small = std::construct_at(reinterpret_cast<PhysicalPagePool<16> *>(storage.data()));
    check(small->initialize(0x300000, 1), "recreated small incarnation");
    auto current = small->acquire();
    check(current && !small->address(*large_lease) && !small->release(*large_lease) && !small->address(*small_lease) &&
              !small->release(*small_lease) && small->release(*current),
          "shared epoch rejects previous capacities");
    std::destroy_at(small);
}

auto main() -> int {
    // Start with each capacity's first owner so a mistakenly per-capacity
    // epoch sequence would collide on the same address and first generation.
    cross_capacity_incarnation();
    owner_cases<16>();
    owner_cases<128>();
    std::cout
        << "PASS: physical-page ownership, 16/128 metadata, invalid inputs, exhaustion, reuse, 20000 model steps\n";
    return 0;
}
} // namespace kernel_pages
