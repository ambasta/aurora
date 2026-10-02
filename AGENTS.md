# Aurora development contract

Aurora is a clean-slate, safe systems-language and operating-system project.
The destination is a self-hosting distribution with native toolchain, libraries,
package management, drivers, services, desktop, and utilities. It is not a C/C++
compatibility layer. Read README.md and docs/completeness-matrix.md first.

## Design requirements

- Preserve a modern, class-based language surface. Do not add struct declarations,
  C headers/macros, unchecked pointer escape hatches, or a C ABI to Aurora itself.
- Class values must not require heap allocation. Resource ownership, borrowing,
  initialization and lifetime rules must be explicit and tested.
- Reflection must not bypass type, lifetime, visibility, or capability checks.
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
4. Run make test and actual emulator gates for kernel-affecting changes. Fault
   injection gates must fail as intended and restore a normal image afterward.
5. Review changes independently before considering a milestone verified. Record
   reproduced defects and fixes, commands, source revision, tool versions and limits.
6. Update implementation docs and the completeness matrix in the same change.
7. Keep changes reviewable and use draft pull requests for subsequent milestones.
   Never force-push, merge, or publish a release without the applicable authorization.

## Validation

- make test: compiler execution/rejection, image and hosted kernel checks
- make smoke: real QEMU normal boot
- make smoke-fault: real fail-stop exception injection (see scripts for modes)
- SANITIZE=1 ./scripts/kernel-tests.sh: hosted allocator sanitizers/model tests

Missing tools or blocked tests must be reported as such, never silently passed.
Do not install this experimental kernel on physical hardware or modify a host
bootloader. Keep secrets, downloaded third-party executables and build products
out of the repository. No licenses or legal commitments should be invented.

## Scope and status

The user accepts a long-term project and wants tested milestone updates, material
decisions and blockers. Preserve work in the repository and leave a precise next
step. Do not call the full language, distribution or AMD support complete until
the relevant acceptance gates have actually passed.
