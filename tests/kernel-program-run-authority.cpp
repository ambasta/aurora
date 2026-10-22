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
    const auto layout = user::ProgramLayout::create(L::user_code + domain * 16384,
                                                    L::user_code + domain * 16384 + 12288,
                                                    L::image_limit(domain) / 4096,
                                                    L::user_stack_begin(domain),
                                                    L::user_stack_end(domain),
                                                    arena + L::rsp0_bottom,
                                                    arena + L::rsp0_top);
    check(layout.has_value());
    const auto pc = L::user_code + domain * 16384;
    return user::ProgramContract{*layout, pc, 128, pc + 32, pc + 64, pc + 66, pc + 68, pc + 70};
}
auto retained_service_authority() -> void {
    using R = uefi::ProgramRunAuthority;
    user::DomainRegistry registry, foreign;
    const auto caller = registry.create(), service = registry.create(), outsider = foreign.create();
    check(caller && service && outsider);
    check(registry.activate(*service));
    const auto image = contract(1);
    for (U purpose = 0; purpose <= 5; ++purpose)
        for (const U transaction : std::array<U, 3>{0, 1, UINT64_MAX})
            for (const unsigned budget : {0U, 1U, 8U, 120U, 128U, 129U}) {
                const bool accepted = ((purpose == 1 || purpose == 3) && transaction == 0 && budget == 8) ||
                                      (purpose == 2 && transaction != 0 && budget == 120);
                const auto run = R::authorize_retained_session(registry,
                                                               *service,
                                                               R::Role::service,
                                                               ipc::Phase::service,
                                                               0,
                                                               transaction,
                                                               purpose,
                                                               arena,
                                                               arena + L::table_offset(1),
                                                               image,
                                                               1,
                                                               budget);
                check(run.has_value() == accepted);
                if (!run)
                    continue;
                check(run->matches_active(registry,
                                          *service,
                                          R::Role::service,
                                          ipc::Phase::service,
                                          0,
                                          transaction,
                                          purpose,
                                          arena,
                                          arena + L::table_offset(1),
                                          image,
                                          1));
                check(!run->matches_active(registry,
                                           *service,
                                           R::Role::service,
                                           ipc::Phase::service,
                                           0,
                                           transaction,
                                           purpose,
                                           arena,
                                           arena + L::table_offset(0),
                                           image,
                                           1));
                check(!run->matches_active(registry,
                                           *service,
                                           R::Role::service,
                                           ipc::Phase::service,
                                           0,
                                           transaction,
                                           purpose,
                                           arena,
                                           arena + L::table_offset(1),
                                           image,
                                           2));
                check(!run->matches_active(registry,
                                           *outsider,
                                           R::Role::service,
                                           ipc::Phase::service,
                                           0,
                                           transaction,
                                           purpose,
                                           arena,
                                           arena + L::table_offset(1),
                                           image,
                                           1));
                const user::ProgramContract changed{image.layout(),
                                                    image.entry(),
                                                    image.size() + 1,
                                                    image.return_pc(),
                                                    image.bounds_pc(),
                                                    image.overflow_pc(),
                                                    image.division_zero_pc(),
                                                    image.shift_count_pc()};
                check(!run->matches_active(registry,
                                           *service,
                                           R::Role::service,
                                           ipc::Phase::service,
                                           0,
                                           transaction,
                                           purpose,
                                           arena,
                                           arena + L::table_offset(1),
                                           changed,
                                           1));
            }
    check(!R::authorize_retained_session(registry,
                                         *service,
                                         R::Role::service,
                                         ipc::Phase::service,
                                         0,
                                         0,
                                         1,
                                         arena,
                                         arena + L::table_offset(1),
                                         image,
                                         0,
                                         8));
    check(!R::authorize_retained_session(registry,
                                         *service,
                                         R::Role::client,
                                         ipc::Phase::request,
                                         0,
                                         0,
                                         1,
                                         arena,
                                         arena + L::table_offset(1),
                                         image,
                                         1,
                                         128));
    const auto run = R::authorize_retained_session(registry,
                                                   *service,
                                                   R::Role::service,
                                                   ipc::Phase::service,
                                                   0,
                                                   0,
                                                   3,
                                                   arena,
                                                   arena + L::table_offset(1),
                                                   image,
                                                   1,
                                                   8);
    check(run.has_value() && !run->ready_owner(registry, *service, 1));
    // Last two monotonically reserved identities: a caller can consume MAX
    // without preventing the already reserved MAX-1 abort-only activation.
    const auto cleanup_epoch = ipc::detail::generation_after(UINT64_MAX - 2, UINT64_MAX);
    const auto caller_epoch = ipc::detail::generation_after(*cleanup_epoch, UINT64_MAX);
    check(cleanup_epoch == UINT64_MAX - 1 && caller_epoch == UINT64_MAX &&
          !ipc::detail::generation_after(*caller_epoch, UINT64_MAX));
    const auto cleanup_run = R::authorize_retained_session(registry,
                                                           *service,
                                                           R::Role::service,
                                                           ipc::Phase::service,
                                                           0,
                                                           0,
                                                           3,
                                                           arena,
                                                           arena + L::table_offset(1),
                                                           image,
                                                           *cleanup_epoch,
                                                           8);
    check(cleanup_run && cleanup_run->epoch() == UINT64_MAX - 1 && cleanup_run->budget() == 8);
    check(!R::authorize_retained_session(registry,
                                         *service,
                                         R::Role::service,
                                         ipc::Phase::service,
                                         0,
                                         1,
                                         3,
                                         arena,
                                         arena + L::table_offset(1),
                                         image,
                                         *cleanup_epoch,
                                         120));
    check(registry.deactivate(*service));
    check(run->ready_owner(registry, *service, 1));
    check(registry.destroy(*service));
    const auto replacement = registry.create();
    check(replacement && !run->ready_owner(registry, *replacement, 1));
    check(registry.activate(*caller));
    const auto client_image = contract(0);
    check(R::authorize_retained_session(registry,
                                        *caller,
                                        R::Role::client,
                                        ipc::Phase::request,
                                        0,
                                        0,
                                        UINT64_MAX,
                                        arena,
                                        arena + L::table_offset(0),
                                        client_image,
                                        2,
                                        128)
              .has_value());
    for (const auto budget : {8U, 120U, 129U})
        check(!R::authorize_retained_session(registry,
                                             *caller,
                                             R::Role::client,
                                             ipc::Phase::request,
                                             0,
                                             0,
                                             1,
                                             arena,
                                             arena + L::table_offset(0),
                                             client_image,
                                             2,
                                             budget));
}

auto main() -> int {
    retained_service_authority();
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
