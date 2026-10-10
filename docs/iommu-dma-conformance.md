# Bounded emulated DMA diagnostics

This is an emulator-only diagnostic model and reusable test material. It does not
implement Aurora production DMA, grant device authority, activate a physical
requester or replace the project's default QEMU runtime. Full IOMMU conformance,
physical isolation/drain/reclamation and AMD hardware support remain unqualified.

The diagnostic integration landed in PR101 after its exact source passed the
then-required 61 dev and 30 slow tests. The unchanged historical emulator results
below retain their original model/fixture scope. New compiler and kernel changes
require current-source canonical Meson `full` with GCC 16 and applicable
image/emulator gates; GCC 14 is optional targeted compatibility evidence.
Earlier receipts do not transfer qualification.

## Aurora-owned event intake

The next implementation adds a real Aurora bounded polling loop through distinct
sealed `IommuEventSession` and `ConsoleSession` borrows. Aurora decodes ordinary
code-2 fault records, emits at most 96 bytes per record, and acknowledges only
after its output succeeds. Code5 and unsupported records remain pending. Closed
poll/ack results, zero budgets, exhaustion and output failure are explicit. This
is source-program ordering; Event authority alone does not certify telemetry.

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

The earlier denial-image checkpoint passed linked-image and stack review: 11,776 bytes
including its exception reserve fit the 15,360-byte admission cap within the
unchanged 16 KiB stack. The first rejected stack attempt remains retained; the
Event-only build uses fixed outgoing argument slots. The image invokes the real
Aurora loop after a finite producer batch and preserves all raw ring slots and
protected data before and after intake. Command-only diagnostics leave EDU bus
mastering disabled. Overflow at initial admission remains a pre-entry refusal.
Hosted and image checks alone do not establish live transport behavior, firmware
quiescence, physical isolation or completion.

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

Evidence is retained in a new private external directory under
`EVENT_OUTPUT_PARENT` (default system temporary directory). Each run reserves
1 GiB with a 1 GiB free floor; completed evidence is not automatically deleted.
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

On 2026-10-09, implementation tree
`9cc4ef76649faca206f8e70407acaa95c9f75b32` passed all 259 full-suite tests with
Debian GCC 16.2.0-3 and binutils 2.47. All four active Event modes passed independent
image/stack and actual guest review on the fresh custom QEMU 10.0.13/default
split-OVMF tuple. Denial execution from tree `4d44dd72` applies through re-admitted,
byte-identical execution images; success, overflow and command-error ran freshly
on `9cc4ef76`.

### Read-only firmware observation checkpoint

The fresh `iommu-event-observe` build is the next dependency for the blocked
handoff. It copies two complete six-port AHCI samples (CAP/GHC/PI and each
CMD/CI/SACT/TFD/CLB/FB) through a read-only UC/NX page, revokes that page before
serial reporting, and checks PCI/capability equality afterward. Matching samples
are observations only, not an idle, drain, ownership or transition guarantee.
Resource observations may retain inherited BME; their explicit read-only purpose
cannot become `EventAdmission`. EDU command 7 is describable only in this
read-only mode after the first stock-tuple observation found all six commands
were 7 and refused before AHCI. The second reviewed stock/default-split-OVMF
observation reached equal AHCI samples: ST/CR and CI/SACT were zero, while five
ports retained FRE/FR. Those facts are scoped to that fresh tuple.

The next read-only revision adds two EDU snapshots: 64-bit DMA command at 0x98,
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
Any future stop must first establish equal idle CI/SACT/TFD samples, ordinary-RAM
firmware backing that remains retained, and an exact reviewed command reduction
with readback. An attempt limit would not establish the specification's timed
wait or physical drain. That preceding observation checkpoint implements no transition; the separate
source handoff below retains its own acceptance gates.

### Narrow firmware handoff source checkpoint

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

Focused hosted controls exercise successful ordering, each read/write failure,
FR timeout, unexpected AHCI/PCI changes, unsuitable backing and retry refusal.
The first production builds exceeded the unchanged 128 KiB bound; their failures
remain preserved. Event-only ECAM/verifier outlining and BSS alignment packing
fit that bound without removing checks, snapshots, sections or alignments.
Other UEFI profiles retain their original outlining and BSS input order; the
shared linker source selects the policy from the existing Event build flag.
Event-specific firmware capture clauses also stay inside that build family;
ordinary BAR capture keeps its original entrypoint and compiled body. The
generated linker input is retained in the existing image build receipts. PE/PIC
checks pass. Extracting the complete bounded FR wait into its own policy helper
removes the counter spill; no SUBL decoder permission was added. Sharing the
unchanged page-table verifier body refreshes only its independently reviewed
source digest, retaining the exact lambda location and every association check.
The fresh denial image now passes automated image/stack checks: normal plus
exception reserve is 11,688 bytes, consumer plus reserve 2,312, within the
unchanged 15,360-byte admission cap. Other profiles, final integrated full tests
and transition execution retain their separate gates.
Neither this source checkpoint nor stock observation results qualify a new
patched-QEMU tuple, transition image or guest. Fresh image/stack and independent
bounded-method review remain required for independent transition qualification.
The current local developer route above does not claim that review status.

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

## Preserved historical results

The exact source/patch/fixture/build/report/review identities are summarized in
[qualification.json](../evidence/iommu-diagnostics/qualification.json). Full source
trees, binaries, raw reports, transcripts and process supervision remain external
preserved evidence; the compact summary does not replace that evidence.

The corrected frozen 17-case fixture had these complete case totals:

| Model | Passed | Failed | Interpretation |
|---|---:|---:|---|
| Stock QEMU | 3 | 14 | Preserved failures |
| Event-only | 4 | 13 | Preserved failures; event transport became live |
| Combined-v2 | 4 | 13 | Preserved failures; bounded denial data improved |

Independent offline reconstruction accepted these as faithful completed diagnostics
with failures, not as aggregate conformance passes. Both candidates retain the
three stock passes and add the reserved-slot event-full case. Combined-v2 also
preserves mapped/physical sentinels in five cases where earlier models exposed the
secret, even though those complete cases remain failed.

Ten ordinary-fault combined cases fail the unchanged tail32-versus16 assertion;
wrap retains unexpected overflow, capacity tail544 differs from272, and the
historical illegal command still executes the forbidden completion and leaves RUN
set. No expectation was changed, waived or relabeled. The earlier stock-first
fixture with an unobservable parent-read result is also preserved externally and
is not qualification.

### Aligned-access diagnostic v1: independently accepted 13/13

A separately named fixture on the combined-v2 model reads complete event bytes.
For both denied reads and writes, aligned count 4 directly records DVA 0x3100;
count 8 records 0x3100/0x3104; count 16 records 0x3100/0x3104/0x3108/0x310c. Tails are
16/32/64 respectively. Those record addresses are now observed, rather than
inferred solely from cursor movement. The original 0x3000-based frozen transcripts
still contain only their original observations.

The source explanation is repeated four-byte access handling through unassigned
memory after denied translations. Actual inner translation callbacks were not
traced, and no universal hardware transaction boundary is established. Exact raw
encoding/model hypotheses remain separate from defined architectural fields.

Positive data and denial sentinels, adjacent guards, numerical-IOVA decoys,
independent observation liveness and whole event pages passed. Denied-read outputs
were observed as zero-filled in this run; that is not a universal error-output
requirement. Four-byte append, disabled-then-live, last-slot wrap and staged-full
suppression controls passed. Staging a reserved full slot is not a fill of all 255
usable entries; no STATUS clearing, overflow restart or MSI delivery was tested.

### Command-stop diagnostic v1: independently accepted 30/30

The separately built command-stop model completed its 30-case diagnostic.
Independent read-only reconstruction accepted the exact binary/source, all 30
runtime outcomes, execution identities and cleanup. It reconstructed 10,910 raw
qtest rows, 299 complete snapshots and 86 DMA operations; its 14,887 overlapping
checks are assertions, not extra cases. No independent rebuild or rerun occurred.

All eight default opcodes stop across live, disabled and staged-full logging,
including a nonzero offending head and the last-slot opcode 15 wrap placement.
Successful predecessor stores remain, later completion stores stay poisoned, and
CmdBufEn stays set while RUN clears. Repeated head/tail notifications, attempted
STATUS RUN writes, new work and moving head past the bad entry do not bypass the
stop. Unrelated permitted DMA stays live and separately denied writes preserve
memory while the command runner is stopped.

Genuine preexisting overflow, healthy store/no-store commands and two explicit
recovery forms pass. Both repaired-entry disable/enable and identical full-control
restart are observed. STATUS non-restart is not STATUS/W1C conformance. Partial
control writes, prefetched/reentrant hardware, recognized invalid commands, read
failures and general overflow recovery remain excluded or defective.

The two reused frozen controls retain their exact original bodies and assertions;
supplemental checks are conjunctive. The original illegal-command case now stops
on this separately identified model. The original eight-byte revoke/completion
case directly retains four code 2 event records at 0x3000/0x3004/0x3000/0x3004; this
is observation, not a new one-event-per-eight-byte requirement or general cache-hit
or requester-invalidation qualification. The other 15 historical cases were not
replayed, and every earlier failure remains unchanged.

Every historical guest retains the missing `kvmvapic.bin` warning. It did not
prevent completion, but these records are not presented as a clean firmware
fixture. Original failures, failed build/preparation attempts and old reports stay
unchanged when a later separately versioned diagnostic succeeds.

### Final-model composition: independently accepted 13/13 and 30/30

A new, separately supervised aligned-access run passed all 13 cases on final
command-stop binary
`e19fa6c25b2eb8198d79284d7f1b161359c96db7c6c9f1147810ef5004a565f4`.
Independent offline reconstruction accepted all 2,744 qtest request/reply pairs,
2,321 checks, 75 complete snapshots and 88 DMA operations. Every complete case
result and every raw qtest stream equals the accepted combined-v2 baseline.
All 43 retained pre-execution identities across this run and the separately
accepted 30-case command suite bind that same final binary. This closes the
bounded same-binary composition gate; it is not a newly executed 43-case aggregate,
full architectural conformance, Aurora native/kernel or physical qualification.

The new external harness changes only `PROFILE` and `BINARY_SHA256` from the
historical aligned-access fixture. Its SHA-256 is
`c9d211f2672755734af2944be10664b3612fe83a01368412e9b568cd57a7280e`;
the published fixture remains byte-identical at
`52f40383a50ddf437c9f240733af93f0722c3ae54092309f933ca658461dde80`
with its original combined-v2 runtime pin. The new report, terminal and independent
decision identities are in [qualification.json](../evidence/iommu-diagnostics/qualification.json).
The missing firmware warning, historical 17-case failures, model-only event
interpretations and all exclusions above remain unchanged.

## Developer use and remaining qualification

`make test-iommu-diagnostics` runs exact artifact/source controls and authored
RAM/register mocks in ordinary and optimized Python. It is compiler-free and
launches no emulator. Root `make test` includes it as a context-guarded prerequisite;
Meson includes both variants in `dev` and `full` without an aurorac dependency.
Meson's existing project setup still requires/probes its C++ compiler. The focused
Make/Python route needs no configured Meson tree or compiler. See the
[offline test scope](../tests/iommu/README.md).

The fixtures retain historical model pins. Future runtime is explicit, external,
model-specific and separately admitted; there is no default guest target, automatic
supervisor, binary download or hidden target substitution. A new build or path/plan
cannot borrow historical acceptance. The model README describes reconstruction,
build instructions and target preparation without embedding private paths.

Before merge, independently review this additive result update and complete the
[canonical final-source native gate](../AGENTS.md#workflow). Actual affected emulator
qualification remains separate; no old receipt qualifies the changed test
routing. Future model qualification still needs actual cache-hit observations,
requester/bus boundaries, excluded-path regressions, broader permissions, command
read/malformed-command corrections and controls, full-capacity/event-memory-error,
W1C/overflow recovery and IRQ/ATS work. Production DMA additionally needs its own
Aurora authority/publication/lifetime API, driver and physical-device acceptance.

Architecture references remain the existing [translation oracle](iommu-translation-oracle.md)
and [event/completion oracle](iommu-event-completion-oracle.md), based on AMD
48882-PUB rev3.10. They are bounded expectation sources, not production isolation
proofs or additional emulator execution.
