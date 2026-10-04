# Independent dormant AMD 3.10 construction review

Date: 2026-10-03. Scope: ordinary CPU construction and validation of never-published leased RAM. No main edits, publication, emulator execution, IOMMU/controller access, BME/engine activation, DMA transaction, physical-device test, or revision 3.11 access.

## Result

The corrected construction-only candidate passes independent review. No production construction/ownership defect was found within the documented trusted single-CPU arena/lifetime contract. One reproduced regression-test defect (R1) was fixed by the owner and independently reverified; no construction-only review blocker remains.

This is review acceptance of a bounded CPU-memory constructor only. It is not hardware isolation, requester containment, activation approval, or main-integration clearance.

## Finding R1: false-confidence method-privacy negatives (fixed and reverified)

Original `normative/run-tests.py:40-43` generates `return t.dte_word;` and `return t.page;`. Neither is a valid way to use a non-static member function even when public. Compiler logs contain member-function conversion errors instead of access-control failures. A private-copy mutant inserting `public:` immediately after the `DormantTables` class declaration still fails both original negatives.

Corrected invocations `return t.dte_word(0,0);` and `return t.page(0);` fail against the frozen private header and compile against the public mutant. These four outcomes establish the defect independently; see `reviewer-commands.json` and the named `page-*`/`dte_word-*` logs. The production methods really are private. This is a verification gap, not a demonstrated pointer/authority escape.

Requested correction: use type-correct calls/member pointers for every privacy negative, and require the same source to compile against an isolated deliberately public copy. Keep the original receipts as historical wrong-reason evidence. The construction owner implemented this correction; no reviewer production edits were made. The final runner uses identical well-formed member-pointer expressions, exact exit status 1 plus the expected private-access diagnostic for rejection, and successful public-mutant compilations for all six members. The full corrected 33-command suite independently passed in `host-corrected-1`.

## Source identity

Reviewed root: `/workspace/scratch/48c5de6446f8/aurora-dma-tables-candidate/normative`.

- Original frozen manifest SHA-256: `ffe9a71ca7404f267c95bf3bd40e425421019bef071b6e83992cd205035513b0`.
- All 14 manifest-listed sources matched before and after original review.
- `include/dormant-tables.hpp`: `26a24e0bece02830c796dc107d5ade6be13eb955cd152526ba97422a580742e5`.
- `include/pin-ledger.hpp`: `ddd49d5ebe1c9781d99b104d66dbbee87cbb50807a6c4df58d5f2600bdbb8174`.
- Verified delta from baseline is exactly the `DormantTables` forward declaration and friend declaration. Baseline `pages.hpp`, `domain-policy.hpp`, and `pin-ledger.hpp` match the current main copies.
- Parent-provided main tree identity: `b7ae932589b7b236aff9f1fc6d02714de33becf0`; this exported filesystem is not a Git checkout, so that tree ID was not locally Git-verified. Instead 13,302 main files were SHA-256 compared, unchanged. Before/after manifest SHA: `e92c249de21ad38d74423b77d6874e296e86e820ab99c872b3856b7bdc8c21de`.
- Supplied AMD 48882-PUB revision 3.10 PDF: 310 pages, SHA `cd7559334b3f46a72d56e9f2fac786fcbf5d6a2c41e7770a46fcacc080bc8a12`. Relevant pages read directly: 63, 71-75, 81-85, 208; page 82 rendered and visually inspected. PDF/excerpts/render remain outside the repository.
- Pinned QEMU commit supplied by source provenance: `98f88efe8f07067667b8d9b1a5ce9551d34036c1`; local source hashes reverified: C `7dbe81fc13a533c265683ee70cd616ccc00e46e890b17dd0113e79d5f9fa52d3`, H `f19a9e828d3fce319099cf3e4800818a824c4b9ae8d7913eb33778b92d87aff5`.

## Reviewed invariants

- Authority and lifetime: production methods return only booleans, with no span/address/lease/callback/export/completion/publication operation. The friend is the concrete constructor type. References and backing mapping still rely on trusted C++ lifetime/exclusive-mapping preconditions; `private` does not defend against arbitrary malicious trusted C++ or raw backing-memory writes.
- Ownership: live domain incarnations are checked through `DomainRegistry`; handles are matched by actual ledger epoch, slot, generation and owner. All three entries must remain reserved. Actual lease addresses, page-width intervals, disjoint roles and the physically contiguous DTE pair are revalidated before encoding and on validation.
- Fixed budget: two contiguous DTE pages, one root and one/two data pages consume three ledger entries/four or five frames. Fragmented first-pair allocation rejects and rolls back; no expanded search or hidden budget is assumed. Separate stack leases remain untouched.
- Representation: all 256 DTEs and 512 leaves are explicitly little-endian and read back exactly. Denied entries are canonical V/TV=1, Mode=0, no root/permissions, DomainID=0. The fixed RID 0x10 has Mode=1, parent IR/IW, root binding and DomainID=1. Selected leaves contain only owned aligned 52-bit-or-narrower addresses, PR and requested IR/IW. All other leaves and unsupported fields are zero.
- Sealing: repeat prepare rejects; validate checks current ownership and every table byte. Every one-bit corruption of the actual constructed 12 KiB was independently tested against production validation. Seal means API construction is closed; it does not set CPU page permissions, flush caches, or prevent external backing mutation.
- Rollback/quarantine: only never-published pages are canceled. Scrub failure retains the affected ledger entry; independent never-published groups can release. A dropped constructor releases nothing. Dead borrowers can be reaped by the permanent ledger; quarantined groups remain retained. A stale constructor cannot cancel a newer allocation even for the same still-live owner. During scrub callbacks, table/ledger mutation reentry rejects.
- Decoder: exact profile validation is intentionally stricter than architectural ignored-bit semantics. Encoded PAs are compared to trusted role descriptions and never dereferenced. Whole-interval software queries reject empty, overflowing, high-IOVA, absent, wrong-RID and insufficient-rights cases. The reader is a software model, not a DMA transaction.

## Specification and QEMU comparison

AMD 3.10 sections 2.2.2/2.2.2.1 confirm dense 32-byte entries, contiguous 4 KiB-aligned/multiple device-table storage, and out-of-range requester rejection when the IOMMU is enabled. The 256-entry profile therefore needs 8 KiB; section 3.4.1 defines the corresponding size units. V=0 bypasses ordinary translation. V/TV=1, Mode=0, IR/IW=0 is the intended ordinary-memory denial. IV stays zero, so no interrupt-isolation claim is admissible. Distinct roots/modes use distinct DomainIDs.

Sections 2.2.3 and the page-entry definitions confirm level-one IOVA width, 4 KiB leaves, address fields, presence, descending levels and cumulative path permissions. A PR-clear entry may architecturally have ignored payload; canonical-zero holes are an explicit stricter profile choice.

Read-only review of the pinned QEMU C source independently confirmed: `amdvi_get_dte` at 867-885 does not apply the computed table length; the walker at 947-979 omits upper-IOVA rejection and final-leaf presence validation and returns leaf permissions without a full path intersection. Cached translations can retain those broad rights. Disabled translation and V=0 are permissive. These differences prohibit treating unmodified pinned QEMU as a normative denial oracle. No emulator or active-device claim follows from the reproduced source-derived model.

## Reproduced verification

Compiler: G++ Debian 14.2.0-19. C++23, `-O1 -g -Wall -Wextra -Werror`. Sanitized runs add `-fsanitize=address,undefined -fno-sanitize-recover=all`; only leak detection is disabled (`ASAN_OPTIONS=detect_leaks=0`).

1. From the normative directory: `python3 run-tests.py /tmp/aurora-amd310-independent-review/host-reproduction`. All 27 expected statuses reproduced. Execution logs match author `host-final-1`: 92,306 ownership/byte checks, 164,313 decoder checks, generation-limit-3 results and production API checks. Those two original privacy negatives retain the R1 limitation.
2. Reviewer-authored `/tmp/aurora-amd310-independent-review/reviewer-tests.cpp`, SHA `5e7522b378d8625288c308f57c3d35cf3ce6e0d4fe8784cba577578327487e17`, compiled/executed ordinarily and with fatal ASan/UBSan: 2,178,006 assertions each. Coverage includes actual encoder whole-page width boundaries for all widths 32-52; first over-width page; malformed arenas; 98,304 actual table-bit corruptions; every one of 512 leaf positions in RO/RW mode; unaligned host byte storage; stale generation replacement; all five cancellation scrub-failure positions; callback reentrancy; data zeroing; independent stack sentinels. Counts include repeated byte/sentinel assertions and are not a safety proof or disjoint test-case count.
3. `python3 .../qemu_deny_model.py` and `python3 -O .../qemu_deny_model.py`: 309 checks each; software source model only.
4. Exact reviewer commands/statuses in `reviewer-commands.json` (SHA `83aa97968f98c52f386b2ed288ce5ac62d59b811dac8bdc4d0fb1becf9878121`); summary in `reviewer-summary.json`. The full runner is `verify-review.py`.

## Remaining gates and limits

The fixed RID and physical width are trusted fixture inputs, not observations of current live PCI/IOMMU identity/capabilities. A later guest adapter must bind actual arena/identity/cache facts and keep pool/registry/ledger/backing alive for every reserved/quarantined page. It must preserve existing gate coverage and undergo independent review before any main integration. No `make test`, QEMU guest CPU gate, hardware fault observation, coherency/invalidation protocol or physical AMD qualification was performed in this construction-only review. Nothing here permits activation, hardware containment claims or replacement of these lifetime/ownership preconditions.

## Final corrected disposition and provenance

R1 is closed. All 33 corrected host commands passed independently, with unchanged before/after full candidate inputs; `privacy_only` is false. All six deliberately public controls compile, and all six real-private equivalents fail with the access-control diagnostic and exact expected status. The ordinary/sanitized executable outputs remain equal to the original reproduced results.

Final frozen-source manifest SHA: `b9e27e11c8a5443a78b1dea0b5895106b92823c4e6364d795a2f992825635a2c`. Runner SHA: `46fad4c5b2586f94396651c73ec245db56a7f936331b114f4f1c9742acc8ebd1`. Final README SHA: `3a47effaa6307c5c28560805600ba8ec59a7376616a0b06243e8bccb9b30d104`. Only README, runner and manifest changed from the reviewed original; every production/test C++ file remains identical. See `correction-delta.json`.

Final reproduction command: from the normative directory, `python3 run-tests.py /tmp/aurora-amd310-independent-review/host-corrected-1`. Its `commands.json`, `summary.json` and full `inputs-before.json`/`inputs-after.json` are the final independent receipts. The author run at `host-final-2` preceded a documentation-only README wording clarification; the independent final run includes that final README.

Final main comparison: all 13,302 files remain byte-identical to the initial review snapshot (`main-final.json` equals `main-before.json`). No reviewer or owner production/main-source correction was necessary. The bounded guest CPU construction/readback proposal may proceed through separate source/integration clearance; all hardware and activation exclusions above remain unchanged.
