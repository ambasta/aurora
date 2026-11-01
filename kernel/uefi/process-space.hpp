#pragma once
#include "memory-manager.hpp"

namespace aurora::uefi {
// A resident is only an issuer, fixed slot and lifetime epoch. The retained
// MemoryManager owns regions, reservations, accounting and the page-table
// lifecycle; these methods transport requests and copied results only.
class ProcessSpace final {
public:
    using U64 = std::uint64_t;
    using Region = process::ProcessRegion;
    static constexpr std::size_t max_regions = 10;
    static constexpr U64 address_mask = KernelSpace::address_mask, hardware_bits = 0x60;
    static constexpr U64 slot_bytes = U64{1} << 21;

    // Immutable physical evidence captured from the boot-verified kernel root.
    // It is admitted once by the manager, not a resident's mapping catalog.
    using Shared = MappingAuthority::SharedEvidence;
    enum class Outcome : U64 {
        resume,
        refuse,
        broken
    };
    class Result final {
    public:
        Outcome outcome = Outcome::broken;
        U64 value = 0;
    };
    enum class Access : U64 {
        granted,
        refused,
        broken
    };
    enum class Fault : U64 {
        refused,
        admitted,
        broken
    };
    class Slot final {
    public:
        U64 table = 0, slot = 0;
    };

private:
    MemoryManager &manager_;
    const U64 slot_, epoch_;

    template <class Copied> [[nodiscard]] static auto result(const Copied &copied) -> Result {
        if (copied.outcome > static_cast<U64>(Outcome::broken))
            words::fail();
        return {static_cast<Outcome>(copied.outcome), copied.value};
    }
    [[nodiscard]] auto value(U64 field) const -> U64 {
        return manager_.space_value(slot_, epoch_, field);
    }

public:
    ProcessSpace(MemoryManager &manager, U64 slot, U64 epoch) : manager_(manager), slot_(slot), epoch_(epoch) {
    }
    ProcessSpace(const ProcessSpace &) = delete;
    auto operator=(const ProcessSpace &) -> ProcessSpace & = delete;
    ProcessSpace(ProcessSpace &&) = delete;
    auto operator=(ProcessSpace &&) -> ProcessSpace & = delete;

    [[nodiscard]] auto epoch() const -> U64 {
        return epoch_;
    }
    [[nodiscard]] auto owner() const -> U64 {
        return value(0);
    }
    [[nodiscard]] auto root() const -> U64 {
        return value(1);
    }
    [[nodiscard]] auto tables() const -> U64 {
        return value(2);
    }
    [[nodiscard]] auto leaves() const -> U64 {
        return value(3);
    }
    [[nodiscard]] auto memory() const -> U64 {
        return value(4);
    }
    [[nodiscard]] auto charged() const -> U64 {
        return value(5);
    }
    [[nodiscard]] auto quota() const -> U64 {
        return value(6);
    }
    [[nodiscard]] auto held() const -> U64 {
        return value(7);
    }

    // source_kind refers to an independently admitted immutable input. No
    // native destination span or source pointer survives this synchronous call.
    [[nodiscard]] auto map(const Region &region, U64 source_kind) -> bool {
        return manager_.map_region(slot_, epoch_, region, source_kind);
    }
    [[nodiscard]] auto finish_load() -> bool {
        return manager_.finish_load(slot_, epoch_);
    }
    [[nodiscard]] auto map_memory(U64 bytes) -> Result {
        return result(manager_.map_memory(slot_, epoch_, bytes));
    }
    [[nodiscard]] auto remap_memory(U64 base, U64 bytes, U64 target) -> Result {
        return result(manager_.remap_memory(slot_, epoch_, base, bytes, target));
    }
    [[nodiscard]] auto unmap_memory(U64 base, U64 bytes) -> Result {
        return result(manager_.unmap_memory(slot_, epoch_, base, bytes));
    }
    [[nodiscard]] auto fault(U64 address, U64 error) const -> Fault {
        const U64 verdict = manager_.fault_access(slot_, epoch_, address, error);
        if (verdict > static_cast<U64>(Fault::broken))
            words::fail();
        return static_cast<Fault>(verdict);
    }
    [[nodiscard]] auto commit(U64 address) -> bool {
        return manager_.commit_fault_block(slot_, epoch_, address);
    }
    [[nodiscard]] auto access(U64 address, U64 length, bool write) -> Access {
        const U64 verdict = manager_.validate_access(slot_, epoch_, address, length, write);
        if (verdict > static_cast<U64>(Access::broken))
            words::fail();
        return static_cast<Access>(verdict);
    }
    [[nodiscard]] auto contains(U64 address, U64 length) const -> bool {
        return manager_.space_contains(slot_, epoch_, address, length);
    }
    [[nodiscard]] auto executable(U64 address, U64 length) const -> bool {
        return manager_.space_executable(slot_, epoch_, address, length);
    }
    [[nodiscard]] auto verify() const -> bool {
        return manager_.verify_space(slot_, epoch_);
    }
    [[nodiscard]] auto release() -> std::optional<U64> {
        return manager_.retire_space(slot_, epoch_);
    }
#ifndef AURORA_PRODUCTION
    // A copied physical location for the existing hostile fixture only. The
    // source manager still chooses traversal; this grants no production effect.
    [[nodiscard]] auto entry(U64 address, unsigned level) const -> std::optional<Slot> {
        const auto copied = manager_.space_entry(slot_, epoch_, address, level);
        if (!copied)
            return std::nullopt;
        return Slot{copied->table, copied->slot};
    }
#endif
};
} // namespace aurora::uefi
