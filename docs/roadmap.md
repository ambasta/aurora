# Aurora implementation roadmap

This roadmap separates a useful executable seed from the research and engineering required for a safe, self-hosted ecosystem. Milestones have evidence gates, not speculative delivery dates. Passing an earlier milestone does not imply later guarantees. The requested scope is a months-scale, multi-stage effort toward a fully self-hosted native ecosystem with Linux-stack-equivalent functionality authored in Aurora, plus qualification across all Zen CPUs and Navi/RDNA-and-later GPUs. This scope is not a delivery estimate or a supported-device claim. See [system release requirements](system-release.md) and [AMD qualification](amd-support.md).

## 0 Bootstrap integration

Produce a reproducible host build, a small source compiler, negative parser/type tests, and an x86-64 emulator image that calls an Aurora-generated function and reports 42. Keep the temporary host/compiler and C++/assembly kernel adapters visible and narrowly scoped.

**Gate:** fresh build succeeds; accepted examples execute correctly; rejected examples fail with diagnostics; emulator serial output demonstrates entry, the compiled function result, and a controlled terminal state. Record exact tools and test commands. A built image without a boot log is only a build result.

The current integration has passed the QEMU boot path and reported 42 from compiled Aurora code. This is milestone evidence for that snapshot, not a claim that the later gates have passed. Class values/reflection and kernel exception/memory bring-up have since expanded; fresh integration and all three emulator gates passed for that expanded checkpoint. See the [verification record](verification.md) for final build and test results.

## 1 Precise scalar semantics

Specify evaluation order, integer overflow, division, conversions, initialization, branch joins, local mutation, moves, and lexical borrow boundaries. Current supported scalar arithmetic intentionally wraps modulo 2^64; decide and test the transition to the proposed checked-default arithmetic before changing that behavior. Memory/index/range arithmetic must be separately checked when introduced. Align emitted behavior with the specification. Add malformed-source fuzzing and differential execution against a simple reference interpreter. Ensure unsupported forms fail closed.

**Gate:** executable semantics and compiler agree across edge cases and generated programs, including failing paths. Document coverage and counterexamples. Do not generalize scalar ownership checks into claims about heap safety.

## 2 Class and lifetime core

A partial implementation exists: local scalar-field classes, named initialization, independent value copies, and field access/mutation. It deliberately excludes methods, nested aggregates, heap storage, aggregate borrowing, and class arguments/results. This partial stage does not waive the scalar semantic evidence gate or satisfy the lifetime gate below.

Implement inline value classes, explicit reference ownership, fields, construction, deterministic destruction, borrowing across function calls, and constrained generics. Define lifetimes, aliasing, pointer provenance, synchronization, and trusted intrinsics in a formal core calculus before claiming soundness. Classify which language features the model actually covers.

**Gate:** tests cover partial initialization, exception/error paths, move/drop ordering, nested and escaping borrows, generic instantiation, and invalidation. Complete an independent soundness review and publish remaining assumptions. Demonstrate that safe clients cannot violate trusted interfaces. A proof of a core calculus is not yet a proof of the compiler.

## 3 Reflection and module contracts

Current type size/ID/field-count queries and runtime size/count lookup include declared classes. They are useful metadata plumbing, not the typed generation or safe dynamic invocation required here.

Add typed compile-time reflection and generation. Introduce opt-in runtime descriptors, checked invocation, exported visibility, dynamic ownership, effect enforcement, and descriptor leases. Define versioned module/package identities and an Aurora-native ABI without adopting C++ layouts.

**Gate:** reflective paths enforce the same authority and lifetime rules as static paths; malformed descriptors and stale generations are rejected; metadata stripping is tested; builds are reproducible and compile-time resource limits work. Keep dynamic borrowed returns disabled until their safety model is established.

## 4 Isolated kernel services

Trusted bootstrap code now includes breakpoint/exception entry, E820 usable-map validation, and a bounded page arena with generation/epoch tickets. These are partial prerequisites; they provide neither protected processes nor a general physical/virtual memory manager. The latest additions passed fresh hosted and emulator checks; see the verification record.

Replace the demo path with memory ownership, protected address spaces, traps, preemption, capability operations, bounded IPC, and service supervision. Introduce a minimal driver broker, then one emulator-backed device service. Design proof-friendly interfaces before adding broad subsystems.

**Gate:** an untrusted service cannot access another service's memory or forge authority; revocation and restart are tested; resource exhaustion is contained; IRQ floods do not monopolize the system. Publish the trusted computing base and exact platform assumptions. Test security properties separately from throughput.

## 5 Aurora self-hosting

Port compiler components and selected kernel services incrementally. Keep the bootstrap compiler available for cross-checking. Remove temporary C++/assembly logic where the language can express it soundly; retain only necessary architecture-specific operations behind audited intrinsics.

**Gate:** the compiler compiles itself, builds the system, and passes differential and regression tests against the prior toolchain. Perform multi-stage reproducibility checks and analyze mismatches. Self-hosting proves ecosystem usefulness, not safety or freedom from compiler backdoors.

## 6 Hardware contracts and profiles

Publish device schemas, vendor reference firmware, simulation models, and conformance suites. Start with a narrowly defined platform and storage/network/input devices before expanding to graphics, mobile, embedded, accelerators, and specialized devices. Use distinct trusted-device and isolated-device profiles.

**Gate:** each supported hardware/firmware tuple passes discovery, DMA isolation, fault injection, power transition, update/recovery, and performance tests. Independent implementations demonstrate protocol interoperability. Advertise only tested tuples and explicit limitations.

## 7 Production assurance

Stabilize release/update policy, reproducible packages, recovery, security response, developer tooling, standard libraries, accessibility, and platform-specific performance/energy budgets. Extend formal verification toward the implemented nucleus and critical compiler transformations; state what is outside each proof.

**Gate:** independent review, sustained adversarial testing, defined support ownership, recoverable upgrades, and published assurance arguments. General-purpose readiness requires usable applications and operations as well as a booting kernel.

## Open decisions

Resolve these by prototypes and RFCs rather than presenting the initial proposal as settled:

- The smallest effect system that handles blocking, allocation, authority, and async composition without unusable signatures.
- Reference-class identity and arenas, shared ownership cycles, and dynamic borrowed-return representation.
- Revocation cost, delegated authority, and bounded IPC priority donation.
- Recovery semantics for non-idempotent device commands and partial persistence.
- How narrowly to profile real-time and non-isolated embedded machines.
- The formal model, proof tooling, target architectures, and optimizer-validation strategy.

The next practical priority is to close scalar and class semantic evidence gaps, validate the current kernel additions, and resolve review findings before broadening the language. Partial implementations in later stages do not count as passing earlier gates; more syntax alone would make the safety story harder to validate.
