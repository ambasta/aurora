#include "owned-bytes.hpp"

#include <utility>

namespace aurora::kernel::bytes {

namespace {
using hosted::bytes::NativeOwner;
using hosted::bytes::valid_value_stride;
using hosted::bytes::value_byte_length;

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
#ifdef AURORA_KERNEL_BYTES_TESTING
    const bool inject = scrub_skip_ == 0;
    if (scrub_skip_ != 0) {
        --scrub_skip_;
    }
#endif
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
        if (inject && index == failed_scrub_) {
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

void Region::release_pages(Allocation &allocation, Allocation *transaction_peer) noexcept {
    if (!scrub(allocation)) {
        if (transaction_peer != nullptr) {
            transaction_peer->state = State::retained;
        }
        retain(allocation);
    }
    // No callbacks or concurrent pool mutation occur after the full preflight.
    // A failed release breaks the trusted lifetime contract: retain what remains.
    for (std::size_t index = 0; index < allocation.count; ++index) {
        if (!pool_->release(*allocation.pages[index])) {
            if (transaction_peer != nullptr) {
                transaction_peer->state = State::retained;
            }
            retain(allocation);
        }
        allocation.pages[index].reset();
        --metrics_.held_pages;
    }
    allocation.count = 0;
}

void Region::release_live(Allocation &allocation) noexcept {
    release_pages(allocation);
    metrics_.used -= static_cast<std::uint64_t>(allocation.length);
    --metrics_.live_allocations;
    ++metrics_.releases;
    metrics_.last_released_id = allocation.id;
    allocation.id = 0;
    allocation.length = 0;
    allocation.state = State::empty;
}

bool Region::revoke_quiescent() noexcept {
    if (!open_)
        return !faulted_;
    if (faulted_)
        return false;
    // A synchronous operation must have completed before this boundary.
    for (const auto &record : allocations_)
        if (record.state != State::empty && record.state != State::live)
            return false;
    for (auto &record : allocations_)
        if (record.state == State::live)
            release_live(record);
    return close();
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

    static void fill_values(Region &target,
                            Region::Allocation &record,
                            std::size_t begin,
                            std::size_t end,
                            std::size_t stride,
                            const unsigned char *fill,
                            Region::Allocation *original = nullptr) noexcept {
        // Elements may cross physical page boundaries; no contiguous backing
        // pointer or unchecked element address is exported to generated code.
        while (begin < end) {
            const auto page = target.page(record, begin / Region::page_bytes);
            if (!page) {
                if (original != nullptr)
                    original->state = Region::State::retained;
                target.retain(record);
            }
            const auto page_offset = begin % Region::page_bytes;
            const auto remaining = end - begin;
            const auto available = Region::page_bytes - page_offset;
            const auto chunk = remaining < available ? remaining : available;
            for (std::size_t byte = 0; byte < chunk; ++byte)
                (*page)[page_offset + byte] = std::byte{fill[(begin + byte) % stride]};
            begin += chunk;
        }
    }

    static void allocate(std::uint64_t id,
                         std::int64_t length,
                         NativeOwner *output,
                         const unsigned char *fill = nullptr,
                         std::int64_t stride = 1) noexcept {
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
        if (fill != nullptr)
            fill_values(target, *record, 0, static_cast<std::size_t>(count), static_cast<std::size_t>(stride), fill);
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

    static std::uint64_t resize(NativeOwner *owner,
                                std::int64_t length,
                                const unsigned char *fill = nullptr,
                                std::int64_t stride = 1) noexcept {
        Region *target = nullptr;
        auto *record = allocation(owner, target);
        // Even invalid and same-size requests must validate current authority.
        if (record == nullptr || length < 0) {
            return 0;
        }
        if (length == record->length) {
            return 1;
        }
        const auto count = static_cast<std::uint64_t>(length);
        const auto old_count = static_cast<std::uint64_t>(record->length);
        if (target->metrics_.used < old_count || target->metrics_.used > target->metrics_.quota) {
            __au_runtime_bytes_kernel_fault(1);
        }
        const auto other_used = target->metrics_.used - old_count;
        if (count > Region::backing_bytes || count > target->metrics_.quota - other_used || allocation_ids_exhausted ||
            target->metrics_.successful_allocations == UINT64_MAX || target->metrics_.releases == UINT64_MAX) {
            return 0;
        }
        Region::Allocation *replacement = nullptr;
        for (auto &candidate : target->allocations_) {
            if (candidate.state == Region::State::empty) {
                replacement = &candidate;
                break;
            }
        }
        if (replacement == nullptr) {
            return 0;
        }
        // Staging is private: no ID, logical quota or live owner is published.
        // page() validates its leases without assuming committed accounting.
        replacement->state = Region::State::preparing;
        const auto required = count / Region::page_bytes + (count % Region::page_bytes != 0 ? 1 : 0);
        while (replacement->count < required) {
            auto lease = target->pool_->acquire();
            if (!lease) {
                target->release_pages(*replacement, record);
                replacement->id = 0;
                replacement->length = 0;
                replacement->state = Region::State::empty;
                return 0;
            }
            replacement->pages[replacement->count++].emplace(std::move(*lease));
            ++target->metrics_.held_pages;
        }
        // Validate the complete source before copying or retiring anything.
        for (std::size_t index = 0; index < record->count; ++index) {
            if (!target->page(*record, index)) {
                replacement->state = Region::State::retained;
                target->retain(*record);
            }
        }
        if (!target->scrub(*replacement)) {
            record->state = Region::State::retained;
            target->retain(*replacement);
        }
        const auto prefix = count < old_count ? count : old_count;
        for (std::size_t offset = 0; offset < prefix;) {
            const auto index = offset / Region::page_bytes;
            const auto source = target->page(*record, index);
            const auto destination = target->page(*replacement, index);
            if (!source || !destination) {
                record->state = Region::State::retained;
                target->retain(*replacement);
            }
            const auto remaining = prefix - offset;
            const auto chunk = remaining < Region::page_bytes ? remaining : Region::page_bytes;
            for (std::size_t byte = 0; byte < chunk; ++byte) {
                (*destination)[byte] = (*source)[byte];
            }
            offset += chunk;
        }
        if (fill != nullptr)
            fill_values(*target,
                        *replacement,
                        static_cast<std::size_t>(prefix),
                        static_cast<std::size_t>(count),
                        static_cast<std::size_t>(stride),
                        fill,
                        record);
        const auto staging_peak = target->metrics_.held_pages;
        const auto retired_id = record->id;
        // All recoverable failures precede retirement. A scrub/lease failure
        // is terminal and retains BOTH transaction records, never false success.
        target->release_pages(*record, replacement);
        record->id = 0;
        record->length = 0;
        record->state = Region::State::empty;
        replacement->id = next_allocation_id;
        replacement->length = length;
        replacement->state = Region::State::live;
        target->metrics_.used = other_used + count;
        ++target->metrics_.successful_allocations;
        ++target->metrics_.releases;
        if (target->metrics_.used > target->metrics_.peak_used) {
            target->metrics_.peak_used = target->metrics_.used;
        }
        if (staging_peak > target->metrics_.peak_held_pages) {
            target->metrics_.peak_held_pages = staging_peak;
        }
        target->metrics_.last_allocation_id = replacement->id;
        target->metrics_.last_released_id = retired_id;
        commit_id(next_allocation_id, allocation_ids_exhausted);
        *owner = NativeOwner{target->id_, replacement->id, length, 1};
        return 1;
    }

    static void allocate_values(
        std::uint64_t id, std::int64_t count, std::int64_t stride, const void *fill, NativeOwner *output) noexcept {
        if (!valid_value_stride(stride) || fill == nullptr)
            __au_runtime_bytes_kernel_fault(1);
        allocate(id, value_byte_length(count, stride), output, static_cast<const unsigned char *>(fill), stride);
    }

    static Region::Allocation *
    value_allocation(const NativeOwner *owner, std::int64_t stride, Region *&target) noexcept {
        auto *record = allocation(owner, target);
        if (!valid_value_stride(stride) || owner->length % stride != 0)
            __au_runtime_bytes_kernel_fault(1);
        return record;
    }

    static void values_at(const NativeOwner *owner, std::int64_t index, std::int64_t stride, void *output) noexcept {
        Region *target = nullptr;
        auto *record = value_allocation(owner, stride, target);
        if (output == nullptr)
            __au_runtime_bytes_kernel_fault(1);
        if (record == nullptr || index < 0 || index >= record->length / stride)
            __au_runtime_bytes_kernel_fault(2);
        const auto begin = static_cast<std::size_t>(index * stride);
        auto *destination = static_cast<unsigned char *>(output);
        for (std::size_t byte = 0; byte < static_cast<std::size_t>(stride); ++byte) {
            const auto offset = begin + byte;
            const auto page = target->page(*record, offset / Region::page_bytes);
            if (!page)
                target->retain(*record);
            destination[byte] = std::to_integer<unsigned char>((*page)[offset % Region::page_bytes]);
        }
    }

    static std::uint64_t
    values_set(NativeOwner *owner, std::int64_t index, std::int64_t stride, const void *value) noexcept {
        Region *target = nullptr;
        auto *record = value_allocation(owner, stride, target);
        if (value == nullptr)
            __au_runtime_bytes_kernel_fault(1);
        if (record == nullptr || index < 0 || index >= record->length / stride)
            return 0;
        const auto begin = static_cast<std::size_t>(index * stride);
        fill_values(*target,
                    *record,
                    begin,
                    begin + static_cast<std::size_t>(stride),
                    static_cast<std::size_t>(stride),
                    static_cast<const unsigned char *>(value));
        return 1;
    }

    static std::uint64_t
    resize_values(NativeOwner *owner, std::int64_t count, std::int64_t stride, const void *fill) noexcept {
        Region *target = nullptr;
        value_allocation(owner, stride, target); // validate even an invalid request
        if (fill == nullptr)
            __au_runtime_bytes_kernel_fault(1);
        return resize(owner, value_byte_length(count, stride), static_cast<const unsigned char *>(fill), stride);
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
        target->release_live(*record);
        *owner = NativeOwner{};
    }
};

#ifdef AURORA_KERNEL_BYTES_TESTING
std::size_t Region::retained_records_for_test() const noexcept {
    std::size_t count = 0;
    for (const auto &record : allocations_) {
        count += record.state == State::retained ? 1 : 0;
    }
    return count;
}
std::size_t Region::preparing_records_for_test() const noexcept {
    std::size_t count = 0;
    for (const auto &record : allocations_) {
        count += record.state == State::preparing ? 1 : 0;
    }
    return count;
}
bool Region::inactive_records_clean_for_test() const noexcept {
    for (const auto &record : allocations_) {
        if (record.state != State::empty) {
            continue;
        }
        if (record.id != 0 || record.length != 0 || record.count != 0) {
            return false;
        }
        for (const auto &page : record.pages) {
            if (page) {
                return false;
            }
        }
    }
    return true;
}
bool Region::advance_counters_for_test(std::uint64_t allocations, std::uint64_t releases) noexcept {
    if (!open_ || faulted_ || allocations < metrics_.successful_allocations || releases < metrics_.releases ||
        allocations < releases || allocations - releases != metrics_.live_allocations) {
        return false;
    }
    metrics_.successful_allocations = allocations;
    metrics_.releases = releases;
    return true;
}
#endif

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
extern "C" void __au_runtime_values_allocate(
    std::uint64_t region, std::int64_t count, std::int64_t stride, const void *fill, NativeOwner *output) noexcept {
    kernel::bytes::RuntimeAccess::allocate_values(region, count, stride, fill, output);
}
extern "C" void
__au_runtime_values_at(const NativeOwner *owner, std::int64_t index, std::int64_t stride, void *output) noexcept {
    kernel::bytes::RuntimeAccess::values_at(owner, index, stride, output);
}
extern "C" std::uint64_t
__au_runtime_values_set(NativeOwner *owner, std::int64_t index, std::int64_t stride, const void *value) noexcept {
    return kernel::bytes::RuntimeAccess::values_set(owner, index, stride, value);
}
extern "C" std::uint64_t
__au_runtime_values_resize(NativeOwner *owner, std::int64_t count, std::int64_t stride, const void *fill) noexcept {
    return kernel::bytes::RuntimeAccess::resize_values(owner, count, stride, fill);
}

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

extern "C" std::uint64_t __au_runtime_bytes_resize(NativeOwner *owner, std::int64_t length) noexcept {
    return kernel::bytes::RuntimeAccess::resize(owner, length);
}

extern "C" void __au_runtime_bytes_drop(NativeOwner *owner) noexcept {
    kernel::bytes::RuntimeAccess::drop(owner);
}
} // namespace aurora::hosted::bytes
