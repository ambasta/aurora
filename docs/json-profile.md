# Bounded native JSON profile

Status: the reconstructed array-input checkpoint passed fresh focused native
qualification and independent review; see [results](json-profile-results.md).
Earlier lost unpublished evidence supplies no acceptance credit.

## Dependency and acceptance gate

`std.json` is an Aurora-authored scanner and iterative whole-document validator.
It reuses `std.utf8`, `std.array`, readonly array spans and copied class results;
compiler, runtime, kernel and host nlohmann code are unchanged. The ASCII
`std.token_scan` has different whitespace/comments/number rules and is not reused
as a JSON lexer. This PR76-based increment does not depend on owner-backed spans.

Accept only after full-width native results match independent grammar/Unicode
oracles, malformed/boundary/limit cases and source type/privacy/borrow rejection
controls pass in ordinary and optimized Python, selected dependencies pass,
public focused Make and Meson routing are checked, and independent source/evidence
review completes. Preserve failed attempts and exact identities. Focused gates
never establish full-native, sanitizer, emulator, hardware or production safety
qualification. No DOM, decoded strings, numeric conversion or host replacement
is claimed.

## API and copied observations

`import std.json;` exports:

- `next_json_token(builtin::span<const u8> bytes, i64 offset, i64 count)` returning
  `std::JsonTokenResult`.
- `validate_json(builtin::span<const u8> bytes, i64 offset, i64 count)` returning
  `std::JsonResult`.
- `JsonStatus`: success, end_of_input, invalid_window, input_limit, invalid_byte,
  invalid_string, invalid_number, invalid_literal, truncated, number_limit,
  token_limit, depth_limit, invalid_structure.
- `JsonTokenKind`: none, left_brace, right_brace, left_bracket, right_bracket,
  colon, comma, string, number, true_value, false_value, null_value.

Token report accessors are `status`, `kind`, `byte_offset`, `byte_count`,
`consumed_bytes` and `error_offset`. Document report accessors are `status`,
`error_offset`, `token_count` and `max_depth`. Numeric observations are i64.
All state is private and copied. No report retains a borrow or certifies a
particular source's continued existence.

Coordinates are relative to the supplied span, including nested subspans.
The requested window is final: no adjacent owner bytes complete it and there is
no streaming/need-more-input state. Negative offset/count, offset beyond size or
count greater than size-minus-offset return invalid_window, before addition or
byte access. A valid endpoint-empty window is allowed by the scanner.

## Explicit limits

- 4,096 requested bytes, including whitespace and punctuation
- 32 simultaneously open containers; a scalar root has depth zero
- 1,024 non-EOF document tokens, including punctuation and keys
- 128 bytes per number spelling, including sign, decimal point and exponent

These are deliberate profile limits. A valid oversized window returns input_limit
at its requested offset before scanning; invalid-window checks take precedence.
On the PR76 array-span surface, a valid >4,096-byte span is unavailable. That
input_limit branch is source-reviewed, not natively reachable in this checkpoint.
A future separately accepted owner-input integration must exercise it before
claiming native coverage. Small windows within larger sources remain allowed by
the function contract; no forged host span is used for qualification.

## Lexical contract

The grammar reference is [RFC 8259](https://www.rfc-editor.org/info/rfc8259/),
sections 2–7; sections 8.2 and 9 discuss Unicode interoperability and limits.
The scalar-valid Unicode/resource rules below define this narrower profile.

Whitespace is exactly bytes 9, 10, 13 and 32. Structural punctuation is exactly
`{ } [ ] : ,`. Keywords are true, false and null. Comments, BOM, VT/FF, extra
punctuation and non-ASCII whitespace reject. Keywords and numbers must end at
EOF, JSON whitespace or structural punctuation; `trueX` and `01` reject.

Numbers follow `-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?`. There is no
numeric conversion: `1e999999` is an admissible spelling without any promise of
a representable value. Plus-prefixed, hexadecimal, NaN and Infinity forms reject.
Original spelling is preserved by byte coordinates, including negative zero.
`std.decimal` is an unsigned accumulator, not a substitute for JSON grammar.

String tokens include both quotes. Raw control bytes 0..31 reject; raw non-ASCII
uses `decode_utf8` with final input, rejecting overlong/surrogate/out-of-range
encodings, bad continuations and truncated sequences. Escapes are exactly quote,
reverse solidus, slash, b/f/n/r/t and `u` plus four hexadecimal digits. A high
surrogate escape must be immediately followed by a low-surrogate `\u` escape.
Lone low/high surrogates and reversed/mismatched pairs reject. Escaped U+0000 is
allowed; DEL and valid raw Unicode scalars are allowed inside strings. This is
stricter than JSON's permissive escape grammar. No normalization, grapheme
handling, Unicode tables or decoded string storage is introduced.

On token success, byte_offset/count identify its spelling, consumed_bytes includes
leading whitespace and the token, and error_offset is zero. EOF returns none,
endpoint offset, length zero, consumed equal to window count, and error zero.
Every successful call advances. Failures are terminal with no recovery contract:
kind and all token/consumption coordinates are zero; only error_offset is meaningful.

## Diagnostics and precedence

After window/input-limit checks, scanning is left-to-right. Bad raw UTF-8 points
to its leading byte. Truncated strings, escapes, UTF-8 and keyword prefixes point
to the final endpoint. Bad escape designators/hex digits point to the bad byte.
An unmatched surrogate points at its initiating escape backslash; an actually
missing suffix is truncated, and an invalid hex digit keeps its own location.

Incomplete number productions (`-`, `1.`, `1e+`) are invalid_number at the current
delimiter or endpoint. A valid DFA transition at the 129th number byte is
number_limit there; an invalid transition is invalid_number instead. This limit
wins before any later missing-digit error. An invalid keyword suffix is
invalid_literal at that suffix; other unsupported starts are invalid_byte.

The document validator lexes before checking token budget, then checks syntax
and the depth limit on a valid push. It excludes the over-budget 1,025th token from
token_count, includes successfully scanned syntax-invalid/depth-rejected tokens,
and excludes lexical failures. max_depth counts admitted pushes only. Failure
counts describe diagnostic prefix work, never a partially successful document.

## Whole-document validation

Exactly one root value and trailing whitespace are required. Empty/whitespace-only
windows and unfinished containers return truncated at the endpoint. Wrong/missing
commas or colons, trailing commas, non-string keys, mismatched closers and extra
root tokens return invalid_structure at the current token start.

Eight states in a 32-entry u8 array distinguish initial value/key-or-end,
required-after-comma value/key, colon, object value and comma-or-end positions.
Parent state advances before a nested push. Iteration replaces recursion; no heap
allocation is used. Progress and profile bounds give bounded linear work and
constant parser-state storage; this does not qualify kernel stack usage or speed.

Duplicate keys are allowed, including `{"a":1,"\u0061":2}`. The validator stores
no decoded keys and selects no winning value. The host LSP rejects duplicates
and has different limits/representation. Decoded strings, key equality, numeric
conversion, value storage, transport integration and serialization remain
separate prerequisites before host nlohmann replacement.

## Public constructor shapes

`JsonTokenResult(status, kind, start, count, used, error)` copies six fields.
Token offsets/length/consumption/error must be nonnegative, length and consumption
at most 4096, and offset-plus-length must not overflow. Success/EOF require error 0,
used>=length and used-minus-length<=offset. Success requires non-none/positive
length; EOF requires none/zero length. Other token outcomes require zero token
payload; document-only statuses reject. Explicit invalid_window masks every field.

`JsonResult(status, error, tokens, depth)` permits nonnegative error, 0..1024 tokens
and 0..32 depth; success requires error 0 and at least one token. end_of_input is
not a document outcome. Invalid shapes normalize to invalid_window and zero/none
accessors. Shape checks do not prove spelling, source validity or parser origin.

## Running the gate

`make -C compiler test-json` uses the controlled compiler workflow.
The bytes/dev Meson suite includes the complete JSON corpus and the example has
explicit JSON/UTF8/array build dependencies. Its selected-compiler mode records
observed artifact stability, not independent pinning or fresh-build provenance,
and is refused inside aggregate contexts.

Direct native runner: `python3 -B tests/compiler/json_profile.py COMPILER
--compiler-sha256 REVIEWED_DIGEST --artifacts FRESH_DIRECTORY`, repeated with `-O`.
`--self-test-only` runs compiler-free oracle controls only. Generated sources,
assembly, complete observations, diagnostics and identities remain retained.
