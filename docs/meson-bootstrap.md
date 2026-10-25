# Canonical incremental native tests

Meson/Ninja is the canonical complete native graph. Every merge requires the
`merge` suite, and every release or compiler bump the `release` suite, on the
final integrated source with GCC 16 (`full` is their union),
plus the separate applicable image and actual guest gates. GCC 14 is optional
targeted compatibility evidence. Previous snapshots do not qualify a new tree.

## Build and run

Use the supported pinned development container. Advanced native use must match
its exact pinned tools: GCC 16.2.0, GNU binutils 2.47, Meson 1.12.1 and Ninja
1.13.2, with Python 3.10+ on a GNU/Linux x86-64 host.
Select matching real `gcc` and `g++` on PATH: a stack-guard
runner invokes bare `gcc`. Keep one stable build directory per toolchain/configuration:

```sh
# C0 is a local copy of the executable pinned by compiler/checkpoint.json.
# PATH must already select the matching GCC 16 pair.
CXX=g++ meson setup build/gcc16 --backend=ninja -Dlsp=false \
  "-Dbootstrap_compiler=$C0"
export MESON_BUILD_DIR=build/gcc16
# Optional quick feedback while developing; merge below includes these tests.
meson test -C build/gcc16 --suite dev
make test
make test-release  # opt-in: releases and compiler bumps
```

These commands build prerequisites and run tests at `nproc` concurrency under
the memory watchdog described below. Do not mutate an image profile while its
artifacts are in use.

Ninja tracks C++ headers and Aurora fixture imports. Unchanged compiler/fixture
builds are reused, but test outcomes are not cached. A different toolchain or flag
configuration needs a separate directory. The Make shortcuts check the selected
compiler, binutils, Meson and Ninja versions before setup or build work, with a
short blocked reason and the container command when tools are unsupported.
Direct Meson setup checks the same tool versions.
Missing or unsupported tools are blocked. Checkpoint admission verifies the
pinned executable digests at configure time; after replacing tools in place,
configure a fresh build directory. Unset `CPATH`, `CPLUS_INCLUDE_PATH`, `C_INCLUDE_PATH` and
`LIBRARY_PATH`, including empty definitions; use explicit Meson include/link flags
instead. Use a clean directory for bootstrap
compatibility or uncertain dependency identity. Do not modify inputs while
qualifying. Record final source/tool identities and Meson's standard commands,
introspection and logs; no new qualification supervisor is introduced.

Test drivers take scratch from Python's `tempfile` beneath the build directory
(`TMPDIR`) and remove it after a pass. Several, including the emitter
differential and `kernel-uefi-smoke.sh --run-only` without `--output-dir`, print
its path and keep it after a failure.
For disk reclamation, `meson compile -C build/gcc16 --clean` removes tracked
build products while keeping configuration/logs. Retire whole directories only
through the [explicit per-directory cleanup steps](local-development.md#reclaiming-old-local-output-explicitly);
never sweep historical, failed, kept or user-owned review output automatically.

`make test` invokes the same `merge` selection; `make test-release` selects `release`. `make -C compiler test` and
`scripts/compiler-test.sh` select `compiler`. Set `MESON_BUILD_DIR` to a
matching checkpoint-configured directory, or omit it for `build/meson` (normal
image-enabled work) or `build/meson-compiler` (hosted-only compiler work).
First configure these directories with the checkpoint and oracle paths using the
[source-bootstrap recipe](../compiler/README.md#source-bootstrap). A missing
checkpoint selection rejects with that recipe rather than creating a raw seed.
The shortcuts stop on build/test failure and reject mismatched compiler/flag
selections or missing project options. Reconfigure an older chosen build
explicitly with the `-Dbootstrap_compiler` option, or configure a fresh matching directory.
The wrapper does not invent a checkpoint or automatically migrate configurations.

Focused checks use exact Meson test names rather than compiler-consuming Make
aliases. For example, in a configured compiler build:

```sh
meson test -C build/meson-compiler --suite compiler
meson test -C build/meson-compiler hosted-lexer-format hosted-lexer-format-cli
meson test -C build/meson-compiler semantic-lint
meson test -C build/meson-compiler modules source-depth host-sources-tests host-output-tests
meson test -C build/meson-compiler short-circuit short-circuit-ir short-circuit-ir-native
meson test -C build/meson-compiler --list
```

`make clean` still preserves configuration.
Make targets and `scripts/bootstrap.py hop` run Meson at `nproc` jobs under
`scripts/watchdog.sh`. It runs the command in its own process group and stops
the group (TERM, then KILL after two seconds) when MemAvailable falls below
`AURORA_MEMORY_RESERVE_MIB` (default 2048). It is a best-effort guard, not
memory containment: other processes can allocate between samples. A stopped run
fails; it never counts as passing. The container wrapper forwards
`MESON_BUILD_DIR`, `MESON_TESTTHREADS` and `AURORA_MEMORY_RESERVE_MIB`.
The obsolete legacy acceptance executor gives a migration error; historical
receipts remain readable without being reinterpreted as current Meson results.

## Native kernel images

`kernel-bios-normal` and `kernel-uefi-normal` are real Meson/Ninja image graphs.
They compile the trusted kernel C++ translation units as native targets, then
use explicit Aurora, GNU assembler, linker, metadata and image edges. No image
target calls either shell builder. Their output directories are respectively
`<build>/kernel-images/bios/normal` and `<build>/kernel-images/uefi/normal`.
The independent BIOS and UEFI image tests read those outputs without rebuilding
or rewriting them; all existing negative image controls remain active.

```sh
MESON_BUILD_DIR=build/gcc16 make kernel
MESON_BUILD_DIR=build/gcc16 make kernel-uefi
meson test -C build/gcc16 native-bios-image native-uefi-normal-image
```

`make` / `make all` builds the normal BIOS image and copies the Meson compiler
to the compatible `build/aurorac` path. `make kernel`
keeps all outputs isolated; `make compiler` also enters the configured Meson
graph and retains its documented compatibility compiler output.

Both normal images are also default build products. BIOS and UEFI have distinct
object/generated-file owners and can build together in one Ninja invocation.
Thin kernel build, smoke and console launchers select a named native Meson
profile and use its returned build-local image directory. Normal and specialized
outputs coexist, so changing profiles requires no shared-image restoration build.
The configuration driver accepts `--kernel bios|uefi --profile NAME
--print-image-dir`; an explicit `AURORAC` selects the compiler through that same
graph. `compile_commands.json` covers each native C++ profile. Qualification
workflows that require a final normal guest boot still boot the separate normal
image and retain fresh logs. Registration and source routing do not establish
final-source pinned-container GCC 16 merge or affected guest qualification.

Kernel flags remain fixed to the admitted freestanding GCC profile. Global
`cpp_args`, `CXXFLAGS` or `CPPFLAGS` are rejected in image-enabled configurations rather than silently adding
hosted instrumentation or profile defines. Native targets disable unity, LTO,
sanitizers, PGO and debug-STL additions. BIOS stays non-PIE; UEFI payload stays
PIE/hidden and its loader retains the Microsoft-ABI outgoing-argument option.
For hosted-only compiler or sanitizer configurations, pass `-Dkernel_images=false`
to a separate Meson setup. That configuration accepts explicit hosted flags and
does not probe the PE linker. The source-bootstrap recipe selects this option
for the separate compiler-only default directory; an explicitly supplied image-enabled build
can still be reused with matching compiler/flags. The two normal
image tests remain registered and fail clearly in `full`/`boot`, including with
`--no-rebuild`; disabled images cannot yield a qualified full pass.

With images enabled (the default), a GNU PE linker with `i386pep` is a setup
requirement, including for BIOS-only target selection. Select it through
`-Duefi_ld=/path/to/ld` or `UEFI_LD` with Make. Its version is checked during
setup, and the convenience wrapper rejects a configured linker-path mismatch.
Changing the toolchain or selected linker requires a separate configuration.

C++ headers use native compiler depfiles. Aurora generation conservatively tracks
all `.au` files and directory membership under each supplied module root, so
adding an ambiguous module also invalidates the target. Source/module paths keep
their lexical identity for the compiler's no-symlink checks. Linker scripts,
embedded binaries, generated headers and validators are explicit dependencies.
Private service bridges are assembled with their generated Aurora assembly in
the same invocation, preserving local-symbol access. Each Aurora generation edge
declares assembly and stack/call facts as paired outputs from one successful
compiler invocation.

The native object export preserves the actual object and its same-compilation
`.su` (and UEFI `.ci`) bytes under stable logical names. A small `.source.json`
records the full translation-unit path, compiler working directory and native
sidecar paths; it does not claim image admission. There is no second metadata
compile or basename-only matching. Missing native sidecars fail the export:
remove the affected native object and rebuild it with its sidecars, or use a
fresh build directory. Deleting an exported declared output reruns its owner.
Specialized stack validators resolve source locations against that recorded
compiler directory and verify the original native exports before staging.

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
Build the selected image first so generated headers exist. For files compiled
under multiple profiles, select the intended compilation-database entry/profile.

This implementation is not fresh-build, incremental, image, guest or full-suite
qualification. The acceptance gate is a fresh GCC 16 build, exact argv/object
review, no-op and changed-header/import/membership/linker-script/embedded-binary
rebuild checks, parallel sibling isolation, declared-output deletion and failed
build controls, followed by final-source `merge`, normal and affected guests and independent
review. Source-only helper controls establish only their stated boundaries.

## Coverage and limits

Use `meson test -C BUILD --list` or Meson introspection for the current registration set. `integration` and
`boot` are additional named selections; native `boot` checks/builds images but
never starts QEMU. Keep development quick with `dev` or exact test names; full
package profiles are slow. `packages` selects both partial and full profiles.

`make test` selects `merge`. `make test-exhaustive` selects the separate
`exhaustive` suite through the same incremental wrapper and resource policy;
direct Meson selection is `meson test -C BUILD --suite exhaustive`.
The `utf8` registration (decoding, validation and encoding of `std.utf8`)
streams every case as a record through one compiled driver. Its normal profile
keeps documented boundary cases and fixed-seed scalar/two-byte samples; the
separate `utf8-exhaustive` registration uses `--profile exhaustive` and
preserves the whole scalar/byte spaces with the same driver, oracles and
rejection family. The normal scalar set has 1,084 values; decoding has 1,277
two-byte inputs. Seed 220104 supplements explicit transition boundaries. All
256 single-byte inputs, 24,200 longer decoder boundary inputs and all 2,048
surrogate rejections remain in normal full. Exhaustive adds all 65,536 decoder
two-byte inputs and a native sweep of every code point, whose encodings are
compared with Python's strict encoder through per-plane fingerprints.
Sector-window and XFS coverage remains complete in normal full after batching;
IR safety, package and other complete regression families are not demoted.
Run relevant whole sweeps when changing their algorithms, oracles or sampling
contract. An exhaustive-only pass is not a full pass. Unfiltered Meson runs both
tiers, so select a suite explicitly for normal development.

Compiler Python runners selected by root Make's Meson forwarding and the fixed lexer/IR/ABI and
module C++ fixtures are registered in the canonical graph. The offline XFS
verifier is registered too. Explicitly classified supplemental/style runners
still require their separate inputs; inspect the current inventory for scope.

Full package Identity/Manifest/Graph retain respectively 5,503/20, 20,022/29 and
5,548/30 native/rejection cases; dev selections remain 183/20, 157/29 and 187/30.
Both retain output-preservation and native negative controls. Full profiles use
fresh build-local artifacts and the existing 1,024 MiB candidate caps. Native Meson registrations preserve
ordinary/optimized Python controls, fault/capacity checks and complex negative
compilation sweeps.

Canonical Meson uses its checked-libstdc++ configuration (`_GLIBCXX_ASSERTIONS`
and large-file definitions); historical Make compiler bytes need not match.
Special native `-O1`, debug, no-PIE, exception/RTTI and testing macros remain where
required; the existing `-O2` framebuffer variants remain distinct. Existing
compiler Python runners use explicit optimized checks rather than Python assert;
ordinary/optimized harness controls remain separate where they test mode behavior.

Observed Meson compiler identity never claims an external pin or fresh bootstrap
build. Full native execution still needs independent final-source review; normal
BIOS/UEFI smoke, affected fault/recovery profiles, sanitizers and physical hardware
remain separate gates. Retained receipts/logs remain readable; generated products
can be losslessly archived with exact mapping after review.

## Bootstrap stages

One pinned checkpoint compiler C0 builds C1 (`aurorac`); C1 builds C2
(`aurorac-stage2`); `hosted-lexer-bootstrap` requires C1/C2 convergence, like
GCC's stage compare. `compiler/checkpoint.json` pins C0 by digest. A bump is one hop
(`scripts/bootstrap.py hop`): build an accepted main commit with the current C0,
check C1/C2 convergence, record its C2 as the new pin. The
six-stage route that produced the first checkpoint is a record in
`compiler/bootstrap-history.json`; see the
[source-bootstrap recipe](../compiler/README.md#source-bootstrap) for both.
