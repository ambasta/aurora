# Synchronous borrowed owning-object results — 2026-10-08

The [bounded contract](../compiler/BORROWED-OBJECTS.md) adds exactly one leading
named concrete owning-class `T&` or `const T&` formal to ordinary free functions.
Loans start before later argument evaluation and end synchronously. Free helpers
retain ordinary lexical privacy; ownership transfer, borrowed results, reference
fields/locals, projected/temporary arguments, templates/overloads and general
pointer support remain excluded.

`std.json_write::append_json_scalar` is the real consumer: it copies the existing
scalar encoder's at-most-six output bytes into a local array and makes one atomic
bulk append to the caller's ByteBuffer. The separate module keeps `std.json`
allocation-free. Class storage, 32-byte owner descriptors and 56-byte spans are
unchanged. Public C interoperability and nested owning composition are not added.

## Exact base and compiler

Final integration preserves merged main
`52f8f5e0de2cbd6ece494384019d4fef67ba83d0`, tree
`96a7d86d3cde8cfb72fb5a9d6b3aa0800bc96a93` (879 source files). All PR88 repaired
checks, GNU-stack handling, fast/slow routing, qualified-name formatting and NVMe
preflight behavior remain; all 22 PR87 native-disposal delta paths are retained.
Only additive documentation/formatter-test changes qualify those existing paths.

Fresh Meson 1.12.1/GCC 14.2.0 C++23 `-O2` strict-warning build selected compiler
SHA256 `64d35e5f735cb29b5d39a15619d29e417d7704a932a45b089b67d7d14dd3f80d`.
An independent reviewer checked the actual executable, compile command, link and
359-entry dependency record, including all 16 project compiler inputs. All current feature/regression source compilations use that compiler; formatter
and IR/ABI fixtures have separate recorded executable identities. Historical O0/Make binaries are diagnostic
checkpoints, not substitutes for this selection. GNU assembler 2.47.20260726 was
active for the new joined runs.

## Fresh focused gates

- Complete source/native runner: 18 programs, 74 native observations, 68 rejection
  fixtures checked with absent and pre-existing output (136 rejection executions).
  Full bytes, copied reports, allocation identities, cleanup and recoverable
  failure preservation are checked. No selected programs/rejections are omitted.
- Fast smoke: two native programs/observations and seven rejection fixtures, each
  checked twice. Its receipts explicitly declare partial coverage.
- Independently constructed typed IR: 22 accepted and 117 rejected cases, including
  loan/root/site identity, aliasing, evaluation order, constness, privacy,
  ownership/drop bypasses, CFG joins, copied results and call cycles.
- Handwritten incoming/outgoing ABI: 1,008 native cases and 14 exact rejected
  corruption controls. Records, root/result pointers, complete descriptor and
  result canaries, retained operands, alignment and private linkage are checked.
  The compiler remains the sole GNU-stack-note authority in each combined
  fixture; retained command stderr is empty.
- Final joined Meson `dev`: 40/40 passed. Final `slow`: 11/11 passed. Together these
  are all 51 non-LSP registered checks, preserving all previous 47 registrations.
  New smoke/IR gates are in `dev`; exhaustive source/helper and ABI gates are in
  `slow`. No timing or performance comparison is claimed.
- Actual public `make -C compiler test-borrowed-objects` passed with the independently
  selected prebuilt pin. Its receipt has `origin=externally-pinned-prebuilt`, no
  bootstrap build command, `status=passed`, `scope=focused` and
  `native_complete=false`. Full source/IR/ABI gates ran again, including optimized
  Python with retained raw artifacts.
- Public formatter gate passed existing goldens/adversarial cases, 128 randomized
  trivia variants, 95 current corpus sources and 47 CLI cases. Added goldens
  distinguish borrowed ampersands from bitwise AND while preserving the accepted
  qualified-name wrapping regression controls.
- Additional function-template, overload, composed/nested-value, method-value and
  readonly-span source regressions passed. A corrected short-circuit invocation
  also passed 320 fixtures, 360 executions, 40 negative fixtures/80 rejection
  executions and 15 exact traps. Original inputs remain unchanged.
- All 29 current kernel source graphs, including `examples/kernel.au` with native
  client disposal and `tests/kernel-programs/client-disposal-copy.au`, emit identical
  assembly under accepted compiler `512050d547be364fe859031417994fe5c2de69814eed4fffd801ba1e2e92fe7c`
  and the new selected compiler. No kernel implementation input is changed by
  this feature; no new guest run is claimed or used as substitute evidence.

Machine-readable scope is recorded in
[qualification.json](../evidence/borrowed-objects/qualification.json). The retained
external archive includes exact commands, source/input hashes, compiler and
fixture identities, native observations, malformed-IR logs, complete ABI
assemblies/mutants, Meson receipts, controlled Make terminal, comparison outputs
and source-join ledgers. Normal focused runs preceded the kernel-only PR87 join;
review verified their compiler/library/test inputs are unchanged. Final joined
Meson, optimized focused Make and formatter/comparison runs followed that join.
Final documentation is a separately reviewed, non-executable overlay.

## Retained corrections and limits

Earlier failures remain preserved, without acceptance credit:

- Initial source probes used reserved method names; corrected fixture names were
  replayed. IR fixtures were corrected to reach their intended ownership/backedge
  diagnostic, and a missing host timing wrapper was replaced with shell timing.
- One source fixture attempted unsupported whole-class reassignment; it now uses
  supported copied-field replacement. Copied-return rejection fixtures now bind
  typed results so the intended loan diagnostic is reached; a const-field parser
  diagnostic expectation was corrected without weakening the input.
- The new helper initially lacked direct `std.array`/`std.binary` imports required
  by public nominal signatures. Imports were fixed in `std.json_write` only.
  The allocation-free JSON probe now uses `validate_json` without an unnecessary
  copied-array signature dependency.
- Independent IR review found the owning-constructor private-call metadata gap;
  the verifier now checks lexical authority, with a rejecting regression.
- The initial ABI diagnostic run overlapped a fixture-source adjustment. It is
  explicitly excluded; fresh before/after input-bound replays supply acceptance.
- A copied stale build directory was detected and removed before any joined
  execution. The admitted Meson directory is freshly configured to the joined
  source. The initial authored 19-program estimate was corrected to the observed
  18 named programs; no coverage was removed. The extra short-circuit supplement
  initially omitted its mandatory artifacts argument; that CLI rejection is
  preserved separately from the corrected passing replay.

These are focused compiler/library results. They do not establish complete root
`make test` native qualification, new sanitizer or LSP transport/editor-UI gates,
new guest/hardware support, performance equivalence or a memory-safety proof.
Fail-stop traps do not unwind, and completed argument side effects are not rolled
back. Atomic scalar append does not promise atomic multi-append string/DOM work.
