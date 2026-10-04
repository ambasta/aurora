# Candidate: DMA ownership and retirement model

This is an isolated, executable **pure host model** for design review. It adds no
kernel code, hardware programming, DMA protection or driver support. Nothing here
is included by the Aurora build. Its acknowledgement objects are simulated
trusted observations, not unforgeable capabilities or hardware completion proof.
Python object fields remain directly mutable; that is outside the model API.

Baseline: accepted milestone015, byte-exact Git tree
`7c1b69896d2fdcccab52e6cbf4d9ede002e44393`, archive SHA256
`4cdfb46478f18e594ebebb42f2871bd60b63f7b14a96684d2be60465284dc637`.
The original main directory is unchanged. `baseline.json` binds the inspected
resource contracts and an actual accepted IVRS read receipt. `observations.json`
contains facts extracted from that receipt, with its hash and original path.

## What the current kernel establishes

The read receipt observes namespace-free NVMe requester 0x10 at 00:02.0 with
memory decoding enabled, bus mastering disabled, and CC/CSTS/AQA/ASQ/ACQ zero.
The paired IVHD descriptions cover requester 0x10. They are bounded topology
facts. The IOMMU CTRL is zero and its architectural capability enable bit is
clear. The explicit QEMU cold-read exception permits observation only. With
IommuEn clear, the model permits identity DMA regardless of pt=off. Other
firmware-enabled requesters also exist. Therefore no current receipt can become
an activation acknowledgement in this model.

PhysicalPages has move-only epoch/generation leases but no DMA pin counter. Its
release method may make a frame immediately reusable. A future broker must
consume exclusive leases and keep them inaccessible to that release path until
retirement completes. The pool must outlive the broker and every quarantine.
This candidate does not modify or wrap that allocator.

## Bounded modeled contract

One kernel-owned broker ledger, one requester (0x10), two distinct exclusive
frames, one mapping, and one outstanding operation. Frame IDs 0 and 1 are abstract;
they are not physical addresses, IOVAs, actual page-table entries or kernel leases.
No aliases, multiple clients, directions, scatter/gather, ATS, peer-to-peer,
interrupt remapping or noncoherent caches are supported by this model.

The broker identity is fresh across object construction. Device incarnations,
frame lease generations, mapping generations and operation IDs never wrap.
Model copies used for exploration represent alternative worlds, not additional
runtime brokers that can share physical frames. The owning ledger is assumed to
remain alive; dropping/reconstructing it is not an operation and cannot be used
to recover quarantined frames. A real implementation must enforce that lifetime
and a global exclusive-frame ledger before adopting this model.

| State | Allowed next observation or intent | Ownership consequence |
|---|---|---|
| Empty/Retired | reserve fresh incarnation | Pin both zeroed frames |
| Reserved | install, or cancel to scrub | No publication before pin |
| Installing | exact install completion | Publication may already be visible |
| Mapped | start, or retire | Start requires completed installation |
| Running | retire | Stop new submission; retain possible DMA reachability |
| Quiescing | exact stop/drain completion | No free frame merely from a stop request |
| Invalidating | exact invalidation completion | Quiescence alone cannot release cached translations |
| Scrubbing | exact visibility/scrub completion | Release only after all retirement observations |
| Quarantined | none | Retain all pages permanently |

`True` means the request/observation was consumed, not that a device operation
succeeded. Generation exhaustion during an operation consumes the request and
enters quarantine without issuing a new operation. `False` means rejection with
no state change. Failed/uncertain completion or timeout is terminal quarantine;
a late success never changes that disposition. Cancellation while an operation
is pending is represented conservatively by timeout/quarantine. There is no
rollback on an uncertain installation failure.

All completions must match the entire binding and current operation kind/ID.
The kernel-selected binding must not come from user-provided scalar claims.
Quiescence means more than BME clear: it must establish completion/cessation of
in-flight access by the exact device incarnation. Invalidation completion must
follow removal of every translation potentially installed and cover all relevant
IOMMU/device caches. CPU INVLPG is not this evidence. Scrub completion includes
visibility/cache obligations before reassignment. These are deliberately assumed
adapter events; no existing Aurora function provides them.

## Observable host gates

Run from this directory:

```
python3 test_lifecycle.py
python3 -O test_lifecycle.py
python3 test_mutations.py
python3 -O test_mutations.py
```

Tests explore all distinct reachable states for generation bounds 1 through 8,
with valid/invalid lifecycle calls, wrong requester, stale incarnation, wrong
operation, failures and timeouts. Focused tests mutate each completion-binding
field, reject cross-broker tickets, replay old scrub completion after reuse, and
check absorbing quarantine at each asynchronous stage. Deliberately broken
release-on-timeout, release-on-quiescence and release-before-scrub variants must
be caught by a separate release predicate. These finite tests are evidence for
this small abstract contract, not a proof of hardware DMA isolation.

## Proposed next integration, requiring review first

1. Implement a kernel-owned pin owner using the actual move-only PageLease and
   a persistent arena/quarantine ledger, with no service-visible release path.
   Bind real frame/IOVA ranges, permissions, domain and requester identity;
   reject aliases, overlap, incomplete coverage and unsupported hardware facts.
2. Add a typed command-intent adapter whose completion identities originate in
   kernel bookkeeping. Before any enable, independently validate the complete
   default-deny device table, owned translation/command/event pages, resource
   limits and failure policy against the normative AMD specification and pinned
   emulator behavior. The current cold-read quirk is not an activation profile.
3. Propose exact emulator programming separately: register/command writes,
   visibility barriers, invalidation/completion semantics and fault evidence.
   Acceptance must demonstrate allowed access to only leased pages, denied
   access to a separate sentinel page, stale-translation denial after revocation,
   preserved sentinels, and failed-quiescence quarantine without reuse. This
   cannot be replaced by register readback or elapsed time.

No active-control test or positive DMA gate is authorized or implemented in this
candidate. NVMe submission queues, engine enable, BME changes, interrupts,
filesystems and physical hardware remain deferred. A default-deny translation
mechanism also does not by itself prove platform-wide DMA isolation.
