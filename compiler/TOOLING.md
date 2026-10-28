# Diagnostics, formatting and language service

The shared frontend serves compiler checking, JSON diagnostics, conservative source formatting and language-service features. Unsupported source fails closed; diagnostic/tool support does not imply language support. [The tooling implementation](lsp/README.md) owns the transport and editor setup where present.

## Diagnostics

### Text and message contract

`Diagnostic.message` is location-neutral: it contains the explanation and any
semantic context, such as `module dep:`, without a redundant `line N:` prefix.
Coordinates belong only to `SourceSpan`. Error construction attaches the actual
lexer/parser/semantic token span; the resolver's unknown-function rejection also
retains its call token. No renderer strips arbitrary location-like message text.

Both command-line tools render shared source errors as:

```text
path/to/source.au:4:5: error AU3001: expected i64, got bool
```

The format is `path:line:column: severity code: message`, with the same one-based
byte coordinates as JSON. A source snapshot with an empty name uses `<source>`.
Unlocated errors use `tool: severity code: message` with no invented coordinates,
for example `aurorac: error AU5001: duplicate --check option`. Import context stays
in the message while the location continues to identify the imported source.
Warnings keep their warning severity. Formatter-specific layout findings keep
their existing format; shared formatter errors and semantic lint use this renderer.

Text and JSON use the same classified diagnostic and source range.
The JSON schema is unchanged, but clients must not depend on embedded location
prefixes in `message`. The LSP adapter continues converting source byte ranges to
UTF-16 positions and adds its existing explicit unknown-location marker only
when the diagnostic has no source span.

Invalid [byte literal spellings](SCALARS.md#ascii-byte-character-literals) use
AU1002; invalid [byte-string spellings](SCALARS.md#bounded-byte-string-array-initializers)
use AU1003. Both are distinct from AU1001 unsupported source characters.

### Coordinates and provenance

Every lexical token owns a shared reference to an immutable `SourceText` snapshot
with the path as supplied/opened and exact source bytes. `SourceSpan` is a half-open
range: zero-based byte offsets, one-based lines and one-based byte columns. LF
starts a new line; CR and tab each count as one byte. EOF is a zero-width range.
The lexer accepts non-ASCII bytes in line comments and valid UTF-8 within
double-quoted byte-string initializers; other token grammar is unchanged.

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

### JSON version 1

One JSON object is written to stdout on success or failure; stderr is empty.
The envelope contains `schemaVersion: 1`, `success` and a `diagnostics` array.
Each diagnostic has `code`, `severity`, `message`, `path`, and `range`. The range
contains `start` and `end`, each with `offset`, `line` and `column` as defined
above. Unlocated errors have null `path` and `range`. Only the first failure is
reported; there is no recovery or multi-error claim. The opt-in
[semantic lint mode](TOOLING.md) can return multiple warnings after successful whole-
graph validation. Severity defaults to `error`; warning-only JSON has `success:
true`. Ordinary `aurorac --check` does not enable lint.

Codes are explicit stable classifications, not inferred from message strings.
The leading family reflects the reporting subsystem, but does not replace the
failure category: recognized unsupported field storage is AU2003, not an
unexpected-token AU2001. Add an explicit enum/catalog entry for a distinct stable
category and preserve it through frontend, imports and renderers; do not classify
by message matching. Existing broad legacy families remain below:


- AU1001: unsupported lexical character
- AU2001: unexpected token or legacy general parser rejection
- AU2002: parser nesting limit
- AU2003: recognized class-field type with unsupported storage
- AU3001: semantic, lifetime or verified-IR rejection
- AU4001: module loading or resolution rejection, including source I/O
- AU5001: invalid command-line invocation
- AU6001: opt-in unread scalar/enum local warning; see [exact scope](TOOLING.md)
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

## Formatter

### Separate modes

- Default formatting and `--check` require syntax accepted by the existing
  compiler parser. They do not resolve imports or check types/lifetimes. An
  unresolved name can still be formatted. `--check` reports whether canonical
  formatting differs plus the bounded style findings below; it emits no source.
- `--lint` invokes the compiler's shared module-resolution, semantic and verified-IR
  checks, then reports the bounded [AU6001 unread-local rule](TOOLING.md). Warnings
  apply to scalar/enum locals in root-module non-template functions and methods.
  `--module-root DIR` is repeatable and applies only to this mode. This mode does
  not run style checks or format source. Warnings exit 0 and never rewrite code.
- `--check` and `--lint` cannot be combined. Run both when both are wanted.

All diagnostics, including requested JSON, go to stderr. Stdout is reserved for
validated formatted source. Exit 0 means success, 1 means `--check` found a
formatting difference or style finding, and 2 means an argument, input, compiler,
formatter-invariant or output error. Existing AU diagnostic families and imported
source ranges remain intact. Format-check JSON adds `mode: "format-check"` and a
`changed` boolean; its warnings have explicit AUF codes. Aurora renders every
finding and failure (`formatter.au`); the host copies and prints them. Semantic-check JSON uses
the compiler's existing schema, with warning severity and success when no errors
are present. No schema promises LSP coordinates.

### Layout and preservation contract

The formatter uses four-space indentation, attached block braces, one statement
per line and a 120-byte-column soft wrapping target. Constructor/class/function
blocks expand; small empty expression initializers stay `{}`. Enum members and
brace-initializer entries are placed on separate lines. Template and unary/binary
operator roles come from the existing parser AST. Intentional blank-line groups
between declarations, statements, members, initializer entries and comments retain
one empty line. Runs of empty or whitespace-only lines become one unindented empty
line. Leading/trailing empty lines, gaps immediately inside braces and gaps within
expressions are removed. An attached `else` remains attached. Only whitespace
between adjacent tokens/comments is inspected; comment contents cannot create
separators, and automatic wrapping never adds a blank line. Line boundaries follow
the shared lexer's LF contract, including CRLF input.

Soft wrapping uses explicit structural opportunities instead of an overflow
check at every token. A pending line prefers the latest fitting argument/list
comma or AST-classified binary operator boundary. Lower-priority boundaries after
an opening parenthesis/bracket, assignment, `return`, or result-type arrow are
fallbacks. Binary operators begin continuation lines. Continuations use one
indentation level beyond their block; this is a deterministic local choice, not
global layout optimization.

Member and qualified access chains (`token.value_or`, `std::ByteWriteStatus`),
unary operators, call/index punctuation and closing delimiters have no internal
soft-break opportunity. Calls can break inside their argument lists; a chained
call retains `).member(` while its arguments can wrap. A member-only chain or
other indivisible atom wider than the target stays intact and retains AUF1001,
except for the standalone oversized string-literal rule below.
Explicitly anchored line comments remain hard boundaries, including a comment
between a dot/scope token and its member; the formatter never moves that comment
across a token to force visual continuity.

Parenthesized operands retain a space after binary operators, including `&&`
and `||`. Unary operators remain attached, for example `!(condition)` and
`-(value)`. AST roles distinguish binary and unary uses; calls, indexing and
constructor argument lists retain their existing layout.

Layout is deliberately simple: it does not optimize line breaking, invent blank
separators, sort declarations or imports, reflow comments, or normalize the token
stream. For example, lexical
`>>` stays one token, while separated `> >` stays two. Valid current syntax is the
boundary; unsupported or malformed syntax gets the compiler's original rejection.

Before any source bytes are printed, the formatter, in one Aurora call:

1. Uses the shared lexer and parser on the original immutable source.
2. Changes only inter-token/comment whitespace using AST roles.
3. Re-lexes and requires the exact same token spellings, including canonical
   combined tokens, and the exact comment bytes and order. Each comment must also
   have the same count of preceding code tokens.
4. Re-parses the result using the same parser.
5. Performs one explicit second layout pass and requires byte-for-byte equality.

A failed invariant rejects the operation instead of emitting guessed or partial
source. This is a guard on this formatter, not a proof of compiler correctness.
A host write failure can still produce a partial stdout stream after validation;
there is no transactional stdout API.

Line comments retain all bytes, including a CR, tabs or trailing spaces. Outside
comments whitespace becomes LF and spaces. Indivisible tokens/comments, member/qualified chains and deep
indentation may exceed 120 bytes. They are preserved and normally reported; this increment
does not promise a strict 120-column result. The limit counts bytes, not Unicode
display cells, codepoints or UTF-16 units.

A standalone byte-string line may exceed 120 bytes because Aurora cannot split
or concatenate string tokens. It must contain only leading spaces, one literal,
and optional closing punctuation (`;`, `,`, `)`, `]`); replacing the literal with
`""` must fit within 120 bytes. Canonical layout and all other findings remain
required by `--check`. Comments, identifiers, member chains, and other code
receive no exception.

Style findings are `AUF1001` (line above 120 bytes), `AUF1002` (trailing space, tab
or CR), and `AUF1003` (tab indentation or a non-four-space leading count). They have
half-open byte ranges from the shared source snapshot, with one-based byte line
and column. These are bounded lexical-style checks, not complete indentation or
style diagnostics. `changed` separately catches all differences from canonical
layout. Comment-preservation can intentionally leave a finding unresolved;
`--check` then stays nonzero even when `changed` is false. Default formatting
reports remaining findings against the output snapshot's coordinates.

## Semantic lint

### AU6001: local binding is never read

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

### Diagnostics and command behavior

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
LSP's default first-error checking behavior do not enable semantic lint.

The shared `checkSource` API accepts `AnalysisMode::Lint` after its optional source
overlays and returns findings in `CheckedSource::lintDiagnostics`. Its default is
`AnalysisMode::Check`. The lint ledger uses existing resolved local indices and
sits outside ownership state restored at branch/loop joins. No backend decision or
IR is changed. The optional LSP reuses this result when initialized with
`initializationOptions: {"lint": true}`. Its [protocol contract](lsp/README.md#opt-in-semantic-lint)
describes session configuration, UTF-16 warning spans and versioned refreshes.


## Shared source snapshots

`Token` retains shared immutable `SourceText` and half-open byte ranges. The lexer retains exact whitespace/line-comment trivia; concatenating slices recovers input. Parser-only nested-template `>>` splitting never mutates retained lexical tokens. aurorac `--check`, `aurora-fmt --lint` and the language server's `frontend.hpp::checkSource` run the same Aurora check/lint pipeline. [Bounded source overlays](SOURCE-OVERLAYS.md) apply only after ordinary no-symlink source admission. Unknown/synthetic ranges remain explicit; full syntax ranges, multi-error recovery and incremental analysis are not implemented. The [LSP guide](lsp/README.md) owns protocol limits, UTF-16 conversion, document formatting and opt-in lint.
