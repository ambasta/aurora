# Dormant host-translation construction candidate

This isolated candidate implements the approved AMD310Host4KBus0 CPU-memory
construction operation. It is pending independent ownership/implementation review.
No main checkout edits or emulator/device operations occurred. M018 baseline main
Git tree supplied by the parent is b7ae932589b7b236aff9f1fc6d02714de33becf0.
The exact consumed main header hashes are in baseline-inputs.json.

The normative design, source identity and QEMU divergence findings are in
../AMD310-CONSTRUCTION-PROPOSAL.md. The earlier sibling notes/models are preserved
as historical pre-specification evidence. No reference PDF or copied specification
figures/tables are included.

## Running host-only tests

Run `python3 run-tests.py /tmp/a-new-output-directory` from this directory. The
output directory must be new. G++ C++23, Python3, ASan and UBSan are required. The
script never invokes QEMU or any device tool. Fatal sanitizer checks remain enabled;
LeakSanitizer is disabled for the environment's ptrace limitation.

Original author run: /tmp/aurora-amd310-review/host-final-1. Its two non-static
member-function privacy probes failed for invalid member-function conversion,
rather than establishing privacy; those receipts are preserved as wrong-reason
failures and do not prove access control. No production escape was demonstrated. The corrected runner
uses well-formed member pointers, requires the actual private-access diagnostic,
and compiles each identical expression against an isolated public-mutant copy.
It also requires exact compiler status1, rejecting crashes as negative evidence.

Corrected targeted run: /tmp/aurora-amd310-review/privacy-corrected-1, all13
commands passed. Final full rerun is /tmp/aurora-amd310-review/host-final-2; its
33-command result and pre/post manifests are authoritative once complete. Results:

- 92,306 real-ledger construction/ownership and independent-byte checks, both
  ordinary and fatal ASan/UBSan.
- Independently authored decoder:164,313 checks, both ordinary and fatal ASan/UBSan.
  It validates every single-bit mutation of the12KiB table snapshot and all65536
  requester values. The author did not read the encoder implementation.
- Small generation limit3:3 successful complete constructions then17 refusals,
  no counter wrap or leaked reserved pages, ordinary and sanitized.
- Production API checks plus10 expected compile rejections for private access or
  invalid testing/generation configuration, and6 positive public-mutant controls.

Native tests are actual CPU executions using real PageLease/PinLedger/DomainRegistry
objects. The independent walker is a software model, not an IOMMU transaction or
DMA-isolation result. No guest CPU construction gate has been run yet.

## Implementation and integration delta

include/dormant-tables.hpp is new. Its only ledger access is through the private
friend in pin-ledger-integration.patch. Copies of the three baseline headers are
retained for exact review; pages.hpp and domain-policy.hpp are byte unchanged.
Only pin-ledger.hpp gains the forward declaration and friend declaration. No
production pin method or policy is otherwise changed. Main integration is not
performed or authorized by these copies.

The typed constructor obtains2/1/1-or2 frames through three actual ledger grants,
requires the first pair to be physically contiguous, initializes the buffers and
seals exact readback. The mapped target uses DomainID1; all denied holes use0.
It accepts no requester scalar, hardware completion, register base or callback.
Public methods return only booleans. Services cannot obtain the backing view or
lease handles. Test-only private access is selected explicitly in the hosted
ownership fixture and is absent from the production class definition.

All cancellation is for never-published storage. Scrub/release is delegated to the
permanent ledger. Failure retains its affected entry in quarantine; unrelated
never-published entries may be released. A stale/reborn owner cannot validate or
cancel the old constructor. The permanent ledger can reap dead reserved owners.
Destroying the constructor does not release any frame. Fragmentation, pool and
ledger exhaustion preserve independent stack-frame leases. Data pages begin zero
in this construction operation, stronger than an ordinary ledger grant.

## Trusted limits and deferred work

The constructor's C++ arena view, physical-to-virtual correspondence, exclusive WB
mapping and lifetimes are trusted bootstrap adapter preconditions. C++ private
fields do not prevent arbitrary malicious trusted C++ from accessing backing RAM.
Seal prevents mutation through this API; it does not change CPU page permissions.
Validation rereads complete table bytes and current ledger ownership. Encoded
addresses are never used to dereference arbitrary memory by the independent reader.

The fixed RID/format profile expresses intended construction for the known bus0
fixture. It does not prove a live PCI identity, requester coverage, firmware facts,
cache visibility, interrupt remapping, or hardware capabilities. Those require a
future guest adapter and separately reviewed activation protocol. The current
private builder has no device-publication path at all. IV remains0, so there is
no interrupt-isolation claim. No software requester/IOVA bound is represented as
containment of a misbehaving peripheral.

Future CPU-only guest tests must bind actual current arena/identity facts, preserve
all existing gates, and undergo independent review before main integration. The
observed QEMU deviations preclude using it unmodified as a normative denial oracle
for the affected cases. No emulator patch, alternate device mechanism or activation
has been attempted here.
