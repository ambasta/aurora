# Read-only PCI inventory on the OVMF/q35 fixture

This executable bootstrap slice snapshots MCFG, admits one explicit emulator
ECAM aperture, and inventories configured PCI functions after ExitBootServices.
It identifies controllers that future drivers can bind to. An inventory record
has no device, interrupt, BAR, allocation or DMA authority.

The supported profile is QEMU 10 q35 with the locally verified OVMF firmware,
segment zero, buses 0 through 255, ECAM physical addresses
`0xe0000000..0xf0000000`. QEMU's reset host property is `0xb0000000`; OVMF
reprograms it to its PCI Express base address. The first attempted boot with the
reset-address profile rejected the actual MCFG before mapping configuration
space. The accepted profile now matches the verified post-firmware aperture;
there is no arbitrary-address fallback.

MCFG describes configuration locations. It does **not** establish resource
reservation. This fixture's explicit platform contract supplies that missing
premise. Generic ACPI `_CRS` resource reconciliation, additional host bridges,
Framework firmware qualification and IOMMU/DMA ownership remain prerequisites
for physical hardware and device activation.

## Authority and mapping boundaries

The existing firmware read window obtains an owned, bounded, checksummed MCFG
snapshot with exact header/full-copy consistency. Duplicate XSDT pointers and
multiple MCFG roots fail closed. `Mcfg` checks revision, reserved fields, entry
size/count, physical width, bus bounds, overlapping physical apertures and
segment bus ranges. Addresses use the **absolute** bus number:
`base + (bus << 20) + (device << 15) + (function << 12)`.

`Q35Ecam` separately requires the exact fixture allocation. It rejects any
intersection with the owned arena or firmware memory other than reserved/MMIO
entries; runtime and persistent attributes are denied. An absent firmware-map
entry is acceptable only within this exact emulator contract. Neither a map
hole nor an MCFG entry grants generic MMIO authority.

Before config access, the full active page-tree walk proves that only owned
arena leaves exist and that the firmware window is revoked. ECAM then reuses
that one high virtual window with supervisor read-only, NX, nonglobal mappings.
PAT entry 3 must already be UC; PWT and PCD select it. No PAT/MTRR programming is
performed. The whole 4 KiB physical function page must fit the admitted aperture.
Each access clears its PTE and executes INVLPG before returning or reusing the
window. Final validation checks that the window is empty and that the complete
owned-root mapping invariant still holds. Thus the active root contains no
writable or differently cached alias of an ECAM page.

The adapter loads naturally aligned DWORDs only within the first 64 config
bytes, reading just the first DWORD for an absent vendor. Two independent
header snapshots must agree before policy consumes them. A change is rejected;
this does not establish an atomic hardware snapshot or support hotplug. The
single CPU has interrupts disabled throughout discovery. Existing firmware
trust, SMM and externally initiated DMA are outside this emulator gate.

## Bounded traversal

Only function zero enables multifunction probing. Configured PCI-to-PCI bridges
are followed using firmware-assigned primary/secondary/subordinate numbers.
Zero secondary/subordinate denotes an unconfigured bridge and is inventoried
without traversal. Cycles, duplicate routes, sibling overlap, escaping ancestor
ranges and contradictory header/class records are rejected. Unknown header
layouts fail closed. Limits are four parsed MCFG allocations (the current
platform authorizes exactly one), 64 visited buses and 256 present functions.
Only a complete immutable inventory escapes success.

Reported records include BDF, vendor/device, class/subclass/interface, header,
observed command bits and bridge bounds. Command bits can show that firmware
already enabled bus mastering. Reading those bits neither changes them nor
proves devices quiescent. There are no BAR-sizing writes, bus assignment,
command writes, interrupt setup, device BAR accesses or driver commands.
The deliberate write-fault gate attempts a store through a read-only PTE and
requires a CPU protection fault before a PCI write transaction could occur.

The native inventory is 4,624 bytes. With current optimized bootstrap flags,
`discover_acpi` uses 3,504 bytes and the inlined PCI discovery path uses 10,736
bytes, plus bounded small caller/helper frames, within the guarded 16 KiB
payload stack. This remains a fixed bootstrap bound, not a general kernel stack
sizing policy.

## Runnable gates

Use the same `QEMU`, `QEMU_DATA`, `LD_LIBRARY_PATH`, `OVMF` and pinned `AURORAC`
setup documented in [the UEFI guide](README.md).

- `meson test -C build/meson --suite full`: hosted parser/range/topology tests and strict
  positive/adversarial transcript validation; `SANITIZE=1` adds ASan/UBSan.
- `meson test -C build/meson --suite guest-pci`: all seven actual OVMF scenarios, using two PCI
  images (ordinary and shared fixture), restoring the normal
  UEFI image after each variant.
- `scripts/kernel-uefi-smoke.sh pci`: default q35 inventory.
- `pci-devices`: NVMe controller with no namespace/backing disk, xHCI controller,
  and a disconnected e1000e network function.
- `pci-bridge`: firmware-configured root port and downstream NVMe controller.
- `pci-checksum`: corrupt only the owned MCFG snapshot and retain the real
  fail-stop witness: ACPI window closure precedes rejection, with no ECAM
  aperture, inventory or language success published.
- Reserved-byte and overlapping-allocation rejection are exercised directly by
  the existing hosted `Mcfg::parse` controls. Zero-base MCFG is parseable but
  rejected by the hosted `Q35Ecam::authorize` control. These replace the former
  `pci-reserved`, `pci-overlap` and `pci-range` image variants without changing
  production parser/admission behavior.
- `pci-cycle`: corrupt only a copied bridge header to point at its parent;
  require no completed inventory or language execution.
- `pci-write`: supervisor write protection, page fault 14/error 3 at the window.
- `pci-revoked`: recently unmapped read, page fault 14/error 0 at the window.

The four remaining PCI fault scenarios share `pci-fixture`, with exact selectors
97 through 100 from the existing fixture catalog. The existing serial readiness
transport sends the selector after ACPI window closure and before MCFG parsing
or PCI mapping. An out-of-family selector fails closed. The ordinary `pci` image
contains no selector reader or injection state. Existing 30-second guest deadlines
and original emulator clock selection are unchanged.

All successful inventory gates continue to compiled language result 42. All
rejections require debug-exit failure and prohibit downstream success markers.
Fault gates validate the owned arena/root/stack, exact CR2 and payload RIP.
The 52 earlier BIOS/UEFI/ACPI/division modes remain separate acceptance gates.

## Primary references

- [EDK2 MCFG layout](https://github.com/tianocore/edk2/blob/edk2-stable202502/MdePkg/Include/IndustryStandard/MemoryMappedConfigurationSpaceAccessTable.h)
- [EDK2 PCI Express base/size defaults](https://github.com/tianocore/edk2/blob/edk2-stable202502/MdePkg/MdePkg.dec)
- [OVMF platform initialization](https://github.com/tianocore/edk2/blob/edk2-stable202502/OvmfPkg/Library/PlatformInitLib/Platform.c)
- [QEMU q35 reset register model](https://github.com/qemu/qemu/blob/v10.0.0/include/hw/pci-host/q35.h)
- [Linux PCI/ACPI documentation on reservation and absolute bus addressing](https://www.kernel.org/doc/html/v6.6/PCI/acpi-info.html)

The initial independent run on compiler
`11ad14a187f0cd69539626dbafaff2f6340762ff1dd0430059ec192332c9f99b`
passed all ten actual modes. Default inventory contained five functions on one
bus with 39 window mappings/revocations; the added-controller fixture contained
eight functions on one bus; the bridge fixture contained seven functions on two
buses with 71 mappings/revocations. Hosted ASan/UBSan covered 71,054 checks;
transcript validation covered ten positive and 289 negative cases, including
an independently reproduced late-row ordering defect that was fixed.
