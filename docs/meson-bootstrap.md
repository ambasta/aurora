# Incremental developer tests

This is a focused developer path alongside Make. It builds the native C++23
`aurorac` once per changed compiler input and runs existing core and byte/storage
scripts directly. It does not invoke compiler-contract build orchestration, create a fresh
compiler per test invocation, or change any existing Make or firmware command.

## Run

On x86-64 Linux, install Meson 1.12.1 or newer and Ninja using your usual package
manager. The existing C++23 compiler, Python 3.10 or newer and GNU binutils are also required.
The minimum Meson version is deliberately the tested version for this prototype;
older-version compatibility has not been qualified.
Choose a compiler when configuring a new build directory:

```sh
CXX=g++ meson setup build/meson --backend=ninja
meson compile -C build/meson -j 2
meson test -C build/meson --suite dev --num-processes 2 --print-errorlogs
```

Use a separate build directory to compare a different compiler or flags. No
formatter or optional style package is needed. Meson stores the configured C++
command and supplies it to the existing native-observer scripts.

`meson compile` builds `aurorac`, the existing C++ initialization-facts fixture,
and the storage-codec example assembly. Repeating it without input changes does
no compilation. The compiler's C++ include dependencies come from the compiler's
generated dependency file. The example declares its Aurora source, the compiler
target, `library/std/bytes.au` and `library/std/binary.au` as inputs. Those modules
currently import no other modules; future imports must be added to this dependency declaration
until the compiler can emit dependency files itself.

## Choose the checks for the change

The default developer feedback set is `dev`, comprising `core`, `bytes` and the
explicitly partial semantic `packages` suite. An unfiltered `meson test` runs the
same fifteen tests. Use two workers initially to bound concurrent compiler/test
memory. The warm `core` design target is under two minutes on the measured host;
this is a feedback budget, not a portable timing guarantee. Cold bootstrap builds
and broader qualification are separate costs. Each Python test has a 300-second
timeout, while initialization-facts has a 120-second timeout.

```sh
meson test -C build/meson --suite core --num-processes 2 --print-errorlogs
meson test -C build/meson --suite bytes --num-processes 2 --print-errorlogs
meson test -C build/meson modules source-depth --num-processes 2 --print-errorlogs
```

Choose by actual dependencies: compiler frontend/class/integer/module changes
start with `core`; `std.bytes`, `std.binary` or `std.binary_writer` changes start with `bytes`.
Run the affected component's additional tests for surfaces not registered here,
including templates, overloads, readonly windows, short-circuit joins and text.
Package changes can start with the partial `packages` suite described below. A focused pass does not imply those other surfaces were exercised.
Run `dev` when multiple covered areas change or a wider quick pass is useful.
For leaf documentation edits, review content, commands and links; do not rebuild
the compiler or require the full native aggregate without a relevant reason.

## Named coverage

The `core` suite keeps eight complete existing tests, without sampling their cases:

- `frontend`: parsing, scalar/array/class basics, ownership and borrow rejections,
  reflection, initialization, stack/depth boundaries and exact SIGILL checks
- `classes`: constructors, receiver mutability, privacy, method calls and cycles
- `value-calls`: copied class arguments/results, nominal/visibility rejection,
  evaluation order, alias isolation and wide-value boundaries
- `signed-integers`: division/remainder boundaries and traps, evaluation order,
  integer algorithms, overflow and access rejection
- `unsigned-integers`: full-width arithmetic, comparison, shifts, conversion,
  overflow traps and mixed-type/literal rejection
- `modules`: imports, defining-module lookup, visibility/reflection isolation,
  cycles, file/path/resource limits and rejected source/output aliases
- `source-depth`: every existing oversized nesting/AST rejection, with unchanged
  source and absent output on failure
- `initialization-facts`: the existing C++ model fixture, also in `compiler`

These registrations preserve the runners' native full-width result checks,
exact SIGILL expectations and diagnostic/output-preservation checks. The core registrations do not alter their runners or oracles; no exhaustive
matrix is replaced with first-N cases.

The `bytes` suite has four named tests, with their existing default case counts:

- `byte-codec`: owned byte encodings, layouts, rejections and the storage example
- `binary-writer`: owned record writes, unchanged-on-failure bytes, copied values,
  reader interoperation, exact bounds traps and rejection cases
- `packed-values`: copied values, bounds traps and rejection cases
- `storage-binary`: readonly readers, CRC32C and offline XFS header cases

`meson test -C build/meson` runs all fifteen registered tests. Select an individual
test by name, or use a named suite for the relevant feedback loop. Test
invocations always rerun the selected tests; a successful previous run is never
used as a cache of current correctness. A library-only edit does not require
rebuilding the native compiler, but a selected test run reads the edited library.
The byte/storage Python oracles still compile their small C++ signal observer once
per test process. Python runners compile/assemble generated Aurora cases. The no-compilation
claim applies to an unchanged `meson compile`, not to these executable tests.

Tests run in parallel by default. Each Python script already owns unique
temporary directories; Meson places those below `build/meson/tests` by setting
`TMPDIR`, `TMP` and `TEMP`. Module symlinks, FIFOs, alias checks and oversized-source
fixtures are all contained in those private directories. The source tree and
other build directories are not output destinations. The C++ model writes no files.
Meson's normal test logs are in `build/meson/meson-logs`. Existing temporary-output
cleanup remains unchanged; these focused logs are not the historical native
acceptance receipts and do not preserve every generated binary.

Only these targets are migrated. Use `make test` explicitly for the complete
native qualification graph and its matching run receipt. Existing sanitizer,
firmware, QEMU and independently pinned qualification workflows remain separate. A pass
here is focused developer evidence, not full-system or hardware qualification.

## Implementation references

- [Meson build targets](https://mesonbuild.com/Build-targets.html)
- [Meson generated sources](https://mesonbuild.com/Generating-sources.html)
- [Meson unit tests and suites](https://mesonbuild.com/Unit-tests.html)
- [Meson custom-target dependency options](https://mesonbuild.com/Reference-manual_functions.html#custom_target)

## Final joined developer suite — 2026-10-07

The twelve-test graph was then checked on the exact 644-file source tree merged
as `46743cd15ff462e03dfab93279808ab68f1fed74`, including console, binary writer,
output-budget/style, structured diagnostics and lossless-lexer work. The selected
compiler, library and runner files matched that tree; this increment changed only
Meson routing and documentation. A fresh Meson compiler build had SHA256
`993c94564d6bf5d66693491e871e07e148e1a75180cedf82f0f9ef1ee4e6003d`.

- All twelve `dev` tests passed with two workers in 20.71 seconds wall, using the
  same recorded GNU/Linux toolchain. Frontend/classes began 4.0 milliseconds apart
  and overlapped for 1.38 seconds.
- Core counts remained 207 frontend, 74 class, 59 value-call, 84 signed-integer,
  95 unsigned-integer, 72 module and 11 depth cases, plus the initialization model's
  7,405,472 checks. Byte/storage counts remained unchanged. The additional complete
  writer runner passed 278 native cases, eight rejections, three exact bounds traps
  and its executable example in 2.44 seconds.
- Reconfiguration and the changed-input build took 0.89 and 35.48 seconds,
  respectively. The final unchanged compile took 0.38 seconds and reported no work.
  Compiler digest, size, modification time and Ninja's build log remained unchanged
  across the test invocation and final no-op.
- The complete controlled check finished in 58.42 seconds. Peak sampled owned
  allocation was 29.49 MiB, including both source snapshots and retained evidence;
  minimum observed free disk was 16.66 GiB and available memory was 7.09 GiB.
  Maximum build-child RSS was 703 MiB. These are observations, not portable limits.
  All 644 source files stayed unchanged during the run; only measured-result
  documentation was updated afterward.

The diagnostics/lossless lexer dedicated harnesses and newer unregistered features
still have separate focused gates. This run does not replace those or the complete
native, sanitizer, emulator or hardware qualification workflows.

## Initial developer suite — 2026-10-07

The initial eleven-test result below predates the additional `binary-writer`
registration, which reuses the complete existing PR40 runner without alteration.

The core registration was tested against merged PR38 source
`54fff77cf2b1cdc796f3fe0929002bd9fca18628`, with the same GCC 14.2.0, GNU binutils
2.44, Python 3.12, Meson 1.12.1 and Ninja toolchain used below. Only scheduling
and documentation changed; compiler, library and all existing runner bytes were
unchanged. One actual `dev` invocation at two workers passed all eleven tests
in 22.09 seconds wall. This was not a separate core-only timing run.

- New core runners passed 207 frontend, 74 class, 59 value-call, 84 signed-integer,
  95 unsigned-integer, 72 module and 11 depth cases. Initialization-facts passed
  its existing 7,405,472 model checks. These counts describe different test kinds,
  not a combined safety-proof count.
- The three byte/storage runners retained the default counts recorded below.
- Frontend and classes started 6.5 milliseconds apart and overlapped for 2.23
  seconds. Meson's test log records each command, result, duration and environment.
- A fresh build took 33.46 seconds; a repeated source-depth test took 0.72 seconds;
  the final unchanged compile took 0.36 seconds and reported `no work to do`.
  Compiler SHA256, size and modification time, and Ninja's build log were unchanged
  across both test invocations and the final compile.
- Setup, build, listing, tests and no-op validation completed in 58.57 seconds.
  Peak sampled owned-directory allocation was 16.67 MiB, including source, build
  and temporary outputs. Cold-build maximum child RSS was 699 MiB; this is not a
  sum of concurrent process memory. All source inputs remained unchanged.

These are focused single-host measurements. There was no full native aggregate,
sanitizer rerun, QEMU gate or new hardware qualification in this increment.

## Measured validation — 2026-10-07

The additive graph was tested on the PR37 source
`f458620b325c4f17c32b32c3c4a09b2771a472b8`, with GCC 14.2.0, GNU binutils 2.44,
Python 3.12, Meson 1.12.1 and the pinned Ninja 1.13.2 wheel. The latter reports
`1.13.2.git.kitware.jobserver-pipe-1`. Wheels were checked against the SHA256 values
from their versioned PyPI registry records and installed in an isolated directory.
Only this GNU/Linux toolchain combination was run.

- Cold `meson compile -j 2`: 33.28 seconds, two C++ compilations, two links and
  the example assembly generation. Ninja's build log records the two independent
  C++ compilations starting together.
- Unchanged `meson compile -j 2`: 0.80 seconds, `ninja: no work to do`, with no
  compiler or linker command.
- Appending a comment to `compiler/lexer.hpp`: 35.94 seconds, rebuilding and
  linking `aurorac` and regenerating its dependent example. The unrelated C++
  fixture did not rebuild. The resulting compiler hash was unchanged.
- Appending a comment to `library/std/bytes.au`: 0.43 seconds, regenerating only
  the example assembly. Compiler bytes, size and modification time were unchanged.
- The `bytes` suite passed twice with two workers: 19.37 and 20.81 seconds wall.
  On the first run, byte-codec and packed-values began 4.2 milliseconds apart
  and overlapped for 2.40 seconds. On both runs, Meson performed no bootstrap
  rebuild before running the tests.
- The C++ initialization-facts fixture passed 7,405,472 checks in 0.69 seconds.
- After restoring the original header/library bytes and timestamps, another
  actual `meson compile` was a no-op in 0.36 seconds.

Before publication, dependency review caught the example's second direct import,
`std.binary`, missing from the custom target. It was added, and a recursive scan
confirmed the example imports exactly `std.bytes` and `std.binary`, with no further
imports from either module. After graph regeneration, a separate `std.binary`
comment edit regenerated only the example in 0.52 seconds; restoring the input
produced another no-op. The codec test passed again with the corrected graph.

Each bytes run covered 789 codec cases plus 19 rejections, 100 packed-value cases
including 54 exact traps plus 18 rejections, and 254 storage cases with 1,186 API
calls. The existing codec test also assembled and executed the storage example;
the Meson example build target itself produces assembly only. Logs use Meson's
standard output and test formats. These are single-host measurements, not stable
performance guarantees or a repeat of the full native qualification.

## Semantic package feedback

`meson test -C build/meson --suite packages --num-processes 2 --print-errorlogs`
selects explicit `--profile dev` cases for Package Identity, Manifest and Graph.
These profiles provide partial developer feedback. They are not complete package
qualification and do not replace the default full package runners or `make test`.
The historical `--quick`/`--smoke` first-N selection remains separate and cannot
be combined with `--profile dev`.

- Identity: 183 cases, 6,048 complete u64 observations, all 20 compile-time
  rejection cases run with both missing and existing output. Named cases cover
  name/version bounds, each component's overflow, delimiter/framing and invalid
  grammar families, selected byte windows, constructor poisoning, comparison,
  copying, eager fallbacks and defining-module lookup.
- Manifest: 157 cases, 13,098 observations, all 29 rejection cases run twice.
  Cases cover zero/one/eight and over-cap dependencies, first/last/bad selectors,
  truncation/framing/CRLF/unknown directives, self/duplicate names with same and
  differing versions, late malformed dependencies, numeric/name/window bounds,
  poisoned constructors, copied storage and lookup isolation.
- Graph: 187 cases, 15,029 observations, all 30 rejection cases run twice.
  Cases cover small and eight-package chain/diamond/cycle/disconnected-cycle
  shapes, empty/dense graphs, separate catalog/dependency permutations, missing
  dependencies, version conflicts, malformed/duplicate packages, all 20 directional pairs
  among malformed/duplicate-package/missing-package/version-mismatch/cycle errors,
  separate range precedence and count/rank/
  window boundaries, poisoned unused selectors and constructor normalization.

Each named selection keeps the existing independent expected-value oracle,
complete u64 comparison, output-preservation checks and every
ownership, eager-fallback, binding and compile-time rejection case. Selected
labels and actual counts are retained in each invocation's manifest.json. Missing
required labels, absent required families or duplicate selected labels fail closed.
The full byte-mutation, seeded-random and graph-mask/permutation corpora remain
unchanged and are generated only on the full path. Compiler-free regression tests
in `tests/test_package_profiles.py` compare the full generated corpus, expected
vectors, rejection sources/diagnostics and shared observers to reviewed digests.

Meson passes its actual `aurorac` target plus `--developer-selected-compiler`.
Ninja owns building and dependency tracking. The runner observes that artifact's
path, metadata and SHA256 before/after; this is expressly not independently pinned
acceptance or a fresh-build provenance receipt. The selected-artifact switch is
restricted to the partial profile, rejects competing pin/receipt arguments and
cannot run inside an aggregate test context. Existing full qualification modes
and their compiler-identity requirements remain unchanged. The package helper
does not invoke Make or build a compiler.

Each family creates a unique output directory under the build-local TMPDIR,
including its own charged subprocess tmp directory. Existing default caps remain
128 MiB for Identity and 256 MiB for Manifest/Graph, with the 1 GiB free-space
floor. Retained package receipts and compacted successful artifacts differ from
the older temporary-output core/byte runners; repeated package tests create new
invocation directories. No shared output directory is cleared.

The first out-of-tree native attempt exposed a pre-existing Manifest self-test
scratch assumption (`source/build` had to exist). Its failure is retained. Dev
mode now places that compiler-free path-control fixture under build-local TMPDIR;
the control checks the exact symlink rejection reason, so generic outside-root
rejection cannot hide a broken symlink check. Full mode keeps its existing default
scratch parent and all artifact containment rules.

### Package-profile measurements

On the PR44-based profile candidate (compiler SHA256 prefix `993c94564d6b`),
using GCC 14.2, Meson 1.12.1 and Ninja 1.13.2 on x86-64 Linux,
the clean two-worker core+packages replay passed all eleven tests in 22.11 seconds.
The final combined `dev` run passed all fifteen registered tests in 33.68 seconds,
including core, all four byte/storage runners and the three partial package
profiles. These are measured wall times, not portable guarantees. The separate
fresh compiler/example/model build took 41.49 seconds; it is excluded from warm
feedback timing. The final dev invocation regenerated changed suite metadata but
rebuilt no C++ target; a following `meson compile` also reported no work.

The final package durations were Identity 2.44 seconds, Manifest 5.17 seconds and
Graph 12.10 seconds. Their peak owned-output allocations were respectively 1.55,
3.78 and 3.21 MiB, below unchanged 128/256/256 MiB caps. Test intervals verify two
concurrent tests. The core+packages replay additionally demonstrated 3.44 seconds
of package-family overlap; in the combined run, storage-binary occupied one slot
while the package families ran in the other. The selected compiler artifact's
before/after identity was unchanged, with no external pin claimed.

All 527 selected native cases, 34,175 complete u64 observations and 158 rejection
executions passed. Seven compiler-free controls passed normally and with Python
optimization; pinned Ruff 0.16.7 format/lint checks passed for touched Python.
Independent review verified generated expectations, exact native observations,
rejection/output-preservation receipts, input hashes and full-corpus equivalence.
This is focused developer evidence only. The retained initial Manifest scratch
failure is not counted as a pass, and no full native aggregate was rerun.

After composing the reviewed profile delta onto PR47, the same three package
profiles passed on the current overlay-aware compiler (SHA256 prefix
`fa426eb231c9`) in 16.96 seconds. Its main source and complete 16-file quoted-include
closure were byte-identical to the published PR47 inputs, so the existing built
artifact was reused without another compiler build. This was a package-only
compatibility check; the 33.68-second combined dev timing remains scoped to the
prior measured candidate and compiler. Both runs record selected-artifact identity,
not an externally approved pin. Worker count remains configurable; only the
two-worker setting is measured here.
