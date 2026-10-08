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

## Current state

Start with the [current project state and contract index](docs/completeness-matrix.md#current-project-state)
for the six goals, implemented foundations, remaining gaps and exact API references.
The [roadmap](docs/roadmap.md) gives the dependency order and acceptance gates.
Historical test receipts are kept in [verification history](docs/verification.md).

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

For an interactive serial prompt, run `make console` (BIOS) or `make console-uefi`, then type `help`,
`status` or `exit`. This opt-in QEMU profile has a 64-byte ASCII line editor and
a five-minute session limit. See the [console contract](docs/kernel-console-contract.md)
and the [UEFI results](docs/uefi-console-results.md) for focused validation and limits.
The simple UEFI editor and command presentation are Aurora-owned through a
[sealed synchronous console service](docs/native-console-service.md). BIOS and
the protected-program console retain their explicitly scoped legacy adapters.
For automated console acceptance, use `make smoke-console` (BIOS) or
`make smoke-console-uefi`. Both are included in `make smoke-all`; `make test`
remains native-only.

A separately reviewed protected-command profile offers `upper`. Its
[contract and current qualification](docs/program-console-contract.md) describe
automatic local build/image/stack checks for public commands, the separate
review-pinned first-image qualification, scoped guest evidence and final integration gates.

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
positive, rejection and regression cases, and update the existing affected contract
and current status in place. Do not create a contract/results document pair for
every increment. Keep run-specific evidence in the existing verification/evidence
locations; preserve historical receipts and their limits instead of copying their
status paragraphs across README, roadmap and matrix.
Host C++ and Python follow the [source style guide](docs/style.md), with pinned
formatter versions and explicit check/format commands.
Use the checks appropriate to the change:

```sh
meson test -C build/meson --suite dev --num-processes 2  # quick incremental feedback
meson test -C build/meson --suite slow --num-processes 2 # longer integration/ABI sweeps
meson test -C build/meson --suite full --num-processes 2 # all registered tests
./scripts/compiler-test.sh    # complete compiler-only suite
make test                     # complete native aggregate; no QEMU
make smoke-all                # complete emulator matrix; QEMU and firmware required
```

Configure the [Meson build](docs/meson-bootstrap.md) first, then choose `core`,
`bytes` or individual tests according to the changed dependencies. Other components
still use their focused checks. Before every merge, run both `dev` and `slow` on
the final integrated source, including documentation changes and conflict resolution.
Documentation also needs content/link review. Full root native and emulator
qualification are separate release/affected-system gates, not implied by these suites.

Make's compiler-consuming tests build the current compiler once per invocation;
Meson reuses an unchanged build. No historical binary pin is needed for either
developer path. A completed matching run record determines full native test coverage;
compiler-only or focused checks do not cover the full system. See the
[developer-test contract](docs/developer-test-contract.md) for result interpretation,
explicit acceptance pins and sanitizer controls, and the
[development contract](AGENTS.md) for design and review requirements.

