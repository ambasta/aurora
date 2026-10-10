#include "../kernel/mapping.hpp"
#include "../kernel/firmware-memory.hpp"
#include <cstdlib>
#include <iostream>
#include <string_view>
#include <type_traits>

using aurora::memory::FirmwareMemory;
using aurora::memory::IdentityMap;
using aurora::memory::PageAccess;
using aurora::memory::PageDomain;
static_assert(!std::is_copy_constructible_v<IdentityMap>);
auto check(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
auto main() -> int {
    IdentityMap map;
    check(!map.map(0, PageAccess::read_write, PageDomain::kernel), "null mapping");
    check(!map.map(4097, PageAccess::read_write, PageDomain::kernel), "unaligned mapping");
    check(!map.map(0x200000, PageAccess::read_only, PageDomain::kernel), "out of range");
    check(!map.map(UINT64_MAX, PageAccess::read_only, PageDomain::kernel), "overflow address");
    check(!map.map(4096, static_cast<PageAccess>(99), PageDomain::kernel), "invalid permission");
    check(!map.map(4096, PageAccess::read_only, static_cast<PageDomain>(99)), "invalid domain");
    check(map.entry(4096) == 0, "invalid request mutated map");
    for (std::uint64_t page = 1; page < 512; ++page) {
        const auto access = page % 3 == 0   ? PageAccess::read_execute
                            : page % 3 == 1 ? PageAccess::read_only
                                            : PageAccess::read_write;
        const auto domain = page % 2 == 0 ? PageDomain::user : PageDomain::kernel;
        check(map.map(page * 4096, access, domain), "valid mapping");
        const auto entry = map.entry(page * 4096);
        check((entry & 1) != 0, "present flag");
        check(((entry & 2) != 0) == (access == PageAccess::read_write), "write flag");
        check(((entry >> 63) == 0) == (access == PageAccess::read_execute), "execute flag");
        check(((entry & 4) != 0) == (domain == PageDomain::user), "user flag");
        check((entry & 0x000ffffffffff000ULL) == page * 4096, "identity/no-alias invariant");
        check(!map.map(page * 4096, PageAccess::read_write, PageDomain::user), "remap rejection");
        check(map.entry(page * 4096) == entry, "remap mutated permissions");
    }
    check(map.entry(0) == 0 && map.entry(0x200000) == 0, "default deny");
    std::array<std::byte, 8 + 32 * 24> handoff{};
    auto put = [&](std::size_t at, std::uint64_t value, unsigned width) {
        for (auto byte = 0U; byte < width; ++byte)
            handoff[at + byte] = static_cast<std::byte>(value >> (byte * 8));
    };
    auto entry = [&](std::size_t index, std::uint64_t base, std::uint64_t size, unsigned type, unsigned flags = 1) {
        put(8 + index * 24, base, 8);
        put(16 + index * 24, size, 8);
        put(24 + index * 24, type, 4);
        put(28 + index * 24, flags, 4);
    };
    check(!FirmwareMemory::grants(handoff, 0x100000, 0x180000), "empty firmware map");
    put(0, 1, 2);
    entry(0, 0x100000, 0x100000, 1);
    check(FirmwareMemory::grants(handoff, 0x100000, 0x180000), "valid firmware grant");
    check(!FirmwareMemory::grants(handoff, 0x100000, 0x210000), "uncovered tail");
    check(!FirmwareMemory::grants(handoff, 1, 1), "empty range");
    check(!FirmwareMemory::grants(std::span(handoff).first(20), 0x100000, 0x180000), "truncated entry");
    put(0, 2, 2);
    entry(1, 0x120000, 0x1000, 2);
    check(!FirmwareMemory::grants(handoff, 0x100000, 0x180000), "reserved overlap after usable range");
    entry(0, 0x120000, 0x1000, 2);
    entry(1, 0x100000, 0x100000, 1);
    check(!FirmwareMemory::grants(handoff, 0x100000, 0x180000), "reserved overlap before usable range");
    entry(0, 0x120000, 0x1000, 2, 0);
    check(FirmwareMemory::grants(handoff, 0x100000, 0x180000), "disabled entry incorrectly active");
    entry(0, UINT64_MAX - 4, 10, 1);
    check(!FirmwareMemory::grants(handoff, 0x100000, 0x180000), "wrapping firmware region");
    put(0, 33, 2);
    check(!FirmwareMemory::grants(handoff, 0x100000, 0x180000), "excess firmware count");
    std::cout << "PASS: 511 identity mappings, W^X/domain/default-deny policy, malformed/overlapping firmware grants\n";
}
