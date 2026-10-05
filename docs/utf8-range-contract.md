# Read-only scalar-indexed UTF-8 ranges

This library-only checkpoint passed independent review and a fresh full top-level
`make test` on the unchanged accepted milestone022 compiler. It observes substring coordinates using existing readonly byte spans and
copied class results. It does not create a string, subspan, pointer, retained borrow,
write capability, optional value, or new compiler/kernel mechanism.

## Dependency and acceptance gate

`std.utf8` already decodes/validates UTF-8 and encodes individual scalar values.
A shell/configuration parser can manually iterate scalars, but there is no library
operation mapping a scalar-indexed substring to its byte interval. This candidate
adds that single observation. Terminal rendering, input services, tokenization,
normalization, grapheme segmentation, display-cell width, and locale remain absent.

Acceptance requires independent native comparison to a strict UTF-8/string-slicing
oracle, exact recoverable error and masked-report checks, source misuse rejection,
unchanged prior UTF-8 gates, independent review, and a fresh full parent aggregate.
Focused checks alone do not establish acceptance or performance qualification.

## API and coordinates

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

## Validation and precedence

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

## Public reports and capabilities

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

## Mechanism and limitations

The implementation first validates the whole selected window, then decodes through
the requested end scalar to locate boundaries. Worst-case work is two linear
passes over the window, with constant scalar state and no target heap allocation.
No duplicate byte buffer is created by the API. Calls and checked operations remain;
these mechanism observations are not throughput, zero-cost, or equivalent-C claims.
The existing 4096-byte local owner and other M022 source/resource limits remain.

The old `std.utf8` module, compiler, kernel, and pre-existing tests are unchanged.
`std.utf8_range` does not re-export its decoder dependency. To call decode_utf8 or
name its result types, explicitly import `std.utf8` as in the example.

## Native gate

`make -C compiler test-utf8-range` runs a bytecode-disabled focused Python gate
using a fresh run-owned compiler and validated developer receipt under the
[shared test contract](developer-test-contract.md). There is no historical default
compiler pin. For a reviewed prebuilt use the shared acceptance selectors, not
`OUT` alone; `UTF8_RANGE_COMPILER_SHA256` remains an explicit focused pin selector.
Direct native use requires exactly one `--compiler-sha256` or
`--developer-build-receipt`. Identity is checked before outputs; imported library
sources are snapshotted and verified afterward. Focused success is not root
native acceptance, and the historical checkpoint below is unchanged.
Each invocation creates a fresh artifact directory, preserving source, assembly,
objects, native bytes, expected/observed full i64 values, and tool receipts.

The independent Python oracle decodes the entire selected window strictly, slices
Python scalar strings, and re-encodes selected prefixes/ranges. It does not reuse
the Aurora scan or the prior UTF-8 test oracle. The finite native corpus covers
mixed-width selections, every one-byte input, every byte window of one mixed-width
sequence, malformed/truncated suffixes, signed extremes, deterministic random
inputs, maximum-size owners, fabricated reports, input stability, copied reports,
and compile-time misuse. This is finite functional evidence, not a Unicode text
library completeness claim or a memory-safety proof.

The runner enforces a 128 MiB owned-output budget, a 1 GiB free floor, and 24 MiB
reserve before each output-producing tool command. Compiler AS is 512 MiB;
assembler/linker/native AS is 128 MiB; CPU is 20/21 seconds, wall time 45 seconds,
regular files at most 8 MiB, and core dumps disabled. At most 16 cases and 64 KiB
of source go in a fixture. `--sanitized-compiler` exempts only compiler AS from the
limit required for sanitizer shadow memory; generated Aurora is not instrumented.

## Verified local checkpoint

The frozen v2 implementation passed 2,250 author cases / 6,750 exact i64
observations and six rejection controls. Independent review separately passed
588 native cases / 1,764 exact i64 observations and ten rejection controls, then
audited the fresh full top-level aggregate and all 434 unchanged frozen inputs.
The previous UTF-8/encoding gates also passed. These populations overlap; do not
add them into a unique-case count.

Only four harness diagnostic expectations needed correction; no product defect
was reproduced. Failed attempts and exact source identities are retained in the
[checkpoint evidence](evidence/utf8-range-m022-20261004/README.md). Later status and
evidence edits are documentation-only. No new emulator or sanitizer run, optional
feature, compiler change, hardware qualification, or performance claim is included.
Remote publication and main-branch adoption are separate.
