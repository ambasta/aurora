# Parent integration handoff

Main has not been changed. Adoption requires the root coordinator's authorization.
The publisher reads immutable M019 archives, so this source delta need not mutate
that checkpoint's evidence or publication input.

1. Read `change-manifest.json`. For every existing file, verify main's current
   SHA256 matches `base_sha256`; verify candidate bytes match `candidate_sha256`.
   For new files, require their target absent. If a main file changed, stop and
   reconcile that file rather than replacing newer work. In particular preserve
   later README/completeness additions. There are 18 changed/new paths.
2. Apply only those paths (or the regenerated `nested-values.patch` after a dry
   check). Do not copy build, tmp, review, receipts, archives or the full candidate
   tree into source. `docs/xfs-geometry-proposal.md` is unchanged and appears only
   as a pinned source-copy test dependency; it is not part of the delta.
3. Force a fresh serial release compiler build on adopted inputs and verify the
   known release pin when using the same toolchain/flags. Capture before/after
   input manifests and exact statuses for a fresh parent `make test`.
4. Suggested three existing UEFI integration spots, using the already verified
   tool/firmware environment and adopted release compiler via AURORAC:

   - `./scripts/kernel-uefi-smoke.sh runtime-span`
   - `./scripts/kernel-uefi-smoke.sh runtime-pin-fault`
   - `./scripts/kernel-uefi-smoke.sh normal`

   These check compiled readonly-value call behavior, retained compiler-fault
   containment and final clean42/normal restoration. They are three fresh spots,
   not a new full166-mode qualification. Main `make test` already covers hosted
   kernel/image/table/pin and source/library/compiler gates. The exact current
   runner contracts and external pins remain authoritative. This worker did not
   operate shared kernel images.
5. Preserve failed development logs and the independent report. Curate evidence
   as a new checkpoint; do not overwrite M019 records. Confirm final normal image
   restoration and source/external pin stability before marking integration done.

## Makefile/sanitizer details

The sole compiler Makefile delta adds:
`python3 -O ../tests/compiler/nested_values.py $(abspath $(OUT))`
Existing IR_TEST_CXXFLAGS and IR_TEST_BUILD_PREFIX hooks remain unchanged.
No default debug, optimization or runtime instrumentation flag was weakened.
The complete instrumented target used command-line -g1 only for ir_tests.cpp;
all other instrumented translation units kept -g. Fatal ASan/UBSan flags,
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 and
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 are in VERIFICATION.md.
CXX-only limits are 2GiB address, CPU120/130s, wall180s, regular-file512MiB/core0;
runtime ASan executions must not inherit the address-space cap.

The instrumented compiler pin is
`78379d081bfae56608a6a60e72bc290e9abd68e88b1a9c3e96f93d25b007cfb5`.
The final 2GiB-capped release rebuild reproduced
`e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6`
byte-for-byte in19.74s, peak698,468KiB RSS, exit0.

## Planning scope and time

Plan one fresh full parent aggregate plus those three existing UEFI profiles,
with no new kernel feature/mode and no claim of a fresh full166 run. A planning
allowance of5–10minutes is reasonable for the aggregate/rebuilds and spots on
this executor, not a measured guarantee. The historical M019 exact-source
receipts show these three profile invocations taking7.35s,7.54s and3.71s
respectively; those old timings do not establish the new integrated outcome.
If the parent wants broader confidence for a compiler change, selecting more
existing profiles or rerunning all166 is its separate integration decision.
