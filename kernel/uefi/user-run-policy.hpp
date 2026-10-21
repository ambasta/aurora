#pragma once
#include "runtime-layout.hpp"
#include "../ipc-policy.hpp"
#include "../user-program.hpp"
#include <optional>

namespace aurora::uefi {
// Kernel-selected launch authority. Two domains admit one client and one service;
// three domains retain the existing dispatcher relationship unchanged.
// This owns values, not references to mutable launch words or domain metadata.
// It does not establish mappings, inspect user memory, or allocate an epoch;
// the adapter verifies its mapping tree and never reuses a run epoch.
template <std::size_t Domains> class BoundedRunAuthority final {
    static_assert(Domains == 2 || Domains == 3);

public:
    enum class Role {
        client,
        service
    };
    static constexpr unsigned maximum_budget = 128;

private:
    using Layout = RuntimeLayoutProfile<Domains>;
    const user::DomainHandle owner_;
    const Role role_;
    const ipc::Phase phase_;
    const std::size_t client_;
    const std::uint64_t transaction_, source_phase_, arena_, root_;
    const user::ProgramContract contract_;
    const std::uint64_t epoch_;
    const unsigned budget_;

    constexpr BoundedRunAuthority(user::DomainHandle owner,
                                  Role role,
                                  ipc::Phase phase,
                                  std::size_t client,
                                  std::uint64_t transaction,
                                  std::uint64_t source_phase,
                                  std::uint64_t arena,
                                  std::uint64_t root,
                                  const user::ProgramContract &contract,
                                  std::uint64_t epoch,
                                  unsigned budget)
        : owner_(owner), role_(role), phase_(phase), client_(client), transaction_(transaction),
          source_phase_(source_phase), arena_(arena), root_(root), contract_(contract), epoch_(epoch), budget_(budget) {
    }

    [[nodiscard]] static constexpr auto valid_phase(Role role, ipc::Phase phase, std::uint64_t transaction) -> bool {
        if (role == Role::service)
            return phase == ipc::Phase::service && transaction != 0;
        if (role != Role::client)
            return false;
        return (phase == ipc::Phase::request && transaction == 0) ||
               (phase == ipc::Phase::completion && transaction != 0);
    }
    [[nodiscard]] static constexpr auto
    owned_contract(std::uint64_t arena, std::size_t domain, const user::ProgramContract &contract) -> bool {
        if (!Layout::valid(arena) || domain >= Layout::domain_count || !contract.valid())
            return false;
        const auto expected = user::ProgramLayout::create(Layout::code_begin(domain),
                                                          Layout::code_end(domain),
                                                          Layout::image_limit(domain) / Layout::page_size,
                                                          Layout::user_stack_begin(domain),
                                                          Layout::user_stack_end(domain),
                                                          arena + Layout::rsp0_bottom,
                                                          arena + Layout::rsp0_top);
        return expected && user::same_layout(*expected, contract.layout()) &&
               contract.entry() == Layout::code_begin(domain) && Layout::code_pages(domain, contract.size()) != 0;
    }
    [[nodiscard]] auto same_live_owner(const user::DomainRegistry &registry, user::DomainHandle owner) const -> bool {
        const auto retained = registry.index(owner_), current = registry.index(owner);
        return retained && current && *retained == *current;
    }

public:
    [[nodiscard]] static auto authorize(const user::DomainRegistry &registry,
                                        user::DomainHandle owner,
                                        Role role,
                                        ipc::Phase phase,
                                        std::size_t client,
                                        std::uint64_t transaction,
                                        std::uint64_t source_phase,
                                        std::uint64_t owned_arena,
                                        std::uint64_t actual_root,
                                        const user::ProgramContract &contract,
                                        std::uint64_t epoch,
                                        unsigned budget) -> std::optional<BoundedRunAuthority> {
        const auto domain = registry.index(owner);
        if (!domain || !registry.active(owner) || client >= (Domains == 2 ? 1U : 2U) || epoch == 0 || budget == 0 ||
            budget > maximum_budget || !valid_phase(role, phase, transaction) ||
            *domain != (role == Role::service ? 1
                        : client == 0         ? 0
                                              : 2) ||
            !owned_contract(owned_arena, *domain, contract) ||
            actual_root != owned_arena + Layout::table_offset(*domain))
            return std::nullopt;
        // source_phase is opaque kernel-selected launch data. Its value never
        // changes rights; Role and Phase alone select the checked relationship.
        return BoundedRunAuthority{
            owner, role, phase, client, transaction, source_phase, owned_arena, actual_root, contract, epoch, budget};
    }
    // Retained sessions have distinct startup/abort-only zero-transaction runs.
    // Reuse immutable storage, never broaden ordinary authorize()/valid_phase().
    // Stable lifetime, grant and backing-lease ownership remain adapter checks.
    [[nodiscard]] static auto authorize_retained_session(const user::DomainRegistry &registry,
                                                         user::DomainHandle owner,
                                                         Role role,
                                                         ipc::Phase phase,
                                                         std::size_t client,
                                                         std::uint64_t transaction,
                                                         std::uint64_t source_phase,
                                                         std::uint64_t owned_arena,
                                                         std::uint64_t actual_root,
                                                         const user::ProgramContract &contract,
                                                         std::uint64_t epoch,
                                                         unsigned budget) -> std::optional<BoundedRunAuthority> {
        // A body assertion avoids constrained-member ABI aliases in linked stack facts.
        static_assert(Domains == 2);
        const auto domain = registry.index(owner);
        if (!domain || !registry.active(owner) || client != 0 || epoch == 0 ||
            !owned_contract(owned_arena, *domain, contract) ||
            actual_root != owned_arena + Layout::table_offset(*domain))
            return std::nullopt;
        const bool caller =
            role == Role::client && *domain == 0 && phase == ipc::Phase::request && transaction == 0 && budget == 128;
        const bool service = role == Role::service && *domain == 1 && phase == ipc::Phase::service &&
                             ((source_phase == 2 && transaction != 0 && budget == 120) ||
                              ((source_phase == 1 || source_phase == 3) && transaction == 0 && budget == 8));
        if (!caller && !service)
            return std::nullopt;
        return BoundedRunAuthority{
            owner, role, phase, client, transaction, source_phase, owned_arena, actual_root, contract, epoch, budget};
    }
    // Use before accepting either a timer or a terminal user frame. Only after
    // this succeeds may the adapter capture ServiceContext under contract().
    [[nodiscard]] auto matches_active(const user::DomainRegistry &registry,
                                      user::DomainHandle owner,
                                      Role role,
                                      ipc::Phase phase,
                                      std::size_t client,
                                      std::uint64_t transaction,
                                      std::uint64_t source_phase,
                                      std::uint64_t owned_arena,
                                      std::uint64_t actual_root,
                                      const user::ProgramContract &contract,
                                      std::uint64_t epoch) const -> bool {
        return same_live_owner(registry, owner) && registry.active(owner_) && registry.active(owner) && role == role_ &&
               phase == phase_ && client == client_ && transaction == transaction_ && source_phase == source_phase_ &&
               owned_arena == arena_ && actual_root == root_ && user::same_contract(contract_, contract) &&
               epoch == epoch_;
    }
    // Narrow ownership evidence after deactivation, for pending-IRQ drain only.
    // This cannot authorize any user frame. The adapter separately proves the
    // kernel root, continuation PC, kernel stack, flags and interrupt state.
    [[nodiscard]] auto
    ready_owner(const user::DomainRegistry &registry, user::DomainHandle owner, std::uint64_t epoch) const -> bool {
        return same_live_owner(registry, owner) && registry.ready(owner_) && registry.ready(owner) && epoch == epoch_;
    }
    [[nodiscard]] constexpr auto owner() const -> user::DomainHandle {
        return owner_;
    }
    [[nodiscard]] constexpr auto role() const -> Role {
        return role_;
    }
    [[nodiscard]] constexpr auto phase() const -> ipc::Phase {
        return phase_;
    }
    [[nodiscard]] constexpr auto client() const -> std::size_t {
        return client_;
    }
    [[nodiscard]] constexpr auto transaction() const -> std::uint64_t {
        return transaction_;
    }
    [[nodiscard]] constexpr auto source_phase() const -> std::uint64_t {
        return source_phase_;
    }
    [[nodiscard]] constexpr auto owned_arena() const -> std::uint64_t {
        return arena_;
    }
    [[nodiscard]] constexpr auto root() const -> std::uint64_t {
        return root_;
    }
    [[nodiscard]] constexpr auto contract() const -> const user::ProgramContract & {
        return contract_;
    }
    [[nodiscard]] constexpr auto epoch() const -> std::uint64_t {
        return epoch_;
    }
    [[nodiscard]] constexpr auto budget() const -> unsigned {
        return budget_;
    }
};
using RunAuthority = BoundedRunAuthority<3>;
using ProgramRunAuthority = BoundedRunAuthority<2>;
} // namespace aurora::uefi
