# Compiler-owned Aurora source formatting

The first `aurora-fmt` increment shares the compiler's lossless lexer, parser,
source snapshots and diagnostic ranges. It is a bootstrap C++ executable; it is
not a Python grammar or a claim of a self-hosted formatter. The optional
[language server](lsp/README.md#document-formatting) calls this same implementation
for whole-document edits; no formatter or parser is duplicated.

Build and run from the repository root:

```sh
make formatter
build/aurora-fmt examples/core_math.au
build/aurora-fmt --check --diagnostics=json examples/core_math.au
build/aurora-fmt --lint --module-root library examples/core_math.au
make test-formatter
```

Default mode prints formatted source to stdout. It does not open any output file,
modify an input file, or implement `-i`, `--write` or `-o`. Review output before
saving it. Never redirect stdout onto the input path: the shell would truncate
that file before this program starts. Input uses the same hardened Linux
no-symlink, regular-file reader as the compiler, bounded to 1 MiB. Output is also
bounded to 1 MiB before append. A limit failure emits no formatted source.

## Separate modes

- Default formatting and `--check` require syntax accepted by the existing
  compiler parser. They do not resolve imports or check types/lifetimes. An
  unresolved name can still be formatted. `--check` reports whether canonical
  formatting differs plus the bounded style findings below; it emits no source.
- `--lint` invokes the compiler's shared module-resolution, semantic and verified-IR
  checks, then reports the bounded [AU6001 unread-local rule](LINT.md). Warnings
  apply to scalar/enum locals in root-module non-template functions and methods.
  `--module-root DIR` is repeatable and applies only to this mode. This mode does
  not run style checks or format source. Warnings exit 0 and never rewrite code.
- `--check` and `--lint` cannot be combined. Run both when both are wanted.

All diagnostics, including requested JSON, go to stderr. Stdout is reserved for
validated formatted source. Exit 0 means success, 1 means `--check` found a
formatting difference or style finding, and 2 means an argument, input, compiler,
formatter-invariant or output error. Existing AU diagnostic families and imported
source ranges remain intact. Format-check JSON adds `mode: "format-check"` and a
`changed` boolean; its warnings have explicit AUF codes. Semantic-check JSON uses
the compiler's existing schema, with warning severity and success when no errors
are present. No schema promises LSP coordinates.

## Layout and preservation contract

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
other indivisible atom wider than the target stays intact and retains AUF1001.
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

Before any source bytes are printed, the formatter:

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
indentation may exceed 120 bytes. They are preserved and reported; this increment
does not promise a strict 120-column result. The limit counts bytes, not Unicode
display cells, codepoints or UTF-16 units.

Style findings are `AUF1001` (line above 120 bytes), `AUF1002` (trailing space, tab
or CR), and `AUF1003` (tab indentation or a non-four-space leading count). They have
half-open byte ranges from the shared source snapshot, with one-based byte line
and column. These are bounded lexical-style checks, not complete indentation or
style diagnostics. `changed` separately catches all differences from canonical
layout. Comment-preservation can intentionally leave a finding unresolved;
`--check` then stays nonzero even when `changed` is false. Default formatting
reports remaining findings against the output snapshot's coordinates.

## Focused validation

`tests/compiler/format.cpp` contains golden layouts, current-syntax and adversarial
cases, comment bytes and token-relative position checks, canonical versus split
template closers, nested initializers, constructor initialization, member calls,
unary/binary operators, original diagnostic rejection, bounded reads and 128
seeded trivia perturbations. Blank-line goldens cover declaration/statement/member
and comment groups, CRLF and whitespace-only runs, block/file/expression edge
normalization, attached `else`, and automatic-wrap stability. Its optional file arguments run format/reparse,
token/comment equality and idempotence on a source corpus. The Make target covers
all repository `.au` files under examples, library, kernel policies and kernel
program fixtures; any unsupported source fails visibly rather than being skipped.

`tests/compiler/format.py` only drives the real executable. It checks stdout and
stderr, status/JSON behavior, syntax-only versus semantic-check distinctions,
module roots/imported diagnostics, original error families, symlink/directory/
missing/oversized input rejection, unchanged input bytes, and unsupported CLI
write options. It does not lex or parse Aurora.

On GNU/Linux with GCC 14.2, the warning-clean focused gate passed in 47.51s:
all 77 repository `.au` sources, golden/current-syntax/adversarial cases,
128 seeded trivia variants and 30 CLI cases. Every corpus source passed
formatting, reparsing, exact token/comment-anchor preservation and idempotence.
C++/Python style checks used clang-format 22.1.8 and Ruff 0.16.7.

Independent source review and a separate 60-case boundary replay passed,
including exact 1 MiB output success, expansion/deep-nesting rejection with
empty stdout, comment anchoring, opaque bytes, CRLF and template closers.

These are focused formatter results. The main compiler is unchanged. No complete
root native aggregate, compiler regression suite, sanitizer or emulator gate was
rerun; the formatter does not replace those checks.

The [blank-line regression results](../docs/formatter-blank-lines-results.md)
record the shared CLI/LSP preservation fix and its focused validation.

## Parenthesized operands and unsupported fields — 2026-10-08

The binary-parenthesis rule repairs logical and arithmetic operands without
changing tokens. Four affected committed library/example sources have been
passed through the fixed formatter, also removing stale qualified-name wraps.
Goldens cover both logical operators, arithmetic and unary controls; CLI checks
keep those four sources canonical. The existing corpus checks still require
source-token/comment equivalence, reparsing and idempotence.

Unsupported class fields now name their type and highlight its complete source
range, rather than the following semicolon. `builtin::span<const u8> view;`
remains unsupported as a class field. The shared parser emits the distinct AU2003 classification and its
supported-storage explanation. Public/private/default visibility, other excluded
storage types, CLI text/JSON parity and unchanged source/output are covered.
The two package exact-message fixtures retain their case sources and identities;
full-corpus hash updates were checked by restoring exactly the prior messages.

Acceptance requires the focused formatter/diagnostic controls and both complete
Meson `dev` and `slow` suites on the final integrated source. The structural
correction qualification below supersedes the original LSP-process exclusion.
This repair does not claim full root `make test`, sanitizer, emulator, release
or hardware qualification.

### Structural wrapping and diagnostic classification correction

The line planner replaces the previous qualified-name exemption and arbitrary
per-token overflow breaks. Width sweeps cover nested and chained calls, comma and
binary boundaries, unary spacing, member-only oversized atoms and UTF-8 comments.
Goldens assert readable comma/operator continuations; the existing token, comment
anchor, reparse, output-bound and second-pass guards remain mandatory. Only the
four previously canonical library/example sources are reformatted in this repair;
unrelated repository formatting is not swept into the change. Compiling their
consumer closures before/after formatting must emit identical assembly.

AU2003 describes recognized but unsupported field storage; AU2001 unexpected
syntax and AU2002 nesting remain distinct. Full type spans and exact rejection
messages are preserved. See the [shared classification catalog](DIAGNOSTICS.md).
The strict negative-case source/message hash oracles remain unchanged; their text
envelope matchers explicitly recognize the new code.

### Structural correction qualification — 2026-10-08

The final terminal-policy/PR91 composition passed all 41 developer and 12 slow
Meson tests with a warning-clean optimized compiler. Focused checks passed
1,260 structural boundary cases, 128 trivia variants, 97 corpus sources,
53 formatter CLI and 77 structured diagnostic CLI cases. Independent review
replayed 672 extra boundary probes, verified exact token/comment sequences for
the four canonicalized files, and compared byte-identical assembly for eight
consumer closures and 31 kernel roots.

Actual LSP protocol runs passed 169 process cases and 18,944 assertions each
under ordinary and optimized Python; 49 transport/position unit checks passed.
The isolated warning-clean optimized server used hash-verified official
nlohmann-json 3.11.3-2.1 headers. This verifies the focused LSP protocol, not
editor UI behavior or a new full native/release qualification.

The initial developer run failed two package-envelope matches after AU2003 was
introduced. The matcher now explicitly lists AU2001/AU2002/AU2003; exact case,
message, source-hash and output-preservation oracles remain intact. That failure
and an interrupted first slow run are retained separately from the fresh final
41/12 success. The final documentation seal changes no executable/test input.
