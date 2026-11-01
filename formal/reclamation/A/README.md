# Disjoint backing-footprint authority

A generalizes the completed A0 whole-allocation profile **in place**. One backing
root admits independent writable footprints, then persistent immutable reads.
It is a bounded part of obligation A, not a native-code proof or a general rights
architecture. The generalized transition proposal received two independent
reviews. Final-source qualification is recorded separately.

## Operational contract

Trusted issuance binds issuer, subject, generation, a finite footprint of
canonical backing cells and write/delegation rights. Lists represent finite sets
extensionally: duplicate list entries do not create permission. Footprints can be
disconnected, and differently named views can overlap. An arbitrary agent type
can represent CPUs, NUMA agents, GPU/DMA queues, loaders or remote endpoints; this
does not imply common coherence, completion semantics or fault behavior.

A gate checks only its retained local free/readable inventory and immutable grant
ceiling. A writable request subtracts its exact footprint into request escrow;
registration and transfer activation preserve that reservation. A narrow use
returns only its own reservation, never the original broader grant ceiling.
The exact fresh **use-ticket** return marker is permanent, including after
reborrow and generation reuse. Lost replies and timeouts never restore ownership.

Freeze consumes a subset of locally free cells into permanent same-generation
frozen backing. Read permissions can overlap and duplicate; they are not extra
exclusive claims. Frozen readers can coexist with writers on disjoint cells.
Whole-snapshot freezing requires full coverage, not merely a broad grant ceiling.
No thaw or writable copy-on-write transition is modeled.

The holdings map is an abstract authority-accounting layer. Its gate component
is endpoint-local available permission; request/transfer/use/frozen components
are protocol escrow accounting, **not remotely queried endpoint state or a
concrete distributed ownership map**. An unconditional operational-equivalence
proof erases non-gate accounting and matches every transition, even from
inconsistent/unreachable states. Accounting therefore cannot suppress an
operational execution. Return retains an abstract atomic authority-return
boundary; decentralized receipt transport is not proved.

Effects inspect only immutable admitted descriptors, their backing footprints
and actual outstanding work—not global ownership, current generation or freeze.
A writable work item is one sequential ordinary-access stream. One GPU job is
not thereby internally race-free. R retains its per-root registration/transfer
coordinator; no global allocation lock, cross-root commutativity or optimal
coordination architecture follows.

## Proof results and nonvacuity

- Exact per-cell union **and uniqueness** of keyed ownership claims for every
  issued generation. Pending requests, unresolved transfers and retired but
  unreturned uses retain their reservations; historical returned/activated
  descriptors do not count again.
- Inductive preservation for every transition and arbitrary finite traces;
  immutable identity/attenuation, bounds and receipt-bound exact returns.
- Distinct enabled streams accessing the **same backing cell** must both read.
  Disjoint writers are legal. The earlier whole-allocation exclusion follows
  only under an explicit whole-writer profile; A does not trace-refine A0's
  stronger exclusion specification.
- Frozen footprints only grow. While their generation remains current, their
  cells exclude ordinary write events in every finite future extension. No data
  heap is modeled: this is not verified heap-byte immutability.
- Metadata erasure/stuttering simulates unchanged R/Q, inheriting absence of
  old-generation accesses after reuse. Returned-ticket tombstones never reset.
- A successful trace has simultaneous disjoint scattered writers and actual
  effects, drain/return/reborrow, refusal of the old duplicate return, overlapping
  readers alongside a remaining disjoint writer, full frozen coverage, and actual
  root closing, retirement, quiescence and reuse with actual new-generation writes.
  A separate same-root trace executes disjoint writes by two distinct agents.
  Delegation, duplicate activation,
  delayed old close packets and lost unresolved transfers remain exercised.
- Faulty ownership copying, duplicate return after reborrow and premature freeze
  start from reachable states and use original subsequent transitions to produce
  conflicting effects. Timeout/rebinding controls and attenuation/alias-image
  refusals are labeled separately; they are not inflated into hardware-unsafe
  executions or a verified total refusal dispatcher.

`Aliases` interprets arbitrary finite logical views through an arbitrary,
possibly noninjective map into canonical cells. Equal backing images cannot
hide a conflict behind different logical names. Correct interpretation of native
frames, page tables, IOMMUs and scatter/gather descriptors remains an obligation.

## Existing snapshot contract connection

`Snapshot.seal_receipt_bridge` constructs exact return and full-cover freeze
from a registered writer's receipt and proves local read admission/no enabled
writes. Its coverage premise includes only already-free cells plus the exact
returned reservation. This is a **contract correspondence**, not source-code
refinement or current parallel snapshot functionality:

| Existing mechanism | Connection | Still required |
|---|---|---|
| `memory_manager.au::fill_snapshot`, `MappingAuthority::fill_snapshot_chunk` | Admitted writable effects and backing bounds. Incoming chunk pins differ from sealed snapshot pins. | Alias-preserving physical mapping, actual copy effects, checked failure and compiler/native semantics. |
| `seal_snapshot`: downgrade every page, then publish phase 2 | Return/drain precedes full-cover freeze and read admission. | Actual page permissions, TLB/cache maintenance and all-agent completion. |
| Sealed `SourcePin` and `SnapshotReadPin` | Frozen-version reads retain backing lifetime. | Current native parser pin is single, synchronous, kernel-root and IRQ-off; multiple readers remain a target generalization. |
| `discard_snapshot`: clear anchor, retire mappings, release frames | Root close, gate fencing, use drains, quiescence and reuse. | Real pin coverage, mapping isolation, invalidation and safe physical reuse. |

Run `./verify-a.sh` from the enclosing directory with pinned Lean 4.24.0/core/Std.
The 51 exported theorem dependency reports permit only `propext` and `Quot.sound`.
Run Q's `./verify.sh` and R's `./verify-r.sh` separately. Ordinary `make test`
neither installs Lean nor substitutes for these proof gates.

Excluded: full restart/revocation/cancellation semantics, malicious endpoints,
cryptography, weak memory/compiler/ISA refinement, physical CPU/GPU/DMA/storage
completion, durable recovery, decentralized coordination, partial thaw/COW,
bounded metadata, liveness, cost optimality and hardware qualification.
