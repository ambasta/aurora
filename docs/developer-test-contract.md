# Development and qualification

## Current test routing

Meson/Ninja owns the complete incremental native graph. `make test` selects
`full`; `make test-compiler`, `make -C compiler test` and
`scripts/compiler-test.sh` select compiler-only coverage. Configure one stable
build directory per toolchain and flags, with matching real GCC/G++ on PATH.
See [build commands and suite selection](meson-bootstrap.md).

Every merge/release still requires final integrated GCC 16 `full`, independent
review, normal BIOS and UEFI image builds and actual smokes, and the applicable
affected profile image/admission/fault/recovery/restoration gates. GCC 14 is
optional compatibility evidence. Native `boot` checks do not run QEMU. A focused
pass, compiler-free control, plan, registration or prior-source result cannot
qualify the current candidate. Preserve the actual compiler distribution/version.

Run final validation locally in a comparable environment with the selected pinned
tools. Container work packages the development environment; it is not a required
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

## Hosted lexer and seed routes

Canonical Meson/compiler targets build the C++ seed, emit the Aurora lexer and
link hosted stage 1. Source-consuming fixtures use that phase; bootstrap and
differential checks compare it with the C++ reference. The [lexer guide](../compiler/LEXER.md)
defines the exact routes and trust boundary.

The supervised `gnu-cxx-main-v1` fresh build, including legacy focused Make
aliases, remains the C++ seed/reference compatibility route. Its old one-command
receipt does not qualify hosted stage 1. Ordinary development needs no historical
binary pin. An observed digest proves artifact identity, not independent review
or fresh-source provenance.

## Explicit externally pinned acceptance

`make test-acceptance ACCEPTANCE_COMPILER_SHA256=REVIEWED_DIGEST` is a separate
legacy compatibility/provenance workflow, not a second mandatory native graph.
The expected pin is exactly 64 lowercase hex characters, supplied independently
of the binary under test. With no path, the supervisor builds current source and
requires that digest before tests. With
`ACCEPTANCE_COMPILER=/absolute/path/to/aurorac`, it validates and copies the
reviewed prebuilt; its provenance is `externally-pinned-prebuilt`, with no claim
that those bytes were freshly built from current source.

`OUT`, `AURORAC` or per-family compiler paths cannot silently substitute for the
controlled fresh compiler. Conflicting selectors and explicitly empty prebuilt
selectors reject before work. An explicit compatible per-family pin remains
available for focused legacy targets. A direct pin-aware runner requires exactly
one `--compiler-sha256 DIGEST` or `--developer-build-receipt FILE`, unless its
separately documented Meson selected-artifact mode applies.

Full aggregates and acceptance reject `*_TEST_FLAGS` and coverage-reducing
controls. Quick, representative, cap-only and self-test selections remain focused
or diagnostic even when every selected case passes. A passing Make exit or a
printed dry-run command is not completed execution.

## Supervised host controls and receipts

The legacy supervisor records source/test contents, recipe/argv, GNU tool
identities, relevant environment and the fresh bootstrap compilation’s discovered
header closure. The run-owned compiler copy is read-only as an accidental-change
guard, not a hostile-host security boundary. Inputs and identities are rechecked
before a successful terminal record.

`CXX` selects one supported GNU executable. `CXXFLAGS` and `IR_TEST_CXXFLAGS`
accept the explicit `parse_flags` allowlist. User header/search/forced-header
options, response files, specs, plugins, PCH controls, LTO, profile/module and
alternate-subtool controls are unsupported. Flags are data, forwarded as exact
argv without eval. Recipe-owned includes remain fixed. Recorded host-test argv
is not a complete header/PCH inventory; prebuilt mode discovers no bootstrap
header closure. Ordinary builds and standalone host-only targets do not establish
this supervised receipt contract.

For this legacy workflow only, root native success requires a newly completed,
matching `run.json` with `status: passed`, `scope: native-aggregate`,
`native_complete: true`, successful native stage and matching source/compiler/
context/pin. Compiler-only records use `scope: compiler-suite` and
`native_complete: false`. Meson uses its own standard logs and current-source
review rather than pretending to produce this legacy receipt. Neither route
implies sanitizers, guests, physical hardware or a general safety proof.

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
