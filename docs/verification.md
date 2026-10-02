# Verification record

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
