# Disjoint backing-footprint authority — work in progress

This branch generalizes the merged A0 model in place. The finite-footprint
split/move conservation algebra, operational model and erasure into unchanged R
compile under pinned Lean 4.24.0. **Generalized inductive preservation, safety,
witnesses, snapshot bridge and the full A audit are still being adapted.**
The earlier A0 description below records the completed predecessor, not claims
that the generalized artifact has already passed its acceptance gates.

## Generalized contract under construction

One backing root has finite canonical-cell footprints, including disconnected
sets. Gate-local writable inventory is subtracted into immutable request escrow;
registered transfers and uses retain exact footprints. A permanent exact-use-ticket
return marker prevents repeated receipts from restoring authority after reborrow.
Freeze consumes only locally free cells and permits overlapping immutable readers
while a disjoint writer remains admitted. All effects inspect only admitted
metadata and actual outstanding work, never a global permission oracle.

The location-indexed non-gate holdings are abstract protocol authority accounting,
not remotely queried endpoint memory or a concrete distributed map. A required
unconditional operational-equivalence theorem will erase that accounting while
preserving every transition. Authority return retains A0's abstract atomic boundary;
no decentralized transport, physical completion or native alias decoder is proved.
The intended partition theorem is exact union **and** per-cell uniqueness, not list
length conservation. Read permissions do not count as extra exclusive claims.

## Completed predecessor: A0

A0 composes a bounded authority profile with R and Q: one arbitrary allocation
has one exclusive sequential writable stream, then shared immutable-read
permissions. It is **not full obligation A**, a native-code proof, or a general
rights architecture. The transition proposal and R prerequisite received
independent reviews; final-source qualification is recorded separately.

## Operational contract

An initial allocated capability binds issuer, subject, generation, backing-cell
interval and write/delegation rights. Its trusted issuance is the boundary—not
cryptographic authentication or a claim that any caller naming an agent is
trusted. Agent identities are arbitrary; CPUs, NUMA agents, GPU/DMA queues,
loaders and remote endpoints may instantiate them without implying common
coherence, completion semantics or fault behavior.

Exclusive permission moves through a gate, immutable request escrow, registered
transfer or use, and receipt-bound return to the original activation. Delegation
attenuates extent and delegation rights; a narrower use reserves its original
owner's permission until return. Lost replies never restore another owner.
Freeze consumes the token into an absorbing generation-indexed frozen location
and enables local read admission. Read requests check local retained permission,
not a remote frozen-state oracle. Existing use modes and grant ceilings never
change. Effects inspect only admitted descriptors and outstanding work; they do
not check global permission, current version or freeze state.

A writable work item denotes **one sequential ordinary-access stream**. One GPU
job/command is not thereby internally race-free. The theorem excludes conflicts
between distinct admitted streams, not races hidden inside a job. Whole-allocation
writer exclusion is deliberately conservative. The initially proposed
disjoint-writer witness is **deferred**, not satisfied: extent-splitting algebra
and cross-allocation product/commutativity proofs remain open. This profile is
not a prescribed global allocation lock or a universal architectural optimum.

Footprints are contiguous intervals in canonical backing-cell coordinates,
not logical alias IDs. The same cell through two views remains the same cell.
Disconnected footprints are not modeled. Relating scattered native frames to
these coordinates requires an alias-preserving address interpretation; it is
not proved here. No staging buffer is required by the shared-read witness, but
no physical traffic/cost or zero-copy implementation claim follows.

Immutable request/ticket maps represent decoded extra wire payload erased by
projection to R. First registration derives its binding from retained request
origin; duplicate messages cannot change that binding. The maps are not remote
mutable endpoint reads. Wire encoding, decoder implementation, authentication
and malicious-message enforcement remain unproved.

## Checked results and controls

- Inductive invariant preservation for every transition, arbitrary agents and
  arbitrary finite traces; attenuation, exact subject/version binding and
  retained exclusive permission through pending requests and transfers.
- Distinct enabled streams must both be readers. Every effect cell lies inside
  the allocated backing interval.
- Frozen history is permanent. While that version remains current, every finite
  future extension excludes ordinary write events. This is **not verification
  of heap-byte immutability**: no data heap is modeled.
- Metadata erasure/stuttering simulates R; R/Q supply no old-version accesses
  after reuse. Immutable grant/payload bindings cannot be rewritten.
- A successful Active-phase fill, local close, queued effect, drain, receipt,
  return, freeze and two overlapping readers, followed by actual root closing,
  complete retirement, reuse and a fresh-generation root grant.
- Writer delegation with attenuation, duplicate registration/activation,
  packet loss and retained unresolved-transfer liability; old close messages
  remain tied to old tickets after reuse.
- Two faulty mutations—duplicated writable ownership and premature freeze—start
  from a reachable live writer and then use only original transitions to produce
  conflicting enabled effects. Timeout escrow restoration and stale descriptor
  rebinding separately break invariants; they are not mislabeled as complete
  physical-unsafety executions. Concrete checks cover extent/write/delegation
  escalation and subject binding. These are guard/refusal facts, not a verified
  total refusal dispatcher: the model's explicit refusal step is nondeterministic.

R now admits an owner-initiated close request for a published use in Active or
Closing. The request only sends the existing close packet: submission disabling,
queued effects, physical completion, sealing and receipts remain distinct. This
small prerequisite avoids forcing normal snapshot completion through whole-root
reclamation. Root closing and its sweep remain unchanged.

## Snapshot contract connection

`Snapshot.seal_receipt_bridge` constructs return and freeze steps from the exact
registered writer's retained receipt, then proves local read activation and
absence of enabled writes. `fill_cell_is_authorized` connects writable effects
to the allocation bounds. The lifecycle witness includes actual fill effects,
shared reads and discard/reuse; the following is a **contract correspondence**,
not a source-code refinement certificate:

| Existing mechanism | A0 connection | Still required |
|---|---|---|
| `memory_manager.au::fill_snapshot`: building phase, epoch and destination bounds; `MappingAuthority::fill_snapshot_chunk` authenticates frames and bounds. | Admitted writable stream and backing-cell bounds. Incoming `SourcePin(chunk)` is distinct from a sealed snapshot pin. | Alias-preserving coordinate/physical mapping, copy effects, checked failure and native/compiler semantics. |
| `seal_snapshot`: downgrade every page, then publish phase 2. | Complete/receipt/return precedes freeze and read admission. | Prove the page-permission/TLB/completion effects establish this protocol boundary; abstract receipts do not verify them. |
| Sealed `SourcePin(snapshot)` and `SnapshotReadPin` validate root/epoch; parser pins are lexical, kernel-root and IRQ-off. | Frozen-version read permission retains backing lifetime. | Current native parser pin is single and synchronous. Multiple A0 readers are a target generalization, not current functionality. |
| `discard_snapshot`: clear anchor, retire mappings and release frames. | Root close, gate fencing, use drains, quiescence and reuse. | Actual pin coverage, mapping isolation, all-agent invalidation and safe frame reuse. |

Run `./verify-a.sh` from the enclosing directory. Pinned Lean 4.24.0, core/Std,
36 exported theorem dependency reports; only `propext` and `Quot.sound` are
permitted. Run Q's `./verify.sh` and R's `./verify-r.sh` independently. Ordinary
`make test` neither installs Lean nor substitutes for these gates.

Excluded: full authority/restart semantics, malicious-endpoint enforcement,
cryptography, weak memory/compiler/ISA refinement, physical CPU/GPU/DMA/storage
completion, durable recovery, decentralized coordination, partial thaw/COW,
bounded metadata, liveness, cost optimality and hardware qualification.
