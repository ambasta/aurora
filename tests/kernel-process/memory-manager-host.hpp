#pragma once
#include "../../kernel/uefi/memory-manager.hpp"
#include <cstring>
#include <vector>
#include <memory>
#include <type_traits>

// A physical-page test device for the real source MemoryManager. This models
// named synchronous reads/writes, not allocation, ownership, quota or traversal
// policy. It deliberately does not substitute for privileged authority tests:
// CR3/IF, exact hardware roles, TLB behavior and physical widths need guests.
namespace aurora::manager_host {
using U64 = std::uint64_t;
using namespace aurora::uefi;
class Device final {
public:
    static constexpr U64 invalid = ~U64{0}, address_mask = 0x000ffffffffff000ULL;
    static constexpr U64 physical_base = 0x100000, shared_entry = 0x8003;
    alignas(16) std::array<std::byte, MemoryManager::root_bytes> root{};
    words::Binding binding;
    std::vector<U64> allocations, mappings, reservations, scratch, incoming;
    const void *allocation_token = nullptr;
    using Page = std::array<U64, 512>;
    std::vector<std::unique_ptr<Page>> pages;
    std::vector<std::byte> source;
    U64 anchor = 0, clears = 0, publishes = 0, observations = 0, fail_after_publish = 0;
    bool window = false;
    volatile U64 *publication_marker = nullptr;
    static inline Device *current = nullptr;
    static auto require(bool value) -> void {
        if (!value)
            words::fail();
    }
    explicit Device(U64 count)
        : allocations(count), mappings(count), reservations(98816), scratch(512), incoming(count), pages(count) {
        require(!current && count > 2 && count <= 131072);
        current = this;
        const std::array<words::Binding::BankGrant, 4> banks{
            {{allocations, 0}, {mappings, 16}, {reservations, 32}, {scratch, 48}}};
        auto grants = binding.bind_set(banks, root.data(), root.size(), 64);
        allocation_token = grants.banks[0].binding;
        __au_runtime_manager_construct(root.data(), &grants);
        require(call(__au_runtime_manager_frames_initialize, {1, 1}));
        require(call(__au_runtime_manager_attach_shared, {}));
    }
    Device(const Device &) = delete;
    ~Device() {
        require(!window && !binding.live());
        current = nullptr;
    }
    template <class Function>
    auto call(Function function, std::initializer_list<U64> values)
        -> std::invoke_result_t<Function, void *, const U64 *> {
        words::Binding::Scope scope(binding, words::Access::write);
        return function(root.data(), values.begin());
    }
    template <class Result, class Function>
    auto copied(Function function, std::initializer_list<U64> values) -> Result {
        words::Binding::Scope scope(binding, words::Access::write);
        Result result{};
        function(root.data(), values.begin(), &result);
        return result;
    }
    auto finish() -> bool {
        words::Binding::Scope scope(binding, words::Access::consume);
        return __au_runtime_manager_finish(root.data(), nullptr);
    }
    [[nodiscard]] auto scalar(std::size_t offset) const -> U64 {
        require(offset <= root.size() - 8);
        U64 value;
        std::memcpy(&value, root.data() + offset, 8);
        return value;
    }
    [[nodiscard]] auto index(U64 address) const -> U64 {
        if (address < physical_base || address % 4096 || (address - physical_base) / 4096 >= pages.size())
            return invalid;
        return (address - physical_base) / 4096;
    }
    [[nodiscard]] auto physical(U64 index) const -> U64 {
        return index < pages.size() ? physical_base + index * 4096 : invalid;
    }
    [[nodiscard]] auto page(U64 ticket) -> std::array<U64, 512> & {
        const U64 index = ticket & 0xffffffff;
        require(index < pages.size() && !window);
        return physical_page(index);
    }
    [[nodiscard]] auto physical_page(U64 index) -> Page & {
        require(index < pages.size());
        if (!pages[index])
            pages[index] = std::make_unique<Page>();
        return *pages[index];
    }
    [[nodiscard]] static auto admit(const void *token, U64 epoch) -> Device & {
        require(current && !current->window);
        static_cast<void>(words::Binding::admitted_authority(token, epoch));
        return *current;
    }
    static auto before_word_write(const void *token, U64 index, U64 value) -> void {
        if (!current || token != current->allocation_token)
            return;
        require(index < current->allocations.size());
        const U64 old = current->allocations[index];
        if ((old & 15) == 2 && ((value & 15) == 1 || (value & 15) == 4))
            require(current->incoming[index] == 0);
    }
    auto add_edge(U64 ticket) -> void {
        const U64 index = ticket & 0xffffffff;
        require(index < incoming.size());
        ++incoming[index];
    }
    auto remove_edge(U64 ticket) -> void {
        const U64 index = ticket & 0xffffffff;
        require(index < incoming.size() && incoming[index]);
        --incoming[index];
    }
    auto observe(U64 ticket) -> bool {
        auto &data = page(ticket);
        ++observations;
        window = true;
        for (U64 slot = 0; slot < 512; ++slot) {
            const U64 raw = data[slot];
            U64 value = raw;
            if (raw && (raw & ~U64{0x60}) != shared_entry) {
                const U64 frame = index(raw & address_mask);
                if (frame == invalid) {
                    window = false;
                    return false;
                }
                value = (frame << 12) | (raw & ~address_mask);
            }
            scratch[slot] = value;
        }
        window = false;
        return true;
    }
    auto next(U64 ticket, U64 first) -> U64 {
        require(first <= 512);
        auto &data = page(ticket);
        window = true;
        U64 slot = first;
        while (slot < 512 && !data[slot])
            ++slot;
        scratch[0] = slot < 512 ? data[slot] : 0;
        scratch[1] = slot;
        window = false;
        return slot;
    }
    auto publish(U64 ticket, U64 slot, U64 value) -> bool {
        auto &data = page(ticket);
        require(slot < 512 && !data[slot]);
        window = true;
        data[slot] = value;
        window = false;
        ++publishes;
        if (publishes == fail_after_publish) {
            require(publication_marker);
            *publication_marker = publishes;
            return false;
        }
        return true;
    }
    auto clear(U64 ticket, U64 slot, U64 expected) -> bool {
        auto &data = page(ticket);
        require(slot < 512 && (data[slot] & ~U64{0x60}) == (expected & ~U64{0x60}));
        window = true;
        data[slot] = 0;
        window = false;
        // Synchronous completion event: the source may release only afterward.
        ++clears;
        return true;
    }
    auto copy(U64 ticket, U64 destination, U64 offset, U64 count) -> bool {
        require(destination <= 4096 && count <= 4096 - destination && offset <= source.size() &&
                count <= source.size() - offset);
        auto &data = page(ticket);
        window = true;
        std::memcpy(reinterpret_cast<std::byte *>(data.data()) + destination, source.data() + offset, count);
        window = false;
        return true;
    }
    auto fill(U64 epoch, U64 destination, U64 offset, U64 count) -> bool {
        require(anchor && scalar(376) == epoch && scalar(384) == 1 && offset <= source.size() &&
                count <= source.size() - offset);
        // This is the physical device's fixed two-level snapshot window, not
        // a metadata ownership walk. The source has already bounded the range.
        for (U64 at = 0; at < count; ++at) {
            const U64 address = destination + at, directory = index(anchor & address_mask);
            require(directory != invalid);
            const U64 table = index(physical_page(directory)[address >> 21] & address_mask);
            require(table != invalid);
            const U64 leaf = index(physical_page(table)[(address >> 12) & 511] & address_mask);
            require(leaf != invalid);
            reinterpret_cast<std::byte *>(physical_page(leaf).data())[address & 4095] = source[offset + at];
        }
        return true;
    }
};
// Explicit host-only terminal admission for the hardware-free allocator cost
// path. No physical operation accepts this marker; they still require Device.
class FrameBenchmarkScope final {
public:
    static inline bool active = false;
    FrameBenchmarkScope() {
        Device::require(!Device::current && !active);
        active = true;
    }
    FrameBenchmarkScope(const FrameBenchmarkScope &) = delete;
    ~FrameBenchmarkScope() {
        Device::require(active && !Device::current);
        active = false;
    }
};
} // namespace aurora::manager_host

extern "C" {
#define MANAGER_DEVICE auto &device = aurora::manager_host::Device::admit(token, epoch)
using ManagerHostU64 = std::uint64_t;
// Source effects return canonical full-width booleans, as OwnedWords does.
// A C++ bool return only guarantees AL and cannot satisfy the checked u64 ABI.
auto __au_runtime_mapping_observe_table(const void *token, ManagerHostU64 epoch, ManagerHostU64 ticket)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    return device.observe(ticket);
}
auto __au_runtime_mapping_observe_next_present(const void *token,
                                               ManagerHostU64 epoch,
                                               ManagerHostU64 ticket,
                                               ManagerHostU64 first) -> ManagerHostU64 {
    MANAGER_DEVICE;
    return device.next(ticket, first);
}
auto __au_runtime_mapping_publish_empty_entry(const void *token,
                                              ManagerHostU64 epoch,
                                              ManagerHostU64 ticket,
                                              ManagerHostU64 slot,
                                              ManagerHostU64 value,
                                              ManagerHostU64 child) -> ManagerHostU64 {
    MANAGER_DEVICE;
    const bool result = device.publish(ticket, slot, value);
    device.add_edge(child);
    return result;
}
auto __au_runtime_mapping_clear_expected_entry(const void *token,
                                               ManagerHostU64 epoch,
                                               ManagerHostU64 ticket,
                                               ManagerHostU64 slot,
                                               ManagerHostU64 expected,
                                               ManagerHostU64 child) -> ManagerHostU64 {
    MANAGER_DEVICE;
    const bool result = device.clear(ticket, slot, expected);
    device.remove_edge(child);
    return result;
}
auto __au_runtime_mapping_scrub_unpublished_frame(const void *token, ManagerHostU64 epoch, ManagerHostU64 ticket)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    device.page(ticket).fill(0);
    return true;
}
auto __au_runtime_mapping_downgrade_snapshot_entry(const void *token,
                                                   ManagerHostU64 epoch,
                                                   ManagerHostU64 ticket,
                                                   ManagerHostU64 slot,
                                                   ManagerHostU64 expected,
                                                   ManagerHostU64 child) -> ManagerHostU64 {
    MANAGER_DEVICE;
    static_cast<void>(child);
    auto &page = device.page(ticket);
    device.require(slot < 512 && (page[slot] & ~ManagerHostU64{0x60}) == (expected & ~ManagerHostU64{0x60}));
    page[slot] &= ~ManagerHostU64{2};
    return true;
}
auto __au_runtime_mapping_snapshot_anchor_publish(const void *token, ManagerHostU64 epoch, ManagerHostU64 ticket)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    device.require(!device.anchor);
    device.anchor = device.physical(ticket & 0xffffffff) | 3;
    device.add_edge(ticket);
    return true;
}
auto __au_runtime_mapping_snapshot_anchor_clear(const void *token, ManagerHostU64 epoch, ManagerHostU64 ticket)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    device.require((device.anchor & device.address_mask) == device.physical(ticket & 0xffffffff));
    device.anchor = 0;
    ++device.clears;
    device.remove_edge(ticket);
    return true;
}
auto __au_runtime_mapping_observe_snapshot_anchor(const void *token, ManagerHostU64 epoch, ManagerHostU64 ticket)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    return (device.anchor & ~ManagerHostU64{0x60}) == (device.physical(ticket & 0xffffffff) | 3);
}
auto __au_runtime_mapping_frame_address(const void *token, ManagerHostU64 epoch, ManagerHostU64 index)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    return device.physical(index);
}
auto __au_runtime_mapping_frame_index(const void *token, ManagerHostU64 epoch, ManagerHostU64 physical)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    return device.index(physical);
}
auto __au_runtime_mapping_shared_slots(const void *token, ManagerHostU64 epoch) -> ManagerHostU64 {
    MANAGER_DEVICE;
    static_cast<void>(device);
    return 1;
}
auto __au_runtime_mapping_shared_slot(const void *token, ManagerHostU64 epoch, ManagerHostU64 index) -> ManagerHostU64 {
    MANAGER_DEVICE;
    device.require(index == 0);
    return 0;
}
auto __au_runtime_mapping_shared_value(const void *token, ManagerHostU64 epoch, ManagerHostU64 index)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    device.require(index == 0);
    return device.shared_entry;
}
auto __au_runtime_mapping_shared_upper(const void *token, ManagerHostU64 epoch, ManagerHostU64 slot) -> ManagerHostU64 {
    MANAGER_DEVICE;
    device.require(slot >= 256 && slot < 512);
    return 0;
}
auto __au_runtime_mapping_reserved_first(const void *token, ManagerHostU64 epoch) -> ManagerHostU64 {
    MANAGER_DEVICE;
    static_cast<void>(device);
    return 0;
}
auto __au_runtime_mapping_reserved_end(const void *token, ManagerHostU64 epoch) -> ManagerHostU64 {
    MANAGER_DEVICE;
    static_cast<void>(device);
    return 2097152;
}
auto __au_runtime_mapping_initialize_shared_upper(const void *token, ManagerHostU64 epoch, ManagerHostU64 ticket)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    auto &page = device.page(ticket);
    for (unsigned slot = 256; slot < 512; ++slot)
        page[slot] = 0;
    return true;
}
auto __au_runtime_mapping_publish_shared_entry(const void *token,
                                               ManagerHostU64 epoch,
                                               ManagerHostU64 ticket,
                                               ManagerHostU64 slot,
                                               ManagerHostU64 shared) -> ManagerHostU64 {
    MANAGER_DEVICE;
    device.require(shared == 0);
    return device.publish(ticket, slot, device.shared_entry);
}
auto __au_runtime_mapping_clear_shared_entry(const void *token,
                                             ManagerHostU64 epoch,
                                             ManagerHostU64 ticket,
                                             ManagerHostU64 slot,
                                             ManagerHostU64 shared) -> ManagerHostU64 {
    MANAGER_DEVICE;
    device.require(shared == 0);
    return device.clear(ticket, slot, device.shared_entry);
}
auto __au_runtime_mapping_copy_source_frame(const void *token,
                                            ManagerHostU64 epoch,
                                            ManagerHostU64 ticket,
                                            ManagerHostU64 destination,
                                            ManagerHostU64 source,
                                            ManagerHostU64 count) -> ManagerHostU64 {
    MANAGER_DEVICE;
    return device.copy(ticket, destination, source, count);
}
auto __au_runtime_mapping_fill_snapshot_chunk(const void *token,
                                              ManagerHostU64 epoch,
                                              ManagerHostU64 snapshot_epoch,
                                              ManagerHostU64 destination,
                                              ManagerHostU64 source,
                                              ManagerHostU64 count) -> ManagerHostU64 {
    MANAGER_DEVICE;
    return device.fill(snapshot_epoch, destination, source, count);
}
auto __au_runtime_mapping_revoke_root(const void *token, ManagerHostU64 epoch, ManagerHostU64 ticket)
    -> ManagerHostU64 {
    MANAGER_DEVICE;
    static_cast<void>(device.page(ticket));
    return true;
}
auto __au_runtime_mapping_finish(const void *token, ManagerHostU64 epoch) -> ManagerHostU64 {
    auto *device = aurora::manager_host::Device::current;
    aurora::manager_host::Device::require((device && !device->window && !device->anchor) ||
                                          (!device && aurora::manager_host::FrameBenchmarkScope::active));
    return aurora::words::Binding::finish_authority(token, epoch);
}
#undef MANAGER_DEVICE
}
