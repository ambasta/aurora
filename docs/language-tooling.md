# Compiler-owned Aurora tooling

Aurora's formatter, linter and language server must share the compiler frontend.
Host Python/C++ style configuration is a separate capability. The interfaces
and milestones below distinguish the implemented diagnostic, lossless-source,
formatter and initial language-server capabilities from remaining editor work.

## Current frontend boundary and remaining gaps

The [structured diagnostic foundation](../compiler/DIAGNOSTICS.md) is implemented.
`aurorac --check --diagnostics=json` uses the same module/type/lifetime and verified-IR
checks as ordinary compilation without producing assembly. It reports the first
error with an explicit diagnostic family and source range when one is available.

- `Token` retains a shared immutable `SourceText` and half-open byte ranges.
  Synthetic and some resolver diagnostics deliberately have unknown ranges.
- `lexSource` now retains exact whitespace and line-comment trivia alongside
  canonical tokens. The compiler uses the same scanner with trivia discarded.
  [Lossless reconstruction](../compiler/LEXER.md) and the standalone
  [Aurora formatter](../compiler/FORMAT.md) are implemented and tested.
- Nested-template `>>` splitting changes only the parser-owned token copy and
  gives its second closer the correct source byte. Retained lexical tokens are
  unchanged. Structured errors preserve imported-file provenance.
- `ModuleLoader` accepts [bounded immutable overlays](../compiler/SOURCE-OVERLAYS.md)
  for existing files after the ordinary source-open policy succeeds. The
  [initial language server](../compiler/lsp/README.md) implements bounded URI
  validation, full-sync version tracking and byte-to-UTF-16 conversion through
  this same frontend. New files and project-root-only analysis remain future work.
- `frontend.hpp::checkSource` is the common checking boundary. CLI text and JSON
  render the same diagnostics; full syntax-node ranges and multi-error recovery
  are not claimed.

Three separate parsers would drift from the compiler's grammar and rejection
rules. Subsequent tools must build on this shared implementation.

## Shared frontend boundary

Keep these facilities in the compiler, initially in its C++ bootstrap:

1. `SourceSnapshot`: owned immutable bytes, stable source identity and document
   version, plus a line-start index. Byte offsets are the canonical coordinates.
2. `SourceRange`: source identity and half-open byte offsets. EOF is a zero-width
   range. Validate bounds before slicing; map to line/column only at interfaces.
3. `LexedSource`: immutable token spelling/ranges and lossless trivia ranges.
   Concatenating original token/trivia slices reproduces the source exactly.
   The parser consumes token indexes; virtual `>>` closers refer to their two
   original byte positions without altering the lossless token stream.
4. `Diagnostic`: stable code, severity, primary range, message and optional
   related ranges. Human CLI text and JSON/LSP are renderers of the same value.
   Keep existing rejection wording initially; do not infer ranges from messages.
5. `ParseResult`: syntax tree, its retained source/tokens and diagnostics.
   `AnalysisResult` adds resolved declarations and checked types using the same
   module resolver and semantic rules as compilation. Code generation consumes
   a successful analysis; tooling never needs to emit assembly.
6. `SourceProvider`: authorized module-root lookup over immutable snapshots.
   CLI uses the existing bounded file reader. Editors overlay open documents
   without widening roots, following symlinks freely or trusting arbitrary URIs.

Keep parsing and analysis separate: formatting a valid file should not require
all imports to exist. Compiler success still requires complete valid analysis.
Start with full reanalysis and first-error diagnostics; incremental parsing and
multi-error recovery are later, measured changes. Recoverable editor trees must
never enter code generation as a successful program.

## Delivery sequence and acceptance gates

### 1. Source and diagnostic foundation

Add byte ranges, immutable trivia retention and structured lexical/parser errors
to the existing lexer/parser path. Preserve the compiler's current `lex` API
during migration. Use explicit unknown/synthetic ranges for compiler-created
tokens until each producer has a real origin; never report invented positions.

Gate: exact source reconstruction, zero-width EOF, CRLF/LF/tabs, comments at EOF,
unsupported bytes, nested-template `>>` and ordinary shifts; normal/optimized
host tests and unchanged compiler acceptance/rejection behavior. Test every
range is within its snapshot and no parser mutation corrupts retained tokens.

### 2. Shared check and lint commands

Expose parse/analyze without code emission, then add `aurora check` and
`aurora lint` adapters. Compiler errors remain mandatory. Begin with a small
documented lint set over source ranges and resolved syntax; warning severity
must not weaken safety errors. JSON reports use stable codes and byte ranges.

Gate: compiler/check diagnostic agreement, no output artifact on check, bounded
module graphs, consistent CLI/JSON diagnostics and positive/negative tests for
every lint. Suggested fixes are explicit non-overlapping edits for one versioned
snapshot, never silently applied by the language server.

### 3. Aurora formatter

Build a syntax-directed printer over the shared lossless source. Preserve
comments and language token meaning, apply four spaces/120 columns, and expose
stdout, `--check` and explicit in-place modes. Reject malformed/unsupported input
without rewriting the original file. Write atomically only after reparse checks.

Gate: golden layout cases, comment preservation, idempotence, semantic-token and
parse-tree equivalence, full current `.au` corpus reparse and unchanged compiler
results. Cover precedence, template closers versus shifts, visibility sections,
inline values and every supported construct. Keep intentionally invalid and
exact-byte fixtures outside bulk rewrites.

### 4. Language server

The initial optional [stdio adapter](../compiler/lsp/README.md) now covers
initialize/shutdown, full-sync document state and first-error diagnostics.
Whole-document formatting now delegates to the same compiler formatter for the
current accepted snapshot. Active cancellation and the semantic editor features
below remain separate gates and are not advertised.

Add a bounded stdio JSON-RPC/LSP adapter for initialize/shutdown, document
open/change/close, diagnostics and document formatting. Full-document changes
and full reanalysis are an acceptable first milestone. Advertise only supported
capabilities; definition/hover/completion follow when resolved symbol ranges are
available. Keep protocol output on stdout and logs on stderr.

Gate: transcript tests against shared frontend results, UTF-8 byte to negotiated
LSP-position conversion, non-ASCII comment positions, CRLF, stale versions,
cancellation, malformed/oversized messages, bounded queues and workspace-root
confinement. Standard formatting requests have no version field; edits refer to the accepted
snapshot at synchronous request handling, and clients must discard them after
a newer local edit.
No external command execution or network access is required to analyze a file.
