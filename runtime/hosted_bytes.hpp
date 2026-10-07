#pragma once

#include <cstddef>
#include <cstdint>
#include <type_traits>

// Trusted single-threaded host machinery only. This is not an Aurora source API,
// a user-process runtime, a kernel allocator, or a public foreign-call boundary.
namespace aurora::hosted::bytes {

// Generated code reserves an opaque 32-byte slot. Only this trusted adapter and
// the compiler's private lowering may interpret it; no payload address is stored.
struct alignas(8) NativeOwner {
    std::uint64_t region = 0;
    std::uint64_t allocation = 0;
    std::int64_t length = 0;
    std::uint64_t success = 0;
};

static_assert(std::is_standard_layout_v<NativeOwner>);
static_assert(std::is_trivially_copyable_v<NativeOwner>);
static_assert(sizeof(NativeOwner) == 32 && alignof(NativeOwner) == 8);
static_assert(offsetof(NativeOwner, region) == 0 && offsetof(NativeOwner, allocation) == 8);
static_assert(offsetof(NativeOwner, length) == 16 && offsetof(NativeOwner, success) == 24);

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
    Region *next_;
};

// Faults are fail-stop: diagnostic "aurora owned bytes: invariant" or
// "aurora owned bytes: bounds", then abort(). They never unwind generated frames.
// Host tests observe both the marker and SIGABRT in an isolated child process.
// Host pointers below are trusted valid descriptor storage, not language pointers.
// Native uniqueness is enforced by source/IR ownership checks; copying a live
// descriptor in malicious trusted C++ is outside this adapter's guarantee.
extern "C" {
void __au_runtime_bytes_allocate(std::uint64_t region, std::int64_t length, NativeOwner *output) noexcept;
std::uint64_t __au_runtime_bytes_at(const NativeOwner *owner, std::int64_t index) noexcept;
std::uint64_t __au_runtime_bytes_set(NativeOwner *owner, std::int64_t index, std::uint64_t value) noexcept;
std::uint64_t __au_runtime_bytes_resize(NativeOwner *owner, std::int64_t length) noexcept;
void __au_runtime_bytes_drop(NativeOwner *owner) noexcept;
}

#if defined(AURORA_HOSTED_BYTES_TESTING)
namespace testing {
// Isolated overflow gate only. Can skip forward, never rewind or revive IDs.
// Requires no open region. Compile both adapter and host test with the same macro.
void advance_next_ids(std::uint64_t region, std::uint64_t allocation) noexcept;
} // namespace testing
#endif

} // namespace aurora::hosted::bytes
