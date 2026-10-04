# Isolated nested generic value acceptance

## Outcome and scope

The isolated candidate implements bounded fully concrete nested template-id
arguments and an executable bounded token/source-range example. The complete
release and fatal ASan/UBSan compiler targets passed; independent source and
adversarial review found no actionable defect. Main integration and any required
kernel/emulator integration remain the parent coordinator's decision. No shared
kernel image, mutable-byte candidate, evidence-helper candidate, network,
installation, authentication or GitHub action was performed for this task.

The implementation adds no IR instruction or ABI and keeps template-body
specializations/dependent expansion, recursion, deduction, owners/references,
structs and C compatibility excluded. Nesting four is independent of class depth
four; 64 leaves, 64 definitions, 256 total instances including inner instances,
and capacities 1..64 retain their separate limits.

## Exact compiler identities

- Frozen baseline: `/tmp/aurora-resource-main-compiler-frozen`
  SHA256 `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`
- Release: `build/aurorac`
  SHA256 `e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6`
- ASan/UBSan: `build/san/aurorac`
  SHA256 `78379d081bfae56608a6a60e72bc290e9abd68e88b1a9c3e96f93d25b007cfb5`
- Frozen implementation manifest: `compiler-frozen-review.json`
  SHA256 `4a9847eddc4419cf032ac449ec63f64bee808ca480fdaf3512616e39c56ca9a9`

GNU C++ 14.2.0, GNU assembler/ld 2.44, Python 3.12.14. The manifest records every
compiler header and main.cpp; the independently reviewed implementation remained
unchanged throughout final gates. `final-seal.json` records the final candidate
input manifest, original-main identity check, compiler pins and disk sizes.

## Acceptance commands and observed results

From the candidate root, with TMPDIR set to its own `tmp` directory:

```
make -C compiler test CXX="$PWD/receipts/bounded-cxx.py"
```

`release-all.log` and `release-all.exit`: complete target exit **0**.

```
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
make -C compiler test OUT=../build/san/aurorac \
  CXX="$PWD/receipts/bounded-cxx.py" \
  CXXFLAGS='-std=c++23 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -Wall -Wextra -Wpedantic -Werror' \
  IR_TEST_CXXFLAGS='-std=c++23 -O1 -g1 -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer -Wall -Wextra -Wpedantic -Werror' \
  UTF8_TEST_FLAGS=--sanitized-compiler \
  XFS_GEOMETRY_TEST_FLAGS=--sanitized-compiler
```

`sanitizer-all.log` and `sanitizer-all.exit`: complete target exit **0**.
Address/undefined-behavior instrumentation is fatal and unchanged; LeakSanitizer
remains disabled for the previously documented tracing-environment limitation.
Only the IR-test translation unit uses the established -g1 debug accommodation.
Runtime instrumented processes do not inherit build address-space limits.

Both targets include:

- 313 new focused checks: 129 native returns, 24 exact-site bounds traps,
  80 negative fixtures each exercised with absent and preserved output files
  (160 normal exit-1 rejection runs).
- The complete prior compiler, class/value, templates, fixed containers,
  composition/enums, numeric, bytes/packed values, readonly spans, storage/XFS,
  UTF-8 and UTF-8 encoding suites and native numeric oracles.
- 960 typed IR cases, including four new unresolved-nested-metadata rejection
  cases; 10 exhaustive visitor/enum-dispatch compile controls; 18 native
  receiver-array IR cases, 10 of which require exact trap sites.
- 7,405,472 initialization-fact model checks, module/depth robustness, and host
  source/output adapter tests (22 output-adapter cases).

The alternate seed 18019/64-step focused run also passes the same 313-check
contract; it overlaps the default 18018/24-step coverage and is not additive.
The example returns 42 after checking independent copied token bytes and range
values. `example/compile-receipt.json` additionally shows normal baseline
rejection, accepted candidate compilation, and deterministic repeated assembly.

## Differential and independent review

`assembly-comparison-final-summary.json` records 1,639 compiler invocations from
1,398 distinct source hashes on a baseline-compatible regression corpus. All
821 accepted invocations have byte-identical assembly; all 818 rejected
invocations have identical exit status. This finite result is not a universal
semantic equivalence or performance claim.

`../review/independent-compiler/REPORT.md` contains the independent review:
78 cases pass on each compiler pin, comprising 31 native successes and 47 normal
rejections. The repeated pins are the same cases. An independently generated
694-source arithmetic differential corpus (520 accepted, 174 rejected) has no
status or assembly difference. Its overlap with other suites is not summed.
The reviewer found no actionable defect and changed no implementation.

## Resource limits and retained evidence

Serial build invocations use the existing 2 GiB virtual-address, CPU120/130s,
wall180s, regular-file512MiB/core0 limits through `bounded-cxx.py`; each exact
return code, wait status, command, timing and peak RSS is preserved in a
`build-*.json` receipt. Intentional failing exhaustive-dispatch controls are
recorded as nonzero compilations and recognized by the aggregate tests.

The full-debug instrumented compiler build passed in 45.88 seconds with
1,445,480 KiB peak RSS. The -g1 instrumented IR-test build passed in 63.40 seconds
with 1,655,932 KiB peak RSS. Neither was signal/deadline killed or had its cap
raised. The initial release build had an explicit 2,304 MiB address cap; the
final release reproducibility rebuild uses the retained 2 GiB cap and is
recorded separately.

The 384 MiB working-space target and 1.5 GiB retained filesystem-free target
were checked before builds. Large completed generated XFS/UTF-8 outputs were
losslessly archived, every member hash compared to its original, and the source
copies removed only after that verification. `archives/*.json` retains all
member hashes, archive hashes and exact byte sizes. Original paths inside the
archives preserve the test logs' references when restored under `build`.
No source or failed log was removed. Sampled disk observations are not claimed
as a continuous whole-task peak measurement.

## Preserved development failures

These earlier failed attempts are retained and do not count as passes:

- `release-regressions-initial`: make exit2 after the old suite demanded rejection
  of newly supported nested Pair arguments; those stale checks became positive
  24-byte layout checks.
- `release-regressions-replay`: make exit2 because the focused suite had not yet
  been written. The aggregate was replayed after the file was complete.
- `release-complete`: make exit2 on a focused-test fixture using reserved local
  name `array`; the test author corrected it. The worker's initial logs also
  retain its unsupported assignment-expression fixture correction.
- `release-final`: make exit2 for a missing pinned XFS proposal document in the
  source-only copy. Only that required small document was added, with unchanged
  approved hash. No complete documentation/evidence tree was copied.
- `assembly-comparison`: driver exit1 because the wrapper assumed a source-first
  CLI. Both compilers had accepted the source; the wrapper was corrected to skip
  option arguments, and all affected suites were replayed successfully.

Each aggregate's exact exit is in its matching `.exit` file. Original failed
logs were not overwritten by successful replays. The complete final gates above
are tied to the unchanged implementation and final test source inputs.
