# Strict UTF-8 library: milestone017

This integrated library adds `std.utf8` using the unchanged M016 compiler
and existing readonly byte spans. Author bounded native validation, independent
source/functional review, main integration and parent aggregate/smoke acceptance
have passed. See verification.md for the exact scope and historical kernel gates.

## Version and scope

The format contract is pinned to the Unicode Standard **17.0.0**, chapter 3,
section 3.9, definition D92 and Table 3-7:
https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/

The decoder recognizes Unicode scalar values, including unassigned code points,
noncharacters, NUL and U+FEFF. It does not strip a BOM. It rejects overlong
representations, surrogates, values above U+10FFFF, standalone continuation bytes,
and all forbidden lead bytes. This is encoding validation, not normalization,
grapheme segmentation, locale processing, path validity, rendering or terminal
support. There is no replacement-character insertion or error resynchronization.

## API

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

## Incomplete input and error precedence

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

## Report objects and representation

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

## Acceptance gates

Native runtime loops will cover all 0x110000 - 0x800 = **1,112,064** scalar values,
excluding the 2,048 surrogate code points. Small generated programs and bounded
batches will test all one- and two-byte inputs, boundary classes for longer
sequences, every split of representative boundary scalars, invalid-byte versus
truncation precedence, extreme signed ranges, windows, leading valid prefixes,
and byte-for-byte input preservation. Separate arithmetic/shortest-length and
Python strict-decoding oracles cross-check expected behavior. Tests have explicit
compiler/native limits and persistent failure artifacts. Scalar coverage is not
exhaustive coverage of all possible byte strings or all text semantics.

Release and instrumented compiler runs, ordinary library regressions, exact
source manifests and independent review are required before acceptance. Tests
are functional evidence, not a proof of whole-compiler or Unicode implementation
correctness.

## Verified isolated candidate

The library source SHA-256 is
`6ad8d1c11ce26197932e2118151a7761e518ea2db7dc64a1fd1a3e956761f31c`.
The test source SHA-256 is
`c30c913e6f5a81b724002a112acfdf7dc98b7c4dc4b9165f0a0999f005e9df84`.

The final known-exit aggregate passed on the unchanged M016 release compiler
`14cbaa33…` and address/undefined-behavior-instrumented compiler `805567b1…`:
406 native checks in 39 bounded fixtures on each, all scalar values, all one- and
two-byte inputs, and 24,200 longer boundary inputs. Existing readonly-span tests
(91 native including 25 exact bounds sites, 69 rejections) and storage tests
(254 native, 1,186 API calls) also passed on both. Independent review used a
separate strict Python codec oracle over 1,367,060 native cases on each compiler,
plus report/capacity and typechecking cases. These are overlapping evidence sets;
they must not be added as a count of unique cases.

Run `make -C compiler test-utf8 OUT=/path/to/aurorac` for the new gate.
For an instrumented compiler use `UTF8_TEST_FLAGS=--sanitized-compiler` and
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`. The flag removes only the compiler
address-space cap needed for ASan shadow reservation. Native/tool caps remain.
LeakSanitizer is not part of this receipt. Existing instrumented M016 compiler
build flags are recorded with the evidence; no compiler rebuild or new IR is
introduced by this library slice.

The new runner caps release compiler address space at 512 MiB, native/tools at
128 MiB, child CPU soft/hard time at 10/11 seconds, regular files at 8 MiB and
core files at zero. Compiler/tools have a 30-second wall timeout, native programs
15 seconds. Each fixture has at most 12 ordinary checks and 64 KiB of source;
exhaustive sets use runtime loops. Captured stdout/stderr pipes do not have a
separate memory cap. No overall compiler resource-bound or throughput claim is
made.

Three initial author fixture failures used unsupported dialect forms (logical
operators, partial array initialization, class assignment); retained sources and
process diagnostics document their correction. The library itself did not
change. The Python incremental oracle needed explicit checking of pending tails
because it delays rejection of ED A0; this adaptation did not change the format
contract. Independent review used strict final-prefix decoding from the start.
A native-tool transport interruption lost the first regression shell status;
terminal PASS logs were preserved, then a fresh stable-source aggregate recorded
known exit statuses for every required gate.
