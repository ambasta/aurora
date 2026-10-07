# Bounded owning-class focused results — 2026-10-07

The [contract](../compiler/OWNING-CLASSES.md) adds private direct OwnedBytes
fields, inferred move-only class values, explicit constructor/local/function
transfers, borrowed methods and reverse normal cleanup. Independent source,
malformed-IR and handwritten-ABI review found no safety blocker in this bounded
scope. Resource-free classes and copied sector/result values retain their ABI.

## Source and compiler identities

The source starts from merged PR71 and includes the eleven-file merged PR72
smoke-entrypoint delta. The resulting base is commit
674296bd9aee5581f0552074d1c284e2f4f5cbdf, tree
3c6c9cbccfc9405ce7157e7e4c2e0849f50f7910. No smoke behavior was changed by this
compiler increment, and no new guest qualification is claimed.

The final warning-clean C++23/O2 compiler is
3653897d2c9780eaec83dc29eb156529bb167de334cad7dd72c2e7dd09985b90.
[Focused identities and counts](evidence/owning-classes-20261007/focused-results.json)
and the [independent review](evidence/owning-classes-20261007/independent-review.json)
identify source hashes, flags, Python modes and limits.

## Focused evidence

- Both Python modes passed 17 new source programs, 22 native cases, two exact
  bounds traps and 29 output-preserving rejection fixtures each. Real hosted
  allocator observations check complete release counts, order and empty regions.
- The unchanged OwnedBytes suite passed 29 native cases, four exact bounds traps
  and 29 rejection fixtures in each Python mode.
- Independently authored IR passed 17 accepted and 89 malformed cases. Ten
  handwritten hosted-runtime ABI boundaries and three deliberately broken
  backend outputs passed their required-success/failure oracles in both modes.
  Descriptor clearing, padding/canaries, register preservation, alignment, copied
  child boundaries and odd/even pending operand depths are covered.
- Thirteen affected existing frontend/class/value/template/method/byte-span
  runners passed. The short-circuit runner passed 360 executions, 80 rejection
  checks and 15 exact traps. Module/depth regressions passed 72/11 cases.
- Legacy typed IR passed 964 cases, plus existing byte-owner, field-mutation,
  method and sector IR suites. Stack probes passed 47 checks. Existing field,
  method and sector handwritten ABI suites passed 12/21/21 cases. Exhaustive
  dispatch controls and their complete native value/span/numeric probes passed.
- All 29 unchanged old examples emit byte-identical assembly against PR71.
  Seventeen owning-class fixtures retain formatter idempotence and exact assembly
  after formatting. All touched host sources pass pinned formatting/lint checks.
- The reviewed eight-file storage migration is joined without a second backend.
  All 167 joined-source consumer assemblies match the admitted inputs. Final
  storage test formatting preserves the complete Python AST, including generated
  Aurora source strings; it does not change the tested programs or assertions.
- Make and Meson register the new source, IR and ABI tests. Meson configuration
  and registration inspection passed; this is not a Meson suite execution claim.

## Preserved corrections and composite scope

The first admission failed because module resolution still rejected resource
constructor parameters; the corrected admission passed. Existing field-mutation
and general IR tests then exposed two changed diagnostic substrings. Their
original failures remain in the evidence directory; compatibility wording was
restored and both complete runners passed on replay.

A short-circuit invocation initially omitted its required artifact argument.
A comparison command initially omitted the kernel policy module root. Their
corrected invocations passed. The first formatter verification loop mistakenly
included the host driver file as a source directory; the formatter rejected that
invalid path. The corrected directory-only loop passed all 17 fixtures.

Strict storage rejection checks additionally found that an illegal owning copy
of a valid imported class pointed at its declaration. Copy barriers now receive
the actual use-site token. Independent normal/optimized regressions verify exact
copy-expression and legitimate declaration locations in separate retained source
folders; the first regression's reused-folder evidence was superseded rather
than treated as source-preserving. All 68 structured CLI diagnostics and the
shared formatter's matching copy-location diagnostic passed. The diagnostic
[review addendum](evidence/owning-classes-20261007/independent-review-diagnostic-v2.json)
records the narrow correction. Both complete language modes were rerun on the
final compiler with all 29 rejection fixtures.

The final compiler changes after earlier dependency builds are diagnostic wording,
source-token provenance and comments only. All 17 feature and all 167 distinct prepared storage-consumer
assemblies are byte-identical to their native-tested predecessors. This is an
explicit focused composite, not a claim that every run used the final binary.
The final independent IR/ABI replay verified unchanged reviewed source hashes;
the separate diagnostic addendum verifies the final semantics-header change.

No full root native aggregate, new sanitizer, emulator, kernel allocator, physical
hardware, performance comparison or general memory-safety proof is claimed.
