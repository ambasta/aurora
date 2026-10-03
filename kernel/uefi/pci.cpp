#include "pci.hpp"
#ifdef AURORA_UEFI_PCI
#include "pci-policy.hpp"
#include "acpi-policy.hpp"
#include "tables.hpp"
#include "../console.hpp"
namespace aurora::uefi {
namespace {
using U64=std::uint64_t;
using hardware::Serial;
class EcamWindow final {
    const Q35Ecam aperture_;
    volatile U64* slot_;
    WindowAuthority authority_;
    unsigned reads_{};
    unsigned revoked_{};
    [[nodiscard]] auto begin(U64 page) -> std::optional<WindowTicket> {
        if (!slot_ || *slot_!=0 || !aperture_.admits_page(page)) return std::nullopt;
        auto ticket=authority_.acquire(); if (!ticket) return std::nullopt;
        // PAT3 (PWT|PCD) was verified UC; supervisor, read-only, NX, nonglobal.
        *slot_=page|1|8|16|PageTables::nx;
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        ++reads_;
        return ticket;
    }
    [[nodiscard]] auto end(WindowTicket ticket) -> bool {
        if (!authority_.accepts(ticket)) return false;
        *slot_=0;
        asm volatile("invlpg (%0)" : : "r"(PageTables::window_address) : "memory");
        ++revoked_;
        return *slot_==0 && authority_.revoke(ticket);
    }
    [[nodiscard]] static auto snapshot() -> std::array<std::byte,64> {
        std::array<std::byte,64> result{};
        // Naturally aligned configuration DWORD loads, restricted to standard header.
        for (unsigned offset=0;offset<64;offset+=4) {
            const auto value=*reinterpret_cast<volatile const std::uint32_t*>(PageTables::window_address+offset);
            put(result,offset,value,4);
            if (offset==0 && (value&65535)==65535) break;
        }
        return result;
    }
public:
    EcamWindow(const Q35Ecam& aperture,volatile U64* slot) : aperture_(aperture),slot_(slot) {}
    [[nodiscard]] auto read(U64 page) -> std::optional<std::array<std::byte,64>> {
        auto ticket=begin(page); if (!ticket) return std::nullopt;
        const auto first=snapshot();
        const auto second=snapshot();
        if (!end(*ticket) || first!=second) return std::nullopt;
        auto result=first;
#ifdef AURORA_PCI_CYCLE
        if ((Bytes{result}.get(14,1)&127)==1) {
            put(result,25,(page-Q35Ecam::base)>>20,1);
            // Keep the configured subordinate bound: secondary now points at its own parent.
        }
#endif
        return result;
    }
    [[nodiscard]] auto probe_write() -> bool {
        auto ticket=begin(Q35Ecam::base); if (!ticket) return false;
        Serial::text("AURORA_PCI_WRITE_PROBE\r\n");
        // Deliberate negative gate: the CPU must reject before a PCI transaction.
        *reinterpret_cast<volatile std::uint32_t*>(PageTables::window_address)=0;
        return end(*ticket);
    }
    [[nodiscard]] auto closed() const -> bool { return slot_ && *slot_==0 && reads_==revoked_; }
    [[nodiscard]] auto reads() const -> unsigned { return reads_; }
};
[[maybe_unused]] auto checksum(std::span<std::byte> table) -> void {
    table[9]=std::byte{0}; unsigned sum=0;
    for (auto value:table) sum+=std::to_integer<unsigned>(value);
    table[9]=std::byte(0U-sum);
}
}
auto discover_pci(U64 arena,const Bytes& handoff,std::span<const std::byte> source,unsigned bits) -> bool {
    // The source is an owned, consistent ACPI snapshot. No firmware pointer escapes.
    std::array<std::byte,108> storage{};
    if (source.size()<60 || source.size()>storage.size()) return false;
    for (std::size_t i=0;i<source.size();++i) storage[i]=source[i];
    auto table=std::span<std::byte>{storage}.first(source.size());
#ifdef AURORA_PCI_CHECKSUM
    table[9]^=std::byte{1};
#endif
#ifdef AURORA_PCI_RESERVED
    table[36]=std::byte{1}; checksum(table);
#endif
#ifdef AURORA_PCI_OVERLAP
    if (table.size()!=60) return false;
    table=std::span<std::byte>{storage}.first(76);
    for (unsigned i=0;i<16;++i) table[60+i]=table[44+i];
    put(table,4,76,4); checksum(table);
#endif
#ifdef AURORA_PCI_RANGE
    if (table.size()!=60) return false;
    put(table,44,0); checksum(table);
#endif
    const auto mcfg=Mcfg::parse(table,bits);
    if (!mcfg) return false;
    const auto map=std::span<const std::byte>{reinterpret_cast<const std::byte*>(arena+Handoff::map_offset),static_cast<std::size_t>(handoff.get(32))};
    const auto aperture=Q35Ecam::authorize(*mcfg,map,handoff.get(40),arena);
    if (!aperture) return false;
    const PageTables tables{handoff.get(88),static_cast<std::size_t>(handoff.get(96))};
    if (!tables.verify(arena,handoff)) return false;
    U64 root; asm volatile("mov %%cr3, %0" : "=r"(root));
    if (root!=handoff.get(88)) return false;
    std::uint32_t low,high; asm volatile("rdmsr" : "=a"(low),"=d"(high) : "c"(0x277));
    if ((low>>24)!=0) return false;
    EcamWindow window{*aperture,tables.window_slot()};
    Serial::text("AURORA_PCI_APERTURE: base="); Serial::number(Q35Ecam::base);
    Serial::text(" bytes="); Serial::number(Q35Ecam::bytes); Serial::text(" segment=0 first=0 last=255\r\n");
#ifdef AURORA_PCI_WRITE
    return window.probe_write();
#endif
#ifdef AURORA_PCI_REVOKED
    if (!window.read(Q35Ecam::base) || !window.closed()) return false;
    Serial::text("AURORA_PCI_REVOKED_PROBE\r\n");
    static_cast<void>(*reinterpret_cast<volatile const std::uint32_t*>(PageTables::window_address));
    return false;
#endif
    const auto inventory=PciInventory::scan(*aperture,[&](U64 page) { return window.read(page); });
    if (!inventory || !window.closed() || !tables.verify(arena,handoff)) return false;
    for (const auto& function:inventory->functions()) {
        Serial::text("AURORA_PCI_FUNCTION: segment="); Serial::number(function.segment);
        Serial::text(" bus="); Serial::number(function.bus); Serial::text(" device="); Serial::number(function.device);
        Serial::text(" function="); Serial::number(function.function); Serial::text(" vendor="); Serial::number(function.vendor);
        Serial::text(" product="); Serial::number(function.device_id); Serial::text(" class="); Serial::number(function.class_code);
        Serial::text(" subclass="); Serial::number(function.subclass); Serial::text(" interface="); Serial::number(function.programming_interface);
        Serial::text(" header="); Serial::number(function.header_type); Serial::text(" command="); Serial::number(function.command);
        Serial::text(" secondary="); Serial::number(function.secondary_bus); Serial::text(" subordinate="); Serial::number(function.subordinate_bus);
        Serial::text("\r\n");
    }
    Serial::text("AURORA_PCI_INVENTORY: functions="); Serial::number(inventory->count());
    Serial::text(" buses="); Serial::number(inventory->bus_count()); Serial::text("\r\n");
    Serial::text("AURORA_PCI_WINDOW_CLOSED: reads="); Serial::number(window.reads()); Serial::text("\r\n");
    return true;
}
}
#endif
