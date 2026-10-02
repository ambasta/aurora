# Aurora architecture

Aurora is a temporary name for a clean-break language and operating-system ecosystem. This document proposes the target architecture; it does not certify the bootstrap as a safe language or a production kernel. “Must” describes a proposed contract that later implementations and conformance tests must satisfy.

## Scope and assumptions

The target assumes open, inspectable firmware and vendors willing to implement Aurora's contracts. That removes a compatibility constraint, not the need for hardware specifications, validation, isolation, or recovery. General-purpose computers, servers, phones, embedded systems, accelerators, and specialized peripherals are design targets, not supported hardware claims. The requested long-term scope includes all AMD Zen CPU generations and Navi/RDNA-and-later GPUs, with per-device qualification rather than inferred universal coverage. A self-hosted native system should eventually supply the practical stack of a Linux-based system, including toolchain, packages, services, desktop, shell, and applications, authored in Aurora; this is functional ambition, not a Linux ABI or source-compatibility promise.

No C/C++ source, header, object model, calling convention, or library compatibility is promised by the new language. The first bootstrap uses existing host tools, a modern C++ kernel shim, architecture-specific assembly, and a temporary link boundary to run an Aurora-compiled function. These are replaceable construction tools, not language features or a commitment to preserve their interfaces.

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

The intended pipeline is source modules → typed syntax → ownership/effect checked IR → lowered IR → machine code. Typed IR retains lifetimes, initialization state, authority requirements, and destruction edges long enough to validate transformations. Runtime type descriptors and IPC serializers derive from the same checked type model.

Compile-time computation is deterministic and resource-bounded. It cannot read arbitrary host files, access the network, or acquire credentials. Build inputs and permitted tools must be declared. Diagnostics should identify the resource or borrow involved, the conflicting use, and the point that established it.

The bootstrap emits GNU x86-64 assembly for scalars and local class values containing scalar fields. It performs lexical integer ownership checks and generates limited built-in/class reflection metadata. It is not yet the compiler architecture above. Self-hosting follows semantic stability and differential tests, rather than becoming evidence of correctness by itself.

## Tradeoffs and alternatives

Service isolation adds IPC, scheduling, and operational complexity. Copy-based IPC may lose throughput; shared buffers require a substantially harder protocol. Static ownership restricts some graph and callback patterns; explicit shared ownership and arenas improve expressiveness but complicate reasoning. Runtime reflection adds metadata, disclosure risk, and dispatch cost. Real-time predictability constrains allocation and dynamic features.

These are proposed choices for an auditable general ecosystem, not a claim of a universally best kernel. Measure alternatives against attack surface, worst-case latency, throughput, power, memory use, developer effort, and recovery behavior. Keep exceptions explicit and limited to profiles whose tests demonstrate their costs.

## Current boundary and next reading

The current bootstrap has booted under QEMU, called an Aurora-compiled function, and reported 42 over serial. This establishes the compiler-to-kernel execution path for that emulator configuration. Subsequent implementation adds IDT breakpoint dispatch, fail-stop exception paths, validation of an E820 usable-memory map, and a bounded 128-page arena allocator with move-only generation/epoch tickets. Fresh integration, sanitizer/model checks and all three emulator gates passed; the verification record owns the exact evidence. This allocator is trusted C++ bootstrap code, not Aurora-language heap ownership. Exception delivery is not a scheduler or a general hardware-interrupt stack. Paging used to enter an execution mode is not process isolation. Printing a value is not a scheduler, IPC implementation, device framework, or memory-safety proof. Consult the [verification record](verification.md) and current build/test output for the tested snapshot and remaining limits.

See [language design](language.md), [device contract](device-contract.md), and [roadmap](roadmap.md).

For context, [seL4's project overview](https://sel4.systems/About/) describes a high-assurance microkernel with formal verification. It is a useful reference point for the assurance ambition; Aurora neither reuses those proofs nor inherits their guarantees.
