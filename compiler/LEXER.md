# Aurora lexer

`compiler/lexer.au` implements the entire lexical phase in Aurora. Its
`next_lexeme(readonly span, copied cursor)` returns one token, whitespace run,
line-comment run, EOF, or lexical error per call, with the byte offset, line and
line start after it. Events cover the source contiguously, so merging them in
offset order reconstructs every input byte exactly; EOF is zero width.

Whitespace is retained in contiguous runs. Only LF starts a new line, matching
compiler diagnostics; CR, tab, vertical tab and form feed retain their exact
bytes. A `//` comment runs up to, but not including, LF and may contain any
non-LF byte. Block comments and other unsupported syntax reject. Lexical errors
are fatal and structured, with the complete attempted spelling as their span.

Single-quoted [byte literals](SCALARS.md#ascii-byte-character-literals) are one
token, including escapes and delimiters; malformed spellings use AU1002.
Double-quoted [byte-string initializers](SCALARS.md#bounded-byte-string-array-initializers)
are one token, including raw UTF-8 and escapes; malformed spellings use AU1003.
Validation constructs no decoded buffer; the 4,096 decoded-byte string bound
holds. Binary integer spellings keep their `0b`/`0B` prefix, apostrophe
separators and exact suffix as one token; malformed attempts stay whole for
semantic rejection. The [integer contract](SCALARS.md#source-contract) defines
ranges. Classification is ASCII; numeric range validation is semantic.

The resolver and the formatter lex each whole source in Aurora before parsing
it, so a lexical error anywhere precedes a grammar error. The host renders the
returned event and coordinates with `hosted_lexer::rejectLexical`; it has no
lexer or token vector of its own. The Aurora `Event` declaration is the sole
event list, and the generated header carries its values.

The private `lexer_next` bridge entry serves only the test drivers. `hosted-lexer`
reads every event of its cases through it, checks each line/column against an
independent byte scan, and compares token boundaries or the rendered diagnostic
with the reviewed golden file `tests/compiler/golden/hosted_lexer.golden`
(`--update GOLDEN` rewrites it). Its raw-record and guard-page cases exercise the
generated entry and the event values directly. `hosted-lexer-bootstrap` is the
C1/C2 stage compare.
