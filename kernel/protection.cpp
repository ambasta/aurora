#include "protection.hpp"
#include "mapping.hpp"
#include "user-program.hpp"
#include <array>
#include <cstddef>
#include <cstdint>

extern const std::byte text_begin asm("__text_begin");
extern const std::byte text_end asm("__text_end");
extern const std::byte read_begin asm("__read_begin");
extern const std::byte read_end asm("__read_end");
extern const std::byte write_begin asm("__write_begin");
extern const std::byte write_end asm("__write_end");
extern const std::byte user_payload_begin asm("aurora_user_payload_begin");
extern const std::byte user_payload_end asm("aurora_user_payload_end");
namespace {
using aurora::memory::PageAccess;
using aurora::memory::PageDomain;
using aurora::hardware::Protection;
constinit aurora::memory::IdentityMap leaves;
alignas(4096) constinit std::array<std::uint64_t, 512> pml4{};
alignas(4096) constinit std::array<std::uint64_t, 512> pdpt{};
alignas(4096) constinit std::array<std::uint64_t, 512> directory{};
auto address(const std::byte& symbol) -> std::uint64_t { return reinterpret_cast<std::uint64_t>(&symbol); }
auto map_range(std::uint64_t begin, std::uint64_t end, PageAccess access, PageDomain domain = PageDomain::kernel) -> bool {
    if (begin % 4096 != 0 || end % 4096 != 0 || begin >= end) return false;
    for (auto page = begin; page < end; page += 4096)
        if (!leaves.map(page, access, domain)) return false;
    return true;
}
auto efer() -> std::uint64_t {
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0xc0000080));
    return (static_cast<std::uint64_t>(high) << 32) | low;
}
}
auto Protection::activate() -> bool {
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000000U), "c"(0));
    if (a < 0x80000001U) return false;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000001U), "c"(0));
    if ((d & (1U << 20)) == 0) return false;
    if (!aurora::user::UserPrograms::install()) return false;
    const auto payload_begin = address(user_payload_begin);
    const auto payload_size = address(user_payload_end) - payload_begin;
    if (payload_size == 0 || payload_size > 4096) return false;
    for (auto byte = std::uint64_t{0}; byte < 4096; ++byte)
        *reinterpret_cast<volatile std::uint8_t*>(user_code + byte) = byte < payload_size
            ? *reinterpret_cast<const std::uint8_t*>(payload_begin + byte) : 0;
    // User data starts sanitized; it never receives allocator or kernel bytes.
    for (auto byte = user_stack_bottom; byte < user_stack_top; ++byte)
        *reinterpret_cast<volatile std::uint8_t*>(byte) = 0;
    if (!map_range(address(text_begin), address(text_end), PageAccess::read_execute)
        || !map_range(address(read_begin), address(read_end), PageAccess::read_only)
        || !map_range(address(write_begin), address(write_end), PageAccess::read_write)
        || !map_range(0x5000, 0x6000, PageAccess::read_only)
        || !map_range(main_stack_bottom, main_stack_top, PageAccess::read_write)
        || !map_range(entry_stack_bottom, entry_stack_top, PageAccess::read_write)
        || !map_range(emergency_stack_bottom, emergency_stack_top, PageAccess::read_write)
        || !map_range(0x100000, 0x180000, PageAccess::read_write)
        || !map_range(aurora::user::UserPrograms::code_begin, aurora::user::UserPrograms::code_end, PageAccess::read_execute, PageDomain::user)
        || !map_range(user_code, user_code + 4096, PageAccess::read_execute, PageDomain::user)
        || !map_range(user_stack_bottom, user_stack_top, PageAccess::read_write, PageDomain::user)) return false;
    pml4[0] = reinterpret_cast<std::uint64_t>(pdpt.data()) | 7;
    pdpt[0] = reinterpret_cast<std::uint64_t>(directory.data()) | 7;
    directory[0] = reinterpret_cast<std::uint64_t>(leaves.hardware_address()) | 7;
    const auto enabled = efer() | (std::uint64_t{1} << 11);
    asm volatile("wrmsr" : : "a"(static_cast<std::uint32_t>(enabled)), "d"(static_cast<std::uint32_t>(enabled >> 32)), "c"(0xc0000080) : "memory");
    std::uint64_t cr0;
    asm volatile("mov %%cr0, %0" : "=r"(cr0));
    cr0 |= std::uint64_t{1} << 16;
    asm volatile("mov %0, %%cr0" : : "r"(cr0) : "memory");
    asm volatile("mov %0, %%cr3" : : "r"(pml4.data()) : "memory");
    return verify();
}
auto Protection::verify() -> bool {
    std::uint64_t cr0, cr3;
    asm volatile("mov %%cr0, %0; mov %%cr3, %1" : "=r"(cr0), "=r"(cr3));
    if ((cr0 & (std::uint64_t{1} << 16)) == 0 || (efer() & (std::uint64_t{1} << 11)) == 0
        || cr3 != reinterpret_cast<std::uint64_t>(pml4.data())) return false;
    for (auto page = std::uint64_t{0}; page < 0x200000; page += 4096) {
        const auto entry = leaves.entry(page);
        if (entry == 0) continue;
        if ((entry & 2) != 0 && (entry >> 63) == 0) return false;
        if ((entry & 4) != 0 && page != user_code && !(page >= aurora::user::UserPrograms::code_begin && page < aurora::user::UserPrograms::code_end)
            && !(page >= user_stack_bottom && page < user_stack_top)) return false;
    }
    return leaves.entry(0) == 0 && leaves.entry(main_stack_bottom - 4096) == 0
        && leaves.entry(entry_stack_bottom - 4096) == 0 && leaves.entry(emergency_stack_bottom - 4096) == 0
        && leaves.entry(user_stack_bottom - 4096) == 0;
}
