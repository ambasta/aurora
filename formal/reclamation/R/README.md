# Endpoint protocol refinement (work in progress)

This second slice replaces Q's acknowledgment-reception oracle with a modeled
asynchronous endpoint protocol. It is not a kernel/ISA proof. The transition
proposal received two independent reviews; final source review and qualification
are still pending.

One backing root has an explicit sequential registration/transfer-commit
coordinator. Arbitrary endpoint identities represent CPUs, device queues or
snapshot consumers without assuming common coherence, atomic scopes or hardware
completion semantics. This intermediate coordinator is not a permanent global
architecture prescription. Independent-root commutativity is not proved here.

Registration precedes publication. Endpoint-local request identities pair the
source gate's activation ticket with a fresh local nonce. Coordinator deduplication
and endpoint pending-request state are separate; message handlers do not read
remote mutable state. Gates close locally, then wait for their earlier registration
replies before sealing. Reserved receivers can activate during Closing. A sealed
tombstone dominates delayed/duplicate publication. Uses disable submission before
draining explicit outstanding work; disabling alone does not prohibit queued
effects. Gate retirement leaves child/use liabilities intact. Logical aliases
share the same backing root, but writer exclusion/snapshot immutability is outside
this reclamation proof.

Packets may be lost, duplicated, reordered or delayed. Receipts are generated from
local seals and accepted using retained ticket identity/generation, without
inspecting physical completion at the receiver. A packet-origin invariant and
permanent sealing derive Q's acknowledgment precondition. Unresolved transfers
cannot be canceled by timeout: they stay outstanding and can block forever.
Coordinator transfer commit atomically reserves a receiver while resolving the
transfer; decentralized or durable handoff is not proved.

The endpoint primitive contract assumes sequential atomic local actions, sound
submission disabling, and exact-once completion/removal of an actual outstanding
work item after its last possible effect. `finishOne` is **not** reception of a
potentially duplicated hardware completion packet. The protocol/channel model
has honest endpoints and no forged message injection; authenticity implementation,
weak memory, TLB/cache/IOMMU semantics, device reset, crashes that forget state,
durable recovery, finite metadata, progress and costs remain unproved. Fail-stop
or unbounded delay is represented by not scheduling the affected endpoint while
retaining its obligations.

## Checked so far

The concrete model, endpoint invariants, one-step projection into Q, inductive
preservation, arbitrary finite trace simulation and future-extension safe reuse
compile under pinned Lean 4.24.0 with core/Std only. The concrete state does not
contain Q.State; projection conservatively treats registered but unpublished
records as possible until local sealing. Operational constructors do not assume
the invariant or the simulation theorem.

Successful concrete traces, mutation controls, the new exported-theorem audit,
independent full-source review and fresh final qualification are not yet complete.
Do not treat this intermediate checkpoint as merge-ready or hardware support.

The registration/grant binding invariant proves the unique retained request/ID
association needed for reclamation; a full typed grant/authorization theorem is
not claimed. The existing Q artifact and its acceptance gate remain separate.
