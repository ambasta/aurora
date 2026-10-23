# Read-only AMD-Vi observation profile

This slice copies firmware topology and observes three static registers in a
specified emulator. It neither configures DMA protection nor grants a device
activation right. No IOMMU control, device/page table, command/event queue,
interrupt, NVMe queue or BME programming belongs to Aurora's path.

## Actual profile and limits

The observed 168-byte IVRS contains one IVHD0x10 and one IVHD0x11 for the same
unit: segment0, requester0x18 (00:03.0), capability0x40, base0xfed80000. Seven
SELECT entries cover the independently enumerated PCI functions, including the
namespace-free NVMe requester0x10. Both record variants must have consistent
shared identity, resource and complete duplicate-free requester sets. Duplicate
same-type records, contradictory companion records and incomplete inventory
coverage reject. Aliases, ranges, special entries and IVMD reserved-memory
records are deliberately unsupported and reject before register access. Their
absence is a bounded profile fact, not a claim that real firmware lacks them.

The parser is explicitly selected for QEMU10.0.13 commit
98f88efe8f07067667b8d9b1a5ce9551d34036c1. Its producer truncates the HATS/GATS
contributions when serializing IVHD0x10 feature0x44; IVHD0x11 EFR0x29d3 retains
those fields. Exact per-format constants and all shared facts are validated.
This is an acknowledged producer discrepancy, not generic equivalence of the
two architectural feature encodings. AMD's indexed specification revisions3.10
and3.09 returned HTTP404 for their PDF bodies during this work. Pinned QEMU
producer/device sources plus actual bytes support this emulator-only profile;
normative physical-hardware qualification is incomplete.

QEMU initializes the PCI capability MMIO base to0xfed80000 with its Enable bit
clear, but maps the16KiB device region unconditionally. Architectural-default
admission therefore refuses the observed device before mapping. Only the
separate compile-selected Qemu10_0_13AmdViCold profile admits observations of
this exact quirk. It is never selected as fallback after an admission failure.
The profile binds the QEMU binary, official-source custom OVMF fixture, pristine
VARS and explicit options: pt=off, intremap=off, device-iotlb=off, xtsup=off,
q35/TCG/qemu64/singleCPU/128MiB. With CTRL.IommuEn=0, QEMU permits identity DMA;
pt=off does not establish isolation. Other firmware-enabled bus masters remain
outside this observation contract.

## Copied facts and mapping lifetime

Firmware tables use the existing bounded copy/header-consistency/checksum path.
No firmware pointer survives it. The live IOMMU header and48-byte capability
region are read twice through ECAM and checked against exact identity, fixed
capability chain and disabled MSI state. The entire16KiB aperture, including
page padding, must fit physical width and avoid RAM/runtime/persistent/cache
conflicts, arena, ECAM, APIC and all assigned memory BAR reservations. The
adapter revalidates complete reservation coverage and includes the NVMe BAR.
The current NVMe admission must already have succeeded with BME clear and zero
controller/queue state; discovery alone supplies no such authority.

A distinct supervisor-only UC, read-only, NX, nonglobal window admits only
64-bit CTRL+0x18, EFR+0x30 and STATUS+0x2020 reads. The first two share one page;
the third uses a second page. Each page is unmapped with INVLPG before reuse.
Fresh configuration snapshots and expected0/0x29d3/0 values precede final ticket
revocation. Stale leases reject and complete page-table validation confirms
closure. A write probe must fault before a device write; a post-revocation read
must fault at the exact linked instruction and window address. No user domain
can map these windows.

## Stack regression and evidence

Adding diagnostics exposed a bootstrap-stack exhaustion: the inspect_bar
prologue wrote192 bytes below the fixed16KiB stack bottom. The real fault trace
records page fault then double/triple-fault delivery. Those failed runs are
retained. ACPI parsing and PCI scan-construction temporaries now end before
subsequent phases. No stack or guard was widened. Compiler stack-usage records
and explicit reviewed call paths are checked at every IVRS build, including a
fault-delivery reserve. This is a regression bound for these paths, not a
whole-program stack proof.

Cold traces contain QEMU startup IOTLB resets and a passthrough interrupt-remap
sequence before guest execution. Those must be accounted for explicitly.
The event named amdvi_mmio_write only covers invalid-range accesses in this
QEMU version. Runtime write absence therefore depends on complete generic
memory_region_ops_write coverage of the full aperture and region identity,
including crossing/malformed writes. A separate stopped-CPU control verifies
the exact valid same-zero CTRL write producer and readback. Any broader failed
control criterion remains recorded; it is not silently reclassified as a
passed boot. The control never becomes part of Aurora execution.

## Gates

Eleven modes cover architectural-default refusal; explicit-profile observation;
write and revoked-read faults; inconsistent pair, alias, reserved-memory and
requester-scope injections; capability and RAM-conflict injections; and missing
IVRS. Injected copied-table/map failures are not claims about hostile firmware
encountered in the normal fixture. Historical147 modes retain their own firmware
and acceptance profiles. Final receipts must include exact source/tool/firmware
hashes, argv, complete raw traces, linked fault metadata and copied input bytes.

The five live modes boot one `ivrs-fixture` image. Default, read, write and
revoked read the serial selector after ACPI closure; default selects the
architectural profile there and every other case the explicit QEMU cold
profile, never as a fallback. Missing IVRS rejects in ACPI discovery before
the selector. Default and read used to be separate images; the fixture now
links both exact fault instructions for every case, and each mode keeps its
own serial, trace and provenance oracles.

Primary implementation references are the pinned QEMU
[IVRS producer](https://github.com/qemu/qemu/blob/98f88efe8f07067667b8d9b1a5ce9551d34036c1/hw/i386/acpi-build.c)
and [AMD-Vi device model](https://github.com/qemu/qemu/blob/98f88efe8f07067667b8d9b1a5ce9551d34036c1/hw/i386/amd_iommu.c).
The source-derived startup explanation follows HPET/PIT, GSI/IOAPIC and AMD-Vi
reset ordering. It was not separately instrumented as a complete dynamic call
trace. Independent review accepted the retained control solely as the exact
valid same-zero CTRL producer witness; its original broader whole-run absence
criterion remains failed.
