# Verifier resource history and compact-fact candidate

Sections before the isolated M015 candidate describe the historical M003 checkpoint. Their future-scope wording is retained in that historical context; current candidate claims appear below.

## Reproduced failure

An extra ASan+UBSan compiler run hit the existing five-second test-command timeout on the supported 4096-element array case. There was no address/undefined-behavior sanitizer diagnostic before the timeout. The failed receipt is retained in [`docs/evidence/milestone-003/compiler-sanitizers.log`](https://github.com/ambasta/aurora/blob/2b1776f13cd02df6588f9e3213815f13c28a71e0/docs/evidence/milestone-003/compiler-sanitizers.log) rather than replaced with a passing result.

Investigation showed a real resource defect, not just instrumentation overhead: the first typed-IR verifier retained complete operand-stack and initialized-slot-set snapshots at every instruction. A straight-line array initializer grows and shrinks these structures over thousands of instructions, retaining quadratic history. Release compilation peaked around 4.3 GiB; instrumentation magnified the cost enough to exceed the unchanged timeout.

## Exact same-input, same-flags sanitizer comparison

Environment: x86-64 Linux; `g++ (Debian 14.2.0-19) 14.2.0`.

Both binaries were built with:

```sh
g++ -std=c++23 -O1 -g -fsanitize=address,undefined \
    -fno-omit-frame-pointer -Wall -Wextra -Wpedantic -Werror \
    compiler/main.cpp -o COMPILER
```

The same source input was supplied to both compiler binaries, with the same `-o` assembly output operation. Python `time.monotonic()` measured elapsed time and `os.wait4()` supplied that compiler process's own peak RSS and CPU usage; memory values below are Linux KiB. Both runs used `ASAN_OPTIONS=detect_leaks=0` and exited zero without diagnostics.

| Version | Elapsed seconds | Peak RSS KiB | User seconds | System seconds |
| --- | ---: | ---: | ---: | ---: |
| Per-instruction snapshots | 14.6024 | 6,054,528 | 11.581846 | 3.015268 |
| Basic-block-entry snapshots | 0.0809 | 46,448 | 0.065564 | 0.015181 |

Binary SHA-256 values:

- Before: `eca41bff079801c02c39af4395fcc77766409f0cc365b1f6e24e5622411e3b9e`
- After: `f336d8269b9f4de441e3b39a163b6d4e1721ea8b2792a0ae0e1902bc1330bd91`
- Input: `3d657ad1858edba2998703b8d24a244eeef722fae7f1a26df614817411c9932e`

The input is exactly reproducible without a trailing newline:

```python
from pathlib import Path
values = ','.join('1' for _ in range(4096))
Path('array4096.au').write_text(
    'module test; auto test() -> i64 { const array<i64,4096> a={'
    + values + '}; return a[4095]+41; }'
)
```

A separate release measurement went from 2.661 seconds / 4,468,364 KiB to below 0.051 seconds / 10,764 KiB (the latter timing used 50 ms polling, so it is only a coarse upper bound). Independent synchronous release measurement reported 0.011 seconds / 10,768 KiB after the fix. These are observations on this machine, not portable performance promises.

LeakSanitizer itself is disabled because this executor's tracing environment causes its documented ptrace incompatibility. An initial unrestricted measurement reached exit and then produced that LeakSanitizer fatal-environment message; it was not a leak finding. AddressSanitizer and UndefinedBehaviorSanitizer remained enabled for the reported comparison and test gate. The pre-fix binary and original failed receipt were preserved.

## Repair and permanent tests

The worklist now retains abstract states only at basic-block entries: function entry, labels and conditional fallthrough. It walks each straight-line block with one mutable state and records per-instruction reachability separately. Branch/loop joins still intersect initialization facts and merge current-value provenance; bounds tokens, structural legality, parameter prefixes and unreachable-code policy are unchanged.

The direct IR suite includes a portable resource regression for 4096 elements. Instead of loosening timeouts or setting a fragile machine-specific latency threshold, it measures retained-state snapshots/facts and peak operand depth. Observed: one retained entry snapshot, 4096 peak operand values, zero retained entry-value facts for the straight-line initializer. The test permits generous small snapshot/fact bounds but rejects retention of the growing per-instruction history.

Additional cases test an initialization fact removed by a later predecessor, a checked-index token lost on a loop backedge, and identical checked tokens safely joined from both branches. All 203 existing source tests and 46 direct IR tests pass. A stronger nonrecovering ASan+UBSan compiler also passed all 203 source tests under the existing five-second timeout. Final aggregate/oracle/kernel receipts are recorded separately by the integration owner.

## Remaining limitation

This fixes the demonstrated quadratic straight-line history. It does not make the entire verifier linear or provide a compiler-wide resource bound. Initialized-slot sets are still copied at block entries, so retained memory grows with block count times live slot facts.

Independent release measurements for a 4096-element initialized array followed by branches:

- 0 branches: 0.011 seconds, 10,768 KiB peak RSS
- 64 if/else branches: 0.087 seconds, 48,512 KiB
- 128 if/else branches: 0.153 seconds, 85,988 KiB

Compact fact representations and explicit compiler-wide resource budgets remain future hardening. The current regression is evidence for this particular repair, not a general denial-of-service or complexity proof.


## Isolated M015-based compact-fact candidate

This section describes a separate candidate derived from the verified M015
compiler, not the interrupted mutable-byte-view candidate. The historical results
above remain unchanged. Only the two local scalar initialization collections and
their join operations change representation. No language grammar, native ABI,
capability policy or supported-program cap changes.

InitializationSlotUniverse owns an immutable sorted mapping of validated scalar
slot offsets to dense indices. Existing frame limits bound the universe to at
most 65,536 slots. Negative, oversized, duplicate and unknown identifiers cannot
become unchecked bit indices. InitializationFacts stores exactly
ceil(universe_size/64) uint64 words, maintains exact set cardinality, and preserves
unused high bits as zero. AND implements must-initialized intersection; OR
implements may-initialized union. Cross-domain operations preserve set meaning
and reject unknown insertions before partial mutation.

The standalone author model passes 7,405,472 comparisons with std::set. Independent
fatal ASan/UBSan modeling passes 37,126,294 checks across every size 0..257, word tails,
large universes, errors, joins and copy/move/default states. The release IR suite
passes 956 cases, retaining all 950 baseline cases and adding six payload metrics.
For 65,536 slots and 7 retained entries, both initialization collections use 114,688
logical payload bytes while logical retained facts count 786,432. A 4096-element
straight-line initializer retains 1 entry, 0 facts and 1024 payload bytes.

### Dense readonly measurements

The readonly-only source generator uses byte arrays, independent copies, shared
span calls and repeated comparisons. It does not require mutable views. Before
and after use the same C++23/O2/strict-warning toolchain. Each compiler process is
bounded to 256 MiB address space, CPU 4/5 seconds, wall 10 seconds, regular-file 8 MiB and
zero core size. RSS is Linux wait4 ru_maxrss, not an estimate from logical words.
One run measured:

| Capacity | Repeated blocks | Baseline RSS KiB | Candidate RSS KiB |
|---:|---:|---:|---:|
|64|16|7,012|6,868|
|512|16|24,256|10,304|
|4096|0|59,292|56,336|
|4096|4|88,044|56,824|
|4096|8|116,140|57,220|
|4096|16|172,400|58,008|
|4096|64|explicit-cap failure|62,988|
|4096|96|explicit-cap failure|66,364|

All jointly successful compilations emitted identical assembly. Under a separately
recorded 512 MiB cap, the independent reviewer compiled 64 blocks in both versions:
510,588 KiB/1.477s baseline versus62,976 KiB/0.456s candidate, with identical assembly.
These are bounded observations, not a target-runtime or equivalent-C benchmark.

The measurement driver now requires candidate success, no diagnostics, an emitted
artifact and exact native u64 result 42 for every valid workload, including when
the baseline is resource-limited. Baseline failures remain explicit. Always-fail
and wrong-output stub controls verify that a rejecting or incorrect compiler
cannot earn a PASS. The earlier joint-success-only check was insufficient and
its original receipts remain separate from corrected-driver receipts.

### Sparse counterexamples and remaining scope

Dense storage depends on the total declared universe, not the number of currently
initialized slots. The independent valid-source case with 2,048 empty branch
pairs before four 4096-byte arrays increases RSS 189,692→210,048KiB (~10.7%), while
both emit identical assembly. Recorded wall times were 0.183→0.162s; this single
run establishes no universal speed claim. The IR-only all-unused 65,536-slot case
with 1,537 entries increases RSS 26,464→51,404KiB and logical payload 25,182,208 bytes,
even though both initialization fact sets remain empty. The sparse source run used a 512 MiB address cap; the IR-only run used 256 MiB. Both used CPU 4/5 seconds, wall 10 seconds, regular-file 8 MiB and core 0. These tradeoffs are
mandatory acceptance disclosures; no hybrid redesign is hidden in this patch.

Other sets/maps, operand stacks, state counts, AST and allocator overhead still
scale with input. Existing file/frame caps are not a practical compiler-wide
memory/time guarantee. This patch removes one measured dense-fact allocation
multiplier; it does not make bad_alloc an adequate general resource policy.

### Gate status

Full release compiler target passed after adding the new header to the exhaustive
probe fixture's copied dependencies. The failed missing-header receipt remains.
Instrumented compiler source/native suites and the fact model passed; the initial
large instrumented IR-test build was SIGKILLed in cc1plus, with cause unestablished.
The identical-flags serialized retry then reached its explicit2GiB address cap,
returning1 with a normal allocation diagnostic after48.38s at1,966,388KiB RSS.
No signal or wall-deadline kill occurred. The original SIGKILL cause is not inferred
from this deliberately capped failure.

An explicitly approved IR-test-only retry now uses -g1 rather than -g, retaining
-O1, address/undefined-behavior sanitizers, fatal sanitizer errors and frame
pointers. Compiler, standalone fact tests and I/O tests keep full -g metadata.
The IR compile alone has the same2GiB address, CPU120/130s, wall180s, regular-file
512MiB/core0 limits; runtime sanitizer executions do not inherit its address cap.
The complete sanitizer target then passed exit0. The bounded -g1 IR build took
67.21s at1,662,392KiB peak RSS, below the2GiB cap, with no signal/deadline kill.
All956 IR, native/exhaustive, module/depth and host-I/O runtime gates actually ran
and passed. Failed attempts remain preserved; they were not relabeled as passes.
Independent source/model/storage review passed with the sparse tradeoff explicitly
retained. Isolated compiler gates are complete; main integration and combined
kernel milestone acceptance remain separate parent-owned steps.


### Main integration follow-through

The exact reviewed nine-file implementation/test/diagnostic delta is integrated.
All targeted pre-edit baseline identities were checked; newer completeness-matrix
content was retained while its resource section was appended. All21 executable
source/test inputs match the reviewed manifest, and a fresh main release build
matches14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980.
The complete main release target and an affected integrated sanitizer replay
passed. The latter reused exact-source instrumented compiler/test binaries,
reran source/model/IR/native/module/I/O checks, and rechecked unchanged inputs.
No new heavy instrumented build was hidden in that replay.

Current receipts, all failed attempts, exact flags/limits and independent review
are under [docs/evidence/milestone-016/compiler-facts](https://github.com/ambasta/aurora/tree/2b1776f13cd02df6588f9e3213815f13c28a71e0/docs/evidence/milestone-016/compiler-facts). Generated independent binary,
assembly and raw-output artifacts are preserved outside distributed source in a
full local archive; its hash and every omission are explicit in
independent-distribution.json. Historical manifests remain unchanged. Combined
milestone acceptance and final kernel gates remain separate.
