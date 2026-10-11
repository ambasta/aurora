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

Single-quoted [byte literals](SCALARS.md#ascii-byte-character-literals) are one
lossless token, including escapes and delimiters. Malformed spellings use AU1002
with the attempted literal span; quote-like bytes inside comments stay trivia.
Double-quoted [byte-string initializers](SCALARS.md#bounded-byte-string-array-initializers)
also remain one exact token, including raw UTF-8 and escapes. Their malformed
spellings use AU1003; literal punctuation never becomes comments or separators.

Binary integer spellings retain their `0b`/`0B` prefix, C++ apostrophe separators
and exact suffix as one token. Malformed binary digit/separator/suffix attempts
also stay whole for semantic integer-literal rejection; an apostrophe starting a
token still begins a byte literal. The [integer contract](SCALARS.md#source-contract)
defines ranges and keeps array/template capacities decimal-only.

The legacy `lex(contents, path)` API wraps the same scanner with
`TriviaRetention::Discard` and returns only tokens. Compilation therefore does
not retain a trivia vector. `Parser` owns a copy of those tokens, so consuming
nested-template `>>` closers cannot mutate a retained lexical stream or snapshot.
This is infrastructure for the Aurora formatter/LSP, not a formatter, linter or
language server by itself. [Existing-file overlays](SOURCE-OVERLAYS.md) now reuse these immutable snapshots.
Editor version tracking and position-encoding conversion remain separate work.

## Hosted Aurora lexer

`compiler/lexer.au` implements the entire lexical phase in Aurora. Its
`next_lexeme(readonly span, copied cursor)` returns one token, whitespace run,
line-comment run, EOF, or lexical error per call. It uses constant auxiliary
storage, accepts long identifiers/comments and the existing 1 MiB file limit,
and validates byte/string escapes and UTF-8 without constructing decoded
buffers. The 4,096 decoded-byte string bound and complete attempted error spans,
including suffixes, are unchanged. Numeric range validation remains semantic.
Classification is explicitly ASCII, matching the compiler's startup C locale;
comments retain every non-LF byte. C++ still owns source I/O, token/trivia vectors,
raw spelling copies, semantic constant decoding and diagnostic presentation.

The small `hosted_lexer.cpp`/`hosted_lexer.S` adapter is an explicitly trusted
bootstrap boundary, not a source-language foreign pointer constructor or C ABI.
It keeps the immutable `SourceText` snapshot alive, imports exactly its backing
and length into the existing 56-byte contiguous readonly span record (kind 0,
zero reserved words, zero starting offset), and supplies a separate 24-byte
copied cursor. The 32-byte copied result never exposes a view or source pointer.
Bounds, monotonic progress, EOF and checked coordinate narrowing are verified
before the host reads a returned range. Direct API inputs must fit the existing
signed line/column representation; file I/O remains limited to 1 MiB.
Owner-runtime descriptors are never fabricated. Generated helper symbols and
reflection entries stay local; only the host shim is externally linked.
The Aurora `Event` declaration is the sole private event list. Meson and Make
generate the host entries included by `hosted_lexer_abi.hpp` from its declaration
order; the narrow bootstrap generator rejects unsupported enum syntax. The
current numeric wire values remain 0 through 7. A generated-code fixture exercises
all eight cases through independent raw records and compares them with that host enum, including
invalid cursors. It does not infer parity from matching source text.

The bootstrap invokes `aurorac --local-symbols`, which emits local binding for
all generated functions and reflection entries without changing their ABI or
instructions. It then appends the trusted shim verbatim; no assembly-text symbol
rewriting is needed. The default binding rules are unchanged. This code-emission
option is rejected with `--check`, and it adds no source-language foreign ABI.

Build and test routes are intentionally distinct:

- Ordinary `make compiler` and `make -C compiler` build the C++ seed, use it to
  emit `lexer.au`, and link the Aurora object into hosted stage 1. The formatter
  uses the same object. Meson performs the same dependency-tracked chain.
- Canonical Meson `full`/`dev`/`core`, source-consuming native fixtures, the
  formatter and optional LSP use stage 1. IR-only fixtures do not lex source.
  `hosted-lexer` links the Aurora phase and compares it against the preserved
  C++ oracle, including all checked-in `.au` source roots. Its ABI and guard-page
  controls exercise real generated code. A separate malformed-return stub tests
  the host adapter's fail-closed checks.
- `hosted-lexer-bootstrap` has stage 1 rebuild `lexer.au` and requires identical
  emitted assembly, then compares diagnostics, assembly and rejected-output
  preservation over the source corpus. Crashes and internal failures fail the
  comparison even when both compilers fail alike. It also assembles both private
  stage outputs, checks that the shim is the sole global definition, compares
  symbol locations/sizes/types and statically linked code/data bytes against
  ordinary output, and rejects invalid `--local-symbols` option combinations.
- The historical `compiler_contract.py` `gnu-cxx-main-v1` fresh-build recipe and
  the legacy focused Make aliases entering it remain explicitly labeled C++
  seed/reference compatibility routes. Their one-command receipts are unchanged
  and do not establish Aurora-phase qualification. Externally pinned prebuilt
  acceptance uses exactly its selected binary; no lexer implementation is
  inferred merely from that mode. `std.token_scan` retains its test-only C++
  reference oracle for independent comparison.

This is an Aurora-written lexer participating in its own hosted rebuild. The
parser, semantic analysis and code generator remain C++; it is not a self-hosted
compiler or native toolchain. Focused validation and independent source review
are separate from final integrated GCC 16 full/image/guest qualification.

The focused `tests/compiler/lexer_trivia.cpp` gate checks independent positions,
exact reconstruction, bounds, token equivalence, EOF, CRLF/tabs, comment-at-EOF,
all non-LF byte values in a comment, structured rejection, canonical `>>`, and
256 deterministic generated scanner inputs. Optional filename arguments extend
reconstruction checks to a corpus.
Neither the focused gate nor a bootstrap comparison substitutes for final-source
GCC 16 full, image and affected guest qualification.
