# Native JSON focused results — 2026-10-08

This checkpoint qualifies the reconstructed, array-backed `std.json` library on
accepted PR76. The [contract](json-profile.md) defines its intentionally bounded
Unicode, lexical, structure and resource policies. It does not depend on the
separately reconstructed readonly-owner work.

## Recovery and identity

The earlier unpublished October7 workspace and native evidence were lost. Its
reported results remain historical and provide no acceptance credit here. The
Python runner was recovered byte-for-byte from retained implementation history;
the library was reconstructed and formatted, producing a different source hash.
All results below are newly executed and independently reviewed.

- Library SHA-256: `027de8b7c06fc2adb819eb33a4a1acad12f02da84f9b85f7f6c68fc0ac503b35`
- Runner SHA-256: `42885297af4a68eccd87f6fa4acfcac5e424883eb8e2a4c12d4685778e4ad39d`
- Fresh compiler SHA-256: `6756e670ccfd2dc1d94a48672915852697ab2ec08df0c09da471e37491f8afc5`

The compiler rebuilt from unchanged restored PR76 sources to the same historical
binary hash. Neither that identity nor recovered test source substituted for
fresh execution. Compiler/runtime/kernel implementation files remain unchanged.
The initial draft PR checkpoint explicitly marked the reconstruction unverified.

## Fresh native evidence

Ordinary and optimized Python each passed 2,111 cases in 136 generated native
batches, 10,768 complete i64 observations and 50 source rejection controls with
expected diagnostics and preserved output. The independent reviewer regenerated
all sources and observers, reconciled every raw native value and all 1,002
command receipts per mode, and verified current input/compiler identities.
Normal/optimized generated sources, observers, assembly and raw outputs agree.
No unresolved runtime imports were allowed by the array-backed native harness.

Independent strict CPython auditing checks 220 accepted and 577 rejected document
fixtures, with 41 explicit window/profile exclusions. Duplicate pairs are retained
for Unicode checks; numeric callbacks preserve spelling rather than introducing
float/integer conversion. Comparator mutation controls are compiler-free plumbing
checks, not native semantic mutation qualification. No fresh native failure was
suppressed or implementation fix required after execution began.

## Dependencies, tools and public entrypoints

Fresh selected dependency checks passed:

- UTF-8: 406 checks/39 fixtures, including all 1,112,064 scalars, all 256 one-byte
  and 65,536 two-byte inputs, plus 24,200 longer boundary inputs.
- Fixed containers: 216 cases, 55 exact-site traps and 96 rejections.
- Readonly spans: 91 native cases including 25 exact bounds traps, plus 69
  rejections checked with absent and existing output.
- Copied class values: 59 function-boundary checks.

The first non-UTF8 dependency invocation retained terminal logs but no standalone
argv receipt. Those three runners were replayed with exact command/source/compiler
receipts; the original logs remain. This is an evidence improvement, not a hidden
failed test. The example compiled, assembled, linked and returned 42 under its
native observer. Pinned Ruff0.16.7 and Aurora formatter/idempotence checks passed.

The public pinned `make -C compiler test-json` completed the full focused corpus
under run `test-contract-qj3aoyfp`. Its completed record is explicitly focused,
uses a sealed prebuilt compiler without rebuilding, and has `native_complete:false`.
It is not a root native aggregate. Meson1.12.1 configuration/introspection confirms
one bytes/dev JSON test, its compiler dependency/selected-artifact identity mode,
and the example's JSON/UTF8/array dependencies. No actual Meson native test/build
is claimed. Final results/status documentation followed the frozen Make run;
executable, test and routing inputs remained unchanged.

## Limits and next dependency

This gate exercises existing array spans only. Their maximum size is already
4,096 bytes, so a valid larger input window cannot be constructed through this
accepted source surface. The explicit input_limit branch is source-reviewed;
future accepted owner-backed views must exercise it before that additional native
coverage can be claimed. No old owned-input result is transferred here.

Strings are scalar-valid, duplicate keys are allowed, and numbers preserve
spelling without conversion. This introduces no DOM, decoded string allocation,
key equality/value-selection behavior, serialization or host nlohmann replacement.
No full-native, sanitizer, emulator, kernel-stack, physical-hardware, production
safety or equivalent-C performance qualification follows.

[Compact source and receipt identities](../evidence/native-json/qualification.json)
accompany this source; bulk artifacts are retained separately.
