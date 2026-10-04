# Independent review: consumed UTF-8 line scanner

## Current decision

**The frozen v1 implementation passes independent review and the fresh full top-level aggregate.** No product defect or source correction was found. Result-only documentation/evidence sealing remains a separate final check before accepting the published source package. This review covers the new read-only library operation and its evidence, not a compiler, kernel, optional-feature, filesystem-extent, framebuffer, or physical-device acceptance.

The reviewer did not modify the candidate, publish, or use the candidate line/range test code as the independent oracle. All review artifacts are separate from the author's source tree.

## Identity

- Candidate: `aurora-utf8-lines-pr17-20261004`.
- Base commit: `d8222ad235fa218629266aa28e7b42ba87f4ee5e`.
- Base tree: `b8369852f9b316680bb24ee54ed228f1b4b5a095`.
- Baseline: all 473 SHA-256/size/mode entries equal the sealed PR17 source manifest.
- Frozen candidate: 477 files, eight-path delta; no deletions.
- Source freeze SHA-256: `a50baa8175acae6b308d1ab3212ff796c6298139b76f91d2fec8062b93549c8f`.
- Early source archive: 1,418,488 bytes; SHA-256 `8a4c528340bb79a604e74e80602785b5762121d962c992064370905810381623`. Every archive member independently matches its frozen path, SHA-256, size, and mode; no extra member.
- New module SHA-256: `900f3f6a1c0a4d0755eff19be98392d4a6adc3d8a7e7ce74f9134e20a185ced6`.
- Accepted M022 compiler SHA-256 before/after tests: `e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
- Independent native runner SHA-256: `60e12095028e5601c449b419d2f478cc16d8b73e83ce10970d7567138014c92e`.
- Supplemental runner SHA-256: `fbe9c86aec58ec4fcca4d30d441c293db655964649dad23f4e4731191b63a508`.

The eight changes are the module, running example, line test driver, contract, root README, library README, completeness matrix, and compiler Makefile wiring. Compiler implementation, kernel, existing library source APIs, and pre-existing tests remain unchanged. `source-verification.json` and `source-delta.diff` preserve the audit.

## Independently executed checks

Commands, full source, assembly, native executables, output bytes, expectations, and per-command receipts remain retained:

```
python3 -B -O review_native.py
python3 -B -O verify_source.py
python3 -B -O supplemental.py
```

The main independent suite passed **871 cases, 3,484 complete signed-i64 observations, 15 rejection controls, and 57 native batches**. Supplemental checks passed **four cases/16 observations plus one checked-bounds SIGILL control**. Combined independent functional output is 875 cases/3,500 observations; counts overlap author coverage and should not be presented as unique added behavioral domains.

The independent oracle uses CPython strict UTF-8 decoding and byte-LF partitioning. It does not replicate the Aurora scanner loop, use `splitlines`, import candidate test oracles, or treat low-byte process exit codes as complete observations.

Coverage includes:

- Every possible one-byte value before LF; malformed leading, continuation, overlong, surrogate, out-of-range, and incomplete encodings before final boundaries and delimiters.
- Malformed suffix deferral and the subsequent error; all byte windows of representative mixed-width input, including mid-scalar starts/ends and invalid owner margins.
- LF versus CRLF, lone CR, repeated CR, empty terminated lines, empty end window, unterminated final line, and no phantom line after a trailing delimiter.
- Valid scalar boundary values, BOM, NUL, ESC, NEL, line/paragraph separators, noncharacters, unassigned scalars, combining marks, and ZWJ as ordinary content.
- Signed `i64` extremes, negative coordinates, oversized windows, and range-error precedence.
- Seven 4,096-byte owner cases, including multibyte sequences adjacent to LF and malformed final prefixes.
- 105 public-constructor combinations covering every status/ending with negative and maximum counts; invalid reports mask all facts, and success count arithmetic never overflows.
- 38 full repeated scans whose **every line's full status/content/consumed/ending tuple** is checked against the oracle, with exact terminator reconstruction and guaranteed progress. Two further 4,096-byte all-LF/all-CRLF loops verify exact empty-line progression and final EOF.
- Byte-for-byte unchanged input, reports copied after the input borrow ends and the owner is edited, and a report returned after its local owner/nested reborrow dies.
- Private fields and helpers, closed nominal enums, non-reexported dependencies, live readonly-borrow mutation denial, mutable-span/retained-span rejection, owner bounds, wrong coordinate type, and denial of converting a report into span authority. Every rejection preserves a pre-existing output file.
- Static/runtime metadata exposes zero public fields for the private report while retaining correct copied-value size.
- Separate CR and LF final windows do not retroactively form a CRLF pair.
- A representable forged success count does not grant bounds authority: a checked span access using its maximum count terminates with SIGILL. This is a SIGILL behavioral control, **not an exact fault-instruction-address claim**.

## Source reasoning

The range guards precede all byte reads and use `count <= size - offset`, avoiding overflowing `offset + count`. The scan only computes `offset + index` while `index < count`; CR lookbehind requires `index > 0`. A found LF makes `index + 1 <= count` and ends the search immediately. Validation then covers exactly that consumed prefix including LF/CRLF, so incomplete multibyte prefixes before LF cannot be silently accepted or misreported as final truncation. No unconsumed suffix is certified.

Without LF, the entire selected final window is validated. Empty input is handled separately; every actual success therefore consumes at least one byte. Result accessors guard signed addition before adding the ending width, mask all failure payloads, and expose only copied historical facts. They neither certify forged reports nor retain a span. Reflection and ownership controls corroborate the narrow interface.

The implementation has constant scalar state and no byte-buffer copy or target heap allocation. Two passes are bounded by the consumed prefix; repeated successful scans are linear over total consumed input. This mechanism argument is not a memory-safety, compiler-correctness, resource, or equivalent-C performance proof.

## Author evidence checked

The corrected author focused run passed 1,815 cases/7,260 observations/seven rejection controls. Its earlier run reached all 1,815 native cases and failed solely because one helper-privacy diagnostic expected `unknown function` rather than the actual `private function is not imported`. Comparing retained first/current scripts confirms that only this expected diagnostic substring changed; product code was not altered.

The author re-ran the existing UTF-8 decoder/validator, encoding, and range Make targets on the same frozen input. Their receipts and retained compacted evidence were independently read and verified. The decoder includes 1,112,064 scalar values, all one- and two-byte inputs, and boundary encodings in both final modes; encoding includes scalar coverage and nominal/lifetime rejections; range passed 2,250 cases/6,750 observations/six rejections. These are author-run regression results audited here, distinct from independently executed new line tests.

The original and corrected focused compaction archives each preserve 2,530 files; the prior-UTF8 archive preserves 4,945 files. All recorded member hashes, sizes, modes, and membership sets were verified without expanding them into the candidate. `author-archive-verification.json` retains exact pins.

## Fresh aggregate verification

The fresh candidate top-level `make test` completed with exit 0 on all 477 frozen v1 sources and the unchanged M022 compiler. The reviewer independently audited the terminal receipt, entire stderr, final output markers, all current frozen source hashes/sizes/modes, and 7,518 archive members containing the four freshly completed UTF-8 gates. The parent confirmed this independently audited isolated full aggregate satisfies this library checkpoint; a redundant root rerun was not required.

Exact command:

```
make test XFS_ROOT_COMPILER_SHA256=e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e UTF8_RANGE_COMPILER_SHA256=e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e UTF8_LINES_COMPILER_SHA256=e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e
```

This passes the actual line Make target (1,815 cases/7,260 complete observations/seven rejections), existing UTF-8/range gates, compiler/source/IR/module/native-ABI tests, image and hosted kernel/UEFI validators, 630 semantics cases, and the inherited package identity target (5,503 cases/199,213 full-u64 observations/40 rejections). Aggregate stderr consists of successful Python test reports. These host/image/validator results are not fresh emulator runs.

- Aggregate receipt SHA-256: `63e4063ce002d6d6653b8ff722af21e672156ca0dbb7fbed818f8d721d5e4ea6`.
- Stdout SHA-256: `9d684dd5ea0652d23be09349aaab9daf1698c63b7f25eec6de95d35a03a4837c`.
- Stderr SHA-256: `fdc478fd0d3e639223faa98a52941c2c8d07711e1c4437d11686bf46379ca6a4`.
- Bounded supervisor SHA-256: `a19bb84225a7beb22ed690b8601b529238747317926066e014c5ae4d4004ce41`.
- Aggregate UTF-8 archive SHA-256: `5aafcdb481f1852003a18f2d7b602bcc12a33dfdad3fe1a0ffbcb533694d3af3`.
- Runtime: 694.94 seconds; peak allocation 411,308,032 bytes under the approved 536,870,912-byte cap; free-space floor remained satisfied.

`aggregate-verification.json` and `verify_aggregate.py` preserve the exact audit. Subsequent result-only documentation changes must be compared against this tested freeze; product, test, or build changes are not covered automatically.

## Tools, resources, and limitations

- Python 3.12.14; GNU assembler/linker 2.44; accepted M022 native compiler.
- Review output initially capped at 64 MiB with a 1 GiB free floor and 24 MiB command reserve. Retained allocation after supplemental checks: 26,140,672 bytes (later small reports add metadata).
- Per command: 45-second wall limit, 20/21-second CPU limits, 8 MiB file limit, disabled cores, 512 MiB compiler AS and 128 MiB assembler/linker/native AS. Generated batches are limited to 16 cases/64 KiB.
- The first ad hoc baseline-map comparison included the seal's extra `git_blob_sha1` metadata and therefore rejected equal source identities; the corrected verifier compares the four declared identity fields and passes. This was a review-comparator schema mismatch, not a candidate source mismatch or product failure.
- No new sanitizer, emulator, graphics, kernel, extent-reader, optional-feature, physical hardware, terminal action, Unicode broad line-break, grapheme, normalization, or performance result is claimed. QEMU is not available in this environment, and this library-only delta does not change kernel/compiler implementation.
- No source mutation or publication was performed by the reviewer. The implementation aggregate and exact identities are now verified. The final result-documentation/evidence seal remains to be checked separately.
