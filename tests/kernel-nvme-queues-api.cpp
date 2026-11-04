// CPU preparation handles, the real compiled Aurora transport owner, and its
// synchronous native adapter. Hosted contexts are observations, not device proof.
#include "../kernel/uefi/nvme-queues.hpp"
#include <type_traits>
#include <cstdio>
#include <cstdlib>
#include "../kernel/uefi/nvme-transport.hpp"
#include "../kernel/retained-nvme-transport.hpp"
#include <sys/wait.h>
#include <unistd.h>

namespace kernel_nvme_queues_api {
using namespace aurora::uefi;
template <class T>
concept Inject = requires(T &q) { q.fail_scrub_for_test(0); };
template <class T>
concept Address = requires(T &q, NvmeQueueHandle h) { q.address(h); };
template <class T>
concept Publish = requires(T &q, NvmeQueueHandle h) { q.publish(h); };
template <class T>
concept Complete = requires(T &q, NvmeQueueHandle h) { q.complete(h); };
template <class T>
concept Activate = requires(T &q) { q.activate(); };
static_assert(!Inject<NvmeQueueBundle> && !Address<NvmeQueueBundle> && !Publish<NvmeQueueBundle>);
static_assert(!Complete<NvmeQueueBundle> && !Activate<NvmeQueueBundle>);
static_assert(!std::is_convertible_v<NvmeQueueHandle, aurora::memory::PageLease>);
static_assert(!std::is_default_constructible_v<NvmeQueueBundle>);
unsigned checks{};
auto check(bool value) -> void {
    ++checks;
    if (!value) {
        std::fprintf(stderr, "NVMe transport failure %u\n", checks);
        std::abort();
    }
}
auto namespace_cases() -> void {
    std::array<std::byte, 4096> identify{};
    put(identify, 0, 16384);
    put(identify, 8, 16384);
    put(identify, 16, 16384);
    put(identify, 24, 0x34, 1);
    put(identify, 130, 9, 1);
    const auto ns = NvmeNamespace::parse(identify);
    check(ns && ns->blocks() == 16384);
    check(ns->contains(0, 1) && ns->contains(16383, 1) && !ns->contains(16384, 1) && !ns->contains(UINT64_MAX, 1));
    check(!ns->contains(0, 0) && !ns->contains(0, 9) && !ns->contains(0, UINT32_MAX));
    for (unsigned count = 1; count <= 8; ++count) {
        check(ns->contains(0, count) && ns->contains(16384 - count, count));
        check(!ns->contains(16385 - count, count) && !ns->contains(UINT64_MAX - 7, count));
        const auto batch = NvmeCommand::io(*ns, 16384 - count, false, count);
        check(batch && Bytes{*batch}.get(0, 1) == 2 && Bytes{*batch}.get(4, 4) == 1 &&
              Bytes{*batch}.get(24) == 0x6000 && Bytes{*batch}.get(32) == 0 && Bytes{*batch}.get(40) == 16384 - count &&
              Bytes{*batch}.get(48, 4) == count - 1);
        check(!NvmeCommand::io(*ns, 16385 - count, false, count));
    }
    check(!NvmeCommand::io(*ns, 0, false, 0) && !NvmeCommand::io(*ns, 0, false, 9));
    check(!NvmeCommand::io(*ns, 0, true, 2));
    for (unsigned offset : {8U, 24U, 26U, 29U, 30U, 31U, 128U, 130U}) {
        auto changed = identify;
        changed[offset] ^= std::byte{1};
        check(!NvmeNamespace::parse(changed));
    }
    auto read = NvmeCommand::io(*ns, 7, false), write = NvmeCommand::io(*ns, 16383, true);
    check(read && write && Bytes{*read}.get(0, 1) == 2 && Bytes{*read}.get(24) == 0x6000 && Bytes{*read}.get(40) == 7);
    check(Bytes{*write}.get(0, 1) == 1 && Bytes{*write}.get(24) == 0x7000 && Bytes{*write}.get(40) == 16383);
    check(!NvmeCommand::io(*ns, 16384, true));
    check(NvmeCommand::io(*ns, 0, false).has_value()); // Range refusal does not poison admission.
}

namespace transport = aurora::nvme;
using U64 = std::uint64_t;
class OwnerPlatform final {
public:
    static inline U64 current_root = 0x1000, expected_root = 0x1000, flags = 2, slot = 0;
    static inline bool slot_present = true, mapped = false;
    static inline unsigned context_reads = 0, change_context_at = 0;
    static auto quiet() -> bool {
        return transport::quiet_context(current_root, expected_root, flags, slot_present, slot, mapped);
    }
    static auto context() -> U64 {
        ++context_reads;
        return change_context_at && context_reads >= change_context_at ? current_root + 4096 : current_root;
    }
    [[noreturn]] static auto fail() -> void {
        _exit(96);
    }
};
using Owner = transport::Root<OwnerPlatform>;
static_assert(!std::is_copy_constructible_v<Owner> && !std::is_move_constructible_v<Owner>);

auto sample(U64 qid, U64 cid, U64 tail, U64 phase) -> transport::Observation {
    const U64 last = cid | (phase << 16);
    return {last, 0, 0, (qid << 16) | tail, last};
}
auto selected(const transport::Completion &completion) -> bool {
    return static_cast<U64>(completion.kind) == 1;
}
auto stage(const Owner &owner, U64 expected) -> void {
    check(static_cast<U64>(owner.stage()) == expected);
}
auto busy(const Owner &owner, U64 expected) -> void {
    stage(owner, expected);
    check(!owner.available(0) && !owner.available(1));
    check(owner.remaining(0) == 0 && owner.remaining(1) == 0);
}
auto poisoned(Owner &owner) -> void {
    check(owner.poisoned());
    busy(owner, 4);
    check(owner.reserve(0, 0).cid == 0 && owner.reserve(1, 0).cid == 0);
    check(!owner.published(0, 1) && !owner.published(1, 1));
    check(!selected(owner.accept_completion(0, 1, sample(0, 1, 1, 1))));
    check(!owner.acknowledged(0, 1) && !owner.acknowledged(1, 1));
    stage(owner, 4); // Rejection never restores idle or usable budget.
}
auto owner_lifetime_cases() -> void {
    Owner owner;
    check(!owner.available(0) && !owner.available(1));
    check(owner.remaining(0) == 0 && owner.remaining(1) == 0);
    owner.create();
    stage(owner, 0);
    check(owner.active_qid() == 2 && owner.active_cid() == 0 && !owner.poisoned());
    for (U64 qid = 0; qid < 2; ++qid) {
        check(owner.available(qid) && owner.remaining(qid) == 65535 && owner.next_cid(qid) == 1);
        check(owner.tail(qid) == 0 && owner.head(qid) == 0 && owner.phase(qid) == 1 && owner.status(qid) == 0);
    }
    // Reviewed two-entry NVMe wire layout: each queue has its own monotone CID,
    // tail/head and phase. Interleaving also detects accidental shared counters.
    for (U64 i = 0; i < 65535; ++i) {
        for (U64 qid = 0; qid < 2; ++qid) {
            const U64 old_head = i & 1, new_head = (i + 1) & 1, old_phase = 1 ^ ((i / 2) & 1);
            const U64 cid = i + 1;
            check(owner.remaining(qid) == 65535 - i);
            const auto plan = owner.reserve(qid, 0);
            check(plan.qid == qid && plan.cid == cid && plan.sq_slot == old_head && plan.new_tail == new_head &&
                  plan.cq_slot == old_head && plan.phase == old_phase);
            busy(owner, 1);
            check(owner.next_cid(qid) == cid + 1 && owner.tail(qid) == new_head);
            check(owner.active_qid() == qid && owner.active_cid() == cid);
            check(owner.head(qid) == old_head && owner.phase(qid) == old_phase);
            check(owner.published(qid, cid));
            busy(owner, 2);
            const auto completion = owner.accept_completion(qid, cid, sample(qid, cid, new_head, old_phase));
            check(selected(completion) && completion.status == 0 && completion.new_cq_head == new_head);
            busy(owner, 3);
            check(owner.head(qid) == old_head && owner.phase(qid) == old_phase);
            check(owner.acknowledged(qid, cid));
            stage(owner, 0);
            check(owner.head(qid) == new_head && owner.phase(qid) == (1 ^ (((i + 1) / 2) & 1)));
            check(owner.active_qid() == 2 && owner.active_cid() == 0 && owner.status(qid) == 0);
            check(owner.remaining(qid) == 65534 - i && !owner.poisoned());
        }
    }
    check(owner.next_cid(0) == 65536 && owner.next_cid(1) == 65536);
    check(!owner.available(0) && !owner.available(1));
    check(owner.reserve(0, 0).cid == 0);
    poisoned(owner);
    for (const U64 qid : {U64{0}, U64{1}, U64{2}, UINT64_MAX}) {
        for (const U64 original_cid : {U64{1}, U64{65535}, UINT64_MAX}) {
            Owner bad;
            bad.create();
            check(bad.reserve(qid, original_cid).cid == 0);
            check(bad.next_cid(0) == 1 && bad.next_cid(1) == 1);
            poisoned(bad);
        }
    }
    for (const U64 qid : {U64{2}, U64{1} << 32, UINT64_MAX}) {
        Owner bad;
        bad.create();
        check(bad.reserve(qid, 0).cid == 0);
        poisoned(bad);
    }
}
auto owner_receipt_cases() -> void {
    // Stage 0 has no reservation. Stages 1..3 have progressively authorized
    // publication, selection and CQ acknowledgment; neither queue can overtake.
    for (U64 reached = 0; reached < 4; ++reached) {
        for (U64 active = 0; active < 2; ++active) {
            for (U64 action = 0; action < 4; ++action) {
                for (U64 identity = 0; identity < 4; ++identity) {
                    if ((action == 1 && reached == 1) || (action == 2 && reached == 2) ||
                        (action == 3 && reached == 3)) {
                        if (identity == 0)
                            continue; // Valid transitions are covered by every CID above.
                    }
                    if (action == 0 && reached == 0)
                        continue;
                    Owner owner;
                    owner.create();
                    if (reached >= 1)
                        check(owner.reserve(active, 0).cid == 1);
                    if (reached >= 2)
                        check(owner.published(active, 1));
                    if (reached >= 3)
                        check(selected(owner.accept_completion(active, 1, sample(active, 1, 1, 1))));
                    const U64 qid = identity == 1 ? 1 - active : active;
                    const U64 cid = identity == 2 ? 2 : identity == 3 ? 0 : 1;
                    if (action == 0)
                        check(owner.reserve(qid, 0).cid == 0);
                    if (action == 1)
                        check(!owner.published(qid, cid));
                    if (action == 2)
                        check(!selected(owner.accept_completion(qid, cid, sample(qid, cid, 1, 1))));
                    if (action == 3)
                        check(!owner.acknowledged(qid, cid));
                    check(owner.head(active) == 0 && owner.phase(active) == 1);
                    poisoned(owner);
                }
            }
        }
    }
    for (U64 receipt = 0; receipt < 3; ++receipt) {
        for (U64 active = 0; active < 2; ++active) {
            Owner owner;
            owner.create();
            check(owner.reserve(active, 0).cid == 1 && owner.published(active, 1));
            check(selected(owner.accept_completion(active, 1, sample(active, 1, 1, 1))));
            check(owner.acknowledged(active, 1));
            check(owner.reserve(active, 0).cid == 2);
            if (receipt >= 1)
                check(owner.published(active, 2));
            if (receipt >= 2)
                check(selected(owner.accept_completion(active, 2, sample(active, 2, 0, 1))));
            if (receipt == 0)
                check(!owner.published(active, 1));
            if (receipt == 1)
                check(!selected(owner.accept_completion(active, 1, sample(active, 1, 1, 1))));
            if (receipt == 2)
                check(!owner.acknowledged(active, 1));
            check(owner.head(active) == 1 && owner.phase(active) == 1 && owner.next_cid(active) == 3);
            poisoned(owner);
        }
    }
    for (U64 qid = 0; qid < 2; ++qid) {
        Owner owner;
        owner.create();
        check(owner.reserve(qid, 0).cid == 1 && owner.published(qid, 1));
        check(selected(owner.accept_completion(qid, 1, sample(qid, 1, 1, 1))));
        check(owner.acknowledged(qid, 1) && owner.remaining(qid) == 65534);
        check(!owner.acknowledged(qid, 1)); // Replay of an actually completed receipt.
        check(owner.head(qid) == 1 && owner.phase(qid) == 1 && owner.next_cid(qid) == 2);
        poisoned(owner);
    }
    for (U64 reached = 0; reached < 4; ++reached) {
        Owner owner;
        owner.create();
        if (reached >= 1)
            check(owner.reserve(1, 0).cid == 1);
        if (reached >= 2)
            check(owner.published(1, 1));
        if (reached >= 3)
            check(selected(owner.accept_completion(1, 1, sample(1, 1, 1, 1))));
        // Native publication, health, timeout or CQ-doorbell failure cannot
        // refund a consumed CID or acknowledge a merely selected completion.
        static_cast<void>(owner.poison());
        check(owner.head(1) == 0 && owner.phase(1) == 1);
        check(owner.next_cid(1) == (reached ? 2 : 1));
        poisoned(owner);
    }
}
auto malformed_completion_cases() -> void {
    struct Case {
        std::array<U64, 5> words;
        U64 status;
    };
    // qid=1, CID=1, SQ tail=1, CQ phase=1. Each literal is a wire observation,
    // not a second implementation of the source validation algorithm.
    constexpr Case cases[] = {
        {{0x10001, 1, 0, 0x10001, 0x10001}, 0},           // Nonzero result DWORD.
        {{0x10001, 0, 1, 0x10001, 0x10001}, 0},           // Reserved DWORD.
        {{0x10001, 0, 0, 0x10000, 0x10001}, 0},           // Wrong SQ head.
        {{0x10001, 0, 0, 0x10002, 0x10001}, 0},           // Out-of-ring SQ head.
        {{0x10001, 0, 0, 0x00001, 0x10001}, 0},           // Foreign SQ identity.
        {{0x10001, 0, 0, 0x20001, 0x10001}, 0},           // Unsupported SQ identity.
        {{0x10000, 0, 0, 0x10001, 0x10000}, 0},           // Zero CID.
        {{0x10002, 0, 0, 0x10001, 0x10002}, 0},           // Foreign CID.
        {{0x00001, 0, 0, 0x10001, 0x00001}, 0},           // Stale phase passed as completion.
        {{0x10001, 0, 0, 0x10001, 0x10002}, 0},           // Unstable second last-DWORD read.
        {{0x30001, 0, 0, 0x10001, 0x30001}, 1},           // Device error.
        {{0x80030001, 0, 0, 0x10001, 0x80030001}, 16385}, // Existing full status diagnostic.
        {{0xffff0001, 0, 0, 0x10001, 0xffff0001}, 32767},
    };
    const auto reject = [](const std::array<U64, 5> &words, U64 status) {
        Owner owner;
        owner.create();
        check(owner.reserve(1, 0).cid == 1 && owner.published(1, 1));
        const auto completion = owner.accept_completion(1, 1, {words[0], words[1], words[2], words[3], words[4]});
        check(!selected(completion) && completion.status == status && completion.new_cq_head == 0);
        check(owner.status(1) == status && owner.head(1) == 0 && owner.phase(1) == 1);
        poisoned(owner);
        check(owner.status(1) == status);
    };
    for (const auto &item : cases)
        reject(item.words, item.status);
    for (unsigned lane = 0; lane < 5; ++lane) {
        for (unsigned bit = 32; bit < 64; ++bit) {
            std::array<U64, 5> words{0x10001, 0, 0, 0x10001, 0x10001};
            words[lane] |= U64{1} << bit;
            reject(words, 0); // Width checks precede status extraction.
        }
    }
}

auto native_context_cases() -> void {
    // This tests the production predicate over copied observations. It does not
    // execute CR3/CLI/MMIO or authenticate a process broker in the host.
    for (const U64 root : {U64{0x1000}, U64{0x2000}}) {
        check(transport::quiet_context(root, root, 2, true, 0, false));
        check(!transport::quiet_context(root + 4096, root, 2, true, 0, false));
        check(!transport::quiet_context(root, root, 0x202, true, 0, false));
        check(!transport::quiet_context(root, root, 0, true, 0, false));
        check(!transport::quiet_context(root, root, 2, false, 0, false));
        check(!transport::quiet_context(root, root, 2, true, 1, false));
        check(!transport::quiet_context(root, root, 2, true, 0, true));
    }
    check(!transport::quiet_context(0, 0, 2, true, 0, false));
    Owner before;
    check(!before.created() && before.reserve(0, 0).cid == 0 && !before.poison());
    for (U64 qid = 0; qid < 2; ++qid)
        check(before.next_cid(qid) == 0 && before.tail(qid) == 0 && before.head(qid) == 0 && before.phase(qid) == 0 &&
              before.status(qid) == 0);
    before.create();
    check(before.created() && before.remaining(0) == 65535);
    OwnerPlatform::current_root = OwnerPlatform::expected_root = 0x2000;
    check(before.remaining(0) == 65535); // A separately admitted synchronous root.
    OwnerPlatform::current_root = OwnerPlatform::expected_root = 0x1000;
    // Existing hosted owner tests use fork plus a distinctive terminal exit.
    // Every child must reach Root's real fail path, never continue execution.
    for (unsigned mode = 0; mode < 12; ++mode) {
        for (unsigned initialized = 0; initialized < 2; ++initialized) {
            if (mode < 3 && initialized)
                continue;
            const auto child = fork();
            check(child >= 0);
            if (child == 0) {
                Owner owner;
                if (initialized || mode == 3)
                    owner.create();
                if (mode == 0)
                    static_cast<void>(owner.published(0, 1));
                else if (mode == 1)
                    static_cast<void>(owner.accept_completion(0, 1, sample(0, 1, 1, 1)));
                else if (mode == 2)
                    static_cast<void>(owner.acknowledged(0, 1));
                else if (mode == 3)
                    owner.create();
                else {
                    if (mode == 4)
                        OwnerPlatform::current_root = 0x2000;
                    if (mode == 5)
                        OwnerPlatform::expected_root = OwnerPlatform::current_root = 0;
                    if (mode == 6)
                        OwnerPlatform::flags = 0x202;
                    if (mode == 7)
                        OwnerPlatform::flags = 0;
                    if (mode == 8)
                        OwnerPlatform::slot_present = false;
                    if (mode == 9)
                        OwnerPlatform::slot = 1;
                    if (mode == 10)
                        OwnerPlatform::mapped = true;
                    if (mode == 11) {
                        OwnerPlatform::context_reads = 0;
                        OwnerPlatform::change_context_at = 2;
                    }
                    if (initialized)
                        static_cast<void>(owner.reserve(0, 0));
                    else
                        owner.create();
                }
                _exit(0);
            }
            int result = 0;
            check(waitpid(child, &result, 0) == child);
            check(WIFEXITED(result) && WEXITSTATUS(result) == 96);
        }
    }
}
auto native_binding_cases() -> void {
    alignas(4096) std::array<std::byte, 4096> submission{}, completion{}, foreign_page{};
    Owner owner, foreign_owner;
    owner.create();
    foreign_owner.create();
    static_assert(!std::is_copy_constructible_v<transport::Effects> &&
                  !std::is_move_constructible_v<transport::Effects>);
    for (U64 qid = 0; qid < 2; ++qid) {
        const transport::Binding binding{&owner, submission.data(), completion.data(), qid};
        const transport::Plan plan{qid, 1, 0, 1, 0, 1};
        check(binding.valid());
        transport::Effects effects(binding, plan);
        check(effects.authenticates(binding));
        check(!effects.selected(binding, 1, 1) && !effects.acknowledged(binding, 1, 1));
        check(effects.published(binding, 0, 1, 1));
        check(!effects.published(binding, 0, 1, 1) && !effects.acknowledged(binding, 1, 1));
        check(effects.selected(binding, 1, 1));
        check(!effects.selected(binding, 1, 1));
        check(effects.acknowledged(binding, 1, 1));
        check(!effects.acknowledged(binding, 1, 1) && !effects.published(binding, 0, 1, 1));
        for (unsigned changed = 0; changed < 10; ++changed) {
            auto wrong = binding;
            if (changed == 0)
                wrong.owner = nullptr;
            if (changed == 1)
                wrong.owner = &foreign_owner;
            if (changed == 2)
                wrong.submission = nullptr;
            if (changed == 3)
                wrong.completion = nullptr;
            if (changed == 4)
                wrong.submission = completion.data();
            if (changed == 5)
                wrong.submission = submission.data() + 1;
            if (changed == 6)
                wrong.completion = completion.data() + 1;
            if (changed == 7)
                wrong.submission = foreign_page.data();
            if (changed == 8)
                wrong.qid = 1 - qid;
            if (changed == 9)
                wrong.qid = 2;
            if (changed == 0 || changed == 2 || changed == 3 || changed == 4 || changed == 5 || changed == 6 ||
                changed == 9) {
                check(!wrong.valid());
                transport::Effects invalid(wrong, plan);
                check(!invalid.authenticates(wrong) && !invalid.published(wrong, 0, 1, 1));
            }
            transport::Effects receipt(binding, plan);
            check(!receipt.authenticates(wrong) && !receipt.published(wrong, 0, 1, 1));
            check(!receipt.selected(wrong, 1, 1) && !receipt.acknowledged(wrong, 1, 1));
        }
        for (unsigned changed = 0; changed < 3; ++changed) {
            transport::Effects receipt(binding, plan);
            check(!receipt.published(binding, changed == 0 ? 1 : 0, changed == 1 ? 2 : 1, changed == 2 ? 0 : 1));
        }
        for (unsigned changed = 0; changed < 2; ++changed) {
            transport::Effects receipt(binding, plan);
            check(receipt.published(binding, 0, 1, 1));
            check(!receipt.selected(binding, changed == 0 ? 2 : 1, changed == 1 ? 0 : 1));
        }
        for (unsigned changed = 0; changed < 8; ++changed) {
            auto invalid = plan;
            if (changed == 0)
                invalid.qid = 1 - qid;
            if (changed == 1)
                invalid.cid = 0;
            if (changed == 2)
                invalid.cid = 65536;
            if (changed == 3)
                invalid.sq_slot = 2;
            if (changed == 4)
                invalid.new_tail = 0;
            if (changed == 5)
                invalid.new_tail = 2;
            if (changed == 6)
                invalid.cq_slot = 2;
            if (changed == 7)
                invalid.phase = 2;
            transport::Effects rejected(binding, invalid);
            check(!rejected.authenticates(binding) && !rejected.published(binding, 0, 1, 1));
            check(!rejected.selected(binding, 1, 1) && !rejected.acknowledged(binding, 1, 1));
        }
    }
    for (unsigned changed = 0; changed < 5; ++changed) {
        Owner active;
        active.create();
        const auto plan = active.reserve(1, 0);
        const transport::Binding binding{&active, submission.data(), completion.data(), 1};
        transport::Effects receipt(binding, plan);
        check(receipt.published(binding, plan.sq_slot, plan.cid, plan.new_tail));
        check(active.published(1, plan.cid));
        const auto done = active.accept_completion(1, plan.cid, sample(1, plan.cid, plan.new_tail, plan.phase));
        check(selected(done) && receipt.selected(binding, plan.cid, done.new_cq_head));
        auto wrong = binding;
        if (changed == 0)
            wrong.owner = &foreign_owner;
        if (changed == 1)
            wrong.completion = foreign_page.data();
        if (changed == 2)
            wrong.qid = 0;
        check(!receipt.acknowledged(
            wrong, changed == 3 ? plan.cid + 1 : plan.cid, changed == 4 ? 1 - done.new_cq_head : done.new_cq_head));
        // The rejected native receipt does not call the source acknowledgment.
        // Production fail-stops here. No hosted claim of physical CQ writes.
        busy(active, 3);
        check(active.head(1) == plan.cq_slot && active.phase(1) == plan.phase);
    }
}

auto recovery_cases() -> void {
    using Phase = NvmeRecoveryPhase::Phase;
    NvmeRecoveryPhase good;
    check(good.begin() && good.phase() == Phase::writer);
    check(good.permit_write(40000));
    check(good.permit_flush(39999) && good.flushed());
    check(good.permit_write(39998));
    check(good.permit_flush(39997) && good.flushed() && good.seal(39996));
    check(good.phase() == Phase::sealing && good.retired());
    check(good.phase() == Phase::readonly && good.admitted_writes() == 2 && good.admitted_flushes() == 2);
    check(!good.begin() && good.phase() == Phase::failed);
    NvmeRecoveryPhase clean;
    check(clean.begin() && clean.permit_flush(32769) && clean.flushed() && clean.seal(32768) && clean.retired());
    // The same phase gate protects sector_count and every cached/DMA readonly
    // access. A late repeated lifecycle operation cannot leave RO usable.
    for (unsigned late = 0; late < 3; ++late) {
        NvmeRecoveryPhase state;
        check(state.permits_readonly()); // Ordinary readonly boot has no writer.
        check(state.begin() && !state.permits_readonly());
        check(state.permit_flush(40000) && state.flushed() && state.seal(39999));
        check(!state.permits_readonly() && state.retired() && state.permits_readonly());
        if (late == 0)
            check(!state.retired());
        if (late == 1)
            check(!state.seal(39999));
        if (late == 2)
            check(!state.fail());
        check(!state.permits_readonly());
    }
    check(clean.admitted_writes() == 0 && clean.admitted_flushes() == 1);
    NvmeRecoveryPhase write_limit;
    check(write_limit.begin());
    for (unsigned i = 0; i < 18; ++i)
        check(write_limit.permit_write(40000 - i));
    check(!write_limit.permit_write(39982));
    NvmeRecoveryPhase flush_limit;
    check(flush_limit.begin());
    for (unsigned i = 0; i < 3; ++i)
        check(flush_limit.permit_flush(40000 - i) && flush_limit.flushed());
    check(!flush_limit.permit_flush(39997));
    NvmeRecoveryPhase unacknowledged;
    check(unacknowledged.begin() && !unacknowledged.flushed());
    NvmeRecoveryPhase pending;
    check(pending.begin() && pending.permit_flush(40000) && !pending.permit_write(39999));
    NvmeRecoveryPhase reserve;
    check(reserve.begin() && reserve.permit_write(32789));
    check(!reserve.permit_read(32768));
    NvmeRecoveryPhase repeat;
    check(repeat.begin() && repeat.permit_flush(40000) && repeat.flushed() && repeat.seal(39999));
    check(!repeat.seal(39999) && !repeat.retired());
    for (unsigned mode = 0; mode < 6; ++mode) {
        NvmeRecoveryPhase bad;
        check(bad.begin());
        if (mode == 0)
            check(!bad.permit_write(32788));
        if (mode == 1)
            check(!bad.seal(40000));
        if (mode == 2)
            check(bad.permit_write(40000) && !bad.seal(39999));
        if (mode == 3)
            check(bad.permit_flush(32769) && bad.flushed() && !bad.seal(32767));
        if (mode == 4)
            check(!bad.retired());
        if (mode == 5)
            check(!bad.fail());
        check(bad.phase() == Phase::failed);
        check(!bad.begin() && !bad.flushed() && !bad.permit_write(65535) && !bad.retired());
    }
}
auto mounted_cases() -> void {
    using Phase = NvmeMountedPhase::Phase;
    constexpr unsigned reserve = NvmeMountedPhase::read_reserve;
    NvmeMountedPhase good;
    check(good.begin() && good.phase() == Phase::mounting && good.permit_read(65535, true));
    check(good.arm() && good.phase() == Phase::armed);
    unsigned remaining = reserve + 21;
    constexpr unsigned writes[] = {10, 2, 2, 1, 1};
    for (unsigned count : writes) {
        for (unsigned i = 0; i < count; ++i) {
            check(good.permit_read(remaining, false)); // A cached read spends no command.
            check(good.permit_write(remaining--));
        }
        check(good.permit_flush(remaining--) && good.flushed());
    }
    check(remaining == reserve && good.phase() == Phase::committed && good.admitted_writes() == 16 &&
          good.admitted_flushes() == 5 && good.permit_read(remaining, true));
    check(!good.permit_write(65535) && good.phase() == Phase::failed && !good.arm());
    for (unsigned mode = 0; mode < 10; ++mode) {
        NvmeMountedPhase bad;
        check(bad.begin());
        if (mode == 0)
            check(!bad.permit_write(65535));
        if (mode == 1)
            check(!bad.permit_flush(65535));
        if (mode == 2)
            check(!bad.begin());
        if (mode >= 3) {
            check(bad.arm());
            if (mode == 3)
                check(!bad.arm());
            if (mode == 4)
                check(!bad.permit_write(reserve + 20));
            if (mode == 5)
                check(!bad.permit_flush(65535));
            if (mode == 6)
                check(bad.permit_write(reserve + 21) && !bad.permit_read(reserve + 20, true));
            if (mode == 7)
                check(bad.permit_write(reserve + 21) && !bad.permit_flush(reserve + 20));
            if (mode >= 8) {
                for (unsigned i = 0; i < 10; ++i)
                    check(bad.permit_write(65535 - i));
                if (mode == 8)
                    check(!bad.permit_write(65525));
                if (mode == 9)
                    check(bad.permit_flush(65525) && !bad.permit_read(65524, false));
            }
        }
        check(bad.phase() == Phase::failed && !bad.permit_read(65535, false) && !bad.begin());
    }
    constexpr unsigned readonly_reserve = NvmeMountedPhase::read_reserve;
    const auto commit = [&](NvmeMountedPhase &state) {
        check(state.begin() && state.arm());
        unsigned budget = readonly_reserve + 21;
        for (unsigned count : writes) {
            for (unsigned i = 0; i < count; ++i)
                check(state.permit_write(budget--));
            check(state.permit_flush(budget--) && state.flushed());
        }
        check(budget == readonly_reserve && state.phase() == Phase::committed);
    };
    // Mounted startup scans the log twice. Its existing smaller reserve still
    // permits one fresh readonly remount without renewing any command IDs.
    NvmeMountedPhase two_scans;
    check(two_scans.begin());
    unsigned two_scan_remaining = 65535;
    for (unsigned i = 0; i < 2 * 16384; ++i)
        check(two_scans.permit_read(two_scan_remaining--, true));
    check(two_scans.arm());
    for (unsigned count : writes) {
        for (unsigned i = 0; i < count; ++i)
            check(two_scans.permit_write(two_scan_remaining--));
        check(two_scans.permit_flush(two_scan_remaining--) && two_scans.flushed());
    }
    check(two_scan_remaining == 32746 && two_scan_remaining < NvmeRecoveryPhase::readonly_reserve);
    check(two_scans.seal(two_scan_remaining) && two_scans.retired() && two_scans.permits_readonly());
    NvmeMountedPhase retired;
    check(retired.permits_readonly());
    commit(retired);
    check(!retired.permits_readonly());
    check(retired.seal(readonly_reserve) && retired.phase() == Phase::sealing);
    check(!retired.available() && !retired.permits_readonly());
    check(retired.retired() && retired.phase() == Phase::readonly && retired.permits_readonly());
    check(!retired.available() && retired.admitted_writes() == 16 && retired.admitted_flushes() == 5);
    // Only the retirement transition opens readonly; there is no rearm or
    // second transaction, even with a fresh caller budget.
    for (unsigned mode = 0; mode < 11; ++mode) {
        NvmeMountedPhase bad;
        commit(bad);
        if (mode == 0)
            check(!bad.seal(readonly_reserve - 1));
        else if (mode == 1)
            check(!bad.seal(0)); // Pending, quarantined or exhausted queue.
        else if (mode == 2) {
            check(bad.permit_read(readonly_reserve, true));
            check(!bad.seal(readonly_reserve - 1)); // A post-commit cache miss.
        } else if (mode == 3)
            check(!bad.retired());
        else {
            check(bad.seal(readonly_reserve));
            if (mode >= 5)
                check(bad.retired());
            if (mode == 4 || mode == 5)
                check(!bad.seal(65535));
            if (mode == 6)
                check(!bad.retired());
            if (mode == 7)
                check(!bad.arm());
            if (mode == 8)
                check(!bad.permit_read(65535, false));
            if (mode == 9)
                check(!bad.permit_write(65535));
            if (mode == 10)
                check(!bad.permit_flush(65535));
        }
        check(bad.phase() == Phase::failed && !bad.permits_readonly() && !bad.available());
        check(!bad.begin() && !bad.arm() && !bad.seal(65535) && !bad.retired());
    }
    // Never seal an unstarted, mounting, armed or incomplete/pending writer.
    for (unsigned mode = 0; mode < 5; ++mode) {
        NvmeMountedPhase bad;
        if (mode >= 1)
            check(bad.begin());
        if (mode >= 2)
            check(bad.arm());
        if (mode >= 3)
            for (unsigned i = 0; i < 10; ++i)
                check(bad.permit_write(65535 - i));
        if (mode == 4)
            check(bad.permit_flush(65525));
        check(!bad.seal(65535) && bad.phase() == Phase::failed && !bad.permits_readonly());
    }
    NvmeMountedPhase abandoned;
    check(abandoned.begin() && abandoned.arm() && !abandoned.fail() && !abandoned.arm() &&
          !abandoned.permit_write(65535));
}
auto main() -> int {
    namespace_cases();
    owner_lifetime_cases();
    owner_receipt_cases();
    malformed_completion_cases();
    native_context_cases();
    native_binding_cases();
    recovery_cases();
    mounted_cases();
    std::printf("NVMe transport: %u checks passed\n", checks);
    return 0;
}
} // namespace kernel_nvme_queues_api
