#include "../kernel/pages.hpp"
#include <cstdlib>
#include <iostream>
#include <string_view>
#include <type_traits>

namespace kernel_pages {
using aurora::memory::PageLease;
using aurora::memory::PhysicalPages;
static_assert(!std::is_copy_constructible_v<PageLease>);
static_assert(!std::is_copy_assignable_v<PageLease>);
static_assert(std::is_move_constructible_v<PageLease>);
static_assert(!std::is_move_assignable_v<PageLease>);
static_assert(!std::is_copy_constructible_v<PhysicalPages>);

auto check(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
auto main() -> int {
    PhysicalPages pool;
    PhysicalPages foreign;
    check(!pool.acquire(), "uninitialized acquisition");
    check(!pool.arena_matches(0, 0), "uninitialized arena metadata");
    check(!pool.initialize(1, 1), "alignment");
    check(!pool.initialize(0x100000, 0), "zero count");
    check(!pool.initialize(0x100000, 129), "capacity");
    check(!pool.initialize(UINT64_MAX - 4095, 1), "address overflow");
    check(pool.initialize(0x100000, 128), "initialization");
    check(pool.arena_matches(0x100000, 128) && !pool.arena_matches(0x200000, 128) && !pool.arena_matches(0x100000, 127),
          "arena identity restriction");
    check(!pool.initialize(0x200000, 1), "reinitialization");
    check(foreign.initialize(0x200000, 1), "foreign initialization");
    std::array<std::optional<PageLease>, 128> leases;
    for (std::size_t index = 0; index < leases.size(); ++index) {
        auto page = pool.acquire();
        check(page.has_value(), "capacity allocation");
        check(pool.address(*page) == 0x100000 + index * 4096, "unique frame");
        check(!foreign.address(*page) && !foreign.release(*page), "foreign ownership");
        leases[index].emplace(std::move(*page));
        check(!page->valid() && !pool.address(*page) && !pool.release(*page), "move invalidation");
    }
    check(pool.used() == 128 && !pool.acquire(), "exhaustion");
    for (std::size_t index = 0; index < leases.size(); index += 2) {
        check(pool.release(*leases[index]), "release");
        check(!pool.release(*leases[index]), "double free");
    }
    check(pool.used() == 64, "partial accounting");
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
    // Same-address allocator replacement must not resurrect previous ownership.
    std::optional<PhysicalPages> incarnation;
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
    std::cout << "PASS: physical-page ownership, invalid inputs, exhaustion, reuse, 10000 model steps\n";
    return 0;
}
} // namespace kernel_pages
