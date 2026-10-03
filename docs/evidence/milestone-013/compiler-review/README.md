# Milestone013 compiler evidence

These are copied existing compiler receipts, collected after the final author
release and ASan/UBSan targets completed successfully and independent compiler
review reported no reproduced defect. Collection performed no rebuild or test
rerun. Parent final acceptance and kernel/emulator evidence remain separate.

## Identities and scope

[artifact-hashes.json](artifact-hashes.json) records full SHA-256 hashes and lengths
for both final compilers, the final instrumented IR/host-I/O test executables, and
the earlier numerical gate A artifacts. Executables remain outside source.

- Final release: `02771e0d94ad9fe9821041ee10081d31a4f4114dde81b7d476e16cba8d5c75d2`
- Final sanitizer: `cbe0d747958892457131bb1175c61a3d8debf86c60d1decee55ce7429d118782`
- Final sanitized IR: `3bcfda07961b5df01686284bab2ee77549568f7fe3d2065e3526df0bd5779b14`

The [frozen compiler manifest](author/compiler-source.json) covers all thirteen
main/header inputs and was rechecked unchanged after both aggregates. The broader
[source/tests/library manifest](source-tests-library.json) covers 67 owned files
including current compiler documentation. It is not a whole-repository manifest;
parent final manifests establish the complete milestone tree.

## Author final runs

[aggregate.log](author/aggregate.log) is the complete release compiler test target.
[aggregate-sanitized.log](author/aggregate-sanitized.log) is the complete equivalent
target using the instrumented compiler plus newly built instrumented IR/reader/
writer binaries. Actual subcommands and test output are retained. Both completed
with exit zero during execution; copied stdout/stderr alone is not an independent
record of every process exit status.

The new source groups are:

- 923,136 numerical observations, 37 source positives, 117 exact-site failures and
  138 rejection fixtures. Arithmetic exhausts representable successful domains;
  excluded inputs use a sentinel, and separate boundary fixtures test failure
  instructions. It does not exhaustively execute all overflowing operations.
- 352 byte-codec native cases and seven ordinary rejections, including default
  compact-layout checks. Python integer/byte conversion models determine values.
- 75 packed value native cases, including thirty exact bounds failures, plus
  nineteen rejection fixtures. Every rejection preserves absent/existing outputs.

The aggregates also include all preserved source suites, signed/unsigned oracles,
846 direct IR cases, ten exhaustive-dispatch controls, preserved native IR groups
18/8/13, 2,627 u8 IR native checks including 260 exact sites, fourteen packed ABI/
padding checks, 72 module tests, eleven depth checks and both host-I/O suites.
Source and direct-IR numerical coverage overlap; counts are not additive evidence
of distinct behaviors. No coverage or test count is a formal safety proof.

`semantics-{default,stress}.log` and corresponding `*-sanitized.log` preserve
630 default and 1,526 seed404 scalar-oracle cases on each final compiler.
`semantics-selftests.log` records nine runner checks. `equivalence.log` records
64 comparisons with the frozen milestone012 compiler. The release and sanitizer
build-output logs are preserved; an empty successful build log is not by itself
proof of flags or execution.

## Build flags and limits

Release uses `g++ -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror`.
Primary sanitizer compilation uses `g++ -std=c++23 -O1 -g
-fsanitize=address,undefined -fno-omit-frame-pointer
-fno-sanitize-recover=all -Wall -Wextra -Wpedantic -Werror`.
IR/adapter builds add include paths; the reader adds `-pthread`, as shown in the
aggregate command lines. Runtime uses
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`. Undefined-behavior recovery is also
disabled by compilation. Leak checking is not claimed because the executor's
tracing environment is incompatible with LeakSanitizer.

Instrumentation applies to hosted compiler and test drivers. Generated native
Aurora code is executed with independent result/failure observations; it is not
ASan-instrumented merely because its compiler is. Native failure observers require
SIGILL at the exact emitted UD2 site; generic crashes or timeouts do not pass.

The scalar oracle's explicit `--sanitized-compiler` mode leaves only the compiler
address-space limit inherited for ASan shadow reservation. Its normal compiler
and native executable limits remain 512 MiB. That runner keeps five-second command
timeouts, three-second CPU limits, disabled cores and an 8 MiB regular-file limit.
Captured pipes are unbounded: RLIMIT_FSIZE does not bound stdout/stderr pipe memory.
These are scalar-runner limits, not a claim about every test harness. The u8 sweep
has its separately documented ten-second default timeout and bounded generated
case counts. Instrumented timings are not performance/resource-bound evidence.

## Independent runs

`independent/` contains existing reviewer logs copied from matching
`/tmp/aurora-review-m13-<filename>` paths: u8, packed, codec and extra constructor
ABI cases on both final compiler pins, plus final sanitized IR and native/exhaustive
checks. `extra.py` is the reviewer's existing additional ABI driver. The reviewer
used the author-built pinned binaries; these are independent executions and source
inspection, not independent toolchain rebuilds.

Alternate codec coverage is 928 native cases/seven rejections, seed39037 and 64
random values. Packed coverage is 75 cases/thirty exact bounds sites/nineteen
rejections with seed39037 and 64 model steps. The additional 64 constructor ABI
cases vary six class/scalar argument positions with compact class sizes
1/3/7/9/17/31. Numerical and IR counts match their author groups. Seeds overlap
existing coverage and must not be summed. The review report in docs/review.md
records the independent disposition; kernel conclusions are not part of this index.

## Development history preserved separately

`development/gate-a-source.json` records the compiler source identities before
packing. Gate A compiler `2f2718048eaaca6f19c99785755238eb15f4c3cea57be4def51bb6c9ae9a6dac`
used padded storage and cannot establish compact representation. Its IR receipts
cover 812 direct cases and the initial numerical/native checks; that IR executable
was built with strict warnings at O0, without a sanitizer claim. The numerical-only
codec log explicitly excludes layout. The gate A manifest identifies source
hashes; it is not a complete archived gate A source checkout.

`gate-a-scalar-oracle.log` preserves a command-line invocation error (`--compiler`
was unsupported); the separate corrected positional invocation passed630 cases.
`gate-b-codec-initial.log` preserves the reproduced missing empty-class shape map
entry, fixed before the final compiler. `packed-values-first.log` preserves fixture
expectation errors: historical scalar bool size is one despite eight-byte field
storage, and a local uncomposed 65-leaf class is allowed while the by-value call
boundary is capped at64. Corrected fixtures exercise those real contracts. Later
packed default/optimized logs remain developmental pin results; final aggregates
retest the final source. No earlier failure is relabeled as a pass.
