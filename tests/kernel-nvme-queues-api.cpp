// CPU preparation handles and the separately admitted active transport codec.
#include "../kernel/uefi/nvme-queues.hpp"
#include <type_traits>
#include <cstdio>
#include <cstdlib>
#include "../kernel/uefi/nvme-transport.hpp"

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
auto transport_cases() -> void {
    alignas(4096) std::array<std::byte, 4096> sq{}, cq{}, identify{};
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
    const auto completion = [&](unsigned slot, unsigned head, unsigned cid, unsigned phase, unsigned error = 0) {
        put(cq, slot * 16, 0);
        put(cq, slot * 16 + 8, (1U << 16) | head, 4);
        put(cq, slot * 16 + 12, cid | (phase << 16) | (error << 17), 4);
    };
    NvmePolledQueue queue{sq, cq, 1};
    // Golden NVMe completion wire layout, including wrap/phase and nonreused CID.
    for (unsigned i = 0; i < 65535; ++i) {
        check(queue.remaining_commands() == 65535 - i);
        check(queue.submit(*read));
        check(queue.remaining_commands() == 0);
        check(Bytes{sq}.get((i & 1) * 64 + 2, 2) == i + 1);
        check(queue.observe() == NvmePolledQueue::Result::pending);
        completion(i & 1, (i + 1) & 1, i + 1, 1 ^ ((i / 2) & 1));
        check(queue.observe() == NvmePolledQueue::Result::complete);
        check(queue.head() == ((i + 1) & 1) && !queue.quarantined());
    }
    check(queue.remaining_commands() == 0);
    check(!queue.submit(*read) && queue.quarantined());
    for (unsigned bad = 0; bad < 8; ++bad) {
        sq.fill(std::byte{});
        cq.fill(std::byte{});
        NvmePolledQueue q{sq, cq, 1};
        check(q.submit(*read));
        completion(0, 1, 1, 1);
        if (bad == 0)
            put(cq, 0, 1, 4);
        if (bad == 1)
            put(cq, 4, 1, 4);
        if (bad == 2)
            put(cq, 8, 0x10000, 4); // Wrong SQ head.
        if (bad == 3)
            put(cq, 8, 0x20001, 4); // Wrong SQ identity.
        if (bad == 4)
            put(cq, 12, 0x10002, 4); // Stale/foreign CID.
        if (bad == 5)
            put(cq, 12, 0x30001, 4); // Device error.
        if (bad == 6)
            q.quarantine(); // Poll budget exhausted.
        if (bad == 7)
            check(!q.submit(*read));
        check(q.remaining_commands() == 0); // Double submission.
        check(q.observe() == NvmePolledQueue::Result::quarantined && q.quarantined());
        check(!q.submit(*read));
        check(q.remaining_commands() == 0);
    }
    cq.fill(std::byte{});
    NvmePolledQueue unsubmitted{sq, cq, 0};
    check(unsubmitted.observe() == NvmePolledQueue::Result::quarantined);
    NvmePolledQueue aliased{sq, sq, 0};
    check(!aliased.submit(*read));
    NvmePolledQueue short_page{std::span{sq}.first(4095), cq, 0};
    check(!short_page.submit(*read));
    NvmePolledQueue misaligned{std::span{sq}.subspan(1), cq, 0};
    check(!misaligned.submit(*read));
    NvmePolledQueue wrong_id{sq, cq, 2};
    check(!wrong_id.submit(*read));
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
    NvmeMountedPhase abandoned;
    check(abandoned.begin() && abandoned.arm() && !abandoned.fail() && !abandoned.arm() &&
          !abandoned.permit_write(65535));
}
auto main() -> int {
    transport_cases();
    recovery_cases();
    mounted_cases();
    std::printf("NVMe transport: %u checks passed\n", checks);
    return 0;
}
} // namespace kernel_nvme_queues_api
