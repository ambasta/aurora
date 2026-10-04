# Independent page pin-ledger lifetime review

Date: 2026-10-03. Working tree: `/workspace/scratch/48c5de6446f8/aurora`.

## Status

PASS for the scoped CPU-only ownership slice. Source review found no blocking
defect. Clean normal and fatal ASan/UBSan hosted runs and all four new actual
QEMU modes passed on the frozen final compiler. The whole milestone still
requires the kernel owner’s full 158 historical plus four new actual-mode suite;
this report does not claim that aggregate. Earlier development receipts are
kept separate from these final independent receipts.

The review did not modify kernel/compiler source or the unrelated interrupted
mutable-byte candidate. Shared image builds remain under the kernel owner's
exclusive coordination. The full 158 historical plus four new actual-mode suite
belongs to that owner; this review does not substitute four new modes for it.

## Reviewed ownership and authority

- `PinLedger::grant` acquires actual move-only `PageLease` objects from one
  `PhysicalPages` instance and moves them into private entries. It does not
  import an arbitrary lease, accept a caller-supplied physical frame, or expose
  a frame address through its handle. Four entries hold at most two pages each.
- `PinHandle` has a private constructor and binds ledger address, nonzero epoch,
  slot and generation. Cancel also validates both recorded and supplied owner
  handles in the same current registry. A copied intent handle is not a lease;
  it cannot double-release or choose completion identity.
- Static runtime storage keeps the ledger, pool and domain registry alive
  across the controlled service death, peer progress and same-service-slot
  restart phases.
  Neither ledger destruction nor `PageLease` destruction releases frames.
- A reserved entry scrubs and verifies every complete page before releasing
  its first page. Partial allocation failure uses the same scrub path for only
  the acquired prefix. Scrub failure permanently quarantines the whole retained
  entry, including any page scrubbed successfully earlier in that attempt.
- Quarantine has no transition back to reserved or empty. Cancellation, live
  borrower disposal, dead-owner reaping, late success, copied handles and owner
  rebirth cannot release it. Other owners can still use disjoint pool frames.
- Generation-exhausted slots are retired rather than wrapped. Production uses
  `UINT64_MAX`; an explicit test-only reduced bound exercises the exhaustion
  transition. Ledger epochs, allocator epochs/generations and registry stamps
  also have no wrap path in source. Their full 64-bit exhaustion is not reached
  dynamically in this review.
- Mutation re-entry from the synchronous scrub callback is rejected. This is
  a single-CPU trusted callback contract, not a locking or SMP implementation.
- The runtime checks exact compiler return/fault sites, selectors and flags,
  entry-stack extent, current domain and CR3 before accepting a result, then
  restores the kernel root before pin operations. Unknown fault origins stop
  the runtime. The scalar `42` selects no owner, frame, operation or completion;
  those are fixed in the privileged fixture.
- Production pin builds have no publication, completion or uncertainty-injection
  API. Only the explicitly marked hosted/fault builds compile injection, whose
  sole effect is loss of release authority. Build configuration rejects
  `AURORA_PIN_LEDGER_TESTING=0`, a small generation bound without testing, and
  zero/negative generation bounds.

## Important trusted limits

The allocator exclusively owns its backing arena. Its lifetime, its backing
memory and the callback context must exceed all retained leases. C++ references
cannot enforce that external storage contract. Rebuilding another allocator
over the same physical range can itself create aliases before the ledger sees
the misuse. Later validation poisons the ledger and refuses to release another
allocator's allocation; it does not revoke an independently created alias.
The static runtime satisfies the contract in this fixture.

The revised actual fault fixture disposes quarantined service slot 1, observes
peer slot 0 progress, retires both, recreates an inactive bounds-image placeholder
in slot 0, and executes the existing distinct clean image in restarted slot 1.
Its old/new incarnation records bind the original grant and restored new return.
The new domain cannot cancel the old token, and the old domain cannot cancel a
fresh grant. No page range, code image, root count or stack bound is expanded.
Final independent actual execution passed this enhancement: original service
incarnation 2 and restarted incarnation 4 were recorded, its final execution
was in slot 1 under the slot-1 root, and final accounting retained exactly two
quarantined pages. Earlier actual four-mode development receipts exercised only
peer-slot reuse and are not used to prove the enhanced same-service restart.

No device register write, DMA mapping/publication, DMA completion, IOMMU command,
cache-coherency protocol, bus-master enable or NVMe queue operation is introduced
or tested. No physical hardware was changed. The result remains a trusted C++
bootstrap mechanism, without a general user service API or a proof of whole-OS
or language memory safety.

## Independent reproduction

Private output directory: `/workspace/scratch/48c5de6446f8/pin-lifetime-review`.
`private-hosted-tests.sh` is a copy of the repository wrapper with only working
directory/output paths redirected. Toolchain: GCC 14.2.0, Python 3.12.14.

Initial normal and ASan/UBSan hosted runs passed full and reduced-bound 3 cases,
production API absence, and the then-present invalid-configuration controls.
The final policy/test wrapper changed during that initial run, so it is not
counted as final frozen-source evidence. Fresh final normal and fatal ASan/UBSan
runs passed 165 checks at the production generation limit and 294 checks at
bound 3, including seven incarnation-accessor checks. Production API absence
and all four invalid build configurations passed. Before/after hashes of all
reviewed source inputs were identical. See `hosted-final.log`,
`sanitized-final.log`, and `hosted-frozen-inputs.json`.

The exact receipt validator passes with regular Python and `python3 -O`:
4 pin positives and 236 negative controls, layered over 15 existing runtime
positives and 793 negatives. Checks remain enabled under optimized Python. An additional independent set of
24 transcript mutations rejects missing/duplicate/misordered owner and restart
records, oversized or replayed incarnations, a peer-slot restart substituted for
the service, and bad fault/restart vector, error, PC, CPL, CR3 or frame. These
controls overlap existing negative coverage and are not a disjoint safety count.
The pin validator requires exact ordered event/accounting tuples, a kernel root
for each row, exact placement after restored authority, unique completion, and
the full underlying metadata/origin checks. Only the fault mode permits final
retained count 2; all historical runtime modes retain default count 0.

## Pure prerequisite model cross-check

The isolated `/workspace/scratch/48c5de6446f8/aurora-dma-candidate` model is not
included in the kernel. Both normal and optimized Python reproduced:

- 16,166 checks for generation limits 1 through 8; reachable-state counts
  10, 23, 41, 63, 90, 121, 157 and 197.
- All three premature-release mutation controls rejected.
- The independent event-history oracle reproduced history-state counts
  11, 25, 43, 67, 101, 149, 215 and 305, with 9,247 edges at bound 8.
- Both stronger history-oracle mutants were caught and cross-broker replay
  rejected.
- The original read-only observation receipt exists, matches recorded SHA256
  `8fc5ca85ece4b968d5ec8aa2c6a8136436ad9453a45e7bf5af6fbbfadbfc5111`, and contains
  every extracted cold-controller/IOMMU record.

The model's completion objects are hypothetical trusted observations, not
unforgeable hardware evidence. It assumes exclusive abstract frames and zeroed
reserve state. The real no-publication ledger may own dirty bytes on grant and
scrubs before release; it is not a DMA-ready grant and does not implement the
model's installation, quiescence, invalidation or visibility stages. Future
activation needs its own separately reviewed adapter and evidence.

## Evidence identity

`review-source-sha256.json` binds final reviewed kernel/build/validator inputs;
`model-source-sha256.json` binds isolated model inputs.

Final actual evidence is in `actual-final-four/`, with one directory per mode.
Each preserves the exact pre-execution EFI image, ELF/binary payload, generated
metadata, stack-usage report, raw serial receipt, QEMU exit status and arguments,
wrapper output, and optimized-Python validator result. `summary.json` contains
artifact hashes. `source-before.json` and `source-after.json` are identical.
Each QEMU process exited 33 and both ordinary and optimized validators passed.
The official wrapper rebuilt normal mode after each run; final normal image
validation passed and its EFI bytes are preserved as `normal-restored.EFI`.

Commands used the official `scripts/kernel-uefi-smoke.sh MODE` for all four modes,
with a private QEMU wrapper that only copies current artifacts and records the
underlying process exit status before returning it unchanged. The configured
compiler was `/tmp/aurora-resource-main-compiler-frozen`, checked before execution.
Tool versions: GCC 14.2.0, Python 3.12.14, QEMU 10.0.13 Debian.

Key final hashes:

- Compiler: `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`
- QEMU executable: `d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067`
- OVMF: `14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db`
- Pin ledger: `5cf4585f517cafb5466c3624ae0c7ec6c000291eb6cf81e0e9999274932e1249`
- Domain policy: `396968cabb276213ef06cbe16793d23fac4766384bc6d0c7883cf55093f0d326`
- Pin runtime: `43c5a45e5fa2716d2bfdc01547786d08a1fd1c6f8dca09a6588a7272adecd481`
- UEFI runtime: `7cf4266309ac9f3ff504b5dad9de3345e465bec0307459aa8cbf55123fcb451f`
- Hosted test: `3d9a4fbec410590ac71b942cba12d1474a9186741fec15134b839a7fa6986bd9`
- Pin receipt validator: `6608955d85117650790472be71143a86e33ba7b5bf377735f46665bf62e6dcc4`
- Runtime receipt validator: `49a670835913d30c0b09ff9c13aaefb7d58e87da4539c27cd97420e163586813`
