#include "nvme.hpp"
#include "nvme-transport.hpp"
#include "../retained-nvme-transport.hpp"
#include "event-backing.hpp"
#include "tables.hpp"
#include "fw-cfg-fixture.hpp"
#include "../console.hpp"
#ifndef AURORA_UEFI_NVME
#error "NVMe transport requires its explicit bounded image profile"
#endif
namespace aurora::uefi {
namespace {
using U64 = std::uint64_t;
using hardware::Serial;
using Page = std::array<std::byte, 4096>;
// No allocator enrollment, destructor release, reset or retry. The controller
// can access only these six queue/data pages, retained on every outcome.
class alignas(4096) Backing final {
public:
    std::array<std::byte, 8192> devices{};
    Page translations{}, commands{}, events{};
    enum IoPage : unsigned {
        admin_submission,
        admin_completion,
        io_submission,
        io_completion,
        read_data,
        write_data
    };
    std::array<Page, 6> io{};
};
static_assert(sizeof(Backing) == 11 * 4096 && offsetof(Backing, io) % 4096 == 0);
Backing backing;
std::array<std::byte, Handoff::header> saved_handoff{};
U64 arena_base{}, root_base{}, table_count{}, nvme_base{}, config_base{};
volatile U64 *window_slot{};
bool begun{}, exposed{}, mapped{}, readonly_open{};
NvmeReadCache cache;
U64 process_root{}, cache_lba{};
bool dual_open{};
unsigned volume_count{};
constinit std::array<std::optional<NvmeNamespace>, 2> volumes;
unsigned cache_sectors{};
std::string_view failure_reason{};
constinit std::optional<NvmeNamespace> admitted_namespace;
unsigned completed{};
NvmeRecoveryPhase recovery;
NvmeMountedPhase mounted;
#if !defined(AURORA_PROCESS_FIXTURE) && !defined(AURORA_PRODUCTION)
unsigned selected{}, flushed{};
#endif
constexpr U64 iommu_base = 0xfed80000, attempts = 1ULL << 22;
constexpr U64 read_permission = 1ULL << 61, write_permission = 1ULL << 62;
[[nodiscard]] auto address(const void *p) -> U64 {
    return reinterpret_cast<U64>(p);
}
[[nodiscard]] auto tables() -> PageTables {
    return PageTables{root_base, static_cast<std::size_t>(table_count)};
}
[[noreturn]] auto halt() -> void {
    for (;;)
        asm volatile("cli; hlt");
}
[[noreturn]] auto fail(std::string_view reason) -> void {
    // A failed operation never makes its DMA pages reusable, even when PCI BME
    // or a controller register appears quiet. No cleanup writes hide failure.
    Serial::text("AURORA_NVME_QUARANTINED: reason=");
    Serial::text(reason);
    Serial::text(" exposed=");
    Serial::number(exposed);
    Serial::text(" completed=");
    Serial::number(completed);
    Serial::text(" retained=boot\r\n");
    halt();
}
auto require(bool condition, std::string_view reason) -> void {
    if (!condition)
        fail(reason);
}
[[nodiscard]] auto closed() -> bool {
    U64 cr3, flags;
    asm volatile("mov %%cr3, %0; pushfq; pop %1" : "=r"(cr3), "=r"(flags));
    return nvme::quiet_context(cr3,
                               process_root ? process_root : root_base,
                               flags,
                               window_slot != nullptr,
                               window_slot ? *window_slot : 0,
                               mapped);
}
class TransportPlatform final {
public:
    static auto context() -> U64 {
        U64 cr3;
        asm volatile("mov %%cr3, %0" : "=r"(cr3));
        return cr3;
    }
    static auto quiet() -> bool {
        return closed();
    }
    [[noreturn]] static auto fail() -> void {
        uefi::fail("transport-source-integrity");
    }
};
// This root is separate from every device-accessible page and never destroyed,
// reset or reconstructed. Source faults terminate with all DMA backing pinned.
nvme::Root<TransportPlatform> transport;
class ProcessScope final {
public:
    ProcessScope(U64 verified_root, U64 generation) {
        require(!process_root && verified_root && verified_root % 4096 == 0 && generation, "transport-context");
        process_root = verified_root;
        require(closed(), "transport-context-window");
    }
    ProcessScope(const ProcessScope &) = delete;
    auto operator=(const ProcessScope &) -> ProcessScope & = delete;
    ~ProcessScope() {
        require(closed(), "transport-context-return");
        process_root = 0;
    }
};
// One short-lived supervisor UC mapping. No raw device pointer escapes.
class Window final {
    [[nodiscard]] static auto begin(U64 physical, unsigned width, bool write) -> U64 {
        require(closed() && (width == 2 || width == 4 || width == 8) && physical % width == 0 &&
                    physical < (1ULL << 40) && (physical & 4095) <= 4096 - width,
                "mapping");
        mapped = true;
        *window_slot = (physical & ~4095ULL) | 1 | 8 | 16 | PageTables::nx | (write ? 2 : 0);
        asm volatile("invlpg (%0)" ::"r"(PageTables::window_address) : "memory");
        return PageTables::window_address + (physical & 4095);
    }
    static auto end(U64 physical, bool write) -> void {
        const auto expected = (physical & ~4095ULL) | 1 | 8 | 16 | PageTables::nx | (write ? 2 : 0);
        const bool intact = mapped && (*window_slot & ~0x60ULL) == expected;
        *window_slot = 0;
        asm volatile("invlpg (%0)" ::"r"(PageTables::window_address) : "memory");
        mapped = false;
        require(intact && closed(), "mapping-revoke");
    }

public:
    [[nodiscard]] static auto read(U64 physical, unsigned width) -> U64 {
        const auto pointer = begin(physical, width, false);
        asm volatile("lfence" ::: "memory");
        const U64 value = width == 2   ? *reinterpret_cast<volatile const std::uint16_t *>(pointer)
                          : width == 4 ? *reinterpret_cast<volatile const std::uint32_t *>(pointer)
                                       : *reinterpret_cast<volatile const U64 *>(pointer);
        asm volatile("lfence" ::: "memory");
        end(physical, false);
        return value;
    }
    static auto write(U64 physical, unsigned width, U64 value) -> void {
        require(width == 8 || value < (1ULL << (width * 8)), "register-width");
        const auto pointer = begin(physical, width, true);
        asm volatile("mfence" ::: "memory");
        if (width == 2)
            *reinterpret_cast<volatile std::uint16_t *>(pointer) = static_cast<std::uint16_t>(value);
        else if (width == 4)
            *reinterpret_cast<volatile std::uint32_t *>(pointer) = static_cast<std::uint32_t>(value);
        else
            *reinterpret_cast<volatile U64 *>(pointer) = value;
        asm volatile("mfence" ::: "memory");
        end(physical, true);
    }
};
[[nodiscard]] auto iommu(U64 offset) -> U64 {
    return Window::read(iommu_base + offset, 8);
}
[[nodiscard]] auto status() -> U64 {
    return Window::read(nvme_base + 0x1c, 4);
}
[[nodiscard]] auto healthy() -> bool {
    return iommu(0x18) == 0x1005 && iommu(0x2020) == 0x18 && !iommu(0x2010) && !iommu(0x2018);
}
auto ready(bool enabled) -> void {
    for (U64 i = 0; i < attempts; ++i) {
        const auto value = status();
        require(value <= 1, "controller-fault");
        if (value == (enabled ? 1U : 0U))
            return;
        asm volatile("pause" ::: "memory");
    }
    fail("controller-timeout");
}
auto guard(Page &page, unsigned used) -> void {
    const volatile std::byte *data = page.data();
    for (unsigned i = used; i < page.size(); ++i)
        require(data[i] == std::byte{0xa5}, "dma-boundary");
}
auto queue_guards() -> void {
    guard(backing.io[Backing::admin_submission], 128);
    guard(backing.io[Backing::admin_completion], 32);
    guard(backing.io[Backing::io_submission], 128);
    guard(backing.io[Backing::io_completion], 32);
}
auto initialize(bool readonly) -> void {
    const Bytes handoff{saved_handoff};
    const auto begin = arena_base + Handoff::payload_offset + handoff.get(72);
    const auto bytes = handoff.get(80) - handoff.get(72);
    require(EventBackingPolicy::page_extent(begin, bytes, address(&backing), sizeof(backing)), "backing-extent");
    for (U64 i = 0; i < sizeof(backing); i += 4096)
        require((tables().entry(address(&backing) + i) & ~0x60ULL) == ((address(&backing) + i) | 3 | PageTables::nx),
                "backing-mapping");
    // A zero DTE is bypass in the model. V=TV=1, Mode0, no IR/IW denies.
    for (unsigned rid = 0; rid < 256; ++rid)
        put(backing.devices, rid * 32, 3);
    put(backing.devices, 0x10 * 32, address(backing.translations.data()) | 0x203 | read_permission | write_permission);
    put(backing.devices, 0x10 * 32 + 8, 0x1234);
    // A typed contiguous array keeps the current image's page addresses PC-relative;
    // no statically relocated pointer table is embedded in the freestanding image.
    for (unsigned i = 0; i < 6; ++i) {
        const bool writes = i == Backing::admin_completion || i == Backing::io_completion || i == Backing::read_data;
        if (readonly && i == Backing::write_data)
            continue; // No device-read data mapping in the readonly broker.
        put(backing.translations,
            (i + 2) * 8,
            address(backing.io[i].data()) | 1 | (writes ? write_permission : read_permission));
        if (i < 4)
            for (unsigned at = (i & 1) ? 32 : 128; at < 4096; ++at)
                backing.io[i][at] = std::byte{0xa5};
    }
    asm volatile("mfence" ::: "memory");
}
auto publish() -> void {
    const auto cold = NvmeColdObservation::sample([](unsigned offset, unsigned width) {
        return Window::read(nvme_base + offset, width);
    });
    require(cold.cold() && Window::read(config_base + 4, 2) == 2, "cold-controller");
    for (unsigned offset : {0U, 8U, 0x10U, 0x18U, 0x30U, 0x2000U, 0x2008U, 0x2010U, 0x2018U, 0x2020U})
        require(iommu(offset) == (offset == 0x30 ? 0x29d3U : 0U), "cold-iommu");
    exposed = true; // Consumed before any hardware publication; never cleared.
    Window::write(iommu_base, 8, address(backing.devices.data()) | 1);
    Window::write(iommu_base + 8, 8, address(backing.commands.data()) | (8ULL << 56));
    Window::write(iommu_base + 0x10, 8, address(backing.events.data()) | (8ULL << 56));
    Window::write(iommu_base + 0x18, 8, 0x1005);
    require(iommu(0) == (address(backing.devices.data()) | 1) &&
                iommu(8) == (address(backing.commands.data()) | (8ULL << 56)) &&
                iommu(0x10) == (address(backing.events.data()) | (8ULL << 56)),
            "iommu-publication");
    require(healthy(), "iommu-fault");
    Window::write(nvme_base + 0xc, 4, 0xffffffff); // Mask all legacy interrupt vectors; CQ interrupt disabled.
    Window::write(nvme_base + 0x24, 4, 0x10001);
    Window::write(nvme_base + 0x28, 8, 0x2000);
    Window::write(nvme_base + 0x30, 8, 0x3000);
    require(Window::read(nvme_base + 0x24, 4) == 0x10001 && Window::read(nvme_base + 0x28, 8) == 0x2000 &&
                Window::read(nvme_base + 0x30, 8) == 0x3000,
            "queue-publication");
    Window::write(config_base + 4, 2, 6);
    require(Window::read(config_base + 4, 2) == 6, "bme-publication");
    Window::write(nvme_base + 0x14, 4, 0x460001); // IOSQES6, IOCQES4, MPS0, NVM, EN.
    ready(true);
    require(healthy(), "iommu-fault");
}
[[nodiscard]] auto quarantine(std::string_view reason) -> bool {
    // Revoke transport policy first. A source fault or broken borrow instead
    // fail-stops; it never claims this transition or adjacent effects ran.
    static_cast<void>(transport.poison());
    cache.invalidate();
    static_cast<void>(recovery.fail());
    static_cast<void>(mounted.fail());
    failure_reason = reason;
    return false;
}
[[nodiscard]] auto binding(unsigned qid) -> nvme::Binding {
    require(qid <= 1, "queue-identity");
    return {&transport, backing.io[qid * 2].data(), backing.io[qid * 2 + 1].data(), qid};
}
[[nodiscard]] auto execute(unsigned qid, std::array<std::byte, 64> command) -> bool {
    if (transport.poisoned())
        return false;
    if (!healthy())
        return quarantine("iommu-fault");
    if (status() != 1)
        return quarantine("queue-submit");
    const auto physical = binding(qid);
    const auto plan = transport.reserve(qid, Bytes{command}.get(2, 2));
    if (!plan.cid)
        return quarantine("queue-submit");
    nvme::Effects effects(physical, plan);
    require(effects.authenticates(binding(qid)) && closed(), "submission-binding");
    // Reservation already consumed the nonreusable CID before any SQ effect.
    put(command, 2, plan.cid, 2);
    for (unsigned i = 0; i < 64; ++i)
        backing.io[qid * 2][plan.sq_slot * 64 + i] = command[i];
    asm volatile("mfence" ::: "memory");
    Window::write(nvme_base + 0x1000 + qid * 8, 4, plan.new_tail);
    require(closed() && effects.published(binding(qid), plan.sq_slot, plan.cid, plan.new_tail), "publication-receipt");
    if (!transport.published(qid, plan.cid))
        return quarantine("publication-state");
    for (U64 i = 0; i < attempts; ++i) {
        require(effects.authenticates(binding(qid)), "completion-binding");
        const auto *entry =
            reinterpret_cast<volatile const std::uint32_t *>(backing.io[qid * 2 + 1].data() + plan.cq_slot * 16);
        const auto first_last = entry[3];
        // Empty polls use only the frozen phase, with no source loan or call.
        if (((first_last >> 16) & 1) == plan.phase) {
            asm volatile("lfence" ::: "memory");
            const auto result = entry[0];
            const auto reserved = entry[1];
            const auto position = entry[2];
            const auto second_last = entry[3];
            const auto selected =
                transport.accept_completion(qid, plan.cid, {first_last, result, reserved, position, second_last});
            if (selected.kind == nvme::CompletionKind::rejected) {
                Serial::text("AURORA_NVME_COMPLETION_ERROR: status=");
                Serial::number(selected.status);
                Serial::text("\r\n");
                return quarantine("completion");
            }
            require(effects.selected(binding(qid), plan.cid, selected.new_cq_head), "completion-selection");
            Window::write(nvme_base + 0x1004 + qid * 8, 4, selected.new_cq_head);
            ++completed;
            if (!healthy())
                return quarantine("iommu-fault");
            if (status() != 1)
                return quarantine("controller-fault");
            queue_guards();
            require(closed() && effects.acknowledged(binding(qid), plan.cid, selected.new_cq_head),
                    "completion-receipt");
            // Head/phase advance and idle admission occur only after all native
            // physical effects, restored mappings and post-completion checks.
            if (!transport.acknowledged(qid, plan.cid))
                return quarantine("acknowledgment-state");
            return true;
        }
        if ((i & 1023) == 0) {
            if (!healthy())
                return quarantine("iommu-fault");
            if (status() != 1)
                return quarantine("controller-fault");
        }
        asm volatile("pause" ::: "memory");
    }
    return quarantine("completion-timeout");
}
auto command(unsigned qid, std::array<std::byte, 64> bytes) -> void {
    if (!execute(qid, bytes))
        fail(failure_reason);
}
#if !defined(AURORA_PROCESS_FIXTURE) && !defined(AURORA_PRODUCTION)
auto close() -> void {
    // This is the NVMe controller's own lifecycle, not an inference from EDU.
    Window::write(nvme_base + 0x14, 4, 0x460000);
    ready(false);
    Window::write(config_base + 4, 2, 2);
    require(Window::read(config_base + 4, 2) == 2, "bme-revoke");
    put(backing.devices, 0x10 * 32, 3);
    NvmeInvalidation batch{backing.commands, address(backing.commands.data())};
    require(batch.prepare(iommu(0x2000), iommu(0x2008), iommu(0x2020)), "revoke-prepare");
    Window::write(iommu_base + 0x2008, 8, NvmeInvalidation::command_bytes);
    for (U64 i = 0; i < attempts; ++i) {
        const auto result = batch.observe(iommu(0x2000), iommu(0x2008), iommu(0x2020), iommu(0x2010), iommu(0x2018));
        require(result != NvmeInvalidation::Result::failed, "revoke-completion");
        if (result == NvmeInvalidation::Result::complete) {
            require(closed() && tables().verify(arena_base, Bytes{saved_handoff}), "final-mappings");
            Serial::text("AURORA_NVME_REVOKED: controller-ready=0 bme=0 invalidation=1 retained=boot\r\n");
            return;
        }
        asm volatile("pause" ::: "memory");
    }
    batch.expire();
    fail("revoke-timeout");
}
[[nodiscard]] auto pattern(unsigned i, bool written) -> std::byte {
    return std::byte((i * 29 + (written ? 0xb7 : 0x3d)) & 255);
}
auto read_check(const NvmeNamespace &ns, bool written) -> void {
    for (auto &byte : backing.io[Backing::read_data])
        byte = std::byte{0xa5};
    const auto read = NvmeCommand::io(ns, 7, false);
    require(read.has_value(), "read-range");
    command(1, *read);
    for (unsigned i = 0; i < 512; ++i)
        require(backing.io[Backing::read_data][i] == pattern(i, written), "read-data");
    guard(backing.io[Backing::read_data], 512);
    Serial::text("AURORA_NVME_READ: lba=7 bytes=512 pattern=");
    Serial::number(written);
    Serial::text("\r\n");
}
#endif
auto open(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission, bool readonly, bool dual = false)
    -> void {
    require(!begun, "one-shot");
    begun = true;
    arena_base = arena;
    root_base = handoff.get(88);
    table_count = handoff.get(96);
    nvme_base = admission.endpoint_base();
    config_base = admission.endpoint_config_address();
    for (unsigned at = 0; at < Handoff::header; at += 8)
        put(saved_handoff, at, handoff.get(at));
    require(Handoff::valid(saved_handoff, arena) && admission.physical_bits() >= 40 &&
                admission.endpoint_initial_command() == 2 && admission.iommu_base() == iommu_base &&
                config_base == 0xe0010000,
            "entry");
    window_slot = tables().window_slot();
    require(closed() && tables().verify(arena, handoff), "entry-mappings");
    U64 cr0, cr4;
    asm volatile("mov %%cr0, %0; mov %%cr4, %1" : "=r"(cr0), "=r"(cr4));
    require((cr0 & (1ULL << 16)) &&
                !(cr4 & ((1ULL << 7) | (1ULL << 12) | (1ULL << 16) | (1ULL << 17) | (1ULL << 18) | (1ULL << 20))),
            "entry-control");
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0x277));
    require((low & 255) == 6 && (low >> 24) == 0, "entry-pat");
    initialize(readonly);
    transport.create();
    publish();
    command(0, NvmeCommand::identify(true));
    const Bytes controller{backing.io[Backing::read_data]};
    require(controller.get(0, 2) == 0x1b36 && controller.get(80, 4) == 0x10400 && controller.get(512, 1) == 0x66 &&
                controller.get(513, 1) == 0x44 && controller.get(516, 4) >= 1 && (controller.get(525, 1) & 1),
            "identify-controller");
    command(0, NvmeCommand::active_namespaces());
    const auto active = NvmeNamespaceList::parse(backing.io[Backing::read_data], dual);
    require(active.has_value(), "namespace-list");
    const auto count = active->count();
    for (unsigned i = 0; i < count; ++i) {
        command(0, NvmeCommand::identify(false, active->id(i)));
        volumes[i] = NvmeNamespace::parse(backing.io[Backing::read_data], active->id(i));
        require(volumes[i] && volumes[i]->blocks() <= (1ULL << 32), "namespace-format");
    }
    admitted_namespace = volumes[0];
    volume_count = count;
    command(0, NvmeCommand::create_queue(false));
    command(0, NvmeCommand::create_queue(true));
    for (unsigned i = 0; i < count; ++i) {
        Serial::text("AURORA_NVME_READY: nsid=");
        Serial::number(volumes[i]->nsid());
        Serial::text(" blocks=");
        Serial::number(volumes[i]->blocks());
        Serial::text(" lba-bytes=512 queue-entries=2\r\n");
    }
}
} // namespace

auto initialize_nvme_readonly(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission) -> void {
    open(arena, handoff, admission, true);
    readonly_open = true;
}
namespace {
auto readonly_count_entered() -> U64 {
    return readonly_open && !dual_open && recovery.permits_readonly() && mounted.permits_readonly() &&
                   !transport.poisoned() && admitted_namespace
               ? admitted_namespace->blocks()
               : 0;
}
auto recovery_count_entered() -> U64 {
    return !transport.poisoned() && recovery.phase() == NvmeRecoveryPhase::Phase::writer && admitted_namespace
               ? admitted_namespace->blocks()
               : 0;
}
auto mounted_count_entered() -> U64 {
    return !transport.poisoned() && mounted.available() && admitted_namespace ? admitted_namespace->blocks() : 0;
}
auto clear(std::span<std::byte, 512> output) -> void {
    for (auto &byte : output)
        byte = std::byte{};
}
auto read_sector(U64 lba,
                 std::span<std::byte, 512> output,
                 bool mounted_read = false,
                 const NvmeNamespace *selected = nullptr,
                 U64 generation = 0) -> NvmeReadStatus {
    clear(output);
    if (transport.poisoned())
        return NvmeReadStatus::failed;
    // The caller's broker-authenticated scope already binds this exact root.
    // Every source borrow ends before DMA, MMIO or the returned output copy.
    require(process_root && closed(), "readonly-context");
    const auto &ns = selected ? *selected : *admitted_namespace;
    if (!ns.contains(lba, 1))
        return NvmeReadStatus::out_of_range;
    const bool miss = !cache.hit(config_base, ns.nsid(), generation, lba);
    if (mounted_read && !mounted.permit_read(static_cast<unsigned>(transport.remaining(1)), miss))
        return NvmeReadStatus::unavailable;
    if (miss) {
        cache.invalidate();
        // Budget exhaustion is ordinary unavailability, never a failed reserve.
        if (selected && !transport.remaining(1))
            return NvmeReadStatus::unavailable;
        if (recovery.phase() == NvmeRecoveryPhase::Phase::writer &&
            !recovery.permit_read(static_cast<unsigned>(transport.remaining(1))))
            return NvmeReadStatus::unavailable;
        cache_lba = lba - lba % 8;
        const auto remaining = ns.blocks() - cache_lba;
        cache_sectors = static_cast<unsigned>(remaining < 8 ? remaining : 8);
        const auto read = NvmeCommand::io(ns, cache_lba, false, cache_sectors);
        require(read.has_value(), "readonly-range");
        for (auto &byte : backing.io[Backing::read_data])
            byte = std::byte{0xa5};
        if (!execute(1, *read))
            return NvmeReadStatus::failed;
        guard(backing.io[Backing::read_data], cache_sectors * 512);
        cache.publish(config_base, ns.nsid(), generation, cache_lba, cache_sectors);
    }
    const auto offset = static_cast<unsigned>((lba - cache_lba) * 512);
    for (unsigned i = 0; i < 512; ++i)
        output[i] = backing.io[Backing::read_data][offset + i];
    return NvmeReadStatus::success;
}

auto write_sector_entered(U64 lba, std::span<const std::byte, 512> input) -> NvmeReadStatus {
    const auto write = NvmeCommand::io(*admitted_namespace, lba, true);
    require(write.has_value(), "admitted-write-range");
    cache.invalidate();
    for (unsigned i = 0; i < 4096; ++i)
        backing.io[Backing::write_data][i] = i < 512 ? input[i] : std::byte{0xa5};
    if (!execute(1, *write))
        return NvmeReadStatus::failed;
    guard(backing.io[Backing::write_data], 512);
    return NvmeReadStatus::success;
}
} // namespace

auto nvme_sector_count() -> U64 {
    if (!transport.created())
        return 0;
    require(!process_root, "readonly-query-root");
    return readonly_count_entered();
}
auto nvme_sector_count(const NvmeReadContext &context) -> U64 {
    if (!transport.created())
        return 0;
    const ProcessScope scope(context.root(), context.generation());
    return readonly_count_entered();
}
auto nvme_read_sector(const NvmeReadContext &context, U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
    clear(output);
    if (!transport.created())
        return NvmeReadStatus::unavailable;
    const ProcessScope scope(context.root(), context.generation());
    if (!readonly_count_entered())
        return NvmeReadStatus::unavailable;
    return read_sector(lba, output, false, nullptr, context.generation());
}
auto initialize_nvme_dual_readonly(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission) -> void {
    open(arena, handoff, admission, true, true);
    dual_open = readonly_open = true;
    Serial::text("AURORA_NVME_VOLUMES: count=");
    Serial::number(volume_count);
    Serial::text(" readonly=1\r\n");
}
auto nvme_volume_count() -> unsigned {
    if (!transport.created())
        return 0;
    require(!process_root, "volumes-query-root");
    return dual_open && readonly_open && !transport.poisoned() ? volume_count : 0;
}
auto nvme_volume_identity(unsigned slot, unsigned field) -> U64 {
    if (slot >= nvme_volume_count())
        return 0;
    return field == 0 ? config_base : field == 1 ? volumes[slot]->nsid() : field == 2 ? volumes[slot]->blocks() : 0;
}
namespace {
auto authenticated_volume(const NvmeVolumeContext &context) -> const NvmeNamespace * {
    if (!dual_open || !readonly_open || transport.poisoned() || context.controller() != config_base)
        return nullptr;
    for (unsigned i = 0; i < volume_count; ++i)
        if (volumes[i]->nsid() == context.nsid() && volumes[i]->blocks() == context.sectors())
            return &*volumes[i];
    return nullptr;
}
} // namespace
auto nvme_volume_count(const NvmeVolumeContext &context) -> U64 {
    if (!transport.created())
        return 0;
    const ProcessScope scope(context.root(), context.generation());
    const auto *ns = authenticated_volume(context);
    return ns ? ns->blocks() : 0;
}
auto nvme_volume_budget(const NvmeVolumeContext &context) -> unsigned {
    if (!transport.created())
        return 0;
    const ProcessScope scope(context.root(), context.generation());
    return authenticated_volume(context) ? static_cast<unsigned>(transport.remaining(1)) : 0;
}
auto nvme_volume_read(const NvmeVolumeContext &context, U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
    clear(output);
    if (!transport.created())
        return NvmeReadStatus::unavailable;
    const ProcessScope scope(context.root(), context.generation());
    const auto *ns = authenticated_volume(context);
    if (!ns)
        return transport.poisoned() ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    return read_sector(lba, output, false, ns, context.generation());
}
auto initialize_nvme_recovery(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission) -> void {
    require(recovery.begin(), "recovery-one-shot");
    open(arena, handoff, admission, false);
}
auto nvme_recovery_sector_count() -> U64 {
    if (!transport.created())
        return 0;
    require(!process_root, "recovery-query-root");
    return recovery_count_entered();
}
auto nvme_recovery_sector_count(const NvmeRecoveryContext &context) -> U64 {
    if (!transport.created())
        return 0;
    const ProcessScope scope(context.root(), context.generation());
    return recovery_count_entered();
}
auto nvme_recovery_admitted_writes() -> unsigned {
    return recovery.admitted_writes();
}
auto nvme_recovery_admitted_flushes() -> unsigned {
    return recovery.admitted_flushes();
}
auto nvme_recovery_budget(const NvmeRecoveryContext &context) -> unsigned {
    if (!transport.created())
        return 0;
    const ProcessScope scope(context.root(), context.generation());
    return recovery_count_entered() ? static_cast<unsigned>(transport.remaining(1)) : 0;
}
auto nvme_recovery_read(const NvmeRecoveryContext &context, U64 lba, std::span<std::byte, 512> output)
    -> NvmeReadStatus {
    clear(output);
    if (!transport.created())
        return NvmeReadStatus::unavailable;
    const ProcessScope scope(context.root(), context.generation());
    if (!recovery_count_entered())
        return transport.poisoned() ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    return read_sector(lba, output);
}
auto nvme_recovery_write(const NvmeRecoveryContext &context, U64 lba, std::span<const std::byte, 512> input)
    -> NvmeReadStatus {
    if (!transport.created())
        return NvmeReadStatus::unavailable;
    const ProcessScope scope(context.root(), context.generation());
    if (!recovery_count_entered())
        return transport.poisoned() ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    if (!admitted_namespace->contains(lba, 1))
        return NvmeReadStatus::out_of_range;
    if (!recovery.permit_write(static_cast<unsigned>(transport.remaining(1))))
        return NvmeReadStatus::unavailable;
    return write_sector_entered(lba, input);
}
auto nvme_recovery_flush(const NvmeRecoveryContext &context) -> NvmeReadStatus {
    if (!transport.created())
        return NvmeReadStatus::unavailable;
    const ProcessScope scope(context.root(), context.generation());
    if (!recovery_count_entered())
        return transport.poisoned() ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    if (!recovery.permit_flush(static_cast<unsigned>(transport.remaining(1))))
        return NvmeReadStatus::unavailable;
    if (!execute(1, NvmeCommand::flush()))
        return NvmeReadStatus::failed;
    require(recovery.flushed(), "recovery-flush-state");
    return NvmeReadStatus::success;
}
namespace {
// Mechanism only: the caller has entered its one-shot sealing phase. Remove
// just the write-data leaf and wait for a fresh invalidation completion. Queue
// and read mappings and every DMA/IOMMU page remain pinned for this boot.
auto revoke_write_data() -> bool {
    cache.invalidate();
    const auto leaf = address(backing.io[Backing::write_data].data()) | 1 | read_permission;
    require(Bytes{backing.translations}.get(0x7000 / 4096 * 8) == leaf, "writer-write-leaf");
    put(backing.translations, 0x7000 / 4096 * 8, 0);
    asm volatile("mfence" ::: "memory");
    // Boot-global phase already became sealing. Reconstructing a local batch
    // cannot repeat this transition or reuse an earlier completion observation.
    NvmeInvalidation batch{backing.commands, address(backing.commands.data())};
    if (!batch.prepare(iommu(0x2000), iommu(0x2008), iommu(0x2020)))
        return quarantine("writer-revoke-prepare");
    Window::write(iommu_base + 0x2008, 8, NvmeInvalidation::command_bytes);
    for (U64 i = 0; i < attempts; ++i) {
        const auto result = batch.observe(iommu(0x2000), iommu(0x2008), iommu(0x2020), iommu(0x2010), iommu(0x2018));
        if (result == NvmeInvalidation::Result::failed)
            return quarantine("writer-revoke-completion");
        if (result == NvmeInvalidation::Result::complete) {
            require(closed() && Bytes{backing.translations}.get(56) == 0, "writer-revoke-window");
            return true;
        }
        asm volatile("pause" ::: "memory");
    }
    batch.expire();
    return quarantine("writer-revoke-timeout");
}
} // namespace
auto nvme_recovery_seal() -> bool {
    if (transport.poisoned() || !transport.created() || !recovery.seal(static_cast<unsigned>(transport.remaining(1))))
        return false;
    require(!process_root && closed(), "recovery-seal-root");
    return revoke_write_data();
}

auto nvme_recovery_retired() -> bool {
    if (transport.poisoned() || !recovery.retired())
        return false;
    require(!process_root && closed() && Bytes{backing.translations}.get(56) == 0, "recovery-retired");
    cache.invalidate();
    readonly_open = true;
    return true;
}
auto nvme_recovery_abandon() -> void {
    readonly_open = false;
    static_cast<void>(recovery.fail());
    cache.invalidate();
}
auto initialize_nvme_mounted(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission) -> void {
    require(recovery.phase() == NvmeRecoveryPhase::Phase::cold && mounted.begin(), "mounted-one-shot");
    open(arena, handoff, admission, false);
}
auto nvme_mounted_sector_count() -> U64 {
    if (!transport.created())
        return 0;
    require(!process_root, "mounted-query-root");
    return mounted_count_entered();
}
auto nvme_mounted_sector_count(const NvmeMountedContext &context) -> U64 {
    if (!transport.created())
        return 0;
    const ProcessScope scope(context.root(), context.generation());
    return mounted_count_entered();
}
auto nvme_mounted_arm() -> bool {
    if (transport.poisoned() || !transport.created())
        return false;
    require(!process_root && closed(), "mounted-arm-root");
    return mounted.arm();
}
auto nvme_mounted_admitted_writes() -> unsigned {
    return mounted.admitted_writes();
}
auto nvme_mounted_admitted_flushes() -> unsigned {
    return mounted.admitted_flushes();
}
auto nvme_mounted_budget(const NvmeMountedContext &context) -> unsigned {
    if (!transport.created())
        return 0;
    const ProcessScope scope(context.root(), context.generation());
    return mounted_count_entered() ? static_cast<unsigned>(transport.remaining(1)) : 0;
}
auto nvme_mounted_read(const NvmeMountedContext &context, U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
    clear(output);
    if (!transport.created())
        return NvmeReadStatus::unavailable;
    const ProcessScope scope(context.root(), context.generation());
    if (!mounted_count_entered())
        return transport.poisoned() ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    return read_sector(lba, output, true);
}
auto nvme_mounted_write(const NvmeMountedContext &context, U64 lba, std::span<const std::byte, 512> input)
    -> NvmeReadStatus {
    if (!transport.created())
        return NvmeReadStatus::unavailable;
    const ProcessScope scope(context.root(), context.generation());
    if (!mounted_count_entered())
        return transport.poisoned() ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    if (!admitted_namespace->contains(lba, 1))
        return NvmeReadStatus::out_of_range;
    if (!mounted.permit_write(static_cast<unsigned>(transport.remaining(1))))
        return NvmeReadStatus::unavailable;
    return write_sector_entered(lba, input);
}
auto nvme_mounted_flush(const NvmeMountedContext &context) -> NvmeReadStatus {
    if (!transport.created())
        return NvmeReadStatus::unavailable;
    const ProcessScope scope(context.root(), context.generation());
    if (!mounted_count_entered())
        return transport.poisoned() ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    if (!mounted.permit_flush(static_cast<unsigned>(transport.remaining(1))))
        return NvmeReadStatus::unavailable;
    if (!execute(1, NvmeCommand::flush()))
        return NvmeReadStatus::failed;
    require(mounted.flushed(), "mounted-flush-state");
    return NvmeReadStatus::success;
}
auto nvme_mounted_committed() -> bool {
    if (!transport.created())
        return false;
    require(!process_root, "mounted-committed-root");
    return !transport.poisoned() && mounted.phase() == NvmeMountedPhase::Phase::committed;
}
auto nvme_mounted_committed(const NvmeMountedContext &context) -> bool {
    if (!transport.created())
        return false;
    const ProcessScope scope(context.root(), context.generation());
    return !transport.poisoned() && mounted.phase() == NvmeMountedPhase::Phase::committed;
}
auto nvme_mounted_seal() -> bool {
    readonly_open = false;
    if (transport.poisoned() || !transport.created())
        return mounted.fail();
    // remaining_commands() is zero for an outstanding or quarantined command.
    // Recheck the mounted remount reserve now: post-commit reads may have
    // spent it. Recovery keeps its separate, larger readonly reserve.
    if (!mounted.seal(static_cast<unsigned>(transport.remaining(1))))
        return false;
    require(!process_root && closed(), "mounted-seal-root");
    if (!healthy() || status() != 1)
        return quarantine("mounted-seal-health");
    return revoke_write_data();
}
auto nvme_mounted_retired() -> bool {
    readonly_open = false;
    if (transport.poisoned() || !transport.created())
        return mounted.fail();
    if (!mounted.retired())
        return false;
    require(!process_root && closed() && Bytes{backing.translations}.get(56) == 0, "mounted-retired");
    cache.invalidate();
    readonly_open = true;
    return true;
}
auto nvme_mounted_readonly() -> bool {
    return mounted.phase() == NvmeMountedPhase::Phase::readonly && nvme_sector_count() != 0;
}
auto nvme_mounted_abandon() -> void {
    readonly_open = false;
    static_cast<void>(mounted.fail());
    cache.invalidate();
}
#if !defined(AURORA_PROCESS_FIXTURE) && !defined(AURORA_PRODUCTION)
[[noreturn]] auto run_nvme(U64 arena, const Bytes &handoff, const NvmeAdmission &admission) -> void {
    const auto choice = fw_cfg::FwCfg::read_case();
    require(choice && *choice <= 4 && handoff.get(8, 4) == 4, "case");
    selected = *choice;
    open(arena, handoff, admission, false);
    const auto &ns = admitted_namespace;
    require(ns->blocks() == 16384, "namespace-format");
    if (selected == 3) {
        auto invalid = NvmeCommand::flush();
        put(invalid, 0, 0x7f, 1);
        command(1, invalid);
        fail("error-accepted");
    }
    if (selected == 4) {
        require(!NvmeCommand::io(*ns, ns->blocks(), false) && !NvmeCommand::io(*ns, UINT64_MAX, true),
                "range-accepted");
        Serial::text("AURORA_NVME_RANGE_REJECTED: submitted=0\r\n");
    } else {
        read_check(*ns, selected == 2);
        if (selected == 1) {
            for (unsigned i = 0; i < 4096; ++i)
                backing.io[Backing::write_data][i] = i < 512 ? pattern(i, true) : std::byte{0xa5};
            const auto write = NvmeCommand::io(*ns, 7, true);
            require(write.has_value(), "write-range");
            command(1, *write);
            guard(backing.io[Backing::write_data], 512);
            command(1, NvmeCommand::flush());
            ++flushed;
            Serial::text("AURORA_NVME_FLUSH: completed=1\r\n");
            read_check(*ns, true);
        }
    }
    close();
    Serial::text("AURORA_NVME_TERMINAL: case=");
    Serial::number(selected);
    Serial::text(" completed=");
    Serial::number(completed);
    Serial::text(" flushed=");
    Serial::number(flushed);
    Serial::text("\r\n");
    halt();
}
#endif
} // namespace aurora::uefi
