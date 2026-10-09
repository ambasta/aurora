// Opt-in default-model admission. All firmware data is copied; no firmware
// pointer survives ExitBootServices. This adapter performs only reads until the
// final sealed EventAdmission reaches the separately bounded producer.
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
    const auto ivrs =
        length <= ivrs_bytes.size() ? EventIvrs::parse_qemu_default(ivrs_bytes.first(length), bits) : std::nullopt;
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
                                                              0xfee00000);
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
    EventAhciFacts ahci{};
    ahci.base = resources->ahci_base();
    *slot = ahci.base | flags;
    asm volatile("invlpg (%0)" ::"r"(window) : "memory");
    const auto read = [&](unsigned offset) {
        return *reinterpret_cast<volatile const std::uint32_t *>(window + offset);
    };
    ahci.capability = read(0);
    ahci.global_control = read(4);
    ahci.implemented_ports = read(12);
    for (unsigned port = 0; port < 6; ++port) {
        ahci.ports[port].command = read(0x100 + port * 0x80 + 0x18);
        ahci.ports[port].sata_active = read(0x100 + port * 0x80 + 0x34);
        ahci.ports[port].command_issue = read(0x100 + port * 0x80 + 0x38);
    }
    // Check a second complete register pass, then revoke the mapping even when
    // unstable or active. No reset, BME clear, engine stop or W1C write fallback.
    bool stable = ahci.capability == read(0) && ahci.global_control == read(4) && ahci.implemented_ports == read(12);
    for (unsigned port = 0; port < 6; ++port)
        stable = stable && ahci.ports[port].command == read(0x100 + port * 0x80 + 0x18) &&
                 ahci.ports[port].sata_active == read(0x100 + port * 0x80 + 0x34) &&
                 ahci.ports[port].command_issue == read(0x100 + port * 0x80 + 0x38);
    *slot = 0;
    asm volatile("invlpg (%0)" ::"r"(window) : "memory");
    if (!stable || !tables.verify(arena, handoff))
        return false;
    const auto admission = EventAdmission::admit(*resources, ahci);
    if (!admission) {
        Serial::text("AURORA_EVENT_REJECTED: reason=firmware-master-active\r\n");
        return false;
    }
    for (const auto &fact : current) {
        const auto page = aperture.address(fact.segment, fact.bus, fact.device, fact.function);
        const auto after = page ? ecam.read(*page) : std::nullopt;
        if (!after || *after != fact.header)
            return false;
    }
    const auto after_caps = ecam.iommu_capability(*address);
    if (!after_caps || *after_caps != *caps || !ecam.closed() || !tables.verify(arena, handoff))
        return false;
    Serial::text("AURORA_EVENT_ADMISSION_OK: default-ivrs=1 masters-quiescent=1\r\n");
    run_event_intake(arena, handoff, *admission);
}
