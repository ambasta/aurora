# Owned UTF-8 scalar encoding: milestone018

This integrated addition uses the M017 readonly-decoder baseline and unchanged
M016 compiler. The candidate was developed while M017 archival was pending;
main integration occurred only after its verified archive clearance. Bounded
author gates, independent source/functional review, integration and parent
aggregate/smoke acceptance passed. See verification.md for exact scope.

The pinned format is Unicode Standard **17.0.0**, chapter 3, §3.9.3, D92,
Tables 3-6 and 3-7:
https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-3/

## Public API

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

## Freely constructible reports

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
Fixed-size copies can have a cost; this candidate makes no zero-cost or measured
throughput claim. Native object padding is compiler-managed and source-inaccessible.
The public byte encoding is independent of those object layout details.

## Validation gate

The author oracle independently computes positional-base shortest encodings and
cross-checks Python's strict encoder for all 1,112,064 scalar values. Native
bounded runtime loops must match exact bytes/widths and zero tail for every scalar
before decoder roundtrips are considered additional evidence. Every surrogate
value, above-range boundaries and u64 maximum are rejected. Boundary/noncharacter,
BOM/NUL, malformed report, extreme-index and copy-independence cases are included.

Fixtures remain bounded by explicit source, batch, CPU, address-space, wall-time
and regular-file limits. The sanitizer-compiler option removes only the compiler
address-space cap needed for shadow reservation; native/tool limits stay active.
Failure artifacts and command exits are retained. Tests do not establish general
compiler correctness or complete text support. No string container, locale,
normalization, grapheme, path, font or terminal API is claimed.

The M017 decoder implementation is preserved; only an import of std.array and
new encoder declarations are added to its module. Its complete regression corpus
must still pass. Main source integration awaits parent archive clearance and
independent review of this isolated delta.

## Frozen author acceptance

Library SHA256: `a9448bed52974ca1e690b9a10e86a5f879c5b24f475a12ab1ec079e4e97bc646`.
Test SHA256: `e35b66182a56c8f7e87622d6ab65b74fa3e4a0199eb1c56f165a838c808ae1f5`.

The final known-exit aggregate passed eleven commands: normal/optimized harness
controls, encoder and existing decoder targets on release and instrumented
compilers, both example compilations, assembly/link and native execution. The
example returns exactly 42; both compiler pins emit identical example assembly.
Source hashes remained stable across the aggregate.

Each encoder gate passes **186 native checks in 35 bounded fixtures**, including
17 runtime plane loops covering every scalar, all 2,048 surrogates and bounded
invalid-u64 cases. Twelve misuse sources are each tested with absent and existing
outputs, for 24 rejected compilations. Rejections require exit 1, expected
diagnostics and byte-preserved existing artifacts. The original decoder corpus
still passes its 406 native checks and exhaustive/boundary loops on both pins.
These generated-check counts and loop populations overlap; do not add them as a
unique-case count.

The comparison strength is deliberately distinguished: native encodings are
compared byte for byte against a separate positional-base arithmetic model; the
Python model is crosschecked against Python strict encoding for every scalar;
ordered native/Python per-plane fingerprints provide an additional aggregate
check. Fingerprints alone are not direct byte-for-byte comparisons or a proof.
Decoder roundtrips are additional evidence, not the encoder oracle.

Constructor source-array mutation, returned-copy mutation and repeated-copy
independence pass. Compile-time/runtime size observations give array/report sizes
4/24 and u8-surrounded wrapper sizes 6/40. These are layout observations, not a
new direct observation of inaccessible native padding bytes or a general ABI proof.
An earlier layout fixture lacked the dialect's required complete constructor;
its normal rejection receipt remains preserved. Correcting that test did not
change the library. Earlier 183-check passing runs remain historical evidence.

`make -C compiler test-utf8-encoding OUT=/path/to/aurorac` runs the gate. For the
instrumented compiler, set `UTF8_TEST_FLAGS=--sanitized-compiler` and
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`. Only the compiler AS limit is omitted
for ASan shadow reservation; release compiler AS is 512 MiB, native/tools 128 MiB,
CPU 10/11 seconds, regular-file size 8 MiB, and core size zero. Compiler/tool wall
time is 30 seconds, native time 15 seconds. Source/batch caps remain 64 KiB/12
checks. Captured pipes have no separate memory cap. Leak checking and measured
performance qualification are not part of this gate.


Independent review separately compared exact native results against strict Python
encoding and a division/remainder model for 1,122,439 inputs per compiler (every
scalar plus 10,375 invalid inputs). Another 8,784 report/copy/value-call cases,
18 negative fixtures and 16 existing checked-array bounds sites passed per compiler.
These overlap author coverage. The result is scoped library correctness evidence;
parent main integration and milestone acceptance remain separate.
