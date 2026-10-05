# Read-only UTF-8 consumed-line scanner

This library-only checkpoint passed independent review and a fresh full top-level
aggregate on the accepted M022 compiler and PR17 source checkpoint. The previous UTF-8 scalar-range and package-identity APIs are unchanged.
No compiler/kernel capability, heap storage, returned view, or mutable-byte API is
introduced. The evidence below records those scoped acceptance gates.

## Dependency and acceptance gate

The native library can decode/validate UTF-8 and observe scalar-indexed byte ranges,
but cannot yet scan text into lines. A shell/configuration/text-file consumer needs
an explicit line-ending policy and a checked way to advance over empty lines.
This candidate adds one operation returning copied byte counts for the first line
of a specified window. It does not read a file or execute terminal control sequences.

Acceptance requires a native oracle comparison of all result fields, repeated-scan
progress/reconstruction checks, malformed-byte/delimiter precedence, report masking,
misuse rejection, preserved existing UTF-8 gates, independent review, and a fresh
full top-level aggregate. A focused pass alone is not final acceptance.

## API

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

## Empty lines, progress, and final windows

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

## Byte validity and error precedence

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

## Copied reports and arithmetic invariants

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

## Mechanism and limits

Each call scans at most the consumed prefix for LF and validates that prefix once.
Repeated calls advancing by actual successful consumed counts perform at most two
linear passes in total over the input bytes. Constant scalar state is used, with
no target heap allocation, byte-buffer copy, or retained borrow. Checked operations
and ordinary call overhead remain. There is no benchmark, equivalent-C, or zero-cost
claim. Existing M022 local byte-owner and source/resource limits remain unchanged.

The [running example](../library/examples/utf8_lines.au) scans a CRLF line, an empty
LF line, and an unterminated EURO SIGN line using copied counts and checked windows.
It returns 42. Import `std.utf8` explicitly when also calling its validator; the new
module does not re-export its dependency.

## Focused gate

`make -C compiler test-utf8-lines` creates fresh retained artifacts using a fresh
run-owned compiler and validated developer receipt under the
[shared test contract](developer-test-contract.md). There is no historical default
compiler pin. For a reviewed prebuilt use the shared acceptance selectors, not
`OUT` alone; `UTF8_LINES_COMPILER_SHA256` remains an explicit focused pin selector.
Direct native use requires exactly one `--compiler-sha256` or
`--developer-build-receipt`. Focused success is not root native acceptance; the
historical checkpoint below is unchanged. The Python
oracle independently partitions at byte LF, detects a preceding CR, and strictly
decodes the consumed bytes; it does not duplicate the Aurora loop. Native output
records complete i64 status/content/consumed/ending values. Repeated-scan fixtures
check progress, exact terminator bytes, complete consumption or first error, and
no phantom trailing line. Scalar policy, malformed-before/after-LF, every one-byte
input, signed extremes, all byte windows of representative strings, 4096-byte owners,
public reports, input stability, copies, and source misuse are exercised.

The unchanged range-gate helper supplies only bounded tool execution and output
budgeting; its range oracle is not used. Source, assembly, binaries, native bytes,
expectations, commands and failures remain retained. The initial owned-output cap
is 128 MiB, with a 1 GiB free floor and 24 MiB command reserve. Compiler AS is 512 MiB;
native/assembler/linker AS is 128 MiB, CPU 20/21 seconds, wall 45 seconds, regular-file
limit 8 MiB, cores disabled, and generated fixtures limited to 16 cases/64 KiB. A
separately identified sanitizer compiler may omit only compiler AS for shadow
memory; this does not instrument generated Aurora or imply fresh sanitizer coverage.

## Verified local checkpoint

The frozen v1 implementation passed 1,815 author cases / 7,260 exact i64
observations and seven rejection controls. Independent review passed 875 native
cases / 3,500 exact i64 observations, 15 rejection controls, and a checked-bounds
SIGILL control. Counts overlap and are not a combined unique-case total.

All previous UTF-8 gates passed separately, then the fresh full top-level `make
test` passed, including the existing package-identity prerequisite. Every one of
477 frozen source files and the accepted compiler pin remained unchanged. One
author expected-diagnostic substring needed correction; no product correction was
required. [Evidence and independent acceptance](evidence/utf8-lines-pr17-20261004/README.md)
preserve exact identities, failure history, commands and resource limits. Later
result-only evidence/status appends do not modify tested implementation or tests.

This is a local library checkpoint. No fresh emulator, sanitizer, compiler,
terminal, physical-device, or performance qualification is implied. PR17 was
verified as open/unmerged when this baseline was selected; publication or main
adoption of either checkpoint remains a separate action.
