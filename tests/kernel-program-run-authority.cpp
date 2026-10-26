#include "../kernel/uefi/user-run-policy.hpp"
#include "../kernel/uefi/service-budget-policy.hpp"
#include "../kernel/uefi/handoff.hpp"
#include <memory>
#include <type_traits>
#include <cstdlib>
#include <iostream>

namespace kernel_program_run_authority {
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
// Exercise the same concrete owner as the adapter, in the existing component driver.
// The fixture friend can inspect fields only after the real family/capacity gates.
using uefi::Bytes;
using uefi::ProgramRunAuthority;
using uefi::ServiceContext;
using U64 = std::uint64_t;
constexpr std::size_t launch_words = 7;
#include "../kernel/uefi/parked-run.inc"
#define AURORA_CALLER_CONTINUATION_TESTING
#include "../kernel/uefi/caller-continuation.inc"
#undef AURORA_CALLER_CONTINUATION_TESTING
static_assert(!std::is_copy_constructible_v<CallerContinuation> && !std::is_move_constructible_v<CallerContinuation>);
static_assert(!std::is_copy_assignable_v<CallerContinuation> && !std::is_move_assignable_v<CallerContinuation>);
static_assert(!std::is_copy_constructible_v<ParkedRun> && !std::is_move_constructible_v<ParkedRun>);
constinit CallerContinuation initial_caller;
class CallerContinuationProbe final {
    using Kind = CallerContinuation::Kind;
    static auto slot(CallerContinuation &owner, Kind kind, bool empty = false) -> ParkedRun * {
        if (kind == Kind::ordinary)
            return !empty || owner.ordinary_empty() ? owner.ordinary() : nullptr;
        return !empty || owner.ram_empty() ? owner.ram() : nullptr;
    }
    static auto scrubbed(const ParkedRun &run) -> bool {
        const auto *bytes = reinterpret_cast<const unsigned char *>(&run);
        for (std::size_t i = 0; i < sizeof(run); ++i)
            if (bytes[i])
                return false;
        return true;
    }

public:
    static auto run() -> void {
        check(!initial_caller.ordinary() && !initial_caller.ram() && !initial_caller.ordinary_empty() &&
              !initial_caller.ram_empty());
        for (const auto kind : {Kind::none, Kind::ordinary, Kind::ram}) {
            CallerContinuation owner;
            check(!owner.initialize(Kind::uninitialized));
            check(owner.initialize(kind));
            for (const auto retry : {Kind::uninitialized, Kind::none, Kind::ordinary, Kind::ram})
                check(!owner.initialize(retry));
            check(bool(owner.ordinary()) == (kind == Kind::ordinary));
            check(bool(owner.ram()) == (kind == Kind::ram));
            check(bool(owner.ordinary_empty()) == (kind == Kind::ordinary));
            check(bool(owner.ram_empty()) == (kind == Kind::ram));
            if (kind == Kind::none)
                continue;
            const auto wrong = kind == Kind::ordinary ? Kind::ram : Kind::ordinary;
            user::DomainRegistry registry;
            const auto caller = registry.create(), service = registry.create();
            check(caller && service && registry.activate(*caller));
            const auto image = contract(0);
            const auto authority = A::authorize(registry,
                                                *caller,
                                                A::Role::client,
                                                ipc::Phase::request,
                                                0,
                                                0,
                                                16,
                                                arena,
                                                arena + L::table_offset(0),
                                                image,
                                                17,
                                                128);
            check(authority.has_value());
            std::array<U64, ServiceContext::word_count> words{};
            for (unsigned i = 0; i < 15; ++i)
                words[i] = UINT64_MAX - i;
            words[15] = 130;
            words[17] = image.entry() + 80;
            words[18] = 0x1b;
            words[19] = 0x202;
            words[20] = image.layout().user_stack_top() - 8;
            words[21] = 0x23;
            const auto context = ServiceContext::capture_call(
                words, image.layout().entry_stack_top() - ServiceContext::byte_count, image, words[17]);
            check(context.has_value());
            check(registry.deactivate(*caller));
            ipc::Mailbox mailbox(registry);
            check(mailbox.bind(*caller, *service));
            const auto ce = mailbox.endpoint(*caller), se = mailbox.endpoint(*service);
            check(ce && se);
            U64 previous = 0;
            for (unsigned round = 0; round < 3; ++round) {
                check(slot(owner, kind, true) && !slot(owner, wrong) && !slot(owner, wrong, true));
                const auto ticket = mailbox.submit(*caller, ipc::Phase::request, *ce, ipc::Request{round, 0});
                check(ticket && *ticket > previous);
                {
                    auto &saved = *slot(owner, kind, true);
                    saved.context.emplace(*context);
                    saved.authority.emplace(*authority);
                    saved.service = *service;
                    saved.endpoint = *ce;
                    saved.ticket = *ticket;
                    saved.launch = {16, 0, ce->slot(), ce->generation(), 0, 0, 0x202};
                    saved.remaining = 127;
                    saved.ticks = 1;
                    saved.resumes = 2;
                    saved.compiled = 3;
                    saved.contexts = 4;
                }
                check(!slot(owner, kind, true) && !slot(owner, wrong) && !slot(owner, wrong, true));
                for (const auto retry : {Kind::none, Kind::ordinary, Kind::ram})
                    check(!owner.initialize(retry));
                check(slot(owner, kind)->context->words() == words && slot(owner, kind)->ticket == *ticket);
                check(!mailbox.consume(*caller, ipc::Phase::completion, *ce, previous));
                const auto request = mailbox.receive(*service, ipc::Phase::service, *se, *ticket);
                check(request && request->first() == round);
                check(mailbox.reply(*service, ipc::Phase::service, *se, *ticket, round + 1));
                const auto reply = mailbox.consume(*caller, ipc::Phase::completion, *ce, *ticket);
                check(reply && reply->value() == round + 1);
                check(slot(owner, kind)->authority->ready_owner(registry, *caller, 17));
                check(slot(owner, kind)->context->call_frame(image, words[17]));
                slot(owner, kind)->clear();
                check(slot(owner, kind, true) && scrubbed(*slot(owner, kind)));
                check(!slot(owner, wrong) && !owner.initialize(wrong));
                check(!mailbox.consume(*caller, ipc::Phase::completion, *ce, *ticket));
                check(mailbox.recycle(ipc::Phase::inactive));
                previous = *ticket;
            }
            // Every accounting field and launch word independently prevents capture.
            constexpr std::array accounting{&ParkedRun::remaining,
                                            &ParkedRun::ticks,
                                            &ParkedRun::resumes,
                                            &ParkedRun::compiled,
                                            &ParkedRun::contexts};
            for (const auto field : accounting) {
                slot(owner, kind)->*field = 1;
                check(!slot(owner, kind, true));
                slot(owner, kind)->clear();
                check(slot(owner, kind, true) && scrubbed(*slot(owner, kind)));
            }
            for (std::size_t i = 0; i < launch_words; ++i) {
                slot(owner, kind)->launch[i] = UINT64_MAX;
                check(!slot(owner, kind, true));
                slot(owner, kind)->clear();
            }
            slot(owner, kind)->ticket = previous;
            check(!slot(owner, kind, true));
            slot(owner, kind)->clear();
            slot(owner, kind)->endpoint = *ce;
            check(!slot(owner, kind, true));
            slot(owner, kind)->clear();
            slot(owner, kind)->service = *service;
            check(!slot(owner, kind, true));
            slot(owner, kind)->clear();
            slot(owner, kind)->authority.emplace(*authority);
            check(!slot(owner, kind, true));
            slot(owner, kind)->clear();
            slot(owner, kind)->context.emplace(*context);
            check(!slot(owner, kind, true));
            slot(owner, kind)->clear();
            check(slot(owner, kind, true) && scrubbed(*slot(owner, kind)));
            check(mailbox.revoke(ipc::Phase::inactive) && registry.destroy(*caller));
            const auto fresh = registry.create();
            check(fresh && !authority->ready_owner(registry, *fresh, 17));
            check(slot(owner, kind, true) && !slot(owner, wrong) && !owner.initialize(kind));
        }
    }
};

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
    CallerContinuationProbe::run();
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
    return 0;
}
} // namespace kernel_program_run_authority
