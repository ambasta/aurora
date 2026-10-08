# Aurora implementation roadmap

For what exists now, use the [current project state](completeness-matrix.md#current-project-state).
This page defines dependencies and observable completion gates, not a second
feature-status log. All six destination goals remain open. The detailed release
inventory is in [system release requirements](system-release.md); storage and
physical-platform requirements retain their own linked acceptance contracts.

## Language and system co-evolution

The language, kernel, userspace libraries, drivers, services and applications
advance together, including drivers wherever they execute. Tie each language extension to a real consumer, the capability
it needs and its safety guarantees. Use existing Aurora features for substantive
subsystem ownership now, rather than waiting for self-hosting or adding only
stateless predicates. GNU C++ remains a legitimate bootstrap tool: retire a
C++ component after its Aurora replacement passes equivalent qualification,
without removing hardware/ownership checks prematurely.

A persistent Aurora-owned console Line/session behind a sealed, bounded
ConsoleSession I/O capability is a proposed next migration. Its lifetime and
transport contract still need implementation and acceptance; the current
protected-command qualification does not claim that migration.

## 1. Protected programs and file services

Build from the existing protected-domain fixtures, bounded scheduling, copied
request/reply IPC, cancellation/restart and Aurora policy functions. These are
working bounded mechanisms, not a general process or runtime API. The
[protected command console](program-console-contract.md) demonstrates one embedded
compiled application with scoped recovery and authority-failure qualification.
General program lifetime and a RAM-backed file service remain the next extensions.

Next integrate protected-program startup/lifecycle and capability-scoped file
services with explicit resource limits, cancellation, partial I/O and reclamation.
Use RAM-backed service tests before claiming durable device-backed operation.
Gate: real compiled programs exercise allowed operations; foreign/stale authority,
exhaustion, restart and interrupted operations fail safely without cross-domain
access. Trusted C++/assembly ownership and commit boundaries remain explicit.

## 2. DMA-safe transport and persistent storage

Actual DMA conformance is blocked. Discovery, CPU-only table/queue preparation,
pin ownership and [test-only event/completion references](iommu-event-completion-oracle.md)
are prerequisites, not observed hardware isolation or completion.
A permissible independently reviewed conformance path must establish default-deny
translation, invalidation completion, fault containment and safe reclamation
before active device authority. No physical disk access follows from this plan.

Gate: separately qualify transport and recovery before advancing the
[native filesystem and XFS roadmap](../storage/design/roadmap.md) to mounted file
services, transactions, durability, recovery/GC and XFS read-write. Offline XFS
parsing and RAM-sector correctness do not establish those outcomes.

## 3. Display, input, terminal and desktop

With usable process/service boundaries, add authority-checked display/input and
buffer lifetimes, then native terminal sessions and the tiling desktop. Serial
diagnostic prompts are not an application terminal. Pending terminal/parser or
console increments must pass their own final integration gates before promotion.

Gate: input/output hotplug, window lifecycle/workspaces, clipboard authority,
Unicode/text shaping, resize/backpressure/EOF, session/job control, composition
and reset recovery. Use the [release inventory](system-release.md) for the full
application and accessibility requirements; functional references do not promise
Linux binaries, configuration, wire protocols or POSIX compatibility.

## 4. Language, runtime and native toolchain

Grow the language where the above consumers need it, retaining checked values,
private class state and explicit ownership. Bounded byte owners, move-only
classes and synchronous borrows already exist; general lifetime/effect and
concurrency models, TypeScript-like type transformations and richer reflection
remain open. See the [compiler reference](../compiler/README.md) and
[library dependency plan](library-stack.md), rather than historical exclusions.

Gate: positive, rejection, adversarial, resource and ABI tests with independent
review; no unchecked assertion, visibility bypass or resource duplication. Then
build native assembler/linker/runtime/graphics components and self-host the
compiler/system with differential and multi-stage reproducibility checks.
Measure equivalent-C workloads before making performance claims. Self-hosting
alone is not a compiler safety proof or a complete binutils/glibc/Mesa alternative.

## 5. Physical qualification and production readiness

Qualify the complete [Framework Laptop 13 / Ryzen 7 7840U](framework-13-7840u.md)
first, then only advertise tested [AMD tuples](amd-support.md). Gate: actual
machine/device discovery, isolation, power transitions, fault recovery, updates,
performance/energy and usable applications. Emulator evidence cannot substitute.
Production acceptance also needs an explicit trusted computing base, sustained
adversarial testing, scoped assurance arguments and recoverable releases.

## Historical roadmap checkpoints

Retained below for traceability. Their “next” steps and “unaccepted” labels describe
the original checkpoint, not today's priority or status. Other milestone evidence
is retained in [verification history](verification.md).

<details>
<summary>Expand milestone014–022 and token-scanner roadmap history</summary>

## Verified bounded checkpoint: milestone014

Readonly whole-array byte spans and synchronous binary reading are independently
reviewed and exercised by a protected Aurora program. Static creation-site tracking
rejects incompatible lifetime joins; it is not a dynamic generation proof or a
general async ownership model. Read-only BAR/resource admission preserves explicit
firmware and device profiles, rejects inherited active state, and tests write and
revoked-access faults. All147 emulator modes and parent aggregate checks pass.

Next library work extends checked endian readers and CRC32C, with a restricted
512-byte XFS v5 header-integrity fact probe. Isolated development is reviewed, but
main integration has not happened at this checkpoint. Good header CRC is not
mountability, log cleanliness, feature support or read-write compatibility.

Next kernel scope is read-only AMD-Vi/IVRS discovery: bounded requester/alias and
reserved-memory facts reconciled with PCI/MMIO authority. Actual table profiles
must be discovered, not guessed. No IOMMU programming, queue setup, DMA or BME
activation is included. Owned default-deny mappings, invalidation completion and
fault containment are separate activation prerequisites.


## Storage requirement expansion

The user-supplied 56-section NVMe-native design and explicit XFS request are
tracked in the [storage roadmap](../storage/design/roadmap.md). Initial executable
work is a host-only durability model with deliberate broken-protocol controls.
Checked endian/CRC32C and a narrowly scoped header-integrity probe come next;
DMA-safe transport, object transactions, recovery/GC and XFS read-write remain
separate acceptance gates. Read-only XFS is an intermediate stage, not fulfillment
of the complete compatibility target. No physical disk access follows from this plan.


## Verified checkpoint: milestone015

The bounded checked-endian/CRC32C/XFS-header library slice and read-only AMD-Vi
observation have passed independent and parent integration gates. All158 emulator
modes passed against unchanged inputs. The broad S1 resource ownership and XFS
mount/log/RW goals remain open. Next dependencies are bounded record construction,
compiler-analysis resource behavior, and default-deny device/DMA authority.
Mutable-byte views remain an isolated, unaccepted candidate after interrupted
independent review; they are not included in this checkpoint. Active IOMMU or NVMe
programming requires its own reviewed design and observable safety gates.


## Verified checkpoint: milestone016

The compiler fact-storage change and actual page-pin lifetime ledger passed
independent and aggregate checks, including162 actual emulator modes. The ledger
is a concrete prerequisite for DMA-safe storage; hardware publication, default-deny
translation, cache invalidation and quiescence completion remain absent. Those
need separate normative contracts, reviewed implementation and actual evidence.
The isolated mutable-byte candidate remains unaccepted. No unused model or
software acknowledgement can substitute for a hardware completion mechanism.


## Verified checkpoint: milestone017

Strict readonly UTF-8 decoding/validation is available as a native library.
Parent aggregate and selected existing kernel smoke profiles passed, with compiler
and kernel implementation unchanged from M016. Next text work is bounded owned
UTF-8 encoding using existing fixed-value arrays. Mutable-byte candidate remains
unaccepted after its interrupted review. AMD table-format implementation is paused
pending a complete permissible AMD48882 specification; source-derived emulator
models and software pin ownership are not hardware isolation proof.


## Verified checkpoint: milestone018

Strict readonly UTF-8 decoding/validation and bounded owned-value scalar encoding
are available. The user supplied AMD48882 revision3.10, resolving the normative
source blocker. Specification review identified pinned-emulator deviations, so
future hardware qualification cannot assume emulator behavior is normative.
Next work is isolated memory-translation table construction tied to real leases,
with no device programming, and XFS header geometry/feature validation planning.
Both require their own review/gates; no DMA isolation or XFS mountability follows.


## Verified checkpoint: milestone019

CPU-only AMD3.10 table construction and the bounded XFS geometry library have
passed their independent and integrated gates, including all 166 emulator modes.
The complete AMD reference is available; earlier M017 source-blocker text is
historical. Next DMA work requires an independent normative oracle and separate
qualification of pinned-emulator translation, events, completion and interrupt
behavior before any active device authority. XFS next needs separate storage,
recovery and mount contracts; header geometry alone cannot authorize I/O.
The mutable-byte candidate remains unaccepted. Full Linux-replacement scope and
physical Framework13/7840U qualification remain open.


## Verified checkpoint: milestone020

The compiler now resolves bounded fully concrete nested generic value arguments
child-first, using existing nominal identity, visibility and copied inline-value
semantics. A token/source-range example consumes private fixed byte storage and
independent value copies. Complete compiler release/fatal ASan/UBSan targets,
independent review, parent aggregate and three existing UEFI integration profiles
passed. M019 remains the historical full 166-mode kernel run. No active device
authority, new kernel mode or physical qualification is added.

The next self-hosting dependency is a separately specified bounded token/text
consumer with observable native behavior on these value contracts; this milestone
is not a lexer, parser, owned-string implementation or native compiler. Any broader
collection/ownership or dependent-generic expansion needs its own safety contract
and gates. The isolated mutable-byte candidate remains unaccepted. DMA and XFS
next steps retain the independent contracts and qualification gates above.


## Verified checkpoint: milestone021

Bounded explicit function templates and the real std::make_pair value factory
passed complete release/fatal host ASan/UBSan compiler targets, independent review
and fatal replay, fresh parent aggregate and three existing UEFI profiles.
Definitions/instances now share the 64/256 graph budgets across class/function
templates. Native token/source-range factory values retain exact nominal identity,
complete initialization and independent copies. The full M019 166-mode run is
historical; no new kernel mode, device authority or physical qualification is added.

The next self-hosting dependency remains a separately specified bounded token/text
consumer with meaningful native behavior on these value contracts. Acceptance must
identify input representation, copied output/errors, finite work limits, exact
positive/negative/adversarial oracles, existing-regression preservation, fatal
host sanitizers and independent review before implementation is called verified.
M021 is not a lexer/parser, owned-string layer, native toolchain or general-purpose
standard library. Deduction, overloads, generic methods and recursive/dependent
generic expansion need separate contracts. Mutable-byte, DMA and XFS work retain
their independent acceptance gates; no active DMA or mountability is implied.


## Current verified checkpoint: milestone022

Copied ordinary method class parameters and std::array exchange pass complete
release/fatal host ASan/UBSan compiler targets, independent source/IR/native ABI
review, fresh parent aggregate and all 166 existing emulator modes. Both normal
images are restored. The new private combined receiver/record/result convention
has independent handwritten native boundary controls; it is not a stable foreign
ABI. Parser grammar remains byte-identical to M021, using existing qualified self.

The next self-hosting dependency remains a separately specified bounded token/text
consumer with meaningful native behavior and independent positive, negative,
adversarial, resource and sanitizer gates. Value transport is not a lexer/parser,
owned-string layer or native toolchain. Generic methods, references/resources,
whole-program resource guarantees, active DMA, XFS mountability and physical
hardware retain their separate contracts. The isolated mutable-byte candidate
remains unaccepted. See [M022 evidence](https://github.com/ambasta/aurora/blob/2b1776f13cd02df6588f9e3213815f13c28a71e0/docs/evidence/milestone-022/README.md).


## Verified bounded self-hosting consumer: ASCII token scanner

`std.token_scan` now has a frozen independent design review and an Aurora-authored
implementation for final readonly byte windows. The copied report names the next
lexical token or recoverable error without storing source authority. See the
[contract](token-scan-contract.md) for exact ASCII behavior, finite limits and
required oracles/regressions. The fresh complete root release native graph and
separate focused fatal host ASan/UBSan scanner gate passed independent review.
See [scoped results](token-scan-results.md), including the preserved initial
diagnostic-expectation failure. Generated Aurora is not sanitizer-instrumented;
complete compiler sanitizer regression and leak checking are not claimed. This
does not replace the host lexer or implement a parser, strings or a native compiler. The previous value-transport milestones remain prerequisites rather
than tokenization evidence.

</details>
