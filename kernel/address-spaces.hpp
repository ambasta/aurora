#pragma once
#include "domain-policy.hpp"
#include "pages.hpp"
#include <cstddef>
#include <cstdint>
#include <optional>
namespace aurora::user {
class AddressSpaces final {
public:
    [[nodiscard]] static auto initialize(memory::PhysicalPages& pool) -> bool;
    [[nodiscard]] static auto create(std::size_t image) -> std::optional<DomainHandle>;
    [[nodiscard]] static auto activate(DomainHandle handle) -> bool;
    [[nodiscard]] static auto active(DomainHandle handle) -> bool;
    [[nodiscard]] static auto deactivate(DomainHandle handle) -> bool;
    [[nodiscard]] static auto destroy(DomainHandle handle) -> bool;
    [[nodiscard]] static auto scrub(DomainHandle handle) -> bool;
    [[nodiscard]] static auto stack_zero(DomainHandle handle) -> bool;
    [[nodiscard]] static auto stack_frame(DomainHandle handle, std::size_t page) -> std::optional<std::uint64_t>;
    [[nodiscard]] static auto root(DomainHandle handle) -> std::optional<std::uint64_t>;
};
}
