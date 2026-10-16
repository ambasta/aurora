# Development and qualification

## Current test routing

Meson/Ninja owns the complete incremental native graph. `make test` selects
`full`; `make -C compiler test` and
`scripts/compiler-test.sh` select compiler-only coverage. Configure one stable
build directory per toolchain and flags, with matching real GCC/G++ on PATH.
See [build commands and suite selection](meson-bootstrap.md).

The whole-source bootstrap corpus runs first in an exclusive test slot to avoid
compiler-workload contention; other tests remain parallel and all limits stay unchanged.

Duplicate Python runner registrations execute one complete case set under `-O`.
The IOMMU mock checks use explicit failures, and unittest checks remain active.
The frozen IOMMU runtime fixture is unchanged and is never executed by these
compiler-free mocks. Generated child scripts retain their original interpreter
arguments; an outer `-O` did not change those children.

Three runner pairs retain both modes because they propagate the selected mode
into child execution: Meson identity, compiler-contract controls and the UEFI BAR
runner. Native-cap and storage-traceability runners already exercise both child
modes internally and run once at the outer level. Cross-suite developer/native
controls retain the union of suite memberships and the stricter existing timeout.
No compiler batches, source caps, watchdogs or guest gates are reduced.

Every merge/release still requires final integrated GCC 16 `full`, independent
review, normal BIOS and UEFI image builds and actual smokes, and the applicable
affected profile image/admission/fault/recovery/restoration gates. GCC 14 is
optional compatibility evidence. Native `boot` checks do not run QEMU. A focused
pass, compiler-free control, plan, registration or prior-source result cannot
qualify the current candidate. Preserve the actual compiler distribution/version.

Run final validation locally in the supported pinned development container.
Advanced native validation must match its exact pinned tools. Container work
packages the development environment; it is not a required
CI validation gate and does not establish a passing image or guest result.
No CI mechanism replaces the current AGENTS merge/release gates.

## Review and test cost

For ordinary feature work, aim for verification/review effort within roughly
2x the feature implementation effort. This is a planning/review budget, not a
permission to skip required safety or merge gates. Compiler and typed-IR safety
work is excluded. Prefer existing oracles, shared runners and dependency-selected
checks; if a justified gate exceeds that budget, state why before expanding it.
Maintain one living component document and update the status table in place.
Historical results belong in Git/PR history and retained run or CI artifacts when
available, rather than new tracked per-feature result files.

## Predecessor-backed frontend and historical receipts

Current compiler source has no C++ expression seed. Complete the explicit
[source-bootstrap recipe](../compiler/README.md#source-bootstrap) before using
Meson or ordinary Make shortcuts. The paired predecessor executable and digest
are checked before generation; all current source-consuming targets link the
Aurora frontend. Current C1/C2 regeneration and corpus checks use the existing
bootstrap gate. A digest proves artifact identity, not independent review or
source-build provenance by itself.

Make is a convenience layer over the predecessor-backed Meson graph. `make test`
forwards to the complete `full` suite without a second prerequisite graph;
the compiler-only `make -C compiler test` uses the same wrapper. Compiler-free
`make test-*` shortcuts call their scripts directly. Obsolete compiler-consuming
focused aliases and the receipt executor/check CLI have been removed; use
`meson test -C BUILD --list` to select exact focused test names.
Full suites still reject coverage-reducing overrides in their owning runner.
Ordinary Make options and custom shells retain GNU Make's normal behavior;
a dry run, skipped command or ignored failure is not qualification evidence.

Historical `gnu-cxx-main-v1` and externally pinned prebuilt receipts remain
readable under their original schema, source/header/tool/argv and tamper checks.
They retain their original scope and do not qualify changed current source.
Direct pin-aware runners retain their existing explicit identity requirements;
no new receipt format is introduced. Current qualification uses the selected
source/tool/compiler identities, standard Meson logs and independent review.

`CXX` selects one supported GNU executable. `CXXFLAGS` and `IR_TEST_CXXFLAGS`
retain their explicit allowlist: user header/search/forced-header options,
response files, specs, plugins, PCH, LTO, profile/module and alternate-subtool
controls reject. Parsed flags are data, never evaluated as commands. Focused,
cap-only, representative and self-test selections remain partial regardless of
exit status. Native tests do not imply guests, physical hardware or a general
safety proof.

## Per-invocation output budgets

Focused package/native caps charge only the fresh invocation’s output directory,
including owned child temporaries. Source, compiler binaries and prior runs are
not charged to that cap; they still reduce available filesystem space. Identity,
Manifest, Graph, kernel-budget, round-robin and IPC defaults are respectively
128/256/256/128/128/128 MiB, with an explicit maximum 1024 MiB. Aggregate selection
of that ceiling is not task-level resource admission. Retained roots, expected
growth and the 1 GiB free-space floor still matter.

The native-cap accountant measures allocated blocks and directory metadata,
counts hardlinked inodes once inside its output scope, and does not follow
symlinks. Root/ancestor symlinks reject. Package archives are charged alongside
originals before deletion; archive or cleanup failures stop and retain remaining
outputs. Samples at operation boundaries are not a filesystem quota or a bound
against arbitrary concurrent writers. No automatic scan deletes old runs to fit.

Manifest/Graph compiler and native commands retain fixed watchdogs: 120 CPU
seconds (121 hard), 360 wall seconds; host tools/rejection compiles retain
10 CPU/30 wall seconds. Batches are at most 128 cases, Graph at most 96.
Commands record actual child CPU/wall costs. Signals and wall timeouts fail
without semantic observations; watchdogs are not performance assertions.
XFS-file uses a 600-second aggregate watchdog; individual command limits remain
unchanged, and batches retain the 128 KiB source budget as host-load protection, not a
compiler scaling workaround. Large compiler graphs run exclusively; child
compilers within each runner remain sequential. Record host load with timings.

JSON integers/lookup use 660/1200-second aggregate watchdogs; their child limits
remain 20/21 CPU seconds and 45 wall seconds. Command receipts record actual
child CPU and wall costs separately from those limits.

Method-values and readonly-spans use 45-second host compilation watchdogs;
integer-oracle uses 30 seconds for symbol inspection. Native execution guards,
imported runner defaults, explicit readonly-spans `--timeout` overrides and the
three 900-second Meson aggregate guards remain unchanged.

Smoke-wrapper timeout cleanup gives each adopted child its own bounded
two-second post-KILL settling period; a child that does not settle fails cleanup.

### Bounded Graph report transport

Graph fixtures evaluate an order report or ranked-entry call once, copy it,
poison input bytes/selectors and observe the complete result. Independent Python
expected vectors still check every output word. Deliberate multi-call ownership
and constructor fixtures retain the scalar path. The private transport passes
an exact 32-byte argument record through R11 and guarded independent 264-byte
result storage through R10. It introduces no language pointer API, target-side
expected-value comparison, result cache or larger value limit.

## Complete native artifact accounting

The shared UTF-8-range/JSON harness separately counts every artifact pathname’s
allocated blocks before/after each command, including each hardlink name and the
symlink itself, without traversing child directory symlinks. `scandir` preserves
stable-tree totals; enumeration/stat errors fail closed with no partial total or
retry. It does not cache totals or weaken reserve/free-space checks.
`make test-artifact-budget` has ordinary/optimized compiler-free controls;
those checks are not native qualification or full-suite speed measurements.

## Partial package profiles and host-tool identity

Identity/Manifest/Graph `--profile dev` selects named semantic cases, retains
complete expected outputs and rejection controls, and records
`qualification_eligible: false`. Full factories remain separate. Do not combine
it with historical quick/smoke prefix selection. Meson controls the selected
compiler artifact; its before/after digest is stability evidence, not an external
pin or fresh-build receipt. Explicit pinned/fresh-build modes remain available.

Manifest/Graph serial transport checks compiler, library, oracle and generated
program identities around commands. Python and GNU host-tool full-content hashes
are compared at suite entry/finalization, including on failure; reused host-tool
receipts are labeled `suite-boundary`. A persistent change fails finalization,
but a change restored before the final check can escape detection. This is not
a hostile multi-user toolchain security boundary.

## Failure and evidence discipline

Missing prerequisites are blocked, malformed/tampered inputs and runtime failures
are failures, and never-run/skipped stages remain unqualified. Host sanitizer
coverage must name the instrumented C++ components; generated Aurora assembly is
not instrumented merely because its compiler is. Report leak-check omissions.
Keep source/tool identity, commands and original failed/interrupted evidence with
the run. Meson’s artifact adapter may remove only its own successful scratch;
explicit keeps and failed runs remain. Explicitly selected whole-directory cleanup is
separate and may remove that directory’s logs or historical/failed evidence; see [local cleanup](local-development.md#reclaiming-old-local-output-explicitly).

### Saved-baseline differential check

The standalone `tests/compiler/equivalence.py BASELINE CANDIDATE` gate compares
64 deterministic source and native outcomes. It requires a separately retained,
user-selected baseline compiler; `full` cannot create that historical input.
Run it explicitly when that baseline is available. A missing baseline means this
differential check has not run, rather than changing ordinary semantic coverage.
Standalone overload qualification, semantic lint and owner-backed JSON codec
windows run in `full`; the display-service runner already executes service-group
behavior as a child, without a duplicate registration.

The emitter migration additionally requires the byte-exact whole-source-corpus
old/new assembly and sidecar gate documented in
[compiler qualification](../compiler/README.md#emitter-migration-qualification).
It is explicitly selected because its old compiler must have independent pinned
source/build provenance; ordinary test runs cannot silently choose that oracle.
