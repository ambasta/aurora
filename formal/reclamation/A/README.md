# A0 snapshot authority profile — proof in progress

This work-in-progress extends the endpoint protocol with a bounded permission
profile for one arbitrary allocation: one exclusive sequential writable stream,
then immutable read sharing. It is not full obligation A or a general grant
architecture. Disjoint writable extent splitting and cross-allocation product
composition remain open; this is not a prescribed global allocation lock.

## Checked so far

The operational model, metadata erasure into R, finite-trace simulation and
inherited future-reuse exclusion compile. Initial invariants, immutable grant
and wire-payload retention, and exclusion consequences *assuming* the invariant
also compile. **Inductive permission preservation, successful A0 witnesses,
mutation controls and the snapshot contract adapter are not complete yet.**
Consequently there is no reachable-state authority theorem or qualification
claim for A0 at this checkpoint.

The initial allocator supplies a named issuer/subject capability. Writer
permission moves through a local gate, request escrow, registered transfer or
use, and receipt-bound return. Freeze consumes it into an absorbing
version-indexed frozen location and locally enables read admission. A lost reply
never restores a second owner. Read/use payloads and grant ceilings never change;
effects inspect admitted descriptors and outstanding work, not a global
permission/frozen-state oracle. A writable work item denotes a single sequential
ordinary-access stream: one GPU job or DMA command is not thereby internally
race-free. Exclusion concerns distinct admitted streams.

The extra immutable request/ticket maps model decoded enriched wire bindings;
R packets erase that payload. Transport encoding, authentication and protection
against forged external packets remain implementation obligations. The model
uses interval footprints in backing-cell coordinates. Connecting scattered
physical frames to those coordinates requires an explicit alias-preserving
mapping contract; no source/physical mapping proof is claimed.

A small prerequisite extends R with an owner-initiated close request for an
already published use in Active as well as Closing. It only sends the existing
close packet. Submission disabling, queued effects, drain, sealing and receipts
remain separate. Normal writable-use completion therefore does not require
prematurely initiating whole-root reclamation.

The planned adapter connects the snapshot lifetime contract to
`memory_manager.au` fill/seal/discard and the native mapping authority's distinct
incoming chunk and sealed snapshot pins. Existing native parser pins are single
lexical pins; multiple A0 read consumers are a target generalization, not current
kernel functionality. No runtime/compiler/ISA refinement, crash recovery, bounded
metadata, progress or hardware-support claim is made.
