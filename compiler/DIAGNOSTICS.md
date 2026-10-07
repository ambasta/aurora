# Shared frontend diagnostics and check-only mode

The first language-tooling increment reuses the existing lexer, parser, module
resolver, semantic/lifetime analyzer and verified IR. It adds no parallel parser
and changes no Aurora syntax or safety rules. `frontend.hpp::checkSource` is the
shared disk-source entry point for checking and ordinary assembly generation.

```sh
build/aurorac --check --module-root library examples/core_math.au
build/aurorac --check --diagnostics=json --module-root library examples/core_math.au
```

Checking validates the complete loaded program through the same verified-IR
boundary as compilation. It never constructs an assembly emitter or output writer.
`--check` rejects `-o`, including an existing destination, without touching it.
Ordinary `INPUT.au -o OUTPUT.s` compilation remains available. Existing source
rejection wording and the `aurorac:` prefix are preserved, except that truncated
expressions/types now report a located parser error at EOF instead of leaking a
host vector-range exception. Invalid invocations consistently exit with status 2.
Successful text checks are quiet.
JSON diagnostics are currently supported only with `--check`.

## Coordinates and provenance

Every lexical token owns a shared reference to an immutable `SourceText` snapshot
with the path as supplied/opened and exact source bytes. `SourceSpan` is a half-open
range: zero-based byte offsets, one-based lines and one-based byte columns. LF
starts a new line; CR and tab each count as one byte. EOF is a zero-width range.
The lexer continues to accept non-ASCII bytes in line comments and rejects them
elsewhere under the existing language grammar.

These coordinates are **not LSP positions**. An LSP client/server must translate
against the same snapshot to zero-based lines and negotiated position encoding
(UTF-16 by default). A UTF-8 supplementary character occupies four source bytes
but two UTF-16 code units. Neither byte offsets nor byte columns may be copied
directly into UTF-16 LSP character positions. Conversion and unsaved document
updates are a later increment, not functionality claimed by this CLI.

Parser-created qualified-name ranges cover their full source spelling, including
spacing. Nested template `>>` splitting updates only the parser-owned token copy;
a retained lexical vector still describes the original token. Synthetic semantic
tokens use an unknown source range rather than a guessed location. Import error
context preserves the imported file's original span and diagnostic code.

## JSON version 1

One JSON object is written to stdout on success or failure; stderr is empty.
The envelope contains `schemaVersion: 1`, `success` and a `diagnostics` array.
Each diagnostic has `code`, `severity`, `message`, `path`, and `range`. The range
contains `start` and `end`, each with `offset`, `line` and `column` as defined
above. Unlocated errors have null `path` and `range`. Only the first failure is
reported; there is no recovery or multi-error claim. The opt-in
[semantic lint mode](LINT.md) can return multiple warnings after successful whole-
graph validation. Severity defaults to `error`; warning-only JSON has `success:
true`. Ordinary `aurorac --check` does not enable lint.

Codes are explicit stable families, not inferred from message strings:

- AU1001: unsupported lexical character
- AU2001: parser rejection / unexpected token
- AU2002: parser nesting limit
- AU3001: semantic, lifetime or verified-IR rejection
- AU4001: module loading or resolution rejection, including source I/O
- AU5001: invalid command-line invocation
- AU6001: opt-in unread scalar/enum local warning; see [exact scope](LINT.md)
- AU9001: unexpected host exception
- AU0000: unclassified internal legacy error, assigned a stage family by the shared frontend

Narrower per-rule codes may be introduced explicitly in later schema-compatible
increments. Clients should display the message and must not interpret a family
as one specific semantic rule. Not all resolver/semantic failures currently have
a located source token; unknown ranges are deliberate.

Exit status is 0 for success, 1 for a source/frontend/host failure, and 2 for an
invalid invocation. Invalid JSON-mode arguments also produce one JSON envelope.
JSON escapes quotes, backslashes and every control byte. Valid UTF-8 paths/messages
are preserved; ill-formed host-path/message bytes are escaped individually as
U+00XX, which is valid JSON but not a reversible Unicode pathname normalization.

## Focused tests

`tests/compiler/diagnostics.cpp` exercises the shared lexer/parser spans, virtual
closers, nesting rejection, unknown synthetic locations and adversarial JSON
escaping. `tests/compiler/diagnostics.py` checks CLI status, Unicode/control-byte
paths, import provenance, type rejection, no-output behavior and ordinary emission.
The compiler aggregate includes both. For a previously built matching compiler:

```sh
c++ -std=c++23 -Wall -Wextra -Wpedantic -Werror -Icompiler tests/compiler/diagnostics.cpp -o /tmp/diagnostics-tests
python3 -B -O tests/compiler/diagnostics.py build/aurorac /tmp/diagnostics-tests
```

The final 2026-10-07 candidate passed a fresh GCC 14.2 `-O2 -Wall -Wextra
-Wpedantic -Werror` compiler build, the C++ span/escaping tests and all 27 CLI
cases in 35.23 seconds. Independent review caught and the correction gate covered
empty `-o` values, full qualified-expression spans and truncated-expression/type
EOF errors. Every prefix of an array/expression sample also gets parser coverage.

A separate 23.72-second replay passed 793 checks from the existing core compiler,
classes, scalar templates, nested values, modules and bounded-depth suites. All
26 examples from that tested source snapshot compiled successfully with both the candidate and reviewed
baseline compiler and emitted byte-identical assembly without path normalization.
The kernel example used its required `kernel/policies` module root. Five negative
fixtures additionally preserved identical legacy stderr/status and existing output
bytes. Both compiler pins and all source hashes remained unchanged during execution.

An earlier regression attempt stopped because the external size sampler raced
with deletion of a test temporary file. That failed harness attempt is retained;
its sampler was corrected and all six suites and comparisons were replayed. No
product failure or storage-cap breach occurred. Independent source and retained-evidence review accepted this bounded increment.

The focused diagnostic gate itself does not assemble/link/run generated Aurora
programs; the six existing regression suites do exercise their ordinary native
fixtures. These bounded checks do not replace a full native aggregate or qualify
kernel behavior, sanitizers or QEMU. [Lossless trivia retention](LEXER.md) now
builds on this foundation; a formatter and LSP server remain separate work.
