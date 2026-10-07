# Aurora

A safe systems language and a native operating system, designed together.

Aurora explores how much of a system can be expressed through checked values,
explicit ownership and small, isolated services. Its language keeps familiar
modern C++ syntax and class-based APIs while making arithmetic, memory access
and authority explicit. Inline classes do not require heap allocation or a GC.
C source and binary compatibility are outside the design.

The goal is a self-hosting system with its own toolchain, libraries, services and
desktop. Safety comes first, followed by clear design and measured performance.
The project is currently an experimental compiler and emulator-based kernel.

## What works today

- **Compiler:** modules, private class state, copied values, checked integers,
  fixed arrays, enums, bounded templates, overloads and readonly byte views.
  A C++23 bootstrap compiler checks source, validates typed IR and emits x86-64
  assembly. See the [language reference](compiler/README.md).
- **Library:** Aurora-authored numeric and fixed-value containers, binary readers,
  UTF-8 decoding/encoding, byte-window and line operations, and a bounded ASCII
  token scanner. See the [library](library/README.md) and [examples](examples/).
- **Kernel:** BIOS and UEFI boot, protected user-domain fixtures, bounded
  scheduling, copied request/reply IPC and service cancellation/restart in QEMU.
  Three small Aurora policies participate in the UEFI dispatcher; trusted
  C++/assembly owns memory, hardware and authority. See the [kernel](kernel/README.md) and [IPC checkpoint](docs/kernel-ipc-transition-integration-results.md).
- **Storage experiments:** a host crash model and offline XFS header/root probes.
  See the [storage project](storage/README.md).

General heap ownership and borrowing, an optimizing or self-hosting compiler,
SMP, a general process/runtime API, active device drivers, filesystem mounts and
a usable desktop remain ahead. There is no production safety proof or
end-to-end performance comparison with C. Physical AMD hardware is a
[qualification target](docs/amd-support.md); current boot testing uses emulators.

## Try it

Use an x86-64 Linux host with a C++23-capable GNU C++ compiler, GNU Make and
binutils, Python 3 and Bash. The native tests also use coreutils and ripgrep.
Run commands from the repository root, in a path without whitespace, one build
or test command at a time.

Build the compiler and BIOS image, then compile a library example:

```sh
make
build/aurorac --module-root library examples/core_math.au -o build/core_math.s
```

The example uses the real freestanding core library:

```cpp
module core_demo;
import std.core;

auto core_answer() -> i64 {
    return std::max(std::abs(-42), 20);
}
```

Boot the self-test payload with QEMU system x86-64 and GNU `timeout`:

```sh
make run
make run-uefi
```

UEFI discovers an installed combined ROM or matching CODE/VARS pair. Both commands run headless,
validate serial output and exit. Images are disposable emulator inputs; do not
write them to a physical disk or replace your bootloader.

For an interactive BIOS serial prompt, run `make console`, then type `help`,
`status` or `exit`. This opt-in QEMU profile has a 64-byte ASCII line editor and
a five-minute session limit. See the [console contract](docs/kernel-console-contract.md)
for its focused validation and limits.

See [local development](docs/local-development.md) for dependencies, compiler and
firmware options, build-only commands and troubleshooting. `make help` lists the
entrypoints. Host/toolchain qualification is recorded with each tested result.
For incremental compiler builds and focused parallel core/byte/storage tests, use the
optional [Meson/Ninja bootstrap](docs/meson-bootstrap.md).

## Explore the project

- [System architecture](docs/architecture.md): design, trust boundaries and tradeoffs
- [Compiler architecture](compiler/ARCHITECTURE.md): frontend, typed IR and backend
- [Language design](docs/language.md): intended ownership, type and reflection model
- [Library plan](docs/library-stack.md) and [storage plan](storage/design/roadmap.md)
- [Roadmap](docs/roadmap.md) and [completeness matrix](docs/completeness-matrix.md)
- [Verification history](docs/verification.md): checkpoint results and evidence

Implementation lives in `compiler/`, `library/`, `kernel/` and `storage/`.
`examples/` contains Aurora programs; `tests/` and `scripts/` hold the validation
and build machinery. Detailed contracts sit beside the component they describe.

## Contributing

Start with a small running mechanism and a clear acceptance condition. Include
positive, rejection and regression cases, and update the affected contract.
Host C++ and Python follow the [source style guide](docs/style.md), with pinned
formatter versions and explicit check/format commands.
Use the checks appropriate to the change:

```sh
meson test -C build/meson --suite dev --num-processes 2  # focused incremental feedback
./scripts/compiler-test.sh    # complete compiler-only suite
make test                     # complete native aggregate; no QEMU
make smoke-all                # complete emulator matrix; QEMU and firmware required
```

Configure the [Meson build](docs/meson-bootstrap.md) first, then choose `core`,
`bytes` or individual tests according to the changed dependencies. Other components
still use their focused checks. Leaf documentation edits need content/link review;
full native qualification is an explicit broader gate, not a prerequisite for every edit.

Make's compiler-consuming tests build the current compiler once per invocation;
Meson reuses an unchanged build. No historical binary pin is needed for either
developer path. A completed matching run record determines full native test coverage;
compiler-only or focused checks do not cover the full system. See the
[developer-test contract](docs/developer-test-contract.md) for result interpretation,
explicit acceptance pins and sanitizer controls, and the
[development contract](AGENTS.md) for design and review requirements.
