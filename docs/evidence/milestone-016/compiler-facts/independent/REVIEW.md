# Independent review: dense scalar initialization facts

Date: 2026-10-03 UTC. Scope: representation-only compiler resource change copied from verified M015. No mutable-span candidate was inspected or resumed. No hardware, emulator, shared/main build, publication or installation was performed. All reviewer outputs are private to `/tmp/aurora-facts-independent-review`.

## Result

No compiler correctness or admission-policy defect found in the reviewed runtime change. The resource measurement driver had a false-success defect: a candidate that rejected every valid input still produced a PASS. The owner repaired it; an independent `/bin/false` negative control now exits 1 and retains the complete failed pair. Sparse initialization states can consume **more** memory with dense bitsets. That measured tradeoff is a mandatory qualification of the favorable dense-workload result, not an instruction to add a new language cap or rush an adaptive redesign.

## Source identity and implementation review

Baseline compiler sources were checked byte-for-byte against `baseline-m015.json` before being copied privately. The complete baseline/candidate compiler source hashes are in `evidence/source-sha256.json`.

- Baseline release binary SHA-256: `2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`
- Candidate release binary SHA-256: `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`
- New initialization_facts.hpp: `d36bd9d835def4b679001facbb7f68627296df8ab4c0c90119e506275b4e6d80`
- Changed ir_verify.hpp: `ded7d28ba24104c82a69fd9922c13caf972ac910df66c129c2e3fa031d05e32b`

Only the `initialized` and `maybeInitialized` scalar-offset sets change representation. Receiver/class/lifetime sets and all language syntax, semantic analysis, IR instruction forms and backend code remain unchanged. Must facts still meet by intersection; may facts still join by union. Slot accesses are validated before new facts are inserted. Unknown membership/removal remains false/zero, while unknown insertion fails instead of losing evidence.

### Bounds and storage arithmetic

Before constructing the universe, existing checks require a 0..65,536-byte, 16-byte-aligned frame and positive scalar slots that lie inside the frame with disjoint occupied bytes. Every slot consumes at least one byte, so the number of scalar slots N is already at most 65,536. This follows from existing validation, not a new program-admission limit.

The word formula `N / 64 + (N % 64 != 0)` avoids the overflowing `N + 63` idiom. It yields at most 1,024 words, 8,192 bytes per set and 16,384 bytes for the two sets in a retained state. Allocation count is also checked against size_t byte arithmetic and vector max_size. Checked dense indices, never raw frame offsets, determine the word index and shift, so shifts stay 0..63. Initial zero words, checked insert/remove, AND/OR, copies and moves preserve zero unused tail bits.

The immutable sorted universe rejects duplicates/out-of-frame values and is shared with ownership across snapshots. Copy assignment preserves value semantics; moves leave an explicitly empty insertion-less source; cross-universe operations preserve set meaning and failed union checks all incoming facts before mutation. In normal verifier integration all states use the same shared universe.

The new retained metric counts **only both word payloads at retained block entries**. It excludes the shared offset universe (up to 65,536 ints), vector/shared-pointer/object/allocator overhead, other state facts, operand stacks, transient current/merge states, code/AST/assembly storage and all other process memory. It is not RSS and does not establish a global compiler or target-stack resource bound. The representation costs O(B*ceil(N/64)) retained words for B snapshots even when live facts are empty; this can be worse than empty/sparse sets.

## Independent validation

Tools: GNU g++ (Debian 14.2.0-19) 14.2.0, Python 3.12.14, x86-64 Linux 6.18.44 with glibc 2.41.

Both release compilers were rebuilt independently with `g++ -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror`, under 180-second build timeouts. The resulting candidate binary exactly matches the owner's binary.

1. Independent model `independent-facts.cpp`, built with `-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer`, passes 37,126,294 checks against std::set. Every count 0..257 exercises every partial-word boundary; randomized operations use seed 0xa11ce; 10,000 independently generated unequal-domain pairs cover meet, join, equality and failed-union atomicity. Additional tests cover zero/default/moved-from sets, lifetime, bounds/errors, max 65,535/65,536 slots, copies and moves. No sanitizer diagnostic. Fatal sanitizer rerun uses `ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 UBSAN_OPTIONS=halt_on_error=1`, CPU 60s/wall 120s/core 0. LeakSanitizer is excluded; the ASan shadow mapping precludes the ordinary small RLIMIT_AS diagnostic cap.
2. Author's dedicated fact-model suite independently rebuilt and run: 7,405,472 checks, including 65,536 slots, pass (256 MiB AS, 60-second wall timeout).
3. Full candidate typed-IR suite independently rebuilt and run: 956 tests pass (1 GiB AS, 60-second runtime timeout). Exact payload checks: N=0 gives 0 bytes; N=1/63/64 gives 112 bytes across 7 snapshots; N=65 gives 224; N=65,536 gives 114,688. Existing 4,096-element straight-line initializer retains one snapshot and 1,024 word-payload bytes.
4. Existing finite baseline equivalence suite: 64 cases pass, including native results, SIGILL outcomes and exact rejection diagnostics (512 MiB process-tree AS, 5-second individual commands, 120-second suite limit).
5. Independent differential compiler wrapper runs both compilers for each ordinary source test, comparing exact exit/stdout/stderr and emitted assembly or existing-output preservation. 831 comparisons pass: 540 successful compilations and 291 normal rejections. Suites: readonly_spans (91 native/69 rejection cases), storage_binary (254 native cases / 1,186 API calls), classes (74 checks), packed_values (75 native/19 rejections) and composed_values (161 checks including 16 exact traps / 77 rejections). Rejection fixtures may be compiled twice to test absent/existing output, so compiler-invocation counts are not distinct-program counts. Each compiler process has 512 MiB AS, CPU 4/5s, wall 10s, regular-file 8 MiB and core 0. Suite wall limits are 180s.

All coverage is finite regression evidence, not a proof of compiler equivalence or complete language safety. The review did not rerun kernel/emulator gates; those are outside this compiler-only change and task scope. Full integration remains the parent's responsibility.

## Dense-workload measurements

`diagnostics/compare_readonly_resources.py` generates copied initialized byte arrays followed by repeated readonly view/loop/branch blocks; no new mutable-span syntax is involved. Measurements use same sources and compiler build flags, `wait4` per-process peak RSS in Linux KiB, coarse ~10ms wall polling, CPU 4/5s, wall 10s, regular-file 8 MiB and core 0. These are single shared-machine observations, not isolated performance qualification or portable promises.

At 256 MiB AS:

- 4,096-byte arrays with 16 blocks: baseline 172,296KiB /0.398s; candidate 57,976KiB /0.173s, identical assembly.
- 64 blocks: baseline normal exit 1 at the external address-space cap; candidate succeeds at 63,032KiB.
- 96 blocks: baseline normal exit 1 at cap; candidate succeeds at 66,400KiB.
- All six jointly successful inputs have identical assembly. Every candidate succeeds.

At 512 MiB AS:

- 4,096-byte arrays with 64 blocks: both succeed; baseline 510,588KiB /1.477s; candidate 62,976KiB /0.456s, identical assembly.
- 96 blocks: baseline normal exit 1 at cap; candidate succeeds at 66,376KiB.
- All seven jointly successful inputs have identical assembly. Every candidate succeeds.

The capped baseline failures are resource observations, not accepted-language changes or equivalence passes. Detailed results and input/output hashes are retained in `evidence/resources-256/results.json` and `evidence/resources-512/results.json`.

## Mandatory sparse-state qualification

### Direct-IR stress case

`sparse-facts-benchmark.cpp` declares 65,536 unused u8 slots and 512 branch diamonds. Both verifiers accept with 1,537 retained snapshots and zero initialized facts. Under 256 MiB AS/CPU 4/5s/wall 10s/file 8 MiB/core 0:

- Baseline 26,464KiB /0.041s
- Candidate 51,404KiB /0.061s

The candidate nevertheless allocates 1,537*16,384=25,182,208 bytes of retained word payload. This exact all-unused-slot shape is an **IR-only** construction: normal source declarations require initialization.

### Ordinary-source counterpart

Normal source can put many branches before later initialized locals, so retained prefix states are empty despite a large whole-function universe. The verified source `evidence/source-sparse/sparse-prefix-4-2048branches.au` contains 2,048 empty `if(true){}else{}` blocks, followed by four const 4,096-byte arrays fully initialized to 0u8, then returns 42. Under 512 MiB AS and the same other limits:

- Baseline 189,692KiB /0.183s
- Candidate 210,048KiB /0.162s

Both succeed with **byte-identical assembly**. RSS rises 20,356KiB, about 10.7%; the measured time does not show a slowdown. This establishes a source-reachable memory tradeoff without claiming the stronger IR-only example is normal frontend output. The exact receipt is `evidence/source-sparse/2048-branches-results.json`.

Additional 512-branch cases with one/four arrays also pass with identical assembly. Sixteen arrays under the 512 MiB external diagnostic limit yield normal `std::bad_alloc` exit 1 in both compilers; no assembly is produced. This limitation is preserved and is not reported as a language rejection or a successful comparison.

## Reproduced and repaired harness issue

Original driver SHA `2940f26a2b68751aee22828045c3a9438d905f9e95cb4abae457c0258ac32fcd` accepted `/bin/false` as its candidate and reported PASS / exit 0 because it only compared assemblies when both sides succeeded. See `evidence/driver-negative-control-before.log` and the full failed candidate data.

Owner repair SHA `63713ce34a19829814b1408a8bc34f54900e98b98a09bffd4c277ad928183f34` requires every valid-corpus candidate to exit 0, emit assembly, produce no stdout/stderr and avoid the harness deadline; successful pairs must have identical assembly. Receipts are written before assertions. Independent `/bin/false` control now fails immediately with exit 1 and the correct message while retaining the pair (`evidence/driver-negative-control-after.log`). The candidate source did not change.

The owner also repaired the exhaustive-dispatch test's copied-header tuple to include the new header. The original failed integration receipt remains preserved by the owner. This is a fixture dependency change, not a semantic workaround.

## Final independent checks

The following addenda record the final fixture, driver and documentation checks.

### Completed final independent controls

The repaired resource driver passed the complete candidate corpus again (`evidence/resources-final-driver.log`, detailed `resources-final-driver/results.json`). The independent fact model passed again with fatal sanitizer runtime settings (`evidence/independent-facts-san-fatal.log`).

The corrected exhaustive-dispatch fixture passed all 10 compile controls and its native groups: 18 receiver-array checks (10 traps), 8 composed-value checks, 13 enum/composed-method-result checks, 2,627 u8 numerical checks (260 traps), 14 packed-byte checks and 14 readonly-span checks (4 traps). See `evidence/ir-exhaustive.log`. These groups overlap existing author coverage and are not a new non-overlapping total.

No reviewer compiler/build processes remain running. The owner's full release target passed. Their full sanitizer target passed source/oracle/fact-model stages, then host cc1plus was killed while building the large direct-IR test binary. A parent-authorized serialized retry is owned by the implementation owner. No full sanitizer-target pass is inferred from that failed build, and no runtime sanitizer defect is implied by the compiler process being killed. Independent reviewer release/ABI and fact-model sanitizer results above remain separately valid.

### Final native-output benchmark controls

The owner strengthened the measurement driver further to assemble, link and execute every successful candidate benchmark, requiring exact eight-byte u64 output 42. Final driver SHA: `d9218c4934bfe290951b581eee1cbd2d5bf0e25b971d3345c59895c7bb90e6e9`; control script SHA: `cb24c3129d6286a30295617af5173241a5d684f1dffb80a07afe4347b0b3ecee`.

Independent `python3 -O diagnostics/test_resource_driver.py BASELINE OUTPUT` passes both negative controls: `/bin/false` must fail compiler success requirements; a stub that emits a program returning 43 must fail the exact native output check. Both retain the precise failing-case receipt. See `evidence/final-driver-controls/controls.json` and `provenance.json`.

All eight previously compiled candidate benchmark assemblies independently passed the final bounded native observer (assemble, bridge assemble, link and run), returning exactly u64 42 with no diagnostics. This includes both large cases whose baselines stopped at the external cap. See `evidence/final-native-outputs/results.json`. No heavy compiler build was repeated during the owner's reserved sanitizer build window.

### Documentation review

The appended current resource note and architecture section were reviewed after the source and benchmark checks. They correctly preserve historical receipts, describe the exact two-bitset change, report payload exclusions, separate ordinary-source and IR-only sparse counterexamples, and avoid global resource/performance or acceptance claims. Final housekeeping requested: explicit 512 MiB source/256 MiB IR sparse limits, normal prose spacing, completeness-matrix update and current manifests. The candidate runtime source hashes remain unchanged.

## Final scoped verdict

**PASS: the reviewed representation-only compiler change.** No unresolved compiler correctness, accepted-language or storage-arithmetic defect was found. The repaired benchmark driver now rejects compiler failure and wrong native output. The dense-workload savings and source-reachable sparse-memory regression must both remain in acceptance reporting.

Final `candidate-inputs.json` verifies all 21 declared source/test inputs and `integration-delta.json` verifies all 9 declared implementation/test changes. The runtime source and candidate binary are unchanged from the independently tested pins. The Makefile's explicit IR-test-only flags/build prefix default to the ordinary CXXFLAGS and empty prefix; they affect test-build orchestration, not compiler semantics. The bounded build helper records the command, input hashes, limits and outcome; its eventual gate outcome was not inferred by this reviewer.

The final resource note explicitly records 512 MiB for the ordinary-source sparse case and 256 MiB for the IR-only case, with CPU 4/5 seconds, wall 10 seconds, regular-file 8 MiB and core 0 for both. The completeness matrix now includes the isolated resource scope, sparse tradeoff and pending aggregate status. Source/test manifests do not include these documentation files; integration must also carry compiler/ARCHITECTURE.md, compiler/RESOURCE-NOTE.md and docs/completeness-matrix.md. Their inspected hashes are separately included in evidence/review-manifest.json.

Complete sanitizer aggregation and main-project integration remain owned by the implementation owner/parent, and are **not** declared passed by this scoped independent verdict. The final resource note corrects the stale retry sentence: it distinguishes the initial unexplained SIGKILL, the identical-flags retry that exited normally at its explicit 2 GiB cap, and the approved IR-only -g1 accommodation still awaiting aggregate completion. The complete source and differential results, faithful storage arithmetic, repaired harness controls, and mandatory sparse tradeoff above do not depend on that aggregate outcome.
