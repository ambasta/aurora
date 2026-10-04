# M021 explicit function-template candidate verification

Status: isolated candidate acceptance gates passed. Complete release and fatal
host ASan/UBSan compiler targets exit 0; independent release review and fatal
sanitizer replay pass with no unresolved implementation findings.
This is isolated source-only work. The accepted main tree, its compiler and all
kernel/images remain unchanged. Parent adoption and fresh aggregate/integration
checks are separate.

## Mechanism and deliverable

Namespace-level explicit one/two Scalar/Value function templates are instantiated
as independent deep copies into the existing concrete function path. The public
library addition is `std::make_pair<T,U>` with complete copied class boundaries.
`examples/function_token_values.au` exercises inline byte-array/source-range
factory values and independent copies. See `compiler/FUNCTION-TEMPLATES.md` for
precise grammar, finite phases, exact nominal authority and limitations.

No deduction, overloads, generic methods, function capacity parameters, dependent
construction/qualified names, function-template calls in any template body,
general heap/reference/span API, runtime-reflection widening or new IR/ABI exists.
Class-template-id arguments in function bodies/signatures can be bare parameters
or concrete M020 trees, but cannot be nested dependent expressions. Combined graph
limits are 64 definitions/256 instances. Class nominal depth after substitution,
containment depth, leaves, frames and copied-value boundaries are independently
checked. Unrequested ordinary tuple semantics are explicitly deferred, with fixed
exported-signature visibility and structural restrictions checked eagerly.

## Exact identities and deliverable files

- Immutable M020 baseline binary: `e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6`.
- Final release compiler: `d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64`.
- Final ASan/UBSan compiler: `423db8bcf0642263e445582107c73f967decdc13132f2bd98a973fce2db03d0f`.
- Final focused test: `7ad364b414ce5c8c0d14e2b4f92153f332282808ce2598750d823649fda13c65`.
- `frozen-final-inputs.json` pins source, tests and candidate docs.
- `change-manifest-final.json` pins all 18 changed/new source/document files and
  corresponding baseline identities. `source-only-change.patch` applies in a
  read-only `patch --dry-run -p1` check against accepted main.
- `review/REVIEW.md` and `review/final-implementation.sha256` record independent
  review, reproduced defects, fixed pins, evidence and remaining scope limits.

The candidate source copy excluded historical docs/evidence/build/cache/git data.
Only the explicitly authorized test dependency `docs/xfs-geometry-proposal.md` was
later copied, with required SHA256
`40021cf66fba001094c9f0762475075967b64bd4f55b8be845490ddf37fc5b86`.
New candidate documentation and evidence are independently authored.

## Focused evidence, counts and overlap

The final focused contract has 227 unique fixtures / 349 executions:
81 full-width native returns, 24 exact-site traps, and 122 rejection fixtures each
run with absent and pre-existing output (244 rejections). Every outcome checks
source/library immutability, output preservation and exact values or trap sites;
checks remain active under `python3 -O`. First failures retain reproduction trees.
The suite passes on release and on final ASan/UBSan with explicit abort-on-error.

This same suite is included again in each full aggregate; these executions are
repeats, not additional unique coverage. Earlier 203/303 and 221/339 intermediate
runs are overlapping historical coverage. Two formerly blanket function-template
negatives were changed to still-unsupported capacity/nested-dependent forms; old
counts must not be described as an identical unchanged contract.

Four new direct IR rejection controls bring the aggregate from 960 to 964 cases.
They reject unresolved generic parameters and residual dependent/substitution
metadata. Existing exact nominal result/argument/receiver, independent copy,
initialization, record separation and borrow controls remain in the aggregate.
No generic IR instruction or backend extension was added.

Independent release review uses 46 independently authored fixtures (24 native,
22 negatives), with 22 extra absent-output rejection executions. Independent
assembly observation preserves all 64 return bits. Five unchanged M020 example
inputs are also compared. This corpus overlaps the owner's contract/differential
work and is not additive unique coverage. The same independent 46 fixtures and
22 absent-output checks also pass on the final instrumented compiler with fatal
abort-on-error settings; see `review/SANITIZER-ADDENDUM.md`.

The owner differential uses 232 unchanged M020 contract fixtures (224 source
hashes): 153 accepted assembly outputs are byte-identical and 79 rejection statuses
agree. An additional 36 unchanged example/program sources also match assembly and
status. These corpora overlap. The single old unused function-template definition
now intentionally accepted is excluded explicitly; the initial comparison which
included it and recorded that expected difference remains preserved.

## Commands and gate receipts

From this candidate directory:

- `TMPDIR="$PWD/tmp" make -C compiler -j1 test CXX="python3 $PWD/evidence/cxx-cap.py g++"`
  passes in `release-all-verified.log`, exit `0` in `release-all-verified.exit`.
- The full sanitizer command uses `OUT=../build/san/aurorac`, the same CXX wrapper,
  `-std=c++23 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all
  -fno-omit-frame-pointer -Wall -Wextra -Wpedantic -Werror`, IR-only `-g1`,
  `UTF8_TEST_FLAGS=--sanitized-compiler` and
  `XFS_GEOMETRY_TEST_FLAGS=--sanitized-compiler`. Exact retained environment:
  `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1` and
  `UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1`. The unchanged full target
  passes in `sanitizer-all.log`, exit `0` in `sanitizer-all.exit`.
- `sanitizer-focused-abort.log` repeats all 349 focused executions with
  `abort_on_error=1` added to both sanitizer environments. This prevents sanitizer
  faults from being confused with ordinary expected rejection exit codes.
- `compare-m020-contract.py`, `compare-baseline.py` and their current JSON/log
  outputs record exact sources, statuses and assembly hashes.
- Complete release includes all existing compiler/library/numeric/module/host-I/O
  targets, 964 IR cases, 10 exhaustive-dispatch controls, and all native IR ABI
  batches. Representative separate counts: 4,219 unsigned oracle cases / 501
  exact traps; 1,510 signed oracle cases / 181 exact traps; 7,405,472 finite
  initialization-fact checks. These are per-suite, overlapping observations.

Host compiler/C++ test executables are instrumented in sanitizer runs. Generated
Aurora machine code is executed natively, not ASan-instrumented. LeakSanitizer alone
is disabled for the previously documented tracing limitation. No safety proof,
whole-program resource bound or equivalent-C performance claim follows.

## Preserved failures and corrections

1. Initial timing wrapper `/usr/bin/time` was unavailable before compilation;
   its failure log remains. Final builds use Python resource receipts.
2. First focused tests exposed nine unused exported-template fixed-signature
   privacy failures. Recursive eager visibility validation fixed these while
   retaining caller-private dependent arguments; failing inputs/logs remain.
3. Independent review reproduced parameter-qualified names hidden in argument
   trees, including a matching namespace collision. Recursive name validation
   fixes both unused and requested forms; 18 dedicated regressions were added.
4. Independent review reproduced receiver-method precedence rejected due to an
   unrelated global/imported function-template name. Structural validation now
   follows concrete receiver lookup. Six owner regressions and seven independent
   controls cover legitimate receiver methods and genuinely forbidden calls.
5. An exploratory positive test used a non-empty constructor body; corrected to
   the existing empty-body contract. Original failure retained.
6. First full release run stopped at the omitted pinned XFS proposal dependency.
   Parent authorized the one document copy; the full gate was rerun unchanged.
7. First expanded IR run rejected unresolved parameters correctly but the new test
   expected the wrong diagnostic family. Expected diagnostics were corrected;
   all 964 cases and the fresh complete gate then passed. Failed log retained.

## Resource discipline and evidence retention

Final C++ invocations use a locked serial wrapper with 2 GiB address-space,
CPU120/130s, wall180s, regular-file512MiB and core0 limits. Runtime ASan processes
do not inherit the build address-space cap. Full-debug final sanitizer compiler
build took 46.62s and peaked at 1,437,796 KiB RSS. The final instrumented IR build peaks at 1,657,196 KiB RSS.
Per-build command/status/time/RSS,
candidate bytes and free-space receipts are `build-*.json`. IR-only `-g1` is the
explicit retained accommodation; no cap increase was made.

Workflow exceptions are disclosed: initial exploratory NativeRunner observer
compiles were small trusted existing helpers but lacked the explicit capped CXX
wrapper. The first exploratory release compiler build used the 2 GiB shell cap
without the later CPU/wall/file receipt wrapper. All final aggregate C++ builds
and final focused observer builds use the locked wrapper. No bounded-resource
claim is made for those preliminary helper compiles.

The candidate budget is 384 MiB with at least 1 GiB filesystem free. Parent
approved lossless archival of only completed-success generated XFS/UTF8 output
directories. Each archive is reopened and every path, file byte hash and mode is
verified against originals, then duplicate expanded outputs are removed. Archive
receipts retain exact original paths, member hashes/modes and archive hashes.
Largest recorded candidate size was 355,665,735 bytes (339.19 MiB); minimum
recorded filesystem free space was 1,541,660,672 bytes (1.44 GiB). Capped receipts
include 16 expected rejected exhaustive-dispatch compile probes across the two
complete runs; these are successful negative controls, not failed compiler builds.
Failure artifacts, source, historical compiler pins, logs and other tasks' data
are not removed. No network, installation, authentication, upload, shared kernel
image operation or access to blocked parallel candidates/reviews occurred.

## Adoption boundary

No main-tree edits or kernel integration were performed. Parent should review the
source-only patch, merge the candidate completeness update into the canonical
matrix, adopt exact reviewed sources/compiler only after all final gates pass,
and own fresh main aggregate plus selected emulator integration. This candidate
does not authorize a new full emulator or physical-hardware claim.
