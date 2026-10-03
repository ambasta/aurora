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
