# Aurora architecture

Aurora is a temporary name for a clean-break language and operating-system ecosystem. This document proposes the target architecture; it does not certify the bootstrap as a safe language or a production kernel. “Must” describes a proposed contract that later implementations and conformance tests must satisfy.

## Scope and assumptions

The target assumes open, inspectable firmware and vendors willing to implement Aurora's contracts. That removes a compatibility constraint, not the need for hardware specifications, validation, isolation, or recovery. General-purpose computers, servers, phones, embedded systems, accelerators, and specialized peripherals are design targets, not supported hardware claims. The requested long-term scope includes all AMD Zen CPU generations and Navi/RDNA-and-later GPUs, with per-device qualification rather than inferred universal coverage. A self-hosted native system should eventually supply the practical stack of a Linux-based system, including toolchain, packages, services, desktop, shell, and applications, authored in Aurora; this is functional ambition, not a Linux ABI or source-compatibility promise.

No C/C++ source, header, object model, calling convention, or library compatibility is promised by the new language. The first bootstrap uses existing host tools, a modern C++ kernel shim, architecture-specific assembly, and a temporary link boundary to run an Aurora-compiled function. These are replaceable construction tools, not language features or a commitment to preserve their interfaces.

## Language identity and assurance goals

Aurora should feel recognizably like a modern C++ API while discarding unsafe features and C/source/ABI compatibility. The confirmed brief combines C-level performance ambitions, Rust-level memory-safety ambitions, Java-inspired encapsulation/interfaces, and a safe TypeScript-inspired type algebra with both compile-time and runtime reflection. Those are independent obligations to specify and verify, not interchangeable slogans or inherited guarantees.

Inline classes and explicit static/dynamic dispatch avoid making Java-inspired OOP imply mandatory boxing or garbage collection. Key queries, mapped types and conditional types must preserve nominal resource identity, visibility, ownership and effects. Reflection may inspect or invoke only through checked authority; neither type transformations nor dynamic calls can fabricate a borrow or bypass privacy. The ordinary language offers no unsafe assertion escape hatch. Necessary hardware operations remain a small trusted implementation boundary.

## Proposed system boundaries

The privileged nucleus owns address spaces, page ownership, threads, scheduling budgets, interrupts, capability tables, IPC endpoints, and the mechanism for configuring DMA isolation. It should contain neither a general filesystem nor network, graphics, or ordinary device-driver policy.

Isolated services provide storage, networking, display, input, audio, device management, package management, and application runtimes. Each receives only explicit capabilities to resources it needs. Capability transfer is an intentional operation: an identifier in a message does not confer authority. Services may delegate attenuated rights, subject to an explicit revocation model. There is no ambient superuser namespace available to every process.

A driver service owns a device session, not physical memory in general. A privileged device broker validates discovery data and grants scoped register, interrupt, and DMA capabilities. Devices without enforceable isolation belong to a separate trust profile and cannot silently satisfy the isolated-driver profile.

IPC has a bounded, copy-based control path plus explicit shared-buffer grants for bulk data. Interfaces use generated, versioned schemas with checked decoding. Cross-process references are handles with generations and rights; they are never borrowed machine addresses. Shared memory must specify ownership transitions, synchronization, cancellation, and crash recovery. Zero-copy is a negotiated optimization, not a default that weakens the ownership contract.

## Scheduling and failure

The target scheduler combines preemptible execution with explicit service budgets. Ordinary workloads use fairness; real-time profiles require admission control and declared deadlines. Priority inheritance or budget donation across synchronous IPC must be specified before claiming bounded response time. A clock, timer, and interrupt model must define monotonicity, ordering, and wrap handling for each platform.

Interrupt handlers acknowledge and enqueue bounded work; driver-service workers do the expensive processing. Storm limiting, lost-interrupt recovery, and backpressure are mandatory contract topics. No IRQ path allocates unpredictably or performs blocking service calls.

A service crash revokes its capabilities and quiesces its hardware before resources are reused. Restart creates a new generation; stale replies and handles must fail. Recovery does not automatically replay non-idempotent writes. Supervisors report operations with uncertain outcomes to their clients.

## Security and trust

Memory safety, authority isolation, and semantic correctness are separate obligations. A memory-safe driver can still issue a destructive device command; a capability system can still authorize the wrong principal. Threat models must cover malicious applications, faulty drivers, hostile devices, compromised firmware, supply-chain changes, and resource exhaustion. Open source is an audit opportunity, not proof of correctness.

The target includes measured boot, reproducible signed packages, rollback policy, auditable capability grants, and update recovery. Trust roots, revocation, user-controlled ownership, and physical recovery must be explicit platform contracts. Remote attestation must not silently remove an owner's ability to run their own software.

The initial assurance boundary includes compiler, privileged intrinsics, kernel, boot path, and relevant hardware/firmware. Language-level proofs alone do not establish an end-to-end security claim. A future verified nucleus would need a precise machine model and explicit proof assumptions.

## Compiler architecture

The intended pipeline is source modules → typed syntax → ownership/effect checked IR → lowered IR → machine code. Typed IR retains lifetimes, initialization state, authority requirements, and destruction edges long enough to validate transformations. Runtime type descriptors and IPC serializers derive from the same checked type model. A bounded type-evaluation layer handles key sets, mapped types and conditional types while retaining visibility, ownership and effect constraints. Its result is checked type information, never authority to reinterpret live storage.

Compile-time computation is deterministic and resource-bounded. It cannot read arbitrary host files, access the network, or acquire credentials. Build inputs and permitted tools must be declared. Diagnostics should identify the resource or borrow involved, the conflicting use, and the point that established it.

The bootstrap uses modern C++-recognizable declarations and emits GNU x86-64 assembly for scalars, local scalar-field class values and fixed scalar arrays. It checks local integer ownership, signed arithmetic overflow and array bounds, supports restricted while loops, and generates limited type-size/field-count reflection metadata. The old fn/let source syntax is not retained. Independent review and a fresh aggregate build passed for this expansion; the verification record contains the receipts. The new implementation separates frontend parsing, trusted semantic/lifetime analysis, typed IR, IR validation and x86-64 lowering. Only an immutable validated module reaches the backend. The IR verifier checks operand types, initialization, control-flow/frame invariants and array bounds-token identity/dominance; it does not independently re-prove source ownership, const or privacy checks. Checked arithmetic remains explicit in IR. No optimizer, general effect system or soundness proof is present. See [compiler phase contracts](../compiler/ARCHITECTURE.md). Corrected-source aggregate integration, semantic-oracle runs and sanitizer gates passed; earlier receipts apply only to their snapshots. Self-hosting follows semantic stability and differential tests, rather than becoming evidence of correctness by itself.

## Tradeoffs and alternatives

Service isolation adds IPC, scheduling, and operational complexity. Copy-based IPC may lose throughput; shared buffers require a substantially harder protocol. Static ownership restricts some graph and callback patterns; explicit shared ownership and arenas improve expressiveness but complicate reasoning. Runtime reflection adds metadata, disclosure risk, and dispatch cost. Real-time predictability constrains allocation and dynamic features.

These are proposed choices for an auditable general ecosystem, not a claim of a universally best kernel. Measure alternatives against attack surface, worst-case latency, throughput, power, memory use, developer effort, and recovery behavior. Keep exceptions explicit and limited to profiles whose tests demonstrate their costs.

## Performance acceptance

The C-like performance goal requires equivalent-C benchmarks with matched algorithms, semantic/error behavior, optimization settings and named platforms. Publish latency, throughput, memory and code-size results, including unfavorable outcomes. Track layout/padding, allocations, atomics, contention, dispatch, checks and reflection costs separately. Safety-check elimination requires validated reasoning; unchecked comparison baselines do not justify weakening semantics. No blanket zero-cost abstraction or no-overhead claim is part of this proposal.

## Current boundary and next reading

The current trusted bootstrap uses E820-validated frames, IDT/GDT/TSS and guarded stacks, W^X/NX/WP mappings, and three separately owned CR3 domains with leased user stacks. Compiled Aurora programs, including an imported std.core call, run in those bounded domains. Foreign-code/data denial, hardware-root validation, inactive teardown, stale handles, zeroing/reuse, allocation rollback and kernel-root restoration are exercised. Only a bounded scalar return or validated compiler trap can finish a controlled run; unexpected kernel-origin or transition events remain fatal. All 19 configured emulator gates passed on the final module-capable compiler.

This is sequential controlled execution, not a scheduler, SMP, a general loader/process lifecycle or a native syscall/runtime contract. The allocator and hardware code remain trusted C++/assembly bootstrap components. No physical AMD qualification or complete memory-safety proof follows. Consult the [verification record](verification.md) for exact source, receipts and limitations.

The compiler now resolves a bounded module graph from explicit roots with exports, namespaces and defining-module identities. Reflection views enforce ordinary module visibility. A narrow Linux host adapter pins source/output directory authority, rejects symlink escapes, captures file bytes and atomically replaces an output leaf under its documented assumptions. It does not provide a whole-repository atomic snapshot or protection from a privileged host. The initial Aurora-authored std.core module is a real dependency of protected user programs; most runtime/standard-library facilities remain requirements.

See [language design](language.md), [device contract](device-contract.md), and [roadmap](roadmap.md).

For context, [seL4's project overview](https://sel4.systems/About/) describes a high-assurance microkernel with formal verification. It is a useful reference point for the assurance ambition; Aurora neither reuses those proofs nor inherits their guarantees.
