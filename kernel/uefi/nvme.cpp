#include "nvme.hpp"
#include "nvme-transport.hpp"
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
bool begun{}, exposed{}, mapped{}, readonly_open{}, backend_failed{}, cache_valid{};
U64 process_root{}, cache_lba{};
unsigned cache_sectors{};
std::string_view failure_reason{};
constinit std::optional<NvmePolledQueue> retained_admin, retained_io;
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
    return !mapped && window_slot && *window_slot == 0 && cr3 == (process_root ? process_root : root_base) &&
           (flags & 0x202) == 2;
}
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
[[nodiscard]] auto quarantine(NvmePolledQueue &queue, std::string_view reason) -> bool {
    backend_failed = true;
    cache_valid = false;
    static_cast<void>(recovery.fail());
    static_cast<void>(mounted.fail());
    failure_reason = reason;
    queue.quarantine();
    return false;
}
[[nodiscard]] auto execute(NvmePolledQueue &queue, unsigned qid, std::array<std::byte, 64> command) -> bool {
    if (backend_failed)
        return false;
    if (!healthy())
        return quarantine(queue, "iommu-fault");
    if (status() != 1 || !queue.submit(command))
        return quarantine(queue, "queue-submit");
    Window::write(nvme_base + 0x1000 + qid * 8, 4, queue.tail());
    for (U64 i = 0; i < attempts; ++i) {
        const auto result = queue.observe();
        if (result == NvmePolledQueue::Result::quarantined) {
            Serial::text("AURORA_NVME_COMPLETION_ERROR: status=");
            Serial::number(queue.status());
            Serial::text("\r\n");
            return quarantine(queue, "completion");
        }
        if (result == NvmePolledQueue::Result::complete) {
            Window::write(nvme_base + 0x1004 + qid * 8, 4, queue.head());
            ++completed;
            if (!healthy())
                return quarantine(queue, "iommu-fault");
            if (status() != 1)
                return quarantine(queue, "controller-fault");
            queue_guards();
            return true;
        }
        if ((i & 1023) == 0) {
            if (!healthy())
                return quarantine(queue, "iommu-fault");
            if (status() != 1)
                return quarantine(queue, "controller-fault");
        }
        asm volatile("pause" ::: "memory");
    }
    return quarantine(queue, "completion-timeout");
}
auto command(NvmePolledQueue &queue, unsigned qid, std::array<std::byte, 64> bytes) -> void {
    if (!execute(queue, qid, bytes))
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
auto read_check(NvmePolledQueue &queue, const NvmeNamespace &ns, bool written) -> void {
    for (auto &byte : backing.io[Backing::read_data])
        byte = std::byte{0xa5};
    const auto read = NvmeCommand::io(ns, 7, false);
    require(read.has_value(), "read-range");
    command(queue, 1, *read);
    for (unsigned i = 0; i < 512; ++i)
        require(backing.io[Backing::read_data][i] == pattern(i, written), "read-data");
    guard(backing.io[Backing::read_data], 512);
    Serial::text("AURORA_NVME_READ: lba=7 bytes=512 pattern=");
    Serial::number(written);
    Serial::text("\r\n");
}
#endif
auto open(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission, bool readonly) -> void {
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
    publish();
    auto &admin =
        retained_admin.emplace(backing.io[Backing::admin_submission], backing.io[Backing::admin_completion], 0);
    retained_io.emplace(backing.io[Backing::io_submission], backing.io[Backing::io_completion], 1);
    command(admin, 0, NvmeCommand::identify(true));
    const Bytes controller{backing.io[Backing::read_data]};
    require(controller.get(0, 2) == 0x1b36 && controller.get(80, 4) == 0x10400 && controller.get(512, 1) == 0x66 &&
                controller.get(513, 1) == 0x44 && controller.get(516, 4) >= 1 && (controller.get(525, 1) & 1),
            "identify-controller");
    command(admin, 0, NvmeCommand::active_namespaces());
    require(Bytes{backing.io[Backing::read_data]}.get(0, 4) == 1, "namespace-list");
    for (unsigned i = 4; i < 4096; ++i)
        require(backing.io[Backing::read_data][i] == std::byte{}, "namespace-list");
    command(admin, 0, NvmeCommand::identify(false));
    admitted_namespace = NvmeNamespace::parse(backing.io[Backing::read_data]);
    require(admitted_namespace && admitted_namespace->blocks() <= (1ULL << 32), "namespace-format");
    command(admin, 0, NvmeCommand::create_queue(false));
    command(admin, 0, NvmeCommand::create_queue(true));
    Serial::text("AURORA_NVME_READY: nsid=1 blocks=");
    Serial::number(admitted_namespace->blocks());
    Serial::text(" lba-bytes=512 queue-entries=2\r\n");
}
} // namespace

auto initialize_nvme_readonly(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission) -> void {
    open(arena, handoff, admission, true);
    readonly_open = true;
}
auto nvme_sector_count() -> U64 {
    return readonly_open && recovery.permits_readonly() && !backend_failed && admitted_namespace
               ? admitted_namespace->blocks()
               : 0;
}
namespace {
auto read_sector(U64 verified_root,
                 U64 generation,
                 U64 lba,
                 std::span<std::byte, 512> output,
                 bool mounted_read = false) -> NvmeReadStatus {
    for (auto &byte : output)
        byte = std::byte{};
    if (backend_failed)
        return NvmeReadStatus::failed;
    require(!process_root && verified_root && verified_root % 4096 == 0 && generation, "readonly-context");
    process_root = verified_root;
    require(closed(), "readonly-window");
    // ProcessBlockBroker already validated the current service/root/incarnation.
    // It owns full lifecycle tree walks; every MMIO operation here restores the
    // shared transient slot exactly before returning to its user-copy path.
    if (!admitted_namespace->contains(lba, 1)) {
        process_root = 0;
        return NvmeReadStatus::out_of_range;
    }
    const bool miss = !cache_valid || lba < cache_lba || lba - cache_lba >= cache_sectors;
    if (mounted_read && !mounted.permit_read(retained_io->remaining_commands(), miss)) {
        process_root = 0;
        return NvmeReadStatus::unavailable;
    }
    if (miss) {
        if (recovery.phase() == NvmeRecoveryPhase::Phase::writer &&
            !recovery.permit_read(retained_io->remaining_commands())) {
            process_root = 0;
            return NvmeReadStatus::unavailable;
        }
        cache_valid = false;
        cache_lba = lba - lba % 8;
        const auto remaining = admitted_namespace->blocks() - cache_lba;
        cache_sectors = static_cast<unsigned>(remaining < 8 ? remaining : 8);
        const auto read = NvmeCommand::io(*admitted_namespace, cache_lba, false, cache_sectors);
        require(read.has_value(), "readonly-range");
        for (auto &byte : backing.io[Backing::read_data])
            byte = std::byte{0xa5};
        if (!execute(*retained_io, 1, *read)) {
            require(closed(), "readonly-failed-window");
            process_root = 0;
            return NvmeReadStatus::failed;
        }
        guard(backing.io[Backing::read_data], cache_sectors * 512);
        cache_valid = true;
    }
    const auto offset = static_cast<unsigned>((lba - cache_lba) * 512);
    for (unsigned i = 0; i < 512; ++i)
        output[i] = backing.io[Backing::read_data][offset + i];
    require(closed(), "readonly-return-window");
    process_root = 0;
    return NvmeReadStatus::success;
}

auto write_sector_entered(U64 lba, std::span<const std::byte, 512> input) -> NvmeReadStatus {
    const auto write = NvmeCommand::io(*admitted_namespace, lba, true);
    require(write.has_value(), "admitted-write-range");
    cache_valid = false;
    for (unsigned i = 0; i < 4096; ++i)
        backing.io[Backing::write_data][i] = i < 512 ? input[i] : std::byte{0xa5};
    if (!execute(*retained_io, 1, *write))
        return NvmeReadStatus::failed;
    guard(backing.io[Backing::write_data], 512);
    return NvmeReadStatus::success;
}
auto mounted_enter(const NvmeMountedContext &context) -> bool {
    if (backend_failed || !mounted.available() || !retained_io || !admitted_namespace)
        return false;
    require(!process_root && context.root() && context.root() % 4096 == 0 && context.generation(), "mounted-context");
    process_root = context.root();
    require(closed(), "mounted-window");
    return true;
}
auto mounted_leave(NvmeReadStatus result) -> NvmeReadStatus {
    require(closed(), "mounted-return-window");
    process_root = 0;
    return result;
}
auto recovery_enter(const NvmeRecoveryContext &context) -> bool {
    if (backend_failed || recovery.phase() != NvmeRecoveryPhase::Phase::writer || !retained_io || !admitted_namespace)
        return false;
    require(!process_root && context.root() && context.root() % 4096 == 0 && context.generation(), "recovery-context");
    process_root = context.root();
    require(closed(), "recovery-window");
    return true;
}
auto recovery_leave(NvmeReadStatus result) -> NvmeReadStatus {
    require(closed(), "recovery-return-window");
    process_root = 0;
    return result;
}
} // namespace

auto nvme_read_sector(const NvmeReadContext &context, U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
    if (!nvme_sector_count() || !retained_io) {
        for (auto &byte : output)
            byte = std::byte{};
        return NvmeReadStatus::unavailable;
    }
    return read_sector(context.root(), context.generation(), lba, output);
}
auto initialize_nvme_recovery(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission) -> void {
    require(recovery.begin(), "recovery-one-shot");
    open(arena, handoff, admission, false);
}
auto nvme_recovery_sector_count() -> U64 {
    return !backend_failed && recovery.phase() == NvmeRecoveryPhase::Phase::writer && admitted_namespace
               ? admitted_namespace->blocks()
               : 0;
}
auto nvme_recovery_admitted_writes() -> unsigned {
    return recovery.admitted_writes();
}
auto nvme_recovery_admitted_flushes() -> unsigned {
    return recovery.admitted_flushes();
}
auto nvme_recovery_budget(const NvmeRecoveryContext &context) -> unsigned {
    if (!recovery_enter(context))
        return 0;
    const auto result = retained_io->remaining_commands();
    static_cast<void>(recovery_leave(NvmeReadStatus::success));
    return result;
}
auto nvme_recovery_read(const NvmeRecoveryContext &context, U64 lba, std::span<std::byte, 512> output)
    -> NvmeReadStatus {
    if (!nvme_recovery_sector_count()) {
        for (auto &byte : output)
            byte = std::byte{};
        return backend_failed ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    }
    return read_sector(context.root(), context.generation(), lba, output);
}
auto nvme_recovery_write(const NvmeRecoveryContext &context, U64 lba, std::span<const std::byte, 512> input)
    -> NvmeReadStatus {
    if (!recovery_enter(context))
        return backend_failed ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    const auto write = NvmeCommand::io(*admitted_namespace, lba, true);
    if (!write)
        return recovery_leave(NvmeReadStatus::out_of_range);
    if (!recovery.permit_write(retained_io->remaining_commands()))
        return recovery_leave(NvmeReadStatus::unavailable);
    return recovery_leave(write_sector_entered(lba, input));
}
auto nvme_recovery_flush(const NvmeRecoveryContext &context) -> NvmeReadStatus {
    if (!recovery_enter(context))
        return backend_failed ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    if (!recovery.permit_flush(retained_io->remaining_commands()))
        return recovery_leave(NvmeReadStatus::unavailable);
    if (!execute(*retained_io, 1, NvmeCommand::flush()))
        return recovery_leave(NvmeReadStatus::failed);
    require(recovery.flushed(), "recovery-flush-state");
    return recovery_leave(NvmeReadStatus::success);
}
auto nvme_recovery_seal() -> bool {
    if (backend_failed || !retained_io || !recovery.seal(retained_io->remaining_commands()))
        return false;
    require(!process_root && closed(), "recovery-seal-root");
    cache_valid = false;
    const auto leaf = address(backing.io[Backing::write_data].data()) | 1 | read_permission;
    require(Bytes{backing.translations}.get(0x7000 / 4096 * 8) == leaf, "recovery-write-leaf");
    put(backing.translations, 0x7000 / 4096 * 8, 0);
    asm volatile("mfence" ::: "memory");
    // Boot-global phase already became sealing. Reconstructing a local batch
    // cannot repeat this transition or reuse an earlier completion observation.
    NvmeInvalidation batch{backing.commands, address(backing.commands.data())};
    if (!batch.prepare(iommu(0x2000), iommu(0x2008), iommu(0x2020)))
        return quarantine(*retained_io, "recovery-revoke-prepare");
    Window::write(iommu_base + 0x2008, 8, NvmeInvalidation::command_bytes);
    for (U64 i = 0; i < attempts; ++i) {
        const auto result = batch.observe(iommu(0x2000), iommu(0x2008), iommu(0x2020), iommu(0x2010), iommu(0x2018));
        if (result == NvmeInvalidation::Result::failed)
            return quarantine(*retained_io, "recovery-revoke-completion");
        if (result == NvmeInvalidation::Result::complete) {
            require(closed() && Bytes{backing.translations}.get(56) == 0, "recovery-revoke-window");
            return true;
        }
        asm volatile("pause" ::: "memory");
    }
    batch.expire();
    return quarantine(*retained_io, "recovery-revoke-timeout");
}
auto nvme_recovery_retired() -> bool {
    if (backend_failed || !recovery.retired())
        return false;
    require(!process_root && closed() && Bytes{backing.translations}.get(56) == 0, "recovery-retired");
    cache_valid = false;
    readonly_open = true;
    return true;
}
auto nvme_recovery_abandon() -> void {
    readonly_open = false;
    static_cast<void>(recovery.fail());
    cache_valid = false;
}
auto initialize_nvme_mounted(U64 arena, const Bytes &handoff, const NvmeControllerAdmission &admission) -> void {
    require(recovery.phase() == NvmeRecoveryPhase::Phase::cold && mounted.begin(), "mounted-one-shot");
    open(arena, handoff, admission, false);
}
auto nvme_mounted_sector_count() -> U64 {
    return !backend_failed && mounted.available() && admitted_namespace ? admitted_namespace->blocks() : 0;
}
auto nvme_mounted_arm() -> bool {
    if (backend_failed || !retained_io)
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
    if (!mounted_enter(context))
        return 0;
    const auto result = retained_io->remaining_commands();
    static_cast<void>(mounted_leave(NvmeReadStatus::success));
    return result;
}
auto nvme_mounted_read(const NvmeMountedContext &context, U64 lba, std::span<std::byte, 512> output) -> NvmeReadStatus {
    if (!nvme_mounted_sector_count()) {
        for (auto &byte : output)
            byte = std::byte{};
        return backend_failed ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    }
    return read_sector(context.root(), context.generation(), lba, output, true);
}
auto nvme_mounted_write(const NvmeMountedContext &context, U64 lba, std::span<const std::byte, 512> input)
    -> NvmeReadStatus {
    if (!mounted_enter(context))
        return backend_failed ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    if (!admitted_namespace->contains(lba, 1))
        return mounted_leave(NvmeReadStatus::out_of_range);
    if (!mounted.permit_write(retained_io->remaining_commands()))
        return mounted_leave(NvmeReadStatus::unavailable);
    return mounted_leave(write_sector_entered(lba, input));
}
auto nvme_mounted_flush(const NvmeMountedContext &context) -> NvmeReadStatus {
    if (!mounted_enter(context))
        return backend_failed ? NvmeReadStatus::failed : NvmeReadStatus::unavailable;
    if (!mounted.permit_flush(retained_io->remaining_commands()))
        return mounted_leave(NvmeReadStatus::unavailable);
    if (!execute(*retained_io, 1, NvmeCommand::flush()))
        return mounted_leave(NvmeReadStatus::failed);
    require(mounted.flushed(), "mounted-flush-state");
    return mounted_leave(NvmeReadStatus::success);
}
auto nvme_mounted_abandon() -> void {
    static_cast<void>(mounted.fail());
    cache_valid = false;
}
#if !defined(AURORA_PROCESS_FIXTURE) && !defined(AURORA_PRODUCTION)
[[noreturn]] auto run_nvme(U64 arena, const Bytes &handoff, const NvmeAdmission &admission) -> void {
    const auto choice = fw_cfg::FwCfg::read_case();
    require(choice && *choice <= 4 && handoff.get(8, 4) == 4, "case");
    selected = *choice;
    open(arena, handoff, admission, false);
    const auto &ns = admitted_namespace;
    require(ns->blocks() == 16384, "namespace-format");
    auto &io = *retained_io;
    if (selected == 3) {
        auto invalid = NvmeCommand::flush();
        put(invalid, 0, 0x7f, 1);
        command(io, 1, invalid);
        fail("error-accepted");
    }
    if (selected == 4) {
        require(!NvmeCommand::io(*ns, ns->blocks(), false) && !NvmeCommand::io(*ns, UINT64_MAX, true),
                "range-accepted");
        Serial::text("AURORA_NVME_RANGE_REJECTED: submitted=0\r\n");
    } else {
        read_check(io, *ns, selected == 2);
        if (selected == 1) {
            for (unsigned i = 0; i < 4096; ++i)
                backing.io[Backing::write_data][i] = i < 512 ? pattern(i, true) : std::byte{0xa5};
            const auto write = NvmeCommand::io(*ns, 7, true);
            require(write.has_value(), "write-range");
            command(io, 1, *write);
            guard(backing.io[Backing::write_data], 512);
            command(io, 1, NvmeCommand::flush());
            ++flushed;
            Serial::text("AURORA_NVME_FLUSH: completed=1\r\n");
            read_check(io, *ns, true);
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
