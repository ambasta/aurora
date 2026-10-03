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

`make smoke-all` runs all 110 unique normal/adversarial BIOS, UEFI, ACPI, PCI and checked-arithmetic gates. `make smoke-scheduling` runs the nine scheduling gates alone, and
`make smoke-uefi` runs the eight OVMF gates (set OVMF to the firmware path).
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
- Local class values, designated field initialization, independent copies and
  access-checked fields. The compiler also supports complete scalar
  constructors, private methods and const-correct receiver calls. Ordinary
  functions also accept and return bounded scalar-field values as independent
  copies; see [class behavior](compiler/CLASSES.md) and
  [value-call semantics](compiler/VALUE-CALLS.md).
- Scoped ownership/borrowing of owned integers and explicit moves. This is not
  a general heap/lifetime implementation or a proof of Rust-equivalent safety.
- Basic compile-time type queries and runtime metadata queries. Full type-level
  transformations and reflective invocation are not implemented. Explicit scalar-constrained
  class templates now have a narrow implemented subset.

A first freestanding Aurora module now provides scalar `std::min`, `std::max`
and checked `std::abs` through genuine imports and namespaces:

```sh
build/aurorac --module-root library examples/core_math.au -o build/core_math.s
```

Imports use explicit roots, bounded graph loading, exports and defining-module
name resolution. Runtime type queries use defining-module visibility views.
This is whole-graph compilation, not a separately compiled stable binary ABI.
See [modules and host I/O](compiler/MODULES.md) and [core library](library/README.md).
The library contains initial scalar-specialized modules, not a complete runtime or standard library.

The compiler also supports `import std.numeric;` and an inline
`std::Accumulator(initial)` with checked `.add(amount)` and readonly `.value()`.
This Aurora-specific scalar API exercises private state and constructors; it is
not a claim that standard C++ has this class. The bounded array subset described
below is the current reusable container implementation.
The milestone006 compiler adds `std::minmax(i64, i64)` returning
an inline `std::MinMax`, with readonly `.min()`/`.max()` and checked
`std::range_width(MinMax)`. Class arguments are immutable snapshots taken
left-to-right; results are complete independent values. Private signatures and
caller type visibility are checked across imports.

Milestone006 verified the value-call checkpoint with 59 new value-call cases,
206 direct IR cases and four exhaustive-dispatch compile checks. Those receipts
remain historical.

The reviewed milestone007 compiler adds checked i64 division and remainder plus
`import std.integer;`: `std::gcd`, `std::lcm`, and `std::div` returning an inline
`std::DivResult` with readonly `.quot()`/`.rem()`. Division truncates toward zero;
remainder follows the dividend sign. Zero divisors trap at a distinct defined site,
minimum i64 divided by -1 traps for overflow, and minimum i64 remainder -1 is zero.
See [integer semantics](compiler/INTEGERS.md). The compiler passes 84 new
integer cases, 216 direct IR cases, six exhaustive-dispatch checks and an independent
1,510-case integer oracle with 181 exact trap-site checks, including sanitizer
runs. Independent compiler review and final milestone007 integration verification
passed. This does not establish a complete numeric library or a performance claim.


The reviewed milestone008 compiler adds distinct `u64` values, explicit checked
`u64(i64)`/`i64(u64)` conversions, exact 64-bit bitwise operations and checked
shifts. Unsigned unary minus and implicit type mixing are rejected. Invalid
shift counts trap separately from left-shift result overflow. `import std.bit;`
provides real Aurora implementations of `std::popcount`, `std::bit_width` and
`std::has_single_bit`. See [the unsigned contract](compiler/UNSIGNED.md).
The checkpoint passes 95 unsigned source cases, 385 direct IR cases and ten
exhaustive-dispatch checks. Its default independent oracle passes 4,219 native
cases with 501 exact trap-site checks and 67 rejection fixtures; alternate-seed
runs cover overlapping cases, not additional disjoint coverage. Existing suites
and address/undefined-behavior sanitizer gates pass. Independent compiler review
passed; final milestone008 integration verification passed.


The reviewed milestone009 compiler adds explicit `template <Scalar T, Scalar U>`
class-value definitions and the real `std.utility` module with `std::pair<T,U>`.
One or two type arguments must each be i64, u64 or bool. Instances are distinct
nominal classes identified by defining module, template and ordered argument tuple;
repeated uses share one specialization. Ordinary initialization, privacy, constness
and independent class-copy rules apply after substitution. Graph limits are 64
templates and 256 specializations; deduction, function templates, nested arguments,
recursive instantiation and general concepts remain deferred.
The checkpoint passes 117 template checks and 393 direct IR cases, alongside the
existing suites, ten exhaustive-dispatch checks and sanitizer gates. Independent
compiler review passed; final milestone009 integration verification passed.
See [the template contract](compiler/TEMPLATES.md).


The independently reviewed milestone010 compiler adds `import std.array;` and
`std::array<T,N>` for scalar T and explicit decimal capacity N from 1 through 64.
Its private inline storage is completely zero-initialized; `.size()` reports the
capacity, `.at(index)` returns a checked scalar copy, and mutable `.set(index,value)`
stores and returns the value. Ordinary class copies and function boundaries copy
all elements independently. No heap, slices or escaping element references are added.
Canonical `builtin::array<T,N>` names the storage type; bare `array<T,N>` remains
its fixed alias in every scope. The `builtin` namespace is reserved, and the
wrapper is always spelled `std::array<T,N>` at use sites.

The checkpoint passes 216 fixed-container cases, including 55 exact trap-site checks
and 96 rejection fixtures, 463 direct IR cases, ten exhaustive-dispatch controls
and 18 native receiver-array IR checks with ten exact trap-site checks. Existing
suites and address/undefined-behavior sanitizer gates pass; alternate-seed runs
overlap this coverage. Independent compiler review passed; final milestone010
integration verification passed. See [the fixed-container contract](compiler/FIXED-CONTAINERS.md)
for literal-capacity templates, logical-field versus flat-storage metadata, the
64-leaf class-value boundary and argument evaluation order.

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
faults remain fatal. The latest controlled execution uses three separately owned CR3 domains and
leased stacks, with foreign-code/data denial, root restoration, stale-handle
checks and scrubbed reuse. It remains sequential, bounded fixture execution;
there is no general application loader, scheduler, SMP or process lifecycle.

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
general interprocedural borrowing, function templates, generic methods, inheritance, concurrency model, scheduler, SMP,
full virtual-memory manager, general runtime/standard library, driver stack,
desktop, native package system or
self-hosting compiler yet. C-level performance has not been established by an
end-to-end benchmark suite. Safety checks may be eliminated only when justified.

The bootstrap C++ toolchain still uses standard-library headers and conventional
host entry points, plus a narrow Linux descriptor-relative source/output adapter.
That adapter protects source roots and atomically publishes output under its
documented assumptions; it does not provide a whole-repository snapshot.
Architecture-specific C++/assembly is trusted. The BIOS loader
is disposable bring-up machinery. None is the proposed final language API,
firmware contract or stable native ABI. Authored C++ uses classes, not structs.

## Repository map

- `compiler/`, `examples/`: compiler implementation and compilable programs
- `library/`: initial native freestanding native core/numeric/integer/bit/utility modules
- `kernel/`, `scripts/`, `tests/`: trusted bootstrap and executable validation
- `docs/`: requirements, design, independent review and historical evidence
- `AGENTS.md`: development and verification contract

## UEFI firmware handoff

A separate relocatable EFI loader and protected payload now pass eight OVMF
gates, including stale map-key retries, malformed handoffs and hardware WP/NX
faults. The payload uses its own memory ownership, page tables and guarded stack
after ExitBootServices and executes generated Aurora code. This does not yet
port the BIOS scheduler to UEFI or support a physical Framework. See the
[UEFI contract](kernel/uefi/README.md).

The optional [ACPI discovery profile](kernel/uefi/acpi.md) now validates firmware
CPU/APIC topology through a bounded read-only mapping window. Eleven OVMF gates
cover discovery, malformed inputs, read-only enforcement and revocation. It does
not yet configure interrupts, start secondary CPUs or activate device drivers.

The [read-only PCI profile](kernel/uefi/pci.md) discovers emulated NVMe, USB and
network controller identities, including a downstream bridge. Its explicit q35
resource contract grants no BAR, DMA or driver-activation authority.

The [UEFI protected-runtime profile](kernel/uefi/runtime.md) now runs compiled
user programs in distinct owned roots after firmware discovery, contains exact
language faults, and restores kernel authority before retirement and reuse.
Fourteen runtime modes verify this bounded sequential path. It does not yet
provide UEFI preemption, IPC, arbitrary processes or device activation.

The [staged IPC profile](kernel/uefi/ipc.md) now links separately compiled client
and service domains through bounded copied requests/replies, incarnation-bound
endpoint rights and fault cancellation/restart. It has no arbitrary suspended
call, shared pointer, timeout or preemption guarantee.

## Composed values and service recovery

The [Value-constrained composition subset](compiler/COMPOSED-VALUES.md) supports
bounded nested class fields, constructor snapshots and independent projections,
including std::pair<std::MinMax,std::Accumulator>. Scalar keeps its original
meaning; containment is acyclic and bounded to four class levels/64 leaves.

The [UEFI service budget](kernel/uefi/service-budget.md) can interrupt/resume a
non-yielding service, cancel its request at a verified interrupt-count budget,
drain pending interrupts, scrub/recreate it and complete a fresh request. This
is neither calibrated wall-clock timing nor a general scheduler.
