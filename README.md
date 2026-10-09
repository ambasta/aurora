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

The merged canonical Meson graph and Aurora graphical console passed all 249
tests on each recorded GCC 14 and GCC 16 toolchain, six image admissions, and
28 graphical emulator cases with ordinary restorations. The two final-source
normal BIOS smokes were completed after the PR100 merge on 2026-10-09. These
results cover the recorded toolchains and emulator profiles; physical hardware
and general terminal/window services remain unqualified.

## Try it

Use an x86-64 Linux host with GCC 16 (C++23), GNU Make and
binutils, Python 3 and Bash. The native tests also use Meson 1.12.1+, Ninja,
coreutils and ripgrep.
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
The simple UEFI prompt also supports `write note <text>` and `cat note`: one
RAM-only note, at most 53 ASCII bytes, lost when the session exits. This is not
a persistent filesystem; see its [scope](docs/native-console-service.md#session-local-ram-note).
For automated console acceptance, use `make smoke-console` (BIOS) or
`make smoke-console-uefi`. Both are included in `make smoke-all`; `make test`
remains native-only.

A separately reviewed protected-command profile offers `upper`. Its
[contract and current qualification](docs/program-console-contract.md) describe
automatic local build/image/stack checks for public commands, the separate
review-pinned first-image qualification, scoped guest evidence and final integration gates.

For the output-only graphical status page, `make capture-framebuffer` builds and
saves a PNG under `build/`. This [developer preview](docs/framebuffer-console.md#developer-preview)
needs no independent review receipts and does not establish qualification.

For the bounded serial-input graphical console, `make smoke-graphical-console`
builds fresh images, exercises production and capture profiles, saves physical/PPM
evidence and boots ordinary normal UEFI afterward. See the
[graphical smoke scope](docs/framebuffer-console.md#current-source-graphical-smoke).

See [local development](docs/local-development.md) for dependencies, compiler and
firmware options, build-only commands and troubleshooting. `make help` lists the
entrypoints. Host/toolchain qualification is recorded with each tested result.
Use the [canonical Meson/Ninja graph](docs/meson-bootstrap.md) for incremental
compiler/fixture builds and complete parallel native tests. GCC 16 is the required
merge/release toolchain; GCC 14 checks are optional targeted compatibility evidence.

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
meson compile -C build/gcc16 -j 3
meson test -C build/gcc16 --suite dev --no-rebuild --num-processes 4
meson test -C build/gcc16 --suite full --no-rebuild --num-processes 4
./scripts/compiler-test.sh    # compiler-only Meson selection
make test                    # alternative to direct Meson full above; no QEMU
make smoke-all               # separate emulator matrix; QEMU and firmware required
```

For direct Meson commands, configure a separate [build](docs/meson-bootstrap.md)
for each toolchain, with matching `gcc`/`g++` on PATH. `make test` and the
compiler-only shortcuts configure a fresh build directory automatically and reuse
it incrementally. `dev` is quick feedback; `full` includes all
native compiler, full-package and kernel/boot-image gates. Named `slow`,
`integration`, `boot`, `core` and `bytes` suites support focused work. A merge
requires the final-source GCC 16 gates in [AGENTS.md](AGENTS.md), including the
complete `full` suite and separate normal BIOS/UEFI and affected emulator profiles.

Normal development reuses dependency-tracked compiler and C++ fixture builds.
Changing source reruns affected build commands; changing toolchain/configuration
requires another directory. Make is a convenience entrypoint to the same graph,
with `MESON_BUILD_DIR`, `AURORA_BUILD_JOBS` and `AURORA_TEST_JOBS` controls. Omit
`MESON_BUILD_DIR` for a stable compiler-bytes/flags-keyed directory, or set it to a
fresh or matching configured directory. Explicit
pinned legacy compatibility remains in the [developer-test contract](docs/developer-test-contract.md).
Selected artifact identity, a focused pass or registration alone does not establish
full native, sanitizer, emulator or hardware qualification.
