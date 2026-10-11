#pragma once
// Independent recursive references retain the pre-conversion traversal for
// hosted differential controls only. Never linked into a kernel image.
#include "../kernel/uefi/tables.hpp"
#include "../kernel/uefi/runtime-tables.hpp"
namespace table_reference {
using namespace aurora::uefi;
inline auto page_verify(std::uint64_t base,
                        std::size_t used,
                        std::uint64_t arena,
                        const Bytes &h,
                        const LocalApicAdmission *apic = nullptr,
                        const FramebufferAdmission *framebuffer = nullptr) -> bool {
    const PageTables current{base, used};
    if (used == 0 || used > Handoff::table_pages || base != arena + Handoff::tables_offset ||
        (apic && apic->owned_arena() != arena) ||
        (framebuffer && (framebuffer->owned_arena() != arena || h.get(8, 4) != 5 || apic)))
        return false;
    std::array<bool, Handoff::table_pages> visited{};
    const auto walk = [&](auto &&self, std::uint64_t physical, unsigned level, std::uint64_t prefix)
                          __attribute__((noinline, noclone)) -> bool {
        if (physical < base || physical >= base + used * 4096 || physical % 4096)
            return false;
        const auto slot = (physical - base) / 4096;
        if (visited[slot])
            return false;
        visited[slot] = true;
        for (std::uint64_t i = 0; i < 512; ++i) {
            const auto value = reinterpret_cast<const std::uint64_t *>(physical)[i] & ~0x60ULL;
            if (!value)
                continue;
            const auto address = prefix | (i << (12 + 9 * level));
            if (level != 0) {
                if ((value & ~0x000ffffffffff000ULL) != 3 ||
                    !self(self, value & 0x000ffffffffff000ULL, level - 1, address))
                    return false;
            } else {
                const auto canonical = (address & (1ULL << 47)) ? address | 0xffff000000000000ULL : address;
                if (apic && canonical == LocalApicAdmission::virtual_address) {
                    if (value != (LocalApicAdmission::physical_address | LocalApicAdmission::leaf_flags))
                        return false;
                    continue;
                }
                if (framebuffer && framebuffer->mapping(canonical)) {
                    if (value != framebuffer->mapping(canonical))
                        return false;
                    continue;
                }
                if (address < arena || address >= arena + Handoff::arena_bytes)
                    return false;
                const auto flags = expected_flags(address - arena, h);
                if (!flags || value != (address | flags))
                    return false;
            }
        }
        return true;
    };
    if (!walk(walk, base, 3, 0))
        return false;
    for (std::size_t i = 0; i < used; ++i)
        if (!visited[i])
            return false;
    for (std::uint64_t offset = 0; offset < Handoff::arena_bytes; offset += 4096) {
        const auto flags = expected_flags(offset, h);
        const auto expected = flags ? (arena + offset) | flags : 0;
        if ((current.entry(arena + offset) & ~0x60ULL) != expected)
            return false;
    }
    if (apic && (current.entry(LocalApicAdmission::virtual_address) & ~0x60ULL) !=
                    (LocalApicAdmission::physical_address | LocalApicAdmission::leaf_flags))
        return false;
    if (framebuffer) {
        for (std::uint64_t offset = 0; offset < framebuffer->geometry().mapped_bytes(); offset += 4096) {
            const auto page = FramebufferAdmission::virtual_address + offset;
            if ((current.entry(page) & ~0x60ULL) != framebuffer->mapping(page))
                return false;
        }
        if (current.entry(FramebufferAdmission::virtual_address - 4096) ||
            current.entry(FramebufferAdmission::virtual_address + framebuffer->geometry().mapped_bytes()))
            return false;
    }
    return true;
}

template <class Expected>
auto runtime_verify(const RuntimeTables &tables, std::span<const std::uint64_t> storage, Expected &&expected) -> bool {
    using Tables = RuntimeTables;
    if (!tables.valid())
        return false;
    const auto used = tables.used(), base = tables.root();
    std::array<bool, Tables::max_pages> visited{};
    const auto walk =
        [&](auto &&self, std::size_t table, unsigned level, std::uint64_t prefix, bool &contains_user, bool &populated)
        -> bool {
        if (table >= used || visited[table])
            return false;
        visited[table] = true;
        contains_user = populated = false;
        for (std::uint64_t slot = 0; slot < Tables::words_per_page; ++slot) {
            const auto raw = storage[table * Tables::words_per_page + slot];
            if (!raw)
                continue;
            const auto value = raw & ~Tables::accessed_dirty;
            const auto address = prefix | (slot << (12 + 9 * level));
            if (level) {
                const auto flags = value & ~Tables::address_mask;
                const auto physical = value & Tables::address_mask;
                if ((flags != (Tables::present | Tables::writable) &&
                     flags != (Tables::present | Tables::writable | Tables::user)) ||
                    physical < base || (physical - base) / RuntimeLayout::page_size >= used)
                    return false;
                bool child_user = false, child_populated = false;
                if (!self(self,
                          (physical - base) / RuntimeLayout::page_size,
                          level - 1,
                          address,
                          child_user,
                          child_populated) ||
                    !child_populated || ((value & Tables::user) != 0) != child_user)
                    return false;
                contains_user = contains_user || child_user;
                populated = true;
            } else {
                const auto flags = value & ~Tables::address_mask;
                const auto va = address & (1ULL << 47) ? address | 0xffff000000000000ULL : address;
                if (!(((flags & Tables::present) &&
                       !(flags & ~(Tables::present | Tables::writable | Tables::user | Tables::nx))) ||
                      flags == (Tables::present | Tables::writable | Tables::nx | 0x18)) ||
                    expected(va) != value)
                    return false;
                contains_user = contains_user || (value & Tables::user) != 0;
                populated = true;
            }
        }
        return true;
    };
    bool contains_user = false, populated = false;
    if (!walk(walk, 0, 3, 0, contains_user, populated))
        return false;
    for (std::size_t i = 0; i < used; ++i)
        if (!visited[i])
            return false;
    for (std::size_t i = used * Tables::words_per_page; i < storage.size(); ++i)
        if (storage[i])
            return false;
    return true;
}
} // namespace table_reference
