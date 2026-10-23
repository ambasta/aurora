#include "hosted_bytes.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <limits>
#include <new>

namespace aurora::hosted::bytes {

namespace {

Region *first_region = nullptr;
Region *last_region = nullptr; // open and linked whenever non-null
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

// Payload ownership and registry traversal stay inside this adapter. An ID is
// checked before accessing any allocation, including the sealed metadata view.
class RuntimeAccess {
public:
    static Region &region(std::uint64_t id) noexcept {
        if (last_region != nullptr && last_region->id_ == id) {
            return *last_region;
        }
        for (Region *current = first_region; current != nullptr; current = current->next_) {
            if (current->id_ == id) {
                last_region = current;
                return *current;
            }
        }
        invariant_trap();
    }

    static Region::Allocation *&recent(Region &region, std::uint64_t id) noexcept {
        return region.recent_[id % std::size(region.recent_)];
    }

    // Call before a record leaves the registry, so the cache never names freed memory.
    static void forget(Region &region, const Region::Allocation *record) noexcept {
        auto *&slot = recent(region, record->id);
        if (slot == record) {
            slot = nullptr;
        }
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
        // IDs are unique and the cache holds only live records of this region, so
        // a matching cached record is exactly the one the registry walk would find.
        auto *&slot = recent(*found_region, owner->allocation);
        auto *record = slot;
        if (record == nullptr || record->id != owner->allocation) {
            record = found_region->allocations_;
            while (record != nullptr && record->id != owner->allocation) {
                record = record->next;
            }
            if (record == nullptr) {
                invariant_trap();
            }
            slot = record;
        }
        if (record->length != owner->length) {
            invariant_trap();
        }
        return record;
    }

    static void allocate(std::uint64_t id,
                         std::int64_t length,
                         NativeOwner *output,
                         const unsigned char *fill = nullptr,
                         std::int64_t stride = 1) noexcept {
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
        if (fill != nullptr) {
            for (std::size_t offset = 0; offset < count; offset += static_cast<std::size_t>(stride))
                std::memcpy(record->payload + offset, fill, static_cast<std::size_t>(stride));
        } else
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

    static std::int64_t borrow_length(const NativeOwner *owner) noexcept {
        Region *target = nullptr;
        const auto *record = allocation(owner, target);
        if (record == nullptr) {
            bounds_trap();
        }
        return record->length;
    }

    static void borrow_span(const NativeOwner *owner, NativeSpan *output) noexcept {
        Region *target = nullptr;
        const auto *record = allocation(owner, target);
        if (record == nullptr) {
            bounds_trap();
        }
        if (output == nullptr) {
            invariant_trap();
        }
        // This trusted adapter is single-threaded. Admitted source/IR forbids
        // resize, mutation, move or destruction of the root while a view lives.
        // No pointer is exposed to Aurora source or to protected processes.
        *output = NativeSpan{0, {reinterpret_cast<std::uintptr_t>(record->payload), 0, 0, 0}, 0, record->length};
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

    static std::uint64_t resize(NativeOwner *owner,
                                std::int64_t length,
                                const unsigned char *fill = nullptr,
                                std::int64_t stride = 1) noexcept {
        Region *target = nullptr;
        auto *record = allocation(owner, target);
        // Validate even same-size and invalid requests. A canonical failed
        // owner is never revived, including by an empty request.
        if (record == nullptr || length < 0) {
            return 0;
        }
        if (length == record->length) {
            return 1;
        }
        const auto count = static_cast<std::uint64_t>(length);
        const auto old_count = static_cast<std::uint64_t>(record->length);
        const auto other_used = target->metrics_.used - old_count;
        if (allocation_ids_exhausted || count > std::numeric_limits<std::size_t>::max() - sizeof(Region::Allocation) ||
            count > target->metrics_.quota - other_used ||
            target->metrics_.successful_allocations == std::numeric_limits<std::uint64_t>::max() ||
            target->metrics_.releases == std::numeric_limits<std::uint64_t>::max()) {
            return 0;
        }

        auto **link = &target->allocations_;
        while (*link != record) {
            link = &(*link)->next;
        }
        const auto size = sizeof(Region::Allocation) + static_cast<std::size_t>(count);
        void *memory = target->allocator_.allocate(target->allocator_.context, size);
        if (memory == nullptr) {
            return 0;
        }
        auto *payload = static_cast<unsigned char *>(memory) + sizeof(Region::Allocation);
        auto *replacement = ::new (memory) Region::Allocation{next_allocation_id, length, payload, record->next};
        const auto prefix = static_cast<std::size_t>(count < old_count ? count : old_count);
        std::memcpy(replacement->payload, record->payload, prefix);
        if (fill != nullptr) {
            for (std::size_t offset = prefix; offset < count; offset += static_cast<std::size_t>(stride))
                std::memcpy(replacement->payload + offset, fill, static_cast<std::size_t>(stride));
        } else
            std::memset(replacement->payload + prefix, 0, static_cast<std::size_t>(count) - prefix);

        // One allocation owns both metadata and bytes. All fallible work is
        // over: commit final logical quota, fresh identity and replacement as
        // one nonthrowing operation, then retire the old block exactly once.
        // Old+new storage coexist transiently; payload quota is not a bound on
        // instantaneous host storage. Live-owner counts do not include staging.
        forget(*target, record);
        *link = replacement;
        target->metrics_.used = other_used + count;
        ++target->metrics_.successful_allocations;
        ++target->metrics_.releases;
        if (target->metrics_.used > target->metrics_.peak_used) {
            target->metrics_.peak_used = target->metrics_.used;
        }
        target->metrics_.last_allocation_id = replacement->id;
        target->metrics_.last_released_id = record->id;
        commit_id(next_allocation_id, allocation_ids_exhausted);
        *owner = NativeOwner{target->id_, replacement->id, length, 1};
        record->~Allocation();
        target->allocator_.deallocate(target->allocator_.context, record);
        return 1;
    }

    static void allocate_values(
        std::uint64_t id, std::int64_t count, std::int64_t stride, const void *fill, NativeOwner *output) noexcept {
        if (!valid_value_stride(stride) || fill == nullptr)
            invariant_trap();
        allocate(id, value_byte_length(count, stride), output, static_cast<const unsigned char *>(fill), stride);
    }

    static Region::Allocation *
    value_allocation(const NativeOwner *owner, std::int64_t stride, Region *&target) noexcept {
        auto *record = allocation(owner, target);
        if (!valid_value_stride(stride) || owner->length % stride != 0)
            invariant_trap();
        return record;
    }

    static void values_at(const NativeOwner *owner, std::int64_t index, std::int64_t stride, void *output) noexcept {
        Region *target = nullptr;
        auto *record = value_allocation(owner, stride, target);
        if (output == nullptr)
            invariant_trap();
        if (record == nullptr || index < 0 || index >= record->length / stride)
            bounds_trap();
        const auto begin = static_cast<std::size_t>(index * stride);
        std::memcpy(output, record->payload + begin, static_cast<std::size_t>(stride));
    }

    static std::uint64_t
    values_set(NativeOwner *owner, std::int64_t index, std::int64_t stride, const void *value) noexcept {
        Region *target = nullptr;
        auto *record = value_allocation(owner, stride, target);
        if (value == nullptr)
            invariant_trap();
        if (record == nullptr || index < 0 || index >= record->length / stride)
            return 0;
        const auto begin = static_cast<std::size_t>(index * stride);
        std::memcpy(record->payload + begin, value, static_cast<std::size_t>(stride));
        return 1;
    }

    static std::uint64_t
    resize_values(NativeOwner *owner, std::int64_t count, std::int64_t stride, const void *fill) noexcept {
        Region *target = nullptr;
        value_allocation(owner, stride, target); // validate even an invalid request
        if (fill == nullptr)
            invariant_trap();
        return resize(owner, value_byte_length(count, stride), static_cast<const unsigned char *>(fill), stride);
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
        forget(*target, record);
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

std::span<const std::byte> Region::observeMetadataBytes(const NativeOwner &owner) const noexcept {
    if (!open_ || owner.region != id_) {
        invariant_trap();
    }
    Region *target = nullptr;
    const auto *record = RuntimeAccess::allocation(&owner, target);
    if (record == nullptr) {
        bounds_trap();
    }
    return {reinterpret_cast<const std::byte *>(record->payload), static_cast<std::size_t>(record->length)};
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
    if (last_region == this) {
        last_region = nullptr;
    }
    return true;
}

extern "C" void __au_runtime_values_allocate(
    std::uint64_t region, std::int64_t count, std::int64_t stride, const void *fill, NativeOwner *output) noexcept {
    RuntimeAccess::allocate_values(region, count, stride, fill, output);
}
extern "C" void
__au_runtime_values_at(const NativeOwner *owner, std::int64_t index, std::int64_t stride, void *output) noexcept {
    RuntimeAccess::values_at(owner, index, stride, output);
}
extern "C" std::uint64_t
__au_runtime_values_set(NativeOwner *owner, std::int64_t index, std::int64_t stride, const void *value) noexcept {
    return RuntimeAccess::values_set(owner, index, stride, value);
}
extern "C" std::uint64_t
__au_runtime_values_resize(NativeOwner *owner, std::int64_t count, std::int64_t stride, const void *fill) noexcept {
    return RuntimeAccess::resize_values(owner, count, stride, fill);
}

extern "C" void __au_runtime_bytes_allocate(std::uint64_t region, std::int64_t length, NativeOwner *output) noexcept {
    RuntimeAccess::allocate(region, length, output);
}

extern "C" std::int64_t __au_runtime_bytes_borrow_length(const NativeOwner *owner) noexcept {
    return RuntimeAccess::borrow_length(owner);
}

extern "C" void __au_runtime_bytes_borrow_span(const NativeOwner *owner, NativeSpan *output) noexcept {
    RuntimeAccess::borrow_span(owner, output);
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

extern "C" std::uint64_t __au_runtime_bytes_resize(NativeOwner *owner, std::int64_t length) noexcept {
    return RuntimeAccess::resize(owner, length);
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
