#include "../kernel/uefi/user-run-policy.hpp"
#include <cstdlib>
#include <iostream>
using namespace aurora;
using A = uefi::ProgramRunAuthority;
using L = uefi::RuntimeLayoutProfile<2>;
using U = std::uint64_t;
constexpr U arena = 0x2000000;
unsigned count;
auto check(bool okay) -> void {
    ++count;
    if (!okay)
        std::abort();
}
auto contract(unsigned domain) -> user::ProgramContract {
    const auto layout = user::ProgramLayout::create(L::user_code,
                                                    L::user_code + L::image_pages * 4096,
                                                    1,
                                                    L::user_stack_begin(domain),
                                                    L::user_stack_end(domain),
                                                    arena + L::rsp0_bottom,
                                                    arena + L::rsp0_top);
    check(layout.has_value());
    const auto pc = L::user_code + domain * 4096;
    return user::ProgramContract{*layout, pc, 128, pc + 32, pc + 64, pc + 66, pc + 68, pc + 70};
}
auto main() -> int {
    user::DomainRegistry registry;
    const auto c = registry.create(), s = registry.create(), third = registry.create();
    check(c && s && third);
    const std::array<user::DomainHandle, 3> owners{*c, *s, *third};
    for (unsigned domain = 0; domain < 3; ++domain) {
        check(registry.activate(owners[domain]));
        const auto image = contract(domain == 2 ? 0 : domain);
        for (const auto role : {A::Role::client, A::Role::service, static_cast<A::Role>(2)})
            for (const auto phase :
                 {ipc::Phase::inactive, ipc::Phase::request, ipc::Phase::service, ipc::Phase::completion})
                for (const U client : std::array<U, 4>{0, 1, 2, UINT64_MAX})
                    for (const U transaction : std::array<U, 3>{0, 1, UINT64_MAX}) {
                        const bool expected =
                            client == 0 && ((domain == 0 && role == A::Role::client &&
                                             ((phase == ipc::Phase::request && transaction == 0) ||
                                              (phase == ipc::Phase::completion && transaction != 0))) ||
                                            (domain == 1 && role == A::Role::service && phase == ipc::Phase::service &&
                                             transaction != 0));
                        const auto authority = A::authorize(registry,
                                                            owners[domain],
                                                            role,
                                                            phase,
                                                            client,
                                                            transaction,
                                                            0,
                                                            arena,
                                                            arena + L::table_offset(domain),
                                                            image,
                                                            1,
                                                            128);
                        check(authority.has_value() == expected);
                        if (authority) {
                            check(authority->matches_active(registry,
                                                            owners[domain],
                                                            role,
                                                            phase,
                                                            client,
                                                            transaction,
                                                            0,
                                                            arena,
                                                            arena + L::table_offset(domain),
                                                            image,
                                                            1));
                            check(!authority->matches_active(registry,
                                                             owners[domain],
                                                             role,
                                                             phase,
                                                             client,
                                                             transaction,
                                                             0,
                                                             arena,
                                                             arena + L::table_offset(domain),
                                                             image,
                                                             2));
                            check(!authority->matches_active(registry,
                                                             owners[domain],
                                                             role,
                                                             phase,
                                                             client,
                                                             transaction,
                                                             0,
                                                             arena,
                                                             arena + L::table_offset(domain) + 4096,
                                                             image,
                                                             1));
                        }
                    }
        check(registry.deactivate(owners[domain]));
    }
    const auto image = contract(0);
    check(registry.activate(*c));
    for (const unsigned budget : {0U, 129U, UINT32_MAX})
        check(!A::authorize(registry,
                            *c,
                            A::Role::client,
                            ipc::Phase::request,
                            0,
                            0,
                            0,
                            arena,
                            arena + L::table_offset(0),
                            image,
                            1,
                            budget));
    check(!A::authorize(
        registry, *c, A::Role::client, ipc::Phase::request, 0, 0, 0, arena, arena + L::table_offset(0), image, 0, 1));
    const auto authority = A::authorize(
        registry, *c, A::Role::client, ipc::Phase::request, 0, 0, 0, arena, arena + L::table_offset(0), image, 1, 1);
    check(authority.has_value());
    check(!authority->ready_owner(registry, *c, 1));
    check(registry.deactivate(*c));
    check(authority->ready_owner(registry, *c, 1));
    check(!authority->ready_owner(registry, *c, 2));
    check(registry.destroy(*c));
    const auto fresh = registry.create();
    check(fresh.has_value());
    check(!authority->ready_owner(registry, *fresh, 1));
    std::cout << "PASS: two-domain immutable run authority (" << count << " checks)\n";
}
