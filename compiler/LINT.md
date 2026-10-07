# Compiler-owned semantic lint

`aurora-fmt --lint` checks the complete source graph through the compiler's existing
module loader, parser, resolver, lifetime/type analyzer and verified IR. Successful
checks additionally collect the opt-in rule below. No second parser, source-name
scan, source rewrite, initializer removal or code action is involved.

```sh
make formatter
build/aurora-fmt --lint --module-root library examples/core_math.au
build/aurora-fmt --lint --diagnostics=json examples/core_math.au
make test-lint
```

## AU6001: local binding is never read

A warning covers the exact identifier token of an unread local declaration. This
first rule includes mutable and const `i64`, `u64`, `u8`, `bool` and enum locals
inside ordinary functions and non-template class methods in the root module.
Nested blocks and lexical shadowing use the compiler's resolved local identities.
Parameters, class values, arrays, owners, references and spans are excluded.
Function templates and generated class-template methods are excluded, whether or
not a template was instantiated. Imported modules still receive the full compiler
checks but do not contribute lint warnings; lint a dependency as the root to
inspect its ordinary functions and methods.

A leading underscore opts out: `_`, `_result` and `_intentional` are ordinary
valid identifiers with the same language behavior as before. The suppression is
a lint convention, not a discard expression or a permission to skip evaluation.
The compiler-reserved `__au_` prefix remains forbidden.

This is syntactic read analysis, not a path-sensitive dead-store proof. Writes
alone do not count as reads. A read in any checked branch, loop or short-circuit
operand counts even if the condition is constant. `value = value + 1` reads the
binding. A same-spelled field, method, type or enum case does not read a local.
An inner binding's initializer can read its outer namesake before the new binding
enters scope. The compiler's existing unreachable-statement errors are unchanged.

An initializer may have observable effects even when its result is unread. This
rule only warns; it never deletes an initializer, a binding or a later assignment.
Use a meaningful underscore-prefixed name when deliberately retaining an unused
result. No autofix or lint-driven optimization exists.

## Diagnostics and command behavior

Warnings use stable code `AU6001`, severity `warning`, the message
`local binding 'NAME' is never read`, and the shared half-open source byte range.
The parser retains the original identifier span, including its immutable source
snapshot. Findings are ordered by declaration byte offset in the root source.
They become available only after the complete graph passes semantic analysis and
IR verification. Any source error instead reports the existing first error, with
no misleading partial warning result.

Text and JSON diagnostics go to stderr; stdout remains empty. Warnings exit 0.
An existing argument/input/compiler failure exits 2, as before. JSON retains
schema version 1 and the existing diagnostic fields; `success` means no error
severity diagnostic, so a warning-only result is successful. `--check` remains the
separate formatting/style check. Ordinary `aurorac`, its `--check` mode and the
LSP's first-error checking behavior do not enable semantic lint.

The shared `checkSource` API accepts `AnalysisMode::Lint` after its optional source
overlays and returns findings in `CheckedSource::lintDiagnostics`. Its default is
`AnalysisMode::Check`. The lint ledger uses existing resolved local indices and
sits outside ownership state restored at branch/loop joins. No backend decision or
IR is changed. The optional LSP does not yet publish these warnings or expose a
configuration switch; it can reuse this frontend result in a later increment.

## Focused verification

`make test-lint` builds the current formatter and compiler, exercises exact spans,
warning/error transport, scope/branch/loop behavior, exclusions, no source writes,
ordinary check behavior, source overlays and a native side-effecting initializer.
`tests/compiler/lint.py` accepts `--baseline COMPILER` for an additional exact
assembly comparison and `--artifacts DIRECTORY` to retain all fixture results.
Python checks remain active under `-O`. The C++ helper verifies exact overlay
snapshot identity and the shared JSON severity contract.

The [dated results](../docs/semantic-lint-results.md) record 62 cases per Python
mode, exact frontend and native-effect checks, complete selected regression
runners, unchanged example assembly and shared formatter/LSP compatibility. They
preserve the failed reserved-name fixture admission and its corrected replay.
These focused tests are not full native acceptance, a proof of compiler safety,
a complete unused-value analysis, or hardware/emulator qualification.
