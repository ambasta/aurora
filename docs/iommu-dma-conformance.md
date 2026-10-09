# Bounded emulated DMA diagnostics

This is an emulator-only diagnostic model and reusable test material. It does not
implement Aurora production DMA, grant device authority, activate a physical
requester or replace the project's default QEMU runtime. Full IOMMU conformance,
physical isolation/drain/reclamation and AMD hardware support remain unqualified.

The diagnostic integration landed in PR101 after its exact source passed the
then-required 61 dev and 30 slow tests. The unchanged historical emulator results
below retain their original model/fixture scope. New compiler and kernel changes
require current-source canonical Meson `full` on both recorded toolchains and
applicable image/emulator gates; earlier receipts do not transfer qualification.

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
not stop or reset an unsuitable firmware controller to force admission.

The denial image passes independent linked-image and stack review: 11,776 bytes
including its exception reserve fit the 15,360-byte admission cap within the
unchanged 16 KiB stack. The first rejected stack attempt remains retained; the
Event-only build uses fixed outgoing argument slots. The image invokes the real
Aurora loop after a finite producer batch and preserves all raw ring slots and
protected data before and after intake. Command-only diagnostics leave EDU bus
mastering disabled. Overflow at initial admission remains a pre-entry refusal.
No new Aurora guest has run yet; hosted and image checks do not establish live
transport behavior, firmware quiescence, physical isolation or completion.

Build-only modes are `iommu-event-denial`, `iommu-event-success`,
`iommu-event-overflow` and `iommu-event-command-error`, selected through
`UEFI_MODE` for `scripts/kernel-uefi-build.sh`. Only the denial image currently has
linked-image qualification. Execution requires the exact retained model, verified
split firmware, an admitted raw ESP and a separately reviewed supervised plan.
The FAT helper uses pinned mtools, reconstructs a second identical image and
checks every allocation and loader byte; each guest receives a fresh writable
copy. Serial/QMP evidence and verified process cleanup are required. No mapping
API, invalidation completion, page release, concurrent producer or physical-device
support follows. Historical NVMe/IVRS policies and guest results stay separate.

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

New compiler/kernel integration requires final-source GCC 14 and GCC 16 Meson
`full`, normal BIOS/UEFI images and relevant emulator qualification per AGENTS.md.
No historical receipt qualifies changed code or routing. Future model qualification still needs actual cache-hit observations,
requester/bus boundaries, excluded-path regressions, broader permissions, command
read/malformed-command corrections and controls, full-capacity/event-memory-error,
W1C/overflow recovery and IRQ/ATS work. Production DMA additionally needs its own
Aurora authority/publication/lifetime API, driver and physical-device acceptance.

Architecture references remain the existing [translation oracle](iommu-translation-oracle.md)
and [event/completion oracle](iommu-event-completion-oracle.md), based on AMD
48882-PUB rev3.10. They are bounded expectation sources, not production isolation
proofs or additional emulator execution.
