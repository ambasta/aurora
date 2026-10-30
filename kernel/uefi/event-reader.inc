#ifdef AURORA_UEFI_NVME
#ifdef AURORA_PRODUCTION
using BootResources = NvmeGraphicsResources;
using BootIvrs = NvmeGraphicsIvrs;
using BootHandoff = NvmeGraphicsHandoff;
#else
using BootResources = NvmeResources;
using BootIvrs = NvmeIvrs;
using BootHandoff = NvmeHandoff;
#endif
using BootObservation = NvmeColdObservation;
constexpr unsigned boot_endpoint_requester = 0x10;
constexpr std::uint64_t boot_capture_magic = 0x314d564e41525541ULL;
#else
using BootResources = EventResources;
using BootIvrs = EventIvrs;
using BootHandoff = EventHandoff;
using BootObservation = EventEduObservation;
constexpr unsigned boot_endpoint_requester = 0x20;
constexpr std::uint64_t boot_capture_magic = 0x3154564541525541ULL;
#endif
using CaptureLayout = DmaCaptureLayout<BootResources::graphics>;
// Exact model-only firmware handoff. Copied firmware facts remain immutable.
// Case 4 is read-only and cannot link transition or Event producer authority.
class EventRegisterWindow final {
    const BootResources &resources_;
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
        const BootResources &resources, const PageTables &tables, const Bytes &handoff, EcamWindow &ecam, U64 arena)
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
    [[gnu::noinline, nodiscard]] auto edu() -> std::optional<BootObservation> {
        if (!begin(resources_.endpoint_base()))
            return std::nullopt;
        const auto facts = BootObservation::sample([](unsigned offset, unsigned width) -> U64 {
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
    const auto record = Handoff::bar_record(handoff);
    if (record != arena + Handoff::bar_offset(handoff) || inventory.count() != BootResources::maximum_functions)
        return false;
#ifndef AURORA_UEFI_NVME
    if (handoff.get(8, 4) != 4)
        return false;
#endif
    const auto storage = std::span<const std::byte>{reinterpret_cast<const std::byte *>(record), 4096};
    const Bytes saved{storage};
    if (saved.get(0) != boot_capture_magic || saved.get(8, 4) != CaptureLayout::version || saved.get(12, 4) != 4096 ||
        saved.get(16) != 0 || saved.get(24) != 0 || saved.get(32) != (boot_endpoint_requester >> 3) ||
        saved.get(40) != 0 || saved.get(48) != 0 || saved.get(56) != 48 || saved.get(64) < 48 || saved.get(64) > 738 ||
        (saved.get(64) - 2) % 46 || saved.get(72) != 64 || saved.get(88) != CaptureLayout::reservation_count ||
        saved.get(96) != CaptureLayout::functions || saved.get(104) != 1)
        return false;
    const auto ivrs_bytes =
        std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + 0x60000), BootIvrs::maximum_table};
    const auto length = Bytes{ivrs_bytes}.get(4, 4);
#if defined(AURORA_UEFI_NVME) && defined(AURORA_PRODUCTION)
    const auto ivrs =
        length <= ivrs_bytes.size() ? read_nvme_graphics_ivrs(ivrs_bytes.first(length), bits) : std::nullopt;
#elif defined(AURORA_UEFI_NVME)
    const auto ivrs = length <= ivrs_bytes.size() ? read_nvme_ivrs(ivrs_bytes.first(length), bits) : std::nullopt;
#else
    const auto ivrs = length <= ivrs_bytes.size() ? read_event_ivrs(ivrs_bytes.first(length), bits) : std::nullopt;
#endif
    if (!ivrs || saved.get(112) != ivrs->unit().device_id())
        return false;
    std::array<EventPciFact, CaptureLayout::functions> copied{}, current{};
    for (std::size_t i = 0; i < copied.size(); ++i) {
        const auto bytes =
            storage.subspan(CaptureLayout::headers + i * CaptureLayout::header_bytes, CaptureLayout::header_bytes);
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
    const auto root = PciResources::parse_edk2_root(storage.subspan(CaptureLayout::root, saved.get(64)), bits);
    if (!caps || !root)
        return false;
    std::array<EventBarFact, CaptureLayout::reservation_count + 1> bars{};
    bars[0].requester = boot_endpoint_requester;
    bars[0].index = 0;
    for (unsigned byte = 0; byte < 48; ++byte)
        bars[0].descriptor[byte] = storage[512 + byte];
    for (unsigned index = 0; index < CaptureLayout::reservation_count; ++index) {
        const auto reservation = storage.subspan(CaptureLayout::reservations + index * CaptureLayout::reservation_bytes,
                                                 CaptureLayout::reservation_bytes);
        const bool vga = BootResources::graphics && index < 2;
        const unsigned requester = vga ? 0x18 : 0xfa, bar_index = vga ? index * 2 : 5;
        const Bytes r{reservation};
        if (r.get(0) || r.get(8) || r.get(16) != (requester >> 3) || r.get(24) != (requester & 7) ||
            r.get(32) != bar_index || r.get(40) != 48)
            return false;
        bars[index + 1].requester = requester;
        bars[index + 1].index = bar_index;
        for (unsigned byte = 0; byte < 48; ++byte)
            bars[index + 1].descriptor[byte] = reservation[128 + byte];
        bool matched = false;
        for (const auto &fact : copied) {
            if (fact.requester() != requester)
                continue;
            matched = true;
            for (unsigned byte = 0; byte < 64; ++byte)
                if (fact.header[byte] != reservation[64 + byte])
                    return false;
        }
        if (!matched)
            return false;
    }
    // The target header is also repeated by the legacy-compatible BAR record.
    for (const auto &fact : copied)
        if (fact.requester() == boot_endpoint_requester)
            for (unsigned byte = 0; byte < 64; ++byte)
                if (fact.header[byte] != storage[256 + byte])
                    return false;
#if defined(AURORA_UEFI_NVME) && defined(AURORA_PRODUCTION)
    const auto framebuffer = FramebufferPayload::restore_storage_boot(arena);
    if (!framebuffer)
        return false;
    const auto *display = &*framebuffer;
#else
    const FramebufferAdmission *display = nullptr;
#endif
    const auto map = std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + Handoff::map_offset),
                                                static_cast<std::size_t>(handoff.get(32))};
    const auto resources = BootResources::admit_qemu_default(*ivrs,
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
                                                             BootResources::Purpose::firmware_handoff,
                                                             display);
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
    auto attempt = BootHandoff::prepare(*resources, current, ahci, second, edu, map, handoff.get(40), arena);
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
        put(expected, 4, fact.requester() == 8 ? 7 : fact.requester() == boot_endpoint_requester ? 2 : 3, 2);
        if (!after || *after != expected)
            return false;
    }
    const auto final_caps = ecam.iommu_capability(*address);
    if (!final_caps || *final_caps != *caps || !ecam.closed() || !tables.verify(arena, handoff))
        return false;
#ifdef AURORA_UEFI_NVME
    Serial::text("AURORA_NVME_ADMISSION_OK: default-ivrs=1 cold=1 handoff-complete=1\r\n");
#if defined(AURORA_PROCESS_FIXTURE) || defined(AURORA_PRODUCTION)
#ifdef AURORA_PROCESS_FIXTURE
    if ((handoff.get(Handoff::case_word) >= 12 && handoff.get(Handoff::case_word) <= 16) ||
        handoff.get(Handoff::case_word) == 41)
        initialize_nvme_recovery(arena, handoff, *admission);
    else if (handoff.get(Handoff::case_word) >= 17 && handoff.get(Handoff::case_word) <= 40)
        initialize_nvme_mounted(arena, handoff, *admission);
    else
#else
    if (handoff.get(Handoff::readonly_profile_word) == 3)
        initialize_nvme_mounted(arena, handoff, *admission);
    else if (handoff.get(Handoff::readonly_profile_word) == 2)
        initialize_nvme_recovery(arena, handoff, *admission);
    else
#endif
        initialize_nvme_readonly(arena, handoff, *admission);
    return true;
#else
    run_nvme(arena, handoff, *admission);
#endif
#else
    Serial::text("AURORA_EVENT_ADMISSION_OK: default-ivrs=1 handoff-complete=1\r\n");
    run_event_intake(arena, handoff, *admission);
#endif
}
