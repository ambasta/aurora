# Bounded ASCII next-token scanner

Current status: the bounded scanner passed the independently reviewed complete
root release native graph and separate focused fatal host sanitizer gate. See
[qualification results](token-scan-results.md). The original contract body below
retains its historical pending status and broader sanitizer wording. The dated
amendment at the end states the actual narrower accepted scope.

## Original pre-implementation contract body (historical)

Status: independently reviewed contract, frozen before implementation on
2026-10-06. Implementation and execution acceptance remain pending. Accepted
source baseline is main
`ca178a69ef1895f5ca7ce635c7761318039ff775`, tree
`de129c66e63b36eac321be0bd9f6808bc75a6918`.

## Dependency and observable acceptance gate

Self-hosting needs an Aurora-authored consumer that turns readonly source bytes
into meaningful copied token coordinates. This library milestone uses the existing
span, enum, scalar and class-value mechanisms. It does not change compiler
semantics, the parser, the host lexer, the kernel or the trusted computing base.
It adds no heap, owned string, returned reference or input-linked report.

Acceptance requires native independent-oracle and host-lexer differential results;
all-byte and signed-coordinate cases; maximal and final-window boundaries;
progress, exact source-spelling reconstruction, LF accounting and unchanged input;
copied reports after borrow release; source type/privacy/lifetime rejection;
no unresolved native runtime imports; deliberate mutation controls; complete
release and fatal host sanitizer regressions under the existing build-once
contract; a fresh full root `make test` with a matching passed `run.json` carrying
`scope: native-aggregate` and `native_complete: true`; and independent review.
Focused results alone are not full acceptance.
Each execution needs separate bounded-resource admission. Existing failed and
blocked attempts remain visible. There is no performance or memory-safety proof.

## Public surface and coordinates

`import std.token_scan;` exports:

- `TokenStatus { success, end_of_input, invalid_byte, invalid_window }`
- `TokenKind { none, identifier, digit_word, punctuation, operator_pair }`
- `TokenResult(status, kind, byte_offset, byte_count, consumed_bytes, skipped_lf)`
- `next_token(builtin::span<const u8> bytes, i64 offset, i64 count) -> TokenResult`

All four numeric arguments to the result constructor and both window arguments
are exactly i64. The result's six readonly accessors are `status()`, `kind()`,
`byte_offset()`, `byte_count()`, `consumed_bytes()` and `skipped_lf()`. Its stored
fields are private copied values, with no retained span or source authority.

The supplied span must have length 0..4096. Require `offset >= 0`, `count >= 0`,
`offset <= bytes.size()` and `count <= bytes.size() - offset`, checking those
conditions before addition or byte access. Invalid windows return
`(invalid_window, none, 0, 0, 0, 0)` without reading input. A valid empty window,
including one at the span endpoint, reports EOF at its offset. Nested subspan
inputs use coordinates relative to that supplied span, never the original owner.

The window `[offset, offset + count)` is final. A token at its boundary is complete
for this call even if adjacent owner bytes could continue it. A trailing `/`, `-`,
`<`, etc. is a single punctuation token. There is no need-more-input state.
Each call starts with no prior lexical state: a window can split a word or pair,
or start in bytes that were inside a comment in a larger containing window.
Maximal matching applies only to the current final window.

`byte_offset` is the token/bad-byte/end coordinate in the supplied span.
`consumed_bytes` starts at the requested offset and includes skipped trivia.
`skipped_lf` counts only byte 10 among consumed trivia. No line number is stored;
callers can accumulate LF counts. No bytes after the reported token are consumed.

## Exact ASCII profile

This intentionally fixes the host lexer's C-locale ASCII behavior independently
of ambient locale. Classification is by numeric byte values, not Unicode:

1. Skip whitespace bytes 9, 10, 11, 12, 13 and 32. Only 10 increments LF count.
2. At two adjacent `/` bytes, skip an opaque comment up to LF or the final
   window boundary. Every byte, including NUL, CR and 128..255, is permitted
   inside that comment. LF is then consumed by the whitespace step.
3. `[A-Za-z_]` starts an identifier; `[0-9]` starts a digit word. Both consume
   the maximal following `[A-Za-z0-9_]*` sequence. A digit word is not a
   validated integer; spellings such as `12foo`, `0x`, `7_` and `9u8` remain words.
4. Otherwise match exactly `-> == != <= >= :: << >> && ||` before a single
   punctuation byte. Adjacent other operators stay separate tokens.
5. Single punctuation is exactly `(){}[]:;,=+-*/%<>!.&|^~`.
6. Any other byte is invalid outside an opaque comment, including NUL, DEL,
   quotes, backslash, non-ASCII bytes and bytes not in the listed punctuation.

Comment detection precedes punctuation. Identifiers are not divided into keywords.
No strings, escapes, Unicode identifiers, numeric validation, block comments,
preprocessor or parser integration are introduced.

## Outcomes and recovery

- Success: non-none kind, positive byte count, exact copied token coordinates;
  consumed is skipped trivia plus the token. The token spelling is obtained by
  reading those coordinates from the still-owned source, not by storing a borrow.
- EOF: kind none, byte count zero, byte offset `offset + count`, consumed count,
  and the LF count of all skipped trivia. This can consume nonempty trivia.
- Invalid byte: kind none, byte count one, byte offset at the first unsupported
  byte, consumed trivia plus that byte, and skipped LF count. It stops before
  inspecting any suffix. This recoverable single-byte progress deliberately
  differs from the host lexer's exception; host parity concerns valid streams.
- Invalid window: all accessors other than status are zero/none.

Success and invalid-byte outcomes always advance by 1..count. EOF terminates;
invalid window is caller error. Repeated scanning decreases remaining count on
every nonterminal result, so at most count such calls are needed. The scanner
has no recursion or dynamic allocation and performs bounded linear work in the selected
window, with constant-size copied output. This does not establish compiler-wide
stack/resource bounds or throughput parity.

## Public constructed reports

Construction copies data and is not a certificate that source bytes were scanned.
An explicitly invalid-window report masks every supplied payload field. Other
reports normalize malformed shapes to invalid-window with zero/none accessors.

For every non-invalid-window shape, all numeric fields lie in 0..4096,
`byte_count <= 4096 - byte_offset`, `consumed_bytes >= byte_count`,
`consumed_bytes - byte_count <= byte_offset` and
`skipped_lf <= consumed_bytes - byte_count`. The latter two relations encode a
nonnegative inferred request start and LF counting only in consumed trivia.
Success requires identifier/digit_word with length at least one, punctuation
with length one, or operator_pair with length two. EOF requires kind none and
length zero. Invalid byte requires kind none and length one. Nominal closed enums
prevent arbitrary out-of-enum values through the supported language surface.

The scanner promises actual requested-window bounds. Constructor shape checking
alone cannot prove a relationship to a particular source/window or validate
spelling, classification, LF contents, or a source's continued existence.

## Test and scope discipline

The independent Python oracle uses anchored byte regular expressions and explicit
window slicing. A separately built host adapter invokes unchanged `aurora::lex`
under the C locale and compares token spellings and accumulated line numbers on
valid streams. Host error behavior and recoverable invalid-byte behavior are
deliberately tested separately. The host adapter is test-only bootstrap machinery.

The bounded native test retains source, assembly, binaries, all six full-width
observations, diagnostics, receipts and failures. It reuses the existing range
gate's command/resource/identity controls rather than adding a generic harness.
Mutated library copies live only under fresh test artifacts; accepted inputs and
baseline evidence must remain unchanged. No execution or receipt from the
separate blocked IPC review is reused or relabeled by this work.


## Acceptance-scope amendment — 2026-10-06

The initial phrase “complete release and fatal host sanitizer regressions” above
is retained as historical planning text. Actual accepted qualification is a fresh
complete release root `make test` plus a separate focused fatal host ASan/UBSan
`test-token-scan` run. Both passed with independent retained-evidence review.
The focused sanitizer gate instruments the host compiler and host lexer adapter
while exercising this scanner's fixtures. Generated Aurora assembly is not
sanitizer-instrumented; leak checking is disabled. It is not complete compiler
sanitizer regression or a full sanitizer native aggregate. Existing UTF-8 harnesses
were not changed merely to widen this scope. The [results](token-scan-results.md)
identify exact commands, receipts, preserved failure, resources and limitations.
