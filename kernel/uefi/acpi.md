# Bounded ACPI discovery and revocable read window

The optional ACPI profile consumes actual OVMF firmware tables after the existing
UEFI handoff. It reports checked processor and local-APIC metadata, revokes every
source mapping, and then completes the ordinary protected payload. It neither
programs APIC hardware nor evaluates AML, routes interrupts, starts processors,
or provides a Framework device driver.

Run `meson test -C build/meson --suite guest-acpi` with the same QEMU/OVMF variables documented in
[the UEFI gate](README.md). `meson test -C build/meson --suite full` runs hosted
range/parser/window-policy tests. The existing 8 UEFI and 28 BIOS gates remain
separate baseline checks. The two-CPU emulator profile discovers both firmware
records; only the bootstrap processor executes our payload.

## Input and ownership boundary

The loader recognizes the ACPI2 configuration-table GUID from a validated UEFI
system table. The table array has a maximum 128 entries, and its complete storage
must be inside admitted firmware RAM before entry bytes are read. Missing,
zero-address or duplicate matching roots fail before ExitBootServices. The root
selector latches failure rather than retaining usable authority after ambiguity.
An optional version 2 of the 128-byte handoff carries the RSDP physical address;
version 1 and its reserved-field requirements remain supported for older gates.

After the private CR3 transition, FirmwareRanges admits only complete ranges
covered by EfiLoaderData, EfiBootServicesData, EfiRuntimeServicesData,
EfiACPIReclaimMemory or EfiACPIMemoryNVS descriptors supporting write-back memory.
EFI_MEMORY_NV is rejected independently of the memory type. MMIO, reserved,
persistent and unaccepted types are rejected. The entire owned 2 MiB kernel arena
is excluded from source reads, preventing a second alias of its writable pages.
Runtime and ACPI pages can be readable without being allocatable: this mechanism
never grants them to PhysicalPages or reclaims them.

Every requested byte range and every mapped containing page must pass admission.
Arithmetic, gaps, physical-address width and page boundaries are checked. Both
loader and consumer obtain the physical width from CPUID, bounded 32..52 bits.
The reader requires PAT support and PAT entry 0=WB before using it. It adds no
conflicting source alias in the active address space: ordinary kernel mappings
cover only the excluded arena, and a single source page exists temporarily in
the read window. Firmware/MTRR correctness remains a platform assumption; this
is not physical-machine cache-policy qualification.

## Temporary mapping lifetime

The dedicated virtual page is0xffff800000000000. Its preallocated page-table
branch contains no leaf until a read begins. A mapped leaf is supervisor-only,
read-only, NX and nonglobal. A unique monotonic ticket identifies one active
mapping; nested, foreign, stale, replayed and reconstructed-controller tickets
are rejected. The single-CPU reader exposes copied bytes rather than a pointer
whose validity could outlast that ticket.

ReadPlan partitions a bounded copy into exact 4 KiB fragments. After each fragment,
the adapter clears the PTE, executes INVLPG and revokes the ticket before mapping
another physical page. Final discovery requires equal copy/revocation counts,
an absent window PTE and a complete private-table-tree validation. An actual
read through the recently used but revoked address faults14/0; an actual write
while the source page is mapped faults14/3. These gates test hardware translation
state, not just a counter claiming that unmapping happened.

Kernel interrupts stay disabled throughout this bounded operation. There are no
parallel readers, page reclamation callbacks or user-facing mapping/syscall API.
Unexpected hardware faults fail-stop; a successful discovery leaves no live
firmware source mapping. Source pages are never mapped executable or writable.

## Snapshot parsing

The parser operates on owned arena copies. RSDP uses its signature, revision 2,
legacy 20-byte checksum, bounded extended length/checksum and reserved bytes.
The XSDT uses revision 1, an exact bounded length, checksum, at most 128 entries,
and rejects zero, repeated or self-referential addresses. Only one MADT is
accepted. Other table pointers are inspected through admitted bounded headers;
no secondary table graph or AML method is followed.

A header read precedes the full copy. The full requested range is admitted, then
the copied header must equal the earlier header byte-for-byte. Lengths and the
full checksum are validated on the final owned snapshot. The hosted changed-header
fault fixture recomputes a valid checksum, so a checksum check alone cannot make
that negative test pass. Checksums detect corruption; they do not authenticate
hostile firmware, make DMA atomic, or provide a cryptographic snapshot guarantee.

The MADT accepts supported revisions 1..6, bounded known local-APIC/x2APIC records,
zero reserved fields and at most 256 processor records. Duplicate APIC IDs or
processor UIDs, conflicting overrides, zero/truncated record lengths and
out-of-width/unaligned local-APIC addresses are rejected. A single 64-bit LAPIC
address override is honored. Enabled and online-capable bits are kept distinct:
a disabled but online-capable processor is never reported as enabled. Unknown
record types are skipped only using a checked, advancing length. No read or
write to the reported local-APIC address follows from parsing its value.

Fixed snapshot storage is at arena offsets0x60000..0x81000, supervisor RW/NX.
The XSDT and MADT each have a 64 KiB buffer; RSDP has 4 KiB. These buffers are outside
the pool and private stacks. The parser receives read-only views of these owned
bytes. The source window never points into these buffers.

## Evidence gates and limits

Eight emulator scenarios are rows of the one `platform-fixture` image, selected
through fw_cfg at loader entry: the baseline row runs ordinary `acpi` (and
`acpi-two`), and loader-time `acpi-duplicate-root` rejects before
ExitBootServices. ACPI rows require no MCFG and end after ACPI discovery, as
their ACPI-only image did. The fault selectors preserve disabled-record success, checksum failure propagation,
bad-source rejection and real write/revoked page faults. The row is admitted in
the loader, before any firmware window acquisition; nothing reads a serial selector.
Ordinary and production images contain no selector or injection authority.

Pure mutations moved to existing hosted assertions: bad-entry uses the MADT
record-length zero loop; changed-header uses the same repaired byte10 mutation;
duplicate CPU records use independent duplicate APIC ID and UID rejection.
Hosted tests also retain page-crossing copies, cache/NV rejection,
stale/foreign/lifetime tickets, table checksums, disabled x2APIC records,
LAPIC override and128-entry/256-processor boundaries. Transcript controls still
reject missing/duplicated phases, incorrect CPU state and wrong fault addresses.
The original30-second guest deadline is unchanged.

Firmware is trusted to provide physical RAM and stable platform configuration.
DMA/device quiescence, IOMMU, NMI/SMI transitions, runtime services, ACPI power
management, PCI enumeration and physical Framework qualification remain outside
this gate. Current functionality is safe bounded discovery on the tested OVMF
platform, not a complete ACPI implementation or a driver-support claim.

Primary references: [UEFI2.11 configuration tables](https://uefi.org/specs/UEFI/2.11/04_EFI_System_Table.html),
[UEFI memory descriptors](https://uefi.org/specs/UEFI/2.11/07_Services_Boot_Services.html),
and [ACPI6.6 RSDP/XSDT/MADT definitions](https://uefi.org/specs/ACPI/6.6/05_ACPI_Software_Programming_Model.html).
