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
