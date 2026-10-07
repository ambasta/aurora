# Failure-safe owned-byte resize — 2026-10-07

The focused hosted checks below passed. The [contract](../compiler/OWNED-BYTES.md#failure-safe-replacement-resize)
extends the existing hosted runtime owner and direct private owning-class fields.
The integration base is merged PR73 main
`8ea36beaed85961e5d5d982908c83fcacb3f96a2`, tree
`e99d40d23eb6cff68af7c8e9a8df450df84ed9cd` (805 files).
The earlier PR69-based resize candidate had source review and compile-only
admission, but no native qualification; its original evidence remains separate.

## Reviewed scope and results

Independent source review accepted the compiler/IR/backend integration and hosted
adapter with its host tests. The new `BytesResize` operation preserves existing
PR73 field selectors, mutable-root and borrowed-receiver checks. Length evaluation
must leave the receiver and containing owner live. RamSectorDevice exposes no
resize method; its whole-sector invariant and private backing remain unchanged.

The warning-clean current-source compiler is SHA256
`6756e670ccfd2dc1d94a48672915852697ab2ec08df0c09da471e37491f8afc5`.
Both Python modes passed compile-only admission: 24 byte-owner programs/38
rejections and 26 owning-class programs/42 rejections. All 50 accepted programs
retain assembly identity after formatting, with second-pass idempotence. The
existing PR73 formatting-only executable is reused; this does not qualify its
old semantic-lint path for new resize syntax. All 167 previously qualified PR73
storage-consumer assemblies and 29 example assemblies remain exactly unchanged.

The host adapter passed 53,969 checks and 68 isolated fail-stop traps normally
and under fatal ASan/UBSan. LeakSanitizer is disabled. Source-reviewed coverage
includes complete prefix/extension byte checks across the tested transitions, final logical quota,
allocation failures, unchanged same-size metrics, stale/forged descriptors,
registry positions and final allocation identity exhaustion. The native host
callbacks deliberately observe old-plus-new staging; logical quota is not a
physical peak-memory guarantee.

The true generated native byte-owner runner passed 56 cases, seven exact bounds
traps and 38 source rejections in each Python mode. The owning-class runner passed
49 native cases, four exact bounds traps and 42 source rejections in each mode.
These use the real hosted adapter, verify normal cleanup and allocation/release
counts, and cover failed/no-op/successful transitions, private first/second fields,
const and consumed roots, post-resize moves, saved scalar expressions and RAM-sector
invalid-backing behavior. Native assertions are summarized by each runner; their
source/assembly/executable artifacts are retained, but not every invocation's raw
stdout is independently preserved.

Independent direct IR passed 86 accepted/308 rejected byte-owner cases and
47 accepted/165 rejected owning-class cases. Both modes of the handwritten ABI
oracle passed 15 literal-layout boundary cases and four deliberately rejected
mutants. Exact descriptor offsets, both payload prefixes, every extension byte,
sibling fields, scalar/padding canaries, odd/even operand stacks, helper alignment,
callee-saved registers and reverse cleanup are checked. The ABI observations and
mutant diagnostics are retained individually.

Selected existing dependencies passed in optimized Python: 74 class-constructor/
method checks, 59 copied-class boundary checks, 50 owned-field mutation cases with
32 rejections/two exact traps, 91 readonly-span native cases including 25 traps with
69 rejection fixtures, and 360 short-circuit executions/80 rejection checks/15
exact traps. Pinned host-source formatting passes. No unrelated full suite or guest
run supplies credit for this checkpoint.

## Reproducible commands and tool scope

The source compiler was built once using the existing compiler Makefile with
`g++ -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror`. The focused source/native
runners are `tests/compiler/owned_bytes.py` and `owning_classes.py`; the latter's
`--compile-only` mode does not link or execute generated programs. Direct helpers
are built from `owned_bytes_ir.cpp` and `owning_classes_ir.cpp` with the same C++
flags and compiler include path; `owning_classes_abi.py HELPER --work-dir DIR`
runs the existing literal-layout harness. Both Python modes are `python3 -B` and
`python3 -B -O`.

The host normal gate compiles `runtime/hosted_bytes.cpp` with
`tests/compiler/owned_bytes_host.cpp` and `-DAURORA_HOSTED_BYTES_TESTING`.
The separate sanitizer build uses `-O1 -g -fsanitize=address,undefined
-fno-sanitize-recover=all -fno-omit-frame-pointer`. Runtime options are
`ASAN_OPTIONS=abort_on_error=1:halt_on_error=1:detect_leaks=0` and
`UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`. Each wrapper retains exact
commands, start/finish timestamps, logs and actual terminal statuses, with bounded
outputs and timeouts. The host is Linux x86-64, GCC 14.2.0, Python 3.12.14 and GNU
binutils 2.44; style tools are Ruff 0.16.7 and clang-format 22.1.8.

## Retained failures and limits

The first new owning-class admission run reached the resize tests but failed in a
RAM-device guard fixture whose imports did not expose the required storage type
graph. Only that fixture's imports changed; the original failure and successful
normal/optimized corrected runs are retained. The older bool-result rejection
uses a distinct `bad_size` binding so shadowing cannot mask its intended error.

The first new ABI run passed existing cases, then the new resize-first padding
oracle rejected its own fixture setup: an unconditional authority-prefix write
had overwritten borrowed-receiver padding before entry. The correction skips that
write for borrowed receiver modes and asserts initial padding before calling any
generated code. All post-call padding checks remain unchanged. Independent source
review accepted the fixture-only delta; the original failing executable/log are
preserved and fresh complete normal/optimized ABI replays passed. Production
compiler/runtime sources did not change after their initial successful build.

Independent source-review receipts and retained-evidence review are recorded
separately alongside the exact source/evidence manifests. The earlier source-only
checkpoint and both retained fixture failures are not reported as native passes.
Generated Aurora assembly is not sanitizer-instrumented. No leak proof, full
native aggregate, performance comparison, kernel integration, physical hardware
qualification or language-wide memory-safety result is claimed.
