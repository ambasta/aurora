# XFS-only M022 checkpoint evidence

The exact baseline is accepted M022 commit53cb2fe5d9222bce5a51a2d176edf8f8321960c7.
The local source subset deliberately omits prior docs/evidence, which incremental
publication must preserve on the remote base. baseline-subset.json inventories
all384 recovered product inputs and their SHA256/Git identities.

- parent-make-test.json/stdout/stderr: fresh successful full top-level aggregate.
- lookup-manifest.json and lookup-full-vector-receipts.json:203 cases/2,233
  complete u64 observations. The receipts retain generated source hashes and exact
  output bytes; the source runner regenerates the bounded inputs from four fixtures.
- api-manifest.json and api-full-receipts.json:77 complete native observations and
  12 rejection/output-preservation controls. No private-ABI malformed spans.
- external-tools-inventory/before/after.json:45 tool/helper/runtime identities;
  captured during the first attempt, rechecked before/after the successful rerun.
- first-incomplete-make-test.* and first-aggregate-failure.json: preserved failed
  supervisor attempt; it does not establish a completed aggregate result.
- first-supervisor.py, fixed-supervisor.py, supervisor-regression-tests.py and
  supervisor-controls.json: historical host bootstrap execution machinery and four
  regression checks, not target-library code. Their paths describe this run.
- inode-reconstruction.json and superblock-reconstruction.json: exact four-slice
  recovery. Complete original filesystem images remain unavailable.
- review.md and independent-*.json: separate final delta/recipe/input review.

Build products and full local native outputs remain outside this source payload;
verified successful duplicates may be held in lossless archives with precise
path/hash/mode restoration maps. No failed log/receipt was removed. No optional
compiler/kernel changes, mount, replay, file-data reading, allocation proof,
physical hardware test, new emulator qualification or performance claim follows.
