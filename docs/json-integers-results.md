# JSON integer codec qualification — 2026-10-08

Status: focused ordinary and optimized native gates, affected prerequisite
regressions and independent source/evidence review passed within the scope below.
The [contract](json-integers.md) defines the library-only scope. No compiler/runtime
implementation changed by this milestone. The final source is composed on PR81. This is not full-native,
sanitizer, kernel, emulator, hardware or production acceptance.

## Mechanism and identities

The accepted PR79 base is commit `cd87875dca0658d07df5d32977d6fd5fb8c121f3`,
tree `f2cd550359b30904d651149f6aea2d4841f94f76`. All 849 archive blobs and executable
modes were checked against the actual untruncated remote tree before qualification.

Frozen implementation SHA-256 values:

- `library/std/json.au`:
  `576eebc8c5c1e6ebdbbdf312a28e534b008a8a11c3e8c785795fd382dd9c2c66`
- `library/std/decimal.au`:
  `00bd7b7522d767e88436d9f41a91953f6149b2aff129fbe662f95b9bc0b982ad`
- `library/examples/json_integers.au`:
  `50eb2a3ed6fdd97747843b8c20753cbcdf9150b4d6ead879e0329893e1b2d1d4`
- Final `tests/compiler/json_integers.py`:
  `699121af6ebaaa68ca25438081889f954c458dbf4ea81c00f5ba47a08e662aec`
- Reused independently reviewed compiler:
  `fde0877e0b3326bc8e6e500bb6d3a8ed9daef814af4f46ae1d319da31d707fe3`

This is pinned prebuilt compiler evidence, not a fresh compiler build. JSON parsing
shares the existing number DFA and checked DecimalAccumulator. Generic decimal
encoding returns at most 20 copied bytes, with no duplicate JSON formatter.

## Final composition and public routing

Final source composes the numeric delta on accepted PR81 main
`c1aeb3bd1969f73f310eac686b2368776a142a86`, tree
`b810d101e398af72bce8bc378ff9acd687e553b8`. All 856 accepted files were retained,
with changes confined to the numeric ledger. Method-span compiler/runtime changes
are accepted base content, not introduced by this numeric milestone.

Fresh composed-source ordinary and public Make optimized gates reused the reviewed
PR81 compiler `512050d547be364fe859031417994fe5c2de69814eed4fffd801ba1e2e92fe7c`.
Both cover the full numeric gate below and have independent retained-output audits.
The public focused Make terminal receipt records focused acceptance with
`native_complete=false`; this does not establish root full-native acceptance.
The entire supervisor-controlled source inventory stayed frozen until supervisor exit. Final result
documentation and the compact qualification record were added afterward without
changing executable inputs; those documentation additions do not claim a rerun.

The first composed Make attempt was interrupted after scalar batch 295, with a
nonterminal running supervisor receipt and no hosted completion. It is retained
as interrupted, never passed. A fresh complete public Make replay supplies the
terminal result. The earlier documentation-drift failure remains separate below.
Meson test/example routing was configured and introspected; no fresh Meson native
suite or compiler rebuild is claimed.

## Native gate

Each final ordinary/optimized Python run independently passed:

- 4,687 cases in 295 batches
- 91,079 complete 64-bit observations
- 81 source rejection controls
- 407 real hosted observations, including allocation/quota failures and cleanup

The independent oracle uses regex grammar/prefix acceptance, CPython JSON callbacks
that retain numeric spellings, arbitrary-precision integer ranges and decimal
strings. No host binary floating point is used. Compiler-free controls include
267 full-width/length mutations; the grammar audit covers 1,694 spellings with
807 syntax-accepted, 801 rejected and 86 window/limit exclusions. It cross-checks
1,127 exact mathematical integer values.

Coverage includes signed/unsigned endpoints and neighbors, powers of two/ten,
deterministic random full-width values, exact window cuts and nested coordinates,
all individual bytes, malformed/overflow/form precedence, 128-byte transitions,
negative zero, forged result shapes, eager fallbacks, private/type rejection,
copy lifetimes and complete encoded bytes. Round trips supplement independent
value/byte observations rather than replacing them.

Actual owner-backed tests use 160, 4,096, 4,097 and 8,192-byte inputs. They preserve
copied token/result snapshots, mutate the source after its borrow ends, then parse
a fresh view to prove revalidation. These are genuine owner spans, not forged host
span representations. The example exposes all 45 bytes of
`[-9223372036854775808,18446744073709551615,0]`, size and capacity. Existing-prefix
append tests check failed reserve leaves bytes, logical size and capacity intact.

Independent audits of both modes regenerated every expected case/observation and
checked all native stdout, source/receipt hashes, 2,559 command receipts and 407
hosted output/accounting observations per mode. No mechanism discrepancy was found.
The two modes overlap; their counts are not additive coverage.

## Affected prerequisite regressions

With the original reviewed fde0877 compiler, each ordinary/optimized Python mode
passed the following existing regression checks on the numeric source:

- JSON profile: 2,111 cases, 10,768 complete i64 observations, 53 rejections
- JSON scalar codecs: 1,942 cases, 19,781 complete observations, 46 rejections and
  431 actual hosted output/allocation checks
- Decimal values: 196 checks, 131 native executions, 65 rejections and 1,396
  independently modeled decimal steps
- Enum/decimal composition: all seven targeted decimal-composition native cases
- Checked signed integers: 1,510 native cases and 181 exact-site trap observations
- Unsigned integers: 4,219 native cases, 501 exact-site traps and 67 rejections

The attempted full enum-composition suite failed because it still expected direct
whole-field replacement to reject. The identical failure was reproduced on the
verified unchanged PR79 baseline with the same compiler. Its fixture imports only
unchanged std.utility/std.array and conflicts with the already accepted direct
owned-field mutation contract. This full-suite attempt remains failed; the passing
seven-case decimal subset is not presented as a full-suite pass. Narrow stale-test
maintenance is separately reviewed and does not change numeric production code.

## Preserved fixture corrections

- `normal-001` stopped after 3,379 completed cases: a copied-result fixture tried
  whole-class reassignment, which Aurora does not support. Removing only that
  reassignment preserved all expected values and other copy/lifetime probes.
- `normal-002` stopped after 4,611 completed cases: a roundtrip fixture used an
  empty initializer for a 20-byte builtin array. It was replaced by 20 explicit
  zeros. A cosmetic Python string wrap was included before the final freeze.
- `diagnostic-001` then passed the remaining 76 cases, all 81 rejections and all
  407 hosted checks. It is a diagnostic subset, not a substitute for full replay.
- Fresh `normal-003` and `optimized-003` supply complete results on the final
  frozen test runner. Earlier failures retain their original manifests and artifacts;
  their partial counts are never added to complete-run coverage.

The first attempted public Make gate also failed terminal source-inventory checking:
only the results document had been edited while the gate was running. The precise
drift and failed terminal receipt are retained; completed semantic batches do not
turn that public run into a pass. The replacement public gate freezes the entire
controlled tree, including documentation, until supervisor exit.

The production modules and example did not change during these fixture corrections.
Full generated sources, assembly, expected/observed bytes, diagnostics and command
receipts are retained outside the repository; only one concise aggregate
qualification record is committed after final acceptance.

## Commands and limits

Direct runner: `python3 -B tests/compiler/json_integers.py COMPILER
--compiler-sha256 PIN --artifacts FRESH_DIRECTORY`, repeated with `-O`.
`--self-test-only` checks compiler-free controls. Public focused routing is
`make -C compiler test-json-integers`, with optional independently reviewed
`ACCEPTANCE_COMPILER` and `ACCEPTANCE_COMPILER_SHA256`. Meson bytes/dev routing
uses the existing selected-compiler mode and explicit example dependencies.

No fraction/exponent arithmetic conversion, floats, owned strings, DOM, key lookup,
JSON-RPC transport, host nlohmann replacement or whole-distribution qualification
is claimed. Huge signed buffer-length arithmetic is source-reviewed, not exercised
with near-I64_MAX allocations. Generated Aurora code is not sanitizer instrumented;
normal cleanup evidence does not imply fail-stop unwinding.
