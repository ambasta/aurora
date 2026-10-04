# Milestone014 compiler evidence provenance

This collection copies existing receipts without builds or reruns. The corrected
compiler completed author release and ASan/UBSan aggregates, and independent
compiler review reported no unresolved finding. Final parent/kernel acceptance
remains separate. Historical milestone013 evidence is unchanged.

## Corrected artifacts

[artifact-hashes.json](artifact-hashes.json) records exact hashes/lengths for final
and initial executables; binaries themselves are outside the source tree.

- Release: `2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`
- Sanitizer: `ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa`
- Sanitized IR: `34181616b8dc98bb105e5437f2245d06c1c29ae40087f03db0a6e9d44c616310`

[author/compiler-source.json](author/compiler-source.json) is the thirteen-file
main/header manifest, checked unchanged after final aggregates and independently
matched by the reviewer. [source-tests-library.json](source-tests-library.json)
records 71 owned compiler/test/library/documentation files. It is not a whole-tree
manifest; parent final manifests bind the complete milestone. Existing generated
Python caches are excluded, not deleted.

## Author final runs

[aggregate.log](author/aggregate.log) and
[aggregate-sanitized.log](author/aggregate-sanitized.log) are the complete corrected
release and instrumented compiler targets. Both returned exit zero during their
recorded execution. Their logs preserve command/output, not a separately signed
exit-status record for every subprocess.

The new source suite passes 91 native cases including 25 exact bounds sites and
69 rejection fixtures, each preserving absent/pre-existing artifacts. Eight
source lifetime failures require the precise live-span mutation diagnostic;
unsupported syntax and privacy failures are not relabelled as lifetime proofs.
The new typed-IR suite totals 950 cases (846 previous, 99 initial span cases and
five site-identity regressions), plus ten exhaustive-dispatch controls. Fourteen
native span checks include four exact bounds sites and mixed scalar/class/span
arguments with class results. Every earlier source, native IR, numeric oracle,
module, depth and host reader/writer group also passes in both complete targets.

`semantics-{default,stress}.log` and their `*-sanitized.log` counterparts preserve
630 default and 1,526 seed404 scalar-oracle cases on each corrected compiler.
`semantics-selftests.log` records nine harness checks. `equivalence.log` records
64 comparisons against milestone013. `assembly-equivalence.log` records the one
binary-reader example's byte-identical assembly before/after the verifier-only
strengthening; that is not a general equivalence or performance proof.

`development-ir-*-corrected.log` are author-worker O0 direct/native checks before
the final sanitizer build, not replacements for the complete primary aggregates.
Alternate seeds and repeated groups overlap; do not add them as distinct coverage.

## Independent final runs

[commands.txt](independent/commands.txt) preserves the reviewer's actual invocation
record and exact compiler/IR identities. `spans{,-san}.log` contain the source
suite; `extra{,-san}.log` contain 64 additional mixed six-position argument and
class-result checks. `ir-san.log` and `ir-native.log` contain final950 IR, exhaustive
and native results. `extra.py` is the existing extra ABI driver. These are
independent executions and inspection of author-built pins, not independently
rebuilt compiler toolchains. No extra review was performed by copying the files.

The original standalone [restart.cpp](independent/restart.cpp) now rejects, as
recorded in [restart-fixed.log](independent/restart-fixed.log). The independent
review disposition is in docs/review.md; kernel conclusions are not part of this
compiler index.

## Initial contract gap and preserved history

Initial release400c8ed0… and sanitizere465373d… passed their then-current aggregates
but accepted an IR branch that ended/restarted the same array/span slots before
joining an unchanged lifetime. The active origin/parent maps compared equal.
This was an exact-lifetime verifier-contract gap, with no invalid-memory failure
reproduced: end operations still required descendants gone, rebegin cleared
initialization and acquisition required complete active storage.

The correction records static array/capability creation sites and root/parent
sites in lifetime state. It rejects three restart/join cases while two wholly
closed loop-reuse cases remain accepted. Static sites are not unique dynamic
iteration/invocation generations. Source/API/backend behavior is otherwise unchanged.

`initial/` preserves the original author source manifest/aggregates, independent
source/ABI logs, invocation record and accepted restart-result receipt under
their original identities. Full initial inputs/artifacts
also remain in /tmp/aurora-m014-pre-lifetime-sites and the reviewer's initial
receipt directory. Initial passes are not called final acceptance of the stronger
contract, and the absence of a memory failure does not erase the reproduced gap.

## Flags, instrumentation and limits

Release uses `g++ -std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror`.
Primary sanitizer compilation uses `g++ -std=c++23 -O1 -g
-fsanitize=address,undefined -fno-omit-frame-pointer
-fno-sanitize-recover=all -Wall -Wextra -Wpedantic -Werror`.
IR/adapter commands add their include paths; the reader adds `-pthread`.
Runtime uses `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`. Leak checking is not
claimed because the executor's tracing environment is incompatible with LSan.
Build-output logs can be empty on success; empty output alone is not proof of flags.

ASan/UBSan instrument hosted compiler/test drivers, not generated Aurora code.
Native observers check exact values and actual SIGILL at the emitted UD2 site;
a timeout or generic crash is not a passing failure test.

Only the scalar oracle's explicit `--sanitized-compiler` mode leaves the compiler
address-space limit inherited for ASan shadow reservation. That runner retains
512 MiB limits for ordinary release compiler/native programs, five-second command
timeouts, three-second CPU limits, disabled cores and an 8 MiB regular-file limit.
Captured stdout/stderr pipes are unbounded; file-size limits do not bound pipe
memory. Other suites use their documented harness limits. These runs establish
neither general compiler resource bounds, stack safety nor equivalent-C performance.
