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
   normal `slow`, `integration` and native `boot` coverage belongs to `full`.
   Explicit combinatorial library sweeps belong to `exhaustive`, outside normal
   `full`; normal cases retain their documented boundary families and fixed-seed
   samples. Select the whole sweeps when changing their library behavior, oracles
   or sampling contract, and record which tier actually ran. Do not silently
   replace complete regression families with first-N limits.
   Before every merge or release, run complete `full` with GCC 16 on the final
   integrated source, including after conflict resolution. `make test` selects
   the same Meson graph; do not run a second duplicate Make aggregate for credit.
   GCC 14 is optional targeted compatibility evidence, not a routine merge or
   release gate. Preserve historical results with their original source/tool scope.
   Use stable, separate build directories per toolchain/configuration. Ninja
   tracks source/header dependencies; never share a build across changed
   toolchain identities. Use a fresh directory for clean/bootstrap checks and
   whenever toolchain identity or dependency tracking is in doubt. Select matching
   real `gcc`/`g++` tools on PATH as well as `CXX`. Record final source identity,
   compiler/binutils/runtime identities, actual commands and Meson test logs.
   Keep raw Meson logs, failed/interrupted scratch and explicitly kept artifacts.
   The Meson artifact adapter removes only its own new scratch after success;
   use `AURORA_MESON_KEEP_ARTIFACTS=1` when successful scratch is needed for review.
   Whole-directory cleanup uses explicit reviewed CLEAN_PATHS and may remove
   their logs/evidence; stop builds/tests/guests first and use .keep to protect
   retained directories. Never sweep unrelated output automatically.
   A selected-compiler digest is artifact stability, not a fresh-build receipt.
   With GCC 16, also build and smoke normal BIOS and UEFI images. Run
   existing image/admission and emulator gates for each affected kernel profile,
   including applicable fault/recovery cases and a normal restoration boot.
   The native `boot` suite does not run QEMU. Missing tools, skipped gates and
   prior-source results leave the current candidate unqualified. Record the actual
   GCC 16 distribution/version; Debian GCC 16.2.0-3 is not Gentoo 16.2.1 evidence.
   Build predecessors must have the source-bootstrap provenance specified in
   compiler/README.md. Ordinary development may reuse a digest-verified retained
   artifact with matching source/build/tool identities and qualification evidence.
   This artifact route is not a fresh source bootstrap and does not qualify changed
   current source. Fresh seed-route qualification remains required for predecessor
   bumps and fresh source-bootstrap claims; retain the reconstructable route.
   Historical raw-seed/prebuilt receipts retain their original validation meaning;
   legacy execution entrypoints are removed; new execution uses only the native
   Meson graph without reinterpreting those records.
5. Review changes independently before considering a milestone verified. Record
   reproduced defects and fixes, commands, source revision, tool versions and limits.
6. Update implementation docs and the completeness matrix in the same change.
   Each PR must report comparable executed build steps, configured target and
   distinct kernel-image counts, and full-suite wall time, with a reason for any
   growth. Record workload/configuration and actual concurrency; label estimates
   and unavailable measurements rather than substituting historical results.
7. Keep changes reviewable. Use a clean, independently reviewed squash merge so
   work-in-progress checkpoints do not enter main. Do not rewrite existing history.
   Verified functional checkpoints may use ready-for-review pull requests;
   unfinished milestones remain draft, per the user's latest approval.
   Never force-push, merge, or publish a release without the applicable authorization.

## Bootstrap evolution

- Separate language implementation from compiler adoption. New features first
  land with independent library or product consumers; all predecessor-compiled inputs,
  including compiler-imported library code, stay within its supported subset.
- Batch predecessor bumps at milestones or when a justified compiler-adoption
  batch is ready, rather than coupling each feature to a bump. Review the pin,
  complete seed route, supported corpus and adoption together. Retain durable
  immutable checkpoint references and original receipts; changing the active
  route must not rewrite their meaning or remove reconstructable source history.
- Keep the build predecessor and historical C++ emitter oracle independently
  identified. A newer bootstrap compiler must not silently replace the independent
  old-backend comparison. Do not demote historical corpus coverage to hide a
  rejection or regression.
- Cached predecessors are provenance-checked conveniences, not trust anchors or
  evidence of chain shortening. Shorter source routes require the direct-build
  and cross-route gates in compiler/README.md. Final-source full, image/emulator
  qualification and independent review requirements above remain unchanged.

## Validation

- meson test -C build/meson --suite core --num-processes 2: focused frontend,
  class/value, integer, module/depth and initialization checks, incrementally built
- meson test -C build/meson --suite bytes --num-processes 2: complete byte/storage runners
- meson test -C build/meson --suite packages --num-processes 4: partial and full package profiles
- meson test -C build/meson --suite dev --num-processes 2: quick cross-component feedback
- meson test -C build/meson --suite slow --num-processes 2: longer integration/ABI sweeps
- meson test -C build/meson --suite full --num-processes 2: normal full non-LSP regression coverage
- meson test -C build/meson --suite exhaustive --num-processes 2: complete combinatorial library sweeps, not a replacement for full
- make test: incremental compile then the complete normal Meson `full` suite;
  `MESON_BUILD_DIR`, `AURORA_BUILD_JOBS` and `AURORA_TEST_JOBS` are configurable
- make test-exhaustive: incremental prerequisites then the separate `exhaustive` suite
- make -C compiler test: complete compiler-only scope, not the root full aggregate
- make smoke: real QEMU normal boot
- make smoke-fault: real fail-stop exception injection (see scripts for modes)
- SANITIZE=1 ./scripts/kernel-tests.sh: hosted allocator sanitizers/model tests

Read [development and qualification](docs/developer-test-contract.md) before
changing test routing. Normal development uses the incremental Meson graph;
historical receipts remain readable while new execution uses Meson. Full aggregates
and acceptance reject coverage-reducing overrides. Focused and compiler-free
checks do not establish root native acceptance. There is no established pinned
CI replacement for this policy; retain these gates until that mechanism is real.

For ordinary feature changes, aim for roughly 2x verification/review effort
relative to implementation effort, excluding compiler/IR safety work. This is a
planning budget, never permission to skip safety or final merge gates. Explain a
justified overrun before expanding scope. Reuse existing test and component docs;
keep the completeness matrix a status table, with historical results in Git/PRs
and retained run/CI evidence rather than new per-feature reports.

Missing tools or blocked tests must be reported as such, never silently passed.
Do not install this experimental kernel on physical hardware or modify a host
bootloader. Keep secrets, downloaded third-party executables and build products
out of the repository. No licenses or legal commitments should be invented.

## Scope and status

The user accepts a long-term project and wants tested milestone updates, material
decisions and blockers. Preserve work in the repository and leave a precise next
step. Do not call the full language, distribution or AMD support complete until
the relevant acceptance gates have actually passed.
