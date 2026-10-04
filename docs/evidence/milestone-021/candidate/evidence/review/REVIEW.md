# Independent M021 function-template implementation review

Review completed 2026-10-03 UTC against the final isolated compiler pin below.

## Verdict

The independent implementation review gate passes for the final reviewed pin.
Two reproduced implementation defects were reported, fixed by the implementation
owner, and independently retested. No unresolved implementation defect was found
within this review's scope. The complete release and fatal ASan/UBSan suites remain
separate owner-run gates; this report does not certify those outcomes or authorize
mainline/kernel integration.

## Reviewed identities

- Immutable accepted M020 compiler:
  `e47a9f89369e4c0399f79f7da88cb5b4f099d7c8aa709bf108e594d7920e33c6`.
- Original M021 compiler, with both reproduced defects:
  `688fbca011d73b9750d30fdaf76d116029c7236f97ccf00416b98c00850a99d3`.
- Dependent-name correction, before receiver-precedence correction:
  `02221c88d5848d619d28ef9b9b795186a3ad25d867272adda8622077ad54984f`.
- Final independently reviewed compiler:
  `d866abc707349ca8652a966800d38bd920bd41345997f08e4b849c9bfc3b7b64`.
- Final `compiler/modules.hpp`:
  `82e558df03f2363cc6d4406971938d7c86641bbc8021b23c51b3779213cf82ad`.
- Final `compiler/templates.hpp`:
  `0014d0c3f7941dcd7350888c1b5fd86655cc14568b2f86d3e92c2ed825ab7d22`.
- All implementation headers, main.cpp and compiler/Makefile are recorded in
  `final-implementation.sha256`; that manifest's SHA-256 is
  `7798e5f81ab4b9ab7de780e473299c2723a6219f833d3d4fb3644fad3af91f46`.

Reviewed AGENTS.md, README.md, accepted completeness matrix, candidate completeness
update, FUNCTION-TEMPLATES.md, relevant existing template/value contracts, and the
implementation delta from accepted M020. Compiler snapshots are retained only in
this review evidence directory so historical failures remain reproducible.

## Defects found and resolved

### 1. Dependent-qualified names hidden in argument trees were admitted

Original `FunctionTemplateExpansion::arguments` substituted bare parameters but
did not validate each argument's qualified name. An unused body containing
`Box<T::Hidden>` compiled instead of rejecting the forbidden dependent spelling.
The same happened in nested locals, construction expressions and compile-time
reflection. If a namespace `T` with class `Hidden` existed, requesting
`exploit<i64>()` also compiled by binding the parameter-qualified spelling to the
unrelated fixed namespace.

Minimal reproductions: `qualified-shadow.au`, and the qualified-name cases from
`structural-probes.py`. Historical diagnostics and publication behavior are in
`defect-reproduction-matrix.json` and `structural-original/results.json`.

The fix validates every argument-node name before recursively substituting the
tree. Final compiler rejects the five argument-tree structural variants and the
requested namespace-collision variant with a dependent-qualified-name diagnostic.
Pre-existing output remains unchanged on these rejections.

### 2. Template-body call validation ignored receiver-member precedence

The original structural validator looked up a bare call only in the namespace.
A class template with an ordinary `helper` method and a `get` method calling
`helper(42)` was therefore rejected if an unrelated namespace-level function
template also had the name `helper`. Concrete resolution correctly prioritizes
the receiver method, so the early checker was rejecting an otherwise valid call.

Minimal reproductions: `member-shadow.au` and `member-shadow-control.au`.
The original and first-corrected pins reject the former; the final pin accepts it
and its native execution returns 42. The control also returns 42.

The fix carries the class-definition context through structural validation and
recognizes matching receiver fields/methods before namespace lookup. Seven final
regressions cover requested and unused class definitions, private methods
shadowing imported templates, real explicit and bare function-template calls,
and a field that must remain noncallable. All pass; the noncallable-field case
rejects specifically as a field invocation, and genuine forbidden template calls
still reject. See `member-regression/results.json`.

## Independent executable evidence

`summary.json` records the final run:

- 46 independently authored main fixtures: 24 native positives, 22 rejection
  fixtures, all with expected outcomes.
- Every main negative is also rerun with an absent output: 22 additional rejection
  executions. Rejected requests neither replace sentinel output nor create absent
  output. Source/module bytes are checked unchanged by the main probe runner.
- Five unchanged accepted main/examples inputs have byte-identical assembly and
  status against frozen M020 and the final compiler.
- Supplemental structural/deferred-validity probes are recorded separately;
  historical reruns are overlapping coverage, not additional independent cases.

The main runner uses an independent freestanding assembler observer, not the
project's NativeRunner. It calls the scalar test entrypoint and writes all eight
return bytes to stdout, so u64/i64 extrema are observed without truncating to a
process exit status. Native assembly and executables are retained beside each
fixture. Tools: Python 3.12.14 and GNU assembler/linker 2.44. No C++ compilation,
installation, upload, network action, kernel/image modification, or main-tree
write was performed by this reviewer.

Coverage includes:

- Scalar i64/u64/u8/bool identities and full-width results; independent branch/loop
  AST copies across scalar instances.
- Left-to-right class snapshots across an intervening mutating argument;
  independent complete 64-byte-array returns and parameter immutability.
- Equal-layout class and enum nominal mismatch rejection; independent generated
  types for same-spelling private classes from different modules.
- Exact caller-private type authority, two separately supplied private argument
  types, inaccessible fields/methods/constructors, and no arbitrary lookup of
  caller helpers or unrelated/nested private type names.
- Compile-time type authority alongside unchanged runtime-reflection visibility.
- Unused ambiguous function/template-vs-class imports; missing transitive
  function visibility; ordinary imported wrappers.
- Post-substitution nominal depth four accepted and five rejected, mixed class
  and function definition counts 64 accepted / 65 rejected, generated factory
  instance counts 256 accepted / 257 rejected, cross-module exact 256 counts,
  and repeated requests remaining interned.
- Many generated instances and independent clones, ordinary/class request order
  convergence, template-body calls with and without explicit arguments, and
  receiver-member precedence fixes.

## Source-level reasoning checked

1. **Finite phases and pointer stability.** Definitions are registered before
   structural checking; ordinary requests are collected into a separate vector
   before functions/classes are appended. Generated function copies are collected
   in a second pass that creates only class requests. Function-template bodies
   cannot recursively generate functions. Source template vectors remain immutable,
   declaration pointers refer to map elements, and active function/class pointers
   are used only after instance creation has finished.
2. **Deep copying.** Function parameters/types and recursive template-argument
   trees copy by value. Every expression and statement node is newly allocated;
   args, bodies and alternate branches are recursively rebuilt. Source templates
   cannot acquire one instance's substituted types or resolved names.
3. **Exact identity and bounds.** Interning uses declaring module/name and ordered
   resolved nominal arguments. Native names have separate generated-function
   mangling, including scalar-only instances. Combined 64/256 budgets charge
   class and function work. Nominal ancestry is recomputed after substitution,
   independently of containment limits.
4. **Authority and encapsulation.** Caller arguments undergo ordinary visible
   type/public-signature closure checks. Substitution carries exact resolved
   identities; it does not create source name lookup. Generated body authority
   admits only checked argument identities and required visible generated classes.
   Existing private-member/constructor checks are unchanged. Runtime reflection
   continues to use module visibility, not the specialization authority set.
5. **Copy boundaries and concrete lowering.** Function templates feed the existing
   concrete semantic/IR path. No new instruction or calling convention was added.
   Class-call arguments still require complete named locals and are snapshotted in
   source order; returned class values initialize fresh typed locals. Existing
   readonly, leaf/frame, initialization and IR-verification limits remain the
   relevant safety boundary.

## Deliberately deferred validity

The implementation owner explicitly clarified that definition loading validates
syntax/expansion restrictions, parameter-qualified names, forbidden template-body
calls and fixed exported-signature visibility. Ordinary specialization arity,
constraints and unresolved concrete body names are checked when requested. There
is no universal validity claim for unrequested signatures or argument tuples.

Accordingly an unrequested `Box<i64,u8>` signature for a one-argument Box, or an
unrequested local `Box<Missing>`, may be admitted. This is not counted as a defect
under the clarified contract. All five preserved deferred-invalid variants reject
normally when `never<i64>()` is requested, with specific unknown-name, wrong-kind
or wrong-arity errors and unchanged output. See `deferred-requested/results.json`.
The contract documentation should retain this explicit limitation.

## Reproduction and evidence map

From the candidate root:

- `python3 evidence/review/independent-probes.py evidence/review/aurorac-reviewed-final`
- `python3 evidence/review/extra-probes.py evidence/review/aurorac-reviewed-final`
- `python3 evidence/review/structural-probes.py` (uses current build/aurorac)
- `python3 evidence/review/finalize-review.py`

Every executed main fixture retains input, modules, compiler command, diagnostics,
assembly/native output and result JSON. Supplemental member fixtures retain full
source and command in `member-regression/`; requested deferred-invalid fixtures
are in `deferred-requested/`. `defect-reproduction-matrix.json` compares the two
minimal defects on all three retained compiler pins.

Two probe-authoring mistakes were corrected rather than counted as compiler
failures: the initial private-method negative used an invalid declaration spelling
and therefore rejected during parsing; the initial two-type authority positive
attempted an unsupported direct class-valued receiver-field return. Final probes
use valid syntax and fresh class-valued return locals. Historical fixture/result
artifacts remain retained in `independent-original/` and
`extra-fixture-correction/`. Only the final corrected run contributes to the 46
main fixture count.

## Limits

This is bounded independent source review and adversarial native evidence, not a
proof of memory safety or language equivalence. The emitted native code is not
ASan-instrumented. This reviewer did not rerun the complete regression, oracle,
fatal host sanitizer, IR-fuzzing, kernel or emulator suites; the owner is running
those separately. No physical-device, equivalent-C-performance, complete-language,
self-hosting or whole-compiler resource guarantee follows. Mainline adoption,
canonical completeness-document integration, kernel images and emulator acceptance
remain parent-controlled work.
