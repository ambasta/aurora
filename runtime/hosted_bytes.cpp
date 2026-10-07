#include "hosted_bytes.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>

namespace aurora::hosted::bytes {

namespace {

Region *first_region = nullptr;
std::uint64_t next_region_id = 1;
std::uint64_t next_allocation_id = 1;
bool region_ids_exhausted = false;
bool allocation_ids_exhausted = false;

[[noreturn]] void invariant_trap() noexcept {
    std::fputs("aurora owned bytes: invariant\n", stderr);
    std::fflush(stderr);
    std::abort();
}

[[noreturn]] void bounds_trap() noexcept {
    std::fputs("aurora owned bytes: bounds\n", stderr);
    std::fflush(stderr);
    std::abort();
}

void *system_allocate(void *, std::size_t size) noexcept {
    return std::malloc(size);
}

void system_deallocate(void *, void *address) noexcept {
    std::free(address);
}

bool pristine(const NativeOwner &owner) noexcept {
    return owner.region == 0 && owner.allocation == 0 && owner.length == 0 && owner.success == 0;
}

void commit_id(std::uint64_t &next, bool &exhausted) noexcept {
    if (next == std::numeric_limits<std::uint64_t>::max()) {
        exhausted = true;
    } else {
        ++next;
    }
}

} // namespace

struct Region::Allocation {
    std::uint64_t id;
    std::int64_t length;
    unsigned char *payload;
    Allocation *next;
};

// All payload addresses and registry traversal stay inside this adapter. An ID
// is looked up before any descriptor-derived offset or allocation is touched.
class RuntimeAccess {
public:
    static Region &region(std::uint64_t id) noexcept {
        for (Region *current = first_region; current != nullptr; current = current->next_) {
            if (current->id_ == id) {
                return *current;
            }
        }
        invariant_trap();
    }

    static Region::Allocation *allocation(const NativeOwner *owner, Region *&found_region) noexcept {
        if (owner == nullptr) {
            invariant_trap();
        }
        found_region = &region(owner->region);
        if (owner->success == 0) {
            if (owner->allocation != 0 || owner->length != 0) {
                invariant_trap();
            }
            return nullptr;
        }
        if (owner->success != 1 || owner->allocation == 0 || owner->length < 0) {
            invariant_trap();
        }
        for (auto *current = found_region->allocations_; current != nullptr; current = current->next) {
            if (current->id == owner->allocation) {
                if (current->length != owner->length) {
                    invariant_trap();
                }
                return current;
            }
        }
        invariant_trap();
    }

    static void allocate(std::uint64_t id, std::int64_t length, NativeOwner *output) noexcept {
        if (output == nullptr || !pristine(*output)) {
            invariant_trap();
        }
        Region &target = region(id);
        *output = NativeOwner{id, 0, 0, 0};
        if (length < 0 || allocation_ids_exhausted) {
            return;
        }
        const auto count = static_cast<std::uint64_t>(length);
        if (count > std::numeric_limits<std::size_t>::max() - sizeof(Region::Allocation) ||
            count > target.metrics_.quota - target.metrics_.used ||
            target.metrics_.live_allocations == std::numeric_limits<std::uint64_t>::max()) {
            return;
        }

        const auto size = sizeof(Region::Allocation) + static_cast<std::size_t>(count);
        void *memory = target.allocator_.allocate(target.allocator_.context, size);
        if (memory == nullptr) {
            return;
        }

        // A zero-length owner still owns this real, unique metadata allocation.
        // Placement construction and zeroing are nonthrowing. No identity,
        // registry entry, quota or observation commits before allocation succeeds.
        auto *payload = static_cast<unsigned char *>(memory) + sizeof(Region::Allocation);
        auto *record = ::new (memory) Region::Allocation{next_allocation_id, length, payload, target.allocations_};
        std::memset(record->payload, 0, static_cast<std::size_t>(count));
        target.allocations_ = record;
        target.metrics_.used += count;
        ++target.metrics_.live_allocations;
        ++target.metrics_.successful_allocations;
        if (target.metrics_.used > target.metrics_.peak_used) {
            target.metrics_.peak_used = target.metrics_.used;
        }
        if (target.metrics_.live_allocations > target.metrics_.peak_live_allocations) {
            target.metrics_.peak_live_allocations = target.metrics_.live_allocations;
        }
        target.metrics_.last_allocation_id = record->id;
        commit_id(next_allocation_id, allocation_ids_exhausted);
        *output = NativeOwner{id, record->id, length, 1};
    }

    static std::uint64_t at(const NativeOwner *owner, std::int64_t index) noexcept {
        Region *target = nullptr;
        const auto *record = allocation(owner, target);
        if (record == nullptr || index < 0 || index >= record->length) {
            bounds_trap();
        }
        return record->payload[static_cast<std::size_t>(index)];
    }

    static std::uint64_t set(NativeOwner *owner, std::int64_t index, std::uint64_t value) noexcept {
        Region *target = nullptr;
        auto *record = allocation(owner, target);
        if (value > 255) {
            invariant_trap();
        }
        if (record == nullptr || index < 0 || index >= record->length) {
            return 0;
        }
        record->payload[static_cast<std::size_t>(index)] = static_cast<unsigned char>(value);
        return 1;
    }

    static void drop(NativeOwner *owner) noexcept {
        if (owner == nullptr) {
            invariant_trap();
        }
        if (pristine(*owner)) {
            return;
        }
        Region *target = nullptr;
        auto *record = allocation(owner, target);
        if (record == nullptr) {
            *owner = NativeOwner{};
            return;
        }
        auto **link = &target->allocations_;
        while (*link != record) {
            link = &(*link)->next;
        }
        *link = record->next;
        target->metrics_.used -= static_cast<std::uint64_t>(record->length);
        --target->metrics_.live_allocations;
        ++target->metrics_.releases;
        target->metrics_.last_released_id = record->id;
        *owner = NativeOwner{};
        record->~Allocation();
        target->allocator_.deallocate(target->allocator_.context, record);
    }
};

Allocator system_allocator() noexcept {
    return Allocator{nullptr, system_allocate, system_deallocate};
}

Region::Region(std::uint64_t payload_quota, Allocator allocator) noexcept
    : id_(0), open_(false), allocator_(allocator), metrics_{}, allocations_(nullptr), next_(nullptr) {
    if (allocator_.allocate == nullptr || allocator_.deallocate == nullptr || region_ids_exhausted) {
        invariant_trap();
    }
    id_ = next_region_id;
    commit_id(next_region_id, region_ids_exhausted);
    metrics_.quota = payload_quota;
    next_ = first_region;
    first_region = this;
    open_ = true;
}

Region::~Region() noexcept {
    if (!close()) {
        invariant_trap();
    }
}

std::uint64_t Region::id() const noexcept {
    return id_;
}

Metrics Region::metrics() const noexcept {
    return metrics_;
}

bool Region::is_open() const noexcept {
    return open_;
}

bool Region::close() noexcept {
    if (!open_) {
        return true;
    }
    if (allocations_ != nullptr) {
        return false;
    }
    Region **link = &first_region;
    while (*link != this) {
        if (*link == nullptr) {
            invariant_trap();
        }
        link = &(*link)->next_;
    }
    *link = next_;
    next_ = nullptr;
    open_ = false;
    return true;
}

extern "C" void __au_runtime_bytes_allocate(std::uint64_t region, std::int64_t length, NativeOwner *output) noexcept {
    RuntimeAccess::allocate(region, length, output);
}

extern "C" std::uint64_t __au_runtime_bytes_at(const NativeOwner *owner, std::int64_t index) noexcept {
    return RuntimeAccess::at(owner, index);
}

extern "C" std::uint64_t __au_runtime_bytes_set(NativeOwner *owner, std::int64_t index, std::uint64_t value) noexcept {
    return RuntimeAccess::set(owner, index, value);
}

extern "C" void __au_runtime_bytes_drop(NativeOwner *owner) noexcept {
    RuntimeAccess::drop(owner);
}

#if defined(AURORA_HOSTED_BYTES_TESTING)
namespace testing {

void advance_next_ids(std::uint64_t region, std::uint64_t allocation) noexcept {
    if (first_region != nullptr || region_ids_exhausted || allocation_ids_exhausted || region < next_region_id ||
        allocation < next_allocation_id) {
        invariant_trap();
    }
    next_region_id = region;
    next_allocation_id = allocation;
}

} // namespace testing
#endif

} // namespace aurora::hosted::bytes
