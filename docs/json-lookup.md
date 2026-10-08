# Bounded decoded-key and array-index JSON lookup

Status: focused native gates and independent source/evidence review passed. See
the [qualification record](json-lookup-results.md). No DOM, stored source view,
compiler semantics, new buffer, or host JSON replacement is introduced.

## Dependency and observable gate

Reuse the accepted scalar-valid JSON scanner, iterative validator, UTF-8 codec,
readonly owned spans, copied class results and ByteBuffer bulk append. Accept
only after independent ordered-duplicate/range oracles, full-width native
observations, constructor/privacy/lifetime controls, real owner hidden-capacity
and limit checks, original JSON regressions and focused public routing pass in
normal and optimized Python, followed by independent source/evidence review.
Focused qualification does not establish full native, sanitizer, guest, hardware,
production-safety or measured-performance acceptance.

## Copied APIs

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

## Precedence, limits and errors

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

## Shared bounded mechanism

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

## Constructors, ownership and authority

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

## No-copy nested example

`library/examples/json_lookup.au` loads 81 transport bytes into an actual
ByteBuffer once, then reads one live logical span throughout extraction:

` {"\u0070ayload":{"items":[null,{"name":"A\u0000\uD83D\uDE00"}]},"ignored":true} `

Member payload selects object (17,47); its member items selects array (26,37);
element 1 selects object (32,30); member name selects string (40,21). Reading its
content (41,19) yields U+0041, U+0000, U+1F600. These are same-span coordinates;
a caller choosing subspans must intentionally rebase coordinates. Each lookup
validates its entire chosen window. No source copies or extracted value buffers
are used, and every extent/scalar is exposed for a hosted oracle.

## Focused test routing

`make -C compiler test-json-lookup` enters the controlled compiler workflow.
The optimized Python runner is also in Meson bytes/dev with explicit example
module dependencies. Direct independent-pinned runs use
`python3 -B tests/compiler/json_lookup.py COMPILER --compiler-sha256 DIGEST
--artifacts FRESH_DIRECTORY`, repeated with `-O`. `--self-test-only` checks only
the independent oracles. Developer-selected mode records observed compiler
stability, not independent provenance, and is refused in aggregate contexts.
