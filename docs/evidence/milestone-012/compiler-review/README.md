# Milestone012 compiler evidence provenance

This directory preserves existing author and independent compiler receipts. It
was collected without rebuilding or rerunning tests. It is not the parent final
aggregate or a kernel acceptance record. Source/tests/Makefiles were not changed.

## Exact artifacts

[artifact-hashes.json](artifact-hashes.json) records SHA-256 and byte length of the
existing release compiler, sanitizer compiler, direct IR test executable and both
sanitized host-I/O executables. Executables themselves are not copied into source.
The primary compiler sanitizer hash is
`3c5272f7e8a32fdbd9561de88f6a7cede2fcd34d3cab7218f8e504faa07551b1`;
the primary IR sanitizer hash is
`1f8acd34a5a11340490ce174fff8b179b67477b77564ad943823aac3ef0b7064`.

[author/compiler-source.json](author/compiler-source.json) is the frozen 12-file
compiler source manifest, rechecked against the checkout at collection with no
mismatch. [author/source-tests-library.json](author/source-tests-library.json)
is the earlier author snapshot of compiler, tests, library and compiler docs;
subsequent root documentation edits are not represented by that earlier snapshot.
Parent final manifests remain authoritative for the full milestone tree.

## Author runs

- [aggregate.log](author/aggregate.log): complete release `make -C compiler test`.
- [aggregate-sanitized.log](author/aggregate-sanitized.log): complete compiler
  target with the instrumented compiler and instrumented IR/source/output adapter
  executables. It contains the actual build command lines for those test binaries,
  592 IR cases, ten exhaustive dispatch controls, native IR arrays 18/composition
  8/enum-result 13, 72 module cases, eleven depth checks, source-reader checks and
  22 artifact-writer checks, alongside all language and integer-oracle suites.
- `semantics-{default,stress}.log`: 630/1,526 scalar-oracle cases on the release
  compiler. The corresponding `*-sanitized.log` files use the sanitizer compiler.
  `semantics-selftests.log` records nine harness selftests.
- [equivalence.log](author/equivalence.log): 64 comparisons against the immutable
  milestone011 baseline.
- `final-build.log` and `sanitizer-build.log` preserve available compiler build
  output. The sanitizer build log is empty because that successful command had no
  output; its flags and artifact identity are recorded here, not inferred from
  an empty log alone.

Author commands completed successfully as reported during execution. Copied
stdout/stderr files do not themselves encode every process exit status. Alternate
seeds and later reviewer reruns overlap coverage; their counts are not additive.
The final parent aggregate is a separate receipt.

## Build flags and instrumentation limits

Release: `g++ -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror`.
Primary sanitizer builds: `g++ -std=c++23 -O1 -g
-fsanitize=address,undefined -fno-omit-frame-pointer
-fno-sanitize-recover=all -Wall -Wextra -Wpedantic -Werror`.
IR and adapter builds add the include path; the reader adds `-pthread`, as shown
in the aggregate log. Execution uses
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`; undefined-behavior recovery is also
disabled by the build. Leak detection is not claimed: the executor reports that
LeakSanitizer is incompatible with its tracing environment.

These instruments check the hosted compiler/test drivers. Generated Aurora native
machine code is executed with its own expected-value/trap checks, not magically
ASan-instrumented. Exhaustive-dispatch controls compile deliberately altered
sources and are separate from runtime instrumentation.

The scalar oracle's explicit `--sanitized-compiler` option omits only the compiler
RLIMIT_AS assignment, retaining its inherited limit for ASan shadow reservation.
Release compiler and native-program limits remain 512 MiB; the scalar runner
retains five-second command timeouts, three-second CPU limits, disabled cores and
an 8 MiB regular-file size limit. Captured stdout/stderr pipes are unbounded; the
regular-file limit does not bound pipe memory. These particular limits describe
the scalar runner, not every unrelated test harness. Instrumented runs are not
compiler resource-bound or performance evidence.

## Preserved unsuccessful development attempts

[ir-sanitizer-attempts.log](author/ir-sanitizer-attempts.log) records a redundant
worker IR compilation killed by the host and a subsequent LeakSanitizer runtime
failure. The cause of the killed compiler was not established. A supplemental
`-O0 -g0` instrumented run passed, recorded in
[ir-tests-sanitized.log](author/ir-tests-sanitized.log). This supplemental receipt
is distinct from the final primary `-O1 -g` IR artifact and full passing aggregate;
it is not a replacement for that gate. [source-diagnostic-attempt.log](author/source-diagnostic-attempt.log)
preserves an earlier development rejection-diagnostic mismatch, superseded by the
complete corrected-source aggregate. No failed attempt is relabeled as a pass.

## Independent compiler review

The `independent/` directory contains existing reviewer receipts, copied unchanged:
combined107 release/sanitized (seed39031, 64 steps), decimal196 release/sanitized
(seed39031, 256 steps, 2,676 model steps), the separate64 ABI matrix on both,
composition161 sanitized (seed39031, 64 steps), sanitized592 IR, and exhaustive10
plus native18/8/13 checks. `extra.py` is the existing independent ABI driver, not a
new permanent test added during collection. Each log's exact source path was
`/tmp/aurora-review-m12-` followed by its preserved filename.

These runs use release a6de1e89…5026 and sanitizer3c5272f7…51b1; the IR executable
is1f8acd34…7064, as recorded in the independent review excerpt and full hashes
above. They are reviewer executions of the author-built pinned binaries, not
independently rebuilt toolchains. The compiler portion of the existing review
report is preserved in `independent-review-excerpt.md`; kernel statements are
excluded from this compiler index. No standalone exact command transcript was
invented where a test log records only test output and seed information.
