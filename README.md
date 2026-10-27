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

Start with the [project status table](docs/completeness-matrix.md#current-project-state)
for the six goals, implemented foundations and remaining gaps.
The [roadmap](docs/roadmap.md) gives the dependency order and acceptance gates.
Historical test receipts remain in Git/PR history and retained run/CI artifacts when available.

The compiler, libraries and bounded serial/graphical consoles are experimental.
Qualification applies only to the exact source, tools and profiles recorded for
a run; an older passing checkpoint does not qualify current changes. Physical
hardware and general terminal/window services remain unqualified.

## Try it

The public dependency image pinned in `ci/image` is the supported reproducible
development environment, with the exact tools and firmware. With Docker or
Podman installed, start from the repository root.

Select a local copy of the checkpoint compiler pinned by
`compiler/checkpoint.json` (or rebuild it from the recorded route). Then enter
the pinned shell with `./scripts/container.sh bash` and configure the two current
Meson graphs with `-Dbootstrap_compiler`, as shown in the
[source-bootstrap recipe](compiler/README.md#source-bootstrap). Meson accepts only
the pinned executable digests rather than trusting a compiler path alone.
Then run:

```sh
make
make test
make run-uefi
```

Native x86-64 Linux setup is an advanced route requiring the exact pinned tool
versions and firmware in [local development](docs/local-development.md). Other
native tool versions are unsupported; a different GCC 16 patch version is not the
pinned GCC 16.2.0. The wrapper handles Podman user namespaces so an owned checkout
stays writable. Keep builds and guests in separate output directories when running
independent work in parallel.

Default `make` builds one Meson compiler and the normal image graph, atomically
preserving the compatible `build/aurorac` path. Compile a library example with it:

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

The supported pinned development container supplies the required UEFI firmware.
Advanced native runs must match its exact pinned tools and firmware, as described
in the developer guide. Both commands run
headless, validate serial output and exit. Images are disposable emulator inputs; do not
write them to a physical disk or replace your bootloader.

For an interactive serial prompt, run `make console` (BIOS) or `make console-uefi`,
then type `help`, `status` or `exit`. Both use a 64-byte ASCII editor and a five-minute
session limit. The [console guide](docs/native-console-service.md) covers their
commands, BIOS IRQ/UEFI timer transport, trust boundaries and acceptance gates.
Simple UEFI and the graphical console also support one RAM-only note and four
named RAM files; their [grammar and limits](docs/native-console-service.md#session-local-ram-note)
are shared, but all state disappears at session exit.
Use `make smoke-console` or `make smoke-console-uefi` for automated PTY checks;
both belong to `make smoke-all`, while `make test` remains native-only.

The opt-in [protected namespace console](docs/native-console-service.md#protected-volatile-namespace)
retains four named RAM files in one CPL3 Aurora owner, with a fresh bounded caller
for each `write` or `cat`. It is a storage-fixture row, not the production console:
owner failure/reset and session exit discard all data. It provides no durable
storage, automatic replay or general process service.

The separate [protected-command console](docs/program-console-contract.md) runs
`upper`, authenticated note and named RAM-file reads/atomic uppercase replacement,
and named-file append through two CPL3 domains. Append launches one live compiled
Call-only caller and one Serve-only producer per command. The producer constructs
its candidate once; both retain source state across exchanges. Only terminal EOF
parking, clean caller return and both domain retirements permit publication to
the surviving supervisor-held store. Revision invalidation and
fault/budget recovery remain bounded to the session; this is not durable storage.
Its public commands perform local build/image/stack checks. The same checked
image can be passed by explicit build directory to the guest oracle; changed
images still require independent review and final qualification. It is the
console of the one production UEFI image, which also renders it on the firmware
framebuffer; `make smoke-production` checks both (QEMU/OVMF only, see
[production image](docs/kernel-fixture-consolidation.md#production-image)).

For the output-only graphical status page, `make capture-framebuffer` builds and
saves a PNG under `build/`. This [developer preview](docs/framebuffer-console.md#developer-preview)
needs no independent review receipts and does not establish qualification.

For the bounded serial-input graphical console, `make smoke-graphical-console`
builds fresh images, exercises production and capture profiles, and boots ordinary
normal UEFI afterward. Successful runs retain summaries and logs; failures or
explicitly kept runs retain full physical/PPM evidence. See the
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
- [Development and qualification](docs/developer-test-contract.md): test scope and merge gates

Implementation lives in `compiler/`, `library/`, `kernel/` and `storage/`.
`examples/` contains Aurora programs; `tests/` and `scripts/` hold the validation
and build machinery. Living component guides describe current behavior and limits.

## Contributing

Start with a small running mechanism and a clear acceptance condition. Include
positive, rejection and regression cases. Maintain one living guide per component
and the concise project status table in place; do not add per-feature contract/results
pairs. Keep historical results in Git/PR history and retained run/CI evidence when
available. Preserve raw evidence and its limits without copying checkpoint narratives
across README, roadmap and matrix.
Host C++ and Python follow the [source style guide](docs/style.md), with pinned
formatter versions and explicit check/format commands.
Use the checks appropriate to the change:

```sh
meson setup build/gcc16 \
  "-Dbootstrap_compiler=$C0"
export MESON_BUILD_DIR=build/gcc16
meson test -C build/gcc16 --suite dev  # optional focused feedback
make test                    # merge suite, nproc jobs with memory watchdog; no QEMU
make run && make run-uefi     # normal BIOS/UEFI smokes; also run affected guest families
# Releases and compiler bumps only:
make test-release
make smoke-all               # complete emulator matrix; QEMU and firmware required
```

For direct Meson commands, configure a separate [build](docs/meson-bootstrap.md)
for each toolchain, with matching `gcc`/`g++` on PATH. `make test` and the
compiler-only shortcuts reuse an explicitly checkpoint-configured build
incrementally. `make test` runs the `merge` suite; `make test-release` runs the
opt-in `release` suite (mutation testing, complete subset sweeps); `full` is their union. Named `dev`, `slow`, `integration`, `boot`,
`core` and `bytes` suites support focused work. A merge requires the final-source
GCC 16 gates in [AGENTS.md](AGENTS.md), including the `merge` suite and separate
normal BIOS/UEFI and affected emulator profiles.

Normal development reuses dependency-tracked compiler and C++ fixture builds.
Changing source reruns affected build commands; changing toolchain/configuration
requires another directory. Make is a convenience entrypoint that runs
`meson compile`/`meson test` on `MESON_BUILD_DIR` (default `build/meson`) under
`scripts/watchdog.sh`, which stops the run if MemAvailable falls below
`AURORA_MEMORY_RESERVE_MIB` (default 2048). Explicit
historical receipt boundaries remain in the [developer-test contract](docs/developer-test-contract.md).
Selected artifact identity, a focused pass or registration alone does not establish
full native, sanitizer, emulator or hardware qualification.
