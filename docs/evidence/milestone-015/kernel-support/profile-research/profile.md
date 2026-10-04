# M015 read-only AMD-Vi / IVRS research

2026-10-03. Research only; no repository changes, builds, firmware changes, PCI configuration writes, or MMIO writes.

## Proposed acceptance profile

Accept a deliberately narrow QEMU 10.0.13 Q35 profile: one physical IOMMU represented by exactly one IVHD 0x10 and one IVHD 0x11, both naming segment 0 / requester 0x0018 / capability 0x40 / MMIO 0xfed80000, with identical, duplicate-free SELECT requester sets and zero per-device settings. Reject all other device-entry forms, IVMD blocks, extra units, unknown blocks, conflicting aliases or scopes, unsupported bits, malformed lengths, bad checksums, and incomplete paired variants. Discovery confers no DMA or interrupt-remapping authority.

The controlled source profile uses `pt=off,intremap=off,device-iotlb=off,xtsup=off`. These options are evidence of configuration, not evidence of isolation. In the exact AMD implementation, disabled CTRL.IommuEn returns identity read/write DMA translations. `pt_supported` and `dt_supported` are not consulted by amd_iommu.c.

## Exact observed IVRS

Independently decoded from `/tmp/aurora-m015-profile/serial.log`; detailed machine-readable result: `actual-ivrs-profile.json` in this directory. The complete table has 168 bytes, revision 1, valid byte checksum, IVinfo at offset 36 = 0x00002801, and eight zero reserved bytes at offset 40. This revision is what the producer actually emits, even with its type-0x11 block.

All integer fields below are little endian.

| Field | IVHD 0x10 | IVHD 0x11 |
|---|---|---|
| Absolute table offset | 48 | 100 |
| Flags / length | 0xd1 / 52 | 0x11 / 68 |
| Header bytes / entry offset | 24 / +24 | 40 / +40 |
| DeviceID / capability offset | 0x0018 / 0x0040 | same |
| Base / segment / info | 0xfed80000 / 0 / 0 | same |
| +20 u32 | feature 0x00000044 | attributes 0 |
| +24 u64 | device entries begin | EFR 0x00000000000029d3 |
| +32 u64 | device entries continue | EFR2 0 |

Both entry blobs are exactly 28 bytes: seven four-byte SELECT records (type 0x02, DeviceID u16 at +1, settings u8 at +3). IDs are 0x0000, 0x0008, 0x0010, 0x0018, 0x00f8, 0x00fa, 0x00fb; settings are all zero. The target NVMe requester is 0x0010 (00:02.0).

Variant equivalence must compare common identity and requester semantics, and validate each type's own constants. Do not count the pair as two IOMMUs. Do not require equality of feature encodings: the QEMU producer computes IVHD10 HATS/GATS using `(48UL << 30) | (48UL << 28)` and writes only four bytes, truncating those contributions; the actual feature field is 0x44, while the EFR carries HATS=2 and GATS=2. Type-10 PrefSup/PPRSup flags occupy bits 6/7, while type-11 reports them through EFR bits 0/1. A generic field-by-field comparison would reject the real producer.

Use bounded readers, checked additions and subtraction-based length checks. Require each block length to cover its complete fixed header, fit the enclosing table, advance positively, and consume the table exactly. Pair matching by sets can tolerate entry ordering, but duplicate entries within a variant must be rejected before comparing sets. Different variants for the same identity are expected; duplicate same-type blocks are not accepted. Exact constants reject unsupported semantics, not necessarily architecturally reserved bits. Do not label every non-profile bit as reserved.

## Device entries outside the accepted profile

The QEMU producer and Linux/ACPICA consumers corroborate these shapes:

- 0x00 padding, 0x01 all devices, 0x02 SELECT, 0x03 range start, 0x04 inclusive range end: four bytes.
- 0x40 padding; 0x42 alias select; 0x43 alias range start; 0x46 extended select; 0x47 extended range start; 0x48 special: eight bytes.
- Alias records encode original DeviceID at +1, settings at +3, reserved +4, used/requester DeviceID at +5, reserved +7. An alias range maps every source ID in its inclusive start/end range to the one requester ID, not to a linearly increasing target range.
- QEMU emits 0x43/0x04 for conventional downstream buses. For a PCIe-to-PCI bridge, the requester alias is secondary-bus 00.0; otherwise it is the bridge's own requester ID. A device's BDF therefore need not be its DMA requester ID.
- Extended records add a u32 at +4. Special records have handle +4, used ID +5, variety +7; varieties 1/2 identify IOAPIC/HPET. With interrupt remapping enabled, QEMU adds a special IOAPIC entry using requester 0x00a0. It is absent in the selected intremap=off profile.
- 0xf0 is variable length: fixed 22 bytes plus UID length at +21, unlike the simple high-two-bits length rule. Reject it for M015. Do not blindly advance every unknown type by `4 << (type >> 6)`.

No general alias or range support is proposed. Reject before acquiring any MMIO read window. If later implemented, require matched, non-nested range delimiters; ordered endpoints; bounded expansion; supported settings; resolved alias target; and conflict/overlap/cycle checks. Treat any alias relationship as a restriction on independent device isolation.

## IVMD and reserved-memory semantics

IVMD types 0x20/0x21/0x22 are 32-byte blocks: all devices / one DeviceID / an inclusive DeviceID range. DeviceID is +4; auxiliary end ID is +6; start physical address is u64 +16; byte length is u64 +24. Flag bits are unity-map=0, read=1, write=2, exclusion=3. These are mapping requirements or restrictions, not proof that RAM is safe to allocate or DMA is isolated. Ignoring a restriction or rounding a prohibited range inward is unsafe.

Important version issue: Linux v6.18 uses PCI segment at +8 and six reserved bytes at +10. ACPICA's same-version actbl2.h still models all eight bytes +8..15 as reserved. The indexed AMD 3.10 table adds the segment field. Do not implement a supposedly current general IVMD parser from the stale ACPICA shape alone. M015 rejects every IVMD, including apparently harmless or non-target ones, so no unresolved reserved-region obligation is discarded. General acceptance is deferred until the current normative body is available and segment/range/permission semantics are verified.

## PCI and MMIO read admission

Exact device source identity: AMD vendor 0x1022, device 0x1419, class/subclass 0x0806, programming interface 0. Actual BDF is 0000:00:03.0. Its command value was 7; the separate NVMe command was 2. Do not confuse an IOMMU's PCI command snapshot with its MMIO translation-enable state.

The AMD capability is 24 bytes at 0x40. Source-derived six u32 values are:

`1f03000f fed80000 00000000 ff000000 00182840 00000000`

The header has capability ID 0x0f, next=0, type=3 (bits 18:16), revision=0, and bits 24..28 set. Base comes from low +4 and high +8; +12 is the range register; +16 encodes GVA=2, physical=40, virtual=48; +20 is zero. Exact source-derived conventional capability chain is 0x60 MSI -> 0x5c HT -> 0x58 MSI stub -> 0x40 AMD -> 0. This chain still needs runtime-capture confirmation. Walk only aligned conventional capability pointers in 0x40..0xfc, track visits, bound the walk, require the IVHD capability to be reachable, and check its complete 24-byte extent. No BAR-sizing writes are needed or allowed.

The QEMU aperture is exactly [0xfed80000,0xfed84000), 16 KiB aligned. The indexed official AMD 3.09 cap+04h description (printed p199) says PCSup=0 uses a 16-KiB sized/aligned aperture, while PCSup=1 requires 512 KiB sized/aligned. The selected EFR has PCSup bit9 clear. The actual base still needs reconciliation against IVRS, PCI, CPU physical-address limits, memory classification and other admitted ranges before mapping.

Critical emulator exception: cap+04h Enable bit0 is zero in QEMU's initialized image, but QEMU maps its MMIO region unconditionally during realization. AMD's base-register description says hardware accepts MMIO when Enable=1. Admit this inconsistency only as the explicitly pinned QEMU profile; do not enable the bit, silently generalize it, or claim physical-platform compatibility.

For the bounded discovery snapshot, allow only aligned 64-bit reads at offset 0x0018 (control), 0x0030 (EFR), and 0x2020 (status), expecting respectively 0, 0x29d3, 0. The exact QEMU read handler performs ordinary loads with no read-clear side effects. Status writes have write-one-to-clear behavior; never write it to acknowledge anything. EFR describes advertised capabilities; it does not indicate activation. These three values establish only a profile-matched inactive discovery snapshot. They do not attest all backing tables, isolation, interrupt safety, or a hardware reset. Revoke the read window after the fixed budget.

## Provenance and access limits

QEMU v10.0.13 annotated tag 1316ebc0a7df407e8f5b91251b9ee2d9498187f9 resolves to commit **98f88efe8f07067667b8d9b1a5ce9551d34036c1**. Source files in this directory were reconstructed from GitHub connector contents and verified against Git blob IDs:

- [acpi-build.c](https://github.com/qemu/qemu/blob/98f88efe8f07067667b8d9b1a5ce9551d34036c1/hw/i386/acpi-build.c), build_amd_iommu/insert_ivhd, blob 3fffa4a332801c7f9780c49b1f5cfdbef3511c94.
- [amd_iommu.c](https://github.com/qemu/qemu/blob/98f88efe8f07067667b8d9b1a5ce9551d34036c1/hw/i386/amd_iommu.c), PCI realization, reset, MMIO read and translation functions, blob 8efebd3eea18335992d4f63df3503551e9787bab.
- [amd_iommu.h](https://github.com/qemu/qemu/blob/98f88efe8f07067667b8d9b1a5ce9551d34036c1/hw/i386/amd_iommu.h), register/feature constants, blob 04e3ad072e062790c1069133e51dd7c0d2197056.
- [pci.c](https://github.com/qemu/qemu/blob/v10.0.13/hw/pci/pci.c), pci_add_capability prepends capabilities; [msi.c](https://github.com/qemu/qemu/blob/v10.0.13/hw/pci/msi.c), msi_init adds the final MSI record.
- [Linux v6.18 init.c](https://github.com/torvalds/linux/blob/v6.18/drivers/iommu/amd/init.c), entry parsing and IVMD handling; [ACPICA actbl2.h](https://github.com/torvalds/linux/blob/v6.18/include/acpi/actbl2.h), layout cross-check only.

AMD [48882 rev3.10 February 2025](https://docs.amd.com/api/khub/documents/GD6kOXjzWsek8QUbn_qMvg/content) is indexed by public search, but its body returns HTTP 404. The [official rev3.09 October 2023 URL](https://www.amd.com/content/dam/amd/en/documents/processor-tech-docs/specifications/48882_IOMMU.pdf) also returns 404. No permission-denial route was bypassed and no downloaded PDF is available here. Official indexed snippets confirm 3.10 section2.3 aperture sizing and these relevant printed references: IVRS tables83..86 pp285..287; IVHD10 tables88..92 pp290..291; IVHD11 tables93..96 pp293..294; entry tables101..108 pp297..301; IVMD tables109..111 pp303..304. This report does not claim a complete normative 3.10 review. The exact emulated acceptance profile is independently justified by pinned producer/device source and observed bytes; physical AMD and Framework 7840U qualification remains deferred.
