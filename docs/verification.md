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
