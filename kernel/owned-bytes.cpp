#include "owned-bytes.hpp"

#include <utility>

namespace aurora::kernel::bytes {

namespace {
using hosted::bytes::NativeOwner;

constinit Region *first_region = nullptr;
constinit std::uint64_t next_region_id = 1;
constinit std::uint64_t next_allocation_id = 1;
constinit bool region_ids_exhausted = false;
constinit bool allocation_ids_exhausted = false;

bool pristine(const NativeOwner &owner) noexcept {
    return owner.region == 0 && owner.allocation == 0 && owner.length == 0 && owner.success == 0;
}

void commit_id(std::uint64_t &next, bool &exhausted) noexcept {
    if (next == UINT64_MAX) {
        exhausted = true;
    } else {
        ++next;
    }
}
} // namespace

bool Region::backing_valid() const noexcept {
    return pool_ != nullptr && backing_.data() != nullptr && backing_.size() == backing_bytes &&
           reinterpret_cast<std::uintptr_t>(backing_.data()) % page_bytes == 0 && base_ % page_bytes == 0 &&
           base_ <= UINT64_MAX - backing_bytes && pool_->arena_matches(base_, pool_pages);
}

std::optional<std::span<std::byte>> Region::page(Allocation &allocation, std::size_t index) noexcept {
    if (!backing_valid() || index >= allocation.count || !allocation.pages[index]) {
        return std::nullopt;
    }
    const auto address = pool_->address(*allocation.pages[index]);
    if (!address || *address % page_bytes != 0 || *address < base_ || *address - base_ > backing_.size() - page_bytes) {
        return std::nullopt;
    }
    return backing_.subspan(static_cast<std::size_t>(*address - base_), page_bytes);
}

bool Region::scrub(Allocation &allocation) noexcept {
    // Validate every lease before any write; verify every page before any release.
    for (std::size_t index = 0; index < allocation.count; ++index) {
        if (!page(allocation, index)) {
            return false;
        }
    }
    for (std::size_t index = 0; index < allocation.count; ++index) {
        volatile std::byte *data = page(allocation, index)->data();
        for (std::size_t offset = 0; offset < page_bytes; ++offset) {
            data[offset] = std::byte{0};
        }
#ifdef AURORA_KERNEL_BYTES_TESTING
        if (index == failed_scrub_) {
            data[page_bytes - 1] = std::byte{1};
        }
#endif
        for (std::size_t offset = 0; offset < page_bytes; ++offset) {
            if (data[offset] != std::byte{0}) {
                return false;
            }
        }
    }
    return true;
}

[[noreturn]] void Region::retain(Allocation &allocation) noexcept {
    allocation.state = State::retained;
    faulted_ = true;
    metrics_.retained_pages = 0;
    for (const auto &record : allocations_) {
        if (record.state == State::retained) {
            for (const auto &lease : record.pages) {
                if (lease) {
                    ++metrics_.retained_pages;
                }
            }
        }
    }
    __au_runtime_bytes_kernel_fault(3);
}

void Region::release_pages(Allocation &allocation) noexcept {
    if (!scrub(allocation)) {
        retain(allocation);
    }
    // No callbacks or concurrent pool mutation occur after the full preflight.
    // A failed release breaks the trusted lifetime contract: retain what remains.
    for (std::size_t index = 0; index < allocation.count; ++index) {
        if (!pool_->release(*allocation.pages[index])) {
            retain(allocation);
        }
        allocation.pages[index].reset();
        --metrics_.held_pages;
    }
    allocation.count = 0;
}

bool Region::open(memory::PhysicalPages &pool,
                  std::span<std::byte> backing,
                  std::uint64_t base,
                  std::uint64_t payload_quota) noexcept {
    if (open_ || faulted_ || metrics_.held_pages != 0 || metrics_.live_allocations != 0 || region_ids_exhausted ||
        payload_quota > backing_bytes || backing.data() == nullptr || backing.size() != backing_bytes ||
        reinterpret_cast<std::uintptr_t>(backing.data()) % page_bytes != 0 || base % page_bytes != 0 ||
        base > UINT64_MAX - backing_bytes || !pool.arena_matches(base, pool_pages)) {
        return false;
    }
    pool_ = &pool;
    backing_ = backing;
    base_ = base;
    id_ = next_region_id;
    commit_id(next_region_id, region_ids_exhausted);
    metrics_ = Metrics{};
    metrics_.quota = payload_quota;
    next_ = first_region;
    first_region = this;
    open_ = true;
    return true;
}

bool Region::close() noexcept {
    if (!open_) {
        return true;
    }
    if (faulted_ || metrics_.held_pages != 0 || metrics_.live_allocations != 0) {
        return false;
    }
    for (const auto &record : allocations_) {
        if (record.state != State::empty) {
            return false;
        }
    }
    Region **link = &first_region;
    while (*link != this) {
        if (*link == nullptr) {
            __au_runtime_bytes_kernel_fault(1);
        }
        link = &(*link)->next_;
    }
    *link = next_;
    next_ = nullptr;
    open_ = false;
    return true;
}

class RuntimeAccess {
public:
    static Region &region(std::uint64_t id) noexcept {
        for (Region *current = first_region; current != nullptr; current = current->next_) {
            if (current->id_ == id && current->open_ && !current->faulted_) {
                return *current;
            }
        }
        __au_runtime_bytes_kernel_fault(1);
    }

    static Region::Allocation *allocation(const NativeOwner *owner, Region *&target) noexcept {
        if (owner == nullptr) {
            __au_runtime_bytes_kernel_fault(1);
        }
        target = &region(owner->region);
        if (owner->success == 0) {
            if (owner->allocation != 0 || owner->length != 0) {
                __au_runtime_bytes_kernel_fault(1);
            }
            return nullptr;
        }
        if (owner->success != 1 || owner->allocation == 0 || owner->length < 0) {
            __au_runtime_bytes_kernel_fault(1);
        }
        for (auto &record : target->allocations_) {
            if (record.state == Region::State::live && record.id == owner->allocation) {
                if (record.length != owner->length) {
                    __au_runtime_bytes_kernel_fault(1);
                }
                return &record;
            }
        }
        __au_runtime_bytes_kernel_fault(1);
    }

    static void allocate(std::uint64_t id, std::int64_t length, NativeOwner *output) noexcept {
        if (output == nullptr || !pristine(*output)) {
            __au_runtime_bytes_kernel_fault(1);
        }
        Region &target = region(id);
        *output = NativeOwner{id, 0, 0, 0};
        if (length < 0 || allocation_ids_exhausted) {
            return;
        }
        const auto count = static_cast<std::uint64_t>(length);
        if (count > Region::backing_bytes || target.metrics_.used > target.metrics_.quota ||
            count > target.metrics_.quota - target.metrics_.used) {
            return;
        }
        Region::Allocation *record = nullptr;
        for (auto &candidate : target.allocations_) {
            if (candidate.state == Region::State::empty) {
                record = &candidate;
                break;
            }
        }
        if (record == nullptr) {
            return;
        }
        record->state = Region::State::preparing;
        const auto required = count / Region::page_bytes + (count % Region::page_bytes != 0 ? 1 : 0);
        while (record->count < required) {
            auto lease = target.pool_->acquire();
            if (!lease) {
                target.release_pages(*record);
                record->state = Region::State::empty;
                return;
            }
            record->pages[record->count++].emplace(std::move(*lease));
            ++target.metrics_.held_pages;
        }
        if (!target.scrub(*record)) {
            target.retain(*record);
        }
        // All fallible work precedes the ID, quota and descriptor commit. A
        // successful empty owner consumes a distinct bounded metadata slot.
        record->id = next_allocation_id;
        record->length = length;
        record->state = Region::State::live;
        target.metrics_.used += count;
        ++target.metrics_.live_allocations;
        ++target.metrics_.successful_allocations;
        if (target.metrics_.used > target.metrics_.peak_used) {
            target.metrics_.peak_used = target.metrics_.used;
        }
        if (target.metrics_.live_allocations > target.metrics_.peak_live_allocations) {
            target.metrics_.peak_live_allocations = target.metrics_.live_allocations;
        }
        if (target.metrics_.held_pages > target.metrics_.peak_held_pages) {
            target.metrics_.peak_held_pages = target.metrics_.held_pages;
        }
        target.metrics_.last_allocation_id = record->id;
        commit_id(next_allocation_id, allocation_ids_exhausted);
        *output = NativeOwner{id, record->id, length, 1};
    }

    static std::int64_t borrow_length(const NativeOwner *owner) noexcept {
        Region *target = nullptr;
        const auto *record = allocation(owner, target);
        if (record == nullptr) {
            __au_runtime_bytes_kernel_fault(2);
        }
        return record->length;
    }

    static std::uint64_t at(const NativeOwner *owner, std::int64_t index) noexcept {
        Region *target = nullptr;
        auto *record = allocation(owner, target);
        if (record == nullptr || index < 0 || index >= record->length) {
            __au_runtime_bytes_kernel_fault(2);
        }
        const auto offset = static_cast<std::size_t>(index);
        const auto page = target->page(*record, offset / Region::page_bytes);
        if (!page) {
            target->retain(*record);
        }
        return std::to_integer<std::uint64_t>((*page)[offset % Region::page_bytes]);
    }

    static std::uint64_t set(NativeOwner *owner, std::int64_t index, std::uint64_t value) noexcept {
        Region *target = nullptr;
        auto *record = allocation(owner, target);
        if (value > 255) {
            __au_runtime_bytes_kernel_fault(1);
        }
        if (record == nullptr || index < 0 || index >= record->length) {
            return 0;
        }
        const auto offset = static_cast<std::size_t>(index);
        const auto page = target->page(*record, offset / Region::page_bytes);
        if (!page) {
            target->retain(*record);
        }
        (*page)[offset % Region::page_bytes] = std::byte{static_cast<unsigned char>(value)};
        return 1;
    }

    static void drop(NativeOwner *owner) noexcept {
        if (owner == nullptr) {
            __au_runtime_bytes_kernel_fault(1);
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
        target->release_pages(*record);
        target->metrics_.used -= static_cast<std::uint64_t>(record->length);
        --target->metrics_.live_allocations;
        ++target->metrics_.releases;
        target->metrics_.last_released_id = record->id;
        record->id = 0;
        record->length = 0;
        record->state = Region::State::empty;
        *owner = NativeOwner{};
    }
};

#ifdef AURORA_KERNEL_BYTES_TESTING
namespace testing {
void advance_next_ids(std::uint64_t region, std::uint64_t allocation) noexcept {
    if (first_region != nullptr || region_ids_exhausted || allocation_ids_exhausted || region < next_region_id ||
        allocation < next_allocation_id) {
        __au_runtime_bytes_kernel_fault(1);
    }
    next_region_id = region;
    next_allocation_id = allocation;
}
} // namespace testing
#endif

} // namespace aurora::kernel::bytes

namespace aurora::hosted::bytes {
extern "C" void __au_runtime_bytes_allocate(std::uint64_t region, std::int64_t length, NativeOwner *output) noexcept {
    kernel::bytes::RuntimeAccess::allocate(region, length, output);
}

extern "C" std::int64_t __au_runtime_bytes_borrow_length(const NativeOwner *owner) noexcept {
    return kernel::bytes::RuntimeAccess::borrow_length(owner);
}

extern "C" std::uint64_t __au_runtime_bytes_at(const NativeOwner *owner, std::int64_t index) noexcept {
    return kernel::bytes::RuntimeAccess::at(owner, index);
}

extern "C" std::uint64_t __au_runtime_bytes_set(NativeOwner *owner, std::int64_t index, std::uint64_t value) noexcept {
    return kernel::bytes::RuntimeAccess::set(owner, index, value);
}

extern "C" void __au_runtime_bytes_drop(NativeOwner *owner) noexcept {
    kernel::bytes::RuntimeAccess::drop(owner);
}
} // namespace aurora::hosted::bytes
