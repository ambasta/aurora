#pragma once
#include <array>
#include <cstddef>
#include <cstdint>

namespace aurora::memory {
enum class PageAccess { read_only, read_write, read_execute };
enum class PageDomain { kernel, user };
// Deliberately bounded, identity-only map. No alias or executable-write API exists.
class alignas(4096) IdentityMap final {
    std::array<std::uint64_t, 512> leaves_{};
public:
    static constexpr auto present = std::uint64_t{1};
    static constexpr auto writable = std::uint64_t{2};
    static constexpr auto user = std::uint64_t{4};
    static constexpr auto no_execute = std::uint64_t{1} << 63;
    IdentityMap() = default;
    IdentityMap(const IdentityMap&) = delete;
    auto operator=(const IdentityMap&) -> IdentityMap& = delete;
    [[nodiscard]] auto map(std::uint64_t address, PageAccess access, PageDomain domain) -> bool {
        if (address % 4096 != 0 || address >= 0x200000 || address == 0) return false;
        if (domain != PageDomain::kernel && domain != PageDomain::user) return false;
        auto flags = present;
        switch (access) {
            case PageAccess::read_only: flags |= no_execute; break;
            case PageAccess::read_write: flags |= no_execute | writable; break;
            case PageAccess::read_execute: break;
            default: return false;
        }
        if (domain == PageDomain::user) flags |= user;
        auto& leaf = leaves_[address / 4096];
        if (leaf != 0) return false;
        leaf = address | flags;
        return true;
    }
    [[nodiscard]] auto entry(std::uint64_t address) const -> std::uint64_t {
        return address < 0x200000 ? leaves_[address / 4096] : 0;
    }
    // Architecture adapter only: hardware consumes this page, callers cannot edit it.
    [[nodiscard]] auto hardware_address() const -> const void* { return leaves_.data(); }
};
static_assert(sizeof(IdentityMap) == 4096);
}
