# Independent review: dormant AMD table guest integration

Date: 2026-10-03. Final disposition: PASS for the four new CPU-only guest construction/validation gates. No remaining blocking defect was found in this scoped integration. The historical 166-mode combined regression and parent aggregate/milestone acceptance are separate; image ownership was released to the implementation owner after the independent four passed and normal-image restoration was verified.

## Exact scope and result

The previously reviewed constructor now operates on real PageLeases in ordinary guest RAM, under the restored kernel CPU root after an existing precisely validated ring-3 return. It never installs these bytes in an IOMMU. The four independently executed modes were:

- runtime-table-readback: all 256 DTEs and 512 leaves independently decoded; canonical fixed format validated; five frames canceled, simultaneously reacquired and checked zero. Final retained pool/pin pages: 0.
- runtime-table-reject: six actual byte corruptions separately rejected by both constructor validation and independent decoding, with a separately checked restoration after each. Five malformed request/owner/width inputs reject without changing allocation accounting. Final retained pages: 0.
- runtime-table-exhaust: fragmented DTE backing, insufficient free frames and insufficient ledger slots reject while unrelated stack/reservation leases remain valid. A subsequent complete construction succeeds and cancels. Final retained pages: 0.
- runtime-table-quarantine: after the exact known bounds fault in service slot 1 and kernel-root restoration, one deliberately failed scrub quarantines the two DTE pages; the other three never-published pages scrub/release. Slot 1 is retired and recreated with incarnation 2 to 4; stale constructor validation/cancellation reject for old and current owners, while a fresh current-owner loan/cancel succeeds. A clean program executes in the restarted slot. Final pool/pinned/quarantined count: 2/2/2 in one entry.

Each actual smoke wrapper returned 0 after requiring the expected guest exit and exact serial/metadata validation. All four archived stack calculations are 13,136 bytes including a 1,024-byte synchronous-fault reserve, against the unchanged 16,384-byte kernel stack: 3,248 bytes remain. The unchanged arena is 1 MiB; the runtime pool is 16 frames; the two user stacks own eight frames; construction uses at most five additional frames and three ledger entries.

These are CPU_BYTES and SOFTWARE_MODEL results. No hardware DMA, IOMMU containment, interrupt isolation, device identity grant, engine activation, cache/invalidation protocol or physical AMD qualification was tested. The ordinary OVMF boot and existing read-only ACPI/PCI discovery remain part of the inherited fixture. No AMD-Vi or NVMe device was added for these tests, and no new controller/IOMMU register or BME operation was introduced.

## Review findings and corrections

1. Stack lifetime/bounding: the initial inherited ACPI/PCI call chain retained a 3,504-byte parser frame across a 10,736-byte PCI frame, close to the 16 KiB limit after subordinate calls. The new TABLES-only adapter now ends parsing before PCI enumeration using the existing phase-separation pattern. Historical non-table branches are unchanged. The final bound includes both inherited discovery and new runtime paths, not merely individual table-function frames.
2. Stack regression defect: the initial checker accepted removal of the PageTables::verify wrapper because a lambda signature still matched the same substring. This was reproduced by its self-test. The owner now selects non-lambda wrapper frames separately. The checker also rejects a linked prepare_table_acpi-to-discover_pci edge, with a negative mutation control guarding against reintroducing nested frames. All corrected stack controls pass.
3. Stale-owner coverage: quarantine restart now explicitly rejects cancellation through the stale constructor with the new slot-1 owner, in addition to old-owner cancellation and new-owner validation rejection. A distinct fresh grant/cancel verifies useful authority for the new incarnation rather than accepting blanket refusal as success.
4. Corruption evidence: the sixth mutation was changed to actual reserved leaf bit 52, matching the documented test. Every case now has an ordered rejection record and a distinct restoration record from both validators. Missing/duplicated outcomes, altered flags/indexes, reorderings and success markers inserted while bytes are corrupt reject. A previous successful seal is expressly not a validation certificate for subsequently changed bytes.

The earlier isolated-host privacy-test finding remains fixed: well-formed member-pointer negative probes are paired with identical positive public-mutant compilations. No production pointer/authority escape was reproduced in either review.

## Ownership, authority and lifetime audit

The imported constructor and decoder are byte-identical to the accepted isolated versions. The only PinLedger API delta remains its concrete DormantTables forward declaration and private friend declaration. Public production methods expose no address, view, callback, PageLease, publication or hardware-completion method to a service.

The ledger and typed constructor have static kernel-session storage. The adapter uses only the existing owned pool mapping at arena+0xc0000, with a 32-bit address bound because the allocation is below 4 GiB. Actual current registry incarnation, ledger generations/epoch, reserved states, page addresses, role disjointness and DTE contiguity are checked by the reviewed core. The scrub callback requires the kernel root, no active user domain, an aligned complete pool page, and zero-byte readback before release. Quarantine remains in the permanent ledger through service retirement/restart and final cleanup; destruction does not recycle it.

The kernel first receives the old clean42 return under unchanged CPL/root/stack/exact-PC checks. Table work runs only in its trusted continuation. It subsequently contains only the already-recognized bounds trap. The quarantine mode reuses the old runtime's same-slot restart mechanism: entry slots are exactly 0,1,0,1, with corresponding private roots and stack ranges, rather than silently running the replacement in slot 0.

The compile-selected inspector returns small views of leased bytes to the kernel's independent decoder. It is not bound to service-visible state. Ordinary preprocessing contains no inspector declaration, ordinary inclusion is rejected, and an independently compiled ordinary pin-runtime object contains no dormant constructor/decoder/inspector symbols. The restored ordinary image after each actual mode also contains no dormant symbols or TABLE receipt bytes. New dormant-function frames are at most 416/736/464/224 bytes by mode, respectively; no full table snapshot is copied onto the kernel stack.

PAT0=WB is checked by inherited ACPI admission. Effective cache/MTRR state, physical-to-virtual correspondence, exclusive external mappings and backing lifetimes remain disclosed trusted bootstrap preconditions. The fixed RID0x10 is a format fixture, not discovered live requester authority. Those limits must remain in future integration/activation work.

## Independently reproduced checks

- Main integrated host runner: 27 expected commands each in ordinary and fatal ASan/UBSan mode, including ownership, independent decoder, limited generations, production API, privacy mutants and production inspector-absence controls. Results: 92,306 ownership/byte checks; 164,313 decoder checks; generation-limit 3 permits three complete constructions then rejects 17 more. Leak detection alone is disabled for the environment limitation.
- Additional compile controls: ordinary/UEFI-only/testing-only/testing-zero inspector configurations reject; explicit test configuration compiles. Ordinary pin-runtime object symbol inspection excludes the dormant implementation and inspector.
- Strict serial controls: 4 positives/607 negatives, independently passed under ordinary and optimized Python. The inherited runtime validator additionally passes 15 positives/793 negatives.
- Stack controls: 2 positives/45 negatives under ordinary and optimized Python.
- Actual final four: independently executed sequentially on the frozen merged sources from 17:26:39 to 17:27:10 UTC. All passed, with exact per-mode log/metadata/.su/disassembly/stack receipts. Archived serial records received additional separate checks for ring-3 slots/roots/stacks, exact accounting, corruption/restoration order and incarnation 2-to-4 restart.
- All 54 archived receipt hashes were verified. All 302 selected source/build/test inputs and 125 external tool/firmware/library inputs remained unchanged across the four runs. Ordinary images were restored and checked after every mode.

The host assertion counts include repeated byte checks and are not independent-case counts or a safety proof. Guest software-model rejection does not establish that an IOMMU or peripheral would reject the same transaction. QEMU's known table-length, high-IOVA, final-presence and path-permission deviations remain outside any containment claim.

## Source and tool pins

- Exact 224-file kernel review manifest: aurora-m019-development/kernel-review-inputs.json; SHA256 e0de2883c7f0cd7f8df351bdc09207ba6017e4e6467f032cc30a51b1ddb23c55. Every entry matched, including root Makefile.
- The parent-approved nine-file XFS integration delta was read from docs/evidence/milestone-019/xfs-geometry/integration-delta.json and all nine final hashes verified before execution. No broad Makefile exception or unexplained runtime/build delta was allowed.
- Merged actual-run source manifest: 07e5e9b59c8b39635f63809518cd4615cf63428f558bf0fddfe2c1adf16271f4.
- Immutable compiler: /tmp/aurora-resource-main-compiler-frozen, SHA256 14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980.
- Constructor: 26a24e0bece02830c796dc107d5ade6be13eb955cd152526ba97422a580742e5. Decoder: 1685d114a06496733bc571b0a2c982b54cfb21dbe7d5815618e037c18cf21a91.
- QEMU 10.0.13 executable: d3c1a558ad220e77a4412048c8d96b44f8c2b41c7ad2a4ecfe522a4b122fe067. Packaged OVMF: 14954040cc754ade0c625ac3470ea46d4c14318b5b1396de4ef77090203d76db.
- G++ 14.2.0-19; GNU binutils 2.44; Python 3.12.14. Complete external hashes and versions are in the receipts.

The previous isolated review's main-unchanged statement applies only to its earlier interval. The authorized kernel/XFS integration changed main afterward. This review's unchanged-input statement applies specifically to the frozen integrated four-run interval, not to all activity since the isolated review.

## Commands and evidence

Working directory: /workspace/scratch/48c5de6446f8/aurora.

Hosted: python3 scripts/kernel-dormant-tests.py <fresh-output-directory>; repeat with SANITIZE=1. Serial and stack controls: python3 tests/kernel-uefi-tables-smoke.py and python3 tests/kernel-uefi-tables-stack.py --self-test, each also under python3 -O.

Actual four: ./scripts/kernel-uefi-smoke.sh followed in turn by runtime-table-readback, runtime-table-reject, runtime-table-exhaust and runtime-table-quarantine, using:
AURORAC=/tmp/aurora-resource-main-compiler-frozen
QEMU=/tmp/aurora-qemu/root/usr/bin/qemu-system-x86_64
QEMU_DATA=/tmp/aurora-qemu/firmware
LD_LIBRARY_PATH=/tmp/aurora-qemu/root/usr/lib/x86_64-linux-gnu
OVMF=/tmp/aurora-ovmf/root/usr/share/ovmf/OVMF.fd

Complete runner and immutable results: /tmp/aurora-amd310-guest-review/actual-final-four. The reusable run-independent-four.py preserves the exact commands, environment, inputs, per-mode artifacts and restoration checks. Integrated hosted results: /tmp/aurora-amd310-guest-review/host-final-normal and host-final-sanitized. This report is separate from the earlier isolated report at /tmp/aurora-amd310-independent-review/REVIEW.md.
