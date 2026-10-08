# Transactional quoted UTF-8 append

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

## Failure order and preservation

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

## Why the emission pass cannot fail recoverably

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

## Qualification

See [the results and exact limits](json-string-write-results.md). Overflow guards
are reviewed arithmetically; practical hosted tests cannot allocate valid owners
near `I64_MAX` and do not forge spans or ownership records to pretend otherwise.
