# CPU-only dormant translation tables

The four `runtime-table-*` modes construct and inspect actual owned guest RAM.
They do not install an IOMMU table or issue a device DMA transaction. They use the
ordinary packaged-OVMF runtime fixture without adding an AMD-Vi or NVMe device.
RID0x10 is a fixed format-test requester, not a discovered live endpoint grant.
The constructor is temporary trusted C++23 bootstrap code; Aurora services gain
no unsafe, pointer, callback or foreign ABI surface.

## Format and normative boundary

The explicit AMD310Host4KBus0 profile has256 dense32-byte DTEs in two contiguous
4KiB pages, one512-entry level-one host table and at most two4KiB data pages.
All DTE holes use V=TV=1, Mode0, IR=IW=0 and DomainID0. Exactly RID0x10 may use
Mode1, the owned root and DomainID1. Read-only and read/write leaves are supported;
unused leaves are exactly zero. Nonzero ignored fields are deliberately rejected
by this narrower canonical profile. IV remains0, so no interrupt denial is implied.

Reference: AMD48882-PUB Rev3.10, February2025, §§2.2.2–2.2.3, pp63–85; table-size
register §3.4.1, p208. The user-supplied reference is
https://kib.kiev.ua/x86docs/AMD/IOMMU/48882-3.10.pdf
with SHA256 cd7559334b3f46a72d56e9f2fac786fcbf5d6a2c41e7770a46fcacc080bc8a12.
The PDF and copied figures/tables are not distributed with Aurora.

Important divergences remain in QEMU10.0.13, pinned commit
98f88efe8f07067667b8d9b1a5ce9551d34036c1, hw/i386/amd_iommu.c:
DTE fetch867–885 lacks the architectural requester-length check; page walk947–979
omits upper-address/final-leaf-presence checks and can return/cache permissions
stronger than a parent. Architecture requires those checks and cumulative rights.
An all-zero DTE bypasses ordinary memory translation. Software-model rejection
of a requester or IOVA does not constrain a misbehaving device. No current guest
result qualifies this emulator as an architectural isolation oracle.

## Actual ownership and trusted adapter

The existing1MiB arena,16-frame pool, two user roots, two RX images, guarded user
stacks, guarded kernel-entry/IST stacks and16KiB bootstrap stack are unchanged.
Eight pool frames remain owned by the two user stacks. Dormant construction uses
at most five additional frames and three of the existing four ledger entries.
No fragmented DTE pair is accepted and no allocator limit is enlarged.

The permanent PinLedger holds real PageLeases; a private typed friend constructs
only its three bound roles. All bytes are initialized before seal. Seal rereads
all DTE and leaf bytes and validates the live owner, epoch/generations and actual
lease addresses. Every later validation repeats those checks. There is no raw
address/view, arbitrary callback, publication or completion method for service
handles. Test-only inspector declarations are absent from production preprocessing;
including the inspector in an ordinary image is a compile error.

The guest adapter binds the arena's existing supervisor-only CPU mapping and
selects32-bit physical bounds because this owned allocation is below4GiB. Existing
ACPI admission checks PAT0=WB; effective cache/MTRR state, the physical-to-virtual
correspondence, exclusive mapping and backing lifetimes remain trusted bootstrap
preconditions. They do not establish IOMMU coherence or hardware capability.

The inspector is compiled only into these explicit CPU test images. It returns
small bounded views for the independent decoder; it never creates a service
binding. Actual table bytes stay in leased pages. A prior successful seal is not
a certificate for subsequently mutated bytes. Corruption tests require a new
rejection from both validators and a separately checked restoration for each case.

## Four observable guest gates

- `runtime-table-readback`: after a compiled clean42 return and actual kernel-root
  restoration, build five pages, independently decode every DTE/leaf, exercise
  software permission/range queries, cancel, then simultaneously reacquire all
  five frames and verify zero bytes. Continue the existing bounds/clean/reuse path.
- `runtime-table-reject`: additionally mutate denied-entry validity, mapped domain,
  root address, leaf presence, write permission and a reserved leaf bit. Each
  case emits ordered rejection/restoration outcomes for constructor and decoder.
  Five malformed request/owner/width cases preserve pool and ledger accounting.
- `runtime-table-exhaust`: reject fragmented DTE backing, fewer than five free
  frames and insufficient ledger entries while preserving separate reservations;
  then complete ordinary construction/cancellation.
- `runtime-table-quarantine`: construct for service slot1, contain only its exact
  compiled bounds trap using unchanged CPL/root/site rules, restore the kernel
  root, then inject one compile-selected scrub failure. Two DTE pages remain
  quarantined; the other three never-published pages scrub/release. Retire the
  owner and restart the same slot with a new incarnation; stale-constructor
  validation/cancellation reject, a fresh loan/cancel succeeds, and clean42 runs.

All groups are provably never published because no publication operation exists
in this slice. Releasing the unaffected groups is not a hardware-quiescence result.
No destructor frees retained pages. Final pool/pin accounting is0/0/0/2 by mode.
Unknown user/kernel origins remain fail-stop; no new fault recovery is introduced.

Records explicitly use CPU_BYTES, SOFTWARE_MODEL and publication=never. The
strict validator checks complete ordered records, exact counts/roots/incarnations,
known runtime metadata and each authorized continuation. It rejects missing or
duplicated corruption outcomes and successful-byte markers inserted while bytes
are corrupt. Hardware/DMA success markers are never emitted or accepted.

## Stack and acceptance

Each table-mode build checks actual compiler .su records and linked direct-call
edges before boot. The TABLES-only ACPI preparation function ends before PCI
scan construction, preserving historical branches. The bound covers ACPI,
Topology parsing, PCI, fixed-four-slot mapping verification, table construction,
readback/corruption, cleanup and runtime helpers, plus1024 bytes for faults.
Mode-specific raw .su, disassembly and the calculated bound are retained under
build/uefi/table-stack/<mode>. A table-sized stack temporary or reintroduced
parser-to-PCI edge fails the regression gate. No stack/page-layout widening occurs.

Commands: make test-dormant-tables, SANITIZE=1 make test-dormant-tables,
make test-uefi-tables and make smoke-uefi-tables. Hosted checks do not establish
actual guest behavior or hardware DMA authority.

## Separate architectural translation oracle

The hosted [Mode 0/1 oracle](../../docs/iommu-models.md) provides test-only
fixtures for noncanonical architectural semantics that this profile cannot
represent. It reads copied constructor bytes and independent fixtures; it grants
no publication authority. The [DMA conformance boundary](../../docs/iommu-dma-conformance.md)
separates software-model behavior from actual translation/isolation evidence.
