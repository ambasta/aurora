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

`make smoke-all` runs all 166 unique normal/adversarial BIOS, UEFI, ACPI, PCI and checked-arithmetic gates. `make smoke-scheduling` runs the nine scheduling gates alone, and
`make smoke-uefi` runs the eight OVMF gates (set OVMF to the firmware path).
Missing QEMU is a blocked test, not a pass. The raw `build/aurora.img` is a
disposable emulator image, **not an installer for a physical machine**.
Do not write it to a physical disk or replace a host bootloader.

See [kernel instructions](kernel/README.md) and [verification](docs/verification.md)
for tools, exact commands, evidence and limitations.

## Verified milestone022: copied ordinary method values

Ordinary methods now accept immutable copied class parameters. The real
`std::array<T,N>::exchange(replacement)` returns independent old contents and
replaces its receiver from a snapshot. The new combined private ABI keeps
receiver, argument record and result authority separate; it adds no source pointer
or foreign ABI. See [the method-value contract](compiler/METHOD-VALUES.md).

Complete release/fatal host ASan/UBSan compiler gates, independent source/IR/native
ABI review, a fresh parent `make test`, and all **166 actual emulator modes**
(37 BIOS, 129 UEFI-family) passed on the rebuilt reviewed compiler. Two additional
normal BIOS/UEFI boots restored both images. All 368 source and 236 external inputs
stayed unchanged through integration. [M022 evidence](docs/evidence/milestone-022/README.md)
preserves the exact receipts, original failures, isolated stress replay and limits.
There is no new kernel functionality, physical-device qualification, heap/reference
API, generic method, whole-program resource proof or equivalent-C performance claim.
Local verification does not imply remote publication.

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
  access-checked fields. The compiler supports complete constructors, private
  methods, const-correct receiver calls and bounded nested value composition.
  Ordinary functions accept and return independent class copies; milestone012 also supports copied class-valued method results
  and closed nominal enums; see [class behavior](compiler/CLASSES.md) and
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
templates and 256 specializations. At that checkpoint, deduction, function templates,
nested arguments, recursive instantiation and general concepts were deferred;
M020/M021 subsequently add the bounded nested-argument and explicit-function subsets.
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
general interprocedural borrowing, template deduction or recursive generic expansion, generic methods, inheritance, concurrency model, scheduler, SMP,
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

## Verified enums, recoverable results and staged dispatch

Milestone012 integrates [closed enums and copied method results](compiler/ENUM-RESULTS.md)
with the verified Value-composition baseline. Value accepts nominal enums; Scalar
remains exactly i64/u64/bool. Enum values have no numeric conversion or invalid
case construction. Complete method results copy into fresh typed locals, including
array, enum and empty-class descendants, with distinct receiver/result storage.

The compiled `std.decimal` module provides `DecimalAccumulator`, `DecimalResult`
and `DecimalStatus`: numeric digits accumulate a checked u64 value, invalid digits
and unrepresentable input produce sticky recoverable status, and `finish()`
returns an independent report. This is a numeric API, not a text representation.
See [the combined example](library/examples/enum_composition.au).

Milestone012 passes 107 combined cases, 196 decimal cases and 592 direct IR
cases, plus existing language regressions and address/undefined-behavior sanitizer
gates. Independent compiler and kernel review passed. The bounded three-domain
UEFI dispatcher serves two isolated clients through one service, confines replies
to the selected transaction, and preserves committed replies during service
failure/restart. All 122 emulator modes and fresh parent aggregate checks pass;
see [verification](docs/verification.md) for source identity and receipt provenance.
Clients remain cooperative; this is not a general scheduler or physical hardware
qualification. No equivalent-C performance claim or general expected/text API is implied.


## Checked bytes and controlled client recovery

Milestone013 adds [checked u8 and compact storage](compiler/BYTES.md). Byte arrays
have stride one; class fields follow verified byte offsets/alignment with typed
copies and deterministic representation padding. Explicit narrowing traps outside
0..255. Existing eight-byte scalar layouts stay unchanged. The native `std.bytes`
module provides recoverable 32-bit little/big-endian encoding and copied decoding.
No pointer, unchecked cast, C ABI, text encoding or heap API is introduced.

[Controlled user phases](kernel/uefi/user-phases.md) now budget request, service
and completion execution. A non-yielding or known-faulting client can be disposed
and rebound while its peer progresses. Committed replies keep their terminal
outcome; actual mapping retirement, scrub and old-epoch interrupt drain precede
reuse. Unknown fault origins remain fail-stop. All 139 emulator gates pass on the
packed-byte compiler; final parent evidence is in [verification](docs/verification.md).
This remains a bounded single-CPU integer-only mechanism, not general process
recovery, calibrated deadlines, SMP or physical Framework qualification.


## Native filesystem and XFS target

The supplied NVMe-native object/extent requirements are adapted in
[storage/design/requirements.md](storage/design/requirements.md), with all 56
sections traced and XFS on-disk support added separately. The implementation
[roadmap](storage/design/roadmap.md) preserves eventual read-write XFS while
staging clean read-only access and recovery first. No C ABI or Linux filesystem
implementation is imported.

A reviewed finite host crash model now checks dependency-before-commit persistence,
acknowledgement loss and bounded retry results, including deliberately broken
protocols. `make test-storage-model` runs it and mutation-tested document checks.
This is executable design evidence, not a working filesystem, XFS mount, NVMe DMA
transport or hardware qualification. See [storage status](storage/README.md).


## Readonly byte views and read-only device resources

Milestone014 adds [readonly whole-array byte spans](compiler/SPANS.md) with
synchronous forwarding, checked access and lexical/call-bounded shared borrowing.
Owner mutation and capability escape are rejected; this is not a general async
borrow or heap-resource system. Real std.binary reads operate on borrowed bytes.
A separate 449-byte protected program executes the span ABI in Aurora; the older
clean program and its 4 KiB limit remain unchanged.

The [BAR resource contract](kernel/uefi/BAR-RESOURCE-CONTRACT.md) validates one
explicit emulated NVMe resource profile, permits seven bounded read-only register
observations and revokes its supervisor UC/R/NX window. Stock firmware's inherited
bus-master state is rejected. A separately pinned, narrowly modified EDK2 fixture
provides an inactive controller with memory decoding enabled and bus mastering
clear. Positive trace controls and cold-reset traces constrain that claim; PCI
attribute probing did transiently set BME before restoration. This is not a driver,
IOMMU isolation, DMA activation or physical Framework support.

Independent review and final 147 emulator modes passed, alongside the parent
aggregate, sanitizers and selected emulator reruns. Exact source identities,
firmware profiles, failed development attempts and distribution limits are in
[verification](docs/verification.md). Native filesystem/XFS work remains staged
as described above; the host crash model is included in make test.

## Verified milestone015

Checked endian readers and CRC32C now support a restricted XFS v5 512-byte
header-integrity probe, including a real offline fixture. Read-only AMD-Vi/IVRS
observation passes its explicit QEMU profile, architectural-default refusal and
write/revocation tests. All158 emulator modes, independent11 new modes, and parent
aggregate checks passed. No IOMMU activation, DMA isolation, NVMe queue transport,
filesystem mount/replay/write or physical AMD qualification is claimed. See the
[verification record](docs/verification.md) for exact inputs and failed historical
controls. Further mutable-byte development is isolated and is not part of this
verified checkpoint.

## Verified milestone016

The compiler retains initialization facts in bounded-index bitsets, preserving
reviewed language decisions and generated code in differential comparisons.
Dense workloads use less memory; measured sparse workloads can use more.
A fixed-capacity kernel page-pin ledger now consumes real move-only leases,
scrubs clean cancellation, and retains quarantined pages across a same-slot
service restart. All162 emulator modes and parent aggregate checks passed.
This is page ownership, not active DMA isolation. See the verification record
for the sparse-memory tradeoff, exact tests and sanitizer-build accommodation.

## Verified milestone017

The native std.utf8 library strictly decodes and validates Unicode17 UTF-8 using
readonly byte spans and recoverable errors. All Unicode scalar values and bounded
malformed/truncated/range fixtures passed independent native checks. Parent
aggregate and three existing emulator smoke profiles passed on unchanged compiler
and kernel implementation. No fresh full162 run or terminal/string completeness
is claimed for this library-only checkpoint. See docs/utf8-contract.md.

## Verified milestone018

UTF-8 scalar encoding now returns an owned fixed-capacity value with checked
access and zeroed unused bytes. Valid scalars use shortest encodings; invalid
scalars fail recoverably. Independent native comparisons cover every scalar,
report/copy semantics and access boundaries. Parent aggregate and three unchanged
kernel smoke profiles passed. Compiler/kernel implementation and the decoder
remain unchanged; this is not a complete string or terminal library.


## Verified milestone019: dormant table bytes and XFS header geometry

The integrated checkpoint passed all **166 actual emulator modes** (37 BIOS,
129 UEFI-family), independent review of all four new modes, a fresh coordinating
`make test`, and fresh readback/quarantine/normal UEFI smoke profiles. The latter
three are selected repetitions, not a second full suite. Normal images restored.

- The bootstrap kernel constructs bounded AMD3.10-format dormant tables in real
  leased guest RAM, checks every DTE/leaf through a software model, rejects
  corruption, tests exhaustion, and scrubs or quarantines pages across restart.
  No IOMMU register programming, device publication, DMA or interrupt isolation
  is implemented. Each mode retains the 16 KiB stack and existing page budgets;
  the measured bound is 13,136 bytes including a 1,024-byte fault reserve.
- Native `fs.xfs_geometry` adds recoverable facts for a deliberately narrow XFS
  v5/512-byte header profile, overflow-safe geometry and explicit feature masks.
  Independent tests exercise 2,016 identical byte-distinct headers under each
  compiler pin, all 42 scalar result leaves, failure zeroing and input stability.
  Success is copied data, not authority or evidence of mountability. No XFS
  mount/replay/write path, storage transport or physical-device qualification.

See [verification](docs/verification.md) for hashes, failures, test limits and
archival evidence. General heap safety, active DMA, SMP, native toolchain,
filesystem service, graphics and the complete desktop remain future work.

## Verified milestone020: bounded nested generic values

Fully concrete nested template-id arguments such as
`std::pair<std::array<u8,16>,SourceRange>` now use the existing inline construction,
copied projections and value-call mechanisms. The executable token/source-range
example returns 42. Template-id nesting is capped at four independently of class
depth four; the existing 64-leaf, 64-definition, 256-instance and 1..64-capacity
limits remain. See [NESTED-VALUES.md](compiler/NESTED-VALUES.md).

Complete release and fatal ASan/UBSan compiler targets, independent adversarial
review, a fresh parent `make test` and three fresh UEFI profiles (`runtime-span`,
`runtime-pin-fault`, `normal`) passed. The normal image was restored. M019 remains
the historical full 166-mode checkpoint; these three spots are not a fresh full
suite. No new kernel functionality, dependent template-body expansion, recursive
instantiation, deduction, new IR/ABI or physical-device support is added.
See [M020 evidence](docs/evidence/milestone-020/README.md) for exact pins, finite
coverage, preserved failures and generated-product omissions. Local functional
verification does not imply remote publication.

## Verified milestone021: explicit copied-value function templates

Bounded namespace-level function templates now accept one/two explicit Scalar/Value
arguments. The real `std::make_pair<T,U>` factory and executable
`examples/function_token_values.au` use complete independent copied values.
Class/function definitions share the 64-definition and 256-instance graph limits.
See [the function-template contract](compiler/FUNCTION-TEMPLATES.md).

Complete release and fatal host ASan/UBSan compiler targets, independent review
and sanitizer replay, a fresh parent `make test`, and three actual UEFI profiles
(`runtime-span`, `runtime-pin-fault`, `normal`) passed. The normal image was restored.
M019 remains the historical full 166-mode result; M021 did not rerun the full suite
or add kernel/physical-device support. No deduction, overloads, recursive generic
expansion, generic methods, new IR/ABI or general heap/reference API is added.
[M021 evidence](docs/evidence/milestone-021/README.md) preserves exact receipts,
corrected defects, finite coverage and resource exceptions. Local verification
does not imply remote publication.

