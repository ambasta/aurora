#include "address-spaces.hpp"
#include "mapping.hpp"
#include "protection.hpp"
#include "user-program.hpp"
#include <array>
namespace aurora::user {
namespace {
using hardware::Protection;
using memory::PageAccess;
using memory::PageDomain;
constexpr auto address_mask = 0x000ffffffffff000ULL;
constexpr auto accessed_dirty = std::uint64_t{0x60};
class alignas(4096) Root final {
    alignas(4096) std::array<std::uint64_t, 512> pml4_{};
    alignas(4096) std::array<std::uint64_t, 512> pdpt_{};
    alignas(4096) std::array<std::uint64_t, 512> directory_{};
    memory::AddressMap leaves_;
public:
    Root() = default;
    Root(const Root&) = delete;
    auto operator=(const Root&) -> Root& = delete;
    auto clear() -> void {
        for (auto& entry : pml4_) entry = 0;
        for (auto& entry : pdpt_) entry = 0;
        for (auto& entry : directory_) entry = 0;
        leaves_.clear();
    }
    [[nodiscard]] auto physical() const -> std::uint64_t { return reinterpret_cast<std::uint64_t>(pml4_.data()); }
    [[nodiscard]] auto build(std::uint64_t image, const std::array<std::uint64_t, 4>& frames) -> bool {
        clear();
        for (auto address = std::uint64_t{4096}; address < 0x200000; address += 4096) {
            const auto leaf = Protection::kernel_entry(address);
            if ((leaf & 1) == 0 || (leaf & 4) != 0 || (address >= UserPrograms::code_begin && address < UserPrograms::code_end)) continue;
            const auto access = (leaf & 2) != 0 ? PageAccess::read_write
                : (leaf >> 63) != 0 ? PageAccess::read_only : PageAccess::read_execute;
            if (!leaves_.map(address, leaf & address_mask, access, PageDomain::kernel)) return false;
        }
        if (!leaves_.map(image, image, PageAccess::read_execute, PageDomain::user)) return false;
        for (std::size_t index = 0; index < frames.size(); ++index)
            if (!leaves_.map(Protection::user_stack_bottom + index * 4096, frames[index], PageAccess::read_write, PageDomain::user)) return false;
        pml4_[0] = reinterpret_cast<std::uint64_t>(pdpt_.data()) | 7;
        pdpt_[0] = reinterpret_cast<std::uint64_t>(directory_.data()) | 7;
        directory_[0] = reinterpret_cast<std::uint64_t>(leaves_.hardware_address()) | 7;
        return valid(image, frames);
    }
    [[nodiscard]] auto valid(std::uint64_t image, const std::array<std::uint64_t, 4>& frames) const -> bool {
        if ((pml4_[0] & ~accessed_dirty) != (reinterpret_cast<std::uint64_t>(pdpt_.data()) | 7)
            || (pdpt_[0] & ~accessed_dirty) != (reinterpret_cast<std::uint64_t>(directory_.data()) | 7)
            || (directory_[0] & ~accessed_dirty) != (reinterpret_cast<std::uint64_t>(leaves_.hardware_address()) | 7)) return false;
        for (std::size_t index = 1; index < 512; ++index)
            if (pml4_[index] != 0 || pdpt_[index] != 0 || directory_[index] != 0) return false;
        for (auto address = std::uint64_t{0}; address < 0x200000; address += 4096) {
            auto expected = Protection::kernel_entry(address) & ~accessed_dirty;
            if ((expected & 4) != 0 || (address >= UserPrograms::code_begin && address < UserPrograms::code_end)) expected = 0;
            if (address == image) expected = image | 5;
            if (address >= Protection::user_stack_bottom && address < Protection::user_stack_top)
                expected = frames[(address - Protection::user_stack_bottom) / 4096] | 7 | memory::IdentityMap::no_execute;
            if ((leaves_.entry(address) & ~accessed_dirty) != expected || (leaves_.entry(address) & 0x100) != 0) return false;
        }
        return physical() % 4096 == 0 && physical() < 0x70000;
    }
};
static_assert(sizeof(Root) == 16384);
class Slot final {
public:
    Root root;
    std::array<std::optional<memory::PageLease>, 4> stack{};
    std::optional<std::size_t> image{};
};
constinit std::array<Slot, 3> slots{};
constinit DomainRegistry registry;
constinit memory::PhysicalPages* allocator = nullptr;
auto approved_frame(std::uint64_t address) -> bool {
    return address >= 0x100000 && address <= 0x180000 - 4096 && address % 4096 == 0;
}

auto frame_addresses(std::size_t slot) -> std::optional<std::array<std::uint64_t, 4>> {
    std::array<std::uint64_t, 4> frames{};
    for (std::size_t page = 0; page < frames.size(); ++page) {
        if (!slots[slot].stack[page]) return std::nullopt;
        const auto physical = allocator->address(*slots[slot].stack[page]);
        if (!physical || !approved_frame(*physical)) return std::nullopt;
        frames[page] = *physical;
    }
    return frames;
}
auto switch_root(std::uint64_t root) -> bool {
    std::uint64_t cr4;
    asm volatile("mov %%cr4, %0" : "=r"(cr4));
    if ((cr4 & (1ULL << 17)) != 0 || root % 4096 != 0 || root >= 0x70000) return false;
    // PCID is disabled, leaves are nonglobal, and a CR3 write flushes this CPU's old translations.
    asm volatile("mov %0, %%cr3" : : "r"(root) : "memory");
    return Protection::current_root() == root;
}
}
auto AddressSpaces::initialize(memory::PhysicalPages& pool) -> bool {
    if (allocator != nullptr || !pool.arena_matches(0x100000, 128) || pool.used() != 0 || !Protection::verify()) return false;
    allocator = &pool;
    return true;
}
auto AddressSpaces::create(std::size_t image) -> std::optional<DomainHandle> {
    const auto* contract = UserPrograms::contract(image);
    if (allocator == nullptr || contract == nullptr || !Protection::verify()) return std::nullopt;
    for (const auto& slot : slots) if (slot.image == image) return std::nullopt;
    auto handle = registry.create();
    if (!handle) return std::nullopt;
    const auto slot = *registry.index(*handle);
    for (auto& page : slots[slot].stack) {
        auto lease = allocator->acquire();
        if (!lease) {
            // Every partially acquired frame is scrubbed before returning it to the pool.
            for (auto& acquired : slots[slot].stack) {
                if (!acquired) continue;
                const auto address = allocator->address(*acquired);
                if (!address || !approved_frame(*address)) return std::nullopt;
                for (auto byte = std::uint64_t{0}; byte < 4096; ++byte)
                    *reinterpret_cast<volatile std::uint8_t*>(*address + byte) = 0;
                for (auto byte = std::uint64_t{0}; byte < 4096; ++byte)
                    if (*reinterpret_cast<volatile const std::uint8_t*>(*address + byte) != 0) return std::nullopt;
                if (!allocator->release(*acquired)) return std::nullopt;
                acquired.reset();
            }
            static_cast<void>(registry.destroy(*handle));
            return std::nullopt;
        }
        page.emplace(std::move(*lease));
    }
    slots[slot].image = image;
    const auto frames = frame_addresses(slot);
    if (!frames || !scrub(*handle) || !slots[slot].root.build(contract->entry(), *frames)) {
        static_cast<void>(destroy(*handle));
        return std::nullopt;
    }
    return handle;
}
auto AddressSpaces::stack_frame(DomainHandle handle, std::size_t page) -> std::optional<std::uint64_t> {
    const auto slot = registry.index(handle);
    if (!slot || allocator == nullptr || page >= 4 || !slots[*slot].stack[page]) return std::nullopt;
    const auto physical = allocator->address(*slots[*slot].stack[page]);
    return physical && approved_frame(*physical) ? physical : std::nullopt;
}
auto AddressSpaces::root(DomainHandle handle) -> std::optional<std::uint64_t> {
    const auto slot = registry.index(handle);
    return slot ? std::optional{slots[*slot].root.physical()} : std::nullopt;
}
auto AddressSpaces::stack_zero(DomainHandle handle) -> bool {
    if (!registry.ready(handle) || !Protection::verify()) return false;
    for (std::size_t page = 0; page < 4; ++page) {
        const auto address = stack_frame(handle, page);
        if (!address) return false;
        for (auto byte = std::uint64_t{0}; byte < 4096; ++byte)
            if (*reinterpret_cast<volatile const std::uint8_t*>(*address + byte) != 0) return false;
    }
    return true;
}
auto AddressSpaces::scrub(DomainHandle handle) -> bool {
    if (!registry.ready(handle) || !Protection::verify()) return false;
    for (std::size_t page = 0; page < 4; ++page) {
        const auto address = stack_frame(handle, page);
        if (!address) return false;
        for (auto byte = std::uint64_t{0}; byte < 4096; ++byte)
            *reinterpret_cast<volatile std::uint8_t*>(*address + byte) = 0;
    }
    return stack_zero(handle);
}
auto AddressSpaces::activate(DomainHandle handle) -> bool {
    const auto slot = registry.index(handle);
    if (!slot || !registry.ready(handle) || !Protection::verify() || !slots[*slot].image) return false;
    const auto frames = frame_addresses(*slot);
    const auto* contract = UserPrograms::contract(*slots[*slot].image);
    if (!frames || contract == nullptr || !slots[*slot].root.valid(contract->entry(), *frames)) return false;
    if (!registry.activate(handle)) return false;
    return switch_root(slots[*slot].root.physical());
}
auto AddressSpaces::active(DomainHandle handle) -> bool {
    const auto slot = registry.index(handle);
    return slot && registry.active(handle) && Protection::current_root() == slots[*slot].root.physical();
}
auto AddressSpaces::deactivate(DomainHandle handle) -> bool {
    if (!active(handle) || !switch_root(Protection::kernel_root())) return false;
    return registry.deactivate(handle) && Protection::verify();
}
auto AddressSpaces::destroy(DomainHandle handle) -> bool {
    const auto slot = registry.index(handle);
    if (!slot || !registry.ready(handle) || !Protection::verify() || !scrub(handle)) return false;
    slots[*slot].root.clear();
    if (!registry.destroy(handle)) return false;
    slots[*slot].image.reset();
    for (auto& lease : slots[*slot].stack) {
        if (!lease || !allocator->release(*lease)) return false;
        lease.reset();
    }
    return true;
}
}
