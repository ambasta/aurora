# Canonical incremental native tests

Meson/Ninja is the canonical complete native graph. Every merge or release
requires its complete `full` suite on the final integrated source with GCC 16,
plus the separate applicable image and actual guest gates. GCC 14 is optional
targeted compatibility evidence. Previous snapshots do not qualify a new tree.

## Build and run

Use Meson 1.12.1+, Ninja, Python 3.10+, GNU binutils and GCC 16 (C++23) on a
GNU/Linux x86-64 host. Select matching real `gcc` and `g++` on PATH: a stack-guard
runner invokes bare `gcc`. Keep one stable build directory per toolchain/configuration:

```sh
# PATH must already select the matching GCC 16 pair.
CXX=g++ meson setup build/gcc16 --backend=ninja -Dlsp=false
meson compile -C build/gcc16 -j 3
# Optional quick feedback while developing; full below includes these tests.
meson test -C build/gcc16 --suite dev --no-rebuild --num-processes 4 --print-errorlogs
meson test -C build/gcc16 --suite full --no-rebuild --num-processes 4 --print-errorlogs
```

Three compile jobs and four test workers are initial configurable choices, not a
scaling guarantee. The prior two-job GCC 16 compile peaked at 2.38 GB aggregate
owned RSS on a host with about 6.78 GB available and no swap. Nine visible CPUs
do not establish nine-core throughput. Measure peak memory and reduce workers
for heavy subprocess compilations; shared fixed-image writers serialize locally.

Ninja tracks C++ headers and Aurora fixture imports. Unchanged compiler/fixture
builds are reused, but test outcomes are not cached. A different toolchain or flag
configuration needs a separate directory. A setup-time compiler/backend/binutils/
runtime fingerprint rejects in-place toolchain replacement, including direct
Meson builds/tests. Unset `CPATH`, `CPLUS_INCLUDE_PATH`, `C_INCLUDE_PATH` and
`LIBRARY_PATH`, including empty definitions; use explicit Meson include/link flags
instead. Pre-policy fingerprints need a fresh directory because their implicit
search environment was not recorded. Use a clean directory for bootstrap
compatibility or uncertain dependency identity. Do not modify inputs while
qualifying. Record final source/tool identities and Meson's standard commands,
introspection and logs; no new qualification supervisor is introduced.

Artifact-managed Meson runners remove only their newly owned `aurora-meson-*`
scratch directory after a confirmed successful child exit. Set
`AURORA_MESON_KEEP_ARTIFACTS=1` to retain successful scratch for review. Failed,
signalled, interrupted or unlaunched runs remain; cleanup errors are reported
without changing the test result. The adapter prints the path before the child
and the cleanup outcome afterward. Raw Meson logs, historical evidence, sibling
directories and explicit artifact paths passed directly to a runner are untouched.
For disk reclamation, `meson compile -C build/gcc16 --clean` removes tracked
build products while keeping configuration/logs. Retire whole directories only
through the [explicit per-directory cleanup steps](local-development.md#reclaiming-old-local-output-explicitly);
never sweep historical, failed, kept or user-owned review output automatically.

`make test` invokes the same `full` graph. `make test-compiler`, `make -C compiler
test` and `scripts/compiler-test.sh` select `compiler`. Set `MESON_BUILD_DIR` to a
fresh or matching configured directory, or omit it for a compiler-bytes/flags-keyed
directory. Backend/binutils/runtime changes are checked immediately before compile;
if they changed in place, set `MESON_BUILD_DIR` to a fresh directory. The wrapper
takes one full snapshot; Meson setup and direct builds retain their own guards.
The shortcuts run Meson setup automatically when needed, stop on setup/build/test
failure, and reject mismatched existing compiler/flag selections.
`AURORA_BUILD_JOBS=3` and `AURORA_TEST_JOBS=4` are independent.
`SANITIZE` and nondefault `CPPFLAGS`/`LDFLAGS` are not silently accepted by the
convenience route; use explicit configured sanitizer builds/separate focused gates.
Explicit pinned `make test-acceptance` remains a distinct legacy compatibility
workflow, not another mandatory run of the same native cases.

## Normal native kernel images

`kernel-bios-normal` and `kernel-uefi-normal` are real Meson/Ninja image graphs.
They compile the trusted kernel C++ translation units as native targets, then
use explicit Aurora, GNU assembler, linker, metadata and image edges. No image
target calls either shell builder. Their output directories are respectively
`<build>/kernel-images/bios/normal` and `<build>/kernel-images/uefi/normal`.
The independent BIOS and UEFI image tests read those outputs without rebuilding
or rewriting them; all existing negative image controls remain active.

```sh
meson compile -C build/gcc16 -j 3 kernel-bios-normal kernel-uefi-normal
meson test -C build/gcc16 native-bios-image native-uefi-normal-image --no-rebuild --print-errorlogs
# Equivalent standalone convenience routes, sharing the configuration driver:
MESON_BUILD_DIR=build/gcc16 make kernel
MESON_BUILD_DIR=build/gcc16 make kernel-uefi
```

`make` / `make all` builds the Meson compiler once through the BIOS image graph
and atomically copies it to the compatible `build/aurorac` path. `make kernel`
keeps all outputs isolated; explicit `make compiler` retains the legacy compiler
recipe for unmigrated consumers.

Both normal images are also default build products. BIOS and UEFI have distinct
object/generated-file owners and can build together in one Ninja invocation.
The legacy shell builders remain for specialized profiles and explicitly selected
prebuilt/pinned workflows; those still share their old output paths and locks.
Normal standalone smoke runs select the native images and put their logs beside
them. The console-service qualifier explicitly requests `--shared-normal` to
restore and boot its owned `build/uefi` image and retain fresh logs there. Actual
final normal guest boots remain required after affected fault tests.
This slice does not migrate specialized image admission or consolidate QEMU code.

Kernel flags remain fixed to the admitted freestanding GCC profile. Global
`cpp_args`, `CXXFLAGS` or `CPPFLAGS` are rejected in image-enabled configurations rather than silently adding
hosted instrumentation or profile defines. Native targets disable unity, LTO,
sanitizers, PGO and debug-STL additions. BIOS stays non-PIE; UEFI payload stays
PIE/hidden and its loader retains the Microsoft-ABI outgoing-argument option.
For hosted-only compiler or sanitizer configurations, pass `-Dkernel_images=false`
to a separate Meson setup. That configuration accepts explicit hosted flags and
does not probe the PE linker. Fresh compiler-only convenience setups automatically select this option and a
separate default directory; an explicitly supplied existing image-enabled build
can still be reused with matching compiler/flags. The two normal
image tests remain registered and fail clearly in `full`/`boot`, including with
`--no-rebuild`; disabled images cannot yield a qualified full pass.

With images enabled (the default), a GNU PE linker with `i386pep` is a setup
requirement, including for BIOS-only target selection. Select it through
`-Duefi_ld=/path/to/ld` or `UEFI_LD` with Make; its bytes join the existing
configuration identity check. Changing the selected linker needs a fresh build.
The default convenience-directory key now includes the PE-linker selection;
explicit pre-migration directories need a fresh configuration.
Explicit kernel targets depend on that identity check too, without making an
unchanged image rebuild.

C++ headers use native compiler depfiles. Aurora generation conservatively tracks
all `.au` files and directory membership under each supplied module root, so
adding an ambiguous module also invalidates the target. Source/module paths keep
their lexical identity for the compiler's no-symlink checks. Linker scripts,
embedded binaries, generated headers and validators are explicit dependencies.
Private service bridges, when migrated later, must be assembled with generated
Aurora assembly in the same invocation to preserve local-symbol access.

The native object export preserves the actual object and its same-compilation
`.su` (and UEFI `.ci`) bytes under stable logical names. A small `.source.json`
records the full translation-unit path, compiler working directory and native
sidecar paths; it does not claim image admission. There is no second metadata
compile or basename-only matching. Missing native sidecars fail the export:
remove the affected native object and rebuild it with its sidecars, or use a
fresh build directory. Deleting an exported declared output reruns its owner.
Specialized stack validators still need explicit source-location mapping before
their profiles can migrate.

Meson generates `compile_commands.json` entries for every real kernel C++ unit,
including the generated include directory and freestanding/profile flags. Run
clangd in the same container or host environment as the build, with matching
source/build/toolchain paths:

```sh
clangd --compile-commands-dir="$PWD/build/gcc16" --query-driver="$(command -v g++)"
```

Allow only that selected trusted driver. The repository `.clangd` removes four
GCC-only code-generation options from editor parsing; it does not change build
flags. Do not copy a container compilation database to unrelated host paths.
Build the selected image first so generated headers exist. Later multi-profile
editing needs an explicit compilation-database/profile selection.

This implementation is not fresh-build, incremental, image, guest or full-suite
qualification. The acceptance gate is a fresh GCC 16 build, exact argv/object
review, no-op and changed-header/import/membership/linker-script/embedded-binary
rebuild checks, parallel sibling isolation, declared-output deletion and failed
build controls, followed by final-source `full`, normal guests and independent
review. Source-only helper controls establish only their stated boundaries.

## Coverage and limits

`full` includes all registered non-LSP tests; `dev` selects fast feedback and
`slow` contains longer cases. `integration` and
`boot` are additional named selections; native `boot` checks/builds images but
never starts QEMU. Keep development quick with `dev` or exact test names; full
package profiles are slow. `packages` selects both partial and full profiles.

All 72 compiler Python runners reachable from legacy root Make are registered.
The 15 newly covered runners are diagnostics, IR exhaustive, method-values ABI,
readonly-windows source/native-IR, short-circuit source/native-IR, source overlays,
token scan, UTF-8 range/lines and XFS geometry/root/root-API/root-entry. Fixed
lexer/IR/ABI and module C++ fixtures are dependency-tracked build targets; the
separate offline XFS verifier is registered. Five explicitly classified
non-root style/supplemental runners still require their separate inputs.

Full package Identity/Manifest/Graph retain respectively 5,503/20, 20,022/29 and
5,548/30 native/rejection cases; dev selections remain 183/20, 157/29 and 187/30.
Both retain output-preservation and native negative controls. Full profiles use
fresh build-local artifacts and the existing 1,024 MiB candidate caps. All 38
non-compiler root prerequisites map to 115 native registrations, preserving
ordinary/optimized Python controls, fault/capacity checks and complex negative
compilation sweeps. See `tests/native/inventory.json` for exact mappings and the
few byte-identical repeated commands deduplicated within a full invocation.

Canonical Meson uses its checked-libstdc++ configuration (`_GLIBCXX_ASSERTIONS`
and large-file definitions); historical Make compiler bytes need not match.
Special native `-O1`, debug, no-PIE, exception/RTTI and testing macros remain where
required; the existing `-O2` framebuffer variants remain distinct. Existing
compiler Python runners use explicit optimized checks rather than Python assert;
ordinary/optimized harness controls remain separate where they test mode behavior.
`tests/test-inventory.py` checks runner/source membership, exact profiles/arguments,
suites, fixtures and native registration contracts. New unaccounted runners fail.

Observed Meson compiler identity never claims an external pin or fresh bootstrap
build. Full native execution still needs independent final-source review; normal
BIOS/UEFI smoke, affected fault/recovery profiles, sanitizers and physical hardware
remain separate gates. Retained receipts/logs remain readable; generated products
can be losslessly archived with exact mapping after review.

## Historical measurements (different source and graph)

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

## Graphical console coverage

The joined graph retains the complete Aurora graphical hosted harness in `slow`,
the paired paging model, both ordinary and optimized admission/image-policy/metadata
controls, and the distinct-service private-ABI runner. Compiler binary-literal
coverage executes through the normal compiler suite. These native tests remain
separate from current-image graphical, failure, timeout and restoration boots.
