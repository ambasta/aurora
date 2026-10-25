# Development and qualification

[AGENTS.md](../AGENTS.md) sets the rules: a cost budget proportional to Linux and
GCC, tests written as one compiled driver per component with cases as data, and
no tests of tests. This page says how to run things today.

## Commands

`make test` runs the merge suite and `make test-release` the release suite.
`full` remains the union of the two for older scripts.

```sh
./scripts/container.sh bash           # pinned GCC 16 / QEMU / OVMF environment
meson setup build/meson -Dbootstrap_compiler=... -Duefi_ld=...
make test                            # nproc build/test jobs with memory watchdog
make test-release                    # opt-in: releases and compiler bumps
```

Guest smokes run QEMU through `scripts/kernel-uefi-smoke.sh MODE`,
`scripts/kernel-smoke.sh` (BIOS) and `scripts/kernel-run.sh`; the fixture modes are
the rows of `kernel/uefi/runtime-fixtures.inc`. The UEFI guest families are Meson
tests outside `full`: `meson test --suite guest` runs all of them and
`--suite guest-<family>` one family (`uefi`, `acpi`, `pci`, `runtime`, `ipc`,
`budget`, `dispatch`, `user-phases`, `tables`, `pins`; listed in
`scripts/kernel_profiles.py`). `scripts/kernel-run.sh bar|ivrs` boots the BAR and
IVRS device families.

## Kernel image checks

Every kernel profile build runs two checks, like objtool and modpost, and fails
the build on a violation:

- `scripts/kernel_stack_check.py` builds one call graph per linked image from the
  stack facts the compilers emit (GCC `.su`/`.ci`, Aurora `.stack.json`); only
  handwritten assembly is decoded instruction by instruction. It rejects call
  cycles, undeclared indirect calls and compiled transfers without a compiler
  edge, and bounds the entry path plus the worst interrupt, every interrupt
  window (functions with STI) and every user trap entry by one limit per image
  (`stack_cap`, 15360 bytes, in `kernel/bootstrap-layout-values.inc`).
- `scripts/kernel_image_check.py` checks PE32+ and ELF format and W^X, entry in
  an executable section, no imports, DIR64-only PE relocations, PC-relative
  payload objects and no undefined symbols.

Both read `kernel-images/image-policy.py`, the declarative per-profile table of
the runtime symbols each Aurora object may import, the policy entry points the
supervisor must call, forbidden symbols, reviewed callbacks and user-mode trap
vectors. Page permissions, relocation application, payload bounds and user
image trap sites are verified again by the kernel itself at load time
(`kernel/uefi/loader.cpp`, `payload.cpp`, `runtime.cpp`, `user-program.cpp`).

## Gates

| When | What |
| --- | --- |
| Development | incremental build, focused tests; a native host build directory is fine for feedback |
| Every merge | pinned container, final source: build, merge suite, the guest families the change touches, normal BIOS and UEFI smokes |
| Releases, compiler bumps | release suite, every guest family; a bump is one checkpoint hop ([compiler/README.md](../compiler/README.md#bumping-the-checkpoint-one-hop)) |

Report fresh-build and merge-suite wall time at full concurrency next to the
previous main. Missing tools or skipped gates are reported, never passed.

## Where tests live

The release suite holds IR mutation testing (`ir-exhaustive`) and the complete
copies of subset tests; everything else is in merge. There are no test inventories, oracle
self-tests or compiler-identity pins.

Compiler-semantics runners in `tests/compiler` register cases as data on
`native_runner.Suite`: accepted cases are packed into one compiled program per
test (more only past the 1 MiB source limit, a per-graph compiler budget, or a
differing import/module set), value cases run in one exec, each trap is one
exec of the same binary selected by argv, and each rejection is one compile.
Hosted owner programs use the same packing through `owned_bytes.Suite`
(`deferred=True`).

Library-behaviour tests (`token-scan`, `utf8*`, `json-*`, `package-*`) compile one
driver per library surface. `tests/compiler/runtime_records.py` checks the
driver's record layout and entry ABI against aurorac's ABI facts, links it once
with `runtime_records_host.cpp` and streams every case through one process as a
fixed-size record; owned-bytes surfaces use `hosted_records.py`, which packs
their fixtures into one module linked with the hosted byte runtime and streams
runs as rows. Expected values come from Python's standard library (json, the
UTF-8 codec, int/str) or from reviewed golden files in `tests/compiler/golden/`
frozen from the former models; rejections are compiled one source each.

Kernel and service observers are Meson executables linked once with their
generated Aurora objects (`scripts/meson-native-fixture.py` compiles, bridges and
assembles each root as a dependency-tracked custom target). `tests/golden.py`
compares a driver's stdout, each `mode` of a multi-mode program, or each
rejected source's exact diagnostic with the golden file beside it (`--update`
rewrites it for a reviewed change). Policy observers print per-family digests
and histograms of their full-width vector families (`tests/policy-vectors.hpp`).
C++ test-configuration guards are one-line compile-fail cases in
`tests/kernel-compile-fail.txt`.

Hand-built IR is data: `.air` case files under `tests/compiler/ir`, one Meson
test per directory, run by the single `aurora-ir-check` driver (format and
directives in [tests/compiler/ir/README.md](../tests/compiler/ir/README.md)).
A new verifier or emitter case is a few lines of module text with its expected
diagnostic or CHECK lines, not a C++ translation unit. The large native-ABI
programs that loop over call shapes are generated at build time by
`tests/compiler/ir/abi_programs.py` rather than stored. Only owner, view, writer
and emitter-object API tests remain C++ (`tests/compiler/ir_api.cpp`).
