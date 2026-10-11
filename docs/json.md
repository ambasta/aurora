# Bounded JSON

`std.json` provides allocation-free scanning, validation, scalar decoding and lookup. `std.json_write` composes these with the explicitly owned `ByteBuffer`; `std.decimal` supplies generic integer formatting. Copied reports retain no source authority. The host LSP still uses nlohmann JSON: no DOM, general serializer, transport integration or host-library replacement is implemented.

## Scanner and whole-document validation

### API and copied observations

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

### Explicit limits

- 4,096 requested bytes, including whitespace and punctuation
- 32 simultaneously open containers; a scalar root has depth zero
- 1,024 non-EOF document tokens, including punctuation and keys
- 128 bytes per number spelling, including sign, decimal point and exponent

These are deliberate profile limits. A valid oversized window returns input_limit
at its requested offset before scanning; invalid-window checks take precedence.
Runtime-owned spans can exceed that limit; a smaller selected window within a larger owner remains supported. No forged span is needed or accepted.

### Lexical contract

The grammar reference is [RFC 8259](https://www.rfc-editor.org/info/rfc8259/),
sections 2–7; sections 8.2 and 9 discuss Unicode interoperability and limits.
The scalar-valid Unicode/resource rules below define this narrower profile.

Whitespace is exactly bytes 9, 10, 13 and 32. Structural punctuation is exactly
`{ } [ ] : ,`. Keywords are true, false and null. Comments, BOM, VT/FF, extra
punctuation and non-ASCII whitespace reject. Keywords and numbers must end at
EOF, JSON whitespace or structural punctuation; `trueX` and `01` reject.

Numbers follow `-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?`. The scanner performs no
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

### Diagnostics and precedence

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

### Whole-document validation

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
and has different limits/representation. The scalar codecs, decoded-key lookup and integer conversion below provide bounded operations. Owned decoded strings, general value storage, larger transport budgets and full serialization remain prerequisites before host nlohmann replacement.

### Public constructor shapes

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

## String scalar codecs

### Copied APIs

Import `std.json` and `std.array` directly; callers using UTF-8 result types also
import `std.utf8`. The module's composed result types use existing visibility rules.

`decode_json_string_scalar(span<const u8> bytes, i64 offset, i64 count)` returns
`JsonScalarResult`: `status`, `scalar_or(u64)`, `consumed_bytes`, `error_offset`.
The window contains string **content**, without enclosing quotes. One call reads
one scalar, not a whole string or document. Success consumes 1..12 bytes; empty
input yields `end_of_input`; raw quotes and bytes 0..31 reject. Other raw bytes
use strict final UTF-8. Escapes and surrogate pairs follow the existing JSON
profile exactly. Decoding U+0000 succeeds and is distinct from failure.

Offsets are relative to the supplied span, including nested subspans. Negative
coordinates and count exceeding size-minus-offset reject as `invalid_window`
before addition or byte access. Every window is final: adjacent bytes never
complete it. There is no streaming state or 4,096-byte scalar-reader cap: one
call examines at most 12 bytes. The token/document scanner retains its separate
4,096-byte profile limit. Runtime-owned spans provide larger backing without changing the scalar reader’s bounded work.

Raw invalid UTF-8 points to its leading byte; truncation points to the endpoint.
Invalid escape designators/hex point to the bad byte. Unpaired or mismatched
surrogates point to the initiating backslash; missing viable suffixes are
truncated. The scanner and decoder use one private scalar helper, preserving
scanner diagnostics. Failure consumes zero and masks scalar payload. EOF has zero
consumption/error. No result retains a borrow or certifies source identity.

`escape_json_scalar(u64)` returns `JsonEscapeResult`: `status` (`JsonEscapeStatus`:
`success`, `invalid_scalar`), `size`, `byte_or(i64,u8)`. Quote/backslash and
backspace/form-feed/newline/carriage-return/tab use short escapes; other U+0000..001F
use lowercase `\u00xx`; slash stays literal; other scalars use raw UTF-8. Surrogates
and values beyond U+10FFFF reject. Output excludes enclosing quotes and has 1..6
bytes. Six is the maximum encoding of one scalar, not a fixed-size string API.
No normalization, ASCII-only mode or source-spelling preservation is implied.

Constructors are ordinary copied-value constructors. `JsonScalarResult(status,
scalar,used,error)` masks every invalid-window payload; success needs valid scalar,
1..12 used and zero error. EOF requires zero scalar/used/error. Other admitted
statuses are invalid_string/truncated with zero scalar/used and nonnegative error.
Other shapes normalize to invalid_window. `JsonEscapeResult(status,array<u8,6>,
width)` accepts success only for widths 1..6; other shapes mask size and bytes.
Constructor shape checks do not prove that user-supplied bytes are canonical JSON.

## Integer conversion and decimal encoding

### Conversion API and grammar

`std.json` exports `parse_json_i64(span<const u8>, i64 offset, i64 count)` and
`parse_json_u64` with the same parameters. They return copied `JsonI64Result` and
`JsonU64Result` respectively, exposing `status`, typed `value_or(fallback)` and
`error_offset`. No source borrow escapes or source identity is certified.

`JsonIntegerStatus` is success, invalid_window, invalid_number, number_limit,
unsupported_number_form or out_of_range. Input must be exactly one JSON number
spelling: no leading/trailing whitespace or punctuation. Use scanner token byte
coordinates to select a spelling, but parsing always revalidates the actual bytes.
A copied or user-constructed token is not an authority to skip validation.

Checks proceed in this order:

1. Negative offset/count, offset beyond span size or count greater than
   size-minus-offset return invalid_window, before addition/access.
2. Reuse the JSON DFA and its 128-byte number-spelling limit. Its invalid-transition
   versus 129th-byte limit precedence remains unchanged. Any unconsumed suffix,
   including whitespace or punctuation, is invalid_number at its first byte.
   Empty input is invalid_number at the endpoint.
3. A valid spelling with a decimal point or exponent returns
   unsupported_number_form, including `1.0`, `1e0` and `1e999999`. These are valid
   JSON numbers; this API does not evaluate their mathematical integer value.
4. Accumulate the already validated integer magnitude with DecimalAccumulator,
   then apply the signed or unsigned range.

Syntax/limit errors therefore win over range errors, even when overflow occurred
in an earlier prefix. Leading zeros (`01`, `-01`), plus-prefixed numbers, NaN,
Infinity, hex and incomplete productions reject as invalid_number. Window endpoints
are final; adjacent backing bytes cannot complete a spelling. Coordinates are
relative to the supplied span, including nested subspans.

The accepted range is [-9223372036854775808,9223372036854775807] for i64 and
[0,18446744073709551615] for u64. Negative nonzero integers are out_of_range for
u64. Both accept `-0` as zero: conversion loses its sign, while scanner coordinates
still preserve original spelling. Signed-min conversion handles magnitude 2^63
explicitly; no out-of-range cast or minimum-value negation is evaluated.

Success has error 0. Syntax/limit errors preserve precise DFA coordinates; semantic
form/range errors point to the spelling start. Failures expose only the caller's
fallback. Unlike the separate 4096-byte document profile, this scalar primitive has
no whole-window cap: it inspects at most the bounded numeric prefix before failure.
A valid oversized owner span is not evidence of a valid oversized number.

Public constructors `(status, typed value, i64 error)` are ordinary copied values.
Invalid_window always masks payload/error. Negative error, success with nonzero
error, or failure with nonzero value normalize to invalid_window. Shape checks do
not prove parser origin or source spelling. There is no consumed-byte field because
success always covers the complete exact window.

### Generic decimal serialization

`std.decimal` exports `format_decimal_i64(i64)` and `format_decimal_u64(u64)`.
Both return `DecimalEncodingResult` with `status` (DecimalEncodingStatus success or
invalid_shape), `size` and `byte_or(i64,u8)`. Import `std.array` directly when using
this composed result under the existing module visibility rules.

Every integer input formats successfully as canonical ASCII decimal, without a
plus sign, leading zeros, fractional part or exponent. Zero is `0`. This generic
encoding is already JSON-compatible; no duplicate JSON formatter wrapper exists.
A private 20-byte array is a mathematical bound on one encoded integer: u64 max
has 20 digits; i64 min has 19 digits plus minus. It is not a fixed-size string API.
The signed magnitude uses `u64(-(value + 1)) + 1u64` when negative, avoiding
`abs(I64_MIN)` and checked-cast overflow. Division/remainder by ten generate digits.

The public `(array<u8,20>, i64 width)` copied constructor accepts widths 1..20;
other widths report invalid_shape, size 0 and fallback bytes. It certifies only
shape, not that arbitrary caller-supplied payload is canonical. Out-of-range byte
indices, including extreme signed values, return fallback before array access.

## Decoded-key and array-index lookup

### Copied APIs

`lookup_json_member(bytes, offset, count, key, key_offset, key_count)` accepts two
`builtin::span<const u8>` parameters and four i64 coordinates.
`lookup_json_element(bytes, offset, count, index)` accepts one readonly span and
three i64 values. Both return `JsonLookupResult` with `status`, `kind`,
`byte_offset`, `byte_count` and `error_offset` accessors.

`JsonValueKind` is none, object, array_value, string, number, true_value,
false_value or null_value. `JsonLookupStatus` is success, invalid_window,
input_limit, invalid_byte, invalid_string, invalid_number, invalid_literal,
truncated, number_limit, token_limit, depth_limit, invalid_structure,
invalid_key_window, key_limit, invalid_key, invalid_index, wrong_root, not_found
or ambiguous. Existing `JsonStatus` and old result contracts are unchanged.

Only direct members/elements of the window's root container are selected. A
member name is plain strict UTF-8, not a JSON-escaped spelling. Empty names,
NUL, controls, quotes and backslashes are valid query content. Compare decoded
Unicode scalar sequences exactly: no normalization, case folding or grapheme
semantics. A literal backslash followed by `u0061` is not the name `a`.

Zero matching root members gives not_found, one gives success, two or more gives
ambiguous. Only matching duplicates cause ambiguity; unrelated duplicates and
nested equal names remain accepted. Array indices are zero-based i64; negative
indices are invalid_index, arbitrarily large nonnegative indices are not_found
after full validation. Valid roots of the wrong kind give wrong_root.

### Precedence, limits and errors

Order is fixed:

1. Document bounds, using subtraction before addition or byte access.
2. Document count above 4096: input_limit at document offset.
3. Query bounds (invalid_key_window) or negative index (invalid_index).
4. Query count above 4096: key_limit at query offset.
5. Complete strict final UTF-8 query validation: invalid_key.
6. Whole-document validation, preserving original diagnostics and statistics.
7. Only after valid EOF: wrong_root, then ambiguity/absence/success.

Query failures need not validate the document. Once document scanning starts,
every document failure wins over all lookup outcomes, including an early found
value or duplicate match. The document retains 1024-token, 32-open-container and
128-byte number-spelling limits; punctuation and keys consume tokens. Lexing
precedes token-budget rejection, syntax/depth failures include their scanned
token, and peak depth counts admitted pushes only.

Coordinates are relative to each supplied span, not to the requested window.
For document failures, error_offset follows the existing JSON contract. For
invalid_key it addresses the query span: invalid UTF-8 points to its leading
byte, incomplete final UTF-8 to the query endpoint. Ambiguous points to the
second matching root key's opening quote. Wrong_root, not_found, invalid_index
and window errors have error zero. All non-success results mask kind to none
and byte_offset/byte_count to zero. No first or last ambiguous winner escapes.

Successful extents exclude surrounding whitespace, member names, colons and
commas. Strings include both quotes; containers include both delimiters and
internal whitespace; other scalars preserve exact spelling. Window endpoints
are final: adjacent bytes cannot complete them. A small window inside a larger
owner remains valid, so offsets are not capped at 4096.

### Shared bounded mechanism

One private iterative walker supplies both validate_json and lookup. The original
32-entry state stack is shared; optional observation uses copied scalar state.
The private copied request respects the current six-parameter ceiling; no
borrowed reference or callback capability is introduced. No span is stored in a
class or result.

Root keys are observed before transition at depth one/object key states; root
values at the object value state or array value states. A selected container
closes when its matching delimiter returns depth to one. The original
root_complete flag marks root start, not completion. Candidate observations
remain private until the whole requested document reaches valid EOF.

The requested UTF-8 name is validated once. After string lexing, each relevant
root key has at most one monotone scalar comparison pass. Comparison stops at
the first mismatch and requires both endpoints together. It never revalidates
a whole token per scalar or a whole query per member. Saturating duplicate
count at two allows further comparisons to stop without stopping validation.
Work is O(document bytes + query bytes), with bounded constant parser storage
and no heap allocation. This is an algorithmic bound, not a speed benchmark.

### Constructors, ownership and authority

`JsonLookupResult(status,kind,start,count,error)` copies private fields. Success
requires nonnegative offset, nonoverflowing offset-plus-count, count 1..4096,
non-none kind and error zero. String/object/array need at least two bytes,
numbers at most 128, true/null exactly four and false exactly five. Failures
require zero/none selection payload and nonnegative error; query-window,
negative-index, wrong-root and absent outcomes require error zero. Explicit
invalid_window masks every field; malformed shapes normalize to it. Constructor
shape checks prove neither source identity, grammar nor parser origin.

Reports retain no borrow and can outlive both inputs. A live owner-backed span
freezes its root under existing rules, including zero-length views. When that
borrow ends, source mutation is allowed; copied coordinates are then historical
observations, not authority over the current bytes. Recheck bounds and content
when applying them to changed storage.

ByteBuffer.bytes() exposes logical length only, never spare capacity or bytes
hidden by truncate/clear. Check allocation success before borrowing: the current
failed-owner borrow contract traps rather than returning a JSON status.

## Transactional quoted UTF-8 append

In module `std.json_write`, `std::append_json_string(ByteBuffer& output,
builtin::span<const u8> input, i64 offset, i64 count)` appends one complete JSON
string, including its two quotation marks. Its input is raw final UTF-8, not JSON
escape syntax. It uses the existing canonical scalar escaping: short escapes for
backspace, tab, newline, form feed and carriage return; lowercase `\u00xx` for
other controls; escapes for quotation marks and backslashes; ordinary UTF-8 for
other Unicode scalars. Slash is not escaped. Empty windows append `""`.

The copied `JsonStringAppendResult` exposes `status()` and `appended_bytes()`.
Success counts include both quotation marks. Failure reports expose zero appended
bytes. A publicly constructed success report with fewer than two bytes is
normalized to `append_failed`; all other failure reports expose zero regardless
of their supplied count. Reports retain no owner, borrow or allocation authority,
and their public construction does not prove that an append occurred.

### Copied append-report invariants

Both `JsonAppendResult` and `JsonStringAppendResult` normalize their supplied
status once during construction using nonexported scalar helpers. A scalar
success count must be 1..6; a string success count must be at least two. Invalid
success counts become `append_failed`. Every other declared status remains
unchanged for every `i64` count. The private raw count is retained; `appended_bytes()`
returns it only for success and otherwise returns zero before caller arithmetic.
Neither report has a field-mutating method. `status()` is therefore a plain read.

Private-field initialization and complete-copy guarantees preserve these normalized reports through copies, returns, projections and field replacement. They do not certify that output was changed.

### Failure order and preservation

1. Negative offset/count, an offset past the input, or a count greater than
   `input.size() - offset` produces `out_of_range`. No addition precedes these
   window checks. A zero-length window at any in-range offset is valid, regardless
   of surrounding bytes.
2. Decode the selected window from left to right with final-input UTF-8 semantics.
   A malformed sequence gives `invalid_utf8`; a valid but incomplete suffix gives
   `truncated`. A malformed available byte wins over missing later bytes, following
   `decode_utf8`. The first encountered decode or escaped-size overflow failure
   wins. Each canonical escaped width is checked before addition; total size
   starts at two for the quotes. Size overflow gives `overflow`.
3. After complete validation and measurement, check the total against
   `I64_MAX - output.size()`. Failure gives `overflow`.
4. Reserve the complete final capacity once. An invalid output owner, quota or
   allocator failure gives `append_failed`.

Every recoverable failure preserves existing output bytes, size, capacity and
committed region accounting. Allocation attempts may still affect diagnostic
counters or a host fault injector. Completed argument evaluation side effects are
outside this transaction. Fail-stop arithmetic/bounds faults do not unwind.

### Why the emission pass cannot fail recoverably

Successful reservation proves that the owner is valid and its capacity is at least
old size plus the measured total. The source is an immutable span of a different
storage owner; the compiler's leading mutable owner borrow excludes all same-root
aliases, even empty or disjoint views. Distinct owners may share one region.
Neither codec modifies the source or invokes callbacks. Re-decoding therefore
produces exactly the same valid scalars and positive widths as the first pass.

The opening quote, each `append_json_scalar` call and the closing quote fit within
that single reserved capacity. Intermediate lengths are bounded by the already
checked final length. The scalar helper's fixed local array does not allocate,
and its bulk append cannot grow while the reserved capacity suffices. Therefore
all emission calls succeed without allocation. Their checked return values are
intentionally unused, matching ByteBuffer's proved in-bounds write convention.
There is no recoverable return after mutation and no truncation-based rollback.

No private ByteBuffer constructor, raw storage access, compiler feature, temporary
heap buffer or 4096-byte JSON-validator limit is introduced. Runtime-sized valid
owner windows may exceed that validator limit. The example constructs a smaller
prefixed JSON array from distinct dynamic owners and validates the resulting
complete document. The API is a string writer, not a DOM, streaming parser,
normalizer, concurrent buffer abstraction or general serializer.
