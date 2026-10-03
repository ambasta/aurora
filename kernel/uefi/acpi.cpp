#include "acpi.hpp"
#include "acpi-policy.hpp"
#include "tables.hpp"
#ifdef AURORA_UEFI_PCI
#include "pci.hpp"
#endif
#include "../console.hpp"
namespace aurora::uefi {
#ifdef AURORA_UEFI_SERVICE_BUDGET
namespace { constinit std::optional<Topology> copied_topology; }
auto discovered_topology() -> const std::optional<Topology>& { return copied_topology; }
#endif
namespace {
using hardware::Serial;
using U64=std::uint64_t;
auto bytes(U64 base,std::size_t size) -> std::span<std::byte> { return {reinterpret_cast<std::byte*>(base),size}; }
class ReadWindow final {
    const FirmwareRanges& ranges_;
    volatile U64* slot_;
    WindowAuthority authority_;
    unsigned bits_;
    unsigned copies_{};
    unsigned revocations_{};
    [[nodiscard]] auto begin(U64 page) -> std::optional<WindowTicket> {
        if (!slot_ || *slot_!=0 || page%4096 || bits_<32 || bits_>52 || page>(1ULL<<bits_)-4096 || !ranges_.readable(page,4096)) return std::nullopt;
        auto ticket=authority_.acquire();
        if (!ticket) return std::nullopt;
        *slot_=page|1|PageTables::nx;
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        return ticket;
    }
    [[nodiscard]] auto end(WindowTicket ticket) -> bool {
        if (!authority_.accepts(ticket)) return false;
        *slot_=0;
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        ++revocations_;
        return *slot_==0 && authority_.revoke(ticket);
    }
public:
    ReadWindow(const FirmwareRanges& ranges,volatile U64* slot,unsigned bits) : ranges_(ranges),slot_(slot),bits_(bits) {}
    [[nodiscard]] auto copy(U64 physical,std::span<std::byte> destination) -> bool {
        if (destination.empty() || destination.size()>Acpi::maximum_table || !ranges_.readable(physical,destination.size())) return false;
        std::size_t done=0;
        while (done<destination.size()) {
            const auto chunk=ReadPlan{physical,destination.size()}.next(done);
            if (!chunk) return false;
            auto ticket=begin(chunk->page); if (!ticket) return false;
            const auto offset=chunk->offset,count=chunk->count;
            for (std::size_t i=0;i<count;++i) destination[done+i]=*reinterpret_cast<volatile const std::byte*>(PageTables::window_address+offset+i);
            if (!end(*ticket)) return false;
            done+=count; ++copies_;
        }
        return true;
    }
    [[nodiscard]] auto table(U64 physical,std::span<std::byte> storage,std::string_view signature) -> std::optional<std::span<const std::byte>> {
        std::array<std::byte,36> header{};
        if (!copy(physical,header) || !Acpi::signature(header,signature)) return std::nullopt;
        const auto size=Bytes{header}.get(4,4);
        if (size<36 || size>storage.size() || size>Acpi::maximum_table) return std::nullopt;
        auto snapshot=storage.first(size);
        if (!copy(physical,snapshot)) return std::nullopt;
#ifdef AURORA_ACPI_CHANGED_HEADER
        snapshot[10]^=std::byte{1};
        snapshot[9]=std::byte{0};
        unsigned changed_sum=0; for (auto value:snapshot) changed_sum+=std::to_integer<unsigned>(value);
        snapshot[9]=std::byte(0U-changed_sum); // Still checksum-valid: only header consistency can reject this.
#endif
        if (!Acpi::same_header(snapshot,header)) return std::nullopt;
        if (!Acpi::table(snapshot,signature)) return std::nullopt;
        return snapshot;
    }
    [[nodiscard]] auto probe_write(U64 physical) -> bool {
        auto ticket=begin(physical&~U64{4095}); if (!ticket) return false;
        Serial::text("AURORA_ACPI_WRITE_PROBE\r\n");
        *reinterpret_cast<volatile std::uint8_t*>(PageTables::window_address)=0;
        return end(*ticket);
    }
    [[nodiscard]] auto closed() const -> bool { return slot_ && *slot_==0 && copies_==revocations_; }
    [[nodiscard]] auto copies() const -> unsigned { return copies_; }
};
[[maybe_unused]] auto fix_checksum(std::span<std::byte> table) -> void {
    table[9]=std::byte{0}; unsigned sum=0;
    for (auto value:table) sum+=std::to_integer<unsigned>(value);
    table[9]=std::byte(0U-sum);
}
}
auto discover_acpi(U64 arena,const Bytes& handoff) -> bool {
#ifdef AURORA_UEFI_SERVICE_BUDGET
    copied_topology.reset();
#endif
    std::uint32_t a,b,c,d;
    asm volatile("cpuid" : "=a"(a),"=b"(b),"=c"(c),"=d"(d) : "a"(1),"c"(0));
    if (!(d&(1U<<16))) return false;
    asm volatile("cpuid" : "=a"(a),"=b"(b),"=c"(c),"=d"(d) : "a"(0x80000000U),"c"(0));
    if (a<0x80000008U) return false;
    asm volatile("cpuid" : "=a"(a),"=b"(b),"=c"(c),"=d"(d) : "a"(0x80000008U),"c"(0));
    const auto physical_bits=a&255;
    std::uint32_t low,high;
    asm volatile("rdmsr" : "=a"(low),"=d"(high) : "c"(0x277));
    if ((low&255)!=6 || physical_bits<32 || physical_bits>52) return false; // PAT0=WB, one cache policy for eligible RAM.
    const FirmwareRanges ranges{bytes(arena+Handoff::map_offset,handoff.get(32)),handoff.get(40),arena,physical_bits};
    const PageTables tables{handoff.get(88),static_cast<std::size_t>(handoff.get(96))};
    auto* slot=tables.window_slot();
    if (!slot || *slot!=0) return false;
    ReadWindow window{ranges,slot,physical_bits};
    auto source=handoff.get(112);
#ifdef AURORA_ACPI_BAD_SOURCE
    source=0xfec00000;
#endif
#ifdef AURORA_ACPI_WRITE
    return window.probe_write(source);
#endif
    std::array<std::byte,36> rsdp_header{};
    if (!window.copy(source,rsdp_header)) return false;
    const auto rsdp_size=Bytes{rsdp_header}.get(20,4);
    if (rsdp_size<36 || rsdp_size>4096) return false;
    auto rsdp=bytes(arena+0x80000,rsdp_size);
    if (!window.copy(source,rsdp)) return false;
    if (!Acpi::same_header(rsdp,rsdp_header)) return false;
#ifdef AURORA_ACPI_REVOKED
    if (!window.closed()) return false;
    Serial::text("AURORA_ACPI_REVOKED_PROBE\r\n");
    static_cast<void>(*reinterpret_cast<volatile const std::byte*>(PageTables::window_address));
    return false;
#endif
    const auto xsdt_address=Acpi::rsdp(rsdp);
    if (!xsdt_address) return false;
    auto xsdt=window.table(*xsdt_address,bytes(arena+0x60000,Acpi::maximum_table),"XSDT");
    if (!xsdt || !Acpi::xsdt(*xsdt,*xsdt_address)) return false;
    U64 madt_address=0;
#ifdef AURORA_UEFI_PCI
    U64 mcfg_address=0;
#endif
    for (std::size_t at=36;at<xsdt->size();at+=8) {
        const auto candidate=Bytes{*xsdt}.get(at);
        if (candidate==source) return false;
        std::array<std::byte,36> header{};
        if (!window.copy(candidate,header)) return false;
        const auto length=Bytes{header}.get(4,4);
        if (length<36 || length>Acpi::maximum_table || !ranges.readable(candidate,length)) return false;
        #ifdef AURORA_UEFI_PCI
        if (Acpi::signature(header,"MCFG")) {
            if (mcfg_address) return false;
            mcfg_address=candidate;
        }
#endif
        if (!Acpi::signature(header,"APIC")) continue;
        if (madt_address) return false;
        madt_address=candidate;
    }
    if (!madt_address) return false;
    auto madt=window.table(madt_address,bytes(arena+0x70000,Acpi::maximum_table),"APIC");
    if (!madt) return false;
#if defined(AURORA_ACPI_CHECKSUM) || defined(AURORA_ACPI_BAD_ENTRY) || defined(AURORA_ACPI_DUPLICATE) || defined(AURORA_ACPI_DISABLED)
    auto altered=bytes(arena+0x70000,madt->size());
#ifdef AURORA_ACPI_CHECKSUM
    altered[9]^=std::byte{1};
#endif
#ifdef AURORA_ACPI_BAD_ENTRY
    altered[45]=std::byte{0}; fix_checksum(altered);
#endif
#if defined(AURORA_ACPI_DUPLICATE) || defined(AURORA_ACPI_DISABLED)
    bool injected=false;
    for (std::size_t at=44;at<altered.size();) {
        const auto type=Bytes{altered}.get(at,1),length=Bytes{altered}.get(at+1,1);
        if (length<2 || length>altered.size()-at) return false;
        if (type==0 || type==9) {
#ifdef AURORA_ACPI_DUPLICATE
            if (altered.size()+length>Acpi::maximum_table) return false;
            auto expanded=bytes(arena+0x70000,altered.size()+length);
            for (std::size_t i=0;i<length;++i) expanded[altered.size()+i]=altered[at+i];
            put(expanded,4,expanded.size(),4); altered=expanded; madt=std::span<const std::byte>{expanded};
#else
            put(altered,at+(type==0 ? 4 : 8),0,4);
#endif
            fix_checksum(altered); injected=true; break;
        }
        at+=length;
    }
    if (!injected) return false;
#endif
#endif
    const auto topology=Topology::parse(*madt,physical_bits);
    if (!topology || !window.closed() || !tables.verify(arena,handoff)) return false;
    unsigned enabled=0,capable=0;
    for (const auto& cpu:topology->processors()) {
        enabled+=cpu.enabled; capable+=cpu.online_capable;
        Serial::text("AURORA_ACPI_CPU: id="); Serial::number(cpu.id); Serial::text(" uid="); Serial::number(cpu.uid);
        Serial::text(" enabled="); Serial::number(cpu.enabled); Serial::text(" capable="); Serial::number(cpu.online_capable);
        Serial::text(" x2="); Serial::number(cpu.extended); Serial::text("\r\n");
    }
    Serial::text("AURORA_ACPI_TOPOLOGY: records="); Serial::number(topology->count()); Serial::text(" enabled="); Serial::number(enabled);
    Serial::text(" capable="); Serial::number(capable); Serial::text(" lapic="); Serial::number(topology->apic()); Serial::text("\r\n");
    #ifdef AURORA_UEFI_PCI
    if (!mcfg_address) return false;
    auto mcfg=window.table(mcfg_address,bytes(arena+0x70000,Acpi::maximum_table),"MCFG");
    if (!mcfg || !window.closed() || !tables.verify(arena,handoff)) return false;
#endif
    Serial::text("AURORA_ACPI_WINDOW_CLOSED: copies="); Serial::number(window.copies()); Serial::text("\r\n");
#ifdef AURORA_UEFI_PCI
    if (!discover_pci(arena,handoff,*mcfg,physical_bits)) return false;
#ifdef AURORA_UEFI_SERVICE_BUDGET
    copied_topology.emplace(*topology);
#endif
    return true;
#else
    return true;
#endif
}
}
