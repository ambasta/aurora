# Aurora development contract

Aurora is a clean-slate, safe systems-language and operating-system project.
The language is an intentionally incompatible safe C++ dialect, not a Rust-syntax
replacement. Priorities are extreme safety, modern/elegant design, then measured
performance comparable to equivalent C implementations.

The destination is a self-hosting distribution with native toolchain, libraries,
package management, drivers, services, desktop, and utilities. It is not a C/C++
compatibility layer. Read README.md and docs/completeness-matrix.md first.

## Design requirements

- Preserve a modern, class-based language surface. Do not add struct declarations,
  C headers/macros, unchecked pointer escape hatches, or a C ABI to Aurora itself.
- Class values must not require heap allocation. Resource ownership, borrowing,
  initialization and lifetime rules must be explicit and tested.
- Reflection must not bypass type, lifetime, visibility, or capability checks.
  The target includes TypeScript-style type-level transformations, compile-time
  reflection, and runtime reflection, with no unchecked assertions or any loophole.
- Preserve C++-recognizable APIs, class privacy and strong encapsulation. Java-like
  object design does not imply forced boxing, heap allocation or a mandatory GC.
- Prefer checked operations and explicit failures to undefined behavior. Optimize
  away a safety check only with a valid proof of its preconditions.
- Temporary host C++/assembly adapters are bootstrap machinery, not the final
  language or a claim that the kernel is written in Aurora already.
- Hardware qualification targets every Zen generation and Navi/RDNA onward,
  including integrated/discrete devices where applicable. A QEMU boot does not
  establish support for a physical AMD device.
- Keep the trusted computing base small and explicit. Never equate a set of tests
  with a proof of Rust-equivalent memory safety or production security.

## Workflow

1. State the next dependency and observable acceptance gate before adding a feature.
2. Implement running mechanisms, not unused scaffolding presented as functionality.
3. Add positive, negative, regression and adversarial tests. Check metadata against
   actual generated layout/behavior. Fail closed for unsupported syntax/semantics.
4. Run dependency-selected focused checks while developing. Keep `dev` fast;
   complete `slow`, `integration` and native `boot` coverage belongs to `full`.
   Before every merge, run complete `full` on the final integrated source,
   including after conflict resolution. Compiler- or kernel-affecting merges and
   releases require separate GCC 14 and GCC 16 full runs. `make test` selects the
   same Meson graph; do not run a second duplicate Make aggregate for credit.
   The current Meson-completion migration remains unqualified until both new
   graphs pass independent source/coverage review and execution.
   Use stable, separate build directories per toolchain/configuration. Ninja
   tracks source/header dependencies; never share a build across changed
   toolchain identities. Use a fresh directory for clean/bootstrap checks and
   whenever toolchain identity or dependency tracking is in doubt. Select matching
   real `gcc`/`g++` tools on PATH as well as `CXX`. Record final source identity,
   compiler/binutils/runtime identities, actual commands and Meson test logs.
   A selected-compiler digest is artifact stability, not a fresh-build receipt.
   For both toolchains, also build and smoke normal BIOS and UEFI images. Run
   existing image/admission and emulator gates for each affected kernel profile,
   including applicable fault/recovery cases and a normal restoration boot.
   The native `boot` suite does not run QEMU. Missing tools, skipped gates and
   prior-source results leave that toolchain unqualified.
   Separately pinned bootstrap compatibility remains available through
   `make test-acceptance ACCEPTANCE_COMPILER_SHA256=<reviewed digest>` and its
   existing matching `run.json` contract. It is not an additional mandatory
   duplicate native graph unless that distinct workflow is the change under test.
5. Review changes independently before considering a milestone verified. Record
   reproduced defects and fixes, commands, source revision, tool versions and limits.
6. Update implementation docs and the completeness matrix in the same change.
7. Keep changes reviewable. Use a clean, independently reviewed squash merge so
   work-in-progress checkpoints do not enter main. Do not rewrite existing history.
   Verified functional checkpoints may use ready-for-review pull requests;
   unfinished milestones remain draft, per the user's latest approval.
   Never force-push, merge, or publish a release without the applicable authorization.

## Validation

- meson test -C build/meson --suite core --num-processes 2: focused frontend,
  class/value, integer, module/depth and initialization checks, incrementally built
- meson test -C build/meson --suite bytes --num-processes 2: complete byte/storage runners
- meson test -C build/meson --suite packages --num-processes 4: partial and full package profiles
- meson test -C build/meson --suite dev --num-processes 2: quick cross-component feedback
- meson test -C build/meson --suite slow --num-processes 2: longer integration/ABI sweeps
- meson test -C build/meson --suite full --num-processes 2: all registered non-LSP tests (see Meson introspection)
- make test: incremental compile then the complete Meson `full` suite;
  `MESON_BUILD_DIR`, `AURORA_BUILD_JOBS` and `AURORA_TEST_JOBS` are configurable
- make test-acceptance ACCEPTANCE_COMPILER_SHA256=<reviewed digest>: explicitly
  pinned root native graph; optional ACCEPTANCE_COMPILER selects a reviewed prebuilt
- make -C compiler test: complete compiler-only scope, not the root full aggregate
- make smoke: real QEMU normal boot
- make smoke-fault: real fail-stop exception injection (see scripts for modes)
- SANITIZE=1 ./scripts/kernel-tests.sh: hosted allocator sanitizers/model tests

Read [the developer-test contract](docs/developer-test-contract.md) before changing
test routing or interpreting its receipts. The exact PR26-based revision-5 full
public developer and prebuilt-acceptance native workflows have independent review;
see docs/developer-test-workflow-results.md for their source and evidence scope.
The original developer outer audit failure remains preserved with a separately
accepted composite. Gentoo make-test, new sanitizer/emulator runs and broad-host
qualification remain separate. Ordinary developer builds require no historical
binary pin. Explicit independently supervised pins
remain supported. Full aggregates/acceptance reject coverage-reducing overrides;
focused and compiler-free diagnostic runs do not establish root native acceptance.

Missing tools or blocked tests must be reported as such, never silently passed.
Do not install this experimental kernel on physical hardware or modify a host
bootloader. Keep secrets, downloaded third-party executables and build products
out of the repository. No licenses or legal commitments should be invented.

## Scope and status

The user accepts a long-term project and wants tested milestone updates, material
decisions and blockers. Preserve work in the repository and leave a precise next
step. Do not call the full language, distribution or AMD support complete until
the relevant acceptance gates have actually passed.


## Current bounded library checkpoint: ASCII token scanner

`std.token_scan` now implements a bounded final-window readonly ASCII scanner with
copied reports and no escaped source view. The fresh complete root release native
graph and a separate focused fatal host compiler/lexer sanitizer gate passed
independent review. Preserve the exact scope, original failed diagnostic fixture
run, fresh corrected replay and dated sanitizer-scope amendment in
[the results](docs/token-scan-results.md). Generated Aurora assembly is unsanitized;
leak checks and complete compiler sanitizer regression are not claimed.
Further parser/text consumers, owned strings and self-hosting need separate
contracts; no new compiler semantics, kernel or hardware qualification is implied.
