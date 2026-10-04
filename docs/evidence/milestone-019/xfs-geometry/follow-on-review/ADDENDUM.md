# XFS geometry post-review recipe, CLI and documentation delta

Result: **PASS after one documentation correction.** This is a separate follow-on
review; the earlier independent report did not cover these final metadata and
recipe changes. No runtime implementation change was required or found.

## Reviewed final identities

- Geometry module, unchanged from the earlier review:
  `c67c03928e0d4cf5896178906bd447523ec15b57cc95c4ade8b8330305a77864`
- Old probe, unchanged:
  `9474dceea9c3dda66d5566396480e88979c6ea28c8d857b944f24e2e70603284`
- Final author test script:
  `fe375d75a7726a538f404f5d2b3f4240065f7d41c3334c104b535b5db2e1c95c`
- Corrected contract:
  `845322d4456762c5f71800867ece9b65c68b9f21a01e75717a77e0481a7a2def`
- Final111-file candidate manifest:
  `e2f8e6b25a052470ec329c9fdb2f0866ec1a8aea9d75bee3537c9598fa75010a`
- Final9-file integration delta:
  `bb8e8968ea0d2932880c9ec39ed94c0df0994b03990a7f8dd2af71416b4b531b`

All111 candidate entries and all9 delta entries match their actual bytes. The
9-file delta exactly equals the changes from the104-file copied baseline; no
baseline file is deleted. Runtime library dependencies, compiler implementation
and the canonical fixture remain unchanged.

## Exact integration delta

Two existing files change:

1. `compiler/Makefile`: adds `XFS_GEOMETRY_TEST_FLAGS`, registers the new geometry
   test with mutation controls in the aggregate compiler test, and adds the
   explicit `test-xfs-geometry` target. No compiler implementation is changed.
2. `library/README.md`: describes the bounded geometry API and its limitations;
   corrects obsolete M013/M014/M015 acceptance-pending language to the already
   recorded checkpoints. Final geometry integration remains explicitly pending.

Seven files are new relative to the baseline:

- `library/fs/xfs_geometry.au` (already independently reviewed, unchanged)
- `tests/compiler/xfs_geometry.py`
- `library/examples/xfs_geometry.au`
- `docs/xfs-geometry-contract.md`
- `docs/xfs-geometry-proposal.md`
- `docs/xfs-observed-fixture-facts.json`
- `docs/xfs-source-check.json`

The original proposal hash is unchanged. The observed-facts JSON is byte-identical
to its proposal source. The example's512 literal bytes independently hash to the
canonical raw fixture identity55ad8219…c6586. Primary-source corroboration agrees
with the pinned Linux blobs independently retrieved in the original review.

## Finding and correction

The initial final contract claimed that all17 author negative fixtures exercised
both absent and existing output artifacts. The actual `Suite.reject` always
creates an existing sentinel and tests that mode only. This was an evidence
wording error, not a runtime/compiler defect.

The author corrected the contract to state existing-output preservation and
separately attribute absent/existing coverage to the independent8-fixture×2-mode
suite. The correction changed only the contract and its manifest entries; no
runtime or test code changed. The corrected contract and refreshed manifests
were verified. No remaining blocking issue was found in this delta.

## New CLI and recipe controls actually executed

The optional `--compiler-sha256` argument validates64 lowercase hexadecimal
characters, compares the supplied value with the actual compiler bytes, records
the actual hash whether or not a pin is supplied, and checks compiler/input
stability again in the final receipt. No hardcoded compiler allowlist remains.
`--sanitized-compiler` retains the existing explicit ASan environment check and
omits only the compiler address-space limit needed for shadow memory.

Fresh checks, using `PYTHONDONTWRITEBYTECODE=1` and separate reviewer output paths:

| Control | Observed result |
|---|---|
| Correct release pin, selected preserved real header | exit0,1 header/43 raw outputs, explicit and actual pin recorded |
| Correct instrumented pin with explicit ASan/UBSan environment | exit0, same selected header/43 outputs |
| Omitted optional pin | exit0, explicit pin null, actual compiler hash recorded |
| Wrong all-zero64-digit pin | exit1, exact identity-mismatch diagnostic; no artifact directory or native execution |
| Actual `make -C compiler test-xfs-geometry` with correct pin and selected header | exit0,1 header plus51 detected mutation controls |
| Same Make target with wrong pin | Make exit2; identity mismatch propagated; no artifact directory |
| Aggregate compiler `make -n test` | exit0; new geometry hook appears with passed flags and mutation controls |

The selected-header controls are diagnostic CLI/recipe tests, not a new full
corpus. They do not add unique coverage to the earlier2,016-case review. The
full2,016-input corpus was not rerun because the runtime module, dependencies and
both compiler binaries are unchanged.

Release compiler:
`14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`.
Instrumented compiler:
`805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf`.
Instrumented control environment:
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`,
`UBSAN_OPTIONS=halt_on_error=1`. No leak-safety claim is made.

Representative exact command shape:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -O \
  aurora-xfs-geometry-next/tests/compiler/xfs_geometry.py \
  /tmp/aurora-resource-main-compiler-frozen \
  --compiler-sha256 14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980 \
  --case-filter 'preserved real header' \
  --artifacts /workspace/scratch/48c5de6446f8/aurora-xfs-geometry-delta-review/positive-pin
```

The negative control substitutes64 zeroes for the pin and a distinct output
path. `make-recipe.log` and `make-wrong-pin.log` retain the complete expanded
Make invocations. Use new artifact paths for any rerun; existing receipts are
preserved and the CLI intentionally refuses an existing artifact directory.

## Author final receipt audit

Read and independently checked the final focused-author aggregate receipts:

- All12 command return codes are known0.
- All71 captured runtime/test/fixture/build inputs still match their hashes.
- Release and instrumented geometry manifests both say586 headers and25,198 raw
  observations, with no filter or mutations-only shortcut.
- Each run has147 successful header batch receipts and no expected/observed
  mismatch;17 existing-output rejection receipts pass;51 mutation receipts say
  detected. Their recorded run-input hashes still match the files.
- Example assembly is identical across the two compiler pins; its native wrapper
  verifies the exact returned42. Existing storage and canonical fixture gate
  receipts are included in the12-command result.

These are audited author receipts, not a claim that this reviewer reran every
command. The12-command focused aggregate is not the main repository's complete
`make test` or a kernel/emulator acceptance run.

## Main-tree and scope boundary

This reviewer made no main-tree writes, image changes or device accesses.
However, the main tree changed concurrently after the earlier review snapshot:
16 additions and7 modifications in the dormant-table/kernel/build-test area,
including a test pycache. No XFS/compiler/library integration change was observed.
The parent was notified, and `final-audit.json` records every exact changed path.
The earlier4,954-file unchanged result remains historical; it must not be reused
as a current whole-tree unchanged claim. This review does not assess or authorize
those independent kernel changes.

No mountability, clean-log, read-only compatibility, stable device-backed memory,
filesystem support, generated-code sanitizer instrumentation or hardware
qualification claim is introduced. Full main integration and combined milestone
acceptance remain separate parent gates.

## Evidence

`final-audit.json` records final hashes, manifest comparisons, author receipt
counts, CLI outcomes and the concurrent main-tree delta. Positive CLI/native
artifacts and the exact intentional wrong-pin failures are retained in this
separate directory. The original independent corpus/report directory was left
unchanged during this follow-on review.
