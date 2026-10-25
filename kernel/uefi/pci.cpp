#include "pci.hpp"
#if defined(AURORA_UEFI_NVME_PREPARE) &&                                                                               \
    (!defined(AURORA_UEFI_ACPI) || !defined(AURORA_UEFI_PCI) || !defined(AURORA_UEFI_BAR_CAPTURE) ||                   \
     !defined(AURORA_UEFI_BAR_EDK2) || defined(AURORA_UEFI_RUNTIME) || defined(AURORA_UEFI_IVRS) ||                    \
     defined(AURORA_UEFI_TABLES))
#error "NVMe preparation requires the standalone BAR profile"
#endif
#if defined(AURORA_PCI_FIXTURE) &&                                                                                     \
    (!defined(AURORA_UEFI_ACPI) || !defined(AURORA_UEFI_PCI) || defined(AURORA_UEFI_RUNTIME) ||                        \
     defined(AURORA_UEFI_BAR_CAPTURE) || defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT))
#error "PCI fixture requires the standalone ACPI/PCI profile"
#endif
#if defined(AURORA_IVRS_FIXTURE) && (!defined(AURORA_UEFI_IVRS) || !defined(AURORA_UEFI_PCI) ||                        \
                                     !defined(AURORA_UEFI_BAR_CAPTURE) || defined(AURORA_PCI_FIXTURE))
#error "IVRS fault fixture requires its explicit cold observation profile"
#endif
#if defined(AURORA_BAR_FIXTURE) &&                                                                                     \
    (!defined(AURORA_UEFI_BAR_CAPTURE) || !defined(AURORA_UEFI_BAR_EDK2) || defined(AURORA_UEFI_IVRS) ||               \
     defined(AURORA_UEFI_NVME_PREPARE) || defined(AURORA_PCI_FIXTURE))
#error "BAR fixture requires the standalone read-only BAR profile"
#endif
#if defined(AURORA_UEFI_IVRS) && !defined(AURORA_IVRS_FIXTURE)
#error "IVRS read profiles are boot-selected cases of the IVRS fixture image"
#endif
#ifdef AURORA_UEFI_PCI
#include "pci-policy.hpp"
#ifdef AURORA_UEFI_IOMMU_EVENT
#include "event-profile-policy.hpp"
#include "event-handoff-policy.hpp"
#include "event-intake.hpp"
#endif
#ifdef AURORA_UEFI_IVRS
#include "ivrs-policy.hpp"
#endif
#ifdef AURORA_UEFI_BAR_CAPTURE
#include "bar-policy.hpp"
#include "bar-record.hpp"
#ifdef AURORA_UEFI_NVME_PREPARE
#include "nvme-queues.hpp"
#endif
#endif
#include "acpi-policy.hpp"
#include "tables.hpp"
#include "../console.hpp"
namespace aurora::uefi {
namespace {
using U64 = std::uint64_t;
using hardware::Serial;
#if defined(AURORA_PCI_FIXTURE) || defined(AURORA_IVRS_FIXTURE) || defined(AURORA_BAR_FIXTURE)
#include "fixture-selector.inc"
Fixture pci_fixture{};
#endif
class EcamWindow final {
    const Q35Ecam aperture_;
    volatile U64 *slot_;
    WindowAuthority authority_;
    unsigned reads_{};
    unsigned revoked_{};
#ifdef AURORA_UEFI_IOMMU_EVENT
    AURORA_UEFI_EVENT_OUTLINE [[nodiscard]] auto begin(U64 page, bool writable = false) -> std::optional<WindowTicket>
#else
    [[nodiscard]] auto begin(U64 page) -> std::optional<WindowTicket>
#endif
    {
        if (!slot_ || *slot_ != 0 || !aperture_.admits_page(page))
            return std::nullopt;
        auto ticket = authority_.acquire();
        if (!ticket)
            return std::nullopt;
        // PAT3 (PWT|PCD) was verified UC; supervisor, NX, nonglobal.
#ifdef AURORA_UEFI_IOMMU_EVENT
        // Only Event command reduction requests a writable mapping.
        *slot_ = page | 1 | 8 | 16 | PageTables::nx | (writable ? 2 : 0);
#else
        *slot_ = page | 1 | 8 | 16 | PageTables::nx;
#endif
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        ++reads_;
        return ticket;
    }
    AURORA_UEFI_EVENT_OUTLINE [[nodiscard]] auto end(WindowTicket ticket) -> bool {
        if (!authority_.accepts(ticket))
            return false;
        *slot_ = 0;
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        ++revoked_;
        return *slot_ == 0 && authority_.revoke(ticket);
    }
    AURORA_UEFI_EVENT_OUTLINE [[nodiscard]] static auto snapshot() -> std::array<std::byte, 64> {
        std::array<std::byte, 64> result{};
        // Naturally aligned configuration DWORD loads, restricted to standard header.
        for (unsigned offset = 0; offset < 64; offset += 4) {
            const auto value = *reinterpret_cast<volatile const std::uint32_t *>(PageTables::window_address + offset);
            put(result, offset, value, 4);
            if (offset == 0 && (value & 65535) == 65535)
                break;
        }
        return result;
    }

public:
    EcamWindow(const Q35Ecam &aperture, volatile U64 *slot) : aperture_(aperture), slot_(slot) {
    }
    AURORA_UEFI_EVENT_OUTLINE [[nodiscard]] auto read(U64 page) -> std::optional<std::array<std::byte, 64>> {
        auto ticket = begin(page);
        if (!ticket)
            return std::nullopt;
        const auto first = snapshot();
        const auto second = snapshot();
        if (!end(*ticket) || first != second)
            return std::nullopt;
        auto result = first;
#ifdef AURORA_PCI_FIXTURE
        if (pci_fixture == Fixture::pci_cycle && (Bytes{result}.get(14, 1) & 127) == 1) {
            put(result, 25, (page - Q35Ecam::base) >> 20, 1);
            // Keep the configured subordinate bound: secondary now points at its own parent.
        }
#endif
        return result;
    }
#if defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
    [[nodiscard]] auto iommu_capability(U64 page) -> std::optional<std::array<std::byte, 48>> {
        auto ticket = begin(page);
        if (!ticket)
            return std::nullopt;
        std::array<std::byte, 48> first{}, second{};
        for (auto *copy : {&first, &second})
            for (unsigned offset = 0; offset < 48; offset += 4)
                put(*copy,
                    offset,
                    *reinterpret_cast<volatile const std::uint32_t *>(PageTables::window_address + 0x40 + offset),
                    4);
        if (!end(*ticket) || first != second)
            return std::nullopt;
        return first;
    }
#endif
#ifdef AURORA_UEFI_IOMMU_EVENT
    [[gnu::noinline, nodiscard]] auto reduce_event_command(const EventPciFact &before, unsigned command)
        -> std::optional<std::array<std::byte, 64>> {
        const auto rid = before.requester();
        const auto page = aperture_.address(before.segment, before.bus, before.device, before.function);
        if (!page || Bytes{before.header}.get(4, 2) != 7)
            return std::nullopt;
        if (rid == 8 && command == 7)
            return read(*page); // Never write the IOMMU command.
        if (!((rid == 0x20 && command == 2) ||
              ((rid == 0 || rid == 0xf8 || rid == 0xfa || rid == 0xfb) && command == 3)))
            return std::nullopt;
        auto ticket = begin(*page, true);
        if (!ticket)
            return std::nullopt;
        const auto first = snapshot(), second = snapshot();
        if (first != before.header || second != before.header) {
            (void)end(*ticket);
            return std::nullopt;
        }
        // Command only. A DWORD store would also touch W1C PCI status.
        *reinterpret_cast<volatile std::uint16_t *>(PageTables::window_address + 4) =
            static_cast<std::uint16_t>(command);
        const auto after = snapshot(), again = snapshot();
        if (!end(*ticket) || after != again)
            return std::nullopt;
        return after;
    }
#endif
    [[nodiscard]] auto probe_write() -> bool {
        auto ticket = begin(Q35Ecam::base);
        if (!ticket)
            return false;
        Serial::text("AURORA_PCI_WRITE_PROBE\r\n");
        // Deliberate negative gate: the CPU must reject before a PCI transaction.
        *reinterpret_cast<volatile std::uint32_t *>(PageTables::window_address) = 0;
        return end(*ticket);
    }
    [[nodiscard]] auto closed() const -> bool {
        return slot_ && *slot_ == 0 && reads_ == revoked_;
    }
    [[nodiscard]] auto reads() const -> unsigned {
        return reads_;
    }
};
#if defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
// Keep scan construction temporaries out of the later BAR/IOMMU call path.
// The fixed bootstrap stack and its guard are unchanged.
[[gnu::noinline]] auto scan_ivrs_inventory(const Q35Ecam &aperture, EcamWindow &window) -> std::optional<PciInventory> {
    return PciInventory::scan(aperture, [&](U64 page) {
        return window.read(page);
    });
}
#endif
#ifdef AURORA_UEFI_IOMMU_EVENT
#include "event-reader.inc"
#endif
#ifdef AURORA_UEFI_BAR_CAPTURE
#ifdef AURORA_UEFI_NVME_PREPARE
#include "nvme-prepare.inc"
#endif
#include "bar-reader.inc"
#ifdef AURORA_UEFI_IVRS
#include "ivrs-reader.inc"
#endif
#endif
} // namespace
auto discover_pci(U64 arena,
                  const Bytes &handoff,
                  std::span<const std::byte> source,
                  unsigned bits,
                  [[maybe_unused]] memory::PhysicalPages &pool) -> bool {
#ifdef AURORA_PCI_FIXTURE
    // ACPI has closed its window before this call. Admit the selector before
    // parsing or acquiring any PCI mapping; no normal image contains this path.
    const auto selected = read_fixture(Fixture::pci_baseline, Fixture::pci_revoked);
    if (!selected)
        return false;
    pci_fixture = *selected;
#endif
#ifdef AURORA_IVRS_FIXTURE
    const auto selected = read_fixture(Fixture::ivrs_write, Fixture::ivrs_read);
    if (!selected)
        return false;
    pci_fixture = *selected;
#endif
#ifdef AURORA_BAR_FIXTURE
    const auto selected = read_fixture(Fixture::bar_read, Fixture::bar_alias);
    if (!selected)
        return false;
    pci_fixture = *selected;
#endif
    // The source is an owned, consistent ACPI snapshot. No firmware pointer escapes.
    std::array<std::byte, 108> storage{};
    if (source.size() < 60 || source.size() > storage.size())
        return false;
    for (std::size_t i = 0; i < source.size(); ++i)
        storage[i] = source[i];
    auto table = std::span<std::byte>{storage}.first(source.size());
#ifdef AURORA_PCI_FIXTURE
    if (pci_fixture == Fixture::pci_checksum)
        table[9] ^= std::byte{1};
#endif
    const auto mcfg = Mcfg::parse(table, bits);
    if (!mcfg)
        return false;
    const auto map = std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + Handoff::map_offset),
                                                static_cast<std::size_t>(handoff.get(32))};
    const auto aperture = Q35Ecam::authorize(*mcfg, map, handoff.get(40), arena);
    if (!aperture)
        return false;
    const PageTables tables{handoff.get(88), static_cast<std::size_t>(handoff.get(96))};
    if (!tables.verify(arena, handoff))
        return false;
    U64 root;
    asm volatile("mov %%cr3, %0" : "=r"(root));
    if (root != handoff.get(88))
        return false;
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0x277));
    if ((low >> 24) != 0)
        return false;
    EcamWindow window{*aperture, tables.window_slot()};
    Serial::text("AURORA_PCI_APERTURE: base=");
    Serial::number(Q35Ecam::base);
    Serial::text(" bytes=");
    Serial::number(Q35Ecam::bytes);
    Serial::text(" segment=0 first=0 last=255\r\n");
#ifdef AURORA_PCI_FIXTURE
    if (pci_fixture == Fixture::pci_write)
        return window.probe_write();
    if (pci_fixture == Fixture::pci_revoked) {
        if (!window.read(Q35Ecam::base) || !window.closed())
            return false;
        Serial::text("AURORA_PCI_REVOKED_PROBE\r\n");
        static_cast<void>(*reinterpret_cast<volatile const std::uint32_t *>(PageTables::window_address));
        return false;
    }
#endif
#if defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
    const auto inventory = scan_ivrs_inventory(*aperture, window);
#else
    const auto inventory = PciInventory::scan(*aperture, [&](U64 page) {
        return window.read(page);
    });
#endif
    if (!inventory || !window.closed() || !tables.verify(arena, handoff))
        return false;
    for (const auto &function : inventory->functions()) {
        Serial::text("AURORA_PCI_FUNCTION: segment=");
        Serial::number(function.segment);
        Serial::text(" bus=");
        Serial::number(function.bus);
        Serial::text(" device=");
        Serial::number(function.device);
        Serial::text(" function=");
        Serial::number(function.function);
        Serial::text(" vendor=");
        Serial::number(function.vendor);
        Serial::text(" product=");
        Serial::number(function.device_id);
        Serial::text(" class=");
        Serial::number(function.class_code);
        Serial::text(" subclass=");
        Serial::number(function.subclass);
        Serial::text(" interface=");
        Serial::number(function.programming_interface);
        Serial::text(" header=");
        Serial::number(function.header_type);
        Serial::text(" command=");
        Serial::number(function.command);
        Serial::text(" secondary=");
        Serial::number(function.secondary_bus);
        Serial::text(" subordinate=");
        Serial::number(function.subordinate_bus);
        Serial::text("\r\n");
    }
    Serial::text("AURORA_PCI_INVENTORY: functions=");
    Serial::number(inventory->count());
    Serial::text(" buses=");
    Serial::number(inventory->bus_count());
    Serial::text("\r\n");
    Serial::text("AURORA_PCI_WINDOW_CLOSED: reads=");
    Serial::number(window.reads());
    Serial::text("\r\n");
#ifdef AURORA_UEFI_IOMMU_EVENT
    return inspect_event(arena, handoff, *aperture, window, *inventory, bits);
#elif defined(AURORA_UEFI_IVRS)
    const auto ivrs_bytes =
        std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + 0x60000), Ivrs::maximum_table};
    const auto ivrs_length = Bytes{ivrs_bytes}.get(4, 4);
    const auto facts =
        ivrs_length <= ivrs_bytes.size() ? Ivrs::parse_qemu_10_0_13(ivrs_bytes.first(ivrs_length), bits) : std::nullopt;
    if (!facts || !facts->matches_inventory(inventory->functions(), 0, 0, 2, 0)) {
        Serial::text("AURORA_IVRS_REJECTED: reason=requester-coverage\r\n");
        return false;
    }
    if (!inspect_bar(arena, handoff, *aperture, window, *inventory, bits, pool))
        return false;
    return inspect_ivrs(arena, handoff, *aperture, window, *inventory, bits);
#elif defined(AURORA_UEFI_BAR_CAPTURE)
    return inspect_bar(arena, handoff, *aperture, window, *inventory, bits, pool);
#elif defined(AURORA_UEFI_BAR_ADMISSION)
    unsigned candidates = 0;
    for (const auto &function : inventory->functions()) {
        if (function.vendor != 0x1b36 || function.device_id != 0x10 || function.class_code != 1 ||
            function.subclass != 8 || function.programming_interface != 2 || function.header_type != 0)
            continue;
        ++candidates;
        Serial::text("AURORA_BAR_ADMISSION: segment=");
        Serial::number(function.segment);
        Serial::text(" bus=");
        Serial::number(function.bus);
        Serial::text(" device=");
        Serial::number(function.device);
        Serial::text(" function=");
        Serial::number(function.function);
        Serial::text(" command=");
        Serial::number(function.command);
        // This early refusal creates no BAR mapping or controller access grant.
        Serial::text(" grant=0 reason=");
        if (function.command & 4)
            Serial::text("bus-master-enabled");
        else
            Serial::text("resource-handoff-required");
        Serial::text("\r\n");
    }
    if (candidates != 1)
        Serial::text("AURORA_BAR_TARGET_REJECTED\r\n");
    return false;
#else
    return true;
#endif
}
} // namespace aurora::uefi
#endif
