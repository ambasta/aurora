# Aurora formal foundations

**Normative design intent; obligations remain unproved unless explicitly stated.**
This is not an implemented contract or a completed proof. The design preserves
Aurora's safe C++-recognizable language, capability isolation and small
services. Its purpose is to make their guarantees composable across
multicore/NUMA, multiple GPUs and storage devices, integrated CPU/GPU systems,
and multiple machines—not to invent a framework independently of those goals.
Prototype capacities are not architectural limits. Existing implementation
descriptions remain authoritative about what runs.

## 1. Claims and models

Use these labels in design reviews: **definition** introduces a model;
**assumption** restricts executions; **external theorem** has an independently
proved statement and hypotheses; **obligation** is an Aurora result still to
prove; **hypothesis** is a design choice not established as optimal. No Aurora
mechanized proof is supplied by this document. Informal arguments below are
proof plans, not verification certificates.

**Definition.** A profile is a labeled transition system `(S, I, →)` plus
permitted observable traces, hardware/compiler semantics, a fault/adversary
model, fairness assumptions, and a cost interpretation. Safety means every
reachable state satisfies an invariant; progress is a separate conditional
temporal property. An implementation must refine the profile's observable
traces, including faults, refusals and uncertain outcomes. Refinement must not
hide implementation nontermination when the profile promises termination.

**Assumptions to discharge per profile.** The boot trust root and explicitly
trusted machine primitives, MMU/IOMMU, interrupt routing, reset and
cache/translation maintenance obey named semantics. Nucleus correctness and
compiler/runtime refinement are obligations, not assumptions that their whole
implementations work. Applications and isolated services can be malicious. A
device belongs to the isolated profile only if its authority is enforceable even
when its driver is malicious. Arbitrary hardware corruption, compromised
firmware and side channels are not excluded silently: either specify protection
and a separate claim, or record them outside that profile's guarantee. Memory
safety is not functional correctness, confidentiality, real-time behavior or
crash durability.

The distributed base profile permits crash/recovery, message loss, duplication,
reordering and partitions. Safety must survive unbounded delay; eventual
progress requires an explicit eventual-connectivity/leadership assumption and
available durable state, a sufficient surviving quorum, fair process/recovery
scheduling and retransmission, and absence of permanent admission starvation.
Byzantine nodes require a distinct authenticated replication/quorum model, not a
renamed crash-fault proof. Real-time profiles instead specify bounded
interference, clocks, communication and recovery, with admission control.
Neither profile may borrow the other's liveness assumptions.

## 2. Identity, authority and topology

**Definition.** Distinct nominal types represent `NodeIdentity`,
`BootIncarnation`, `Principal`, `ObjectIdentity`, `ObjectVersion`,
`DeviceSession`, `OperationId` and `AuthorityEpoch`. An object reference names
its authority domain and incarnation; it is not authority. Equality of a local
integer or virtual address never implies equality of these identities.
Generation reuse/wrap must be ruled out while old references remain possible, or
an authenticated fresh namespace must be created. Remote identity requires an
explicit trust-root, authentication and key-lifecycle contract; a local
capability-table index is not a transferable network capability.

**Definition.** A grant binds issuer, subject, object/version, rights, authority
epoch, permitted effect domain, delegation restrictions and revocation rule.
Attenuation cannot enlarge any authorized set of effects. A receiving domain
must validate authority under its own trust policy. Authentication proves
origin, not permission. Placement is not logical identity; migration preserves
the latter while changing the former. Wire schemas are versioned independently
of compiler ABI. Quotas and execution budgets are separate conserved resources;
a valid grant does not imply resources will be available.

**Definition.** Hardware is a typed graph/hypergraph of compute agents, memory
regions, devices, links and failure domains. Relations include reachability,
addressability, cache coherence, atomic synchronization scope, DMA isolation,
reset scope, persistence domain, power domain and contention. They are distinct;
none is inferred from physical integration or a shared address. NUMA distance
and bandwidth are costs, not security boundaries. A CPU/GPU SoC shares a power
or memory controller without necessarily sharing every atomic or cache domain.
Device removal, reset and topology changes create new sessions and obligations.

**Hypothesis.** Use a capability nucleus with partitionable authority state,
per-CPU execution/trap state and topology-aware services. Localize independent
state; coordinate conflicting transitions at the smallest sound authority
domain. This rejects both a mandatory global kernel lock/order and an
unconditional message-only multikernel. Shared-memory and message
implementations are allowed only as refinements of the same relevant abstract
operation—not as a claim that remote memory has local borrowing semantics.

## 3. Access, transfer and reclamation

**Definition.** For each mutable extent/version, ordinary non-atomic access has
one exclusive writer and no readers, or immutable readers and no writer.
Exclusion applies to overlapping underlying backing, not merely distinct logical
IDs: CPU virtual views, GPU mappings and object versions may alias physical
bytes. Immutable snapshots need separate/COW backing or proved ordering
preventing mutation during observation. Disjoint backing extents can be owned
independently. Atomic shared state is a separate protocol with a named invariant
and memory-order semantics; it is not an exception that permits ordinary data
races. Fractional read permissions are a possible proof encoding, not a required
language surface or runtime counter.

The language must distinguish: (a) lexical local borrowing under a specified
memory model; (b) asynchronous transfer that consumes a permission and returns a
completion/failure obligation; (c) immutable versioned sharing; and (d) remote
operations with explicit uncertain completion. A task, GPU queue, DMA engine,
loader snapshot or remote peer can outlive the initiating stack frame. Its
permission must therefore be owned by an asynchronous protocol, not extended by
pretending a lexical borrow is still local.

**Shared-backing obligation.** If agents can access the same representation and
backing under compatible lifetime, isolation and synchronization contracts, the
interface admits that backing without requiring a separate full-buffer staging
copy. Prove a shared execution realizes the same observations as the abstract
transfer. This positive SoC/zero-copy contract does not eliminate cache, DRAM or
interconnect traffic or assert that sharing always minimizes the cost objective.

**Definition.** Reclamation follows `Active → Closing → Quiescent → Reclaimed`
for a resource-version root, not one handle or delegation path. Closing
initiates fencing of every authority able to admit accesses, including aliases,
descendants and transfers in flight. It blocks admission at a gate only once
that gate has installed its fence; a partitioned remote gate may still admit
accesses while its delegation remains an outstanding obligation. Quiescence
requires all such gates fenced and all previously admitted CPU/GPU/DMA/snapshot
accesses drained. Cache/translation invalidation and device completion remain
distinct obligations. Epoch checks alone do not remove stale TLB entries, issued
DMA or delegated admission authority. Timeout triggers containment/reset or
quarantine, not an assertion of quiescence or safe reuse.

**Obligation Q (first proof slice; not yet a proof).** Model one resource
version with phase, a ghost issued-ticket identity set (not a required runtime
log), a live-obligation multiset `O`, and registered admission gates `G`. A use
ticket may cover an execution lease, live mapping or queued DMA command, not
necessarily one CPU load. Tickets represent both such uses and authority that
could admit future uses; transfer-in-flight is an obligation, not a gap between
owners. Specify these transitions:

- `Admit(g)`: an unfenced authorized gate creates a fresh use ticket before the
  covered accesses can issue. Existing mappings may continue loads during Closing
  until their ticket is drained; Closing is not an instantaneous physical fence.
  A delegated gate is itself covered by a live authority ticket.
- `Delegate/Transfer`: before authority leaves one owner, record a fresh child or
  transfer ticket. Parent discharge cannot drop the child/transfer obligation.
  After a gate is fenced, transfer is disallowed or conserves the same liability
  without extending its audience. Duplicate delivery can resolve the same ticket
  but cannot create fresh authority.
- `BeginClose`: freeze root grant creation and request fences for every gate and
  unresolved delegation/transfer path; existing obligations stay live.
- `FenceAck(g)`: mark the gate fenced only on evidence that no later old-version
  admission can occur there. Its prior issued uses remain live until drained.
  Unresolved remote authority cannot be erased merely because it is unreachable.
- `AuthorityRetire/TransferResolve`: discharge a gate authority ticket only after
  its sound fence, with every child, use and queued-transfer liability separately
  represented. Resolve a transfer by conserving receiver liability or proving
  cancellation at every possible destination; losing the reply is neither.
- `Complete/DrainAck`: retire the specifically identified use ticket only after
  the access has ceased and cannot recur. A reset acknowledgment may discharge a
  set only if the hardware contract excludes all later effects from that set.
  Acknowledgments bind resource, version and obligation identity; stale/duplicate
  acknowledgments are inert and never subtract an obligation twice.
- `Quiesce`: require every admission path resolved/fenced and `O` empty. `Reuse`
  requires Quiescent, establishes a fresh version and cannot revive old tickets.

Prove inductively: (i) every possible old-version access has a live use ticket
or a live authority/transfer obligation covering its admission; (ii) no such
obligation disappears through epoch advance, timeout, loss, duplication or
crash; (iii) a fenced gate cannot issue a new old-version ticket; and (iv)
discharge preserves coverage of all other obligations. Then derive that Reuse
excludes old access, rather than assuming that closing already eliminated it.
The nontrivial work is proving gate registration/coverage and acknowledgment
transitions from the CPU, device, network and persistent recovery mechanisms.
Their hardware meaning is a named assumption at this abstraction level; proving
the software produces a valid acknowledgment is an additional refinement
obligation. First mechanize an arbitrary finite CPU-agent set with mathematical
generations, activation/migration messages and mapping/use tickets. Explore
small instances for close-versus-activation, acknowledgment-before-invalidation,
duplicate acknowledgment and lost-transfer-obligation counterexamples.
Generalization needs a parameterized invariant, not enumeration. Reclamation
progress separately needs finite admitted work, fair processing/delivery and
eventual completion or sound fencing; a permanently stalled agent may require
quarantine.

First-slice acceptance also requires exhibiting a successful trace through
delegation, close, fence, authority retirement, use drain and Reuse, checking
nonvacuity: safety must not be obtained merely by forbidding all reclamation.

**Obligation A.** Grant creation, attenuation, transfer, revocation and restart
preserve authorization and non-aliasing across incarnations. Prove each
transition's invariant preservation, including refusal and cancellation.
Transfer must name its linearization/commit rule and recovery owner; a lost
acknowledgment must not mint a second owner. Immutable snapshots retain the
required version until all consumers retire it, including GPU jobs and
executable loaders.

## 4. Ordering, failure and durable effects

**Hypothesis.** Specify consistency per object/protocol. Require linearizability
for conflicting authority decisions where the contract needs it; permit causal,
snapshot or commutative semantics where the application contract allows them.
Coordination avoidance requires an invariant-preservation argument for allowed
merges, not commutativity alone. There is no default cluster-wide total order or
single global scheduler.

Remote calls return a committed result, a permanently fenced noncommit for that
operation identity, or an uncertain outcome. Observing no commit yet is not a
noncommit proof: a durable abort/fence must reject delayed copies before
ownership can be recovered. Cancellation revokes interest or initiates a
protocol; it does not erase an already committed effect. Retry safety requires
stable operation identity, durable duplicate suppression and an explicit
retention/recovery contract, or an effect idempotent under repeated delivery of
that operation. Commutativity alone only relaxes ordering: two duplicate
increments still change the result twice. An external irreversible action cannot
inherit “exactly once” from an in-memory request table. Bounded
completion-record storage requires explicit credit/admission and retirement
rules; forgetting a record cannot silently make an old request safe to execute
again. Retire a record only when a retained monotone session/request floor or
expired/fenced authority rejects late replay; refuse admission rather than evict
live recovery evidence. Revocation cannot erase plaintext already observed by an
authorized receiver.

**Conditional impossibility argument (not mechanized).** A disconnected verifier
whose local state and received messages are identical in executions with and
without remote revocation must make the same acceptance decision. Thus immediate
global revocation and unrestricted offline acceptance cannot both be promised.
Require online validation, a bounded-validity credential under explicit clock
assumptions, or delayed revocation; label requested, fenced and retired states
separately. A local asynchronous operation owner is not automatically exclusive
remote ownership.

For replicated authority, distinguish agreement, commit durability, visibility
and client acknowledgment. Fencing must be enforced where writes take effect; a
lease or epoch checked only by a coordinator cannot stop a stale writer at an
unfenced device. Multi-device persistence defines ordering/flush semantics and
failure independence; two devices behind one lost power domain are not two
independent survivors. Cross-shard atomic commit needs a separate protocol and
blocking/recovery argument, not an extrapolation from a single local
transaction.

## 5. Limits, costs and architectural comparison

A candidate is admissible only after satisfying its safety and required progress
contracts. Among admissible candidates, compare a vector of model-derived costs
(latency, communication, memory, energy, contention and trusted assumptions).
There is no universal optimum without a workload, hardware model and objective.
A lower bound is necessary, not evidence that a construction attains it; pair
bounds with constructive upper bounds or approximation/competitive guarantees.
State unavoidable tradeoffs rather than replacing them with benchmark rankings.

For a homogeneous unit-speed processor profile with a precedence DAG, total work
`W`, critical path `L` and `P` processors, every schedule has makespan `T ≥
max(W/P, L)`. This elementary bound is not an Aurora heterogeneous scheduling
theorem. Heterogeneous profiles require task eligibility, per-resource execution
costs, communication, contention and migration costs, and feasible simultaneous
execution under shared power/thermal limits—not a sum of independent peak CPU
and GPU capacities. Resource-cut/eligible-demand bounds are a proposed analysis
technique whose exact statement must be proved for the selected model. Never add
CPU instructions and GPU work items as though they were interchangeable work
units.

Persistence and communication bounds must likewise state the failure model,
bytes/messages being counted, permitted coding/compression, topology and what
information must be distinguished. Energy bounds need an explicit device model;
“zero copy” does not imply zero movement, zero synchronization or zero energy.
Measurements can validate an implementation/model fit and expose a mistaken
assumption. They do not prove a safety theorem, establish a universal optimum,
or replace a mathematical architectural argument.

## 6. Dependency-ordered acceptance

1. **Semantic core:** define traces, identities, authority and access invariants;
   give finite counterexample models for restart, cancellation and reclamation.
   Acceptance: reviewed transition rules and first machine-checked Q/A instances,
   with assumptions and excluded behaviors listed.
2. **Language/machine refinement:** specify concurrency, atomics, asynchronous
   ownership and checked failure in Aurora; connect compiler transformations and
   privileged effects to target memory models. Acceptance: preservation/refinement
   theorems for the first implemented subset, not a language-wide safety claim.
3. **Multicore/NUMA instance:** per-CPU state, scheduling ownership, interprocessor
   communication and shootdown/reclamation. Acceptance: concurrent invariant and
   conditional progress proof before treating single-core tests as evidence here.
4. **Heterogeneous instance:** compose CPU, GPU, DMA, snapshot and multiple-storage
   permissions with topology/isolation/persistence facts. Acceptance: coherent and
   noncoherent cases, reset/hot-unplug and SoC shared-resource interference modeled;
   prove session revocation and reuse separately from successful execution.
5. **Distributed instance:** authenticated identities, durable operation/fencing
   state, consistency and replication/commit protocols. Acceptance: partition,
   restart, duplicate delivery and uncertain-outcome safety. First prove fenced
   single-writer transfer with a durable monotone epoch, crash at each persistence
   transition, delayed/duplicate messages and no timeout reacquisition; permit
   blocked/uncertain outcomes. Progress only under
   stated synchrony/fairness assumptions. Cluster simulation is not that proof.
6. **Optimization and ecosystem:** attach model-specific bounds and constructions
   to scheduling/placement/storage policies, then refine implementations and grow
   native services/toolchain. Acceptance: explicit proof scope and implementation
   conformance, with physical-platform qualification reported independently.

These are dependencies, not a single serial waterfall: abstract heterogeneous
and distributed counterexamples inform the semantic core from the start. The
first proof must not hard-code two owners, one CPU, one GPU or one disk as the
destination model. Finite instances help find errors; they do not prove
arbitrary cardinality without a reduction or parameterized argument.

Tool choice is an evaluation task: compare Lean/Coq for inductive/metatheoretic
proofs, an applicable separation-logic framework such as Iris for concurrent
resource reasoning, and TLA+/PlusCal or equivalent for protocol specification
and finite-state exploration. They solve different obligations. Choose a small
proof slice, record trusted kernels/axioms, extraction/compiler boundaries and
effort; do not claim a model-checker run proves an unbounded implementation or
that a proof assistant automatically supplies the hardware semantics.

## 7. Decision ledger and primary evidence

These choices are proposed architectural hypotheses. External results justify
particular obligations or restricted constructions, not the whole design.

| Decision; rejected alternative | Evidence and exact limit | Aurora proof still needed |
|---|---|---|
| Adopt capability-enforced isolation and topology-local ownership; reject mandatory global mutable kernel state and unrestricted physical delegation. | [Barrelfish, SOSP 2009](https://barrelfish.org/publications/barrelfish_sosp09.pdf) demonstrates explicit inter-core protocols. [seL4 proof caveats](https://github.com/seL4/seL4/blob/master/CAVEATS.md) delimit configurations and do not confer verified SMP on Aurora. These are architecture/proof-scope examples, not an optimum theorem. | Authority conservation, isolation, delegation/revocation and compiler/hardware refinement for each admitted configuration. |
| Adopt semantics that let independent operations commute; reject observable global issuance order when it serves no contract. | [Revised Scalable Commutativity Rule, 2018](https://arxiv.org/abs/1809.09550) supplies a repaired Coq-verified existence result under its model. It does not prove any particular implementation scales or meets deadlines. | Commutativity conditions and a concrete conflict-free implementation/refinement, including resource exhaustion. |
| Use local shared primitives inside an appropriate coherence model and explicit transfer elsewhere; reject mandatory messaging everywhere and false global UMA. | [Compound Memory Models, PLDI 2023](https://www.goens.org/publications/pldi23.pdf) proves composition results for an x86TSO/PTX instance. [RustBelt Meets Relaxed Memory, POPL 2020](https://plv.mpi-sws.org/rustbelt/rbrlx/paper.pdf) demonstrates why ownership/library reasoning needs a weak-memory model. Neither proves Aurora or AMD GPU semantics. | Aurora source semantics and target-specific mappings; scoped GPU atomics, cache maintenance and DMA publication. |
| Track actual translation/access sharers; reject frame reuse after local invalidation alone or timeout. | [Hydra, ATC 2024](https://www.usenix.org/conference/atc24/presentation/gao-bin-scalable) is a NUMA page-table replication/sharer-tracking example. [Linux DMA guide v6.17](https://origin.kernel.org/doc/html/v6.17/core-api/dma-api-howto.html) separates coherent allocation from required ordering and streaming synchronization. Neither is an Aurora reclamation proof. | Q plus sharer-set soundness, invalidation completion, reset containment and no resurrection under migration. |
| Model CPU/GPU/SoC synchronization scope and power separately; reject “integrated means uniformly coherent and equally cheap.” | [CUDA 12.4 programming guide](https://docs.nvidia.com/cuda/archive/12.4.0/cuda-c-programming-guide/) specifies memory-synchronization domains; [Linux energy-aware scheduling](https://kernel.org/doc/html/latest/scheduler/sched-energy.html) uses shared performance domains with specific applicability limits. These are deployed model examples, not AMD contracts. | Per-target compound memory and interference model; admitted bounds for shared bandwidth, power and thermal constraints. |
| Adopt exclusive logical device/queue owners with explicit handover; reject owner identity equaling CPU number and singleton device APIs. | [SPDK concurrency](https://spdk.io/doc/concurrency.html) is a real-world ownership/I/O-channel example. [GPUMC, May 2025 preprint](https://arxiv.org/abs/2505.20207) checks scoped GPU programs; finite modeled checking is not universal liveness. | Queue/session migration, completion identity, credit conservation and CPU/GPU/DMA reclamation. |
| Prefer communication-aware placement with declared approximation/optimality scope; reject a universal efficiently optimal heterogeneous scheduler. | [Hong–Kung, STOC 1981](https://www.eecs.harvard.edu/~htk/publication/1981-stoc-hong-kung.pdf) derives I/O bounds in a specific pebble model. [Multiprocessor red–blue pebbling, September 2024 preprint](https://arxiv.org/abs/2409.03898) studies a multiprocessor extension and tradeoffs. Bounds depend on memory and permitted computation/recomputation. | Workload/topology-specific lower bounds and a construction with a proved gap; not just measured placement heuristics. |
| Offer a structured parallel profile, not one scheduler for every workload. | [Blumofe–Leiserson, FOCS 1994](https://www.cs.cornell.edu/courses/cs612/2006sp/papers/blumofe94.pdf) gives expected `O(T₁/P + T∞)` work-stealing time for fully strict computations under its processor model. This is a constructive complement to restricted work/span bounds, not a NUMA/GPU/service theorem. | API-to-DAG refinement and scheduler assumptions; separate proofs for blocking, deadlines and heterogeneous execution. |
| Preserve uncertainty and scoped agreement remotely; reject unconditional consensus termination under arbitrary asynchrony/crash. | [Fischer–Lynch–Paterson, JACM 1985](https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf) proves a possible nonterminating admissible execution for deterministic asynchronous consensus even with one possible crash. It does not prohibit safety or termination under additional assumptions. | Replication/commit invariant and conditional termination under a named synchrony/failure-detector or randomized model. |
| Adopt compositional crash/recovery proofs and bounded retry metadata; reject equating RPC delivery with exactly-once external effects. | [Grove, SOSP 2023](https://arxiv.org/abs/2309.03046) verifies interacting leases, reconfiguration, crash recovery and concurrency. [RIFL, SOSP 2015](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf) demonstrates scoped exactly-once effects with completion records and migration/retention rules. | Atomic effect/completion recording, durable replay suppression, bounded metadata lifecycle and recovery refinement. |
| Keep Byzantine safety/liveness as an explicit stronger profile; reject silently importing crash-fault results. | [Shipwright, July 2025 preprint](https://arxiv.org/abs/2507.14080) verifies a limited single-log-entry PBFT prototype, not a complete universally live Byzantine service. | Cryptographic assumptions, quorum/fault thresholds and conditional liveness for Aurora's actual protocol and implementation. |
| Derive bounds from the precise distributed interface; reject using a consensus bound as an arbitrary RPC latency bound. | [Revisiting Lower Bounds for Two-Step Consensus, PODC 2025, revised January 2026](https://arxiv.org/abs/2505.03627) obtains different tight process bounds for atomic-object and decision-task formulations under its specified partial-synchrony/two-step conditions. | Match the chosen API and failure/timing assumptions before applying a bound or claiming a matching construction. |

Research freshness does not determine evidential strength: a recent preprint is
not stronger than an applicable mechanized theorem. Recheck living vendor and
project documentation when selecting an implementation target; pin the actual
specification revision in that target's proof assumptions. GPU, storage and
network optimizations must preserve the same semantics, not silently weaken the
model to obtain an attractive bound.

## 8. Current prototype gap and integration boundary

At the reviewed source tree, [process documentation](../kernel/uefi/process.md)
explicitly limits execution to one CPU and two resident processes. The current
architecture also documents fixed-pair synchronous calls, no general wait queues
and no budget donation. [AMD support requirements](amd-support.md) list per-CPU
state, AP startup and shootdowns as required work, not achieved support. The
[device contract](device-contract.md), [storage contract](storage.md) and
[architecture](architecture.md) already separate intended guarantees from
qualification; this proposal supplies a common model rather than deleting those
obligations.

The audited prototype's global current-process/trap state, local-only TLB
invalidation, fixed owner slots, single NVMe/mount path and framebuffer path
must not become permanent public abstractions. Source-language conversion of
them is useful only within their stated profile; it does not establish
concurrent, multi-device or distributed correctness. Remote identities, durable
operation identities and cross-node grants need explicit new semantics, not a
larger local handle table. No current hardware support or test result is
upgraded here.

The architecture and roadmap use these contracts as their formal design
foundation. Working prototype structures
may be replaced wherever they conflict with the model; their accidental behavior
is not a compatibility requirement. Preserve the intended safety contract while
requiring replacements to meet their stated proof/refinement and qualification
obligations. This document alone neither changes implementation nor authorizes
hardware deployment.
