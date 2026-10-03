# Verification record

Receipts are historical snapshots. A source manifest applies only to its own
checkpoint, not a later tree with different code. Milestone001 belongs to commit
`4ae3f1f475a3f61d8a1534a82ac5d7d532677c7e`.

## Bring-up checkpoint — 2026-10-02

This checkpoint establishes only the small scalar compiler and emulator boot path.
It does not establish production readiness, Rust-equivalent general memory
safety, self-hosting, or physical AMD hardware support.

### Commands independently run by the coordinating build

```sh
make test
LD_LIBRARY_PATH=/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu \
  QEMU=/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64 \
  QEMU_DATA=/tmp/aurora-qemu/firmware make smoke
python3 tests/kernel-smoke.py --self-test
```

### Observed results

- 75 compiler execution/rejection tests passed.
- Boot image validation passed: exact ELF entry, BIOS signature, bounded payload,
  no unresolved symbols, and six malformed-image negative controls.
- Smoke validator passed its success case and eight failure regressions.
- Actual QEMU execution entered x86-64 long mode, ran compiled Aurora code,
  printed `Aurora language result: 42` and `AURORA_BOOT_OK`, and exited with the
  required status 33.
- Image: 1 MiB; linked payload: 970 bytes at this checkpoint.
- Independent adversarial review reproduced and verified fixes for leading-zero
  integer literals and contradictory boot success/failure markers.

The compiler worker additionally ran its suite with UBSan and the reviewer ran
checks with Python optimization; see [review](review.md). These checks are
supplementary, not a proof of the language's safety or of the compiler's correctness.

## Class and kernel-foundation checkpoint — 2026-10-02

A fresh build from an empty build directory passed:

- `make test`: 116 compiler execution/rejection cases, six invalid-image controls,
  page allocator/model checks, three accepted and 17 rejected smoke transcripts.
- `SANITIZE=1 ./scripts/kernel-tests.sh`: AddressSanitizer/UndefinedBehaviorSanitizer
  plus 10,000 allocator state-machine steps. Leak detection was disabled because
  the execution environment uses tracing; no leak-sanitizer claim is made.
- Actual QEMU normal boot, divide-error injection and page-fault injection passed
  via `make smoke smoke-fault smoke-page-fault`. These exercise breakpoint register
  preservation, ordinary exception frames and CPU-error-code exception frames.
- Normal image was restored afterward. Its linked payload is 5,109 bytes; image
  remains 1 MiB. No unresolved symbols were present.
- Independent review verified class-copy isolation and initialization behavior,
  corrected malformed E820 handling, and a permanent allocator-reincarnation
  regression. See [review](review.md).

Receipts: [main tests](evidence/milestone-001/test.log),
[sanitizers](evidence/milestone-001/sanitizers.log),
[emulator](evidence/milestone-001/emulator.log), and
[implementation SHA-256 manifest](evidence/milestone-001/source.sha256).
Verify the tested implementation with:

```sh
sha256sum -c docs/evidence/milestone-001/source.sha256
```

Compiler: GNU C++ 14.2, C++23. Emulator: QEMU 10.0.13, software TCG, pc/qemu64,
32 MiB memory, SeaBIOS. No physical Zen or Navi device was tested. This checkpoint
still lacks interprocedural ownership, heap safety, general methods/generics,
process isolation, scheduling, native toolchain self-hosting and device drivers.

## Safe C++ and memory-protection checkpoint — 2026-10-02

A fresh build in the original workspace passed all commands below. No saved
Codex cloud environment was used for this checkpoint.

```sh
make test
SANITIZE=1 ./scripts/kernel-tests.sh
# With the same local QEMU environment described above:
make smoke-all
```

- **203 compiler tests** passed after intentionally replacing fn/let syntax and
  wrapping arithmetic. The current modern C++ surface, const/privacy semantics,
  loops, fixed arrays and checked arithmetic are defined in compiler/README.md.
- The source author additionally ran the compiler suite with UBSan and optimized
  Python. Independent review added 34 adversarial programs and five exact
  trap-address checks; see review.md for scope and revision distinctions.
- Hosted kernel validation passed the 10,000-step allocator model, 511 page
  mappings, hostile/overlapping firmware cases, and sanitizer runs. Leak detection
  remains disabled under the tracing environment; no leak-sanitizer result claimed.
- Eight malformed-image controls passed, including distinct RX/R/RW ELF segments.
- Transcript validators accepted 13 positive cases and rejected 89 negative cases.
- All **13 actual QEMU modes** passed: normal, divide error, page fault, supervisor
  text write, data execution, guard-stack/double-fault IST, missing-NX rejection,
  and ring-3 kernel read/write, privileged CLI, code write, stack execution and I/O.
- Normal image restored afterward: 12,344-byte payload in the 1 MiB emulator disk.
- The README example compiled and assembled independently. Source hashes matched.

Receipts: [tests](evidence/milestone-002/test.log),
[sanitizers](evidence/milestone-002/sanitizers.log),
[all emulator modes](evidence/milestone-002/emulator.log),
and [source manifest](evidence/milestone-002/source.sha256).

```sh
sha256sum -c docs/evidence/milestone-002/source.sha256
```

This establishes a controlled integer-only user-boundary experiment, not arbitrary
process isolation, scheduling, SIMD context management, full language safety or
physical AMD support. The old milestone001 results remain unchanged and cannot
be used as evidence for this new syntax/semantics. C-level performance remains a
benchmark target rather than a measured claim.

## Typed IR, runtime containment and resource correction — 2026-10-02

The final corrected release compiler has SHA-256
`753845632fa5361f7262266c5b74b75927393403cf86c1d84a3ba34bc86ebf53`.
A fresh build in the original workspace passed:

- `make test`: 203 source tests, 46 direct typed-IR tests, hosted kernel/image
  checks, seven oracle-harness checks and 630 bounded semantic-oracle cases.
- `make test-semantics-stress`: 1,526 cases at seed 404 with 1,024 generated cases.
  Its fixed/model corpus overlaps the default run; counts are not additive
  independent coverage.
- 64 previous-compiler/candidate behavior comparisons. The prior compiler is a
  local baseline artifact; it is not a new runtime dependency.
- AddressSanitizer and UndefinedBehaviorSanitizer on all 203 compiler source
  tests and 46 IR tests, preserving the source harness's five-second timeout.
- Sanitized hosted allocator/mapping/program-authority tests; 10,000 allocator
  model steps, 511 mappings/firmware cases, eight kernel-image and 27 user-image
  negative controls, 16 accepted and 110 rejected transcript cases.
- All 16 actual QEMU modes through `make smoke-all`, including separately
  compiled safe-C++ programs, exact user bounds/overflow trap containment followed
  by clean runs, and rejection of invalid return PCs, unknown traps and kernel
  origin traps. Normal image restored afterward; payload 16,440 bytes.

The first extra compiler sanitizer run hit the five-second timeout on a
4,096-element initializer. Investigation found real quadratic state retention
in the IR verifier. No sanitizer violation was observed in that failing run;
it was a timeout. The failed and preliminary receipts remain in
[pre-resource-fix](evidence/milestone-003/pre-resource-fix/).

Retaining snapshots at basic-block entries corrected that straight-line case.
Matched release measurements fell from roughly 4.3 GiB peak RSS to 10.5 MiB.
Matched sanitizer measurements fell from 6,054,528 KiB / 14.6024 seconds to
46,448 KiB / 0.0809 seconds for the documented input.
See [resource note](../compiler/RESOURCE-NOTE.md) and [independent review](review.md).
These measurements are environment-specific. Join-state storage can still grow
with blocks times live slot facts; no global resource bound is claimed.
LeakSanitizer alone remains disabled under the tracing environment.

Final receipts:
- [Source, IR, kernel and default oracle](evidence/milestone-003/test.log)
- [Stress oracle](evidence/milestone-003/semantics-stress.log)
- [Baseline comparisons](evidence/milestone-003/equivalence.log)
- [Compiler sanitizers](evidence/milestone-003/compiler-sanitizers.log)
- [IR sanitizers](evidence/milestone-003/ir-sanitizers.log)
- [Hosted kernel sanitizers](evidence/milestone-003/kernel-sanitizers.log)
- [All actual CPU gates](evidence/milestone-003/emulator.log)
- [Linked image/trap metadata](evidence/milestone-003/image-metadata/)
- [Final implementation hashes](evidence/milestone-003/source.sha256)

This remains one controlled user domain, not general process isolation or
preemption. Source ownership/const/privacy analysis and bootstrap hardware code
remain trusted. No soundness proof, full runtime/stdlib, self-hosting or physical
AMD support is claimed. Earlier candidate hashes and preliminary results in
review/oracle notes are historical and are superseded by these corrected-source
aggregate receipts.

## Modules, core library and private domains — 2026-10-03

Final release compiler SHA-256:
`04b7cc71bd2ef8721f99f8c6ec6ef2cdf850358d1b55a5fea2d660073c8bae03`.
A fresh original-workspace build passed:

- 207 source tests, 51 typed-IR tests, 72 module/library tests, 11 bounded-depth
  rejection tests, 13 source-reader tests and 22 atomic-artifact-writer tests.
- The seven independent-oracle harness checks, 630-case default run and 1,526-case
  stress run. The fixed corpus overlaps between oracle runs.
- Address/undefined-behavior sanitizer checks for compiler source/modules/depth,
  typed IR, reader/writer adapters and hosted kernel policies. LeakSanitizer alone
  remains disabled under tracing. No test timeout or host stack limit was increased.
- All 19 actual QEMU modes, including three distinct CR3 roots, imported std.core
  execution, foreign-code/data denial and hardware-root mismatch rejection.
- 14 kernel-image/EDD and 27 user-image negative controls; 19 valid and 134 invalid
  transcript controls; allocator, mapping, return-policy and domain lifecycle checks.
- The documented examples/core_math.au compiled and executed to the expected 42.

Review found and verified fixes for defining-module lookup hijacking, two atomic
writer state/collision defects, and host stack crashes on deeply nested source.
The loader now uses bounded descriptor-relative Linux reads. Output publication
uses a pinned parent and fail-latched atomic writer. Parser/constructed-AST depth
limits reject the reproductions with ordinary diagnostics while preserving input
bytes and leaving no output artifact. These are scoped defenses, not a general
compiler resource guarantee or atomic whole-repository snapshot.

Normal kernel payload is 32,880 bytes. The disposable BIOS loader now reads 96
sectors, and binary packet/image checks verify alignment and the 64 KiB transfer
window. The normal image was restored after fault injection. User domains remain
bounded and sequential, without preemption, SMP or a general process API.

Receipts:
- [Aggregate](evidence/milestone-004/test.log)
- [Oracle stress](evidence/milestone-004/semantics-stress.log)
- [Compiler sanitizer](evidence/milestone-004/compiler-sanitizers.log)
- [IR sanitizer](evidence/milestone-004/ir-sanitizers.log)
- [Host I/O sanitizers](evidence/milestone-004/host-io-sanitizers.log)
- [Hosted kernel sanitizers](evidence/milestone-004/kernel-sanitizers.log)
- [All CPU gates](evidence/milestone-004/emulator.log)
- [Core example](evidence/milestone-004/core-example.log)
- [Linked-image metadata](evidence/milestone-004/image-metadata/)
- [Implementation hashes](evidence/milestone-004/source.sha256)

This is the first small freestanding core module, not libc/stdlib completeness.
No full language-safety proof, production process model, self-hosting or physical
Zen/Navi support is claimed. Prior receipts remain historical and unchanged.
