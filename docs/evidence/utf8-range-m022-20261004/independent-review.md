# Independent review: read-only UTF-8 scalar subranges

## Decision

ACCEPTED for the narrowly scoped library-only frozen candidate identified below. Independent native/rejection checks and the fresh full parent `make test` all passed. No product defect was reproduced. The reviewer independently audited the aggregate terminal receipt, its logs, compiler/supervisor/tool pins, source invariance, and the actual newly integrated range target. This acceptance does not cover subsequent implementation changes or unrelated optional/XFS-extent work.

## Exact reviewed inputs

- Candidate: `/workspace/scratch/48c5de6446f8/aurora-readonly-text-m022-20261004`.
- Accepted baseline commit: `b151aec6c4d98adfb542da91e5a34cff279dc832`; tree: `f82a724d2b1bbe69aa4021bef8689d546acd8b9a`.
- Source freeze: `work/source-freeze-v2.json`, SHA-256 `401f19344f0f33dc56a686833ee3e19f310e6657b2240a3db9d584e4c24aa731`.
- Source archive: `work/readonly-text-source-v2.tar.gz`, SHA-256 `09ce6bd126a55e8fed813f31f23a87adbb22bc50c57b3f1b930bcb54f2debff7`.
- Range module SHA-256: `7e05a05ec4c622737804fdd8aac62e7328539c2280e5b9c0dc17d27a83d51030`.
- Author runner SHA-256: `8c8f4a9bac782bcf24ffeda01099c98ec8fa3643efa83d3bb6f9b5ff953821ec`.
- Accepted M022 compiler SHA-256: `e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
- Independent runner SHA-256: `65ca1293e46fb5ea2b649da42dc329cb9c072219b435db889c7f8588b58d2c72`.

The reviewer verified every one of the 434 frozen source files and every one of the 430 accepted baseline source files against the actual respective files. There are four added paths and four modified paths, with no removal. Only `compiler/Makefile` changes under `compiler/`; all 31 other compiler files, all 80 kernel files, pre-existing tests and `library/std/utf8.au` remain byte-identical to the accepted baseline. Complete paths and hashes are in `source-verification.json`.

This was a read-only product review. The reviewer did not edit candidate code, alter the accepted baseline, publish, or touch a main branch.

## Algorithm and API review

Reviewed AGENTS, README, completeness matrix, library README, new contract/example/module/test, prior UTF-8 implementation, span contract, root Makefile and compiler Makefile.

- Negative scalar coordinates return recoverable `out_of_range` before byte access.
- Whole-window validation occurs before positive scalar-range bounds. An invalid/truncated suffix invalidates even an empty or entirely earlier requested interval. Only the selected window is interpreted.
- The validator proves the selected window lies within the borrowed owner. Subtraction-based scalar bounds establish `first_scalar + scalar_count <= total_scalars` before forming that sum.
- The subsequent decoder walk observes the same immutable span. Every walked scalar has width 1–4 and remains within the validated window; `offset + position`, `count - position`, `position + width`, and `position - start` are bounded. The omitted repeated status test relies on this valid unchanged-input invariant.
- The initial start value of zero handles `first_scalar == 0`. Other starts are recorded exactly when the walk reaches the requested index. Walking to `first_scalar` with zero requested scalars returns an empty range at that boundary, including the end. Empty end windows accept `(0,0)`.
- Returned offsets are relative to the selected window. Results are copied numeric observations, never retained spans or validity/ownership certificates.
- Error accessors mask both coordinates. Fabricated success reports with negative coordinates or an unrepresentable sum normalize to `out_of_range` using guards before subtraction; valid-looking fabricated values still confer no byte authority.
- No mutation, retained borrow, heap allocation, normalization, grapheme handling, display width, or implicit import re-export is introduced.

No product correction was requested.

## Independent native gate

Command: `python3 -B -O review_native.py`, run from this review directory against the pinned accepted M022 compiler and candidate library. This independently authored runner does not import or execute the author's test implementation. Its oracle strictly decodes the entire selected window in Python, slices scalar strings, and re-encodes prefixes/ranges, rather than reproducing the Aurora validation/walk algorithm. Native results are collected through a small assembly host-test seam as complete signed 64-bit values, then unpacked and compared exactly.

Final replay: **588 native cases, 1,764 exact i64 observations, 38 fixtures, and 10 compile-time rejection controls passed**. See `summary.json`, `coverage.json`, `native/batch-*/cases.json`, `native/batch-*/result.json`, native stdout bytes, and per-command receipts.

Coverage includes:

- 144 mixed-width scalar intervals with outside-window invalid sentinels.
- 42 scalar-policy boundaries, including NUL, BOM, noncharacters, unassigned values, and all UTF-8 width boundaries.
- Every one of 78 byte windows of an independently chosen mixed-width sequence.
- 75 malformed/truncated trailing-window cases with early/empty/oversized requests, and 25 malformed-prefix cases.
- 28 separate signed coordinate boundaries, 16 combined extremes, and four negative-versus-malformed precedence cases.
- 80 independently seeded random valid Unicode sequences and 60 random byte sequences.
- Three maximum 4096-byte owner cases, including the four-byte final scalar and empty-at-end selection.
- 32 fabricated copied report/masking cases and a copied result returned after a local owner and nested reborrows cease to exist.
- Input checksums remain unchanged by calls, and result observations remain valid after the owner is mutated following the temporary call borrow.

The 10 rejection controls cover all three private fields, owner mutation while a nested read-only reborrow lives, owner sizes 0 and 4097, mutable span syntax, returned span signatures, constructing span authority from a fabricated report, and dependency visibility. The returned-span and mutable-span cases are unsupported-syntax/API rejection evidence; they are not claimed as evidence of a lifetime analyzer evaluating an otherwise supported returned-borrow operation. Every rejected compile preserved an existing output marker.

The review enforced a 64 MiB owned-output cap, 1 GiB free-space floor, and 24 MiB command reserve; the final replay plus retained failed attempts allocated 28,561,408 bytes at completion. Compiler AS is 512 MiB; assembler/linker/native AS is 128 MiB; CPU is 20/21 seconds, wall limit 45 seconds, file limit 8 MiB, and cores disabled. No generated target sanitizer claim is made. Python was 3.12.14; GNU binutils was 2.44. Exact tool text is retained.

## Harness corrections and preserved failures

Two reviewer-only fixture problems were retained and corrected before the successful complete replay:

1. An attempted whole-class reassignment is outside accepted M022's supported assignment grammar. The fixture was changed to exercise copied results and post-call owner mutation without unsupported reassignment. `failed-unsupported-class-assignment/` retains its source and failure.
2. Returning a span rejected at the result-signature parser, with `only scalar function results...`, rather than a diagnostic containing `span`. Only the expected substring was corrected. `failed-return-diagnostic/` retains all 588 successful native cases from that attempt and the diagnostic mismatch.

Neither issue was a product defect. Failed receipts are not counted as final acceptance passes.

The author's initial failure is similarly a harness expectation failure. The reviewer compared the exact recovered initial runner to the corrected runner: only four diagnostic substrings changed (`borrow`, `span`, `type`, and `visible` to the actual specific diagnostics); no native case, expected result, or product API code changed. The corrected runner's full rerun passed.

## Author gate, integration and artifact verification

- The focused author gate passed 2,250 cases / 6,750 exact i64 observations and six rejection controls.
- The unchanged previous UTF-8 and encoding Make targets passed on the same accepted compiler; the encoding suite reports all 1,112,064 Unicode scalar values and 2,048 surrogates covered by its existing checks.
- Make's `test` target has the actual `test-utf8-range` prerequisite; it is not just a documented optional command. The fresh aggregate executed that prerequisite, again passing 2,250 cases, six rejections, and the exact accepted compiler pin. The aggregate as a whole subsequently passed with exit code 0.
- Compaction was lossless. The reviewer independently decompressed and hash/size/mode-verified all 3,146 files in the corrected author's range archive, all 1,762 files in the prior-UTF8 archive, and all 3,183 files in the fresh aggregate's range archive. Native range receipts contain identical full expected and observed values. See `author-archive-verification.json` and `aggregate-range-verification.json`.

Focused archive SHA-256: `514b7e8b6c327f1fafddc4b10be14bed2b0488038c2135def7f199e559102506`.
Prior-UTF8 archive SHA-256: `23c70bd7bb93bcd532472939e223a7ba83bdef702aad156180a952c85b75a2dd`.
Aggregate range archive SHA-256: `e15b56c41208f40ebf297b82cb19f5d955d074b2aeed9193212537cb1f2cac91`.

Reviewer and author case counts overlap and must not be added into a unique-case total. This is bounded functional evidence, not a whole-Unicode text library, general lifetime/heap API, safety proof, performance benchmark, compiler milestone, emulator/hardware qualification, or acceptance of unrelated optional/XFS-extent work.

## Final aggregate audit

The fresh command was `make test XFS_ROOT_COMPILER_SHA256=e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e UTF8_RANGE_COMPILER_SHA256=e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`, run in the candidate checkout. `work/parent-make-test.json` reports pass/exit 0; its command, before/after compiler pin, 434-input freeze hash and supervisor hash were independently verified. The stdout includes the actual new range Make recipe and the subsequent compiler/IR/module, image, hosted kernel/UEFI and final semantics gates through `PASS 630 cases`. Stderr contains expected successful Python unittest output, with no failed test or traceback. Nine available tool executable pins were independently rechecked. See `parent-aggregate-verification.json` for exact receipt/log/tool hashes.

The author's aggregate reported peak allocation 360,194,048 bytes under its 384 MiB cap and ended with over 29 GB free; the reviewer verified all 434 frozen inputs and the accepted compiler again after completion. QEMU is absent in this environment, and no new emulator or sanitizer qualification was performed in this library-only review. Existing kernel/compiler sources remain unchanged, so this acceptance makes no new emulator, physical-device, optional-feature, compiler-safety or performance claim.
