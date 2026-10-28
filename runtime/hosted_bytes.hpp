#pragma once

#include "bytes_abi.hpp"

// Trusted single-threaded host machinery only. This is not an Aurora source API,
// a user-process runtime, a kernel allocator, or a public foreign-call boundary.
namespace aurora::hosted::bytes {

// A trusted test host may replace the matched allocation/deallocation pair.
// allocate must return nullptr or fresh malloc-aligned storage of at least size
// bytes; deallocate must accept that exact base once. Context outlives Region.
// Neither callback may throw, reenter the adapter, or retain/access freed storage.
struct Allocator {
    void *context;
    void *(*allocate)(void *context, std::size_t size) noexcept;
    void (*deallocate)(void *context, void *address) noexcept;
};

Allocator system_allocator() noexcept;

// Copied observations for the trusted bridge. Metadata is outside payload quota.
struct Metrics {
    std::uint64_t quota = 0;
    std::uint64_t used = 0;
    std::uint64_t live_allocations = 0;
    std::uint64_t successful_allocations = 0;
    std::uint64_t releases = 0;
    std::uint64_t peak_live_allocations = 0;
    std::uint64_t peak_used = 0;
    std::uint64_t last_allocation_id = 0;
    std::uint64_t last_released_id = 0;

    bool operator==(const Metrics &) const = default;
};

class RuntimeAccess;

class Region final {
public:
    explicit Region(std::uint64_t payload_quota, Allocator allocator = system_allocator()) noexcept;
    ~Region() noexcept;

    Region(const Region &) = delete;
    Region &operator=(const Region &) = delete;
    Region(Region &&) = delete;
    Region &operator=(Region &&) = delete;

    std::uint64_t id() const noexcept;
    Metrics metrics() const noexcept;
    bool is_open() const noexcept;

    // Refusal leaves the grant and every live owner unchanged. Repeated close of
    // an already closed region succeeds. A destructor cannot silently leak owners.
    bool close() noexcept;

private:
    struct Allocation;

    friend class RuntimeAccess;

    std::uint64_t id_;
    bool open_;
    Allocator allocator_;
    Metrics metrics_;
    Allocation *allocations_;
    // Direct-mapped by allocation ID. Holds only live records of this region:
    // every unlink clears its slot first, and IDs are never reused.
    Allocation *recent_[64]{};
    Region *next_;
};

// Faults are fail-stop: diagnostic "aurora owned bytes: invariant" or
// "aurora owned bytes: bounds", then abort(). They never unwind generated frames.
// Host tests observe both the marker and SIGABRT in an isolated child process.
// Host pointers below are trusted valid descriptor storage, not language pointers.
// Native uniqueness is enforced by source/IR ownership checks; copying a live
// descriptor in malicious trusted C++ is outside this adapter's guarantee.
// A readonly contiguous span is valid only while its owner remains live and
// unchanged. Admitted Aurora source/IR enforces that lifetime; trusted native
// code must not mutate, resize, move or drop its source behind a live span.

#if defined(AURORA_HOSTED_BYTES_TESTING)
namespace testing {
// Isolated overflow gate only. Can skip forward, never rewind or revive IDs.
// Requires no open region. Compile both adapter and host test with the same macro.
void advance_next_ids(std::uint64_t region, std::uint64_t allocation) noexcept;
} // namespace testing
#endif

} // namespace aurora::hosted::bytes
