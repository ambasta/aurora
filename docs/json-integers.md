# Checked JSON integer spelling codecs

Status: bounded focused qualification and independent source/evidence review passed;
see the [results and limits](json-integers-results.md).
This library-only increment adds no compiler semantics, floats, string container,
DOM or replacement for host nlohmann. It does not depend on method-span/bulk append
work. The original mechanism base was accepted PR79; final publication composes
on accepted PR81 and is separately qualified with its reviewed compiler.

## Dependency and observable acceptance gate

Reuse the private JSON number DFA, `std::DecimalAccumulator`, copied class values,
readonly spans and existing ByteBuffer. Accept after native full-width observations
match independent arbitrary-precision integer and decimal-byte oracles in ordinary
and optimized Python; window cuts, overflow/syntax precedence, copied/forged results,
privacy, actual owner-input revalidation and real allocation-failure composition
must pass. Preserve scanner, codec and decimal regressions, public focused Make and
Meson routing, exact identities and independent review. Focused checks do not
establish full-native, sanitizer, kernel, hardware or production qualification.

## Conversion API and grammar

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

## Generic decimal serialization

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

## Storage composition

`library/examples/json_integers.au` formats signed minimum, unsigned maximum and
parsed negative zero into `[-9223372036854775808,18446744073709551615,0]`.
It measures all 45 bytes, reserves once, appends copied bytes and revalidates the
actual ByteBuffer logical view, including integer conversions over its spans.
The hosted observation interface exposes every output byte, size and capacity.

Before append, check width <= I64_MAX - output.size(), then reserve the sum.
Failed reserve leaves existing bytes, size, capacity and committed allocation
accounting unchanged. Successful reserve makes subsequent bounded appends
allocation-free. Prior caller side effects and fail-stop faults do not roll back;
this is not a transaction over an arbitrary series of writes. No mutable borrowed
buffer function or escaped result-array view is introduced.

## Remaining ecosystem dependencies

Exact conversion of fraction/exponent spellings, floats, larger JSON/LSP budgets,
owned text/value containers, decoded key equality/duplicate policy, native
transport and whole-document serialization remain separate work. Host nlohmann
remains in use. No language or distribution completion is implied.
