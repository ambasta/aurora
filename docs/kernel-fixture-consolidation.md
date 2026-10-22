# Kernel fixture consolidation

The native-main cleanup reduces the source catalog from 233 canonical images
(196 UEFI, 37 BIOS) to 125 (105 UEFI, 20 BIOS). This is a source inventory, not
qualification of the restacked candidate or completion of the fewer-than-15
image target. Actual guest observations, original payload/page contracts,
emulator clocks and strict ordered receipt assertions remain distinct.

## Copied-input assertions moved to hosted tests

- PCI reserved: `kernel-pci.cpp` nonzero reserved-field loop. PCI overlap:
  independent bus and physical overlap rejection. PCI range: zero base remains
  structurally valid but the existing Q35 aperture-authority loop rejects it.
- ACPI bad-entry: `kernel-acpi.cpp` zero record-length rejection. Changed-header:
  the same checksum-repaired byte 10 mutation fails `same_header`. Duplicate:
  duplicate APIC ID and UID are independently rejected.
- IVRS pair: `kernel-uefi-ivrs.cpp` companion identity mismatch rejection. Alias:
  unsupported SELECT type 0x42. Reserved: unsupported IVMD block type 0x20 before
  its range can carry authority. Capability: copied capability byte 4 bit 1 is
  rejected. Range: type 7/four pages/WB at the aperture is rejected. Scope:
  agreeing requester 16→17 substitutions parse but cannot match the actual PCI
  inventory; this last positive-parse/negative-coverage assertion is retained.

No production parser or admission rule changes. Historical IVRS synthetic
transcript controls remain useful oracle tests, but the current native runner
no longer builds or launches those six policy-only images.

## Actual guest observations retained in shared images

The existing one-byte READY transport and fixture catalog are reused. The
reader accepts only the selected family's contiguous byte interval and fails
closed otherwise. No normal image contains a fixture reader or injection state.

- PCI 97–100: checksum propagation, cyclic bridge inventory, actual read-only
  ECAM write fault, revoked mapping fault. Admission follows ACPI window closure
  and precedes MCFG parsing/mapping. Three ordinary topology scenarios keep the
  normal PCI image.
- ACPI 101–105: disabled CPU topology success, checksum propagation, bad-source
  mapping denial, actual read-only and revoked window faults. Admission occurs
  at payload ACPI entry before firmware windows. Loader duplicate-root remains
  a separate earlier image; it never waits on this later selector.
- IVRS 106–107: actual write and revoked IOMMU-window faults. Admission follows
  ACPI closure and precedes PCI mapping. The pinned 60-second runner records the
  selector and checks the canonical build directory. Both exact linked fault
  instructions must exist in the shared image; the selected scenario still
  requires its own exact RIP, error code and address. Architectural default
  denial and cold read success remain separate selector-free images. Missing
  table uses read-image bytes with the original no-IOMMU machine configuration.
- IPC 108–115: fault/restart/scrub, cancellation, actual stale endpoint after
  revoke/rebind and CPL3 reentry, wrong root, kernel-origin trap, duplicate reply,
  late reply and transaction exhaustion. Selector admission precedes mailbox
  creation. Original clean/bounds payloads and one-page contracts are identical
  to normal IPC. The budget oracle's synthetic IPC projection is explicitly
  separate from real IPC selector admission.
- Budget 116–123: service fault, discovery/cache denial, actual page-table alias,
  pending interrupt, forged interrupt, wrong root and epoch mismatch. Admission
  precedes timer initialization. Original clean/bounds payloads and page limits
  remain unchanged. The one named forged-interrupt instruction is not cloned;
  ordinary budget contains no fixture selector. SMP uses normal budget bytes
  with its unchanged two-CPU guest configuration, because the former SMP macro
  changed no kernel code.

- Dispatch 124–133: service budget/fault and mixed cancellation, pending interrupt,
  cross-client and client-owner reply authority, stale generation, duplicate reply,
  full mailbox and wrong root. Admission precedes timer initialization. The two
  original client payloads and service payload retain their three-domain layout.
- User 134–147: retirement while pending, request/completion budget, bounds and
  overflow, pending interrupt, role/phase/transaction/epoch/root authority and
  stale grant. Admission precedes timer initialization; stale endpoint substitution
  remains at the original first-client request point. Normal non-resuming and
  resumable compositions remain distinct and selector-free.

The original 30-second generic guest deadlines and 60-second IVRS deadline are
unchanged. New grouped artifacts still require all original stack/page/metadata
checks; grouping does not permit larger admitted user images.

## Copied policy negatives with hosted equivalents

Thirteen guest-local copied input/result mutation profiles are replaced by
hosted producer/production-decoder cases. Ordinary decisions, live-state commit
ordering and real machine scenarios remain unchanged.

- IPC request/cancel input: `kernel-ipc-transition-native.py` includes the same
  maximum-width phase. Decoder vectors cover zero/reserved-bit outputs against
  every original context. `kernel-ipc-transition-adapter.cpp` rejection loops
  preserve the whole object, registry and generation across adapter lifecycles.
- Dispatch cursor/mask/output: `kernel-round-robin-native.py` covers maximum-width
  copied inputs and zero/bit-63 results. `kernel-round-robin-adapter.cpp` rejection
  controls preserve every Dispatcher byte; peer isolation and stale replies
  remain actual guests.
- User disposal input/output: `kernel-client-disposal-native.py` covers maximum
  phase and reserved-bit outputs. `kernel-client-disposal-adapter.cpp` preserves
  dispatcher, registry and generation on denial. Retirement, scrub,
  reincarnation, peer-state preservation and stale-grant guests remain.
- Budget zero/counts/wide/output: `kernel-budget-native.cpp` composes the genuine
  producer and production decoder for original first-tick contexts 3 and 128,
  including exact copied-input mutations and the reserved output bit. Interrupt,
  context and cleanup guests remain. No-APIC stays in the guest because topology
  discovery and CPUID-before-MMIO are not covered by the hosted predicate alone.

Historical synthetic transcript cases remain rejection controls, not currently
admitted boot profiles. Public launch lists and the clock catalog reject the
retired modes. `tests/meson-kernel-images.py` reconstructs the original recipe
records and checks their unchanged frozen digest, separately from current routing.

## Other same-payload groups

- BIOS retains selector-free ordinary and scheduling baselines plus two bounded
  fixture images for nineteen scenarios, reducing 37 producers to 20. Distinct
  original payload/entry triples, unsigned baseline, early EDD/protection failures
  and the separate console supervisor/bridge are not combined.
- Program selectors 167–173 preserve request/service/completion fault and budget
  mutations and pending IRQ injection at their original sites, before timer
  initialization. Snapshot selectors 174–180 preserve fault/cancel recovery,
  stale/revoked endpoint rejection and producer selector/quota/page failures,
  admitted before publication. Both retain their original payload pairs, entry
  assembly, page limits and selector-free baselines.
- Plain runtime selectors 181–183 cover root, kernel-trap and entry-stack behavior;
  pin selectors 184–187 cover cancel/fault/stale/exhaustion; table selectors
  188–191 cover readback/reject/exhaustion/quarantine. These are three distinct
  supervisor compositions. Admission follows handoff/page-table/pool validation
  and architecture installation, before creating or entering any domain.
- Only the pin fixture compiles the pin uncertainty-testing API, used solely by
  selected pin-fault. The table fixture rejects that API; its first-page scrub
  refusal is armed only after the bounds return. Both quarantine paths retain
  two pages and the original create(1), create(0), service slot-1 restart order.

No payload bank or loader extension is introduced. Grouping does not widen
user-image, stack or page admission, and normal images remain selector-free.
The console deadline remains 180 seconds, generic guests 30 seconds and IVRS
60 seconds. Unknown/malformed selectors and missing readiness fail closed.

## Limits and qualification

The 105 UEFI producers comprise 64 user-bearing images across 50 exact generated
user tuples and 41 firmware/kernel-only images. Tuples are not boot ABIs or a
mathematical lower bound. Repeated tuples include ordinary versus fixture
baselines, no-APIC discovery and distinct plain/pin/table supervisors.

One-page/multipage, owned-text/call, resume assembly, console-region and early
firmware admission are real composition boundaries. BAR alias is a live PTE
mutation; IPC stale executes actual CPL3 rejection. Neither can be retired using
only parser or Mailbox-policy tests. Selecting distinct original payloads would
require a bank in the generator/loader with unchanged descriptors and admission;
that architecture is not implemented. At least 27 baseline compositions remain
separately named, so retaining them untouched already exceeds 14 producers.
This is a current design limit, not proof that fewer than 15 is impossible.

The original staged changes and focused receipts are preserved in the Git
history of stacked cleanup checkpoint `ffcfe8e29901db2647dd274f9bb80321ee3c106b`.
Those earlier image builds, representative boots and transcript controls do not
qualify this independent native-main restack. Current source still requires the
pinned GCC 16 complete `full`, relevant exhaustive checks, normal BIOS/UEFI
smokes, every affected real emulator gate and independent review. Missing tools,
firmware/trace gates or unavailable historical artifacts remain explicit gaps.
Whole-suite cost comparisons require matching workload, source/tool identities
and actual concurrency, as specified in the PR template; source image counts
alone are not measured build or execution savings.
