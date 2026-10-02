# Aurora

A clean-slate systems language and operating-system research project.
**Aurora is a working name.**

This repository contains the first experimental compiler and kernel bootstrap,
not a production OS or a proven memory-safe language. It deliberately makes no
source or binary compatibility promise with C or existing C++.

## Start here

Requirements: an x86-64 Linux host, GNU C++ with C++23 support, GNU Make, GNU
binutils, Python 3, and Bash. QEMU system x86 is required for the separate boot gate.

```sh
make                 # compiler and raw emulator image
make test            # compiler execution/rejection tests and image checks
make smoke           # actual QEMU boot; missing QEMU is a failure, not a pass
```

Build products are in `build/`. `aurora.img` is a disposable emulator disk.
**Do not install this image on a physical device.** It is not an installer and
has no production storage, isolation, recovery, or hardware support.

To compile the sample independently:

```sh
build/aurorac examples/kernel.au -o build/kernel-language.s
as --64 build/kernel-language.s -o build/kernel-language.o
```

See [kernel setup and limits](kernel/README.md) for emulator details, and
[verification](docs/verification.md) for the exact tests run for this snapshot.

## What is real in this milestone

- A C++23 compiler with its own lexer, parser, type checks, ownership checks,
  and x86-64 assembly emitter. It does not transpile Aurora into C.
- A small scalar language: modules, typed functions, local bindings, expressions,
  branches, explicit moves, and scoped shared/exclusive borrows of owned integers.
- Local class values with scalar fields, named initialization, independent copies,
  field reads and mutable field writes. Methods and aggregate ownership are absent.
- Compile-time size/type-ID/field-count queries and runtime size/count lookup for
  builtins and classes. These are **not** complete class reflection, reflective
  invocation, or Java-style dynamic class loading.
- A freestanding C++ bootstrap kernel that enters x86-64 mode, calls compiled
  Aurora code, and reports the result over a serial device. New trusted bootstrap
  code adds breakpoint/fail-stop exception entry, E820 usable-memory validation,
  and a bounded 128-page arena allocator with generation/epoch ownership tickets.
- Positive execution tests and negative compiler tests, plus distinct image and
  emulator acceptance gates.

The expanded checkpoint passed a fresh build, 116 compiler tests, allocator
sanitizer/model checks, and actual QEMU normal/divide-error/page-fault gates.
[Verification](docs/verification.md) records the source hashes and test output.
Test counts alone are not a safety or OS-completeness claim.

The sample `examples/kernel.au` borrows and updates an owned integer, releases
the borrow, moves ownership, and returns the value to the bootstrap kernel.

## Where the design is heading

- Modern class-based value types without forced heap allocation.
- Modules instead of headers or textual macros in the new language.
- Deterministic resource lifetimes, ownership, checked borrowing and indexing.
- Compile-time reflection and permission-checked runtime reflection from one
  type model.
- A small capability-oriented kernel with isolated drivers and typed messages.
- Versioned device protocols for cooperative, open firmware, including explicit
  DMA lifetimes, reset/recovery and hardware conformance testing.

Read the [architecture](docs/architecture.md), [language design](docs/language.md),
[device contract](docs/device-contract.md), and [roadmap](docs/roadmap.md).
These documents clearly label proposed facilities that are not implemented.
The requested long-term destination is a self-hosted native ecosystem with the
practical functionality of a Linux system stack authored in Aurora: toolchain,
packages, services, desktop, shell, and applications. All Zen CPUs and
Navi/RDNA-and-later GPUs are qualification targets, not supported hardware.
See the [completeness matrix](docs/completeness-matrix.md),
[system release plan](docs/system-release.md), and [AMD plan](docs/amd-support.md).

## Deliberate limits

The owned integers and lexical borrow checks are a testable starting point, not
Rust's general ownership system. General classes with methods, nested/resource
fields, heap allocation, borrowing across function boundaries, concurrency
checking, comprehensive reflection,
self-hosting, an optimizing middle end, process isolation, a scheduler, driver
services, and broad physical-device support are not yet implemented. The C++
page arena does not supply language-level heap ownership or process isolation.

Open firmware makes a consistent device contract possible; it does not remove
hardware variation or the need for drivers and validation. No universal "ideal"
kernel design is claimed: the architecture records tradeoffs and evidence gates.

## Temporary bootstrap boundary

Authored C++ uses classes rather than struct declarations. The existing host
compiler still needs standard-library includes and a conventional host entry
point. The kernel uses a tiny hardware/assembly bridge and an emulator-only BIOS
loader. Those are temporary bootstrap accommodations, not the proposed language,
firmware API, or stable system ABI. The generated assembly uses a documented
scalar calling convention so components can be linked during bootstrapping.

## Layout

- `compiler/`: bootstrap compiler and its build rule
- `examples/`: actual compilable Aurora programs
- `kernel/`: freestanding bootstrap and emulator loader
- `scripts/`: kernel build and boot acceptance commands
- `tests/`: compiler and image checks
- `docs/`: target design, roadmap, review, and verification evidence
