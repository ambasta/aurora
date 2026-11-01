# A0 transition review proposal (not a completed theorem)

A0 fills the permission gap in R, without changing Q or R. This is an initial
allocated-capability boundary, not generic authentication or full obligation A.

## Smallest first slice

One allocation/version has an immutable physical-cell footprint. Logical views
carry sub-footprints of it; distinct view IDs never establish disjointness.
The first slice conservatively grants one exclusive sequential writable lease
for the whole allocation, then freezes it for shared readers. It does not permit
disjoint writers within this allocation. Separate disjoint allocations can be
modeled independently, but an independent-root commutativity theorem is not
part of this slice. This scope reduction avoids inventing a general permission
algebra before validating its composition with R and the native snapshot policy.

State includes the R endpoint state, immutable grant ceilings/provenance and
request/use modes (never retrospectively changed), monotone read-admission
activation for gates,
generation-indexed mutable/frozen history, and one exclusive token location:
unissued, at a gate, in request escrow, at a transfer, or at a use lease.
Initial allocation gives a trusted issuer one grant for a named initial subject.
Root creation consumes that grant; R's unrestricted root creation is not exposed.

1. Writable use request: a locally published, open gate possessing the token
   checks requested footprint inclusion and subject, then consumes its token
   into a fresh request escrow while making the existing R request transition.
   Only one writer request/lease can consequently exist. Read requests check
   a retained local read grant/activation; frozen-generation provenance is derived
   by invariant, not a remote mutable-state check. They do not consume exclusivity.
2. Writable delegation likewise consumes the token into request escrow. There is
   no timeout reacquisition. Read delegation attenuates the read-only footprint.
3. Coordinator registration creates immutable ticket metadata from the retained
   request binding and moves writer escrow to the newly registered use/transfer.
   Duplicate registration does not create metadata or move permission.
4. Transfer activation moves a writer token from its transfer record to the
   reserved receiver gate, alongside R activation. Duplicate activation does not
   move it again. Read receiver metadata is copied from its immutable transfer.
5. Use submission checks the immutable admitted mode/footprint and local lease
   state. A writable lease is sequential: at most one outstanding work item.
   A writable work item denotes one sequential ordinary-access stream, not a
   GPU job assumed internally race-free merely because its work count is one.
   Effects consult only the admitted use record and outstanding work, not a
   global authorization oracle. The exclusion theorem concerns distinct admitted
   streams/leases; within-job race freedom requires a separate refinement. Read/write event labels include physical cell.
6. Close, finish, seals, packet delivery/loss/duplication and receipt handlers are
   R operations. A sealed use has no possible future work by R's proved invariant.
7. Returning the unique writer token to its originating gate requires that exact
   use's sound retained receipt, and consumes the token-at-use location. Repeated
   return cannot mint another token. The operation erases to R stutter.
8. Freeze requires token-at-gate, so no pending writer request, transfer or use
   survives. It consumes the write token and activates read-only admission under that gate's immutable grant ceiling. Descendant read grants remain read-only. It erases to R stutter.
9. Reuse follows R quiescence and creates the next allocation-version grant only
   for the trusted initial subject. Old metadata remains version-bound.
10. Refusal is an explicit no-change event. No accepted-request cancellation
    recovery, restart, partial thaw, COW or rights enlargement is supplied.

The implementation may use explicit operational constructors wrapping each R
primitive. It must not expose an arbitrary R transition that bypasses permission
updates, nor use global invariant/compatibility predicates as transition guards.

## Required proof and observables

Inductively derive immutable provenance/attenuation, unique writer conservation,
and the fact that any possible writable lease owns the exclusive token while
any possible reader belongs to a frozen generation. Therefore conflicting
possible ordinary uses on the same physical cell cannot coexist. A logical
alias has no special exemption. Sequentiality is per-use protocol state, not
inferred from an endpoint/agent identity.

Projection erases metadata and erases cell/mode from access labels; every step
is an R step or internal stutter. R/Q supply safe reuse. Freeze immutability is
absence of admitted write events until reuse, NOT a verified byte-heap theorem.

A checked abstract snapshot adapter must exhibit writable preparation, fill,
drain, seal, shared read pins, pin retirement and discard through this model.
The reviewed R extension permits an owner-initiated published-use close request
in Active. It sends the existing close packet without changing work, phase,
seal or receipt state. Normal fill/drain/freeze stays Active; root BeginClose
is reserved for the actual allocation discard/reclamation phase.

Its contract table names memory_manager.au fill_snapshot/seal_snapshot and
MappingAuthority SourcePin/SnapshotReadPin checks. It does not claim native code,
compiler, memory model or ISA refinement.

Acceptance includes a successful writer/freeze/two-alias-reader/close/reuse
trace, delayed/duplicate delegation, rights/footprint refusal examples and
reachable mutant witnesses for duplicated writable authority, premature freeze,
timeout escrow recovery and stale-version rebinding. At least one control must
exhibit actual conflicting enabled effects, not only an invariant failure.

The deliberately narrowed artifact is A0 snapshot-profile authority conservation,
not general authority architecture. The originally proposed disjoint-writer
witness is deferred with the extent-splitting algebra, explicitly not satisfied
by this slice. It quantifies one arbitrary allocation, not one global allocation
lock; cross-root independence/commutativity still needs product composition.

Immutable request metadata represents extra wire payload erased by projection,
not coordinator access to mutable endpoint state. Writer use return restores
the exact reserved origin activation/generation and its retained grant ceiling;
a narrower use footprint is not a narrower reserved ownership obligation.
Delegation may attenuate the ceiling and never restores the source owner.
No global frozen/token check is added to use effects: sealed old records cannot
submit/effect by the existing R seal invariant.

## Adopted prerequisite: local use closure extension

Rather than force normal fill/drain through root Closing, the proposed minimal
R extension is requestUseClose: for an existing use ticket, enqueue its existing
close message in any root phase. Receipt/drain/actual-work semantics are unchanged.
Projection maps this request to Q stutter; close packet validity is already True.
A successful Active-phase witness must retain queued effects after submission
disable, then finish/seal/send receipt while the issuer gate stays open.
Both independent reviewers approved this replacement of the earlier
Closing-adapter workaround; the exact R delta was independently reviewed.

Native SnapshotReadPin currently permits only a single lexical parser pin, not
two simultaneous native pins. The abstract shared-reader witness is a target
generalization. The adapter distinguishes the incoming fill SourcePin(chunk)
from sealed SourcePin(snapshot) and SnapshotReadPin; native/compiler/ISA
refinement remains unproved.
