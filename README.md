# Aurora

Aurora is an intentionally incompatible, safe C++ dialect and a native operating
system project. The priorities are **extreme safety, modern/elegant design, and
measured high performance**. Aurora remains a working name.

The long-term target combines C-like native performance, Rust-like safety,
Java-inspired object design, TypeScript-style type-level programming, compile-time
and runtime reflection, and recognizable modern C++ APIs. It deliberately does
not preserve C source support, C/C++ binary compatibility, or arbitrary unsafe
operations. These are design targets, not current guarantees.

## Build and test

Requirements: x86-64 Linux, GNU C++ with C++23 support, GNU Make, GNU binutils,
Python 3, Bash, and QEMU system x86 for the actual emulator gates.

```sh
make
make test
SANITIZE=1 ./scripts/kernel-tests.sh
make smoke-all
```

`make smoke-all` runs the normal boot and adversarial CPU/memory/program probes.
Missing QEMU is a blocked test, not a pass. The raw `build/aurora.img` is a
disposable emulator image, **not an installer for a physical machine**.
Do not write it to a physical disk or replace a host bootloader.

See [kernel instructions](kernel/README.md) and [verification](docs/verification.md)
for tools, exact commands, evidence and limitations.

## Current language subset

```cpp
module example;

class Point {
public:
    i64 x;
    i64 y;
};

auto answer() -> i64 {
    const Point point = Point{.x = 20, .y = 22};
    const array<i64, 2> values = {point.x, point.y};
    i64 total = 0;
    i64 index = 0;
    while (index < len(values)) {
        total = total + values[index];
        index = index + 1;
    }
    return total;
}
```

- A C++23-hosted frontend, trusted semantic/lifetime analyzer, typed IR verifier
  and separate x86-64 backend. Checked arithmetic and bounds evidence remain
  explicit through lowering. Aurora
  source is not transpiled into C. The host assembler/linker are still bootstrap
  dependencies; native replacements and self-hosting are future milestones.
- Typed functions, initialized locals, branches and conservative while-loop checks.
- Checked signed arithmetic and bounds-checked fixed-size scalar arrays.
- Local class values, named field initialization, independent copies and field
  access, with private-by-default class visibility and const enforcement.
- Scoped ownership/borrowing of owned integers and explicit moves. This is not
  a general heap/lifetime implementation or a proof of Rust-equivalent safety.
- Basic compile-time type queries and runtime metadata queries. Full type-level
  transformations, reflective invocation, methods and generics are not implemented.

The previous `fn`/`let` prototype syntax is intentionally removed. The current
surface, evaluation order and unsupported features are specified in
[compiler/README.md](compiler/README.md). Examples live in `examples/`.

## Current trusted kernel bootstrap

The kernel enters x86-64 mode, calls generated Aurora machine code, and validates
its result over serial. Its C++/assembly bootstrap implements a bounded physical
page allocator, E820 validation, IDT exception delivery, private GDT/TSS and guarded
stacks. Explicit page permissions enforce supervisor write protection and NX.

A controlled integer-only ring-3 probe exercises its own user stack and an entry
gate. Adversarial probes test denied kernel accesses, code writes, data execution,
privileged instructions, I/O and damaged-stack exception handling. This is a
limited boundary test, **not a complete process isolation or scheduling system**.
Separately compiled Aurora fixtures now execute in user RX pages through a
scalar-only return contract. Recognized user bounds/overflow traps are contained,
then a clean fixture runs again. Unexpected returns/traps fail closed, and kernel
faults remain fatal. These fixtures share one bounded user domain; this is not
a general application loader, scheduler or per-process address-space system.

## Whole-system destination

The eventual distribution is native to Aurora: compiler/binutils equivalents,
runtime/libraries, Portage-like source package management, services, storage,
networking, security, installer and applications. A native platform/runtime layer
will replace libc responsibilities without its C API/ABI, alongside a safe C++
standard library. See [library stack](docs/library-stack.md). Desktop targets include a
Sway-like tiling environment, Foot-like terminal and Wayland-like display protocol.
Later language/library/FOSS ports will require native backends, API adaptation or
safe rewrites; compatibility is not implied by those comparisons.

Hardware targets all Zen CPU generations and Navi/RDNA GPUs onward, including
integrated/discrete devices where applicable. **No physical AMD support is yet
qualified.** Emulator success is not hardware qualification or GPU acceleration.

Read the [architecture](docs/architecture.md), [language](docs/language.md),
[device contract](docs/device-contract.md), [AMD plan](docs/amd-support.md),
[system release plan](docs/system-release.md), [completeness matrix](docs/completeness-matrix.md)
and [roadmap](docs/roadmap.md).

## Important limits

There is no production safety proof, optimizing compiler, general heap ownership,
interprocedural borrowing, methods/generics, concurrency model, scheduler, SMP,
full virtual-memory manager, driver stack, desktop, native package system or
self-hosting compiler yet. C-level performance has not been established by an
end-to-end benchmark suite. Safety checks may be eliminated only when justified.

The bootstrap C++ toolchain still uses standard-library headers and conventional
host entry points. Architecture-specific C++/assembly is trusted. The BIOS loader
is disposable bring-up machinery. None is the proposed final language API,
firmware contract or stable native ABI. Authored C++ uses classes, not structs.

## Repository map

- `compiler/`, `examples/`: compiler implementation and compilable programs
- `kernel/`, `scripts/`, `tests/`: trusted bootstrap and executable validation
- `docs/`: requirements, design, independent review and historical evidence
- `AGENTS.md`: development and verification contract
