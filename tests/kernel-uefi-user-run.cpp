#include "../kernel/uefi/user-run-policy.hpp"
#include "../kernel/uefi/service-budget-policy.hpp"
#include <array>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string_view>
#include <type_traits>

namespace kernel_uefi_user_run {
using namespace aurora::uefi;
using aurora::ipc::Phase;
using aurora::user::DomainHandle;
using aurora::user::DomainRegistry;
using aurora::user::ProgramContract;
using aurora::user::ProgramEvent;
using aurora::user::ProgramLayout;
using L = RuntimeLayoutProfile<3>;
using Role = RunAuthority::Role;
using U64 = std::uint64_t;
using Words = std::array<U64, ServiceContext::word_count>;
constexpr U64 arena = 0x2000000;
constexpr U64 maximum = std::numeric_limits<U64>::max();
constexpr U64 entry_bottom = arena + L::rsp0_bottom;
constexpr U64 entry_top = arena + L::rsp0_top;
constexpr U64 frame = entry_top - ServiceContext::byte_count;
static_assert(!std::is_default_constructible_v<RunAuthority> && !std::is_aggregate_v<RunAuthority>);
static_assert(!std::is_constructible_v<RunAuthority,
                                       DomainHandle,
                                       Role,
                                       Phase,
                                       std::size_t,
                                       U64,
                                       U64,
                                       U64,
                                       U64,
                                       const ProgramContract &,
                                       U64,
                                       unsigned>);
static_assert(std::is_copy_constructible_v<RunAuthority> && std::is_move_constructible_v<RunAuthority>);
static_assert(!std::is_copy_assignable_v<RunAuthority> && !std::is_move_assignable_v<RunAuthority>);
static_assert(std::is_same_v<decltype(std::declval<RunAuthority &>().contract()), const ProgramContract &>);
static_assert(std::is_same_v<decltype(std::declval<RunAuthority &>().owner()), DomainHandle>);
static_assert(RunAuthority::maximum_budget == 128);

unsigned checks{};
auto check(bool result, std::string_view message) -> void {
    ++checks;
    if (!result) {
        std::cerr << "FAIL: " << message << '\n';
        std::exit(1);
    }
}
auto layout(std::size_t domain, U64 owned = arena) -> ProgramLayout {
    const auto result = ProgramLayout::create(0x10000000000ULL + domain * 16384,
                                              0x10000000000ULL + domain * 16384 + 12288,
                                              L::image_limit(domain) / 4096,
                                              L::user_stack_begin(domain),
                                              L::user_stack_end(domain),
                                              owned + L::rsp0_bottom,
                                              owned + L::rsp0_top);
    check(result.has_value(), "valid contract layout fixture");
    return *result;
}
auto contract(std::size_t domain, U64 owned = arena) -> ProgramContract {
    const auto pc = L::user_code + domain * 16384;
    return ProgramContract{layout(domain, owned), pc, 128, pc + 32, pc + 64, pc + 66, pc + 68, pc + 70};
}
class Launch final {
public:
    DomainHandle owner;
    Role role;
    Phase phase;
    std::size_t client;
    U64 transaction, source_phase, owned_arena = arena, root, epoch = 17;
    unsigned budget = 128;
    std::optional<ProgramContract> program;
    Launch(DomainHandle handle, std::size_t domain)
        : owner(handle), role(domain == 1 ? Role::service : Role::client),
          phase(domain == 1 ? Phase::service : Phase::request), client(domain == 2 ? 1 : 0),
          transaction(domain == 1 ? 91 : 0), source_phase(domain == 1 ? 1 : 0), root(arena + L::table_offset(domain)),
          program(contract(domain)) {
    }
};
auto authorize(const DomainRegistry &registry, const Launch &launch) -> std::optional<RunAuthority> {
    return RunAuthority::authorize(registry,
                                   launch.owner,
                                   launch.role,
                                   launch.phase,
                                   launch.client,
                                   launch.transaction,
                                   launch.source_phase,
                                   launch.owned_arena,
                                   launch.root,
                                   *launch.program,
                                   launch.epoch,
                                   launch.budget);
}
auto matches(const RunAuthority &authority, const DomainRegistry &registry, const Launch &launch) -> bool {
    return authority.matches_active(registry,
                                    launch.owner,
                                    launch.role,
                                    launch.phase,
                                    launch.client,
                                    launch.transaction,
                                    launch.source_phase,
                                    launch.owned_arena,
                                    launch.root,
                                    *launch.program,
                                    launch.epoch);
}
auto handles(DomainRegistry &registry) -> std::array<DomainHandle, 3> {
    std::array<DomainHandle, 3> result{};
    for (auto &owner : result) {
        const auto created = registry.create();
        check(created.has_value(), "create three-domain fixture");
        owner = *created;
    }
    return result;
}
auto words(const ProgramContract &program, U64 vector = 64) -> Words {
    Words result{};
    for (unsigned reg = 0; reg < 15; ++reg)
        result[reg] = 0x9e3779b97f4a7c15ULL * (reg + 1);
    result[15] = vector;
    result[17] = program.entry();
    result[18] = 0x1b;
    result[19] = 0x202;
    result[20] = program.layout().user_stack_top();
    result[21] = 0x23;
    return result;
}

auto phase_matrix() -> void {
    DomainRegistry registry;
    const auto owners = handles(registry);
    for (std::size_t domain = 0; domain < 3; ++domain) {
        Launch launch{owners[domain], domain};
        check(!authorize(registry, launch), "ready owner cannot authorize a running frame");
        check(registry.activate(launch.owner), "activate matrix owner");
        for (const auto role : {Role::client, Role::service, static_cast<Role>(2)})
            for (const auto phase :
                 {Phase::inactive, Phase::request, Phase::service, Phase::completion, static_cast<Phase>(255)})
                for (const std::size_t client :
                     std::array<std::size_t, 4>{0, 1, 2, std::numeric_limits<std::size_t>::max()})
                    for (const U64 transaction : std::array<U64, 3>{0, 91, maximum}) {
                        auto candidate = launch;
                        candidate.role = role;
                        candidate.phase = phase;
                        candidate.client = client;
                        candidate.transaction = transaction;
                        const bool client_valid = role == Role::client && client < 2 &&
                                                  domain == (client == 0 ? 0U : 2U) &&
                                                  ((phase == Phase::request && transaction == 0) ||
                                                   (phase == Phase::completion && transaction != 0));
                        const bool service_valid = role == Role::service && domain == 1 && client < 2 &&
                                                   phase == Phase::service && transaction != 0;
                        const auto permit = authorize(registry, candidate);
                        check(permit.has_value() == (client_valid || service_valid),
                              "exhaustive role/domain/phase/client/transaction policy");
                        if (permit)
                            check(matches(*permit, registry, candidate),
                                  "authorized phase matches exact active identity");
                    }
        const auto permit = authorize(registry, launch);
        check(permit.has_value(), "canonical launch authorized");
        check(registry.index(permit->owner()) == registry.index(launch.owner) && permit->role() == launch.role &&
                  permit->phase() == launch.phase && permit->client() == launch.client &&
                  permit->transaction() == launch.transaction && permit->source_phase() == launch.source_phase &&
                  permit->owned_arena() == launch.owned_arena && permit->root() == launch.root &&
                  permit->epoch() == launch.epoch && permit->budget() == launch.budget,
              "all immutable launch fields retained");
        check(!permit->ready_owner(registry, launch.owner, launch.epoch), "active owner cannot enter ready drain path");
        for (unsigned budget = 0; budget <= 129; ++budget) {
            auto candidate = launch;
            candidate.budget = budget;
            check(authorize(registry, candidate).has_value() == (budget >= 1 && budget <= 128),
                  "every bounded budget and adjacent denial");
        }
        auto large_budget = launch;
        large_budget.budget = std::numeric_limits<unsigned>::max();
        check(!authorize(registry, large_budget), "wrapped or oversized budget denied");
        for (const auto source : std::array<U64, 9>{0, 1, 2, 3, 4, 5, 6, 7, maximum}) {
            auto candidate = launch;
            candidate.source_phase = source;
            const auto opaque = authorize(registry, candidate);
            check(opaque && matches(*opaque, registry, candidate),
                  "source phase is opaque kernel-selected launch data");
            candidate.source_phase ^= 1;
            check(!matches(*opaque, registry, candidate), "changed source phase never inherits run authority");
        }
        check(registry.deactivate(launch.owner), "deactivate matrix owner");
        check(!matches(*permit, registry, launch), "deactivation removes all user-frame authority");
        check(permit->ready_owner(registry, launch.owner, launch.epoch),
              "ready owner supplies only drain ownership evidence");
        check(!permit->ready_owner(registry, launch.owner, launch.epoch + 1) &&
                  !permit->ready_owner(registry, launch.owner, 0),
              "drain requires exact nonzero epoch");
    }
}

auto identity_and_metadata() -> void {
    DomainRegistry registry;
    const auto owners = handles(registry);
    for (std::size_t domain = 0; domain < 3; ++domain) {
        Launch launch{owners[domain], domain};
        check(registry.activate(launch.owner), "activate metadata owner");
        const auto permit = authorize(registry, launch);
        check(permit.has_value(), "metadata authority fixture");
        const auto deny = [&](auto mutation, std::string_view label) {
            auto candidate = launch;
            mutation(candidate);
            check(!authorize(registry, candidate), label);
            check(!matches(*permit, registry, candidate), label);
        };
        deny(
            [](Launch &candidate) {
                candidate.owner = DomainHandle{};
            },
            "default handle denied");
        for (const auto other : owners)
            if (registry.index(other) != registry.index(launch.owner))
                deny(
                    [&](Launch &candidate) {
                        candidate.owner = other;
                    },
                    "foreign inactive handle denied");
        deny(
            [](Launch &candidate) {
                candidate.role = static_cast<Role>(255);
            },
            "unknown role denied");
        deny(
            [](Launch &candidate) {
                candidate.phase = Phase::inactive;
            },
            "inactive launch denied");
        deny(
            [](Launch &candidate) {
                candidate.client = 2;
            },
            "out-of-bounds client denied");
        deny(
            [](Launch &candidate) {
                candidate.epoch = 0;
            },
            "zero run epoch denied");
        for (const U64 root : std::array<U64, 10>{0,
                                                  arena,
                                                  launch.root - 4096,
                                                  launch.root + 4096,
                                                  launch.root + 1,
                                                  arena + L::table_offset((domain + 1) % 3),
                                                  1ULL << 47,
                                                  0xffff800000000000ULL,
                                                  maximum - 4095,
                                                  maximum})
            deny(
                [&](Launch &candidate) {
                    candidate.root = root;
                },
                "root must equal exact owned table pool");
        for (const U64 base : std::array<U64, 10>{0,
                                                  0xff000,
                                                  arena + 1,
                                                  0xfffff000ULL,
                                                  0x100000000ULL,
                                                  (1ULL << 47) - 4096,
                                                  1ULL << 47,
                                                  0xffff800000000000ULL,
                                                  maximum - 4095,
                                                  maximum})
            deny(
                [&](Launch &candidate) {
                    candidate.owned_arena = base;
                },
                "invalid or mismatched arena interval denied");
        for (const U64 epoch : std::array<U64, 3>{1, 18, maximum}) {
            auto candidate = launch;
            candidate.epoch = epoch;
            check(authorize(registry, candidate).has_value() && !matches(*permit, registry, candidate),
                  "new valid epoch cannot reuse old run snapshot");
        }
        auto new_transaction = launch;
        new_transaction.transaction = 92;
        check(!matches(*permit, registry, new_transaction), "different nonzero transaction rejected by retained run");
        if (domain != 1) {
            auto completion = launch;
            completion.phase = Phase::completion;
            completion.transaction = 91;
            const auto completed = authorize(registry, completion);
            check(completed && !matches(*permit, registry, completion) && !matches(*completed, registry, launch),
                  "request and completion authority never interchange");
        } else {
            auto other_client = launch;
            other_client.client = 1;
            check(authorize(registry, other_client).has_value() && !matches(*permit, registry, other_client),
                  "service authority is confined to selected client");
        }
        const auto pc = launch.program->entry();
        const auto policy = launch.program->layout();
        for (const auto &changed :
             std::array{ProgramContract{policy, pc, 127, pc + 32, pc + 64, pc + 66, pc + 68, pc + 70},
                        ProgramContract{policy, pc, 128, pc + 34, pc + 64, pc + 66, pc + 68, pc + 70},
                        ProgramContract{policy, pc, 128, pc + 32, pc + 62, pc + 66, pc + 68, pc + 70},
                        ProgramContract{policy, pc, 128, pc + 32, pc + 64, pc + 72, pc + 68, pc + 70},
                        ProgramContract{policy, pc, 128, pc + 32, pc + 64, pc + 66, 0, pc + 70},
                        ProgramContract{policy, pc, 128, pc + 32, pc + 64, pc + 66, pc + 68, 0}}) {
            auto candidate = launch;
            candidate.program.emplace(changed);
            check(changed.valid() && authorize(registry, candidate).has_value(),
                  "altered metadata is independently valid");
            check(!matches(*permit, registry, candidate), "every metadata field participates in exact snapshot match");
        }
        for (const auto &changed :
             std::array{ProgramContract{policy, pc, 0, pc + 32, pc + 64, pc + 66},
                        ProgramContract{policy, pc, policy.max_image_size() + 1, pc + 32, pc + 64, pc + 66},
                        ProgramContract{policy, pc, maximum, pc + 32, pc + 64, pc + 66},
                        ProgramContract{policy, maximum, 128, pc + 32, pc + 64, pc + 66},
                        ProgramContract{policy, pc + 1, 128, pc + 32, pc + 64, pc + 66},
                        ProgramContract{policy, pc, 128, pc + 1, pc + 64, pc + 66},
                        ProgramContract{policy, pc, 128, pc + 127, pc + 64, pc + 66},
                        ProgramContract{policy, pc, 128, pc + 32, pc + 32, pc + 66},
                        ProgramContract{policy, pc, 128, pc + 32, pc + 64, pc + 64},
                        ProgramContract{policy, pc, 128, pc + 32, pc + 64, pc + 66, maximum},
                        ProgramContract{policy, pc, 128, pc + 32, pc + 64, pc + 66, pc + 68, pc + 68},
                        ProgramContract{pc, 128, pc + 32, pc + 64, pc + 66}})
            deny(
                [&](Launch &candidate) {
                    candidate.program.emplace(changed);
                },
                "invalid, duplicate, out-of-image or BIOS metadata denied");
        for (std::size_t other = 0; other < 3; ++other)
            if (other != domain)
                deny(
                    [&](Launch &candidate) {
                        candidate.program.emplace(contract(other));
                    },
                    "foreign image and stack contract denied");
        for (unsigned field = 0; field < 7; ++field) {
            U64 begin = 0x10000000000ULL + domain * 16384, end = begin + 12288, pages = L::image_limit(domain) / 4096;
            auto bottom = L::user_stack_begin(domain), top = L::user_stack_end(domain);
            U64 rsp0_bottom = entry_bottom, rsp0_top = entry_top;
            if (field == 0) {
                begin -= 4096;
                end -= 4096;
            }
            if (field == 1) {
                end -= 4096;
                if (pages > 2)
                    pages = 2;
            }
            if (field == 2)
                pages = 2;
            if (field == 3)
                bottom += 4096;
            if (field == 4)
                top -= 4096;
            if (field == 5)
                rsp0_bottom += 4096;
            if (field == 6)
                rsp0_top -= 4096;
            const auto changed_layout = ProgramLayout::create(begin, end, pages, bottom, top, rsp0_bottom, rsp0_top);
            check(changed_layout.has_value(), "altered layout remains valid as a generic policy");
            deny(
                [&](Launch &candidate) {
                    candidate.program.emplace(*changed_layout, pc, 128, pc + 32, pc + 64, pc + 66, pc + 68, pc + 70);
                },
                "every code, stack and frame layout bound must match owned profile");
        }
        auto mutable_launch = launch;
        const auto copied = authorize(registry, mutable_launch);
        mutable_launch.owner = DomainHandle{};
        mutable_launch.role = Role::client;
        mutable_launch.phase = Phase::inactive;
        mutable_launch.client = 2;
        mutable_launch.transaction = 0;
        mutable_launch.source_phase = maximum;
        mutable_launch.owned_arena = 0;
        mutable_launch.root = 0;
        mutable_launch.epoch = 0;
        mutable_launch.budget = 0;
        mutable_launch.program.reset();
        check(copied && matches(*copied, registry, launch),
              "snapshot survives source metadata mutation and destruction");
        const RunAuthority copied_again = *copied;
        check(matches(copied_again, registry, launch), "value copies preserve complete immutable authority");
        check(registry.deactivate(launch.owner), "deactivate metadata owner");
    }
    Launch old{owners[0], 0};
    check(registry.activate(old.owner), "activate stale owner fixture");
    const auto stale = authorize(registry, old);
    check(stale.has_value(), "capture stale owner fixture");
    check(registry.deactivate(old.owner) && registry.destroy(old.owner), "retire original domain incarnation");
    const auto replacement = registry.create();
    check(replacement && registry.index(*replacement) == 0, "reuse original domain slot");
    check(!stale->ready_owner(registry, *replacement, old.epoch) && !stale->ready_owner(registry, old.owner, old.epoch),
          "ready drain rejects destroyed and replacement incarnations");
    check(registry.activate(*replacement), "activate new incarnation");
    check(!authorize(registry, old) && !matches(*stale, registry, old), "stale handle cannot mint or retain authority");
    auto reborn = old;
    reborn.owner = *replacement;
    check(authorize(registry, reborn).has_value() && !matches(*stale, registry, reborn),
          "new incarnation cannot revive captured authority");
    DomainRegistry foreign;
    const auto strangers = handles(foreign);
    Launch foreign_launch{strangers[0], 0};
    check(foreign.activate(foreign_launch.owner), "activate foreign registry");
    check(!matches(*stale, foreign, foreign_launch) && !matches(*stale, foreign, old),
          "separate registries cannot substitute slot identities");
    std::optional<DomainRegistry> reincarnated{std::in_place};
    const auto original_handle = reincarnated->create();
    check(original_handle.has_value(), "registry rebirth owner");
    Launch original{*original_handle, 0};
    check(reincarnated->activate(original.owner), "activate rebirth fixture");
    const auto retained = authorize(*reincarnated, original);
    check(retained.has_value(), "retain registry rebirth fixture");
    reincarnated.reset();
    reincarnated.emplace();
    const auto reborn_handle = reincarnated->create();
    check(reborn_handle.has_value(), "replacement registry owner");
    Launch replacement_launch{*reborn_handle, 0};
    check(reincarnated->activate(*reborn_handle), "activate replacement registry");
    check(!matches(*retained, *reincarnated, replacement_launch) && !authorize(*reincarnated, original),
          "registry reconstruction at same address cannot revive old handles");
}

auto checked_frames() -> void {
    DomainRegistry registry;
    const auto owners = handles(registry);
    for (std::size_t domain = 0; domain < 3; ++domain) {
        Launch launch{owners[domain], domain};
        check(registry.activate(launch.owner), "activate frame owner");
        const auto permit = authorize(registry, launch);
        check(permit.has_value(), "frame run authority fixture");
        const auto &program = permit->contract();
        const auto original = words(program);
        const auto capture = [&](std::span<const U64> source, U64 location = frame) -> std::optional<ServiceContext> {
            if (!matches(*permit, registry, launch))
                return std::nullopt;
            return ServiceContext::capture(source, location, permit->contract());
        };
        const auto snapshot = capture(original);
        check(snapshot && snapshot->timer_frame(program) && snapshot->words() == original && snapshot->frame() == frame,
              "all controlled domains capture exact IRQ snapshots");
        if (domain != 1) {
            auto completion = launch;
            completion.phase = Phase::completion;
            completion.transaction = 91;
            completion.source_phase = 7;
            completion.budget = 3;
            const auto completion_run = authorize(registry, completion);
            check(completion_run && matches(*completion_run, registry, completion),
                  "completion run owns its independent timer budget");
            const auto completion_irq = ServiceContext::capture(original, frame, completion_run->contract());
            auto terminal_words = original;
            terminal_words[15] = 129;
            terminal_words[17] = program.return_pc();
            const auto completion_terminal = ServiceContext::capture(terminal_words, frame, completion_run->contract());
            check(completion_irq && completion_irq->timer_frame(completion_run->contract()) && completion_terminal &&
                      completion_terminal->terminal(completion_run->contract()) == ProgramEvent::returned,
                  "both client completion phases support unchanged timer and exact terminal contracts");
            check(!matches(*completion_run, registry, launch) && !matches(*permit, registry, completion),
                  "even identical physical frames require the currently selected run phase");
        }
        check(!snapshot->terminal_context(program) && snapshot->terminal(program) == ProgramEvent::rejected,
              "IRQ snapshot cannot classify as a terminal frame");
        for (unsigned reg = 0; reg < 15; ++reg)
            for (unsigned bit = 0; bit < 64; ++bit) {
                auto source = original;
                source[reg] ^= 1ULL << bit;
                const auto saved = capture(source);
                check(saved && saved->words() == source, "all 15 GPRs retain every bit, without scalar interpretation");
                source.fill(0);
                check(saved->words()[reg] == (original[reg] ^ (1ULL << bit)) && saved->timer_frame(program),
                      "saved GPRs own values after caller storage changes");
            }
        for (unsigned word = 0; word < ServiceContext::word_count; ++word) {
            auto source = original;
            const auto saved = capture(source);
            source[word] ^= maximum;
            check(saved && saved->words() == original, "all 22 captured words are immutable snapshots");
        }
        for (std::size_t length = 0; length < ServiceContext::word_count; ++length)
            check(!capture(std::span{original}.first(length)), "every truncated frame denied");
        std::array<U64, 23> longer{};
        for (std::size_t i = 0; i < original.size(); ++i)
            longer[i] = original[i];
        check(!capture(longer), "extended frame denied");
        for (U64 location = entry_bottom; location <= frame; location += 8)
            check(capture(original, location).has_value(), "every complete aligned owned RSP0 frame admitted");
        for (const auto location : std::array<U64, 12>{0,
                                                       entry_bottom - 8,
                                                       entry_bottom + 1,
                                                       frame + 1,
                                                       frame + 8,
                                                       entry_top,
                                                       entry_top + 8,
                                                       0x85f50,
                                                       1ULL << 47,
                                                       0xffff800000000000ULL,
                                                       maximum - 175,
                                                       maximum})
            check(!capture(original, location), "truncated, misaligned, foreign or wrapped frame interval denied");
        for (unsigned bit = 0; bit < 64; ++bit) {
            auto source = original;
            source[19] |= 1ULL << bit;
            check(capture(source).has_value() == ((ServiceContext::allowed_flags & (1ULL << bit)) != 0),
                  "all RFLAGS bits retain existing whitelist");
            source = original;
            source[16] = 1ULL << bit;
            check(!capture(source), "all nonzero error bits rejected");
        }
        for (const auto required : std::array<U64, 2>{2, 0x200}) {
            auto source = original;
            source[19] &= ~required;
            check(!capture(source), "bit1 and original enabled interrupt flag required");
        }
        for (const auto vector : std::array<U64, 9>{0, 8, 13, 14, 32, 63, 65, 128, maximum}) {
            auto source = original;
            source[15] = vector;
            check(!capture(source), "unknown and kernel fault vectors remain rejected");
        }
        for (const auto selector : std::array<U64, 7>{0, 8, 0x18, 0x19, 0x1a, 0x1001b, maximum}) {
            auto source = original;
            source[18] = selector;
            check(!capture(source), "exact ring3 code selector required");
        }
        for (const auto selector : std::array<U64, 7>{0, 0x10, 0x20, 0x21, 0x22, 0x10023, maximum}) {
            auto source = original;
            source[21] = selector;
            check(!capture(source), "exact ring3 stack selector required");
        }
        for (U64 offset = 0; offset < program.size(); ++offset) {
            auto source = original;
            source[17] = program.entry() + offset;
            check(capture(source).has_value(), "every owned image byte is a valid interrupted PC");
        }
        for (const auto pc : std::array<U64, 6>{0,
                                                program.entry() - 1,
                                                program.entry() + program.size(),
                                                program.entry() + 4096,
                                                1ULL << 47,
                                                maximum}) {
            auto source = original;
            source[17] = pc;
            check(!capture(source), "PC outside exact image denied");
        }
        for (auto sp = program.layout().user_stack_bottom(); sp <= program.layout().user_stack_top(); sp += 8) {
            auto source = original;
            source[20] = sp;
            check(capture(source).has_value(), "every aligned stack position admitted");
        }
        for (const auto sp : std::array<U64, 8>{0,
                                                program.layout().user_stack_bottom() - 8,
                                                program.layout().user_stack_bottom() + 1,
                                                program.layout().user_stack_top() + 1,
                                                program.layout().user_stack_top() + 8,
                                                L::user_stack_begin((domain + 1) % 3),
                                                1ULL << 47,
                                                maximum}) {
            auto source = original;
            source[20] = sp;
            check(!capture(source), "unowned or misaligned user stacks denied");
        }
        for (unsigned event = 0; event < 5; ++event) {
            auto source = original;
            source[15] = event == 0 ? 129 : 6;
            const std::array pcs{program.return_pc(),
                                 program.bounds_pc(),
                                 program.overflow_pc(),
                                 program.division_zero_pc(),
                                 program.shift_count_pc()};
            const std::array events{ProgramEvent::returned,
                                    ProgramEvent::bounds,
                                    ProgramEvent::overflow,
                                    ProgramEvent::division_zero,
                                    ProgramEvent::shift_count};
            source[17] = pcs[event];
            const auto terminal = capture(source);
            check(terminal && terminal->terminal(program) == events[event] && !terminal->timer_frame(program),
                  "every known exact compiler terminal site remains classified");
            check(terminal->words()[19] == 0x202, "terminal IF normalization never changes captured flags");
            source[19] |= 0x400;
            const auto direction = capture(source);
            check(direction && direction->terminal(program) == ProgramEvent::rejected, "terminal DF remains rejected");
        }
        auto source = original;
        source[19] = ServiceContext::allowed_flags;
        const auto direction = capture(source);
        check(direction && direction->timer_frame(program) && direction->words() == source,
              "IRQ keeps arithmetic flags, RF and DF exactly");
        source = original;
        source[15] = 129;
        source[17] = program.return_pc() + 2;
        const auto wrong_site = capture(source);
        check(wrong_site && wrong_site->terminal(program) == ProgramEvent::rejected,
              "return vector alone grants no terminal authority");
        source[17] = program.return_pc();
        source[20] -= 8;
        const auto wrong_stack = capture(source);
        check(wrong_stack && wrong_stack->terminal(program) == ProgramEvent::rejected,
              "successful return still requires exact stack top");
        for (std::size_t other = 0; other < 3; ++other)
            if (other != domain)
                check(!capture(words(contract(other))), "foreign program frames cannot cross domain authority");
        check(registry.deactivate(launch.owner), "deactivate frame owner");
        check(!capture(original) && permit->ready_owner(registry, launch.owner, launch.epoch),
              "ready drain ownership cannot authorize any former user frame");
    }
}

auto arena_and_interval_boundaries() -> void {
    DomainRegistry registry;
    const auto owners = handles(registry);
    check(registry.activate(owners[0]), "activate interval owner");
    for (const auto base : std::array<U64, 4>{0x100000, arena, 0x80000000, 0xfff00000}) {
        Launch launch{owners[0], 0};
        launch.owned_arena = base;
        launch.root = base + L::table_offset(0);
        launch.program.emplace(contract(0, base));
        const auto permit = authorize(registry, launch);
        check(permit && matches(*permit, registry, launch),
              "relocated arena boundaries preserve exact owned authority");
        const auto source = words(permit->contract());
        check(ServiceContext::capture(source, base + L::rsp0_top - ServiceContext::byte_count, permit->contract())
                  .has_value(),
              "relocated owned frame validates with snapshot contract");
    }
    for (const auto range : std::array<std::array<U64, 2>, 9>{{{0, 0},
                                                               {1, 4096},
                                                               {4096, 1},
                                                               {1ULL << 47, 4096},
                                                               {(1ULL << 47) - 4096, 8192},
                                                               {maximum - 4095, 4096},
                                                               {0, maximum},
                                                               {0x1000, maximum - 4095},
                                                               {0x1000, 0}}})
        check(!L::valid_interval(range[0], range[1]),
              "untrusted intervals reject alignment, emptiness, wrap and canonical overflow");
    check(L::valid_interval((1ULL << 47) - 4096, 4096), "half-open canonical boundary interval remains valid");
    check(!ProgramLayout::create(
              L::user_code, L::user_code + 4096, 1, L::user_stack_bottom, L::user_stack_top, maximum - 4095, 4096),
          "wrapped entry stack rejected before constructing contract");
}

auto image_extent_authority() -> void {
    DomainRegistry registry;
    const auto owners = handles(registry);
    for (std::size_t domain = 0; domain < 3; ++domain) {
        check(registry.activate(owners[domain]), "activate extent owner");
        const U64 pc = 0x10000000000ULL + domain * 16384;
        U64 allowed = 4096;
#ifdef AURORA_RUNTIME_MULTIPAGE
        allowed = 12288;
#endif
        check(L::image_limit(domain) == allowed, "independent per-image allowance");
        for (const U64 size : {4ULL, 4096ULL, 4097ULL, 8192ULL, 8193ULL, 12288ULL, 12289ULL}) {
            Launch candidate{owners[domain], domain};
            // Place every terminal inside even the shortest accepted image.
            candidate.program.emplace(layout(domain), pc, size, pc + 2, pc, pc + 1, 0, 0);
            check(authorize(registry, candidate).has_value() == (size <= allowed),
                  "exact size admitted only by selected image allowance");
        }
        const auto enlarged = ProgramLayout::create(pc,
                                                    pc + 12288,
                                                    allowed == 4096 ? 3 : 1,
                                                    L::user_stack_begin(domain),
                                                    L::user_stack_end(domain),
                                                    entry_bottom,
                                                    entry_top);
        check(enlarged.has_value(), "generic alternate image allowance fixture");
        Launch forged{owners[domain], domain};
        forged.program.emplace(*enlarged, pc, 128, pc + 32, pc + 64, pc + 66, pc + 68, pc + 70);
        check(!authorize(registry, forged), "metadata cannot change selected image allowance");
        check(registry.deactivate(owners[domain]), "deactivate extent owner");
    }
    check(ProgramLayout::bios().max_image_pages() == 1, "BIOS retains one-page image allowance");
}

auto main() -> int {
    image_extent_authority();
    phase_matrix();
    identity_and_metadata();
    checked_frames();
    arena_and_interval_boundaries();
    std::cout << "PASS: " << checks
              << " UEFI immutable user-run authority, exact origins and adversarial frame checks\n";
    return 0;
}
} // namespace kernel_uefi_user_run
