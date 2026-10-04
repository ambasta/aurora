// Included inside the PCI adapter namespace. Diagnostic reads are bounded and
// separate from the inactive-controller receipt; neither enables a device.
#ifdef AURORA_UEFI_IVRS
[[gnu::noinline]]
#endif
auto inspect_bar(U64 arena,const Bytes& handoff,const Q35Ecam& aperture,EcamWindow& ecam,const PciInventory& inventory,unsigned bits) -> bool {
    if (handoff.get(8,4)!=4 || handoff.get(120)!=arena+Handoff::bar_record_offset) return false;
    const auto storage=std::span<const std::byte>{reinterpret_cast<const std::byte*>(handoff.get(120)),4096};
    const Bytes record{storage};
    const BarRecord captured{storage};
    if (!captured.valid()) return false;
    const auto copied=PciBarSnapshot::parse(0,0,2,0,storage.subspan(256,64));
    const auto address=aperture.address(0,0,2,0);
    const auto initial_reads=ecam.reads();
    if (!copied || !address) return false;
    const auto current_bytes=ecam.read(*address); if (!current_bytes) return false;
    const auto current=PciBarSnapshot::parse(0,0,2,0,*current_bytes); if (!current) return false;
#ifdef AURORA_UEFI_BAR_EDK2
    const auto bar=PciResources::parse_edk2_bar(storage.subspan(512,48),bits);
    const auto resources=PciResources::parse_edk2_root(storage.subspan(1024,record.get(64)),bits);
#else
    const auto bar=PciResources::parse(storage.subspan(512,48),bits);
    const auto resources=PciResources::parse(storage.subspan(1024,record.get(64)),bits);
#endif
    if (!bar || !resources) { Serial::text("AURORA_BAR_REJECTED: reason=resource-profile\r\n"); return false; }
    const auto reservations=captured.reservations(inventory.functions(),bar->resources()[0],bits,[&](const PciFunction& function) {
        const auto location=aperture.address(function.segment,function.bus,function.device,function.function);
        return location ? ecam.read(*location) : std::nullopt;
    });
    if (!reservations) { Serial::text("AURORA_BAR_REJECTED: reason=reservation-conflict\r\n"); return false; }
    Serial::text("AURORA_BAR_RESERVATIONS: count="); Serial::number(*reservations); Serial::text(" matched=1\r\n");
    const PageTables tables{handoff.get(88),static_cast<std::size_t>(handoff.get(96))};
    auto slot=tables.window_slot();
    if (!slot || !ecam.closed() || !tables.verify(arena,handoff)) return false;
    ++slot; // Distinct adjacent PTE: no ECAM/BAR mapping substitution.
    constexpr U64 window=PageTables::window_address+4096;
    constexpr U64 flags=1|8|16|PageTables::nx;
    if (*slot!=0) return false;
    WindowAuthority authority; const auto ticket=authority.acquire(); if (!ticket) return false;
    const auto map=std::span<const std::byte>{reinterpret_cast<const std::byte*>(arena+Handoff::map_offset),static_cast<std::size_t>(handoff.get(32))};
    const auto probe=NvmeBarProbe::authorize(*copied,*current,*bar,*resources,0,map,handoff.get(40),arena,0xfee00000,authority,*ticket);
    if (!probe) { static_cast<void>(authority.revoke(*ticket)); Serial::text("AURORA_BAR_REJECTED: reason=resource-admission\r\n"); return false; }
    const auto page=probe->page(authority); if (!page) return false;
#ifdef AURORA_BAR_ALIAS
    slot[1]=*page|3|8|16|PageTables::nx;
    const bool rejected_alias=!tables.verify(arena,handoff);
    slot[1]=0;
    asm volatile("invlpg (%0)"::"r"(window+4096):"memory");
    if (rejected_alias && authority.revoke(*ticket) && tables.verify(arena,handoff)) {
        Serial::text("AURORA_BAR_REJECTED: reason=mapping-alias\r\n"); return false;
    }
    return false;
#endif
    *slot=*page|flags;
    asm volatile("invlpg (%0)"::"r"(window):"memory");
    unsigned reads=0;
    const auto read=[&](U64 offset,unsigned width) -> std::optional<U64> {
        const auto physical=probe->read_address(authority,*current,offset,width);
        if (!physical || *physical!=*page+offset || (*slot&~0x60ULL)!=(*page|flags)) return std::nullopt;
        ++reads;
        if (width==8) return *reinterpret_cast<volatile const U64*>(window+offset);
        if (width==4) return *reinterpret_cast<volatile const std::uint32_t*>(window+offset);
        return std::nullopt;
    };
    const auto cap=read(0,8),version=read(8,4),cc=read(0x14,4),csts=read(0x1c,4),aqa=read(0x24,4),asq=read(0x28,8),acq=read(0x30,8);
    const auto after_bytes=ecam.read(*address);
    const auto after=after_bytes ? PciBarSnapshot::parse(0,0,2,0,*after_bytes) : std::nullopt;
    const bool complete=cap && version && cc && csts && aqa && asq && acq && after && current->same(*after);
    const auto grant=complete ? probe->finish(authority,*after,*cap,static_cast<std::uint32_t>(*version),static_cast<std::uint32_t>(*cc),
        static_cast<std::uint32_t>(*csts),static_cast<std::uint32_t>(*aqa),*asq,*acq) : std::nullopt;
    if (complete) {
        Serial::text("AURORA_BAR_STATE: segment=0 bus=0 device=2 function=0 command="); Serial::number(after->command());
        Serial::text(" base="); Serial::number(*page); Serial::text(" length="); Serial::number(probe->length());
        Serial::text(" cap="); Serial::number(*cap); Serial::text(" version="); Serial::number(*version);
        Serial::text(" cc="); Serial::number(*cc); Serial::text(" csts="); Serial::number(*csts);
        Serial::text(" aqa="); Serial::number(*aqa); Serial::text(" asq="); Serial::number(*asq); Serial::text(" acq="); Serial::number(*acq); Serial::text("\r\n");
    }
#ifdef AURORA_BAR_WRITE
    if (grant) {
        Serial::text("AURORA_BAR_WRITE_PROBE\r\n");
        asm volatile(".global uefi_bar_write_probe\nuefi_bar_write_probe: movl $0,(%%rax)"::"a"(window+8):"memory");
    }
#endif
    *slot=0;
    asm volatile("invlpg (%0)"::"r"(window):"memory");
    if (!authority.revoke(*ticket) || *slot || probe->page(authority) || !ecam.closed() || !tables.verify(arena,handoff)) return false;
    if (grant && grant->read_address(authority,*after,0,8)) return false;
    Serial::text("AURORA_BAR_WINDOW_CLOSED: reads="); Serial::number(reads); Serial::text(" config="); Serial::number(ecam.reads()-initial_reads);
    Serial::text(" revoked=1\r\n");
    if (!grant) { Serial::text("AURORA_BAR_REJECTED: reason=inactive-controller-required\r\n"); return false; }
#ifdef AURORA_BAR_REVOKED
    Serial::text("AURORA_BAR_REVOKED_PROBE\r\n");
    U64 ignored; asm volatile(".global uefi_bar_revoked_probe\nuefi_bar_revoked_probe: movl (%%rax),%%eax":"=a"(ignored):"0"(window+8):"memory");
    static_cast<void>(ignored);
    return false;
#endif
    Serial::text("AURORA_BAR_READ_ONLY_OK\r\n");
    return true;
}
