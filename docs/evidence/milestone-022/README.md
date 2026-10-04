# Milestone022 evidence and integration

The bounded copied ordinary method-parameter compiler slice and real std::array
exchange passed complete release/fatal host ASan/UBSan compiler gates, independent
source/IR/native ABI review, parent adoption/rebuild and fresh make test. All 166
actual existing emulator modes passed on the reviewed M022 compiler, followed by
normal BIOS/UEFI restoration. All 368 source and 236 external input records were
unchanged through integration; independent receipt/live-image validation and all
168 retained validator replays passed. This adds no kernel/hardware feature.

## Receipt map

- candidate/evidence/INTEGRATION-SEAL.json, INTEGRATION-HANDOVER.md and
  change-manifest-final.json preserve the original 28-path source delta and pins.
- candidate/evidence/VERIFICATION.md and DEVELOPMENT-CORRECTIONS.md record finite
  counts, exact full gates, grammar revert, preserved failures and resource limits.
- candidate/review/independent-method-review/REVIEW.md and addendum/ADDENDUM.md
  preserve independent source, malformed IR, handwritten native ABI and diagnostic-
  specific fixture corrections. Original reviews are not relabeled as integration.
- candidate/build-receipts/ preserves historical build/test failure and success
  logs. This deliberate destination avoids the source archive's build exclusion.
- candidate/tmp/ preserves the qualified-self grammar control source;
  candidate/baseline/library/ is the intentional frozen M021 old-input differential
  library, not a new current library or downloaded third-party reference.
- parent/ retains the fresh rebuild, adoption, aggregate and source-pin receipts.
- kernel-gates/ retains all eligible full166 run text, raw trace/provenance/stack
  records, exact commands, statuses, input/hash/mode manifests and restoration.
- kernel-preparation/ retains the initial scope-only preflight mismatch and fix.
- kernel-review/ retains independent final receipt/live-image review and exact
  original-validator replay of all166 modes plus two normal restorations.
- curation-manifest.json maps each included text to its exact original path,
  size, mode and SHA256. No normalization is performed. Historical pending states
  and failures remain historical; current acceptance is stated separately here.
- omitted-generated-products.json inventories every scoped generated/binary
  product left unchanged outside source. Retained archive JSON receipts describe
  successful generated output member/mode/hash inventories.
- documentation-finalization.json identifies later documentation-only changes
  against all 368 parent-tested source inputs; implementation/test/fixture changes
  are zero. candidate-source/ preserves pre-integration overview/contract text.

## Failures and limits

The first concurrent sanitized stress SIGKILL remains unclassified; exact isolated
input replay and complete28/28 stress success are separate retained evidence.
The temporary bare-array parser exception was reverted to byte-identical M021
parser grammar. Two original source-test gaps are not credited as the intended
semantic checks; the independent mutref/existing-inspect addendum closes them.

The integration runner's unguarded failure-sealing path did not trigger. The
preflight inventory mismatch happened before emulator execution and was corrected
without changing test assertions. Existing AMD-Vi whole-run criteria remain false;
coverage uses only its reviewed bounded stopped-CPU CTRL witness. Finite passing
tests and hashes are neither general safety/resource proofs nor signed execution
attestations. No active DMA, physical qualification or complete ecosystem claim.

Final raw/canonical archive, actual Git tree/blob and independent archive-review
receipts live outside source to avoid recursive self-pinning. The reviewed
M020/M021 tree-only approach uses unchanged 1 GiB payload / 16 MiB member / 512 MiB
address-space caps, 1 GiB free reserve for active work and 512 MiB hard floor.
No full JSON-export claim or spool is created. The sole existing 0700 test script
keeps live/raw permissions; canonical Git representation maps it to0755 with an
explicit new M022 note. M019/M020/M021 archives and earlier evidence are immutable.
No binary archive, downloaded reference extract, secret or rejected carrier helper
is copied into source. No image operation, network/authentication or publication
is performed by the finalizer.
