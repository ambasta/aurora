# Endpoint protocol refinement

This second slice replaces Q's acknowledgment-reception oracle with a modeled
asynchronous endpoint protocol. It is not a kernel/ISA proof. The transition
proposal received two independent reviews; the proof is about the stated
endpoint contracts, not a deployed concurrent implementation.

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
effects. A responsible use owner may request closure of its exact published use
in any root phase (`requestUseClose`); this only enqueues the existing close
packet. It does not close the parent gate or change work, seals or receipts.
Owner identity is bound by the use descriptor in the honest-endpoint action
contract, not by a proved sender-authentication implementation. Gate retirement leaves child/use liabilities intact. Logical aliases
share the same backing root, but writer exclusion/snapshot immutability is outside
this reclamation proof.

Packets may be lost, duplicated, reordered or delayed. The support-subset
channel rule permits rearrangement/multiplicity changes, not only deletion. Receipts are generated from
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

## Checked results

The concrete model, endpoint invariants, one-step projection into Q, inductive
preservation, arbitrary finite trace simulation and future-extension safe reuse
compile under pinned Lean 4.24.0 with core/Std only. The concrete state does not
contain Q.State; projection conservatively treats registered but unpublished
records as possible until local sealing. Operational constructors do not assume
the invariant or the simulation theorem.

A successful concrete trace includes two agents and two use aliases, pending
registration after gate close, activation during Closing, authority retirement
while queued uses remain, effects after submission disable, duplicate/lost
packets, individual completions, receipts and reuse. A separate reachable trace
closes and seals an unpublished gate while its initial publication packet remains
queued; that packet cannot pass the tombstone guard. An Active-phase trace
closes a use while queued work can still effect, finishes/seals/acknowledges it,
then admits a fresh use from the same still-open gate. Two delayed deliveries
of the old exact-ticket close cannot close that fresh use. Losing all packets preserves
the remaining liability rather than allowing quiescence.

Seven controls establish invariant/provenance failures: premature gate sealing,
premature work drain, late-publication reopening, duplicate registration,
misbound receipts, uncovered publication and false drain-receipt origin. These
are not seven physical-unsafety proofs. A separate counterexample starts from a
reachable state, emits one premature drain receipt, then uses the original
reception/retirement/quiescence/reuse/effect rules to exhibit an actual old-version
access after reuse.

Run `./verify-r.sh` from the enclosing directory with the pinned Lean toolchain.
It builds this refinement and audits 33 exported theorem dependency reports;
only standard `propext` and `Quot.sound` are permitted. No project axioms,
admitted proofs or compiler-backed proof shortcuts are used. Run the existing
`./verify.sh` separately for Q. Ordinary `make test` does not install Lean or
replace these mandatory proof gates. Final-source qualification is recorded in
the PR; none of these results upgrades physical-platform qualification.

The registration/grant binding invariant proves the unique retained request/ID
association needed for reclamation; a full typed grant/authorization theorem is
not claimed. The existing Q artifact and its acceptance gate remain separate.

The [A0 snapshot authority layer](../A/README.md) separately composes immutable
grant/footprint metadata and conserved writer permission with this protocol.
It does not change R's hardware, recovery or concurrency qualification.
