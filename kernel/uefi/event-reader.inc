// Exact model-only firmware handoff. Copied firmware facts remain immutable.
// Case 4 is read-only and cannot link transition or Event producer authority.
class EventRegisterWindow final {
    const EventResources &resources_;
    const PageTables &tables_;
    const Bytes &handoff_;
    EcamWindow &ecam_;
    U64 arena_;
    volatile U64 *slot_;
    static constexpr U64 window = PageTables::window_address + 4096;
    [[gnu::noinline, nodiscard]] auto begin(U64 base, bool writable = false) -> bool {
        if (!slot_ || *slot_ || !ecam_.closed() || !tables_.verify(arena_, handoff_))
            return false;
        *slot_ = base | 1 | 8 | 16 | PageTables::nx | (writable ? 2 : 0);
        asm volatile("invlpg (%0)" ::"r"(window) : "memory");
        return true;
    }
    [[gnu::noinline, nodiscard]] auto end() -> bool {
        *slot_ = 0;
        asm volatile("invlpg (%0)" ::"r"(window) : "memory");
        return tables_.verify(arena_, handoff_);
    }

public:
    EventRegisterWindow(
        const EventResources &resources, const PageTables &tables, const Bytes &handoff, EcamWindow &ecam, U64 arena)
        : resources_(resources), tables_(tables), handoff_(handoff), ecam_(ecam), arena_(arena),
          slot_(tables.window_slot()) {
        if (slot_)
            ++slot_;
    }
    [[gnu::noinline, nodiscard]] auto ahci() -> std::optional<EventAhciFacts> {
        if (!begin(resources_.ahci_base()))
            return std::nullopt;
        const auto facts = EventAhciFacts::sample<true>(resources_.ahci_base(), [](unsigned offset) {
            return *reinterpret_cast<volatile const std::uint32_t *>(window + offset);
        });
        if (!end())
            return std::nullopt;
        return facts;
    }
    [[gnu::noinline, nodiscard]] auto edu() -> std::optional<EventEduObservation> {
        if (!begin(resources_.edu_base()))
            return std::nullopt;
        const auto facts = EventEduObservation::sample([](unsigned offset, unsigned width) -> U64 {
            if (width == 4)
                return *reinterpret_cast<volatile const std::uint32_t *>(window + offset);
            return *reinterpret_cast<volatile const U64 *>(window + offset);
        });
        if (!end())
            return std::nullopt;
        return facts;
    }
    [[nodiscard]] auto clear_fre(unsigned port, unsigned command) -> bool {
        if (port >= 6 || command != 0x4004 || !begin(resources_.ahci_base(), true))
            return false;
        auto *reg = reinterpret_cast<volatile std::uint32_t *>(window + 0x100 + port * 0x80 + 0x18);
        const bool unchanged = *reg == 0x4014;
        if (unchanged)
            *reg = command;
        const bool closed = end();
        return unchanged && closed;
    }
};
constinit bool event_handoff_attempted{};
[[gnu::noinline]] auto inspect_event(U64 arena,
                                     const Bytes &handoff,
                                     const Q35Ecam &aperture,
                                     EcamWindow &ecam,
                                     const PciInventory &inventory,
                                     unsigned bits) -> bool {
    if (event_handoff_attempted)
        return false;
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
                                                              0xfee00000,
                                                              EventResources::Purpose::firmware_handoff
    );
    if (!resources) {
        Serial::text("AURORA_EVENT_REJECTED: reason=resources-or-bme\r\n");
        return false;
    }
    const PageTables tables{handoff.get(88), static_cast<std::size_t>(handoff.get(96))};
    EventRegisterWindow registers{*resources, tables, handoff, ecam, arena};
    const auto first_sample = registers.ahci(), second_sample = registers.ahci();
    const auto edu_sample = registers.edu();
    if (!first_sample || !second_sample || !edu_sample)
        return false;
    const auto &ahci = *first_sample, &second = *second_sample;
    const auto &edu = *edu_sample;
    const bool stable = ahci == second;
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
    auto attempt = EventHandoff::prepare(*resources, current, ahci, second, edu, map, handoff.get(40), arena);
    const auto admission = attempt ? attempt->complete(
                                         event_handoff_attempted,
                                         [&] {
                                             return registers.ahci();
                                         },
                                         [&](unsigned port, unsigned command) {
                                             return registers.clear_fre(port, command);
                                         },
                                         [&] {
                                             return registers.edu();
                                         },
                                         [&](const EventPciFact &fact, unsigned command) {
                                             return ecam.reduce_event_command(fact, command);
                                         })
                                   : std::nullopt;
    if (!admission) {
        Serial::text("AURORA_EVENT_REJECTED: reason=firmware-handoff\r\n");
        return false;
    }
    for (const auto &fact : current) {
        const auto page = aperture.address(fact.segment, fact.bus, fact.device, fact.function);
        const auto after = page ? ecam.read(*page) : std::nullopt;
        auto expected = fact.header;
        put(expected, 4, fact.requester() == 8 ? 7 : fact.requester() == 0x20 ? 2 : 3, 2);
        if (!after || *after != expected)
            return false;
    }
    const auto final_caps = ecam.iommu_capability(*address);
    if (!final_caps || *final_caps != *caps || !ecam.closed() || !tables.verify(arena, handoff))
        return false;
    Serial::text("AURORA_EVENT_ADMISSION_OK: default-ivrs=1 handoff-complete=1\r\n");
    run_event_intake(arena, handoff, *admission);
}
