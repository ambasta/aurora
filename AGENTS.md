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

## Cost budget

Build and test cost must be proportional to the project's size, judged against
Linux and GCC. A Linux defconfig compiles a few million lines in roughly 80-120 s
on 8 cores; this repository compiles about 25x less. On the 8-vCPU development
instance:

- a fresh build must finish in 60 s or less, and an incremental rebuild after a
  one-file change in seconds;
- the merge suite (`meson test --suite merge`) must finish in 60 s or less;
- the release suite (`--suite release`) is opt-in and runs before releases and
  compiler bumps, not on every merge.

Every change that touches the build or tests reports fresh-build and merge-suite
wall time next to the previous main, measured at full concurrency. Growth needs a
stated reason; over-budget changes do not merge without the user's approval.
Use every core: build and test at `nproc` jobs, bounded by a MemAvailable
watchdog rather than a low fixed job count.

## How tests are written

Match how Linux, GCC and LLVM test themselves. Anything beyond that needs a
stated safety reason; more checking is not a reason by itself.

- One compiled driver per component. Cases are data: small input files with
  their expected output beside them (golden files, LLVM lit style), fed to one
  driver that is compiled once and run over all cases in parallel. Never
  generate and compile a program per case or per batch of cases.
- Expected values come from a standard-library reference or a reviewed golden
  file. Do not reimplement the code under test in another language as its oracle.
- No tests of tests: no inventories that pin other tests' command lines, no
  self-tests or negative controls for oracles, no controls for controls, no
  fake-tool routing tests for developer scripts.
- Properties such as stack bounds, page permissions, W^X and entry/exit integrity
  are proved by compiler facts emitted with the code and by the kernel's own
  load-time checks, inside the build (like objtool/modpost). Do not pin exact
  instruction sequences, addresses or digests that legitimate code generation
  or layout changes must then re-pin.
- One production kernel configuration per supported target. Fault and hostile
  cases are boot-selected fixtures in a few test images, not separate builds.
- Fixtures and hosted test drivers are not performance-critical: build them
  unoptimized unless a test needs optimized code.
- Python is for orchestration and small generators only. Checks that cost real
  time belong in C++ or Aurora.
- A check may move (separate image to fixture, script to compiler facts or
  load-time verification) when the change names where the property is now
  enforced and a test still covers it. Deleting duplicated or meta checking
  needs no replacement.

## Workflow

1. State the next dependency and its observable acceptance before adding a feature.
2. Implement running mechanisms, not unused scaffolding presented as functionality.
3. Add positive, negative and regression tests in the style above. Fail closed for
   unsupported syntax/semantics.
4. Develop with incremental builds and focused tests. Before a merge, run the
   merge suite with GCC 16 in the pinned container on the final source, the guest
   families the change affects, and the normal BIOS and UEFI smokes. Release suite
   and every guest family run before releases and compiler bumps.
5. The pinned container (`scripts/container.sh`: Debian GCC 16, pinned QEMU, OVMF
   and test tooling under /opt) is the reference for merge evidence. Native host
   builds are fine for fast development feedback in their own build directory;
   never share a build directory across toolchains.
6. Bootstrap: one verified checkpoint compiler builds C1, C1 builds C2, and C1/C2
   convergence is the self-check, like GCC's stage compare. New compiler features
   are adopted at scheduled bumps; the historical-oracle corpus differential runs
   at bumps, not on every merge. See compiler/README.md.
7. Review changes independently before merge. Record commands, tool versions,
   timings and limits in the commit or PR, not in new per-feature report files.
8. Update implementation docs and the completeness matrix in the same change.
   Keep docs short; history lives in Git.
9. Use clean squash merges so work-in-progress checkpoints do not enter main.
   Do not rewrite existing history and never force-push.

## Limits

Missing tools or blocked tests must be reported as such, never silently passed.
Do not install this experimental kernel on physical hardware or modify a host
bootloader. Keep secrets, downloaded third-party executables and build products
out of the repository. No licenses or legal commitments should be invented.

## Scope and status

The user accepts a long-term project and wants tested milestone updates, material
decisions and blockers. Do not call the full language, distribution or AMD support
complete until the relevant acceptance gates have actually passed.
