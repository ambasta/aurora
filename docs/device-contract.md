# Aurora device contract

This proposal defines the interface Aurora would require from cooperating hardware and open firmware vendors. It is not an implemented bus standard, driver collection, or promise of current device support. The x86-64 emulator bootstrap exercises only a tiny machine-specific path.

## Common discovery envelope

Every platform exposes a bounded, versioned discovery graph through an authenticated boot handoff. The graph identifies CPUs, memory regions, interrupt domains, timers, buses, DMA translation units, power dependencies, and device endpoints. A node includes:

- Stable vendor/product identity and instance generation, distinct from a capability.
- Protocol identifier, major/minor version, and explicit optional feature bits.
- Resource requirements, alignment, address widths, limits, and isolation group.
- Interrupt routing and acknowledgement contract.
- DMA coherence, ordering, cache maintenance, and completion semantics.
- Power/reset dependencies, latency bounds where provided, and recovery behavior.
- Firmware identity, update/rollback policy, and discovery provenance.

A checked decoder rejects overlapping protected resources, malformed lengths, unknown required fields, cycles in dependency graphs, and impossible address arithmetic. Discovery is a statement to validate, not authorization to map physical resources. Root trust and manifest signatures do not prove the device behaves correctly.

A major version change requires a compatible adapter or rejection. Minor revisions add optional fields/features without changing existing behavior. Negotiation selects the intersection of supported features; an unavailable mandatory feature causes an explicit failure. Extensions are namespaced and cannot silently change base semantics. Wire layouts define byte order, integer width, alignment, length limits, and reserved-field behavior independently of language class layout.

## Device session lifecycle

The broker moves an endpoint through discovered → validated → assigned → active → quiescing → reset/released. Every command and completion carries a session generation and correlation ID. After hot-unplug or reset, stale completions cannot modify a new session.

Only the broker grants device register windows, interrupt endpoints, and DMA domains. Rights distinguish inspection, configuration, command submission, reset, firmware update, and delegation. Drivers have no blanket physical-address capability. Configuration space and register operations use typed accessors with declared widths and side effects; ordinary compiler loads are not an MMIO specification.

Timeouts, cancellation, partial completion, retries, and operation idempotency must be explicit. A timeout does not prove the device stopped. Before release, the broker stops new submission, masks delivery where needed, drains or resets outstanding work, invalidates translations with required completion barriers, and only then releases memory. If quiescence cannot be established, affected memory remains quarantined or the containing device/platform is reset.

## DMA and shared buffers

The isolated profile requires an enforceable DMA translation boundary and defined isolation groups. A driver sees a DMA mapping token scoped to a device session, region, direction, permissions, and lifetime. It never receives authority over all physical RAM. Peer-to-peer paths and translation caches must be included in the platform's isolation argument.

The buffer state machine separates CPU-owned, submitted/device-owned, completed, and reclaimed states. Submission temporarily removes incompatible CPU access; completion restores access only after required ordering/cache operations. Descriptor rings obey the same rules. A malicious completion length is validated against the original grant, not trusted.

For coherent and non-coherent devices alike, the contract specifies visibility, ordering, cache maintenance, and fencing. Mapping revocation must finish before pages are reassigned. The platform must test reset during transfer, cancellation races, stale DMA, invalid descriptors, and device writes outside grants.

A platform without a usable translation boundary may provide a separately named trusted-device profile or deny the device. Bounce buffers alone do not establish protection against a malicious bus master. No weak profile is advertised as equivalent to hardware-isolated DMA.

## Interrupts, scheduling, and power

Interrupt delivery uses a capability scoped to one source and session. Edge/level semantics, acknowledgement order, coalescing, queue overflow, and fallback polling are negotiated. The nucleus performs bounded delivery; service workers consume a declared CPU budget. Flooding one endpoint must not starve unrelated services. Real-time claims require measured or justified bounds across firmware, device, interrupt, scheduler, and IPC paths.

Power management uses explicit dependency ordering and session-aware transitions. Suspend first quiesces DMA and submissions; resume revalidates firmware/resource state before restoring grants. Wake sources are independently authorized. Driver requests express latency/energy needs; a policy service selects operating points within thermal and platform safety limits. Firmware callbacks must not acquire undeclared access to OS memory.

## Device families

Family protocols extend the common envelope rather than putting every behavior into the kernel:

- Storage: block geometry, durability barriers, discard, integrity, atomicity, and ambiguous-write recovery.
- Networking: bounded queues, packet ownership, offload validation, link state, and isolation among virtual endpoints.
- Graphics and accelerators: command validation, per-context memory, preemption, watchdogs, reset scope, and buffer fences.
- Input, audio, cameras, and sensors: timestamps, stream formats, latency, overrun behavior, and explicit privacy authority.
- Compute and embedded platforms: topology, interrupt/timer guarantees, isolation limits, and power-state constraints.

These are specification work areas. Listing a family is not a driver implementation or a conformance result. A genuinely unsupported operation returns an explicit error rather than simulating success.

## Conformance evidence

A vendor submission needs machine-readable schemas, a simulator or test endpoint, reproducible firmware sources/build instructions, limits, error behavior, and a threat model. Tests cover positive behavior and adversarial sequences: malformed discovery, version skew, queue saturation, reset, power loss, surprise removal, stale handles, corrupt replies, interrupt storms, and DMA faults.

Certify a precise tuple of device revision, firmware build, protocol version, platform isolation profile, and Aurora build. Publish results and remaining exclusions. One passing emulator establishes only that emulator configuration; it cannot establish general hardware support. Performance and energy profiles supplement correctness tests rather than replacing them.
