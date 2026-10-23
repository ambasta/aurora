# Development and qualification

[AGENTS.md](../AGENTS.md) sets the rules: a cost budget proportional to Linux and
GCC, tests written as one compiled driver per component with cases as data, and
no tests of tests. This page says how to run things today.

## Commands

```sh
./scripts/container.sh bash           # pinned GCC 16 / QEMU / OVMF environment
meson setup build/meson -Dbootstrap_receipt=... -Duefi_ld=...
ninja -C build/meson -j"$(nproc)"
meson test -C build/meson --suite merge --num-processes "$(nproc)"
meson test -C build/meson --suite release --num-processes "$(nproc)"   # opt-in
```

Guest smokes run QEMU through `scripts/kernel-uefi-smoke.sh MODE`,
`scripts/kernel-smoke.sh` (BIOS) and `scripts/kernel-run.sh`; the fixture modes are
the rows of `kernel/uefi/runtime-fixtures.inc`.

## Gates

| When | What |
| --- | --- |
| Development | incremental build, focused tests; a native host build directory is fine for feedback |
| Every merge | pinned container, final source: build, merge suite, the guest families the change touches, normal BIOS and UEFI smokes |
| Releases, compiler bumps | release suite, every guest family, bootstrap reseed checks in [compiler/README.md](../compiler/README.md) |

Report fresh-build and merge-suite wall time at full concurrency next to the
previous main. Missing tools or skipped gates are reported, never passed.

## Transition

The test tree still predates these rules: most of `full` is per-batch generated
programs, Python reimplementation oracles, admission scripts and meta-tests, and
it takes about 14 minutes. Until the merge suite exists, `full` remains the merge
gate. The rewrite replaces it with data-driven drivers, deletes the meta-tests,
admission pins and provenance pins, and moves the corpus differential to the
release suite.
