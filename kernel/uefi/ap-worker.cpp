#include "ap-worker.hpp"
#include "ap-worker-native.hpp"
#include "acpi.hpp"
#include "tables.hpp"
#include "../retained-ap-worker.hpp"
#include "../console.hpp"
#include <array>

namespace aurora::uefi {
namespace {
using U64 = std::uint64_t;
using Serial = hardware::Serial;
constinit U64 bound_root = 0, bound_bsp = 0;
constinit const void *bound_owner = nullptr;
constinit ApWorkerNative transport;
constinit std::optional<ApWorkerAdmission> bound_grant;
auto current_root() -> U64 {
    U64 result;
    asm volatile("mov %%cr3,%0" : "=r"(result)::"memory");
    return result;
}
auto msr(std::uint32_t index) -> U64 {
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(index));
    return (U64{high} << 32) | low;
}
class OwnerPlatform final {
public:
    [[nodiscard]] static auto authenticates(const void *owner) -> bool {
        return owner == bound_owner && bound_root && current_root() == bound_root;
    }
    [[nodiscard]] static auto quiet() -> bool {
        U64 flags;
        std::uint32_t a, b, c, d;
        asm volatile("pushfq; pop %0" : "=r"(flags)::"memory");
        asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
        return (flags & 0x202) == 2 && current_root() == bound_root && (b >> 24) == bound_bsp &&
               msr(0x1b) == (ApWorkerAdmission::physical_address | 0x900);
    }
    [[nodiscard]] static auto context() -> U64 {
        return current_root();
    }
    [[noreturn]] static void fail() {
        transport.close();
        Serial::text("AURORA_AP_OWNER_FAIL_STOP\r\n");
        for (;;)
            asm volatile("cli; hlt");
    }
};
constinit ap::Root<OwnerPlatform> owner;
auto quarantine(ap_worker::Case selected, ApWorkerStatus status) -> bool {
    transport.close();
    static_cast<void>(owner.fail());
    if (owner.stage() != ap::Stage::failed || owner.reserve(3, 1).sequence || !transport.closed() ||
        !transport.retained())
        return false;
    if (selected == ap_worker::Case::late) {
        bool observed = false;
        for (U64 polls = 0; polls < 10000000 && !observed; ++polls) {
            observed = transport.late_completion_seen();
            asm volatile("pause");
        }
        if (!observed || owner.reserve(3, 1).sequence || owner.stage() != ap::Stage::failed)
            return false;
        Serial::text("AURORA_AP_LATE_IGNORED\r\n");
    }
    Serial::text("AURORA_AP_QUARANTINED: status=");
    Serial::number(static_cast<U64>(status));
    Serial::text(" retained=1 retry=0\r\n");
    return true;
}
} // namespace

auto run_ap_worker(U64 arena, const Bytes &h, memory::PhysicalPages &pool) -> bool {
    static_assert(Handoff::worker_pages * 4096 == ApWorkerLayout::bytes &&
                  Handoff::worker_request_offset == ApWorkerLayout::request);
    if (bound_owner || !discovered_ap_worker_topology() || !discovered_ap_worker_timer())
        return false;
    // Every ordinary return closes physical publication. A source trap does
    // not unwind this guard; that separate path fail-stops the BSP.
    class CloseOnReturn final {
    public:
        ~CloseOnReturn() {
            transport.close();
        }
    } close_on_return;
    const auto selected = static_cast<ap_worker::Case>(h.get(Handoff::worker_case_word));
    const auto map_bytes = std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + Handoff::map_offset),
                                                      static_cast<std::size_t>(h.get(32))};
    const MemoryMap map{map_bytes, h.get(40), static_cast<std::uint32_t>(h.get(48, 4))};
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0), "c"(0));
    const auto vendor_b = b, vendor_c = c, vendor_d = d;
    if (a < 1)
        return false;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    const auto features = d, identifiers = b;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000000U), "c"(0));
    if (a < 0x80000008U)
        return false;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000001U), "c"(0));
    const auto extended = d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
    const auto admitted = ApWorkerAdmission::authorize(*discovered_ap_worker_topology(),
                                                       *discovered_ap_worker_timer(),
                                                       map_bytes,
                                                       h.get(40),
                                                       static_cast<std::uint32_t>(h.get(48, 4)),
                                                       arena,
                                                       current_root(),
                                                       a & 255,
                                                       vendor_b,
                                                       vendor_d,
                                                       vendor_c,
                                                       features,
                                                       identifiers,
                                                       extended,
                                                       msr(0x1b),
                                                       msr(0x277));
    if (!admitted || bound_grant)
        return false;
    bound_grant.emplace(*admitted);
    const auto &grant = bound_grant;
    const PageTables tables{current_root(), static_cast<std::size_t>(h.get(96))};
    const auto slot = tables.interrupt_slot();
    if (!slot || *slot)
        return false;
    *slot = grant->mapping(ApWorkerAdmission::virtual_address);
    asm volatile("invlpg (%0)" ::"r"(ApWorkerAdmission::virtual_address) : "memory");
    if (!tables.verify(arena, h, nullptr, &*grant))
        return false;
    const auto native_case = selected >= ap_worker::Case::overlap ? ApWorkerFixture::overlap
                             : selected == ap_worker::Case::malformed_completion
                                 ? ApWorkerFixture::malformed_status
                                 : static_cast<ApWorkerFixture>(static_cast<U64>(selected));
    if ((selected > ap_worker::Case::stagnant_timer && selected != ap_worker::Case::malformed_completion &&
         selected < ap_worker::Case::overlap) ||
        !transport.prepare(
            *grant, map, h.get(Handoff::worker_block_word), h.get(Handoff::worker_low_word), 1, native_case) ||
        !transport.seal() || !tables.verify(arena, h, nullptr, &*grant, true))
        return false;
    bound_root = current_root();
    bound_bsp = grant->bsp_id();
    bound_owner = &owner;
    owner.create();
    if (!owner.begin_start(grant->ap_id(), 1))
        return false;
    const auto ready = transport.start();
    Serial::text("AURORA_AP_START_ATTEMPT: value=");
    Serial::number(transport.startup_attempted() ? 1 : 0);
    Serial::text("\r\n");
    if (ready.status != ApWorkerStatus::ready) {
        const bool expected =
            (selected == ap_worker::Case::wrong_identity || selected == ap_worker::Case::wrong_root)
                ? ready.status == ApWorkerStatus::fault && ready.vector == 256
                : selected == ap_worker::Case::stagnant_timer && ready.status == ApWorkerStatus::rejected;
        return expected && quarantine(selected, ready.status);
    }
    if (!owner.startup_sent(ready.apic, ready.incarnation) || !owner.ready(ready.apic, ready.incarnation))
        return false;
    Serial::text("AURORA_AP_READY: bsp=");
    Serial::number(grant->bsp_id());
    Serial::text(" ap=");
    Serial::number(ready.apic);
    Serial::text(" root=");
    Serial::number(transport.permanent_root());
    Serial::text("\r\n");
    // Independently calculated Castagnoli CRCs over the presealed byte page.
    constexpr std::array<std::array<std::int64_t, 2>, 8> ranges{
        {{4096, 0}, {4095, 1}, {1, 511}, {512, 512}, {1024, 512}, {1536, 512}, {2048, 1024}, {3072, 1024}}};
    constexpr std::array<U64, 8> expected{
        0, 2548833443, 819199888, 1917529135, 1917529135, 1917529135, 1134909107, 1134909107};
    const auto bsp_work = [&](U64 sequence) -> bool {
        // Independent BSP-owned physical memory, never mapped into the AP root.
        // No retained owner loan or AP request access spans this operation.
        if (pool.used() != 0)
            return false;
        auto page = pool.acquire();
        if (!page)
            return false;
        const auto address = pool.address(*page);
        if (!address || *address != arena + Handoff::pool_offset)
            return false;
        U64 sum = 0;
        for (U64 i = 0; i < 4096; ++i)
            *reinterpret_cast<volatile std::uint8_t *>(*address + i) = static_cast<std::uint8_t>(i + sequence);
        for (U64 i = 0; i < 4096; ++i) {
            const auto value = *reinterpret_cast<volatile std::uint8_t *>(*address + i);
            if (value != static_cast<std::uint8_t>(i + sequence))
                return false;
            sum += value;
        }
        if (sum != 522240 || !pool.release(*page) || pool.used() != 0)
            return false;
        if (selected == ap_worker::Case::overlap) {
            Serial::text("AURORA_AP_BSP_WORK: sequence=");
            Serial::number(sequence);
            Serial::text(" value=");
            Serial::number(sum);
            Serial::text("\r\n");
        }
        return true;
    };
    for (std::size_t i = 0; i < expected.size(); ++i) {
        const auto plan = owner.reserve(ranges[i][0], ranges[i][1]);
        if (!plan.sequence || owner.stage() != ap::Stage::reserved || owner.incarnation() != plan.incarnation ||
            owner.sequence() != plan.sequence || owner.start() != plan.start || owner.count() != plan.count)
            return false;
        const auto publication = transport.publish(plan.incarnation, plan.sequence, plan.start, plan.count);
        if (publication.status != ApWorkerStatus::pending)
            return false;
        // The source transition is immediate after the physical release. Failure
        // is terminal; no caller-visible "unsubmitted" state or refund escapes.
        if (!owner.published(plan.incarnation, plan.sequence))
            OwnerPlatform::fail();
        // These boot-selected rows probe the native boundary, not forged source
        // authority. Each refusal must close transport before owner quarantine.
        if (selected == ap_worker::Case::second_publication) {
            const auto refused = transport.publish(plan.incarnation, plan.sequence + 1, 0, 1);
            return refused.status == ApWorkerStatus::rejected && transport.closed() &&
                   quarantine(selected, refused.status);
        }
        if (selected == ap_worker::Case::premature_settlement)
            return !transport.settle(plan.incarnation, plan.sequence) && transport.closed() &&
                   quarantine(selected, ApWorkerStatus::rejected);
        bool worked = false;
        if (selected != ap_worker::Case::overlap) {
            if (!bsp_work(plan.sequence))
                return false;
            worked = true;
        }
        for (;;) {
            const auto ordinal = owner.reserve_observation(plan.incarnation, plan.sequence);
            if (!ordinal)
                return (selected == ap_worker::Case::withheld || selected == ap_worker::Case::late) &&
                       quarantine(selected, ApWorkerStatus::timeout);
            if (owner.stage() != ap::Stage::observation_reserved || owner.incarnation() != plan.incarnation ||
                owner.sequence() != plan.sequence || owner.ordinal() != ordinal)
                OwnerPlatform::fail();
            const auto result = transport.progress(plan.incarnation, plan.sequence, ordinal);
            if (result.status != ApWorkerStatus::done && result.status != ApWorkerStatus::pending) {
                const bool expected_failure =
                    selected == ap_worker::Case::malformed_completion ? result.status == ApWorkerStatus::rejected
                    : selected == ap_worker::Case::fault
                        ? result.status == ApWorkerStatus::fault && result.vector == 6 && result.error == 0
                        : false;
                return expected_failure && quarantine(selected, result.status);
            }
            if (result.ordinal != ordinal || !owner.observe({result.apic,
                                                             result.incarnation,
                                                             result.sequence,
                                                             result.value,
                                                             result.status == ApWorkerStatus::pending ? 1ULL : 0ULL},
                                                            ordinal,
                                                            result.ticks)) {
                const bool expected_timeout =
                    selected == ap_worker::Case::withheld || selected == ap_worker::Case::late;
                return expected_timeout && quarantine(selected, ApWorkerStatus::timeout);
            }
            if (selected == ap_worker::Case::repeated_observation) {
                const auto refused = transport.progress(plan.incarnation, plan.sequence, ordinal);
                return result.status == ApWorkerStatus::pending && refused.status == ApWorkerStatus::rejected &&
                       transport.closed() && quarantine(selected, refused.status);
            }
            if (result.status == ApWorkerStatus::pending) {
                if (selected == ap_worker::Case::overlap && result.started && !worked) {
                    Serial::text("AURORA_AP_STARTED: sequence=");
                    Serial::number(plan.sequence);
                    Serial::text("\r\n");
                    if (!bsp_work(plan.sequence) || owner.stage() != ap::Stage::running ||
                        owner.incarnation() != plan.incarnation || owner.sequence() != plan.sequence ||
                        owner.ordinal() != ordinal ||
                        !transport.release_overlap(plan.incarnation, plan.sequence, ordinal))
                        return false;
                    worked = true;
                    Serial::text("AURORA_AP_RELEASED: sequence=");
                    Serial::number(plan.sequence);
                    Serial::text("\r\n");
                }
                asm volatile("pause");
                continue;
            }
            if (!worked || !owner.acknowledged(plan.incarnation, plan.sequence) ||
                !transport.settle(plan.incarnation, plan.sequence) ||
                owner.result() != static_cast<std::int64_t>(expected[i]))
                return false;
            break;
        }
        Serial::text("AURORA_AP_RESULT: sequence=");
        Serial::number(plan.sequence);
        Serial::text(" value=");
        Serial::number(expected[i]);
        Serial::text("\r\n");
    }
    if (owner.stage() != ap::Stage::exhausted || owner.used() != 4096 || owner.remaining() || owner.jobs() != 8 ||
        owner.reserve(3, 1).sequence)
        return false;
    transport.close();
    Serial::text("AURORA_AP_EXHAUSTED: jobs=8 work=4096 retained=1\r\n");
    return transport.closed() && transport.retained();
}
} // namespace aurora::uefi
