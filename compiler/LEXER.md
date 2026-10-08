# Lossless shared lexer

`lexSource(contents, path)` runs the same scanner as the compiler and returns an
owned immutable source snapshot, canonical tokens and whitespace/line-comment
trivia. Tokens and trivia carry half-open byte spans into that one snapshot.
Merging their ranges in offset order reconstructs every input byte exactly.
EOF is zero width and is not a source spelling to concatenate.

Whitespace is retained in contiguous runs. Only LF starts a new line, matching
existing compiler diagnostics; CR, tab, vertical tab and form feed retain their
exact original bytes. A `//` comment runs up to, but not including, LF. Its bytes
may include Unicode or arbitrary non-LF values, as before. Block comments and
other unsupported syntax are not newly accepted. Lexical errors remain fatal
and structured; a failed scan is never presented as a complete lossless result.

Single-quoted [byte literals](BYTES.md#ascii-byte-character-literals) are one
lossless token, including escapes and delimiters. Malformed spellings use AU1002
with the attempted literal span; quote-like bytes inside comments stay trivia.

The legacy `lex(contents, path)` API wraps the same scanner with
`TriviaRetention::Discard` and returns only tokens. Compilation therefore does
not retain a trivia vector. `Parser` owns a copy of those tokens, so consuming
nested-template `>>` closers cannot mutate a retained lexical stream or snapshot.
This is infrastructure for the Aurora formatter/LSP, not a formatter, linter or
language server by itself. [Existing-file overlays](SOURCE-OVERLAYS.md) now reuse these immutable snapshots.
Editor version tracking and position-encoding conversion remain separate work.

The focused `tests/compiler/lexer_trivia.cpp` gate checks independent positions,
exact reconstruction, bounds, token equivalence, EOF, CRLF/tabs, comment-at-EOF,
all non-LF byte values in a comment, structured rejection, canonical `>>`, and
256 deterministic generated scanner inputs. Optional filename arguments extend
reconstruction checks to a corpus. The fresh warning-clean GCC 14.2 gate passed
all 73 `.au` sources in the frozen pre-composition candidate and all generated/adversarial cases. The 27
structured-diagnostic cases and 793 existing frontend checks also passed. All
26 examples from that candidate emitted byte-identical assembly against the accepted diagnostics
compiler; five legacy rejection/output-preservation pairs were unchanged. Total
bounded gate time was 73.03 seconds. Source and compiler pins were unchanged.
Independent review accepted this bounded increment; no full native aggregate, sanitizer or QEMU
qualification is claimed.

The permanent compiler Make recipe uses explicit example and `library/std`
source-directory globs. They matched 40 files in the tested candidate and 43 in
the PR43 publication composition. The standalone gate supplied all 73 `.au` files
from its frozen source manifest. That composition contains 77 `.au` files; its
four added console/writer files do not gain coverage from this historical gate.
Neither route scans generated build output.
