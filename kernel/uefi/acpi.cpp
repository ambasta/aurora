#include "acpi.hpp"
#include "acpi-policy.hpp"
#include "tables.hpp"
#if defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
#include "ivrs-policy.hpp"
#ifdef AURORA_UEFI_IOMMU_EVENT
#include "event-profile-policy.hpp"
#endif
#endif
#ifdef AURORA_UEFI_PCI
#include "pci.hpp"
#endif
#include "../console.hpp"
namespace aurora::uefi {
#ifdef AURORA_UEFI_IOMMU_EVENT
[[gnu::noinline]] auto read_event_ivrs(std::span<const std::byte> bytes, unsigned bits) -> std::optional<EventIvrs> {
    return EventIvrs::parse_qemu_default(bytes, bits);
}
#endif

#if defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_GRAPHICAL_CONSOLE) ||   \
    defined(AURORA_PROCESS_FIXTURE)
namespace {
constinit std::optional<TimerTopology> copied_timer_topology;
}
auto discovered_timer_topology() -> const std::optional<TimerTopology> & {
    return copied_timer_topology;
}
#endif
namespace {
using hardware::Serial;
using U64 = std::uint64_t;
auto bytes(U64 base, std::size_t size) -> std::span<std::byte> {
    return {reinterpret_cast<std::byte *>(base), size};
}
class ReadWindow final {
    const FirmwareRanges &ranges_;
    volatile U64 *slot_;
    WindowAuthority authority_;
    unsigned bits_;
    unsigned copies_{};
    unsigned revocations_{};
    [[nodiscard]] auto begin(U64 page) -> std::optional<WindowTicket> {
        if (!slot_ || *slot_ != 0 || page % 4096 || bits_ < 32 || bits_ > 52 || page > (1ULL << bits_) - 4096 ||
            !ranges_.readable(page, 4096))
            return std::nullopt;
        auto ticket = authority_.acquire();
        if (!ticket)
            return std::nullopt;
        *slot_ = page | 1 | PageTables::nx;
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        return ticket;
    }
    [[nodiscard]] auto end(WindowTicket ticket) -> bool {
        if (!authority_.accepts(ticket))
            return false;
        *slot_ = 0;
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        ++revocations_;
        return *slot_ == 0 && authority_.revoke(ticket);
    }

public:
    ReadWindow(const FirmwareRanges &ranges, volatile U64 *slot, unsigned bits)
        : ranges_(ranges), slot_(slot), bits_(bits) {
    }
    [[nodiscard]] auto copy(U64 physical, std::span<std::byte> destination) -> bool {
        if (destination.empty() || destination.size() > Acpi::maximum_table ||
            !ranges_.readable(physical, destination.size()))
            return false;
        std::size_t done = 0;
        while (done < destination.size()) {
            const auto chunk = ReadPlan{physical, destination.size()}.next(done);
            if (!chunk)
                return false;
            auto ticket = begin(chunk->page);
            if (!ticket)
                return false;
            const auto offset = chunk->offset, count = chunk->count;
            for (std::size_t i = 0; i < count; ++i)
                destination[done + i] =
                    *reinterpret_cast<volatile const std::byte *>(PageTables::window_address + offset + i);
            if (!end(*ticket))
                return false;
            done += count;
            ++copies_;
        }
        return true;
    }
    [[nodiscard]] auto table(U64 physical, std::span<std::byte> storage, std::string_view signature)
        -> std::optional<std::span<const std::byte>> {
        std::array<std::byte, 36> header{};
        if (!copy(physical, header) || !Acpi::signature(header, signature))
            return std::nullopt;
        const auto size = Bytes{header}.get(4, 4);
        if (size < 36 || size > storage.size() || size > Acpi::maximum_table)
            return std::nullopt;
        auto snapshot = storage.first(size);
        if (!copy(physical, snapshot))
            return std::nullopt;
        if (!Acpi::same_header(snapshot, header))
            return std::nullopt;
        if (!Acpi::table(snapshot, signature))
            return std::nullopt;
        return snapshot;
    }
    [[nodiscard]] auto probe_write(U64 physical) -> bool {
        auto ticket = begin(physical & ~U64{4095});
        if (!ticket)
            return false;
        Serial::text("AURORA_ACPI_WRITE_PROBE\r\n");
        *reinterpret_cast<volatile std::uint8_t *>(PageTables::window_address) = 0;
        return end(*ticket);
    }
    [[nodiscard]] auto closed() const -> bool {
        return slot_ && *slot_ == 0 && copies_ == revocations_;
    }
    [[nodiscard]] auto copies() const -> unsigned {
        return copies_;
    }
};
[[maybe_unused]] auto fix_checksum(std::span<std::byte> table) -> void {
    table[9] = std::byte{0};
    unsigned sum = 0;
    for (auto value : table)
        sum += std::to_integer<unsigned>(value);
    table[9] = std::byte(0U - sum);
}
} // namespace
#if defined(AURORA_UEFI_TABLES)
[[gnu::noinline]] auto
prepare_table_acpi(U64 arena, const Bytes &handoff, unsigned &copied_bits, std::size_t &copied_mcfg_size) -> bool {
#elif defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
[[gnu::noinline]] auto
prepare_ivrs_acpi(U64 arena, const Bytes &handoff, unsigned &copied_bits, std::size_t &copied_mcfg_size) -> bool {
#elif defined(AURORA_UEFI_PCI)
[[gnu::noinline]] auto
prepare_service_acpi(U64 arena, const Bytes &handoff, unsigned &copied_bits, std::size_t &copied_mcfg_size) -> bool {
#else
auto discover_acpi(U64 arena, const Bytes &handoff, [[maybe_unused]] memory::PhysicalPages &pool) -> bool {
#endif
#ifdef AURORA_PLATFORM_FIXTURE
    // The loader admitted and copied the fw_cfg row before any firmware window
    // exists. Only PCI rows need MCFG; only IVRS rows need IVRS and the q35 LAPIC.
    using platform::Fixture;
    const auto fixture = platform::row(handoff.get(Handoff::fixture_offset));
    const bool pci_row = platform::pci(fixture), ivrs_row = platform::ivrs(fixture);
#else
    [[maybe_unused]] constexpr bool pci_row = true, ivrs_row = true;
#endif
#if defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_GRAPHICAL_CONSOLE) ||   \
    defined(AURORA_PROCESS_FIXTURE)
    copied_timer_topology.reset();
#endif
    std::uint32_t a, b, c, d;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(1), "c"(0));
    if (!(d & (1U << 16)))
        return false;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000000U), "c"(0));
    if (a < 0x80000008U)
        return false;
    asm volatile("cpuid" : "=a"(a), "=b"(b), "=c"(c), "=d"(d) : "a"(0x80000008U), "c"(0));
    const auto physical_bits = a & 255;
    std::uint32_t low, high;
    asm volatile("rdmsr" : "=a"(low), "=d"(high) : "c"(0x277));
    if ((low & 255) != 6 || physical_bits < 32 || physical_bits > 52)
        return false; // PAT0=WB, one cache policy for eligible RAM.
    const FirmwareRanges ranges{
        bytes(arena + Handoff::map_offset, handoff.get(32)), handoff.get(40), arena, physical_bits};
    const PageTables tables{handoff.get(88), static_cast<std::size_t>(handoff.get(96))};
    auto *slot = tables.window_slot();
    if (!slot || *slot != 0)
        return false;
    ReadWindow window{ranges, slot, physical_bits};
    auto source = handoff.get(112);
#ifdef AURORA_PLATFORM_FIXTURE
    if (fixture == Fixture::acpi_bad_source)
        source = 0xfec00000;
    if (fixture == Fixture::acpi_write)
        return window.probe_write(source);
#endif
    std::array<std::byte, 36> rsdp_header{};
    if (!window.copy(source, rsdp_header))
        return false;
    const auto rsdp_size = Bytes{rsdp_header}.get(20, 4);
    if (rsdp_size < 36 || rsdp_size > 4096)
        return false;
    auto rsdp = bytes(arena + 0x80000, rsdp_size);
    if (!window.copy(source, rsdp))
        return false;
    if (!Acpi::same_header(rsdp, rsdp_header))
        return false;
#ifdef AURORA_PLATFORM_FIXTURE
    if (fixture == Fixture::acpi_revoked) {
        if (!window.closed())
            return false;
        Serial::text("AURORA_ACPI_REVOKED_PROBE\r\n");
        static_cast<void>(*reinterpret_cast<volatile const std::byte *>(PageTables::window_address));
        return false;
    }
#endif
    const auto xsdt_address = Acpi::rsdp(rsdp);
    if (!xsdt_address)
        return false;
    auto xsdt = window.table(*xsdt_address, bytes(arena + 0x60000, Acpi::maximum_table), "XSDT");
    if (!xsdt || !Acpi::xsdt(*xsdt, *xsdt_address))
        return false;
    U64 madt_address = 0;
#if defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
    U64 ivrs_address = 0;
#endif
#ifdef AURORA_UEFI_PCI
    U64 mcfg_address = 0;
#endif
    for (std::size_t at = 36; at < xsdt->size(); at += 8) {
        const auto candidate = Bytes{*xsdt}.get(at);
        if (candidate == source)
            return false;
        std::array<std::byte, 36> header{};
        if (!window.copy(candidate, header))
            return false;
        const auto length = Bytes{header}.get(4, 4);
        if (length < 36 || length > Acpi::maximum_table || !ranges.readable(candidate, length))
            return false;
#ifdef AURORA_UEFI_PCI
        if (pci_row && Acpi::signature(header, "MCFG")) {
            if (mcfg_address)
                return false;
            mcfg_address = candidate;
        }
#endif
#if defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
        if (ivrs_row && Acpi::signature(header, "IVRS")) {
            if (ivrs_address)
                return false;
            ivrs_address = candidate;
        }
#endif
        if (!Acpi::signature(header, "APIC"))
            continue;
        if (madt_address)
            return false;
        madt_address = candidate;
    }
    if (!madt_address)
        return false;
    auto madt = window.table(madt_address, bytes(arena + 0x70000, Acpi::maximum_table), "APIC");
    if (!madt)
        return false;
#ifdef AURORA_PLATFORM_FIXTURE
    auto altered = bytes(arena + 0x70000, madt->size());
    if (fixture == Fixture::acpi_checksum)
        altered[9] ^= std::byte{1};
    if (fixture == Fixture::acpi_disabled) {
        bool injected = false;
        for (std::size_t at = 44; at < altered.size();) {
            const auto type = Bytes{altered}.get(at, 1), length = Bytes{altered}.get(at + 1, 1);
            if (length < 2 || length > altered.size() - at)
                return false;
            if (type == 0 || type == 9) {
                put(altered, at + (type == 0 ? 4 : 8), 0, 4);
                fix_checksum(altered);
                injected = true;
                break;
            }
            at += length;
        }
        if (!injected)
            return false;
    }
#endif
    const auto topology = Topology::parse(*madt, physical_bits);
    if (!topology || !window.closed() || !tables.verify(arena, handoff))
        return false;
#if defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
    if (ivrs_row && topology->apic() != 0xfee00000)
        return false; // Explicit q35 profile; no unverified APIC alias.
#endif
    unsigned enabled = 0, capable = 0;
    for (const auto &cpu : topology->processors()) {
        enabled += cpu.enabled;
        capable += cpu.online_capable;
        Serial::text("AURORA_ACPI_CPU: id=");
        Serial::number(cpu.id);
        Serial::text(" uid=");
        Serial::number(cpu.uid);
        Serial::text(" enabled=");
        Serial::number(cpu.enabled);
        Serial::text(" capable=");
        Serial::number(cpu.online_capable);
        Serial::text(" x2=");
        Serial::number(cpu.extended);
        Serial::text("\r\n");
    }
    Serial::text("AURORA_ACPI_TOPOLOGY: records=");
    Serial::number(topology->count());
    Serial::text(" enabled=");
    Serial::number(enabled);
    Serial::text(" capable=");
    Serial::number(capable);
    Serial::text(" lapic=");
    Serial::number(topology->apic());
    Serial::text("\r\n");
#ifdef AURORA_UEFI_PCI
    std::size_t mcfg_size = 0;
    if (pci_row) {
        if (!mcfg_address)
            return false;
        auto mcfg = window.table(mcfg_address, bytes(arena + 0x70000, Acpi::maximum_table), "MCFG");
        if (!mcfg || !window.closed() || !tables.verify(arena, handoff))
            return false;
        mcfg_size = mcfg->size();
    }
#endif
#if defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
    if (ivrs_row) {
        if (!ivrs_address) {
            Serial::text("AURORA_IVRS_REJECTED: reason=missing-table\r\n");
            return false;
        }
        auto ivrs = window.table(ivrs_address, bytes(arena + 0x60000, Acpi::maximum_table), "IVRS");
        if (!ivrs || !window.closed() || !tables.verify(arena, handoff))
            return false;
        Serial::text("AURORA_IVRS_RAW: bytes=");
        Serial::number(ivrs->size());
        Serial::text(" data=");
        constexpr std::string_view digits = "0123456789abcdef";
        for (auto value : *ivrs) {
            const auto byte = std::to_integer<unsigned>(value);
            Serial::put(digits[byte >> 4]);
            Serial::put(digits[byte & 15]);
        }
        Serial::text("\r\n");
#ifdef AURORA_UEFI_IOMMU_EVENT
        const auto facts = read_event_ivrs(*ivrs, physical_bits);
#else
        const auto facts = Ivrs::parse_qemu_10_0_13(*ivrs, physical_bits);
#endif
        if (!facts) {
            Serial::text("AURORA_IVRS_REJECTED: reason=table-profile\r\n");
            return false;
        }
        Serial::text("AURORA_IVRS_TABLE: units=1 records=2 requesters=");
        Serial::number(facts->requesters().size());
        Serial::text(" base=");
        Serial::number(facts->unit().base());
        Serial::text(" bytes=16384\r\n");
    }
#endif
    Serial::text("AURORA_ACPI_WINDOW_CLOSED: copies=");
    Serial::number(window.copies());
    Serial::text("\r\n");
#ifdef AURORA_UEFI_PCI
    copied_bits = physical_bits;
    copied_mcfg_size = mcfg_size;
#endif
#if defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_GRAPHICAL_CONSOLE) ||   \
    defined(AURORA_PROCESS_FIXTURE)
    copied_timer_topology.emplace(topology->timer_topology());
#endif
    return true;
}
#ifdef AURORA_UEFI_PCI
auto discover_acpi(U64 arena, const Bytes &handoff, [[maybe_unused]] memory::PhysicalPages &pool) -> bool {
    unsigned physical_bits = 0;
    std::size_t mcfg_size = 0;
#ifdef AURORA_UEFI_TABLES
    if (!prepare_table_acpi(arena, handoff, physical_bits, mcfg_size))
        return false;
#elif defined(AURORA_UEFI_IVRS) || defined(AURORA_UEFI_IOMMU_EVENT)
    if (!prepare_ivrs_acpi(arena, handoff, physical_bits, mcfg_size))
        return false;
#else
    if (!prepare_service_acpi(arena, handoff, physical_bits, mcfg_size))
        return false;
#endif
#ifdef AURORA_PLATFORM_FIXTURE
    // Early and ACPI rows end after ACPI discovery, as their ACPI-only images did.
    if (!platform::pci(platform::row(handoff.get(Handoff::fixture_offset))))
        return true;
#endif
    // ACPI parsing/Topology temporaries have ended before PCI scan construction.
    const bool accepted = discover_pci(arena, handoff, bytes(arena + 0x70000, mcfg_size), physical_bits, pool);
#if defined(AURORA_UEFI_SERVICE_BUDGET) || defined(AURORA_UEFI_CONSOLE) || defined(AURORA_UEFI_GRAPHICAL_CONSOLE) ||   \
    defined(AURORA_PROCESS_FIXTURE)
    // Preserve the public success boundary: rejected PCI leaves no timer topology.
    if (!accepted)
        copied_timer_topology.reset();
#endif
    return accepted;
}
#endif

} // namespace aurora::uefi
