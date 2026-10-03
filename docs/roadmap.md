# Aurora implementation roadmap

This roadmap separates a useful executable seed from the research and engineering required for a safe, self-hosted ecosystem. Milestones have evidence gates, not speculative delivery dates. Passing an earlier milestone does not imply later guarantees. The requested scope is a months-scale, multi-stage effort toward a fully self-hosted native ecosystem with Linux-stack-equivalent functionality authored in Aurora, plus qualification across all Zen CPUs and Navi/RDNA-and-later GPUs. This scope is not a delivery estimate or a supported-device claim. See [system release requirements](system-release.md) and [AMD qualification](amd-support.md).

## 0 Bootstrap integration

Produce a reproducible host build, a small source compiler, negative parser/type tests, and an x86-64 emulator image that calls an Aurora-generated function and reports 42. Keep the temporary host/compiler and C++/assembly kernel adapters visible and narrowly scoped.

**Gate:** fresh build succeeds; accepted examples execute correctly; rejected examples fail with diagnostics; emulator serial output demonstrates entry, the compiled function result, and a controlled terminal state. Record exact tools and test commands. A built image without a boot log is only a build result.

The current integration has passed the QEMU boot path and reported 42 from compiled Aurora code. This is milestone evidence for that snapshot, not a claim that the later gates have passed. Class values/reflection and kernel exception/memory bring-up have since expanded; fresh integration and all 13 protection/exception emulator gates passed for that expanded checkpoint. See the [verification record](verification.md) for final build and test results.

## Design priorities and syntax direction

Preserve a recognizable modern C++ API and identity while removing unsafe features, C compatibility and C ABI promises. C-like performance, Rust-like safety, Java-inspired OOP, and safe TypeScript-style key/mapped/conditional type expressiveness are acceptance goals alongside compile-time and runtime reflection. The type algebra must not introduce `any`/assertion loopholes, erase ownership, bypass access control or require heap-boxing ordinary values. Performance must be measured against equivalent C workloads, not asserted.

The compiler now implements modern C++ declarations, private-by-default scalar class fields, fixed arrays, restricted while loops and checked signed arithmetic; independent review and fresh aggregate integration verification passed. The earlier `fn`/`let` syntax and wrapping-arithmetic evidence belong to the historical checkpoint; they are not a compatibility promise. The compiler reference defines the exact supported grammar; new verification must identify this changed source/semantic checkpoint.

## 1 Precise scalar semantics

Specify evaluation order, integer overflow, division, conversions, initialization, branch joins, local mutation, moves, and lexical borrow boundaries. The compiler now checks signed +, -, *, unary negation, division/remainder and fixed-array bounds with fail-stop traps, replacing historical wrapping behavior. The reviewed milestone007 compiler defines truncation toward zero, dividend-signed remainder, distinct division-zero failures, quotient overflow for minimum/-1 and remainder zero for that pair. It adds real scalar std.integer gcd/lcm/DivResult APIs; 84 integer cases, 216 direct IR cases, six exhaustive-dispatch checks and 1,510 independent integer-oracle cases with 181 exact trap-site checks pass, including sanitizers. Final milestone007 integration verification passed; see [INTEGERS.md](../compiler/INTEGERS.md). Specify and test that failure contract, loop flow and const-owner rules. Future memory/range arithmetic must be checked when introduced. Align emitted behavior with the specification. Add malformed-source fuzzing and differential execution against a simple reference interpreter. Ensure unsupported forms fail closed.

The reviewed milestone008 compiler extends that contract to u64, checked cross-type integer conversions and exact 64-bit operations. Shifts distinguish invalid counts from representational overflow and retain their checks through typed lowering. The real `std.bit` algorithms execute without a foreign runtime. It passes 95 unsigned source cases, 385 direct IR cases, ten exhaustive-dispatch checks and 4,219 default independent-oracle cases with 501 exact trap-site checks and 67 rejection fixtures, including sanitizer runs. Alternate-seed results overlap that coverage and are not additive. Final milestone008 integration verification passed. See [UNSIGNED.md](../compiler/UNSIGNED.md). The next library dependency should enable reusable value abstractions or fixed collections rather than indefinitely widening the scalar API.

**Gate:** executable semantics and compiler agree across edge cases and generated programs, including failing paths. Document coverage and counterexamples. Do not generalize scalar ownership checks into claims about heap safety.

## 2 Class and lifetime core

A partial implementation exists: private-by-default local scalar-field classes, designated initialization, independent value copies and access-checked field reads/mutation. Local fixed scalar arrays are also present. Milestone005 adds one complete initializer-list constructor per class, private scalar methods, const-correct hidden receivers and synchronous checked reborrows, with explicit lexical object lifetime IR. It passes 74 new source class cases and 132 direct IR checks alongside baseline/oracle/sanitizer gates; independent review and final aggregate verification passed. The real `std.numeric` accumulator module exercises this encapsulation. See [the narrow contract](../compiler/CLASSES.md).

The milestone006 compiler adds immutable by-value class parameters and complete independent results for ordinary functions, with explicit nominal call-record/result-capability IR. Its real `std::minmax`/`std::MinMax` and `std::range_width` APIs demonstrate factory and consumer boundaries. The checkpoint passes 59 new value-call cases, 206 direct IR tests and four exhaustive-dispatch compiler checks, plus baseline/oracle/sanitizer gates; independent compiler review passed. Final integrated verification passed. [VALUE-CALLS.md](../compiler/VALUE-CALLS.md) specifies left-to-right snapshots, signature visibility, 64-field/6-argument limits and the temporary private ABI.

The reviewed milestone009 compiler establishes reusable value definitions through explicit one/two-parameter Scalar-constrained class templates and a real `std.utility` pair. Instances preserve defining-module lexical binding, nominal ordered-tuple identity, private access, complete initialization and independent value boundaries. The graph is capped at 64 templates and 256 concrete specializations. Its 117 template cases and 393 direct IR cases pass with existing suites, ten exhaustive-dispatch checks and sanitizers; final integrated verification passed. See [TEMPLATES.md](../compiler/TEMPLATES.md). General concepts, deduction, function templates, nested arguments and recursive instantiation remain deferred. Milestone010 now implements that bounded collection: compiled `std::array<T,N>` with scalar T, literal N from 1..64, complete zero initialization, private fixed-array fields, checked copied access and mutable set. Canonical `builtin::array` and its fixed bare `array` alias are distinct from the explicitly qualified wrapper; the builtin namespace is reserved. Logical field metadata and flat leaf layout remain separate, and ordinary value boundaries copy at most 64 leaves per class. The checkpoint passes 216 container cases, 463 direct IR cases, ten exhaustive-dispatch controls, 18 native receiver-array IR checks and existing suites/sanitizers. Independent compiler review passed; final milestone010 integration verification passed. See [FIXED-CONTAINERS.md](../compiler/FIXED-CONTAINERS.md). Milestone011 subsequently established bounded Value composition; the reviewed milestone012 candidate adds closed enums and copied method results for recoverable numeric reports.

General constructor bodies, overloads, inheritance/interfaces, resource fields, heap storage, source-visible aggregate borrowing and class-valued method parameters remain deferred. Bounded nested class fields and constructor class snapshots are implemented; copied class-valued method results are reviewed in milestone012. Constructor/method call cycles are conservatively rejected; ordinary scalar recursion still permits stack exhaustion. This partial stage does not waive the scalar semantic evidence gate or satisfy the general lifetime gate below.

Implement inline value classes, Java-inspired encapsulation/interfaces, explicit reference ownership and dispatch, fields, construction, deterministic destruction, borrowing across function calls, and constrained generics. Do not make interfaces or identity force heap allocation, garbage collection, or boxing. Define lifetimes, aliasing, pointer provenance, synchronization, and trusted intrinsics in a formal core calculus before claiming soundness. Classify which language features the model actually covers.

**Gate:** tests cover partial initialization, exception/error paths, move/drop ordering, nested and escaping borrows, generic instantiation, and invalidation. Complete an independent soundness review and publish remaining assumptions. Demonstrate that safe clients cannot violate trusted interfaces. A proof of a core calculus is not yet a proof of the compiler.

## 3 Reflection and module contracts

Current type size/ID/field-count queries and runtime size/count lookup include declared classes. They are useful metadata plumbing, not the typed generation or safe dynamic invocation required here.

Specify and implement safe key-set queries, mapped types and conditional types with bounded evaluation, checked refinement and ownership-preserving constraints. Reject unchecked top types, assertion loopholes, private-member exposure and transformations that duplicate resources. Add typed compile-time reflection and generation. Introduce opt-in runtime descriptors, checked invocation, exported visibility, dynamic ownership, effect enforcement, and descriptor leases. Define versioned module/package identities and an Aurora-native ABI without adopting C++ layouts.

**Gate:** reflective paths enforce the same authority and lifetime rules as static paths; malformed descriptors and stale generations are rejected; metadata stripping is tested; builds are reproducible and compile-time resource limits work. Keep dynamic borrowed returns disabled until their safety model is established.

## 4 Isolated kernel services

Trusted bootstrap code now includes breakpoint/exception entry, E820 usable-map validation, and a bounded page arena with generation/epoch tickets. These are partial prerequisites, not general protected processes or a physical/virtual memory manager. Separately compiled user fixtures now run sequentially in three owned CR3 domains with leased stacks, bounded scalar returns and validated compiler-fault containment. Foreign-access denial, zeroed frame reuse and root restoration are tested. Milestone005 adds a bounded QEMU xAPIC integer-only preemption harness, forced spinner cancellation and safe context restoration. General process lifecycle, SMP, IPC and native service APIs remain absent. The final exact-source aggregate passed all twenty-eight configured gates; see the verification record for snapshot-specific outcomes.

Replace the demo path with memory ownership, protected address spaces, traps, preemption, capability operations, bounded IPC, and service supervision. Introduce a minimal driver broker, then one emulator-backed device service. Design proof-friendly interfaces before adding broad subsystems.

**Gate:** an untrusted service cannot access another service's memory or forge authority; revocation and restart are tested; resource exhaustion is contained; IRQ floods do not monopolize the system. Publish the trusted computing base and exact platform assumptions. Test security properties separately from throughput.

## Native core and library dependency gates

Develop two explicit Aurora-authored layers: a platform/runtime replacing libc responsibilities without its C API/ABI, and a safe C++-recognizable standard library for strings, containers, algorithms, ranges, ownership, concurrency and reflection. Neither host C++ libraries nor empty package scaffolding satisfy this requirement. See [library-stack.md](library-stack.md) for profile contracts and staged tests.

The first real std.core scalar module now compiles through explicit imports and runs in a protected user image. Expand this into a genuinely freestanding core on specified value/lifetime semantics; the current scalar core, encapsulated numeric values and checked integer algorithms do not constitute the full library stack. Allocation follows checked ownership/destruction, layout arithmetic and region/quota capabilities. User startup and service wrappers require a native ABI/loader, protected task lifecycle and validated capability boundary; a controlled user-domain execution probe is not a complete runtime. Kernel facilities use their own nonblocking/IRQ-safe profile. Threading waits for both kernel scheduling and a language memory model. Text/numeric APIs require explicit Unicode, rounding/error and resource-limit contracts.

**Gate:** real library operations are consumed by compiled Aurora programs and pass normal/failure/lifetime tests without target host-runtime dependencies. Collections prove safe invalidation behavior; system wrappers test cancellation, partial I/O and reclamation; native rebuilds demonstrate the declared package set. Ports need explicit backend/API adaptation or safe rewrites and license review before reuse, with no inferred C/binary/POSIX compatibility.

## 5 Aurora self-hosting

Port compiler components and selected kernel services incrementally. Keep the bootstrap compiler available for cross-checking. Remove temporary C++/assembly logic where the language can express it soundly; retain only necessary architecture-specific operations behind audited intrinsics.

**Gate:** the compiler compiles itself, builds the system, and passes differential and regression tests against the prior toolchain. Perform multi-stage reproducibility checks and analyze mismatches. Self-hosting proves ecosystem usefulness, not safety or freedom from compiler backdoors.

## 6 Hardware contracts and profiles

Milestone006 adds a separate validated UEFI handoff consumer with eight OVMF
gates, own post-firmware stack/mappings and compiled Aurora execution. It is
not a physical-platform qualification or a UEFI port of the BIOS scheduler.
See the [handoff contract](../kernel/uefi/README.md).

The first complete-machine target is [Framework Laptop 13 / Ryzen 7 7840U](framework-13-7840u.md), including the mainboard and all installed device classes, multi-user services and persistent filesystems. This is a qualification target, not current hardware support.

Publish device schemas, vendor reference firmware, simulation models, and conformance suites. Start with a narrowly defined platform and storage/network/input devices before expanding to graphics, mobile, embedded, accelerators, and specialized devices. Use distinct trusted-device and isolated-device profiles.

**Gate:** each supported hardware/firmware tuple passes discovery, DMA isolation, fault injection, power transition, update/recovery, and performance tests. Independent implementations demonstrate protocol interoperability. Advertise only tested tuples and explicit limitations.

## 7 Native desktop and developer system

Build the requested Sway-like tiling desktop, Foot-like terminal, and Wayland-like display protocol as native Aurora components after process isolation, input/display services, text libraries, GPU buffer contracts and native package tooling are usable. These are functional design references, not C source, configuration, wire-protocol, ABI or POSIX compatibility promises. The target remains a native system authored in Aurora.

**Gate:** demonstrate tiling/workspaces and window lifecycle, hotplugged input/outputs, authority-checked clipboard/selection, accessible keyboard navigation and assistive interfaces, text shaping/input methods, GPU composition and reset recovery. The terminal must pass a specified Unicode/emulation profile and native PTY-equivalent process/session tests for resize, backpressure, EOF/hangup and job control. Use the detailed [system-release acceptance inventory](system-release.md); none of these desktop facilities is implemented by the current boot milestone.

## 8 Native runtime and FOSS ports

After the foundation is mature, choose useful language runtimes, libraries and FOSS applications to port to the native kernel/compiler ecosystem. Inventory dependencies and unsafe assumptions before selecting native backend/API adaptation or an Aurora safety-oriented rewrite. Specify runtime ownership, threading and error boundaries; do not quietly add a C compatibility layer or promise that existing Linux source/binaries run unchanged. Resolve any exception to the all-Aurora implementation goal explicitly.

**Gate:** each selected port has a named version, reviewed licensing/attribution plan, native dependencies, functional/isolation tests, package/update owner and documented exclusions. The existence of an upstream project is neither permission to copy its code indiscriminately nor proof of port feasibility. Ports follow readiness of their foundation rather than an arbitrary date.

## Performance qualification

Add representative algorithm, allocation, dispatch, synchronization, reflection and systems workloads with equivalent C baselines. Keep algorithms, validation/error behavior, data layouts where comparable, optimization settings and hardware explicit. Record layout/padding, allocation counts, atomics/contention, dynamic dispatch and reflective-operation costs rather than declaring every abstraction zero-cost.

**Gate:** publish reproducible throughput, latency, memory and code-size comparisons, identify remaining regressions, and validate any safety-check elimination. Real-time profiles also require bounded/worst-case behavior. A benchmark result applies to its workload and target, not to every program.

## 9 Production assurance

Stabilize release/update policy, reproducible packages, recovery, security response, developer tooling, standard libraries, accessibility, and platform-specific performance/energy budgets. Extend formal verification toward the implemented nucleus and critical compiler transformations; state what is outside each proof.

**Gate:** independent review, sustained adversarial testing, defined support ownership, recoverable upgrades, and published assurance arguments. General-purpose readiness requires usable applications and operations as well as a booting kernel.

## Evidence and checkpoint history

Preserve the milestone001 source manifest and associated logs as historical evidence for their original checkpoint and earlier source language, including its then-wrapping arithmetic. Do not edit historical receipts to imply they tested the new C++-style syntax or semantics. Every later verification batch identifies its own source snapshot and outcomes; new capability claims cannot be backdated into the earlier manifest. Track requirements and passed/failed/missing gates without speculative completion percentages.

## Open decisions

Resolve these by prototypes and RFCs rather than presenting the initial proposal as settled:

- The smallest effect system that handles blocking, allocation, authority, and async composition without unusable signatures.
- Reference-class identity and arenas, shared ownership cycles, and dynamic borrowed-return representation.
- Revocation cost, delegated authority, and bounded IPC priority donation.
- Recovery semantics for non-idempotent device commands and partial persistence.
- How narrowly to profile real-time and non-isolated embedded machines.
- The formal model, proof tooling, target architectures, and optimizer-validation strategy.

The next practical priority is to close scalar and class semantic evidence gaps, validate the current kernel additions, and resolve review findings before broadening the language. Partial implementations in later stages do not count as passing earlier gates; more syntax alone would make the safety story harder to validate.

## Current bounded checkpoint: milestone013

Checked u8 arithmetic/conversions, compact byte-stride storage and recoverable
endian codecs are implemented and independently reviewed. Controlled client and
service phases have immutable interrupt-count authority; an offender can be
retired and rebound after quiescence while a peer progresses. All 139 actual modes
pass on the final packed-byte compiler. The verification record distinguishes
independent slice review, complete final integration and fresh parent reruns.

Next language scope is readonly whole-array byte spans and synchronous forwarding,
with static shared borrowing, bounded lexical/call lifetimes and a recoverable
binary reader. No mutable view, return/field escape, raw-address conversion,
private-wrapper exception or heap allocator is implied. Branch/backedge and
argument-evaluation borrowing must fail closed when unsupported.

Next platform scope is validated read-only PCI BAR resource handoff for a narrow
namespace-free emulated NVMe fixture. Only documented non-destructive identity,
capability and inactive-state register checks are contemplated. No controller
reset, command/BME change, queues, DMA or interrupt activation is included. Active
inherited firmware state must be reported and rejected rather than silently reset.
IOMMU/requester authority, invalidation/fault handling and revocation are separate
prerequisites before storage DMA. Neither next scope is implemented by this checkpoint.
