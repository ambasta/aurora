# Reviewed UTF-8 library integration

The additive five-file candidate passed independent source/functional review and
was integrated after checking the M016 baseline. Existing compiler implementation,
kernel, scripts, root Makefile and old fixture inputs remained byte-identical.
Only compiler/Makefile changed among existing files, registering the new test.

- library/std/utf8.au: strict readonly decoding/validation, Unicode 17.0.0.
- library/examples/utf8_scalars.au: actual validation and decoding returning 42.
- tests/compiler/utf8.py: bounded native/oracle tests with preserved failures.
- docs/utf8-contract.md: exact API, exclusions, incremental behavior and evidence.
- compiler/Makefile: full-test registration, test-utf8 and UTF8_TEST_FLAGS.

`integration-delta.json` records exact original/final hashes.
`integration-baseline-check.json` records every copied baseline comparison.
`runtime-inputs-before.json` records unchanged implementation/runtime inputs.
The historical isolated candidate and independent manifests are retained unchanged.

## Known outcomes

Author final isolated aggregate: eight commands exited zero with pre/post input
hashes unchanged, including normal/optimized harness controls, UTF8, readonly-span
and storage suites on both release/instrumented compilers. UTF8 has 406 native
checks in 39 bounded fixtures per pin, exercising all 1,112,064 Unicode scalars,
256 one-byte inputs, 65,536 two-byte inputs and 24,200 longer boundary combinations.
The complete scalar count is 0x110000 minus the 0x800 surrogate code points.

Independent review separately passed 1,367,060 native cases per pin and additional
report/capacity/typechecking groups. It uses Python strict final-prefix decoding;
its corpus overlaps author cases and must not be added as unique coverage.
See independent/REVIEW.md and manifest.json for exact commands and limits.

Main integrated verification: both Makefile targets and example compilation passed;
the two example assemblies were byte-identical. The linked native example returned
exactly 42. All eight integrated commands have known exit zero in
integrated/result.json. Parent aggregate/smoke and milestone acceptance are separate.
No new kernel profile or fresh full-162 run is claimed by this pure-library work.

Release compiler SHA256:
14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980
Instrumented compiler SHA256:
805567b1cac1e535d0951b4ddbc02b598d9bb546bea718f7afb74d482dab94bf

## Provenance and limits

Author failures, the infrastructure-lost first shell status, explicit sanitizer
address-space accommodation and regular-file-versus-pipe distinction are preserved
in author/README.md and the contract. Final known-exit reruns replace no history.
There is no leak-checking, new compiler grammar, normalization, grapheme, path,
font or terminal completeness claim. Public report objects confer no authority.

Author and independent byte-exact originals are archived outside the distributed
source. Each distribution.json lists or describes generated binary/assembly/raw
output omissions and the archive hash/location. No binary has been normalized or
re-encoded as text. Curated receipts are text only. Archive audit/creation tooling
is not introduced into the main source tree.
