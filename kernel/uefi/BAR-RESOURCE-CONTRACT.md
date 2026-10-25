# Bounded read-only NVMe resource handoff

This development slice grants seven precise read operations on one namespace-free
QEMU NVMe controller. It does not activate a controller, allocate queues, grant
DMA, configure interrupts, reset inherited state, or qualify Framework hardware.

## Authority and lifetime

Before ExitBootServices the loader copies PCI configuration and firmware BAR/root
resource descriptors into an owned, subsequently read-only arena page. Copies
are bounded and repeated for consistency. Firmware readability does not imply
allocation ownership. The named fixture requires segment 0, bus 0, device 2,
function 0, vendor/device 1b36:0010, class 01:08:02, header 0 and BAR0's exact
64-bit, non-prefetchable shape. The runtime compares fresh configuration against
the captured snapshot and inventories all other assigned memory BAR slots.
Missing, duplicate, extra and overlapping reservation records reject admission.

The strict descriptor parser remains the default. The explicitly selected
`edk2-stable202502-q35-nvme` profile reflects the pinned EDK2 producer: BAR
AddrRangeMax is an alignment mask equal to length minus one, while root memory
windows use inclusive ends. BAR lengths must be bounded powers of two, bases
aligned, all arithmetic within physical width, and the entire range covered by
one unambiguous zero-translation root window. Root I/O flags grant no I/O rights.
BAR/root profile substitution rejects. This is not a generic Framework ACPI
_CRS or UEFI resource interpretation.

The complete BAR and mapped-page padding must avoid owned arena pages, RAM,
runtime/persistent memory, ECAM, APIC and other accepted BAR reservations. A
separate supervisor-only, read-only, NX, UC, nonglobal window admits only aligned
CAP(64), VS(32), CC(32), CSTS(32), AQA(32), ASQ(64) and ACQ(64) reads. These are
non-destructive register observations; doorbells and MSI-X are inaccessible.
A final fresh configuration comparison precedes admission. The final grant
requires memory decoding enabled, bus mastering disabled and CC/CSTS/admin queue
registers zero. Mapping teardown clears the PTE, executes INVLPG, revokes the
lifetime ticket, and rechecks the closed page-table tree. The stale window is
actually faulted in an emulator gate. Another gate verifies a write faults before
any device write. No writable or differently cached alias is admitted.

The state, capture, read, inherited, write, revoked, alias and NVMe preparation
gates are rows of the one `platform-fixture` image, selected through fw_cfg at
loader entry. Only capture and later rows capture the firmware BAR record, only
capture keeps the generic resource parser, and only state prints the admission
refusal. Write, revoked and alias used to be separate images. The fixture links both exact fault
instructions for every case and each gate keeps its own serial, trace and
provenance oracles; the stock-firmware trace control boots the same image as
the inherited case.

## Explicit firmware fixture

Original packaged OVMF leaves this controller active: command=7, CC=0x460001,
CSTS=1 and nonzero AQA/ASQ/ACQ. That real rejected admission is retained. Aurora
does not clear BME or reset it.

A separate official EDK2 source fixture is pinned to
fbe0805b2091393406952e84724188f8c1941837 (edk2-stable202502). Its three-file policy
diff removes NvmExpressDxe from DSC/FDF and changes only the exact matching
endpoint in PlatformBootManagerLib: unexpected initial BME rejects; only memory
decoding is enabled, then MSE=1/BME=0 is read back. Other endpoints retain upstream
behavior. Generic PCI enumeration transiently probes command bits including BME
and restores them. The claim is never-initialized NVMe from cold reset with an
inactive/BME-clear handoff, not that BME was never transiently set.

Each accepted fixture boot starts from a preserved pristine VARS image. QEMU
configuration/MMIO/debug traces begin at process startup and must show the pinned
configuration sequence, firmware markers before Aurora entry, no controller
initialization/queue/doorbell writes and the seven exact Aurora reads. Stock OVMF
provides a positive initialization-write trace control. A separately labeled
stopped-CPU, no-firmware/no-drive/no-namespace MSI-X control verifies generic
write trace coverage with exactly one same-value masked vector-control write.
It is excluded from Aurora/clean-firmware acceptance runs.

The dependency closure excludes uninitialized GoogleTest/Subhook placeholders;
this is not a fully recursive checkout. Official target dependencies, exact
source/submodule hashes, the three-file diff, consumed-header hashes, build logs
and firmware hashes are external build receipts. Third-party binaries do not
belong in this repository. Firmware trust and other inherited bus-master devices
remain outside this grant: neither discovery nor inactive readback establishes
DMA isolation. IOMMU activation and controller teardown require separate designs.

## Gates

`meson test -C build/meson --suite full` runs profile/range/lifetime/reservation policy and strict
serial/trace controls. `scripts/kernel-run.sh bar` runs seven actual modes:
stock state refusal, strict-profile refusal, inherited-controller refusal,
clean read success, write fault, revoked-read fault and alias rejection.
`AURORA_BAR_RECEIPTS` must name a fresh output directory. Set `AURORA_BAR_FIRMWARE`
to the separately built fixture directory and `AURORA_BAR_COVERAGE` to its pinned
trace-control description, alongside AURORAC/QEMU/QEMU_DATA/OVMF and library path.
Every run preserves argv, tool/firmware hashes, cold VARS, serial/debug/trace,
payload bytes/ELF/exact fault offsets and status. A normal image is restored.

## Queue-page preparation

The [CPU preparation increment](NVME-QUEUE-PREPARATION.md) adds the
opt-in `bar-prepare` fixture over the existing owned payload pool. Preparation and
scrubbed cancellation happen before this BAR window is revoked. BAR read-only grants confer no device/DMA authority; the seven BAR modes retain
their read-only semantics. Preparation uses its own linked-stack and actual
preparation/refusal gates before normal-image restoration.
