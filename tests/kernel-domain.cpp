#include "../kernel/domain-policy.hpp"
#include "../kernel/mapping.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <optional>
#include <string_view>
#include <type_traits>
using aurora::memory::AddressMap;
using aurora::memory::PageAccess;
using aurora::memory::PageDomain;
using aurora::user::DomainHandle;
using aurora::user::DomainRegistry;
static_assert(!std::is_copy_constructible_v<DomainRegistry>);
auto check(bool condition, std::string_view message) -> void {
    if (!condition) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
auto main() -> int {
    DomainRegistry registry, foreign;
    std::array<DomainHandle, 3> handles{};
    check(!registry.activate(DomainHandle{}) && !registry.destroy(DomainHandle{}), "default handle");
    for (std::size_t index = 0; index < 3; ++index) {
        const auto handle = registry.create();
        check(handle.has_value(), "bounded create");
        handles[index] = *handle;
        check(registry.index(*handle) == index, "unique slot");
    }
    check(!registry.create(), "capacity enforcement");
    const auto outsider = foreign.create();
    check(outsider.has_value(), "foreign create");
    check(!registry.index(*outsider) && !foreign.index(handles[0]), "cross-registry forgery");
    check(registry.activate(handles[0]) && registry.active(handles[0]), "activation");
    check(!registry.activate(handles[1]) && !registry.create(), "one active context");
    check(!registry.destroy(handles[0]) && !registry.destroy(handles[1]), "teardown while root active");
    check(!registry.deactivate(handles[1]) && registry.active(handles[0]), "wrong deactivation");
    check(registry.deactivate(handles[0]) && !registry.active(handles[0]), "kernel-root transition");
    const auto stale = handles[0];
    check(registry.destroy(stale) && !registry.destroy(stale) && !registry.activate(stale), "destroyed authority");
    const auto replacement = registry.create();
    check(replacement.has_value(), "slot reuse");
    check(!registry.index(stale) && !registry.activate(stale) && !registry.destroy(stale), "stale reuse authority");
    check(registry.activate(*replacement) && registry.deactivate(*replacement), "fresh owner");
    std::optional<DomainRegistry> incarnation;
    incarnation.emplace();
    const auto previous = incarnation->create();
    check(previous.has_value(), "incarnation");
    incarnation.reset();
    incarnation.emplace();
    const auto current = incarnation->create();
    check(current.has_value() && !incarnation->index(*previous), "registry address resurrection");
    AddressMap map;
    check(!map.map(0, 0x100000, PageAccess::read_write, PageDomain::user), "null virtual page");
    check(!map.map(0x100000, 0, PageAccess::read_write, PageDomain::kernel), "null physical page");
    check(!map.map(0x100000, 0x200001, PageAccess::read_write, PageDomain::kernel), "physical bound/alignment");
    check(!map.map(0x100000, 0x100000, static_cast<PageAccess>(99), PageDomain::kernel), "invalid permission");
    check(map.map(0x100000, 0x100000, PageAccess::read_write, PageDomain::kernel), "supervisor direct map");
    check(map.map(0x1e0000, 0x100000, PageAccess::read_write, PageDomain::user), "private stack alias");
    check((map.entry(0x100000) & 4) == 0 && (map.entry(0x1e0000) & 4) != 0, "alias privilege split");
    check(!map.map(0x1b0000, 0x100000, PageAccess::read_execute, PageDomain::user), "RW-to-RX alias violation");
    check(map.map(0x1b0000, 0x1b0000, PageAccess::read_execute, PageDomain::user), "own immutable code");
    check(!map.map(0x180000, 0x1b0000, PageAccess::read_write, PageDomain::kernel), "RX-to-RW alias violation");
    check(!map.map(0x1b0000, 0x1b1000, PageAccess::read_only, PageDomain::user), "existing leaf replacement");
    check(map.entry(0x1b1000) == 0, "foreign image default deny");
    map.clear();
    for (std::uint64_t page = 0; page < 0x200000; page += 4096)
        check(map.entry(page) == 0, "root clear");
    std::cout
        << "PASS: domain ownership, active/foreign/stale/rebirth rejection, bounded slots, nonidentity W^X aliases\n";
}
