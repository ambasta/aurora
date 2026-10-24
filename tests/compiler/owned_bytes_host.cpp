// Isolated trusted-host adapter gate. Generated Aurora code is not instrumented
// by this test's sanitizers. Run only after the completed-source review gate.
#include "../../runtime/hosted_bytes.hpp"

#include <array>
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <limits>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <type_traits>
#include <unistd.h>

using namespace aurora::hosted::bytes;

#if defined(AURORA_HOSTED_BYTES_TESTING)
namespace aurora::hosted::bytes::testing {
// The production bridge is private to the sealed compiler Metadata owner.
class MetadataObservation {
public:
    static std::span<const std::byte> bytes(const Region &region, const NativeOwner &owner) noexcept {
        return region.observeMetadataBytes(owner);
    }
};
} // namespace aurora::hosted::bytes::testing
#endif

static_assert(!std::is_copy_constructible_v<Region> && !std::is_copy_assignable_v<Region>);
static_assert(!std::is_move_constructible_v<Region> && !std::is_move_assignable_v<Region>);
static_assert(std::is_nothrow_constructible_v<Region, std::uint64_t>);
static_assert(std::is_nothrow_destructible_v<Region>);
static_assert(noexcept(__au_runtime_bytes_allocate(0, 0, nullptr)));
static_assert(noexcept(__au_runtime_bytes_at(nullptr, 0)));
static_assert(noexcept(__au_runtime_bytes_set(nullptr, 0, 0)));
static_assert(noexcept(__au_runtime_bytes_drop(nullptr)));
static_assert(noexcept(__au_runtime_bytes_resize(nullptr, 0)));

namespace {

std::uint64_t checks = 0;
std::uint64_t traps = 0;

void require(bool condition, const char *message) {
    if (!condition) {
        std::fprintf(stderr, "FAIL owned bytes host: %s\n", message);
        std::exit(1);
    }
    ++checks;
}

bool cleared(const NativeOwner &owner) {
    return owner.region == 0 && owner.allocation == 0 && owner.length == 0 && owner.success == 0;
}

bool same_owner(const NativeOwner &left, const NativeOwner &right) {
    return left.region == right.region && left.allocation == right.allocation && left.length == right.length &&
           left.success == right.success;
}

void require_failed(const NativeOwner &owner, const Region &region) {
    require(owner.region == region.id() && owner.allocation == 0 && owner.length == 0 && owner.success == 0,
            "allocation failure has the exact canonical shape");
}

void require_live(const NativeOwner &owner, const Region &region, std::int64_t length) {
    require(owner.region == region.id() && owner.allocation != 0 && owner.length == length && owner.success == 1,
            "successful owner has exact authority, identity, length and success");
}

struct AllocationTrace {
    struct Event {
        bool allocation;
        std::uintptr_t address;
        std::uint64_t live_before;
    };
    std::array<Event, 512> events{};
    std::size_t event_count = 0;
    std::uint64_t peak_live = 0;
    std::uintptr_t last_allocated = 0;

    void record(bool allocation, void *address) noexcept {
        require(event_count < events.size(), "allocator event trace stays within its fixed capacity");
        events[event_count++] = Event{allocation, reinterpret_cast<std::uintptr_t>(address), live};
    }

    std::uint64_t calls = 0;
    std::uint64_t frees = 0;
    std::uint64_t live = 0;
    std::size_t last_size = 0;
    bool fail_next = false;

    static void *allocate(void *context, std::size_t size) noexcept {
        auto &trace = *static_cast<AllocationTrace *>(context);
        ++trace.calls;
        trace.last_size = size;
        const bool injected_failure = trace.fail_next;
        trace.fail_next = false;
        // The huge-length test must not ask ASan or the host to reserve exabytes.
        if (injected_failure || size > 65536) {
            trace.record(true, nullptr);
            return nullptr;
        }
        void *result = std::malloc(size);
        trace.record(true, result);
        if (result != nullptr) {
            trace.last_allocated = reinterpret_cast<std::uintptr_t>(result);
            ++trace.live;
            if (trace.live > trace.peak_live) {
                trace.peak_live = trace.live;
            }
            std::memset(result, 0xa5, size);
        }
        return result;
    }

    static void deallocate(void *context, void *address) noexcept {
        auto &trace = *static_cast<AllocationTrace *>(context);
        trace.record(false, address);
        ++trace.frees;
        require(trace.live != 0, "native free cannot underflow live allocation accounting");
        --trace.live;
        std::free(address);
    }

    Allocator allocator() noexcept {
        return Allocator{this, allocate, deallocate};
    }
};

template <typename Action> void expect_trap(const char *label, const char *marker, Action action) {
    int descriptors[2];
    require(pipe(descriptors) == 0, "create trap observation pipe");
    std::fflush(nullptr);
    const pid_t child = fork();
    require(child >= 0, "fork isolated trap observer");
    if (child == 0) {
        close(descriptors[0]);
        if (dup2(descriptors[1], STDERR_FILENO) < 0) {
            std::_Exit(91);
        }
        close(descriptors[1]);
        // A non-dumpable child skips the core handler entirely; with a piped
        // core_pattern a zero RLIMIT_CORE alone still runs the helper per trap.
        const rlimit no_core{0, 0};
        if (setrlimit(RLIMIT_CORE, &no_core) != 0 || prctl(PR_SET_DUMPABLE, 0) != 0) {
            std::_Exit(92);
        }
        alarm(10);
        action();
        std::_Exit(0);
    }
    close(descriptors[1]);
    char diagnostic[4096]{};
    std::size_t used = 0;
    for (;;) {
        char chunk[512];
        const ssize_t count = read(descriptors[0], chunk, sizeof(chunk));
        if (count < 0 && errno == EINTR) {
            continue;
        }
        require(count >= 0, "read child diagnostic");
        if (count == 0) {
            break;
        }
        const std::size_t available = sizeof(diagnostic) - 1 - used;
        const std::size_t copied =
            static_cast<std::size_t>(count) < available ? static_cast<std::size_t>(count) : available;
        std::memcpy(diagnostic + used, chunk, copied);
        used += copied;
    }
    close(descriptors[0]);
    int status = 0;
    pid_t waited;
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    require(waited == child, "reap isolated trap observer");
    if (!WIFSIGNALED(status) || WTERMSIG(status) != SIGABRT || std::strstr(diagnostic, marker) == nullptr) {
        std::fprintf(stderr, "FAIL owned bytes host trap %s: status=%d diagnostic=%s\n", label, status, diagnostic);
        std::exit(1);
    }
    ++traps;
    std::printf("PASS owned bytes host trap: %s\n", label);
}

template <typename Action> void invariant(const char *label, Action action) {
    expect_trap(label, "aurora owned bytes: invariant\n", action);
}

template <typename Action> void bounds(const char *label, Action action) {
    expect_trap(label, "aurora owned bytes: bounds\n", action);
}

template <typename Action> void isolated_success(const char *label, Action action) {
    int descriptors[2];
    require(pipe(descriptors) == 0, "create successful isolation result pipe");
    std::fflush(nullptr);
    const pid_t child = fork();
    require(child >= 0, "fork successful isolated identity fixture");
    if (child == 0) {
        close(descriptors[0]);
        alarm(10);
        checks = 0;
        traps = 0;
        action();
        const std::uint64_t totals[] = {checks, traps};
        const auto count = write(descriptors[1], totals, sizeof(totals));
        close(descriptors[1]);
        std::_Exit(count == static_cast<ssize_t>(sizeof(totals)) ? 0 : 93);
    }
    close(descriptors[1]);
    std::uint64_t totals[2]{};
    std::size_t used = 0;
    while (used < sizeof(totals)) {
        const auto count =
            read(descriptors[0], reinterpret_cast<unsigned char *>(totals) + used, sizeof(totals) - used);
        if (count < 0 && errno == EINTR) {
            continue;
        }
        require(count >= 0, "read successful isolated fixture totals");
        if (count == 0) {
            break;
        }
        used += static_cast<std::size_t>(count);
    }
    close(descriptors[0]);
    int status = 0;
    pid_t waited;
    do {
        waited = waitpid(child, &status, 0);
    } while (waited < 0 && errno == EINTR);
    require(waited == child, "reap successful isolated identity fixture");
    require(WIFEXITED(status) && WEXITSTATUS(status) == 0 && used == sizeof(totals),
            "isolated identity fixture completed all assertions and returned its totals");
    checks += totals[0];
    traps += totals[1];
    std::printf("PASS owned bytes host isolated success: %s\n", label);
}

std::int64_t checked_span(const NativeOwner *owner) {
    NativeSpan view{99, {99, 99, 99, 99}, 99, 99};
    __au_runtime_bytes_borrow_span(owner, &view);
    require(view.kind == 0 && view.start == 0 && view.length == owner->length,
            "hosted borrow publishes exact contiguous kind/start/length");
    require(view.payload[1] == 0 && view.payload[2] == 0 && view.payload[3] == 0,
            "hosted borrow clears all unused payload words");
    const auto *data = reinterpret_cast<const unsigned char *>(view.payload[0]);
    for (std::int64_t index = 0; index < view.length; ++index) {
        require(data[index] == __au_runtime_bytes_at(owner, index), "direct view matches checked owner bytes");
    }
    return view.length;
}

void readonly_descriptor_snapshots(std::int64_t (*borrow)(const NativeOwner *)) {
    for (const std::int64_t length : {0, 1, 4095, 4096, 4097}) {
        Region region(16384);
        NativeOwner owner;
        __au_runtime_bytes_allocate(region.id(), length, &owner);
        const NativeOwner snapshot = owner;
        const auto metrics = region.metrics();
        require(borrow(&owner) == length, "borrow returns complete logical owner length");
        require(borrow(&snapshot) == length, "immutable snapshot validates without ownership");
        require(region.metrics() == metrics && same_owner(owner, snapshot),
                "borrow leaves descriptor and metrics intact");
        if (length) {
            require(__au_runtime_bytes_set(&owner, length - 1, 213) == 1, "seed source last byte");
            require(__au_runtime_bytes_at(&snapshot, length - 1) == 213, "snapshot reads original backing");
        }
        __au_runtime_bytes_drop(&owner);
        invariant("borrow stale snapshot after drop", [=] {
            borrow(&snapshot);
        });
        require(region.close(), "snapshot contributes no release obligation");
    }
    bounds("borrow failed allocation", [borrow] {
        Region region(0);
        NativeOwner failed;
        __au_runtime_bytes_allocate(region.id(), 1, &failed);
        borrow(&failed);
    });
    invariant("borrow null descriptor", [borrow] {
        borrow(nullptr);
    });
    for (int field = 0; field < 4; ++field) {
        invariant("borrow forged descriptor word", [=] {
            Region region(8);
            NativeOwner owner;
            __au_runtime_bytes_allocate(region.id(), 1, &owner);
            if (field == 0)
                owner.region = 0;
            if (field == 1)
                owner.allocation = 0;
            if (field == 2)
                owner.length = 2;
            if (field == 3)
                owner.success = 2;
            borrow(&owner);
        });
    }
    invariant("borrow snapshot stale after resize", [borrow] {
        Region region(8);
        NativeOwner owner;
        __au_runtime_bytes_allocate(region.id(), 1, &owner);
        const NativeOwner snapshot = owner;
        require(__au_runtime_bytes_resize(&owner, 2) == 1, "resize succeeds before stale borrow test");
        borrow(&snapshot);
    });
    invariant("borrow snapshot after grant closes", [borrow] {
        Region region(8);
        NativeOwner owner;
        __au_runtime_bytes_allocate(region.id(), 0, &owner);
        const NativeOwner snapshot = owner;
        __au_runtime_bytes_drop(&owner);
        require(region.close(), "close source grant");
        borrow(&snapshot);
    });
}

void runtime_lengths_and_initialization() {
    AllocationTrace trace;
    Region region(8192, trace.allocator());
    NativeOwner empty;
    __au_runtime_bytes_allocate(region.id(), 0, &empty);
    require_live(empty, region, 0);
    const std::size_t header_size = trace.last_size;
    require(header_size > 0 && trace.calls == 1 && trace.live == 1, "empty success makes a real header allocation");
    require(region.metrics().used == 0 && region.metrics().live_allocations == 1, "empty owner charges no payload");
    const auto empty_id = empty.allocation;
    __au_runtime_bytes_drop(&empty);
    require(cleared(empty) && trace.live == 0 && trace.frees == 1, "empty header released exactly once");

    std::uint64_t previous_id = empty_id;
    for (const std::int64_t length : {0, 1, 65, 513, 4097}) {
        NativeOwner first;
        NativeOwner second;
        const auto before = region.metrics();
        const auto calls_before = trace.calls;
        __au_runtime_bytes_allocate(region.id(), length, &first);
        require_live(first, region, length);
        require(first.allocation > previous_id, "allocation identities are monotonic and never reused");
        require(trace.last_size == header_size + static_cast<std::size_t>(length), "one checked header plus payload");
        __au_runtime_bytes_allocate(region.id(), 1, &second);
        require_live(second, region, 1);
        require(second.allocation > first.allocation, "concurrent owners have distinct allocation identities");
        previous_id = second.allocation;
        require(trace.calls == calls_before + 2 && trace.live == 2, "two owners have two real native allocations");
        require(region.metrics().used == static_cast<std::uint64_t>(length) + 1, "payload-only accounting is exact");
        require(region.metrics().live_allocations == 2, "both owner records stay live");
        require(__au_runtime_bytes_at(&second, 0) == 0, "second payload initialized independently");

        for (std::int64_t index = 0; index < length; ++index) {
            require(__au_runtime_bytes_at(&first, index) == 0, "every requested byte initializes to zero");
            const auto value = (static_cast<std::uint64_t>(index) * 37 + 255) & 255;
            require(__au_runtime_bytes_set(&first, index, value) == 1, "every requested byte is writable");
        }
        require(__au_runtime_bytes_set(&second, 0, 91) == 1, "second owner independently writable");
        for (std::int64_t index = 0; index < length; ++index) {
            const auto value = (static_cast<std::uint64_t>(index) * 37 + 255) & 255;
            require(__au_runtime_bytes_at(&first, index) == value, "every requested byte retains its copied value");
        }
        require(__au_runtime_bytes_at(&second, 0) == 91, "first owner never changes second owner payload");
        const auto live_metrics = region.metrics();
        for (const auto index : {std::int64_t{-1}, length, std::numeric_limits<std::int64_t>::max()}) {
            require(__au_runtime_bytes_set(&first, index, 77) == 0, "invalid set returns canonical false");
        }
        require(region.metrics() == live_metrics, "failed bounds checks preserve all accounting and identities");
        for (std::int64_t index = 0; index < length; ++index) {
            const auto value = (static_cast<std::uint64_t>(index) * 37 + 255) & 255;
            require(__au_runtime_bytes_at(&first, index) == value, "failed set preserves every payload byte");
        }
        const auto first_id = first.allocation;
        __au_runtime_bytes_drop(&first);
        require(cleared(first), "successful drop clears descriptor");
        require(region.metrics().used == 1 && region.metrics().live_allocations == 1, "drop conserves remaining owner");
        require(region.metrics().last_released_id == first_id, "released identity is observable by trusted bridge");
        require(__au_runtime_bytes_at(&second, 0) == 91, "surviving owner bytes remain untouched");
        __au_runtime_bytes_drop(&second);
        require(cleared(second) && trace.live == 0, "second drop closes final native allocation");
        require(region.metrics().used == 0 && region.metrics().live_allocations == 0, "payload quota fully reusable");
        require(region.metrics().successful_allocations == before.successful_allocations + 2 &&
                    region.metrics().releases == before.releases + 2,
                "cumulative observations survive scalar-return cleanup");
        const auto after = region.metrics();
        __au_runtime_bytes_drop(&first);
        __au_runtime_bytes_drop(&second);
        require(region.metrics() == after, "dropping already-cleared slots is inert");
    }
    require(region.metrics().peak_live_allocations == 2 && region.metrics().peak_used == 4098,
            "peak observations preserve concurrent owner evidence");
    require(trace.calls == trace.frees && trace.live == 0, "every successful host allocation is released once");
    require(region.close() && !region.is_open() && region.close(), "empty region closes idempotently");
}

void failure_atomicity_and_quota_reuse() {
    AllocationTrace trace;
    Region region(65, trace.allocator());
    NativeOwner live;
    __au_runtime_bytes_allocate(region.id(), 65, &live);
    require_live(live, region, 65);
    for (std::int64_t index = 0; index < 65; ++index) {
        require(__au_runtime_bytes_set(&live, index, 128 + static_cast<std::uint64_t>(index)) == 1,
                "fill sentinel owner before failures");
    }
    const std::int64_t invalid_lengths[] = {-1, std::numeric_limits<std::int64_t>::min(), 1, 65, 66};
    for (const std::int64_t length : invalid_lengths) {
        const auto metrics = region.metrics();
        const auto calls = trace.calls;
        NativeOwner failed;
        __au_runtime_bytes_allocate(region.id(), length, &failed);
        require_failed(failed, region);
        require(region.metrics() == metrics && trace.calls == calls, "invalid and quota failures have no host effect");
        require(__au_runtime_bytes_set(&failed, 0, 7) == 0, "failed owner set returns canonical false");
        __au_runtime_bytes_drop(&failed);
        require(cleared(failed) && region.metrics() == metrics, "canonical failed owner cleanup has no allocation");
        for (std::int64_t index = 0; index < 65; ++index) {
            require(__au_runtime_bytes_at(&live, index) == 128 + static_cast<std::uint64_t>(index),
                    "allocation failures preserve every existing byte");
        }
    }

    NativeOwner empty;
    __au_runtime_bytes_allocate(region.id(), 0, &empty);
    require_live(empty, region, 0);
    require(region.metrics().used == 65, "zero-length header can succeed at exact payload quota");
    const auto metrics = region.metrics();
    const auto empty_id = empty.allocation;
    trace.fail_next = true;
    NativeOwner host_failed;
    __au_runtime_bytes_allocate(region.id(), 0, &host_failed);
    require_failed(host_failed, region);
    require(region.metrics() == metrics && trace.live == 2, "empty metadata host failure commits nothing");
    __au_runtime_bytes_drop(&host_failed);
    __au_runtime_bytes_drop(&empty);
    __au_runtime_bytes_drop(&live);

    NativeOwner retry;
    trace.fail_next = true;
    const auto before_failure = region.metrics();
    __au_runtime_bytes_allocate(region.id(), 65, &retry);
    require_failed(retry, region);
    require(region.metrics() == before_failure && trace.live == 0, "positive host failure preserves all metrics");
    __au_runtime_bytes_drop(&retry);
    __au_runtime_bytes_allocate(region.id(), 65, &retry);
    require_live(retry, region, 65);
    require(retry.allocation == empty_id + 1, "failed requests consume no allocation identity");
    require(__au_runtime_bytes_at(&retry, 0) == 0 && __au_runtime_bytes_at(&retry, 64) == 0,
            "reused quota returns newly initialized bytes");
    __au_runtime_bytes_drop(&retry);
    require(trace.live == 0 && region.metrics().used == 0, "host failure retry cleans up exactly");

    NativeOwner survivor;
    __au_runtime_bytes_allocate(region.id(), 1, &survivor);
    require_live(survivor, region, 1);
    require(__au_runtime_bytes_set(&survivor, 0, 217) == 1, "sentinel for positive host failure");
    const auto before_positive_failure = region.metrics();
    trace.fail_next = true;
    __au_runtime_bytes_allocate(region.id(), 64, &retry);
    require_failed(retry, region);
    require(region.metrics() == before_positive_failure && trace.live == 1,
            "positive host failure keeps existing allocation and observations");
    require(__au_runtime_bytes_at(&survivor, 0) == 217, "positive host failure keeps existing payload");
    __au_runtime_bytes_drop(&retry);
    __au_runtime_bytes_drop(&survivor);

    AllocationTrace large_trace;
    Region large(std::numeric_limits<std::uint64_t>::max(), large_trace.allocator());
    NativeOwner zero;
    __au_runtime_bytes_allocate(large.id(), 0, &zero);
    const auto header_size = large_trace.last_size;
    __au_runtime_bytes_drop(&zero);
    NativeOwner huge;
    const auto before_huge = large.metrics();
    const auto previous_calls = large_trace.calls;
    __au_runtime_bytes_allocate(large.id(), std::numeric_limits<std::int64_t>::max(), &huge);
    require_failed(huge, large);
    require(large.metrics() == before_huge, "unrepresentable or host-exhausted huge request is canonical failure");
    if (static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) >
        std::numeric_limits<std::size_t>::max() - header_size) {
        require(large_trace.calls == previous_calls, "size overflow rejected before allocator callback");
    } else {
        require(large_trace.calls == previous_calls + 1, "representable huge request reaches rejecting trusted host");
    }
    __au_runtime_bytes_drop(&huge);
}

void resize_replacement_and_preservation() {
    for (const std::int64_t initial : {0, 1, 65, 513, 4097}) {
        AllocationTrace trace;
        Region region(4105, trace.allocator());
        NativeOwner first;
        NativeOwner resized;
        NativeOwner last;
        __au_runtime_bytes_allocate(region.id(), 3, &first);
        auto first_address = trace.last_allocated;
        __au_runtime_bytes_allocate(region.id(), initial, &resized);
        auto resized_address = trace.last_allocated;
        const auto header_size = trace.last_size - static_cast<std::size_t>(initial);
        __au_runtime_bytes_allocate(region.id(), 5, &last);
        auto last_address = trace.last_allocated;
        const auto first_descriptor = first;
        const auto last_descriptor = last;
        std::array<unsigned char, 4097> expected{};
        for (std::int64_t index = 0; index < initial; ++index) {
            expected[static_cast<std::size_t>(index)] = static_cast<unsigned char>((index * 37 + 153) & 255);
            require(__au_runtime_bytes_set(&resized, index, expected[static_cast<std::size_t>(index)]) == 1,
                    "seed every original resize byte");
        }
        for (std::int64_t index = 0; index < 3; ++index) {
            require(__au_runtime_bytes_set(&first, index, 71 + index) == 1, "seed first independent owner");
        }
        for (std::int64_t index = 0; index < 5; ++index) {
            require(__au_runtime_bytes_set(&last, index, 181 + index) == 1, "seed last independent owner");
        }
        // Replacement includes growing at final quota while all three native
        // allocations are live, shrinking, zero metadata and regrowing.
        for (const std::int64_t requested : {initial,
                                             std::int64_t{4097},
                                             std::int64_t{65},
                                             std::int64_t{0},
                                             std::int64_t{513},
                                             std::int64_t{1},
                                             std::int64_t{1}}) {
            const auto descriptor = resized;
            const auto metrics = region.metrics();
            const auto calls = trace.calls;
            const auto frees = trace.frees;
            const auto event_count = trace.event_count;
            if (requested == resized.length) {
                trace.fail_next = true;
                require(__au_runtime_bytes_resize(&resized, requested) == 1, "same-size resize returns true");
                require(same_owner(resized, descriptor) && region.metrics() == metrics,
                        "same-size resize leaves every descriptor word and committed observation unchanged");
                require(trace.calls == calls && trace.frees == frees && trace.event_count == event_count &&
                            trace.fail_next,
                        "same-size resize does not even consume an injected native allocation failure");
                trace.fail_next = false;
            } else {
                require(__au_runtime_bytes_resize(&resized, requested) == 1, "valid changed-size resize succeeds");
                require_live(resized, region, requested);
                require(resized.allocation == metrics.last_allocation_id + 1,
                        "changed-size resize commits the next fresh allocation identity");
                require(trace.calls == calls + 1 && trace.frees == frees + 1 && trace.live == 3,
                        "resize makes exactly one replacement and releases exactly one old header");
                require(trace.last_size == header_size + static_cast<std::size_t>(requested),
                        "resize allocates exactly one header plus the requested payload");
                require(trace.event_count == event_count + 2 && trace.events[event_count].allocation &&
                            trace.events[event_count].address != 0 && trace.events[event_count].live_before == 3 &&
                            !trace.events[event_count + 1].allocation &&
                            trace.events[event_count + 1].address == resized_address &&
                            trace.events[event_count + 1].live_before == 4,
                        "replacement allocation precedes freeing the exact old header with other owners live");
                require(trace.events[event_count].address != resized_address &&
                            trace.events[event_count].address != first_address &&
                            trace.events[event_count].address != last_address,
                        "replacement is distinct from every still-live native allocation");
                resized_address = trace.last_allocated;
                auto expected_metrics = metrics;
                expected_metrics.used = static_cast<std::uint64_t>(requested) + 8;
                if (expected_metrics.used > expected_metrics.peak_used) {
                    expected_metrics.peak_used = expected_metrics.used;
                }
                ++expected_metrics.successful_allocations;
                ++expected_metrics.releases;
                expected_metrics.last_allocation_id = resized.allocation;
                expected_metrics.last_released_id = descriptor.allocation;
                require(region.metrics() == expected_metrics,
                        "resize changes only committed payload, success/release counts and replacement identities");
                for (std::int64_t index = requested; index < descriptor.length; ++index) {
                    expected[static_cast<std::size_t>(index)] = 0;
                }
            }
            for (std::int64_t index = 0; index < requested; ++index) {
                require(__au_runtime_bytes_at(&resized, index) == expected[static_cast<std::size_t>(index)],
                        "resize preserves the prefix and zeroes each newly exposed byte including after regrowth");
            }
            require(same_owner(first, first_descriptor) && same_owner(last, last_descriptor),
                    "resize never rewrites an unrelated owner descriptor");
            for (std::int64_t index = 0; index < 3; ++index) {
                require(__au_runtime_bytes_at(&first, index) == 71 + static_cast<std::uint64_t>(index),
                        "first independent payload survives every resize");
            }
            for (std::int64_t index = 0; index < 5; ++index) {
                require(__au_runtime_bytes_at(&last, index) == 181 + static_cast<std::uint64_t>(index),
                        "last independent payload survives every resize");
            }
        }
        require(trace.peak_live == 4 && region.metrics().peak_live_allocations == 3 &&
                    region.metrics().peak_used == 4105,
                "transient replacement storage never inflates committed live or payload peaks");
        // Exercise replacement at both registry ends as well as the middle.
        auto replace_edge = [&](NativeOwner &edge, std::int64_t length, std::uintptr_t &address) {
            const auto before = edge;
            const auto events = trace.event_count;
            require(__au_runtime_bytes_resize(&edge, length) == 1, "resize a registry end with peers still live");
            require_live(edge, region, length);
            require(edge.allocation > before.allocation && trace.event_count == events + 2 &&
                        trace.events[events].allocation && !trace.events[events + 1].allocation &&
                        trace.events[events + 1].address == address && trace.live == 3,
                    "registry-end replacement frees exactly its prior header after allocating");
            address = trace.last_allocated;
        };
        replace_edge(last, 4, last_address);
        replace_edge(first, 2, first_address);
        require(__au_runtime_bytes_at(&first, 0) == 71 && __au_runtime_bytes_at(&first, 1) == 72 &&
                    __au_runtime_bytes_at(&last, 0) == 181 && __au_runtime_bytes_at(&last, 3) == 184 &&
                    __au_runtime_bytes_at(&resized, 0) == expected[0],
                "replacing registry head and tail preserves all three payloads and links");
        const auto event_count = trace.event_count;
        __au_runtime_bytes_drop(&last);
        __au_runtime_bytes_drop(&resized);
        __au_runtime_bytes_drop(&first);
        require(trace.event_count == event_count + 3 && !trace.events[event_count].allocation &&
                    trace.events[event_count].address == last_address &&
                    trace.events[event_count + 1].address == resized_address &&
                    trace.events[event_count + 2].address == first_address,
                "normal cleanup frees exactly the surviving allocations in requested order");
        require(trace.calls == trace.frees && trace.live == 0 && region.metrics().used == 0,
                "all replacement and original native allocations close exactly once");
    }
}

void resize_failure_atomicity() {
    AllocationTrace trace;
    Region region(70, trace.allocator());
    NativeOwner owner;
    NativeOwner other;
    __au_runtime_bytes_allocate(region.id(), 65, &owner);
    __au_runtime_bytes_allocate(region.id(), 5, &other);
    for (std::int64_t index = 0; index < 65; ++index) {
        require(__au_runtime_bytes_set(&owner, index, 128 + index) == 1, "seed resize-failure sentinel bytes");
    }
    require(__au_runtime_bytes_set(&other, 4, 247) == 1, "seed other resize-failure owner");
    const auto descriptor = owner;
    const auto other_descriptor = other;
    const auto metrics = region.metrics();
    auto unchanged = [&] {
        require(same_owner(owner, descriptor) && same_owner(other, other_descriptor) && region.metrics() == metrics,
                "failed resize preserves both exact descriptors and every committed observation");
        require(trace.live == 2 && trace.frees == 0, "failed resize never frees either native allocation");
        for (std::int64_t index = 0; index < 65; ++index) {
            require(__au_runtime_bytes_at(&owner, index) == 128 + static_cast<std::uint64_t>(index),
                    "failed resize preserves all old bytes");
        }
        require(__au_runtime_bytes_at(&other, 4) == 247, "failed resize preserves independent bytes");
    };
    for (const std::int64_t length : {std::int64_t{-1},
                                      std::numeric_limits<std::int64_t>::min(),
                                      std::int64_t{66},
                                      std::int64_t{70},
                                      std::numeric_limits<std::int64_t>::max()}) {
        const auto calls = trace.calls;
        const auto events = trace.event_count;
        require(__au_runtime_bytes_resize(&owner, length) == 0, "negative and final-quota resize return false");
        require(trace.calls == calls && trace.event_count == events,
                "negative and final-quota resize reject before native allocation");
        unchanged();
    }
    for (const std::int64_t length : {0, 1, 64}) {
        const auto calls = trace.calls;
        trace.fail_next = true;
        require(__au_runtime_bytes_resize(&owner, length) == 0,
                "shrinking and zero resize can fail their replacement metadata allocation");
        require(trace.calls == calls + 1 && !trace.fail_next,
                "shrinking failure attempts exactly one replacement allocation");
        unchanged();
    }
    NativeOwner failed;
    __au_runtime_bytes_allocate(region.id(), -1, &failed);
    const auto failed_descriptor = failed;
    const auto calls = trace.calls;
    for (const std::int64_t length : {-1, 0, 1, 65}) {
        require(__au_runtime_bytes_resize(&failed, length) == 0, "canonical failed owner cannot be revived by resize");
        require(same_owner(failed, failed_descriptor) && region.metrics() == metrics && trace.calls == calls,
                "canonical failed resize preserves descriptor and committed accounting without allocating");
    }
    __au_runtime_bytes_drop(&failed);
    require(__au_runtime_bytes_resize(&owner, 64) == 1, "shrinking retry can reuse final logical quota");
    require(owner.allocation == metrics.last_allocation_id + 1, "every preceding resize failure consumed no ID");
    require(region.metrics().used == 69, "successful shrinking releases exactly the payload difference");
    const auto after_shrink = owner;
    const auto shrink_metrics = region.metrics();
    trace.fail_next = true;
    require(__au_runtime_bytes_resize(&owner, 65) == 0, "positive growth can fail native allocation at final quota");
    require(same_owner(owner, after_shrink) && region.metrics() == shrink_metrics && trace.live == 2,
            "positive growth failure leaves old ownership and every observation committed as before");
    for (std::int64_t index = 0; index < 64; ++index) {
        require(__au_runtime_bytes_at(&owner, index) == 128 + static_cast<std::uint64_t>(index),
                "growth failure preserves the complete shrunken payload");
    }
    require(__au_runtime_bytes_resize(&owner, 65) == 1 && __au_runtime_bytes_at(&owner, 64) == 0,
            "retry grows at final quota and never resurrects a truncated byte");
    __au_runtime_bytes_drop(&owner);
    __au_runtime_bytes_drop(&other);

    AllocationTrace large_trace;
    Region large(std::numeric_limits<std::uint64_t>::max(), large_trace.allocator());
    NativeOwner huge;
    __au_runtime_bytes_allocate(large.id(), 1, &huge);
    require(__au_runtime_bytes_set(&huge, 0, 219) == 1, "seed huge-resize survivor");
    const auto huge_before = huge;
    const auto large_metrics = large.metrics();
    const auto large_calls = large_trace.calls;
    const auto header_size = large_trace.last_size - 1;
    require(__au_runtime_bytes_resize(&huge, std::numeric_limits<std::int64_t>::max()) == 0,
            "unrepresentable or host-exhausted huge resize fails without wrapping");
    require(same_owner(huge, huge_before) && large.metrics() == large_metrics && large_trace.frees == 0 &&
                __au_runtime_bytes_at(&huge, 0) == 219,
            "huge resize failure preserves complete descriptor, payload and committed accounting");
    if (static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()) >
        std::numeric_limits<std::size_t>::max() - header_size) {
        require(large_trace.calls == large_calls, "unrepresentable resize layout rejects before native allocator");
    } else {
        require(large_trace.calls == large_calls + 1, "representable huge resize reaches rejecting trusted host");
    }
    __au_runtime_bytes_drop(&huge);
}

void resize_descriptor_validation() {
    AllocationTrace trace;
    Region region(16, trace.allocator());
    Region other(16);
    NativeOwner owner;
    __au_runtime_bytes_allocate(region.id(), 4, &owner);
    const auto original = owner;
    require(__au_runtime_bytes_set(&owner, 0, 201) == 1, "seed stale resize descriptor fixture");
    require(__au_runtime_bytes_resize(&owner, 2) == 1, "shrink replaces identity before stale checks");
    const auto shrunken = owner;
    require(__au_runtime_bytes_resize(&owner, 4) == 1, "regrow creates a third identity at the old length");
    for (auto stale : {original, shrunken}) {
        invariant("stale pre-resize owner cannot read after regrow", [=] {
            __au_runtime_bytes_at(&stale, 0);
        });
        invariant("stale pre-resize owner cannot write after regrow", [=]() mutable {
            __au_runtime_bytes_set(&stale, 0, 7);
        });
        invariant("stale pre-resize owner cannot release after regrow", [=]() mutable {
            __au_runtime_bytes_drop(&stale);
        });
        for (const std::int64_t length : {std::int64_t{-1}, stale.length, std::int64_t{0}}) {
            invariant("stale resize validates before negative, same-size or zero request", [=]() mutable {
                __au_runtime_bytes_resize(&stale, length);
            });
        }
    }
    for (int field = 0; field < 7; ++field) {
        auto forged = owner;
        switch (field) {
        case 0:
            forged.region = other.id();
            break;
        case 1:
            forged.allocation = 0;
            break;
        case 2:
            forged.length = -1;
            break;
        case 3:
            forged.length = 3;
            break;
        case 4:
            forged.success = 2;
            break;
        case 5:
            forged.success = 0;
            break;
        case 6:
            forged.region = 0;
            break;
        }
        for (const std::int64_t length : {std::int64_t{-1}, forged.length}) {
            invariant("forged resize descriptor validates before request shortcut", [=]() mutable {
                __au_runtime_bytes_resize(&forged, length);
            });
        }
    }
    invariant("pristine resize cannot fabricate a region", [] {
        NativeOwner pristine;
        __au_runtime_bytes_resize(&pristine, 0);
    });
    invariant("null resize descriptor validates before negative request", [] {
        __au_runtime_bytes_resize(nullptr, -1);
    });
    NativeOwner failed;
    __au_runtime_bytes_allocate(region.id(), -1, &failed);
    invariant("failed resize still rejects forged length", [=]() mutable {
        failed.length = 1;
        __au_runtime_bytes_resize(&failed, 0);
    });
    require(__au_runtime_bytes_at(&owner, 0) == 201 && __au_runtime_bytes_at(&owner, 2) == 0,
            "all isolated descriptor traps leave the current live replacement usable");
    __au_runtime_bytes_drop(&owner);
    require(region.close(), "replacement cleanup permits closing its region");
    invariant("canonical failed resize rejects a closed grant", [=]() mutable {
        __au_runtime_bytes_resize(&failed, 0);
    });
    invariant("stale replacement resize rejects a closed grant", [=]() mutable {
        auto stale = shrunken;
        __au_runtime_bytes_resize(&stale, stale.length);
    });
}

void region_lifetime_and_failures() {
    Region first(1);
    Region second(1);
    NativeOwner owner;
    __au_runtime_bytes_allocate(first.id(), 1, &owner);
    const auto before_close = first.metrics();
    require(!first.close() && first.is_open() && first.metrics() == before_close,
            "close refusal preserves grant and complete observations");
    require(__au_runtime_bytes_set(&owner, 0, 42) == 1 && __au_runtime_bytes_at(&owner, 0) == 42,
            "close refusal leaves owner authority usable");
    NativeOwner empty;
    __au_runtime_bytes_allocate(second.id(), 0, &empty);
    require(!second.close() && second.is_open(), "successful empty owner also prevents region close");

    bounds("negative read index", [&] {
        __au_runtime_bytes_at(&owner, -1);
    });
    bounds("endpoint read index", [&] {
        __au_runtime_bytes_at(&owner, 1);
    });
    bounds("huge read index", [&] {
        __au_runtime_bytes_at(&owner, std::numeric_limits<std::int64_t>::max());
    });
    bounds("successful empty read", [&] {
        __au_runtime_bytes_at(&empty, 0);
    });
    invariant("noncanonical byte", [&] {
        __au_runtime_bytes_set(&owner, 0, 256);
    });
    invariant("noncanonical byte despite invalid index", [&] {
        __au_runtime_bytes_set(&owner, -1, 256);
    });
    invariant("non-pristine allocation output", [&] {
        __au_runtime_bytes_allocate(first.id(), 0, &owner);
    });
    invariant("wrong live region", [&] {
        auto forged = owner;
        forged.region = second.id();
        __au_runtime_bytes_at(&forged, 0);
    });
    invariant("wrong region checked before index", [&] {
        auto forged = owner;
        forged.region = second.id();
        __au_runtime_bytes_set(&forged, -1, 1);
    });
    invariant("forged length", [&] {
        auto forged = owner;
        forged.length = 4097;
        __au_runtime_bytes_set(&forged, 4096, 1);
    });
    invariant("shortened length checked before index", [&] {
        auto forged = owner;
        forged.length = 0;
        __au_runtime_bytes_at(&forged, 0);
    });
    invariant("negative descriptor length", [&] {
        auto forged = owner;
        forged.length = -1;
        __au_runtime_bytes_drop(&forged);
    });
    invariant("noncanonical success", [&] {
        auto forged = owner;
        forged.success = 2;
        __au_runtime_bytes_at(&forged, 0);
    });
    invariant("failed descriptor with live identity", [&] {
        auto forged = owner;
        forged.success = 0;
        __au_runtime_bytes_drop(&forged);
    });
    invariant("success with missing identity", [&] {
        auto forged = owner;
        forged.allocation = 0;
        __au_runtime_bytes_set(&forged, 0, 1);
    });
    invariant("region destructor with live owner", [] {
        Region doomed(1);
        NativeOwner live;
        __au_runtime_bytes_allocate(doomed.id(), 1, &live);
    });
    invariant("region destructor with live empty owner", [] {
        Region doomed(0);
        NativeOwner live;
        __au_runtime_bytes_allocate(doomed.id(), 0, &live);
    });

    NativeOwner failed;
    __au_runtime_bytes_allocate(first.id(), -1, &failed);
    bounds("canonical failed read", [&] {
        __au_runtime_bytes_at(&failed, 0);
    });
    invariant("noncanonical byte on failed owner", [&] {
        __au_runtime_bytes_set(&failed, 0, 256);
    });
    invariant("failure with forged length", [&] {
        auto forged = failed;
        forged.length = 1;
        __au_runtime_bytes_set(&forged, 0, 1);
    });
    invariant("failure with unknown region", [&] {
        auto forged = failed;
        // This ID is ungranted until the isolated exhaustion fixture below.
        // Zero would instead produce the deliberately inert pristine descriptor.
        forged.region = std::numeric_limits<std::uint64_t>::max();
        __au_runtime_bytes_drop(&forged);
    });
    __au_runtime_bytes_drop(&failed);
    require(cleared(failed), "valid failed descriptor clears without quota effect");

    const auto stale = owner;
    __au_runtime_bytes_drop(&owner);
    invariant("stale read", [&] {
        __au_runtime_bytes_at(&stale, 0);
    });
    invariant("stale set with invalid index", [&] {
        auto copy = stale;
        __au_runtime_bytes_set(&copy, -1, 1);
    });
    invariant("stale double release", [&] {
        auto copy = stale;
        __au_runtime_bytes_drop(&copy);
    });
    __au_runtime_bytes_drop(&empty);
    require(first.close() && second.close(), "regions close after every owner ends");
    const auto old_region_id = first.id();
    Region replacement(1);
    require(replacement.id() > second.id() && replacement.id() != old_region_id, "region grants are never reused");
    invariant("allocation through closed grant", [&] {
        NativeOwner value;
        __au_runtime_bytes_allocate(old_region_id, 0, &value);
    });
    invariant("canonical failure from closed grant", [&] {
        NativeOwner value{old_region_id, 0, 0, 0};
        __au_runtime_bytes_drop(&value);
    });
    invariant("closed stale owner", [&] {
        __au_runtime_bytes_at(&stale, 0);
    });
    invariant("null allocation output", [&] {
        __au_runtime_bytes_allocate(replacement.id(), 0, nullptr);
    });
    invariant("null read descriptor", [] {
        __au_runtime_bytes_at(nullptr, 0);
    });
    invariant("null set descriptor", [] {
        __au_runtime_bytes_set(nullptr, 0, 0);
    });
    invariant("null drop descriptor", [] {
        __au_runtime_bytes_drop(nullptr);
    });
    invariant("unknown region grant", [] {
        NativeOwner value;
        __au_runtime_bytes_allocate(0, 0, &value);
    });
    invariant("incomplete allocator pair", [] {
        Region invalid(1, Allocator{nullptr, nullptr, nullptr});
    });
    NativeOwner pristine;
    __au_runtime_bytes_drop(&pristine);
    require(cleared(pristine), "all-zero pristine or moved-from descriptor cleanup is inert");
}

#if defined(AURORA_HOSTED_BYTES_TESTING)
void nonwrapping_identity_limits() {
    // Keep the original allocate-final-ID regression independently of the
    // resize-final-ID path. The successful child cannot exhaust parent IDs.
    isolated_success("direct allocation may still consume the final identity", [] {
        testing::advance_next_ids(std::numeric_limits<std::uint64_t>::max(), std::numeric_limits<std::uint64_t>::max());
        AllocationTrace trace;
        Region region(1, trace.allocator());
        NativeOwner failed;
        trace.fail_next = true;
        __au_runtime_bytes_allocate(region.id(), 1, &failed);
        require_failed(failed, region);
        __au_runtime_bytes_drop(&failed);
        NativeOwner owner;
        __au_runtime_bytes_allocate(region.id(), 1, &owner);
        require_live(owner, region, 1);
        require(owner.allocation == std::numeric_limits<std::uint64_t>::max(),
                "direct allocation after host failure consumes the final nonzero identity");
        require(__au_runtime_bytes_set(&owner, 0, 233) == 1, "direct final identity owns writable bytes");
        const auto metrics = region.metrics();
        const auto calls = trace.calls;
        __au_runtime_bytes_allocate(region.id(), 0, &failed);
        require_failed(failed, region);
        require(region.metrics() == metrics && trace.calls == calls && __au_runtime_bytes_at(&owner, 0) == 233,
                "direct allocation exhaustion leaves final owner and accounting untouched");
        __au_runtime_bytes_drop(&failed);
        __au_runtime_bytes_drop(&owner);
        __au_runtime_bytes_allocate(region.id(), 0, &failed);
        require_failed(failed, region);
        require(trace.calls == calls, "directly allocated final identity cannot be reused after drop");
        __au_runtime_bytes_drop(&failed);
        require(region.close(), "direct final-identity region still closes normally");
    });
    invariant("test seam refuses identity rewind", [] {
        testing::advance_next_ids(1, 1);
    });
    testing::advance_next_ids(std::numeric_limits<std::uint64_t>::max(), std::numeric_limits<std::uint64_t>::max() - 2);
    AllocationTrace trace;
    Region last_region(2, trace.allocator());
    require(last_region.id() == std::numeric_limits<std::uint64_t>::max(), "final nonzero region ID is usable");
    NativeOwner failed;
    trace.fail_next = true;
    __au_runtime_bytes_allocate(last_region.id(), 1, &failed);
    require_failed(failed, last_region);
    __au_runtime_bytes_drop(&failed);
    NativeOwner final_empty;
    __au_runtime_bytes_allocate(last_region.id(), 0, &final_empty);
    require_live(final_empty, last_region, 0);
    require(final_empty.allocation == std::numeric_limits<std::uint64_t>::max() - 2,
            "failed host allocation kept the first of the final three identities");
    NativeOwner final_owner;
    __au_runtime_bytes_allocate(last_region.id(), 1, &final_owner);
    require_live(final_owner, last_region, 1);
    require(final_owner.allocation == std::numeric_limits<std::uint64_t>::max() - 1,
            "failed host allocation kept the penultimate identity");
    require(__au_runtime_bytes_set(&final_owner, 0, 233) == 1, "penultimate identity owns real initialized bytes");
    const auto before_resize = final_owner;
    const auto before_resize_metrics = last_region.metrics();
    trace.fail_next = true;
    require(__au_runtime_bytes_resize(&final_owner, 2) == 0, "host failure leaves final resize identity available");
    require(same_owner(final_owner, before_resize) && last_region.metrics() == before_resize_metrics &&
                __au_runtime_bytes_at(&final_owner, 0) == 233 && trace.frees == 0,
            "failed resize before identity exhaustion preserves every committed fact");
    require(__au_runtime_bytes_resize(&final_owner, 2) == 1, "resize may consume the final nonzero identity");
    require_live(final_owner, last_region, 2);
    require(final_owner.allocation == std::numeric_limits<std::uint64_t>::max() &&
                __au_runtime_bytes_at(&final_owner, 0) == 233 && __au_runtime_bytes_at(&final_owner, 1) == 0,
            "final resize identity preserves old byte and zero-initializes extension");
    const auto descriptor = final_owner;
    const auto metrics = last_region.metrics();
    const auto calls = trace.calls;
    const auto frees = trace.frees;
    trace.fail_next = true;
    require(__au_runtime_bytes_resize(&final_owner, 2) == 1,
            "same-size resize still succeeds after all allocation identities are exhausted");
    require(same_owner(final_owner, descriptor) && last_region.metrics() == metrics && trace.calls == calls &&
                trace.frees == frees && trace.fail_next,
            "exhausted same-size resize preserves identity, metrics and unused host-failure injection");
    const auto empty_descriptor = final_empty;
    require(__au_runtime_bytes_resize(&final_empty, 0) == 1 && same_owner(final_empty, empty_descriptor) &&
                last_region.metrics() == metrics && trace.calls == calls && trace.frees == frees && trace.fail_next,
            "successful empty same-size resize also bypasses exhausted IDs and host allocation");
    trace.fail_next = false;
    require(__au_runtime_bytes_resize(&final_empty, 1) == 0 && same_owner(final_empty, empty_descriptor) &&
                last_region.metrics() == metrics && trace.calls == calls && trace.frees == frees,
            "exhausted identities cannot revive empty payload by resizing");
    for (const std::int64_t length : {-1, 0, 1, 3}) {
        require(__au_runtime_bytes_resize(&final_owner, length) == 0,
                "exhausted identities reject changed-size requests including shrink and metadata-only zero");
        require(same_owner(final_owner, descriptor) && last_region.metrics() == metrics && trace.calls == calls &&
                    trace.frees == frees && __au_runtime_bytes_at(&final_owner, 0) == 233 &&
                    __au_runtime_bytes_at(&final_owner, 1) == 0,
                "exhausted resize never wraps identity, calls allocator, frees or mutates either byte");
    }
    invariant("stale resize validates even after identity exhaustion", [=]() mutable {
        auto stale = before_resize;
        __au_runtime_bytes_resize(&stale, -1);
    });
    __au_runtime_bytes_allocate(last_region.id(), 0, &failed);
    require_failed(failed, last_region);
    require(last_region.metrics() == metrics && trace.calls == calls, "exhausted IDs never wrap or allocate");
    require(__au_runtime_bytes_at(&final_owner, 0) == 233, "ID exhaustion leaves existing bytes unchanged");
    __au_runtime_bytes_drop(&failed);
    __au_runtime_bytes_drop(&final_owner);
    __au_runtime_bytes_drop(&final_empty);
    __au_runtime_bytes_allocate(last_region.id(), 0, &failed);
    require_failed(failed, last_region);
    require(trace.calls == calls, "released final ID is never reused");
    __au_runtime_bytes_drop(&failed);
    require(last_region.close(), "final region still closes after ID exhaustion");
    invariant("exhausted region IDs fail-stop", [] {
        Region impossible(0);
    });
    invariant("test seam cannot revive exhausted IDs", [] {
        testing::advance_next_ids(std::numeric_limits<std::uint64_t>::max(), std::numeric_limits<std::uint64_t>::max());
    });
}
#endif

void typed_value_storage() {
    AllocationTrace trace;
    Region region(20000, Allocator{&trace, AllocationTrace::allocate, AllocationTrace::deallocate});
    std::array<unsigned char, 24> fill{}, replacement{}, output{};
    for (std::size_t byte = 0; byte < fill.size(); ++byte) {
        fill[byte] = static_cast<unsigned char>(byte + 1);
        replacement[byte] = static_cast<unsigned char>(200 - byte);
    }
    NativeOwner owner;
    __au_runtime_values_allocate(region.id(), 200, 24, fill.data(), &owner);
    require_live(owner, region, 4800);
    __au_runtime_values_at(&owner, 170, 24, output.data());
    require(output == fill, "typed allocation fills every complete element beyond fixed-array bounds");
    require(__au_runtime_values_set(&owner, 170, 24, replacement.data()) == 1, "typed copied set succeeds");
    require(__au_runtime_values_set(&owner, -1, 24, fill.data()) == 0 &&
                __au_runtime_values_set(&owner, 200, 24, fill.data()) == 0,
            "typed copied set checks signed and upper bounds");
    const auto before = owner;
    const auto metrics = region.metrics();
    trace.fail_next = true;
    require(__au_runtime_values_resize(&owner, 300, 24, fill.data()) == 0 && same_owner(owner, before) &&
                region.metrics() == metrics,
            "typed replacement host failure preserves descriptor and accounting");
    __au_runtime_values_at(&owner, 170, 24, output.data());
    require(output == replacement, "typed replacement failure preserves complete payload");
    require(__au_runtime_values_resize(&owner, std::numeric_limits<std::int64_t>::max(), 24, fill.data()) == 0 &&
                same_owner(owner, before) && region.metrics() == metrics,
            "typed count multiplication overflow is rejected before allocation");
    require(__au_runtime_values_resize(&owner, 171, 24, fill.data()) == 1, "typed shrink succeeds");
    require(__au_runtime_values_resize(&owner, 220, 24, replacement.data()) == 1, "typed regrow succeeds");
    __au_runtime_values_at(&owner, 169, 24, output.data());
    require(output == fill, "typed resize preserves retained prefix");
    __au_runtime_values_at(&owner, 219, 24, output.data());
    require(output == replacement, "typed regrow fills the complete new suffix explicitly");
    const auto current = owner;
    const auto same_metrics = region.metrics();
    require(__au_runtime_values_resize(&owner, 220, 24, fill.data()) == 1 && same_owner(owner, current) &&
                region.metrics() == same_metrics,
            "same typed count does not replace or refill");
    invariant("typed storage rejects wrong stride", [&] {
        __au_runtime_values_at(&owner, 0, 23, output.data());
    });
    invariant("typed storage rejects zero stride", [&] {
        __au_runtime_values_resize(&owner, 0, 0, fill.data());
    });
    __au_runtime_bytes_drop(&owner);
    require(output == replacement, "copied value remains independent after owner drop");
    __au_runtime_values_allocate(region.id(), 0, 8, fill.data(), &owner);
    require_live(owner, region, 0);
    __au_runtime_bytes_drop(&owner);
    __au_runtime_values_allocate(region.id(), -1, 24, fill.data(), &owner);
    require_failed(owner, region);
    require(__au_runtime_values_resize(&owner, 0, 24, fill.data()) == 0,
            "failed typed owner remains inert even for empty resize");
    __au_runtime_bytes_drop(&owner);
    require(region.close(), "typed owners release all shared byte-region allocations");
}

#if defined(AURORA_HOSTED_BYTES_TESTING)
void readonly_metadata_observations() {
    AllocationTrace trace;
    Region region(256, trace.allocator()), other(0);
    NativeOwner owner;
    const std::array<std::int64_t, 3> fill{11, 22, 33};
    __au_runtime_values_allocate(region.id(), 2, sizeof(fill), fill.data(), &owner);
    const auto descriptor = owner;
    const auto metrics = region.metrics();
    const auto calls = trace.calls, frees = trace.frees;
    std::array<std::int64_t, 3> copied{};
    {
        const auto bytes = testing::MetadataObservation::bytes(region, owner);
        static_assert(std::is_same_v<decltype(bytes)::element_type, const std::byte>);
        require(bytes.size() == 2 * sizeof(fill), "metadata observation covers exact live byte extent");
        std::memcpy(copied.data(), bytes.data() + sizeof(fill), sizeof(copied));
        require(copied == fill, "metadata observation supports copied rows without typed payload aliasing");
        const auto snapshot = testing::MetadataObservation::bytes(region, descriptor);
        require(snapshot.data() == bytes.data() && snapshot.size() == bytes.size(),
                "readonly descriptor observation identifies the same backing without another owner");
        require(same_owner(owner, descriptor) && region.metrics() == metrics && trace.calls == calls &&
                    trace.frees == frees,
                "metadata observation neither mutates descriptors/accounting nor calls an allocator");
    } // Destroy every byte view before any mutation or consuming cleanup.
    invariant("metadata observation requires its exact Region", [&] {
        testing::MetadataObservation::bytes(other, owner);
    });
    for (int field = 0; field < 4; ++field) {
        invariant("metadata observation rejects forged descriptor words", [&] {
            auto forged = owner;
            if (field == 0)
                forged.region = other.id();
            if (field == 1)
                forged.allocation = 0;
            if (field == 2)
                ++forged.length;
            if (field == 3)
                forged.success = 2;
            testing::MetadataObservation::bytes(region, forged);
        });
    }
    __au_runtime_bytes_drop(&owner);
    require(copied == fill && trace.frees == frees + 1 && region.metrics().live_allocations == 0,
            "copied metadata rows survive the single owner release");
    invariant("metadata observation rejects a released descriptor", [&] {
        testing::MetadataObservation::bytes(region, descriptor);
    });
    __au_runtime_values_allocate(region.id(), 0, sizeof(fill), fill.data(), &owner);
    {
        const auto empty = testing::MetadataObservation::bytes(region, owner);
        require(empty.empty() && owner.success == 1 && region.metrics().live_allocations == 1,
                "successful empty metadata pool is validated as a live owner");
    }
    const auto beforeResize = owner;
    require(__au_runtime_values_resize(&owner, 1, sizeof(fill), fill.data()) == 1,
            "prepare a replaced descriptor before new metadata observation");
    invariant("metadata observation rejects a descriptor stale after resize", [&] {
        testing::MetadataObservation::bytes(region, beforeResize);
    });
    __au_runtime_bytes_drop(&owner);
    __au_runtime_values_allocate(region.id(), -1, sizeof(fill), fill.data(), &owner);
    bounds("metadata observation rejects failed owner even with zero byte length", [&] {
        testing::MetadataObservation::bytes(region, owner);
    });
    __au_runtime_bytes_drop(&owner);
    require(region.close(), "metadata views leave no extra release obligation");
    invariant("metadata observation rejects a closed Region", [&] {
        testing::MetadataObservation::bytes(region, descriptor);
    });
}
#endif

} // namespace

// The owner lookup cache is direct-mapped by allocation ID. Colliding, dropped,
// replaced and foreign-region owners must behave exactly like the registry walk.
// Freed records keep their bytes, so a stale cache entry would still match its ID.
struct Quarantine {
    std::array<void *, 256> retired{};
    std::size_t count = 0;
    static void *allocate(void *, std::size_t size) noexcept {
        return std::malloc(size);
    }
    static void deallocate(void *context, void *address) noexcept {
        auto &self = *static_cast<Quarantine *>(context);
        require(self.count < self.retired.size(), "quarantine capacity");
        self.retired[self.count++] = address;
    }
    ~Quarantine() {
        for (std::size_t index = 0; index < count; ++index) {
            std::free(retired[index]);
        }
    }
};

void owner_lookup_cache_identity() {
    constexpr std::size_t count = 130; // more than two full cache rounds
    Quarantine quarantine;
    Region region(4096, Allocator{&quarantine, Quarantine::allocate, Quarantine::deallocate});
    std::array<NativeOwner, count> owners{};
    for (std::size_t index = 0; index < count; ++index) {
        __au_runtime_bytes_allocate(region.id(), 2, &owners[index]);
        require_live(owners[index], region, 2);
        require(__au_runtime_bytes_set(&owners[index], 1, index & 0xff) == 1, "write colliding owner");
    }
    require(owners[64].allocation == owners[0].allocation + 64, "fixture owners collide in one cache slot");
    for (int pass = 0; pass < 3; ++pass) {
        for (std::size_t step = 0; step < count; ++step) {
            const std::size_t index = pass == 1 ? count - 1 - step : (step * 67) % count;
            require(__au_runtime_bytes_at(&owners[index], 1) == (index & 0xff), "colliding owner reads its own bytes");
        }
    }
    const NativeOwner dropped = owners[3];
    require(__au_runtime_bytes_at(&owners[3], 1) == 3, "cache the owner about to be dropped");
    __au_runtime_bytes_drop(&owners[3]);
    invariant("cached dropped owner", [dropped] {
        __au_runtime_bytes_at(&dropped, 1);
    });
    require(__au_runtime_bytes_at(&owners[67], 1) == 67, "same-slot owner survives a drop");
    const NativeOwner replaced = owners[5];
    require(__au_runtime_bytes_at(&owners[5], 1) == 5, "cache the owner about to be replaced");
    require(__au_runtime_bytes_resize(&owners[5], 3) == 1, "resize cached owner");
    require(owners[5].allocation != replaced.allocation && __au_runtime_bytes_at(&owners[5], 1) == 5,
            "replacement keeps bytes under a fresh identity");
    invariant("cached replaced owner", [replaced] {
        __au_runtime_bytes_at(&replaced, 1);
    });
    {
        Region other(64, Allocator{&quarantine, Quarantine::allocate, Quarantine::deallocate});
        NativeOwner foreign;
        __au_runtime_bytes_allocate(other.id(), 1, &foreign);
        for (int round = 0; round < 4; ++round) {
            require(__au_runtime_bytes_at(&owners[7], 1) == 7, "alternate regions: first");
            require(__au_runtime_bytes_at(&foreign, 0) == 0, "alternate regions: second");
        }
        const NativeOwner relabeled{region.id(), foreign.allocation, foreign.length, 1};
        invariant("other region's cached ID under this region", [relabeled] {
            __au_runtime_bytes_at(&relabeled, 0);
        });
        const NativeOwner stale = foreign;
        __au_runtime_bytes_drop(&foreign);
        require(other.close(), "close the cached region after its last owner");
        invariant("owner of a closed cached region", [stale] {
            __au_runtime_bytes_at(&stale, 0);
        });
    }
    for (auto &owner : owners) {
        __au_runtime_bytes_drop(&owner);
    }
    require(region.close(), "close after every cached owner is dropped");
    std::puts("PASS owned bytes host: owner lookup cache matches registry identity");
}

int main() {
    owner_lookup_cache_identity();
    typed_value_storage();
    readonly_descriptor_snapshots(__au_runtime_bytes_borrow_length);
    readonly_descriptor_snapshots(checked_span);
    invariant("span null result storage", [] {
        Region region(1);
        NativeOwner owner;
        __au_runtime_bytes_allocate(region.id(), 1, &owner);
        __au_runtime_bytes_borrow_span(&owner, nullptr);
    });
    runtime_lengths_and_initialization();
    failure_atomicity_and_quota_reuse();
    resize_replacement_and_preservation();
    resize_failure_atomicity();
    resize_descriptor_validation();
    region_lifetime_and_failures();
#if defined(AURORA_HOSTED_BYTES_TESTING)
    readonly_metadata_observations();
    nonwrapping_identity_limits();
#else
    std::puts("NOTE owned bytes host: overflow seam disabled; no ID-overflow execution claimed");
#endif
    std::printf("PASS owned bytes host: %llu checks, %llu isolated fail-stop traps\n",
                static_cast<unsigned long long>(checks),
                static_cast<unsigned long long>(traps));
    return 0;
}
