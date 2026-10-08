# Reconstructed readonly owned-byte spans — 2026-10-08

This is fresh implementation and qualification from accepted PR76, joined with
the additive accepted PR77 JSON profile. The earlier unpublished candidate was
lost in a filesystem rollback. Its source tree, binary identities and acceptance
receipts do not apply to this reconstruction. An explicitly unverified draft
source checkpoint was published before long validation to preserve progress.

The [contract](../compiler/READONLY-OWNED-SPANS.md) defines the fixed 56-byte
logical record, exact owner/root/field/parent provenance, const receiver-bound
results and limits. `ByteBuffer.bytes()` exposes logical length only. Generated
reads reuse existing binary, UTF-8 and JSON consumers without a payload copy.

## Fresh focused qualification

- Source gate: 22 admissions and 32 exact-diagnostic rejections per Python mode;
  independent reviewer adds eight admissions/11 rejections and array-only
  no-owner-import verification.
- Independent IR: 19 accepted/136 rejected owner-span cases; 964 general typed-IR
  tests; windows seven/25, short-circuit 13/35 and owned bytes 86/308. Those last
  three ran before a final ReturnSpan-only tightening and contain no ReturnSpan.
- Generated hosted owner/receiver suite: 11 programs, 14 native cases, four exact
  emitted bounds traps, one exact adapter bounds abort and eight rejections per
  Python mode. Copied-class arguments exercise the combined hidden-result ABI.
- Real kernel adapter hosted integration: standalone and receiver-bound source
  each pass three modes (fragmented, empty, failed) under normal Python,
  optimized Python and fatal host-C++ sanitizers. Physical pages 1/3/5, UTF-8 and
  binary crossing reads, descriptor/canary integrity, cleanup and failed-borrow
  metrics are observed; no guest execution is implied by these host tests.
- Direct hosted adapter: 54,062 checks/81 exact isolated traps normally and under
  fatal ASan/UBSan. Direct kernel adapter: 483,291 checks/247 exact isolated faults
  in both configurations. LeakSanitizer is excluded; generated assembly is not
  sanitizer-instrumented.

## Preserved failures and corrections

The deeper source-native fixture exposed a real frontend cleanup gap for copied
class parameters/locals on a span-result return. It now emits their ordinary
EndObject operations before exporting the view; the verifier remains strict and
requires all unrelated lifetimes ended. ReturnSpan additionally accepts only the
returned view and its exact ancestor chain, rejecting unrelated receiver views.

Fixture corrections retain their original failure logs: class declarations
needed semicolons; a reserved method name was renamed; failed-borrow observation
was separated from the compiler's emitted bounds trap because this operation
correctly terminates in the runtime adapter; the kernel null-helper call needed
an explicit namespace import; direct IR migrated former 16-byte spans and stale
diagnostics, with one accidentally changed test offset restored. No production
safety rejection was weakened to accept a bad program. Legacy array/parameter
temporary subspan-chain rejections remain intact while owner-derived temporary
chains gain explicit parent lifetimes.

The dependency-selected Meson core/bytes run passed all 37 selected tests, using
one compile job and one test worker. Both Python modes passed readonly span,
readonly-window, short-circuit, UTF-8 decode/encode/range/line and token consumers.
The orchestration wrapper initially constructed two wrong IR-native script names;
those invocations did not run. Original failures remain, and a separate corrected
replay passed all four normal/optimized IR-native gates. An in-flight wrapper
edit also produced a terminal shell error after all ordinary consumer results;
the individual successful receipts and corrected replay form the final composite,
not a claimed all-green wrapper exit.

Independent handwritten ABI gates passed 1,239 native boundary executions and ten
exact targeted mutation failures in each Python mode. They cover all 1–6 source
arities/span positions, full seven-word opaque records, scalar neighbors,
canaries, copies/windows, returned views, both hidden-result register modes,
current-register/saved-stack preservation and entry alignment. Array-only objects
have no owner-runtime references or undefined symbols. A first handwritten
alignment probe accidentally clobbered an argument; its original failure remains,
and the corrected flags-only probe passed fresh complete runs. The fixture's
initial scalar MethodCall metadata also required a test-only correction. The
Make/Meson ABI entrypoints are registered, with collision-free default artifacts.

Fresh build-only normal/runtime-span/owned-bytes UEFI image admissions and their
negative-image controls preceded all three actual public guest gates. The exact
owned-byte linked stack proof remains 1,072 + 512 fault reserve = 1,584 <= 15,360 bytes,
and matches the actual guest build. Runtime-span clean/fault/domain reuse and
owned-byte allocation/cleanup observations passed. Public special-profile gates
restored normal image artifacts byte-for-byte; the final normal boot passed.
The unchanged four-helper allowlist still rejects borrow_length. These are
existing-profile regressions, not a new guest-owned-span capability. Independent
review checked the source snapshot, linked receipt, runtime artifacts and normal
restoration identities.

These gates are bounded qualification, not full-native/full-emulator acceptance
or a general memory-safety proof.

## JSON join

The PR77 JSON library was replayed unchanged on the rebuilt span compiler, then
genuine owner-backed spans and ByteBuffer logical views passed 230 full-width
observations in both Python modes: 16 programs and 23 vectors cover valid large-
owner subwindows, >4096 input-limit precedence, nested coordinates and copied
reports after owner changes. Six live-borrow rejection controls and two exact
hosted bounds aborts passed per mode. The first recovered fixture run retained
an expected-diagnostic spelling mismatch; only that literal changed before fresh
passes. No JSON implementation or historical owned-evidence credit was used.
The unchanged full array profile also passed 2,111 cases/10,768 observations and
50 rejection controls under optimized Python with this rebuilt compiler.
Independent review accepted the joined runner and receipts; test-json and
Meson bytes/dev routes include it. Final runner SHA-256:
`9a170e5164e3396341dcfbe5398478cdf18446b28f244ec8382b6dfec73147b9`.

## Exact reconstructed inputs

Native/source consumer compiler SHA-256:
`fde0877e0b3326bc8e6e500bb6d3a8ed9daef814af4f46ae1d319da31d707fe3`.
The Meson compiler uses the same sources with its configured flags, SHA-256:
`5f5f86739ad791dfca6fa4bd8ceb532cc1adaf85fceedeb0177175a4efb5a6f2`.
GNU C++ 14.2.0, binutils 2.44, Python 3.12.14, Meson 1.12.1 and Ninja 1.13.2 are
recorded with receipts. Ruff 0.16.7 and clang-format 22.1.8 check touched host files;
the fresh compiler-owned formatter checks ByteBuffer's updated Aurora source.
Source/receipt manifests and original failures are retained outside the repository
for review and checkpoint delivery. The stable production sources are unchanged
since the final compiler and independent source review; later edits concern tests,
formatting, registration and these results. No old lost-source evidence is reused.
