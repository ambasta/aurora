// Included only in the explicitly selected AMD-Vi observation adapter.
[[gnu::noinline]] auto inspect_ivrs(U64 arena,
                                    const Bytes &handoff,
                                    const Q35Ecam &aperture,
                                    EcamWindow &ecam,
                                    const PciInventory &inventory,
                                    unsigned bits) -> bool {
    const auto table =
        std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + 0x60000), Ivrs::maximum_table};
    const auto length = Bytes{table}.get(4, 4);
    const auto facts = length <= table.size() ? Ivrs::parse_qemu_10_0_13(table.first(length), bits) : std::nullopt;
    if (!facts || !facts->matches_inventory(inventory.functions(), 0, 0, 2, 0)) {
        Serial::text("AURORA_IVRS_REJECTED: reason=requester-coverage\r\n");
        return false;
    }
    const auto location = aperture.address(0, 0, 3, 0);
    if (!location)
        return false;
    const auto header = ecam.read(*location);
    auto capability = ecam.iommu_capability(*location);
    if (!header || !capability)
        return false;
    Serial::text("AURORA_IVRS_PCI_RAW: header=");
    constexpr std::string_view hex = "0123456789abcdef";
    for (auto value : *header) {
        const auto byte = std::to_integer<unsigned>(value);
        Serial::put(hex[byte >> 4]);
        Serial::put(hex[byte & 15]);
    }
    Serial::text(" cap=");
    for (auto value : *capability) {
        const auto byte = std::to_integer<unsigned>(value);
        Serial::put(hex[byte >> 4]);
        Serial::put(hex[byte & 15]);
    }
    Serial::text("\r\n");
    const auto copied = Q35IommuSnapshot::parse(0, 0, 3, 0, *header, *capability);
    if (!copied) {
        Serial::text("AURORA_IVRS_REJECTED: reason=capability\r\n");
        return false;
    }
    const auto storage = std::span<const std::byte>{reinterpret_cast<const std::byte *>(handoff.get(120)), 4096};
    const BarRecord captured{storage};
    const Bytes record{storage};
    const auto bar = PciResources::parse_edk2_bar(storage.subspan(512, 48), bits);
    if (!bar ||
        !captured.reservations(inventory.functions(), bar->resources()[0], bits, [&](const PciFunction &function) {
            const auto address = aperture.address(function.segment, function.bus, function.device, function.function);
            return address ? ecam.read(*address) : std::nullopt;
        }))
        return false;
    std::array<std::optional<PciBarReservation>, 9> reservations{};
    const auto nvme_address = aperture.address(0, 0, 2, 0);
    if (!nvme_address)
        return false;
    const auto nvme = ecam.read(*nvme_address);
    if (!nvme)
        return false;
    const auto nvme_snapshot = PciBarSnapshot::parse(0, 0, 2, 0, *nvme);
    const auto old_nvme = PciBarSnapshot::parse(0, 0, 2, 0, storage.subspan(256, 64));
    if (!nvme_snapshot || !old_nvme || nvme_snapshot->command() != 2)
        return false;
    reservations[0] = PciBarReservation::parse_edk2(*old_nvme, *nvme_snapshot, 0, storage.subspan(512, 48), bits);
    const auto count = record.get(88);
    if (count > 8)
        return false;
    for (unsigned index = 0; index < count; ++index) {
        const auto row = storage.subspan(2048 + index * 256, 256);
        const Bytes saved{row};
        const auto address = aperture.address(saved.get(0), saved.get(8), saved.get(16), saved.get(24));
        if (!address)
            return false;
        const auto current = ecam.read(*address);
        if (!current)
            return false;
        const auto before =
            PciBarSnapshot::parse(saved.get(0), saved.get(8), saved.get(16), saved.get(24), row.subspan(64, 64));
        const auto after = PciBarSnapshot::parse(saved.get(0), saved.get(8), saved.get(16), saved.get(24), *current);
        if (!before || !after)
            return false;
        reservations[index + 1] =
            PciBarReservation::parse_edk2(*before, *after, saved.get(32), row.subspan(128, 48), bits);
    }
    const PageTables tables{handoff.get(88), static_cast<std::size_t>(handoff.get(96))};
    auto *first = tables.window_slot();
    if (!first || !ecam.closed() || !tables.verify(arena, handoff))
        return false;
    auto *slot = first + 2;
    constexpr U64 window = PageTables::window_address + 8192;
    constexpr U64 flags = 1 | 8 | 16 | PageTables::nx;
    WindowAuthority authority;
    const auto ticket = authority.acquire();
    if (!ticket)
        return false;
    auto map = std::span<const std::byte>{reinterpret_cast<const std::byte *>(arena + Handoff::map_offset),
                                          static_cast<std::size_t>(handoff.get(32))};
    auto stride = static_cast<std::size_t>(handoff.get(40));
#ifdef AURORA_IVRS_DEFAULT
    const auto grant = Q35IommuReadPolicy::authorize(*facts,
                                                     *copied,
                                                     *copied,
                                                     map,
                                                     stride,
                                                     arena,
                                                     0xfee00000,
                                                     std::span{reservations}.first(count + 1),
                                                     authority,
                                                     *ticket);
#else
    const auto grant = Q35IommuReadPolicy::authorize_qemu_10_0_13_cold(*facts,
                                                                       *copied,
                                                                       *copied,
                                                                       map,
                                                                       stride,
                                                                       arena,
                                                                       0xfee00000,
                                                                       std::span{reservations}.first(count + 1),
                                                                       authority,
                                                                       *ticket);
#endif
    if (!grant) {
        if (!authority.revoke(*ticket) || !tables.verify(arena, handoff))
            return false;
#ifdef AURORA_IVRS_DEFAULT
        Serial::text("AURORA_IVRS_REJECTED: reason=mmio-disabled\r\n");
#else
        Serial::text("AURORA_IVRS_REJECTED: reason=resource-admission\r\n");
#endif
        return false;
    }
    Serial::text("AURORA_IVRS_READ_POLICY: profile=qemu-10.0.13-cold base=4275568640 bytes=16384\r\n");
    const auto read_page = [&](U64 page_offset, U64 first_offset, U64 &value, U64 *second_value) -> bool {
        const auto page = grant->page(authority, page_offset);
        const auto physical = grant->read_address(authority, *copied, first_offset, 8);
        if (!page || !physical || *physical < *page || *physical - *page > 4088 || *slot)
            return false;
        *slot = *page | flags;
        asm volatile("invlpg (%0)" ::"r"(window) : "memory");
        value = *reinterpret_cast<volatile const U64 *>(window + first_offset - page_offset);
        if (second_value) {
            const auto second = grant->read_address(authority, *copied, 0x30, 8);
            if (!second || *second != *page + 0x30)
                return false;
            *second_value = *reinterpret_cast<volatile const U64 *>(window + 0x30);
        }
        *slot = 0;
        asm volatile("invlpg (%0)" ::"r"(window) : "memory");
        return tables.verify(arena, handoff);
    };
    U64 control = 0, efr = 0, status = 0;
    if (!read_page(0, 0x18, control, &efr) || !read_page(0x2000, 0x2020, status, nullptr))
        return false;
    const auto after_header = ecam.read(*location);
    const auto after_cap = ecam.iommu_capability(*location);
    const auto after =
        after_header && after_cap ? Q35IommuSnapshot::parse(0, 0, 3, 0, *after_header, *after_cap) : std::nullopt;
    const auto after_nvme = ecam.read(*nvme_address);
    if (!after || !after_nvme || *after_nvme != *nvme || !grant->finish(authority, *after, control, efr, status))
        return false;
    Serial::text("AURORA_IVRS_REGISTERS: control=");
    Serial::number(control);
    Serial::text(" efr=");
    Serial::number(efr);
    Serial::text(" status=");
    Serial::number(status);
    Serial::text("\r\n");
#ifdef AURORA_IVRS_FIXTURE
    if (pci_fixture == Fixture::ivrs_write) {
        const auto page = grant->page(authority, 0);
        if (!page || *slot)
            return false;
        *slot = *page | flags;
        asm volatile("invlpg (%0)" ::"r"(window) : "memory");
        Serial::text("AURORA_IVRS_WRITE_PROBE\r\n");
        asm volatile(".global uefi_ivrs_write_probe\nuefi_ivrs_write_probe: movq $0,(%%rax)" ::"a"(window + 0x18)
                     : "memory");
        return false;
    }
#endif
    if (!authority.revoke(*ticket) || grant->page(authority, 0) || grant->read_address(authority, *after, 0x18, 8) ||
        *slot || !ecam.closed() || !tables.verify(arena, handoff))
        return false;
    Serial::text("AURORA_IVRS_WINDOW_CLOSED: reads=3 pages=2 revoked=1\r\n");
#ifdef AURORA_IVRS_FIXTURE
    if (pci_fixture == Fixture::ivrs_revoked) {
        Serial::text("AURORA_IVRS_REVOKED_PROBE\r\n");
        U64 ignored;
        asm volatile(".global uefi_ivrs_revoked_probe\nuefi_ivrs_revoked_probe: movq (%%rax),%%rax"
                     : "=a"(ignored)
                     : "0"(window + 0x18)
                     : "memory");
        static_cast<void>(ignored);
        return false;
    }
#endif
    Serial::text("AURORA_IVRS_READ_ONLY_OK\r\n");
    return true;
}
