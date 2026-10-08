# JSON scalar codec qualification — 2026-10-08

The library-only scalar decoding/escaping increment passed fresh focused native
checks on accepted PR78 compiler/library prerequisites. The final source also
preserves the subsequently accepted PR80 kernel/docs changes, without modifying
those compiler, runtime or library prerequisites. The [contract](json-codecs.md)
defines scope; this is not full-native, sanitizer, emulator or hardware acceptance.

## Frozen mechanisms

- `library/std/json.au` SHA-256:
  `91d96b749b40661aae0ad467875bfece6ac2fa912458d5196bdd1a298ae2e75c`
- `library/examples/json_codecs.au` SHA-256:
  `c178032a8a1f671056c332dbd6913b3788275a0a465fea45fb850049fb0397e3`
- `tests/compiler/json_codecs.py` SHA-256:
  `14432395abac011d26240410e9205ef2480463efcc676a278fc5c551dd9658c1`
- Independently reviewed, reused compiler SHA-256:
  `fde0877e0b3326bc8e6e500bb6d3a8ed9daef814af4f46ae1d319da31d707fe3`

This is selected prebuilt compiler evidence, not a fresh compiler rebuild. The
scalar helper is shared with string token scanning; ByteBuffer remains generic.
The example scans once, measures in a linear pass, reserves total output, emits
in a second pass, then validates logical owned JSON/UTF8 output views. Its
complete decoded bytes are `41000a2f225cc3a9f09f9880`; serialized bytes are
`22415c75303030305c6e2f5c225c5cc3a9f09f988022` (12 and 22 bytes).

## Fresh focused results

Each ordinary/optimized Python run independently passed:

- Codec corpus: 1,942 cases, 19,781 complete 64-bit observations, 45 source
  rejection fixtures and 431 hosted observations, across 122 scalar batches.
- Original scanner/document corpus: 2,111 cases, 10,768 complete i64 observations
  and 52 source rejection fixtures, across 136 batches.
- Supplemental real owner-input join: two programs, 41 native invocations.
  These include the exact frozen example and valid 4,096, 4,097, 5,000 and 8,192
  byte owned spans, endpoint-truncated escapes and nested relative diagnostics.

Runs overlap and are not additive coverage counts. The broad scalar corpus has
fixed-array origins; genuine larger-owner coverage is separately identified.
The independent oracle checks CPython strict Unicode/JSON prefix acceptance,
canonical escape bytes, result shape masking and full-width outputs. Hosted
checks cover actual region quotas/allocation failures, untouched existing buffer
state on failed scalar reservation, complete output bytes, invalid/empty ownership,
extreme observation indices and cleanup identities.

The [qualification record](../evidence/native-json-codecs/qualification.json)
binds retained manifests, corrected diagnostics, Make routing and supplemental
receipts. Full generated sources/assembly, raw expected and observed values,
diagnostics and logs were retained locally and independently audited. A single concise aggregate qualification record is committed. Detailed per-mode
receipts, commands, generated artifacts and independent review reports are preserved
in a separate evidence checkpoint rather than proliferated through the source tree.

## Public routing and tools

The actual supervised public focused command passed:

```
make -C compiler test-json-codecs \
  ACCEPTANCE_COMPILER=/path/to/reviewed/aurorac \
  ACCEPTANCE_COMPILER_SHA256=fde0877e0b3326bc8e6e500bb6d3a8ed9daef814af4f46ae1d319da31d707fe3
```

Its completed matching `run.json` records `origin=externally-pinned-prebuilt`,
`scope=focused`, zero compiler builds, native exit zero, and `native_complete=false`.
This is an actual public Make execution, not merely a dry run. Meson setup and
introspection verified the new `bytes`/`dev` test, selected-compiler invocation and
explicit example dependencies; no Meson compiler rebuild/native-suite pass is
claimed. Normal/optimized oracle controls and Ruff 0.16.7 checks passed. Aurora
formatting was applied and compiler admission checked with the unchanged compiler.

Direct gates are `python3 -B tests/compiler/json_codecs.py COMPILER
--compiler-sha256 PIN --artifacts FRESH_DIRECTORY`, then the same command with
`-O`; original scanner regression uses `json_profile.py`. The supplemental runner
is `tests/compiler/json_codecs_owned.py`, with the same compiler/pin/artifact
arguments. It records command stdout/stderr and expected/observed cases.

## Corrections preserved

1. The first example omitted a direct `std.array` import required by composed
   result visibility. Admission rejected it; adding the import corrected it.
2. Independent review found that an extreme negative example observation could
   underflow before copied output lookup. An explicit negative guard fixed it;
   final native tests cover minimum i64 and other negative observations.
3. `codecs-001` stopped after 1,911 cases because a test fixture used an unsupported
   empty builtin-array initializer. The explicit zero initializer corrected it.
4. `codecs-002` completed all scalar/rejection checks, then its hosted oracle
   incorrectly counted replacement staging as another live owner. Runtime accounting
   explicitly excludes that staging; the corrected expected peak is two owners
   for the example, one for a single-buffer scalar append. A separate 431-observation
   hosted diagnostic and every fresh final full gate passed afterward.
5. The first supplemental owner runs lacked persisted per-invocation output.
   They remain diagnostic. The committed runner records full commands/cases;
   fresh audited reruns supply complete evidence. The reusable runner was then
   moved to `tests/compiler/json_codecs_owned.py`, formatted and replayed as
   `normal-final` and `optimized-final`, each passing all 41 invocations.

Earlier attempts are not silently converted into passes. The source found in
unverified draft checkpoints is not qualified by later evidence for different bytes.

## Limits and next dependency

No general string container, bulk borrowed-output function, numeric JSON
conversion, DOM, key lookup, duplicate-key rejection or native transport is added.
Per-scalar append failure atomicity does not imply rollback for a previously
appended prefix or a two-buffer transaction. Huge signed-length arithmetic is
source-reviewed; no near-I64_MAX allocation is claimed. Normal cleanup is tested;
fail-stop faults do not unwind. Generated Aurora code is not sanitizer instrumented.
Host nlohmann remains in use by LSP, with its separate limits and duplicate policy.
