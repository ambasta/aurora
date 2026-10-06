# Verification record

Receipts are historical snapshots. A source manifest applies only to its own
checkpoint, not a later tree with different code. Milestone001 belongs to commit
`4ae3f1f475a3f61d8a1534a82ac5d7d532677c7e`.

## Accepted PR27 test-tooling checkpoint — 2026-10-05

The [developer-test contract](developer-test-contract.md) separates a fresh
current-source developer compiler from a caller-supplied independently reviewed
acceptance pin. `make test` builds once and routes the root native graph through
the same read-only compiler bytes. `make test-acceptance` requires
`ACCEPTANCE_COMPILER_SHA256`; optional `ACCEPTANCE_COMPILER` selects an explicitly
pinned prebuilt private copy without a fresh-source provenance claim. A newly
completed matching `run.json` and actual native-stage result are required;
Make exit zero, dry runs, skipped/replaced recipes, preflight and focused runs
cannot establish root native acceptance. Compiler-entry `test` has complete
compiler-only scope. Actual emulator gates remain separate.

Status: **PR27 developer-test tooling accepted**, merged into main
`772b9c8a6291aa3cc656b409ce0263f73d45b034`, tree
`62a2728942d9c36df16bd00189260f6a94cb847e`, on 2026-10-05 at 22:52:33 UTC.
The PR26-based revision-5 implementation has independently reviewed full public
developer and externally pinned prebuilt native results on the identified
GNU/Linux GCC 14 host. Those executions used the 572-file tested source;
the later 574-file results overlay preserves implementation bytes and is not a
new native execution. See [workflow results](developer-test-workflow-results.md)
for exact source/result scopes and the preserved developer audit failure.

Acceptance of that five-consumer tooling checkpoint does not qualify the
reconstructed six-consumer IPC/clock integration below. Earlier D/P focused
kernel-budget evidence remains explicitly PR25-only. Gentoo, new sanitizer/emulator
runs and broad-host qualification remain separate. Existing checkpoint evidence
below keeps its original source scope.

## Provisional IPC/tooling/clock preparation — 2026-10-05

The new [clock contract](kernel-emulator-clock-contract.md) selects exactly 51 UEFI
timer modes for fixed instruction-derived virtual time; 126 other production
modes, three BIOS capacity probes and two normal restoration boots retain their
original clocks. The original IPC aggregate is still failed at mode 163,
`user-retire-pending`, after 162 partial passes. Its normal restorations remain
preserved, and the later single traced exit 33 is inconclusive with no acceptance
credit. No guest source, budgets 128/3 or original strict validator is changed.

The reconstructed six-consumer IPC/clock integration remains unaccepted and
unqualified; accepted PR27 tooling results do not transfer to it.

The reconstructed source with manifest
`e6c08e72e9764615043b4ef7c5a726c5a5dda12c6f1de9f8735ec0fe8b6230b7`
passed the four admitted compiler-free clock controls on 2026-10-06. The four
command supervisors exited 0. These controls covered launcher syntax, ordinary
and optimized eight-method suites, and the exact retirement/default command
plans. Independent terminal-closure review is still pending. Combined native,
ABI/linked-image review and actual 177-mode qualification remain pending.

This publication composition changes only the two status/clock documents from
that tested source, including the caveats and this status note. These documentation
changes receive separate review; the four control results are not new-source
execution credit. Historical native tooling and emulator results below retain
their identified source scopes.

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

## Milestone 005: encapsulated classes and bounded preemption (2026-10-03)

Final aggregate and independent review passed on release compiler SHA-256
`d1aef9e30e8e5a874b02e6f2de589ac4908950f7264d64aab08ff89ff2141c1a`.
The constructor/method subset is specified in [CLASSES.md](../compiler/CLASSES.md).
The Aurora-authored `std.numeric` module exercises a private checked accumulator.
One complete initializer-list constructor, scalar fields/arguments/results,
private methods and scoped const/mutable receivers are supported. General
constructor bodies, escaping receivers, generics and resource fields remain absent.

Kernel preemption uses a feature-checked QEMU BSP xAPIC one-shot timer, with no
calibrated time claim. It preserves integer state in privileged snapshots,
validates domain/CR3 authority, interrupts a non-yielding compiled loop, cancels it
after 24 slices and runs a fresh clean task after scrubbed frame reuse. Pending
interrupts are drained across task lifetimes. Unknown user faults remain fail-stop
in this harness; FPU/SIMD/TLS lifecycle, SMP, arbitrary programs and a general
scheduler/process API are not implemented. This is not Framework hardware support.

Final receipts:
- [make test](evidence/milestone-005/test.log): 207 source, 74 class, 132 direct IR,
  72 module, 11 depth, 13 source-reader and 22 output-writer tests; hosted kernel
  policy and transcript tests; seven oracle harness tests and 630 default cases.
- [Independent stress oracle](evidence/milestone-005/semantics-stress.log): 1,526
  cases, seed404, pinned exact release binary. Default and stress sets overlap;
  do not add their counts as disjoint coverage.
- [Compiler/IR ASan+UBSan](evidence/milestone-005/compiler-sanitizers.log): 207
  source, 74 class, 72 module, 11 depth and 132 IR cases. Sanitized compiler SHA
  `060095244309c4db5bc04a19de53b39d36c264363ce0f3ede7488e05985b2032`;
  IR binary SHA `5462faf7ae5c3defadf6b15dbd01550a25e20d8a79f26471f4fd823be615cadd`.
- [Host I/O sanitizers](evidence/milestone-005/host-io-sanitizers.log) and
  [kernel sanitizers](evidence/milestone-005/kernel-sanitizers.log).
- [make smoke-all](evidence/milestone-005/emulator.log): all 28 actual QEMU gates,
  preserving the old 19 and adding nine timer/preemption/adversarial modes.
- [Normal image restored](evidence/milestone-005/normal-restored.log),
  [image metadata](evidence/milestone-005/image-metadata/), and
  [source identity](evidence/milestone-005/source.sha256).

Sanitizers use address and undefined-behavior instrumentation; LeakSanitizer is
explicitly disabled for the tracing environment, so no leak-check claim is made.
The normal payload is 41,712 bytes within the existing 96-sector loader budget.
The independent [review](review.md) records a typed-constructor syntax defect and
an overly permissive per-slice transcript check, their fixes and regressions.
Earlier evidence directories are preserved unchanged. All results are bounded
bootstrap evidence, not a full-language safety proof or production OS release.

## Milestone 006: value calls and UEFI handoff (2026-10-03)

Final aggregate and independent review passed on release compiler SHA-256
`f16fffe8a976b71c82bbebf90e32150142aad044649b2f02dd585c8933719a71`.
Ordinary functions now accept immutable scalar-field class copies and return
complete independent class values. Left-to-right snapshot semantics, nominal
private ABI capabilities, complete initialization and direct-import signature
visibility are checked. [VALUE-CALLS.md](../compiler/VALUE-CALLS.md) specifies the
64-field/six-argument boundary and excluded features. Native `std::minmax`,
`std::MinMax` and `std::range_width` exercise the feature; a protected ring3
fixture now uses the class-result library path.

The separate [UEFI loader and payload](../kernel/uefi/README.md) pass OVMF boot,
stale map-key retry/exhaustion, malformed handoff/map/table rejection and actual
WP/NX faults. Own CR3, guarded stack, complete mapping validation and a bounded
owned-page exercise precede Aurora execution after ExitBootServices. BIOS
scheduler functionality is not yet ported to this consumer. It does not perform
ACPI discovery, physical Framework boot, device enumeration or general allocation
from all firmware memory. Firmware assumptions and resource limits are explicit.

Final receipts:
- [make test](evidence/milestone-006/test.log): 207 original source, 74 methods,
  59 value-call, 206 IR and four exhaustive-dispatch compile checks; 72 module,
  11 depth, 13 reader and 22 writer cases; kernel policies; 124 UEFI policies;
  UEFI transcript eight positive/148 negative controls; seven oracle self-tests
  and 630 default cases.
- [Independent stress oracle](evidence/milestone-006/semantics-stress.log): 1,526
  scalar cases with seed404. Default/stress fixed cases overlap.
- [Compiler/IR sanitizers](evidence/milestone-006/compiler-sanitizers.log),
  [host I/O sanitizers](evidence/milestone-006/host-io-sanitizers.log), and
  [BIOS/UEFI policy sanitizers](evidence/milestone-006/kernel-sanitizers.log).
- [make smoke-all](evidence/milestone-006/emulator.log): all 36 actual emulator
  gates, comprising 28 preserved BIOS gates and eight OVMF gates. PE/PIC image
  validation includes 14 malformed-image controls.
- [Restored normal BIOS/UEFI boots](evidence/milestone-006/normal-restored.log),
  [image metadata](evidence/milestone-006/image-metadata/) and
  [source hashes](evidence/milestone-006/source.sha256).

The sanitized compiler hash is
`ab8ad95501780fdc268d0e1511b323cfeb9f0d9884814ab245a1803c8c77f63b`;
the sanitized IR test hash is
`5c8e6abb1e2f783605de5d3b02c62ddf0118ec53ee13695121a2b21f967eca94`.
Address/undefined-behavior checks use halt-on-error; LeakSanitizer is disabled
under tracing. An initial parent command named a nonexistent value-test script;
it was corrected to value_calls.py and the entire compiler sanitizer command
was rerun successfully. The successful receipt is the evidence cited above.

Review recorded incomplete opcode emission during integration (now rejected by
exhaustive dispatch), an RX GDT accessed-bit write fault, PIC linker relaxation,
inherited translation concerns and insufficient failure-log ordering checks.
Fixes and independent evidence are in [review.md](review.md). No unresolved
reproduced defect remains within the reviewed slice; this is not a full-language
proof, complete runtime/stdlib, multi-user filesystem system or hardware release.
Historical milestone receipts are unchanged.

## Milestone 007: checked integers and ACPI discovery (2026-10-03)

Final parent aggregate and independent review passed on compiler SHA-256
`6bed4b61d50cb2f40f2b1f6f4564172daade95336df852f80938c3f0726998b1`.
[Integer semantics](../compiler/INTEGERS.md) cover checked division/remainder and
native gcd/lcm/DivResult. Zero divisors trap before IDIV; minimum/-1 quotient
traps for overflow while remainder is explicitly zero. BIOS fixtures validate
exact user-trap containment, clean restarts and fatal kernel-origin misuse.

[ACPI discovery](../kernel/uefi/acpi.md) now snapshots RSDP/XSDT/MADT after firmware
exit, using one revocable supervisor read-only/non-executable window. Source
ranges are admitted separately from allocator ownership; runtime/ACPI readability
does not grant allocation. Actual OVMF gates cover one/two CPU descriptions,
disabled CPU exclusion, malformed tables/roots/header changes, write denial and
revoked-window fault. This does not perform AML, SMP startup, PCI/device-driver
activation or Framework qualification.

Evidence:
- [Aggregate](evidence/milestone-007/test.log): 207 original source, 74 methods,
  59 value calls, 84 integer cases, 216 IR and six exhaustive-dispatch checks;
  72 modules, 11 depth, 13 reader and 22 writer cases; kernel policy suites.
  Division host checks ran explicitly after the aggregate and are now included
  in the Makefile's test-division dependency.
- [Integer oracle](evidence/milestone-007/integer-oracle-independent.log): 1,510
  native cases with 181 exact trap-site checks. Independent reviewer seed8731
  additionally covered 1,792 cases/213 traps on release and sanitizer binaries;
  sets overlap and must not be summed as disjoint coverage.
- [Scalar stress](evidence/milestone-007/semantics-stress.log): 1,526 cases,
  supplementing seven harness self-tests and 630 default scalar cases.
- [Compiler/IR sanitizers](evidence/milestone-007/compiler-sanitizers.log),
  [host I/O sanitizers](evidence/milestone-007/host-io-sanitizers.log), and
  [kernel/UEFI/ACPI/division sanitizers](evidence/milestone-007/kernel-sanitizers.log).
- [Actual emulator aggregate](evidence/milestone-007/emulator.log): 52 unique
  modes (28 previous BIOS + eight UEFI + eleven ACPI + five division), plus a
  repeated normal BIOS confirmation. No aggregate count treats the repeat as
  a new mode. Normal BIOS/UEFI artifacts are restored by the wrappers.
- [Image metadata](evidence/milestone-007/image-metadata/) and
  [source identities](evidence/milestone-007/source.sha256).

ACPI policy testing includes 16,475 cases; transcript controls are eleven positive
and 217 negative. Division metadata controls are three positive/30 negative and
transcript controls five positive/210 negative. Existing UEFI policy124 and
transcript8/148 controls remain separate. Sanitizers use address/undefined-behavior
checks with halt-on-error; LeakSanitizer stays disabled in the tracing environment.
Sanitized compiler SHA: `50457148c8c22d4c5bf3ce1b7044fe5ada38bb827593728b951d14db4b0ba160`.
Sanitized IR SHA: `142cad295cfddb6ea37b94a0b29c3eeb6b9de28f64e5c6347e35149676cbcc87`.

[Independent review](review.md) records fixes for nonzero x2APIC reserved bytes,
NV-tagged firmware source pages and two over-permissive transcript checks.
Original counterexamples now reject. No unresolved reproduced defect remains in
this reviewed slice. Previous receipts are unchanged; no full safety proof,
complete numeric library, physical hardware or complete OS claim is made.

## Milestone 008: unsigned core and read-only PCI inventory (2026-10-03)

Final aggregate and independent review passed on compiler SHA-256
`11ad14a187f0cd69539626dbafaff2f6340762ff1dd0430059ec192332c9f99b`.
[Unsigned semantics](../compiler/UNSIGNED.md) define distinct u64 values, checked
integer conversions/arithmetic, exact 64-bit bitwise operations and checked shifts.
No implicit signed mixing or pointer conversion is added. The native std.bit
module supplies scalar popcount, bit_width and has_single_bit. Protected BIOS
fixtures exercise full-width values, invalid shift counts and conversion faults.

[PCI inventory](../kernel/uefi/pci.md) uses validated MCFG snapshots and a separate
revocable supervisor read-only UC window under an explicit q35/OVMF aperture
contract. Default, added-controller and downstream-bridge fixtures discover
5/8/7 functions respectively. Device identity is not a DMA/resource capability;
no BAR sizing, bus-master enable, device commands or host hardware changes occur.
MCFG alone is not generic resource reservation or Framework qualification.

Final receipts:
- [make test](evidence/milestone-008/test.log): existing 207 source/74 methods/
  59 value/84 signed cases; 95 unsigned, 385 IR and ten exhaustive-dispatch checks;
  72 modules/11 depth/13 reader/22 writer cases plus all hosted kernel policies.
- Unsigned default oracle: 4,219 cases, 501 exact trap sites and 67 rejection
  fixtures, included in aggregate and sanitizer receipts. [Stress](evidence/milestone-008/unsigned-stress.log)
  covers 8,959 cases/1,044 traps; independent reviewer seed covers 6,665/766 on
  release and sanitized compiler. These overlap; counts are not additive.
- Signed oracle remains 1,510/181; scalar harness seven tests/default630 and
  [stress1,526](evidence/milestone-008/semantics-stress.log) remain separate.
- [Compiler/IR sanitizers](evidence/milestone-008/compiler-sanitizers.log),
  [host I/O sanitizers](evidence/milestone-008/host-io-sanitizers.log), and
  [kernel sanitizers](evidence/milestone-008/kernel-sanitizers.log).
- [Emulator aggregate](evidence/milestone-008/emulator.log): all 66 distinct modes,
  preserving 52 and adding ten PCI plus four protected unsigned modes. Repeated
  normal confirmations are not additional distinct modes. Wrappers restore
  normal BIOS and UEFI artifacts.
- [Image metadata](evidence/milestone-008/image-metadata/) and
  [source manifest](evidence/milestone-008/source.sha256).

PCI hosted policy has 71,054 checks; transcript controls are ten positive/289
negative. Unsigned image controls are nine/34, transcript four/197, plus four
exact source fixtures. A PCI transcript-order false positive was fixed and
retested; [review.md](review.md) retains independent evidence and limits.
Sanitized compiler SHA `98ab2ea7c51c3d4bc43f00b396c64f12747c1f10b4fbd610a8aa38af50ff3f46`;
sanitized IR binary SHA `06e01199939b356048680448197806ff9ea43caf16460ec86a7dd523a197e38d`.
Address/undefined-behavior checks halt on errors; LeakSanitizer is disabled under
tracing. No unresolved reproduced defect remains in this reviewed scope. Full
stdlib, generic templates, physical device drivers, IOMMU, multi-user/filesystem
services and complete OS readiness remain unimplemented. Historical receipts
are unchanged, and none of these tests constitutes a full safety proof.

## Milestone 009: constrained templates and UEFI user domains (2026-10-03)

Final aggregate and independent review passed on compiler SHA-256
`351a46e42c1ad2e0b224d01a57f249039c37ffe44e051a5d67b420eae54c9174`.
[Templates](../compiler/TEMPLATES.md) add explicit one/two-parameter Scalar-constrained
class definitions and native std.utility/std::pair<T,U>. Nominal identity includes
the defining module/template and ordered scalar type tuple. Privacy, complete
initialization and independent class copies remain checked. Exact graph limits
are 64 template definitions/256 specializations; these are not global stack/time
bounds. Function templates, deduction, recursive/nested instantiation and general
concepts are not implemented.

[UEFI protected execution](../kernel/uefi/runtime.md) now runs two separately
linked compiled user images backed only by the validated allocated arena. Explicit
canonical user layouts, immutable layout authority, independent CR3 roots, private
stacks and guarded RSP0/IST protect the boundary. A clean std::pair program returns
42, an exact bounds trap is contained, clean execution resumes, retired stack
frames are scrubbed/reused and a fresh execution returns 42. Inherited SYSCALL and
SYSENTER paths are disabled and adversarially tested. Execution remains sequential
and integer-only; UEFI timers, arbitrary processes, IPC and drivers remain absent.

Final receipts:
- [Aggregate](evidence/milestone-009/test.log): 117 template, 393 IR and ten
  exhaustive-dispatch cases plus existing source/module/host-I/O and kernel suites.
- Existing signed1,510/181 and unsigned4,219/501/67-rejection oracles remain in
  aggregate and [compiler/IR sanitizer](evidence/milestone-009/compiler-sanitizers.log)
  receipts. Independent template review adds seven scope/identity cases on release
  and sanitizer; alternative suites overlap and are not additive coverage.
- Scalar harness7/default630 and [stress1,526](evidence/milestone-009/semantics-stress.log).
- [Host I/O sanitizers](evidence/milestone-009/host-io-sanitizers.log) and
  [kernel policies/sanitizers](evidence/milestone-009/kernel-sanitizers.log).
- [Actual emulator aggregate](evidence/milestone-009/emulator.log): all 80 distinct
  modes, preserving 66 and adding fourteen UEFI runtime modes. Repeated normal
  confirmations are not new modes. Normal artifacts are restored by wrappers.
- [Image metadata](evidence/milestone-009/image-metadata/) and
  [source identities](evidence/milestone-009/source.sha256).

Runtime hosted checks include 1,274 layout/table/corruption/reuse cases, immutable
layout authority tests, three positive/64 negative image controls and fourteen
positive/716 negative transcript controls. Independent review reran all fourteen
actual runtime modes after fixes. The SYSENTER negative uses an explicit Intel
vendor QEMU fixture to exercise that instruction path; it is not Intel or AMD
physical qualification. Normal AMD-emulated behavior remains separately tested.

Sanitized compiler SHA `4f4766c0ee311fff00de84ebfe9aafa9ce301268bf7ef41d3196fca220da5a28`;
IR binary SHA `06950dba4bc0ff466f7c53f7cb4de5659b12747e0bf6ea26c197c9d1be825ac3`.
Address/undefined-behavior checks halt on error; LeakSanitizer is disabled under
tracing. [Review](review.md) records the short-image subtraction fix, rejection
of an unused absolute BIOS vector table from the PIC build, metadata PC-zero
forgery rejection, and successful corrected reruns. Launch-time stack scrubbing
also closes the stale return-word found during integration. Strict relocation
validation was retained, not bypassed. No unresolved reproduced defect remains
within scope. No full language-safety proof, full stdlib, filesystem/multi-user
stack or physical Framework readiness is claimed. Historical receipts remain
unchanged.

## Milestone 010: fixed containers and staged IPC (2026-10-03)

Verified snapshot compiler SHA-256:
`d91e06fad144a89c1c836e16db20ef48b8a644bf4c23b22a1517e08f25e1d82c`.
[Fixed containers](../compiler/FIXED-CONTAINERS.md) provide std::array<T,N> with
scalar T, explicit literal N in 1..64, private complete zero initialization,
copied checked access, mutable set and independent value copies. Canonical
builtin::array and fixed unqualified array storage names are distinct from the
qualified library wrapper. Logical named fields and flattened leaf layout are
separate; ordinary class-value boundaries remain bounded to 64 leaves. General
nested values, heap allocation, slices and dynamic collections remain absent.

[Staged IPC](../kernel/uefi/ipc.md) connects separately compiled UEFI client and
service images through fixed copied scalar messages. Kernel-selected phases and
live domain identity bind generation/rights claims. Reply/cancel is first-terminal-
wins; exact service faults cancel, revoke and retire service authority before
scrub/reuse/restart. Pending cancellation, stale grants, forged identities,
versions/transactions/sites, duplicate and late replies are tested. This does
not suspend an arbitrary instruction/stack or provide non-yielding-service timeouts.

Evidence and execution provenance:
- [Fresh parent aggregate](evidence/milestone-010/test.log): 216 container cases
  (55 exact bounds/order sites, 96 rejections), 463 IR, ten exhaustive-dispatch
  checks and 18 native receiver-array IR probes/ten exact sites, plus all prior
  source/template/module/I/O suites and current hosted kernel checks.
- [Compiler/IR sanitizers](evidence/milestone-010/compiler-sanitizers.log),
  [host I/O sanitizers](evidence/milestone-010/host-io-sanitizers.log), and preserved
  [kernel sanitizer records](evidence/milestone-010/kernel-gates/).
- Existing signed1,510/181, unsigned4,219/501/67-rejection and scalar7/630 checks
  remain separate. [Scalar stress](evidence/milestone-010/semantics-stress.log)
  has 1,526 cases. Alternative seeds overlap and must not be summed.
- [Complete final kernel run](evidence/milestone-010/kernel-gates/results.json):
  all 95 distinct modes (80 preserved + fifteen IPC), with per-mode logs/metadata,
  commands, tools and source-input identities in the same directory. The run
  used the exact frozen compiler. Independent review repeated all fifteen new
  IPC modes. This retained run is not relabeled as a new parent invocation.
- [Parent receipt validation](evidence/milestone-010/receipt-validation.log)
  checked all retained file hashes and 139 captured source/build inputs before
  adding Makefile test/smoke IPC wiring. The source manifest was captured during
  the run, not asserted to be a pre-run snapshot; unchanged executable/test code
  was verified at completion and again at handover.
- [Fresh parent BIOS/IPC spot checks](evidence/milestone-010/parent-spot-checks.log)
  repeated normal BIOS, IPC success and actual service fault/restart after the
  full run; no executable/test source changed. Normal artifacts are restored.
- [Final source manifest](evidence/milestone-010/source.sha256).

IPC policy covers 26,120 rejected envelopes and 262,144 six-operation sequences
against an independent state model. Image controls retain runtime3/64 plus
IPC4/26; IPC transcript controls are fifteen positive/1,732 negative. No defect
was reproduced by independent M010 review within its stated scope. Review and
limitations are recorded in [review.md](review.md).

Sanitized compiler SHA `cb7778a8078878a9fc1d25e9059cc9de07928a9ad9f9fae984ce4fb365391943`;
IR binary SHA `c987707b2ec21f046ea790fac5b5f783977b58a9e40dab925b05712e8a534369`.
Address/undefined-behavior checks halt on error; LeakSanitizer is disabled under
tracing. The separately preserved original kernel receipt archive hash is
`b75190e86d152ed9176a3b3d672beb9d93aeedaff6303c0631bec2e1ebc5ed03`.
Historical receipts are unchanged. This remains bounded bootstrap functionality,
not a full safety proof, physical Framework qualification, driver activation,
filesystem/multi-user OS or complete standard library.

## Milestone 011: composed values and UEFI service budgets (2026-10-03)

Verified compiler SHA-256:
`84e14fc5e81ac6b18abb974d5d3a5c84d68e5ba99323bd04f686ac69ba443808`.
[Composition](../compiler/COMPOSED-VALUES.md) adds Value constraints, complete
nested class initialization, readonly left-to-right constructor snapshots and
independent public-field projections. Acyclic containment is bounded to four
class levels and 64 scalar leaves; empty fields still require logical completion.
Scalar remains unchanged. No nested mutation, resource/reference fields, general
template deduction or recursive instantiation is introduced.

[Service budgets](../kernel/uefi/service-budget.md) reconcile copied MADT evidence,
BSP/MSR/APIC identity and an explicit q35 aperture, then use supervisor UC mappings
and one-shot timer interrupts to resume or cancel one running service. Cancellation
restores the kernel root and drains pending delivery before revocation/scrub/reuse.
Replies retain first-terminal-wins semantics. Budget units are verified interrupts,
not time. General scheduling, SMP and arbitrary non-yielding clients remain absent.

Final evidence:
- [Fresh parent aggregate](evidence/milestone-011/test.log): 161 composition cases
  (16 exact-site traps/78 rejections), 529 IR, ten exhaustive-dispatch controls,
  18 previous native IR checks plus eight composition-native cases, and all prior
  source/library/module/I/O suites. Independent review also ran a 64-case
  constructor ABI matrix on release and sanitizer candidates.
- [Compiler/IR sanitizers](evidence/milestone-011/compiler-sanitizers.log),
  [host I/O sanitizers](evidence/milestone-011/host-io-sanitizers.log),
  scalar harness7/default630 and [stress1,526](evidence/milestone-011/semantics-stress.log).
  Signed and unsigned numeric oracles remain separate overlapping coverage.
- [Complete final kernel run](evidence/milestone-011/kernel-gates/results.json):
  all 110 distinct modes (37 BIOS + 73 UEFI), preserving 95 and adding fifteen
  service-budget modes. Source inputs were hashed before the first build and
  rechecked after the last gate; all 170 matched. Per-mode command/serial logs,
  available metadata, tools and pre/post manifests are retained in that directory.
- [Parent hash/source validation](evidence/milestone-011/receipt-validation.log)
  checked every retained receipt and the 170 live inputs before parent reruns.
  [Fresh parent spots](evidence/milestone-011/parent-spot-checks.log) repeated normal
  BIOS, budget recovery and the corrected pending-interrupt drain. This does not
  relabel the full retained run as a duplicate parent invocation.
- [Final source manifest](evidence/milestone-011/source.sha256).

Hosted service-budget checks include 6,726 admission/context/table cases, image
controls four positive/38 negative and final transcript controls fifteen positive/
2,543 negative. The independent reviewer repeated all fifteen corrected actual
modes. The originally failing strict drain check was diagnosed with saved/live
kernel SS=0. Trusted user return now restores SS=0x10 with DS/ES while IF is clear;
the original strict predicate remains. Corrected receipts require SS=16. Original
failures and the selector trace are retained under kernel-gates/prior-development-failures.
The earlier unverified archive is historical and not an accepted milestone.

Independent review was initially interrupted by an unidentified tool restriction.
At the user's explicit request it resumed once through the same reviewer and
normal local workflow, without changing safeguards or environments, and completed.
No acceptance was inferred from the failed turn; only subsequent completed evidence
is counted. [review.md](review.md) records scope and results.

Sanitized compiler SHA `09ae587a55fd7bc91134a7010d2500017bd52d9827f884fd877204d63efb0000`;
IR SHA `dfacecd5a4f47894e2bb84428db15ab614b16e2f0096cd9c63d29736fd1dc55f`.
Address/undefined-behavior checks halt on error; LeakSanitizer is disabled under
tracing. Original full kernel receipt archive SHA:
`74692077e6e4f30620fde44b26a4eaeae09b25304d4c67b6dbe7cadf6572f790`.
No unresolved reproduced issue remains within the reviewed slice. Historical
receipts are unchanged. Physical Framework support, driver activation, persistent
filesystems, multi-user services and complete language/stdlib safety remain goals,
not results of this checkpoint. The separate decimal/enums branch is not included.


## Milestone012: enums, copied reports and bounded three-domain dispatch

Verified 2026-10-03. Release compiler SHA256:
`a6de1e89e307b076672a1e2ee8a5e848625ac92e386622c1fa5fe7c6ab675026`.
The clean UEFI fixture exercises an enum and independent class-valued method
result alongside prior Value/container behavior: 3,379 bytes within the unchanged
4,096-byte RX cap. This is native execution, not an unexecuted API sketch.

Evidence and provenance:

- [Fresh parent make test](evidence/milestone-012/parent-make-test.log): all aggregate
  compiler, image, hosted kernel, metadata, transcript and scalar harness gates.
- [Compiler author and independent evidence index](evidence/milestone-012/compiler-review/README.md):
  full release/sanitizer regression runs, independent alternate-seed and ABI tests,
  exact artifacts, earlier unsuccessful attempts and instrumentation limits.
- Fresh parent sanitized [decimal196](evidence/milestone-012/parent-sanitized-decimal_values.log),
  [combined107](evidence/milestone-012/parent-sanitized-enum_composition.log),
  [composition161](evidence/milestone-012/parent-sanitized-composed_values.log), and
  [IR592 and host I/O13/22](evidence/milestone-012/parent-ir-io-sanitized.log) pass.
- Independent scalar harness logs retain [nine self-tests](evidence/milestone-012/parent-oracle-selftests.log),
  [630 default](evidence/milestone-012/parent-oracle-default.log) and
  [1,526 stress](evidence/milestone-012/parent-oracle-stress.log) cases. These cover
  existing scalar semantics; alternate seeds and reruns are not disjoint totals.
- [Complete retained kernel run](evidence/milestone-012/kernel-gates/README.txt):
  all 122 distinct modes, 37 BIOS + 85 UEFI, from 08:56:24 through 09:07:52 UTC.
  All 110 historical modes and twelve new dispatcher modes passed. Commands,
  serial logs, available metadata, tools and pre/post input hashes are retained.
- [Parent receipt validation](evidence/milestone-012/receipt-validation.log) checked
  344 receipt hashes and all 186 live executable/build/test inputs against both
  pre-run and post-run captures, plus the exact release compiler hash.
- [Fresh parent emulator spots](evidence/milestone-012/parent-spot-checks.log): normal
  BIOS, normal dispatcher, service-budget recovery and pending-interrupt drain.
  Normal UEFI image restored afterward. This is not a second complete 122-mode run.
- [Final source identity](evidence/milestone-012/source.sha256) and
  [compiler binaries](evidence/milestone-012/compiler-binaries.sha256).

Independent review repeated all twelve new actual dispatcher modes. Hosted checks
include 6,039 layout cases, 9,540 rejected envelopes, 248,832 exhaustive five-step
sequences and 4,096 independent 128-operation traces. Image controls are three
positive/72 negative, transcript controls twelve positive/5,988 negative. Distinct
client results42/73 and selection0→1→0 were observed. Fault/budget recovery cancels
only affected nonterminal transactions, preserves committed replies, drains the
old timer epoch before reuse and requires fresh service grants.

The final sanitizer compiler hash is
`3c5272f7e8a32fdbd9561de88f6a7cede2fcd34d3cab7218f8e504faa07551b1`;
IR hash `1f8acd34a5a11340490ce174fff8b179b67477b77564ad943823aac3ef0b7064`.
Sanitizers instrument host tools, not emitted native programs. Leak detection is
disabled under the documented tracing limitation. The sanitizer harness drops
only compiler address-space limiting for shadow memory; native limits remain.
RLIMIT_FSIZE limits regular files, not captured-pipe memory; pipes remain unbounded.
A redundant O1/g compiler build was killed for an unverified reason; the final
unchanged-flags aggregate succeeded. Earlier attempt receipts remain separate.
The temporary development zero-interrupt loop failure raw log was overwritten by
its development rerun; only its observation is retained. No archived raw failure
receipt is claimed. See kernel-gates/development-notes.txt.

Original full kernel receipt archive SHA256:
`c197799ba8c044f0d9449bb1859275eb7acec3217111627d619236f9db8f925e`.
No unresolved reproduced defect remains in this reviewed bounded slice. Clients
remain cooperative; this is not a general scheduler or a wall-clock guarantee.
No physical Framework/device/DMA, filesystem, multi-user desktop, complete stdlib,
Rust-equivalent safety proof or equivalent-C performance qualification follows.


## Milestone013: checked compact bytes and controlled client recovery

Verified 2026-10-03. Final release compiler SHA256:
`02771e0d94ad9fe9821041ee10081d31a4f4114dde81b7d476e16cba8d5c75d2`.
The clean native protected fixture asserts two-byte std::array<u8,2> storage,
preserves a neighboring 255 byte while storing 42, and widens the result to i64.
Its 3,658-byte image fits the unchanged 4,096-byte RX bound while preserving prior
enum, copied method result and composition behavior.

Evidence and provenance:

- [Fresh parent make test](evidence/milestone-013/parent-make-test.log) passed the
  full aggregate including newly wired user-phase hosted/image/transcript tests.
- [Compiler author and independent evidence](evidence/milestone-013/compiler-review/README.md)
  retains full release/ASan/UBSan aggregates, exact binary/source hashes, mathematical
  oracles, alternate seeds, additional constructor ABI checks and failed/interim
  development attempts. Parent validated all 38 indexed receipt hashes.
- [Fresh parent sanitized tools](evidence/milestone-013/parent-sanitized-tools.log)
  passed the u8 numeric sweep, byte codec, packed-value suite, direct IR 846 and
  host source/output adapters 13/22. Fatal sanitizer settings and hashes are recorded.
- Existing scalar regression passed [nine self-tests](evidence/milestone-013/parent-oracle-selftests.log),
  [630 default](evidence/milestone-013/parent-oracle-default.log) and
  [1,526 stress](evidence/milestone-013/parent-oracle-stress.log) cases on the exact pin.
- [Complete retained actual kernel run](evidence/milestone-013/kernel-gates/README.txt)
  passed 139 distinct modes:37 BIOS+102 UEFI,09:53:41–10:07:46 UTC. All 122 previous
  modes and 17 new controlled-user-phase modes passed on the final M013 compiler.
  The 202 executable/test/build inputs were captured before the first build and
  matched afterward. Commands, per-mode serial logs, available metadata, tools,
  pre/post manifests and distinct results are retained.
- [Parent receipt validation](evidence/milestone-013/receipt-validation.log) checked
  all 396 kernel receipt hashes,202 live inputs,139 unique successful mode records
  and the exact compiler hash, then rechecked inputs after fresh parent tests.
- [Fresh parent emulator spots](evidence/milestone-013/parent-spot-checks.log)
  repeated normal BIOS, request and completion non-yielding client budgets, and
  pending interrupt drain at retirement. Normal UEFI image restored afterward.
  These selected reruns are not represented as a second complete 139-mode execution.
- [Final source manifest](evidence/milestone-013/source.sha256) and
  [binary identity](evidence/milestone-013/compiler-binaries.sha256).

Independent kernel review repeated all 17 new modes on the preceding immutable
M012 compiler pin. The separate final 139 run establishes their integration with
M013. New hosted checks include 20,611 authority cases,65,536 exhaustive disposal
sequences and 4,096 longer independent model traces under fatal ASan/UBSan, plus
image 12 positive/127 negative and transcript 34 positive/25,222 negative controls.
The committed replied 42 disposition survived client retirement; peer 73 and a
fresh client 42 completed after old-root invalidation, table clearing, frame scrub,
old-epoch timer draining and grant rebinding. Unknown fault origins remain fatal.

The u8 oracle reports 923,136 observations,37 source fixtures,117 exact named-site
traps and 138 ordinary rejections. It exhausts successful arithmetic domains and
reports excluded overflow/zero-divisor inputs; failure edges are sampled separately,
not claimed as an exhaustive crash sweep. Default codec 352+7 rejections and packed
suite 75+19 rejections pass. Independent alternate codec 928 cases and constructor
ABI 64 cases overlap base semantics and are not disjoint total coverage. Native IR
adds 2,627 u8 checks/260 exact traps and 14 packed ABI/padding cases alongside 18+8+13
prior groups and ten exhaustive-dispatch controls.

Sanitizer compiler SHA256:
`cbe0d747958892457131bb1175c61a3d8debf86c60d1decee55ce7429d118782`;
IR SHA256 `3bcfda07961b5df01686284bab2ee77549568f7fe3d2065e3526df0bd5779b14`.
Host tools are instrumented, emitted native programs are not. Leak detection remains
disabled for the documented executor limitation; regular-file limits do not bound
captured pipes. Padded numeric-only gate A and an earlier empty-class map integration
failure remain explicitly separate development evidence, not compact-layout passes.
The initial kernel heterogeneous-auto/unused-function build failure is retained;
all final gates followed its correction. No final test failure is hidden or waived.

Original kernel receipt archive SHA256:
`c5683b8bf390b20a353f7888c53fd648951c613efd792cc74a6cbc736401b59f`.
No unresolved reproduced defect remains in this reviewed bounded checkpoint.
It does not establish arbitrary process recovery, global resource/stack bounds,
SMP, calibrated deadlines, DMA or physical Framework support, complete language or
stdlib safety, arbitrary binary serialization or equivalent-C throughput.

## Milestone014: readonly spans and read-only PCI resources

Verified 2026-10-03. Corrected compiler SHA256:
`2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`.
Readonly whole-array byte spans provide a bounded synchronous borrowing interface;
std.binary reads are real compiled code. A separate 449-byte protected span program
runs without enlarging the existing 4 KiB RX profile or dropping historical checks.

Evidence and provenance:

- [Fresh parent make test](evidence/milestone-014/parent-make-test.log) passed the
  complete aggregate, including storage host-model, BAR and span targets.
- [Compiler evidence index](evidence/milestone-014/compiler-review/README.md)
  preserves author and independent runs, exact pins, initial lifetime-join
  reproduction, corrected rejection and all failed/interim attempts.
- [Fresh parent sanitized tools](evidence/milestone-014/parent-sanitized-tools.log)
  passed readonly-span execution/rejection tests, all 950 direct IR cases and
  host source/output adapters. Instrumentation is on host tools, not emitted code.
- Independent scalar regression passed [nine self-tests](evidence/milestone-014/parent-oracle-selftests.log),
  [630 default](evidence/milestone-014/parent-oracle-default.log) and
  [1,526 stress](evidence/milestone-014/parent-oracle-stress.log) cases on the exact pin.
- [Complete retained final run](evidence/milestone-014/kernel-gates/README.txt)
  passed 147 distinct modes from 11:45:08 through 12:00:43 UTC: 37 BIOS, 102
  historical UEFI, one span mode and seven BAR modes. All 225 executable/build/test
  inputs, including the four storage-model Python files, were hashed before the
  first build and matched afterward. Independent review separately repeated all
  eight new modes on the same corrected compiler.
- [Parent receipt validation](evidence/milestone-014/receipt-validation.log)
  checked 498 original local receipt hashes, all 225 live inputs, 147 unique
  successful mode records and 36 compiler-review receipts.
- [Fresh parent actual spots](evidence/milestone-014/parent-spot-checks.log)
  repeated normal BIOS, protected span, stock BAR-state refusal, clean read and
  revoked-window fault. Selected reruns are not a second complete 147-mode run.
  [Retained parent BAR records](evidence/milestone-014/parent-bar-spots/retained-sha256.json)
  preserve metadata/serial/debug/trace and explicitly list omitted generated or
  third-party artifacts by hash and local audit path. Normal images were restored.
- [Final source manifest](evidence/milestone-014/source.sha256) and
  [binary identities](evidence/milestone-014/compiler-binaries.sha256).

The independent compiler runs passed 91 native span cases, including 25 exact
bounds traps, 69 normal rejections and 64 additional mixed-argument ABI cases on
both release and sanitized pins. The initial same-storage restart/unchanged-branch
IR join was accepted without a reproduced invalid-memory access. Static origin,
creation and parent-site identity now rejects that incompatible join, with five
additional IR regressions. Fully closed loop reuse remains permitted; static
sites are not claimed to be unique dynamic generations. The final 950 IR cases,
ten exhaustive-dispatch checks and native groups, including fourteen span cases
and four exact bounds sites, passed independently.

The BAR slice validates one explicitly selected EDK2/q35/NVMe producer profile,
resource ownership and every assigned competing memory BAR, exact live PCI
identity, RAM/arena/ECAM/APIC exclusions and readonly supervisor UC/R/NX mapping.
Seven bounded register observations establish the narrowly permitted inactive
state. Stock firmware command 7 and initialized-controller state are refused.
The clean firmware observed command 2 and zero CC/CSTS/AQA/ASQ/ACQ; write and
revoked-read probes produced exact page faults 14/error 3 and 14/error 0. This
is not DMA ownership or an NVMe queue/namespace driver.

The clean fixture uses EDK2 commit
`fbe0805b2091393406952e84724188f8c1941837`, with exactly the reviewed X64 DSC/FDF
NVMe-driver omissions and exact-endpoint MEMORY-only platform policy. Initial
BME must already be clear; no clearing/reset operation is added. Other endpoints
keep upstream behavior. Official source/dependency hashes, the three-file patch,
notices, build receipts, consumed-input hashes and trace controls are retained in
[supporting evidence](evidence/milestone-014/supporting/SHA256.json). QEMU's PCI
attribute probe did transiently enable and restore BME, so no claim of 'BME was
never enabled' is made. The relevant claim is no NVMe initialization from cold
reset and the validated inactive handoff.

Firmware profiles are explicit per mode: BIOS uses the existing BIOS/QEMU path;
historical UEFI, span and three refusal BAR modes use packaged OVMF; four clean
BAR modes use custom CODE with fresh VARS. Cold config/MMIO traces have positive
stock-firmware and separately isolated MSI-X observation controls. Validator
review closed contradictory failure-marker, late handoff-marker, unaccounted
configuration-write and overlapping-write-interval gaps. Hosted checks passed
142,075 policy and 1,101 complete-reservation cases with fatal sanitizers and
NDEBUG, plus serial 7 positive/859 negative and trace 4 positive/1,003 negative
controls. Supplemental firmware-directory hashes were captured after the initial
BIOS gates began; this timing is disclosed, while each BAR invocation separately
pins its actual tools, firmware and artifacts before execution.

Optional unused GoogleTest/Subhook dependency fetches encountered a retained 403;
no alternate fetch/version was substituted and unused placeholders remained.
A conservative target closure and consumed-input manifest exclude those missing
unit-test dependencies. A local-socket control encountered EPERM; the separately
recorded ordinary-pipe control used no socket/network endpoint or sandbox change.
Its actual timing relative to the hold/clarification is retained, not rewritten.
The control left CPUs stopped, DMA/controller/MSI-X activation disabled and made
one same-value masked table write solely to validate trace observation. It is
not part of Aurora's readonly runtime path. Failed over-limit combined span
fixtures remain historical; a separate bounded program was used instead.

The source distribution omits eight third-party VARS files and 21 generated
ELF/payload/EFI products while retaining hashes and original local audit copies.
The original-local and worker-distribution manifests are historical provenance;
the parent kernel-gates SHA256.json covers retained source/evidence files. See
[PARENT-DISTRIBUTION.txt](evidence/milestone-014/kernel-gates/PARENT-DISTRIBUTION.txt).
Original worker filtered archive SHA256:
`96cb40a9615f042e3e5d9aa5b4b90fa639b7fc8a06589337c601dd014412663a`;
supporting archive SHA256:
`756be74e63daf2f29d5f0cef280b87f55e40caa006b71fb76137512a7d93350b`.
Corrected sanitizer compiler SHA256:
`ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa`;
IR SHA256 `34181616b8dc98bb105e5437f2245d06c1c29ae40087f03db0a6e9d44c616310`.
Leak detection remains disabled for the recorded environment limitation; captured
pipe memory is not covered by the regular-file size limit.

The separately reviewed storage S0 package is integrated under storage/design
with its original 56 sections, XFS extension, traceability, roadmap and host-only
model. Fourteen model tests and eight document mutation controls pass normally
and under Python optimization. No target filesystem, XFS mount/replay/write,
DMA/IOMMU isolation, physical Framework support or complete Rust-level safety/
C-level performance follows from this checkpoint. Isolated next-library work
is intentionally not part of this verified main-tree snapshot.


### Publication byte-identity correction

The [publication audit](publication-integrity.md) identified historical JSON
newline normalization in evidence files only. Original raw source archives and
receipts remain intact; this snapshot uses byte-preserving serialization. The
new publication helper passed seventeen independent normal and optimized tests,
separate from the kernel aggregate. No execution result or failed test is changed
by restoring diagnostic bytes. Remote publication state is not inferred from
local snapshot preparation.


## Milestone015: storage integrity libraries and read-only AMD-Vi

Verified locally on2026-10-03. The complete final emulator run passed158 distinct
modes (37 BIOS,121 UEFI), from13:21:02 to13:38:18 UTC. All257 project inputs and178
external tool/firmware/control inputs matched their pre-run hashes afterward.
Parent verification independently checked all708 original receipt hashes, reran
make test, and executed four fresh actual IVRS modes: architectural-default
refusal, read success, write fault and revoked-read fault. These spots are not a
second full158 run. Normal images were restored. Parent results are in
[evidence/milestone-015/parent/results.json](evidence/milestone-015/parent/results.json).
The release compiler remains SHA256
`2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`.

### Library slice

Checked LE/BE16/32/64 readers and CRC32C/extend execute over readonly byte spans.
The XFS probe accepts only an exact512-byte v5 header geometry and reports header
integrity, not mountability. Complete compiler targets passed release and fatal
ASan/UBSan with950 IR cases and existing semantics, plus254 new native storage
cases and real-fixture replay. Independent polynomial/hardware CRC comparison,
extra boundary/feature tests and strict canonical-hex transport checks passed.
See [storage-library validation](storage-library-validation.md) for commands,
exact pins and the unchanged raw512-byte identity. The original mkfs exit code
was not retained; independent read-only inspection and native replay are separate
evidence. No disk was mounted or physical device accessed. Two duplicate generated
binary fixture receipts are omitted from the source distribution, with explicit
hash mappings to the canonical hex fixture; historical receipt manifests remain.

### Kernel observation slice

The actual168-byte IVRS pairs IVHD10/11 descriptions of one IOMMU. The admitted
profile exactly reconciles its seven requester SELECT entries, live PCI identity,
capability bytes and full16KiB aperture. Contradictory pairs, aliases, IVMD,
requester mismatch, capability mismatch, overlaps and missing-device cases refuse.
Architecture-default refuses MMIO Enable=0 before mapping. The distinct compile-
selected Qemu10_0_13AmdViCold profile reflects the pinned producer's unconditional
MMIO mapping and per-format feature constants; it is not generic AMD equivalence.
Only CTRL/EFR/STATUS reads occur, with expected0/0x29d3/0, through supervisor UC,
read-only/NX mappings. Write and revoked probes fault before prohibited access.
The target NVMe remains inactive/BME-clear. CTRL.IommuEn=0 permits identity DMA;
pt=off alone does not provide isolation. Other firmware bus masters are outside
this bounded observation claim.

Independent review passed eleven fresh actual modes and121,025 host-policy cases
in both release and ASan/UBSan. It closed timestamp/order, post-handoff APIC/IOAPIC
write and missing-device startup validation gaps. Parent make test additionally
passed serial11/4236, trace11/723, provenance11/532 and stack1/27 synthetic controls.
These finite checks are not a proof. The original stack-guard fault is retained;
temporary lifetimes were shortened and inspect_bar made explicit for frame
accounting, keeping the unchanged16KiB stack. Independent .su/linked-call analysis
bounds the reviewed maximum at12,776 bytes including512 bytes of fault reserve.
The original failed ELF/.su was not preserved, so pre-fix function attribution
must not be represented as independently hash-bound binary evidence.

The separate stopped-CPU trace control made one same-zero64-bit CTRL write with
unchanged readbacks. It validates the generic write-event producer only. Its
original whole-run no-interrupt criterion FAILED and remains failed: a startup
APIC passthrough event and its four related records are retained. Pinned-source
HPET/PIT/IOAPIC reset ordering explains that sequence by inference, not an
instrumented call stack. No rerun erased the failure, no blanket event whitelist
was introduced, and no claim of globally clean interrupt state follows. Named
amdvi_mmio_write absence alone is insufficient because valid writes use the
generic producer. See the [independent report](evidence/milestone-015/kernel-support/independent-review/review.md).

### Distribution and remaining limits

Original filtered kernel archive SHA256
`53f5296dd4ca0a14793cc0b84742da5f131dd6cc948bfacde07cfd3e0978fdf5`;
supporting archive SHA256
`ced086117b5720d41253ce766e3e5c599dcd4cee59cdaef3beeca11ac9076e01`.
The source distribution omits30 third-party VARS copies and54 generated ELF/bin/
EFI files while preserving original local artifacts, hashes and explicit omission
maps. Parent spot outputs have equivalent explicit omission records. Original
worker manifests are historical; current distribution manifests cover retained
bytes. Serialization preserves raw text bytes, including diagnostic CRLF.

No active IOMMU mappings, NVMe queues, target filesystem, XFS mount/replay/write,
SMP, physical Framework qualification, full-language safety proof or C-performance
equivalence is established. Isolated mutable-byte and resource-hardening work is
not included in this snapshot. Publication is separately permission-gated; local
verification does not imply a remote commit or draft PR.


## Milestone016: compiler fact storage and real page-pin ownership

Verified locally2026-10-03. The final exact-source run passed162 modes (37 BIOS,
125 UEFI), from14:40:39 to14:58:39 UTC. All266 project inputs and182 external pins
matched pre/post hashes. Parent independently checked720 raw receipt hashes,
reran make test and1,526 seed404 semantic cases, then freshly ran pin-cancel,
pin-fault and normal UEFI profiles. Normal images were restored. These spots are
not a second full162 run. See [parent results](evidence/milestone-016/parent/results.json)
and [kernel receipts](evidence/milestone-016/kernel-gates/results.json).

### Representation-only compiler change

Release SHA256 `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`;
instrumented compiler `805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf`.
The two initialized/maybe-initialized scalar-slot fact sets now use checked dense
bitsets over the existing validated slot universe. Other lifetime/provenance facts
and CFG/worklist behavior remain unchanged. Existing frame validation bounds the
universe to65,536 slots; two fact payloads are at most16,384 bytes per retained
state. This is not a total compiler memory bound or a new language admission cap.

Author and independent checks cover set-operation equivalence,956 IR cases,
source/native/module/host-I/O regressions and exact before/after outputs. Independent
review executed37,126,294 fatal-sanitizer fact checks and831 exact compiler
comparisons. All eight candidate benchmark programs execute42. The benchmark
originally could report success for an always-failing candidate; it was corrected
and independently tested with always-fail and wrong-output controls.

Controlled dense workload RSS fell510,588 to62,976KiB with identical assembly.
A valid sparse-prefix source instead rose189,692 to210,048KiB (~10.7%); observed
wall time did not worsen in that sample. The stronger all-unused65,536-slot case
is IR-only. These are bounded individual measurements, not universal throughput
or memory claims; other state/AST/resource growth remains open.

The complete release target passed. The full instrumented target initially failed
when GCC compiling the large IR-test translation unit was SIGKILLed; cause was
not established. A serialized same-flags retry under2GiB failed cleanly with virtual
memory exhaustion. Both receipts remain. An explicit IR-test-only -g1 debug-info
accommodation then completed in67.21s at1,662,392KiB RSS. It retained -O1, fatal
ASan/UBSan and frame pointers; compiler/fact-model/host-I/O builds retained -g.
All runtime gates executed and passed. Integrated replay used exact-source pinned
instrumented binaries and reran the affected suites. This is not an assertion
that the original full-debug build passed. [Compiler evidence](evidence/milestone-016/compiler-facts/README.md)
records flags, source identities, partial failures and distribution omissions.
No mutable-byte-view candidate was integrated.

### Kernel page ownership

A static fixed-capacity ledger consumes actual move-only PageLease objects,
binding owner DomainHandle/incarnation and non-wrapping entry generations.
Clean cancellation is permitted only before any publication and scrubs every
page before releasing any. Uncertain-publication injection is test-build-only;
production exposes no publication or completion operation. Quarantine is
absorbing and survives service destruction/restart. No scalar service value can
mint retirement evidence. All origins retain existing CPL/CR3/ProgramRun checks.

Independent hosted normal/fatal-sanitizer checks passed165 ordinary and294
bounded-generation cases, production API absence and four invalid configurations.
Receipt tests passed4 positives/236 negatives in Python and optimized Python,
plus24 independent mutations. Four independent actual modes passed on the final
compiler before the full162 run. The actual fault mode observes service slot1
incarnation2 to4, stale original owner/token rejection, clean peer42 progress,
new-incarnation compiled42 and exactlytwo retained quarantined pages. Original
pre-strengthening development receipts remain distinct. Explicit exhaustion
checks do not steal domain stack frames. Trusted allocator/backing lifetime,
singleCPU and static ledger persistence remain assumptions; reconstructing a
trusted allocator over the same physical range is not globally prevented by this
bootstrap API. See [pin contract](../kernel/uefi/PIN-OWNERSHIP-CONTRACT.md).

The accompanying finite host model is a prerequisite design experiment only:
its hardware completion observations are assumed and unavailable in the actual
kernel. The implemented ledger does not use simulated observations to release
uncertain pages. There is no IOMMU programming, DMA publication, NVMe queue,
filesystem mount/replay/write or physical device support in this milestone.

### Distribution

Filtered kernel evidence archive SHA256
`522219f7909b356cc1be1951bc2c0c90983bb7519cce862e658332936045c5bc`;
supporting archive SHA256
`4cdd2b828f5bc9e546ffd51ac12cc24c7f0bed36c0f402b92515329d618ef625`.
Thirty firmware copies and54 generated kernel products are excluded with explicit
hashes; supporting evidence excludes16 generated products. Compiler review
excludes306 generated artifacts while preserving an unchanged full audit archive
outside source. Original manifests refer to preserved local originals; current
distribution SHA256 manifests describe included bytes. Source serialization must
remain byte-preserving. Remote publication remains separate from local acceptance.


## Milestone017: strict readonly UTF-8

Verified locally2026-10-03. The additive library/test delta introduces std.utf8,
a native example, bounded tests and contract; compiler/Makefile only registers
its target/flags. The existing140 tracked compiler/runtime/script/root-Makefile/
old-fixture inputs remain byte-identical. Release compiler SHA256 is still
`14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`;
instrumented compiler remains
`805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf`.
Library implementation SHA256:
`6ad8d1c11ce26197932e2118151a7761e518ea2db7dc64a1fd1a3e956761f31c`.

The contract pins Unicode17.0.0 chapter3 §3.9 D92/Table3-7. Checked range validation
precedes all reads. Decoding rejects overlong/surrogate/out-of-range/forbidden
byte forms, accepts all scalar values including noncharacters/NUL/BOM, and strips
nothing. Already-invalid available bytes reject immediately even when later bytes
are absent. Otherwise a proper incomplete prefix reports truncated for final input
or need_more for nonfinal input, consuming no incomplete scalar. The API is
stateless: caller retains/replays the tail. Result constructors are ordinary data,
not certificates or authority. See [the complete contract](utf8-contract.md).

Author bounded tests passed406 checks/39 fixtures per pin, using runtime loops
and batches for all1,112,064 scalar values, all one/two-byte inputs and24,200 longer
boundary combinations. Independent native review passed1,367,060 cases per pin,
plus seven report/capacity groups and nine semantic-rejection groups. Corpus counts
overlap and must not be summed as unique coverage. Independent Table3-7 checks
include immediate-invalid ED/E0/F0/F4 second-byte prefixes in both final modes;
Python incremental-decoder timing is not the normative contract. Native release
and instrumented-compiler outputs agreed; generated machine code itself is not
ASan-instrumented. The example actually decodes/validates and returns42.

Eight final isolated commands and eight integrated commands had known zero exits
with stable inputs. A prior exec transport outage lost its shell session status
although terminal logs showed PASS; these remain historical unknown-status records,
not inferred successful exits. Later known-status verification is recorded
separately. Parent verified429 curated evidence hashes, reran make test and freshly
executed runtime-span, runtime-pin-fault and normal UEFI profiles. Images restored.
See [parent results](evidence/milestone-017/parent/results.json) and
[UTF8 evidence](evidence/milestone-017/utf8/README.md).

No fresh full162 emulator run was performed for this pure-library change. M016
remains the historical full-suite checkpoint for unchanged runtime implementation.
This milestone does not implement UTF-8 encoding, owned strings, normalization,
grapheme segmentation, path policy, rendering, terminal behavior, filesystem I/O,
DMA isolation or physical hardware qualification. Public documentation updates do
not change the historical source/test identities preserved in integration receipts.


## Milestone018: owned UTF-8 scalar encoding

Verified locally2026-10-03. An additive std.utf8 extension encodes one u64 scalar
into a private copied std::array<u8,4>, logical size and recoverable status. Only
library/std/utf8.au and compiler/Makefile changed among implementation/test baseline
files, with one new example, bounded test and contract. The prior decoder text
and all246 captured inputs outside the delta stayed byte-identical, including
compiler, kernel, scripts and old fixtures. The release/instrumented compiler
pins remain14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980
and805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf.
The extended module SHA256 is
`a9448bed52974ca1e690b9a10e86a5f879c5b24f475a12ab1ec079e4e97bc646`.

Factory-produced valid scalars yield canonical shortest UTF-8 bytes, size1..4 and
zero padding. Surrogates and values aboveU+10FFFF produce failure, size0 and zeros.
NUL is valid size1. byte_or validates logical index/status/width before array
access; bytes_or_zero returns an independent value with unused tail zeroed. Public
constructors remain ordinary report data. Invalid widths/status normalize to
failure, but a valid-width forged success report can still carry non-UTF8 bytes.
No validation certificate, borrow, mutable span or raw capability is introduced.
See [owned encoding contract](utf8-encoding-contract.md).

Author final11-command aggregate and integrated10-command targets all exited0
with stable inputs. Author186 checks/35 fixtures and24 rejection compilations
passed both compilers. Independent review compared actual output for all1,112,064
scalars with Python strict encoding, a separate arithmetic oracle and Unicode17
Tables3-6/3-7, plus10,375 invalid values per compiler. It also passed8,784 report/
copy cases, a mixed-six-argument ABI fixture,16 exact native bounds sites and18
compile rejections per pin. Those overlapping observation counts are not unique
population totals. The native example actually encodes/observes bytes and returns42;
release/instrumented compiler example assemblies are identical. Generated native
code itself is not ASan-instrumented. Fixed-value copies are explicit; no universal
zero-cost or performance assertion is made. One stale preliminary contract hash
was corrected with its original metadata retained historically.

Parent independently checked97 curated receipt hashes and246 unchanged inputs,
reran make test, then freshly executed runtime-span, runtime-pin-fault and normal
UEFI profiles. Normal images restored. [Parent results](evidence/milestone-018/parent/results.json)
and [integration evidence](evidence/milestone-018/utf8-encoding/README.md) distinguish
author, independent and parent outcomes. No fresh full162 suite was run for this
library-only delta; M016 remains the historical complete kernel checkpoint.
Original binary/output audits are archived outside distributed text evidence with
explicit omission records. This milestone does not implement owned strings,
normalization, graphemes, terminals, XFS mounting, hardware DMA or physical support.


## Milestone019 — verified functional checkpoint, 2026-10-03

The full integrated run began 17:28:21.332659 UTC and completed
17:46:44.819577 UTC: **166 distinct modes, 37 BIOS and 129 UEFI-family**.
All 288 project input hashes and 183 external pins were unchanged; all 757
original receipt hashes verified. The coordinating build separately passed
`make test`, `runtime-table-readback`, `runtime-table-quarantine` and `normal`.
Independent guest review passed all four new actual modes. Normal images were
restored with test-inspector/code absence checks. No claim of a second full run.

Compiler SHA256: `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`.
Instrumented compiler SHA256: `805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf`.
Project manifest SHA256: `c563aa97e3c585cca5688331c62748d1e16a2f71d95b4cc8fbf8ab721f0f023b`.
External manifest SHA256: `ef6336767f277b6cbf36af3eed36986300b9cf6a8eedd684a771bf40c662d651`.

### Dormant table scope and corrective evidence

The AMD310Host4KBus0 profile constructs 256 dense DTEs in two 4 KiB pages,
one 512-entry leaf page and at most two data pages, five frames/three ledger
entries. Canonical holes are V=TV=1, Mode0, read/write denied. The exact RID0x10
mapping has DomainID1 and checked root/leaf alignment, widths and ownership.
IV=0 does not isolate interrupts. There is no MMIO/base/enable/BME/queue,
publication or hardware-completion API. All guest markers are CPU-byte or
software-model observations, not device DMA.

The four modes cover full readback, rejection, exhaustion and quarantine. The
stack bound is 13,136/16,384 bytes including 1,024 bytes of fault reserve, derived
from raw `.su` and linked call paths. Phase separation fixes the earlier nested
ACPI/PCI path; wrapper/lambda call edges and a forbidden nesting control are
included. No stack/page budget was widened. Initially invalid privacy tests
failed for the wrong C++ reason; preserved originals are superseded by valid
member-pointer probes and compiling public-mutant controls. Independent host
checks include all 98,304 table-bit corruptions and scrub/reentrancy controls.

### XFS geometry scope and corrective evidence

`library/fs/xfs_geometry.au` SHA256
`c67c03928e0d4cf5896178906bd447523ec15b57cc95c4ade8b8330305a77864`.
The result contains 42 scalar leaves, 336-byte layout, no device authority.
Independent review repeats the same 2,016 headers on both compiler pins:
451 narrow successes and 1,565 recoverable failures per pin, not summed coverage.
It checks all leaves, copied/forged reports, input stability, ten killed semantic
mutants and privacy/lifetime/artifact-preservation controls. Author coverage is
586 headers, 25,198 raw observations and 51 mutation controls per pin; these
sets overlap independent coverage. The final recipe/docs addendum and all 127
curated receipt hashes and 90 protected inputs passed coordinating rechecks.
Initial LeakSanitizer failures under ptrace remain retained; later runs disabled
only leak detection, retaining fatal ASan/UBSan. An incorrect expected diagnostic
was fixed in the test, with library source unchanged. Optional compiler pinning
records actual hashes and rejects a supplied wrong hash. Author negative-test
coverage is existing-output preservation, not absent-plus-existing coverage.

The old checksum probe is unchanged. Error priority, supported masks, overflow
checks and encoded AG addresses are detailed in the
[XFS contract](xfs-geometry-contract.md). Reports describe bytes only: no
mountability, clean log, replay, read/write support or storage-capacity assurance.

### Evidence and preservation

[Coordinating evidence](evidence/milestone-019/parent/README.md),
[full kernel evidence](evidence/milestone-019/kernel-gates/README.txt),
[kernel supporting review](evidence/milestone-019/kernel-support/) and
[XFS evidence](evidence/milestone-019/xfs-geometry/) preserve the bounded text
receipts. Original generated binaries/images are retained locally and omitted
from source with exact hashes/reasons; original manifests remain distinguishable
from source-included manifests. An initial staging-layout mismatch was rejected
before adoption and documented. No AMD PDF or copied specification tables are
redistributed. Independent distribution review caught four copied reference extracts
in the initial supporting bundle. They were moved outside source unchanged, with
exact omission hashes/reasons; the initial byte-valid archives remain unaccepted
and are not publication sources. The corrected source archives are byte-preserving
and independently audited. Five inherited complete QEMU C references were also
omitted from the M019 source distribution, with unchanged external originals,
source URLs, hashes and distinct historical/current manifests retained;
the documented archive-only 0700-to-Git100755 script representation never changes
the live source permission. Functional verification is not remote publication.


## Milestone020: bounded concrete nested generic values

Verified locally 2026-10-03. The parent adopted 18 exact reviewed paths from the
isolated candidate after checking original base hashes and candidate hashes.
Only four compiler implementation headers changed (`parser.hpp`, `types.hpp`,
`templates.hpp`, `modules.hpp`); no kernel/runtime implementation changed. The
extension resolves fully concrete nested template-id children before parents and
reuses existing nominal identity, visibility, class/value-copy and metadata checks.
It adds no IR instruction, backend operation, ABI or calling convention.

Template-id nesting four is independent of class-containment depth four. Existing
64 leaves, 64 template definitions, 256 total concrete instances including inner
instances, and literal capacities 1..64 remain separate bounds. Dependent template
bodies, recursive instantiation, deduction, owners/references as arguments and C
compatibility remain excluded. The native token/source-range example returns 42
after checking independent copied token bytes and range data. See the
[nested-value contract](../compiler/NESTED-VALUES.md).

### Exact identities and compiler evidence

- Release compiler SHA256:
  `e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6`.
- Fatal ASan/UBSan compiler SHA256:
  `78379d081bfae56608a6a60e72bc290e9abd68e88b1a9c3e96f93d25b007cfb5`.
- Frozen baseline compiler SHA256:
  `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`.
- Frozen implementation manifest SHA256:
  `4a9847eddc4419cf032ac449ec63f64bee808ca480fdaf3512616e39c56ca9a9`.

Both complete compiler targets exited 0 on the final isolated inputs. Each
includes 313 focused checks (129 native returns, 24 exact-site bounds traps,
80 rejection fixtures run with absent and existing outputs), 960 typed IR cases,
10 exhaustive-dispatch controls, 18 native receiver-array IR cases and all prior
compiler/library/numeric/model suites. The alternate seed repeats the same focused
contract and is not additive. Instrumentation applies to the host compiler/C++
tests; emitted native Aurora machine code is not itself ASan-instrumented.

Serial compiler builds retain a 2 GiB address-space cap, CPU120/130s, wall180s,
regular-file512MiB/core0 limits. Runtime ASan processes do not inherit the build
address cap. Full-debug instrumented compiler build: 45.88s / 1,445,480 KiB peak
RSS. Instrumented IR-test build uses the retained `-g1` debug-only accommodation:
63.40s / 1,655,932 KiB peak RSS. Fatal ASan/UBSan checks were unchanged;
LeakSanitizer alone remains disabled for the known tracing limitation. The initial
release build used 2,304 MiB; the final release reproduction used 2 GiB and matched
the release hash byte-for-byte. These measurements are finite observations, not
whole-task resource bounds or equivalent-C performance claims.

The baseline-compatible differential corpus has 1,639 invocations from 1,398
source hashes: all 821 accepted assembly outputs are byte-identical and all 818
rejection statuses agree. Independent review passed the same 78 adversarial cases
on each compiler (31 native successes, 47 ordinary rejections) and an independent
694-source arithmetic differential control (520 accepted, 174 rejected), with no
status or assembly difference. These overlapping corpora must not be summed into
unique coverage or interpreted as whole-compiler safety proof. No actionable
implementation defect was reproduced within the reviewed scope.

### Parent integration and restoration

The parent rebuilt the adopted release compiler, verified the exact release pin,
and completed `make test` with exit 0. It then ran three actual UEFI profiles:

- `./scripts/kernel-uefi-smoke.sh runtime-span`: exit 0; compiled readonly-value
  behavior returned 42 and restored the domain/root.
- `./scripts/kernel-uefi-smoke.sh runtime-pin-fault`: exit 0; retained compiler
  fault containment and CPU-only pin-ledger contract passed.
- `./scripts/kernel-uefi-smoke.sh normal`: exit 0; final clean language result 42
  and `AURORA_UEFI_OK`, with the normal image restored.

The 359 captured source inputs and 183 external pins were unchanged throughout
these gates. Final acceptance documentation is a separately recorded text-only
change after testing; no implementation/test input was changed. This is three
fresh selected profiles, not a fresh full 166-mode qualification. M019 remains
the historical full-suite evidence for the unchanged kernel implementation.
No physical AMD support, device DMA, active IOMMU, interrupt isolation, XFS mount,
self-hosting, owned-string or full standard-library capability follows.

### Historical failures and distribution evidence

Original nonzero development attempts are retained: stale nested-argument
rejection expectations, a not-yet-written focused suite, a reserved-name fixture,
a missing pinned XFS proposal document in the source-only candidate, and an
incorrect source-first CLI assumption in the differential wrapper. Each is
identified in the unchanged candidate verification record with its own exit/log;
none is relabeled as a pass. The unsupported assignment-expression fixture and
other early focused logs also remain preserved.

[M020 evidence](evidence/milestone-020/README.md) includes byte-preserved candidate
and independent receipts, exact parent logs/statuses and source/external manifests,
source-delta provenance, copied-file hashes and an explicit omission ledger. The
original evidence ZIP contains 152 hash-listed payload members plus its manifest
(153 ZIP entries); all member hashes match the originals. Generated binaries,
assembly products, binary archives, full build/tmp trees and duplicate source
archives remain outside source. No third-party reference extract or secret is
added. Historical candidate acceptance statements remain labeled as historical.
M019 archives are immutable and unchanged. Source archive audit/publication status
is recorded separately from functional acceptance; no remote action is implied.


## Milestone021: bounded explicit copied-value function templates

Verified locally 2026-10-03. Parent adopted exactly 18 base/candidate-hash-checked
paths and rebuilt the identical reviewed release compiler. The implementation
adds finite namespace-level explicit one/two Scalar/Value function-template
instantiation and real std::make_pair<T,U>. It deep-copies concrete function ASTs,
uses existing exact nominal authority and copied-value boundaries, and adds no
IR instruction, backend operation, runtime generic representation or ABI.
The [contract](../compiler/FUNCTION-TEMPLATES.md) defines eager structural/privacy
checks versus deferred ordinary validity for unrequested tuples. Class/function
graph limits are combined 64 definitions/256 instances; class nominal/containment
depths, leaves, array capacities and frames remain separately checked.

### Exact pins and finite compiler evidence

- Release compiler: d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64.
- ASan/UBSan compiler: 423db8bcf0642263e445582107c73f967decdc13132f2bd98a973fce2db03d0f.
- Immutable M020 compiler: e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6.
- Compiler-source manifest: 7d073cd0ec17d7da500baea3b66e6cf810fe21af235d6e99cc5ea4924df4d65e.
- Adoption manifest: 6e0dbfb3c5d9a15755d741b7a8c78f1ef48578a08c99136c3c3c6e9e1fb4c48b.

Both complete compiler targets exited zero. Each includes 227 focused fixtures /
349 executions: 81 native returns, 24 exact-site traps and 122 negative fixtures
run with absent and existing output. The same focused suite passed a fatal-abort
sanitizer replay. The aggregate also passes 964 direct IR cases, ten exhaustive
controls and all existing native ABI/library/numeric/module/host-I/O suites.
Independent review passes 46 fixtures (24 native, 22 negatives) plus 22 absent-output
checks on both release and fatal instrumented compilers. Owner M020 differential
checks 232 unchanged contract fixtures (224 source hashes): 153 byte-identical
accepted assemblies and 79 matching rejections, plus 36 unchanged example/program
sources. Corpora and repeat runs overlap and are not additive unique coverage.
Two formerly blanket function-template negatives changed to still-unsupported
forms; the newly accepted unused definition is explicitly excluded from the final
differential, with the original expected difference retained.

Instrumentation covers the compiler host/C++ tests, not generated native Aurora
machine code. ASan/UBSan errors remain fatal; leak detection alone is disabled for
the documented tracing limitation. Final C++ builds use the locked serial wrapper:
2 GiB address space, CPU120/130s, wall180s, regular-file512MiB, core0. Runtime ASan
does not inherit the build address cap. Full-debug sanitizer compiler build took
46.62s / 1,437,796 KiB peak RSS; instrumented IR build peaked at 1,657,196 KiB with
the retained IR-only -g1 accommodation. Initial exploratory observer compiles
lacked that explicit wrapper; the initial release build had only the shell address
cap. These exceptions remain disclosed rather than relabeled as bounded builds.
No whole-compiler safety/resource proof or equivalent-C performance is claimed.

### Reproduced defects and retained development failures

Independent review reproduced parameter-qualified names hidden in argument trees,
including namespace collisions, and receiver-method precedence incorrectly blocked
by unrelated function-template names. Recursive structural-name validation and
receiver-aware lookup fixed them; final independent release/fatal replay passes.
Owner tests also exposed fixed exported-signature privacy leakage, corrected by
eager recursive visibility checks. Original failures, reproductions, fixes and
final source pins are retained byte-for-byte. Other preserved failures include
unavailable /usr/bin/time, a non-empty-constructor test outside the existing
contract, initially omitted pinned XFS proposal dependency, and a new IR check's
wrong expected diagnostic. No failing attempt is silently recast as a pass.

### Parent integration, curation and archival boundary

Fresh parent make test exited zero on the rebuilt reviewed release pin. Actual
runtime-span, runtime-pin-fault and final normal UEFI profiles all exited zero;
normal returned 42 with AURORA_UEFI_OK and restored the normal image. All 363
captured source inputs and 183 external pins stayed unchanged through these gates.
Final acceptance documentation is a separately recorded text-only change afterward;
implementation/test/fixture bytes remain the reviewed ones. This is three fresh
selected profiles, not a fresh full 166-mode run. M019 remains the historical
full-suite checkpoint for unchanged kernel implementation.

[M021 evidence](evidence/milestone-021/README.md) provides exact copied-file mapping,
byte hashes, parent statuses/input manifests, independent review, original failed
receipts and capped-build exceptions. Generated assembly/binaries/archives and
sentinel binary outputs remain unchanged outside source with exact omission
inventories; archive-member JSON receipts describe external generated products.
No binary product, reference extract, secret or carrier helper is added to source.
M019/M020 archives remain immutable. Raw-source archive/canonical Git audit is a
separate bounded tree-only gate; no large JSON export, publication, hardware,
active DMA, filesystem mount or native self-hosting claim follows.


## Milestone022: copied method values and complete emulator regression

Verified 2026-10-04. The new [method-value contract](../compiler/METHOD-VALUES.md)
permits immutable copied class parameters on ordinary methods, alongside scalar/
enum values, and adds the real std::array exchange member. A NEW private combined
receiver/argument-record/result ABI reuses existing typed IR instructions while
keeping each authority separate. Six explicit parameters, 64 leaves per class
boundary, four-level class/template limits, existing graph budgets and the source
frame cap remain independently checked. This is not a foreign ABI or source pointer.

### Exact compiler and source identity

- Release compiler: e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e.
- Fatal host ASan/UBSan compiler: d3033d68ad6308030a057c9eaf2b2e258b15e245ca84a22cc2fce1873847adcd.
- Immutable old-input M021 compiler: d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64.
- Candidate final manifest: 552a679b7ba80caf98c0d98d37ec212fad95f830b1c14677b184f3bc89ec8d5c.
- Integration source manifest: 6f82683653b92910965b1343cac8b63ea355c67f125067ebc7f9018e0b9213c0.
- Kernel results: 4f33b9e490f43342ba55f8b65c48df5fb47745db4d8e87688bd225e4194b0050.
- Kernel receipt manifest: 513237c77a1765398e61fa3bf74ccbb9322ec5f24a39f45c5818cd81c6af8a67.

Parent adopted exactly 28 sealed source/document paths and rebuilt the reviewed
release binary. Original candidate documents remain snapshots of the earlier
pending integration state. Functional-source/test/library/fixture bytes stayed
unchanged through the later documentation-only finalization identified separately.

### Finite compiler coverage and limits

The focused source suite has 152 fixtures/219 executions, including 72 full-width
native returns, 13 exact-site traps, and 67 rejections with absent/preexisting
output controls. New direct IR has 51 cases (5 accepted, 46 malformed rejected).
New native ABI has 21 cases with independently handwritten assembly on one side
of each boundary, both directions, 3,072-byte maximum records, alignment/slot/
clobber controls and eight legacy modes. The historical IR target retains 964
cases with five explicitly recorded source-contract/diagnostic migrations.

Independent review adds 17 source probes, 15 qualified-self controls and all 256
capacity/type array models per compiler pin. Exact isolated 48-step stress passes
28 native models per pin. Old-library differential checks 227 contract fixtures
(217 source hashes; 105 accepted/122 rejected) and 37 unchanged example/kernel/
library-example inputs using frozen old library bytes on BOTH compilers. Default
scalar semantics uses 630 cases per release/fatal pin; release stress uses 1,526.
These corpora and repeat runs overlap and must not be summed as unique coverage.

Complete frozen release and fatal host sanitizer targets exit zero with before/
after source identities unchanged. C++ builds alone are serialized with a 2 GiB
address-space cap. Only the large historical IR sanitizer binary uses -g1 debug
metadata; address/undefined instrumentation, no-recovery and fatal halt/abort
remain enabled. LeakSanitizer alone remains disabled as in prior milestones.
Sanitizer runtime has no address-space cap. Instrumenting the host compiler does
not instrument emitted Aurora programs or prove whole-language memory safety.

### Preserved failures and review qualifications

The initial bare injected array spelling failed. A temporary parser exception
was abandoned after independent review demonstrated the existing qualified
std::array self spelling; parser.hpp is byte-identical to M021. Original failed
source/diagnostics, temporary build receipts and corrected frozen outputs remain.

The first concurrent sanitized model stress process was SIGKILLed without a
diagnostic. OOM is plausible but unproven. The exact isolated input then compiled
and returned 42 in 3.505 seconds with 1,217,592 KiB peak RSS; complete isolated
28/28 stress passed. Both attempts are preserved. No universal resource bound is
claimed. Independent addenda close two test-quality gaps: the original mut<i64>
fixture tested an invalid spelling, and the original extraction fixture named an
absent method. Separate real mutref<i64> and declared-inspect extraction controls
reject on both pins with output preservation; an inspect call returns 42. Only
the addendum is credited for those two exact semantic controls.

### Fresh complete integration and independent receipt replay

From 03:44:26.818302 to 04:01:54.208614 UTC on 2026-10-04, all 166 original modes
passed: 37 BIOS, 111 direct UEFI, 7 BAR and 11 IVRS. Two further normal BIOS/UEFI
boots restored the images, making 168 observed executions rather than 168 unique
modes. Wrapper statuses are zero; QEMU statuses 33/35 retain their expected mode
semantics. All 368 source and 236 external input records stayed unchanged before/
after. The separate fresh parent make test also passed.

Independent review verified 935 receipt hashes, 920 per-mode file records, the
permission manifest, live restored image identities and absence of dormant table
test markers/symbols. Every original retained validator replay passed (166 modes
plus two restorations), including unchanged BAR/IVRS trace/provenance checks.
All project kernel/scripts/validators match the historical M019 bytes. The
existing AMD-Vi broader whole-run zero-interrupt and named-write-event criteria
remain false; only the reviewed bounded stopped-CPU CTRL witness gives coverage.
No new device authority or hardware qualification follows.

A preparatory inventory mismatch (384 entries instead of 368, from 16 historical
storage-evidence files) failed before any emulator mode and was corrected without
changing source or test assertions. The reviewed runner has an unguarded failure-
finalization path that could leave unsealed summaries after a missing input;
it did not trigger. The completed run restored images, recorded errors=[] and
sealed its receipts. This successful run is valid; future failure-sealing should
be guarded. Hashes provide artifact identity, not signed execution attestation.

### Curated evidence and distribution boundary

[M022 evidence](evidence/milestone-022/README.md) maps each copied receipt to its
original bytes/hash, retains every eligible trace and every failure, and inventories
omitted generated assembly/binaries/archives/sentinel outputs retained externally.
Build logs are mapped to build-receipts so the source archive's build exclusion
cannot silently omit them. Frozen old-library files are intentional differential
inputs. No downloaded specification/reference extracts, secrets or rejected carrier
helpers are added. Earlier evidence and M019/M020/M021 archives remain unchanged.

Raw/canonical source and actual Git validation use the independently reviewed
M020/M021 tree-only path with unchanged 1 GiB payload, 16 MiB member and 512 MiB
address-space limits; no full JSON export or payload spool is generated. The
existing 0700 negative-control script retains live/raw mode; only canonical Git
representation is 0755, explicitly documented by the new M022 archive note.
Archive/review receipts remain outside the source tree to avoid recursive hashes.
No network, authentication, remote publication, active DMA, filesystem mount,
physical-device, native self-hosting or equivalent-performance claim is made.

## XFS-only M022 integration checkpoint — 2026-10-04

Baseline: accepted commit `53cb2fe5d9222bce5a51a2d176edf8f8321960c7`.
This checkout materializes only the384 exact product files listed in the
[baseline subset receipt](evidence/xfs-root-m022-20261004/baseline-subset.json).
Earlier docs/evidence remain on the remote baseline and are intentionally omitted
from this local source subset. An incremental publication must preserve them.
No compiler implementation, kernel code, device profile or emulator script changed.
The copied M022 compiler is checked against SHA-256
`e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.

Prior fresh XFS standalone203/2,233 and API77/12 gates, copied-report boundary review,
and portable Make review establish the input delta. They are not substitutes for
this checkout's fresh top-level `make test` and independent delta review.
The ordinary `compiler test` target now invokes the full XFS gate using the actual
compiler pin and explicit source/fixture/artifact roots. A fixed preflight rejects
symlink/missing/nondirectory roots before creating any output. No new QEMU run or
166/170-mode milestone is claimed by this filesystem-only checkpoint.


The fresh parent `make test` completed with exit0 on the unchanged M022 binary;
all396 non-build input files and45 captured external tool/helper/runtime files
stayed unchanged across the successful rerun. The tool inventory was first taken
during an earlier attempt and then fully rechecked before and after this rerun.
The aggregate ran the complete compiler, image, hosted-kernel/validator, storage
model and630-case semantics gate (including128 generated inputs), with full
XFS203/2,233 and API77/12 checks.
No new emulator mode was run for this checkpoint. Prior M022 emulator evidence
remains historical and is not relabeled as current XFS-only execution.

The first attempt was incomplete: its host disk-accounting supervisor raced a
removed temporary semantics output, so final make exit was not captured. It is
retained as a failure, not counted as a pass. The supervisor now tolerates only
disappeared files/directories during accounting and terminates/waits an owned
child on failure; four deterministic controls pass. A complete fresh aggregate
rerun supplies the successful receipt. No Aurora implementation change was needed.
See [curated receipts and limitations](evidence/xfs-root-m022-20261004/README.md).


## Aurora interrupt-budget policy checkpoint — 2026-10-05

The kernel delta is based on accepted ordinary-function-overload PR21 main
`758458e8258b76b24f7c29e06a2ce01a83766b68`, tree
`df584b38be517aa444257c90f5c7897487d484f8`. Publication is an explicit narrow
path overlay; unlisted remote historical files must remain in that baseline.
The tested 533-file manifest is
`627fb53116ec13b72cd3d755dd190abb2f6ab59cc3cecb6e4560cd3cefbb0c25` and
accepted rebuilt compiler is
`8d4099fe52a19307a266a6cbe5191203307462877cc94c7b6f3dae78f817c631`.

The Aurora `kernel::interrupt_tick` class/enum API computes the bounded interrupt
count transition and selects resume/exhaust. A private scalar bootstrap transport
returns that result to the existing UEFI timer path. Domain/frame/epoch/ISR
checks, timer hardware, live storage and cancellation remain trusted C++/assembly.
The BIOS scheduler is unchanged. No general scheduler/SMP, physical-platform,
whole-language safety proof or equivalent-performance result is added.

The successful acceptance chain is entirely fresh and same-root:

- Fresh compiler build returned the exact accepted binary.
- Full serial `make test` passed. Kernel-native observations include 104,120 policy
  cases, 815,301 decoder cases and ten diagnostic/output-preservation rejections.
  Full package identity/manifest/graph gates and existing regressions also ran.
- All 170 distinct actual emulator modes passed: 37 BIOS, 115 UEFI, seven BAR and
  eleven IVRS modes. All four new policy fault modes returned the required exit35.
  The output-fault image matched all five independently reviewed linked members
  before QEMU and exercised the ordinary defensive decoder.
- Two additional fresh normal BIOS/UEFI boots each returned exit 33. Final normal
  images, source/runtime/control identity, complete evidence sealing and owned
  process cleanup passed independent review.
- The full native build remains in a verified 21,429-member preservation archive.
  The final emulator seal covers 1,207 paths. Sampled counted allocation peaked
  at 998,391,808 bytes under the three-root 3 GiB cap. Sampling is not a hard quota.

The earlier first full-170 attempt failed in the live build-size census after 46
completed modes. Its planned continuation later stopped after 88 new completed
modes, through global ordinal134, during the following image build; it has no
successful terminal or final normal pair and its ownership fence remains
unresolved. Those records are preserved with their actual statuses. The successful
fresh run borrowed no prefix or normal boot from either attempt.

Only result documentation and the concise evidence index changed after the
accepted tests. Runtime, implementation, compiler, fixture, launcher and test bytes
remain those of the tested freeze. See the [receipt index](evidence/kernel-budget-policy/README.md)
for exact terminal/review/source hashes, artifact-relative paths and limits.


## Verified readonly byte-window integration (2026-10-05)

The checked named-span subspan feature completed isolated full release/fatal
ASan/UBSan compiler targets and independent source/IR/native provenance review.
Fresh combined PR22 integration rebuilt release compiler `b3c8d58565844e1b671d1589975985374b17387b405543e05762631b95552580`,
passed the complete native aggregate and all170 actual emulator modes, then two
additional actual normal BIOS/UEFI restoration boots. Both normals exited33.
All540 tested source files and the declared host/runtime/firmware input closure
remained exact. Independent review replayed all172 retained validators, verified
native-original preservation, final normal images and closed ownership receipts.

The tested-source manifest is `11d804796114f1e0bdf8f6fc1a51db7db170cfeb509d42e7328ed6abe321782c`.
The full-native terminal is `0f4df6ecd6080fab53dc257f73b701a4d4efa850a571e6e56bd0881abc556611`;
the emulator terminal is `60100263b54dd87804d553b2f82cc884f9cdb96133211d61ed6cebb7d2ed3c46`.
The [results record](readonly-windows-integration-results.md) and
[receipt index](evidence/readonly-windows/receipts.json) distinguish the final
documentation-only checkpoint, earlier preserved failures and exact review pins.
The qualified replacement firmware remains exact. No physical-device, general
heap/returned-view, universal safety/resource or performance claim is added.
Leak checking remains unavailable, while isolated ASan/UBSan findings were fatal.
