# Bounded emulated DMA diagnostics

This is an emulator-only diagnostic model and reusable test material. It does not
implement Aurora production DMA, grant device authority, activate a physical
requester or replace the project's default QEMU runtime. Full IOMMU conformance,
physical isolation/drain/reclamation and AMD hardware support remain unqualified.

Current-source compiler/kernel changes require the final GCC 16 full suite and applicable image/guest checks. Earlier receipts do not transfer qualification.

## Aurora-owned event intake

The implementation provides a real Aurora bounded polling loop through distinct
sealed `IommuEventSession` and `ConsoleSession` borrows. Aurora decodes ordinary
code-2 fault records, emits at most 96 bytes per record, and acknowledges only
after its output succeeds. Code5 and unsupported records remain pending. Closed
poll/ack results, zero budgets, exhaustion and output failure are explicit. This
is source-program ordering; Event authority alone does not certify telemetry.

The shared `console.io` writer adds one defining-module reflection scope. Event
image admission requires exactly the root and scope-1 size/field-count helper
pairs, all global text definitions owned by the language object. Extra scopes,
different bindings and additional runtime authorities remain rejected. The
generated-source runner checks this inventory against actual linked output.

The bootstrap adapter authenticates both grants before live transport admission,
retains one copied pending record, and makes at most one head-write attempt per
acknowledgement. Overflow and uncertainty are absorbing. A failed acknowledgement
may have advanced the head; it conveys no retry or rollback guarantee. Entry
return revokes both grants. Event backing has a boot-lifetime owner and cannot
enter the existing CPU-only pin cancellation/reclamation paths.

The hosted implementation passes generated-source, real wrapper/session composition,
closed-result and hostile-IR controls. The opt-in UEFI adapter now retains its
DTE, mode-1 table, command, data and event pages for the whole boot; verifies actual
writable NX mappings; and opens operation-local MMIO windows. It requires exact
default-model IVRS/IOAPIC bytes, complete pre/post-firmware PCI facts, EDU BAR
ownership, other endpoint bus mastering disabled, and AHCI engines idle. It does
not reset an unsuitable controller to force admission. The newly implemented
firmware handoff below is a separate one-shot boundary before Event admission.

The four active modes are `iommu-event-denial`, `iommu-event-success`,
`iommu-event-overflow` and `iommu-event-command-error`. Build-only selection through
`UEFI_MODE` and `scripts/kernel-uefi-build.sh` remains available. Ordinary hosted
Event tests stay in the fast native graph and never launch QEMU.

### Supported local developer execution

`make smoke-iommu-event` builds fresh normal and Event images, reproduces current
`checked()` source/image/stack admission and validates two byte-identical raw ESPs
per profile. It runs the four active profiles sequentially, then restores the
exact staged normal artifact inventory and boots normal UEFI with the existing
serial oracle and native exit 33. The generic UEFI launcher still rejects Event;
this opt-in target is outside `make test` and `smoke-all`.

Supply the [custom-model inputs](../tools/qemu-amdvi/README.md#developer-event-runtime)
through `EVENT_BUILD_RECEIPT`, `EVENT_CODE`, `EVENT_VARS`, `EVENT_DATA`. Ordinary
`QEMU`/`QEMU_DATA` and `OVMF` or `OVMF_CODE`/`OVMF_VARS` independently select normal
restoration. `scripts/kernel-iommu-event-smoke.sh --build-only` checks the same
fresh images/ESPs and restores normal bytes without guests or a custom runtime.
Missing tools, files or required configuration and insufficient reserved space are
`BLOCKED` (runner exit 2) before build/evidence allocation. Present but malformed,
unsupported or mismatched inputs, including custom model, binary and dependency
integrity failures, are `FAIL` (runner exit 1), as are build, image-admission and
guest defects. GNU Make returns 2 for an unsuccessful recipe in either case.

Initial ESP support is installed GNU mtools 4.0.48 with standard system config
locations, selected through PATH or `MTOOLS_DIR`. It checks initial versions and
current executable/link identities, without historical binary-size/hash pins.
Private HOME and a clean environment are required. Both `/etc/mtools.conf` and
`/etc/default/mtools.conf` must be absent: `MTOOLSRC=/dev/null` is additive.
Other versions/custom compiled config paths are unsupported. Instead of changing
host configuration, `EVENT_ESP_DIR` may supply `<mode>.raw` for each fresh loader;
the same complete FAT/allocation/loader validator runs before a SHA-bound private
copy. Historical pinned mtools behavior and receipts are unchanged.

Each run creates a fresh `build/aurora-event-smoke-*` directory and prints its path
before work starts. `EVENT_OUTPUT_PARENT` may select another existing directory
within `build/` or outside the source tree. After all selected checks and normal
restoration succeed, the shared graphical/Event retention helper drops only known
raw ESP copies, writable guest VARS and RAM captures. Summaries, oracle results,
serial/QMP/stderr, build logs and staged images remain. Default retention keeps
the newest two successful managed runs; `AURORA_EVENT_KEEP_RUNS=N` accepts 1..999,
or `all` to keep and pin the new run, including its raw files. Use `all` when
build-only inspection requires the raw ESPs. A `.keep` also pins an individual run.
Failures and interruptions retain all output. Unmarked historical directories,
active runs and malformed markers are never adopted for cleanup. Successful runs
are ordered by status-marker modification time, including older successful markers;
pruning happens after the current run finishes. Cleanup errors
warn without changing the completed test result. Each run reserves 1 GiB with a
1 GiB free floor; the shared policy bounds completed successful output without
removing failures or explicit keeps.
Closed q35/TCG argv uses owned regular ESP/VARS copies, private HOME/empty module
directory, no network, host disks, mounts, VFIO or arbitrary options. Fixed limits
are 1 MiB each serial/stderr, 64 KiB QMP, 30 seconds per case except overflow's
90 seconds, and separate two-second TERM/two-second KILL cleanup grace.

QMP stdio and an inherited anonymous serial pipe require no sockets. Paused proof
precedes six current-layout RAM captures totaling 45,856 bytes. The oracle checks
full ordered Event serial, the handoff/terminal, all three ring pages, guarded
snapshots and all 32 KiB of backing including tables/zero regions. Denial preserves
the discriminating sink check, not a universal zero-filled denied-read promise.
Failure markers, limits, early exit, forced cleanup, capture/restoration failure
never pass; an unsettled owned child blocks restoration rather than racing it.

A pass is **local developer emulator evidence**, without per-run handwritten
supervision or an independent receipt pin. `reviewed()` and historical qualification
remain unchanged. Final-source merge/release gates still need independent review;
old evidence does not transfer. Source-copied MMIO observations plus captured RAM
do not establish physical DMA drain, reclamation, concurrent producers or hardware
support. Historical NVMe/IVRS results remain separate.

### Read-only firmware observation

The separate `iommu-event-observe` build is read-only. It copies two complete six-port AHCI samples (CAP/GHC/PI and each
CMD/CI/SACT/TFD/CLB/FB) through a read-only UC/NX page, revokes that page before
serial reporting, and checks PCI/capability equality afterward. Matching samples
are observations only, not an idle, drain, ownership or transition guarantee.
Resource observations may retain inherited BME; their explicit read-only purpose
cannot become `EventAdmission`. EDU command 7 is describable only in this read-only mode; it is not Event admission.

Read-only observation also includes two EDU snapshots: 64-bit DMA command at 0x98,
32-bit status at 0x20 and IRQ status at 0x24. The reviewed
[QEMU EDU model](https://github.com/qemu/qemu/blob/98f88efe8f07067667b8d9b1a5ce9551d34036c1/hw/misc/edu.c)
returns these fields without scheduling the DMA timer or acknowledging IRQs.
The admitted EDU BAR receives one temporary read-only UC/NX page, revoked before
reporting. Twelve bounded metadata lookups report the copied UEFI descriptors
covering each page-rounded CLB/FB extent. Firmware buffers themselves are neither
mapped nor read; descriptor type/attributes are observations, not RAM ownership
or retention authority. Shared CLB/FB pages are reported without an alias claim.
Changed EDU samples or missing/invalid descriptors fail closed after reporting.
Production Event admission retains exact EDU command 2 and its BME denial.
The observation image links the ordinary
scalar language fixture and no Event producer, session, retained DMA backing or
service bridge. It returns through the existing normal diagnostic exit.

Acceptance is focused hosted positive/negative controls, a fresh GCC 16 image and
existing linked-image/stack admission under the unchanged 128 KiB payload and
16 KiB stack bounds, followed by an independently reviewed, separately authorized
read-only emulator plan. No transition writes, new DMA, reset/fallback, physical
access or recovered lost-run evidence is claimed. Raw observations must precede
any exact PCI command-reduction policy.

For the later handoff, [AHCI 1.3.1 sections 10.1.2 and 10.3](https://www.intel.com/content/dam/www/public/us/en/documents/technical-specifications/serial-ata-ahci-spec-rev1-3-1.pdf)
require ST clear and CR=0 before FRE clear and FR=0. The pinned
[QEMU 10.0.13 implementation](https://github.com/qemu/qemu/blob/v10.0.13/hw/ide/ahci.c)
clears CI/SACT when ST is cleared, so post-stop zeroes cannot prove prior idleness.
A stop must first establish equal idle CI/SACT/TFD samples, ordinary-RAM
firmware backing that remains retained, and an exact reviewed command reduction
with readback. An attempt limit would not establish the specification's timed
wait or physical drain. That preceding observation checkpoint implements no transition; the separate
source handoff below retains its own acceptance gates.

### One-shot firmware handoff

The handoff now accepts only the freshly observed six-function Q35 tuple with
all initial command words 7. It requires equal full AHCI samples, ST/CR already
zero, CI/SACT zero and TFD exactly 0x50; active command engines remain denied.
Two equal EDU DMA-command/status/IRQ samples must be zero. The shared command
list and six adjacent FIS extents must occupy two distinct, complete pages in
copied BootServicesData descriptors with exactly cache-capability attributes
0x0f. Both pages remain outside the arena and every admitted MMIO aperture.
Aurora's fixed allocator only uses arena pages, so these firmware pages are
never mapped as CPU data, overwritten, enrolled for allocation or reclaimed,
including on partial failure. Descriptor checks do not establish DMA drain.

Only FRE is cleared, preserving every other writable CMD bit; each bounded FR
poll compares all other AHCI fields with the prevalidated snapshot. Any timeout,
changed field or access failure denies further transition. There is no ST-stop,
reset, fallback or rollback. The 1,024-poll limit counts attempts, not a timed
specification wait. A boot-lifetime latch is consumed before transition I/O;
neither the same nor a fresh local policy object can retry after failure.

After all FIS engines stop, command-only 16-bit PCI writes reduce host, LPC,
AHCI and SMBus from 7 to 3, and EDU from 7 to 2. The IOMMU command remains 7.
This preserves IO/MEM decode except unused EDU IO decode. The
[model's generic PCI command handling](https://github.com/qemu/qemu/blob/98f88efe8f07067667b8d9b1a5ce9551d34036c1/hw/pci/pci.c)
gates each function's bus-master address space; it does not cancel or drain
operations, and LPC BME does not gate legacy ISA DMA. Every complete header
must read back with only its authorized command-word change. Original firmware
copies stay immutable, EDU zero state is checked around its reduction, and all
headers/caps and AHCI fields are rechecked before the one-shot post-state
admission is used.

Focused controls must cover successful ordering, every read/write failure, FR timeout, unexpected AHCI/PCI changes, unsuitable backing and retry refusal. Event image/stack admission retains the 128 KiB payload, 16 KiB stack and 15,360-byte normal-plus-reserve limit. Hosted/admission checks do not establish a real guest result or physical DMA drain.

## Mechanism and trust boundary

The harnesses launch q35/TCG with 64 MiB guest RAM, AMD-Vi and an EDU PCI test
device, no default devices/display, and an owned reset ROM that halts the CPU.
They do not boot Aurora, open a host disk or attach hardware. Only the emulated
EDU requester receives test BME. qtest physical reads/writes arrange tables and
inspect memory; they are not DMA evidence. EDU itself calls `pci_dma_read/write`
through its requester, providing a separate emulated DMA observation path.

Positive transfers require exact distinct source bytes to reach a translated
sink while numerical-IOVA decoys and guards stay unchanged. Denied writes must
preserve selected target bytes. Denied reads use a fresh secret, a separately
permitted output mapping and independent helper/liveness controls; helper success
is never counted as the denied request's success. The EDU RUN bit clearing means
its emulated operation finished, not that a physical fabric drained. EDU ignores
MemTxResult, and an errored read need not preserve its prior internal buffer.

[Three exact patches](../tools/qemu-amdvi/README.md) repair distinct model slices:

1. Event transport: correct the overflow-mask predicate, byte-sized ring geometry,
   reserved empty slot, wrap/tail publication, little-endian record encoding,
   EventLogInt selection and EventIntEn notification gating. Failed event-RAM
   writes, malformed rings and IRQ delivery remain outside the accepted slice.
2. Bounded requester/Mode1 permissions: enforce the full requester-table bound,
   separate raw DTE fetch from ordinary-memory validity, reject supported high
   IOVA/nonpresent/TV=0 cases, intersect parent/leaf permissions and record bounded
   cache provenance. The profile is common 40-bit ordinary memory with no exclusion.
   Early range/parent faults can precede discovery of excluded leaf attributes;
   general preservation of every excluded input is not claimed. V=0 bypass and
   legacy/excluded paths retain their separately documented source behavior.
3. Dispatch-default stop: only opcodes 0 and 9–15 stop the synchronous command
   runner, retain the offending head and clear CmdBufRun before later commands
   can execute. The RUN gate prevents head/tail notifications from bypassing the
   settled stop. Logging disabled, overflowed or full does not suppress stopping.
   The trace uses the actual first-qword opcode and the illegal event is code/address
   only. Recognized handler bodies are unchanged.

Recognized malformed commands can still continue effects, and command-read errors
can still advance through the caller. These are known defects, not accepted
alternative behavior. STATUS writes are ignored because the MMIO switch has no
STATUS dispatch; this also leaves W1C/overflow recovery broken. The declared RO
mask is not the operative explanation. Exclusion-base writes are likewise not
implemented, so the bounded profile must remain explicitly no-exclusion.

No internal cache hit, requester-targeted invalidation, general IRQ/ATS, other
translation mode, broad excluded-path behavior, arbitrary confidentiality or
physical-device property follows from these patches. Priming a request is not
proof of a cache hit. The unchanged requester-cache invalidation defects remain
separate work.
