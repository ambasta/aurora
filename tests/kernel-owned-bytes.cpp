// Isolated hosted test of the real CPU-only kernel adapter and PhysicalPages.
// Host sanitizers instrument these C++ sources, never generated Aurora assembly.
#include "../kernel/owned-bytes.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <optional>
#include <span>
#include <sys/wait.h>
#include <type_traits>
#include <unistd.h>

using aurora::hosted::bytes::__au_runtime_bytes_allocate;
using aurora::hosted::bytes::__au_runtime_bytes_at;
using aurora::hosted::bytes::__au_runtime_bytes_drop;
using aurora::hosted::bytes::__au_runtime_bytes_set;
using aurora::hosted::bytes::NativeOwner;
using aurora::kernel::bytes::Metrics;
using aurora::kernel::bytes::Region;
using aurora::memory::PageLease;
using aurora::memory::PhysicalPages;

static_assert(!std::is_copy_constructible_v<Region> && !std::is_copy_assignable_v<Region>);
static_assert(!std::is_move_constructible_v<Region> && !std::is_move_assignable_v<Region>);
static_assert(std::is_trivially_destructible_v<Region>);
static_assert(Region::pool_pages == 16 && Region::page_bytes == 4096 && Region::max_allocations == 4);
static_assert(noexcept(__au_runtime_bytes_allocate(0, 0, nullptr)));
static_assert(noexcept(__au_runtime_bytes_at(nullptr, 0)));
static_assert(noexcept(__au_runtime_bytes_set(nullptr, 0, 0)));
static_assert(noexcept(__au_runtime_bytes_drop(nullptr)));

namespace {

constexpr std::size_t page_bytes = 4096;
constexpr std::size_t pool_pages = 16;
constexpr std::size_t arena_bytes = page_bytes * pool_pages;
constexpr std::uint64_t default_base = 0x200000;
using Backing = std::array<std::byte, arena_bytes>;
using Leases = std::array<std::optional<PageLease>, pool_pages>;
std::uint64_t checks = 0;
std::uint64_t traps = 0;

void require(bool condition, const char *message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL kernel owned bytes: %s\n", message);
        std::exit(1);
    }
    ++checks;
}

bool same_owner(const NativeOwner &left, const NativeOwner &right) noexcept {
    return left.region == right.region && left.allocation == right.allocation && left.length == right.length &&
           left.success == right.success;
}

bool cleared(const NativeOwner &owner) noexcept {
    return same_owner(owner, NativeOwner{});
}

bool bytes_are(std::span<const std::byte> bytes, std::byte value) noexcept {
    return std::all_of(bytes.begin(), bytes.end(), [value](std::byte byte) {
        return byte == value;
    });
}

struct Arena {
    PhysicalPages pool;
    alignas(page_bytes) Backing backing;
    std::uint64_t base;

    explicit Arena(std::uint64_t physical_base = default_base) : base(physical_base) {
        backing.fill(std::byte{0xa5});
        require(pool.initialize(base, pool_pages), "real PhysicalPages initializes exact sixteen-page arena");
    }

    std::span<std::byte> page(std::size_t index) {
        return std::span{backing}.subspan(index * page_bytes, page_bytes);
    }
};

struct Fixture {
    Arena arena;
    Region region;

    explicit Fixture(std::uint64_t quota = arena_bytes, std::uint64_t physical_base = default_base)
        : arena(physical_base) {
        require(region.open(arena.pool, arena.backing, arena.base, quota), "valid explicit CPU region opens");
        require(region.id() != 0 && region.is_open() && !region.faulted(), "fresh grant has live nonzero identity");
    }

    ~Fixture() {
        require(region.close(), "fixture explicitly closes every non-faulted grant");
        require(arena.pool.used() == 0, "fixture ends with every physical lease released");
    }
};

void hold(Arena &arena, std::optional<PageLease> &slot) {
    auto lease = arena.pool.acquire();
    require(lease.has_value(), "independent page holder acquires from actual allocator");
    slot.emplace(std::move(*lease));
}

void release_holders(Arena &arena, Leases &holders) {
    for (auto &holder : holders) {
        if (holder && holder->valid()) {
            require(arena.pool.release(*holder), "independent page holder releases its own lease");
        }
    }
}

void require_live(const NativeOwner &owner, const Region &region, std::int64_t length) {
    require(owner.region == region.id() && owner.allocation != 0 && owner.length == length && owner.success == 1,
            "successful descriptor has exact region, unique identity, requested length and canonical success");
}

void require_failed(const NativeOwner &owner, const Region &region) {
    require(same_owner(owner, NativeOwner{region.id(), 0, 0, 0}), "failed descriptor has exact canonical shape");
}

// The child hook checks pre-halt state. _Exit is a hosted observation boundary,
// not a claim that this runner executes the kernel's terminal CPU halt.
struct FaultObservation {
    enum class Mode {
        none,
        immutable,
        retained
    } mode = Mode::none;
    Region *region = nullptr;
    Arena *arena = nullptr;
    NativeOwner *owner = nullptr;
    NativeOwner expected_owner{};
    Metrics metrics{};
    Backing backing{};
    std::size_t pool_used = 0;
    bool open = false;
    const NativeOwner *other_owner = nullptr;
    NativeOwner expected_other{};
    const PageLease *foreign_lease = nullptr;
    std::optional<std::uint64_t> foreign_address{};

    void immutable(Fixture &fixture, NativeOwner *descriptor = nullptr) {
        mode = Mode::immutable;
        region = &fixture.region;
        arena = &fixture.arena;
        owner = descriptor;
        expected_owner = descriptor == nullptr ? NativeOwner{} : *descriptor;
        metrics = region->metrics();
        backing = arena->backing;
        pool_used = arena->pool.used();
        open = region->is_open();
    }

    bool verify() const noexcept {
        if (mode == Mode::none) {
            return true;
        }
        if (arena->pool.used() != pool_used || (owner != nullptr && !same_owner(*owner, expected_owner))) {
            return false;
        }
        if ((other_owner != nullptr && !same_owner(*other_owner, expected_other)) ||
            (foreign_lease != nullptr && arena->pool.address(*foreign_lease) != foreign_address)) {
            return false;
        }
        if (mode == Mode::immutable) {
            return region->metrics() == metrics && arena->backing == backing && !region->faulted() &&
                   region->is_open() == open;
        }
        // The fail-stop hook only observes. It never closes a region, acquires
        // or releases a lease, reenters the runtime, or unwinds owner storage.
        return region->faulted() && region->is_open() && region->metrics() == metrics && arena->backing == backing;
    }
};

FaultObservation fault_observation;

template <typename Action> void expect_fault(const char *label, std::uint64_t reason, Action action) {
    int descriptors[2];
    require(pipe(descriptors) == 0, "create isolated fault observation pipe");
    std::fflush(nullptr);
    const pid_t child = fork();
    require(child >= 0, "fork isolated kernel fault observer");
    if (child == 0) {
        close(descriptors[0]);
        if (dup2(descriptors[1], STDERR_FILENO) < 0) {
            std::_Exit(91);
        }
        close(descriptors[1]);
        alarm(10);
        fault_observation = FaultObservation{};
        action();
        std::_Exit(0);
    }
    close(descriptors[1]);
    char diagnostic[4096]{};
    std::size_t used = 0;
    for (;;) {
        char chunk[512];
        const auto count = read(descriptors[0], chunk, sizeof(chunk));
        if (count < 0 && errno == EINTR) {
            continue;
        }
        require(count >= 0, "read isolated fault diagnostics");
        if (count == 0) {
            break;
        }
        const auto copied = std::min(static_cast<std::size_t>(count), sizeof(diagnostic) - 1 - used);
        std::memcpy(diagnostic + used, chunk, copied);
        used += copied;
    }
    close(descriptors[0]);
    int status = 0;
    pid_t waited;
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    require(waited == child, "reap isolated kernel fault observer");
    char expected[80];
    std::snprintf(
        expected, sizeof(expected), "kernel owned bytes fault %llu\n", static_cast<unsigned long long>(reason));
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 80 + static_cast<int>(reason) ||
        std::strcmp(diagnostic, expected) != 0) {
        std::fprintf(stderr, "FAIL kernel owned bytes fault %s: status=%d diagnostic=%s\n", label, status, diagnostic);
        std::exit(1);
    }
    ++traps;
    std::printf("PASS kernel owned bytes fault: %s\n", label);
}

void admission() {
    Arena arena;
    Region region;
    require(!region.is_open() && region.id() == 0 && !region.faulted() && region.close(),
            "pristine region has no authority and closes inertly");
    const auto pristine_metrics = region.metrics();
    for (const std::uint64_t base : {arena.base + 1, arena.base + page_bytes, UINT64_MAX}) {
        require(!region.open(arena.pool, arena.backing, base, arena_bytes), "wrong physical authority is refused");
    }
    for (const auto length : {std::size_t{0}, page_bytes, arena_bytes - 1}) {
        require(!region.open(arena.pool, std::span{arena.backing}.first(length), arena.base, arena_bytes),
                "partial backing extent is refused");
    }
    alignas(page_bytes) std::array<std::byte, arena_bytes + page_bytes> oversized;
    oversized.fill(std::byte{0x6b});
    require(!region.open(arena.pool, oversized, arena.base, arena_bytes), "oversized backing extent is refused");
    require(!region.open(arena.pool, std::span{oversized}.subspan(1, arena_bytes), arena.base, arena_bytes),
            "unaligned backing is refused");
    require(!region.open(arena.pool, arena.backing, arena.base, arena_bytes + 1),
            "payload quota above the physical arena is refused");
    require(!region.open(arena.pool, arena.backing, arena.base, UINT64_MAX),
            "maximum integer quota cannot bypass the arena bound");
    require(!region.open(arena.pool, {}, arena.base, arena_bytes), "null empty backing is refused");
    PhysicalPages empty;
    require(!region.open(empty, arena.backing, arena.base, arena_bytes), "uninitialized physical allocator is refused");
    PhysicalPages short_pool;
    require(short_pool.initialize(arena.base, 15), "construct short real allocator");
    require(!region.open(short_pool, arena.backing, arena.base, arena_bytes), "wrong physical extent is refused");
    require(region.metrics() == pristine_metrics && region.id() == 0 && !region.is_open() && arena.pool.used() == 0,
            "all admission failures preserve pristine grant, metrics and allocator");
    require(bytes_are(arena.backing, std::byte{0xa5}) && bytes_are(oversized, std::byte{0x6b}),
            "admission failure never writes any host backing");
    require(region.open(arena.pool, arena.backing, arena.base, 0), "zero-quota grant is valid");
    const auto opened = region.metrics();
    const auto id = region.id();
    require(!region.open(arena.pool, arena.backing, arena.base, arena_bytes), "live region cannot be rebound");
    require(region.id() == id && region.metrics() == opened, "rebind refusal preserves original grant");
    require(region.close() && region.close(), "explicit empty close is idempotent");
}

void runtime_lengths_and_pages() {
    Fixture fixture;
    auto &region = fixture.region;
    auto &arena = fixture.arena;
    std::uint64_t previous_id = 0;
    for (const std::int64_t length :
         {0, 1, 65, 513, 4095, 4096, 4097, 8192, 8193, 65535, static_cast<int>(arena_bytes)}) {
        arena.backing.fill(std::byte{0xa5});
        NativeOwner first;
        NativeOwner second;
        const auto before = region.metrics();
        __au_runtime_bytes_allocate(region.id(), length, &first);
        require_live(first, region, length);
        require(first.allocation > previous_id, "successful identity is never reused");
        const auto pages = (static_cast<std::size_t>(length) + page_bytes - 1) / page_bytes;
        require(arena.pool.used() == pages && region.metrics().held_pages == pages,
                "actual PhysicalPages usage equals rounded payload requirement");
        for (std::size_t index = 0; index < pool_pages; ++index) {
            require(bytes_are(arena.page(index), index < pages ? std::byte{0} : std::byte{0xa5}),
                    "initialization covers complete acquired pages and leaves all other pages untouched");
        }
        const std::int64_t second_length = pages == pool_pages ? 0 : 1;
        __au_runtime_bytes_allocate(region.id(), second_length, &second);
        require_live(second, region, second_length);
        require(second.allocation > first.allocation, "simultaneous owners have distinct identities");
        previous_id = second.allocation;
        require(region.metrics().used == static_cast<std::uint64_t>(length + second_length) &&
                    region.metrics().live_allocations == 2 &&
                    arena.pool.used() == pages + static_cast<std::size_t>(second_length),
                "two-owner accounting separates payload bytes, pages and metadata");
        for (std::int64_t index = 0; index < length; ++index) {
            require(__au_runtime_bytes_at(&first, index) == 0, "every runtime payload byte initializes to zero");
            const auto value = (static_cast<std::uint64_t>(index) * 37 + 255) & 255;
            require(__au_runtime_bytes_set(&first, index, value) == 1, "every valid runtime byte accepts copied write");
        }
        if (second_length != 0) {
            require(__au_runtime_bytes_set(&second, 0, 91) == 1, "second owner gets independent sentinel");
        }
        const auto metrics = region.metrics();
        const auto bytes = arena.backing;
        const auto descriptor = first;
        for (const auto index : {std::numeric_limits<std::int64_t>::min(),
                                 std::int64_t{-1},
                                 length,
                                 std::numeric_limits<std::int64_t>::max()}) {
            require(__au_runtime_bytes_set(&first, index, 77) == 0, "invalid write returns canonical false");
        }
        require(region.metrics() == metrics && arena.backing == bytes && same_owner(first, descriptor),
                "invalid writes preserve every byte, descriptor and metric");
        for (std::int64_t index = 0; index < length; ++index) {
            require(__au_runtime_bytes_at(&first, index) == ((static_cast<std::uint64_t>(index) * 37 + 255) & 255),
                    "copied read returns exact byte across every page boundary");
        }
        if (pages != 0) {
            // Dirty all slack with trusted host access, so a payload-only scrub
            // would fail this test even if allocation initialization was correct.
            std::fill(arena.backing.begin() + length, arena.backing.begin() + pages * page_bytes, std::byte{0xdd});
        }
        const auto first_id = first.allocation;
        __au_runtime_bytes_drop(&first);
        require(cleared(first) && region.metrics().last_released_id == first_id,
                "drop clears authority and records exact released identity");
        require(bytes_are(std::span{arena.backing}.first(pages * page_bytes), std::byte{0}),
                "release scrubs complete pages including explicitly dirtied slack");
        require(region.metrics().used == static_cast<std::uint64_t>(second_length) &&
                    region.metrics().live_allocations == 1 &&
                    arena.pool.used() == static_cast<std::size_t>(second_length),
                "first drop keeps remaining owner and physical accounting exact");
        if (second_length != 0) {
            require(__au_runtime_bytes_at(&second, 0) == 91, "first release never scrubs second payload");
        }
        __au_runtime_bytes_drop(&second);
        require(cleared(second) && arena.pool.used() == 0 && region.metrics().used == 0 &&
                    region.metrics().held_pages == 0 && region.metrics().live_allocations == 0,
                "final release returns every physical lease and payload charge");
        require(region.metrics().successful_allocations == before.successful_allocations + 2 &&
                    region.metrics().releases == before.releases + 2,
                "successful allocations and releases are committed exactly once");
        const auto ended = region.metrics();
        __au_runtime_bytes_drop(&first);
        __au_runtime_bytes_drop(&second);
        require(region.metrics() == ended, "cleared descriptor drops are inert");
    }
    require(region.metrics().peak_held_pages == pool_pages && region.metrics().peak_live_allocations == 2 &&
                region.metrics().peak_used == arena_bytes,
            "peak observations preserve exact maximum-arena and two-owner use");
}

void quota_and_metadata_failure() {
    Fixture fixture(65);
    NativeOwner live;
    __au_runtime_bytes_allocate(fixture.region.id(), 65, &live);
    require_live(live, fixture.region, 65);
    require(__au_runtime_bytes_set(&live, 64, 217) == 1, "quota sentinel initialized");
    const auto original = fixture.arena.backing;
    const auto before = fixture.region.metrics();
    for (const auto length : {-1LL,
                              std::numeric_limits<long long>::min(),
                              1LL,
                              65LL,
                              66LL,
                              static_cast<long long>(arena_bytes + 1),
                              std::numeric_limits<long long>::max()}) {
        NativeOwner failed;
        __au_runtime_bytes_allocate(fixture.region.id(), static_cast<std::int64_t>(length), &failed);
        require_failed(failed, fixture.region);
        require(fixture.region.metrics() == before && fixture.arena.backing == original &&
                    fixture.arena.pool.used() == 1,
                "quota, negative and oversized requests leave exact live state immutable");
        require(__au_runtime_bytes_set(&failed, 0, 42) == 0, "canonical failed set is false");
        __au_runtime_bytes_drop(&failed);
        require(cleared(failed) && fixture.region.metrics() == before, "failed drop only clears its descriptor");
    }
    std::array<NativeOwner, 3> empties{};
    std::uint64_t previous = live.allocation;
    for (auto &empty : empties) {
        __au_runtime_bytes_allocate(fixture.region.id(), 0, &empty);
        require_live(empty, fixture.region, 0);
        require(empty.allocation > previous, "each empty owner owns unique metadata identity");
        previous = empty.allocation;
    }
    require(fixture.region.metrics().live_allocations == 4 && fixture.region.metrics().used == 65 &&
                fixture.arena.pool.used() == 1,
            "four metadata slots include empty owners with zero physical and payload charge");
    const auto full = fixture.region.metrics();
    NativeOwner failed;
    __au_runtime_bytes_allocate(fixture.region.id(), 0, &failed);
    require_failed(failed, fixture.region);
    require(fixture.region.metrics() == full && fixture.arena.backing == original,
            "fifth empty owner fails metadata exhaustion without mutation");
    __au_runtime_bytes_drop(&failed);
    __au_runtime_bytes_drop(&empties[1]);
    __au_runtime_bytes_allocate(fixture.region.id(), 0, &failed);
    require_live(failed, fixture.region, 0);
    require(failed.allocation == previous + 1, "failed metadata allocation did not consume an identity");
    __au_runtime_bytes_drop(&failed);
    for (auto &empty : empties) {
        __au_runtime_bytes_drop(&empty);
    }
    __au_runtime_bytes_drop(&live);
    NativeOwner reused;
    __au_runtime_bytes_allocate(fixture.region.id(), 65, &reused);
    require_live(reused, fixture.region, 65);
    require(__au_runtime_bytes_at(&reused, 64) == 0, "released quota and metadata return initialized storage");
    __au_runtime_bytes_drop(&reused);

    Fixture maximum(arena_bytes, default_base + arena_bytes);
    NativeOwner excessive;
    const auto metrics = maximum.region.metrics();
    __au_runtime_bytes_allocate(maximum.region.id(), static_cast<std::int64_t>(arena_bytes + 1), &excessive);
    require_failed(excessive, maximum.region);
    require(maximum.region.metrics() == metrics && bytes_are(maximum.arena.backing, std::byte{0xa5}),
            "oversized payload fails against the largest admitted quota without backing mutation");
    __au_runtime_bytes_drop(&excessive);
}

void fragmented_leases() {
    Fixture fixture;
    Leases holders;
    for (auto &holder : holders) {
        hold(fixture.arena, holder);
    }
    for (std::size_t index = 1; index < pool_pages; index += 2) {
        require(fixture.arena.pool.release(*holders[index]),
                "release alternating slots to produce actual fragmentation");
    }
    NativeOwner first;
    NativeOwner second;
    __au_runtime_bytes_allocate(fixture.region.id(), 8193, &first);
    __au_runtime_bytes_allocate(fixture.region.id(), 4097, &second);
    require_live(first, fixture.region, 8193);
    require_live(second, fixture.region, 4097);
    require(fixture.arena.pool.used() == 13 && fixture.region.metrics().held_pages == 5,
            "fragmented owners use five independently leased pages");
    const std::array<std::int64_t, 5> offsets{0, 4095, 4096, 8191, 8192};
    const std::array<std::size_t, 5> positions{4096, 8191, 12288, 16383, 20480};
    for (std::size_t index = 0; index < offsets.size(); ++index) {
        const auto value = 101 + index;
        require(__au_runtime_bytes_set(&first, offsets[index], value) == 1, "fragmented owner boundary write succeeds");
        require(fixture.arena.backing[positions[index]] == std::byte{static_cast<unsigned char>(value)},
                "logical offset resolves through retained PageLease identity, not physical contiguity");
    }
    require(__au_runtime_bytes_set(&second, 0, 211) == 1 && __au_runtime_bytes_set(&second, 4096, 212) == 1,
            "second fragmented owner boundary writes succeed");
    require(fixture.arena.backing[7 * page_bytes] == std::byte{211} &&
                fixture.arena.backing[9 * page_bytes] == std::byte{212},
            "second owner retains its independent fragmented page ordering");
    for (std::size_t index = 0; index < pool_pages; index += 2) {
        require(bytes_are(fixture.arena.page(index), std::byte{0xa5}) &&
                    fixture.arena.pool.address(*holders[index]) == fixture.arena.base + index * page_bytes,
                "allocation and payload access preserve every foreign holder and byte");
    }
    for (const std::size_t index : {1, 3, 5}) {
        std::fill(fixture.arena.page(index).begin(), fixture.arena.page(index).end(), std::byte{0x5a});
    }
    __au_runtime_bytes_drop(&first);
    require(__au_runtime_bytes_at(&second, 0) == 211 && __au_runtime_bytes_at(&second, 4096) == 212,
            "fragmented release preserves surviving owner's exact payload");
    for (const std::size_t index : {1, 3, 5}) {
        require(bytes_are(fixture.arena.page(index), std::byte{0}), "fragmented whole-page release scrubs every byte");
    }
    __au_runtime_bytes_drop(&second);
    require(fixture.arena.pool.used() == 8, "only independently held pages remain after both owner drops");
    release_holders(fixture.arena, holders);
}

void partial_acquisition_rollback() {
    for (std::size_t available = 0; available < pool_pages; ++available) {
        Fixture fixture;
        Leases holders;
        const auto held = pool_pages - available;
        for (std::size_t index = 0; index < held; ++index) {
            hold(fixture.arena, holders[index]);
        }
        const auto metrics = fixture.region.metrics();
        NativeOwner failed;
        __au_runtime_bytes_allocate(fixture.region.id(), arena_bytes, &failed);
        require_failed(failed, fixture.region);
        require(fixture.region.metrics() == metrics && fixture.arena.pool.used() == held,
                "every exhausted acquisition prefix rolls back without committed accounting or identity");
        require(bytes_are(std::span{fixture.arena.backing}.first(held * page_bytes), std::byte{0xa5}),
                "rollback never modifies independently held pages");
        require(bytes_are(std::span{fixture.arena.backing}.subspan(held * page_bytes), std::byte{0}),
                "every acquired prefix page is fully scrubbed before rollback release");
        __au_runtime_bytes_drop(&failed);
        release_holders(fixture.arena, holders);
        NativeOwner retry;
        __au_runtime_bytes_allocate(fixture.region.id(), arena_bytes, &retry);
        require_live(retry, fixture.region, arena_bytes);
        require(fixture.arena.pool.used() == pool_pages, "all rolled-back leases are reusable by a successful retry");
        __au_runtime_bytes_drop(&retry);
    }
}

void close_and_reopen() {
    Fixture fixture;
    NativeOwner empty;
    NativeOwner live;
    __au_runtime_bytes_allocate(fixture.region.id(), 0, &empty);
    __au_runtime_bytes_allocate(fixture.region.id(), 4097, &live);
    require_live(empty, fixture.region, 0);
    require_live(live, fixture.region, 4097);
    require(__au_runtime_bytes_set(&live, 4096, 137) == 1, "close refusal sentinel written");
    const auto before = fixture.region.metrics();
    const auto backing = fixture.arena.backing;
    const auto id = fixture.region.id();
    require(!fixture.region.close(), "explicit close refuses live page ownership");
    require(fixture.region.id() == id && fixture.region.is_open() && !fixture.region.faulted() &&
                fixture.region.metrics() == before && fixture.arena.backing == backing &&
                fixture.arena.pool.used() == 2,
            "refused close preserves exact authority, payload, accounting and leases");
    require(__au_runtime_bytes_at(&live, 4096) == 137, "refused close preserves operational ownership");
    __au_runtime_bytes_drop(&live);
    const auto only_empty = fixture.region.metrics();
    require(!fixture.region.close() && fixture.region.metrics() == only_empty && fixture.arena.pool.used() == 0,
            "empty live owner independently prevents closing metadata authority");
    __au_runtime_bytes_drop(&empty);
    const auto final_metrics = fixture.region.metrics();
    require(fixture.region.close() && fixture.region.close() && !fixture.region.is_open() &&
                fixture.region.metrics() == final_metrics,
            "successful explicit close unregisters once without erasing historical metrics");
    require(fixture.region.open(fixture.arena.pool, fixture.arena.backing, fixture.arena.base, 0),
            "fully released region storage can receive a fresh zero-quota grant");
    Metrics reset;
    require(fixture.region.id() > id && fixture.region.metrics() == reset,
            "reopened storage has fresh authority and reset grant accounting");
    NativeOwner failed;
    __au_runtime_bytes_allocate(fixture.region.id(), 1, &failed);
    require_failed(failed, fixture.region);
    require(fixture.region.metrics() == reset, "zero-quota nonempty failure commits nothing");
    __au_runtime_bytes_drop(&failed);
    __au_runtime_bytes_allocate(fixture.region.id(), 0, &empty);
    require_live(empty, fixture.region, 0);
    __au_runtime_bytes_drop(&empty);
}

void descriptor_faults() {
    for (int operation = 0; operation < 4; ++operation) {
        char label[80];
        std::snprintf(label, sizeof(label), "null descriptor operation %d", operation);
        expect_fault(label, 1, [operation] {
            Fixture fixture;
            fault_observation.immutable(fixture);
            switch (operation) {
            case 0:
                __au_runtime_bytes_allocate(fixture.region.id(), 0, nullptr);
                break;
            case 1:
                static_cast<void>(__au_runtime_bytes_at(nullptr, 0));
                break;
            case 2:
                static_cast<void>(__au_runtime_bytes_set(nullptr, 0, 0));
                break;
            default:
                __au_runtime_bytes_drop(nullptr);
                break;
            }
        });
    }
    const std::array<NativeOwner, 5> dirty_outputs{NativeOwner{1, 0, 0, 0},
                                                   NativeOwner{0, 1, 0, 0},
                                                   NativeOwner{0, 0, 1, 0},
                                                   NativeOwner{0, 0, -1, 0},
                                                   NativeOwner{0, 0, 0, 1}};
    for (std::size_t index = 0; index < dirty_outputs.size(); ++index) {
        char label[80];
        std::snprintf(label, sizeof(label), "non-pristine allocation output %zu", index);
        expect_fault(label, 1, [&, index] {
            Fixture fixture;
            NativeOwner dirty = dirty_outputs[index];
            fault_observation.immutable(fixture, &dirty);
            __au_runtime_bytes_allocate(fixture.region.id(), 0, &dirty);
        });
    }
    for (const std::uint64_t region : {std::uint64_t{0}, UINT64_MAX}) {
        expect_fault("unknown allocation authority", 1, [region] {
            Fixture fixture;
            NativeOwner owner;
            fault_observation.immutable(fixture, &owner);
            __au_runtime_bytes_allocate(region, 0, &owner);
        });
    }
    for (int operation = 0; operation < 3; ++operation) {
        for (int mutation = 0; mutation < 14; ++mutation) {
            char label[80];
            std::snprintf(label, sizeof(label), "malformed descriptor operation %d mutation %d", operation, mutation);
            expect_fault(label, 1, [operation, mutation] {
                Fixture fixture;
                NativeOwner live;
                __au_runtime_bytes_allocate(fixture.region.id(), 65, &live);
                require_live(live, fixture.region, 65);
                require(__au_runtime_bytes_set(&live, 64, 173) == 1, "malformed descriptor sentinel written");
                NativeOwner owner = live;
                switch (mutation) {
                case 0:
                    owner.region = 0;
                    break;
                case 1:
                    owner.region = UINT64_MAX;
                    break;
                case 2:
                    owner.allocation = 0;
                    break;
                case 3:
                    owner.allocation = UINT64_MAX;
                    break;
                case 4:
                    owner.length = -1;
                    break;
                case 5:
                    owner.length = 64;
                    break;
                case 6:
                    owner.length = 66;
                    break;
                case 7:
                    owner.success = 0;
                    break;
                case 8:
                    owner.success = 2;
                    break;
                case 9:
                    owner.success = UINT64_MAX;
                    break;
                case 10:
                    owner = NativeOwner{live.region, 0, 0, 1};
                    break;
                case 11:
                    owner = NativeOwner{live.region, 0, 1, 0};
                    break;
                case 12:
                    owner = NativeOwner{live.region, 1, 0, 0};
                    break;
                default:
                    owner = NativeOwner{live.region, 0, -1, 0};
                    break;
                }
                fault_observation.immutable(fixture, &owner);
                fault_observation.other_owner = &live;
                fault_observation.expected_other = live;
                if (operation == 0) {
                    static_cast<void>(__au_runtime_bytes_at(&owner, 0));
                } else if (operation == 1) {
                    static_cast<void>(__au_runtime_bytes_set(&owner, 0, 31));
                } else {
                    __au_runtime_bytes_drop(&owner);
                }
            });
        }
        expect_fault("released identity after metadata and page reuse", 1, [operation] {
            Fixture fixture;
            NativeOwner owner;
            __au_runtime_bytes_allocate(fixture.region.id(), 65, &owner);
            NativeOwner stale = owner;
            __au_runtime_bytes_drop(&owner);
            __au_runtime_bytes_allocate(fixture.region.id(), 65, &owner);
            require_live(owner, fixture.region, 65);
            require(owner.allocation != stale.allocation, "metadata reuse cannot revive released identity");
            fault_observation.immutable(fixture, &stale);
            fault_observation.other_owner = &owner;
            fault_observation.expected_other = owner;
            if (operation == 0) {
                static_cast<void>(__au_runtime_bytes_at(&stale, 0));
            } else if (operation == 1) {
                static_cast<void>(__au_runtime_bytes_set(&stale, 0, 0));
            } else {
                __au_runtime_bytes_drop(&stale);
            }
        });
        expect_fault("foreign live region cannot adopt allocation identity", 1, [operation] {
            Fixture fixture;
            Fixture other(arena_bytes, default_base + arena_bytes);
            NativeOwner owner;
            NativeOwner foreign;
            __au_runtime_bytes_allocate(fixture.region.id(), 65, &owner);
            __au_runtime_bytes_allocate(other.region.id(), 65, &foreign);
            require_live(owner, fixture.region, 65);
            require_live(foreign, other.region, 65);
            require(owner.allocation != foreign.allocation, "allocation identity is globally unique across grants");
            owner.allocation = foreign.allocation;
            fault_observation.immutable(fixture, &owner);
            if (operation == 0) {
                static_cast<void>(__au_runtime_bytes_at(&owner, 0));
            } else if (operation == 1) {
                static_cast<void>(__au_runtime_bytes_set(&owner, 0, 0));
            } else {
                __au_runtime_bytes_drop(&owner);
            }
        });
        expect_fault("closed and reopened region rejects stale authority", 1, [operation] {
            Fixture fixture;
            NativeOwner owner;
            __au_runtime_bytes_allocate(fixture.region.id(), 0, &owner);
            NativeOwner stale = owner;
            __au_runtime_bytes_drop(&owner);
            require(fixture.region.close(), "close original grant before stale authority test");
            require(fixture.region.open(fixture.arena.pool, fixture.arena.backing, fixture.arena.base, arena_bytes),
                    "reopen same storage with fresh authority");
            fault_observation.immutable(fixture, &stale);
            if (operation == 0) {
                static_cast<void>(__au_runtime_bytes_at(&stale, 0));
            } else if (operation == 1) {
                static_cast<void>(__au_runtime_bytes_set(&stale, 0, 0));
            } else {
                __au_runtime_bytes_drop(&stale);
            }
        });
    }
    expect_fault("allocate through closed authority", 1, [] {
        Fixture fixture;
        const auto id = fixture.region.id();
        require(fixture.region.close(), "explicitly close authority before stale allocation");
        NativeOwner owner;
        fault_observation.immutable(fixture, &owner);
        __au_runtime_bytes_allocate(id, 1, &owner);
    });
    for (const auto value : {std::uint64_t{256}, UINT64_MAX}) {
        for (const auto length : {std::int64_t{-1}, std::int64_t{0}, std::int64_t{1}}) {
            expect_fault("non-byte copied write value", 1, [value, length] {
                Fixture fixture;
                NativeOwner owner;
                __au_runtime_bytes_allocate(fixture.region.id(), length, &owner);
                fault_observation.immutable(fixture, &owner);
                static_cast<void>(__au_runtime_bytes_set(&owner, 0, value));
            });
        }
    }
    expect_fault("test identity advance forbidden with live grant", 1, [] {
        Fixture fixture;
        fault_observation.immutable(fixture);
        aurora::kernel::bytes::testing::advance_next_ids(UINT64_MAX, UINT64_MAX);
    });
}

void bounds_faults() {
    for (const auto length : {std::int64_t{-1}, std::int64_t{0}, std::int64_t{1}, std::int64_t{4097}}) {
        for (const auto index : {std::numeric_limits<std::int64_t>::min(),
                                 std::int64_t{-1},
                                 std::max(std::int64_t{0}, length),
                                 std::numeric_limits<std::int64_t>::max()}) {
            char label[100];
            std::snprintf(label,
                          sizeof(label),
                          "read bounds length %lld index %lld",
                          static_cast<long long>(length),
                          static_cast<long long>(index));
            expect_fault(label, 2, [length, index] {
                Fixture fixture;
                NativeOwner owner;
                __au_runtime_bytes_allocate(fixture.region.id(), length, &owner);
                fault_observation.immutable(fixture, &owner);
                static_cast<void>(__au_runtime_bytes_at(&owner, index));
            });
        }
    }
}

void observe_retention(Fixture &fixture,
                       NativeOwner &owner,
                       std::size_t first_page,
                       std::size_t count,
                       std::size_t failed_ordinal,
                       bool committed) {
    require(count != 0 && failed_ordinal < count && first_page + count <= pool_pages,
            "retention oracle describes an exact in-arena lease sequence");
    fault_observation.immutable(fixture, &owner);
    fault_observation.mode = FaultObservation::Mode::retained;
    fault_observation.metrics.retained_pages = count;
    if (!committed) {
        fault_observation.expected_owner = NativeOwner{fixture.region.id(), 0, 0, 0};
        fault_observation.metrics.held_pages += count;
        fault_observation.pool_used += count;
    }
    // Independently derive the complete backing image at failed readback. The
    // failing page is zero except its injected last byte; later pages are intact.
    for (std::size_t ordinal = 0; ordinal <= failed_ordinal; ++ordinal) {
        auto page = std::span{fault_observation.backing}.subspan((first_page + ordinal) * page_bytes, page_bytes);
        std::fill(page.begin(), page.end(), std::byte{0});
    }
    fault_observation.backing[(first_page + failed_ordinal + 1) * page_bytes - 1] = std::byte{1};
}

void retained_initialization_and_drop() {
    for (std::size_t ordinal = 0; ordinal < pool_pages; ++ordinal) {
        char label[80];
        std::snprintf(label, sizeof(label), "initialization retains all sixteen leases at ordinal %zu", ordinal);
        expect_fault(label, 3, [ordinal] {
            Fixture fixture;
            NativeOwner owner;
            observe_retention(fixture, owner, 0, pool_pages, ordinal, false);
            fixture.region.fail_scrub_for_test(ordinal);
            __au_runtime_bytes_allocate(fixture.region.id(), arena_bytes, &owner);
        });
        std::snprintf(label, sizeof(label), "drop retains all sixteen leases at ordinal %zu", ordinal);
        expect_fault(label, 3, [ordinal] {
            Fixture fixture;
            NativeOwner owner;
            __au_runtime_bytes_allocate(fixture.region.id(), arena_bytes, &owner);
            require_live(owner, fixture.region, arena_bytes);
            fixture.arena.backing.fill(std::byte{0x7b});
            observe_retention(fixture, owner, 0, pool_pages, ordinal, true);
            fixture.region.fail_scrub_for_test(ordinal);
            __au_runtime_bytes_drop(&owner);
        });
    }
    expect_fault("retention preserves unrelated live owner and foreign physical lease", 3, [] {
        Fixture fixture;
        NativeOwner survivor;
        NativeOwner owner;
        __au_runtime_bytes_allocate(fixture.region.id(), 1, &survivor);
        require_live(survivor, fixture.region, 1);
        require(__au_runtime_bytes_set(&survivor, 0, 219) == 1, "retention survivor sentinel written");
        std::optional<PageLease> holder;
        hold(fixture.arena, holder);
        __au_runtime_bytes_allocate(fixture.region.id(), 13 * page_bytes + 1, &owner);
        require_live(owner, fixture.region, 13 * page_bytes + 1);
        std::fill(fixture.arena.backing.begin() + 2 * page_bytes, fixture.arena.backing.end(), std::byte{0x6c});
        observe_retention(fixture, owner, 2, 14, 7, true);
        fault_observation.other_owner = &survivor;
        fault_observation.expected_other = survivor;
        fault_observation.foreign_lease = &*holder;
        fault_observation.foreign_address = fixture.arena.pool.address(*holder);
        fixture.region.fail_scrub_for_test(7);
        __au_runtime_bytes_drop(&owner);
    });
}

void retained_rollback() {
    // Every nonempty acquired prefix, with the failed readback at every position
    // in that prefix. Empty rollback owns no page and is covered separately.
    for (std::size_t available = 1; available < pool_pages; ++available) {
        for (std::size_t ordinal = 0; ordinal < available; ++ordinal) {
            char label[80];
            std::snprintf(label, sizeof(label), "rollback retains prefix %zu at ordinal %zu", available, ordinal);
            expect_fault(label, 3, [available, ordinal] {
                Fixture fixture;
                Leases holders;
                const auto held = pool_pages - available;
                for (std::size_t index = 0; index < held; ++index) {
                    hold(fixture.arena, holders[index]);
                }
                NativeOwner owner;
                observe_retention(fixture, owner, held, available, ordinal, false);
                fault_observation.foreign_lease = &*holders[0];
                fault_observation.foreign_address = fixture.arena.pool.address(*holders[0]);
                fixture.region.fail_scrub_for_test(ordinal);
                __au_runtime_bytes_allocate(fixture.region.id(), arena_bytes, &owner);
            });
        }
    }
}

void identity_ceilings() {
    // Run last. Production-width exhaustion is permanent in this process, not
    // simulated by narrowing IDs or resetting the runtime globals afterward.
    aurora::kernel::bytes::testing::advance_next_ids(UINT64_MAX - 1, UINT64_MAX - 1);
    Fixture penultimate;
    require(penultimate.region.id() == UINT64_MAX - 1, "penultimate region identity is represented exactly");
    NativeOwner first;
    NativeOwner last;
    __au_runtime_bytes_allocate(penultimate.region.id(), 1, &first);
    __au_runtime_bytes_allocate(penultimate.region.id(), 0, &last);
    require_live(first, penultimate.region, 1);
    require_live(last, penultimate.region, 0);
    require(first.allocation == UINT64_MAX - 1 && last.allocation == UINT64_MAX,
            "last two production-width allocation identities succeed without narrowing");
    const auto metrics = penultimate.region.metrics();
    const auto backing = penultimate.arena.backing;
    for (const auto length : {std::int64_t{-1}, std::int64_t{0}, std::int64_t{1}}) {
        NativeOwner failed;
        __au_runtime_bytes_allocate(penultimate.region.id(), length, &failed);
        require_failed(failed, penultimate.region);
        require(penultimate.region.metrics() == metrics && penultimate.arena.backing == backing &&
                    penultimate.arena.pool.used() == 1,
                "exhausted allocation IDs fail without wrap, backing mutation or quota commit");
        __au_runtime_bytes_drop(&failed);
    }
    __au_runtime_bytes_drop(&first);
    __au_runtime_bytes_drop(&last);
    require(penultimate.region.metrics().last_released_id == UINT64_MAX && penultimate.arena.pool.used() == 0,
            "maximum allocation identity remains releasable");
    Fixture final(arena_bytes, default_base + arena_bytes);
    require(final.region.id() == UINT64_MAX, "maximum region identity is granted once");
    NativeOwner failed;
    const auto empty = final.region.metrics();
    __au_runtime_bytes_allocate(final.region.id(), 0, &failed);
    require_failed(failed, final.region);
    require(final.region.metrics() == empty, "allocation exhaustion survives a fresh region grant");
    __au_runtime_bytes_drop(&failed);
    Arena rejected_arena(default_base + 2 * arena_bytes);
    Region rejected;
    require(!rejected.open(rejected_arena.pool, rejected_arena.backing, rejected_arena.base, arena_bytes) &&
                rejected.id() == 0 && !rejected.is_open() && rejected.metrics() == Metrics{} &&
                rejected_arena.pool.used() == 0 && bytes_are(rejected_arena.backing, std::byte{0xa5}),
            "region identity exhaustion refuses new authority without wrapping or touching resources");
    require(final.region.close(), "maximum region identity closes after failed owner cleanup");
    require(!final.region.open(final.arena.pool, final.arena.backing, final.arena.base, arena_bytes) &&
                final.region.id() == UINT64_MAX && !final.region.is_open() && final.region.metrics() == empty,
            "exhausted region identity cannot be revived by closing and reopening storage");
}

} // namespace

extern "C" [[noreturn]] void __au_runtime_bytes_kernel_fault(std::uint64_t reason) noexcept {
    // Observe only; do not call close, allocate, drop, acquire or release here.
    // _Exit deliberately bypasses all fixture and owner stack unwinding.
    if (reason < 1 || reason > 3 || !fault_observation.verify()) {
        std::fprintf(stderr, "FAIL kernel owned bytes fault observation\n");
        std::_Exit(90);
    }
    std::fprintf(stderr, "kernel owned bytes fault %llu\n", static_cast<unsigned long long>(reason));
    std::_Exit(80 + static_cast<int>(reason));
}

int main() {
    admission();
    runtime_lengths_and_pages();
    quota_and_metadata_failure();
    fragmented_leases();
    partial_acquisition_rollback();
    close_and_reopen();
    descriptor_faults();
    bounds_faults();
    retained_initialization_and_drop();
    retained_rollback();
    identity_ceilings();
    std::printf("PASS kernel owned bytes: %llu checks, %llu isolated exact faults\n",
                static_cast<unsigned long long>(checks),
                static_cast<unsigned long long>(traps));
    return 0;
}
