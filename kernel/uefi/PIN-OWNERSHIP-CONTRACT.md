# CPU-only pin ownership candidate

This slice exercises actual PhysicalPages leases in the existing protected UEFI
runtime. It does not publish DMA mappings, initialize an IOMMU, enable a controller
or BME, submit commands, or provide hardware completion authority. The earlier
read-only IVRS and BAR facts remain insufficient for any of those operations.

A static kernel-owned PinLedger holds four entries, up to two move-only PageLease
objects each, from the existing sixteen-frame runtime pool. Domain stacks keep
their independently owned leases. Pool and ledger storage remain alive throughout
the boot; no destructor frees retained leases. The ledger, registry and allocator
cannot be copied or moved. Reconstructing the allocator or reassigning its arena
while ownership remains is an excluded trusted lifetime violation, not recovery.

The opaque PinHandle binds ledger address/epoch, entry generation and slot. Its
use additionally requires the currently live DomainHandle incarnation. Clients
receive no frame address, PageLease, scrub callback, publication operation or
completion constructor. The trusted adapter performs requests only after the
existing ProgramRun exact-site, CPL, CR3 and stack validation and kernel-root
restoration. The clean program's scalar42 is a controlled request result; it does
not choose the owner, ledger operation or completion. Kernel test configuration
selects the phase and owner.

Normal entries are provably unpublished because this API has no publication
adapter. Granting a pin does not promise initially zero bytes, and exposes no
view of them. This differs from the isolated host model's zero-at-reserve
assumption; future publication must independently establish initialization and
visibility before granting any device or service access. Cancellation, borrower disposal and dead-owner reaping scrub every
owned page and verify its bytes before releasing any lease. Failed scrubbing
quarantines all pages of that entry. Partial acquisition failures scrub and
release only their actually acquired prefix; failure keeps that prefix pinned.
No unrelated domain stack lease can be imported or released through this API.
Counters retire exhausted entries and never wrap.

Quarantine has no release transition. The only uncertainty injection function is
compiled under AURORA_PIN_LEDGER_TESTING in the fault fixture and hosted tests;
it is absent from normal builds and no service scalar reaches it. Its effect is
to remove release authority, never grant hardware authority. Test-injected
uncertainty is not evidence of real DMA publication or a real hardware failure.
A future adapter must introduce a reviewed publication state and authentic
ordered quiescence/invalidation evidence; it may not reinterpret this CPU scrub
callback as device completion.

## Four actual modes

All modes retain the existing two-domain layout, guarded stacks, four compiled
user executions, exact bounds-fault recovery, private CR3 restoration and
page-table verification. No arena, image or stack limit is widened.

- runtime-pin-cancel: after a validated clean return, pin two real pages, poison
  their bytes, cancel, verify zero bytes before reacquisition, and finish with
  zero pin/pool allocations.
- runtime-pin-fault: the kernel fixture pins two pages for the bounds-faulting
  service and injects uncertainty before execution. Following the recognized
  fault and domain disposal, the static ledger retains both pages. The clean
  peer still returns 42. After original domain retirement, recreate slot 0 with the existing bounds
  image as an inactive placeholder and slot 1 with the distinct existing clean
  image. The restarted service in slot 1 returns 42 with a new registry incarnation;
  its stale original owner/token cannot cancel fresh or quarantined grants.
  Old/new incarnation records are bound to the initial loan and restored
  restarted-service return. No extra root, frame range or shared RX alias is used.
  After restarted-service cleanup, exactly two quarantined pages
  remain allocated and their poison remains, proving that disposal did not scrub
  or recycle them.
- runtime-pin-stale: reject an old entry generation and a foreign live owner;
  after domain retirement/rebirth, reject its stale incarnation and token while
  accepting clean cancellation for the new owner.
- runtime-pin-exhaust: fill four ledger slots while spare pool frames remain,
  then separately hold seven of the eight non-stack frames and request two.
  The one-frame partial acquisition is scrubbed/rolled back, without releasing
  the seven independent reservations or eight stack frames. A later unpublished
  loan is scrubbed by borrower disposal after its recognized fault.

Only known compiler fault sites are contained. Unknown origins remain fail-stop.
These are sequential controlled phases, without general scheduling, arbitrary
client requests, device-cache management, hardware aliases or DMA visibility.

## Validation and status

Run `make test-pin-ledger test-uefi-pins` and, with the existing QEMU/OVMF variables,
`make smoke-uefi-pins`. The actual wrapper restores a normal UEFI image after each
mode. Receipt validation reuses the full runtime origin/metadata checker, then
requires every pin accounting row at its exact restored-kernel phase. The fault
fixture alone permits retained count 2; historical modes still require 0.

Initial development execution passed all four modes using the immutable M014
compiler 2d86780c before the same-service-slot restart enhancement; those earlier
receipts are preserved and do not establish the enhanced restart gate. A subsequent
development rerun of all four modes passes the enhanced slot 1 restart on the same
compiler, recording incarnation 2 to 4 and final retained count 2. Hosted tests pass 165 normal and 294 generation-bound checks, also under fatal
ASan/UBSan, with production API and four invalid-configuration controls. Strict
transcript tests pass 4 positive and 236 negative controls, also under Python-O.
Independent integration review passed all four final modes on compiler 14cbaa33,
including same-service-slot 1 restart, with source hashes unchanged. The final
worker run passed all 162 modes (158 historical plus four new), with 266 project
inputs and 182 external pins equal before/after and 720 verified receipt hashes.
Normal images were restored. Parent aggregate/spot verification and archive
acceptance remain separate and pending at this record.

Full local audit: `/workspace/scratch/48c5de6446f8/aurora-m016-kernel-receipts`.
Independent final evidence:
`/workspace/scratch/48c5de6446f8/pin-lifetime-review/actual-final-four`.
The distributable evidence explicitly omits 30 third-party firmware files and 54
generated executables; their hashes and local originals remain available.
No hardware activation, DMA safety or physical-platform qualification follows
from these CPU-only lifetime gates.
