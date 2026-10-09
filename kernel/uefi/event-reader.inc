// Opt-in default-model admission. All firmware data is copied; no firmware
// pointer survives ExitBootServices. This adapter performs only reads until the
// final sealed EventAdmission reaches the separately bounded producer. Case 4
// is observation-only: no producer is linked and no admission can be minted.
#if AURORA_IOMMU_EVENT_CASE == 4
[[gnu::noipa]] auto inspect_event(U64, const Bytes &, const Q35Ecam &, EcamWindow &, const PciInventory &, unsigned)
    -> bool asm("uefi_event_observation");
#endif
[[gnu::noinline]] auto inspect_event(U64 arena,
                                     const Bytes &handoff,
                                     const Q35Ecam &aperture,
                                     EcamWindow &ecam,
                                     const PciInventory &inventory,
                                     unsigned bits) -> bool {
    if (handoff.get(8, 4) != 4 || handoff.get(120) != arena + Handoff::bar_record_offset ||
        inventory.count() != EventResources::maximum_functions)
        return false;
    const auto storage = std::span<const std::byte>{reinterpret_cast<const std::byte *>(handoff.get(120)), 4096};
    const Bytes saved{storage};
    if (saved.get(0) != 0x3154564541525541ULL || saved.get(8, 4) != 1 || saved.get(12, 4) != 4096 ||
        saved.get(16) != 0 || saved.get(24) != 0 || saved.get(32) != 4 || saved.get(40) != 0 || saved.get(48) != 0 ||
        saved.get(56) != 48 || saved.get(64) < 48 || saved.get(64) > 738 || (saved.get(64) - 2) % 46 ||
        saved.get(72) != 64 || saved.get(88) != 1 || saved.get(96) != 6 || saved.get(104) != 1)
        return false;
    const auto ivrs_bytes =
        std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + 0x60000), EventIvrs::maximum_table};
    const auto length = Bytes{ivrs_bytes}.get(4, 4);
    const auto ivrs = length <= ivrs_bytes.size() ? read_event_ivrs(ivrs_bytes.first(length), bits) : std::nullopt;
    if (!ivrs || saved.get(112) != ivrs->unit().device_id())
        return false;
    std::array<EventPciFact, 6> copied{}, current{};
    for (std::size_t i = 0; i < 6; ++i) {
        const auto bytes = storage.subspan(576 + i * 72, 72);
        const Bytes fact{bytes};
        if (fact.get(5, 3) != 0)
            return false;
        copied[i].segment = static_cast<std::uint16_t>(fact.get(0, 2));
        copied[i].bus = static_cast<std::uint8_t>(fact.get(2, 1));
        copied[i].device = static_cast<std::uint8_t>(fact.get(3, 1));
        copied[i].function = static_cast<std::uint8_t>(fact.get(4, 1));
        for (unsigned byte = 0; byte < 64; ++byte)
            copied[i].header[byte] = bytes[8 + byte];
        const auto &function = inventory.functions()[i];
        const auto address = aperture.address(function.segment, function.bus, function.device, function.function);
        const auto header = address ? ecam.read(*address) : std::nullopt;
        if (!header)
            return false;
        current[i] = {function.segment, function.bus, function.device, function.function, *header};
    }
    const auto rid = ivrs->unit().device_id();
    const auto address = aperture.address(0, rid >> 8, (rid >> 3) & 31, rid & 7);
    const auto caps = address ? ecam.iommu_capability(*address) : std::nullopt;
    const auto root = PciResources::parse_edk2_root(storage.subspan(1024, saved.get(64)), bits);
    if (!caps || !root)
        return false;
    std::array<EventBarFact, 2> bars{};
    bars[0].requester = 0x20;
    bars[0].index = 0;
    for (unsigned byte = 0; byte < 48; ++byte)
        bars[0].descriptor[byte] = storage[512 + byte];
    const auto reservation = storage.subspan(2048, 256);
    const Bytes r{reservation};
    if (r.get(0) != 0 || r.get(8) != 0 || r.get(16) != 31 || r.get(24) != 2 || r.get(32) != 5 || r.get(40) != 48)
        return false;
    bars[1].requester = 0xfa;
    bars[1].index = 5;
    for (unsigned byte = 0; byte < 48; ++byte)
        bars[1].descriptor[byte] = reservation[128 + byte];
    // Redundant copies in the legacy-compatible capture layout must agree too.
    for (const auto &fact : copied) {
        if (fact.requester() != 0x20 && fact.requester() != 0xfa)
            continue;
        const auto raw = fact.requester() == 0x20 ? storage.subspan(256, 64) : reservation.subspan(64, 64);
        for (unsigned byte = 0; byte < 64; ++byte)
            if (fact.header[byte] != raw[byte])
                return false;
    }
    const auto map = std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + Handoff::map_offset),
                                                static_cast<std::size_t>(handoff.get(32))};
    const auto resources = EventResources::admit_qemu_default(*ivrs,
                                                              copied,
                                                              current,
                                                              storage.subspan(128, 48),
                                                              *caps,
                                                              bars,
                                                              *root,
                                                              0,
                                                              map,
                                                              handoff.get(40),
                                                              arena,
                                                              0xfee00000
#if AURORA_IOMMU_EVENT_CASE == 4
                                                              ,
                                                              EventResources::Purpose::read_only_observation
#endif
    );
    if (!resources) {
        Serial::text("AURORA_EVENT_REJECTED: reason=resources-or-bme\r\n");
        return false;
    }
    const PageTables tables{handoff.get(88), static_cast<std::size_t>(handoff.get(96))};
    auto *slot = tables.window_slot();
    if (!slot || !ecam.closed() || !tables.verify(arena, handoff))
        return false;
    ++slot;
    if (*slot)
        return false;
    constexpr U64 window = PageTables::window_address + 4096;
    constexpr U64 flags = 1 | 8 | 16 | PageTables::nx;
    *slot = resources->ahci_base() | flags;
    asm volatile("invlpg (%0)" ::"r"(window) : "memory");
    const auto read = [&](unsigned offset) {
        return *reinterpret_cast<volatile const std::uint32_t *>(window + offset);
    };
    constexpr bool detailed = AURORA_IOMMU_EVENT_CASE == 4;
    const auto ahci = EventAhciFacts::sample<detailed>(resources->ahci_base(), read);
    const auto second = EventAhciFacts::sample<detailed>(resources->ahci_base(), read);
    // Every read is performed, even after a mismatch. Revoke before reporting.
    const bool stable = ahci == second;
    *slot = 0;
    asm volatile("invlpg (%0)" ::"r"(window) : "memory");
#if AURORA_IOMMU_EVENT_CASE == 4
    if (*slot || !tables.verify(arena, handoff))
        return false;
    *slot = resources->edu_base() | flags;
    asm volatile("invlpg (%0)" ::"r"(window) : "memory");
    const auto edu = EventEduObservation::sample([&](unsigned offset, unsigned width) -> U64 {
        if (width == 4)
            return *reinterpret_cast<volatile const std::uint32_t *>(window + offset);
        return *reinterpret_cast<volatile const U64 *>(window + offset);
    });
    *slot = 0;
    asm volatile("invlpg (%0)" ::"r"(window) : "memory");
    for (unsigned sample = 0; sample < edu.samples.size(); ++sample) {
        Serial::text("AURORA_EVENT_EDU: sample=");
        Serial::number(sample);
        Serial::text(" command=");
        Serial::number(edu.samples[sample].command);
        Serial::text(" status=");
        Serial::number(edu.samples[sample].status);
        Serial::text(" irq=");
        Serial::number(edu.samples[sample].irq);
        Serial::text("\r\n");
    }
    bool backing_complete = true;
    for (unsigned port = 0; port < ahci.ports.size(); ++port) {
        for (unsigned kind = 0; kind < 2; ++kind) {
            const auto address = kind == 0 ? ahci.ports[port].command_list : ahci.ports[port].received_fis;
            const auto fact =
                EventBackingObservation::capture(map, handoff.get(40), address, kind == 0 ? 1024 : 256, arena, bits);
            Serial::text("AURORA_EVENT_AHCI_BACKING: port=");
            Serial::number(port);
            Serial::text(" kind=");
            Serial::number(kind);
            Serial::text(" valid=");
            Serial::number(fact.has_value());
            if (fact) {
                Serial::text(" page=");
                Serial::number(fact->page);
                Serial::text(" type=");
                Serial::number(fact->type);
                Serial::text(" begin=");
                Serial::number(fact->begin);
                Serial::text(" pages=");
                Serial::number(fact->pages);
                Serial::text(" attributes=");
                Serial::number(fact->attributes);
            } else {
                backing_complete = false;
            }
            Serial::text("\r\n");
        }
    }
    for (const auto *snapshot : {&ahci, &second}) {
        Serial::text("AURORA_EVENT_AHCI: sample=");
        Serial::number(snapshot == &ahci ? 0 : 1);
        Serial::text(" base=");
        Serial::number(snapshot->base);
        Serial::text(" cap=");
        Serial::number(snapshot->capability);
        Serial::text(" ghc=");
        Serial::number(snapshot->global_control);
        Serial::text(" pi=");
        Serial::number(snapshot->implemented_ports);
        Serial::text("\r\n");
        for (unsigned port = 0; port < snapshot->ports.size(); ++port) {
            const auto &fact = snapshot->ports[port];
            Serial::text("AURORA_EVENT_AHCI_PORT: port=");
            Serial::number(port);
            Serial::text(" cmd=");
            Serial::number(fact.command);
            Serial::text(" ci=");
            Serial::number(fact.command_issue);
            Serial::text(" sact=");
            Serial::number(fact.sata_active);
            Serial::text(" tfd=");
            Serial::number(fact.task_file);
            Serial::text(" clb=");
            Serial::number(fact.command_list);
            Serial::text(" fb=");
            Serial::number(fact.received_fis);
            Serial::text("\r\n");
        }
    }
    Serial::text("AURORA_EVENT_OBSERVATION: stable=");
    Serial::number(stable);
    Serial::text("\r\n");
    if (!backing_complete || edu.samples[0] != edu.samples[1])
        return false;
#endif
    if (!stable || !tables.verify(arena, handoff))
        return false;
    for (const auto &fact : current) {
        const auto page = aperture.address(fact.segment, fact.bus, fact.device, fact.function);
        const auto after = page ? ecam.read(*page) : std::nullopt;
        if (!after || *after != fact.header)
            return false;
    }
    const auto after_caps = ecam.iommu_capability(*address);
    if (!after_caps || *after_caps != *caps || !ecam.closed() || !tables.verify(arena, handoff))
        return false;
#if AURORA_IOMMU_EVENT_CASE == 4
    Serial::text("AURORA_EVENT_OBSERVATION_OK: pci-unchanged=1 windows-closed=1 producer-linked=0\r\n");
    return true;
#else
    const auto admission = EventAdmission::admit(*resources, ahci);
    if (!admission) {
        Serial::text("AURORA_EVENT_REJECTED: reason=firmware-master-active\r\n");
        return false;
    }
    Serial::text("AURORA_EVENT_ADMISSION_OK: default-ivrs=1 masters-quiescent=1\r\n");
    run_event_intake(arena, handoff, *admission);
#endif
}
