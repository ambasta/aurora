# Independent compiler review: bounded nested generic values

## Result

**No actionable implementation defect reproduced in the bounded scope below.**
The frozen compiler implementation is suitable to advance to the coordinating
integration decision, subject to the separately required full sanitizer and
integration gates. This is a source review and finite adversarial test result,
not a proof of whole-compiler safety or a claim about untested kernel behavior.

## Exact inputs and tools

- Candidate: `/workspace/scratch/48c5de6446f8/aurora-nested-values-next`
- Original implementation comparison: sibling `aurora/compiler`
- Frozen compiler manifest SHA-256:
  `4a9847eddc4419cf032ac449ec63f64bee808ca480fdaf3512616e39c56ca9a9`
- Release compiler SHA-256:
  `e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6`
- ASan/UBSan compiler SHA-256:
  `78379d081bfae56608a6a60e72bc290e9abd68e88b1a9c3e96f93d25b007cfb5`
- Immutable differential baseline: `/tmp/aurora-resource-main-compiler-frozen`
- Baseline compiler SHA-256:
  `14cbaa33b69b81240b5828b6893f4c150eeaa9a11d95a83726d32e417c1f8980`
- Python 3.12.14; GNU assembler and GNU ld 2.44.

All files listed in `receipts/compiler-frozen-review.json` were independently
rehash-checked against the manifest, with no mismatch. The reviewer changed no
candidate implementation, original source, library, kernel, or project test file.
All authored probes and receipts are under `review/independent-compiler`; their
small source/native transient artifacts are under `tmp/independent-compiler`.
No compiler or C++ test-binary build was launched by this reviewer. No network,
installation, authentication, GitHub, or kernel-image operation was performed.

## Source review

Read AGENTS.md, README.md, completeness matrix, NESTED-VALUES.md, the template,
composition, enum/result, fixed-container and module contracts, and compared the
four changed implementation headers against the original:

- `parser.hpp`: bounded recursive concrete argument trees; contextual one-closer
  consumption from `>>`; non-mutating balanced declaration/construction lookahead;
  no lexer or arithmetic precedence change. The parser refuses explicit template
  references within a template definition, including otherwise-concrete bodies.
- `types.hpp`: frontend-only unresolved child arguments; nominal concrete types
  and resolved metadata remain distinct from their presentation names.
- `templates.hpp`: unresolved-child guards before type substitution and both
  identity encodings; concrete copies retain the existing Scalar/Value/capacity
  checks. No dependent-body expansion mechanism was added.
- `modules.hpp`: requests are collected before class-vector append operations;
  recursive expansion only follows the bounded source tree; inner arguments are
  interned before parents; template definitions reside in the separate unchanged
  template vector; map-backed declarations retain stable addresses. Parent tuples
  use exact resolved class/enum identities. Existing instance records, public
  signatures and direct-import checks provide the transitive visibility closure.
  Instantiated bodies still use their defining unit and lexical helper lookup.

Also inspected unchanged semantic containment/copy checks, native layout and IR
validation. Type equality rejects nonempty unresolved template metadata at the
concrete boundary. The change introduces no IR instruction, backend operation,
ABI, or calling convention. Source class-depth/leaf checks remain independent of
source template-id depth. Existing nominal/class/enum validity rules remain in
force rather than being reimplemented in the new resolver.

## Independent executable probes

Command, from the candidate directory:

```
python3 review/independent-compiler/probe.py
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
python3 review/independent-compiler/probe.py build/san/aurorac \
  review/independent-compiler/results-sanitized.json
```

**78 cases passed independently on each compiler: 31 accepted/native executions,
47 exit-1 rejections.** Repeated release/sanitizer executions are the same 78
cases, not additional distinct coverage. ASan shadow memory was not restricted
with RLIMIT_AS. Native positive programs are assembled and linked through an
independent Linux `_start` bridge; their complete 64-bit results are checked.
Every rejection preserves an existing sentinel output, and every source/import
hash is checked after compilation.

Coverage includes:

- All intended frontend positions: mutable/const locals, constructors, ordinary
  function parameters/results, class fields/constructor signatures, copied method
  results, static type/size/field queries and runtime reflection views.
- Class and template depths four accepted/five rejected independently, including
  phantom templates whose argument depth does not affect class containment.
- Exact 64 versus 65 leaves, capacities 1 and 64, rejected capacities 0/65,
  canonical `03`/`0003` identity, template definitions 64/65, and exactly 256
  inner-plus-outer instances versus a 257th unique instance.
- Child-first IDs with the outermost request appearing first; deduplication;
  ordered same-layout scalar arguments and nominal enum distinctions.
- Deep copies, empty descendants, nested enum values, full binary argument trees,
  array privacy, snapshots before later argument mutation, copied results, and
  forbidden nested-field assignment/chained receiver/temporary-value boundaries.
- Requesting lexical scope, defining-module helper binding, private arguments,
  phantom-private arguments, transitive-only imports, public inner signatures,
  direct-import positive controls, and unavailable runtime metadata returning zero.
- Scalar rejection of classes/enums; builtin-array/owner/reference/span arguments;
  wrong kind/arity, forbidden concrete template bodies, malformed extra/missing
  closers, spaced/newline/commented closers and long qualified names.
- 10,000-open-template, 10,000-extra-closer and 10,000-wide-argument malformed
  inputs, all normal bounded rejections rather than signals or output replacement.

Receipts: `results.json`, `results-sanitized.json`, `release.log`, `sanitized.log`.
Each JSON case records the exact source/import paths and hashes, invocation,
compiler pin, status, diagnostic and expected/actual native result where relevant.
The generator fully recreates every fixture.

## Arithmetic differential control

```
python3 review/independent-compiler/differential.py
```

**694 independently generated source inputs, seed 48151623: 520 accepted and 174
rejected; zero compiler-status or emitted-assembly differences.** The 400
randomized type-directed numeric trees and 294 unparenthesized combinations
exercise shifts, relational/equality comparisons, bitwise expressions, explicit
narrow-width types, named operands, parentheses and unchanged precedence.

The differential control compares compile admission and exact emitted bytes; it
is not an independent runtime arithmetic oracle. Expected trap-producing sources
need not execute for this control. Rejection artifacts remain the same sentinel.
`arithmetic-differential.json` retains every source, source hash, status,
diagnostic and output hash, plus both exact compiler pins.

## Limits

This review did not run a separate full compiler aggregate, kernel/emulator gates,
physical hardware, or a general performance benchmark. The coordinator owns those
required gates. Existing aggregate results are not counted in this independent
probe total. The source review is scoped to this bounded concrete nested-value
extension and its unchanged semantic/IR interfaces; it is not a whole-language
security audit. No implementation change was requested by this review.
