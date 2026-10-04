# Independent M022 + XFS-only checkpoint review

Decision: accepted for the frozen 419-file candidate described below. No unresolved product or integration blocker remains. This is a distinct library/test/documentation checkpoint on the accepted M022 compiler, not acceptance of the optional compiler or kernel work.

## Identity and delta

- Accepted remote baseline: commit `53cb2fe5d9222bce5a51a2d176edf8f8321960c7`, tree `61fb4071050450de758d5c90291ca34d3dc73fb7`.
- Final reviewed source manifest: `FINAL-SOURCE-REVIEW-v2.json`, SHA256 `f32134af126fc4ce0bd06777c40bcc8ab8d927ee4d567f3be78088dfab2a94f7`.
- Unchanged M022 compiler: `e1953ce8446973194a66ba579809c37459466f746f491a53a98b1c910ef4110e`.
- XFS module: `8f669775ea7a5e850a314e50c37d90a5ba1ef30b1d60f6c8a54be5a6faef9e4f`.
- Adopted compiler Makefile: `fb62f07365763fb6a9ea94d242e1bc290cf0977158b3c098164451f025507f77`.

The reviewer independently hashed all 384 recovered baseline product files, including byte counts, SHA256, Git blob identity and executable mode. Of those, 379 remain exact. Only README.md, compiler/Makefile, docs/completeness-matrix.md, docs/verification.md and library/README.md change. There are 35 added source/fixture/contract/evidence files and no deletions at this boundary. Compiler implementation, kernel code, emulator profiles, prior library dependencies and executable modes are unchanged. The new module, both harnesses, four exact 512-byte decoded fixtures and both integration overlays match their accepted input pins.

`reviewed-delta-before-review-evidence.json` gives SHA256, Git blob and mode for all 40 changed/added paths. Subsequent addition of byte-identical copies of the reviewer-approved reports does not alter this product decision; those extra evidence paths must be included in the final publication manifest.

## Fresh independent checks

1. Executed the adopted candidate's actual `make -C compiler test-xfs-root` recipe with an explicitly pinned, supplied M022 compiler, compatibility lookup selection and full API gate. It passed 6 cases / 66 complete-u64 observations and 77 API observations / 12 source-rejection controls, with exit 0 and empty stderr. All 396 then-present non-build candidate inputs, ten resolved external tools and the compiler remained unchanged. Exact arguments, input/output hashes and manifests are in `focused-recipe.json`.
2. Executed 13 no-output rejection controls against the actual adopted recipe: direct/ancestor symlinks, missing and nondirectory repository/fixture/artifact roots, plus wrong explicit compiler hash. Each failed before creating artifact output. The supplied compiler was marked old to prevent a rebuild; no native invocation was reached.
3. Independently decoded all four fixture slices and checked CRC32C with a separate reflected-recurrence helper. The exact byte hashes and documented root128/offset65536, empty payload6, named payload31, alpha131/type1/offset96 and docs132/type2/offset120 agree. This did not open a complete filesystem image or run xfs_db.
4. Independently replayed all four supervisor regression controls against the final exact supervisor: vanished file and directory races are tolerated, permission failures are not hidden, and a live owned child is terminated and waited after a supervisor failure.
5. Checked every retained full author lookup/API vector against its raw native bytes: 34 batches, 2,233 lookup observations, 77 API observations and 12 normal rejection exits. These are receipt checks, not another independent execution of the entire 203-case corpus.

The source review checked geometry-before-use, inode/query lengths before indexed reads, complete directory validation before lookup, bounded entry/name/offset arithmetic, private helpers, copied reports and error zeroing. The already reviewed parser/format scope and portable overlays are retained; this integration review does not relabel their earlier results as new independent full-corpus execution.

## Full parent aggregate and failure handling

The complete fresh top-level `make test` rerun passed with exit 0, including full XFS203/2,233 + API77/12, compiler/image/hosted-kernel/validator/storage gates and 630 semantics cases (128 generated). The reviewer matched both complete log hashes, the successful receipt, all 396 tested source inputs before final documentation edits, and the unchanged compiler. Successful aggregate receipt SHA256: `87302e834a3ecf078e5b38afe3ab48bb6a61e1c3199fa446572a90dd6035c9e9`.

All 45 captured external tool/helper/runtime identities match after the run. That inventory was first captured during an earlier incomplete attempt, then rechecked before and after the successful rerun. It is a bounded captured inventory, not a claim to have traced or frozen every operating-system dependency.

The first aggregate was incomplete because its disk-accounting supervisor raced deletion of a temporary semantics output and failed to capture a trustworthy final make exit. Its original logs and receipt are preserved and are not counted as a pass. The final supervisor is pinned at `50038e8b05a518b0ab0d4d422ec9b36047160db119df319913fa76f2f36e8307`. The earlier failure envelope's intermediate `03b5bcde...` hash is now explicitly distinguished by a clarification record and exact reconstructed intermediate bytes. Only the reserve and self-pin recording changed between those supervisor versions; the successful receipt pins the final version. No Aurora implementation change was needed.

Final post-gate edits are confined to four documentation files and results/provenance evidence. The final 419-file manifest matches exactly. The report contract now explicitly states that not_found preserves validated directory facts while error statuses zero them.

## Limits and publication conditions

This checkpoint adds offline root-directory metadata parsing only. It does not mount, replay, read file data, establish inode allocation/existence, access a device, authenticate bytes, or qualify physical hardware. No new QEMU gate or full 166/170-mode result is claimed. Prior M022 emulator and sanitizer evidence remains historical. Public report construction can fabricate success data; reports confer no capability or certificate.

The source subset omits remote historical docs/evidence. Publication must apply only the reviewed explicit modifications/additions to the exact remote base and preserve every unlisted remote path and blob. Never replace the remote tree from this incomplete local checkout. This review does not authorize publication, merging or a release.

The review retained approximately 3.2 MiB, below its approved temporary 64 MiB cap; the observed global free-space floor stayed above 1 GiB. No author source was edited. The first fixture helper invocation under optimized Python did not execute its Python assert statements and is not counted; the helper was rerun with explicit guards. An intermediate final-manifest check also correctly rejected the old freeze while the author's requested evidence-only clarification was being added; the refreshed v2 freeze passed.
