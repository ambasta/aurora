# UTF-8 codecs, ranges and lines

The modules `std.utf8`, `std.utf8_range` and `std.utf8_lines` operate on checked readonly byte spans and return independent copied reports. Imports are direct; one module does not re-export its dependencies. The encoding reference is Unicode 17.0.0, chapter 3, D92 and Table 3-7. These APIs do not provide strings, normalization, graphemes, locale or display width.

## Decode and validate

### Version and scope

The format contract is pinned to the Unicode Standard **17.0.0**, chapter 3,
section 3.9, definition D92 and Table 3-7:
https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/

The decoder recognizes Unicode scalar values, including unassigned code points,
noncharacters, NUL and U+FEFF. It does not strip a BOM. It rejects overlong
representations, surrogates, values above U+10FFFF, standalone continuation bytes,
and all forbidden lead bytes. This is encoding validation, not normalization,
grapheme segmentation, locale processing, path validity, rendering or terminal
support. There is no replacement-character insertion or error resynchronization.

### API

```cpp
import std.utf8;

auto decode_utf8(builtin::span<const u8> bytes, i64 offset, i64 count,
                 bool final_input) -> std::Utf8DecodeResult;
auto validate_utf8(builtin::span<const u8> bytes, i64 offset, i64 count,
                   bool final_input) -> std::Utf8ValidationResult;
```

Both functions live in `std`. `Utf8Status` is a closed enum with `success`,
`end_of_input`, `out_of_range`, `invalid_sequence`, `truncated`, and `need_more`.
The functions never retain their borrowed span or mutate the input.

Ranges use a byte offset and byte count. Negative values, an offset greater than
span size, or a count greater than `size - offset` produce `out_of_range` before
any byte access, with zero output counts. No unchecked `offset + count` is used.
An empty range at the end of a span is valid.

`decode_utf8` returns the first scalar in the selected range. `status()` reports
the outcome; `scalar_or(fallback)` returns its u64-carried scalar on success;
`width()` returns its byte width (1 through 4 for results produced by decoding).
Every decoding failure has width zero and returns the fallback. An empty valid
range produces `end_of_input`, irrespective of `final_input`.

`validate_utf8` scans the selected range. Its `prefix_bytes()` and
`scalar_count()` count only complete valid leading scalars, relative to the
selected range. An entirely valid range, including an empty one, yields success.
A failure identifies the first nondecodable scalar at `offset + prefix_bytes()`;
this sum is safe for results returned by the validator on a valid range.
`end_of_input` is not a validator-produced status.

### Incomplete input and error precedence

The decoder examines available continuation bytes in order. An already present
invalid byte produces `invalid_sequence`, even when the expected complete width
exceeds the range. Thus E0 80 is invalid, while E0 A0 is incomplete. A proper
prefix of a valid scalar yields `truncated` for final input and `need_more` for
nonfinal input. Neither failure consumes a partial scalar.

Incremental use is stateless replay. After `need_more`, the caller retains the
suffix beginning at `prefix_bytes()` (at most three bytes) and presents it with
later bytes in a new valid borrowed range. The API does not retain a cross-call
borrow, buffer data, join spans, or create mutable storage. Callers can already
construct a fresh bounded local array using ordinary checked array operations.
Supplying only the continuation chunk without its prefix does not resume a
hidden decoder state. `final_input = false` still succeeds if all supplied bytes
form complete scalars; it makes no assertion about future input.

### Report objects and representation

Results have ordinary public constructors, private scalar fields and const
getters. Constructing one manually does not certify bytes or grant any buffer,
reference or indexing authority. Manually supplied widths/counts/statuses are
ordinary report data and are not automatically validated. `scalar_or` additionally
masks manually supplied surrogate or above-range payloads even under a success
status. A fallback is unrestricted ordinary u64 data, not a certified scalar.

No new scalar type, UTF string representation, constructor grammar, pointer,
write capability, runtime borrow checker or compiler instruction is added.
Existing span lifetime checks apply unchanged. Public structs and C compatibility
are not introduced.

## Encode one scalar

### Public API

```cpp
import std.utf8;
import std.array; // Required when naming the copied std::array return type.

// All names below live in std.
enum class Utf8EncodeStatus { success, invalid_scalar };
auto encode_utf8(u64 scalar) -> Utf8EncodeResult;
```

`Utf8EncodeResult` owns a private inline `std::array<u8,4>`, a status and an i64
logical width. It provides const methods `status()`, `size()`,
`byte_or(i64 index, u8 fallback)` and `bytes_or_zero()` returning a fresh
`std::array<u8,4>` value. The result and copied arrays have independent value
semantics. No resource, pointer, borrowed reference or mutable view escapes.

Factory results satisfy the canonical contract:

- Every scalar U+0000..U+D7FF or U+E000..U+10FFFF succeeds, including noncharacters,
  unassigned values and U+FEFF. There is no BOM insertion or stripping.
- The logical size is 1 through 4 and exactly that prefix is the shortest UTF-8
  encoding. Remaining bytes of the fixed four-byte storage are zero.
- Surrogates and values above U+10FFFF yield `invalid_scalar`, size zero and a
  zeroed copied array. NUL yields success, size one and byte zero.
- There is no caller output destination, partial write, replacement character or
  truncation. The fixed capacity always accommodates a valid scalar completely.

`byte_or` checks normalized status, then index < 0 and index >= size before
reading storage. It returns the supplied u8 fallback on failure or out-of-range
access, including the most negative/positive i64 indices. A fallback may equal a
real byte; callers use status/size when they need to distinguish those cases.
`bytes_or_zero` copies only the logical prefix into a new zero-initialized array,
so its remaining bytes are deterministic zero. Mutating that copy cannot change
the report or another returned copy.

### Freely constructible reports

The current dialect uses a public constructor:

```cpp
Utf8EncodeResult(Utf8EncodeStatus status, std::array<u8,4> bytes, i64 width);
```

Constructor arguments are complete independent class snapshots under existing
rules. The constructor does not certify that supplied bytes encode a scalar.
Accessors normalize every stored non-success status or width outside 1..4 to
`invalid_scalar`/size zero; byte access returns fallback and copied storage is
zero in these cases. For a valid-width manually constructed success report,
accessors enforce bounds and mask unused tail bytes, but do not prove that its
prefix is valid UTF-8. Its status is report data, not a validation certificate or
buffer authority. Use the decoder/validator when accepting untrusted bytes.

Private payload projection first copies to a named local before method calls.
No chained mutation or new class-method argument grammar is needed. Existing
constructor, const receiver, copied result and zero-padding rules remain in force.
Fixed-size copies can have a cost; these APIs make no zero-cost or measured
throughput claim. Native object padding is compiler-managed and source-inaccessible.
The public byte encoding is independent of those object layout details.

## Scalar-indexed ranges

### API and coordinates

```cpp
import std.utf8_range;

enum class Utf8RangeStatus { success, out_of_range, invalid_sequence, truncated };
auto utf8_subrange(builtin::span<const u8> bytes, i64 offset, i64 count,
                   i64 first_scalar, i64 scalar_count) -> std::Utf8RangeResult;
```

All names are in namespace `std`. The byte window is `offset`/`count` within the
whole borrowed owner. `first_scalar` is a zero-based scalar index within that
window; `scalar_count` is the exact requested number of scalar values. A scalar
is a Unicode scalar value, not necessarily a grapheme or displayed character.

The copied result has `status()`, `byte_offset()`, and `byte_count()` const methods.
On success, **byte_offset is relative to the selected byte window, not the owner**.
For an actual successful call, the owner-relative start is
`offset + result.byte_offset()` and the length is `result.byte_count()`.
The two input scalar coordinates never directly become byte indices.

For example, a window containing ASCII A, EURO SIGN, GRINNING FACE, ASCII Z has
nine bytes and four scalars. Selecting `(first_scalar=1, scalar_count=2)` yields
`byte_offset=1`, `byte_count=7`, regardless of where that window starts in its owner.
The executable [example](../library/examples/utf8_subrange.au) places this window
between invalid-byte sentinels and uses the observed coordinates with decode_utf8.
Only bytes inside the selected window are interpreted.

An empty window, including one at the end of the owner, accepts only `(0,0)`.
An empty scalar interval is allowed at any scalar boundary through the end of a
valid window. Selecting `(total_scalars,0)` yields `(window_byte_count,0)`.
There is no clamping, replacement insertion, or resynchronization.

### Validation and precedence

1. Negative `first_scalar` or `scalar_count` produces `out_of_range`.
2. The existing validator checks the byte window: negative byte coordinates,
   offset beyond owner size, or count beyond `size - offset` yield `out_of_range`
   before reading bytes. Empty end windows are allowed.
3. The **entire** selected byte window is validated as final input, even if the
   requested scalar interval is empty or occurs entirely before a malformed suffix.
   A malformed sequence produces `invalid_sequence`; a viable incomplete final
   scalar produces `truncated`. Existing invalid-byte versus truncation precedence
   is unchanged. Outside-window sentinels do not affect validation.
4. For a valid window, `first_scalar > total_scalars` or
   `scalar_count > total_scalars - first_scalar` produces `out_of_range`.
   Otherwise the requested interval's exact byte coordinates are returned.

Thus a nonnegative oversized scalar request on a malformed window reports its
encoding error. A negative scalar request reports `out_of_range` without examining
that window. No `first_scalar + scalar_count` is formed until the subtraction-based
checks prove it representable and bounded. Similar bounds justify later offset
additions. The validator uses the already-reviewed Unicode 17.0.0 D92/Table 3-7
contract: [official Unicode chapter 3](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/).
NUL, BOM, noncharacters, and unassigned scalar values receive ordinary scalar
positions; this operation performs no additional text-policy filtering.

### Public reports and capabilities

`Utf8RangeResult(status, byte_offset, byte_count)` has a public constructor,
private fields, and const accessors. Error reports always expose zero coordinates,
even if manually constructed with nonzero or extreme payloads. A manually
constructed success with a negative coordinate or an unrepresentable coordinate
sum is normalized to `out_of_range`, exposing zeros. Representable success data
can still be fabricated. It does **not** certify a byte owner, UTF-8 validity,
lifetime, or indexing authority. The consumer must use the existing checked byte
APIs; numeric result objects are never accepted as capabilities.

Results are independent values and remain usable after the input borrow ends or
the input owner is subsequently mutated. Their meaning records the original call;
they do not track edits. The function never retains the span or mutates its owner.
All existing lexical borrowing rules apply unchanged.

### Mechanism and limitations

The implementation first validates the whole selected window, then decodes through
the requested end scalar to locate boundaries. Worst-case work is two linear
passes over the window, with constant scalar state and no target heap allocation.
No duplicate byte buffer is created by the API. Calls and checked operations remain;
these mechanism observations are not throughput, zero-cost, or equivalent-C claims.
Fixed local byte arrays remain bounded to 4096 bytes; runtime-owned spans use their validated runtime length.

The old `std.utf8` module, compiler, kernel, and pre-existing tests are unchanged.
`std.utf8_range` does not re-export its decoder dependency. To call decode_utf8 or
name its result types, explicitly import `std.utf8` as in the example.

## Line scanning

### API

```cpp
import std.utf8_lines;

enum class Utf8LineStatus {
    success, end_of_input, out_of_range, invalid_sequence, truncated
};
enum class Utf8LineEnding { none, lf, crlf };
auto read_utf8_line(builtin::span<const u8> bytes, i64 offset, i64 count)
    -> std::Utf8LineResult;
```

All names are in namespace `std`. A result has const `status()`, `content_bytes()`,
`consumed_bytes()`, and `ending()` accessors. The content starts **at the supplied
owner-relative offset**; it is not a newly returned view. Content length excludes
the terminator. Consumed length includes it and is **relative to that window**.
For an actual successful result, the next owner-relative position is
`offset + result.consumed_bytes()` and the remaining count is
`count - result.consumed_bytes()`. Existing checked byte APIs remain mandatory.

The first LF byte ends the line. If the preceding byte within this window is CR,
both bytes form the CRLF terminator. Otherwise the terminator is LF. Lone CR is
ordinary content, including a trailing CR in an unterminated line. A CR outside the
window cannot participate in CRLF; a window starting at LF reports LF.

NUL, BOM, ESC, U+0085, U+2028, U+2029, noncharacters, and unassigned scalar values
are ordinary content. No Unicode line-breaking algorithm, normalization, grapheme,
display-width, locale, escape interpretation, terminal behavior, or path policy is
claimed. This is an explicit Aurora line policy, not a claim to implement every
standard-library `getline` or `splitlines` convention.

### Empty lines, progress, and final windows

- A valid empty byte window returns `end_of_input`, zero counts, and ending `none`.
- A nonempty window without LF is one unterminated final line, ending `none`.
- LF alone returns an empty successful line with consumed length one.
- CRLF alone returns an empty successful line with consumed length two.
- Consecutive terminators produce empty terminated lines when scanned repeatedly.
- A trailing terminator does not produce a phantom extra empty final line. The
  subsequent empty window returns `end_of_input`.
- Every actual successful result consumes at least one byte and at most `count`.

This API treats each supplied window as final input. It does not buffer chunks,
retain decoder state, wait for more bytes, or report `need_more`. A window ending
at a lone CR treats that CR as content; a future window starting with LF cannot
retroactively turn it into CRLF. Callers must supply their intended complete input
window or manage their own separate chunk-assembly policy.

### Byte validity and error precedence

Negative byte coordinates, offset beyond owner size, or count beyond
`size - offset` produce `out_of_range` before any byte access. The subtraction-based
check avoids unchecked `offset + count` arithmetic. An empty end window is valid.

The scanner first locates the first LF inside the selected window. It then invokes
the existing strict UTF-8 validator on exactly the consumed prefix **including the
terminator bytes**, or on the entire window if no LF exists. An unsuccessful
validation returns `invalid_sequence` or `truncated`, with all counts zero and
ending `none`. No replacement or resynchronization occurs.

Including LF/CRLF in validation is essential: for example C2 LF is
`invalid_sequence`, not an accepted line and not a partial scalar silently cut
away at LF. A valid multibyte scalar cannot contain ASCII LF as an encoding byte
under [Unicode 17.0.0 D92/Table 3-7](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/).
C2 at the final window end is `truncated`; known-invalid available prefixes keep
the prior validator's `invalid_sequence` precedence.

Bytes after the first complete line are **not certified or validated by that call**.
Thus `A LF FF` returns the valid first line; scanning the remainder reports the
invalid byte. This explicitly differs from `utf8_subrange`, which validates its
whole selected window even when only an earlier substring is requested. Consumers
requiring whole-input validity before observing any line should first call the
existing `validate_utf8` on that input window. The line scanner never claims that
an unconsumed suffix is valid.

### Copied reports and arithmetic invariants

`Utf8LineResult(status, content_bytes, ending)` has a public constructor and private
fields. Non-success reports expose zero counts and ending `none`, regardless of
fabricated payloads. A fabricated success with negative content length, an
unrepresentable `content + terminator width`, or zero total consumed bytes is
normalized to `out_of_range` with zero facts. `end_of_input` is never a success.

Representable public reports can still be forged. Constructors do not inspect or
certify original bytes, verify an owner length, establish a line boundary, or grant
indexing/lifetime authority. The result is ordinary historical data. It remains
independent after its input borrow ends or the owner is later edited; it does not
track those edits. No span or pointer escapes, and the scanner does not mutate input.

The range guards establish `offset + index` within the owner while searching.
Only a found LF yields `index + 1`, which is bounded by `count`. CR lookbehind occurs
only when `index > 0`. LF/CRLF success subtracts the known terminator width from a
validated prefix that actually contains those bytes. Public report accessors guard
addition before computing consumed length. These are bounded mechanism arguments,
not a general memory-safety or compiler correctness proof.

### Mechanism and limits

Each call scans at most the consumed prefix for LF and validates that prefix once.
Repeated calls advancing by actual successful consumed counts perform at most two
linear passes in total over the input bytes. Constant scalar state is used, with
no target heap allocation, byte-buffer copy, or retained borrow. Checked operations
and ordinary call overhead remain. There is no benchmark, equivalent-C, or zero-cost
claim. The compiler’s separate array/layout/resource limits still apply.

The [running example](../library/examples/utf8_lines.au) scans a CRLF line, an empty
LF line, and an unterminated EURO SIGN line using copied counts and checked windows.
It returns 42. Import `std.utf8` explicitly when also calling its validator; the new
module does not re-export its dependency.
