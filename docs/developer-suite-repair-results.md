# Developer-suite and tooling repairs — 2026-10-08

Focused qualification starts from accepted main
`36219aef05cf74db710b50fae9011190f3bfcee1`, tree
`d1acfbd64ca74af747f8bdf5faa19cfc85bd2f87`.
The [aggregate qualification](../evidence/developer-suite-repair/qualification.json)
records exact suite membership, timings, compiler identities and public Make gates.
Raw test products, rejected attempts and independent reviews are retained outside
the repository. This is not a fresh root `make test` or full-native qualification.

## Root causes and bounded corrections

- Eight package rejection expectations still described pre-owned-byte syntax.
  The three package runners now expect current class-storage and borrow-origin
  wording. All 79 negative source programs, labels, rejection predicates and
  existing-output preservation controls are unchanged. Three corpus hash pins
  were refreshed only after reversing those two wording changes reproduced every
  original reviewed hash; native cases, expected vectors and shared observers
  were unchanged.
- The hosted ownership bridge repeated the compiler-owned GNU-stack directive.
  Genuine GNU assembler 2.47 emits two warnings for that duplicate; 2.44 does not.
  The bridge now relies on the compiler's single note. Both shared composition
  paths require exactly one canonical non-executable note; missing, duplicate,
  executable and mixed canonical/executable controls reject even under Python
  optimization. Empty-stderr assertions remain unchanged. Independent real
  host linking is quiet and ELF GNU_STACK remains RW, without execute permission.
- The formatter treats `::` qualification as an indivisible token run when it
  chooses a wrap point. The standalone formatter and shared formatting adapter
  were reviewed; the joined public formatter gate passed. The compiler's
  executable generation does not include `format.hpp`, and Ninja reported no
  compiler rebuild after composition; its verified artifact identity is unchanged.
- The [NVMe preparation repair](smoke-entrypoint-repair.md) classifies unavailable
  external prerequisites as BLOCKED while malformed selectors, wrong-kind or
  non-executable explicit paths, bad images, pin failures and post-start errors
  remain FAIL. Validation and no-device authority are preserved. These are
  preflight/stub controls, not evidence of an actual guest or device operation.

## Developer feedback and complete registered coverage

Nine existing longer integration/ABI runners move from `dev` to `slow`:
block-io, sector-window, xfs-sector, xfs-file, method-spans-abi, json-profile,
json-codecs, json-integers and json-lookup. The other 38 tests stay in `dev`,
including json-owned and all three partial package profiles. Existing core,
bytes, compiler and packages memberships are preserved. No test command,
argument, environment override, timeout or assertion is removed or weakened.

Both `--suite full` and unfiltered Meson retain all 47 non-LSP tests. The new
`dev` and `slow` suites are a disjoint complete partition. See the
[commands and selection guidance](meson-bootstrap.md).

All measurements used the same x86-64 cloud host, compiler, isolated GNU
assembler 2.47 and two Meson workers. Durations are first-test start through
last-test completion, excluding the fresh bootstrap build. The original baseline
briefly overlapped a small formatter build during its early checks; results are
illustrative host measurements, not an isolated benchmark or portable guarantee.

| Run | Tests | Passed | Test span |
| --- | ---: | ---: | ---: |
| Original corrected dev registration | 47 | 47 | 430.88 s |
| Final quick dev | 38 | 38 | 42.06 s |
| Final slow | 9 | 9 | 385.54 s |

The measured quick loop is about 42 seconds here, not a promised 30 seconds.
The complete coverage still incurs the longer work. The fresh Meson compiler
SHA256 is `f0dee7330d02dfff6e145e1f8a6fbf78291c986667c0c07448140f294d5a1a65`.
Official GNU binutils 2.47 source, release checksum and detached signature were
verified; the isolated assembler was selected through PATH, without replacing
system binutils 2.44. Its precise version is 2.47.20260726.

## Joined public gates and limits

After composing the independently reviewed formatter and NVMe repairs:

- `make test-formatter` passed current goldens/adversaries, 128 trivia variants,
  92 repository sources and 47 CLI cases. Separate shared-adapter checks passed;
  this is not full optional-LSP qualification.
- `make test-developer-commands` and `make test-emulator-clock` passed, as did
  the 37 BAR-runner tests in ordinary and optimized Python.
- Actual `make -C compiler test-json-codecs`, `test-json-integers` and
  `test-json-lookup` each passed their complete existing runner. They used the
  independently approved fresh Meson compiler through explicit
  `ACCEPTANCE_COMPILER` and `ACCEPTANCE_COMPILER_SHA256` controls.
- Actual `make test-package-identity PACKAGE_IDENTITY_TEST_FLAGS=--smoke`,
  `make test-package-manifest PACKAGE_MANIFEST_TEST_FLAGS=--smoke` and
  `make test-package-graph PACKAGE_GRAPH_TEST_FLAGS=--smoke` passed with fresh
  controlled compiler builds. This is bounded full-profile smoke execution, not
  the full native package corpus. Every one of the 79 rejection cases still runs
  twice, including existing-output preservation. The partial Meson package
  profiles separately passed all 527 selected native cases.
- Seven package-profile controls passed normally and under `-O`, including
  full-corpus hash verification. All nine changed Python files pass Ruff lint
  and format checks.

The attempted public Make `--profile dev` selection was rejected by the existing
aggregate-context authority guard and is retained as a failed attempt. The guard
was not relaxed; the supported smoke route above was used instead. Preliminary
reconfigure and formatter-manifest failures are also retained, with their fresh
corrected replays. Final reporting-only documentation and the aggregate record
were added after the source-stable test runs; no extra native execution is claimed
for those leaf reporting edits.

Meson exports preserve exact commands, test output, result codes and timing data.
Unrelated inherited environment entries are omitted using an explicit allowlist;
original and exported hashes plus the redaction rule are retained. Host sanitizers,
root full-native acceptance, complete package native corpora, actual NVMe/QEMU
boots and physical hardware are not newly qualified by this repair.
