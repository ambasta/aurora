// Isolated trusted-host adapter gate. Generated Aurora code is not instrumented
// by this test's sanitizers. Run only after the completed-source review gate.
#include "../../runtime/hosted_bytes.hpp"

#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <limits>
#include <sys/resource.h>
#include <sys/wait.h>
#include <type_traits>
#include <unistd.h>

using namespace aurora::hosted::bytes;

static_assert(!std::is_copy_constructible_v<Region> && !std::is_copy_assignable_v<Region>);
static_assert(!std::is_move_constructible_v<Region> && !std::is_move_assignable_v<Region>);
static_assert(std::is_nothrow_constructible_v<Region, std::uint64_t>);
static_assert(std::is_nothrow_destructible_v<Region>);
static_assert(noexcept(__au_runtime_bytes_allocate(0, 0, nullptr)));
static_assert(noexcept(__au_runtime_bytes_at(nullptr, 0)));
static_assert(noexcept(__au_runtime_bytes_set(nullptr, 0, 0)));
static_assert(noexcept(__au_runtime_bytes_drop(nullptr)));

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

void require_failed(const NativeOwner &owner, const Region &region) {
    require(owner.region == region.id() && owner.allocation == 0 && owner.length == 0 && owner.success == 0,
            "allocation failure has the exact canonical shape");
}

void require_live(const NativeOwner &owner, const Region &region, std::int64_t length) {
    require(owner.region == region.id() && owner.allocation != 0 && owner.length == length && owner.success == 1,
            "successful owner has exact authority, identity, length and success");
}

struct AllocationTrace {
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
            return nullptr;
        }
        void *result = std::malloc(size);
        if (result != nullptr) {
            ++trace.live;
            std::memset(result, 0xa5, size);
        }
        return result;
    }

    static void deallocate(void *context, void *address) noexcept {
        auto &trace = *static_cast<AllocationTrace *>(context);
        ++trace.frees;
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
        const rlimit no_core{0, 0};
        if (setrlimit(RLIMIT_CORE, &no_core) != 0) {
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
    invariant("test seam refuses identity rewind", [] {
        testing::advance_next_ids(1, 1);
    });
    testing::advance_next_ids(std::numeric_limits<std::uint64_t>::max(), std::numeric_limits<std::uint64_t>::max());
    AllocationTrace trace;
    Region last_region(2, trace.allocator());
    require(last_region.id() == std::numeric_limits<std::uint64_t>::max(), "final nonzero region ID is usable");
    NativeOwner failed;
    trace.fail_next = true;
    __au_runtime_bytes_allocate(last_region.id(), 1, &failed);
    require_failed(failed, last_region);
    __au_runtime_bytes_drop(&failed);
    NativeOwner final_owner;
    __au_runtime_bytes_allocate(last_region.id(), 1, &final_owner);
    require_live(final_owner, last_region, 1);
    require(final_owner.allocation == std::numeric_limits<std::uint64_t>::max(), "failed host request kept final ID");
    require(__au_runtime_bytes_set(&final_owner, 0, 233) == 1, "last identity can own real initialized bytes");
    const auto metrics = last_region.metrics();
    const auto calls = trace.calls;
    __au_runtime_bytes_allocate(last_region.id(), 0, &failed);
    require_failed(failed, last_region);
    require(last_region.metrics() == metrics && trace.calls == calls, "exhausted IDs never wrap or allocate");
    require(__au_runtime_bytes_at(&final_owner, 0) == 233, "ID exhaustion leaves existing bytes unchanged");
    __au_runtime_bytes_drop(&failed);
    __au_runtime_bytes_drop(&final_owner);
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

} // namespace

int main() {
    runtime_lengths_and_initialization();
    failure_atomicity_and_quota_reuse();
    region_lifetime_and_failures();
#if defined(AURORA_HOSTED_BYTES_TESTING)
    nonwrapping_identity_limits();
#else
    std::puts("NOTE owned bytes host: overflow seam disabled; no ID-overflow execution claimed");
#endif
    std::printf("PASS owned bytes host: %llu checks, %llu isolated fail-stop traps\n",
                static_cast<unsigned long long>(checks),
                static_cast<unsigned long long>(traps));
    return 0;
}
