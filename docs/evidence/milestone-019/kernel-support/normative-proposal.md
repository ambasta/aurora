# Dormant AMD 3.10 host-translation construction proposal

Status: normative review completed; implementation approval pending. This original
engineering note supersedes no historical receipt. The earlier PROPOSAL.md and
qemu-review.md remain the pre-specification research record. No main-tree change,
IOMMU register access, device activation, DMA, or hardware qualification is part
of this proposal.

## Reference identity

The user supplied AMD publication 48882-PUB, Revision 3.10, February 2025:
https://kib.kiev.ua/x86docs/AMD/IOMMU/48882-3.10.pdf

The locally read PDF has SHA-256
`cd7559334b3f46a72d56e9f2fac786fcbf5d6a2c41e7770a46fcacc080bc8a12`.
It has 310 pages. Printed and PDF page numbers agree. The document and rendered
reference pages remain outside the repository and are excluded from deliverables.
Its access-based agreement was disclosed by the parent. These notes contain
original design decisions and section/page citations, not copied specification
figures or tables. The separately denied revision 3.11 was not accessed.

Pinned QEMU remains commit `98f88efe8f07067667b8d9b1a5ce9551d34036c1`.
The file identities and exact line references are in the historical qemu-review.md.
A second reader independently checked the normative format and constraints.

## Normative findings and emulator differences

The specification's sections 2.2.2 and 2.2.2.1 (pages 63, 71–75) confirm that an
all-zero DTE is permissive for ordinary memory. Our canonical memory-denied entry
sets V and TV, selects Mode zero and clears both memory permissions. This leaves
IV clear: interrupt pass-through remains, and interrupt isolation is expressly
excluded. ATS, PPR, guest translation and exclusion permissions are not enabled.
TV-clear semantics must not be inferred from QEMU's permissive permission branch.

Domain IDs identify compatible translation contexts. The mapped root must have a
different DomainID from the Mode-zero denied entries (Table 7, page 71). Merely
choosing different requester IDs does not remove that requirement.

Section 2.2.2 (page 63) specifies dense 32-byte DTEs, contiguous storage without
segmentation, and 4KiB alignment/length units. Section 3.4.1 (page 208) defines the
size field. An enabled architectural IOMMU rejects a requester beyond its table;
QEMU's `amdvi_get_dte` (c:867–885) does not check its computed length. PPR is a
separate architectural exception, deliberately excluded here.

Section 2.2.3 (pages 81–85) requires upper-address rejection, presence checks,
cumulative path permissions, valid descending levels and correct alignment.
QEMU c:947–979 omits several of these checks: high IOVAs can alias a low root,
a final absent nonzero leaf may return permissions, and returned/cached rights
can exceed a restrictive parent. Section 2.5.3's fault cases corroborate these
requirements (pages 144–145). Software builder bounds do not constrain requests
from a misbehaving device. QEMU cannot serve as a conformance or isolation oracle
for these cases without a separately reviewed qualification change.

The exact-zero absent-leaf requirement below is deliberately stricter than the
architecture: Table 16 (page 82) ignores remaining bits when PR is clear. It
simplifies deterministic validation and rejects stale encoded addresses.

Sections 2.2.2.2 (pages 77–78) and 2.3.1 (pages 120–121) describe additional live
update/initialization requirements. No construction result discharges cache
invalidation, visibility, quiescence, event/fault observation or activation duties.

## Explicit profile: AMD310Host4KBus0

This is a CPU-memory format profile, not a platform qualification profile.

- One unsegmented, dense 256-entry device table: exactly two contiguous 4KiB
  pages. Every hole is initialized to the canonical memory-denied entry. The
  exact accepted requester is segment zero, bus zero, device two, function zero
  (RID 0x10), independently bound to trusted fixture identity. No alias, phantom
  function, bridge requester substitution, or caller-selected identity is admitted.
- One 4KiB level-one host page table with 512 entries and at most two 4KiB data
  pages. All other leaves are canonical zero. IOVAs are page-aligned below 2MiB;
  accesses validate the whole checked interval before offset arithmetic.
- Mapped DTE: V/TV set, Mode one, parent IR/IW set, DomainID one. Denied DTEs use
  DomainID zero and have no root or permissions. The other DTE words/fields are
  zero. Interrupt state is never presented as blocked or remapped.
- Leaves: explicit little-endian physical address, PR set, NextLevel zero, and
  exactly requested read-only or read/write permission. No huge pages, skipped
  levels, accessed/dirty mutation, guest tables, PASID, ATS/PRI, migration,
  exclusion, force-coherent override, or cache-attribute override.
- Every complete physical interval must fit both the format's 52-bit field and
  the narrower trusted arena/profile width. Masking an invalid address is forbidden.
  CPU physical width alone cannot certify IOMMU capability for future activation.
- Table and data roles are disjoint exclusive owned RAM pages; no kernel stacks,
  user RX images, firmware, MMIO, reserved RAM or incompatible aliases. Unsupported
  cache/coherence assumptions reject instead of becoming defaults for hardware.

## Ownership and lifetime

Five frames and three ledger entries suffice: two contiguous DTE pages, one root
page, two data pages. This fits the existing two-domain fixture's eight spare
frames without consuming its eight stack pages. Fragmented DTE backing is refused;
there is no silent allocator/layout expansion. Contiguity must be checked against
actual leases, not assumed from acquisition order.

A narrow trusted construction owner will bind the three live PinHandles to their
roles, actual domain incarnation, ledger epoch and generations. A private typed
operation may access only those owned pages synchronously. It must not expose a
raw-address lookup, arbitrary write callback or mutable span through service
scalar tokens. No lease import, publication, device completion or register-base
export operation is added. An isolated extension must retain the production
ledger's reentrancy and ownership checks and be reviewed before integration.

Construction starts by initializing all owned bytes. Seal reads back every DTE
and leaf and matches exact role extents, identity, permissions and unused entries.
Queries decode only this bounded owned snapshot; encoded pointers are resolved
against owned extents rather than dereferenced as arbitrary host addresses.
Changes after seal are rejected; test-only corruption is explicitly selected and
must invalidate acceptance. Seal means validated dormant bytes, never hardware
consumption, visibility, cache flush or DMA authority.

Cancellation is allowed because no publication path exists. Complete-frame scrub
and verification precede reassignment. Failed scrub or uncertain ownership keeps
frames quarantined in the permanent ledger, even after borrower death. Partial
construction cannot release unrelated stack or retained pages. Stale handles,
reborn domain slots, generation exhaustion and ledger exhaustion fail closed.

## Proposed isolated acceptance

1. An independently written decoder checks all 256 DTEs, all 512 leaves, explicit
   endian bytes, exact target index and physical-role bindings. Boundary IOVAs,
   offsets and R/RW permissions are checked using the architectural software model.
2. Mutations cover zero/bypass DTEs, wrong domain, nonzero absent leaves, cleared
   PR, over-wide addresses, upper IOVAs, misalignment, overflow, unsupported fields,
   duplicate/overlapping roles, forged requester/root, extra leaves and permissions.
3. Use real PinLedger/PhysicalPages/DomainRegistry for bounded allocation,
   fragmented contiguous-pair refusal, partial rollback, exhausted pool/ledger,
   stale owner/token, service death, scrub failure quarantine and zeroed reuse.
4. Preserve the earlier QEMU-only tests as a separate implementation model;
   divergent behavior must remain an explicit expected mismatch, never a waived
   architectural requirement. No actual QEMU DMA translation is tested.

After isolated review and main-source clearance, propose a guest CPU construction
and readback gate using the same owned pages. That later gate still requires no
IOMMU/MMIO/BME write. Activation, command/invalidation engines, requester fault
containment and any device DMA require a separate scope and qualified mechanism.
