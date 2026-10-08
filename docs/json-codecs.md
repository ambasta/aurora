# JSON string scalar codecs

Status: fresh focused native gates passed; see [results](json-codecs-results.md). This library-only
increment shares scalar reading with the accepted bounded JSON scanner. It adds
no compiler semantics, string container, DOM or replacement for host nlohmann.

## Dependency and observable gate

The prerequisite is the existing readonly byte span, copied class-result, UTF-8
codec and hosted ByteBuffer contracts. Accept after independent scalar/escape
oracles and original scanner regressions pass with the unchanged selected compiler,
including full-width observations, malformed inputs, window cuts, result shapes,
privacy and real allocation-failure composition. Repeat in ordinary and optimized
Python and independently review source and retained evidence. The example must
produce every decoded and serialized byte, not merely compile or return a checksum.
Owner-backed revalidation needs the separately accepted readonly-owned-view
compiler; an array-only run does not qualify that integration.

## Copied APIs

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
4,096-byte profile limit. PR77 array origins cannot natively supply a larger
valid span; owner-input coverage is separately reported, never fabricated.

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

## Append composition and truthful atomicity

ByteBuffer remains generic and unchanged. A caller obtains the escaped scalar,
checks status, checks `encoded.size() <= I64_MAX - output.size()`, reserves that
sum once, then appends each copied byte. On reserve failure its existing size,
capacity, bytes and committed allocation accounting are unchanged. Successful
reserve proves the following writes fit, so they do not allocate or encounter
recoverable failure. Invalid scalar and overflow reject before mutation. Already
completed argument side effects and fail-stop faults have no rollback promise.

This proves atomicity for one scalar, not an arbitrary series. A streaming caller
that successfully appends a prefix before a later error keeps that prefix. Truncate
can hide appended bytes but does not restore capacity or allocation identity.
For one complete string, validate/measure first with checked accumulation, reserve
the full output including quotes once, then emit in a second linear pass. Repeated
exact reserve for each scalar can incur quadratic replacement-copy work; a total
reservation avoids that. There is no measured performance claim.

The executable `library/examples/json_codecs.au` scans once, measures in one pass,
then fills separate decoded-UTF8 and escaped-output ByteBuffers. Its inputs include
NUL, simple escapes, literal UTF-8 and a surrogate pair. It exposes complete output
bytes through copied reads for the hosted oracle. Reserving the two distinct
buffers is not a joint transaction; a later failure does not roll back a successful
reservation of the other buffer. No such cross-buffer guarantee is claimed.

Synchronous readonly span method parameters are supported by the accepted
[method-span contract](../compiler/METHOD-SPANS.md), including bulk ByteBuffer
append. General mutable-object references and a writer owning a nested ByteBuffer
remain unsupported; a free helper taking a span plus a mutable borrowed ByteBuffer
is not admitted. Callers compose the scalar codecs locally. No duplicate JsonBuffer or new borrowed-resource
signature is introduced to evade these boundaries. Native transport, decoded-key
lookup/duplicate policy, numeric conversion/formatting, value representation and
larger LSP budgets remain distinct dependencies before host JSON replacement.

The separate [integer codecs](json-integers.md) reuse the number DFA and generic
decimal accumulator/encoding. They do not change string-codec behavior or add a
string/DOM representation; see their [qualification status](json-integers-results.md).
