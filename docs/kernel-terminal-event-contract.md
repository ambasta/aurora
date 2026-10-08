# Copied terminal-event classification

## Dependency and acceptance gate

The existing `ProgramContract::classify` must depend on the genuine Aurora
producer before it returns a terminal event. No fallback accepts an event when
the producer refuses. The observable gates are independent finite/full-width
producer and decoder tables, real `ProgramRun` refusal/no-mutation controls,
existing authority regressions, fatal hosted sanitizers and exact linked stack
admission before any changed BIOS or UEFI guest executes.

## Copied relation

`kernel.terminal_event` receives three u64 words: interrupt vector, a five-bit
matched-site mask (return, bounds, overflow, division-zero, shift-count), and a
canonical 0/1 fact that the stack equals its expected top. Vector >255, mask >31,
multiple matched sites, or a noncanonical boolean refuse. Zero mask refuses.
Vector 129 at the return site and stack top returns `returned`. Vector 6 at
exactly one of the four fault sites returns that fault regardless of stack-top
fact. Every other combination refuses.

The private scalar wrapper explicitly maps nominal enum results to wire words
0 rejected, 1 returned, 2 bounds, 3 overflow, 4 division-zero, 5 shift-count.
No enum ordinal is a wire contract. The independent C++ decoder checks each
positive proposed event against the original copied facts and rejects all
other words, including high bits. It never supplies success for native refusal.

## Trusted boundary

The image/layout validity checks, exact address comparisons, absent-site rules,
frame bounds/alignment, selectors, flags and error word remain C++. Existing
active-run, active-domain/root, role, phase, timer and authenticated continuation
checks remain unchanged in their callers. No address, frame, handle, capability,
image, payload or mutable state crosses into this policy. `ProgramRun` commits
its event/value and clears its active contract only after accepted classification.

The shared classifier is also called by BIOS `IntegerContext::terminal` and
UEFI `ServiceContext::terminal`; these paths must be included in new linked
stack analysis, not just direct `ProgramRun::accept`. Generated Aurora code is
not instrumented by hosted C++ sanitizers.

## Roots and controls

The normal UEFI root, normal BIOS root and BIOS console root export the copied
wrapper. The UEFI console shares that source root but does not execute the
user-runtime classifier. The separate owned-byte root has no dependency.
Previously compiler-free host classifier routes now link genuine generated
code and join the controlled shared-compiler workflow.

BIOS `--program-terminal-input`/`--program-terminal-output` and UEFI
`runtime-terminal-input`/`runtime-terminal-output` alter only a local copied
vector or the real returned word. The invalid vector is UINT64_MAX; the output
control uses a volatile high reserved bit after the genuine call. Decoding uses
original facts. The normal authenticated clean return must fail at the existing
site-authority/fatal boundary with no accepted event or supervisor continuation.
Both new UEFI modes retain the original runtime clock, not timed-service clocks.

No compiler semantics, authority widening, source-language foreign ABI,
performance parity, complete native aggregate, physical-hardware support or
self-hosting is claimed. Selected guest and host qualification is recorded below.

## Focused qualification — 2026-10-08

The final integration preserves accepted PR91, commit
`1024f40ebe87bfdbd6ca04820a9ec4651da9922c`, tree
`a40fc7c6a8456d0b940cbe96e292a13f90c9de80`, including the formatter/field
repairs and direct copied-constructor returns. The freshly built joined compiler
matches the image/test compiler SHA256
`f462041ab5b91f60723c8fc752e64ba38ba0f9e4bf95ed69810350a9e5ae2912`.

- Genuine ordinary and fatal hosted ASan/UBSan gates passed: 16,384 finite
  contexts, 39,688 producer vectors, 159,251 decoder vectors and 3,750 actual
  `ProgramRun` proposal/retry cases. Refusal preserves the entire run object;
  genuine retry succeeds. Invalid origin/error/contract controls never consult
  the producer. Generated Aurora assembly is not sanitizer-instrumented, and
  leak checking is disabled.
- Genuine-linked kernel, division, unsigned, UEFI runtime, service-budget,
  dispatcher and user-phase host routes passed, along with ordinary/optimized
  clock controls, 76 compiler/Make controls and the pinned public
  `make -j1 test-terminal-event` route.
- The complete final integrated Meson partition passed: all 41 dev and 12 slow
  tests, after an explicit one-job build and serial no-rebuild test runs.
- Fresh independent stack/PIC/PE/mapping admission covered 48 exact snapshots.
  The terminal producer requires 112 bytes including its incoming call; the
  largest checked supervisor initialization path is 14,688/16,384 bytes,
  exception path 2,119/16,384, and enabled supervisor IRQ path 3,447 bytes.
  Actual linked pushes, switch tables, IF windows and hostile call/result
  dependencies were checked; earlier stack margins were not substituted.
- All 46 selected admitted guests passed: 38 UEFI and eight BIOS. This includes
  both new producer-denial modes on both firmware paths, BIOS scheduler,
  division-zero and shift-count faults, selected runtime/IPC/budget/dispatcher
  paths and all 19 existing user-lifecycle modes. Both actual normal boots ran
  last, UEFI then BIOS; normal image bytes were restored after each run.

The guest runner binds source, images, metadata, execution-tool/firmware/library
identities, actual environment selections and its own reviewed hash. It rejects
alternate selections and preloads, uses production clocks and validators, and
never rebuilds during the admitted run. Raw logs, commands, receipts, source
inventories and independent reviews are retained in the qualification archive.
BIOS/UEFI console snapshots are link-only; interactive-console qualification is
not claimed here.

Evidence nuance: the BIOS builder reuses one entry-object path across three
user links. The reviewer reconstructed the scheduled-clean context-probe entry
from exact source/tool inputs and checked it against the actual linked ELF;
that reconstruction is distinguished from original retained build inputs.
Initial stale BIOS root and clock inventories failed closed and were corrected
without weakening authority or old mode coverage. The clock failure logs and
captured BIOS diagnostic excerpt are retained; the original complete failed
BIOS build log was overwritten during development. The sole post-build upstream
status-document update was explicitly rebound with compiled inputs unchanged.

This is focused native and selected-emulator qualification. It is not a fresh
root `make test`, an all-mode sweep, physical-hardware qualification, a nested
fault/NMI/SMP proof, a complete kernel rewrite or a performance-parity claim.
Full `make test` remains required before releases.
