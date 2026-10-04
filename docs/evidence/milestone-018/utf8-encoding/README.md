# Reviewed owned UTF-8 encoding integration

The independently reviewed five-file delta was applied after exact baseline and
candidate hash checks. All 246 captured existing inputs outside the approved delta
remain unchanged, including compiler implementation, kernel, scripts, prior
fixtures, root Makefile and the parent-finalized M017 decoder contract.

Modified:
- compiler/Makefile: one test line and test-utf8-encoding target, using UTF8_TEST_FLAGS.
- library/std/utf8.au: std.array import and owned encoder declarations appended;
  original decoder implementation remains byte-identical.

Added:
- library/examples/utf8_owned_scalar.au
- tests/compiler/utf8_encoding.py
- docs/utf8-encoding-contract.md

Exact original/final hashes are in integration-delta.json and baseline-check.json.
The isolated 79-file manifest and initial/final library snapshots remain historical.
No mutable-view candidate, compiler grammar, native-pointer surface or kernel
profile was introduced. Archive tooling is not part of this source delta.

## Observed results

Author final stable-input aggregate: all 11 commands exited zero. Both compiler
pins passed 186 native checks / 35 bounded fixtures plus 24 rejection compilations
(12 misuse inputs, absent/existing output). Native loops cover every 1,112,064
scalar and all 2,048 surrogates. Decoder 406/39 regressions also pass both pins.
Native arithmetic byte comparisons, exhaustive Python-model comparison, ordered
fingerprints and decoder roundtrips are distinguished in the contract. Fingerprints
alone do not prove byte equality.

Independent review passed on both compilers: 1,122,439 exact-output observations
(all scalars plus 10,375 invalid inputs), 8,784 report/copy cases, one mixed value-call
fixture, 16 exact checked-array bounds sites and 18 compiler rejections. Counts
across these suites overlap and are not a unique-case total. See the unchanged
independent/REVIEW.md and manifest.json for exact identities, commands and limits.

Integrated verification: all 10 commands exited zero. Both encoder and decoder
Makefile targets pass on release/instrumented compiler pins. Example assembly is
identical from both pins; its linked native result is exactly 42. Before/after
source hashes match. Parent aggregate/smoke and milestone acceptance remain
separate; no new complete kernel-mode run is claimed here.

Release compiler:
14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980
Instrumented compiler:
805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf
Library:
a9448bed52974ca1e690b9a10e86a5f879c5b24f475a12ab1ec079e4e97bc646
Test:
e35b66182a56c8f7e87622d6ab65b74fa3e4a0199eb1c56f165a838c808ae1f5

## Scope and preserved evidence

The constructor-fixture failure and earlier 183-check passes remain preserved.
The library required no correction. Existing M016 ASan/UBSan compiler flags and
pins are reused; sanitizer execution disables unsupported leak checking and omits
only the compiler address cap for shadow reservation. Native/tool limits remain.
Regular-file limits do not cap pipes. Physical object padding was not newly
observed; zero unused encoding bytes, copy independence and layout sizes were.
Freely constructed reports are data, not proof that supplied bytes encode a scalar.

Author and independent full original artifacts are archived byte-exact outside the
source tree. Each distribution.json gives archive hashes/locations and explicit
generated-artifact omissions. JSON consolidation preserves parsed records; raw
originals remain archived. No binary/raw native output is normalized into text.
