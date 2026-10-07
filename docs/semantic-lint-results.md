# Unread-local semantic lint results — 2026-10-07

## Scope and exact source

The [bounded contract](../compiler/LINT.md) adds opt-in `AU6001` warnings for unread
scalar/enum local bindings in root-module ordinary functions and non-template
methods. It shares compiler name resolution and identifier spans. It does not
remove initializers or change ordinary compilation, and it does not publish lint
warnings through LSP yet. This is syntactic read analysis, not a path-sensitive
dead-store proof.

The base is PR65 main commit `51eddaba18142f618f41f59b2ccd08556c768ea3`, tree
`c5c80c24701ffb40d3eb6662fde69b39086468aa`. All 753 base files were verified by
SHA-256, Git blob identity and mode. The focused execution used 756 source files
with manifest SHA-256:

`a1816f5debbaa62bc4133c8f9d02ce3d7e640f8ec73909c18b18c505a338d183`

The final results documentation is a later documentation-only overlay. It does not
claim that documentation bytes were compiled. All tested implementation and
fixture bytes remain unchanged.

## Independent admission and retained failure

Independent source review accepted the resolved-local read ledger, exact lexical
spans, root/template exclusions, warning severity, whole-graph error dominance and
unchanged default compiler mode. Review first corrected a fixture using an empty
fixed-array initializer to give both required byte elements. A later source-only
regression added an unread local in a valid earlier function followed by a later
function's type error; the result must contain only the error.

The first actual focused admission built fresh candidate/baseline compilers,
formatter and frontend helper cleanly. After 39 lint cases passed, its method
fixture named `read` was correctly rejected by the existing compiler as a reserved
class member. That attempt remains failed, with original diagnostics, fixture
bytes and exit status 2. It did not reach generated-program execution.

Only the fixture method name changed to `inspect`. Independent narrow review
accepted that correction. Candidate compiler and formatter source inputs and
binary hashes stayed unchanged, so the corrected replay reused those already
fresh binaries. This was a test-fixture repair, not a compiler repair or a waived
failure.

## Focused execution

A fresh serial replay completed with exit status 0. It used GCC 14.2.0, GNU
binutils 2.44, GNU Make 4.4.1 and Python 3.12.14 on x86-64 Linux. Compiler, formatter
and direct C++ helpers used `-std=c++23 -O2 -Wall -Wextra -Wpedantic -Werror`.
The optional Meson LSP build additionally used its existing
`-D_GLIBCXX_ASSERTIONS=1` configuration and external nlohmann-json 3.11.3 headers;
no new dependency was installed or vendored.

The passing gates were:

- 62 lint CLI cases in normal Python and again under `-O`, with exact code,
  severity, message, identifier-only byte ranges, source paths and exit statuses.
- 13 shared-frontend contract checks per mode, including immutable overlay
  snapshot identity, default-mode silence, verified IR and warning/error JSON.
- Root-only lint, imports, template exclusions, lexical shadowing, sibling and
  branch identities, self-read assignments, loops, short-circuit reads, type/
  field/method/enum-case name distinctions and leading-underscore opt-out.
- Existing source errors, including a later-function error after a warning has
  accumulated, produce only the original error. Missing/self initializers,
  unreachable source, reserved names, duplicates and use-after-move still reject.
- A class-method initializer mutates its receiver even though its scalar result
  is warned as unread. Ordinary compilation and the generated native program
  preserve that effect, returning 42. Its assembly matches the fresh base compiler.
- 27 existing diagnostic CLI cases and shared lexer/parser span checks.
- Existing formatter goldens/adversarial cases, 128 seeded trivia variations,
  84 corpus sources and 30 CLI cases in each Python mode.
- 207 core compiler cases, 74 class checks, 117 scalar-template checks,
  348 function-template executions, 308 nested-value executions, 72 module cases
  and 11 bounded-depth rejection cases, using their complete existing runners.
- 7,405,472 existing initialization-fact oracle checks, including 65,536 slots.
- 49 LSP transport/position checks; 118 real-server protocol cases with 5,458
  assertions in each Python mode, including the existing formatting protocol.
- Byte-identical assembly from the fresh baseline and candidate for all 29 source
  examples in `examples/` and `library/examples/`, without path normalization.
- Pinned style checks for the new tests and already-formatted modified frontend,
  diagnostic and CLI files. Legacy parser/analyzer files were not broadly reformatted.

Every one of the 756 tested source files, the recorded host tool binaries and the
reused compiler/formatter/helper identities was rechecked unchanged after the
original successful process reached its terminal status. Commands, phase logs,
fixture inputs and comparison assemblies are retained in the checkpoint evidence.

Candidate compiler SHA-256:
`ac24f09edbb6298e6be7cd23bb235434acd326c627041e3ed812f3c334b2a252`

Fresh PR65 baseline compiler SHA-256:
`f44ecd5ae4cad266ca8cff62d42cd3970c61a4bcc04e025cd68e2b5f0656cdbd`

Independent retained-evidence and final-claim review accepted this bounded checkpoint.

## Limits

These are focused compiler/tooling results, not a fresh complete native aggregate,
a sanitizer run, a kernel/emulator gate, physical hardware qualification or a
proof of language safety. Templates, imported-module warnings, parameters and
aggregate/capability local warnings remain outside this rule. Ordinary compiler
checks and the LSP remain warning-free unless a later, explicit integration enables
semantic lint. Warnings do not change runtime code generation or authorize an
autofix.
