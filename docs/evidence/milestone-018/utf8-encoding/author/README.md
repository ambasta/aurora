# Owned UTF-8 author evidence

Final isolated aggregate: all eleven commands exited zero and implementation/test
hashes stayed unchanged. See final-acceptance/result.json and inputs.json. Both
compiler pins passed encoder186/35/24 and original decoder406/39 gates; native
example returned exactly42 with identical assembly from both compilers.

Encoder counts mean186 generated native checks across35 source fixtures plus
24 rejected compilations (12 misuse sources, absent/existing artifacts). Runtime
loops cover every scalar and surrogate. Native byte-by-byte arithmetic checks,
Python model crosschecks, plane fingerprints and decoder roundtrips are distinct
forms of evidence; fingerprints do not prove byte equality by themselves.

The earlier183-check passes and missing-constructor fixture failure are retained.
The library implementation did not change. The corrected source and final runner
hash are pinned in candidate-inputs.json. Each run records process limits and
compiler/helper hashes. Address/undefined-behavior-instrumented compiler is the
existing M016 pin; only its address-space cap is omitted for shadow reservation.
Native/tool caps remain active; LeakSanitizer is disabled, not passed. Regular-file
limits do not bound captured pipes. No performance/resource guarantee is claimed.

Per-run *-receipts.json files consolidate parsed original records. Full byte-exact
original artifacts, final source and failed fixture are preserved in the separate
archive identified by distribution.json. Generated native binaries/objects/raw
output are intentionally omitted from distributed source and never re-encoded as
text. Independent review and parent integration acceptance are separate.
