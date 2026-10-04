# Aurora native core library: scalar seed

The library is authored in Aurora's safe C++ dialect and compiled freestanding by the native module pipeline. These are small working library modules, not a complete C++ standard library or libc replacement.

```text
module application;
import std.core;

auto answer() -> i64 {
    return std::min(42, 100) + std::max(-1, 0) + std::abs(0);
}
```

Compile with an explicit source-module root:

```sh
build/aurorac --module-root library application.au -o build/application.s
```

## Implemented API

The std.core parameters/results are scalar `i64` values; there are no implicit conversions, reference returns or overloads.

- `std::min(i64 left, i64 right) -> i64`: returns the smaller mathematical value. Equal inputs return that same value. Both signed endpoints are supported.
- `std::max(i64 left, i64 right) -> i64`: returns the larger mathematical value, including both signed endpoints.
- `std::abs(i64 value) -> i64`: returns the nonnegative magnitude when representable. Zero returns zero. The minimum signed value (`-9223372036854775808`) triggers the language's defined checked-overflow fail-stop trap; it does not wrap or invoke undefined arithmetic behavior.

Calls evaluate their arguments left to right under the existing language rules. These implementations use no allocation, system call, libc symbol or foreign-function interface. The `std::detail` helper is module-private, and caller declarations cannot hijack its binding.

The implementations are intentionally simple and currently retain ordinary function-call overhead. There is no unmeasured zero-cost or equivalent-C performance claim. Inlining and other optimizations must preserve checked arithmetic, module identity and reflection scope.

## Deliberately absent

There are no placeholder implementations of allocator, memory-copy, string, vector, streams, threading, filesystem, locale or process services. General templates, heap ownership and general interprocedural borrowing remain deferred; the milestone014 candidate adds only synchronous readonly local-byte-array spans. ordinary inline class arguments/results have a bounded implemented value contract. Those mechanisms must precede the corresponding library contracts.

The long-term goal remains a native runtime responsible for the useful roles currently served by libc, and a broad safe C++ standard-library ecosystem without C source/ABI compatibility. This module establishes actual imports, private implementation helpers, typed calls and executable scalar contracts toward that goal.

## Encapsulated scalar accumulation

`import std.numeric;` supplies `std::Accumulator(initial)`, `.add(amount)` and
`.value() const`. This is a small Aurora-specific scalar API, not a claim that
standard C++ defines `std::Accumulator` or that generic numeric algorithms are
complete. It keeps the checked signed total private, uses no allocation, and
traps on overflow before updating the total. Copies have independent totals.

The compiler supports `std.numeric` with scalar-specialized
`std::minmax(i64, i64) -> std::MinMax` and `std::range_width(std::MinMax) -> i64`.
MinMax keeps ordered endpoints private and exposes readonly min()/max() methods.
The returned value and consumed argument are independent copies. Width traps on
signed overflow, including the full minimum-to-maximum i64 range. This is an
Aurora value API, not standard C++ pair/reference ABI compatibility or a generic
container implementation. See compiler/VALUE-CALLS.md for its current restrictions.

## Checked scalar integer algorithms

`import std.integer;` adds i64-specialized `std::gcd`, `std::lcm` and `std::div`.
The latter returns an independent private-field `std::DivResult` with readonly
quot()/rem() methods. Division truncates toward zero; remainder follows the
dividend sign. Zero divisors and unrepresentable quotients trap at defined UD2
sites. Minimum i64 % -1 is explicitly zero. Gcd/lcm return nonnegative mathematical
results when representable, otherwise checked overflow; lcm is zero when either
input is zero. These are freestanding Aurora value APIs, not C runtime or generic
standard-library compatibility. See compiler/INTEGERS.md for edge cases and bounds.

## Unsigned bit algorithms

`import std.bit;` adds `std::popcount(u64) -> i64`, `std::bit_width(u64) -> i64` and `std::has_single_bit(u64) -> bool`. Zero has count/width zero and is not a single bit; maximum u64 has count/width 64. The real Aurora implementations require no allocation or target host runtime. Their loops are bounded by 64 iterations, while ordinary call overhead remains. These are scalar-specialized APIs, with checked arithmetic and exact 64-bit operations defined in compiler/UNSIGNED.md; no unsigned wrapping, generic implementation or performance claim is implied.

## Reusable value pairs

The current template candidate supplies `import std.utility;` and `std::pair<T,U>` for explicit i64/u64/bool type arguments; the milestone011 development
extension also accepts named concrete class arguments under the Value constraint. A complete constructor initializes public first/second fields; exact-type scalar-field mutation and independent ordinary-function value copies use the existing safe class semantics. All nine scalar tuples compile from one actual Aurora template definition. Verified milestone020 accepts fully concrete nested template-id arguments,
including std::pair<std::array<u8,16>,SourceRange>, under compiler/NESTED-VALUES.md.
No deduction, reference pairs, operator overloads or foreign pair ABI is provided. See compiler/TEMPLATES.md for nominal identity, module privacy and bounded instantiation.

## Fixed initialized containers

The current fixed-container candidate supplies `import std.array;` and `std::array<T,N>` for scalar T and explicit capacity1..64. Construction zero-initializes all elements; size() returns the capacity, at() returns a checked copy, and mutable set() checks/stores/returns an exact-type value. Class copies and function boundaries copy all leaves independently. The implementation is real Aurora source over private builtin::array storage, without heap or foreign calls. This is not a reference-returning span, dynamic vector or text/runtime package; see compiler/FIXED-CONTAINERS.md.

## Composed inline library values in development

`examples/composed_values.au` demonstrates a real
`std::pair<std::MinMax,std::Accumulator>`: independent constructor snapshots, an
ordinary by-value function boundary, projection into fresh locals, and mutation
of an extracted copy while the original remains unchanged. Compile it with
`build/aurorac --module-root library library/examples/composed_values.au -o build/composed-values.s`.
Its test function returns 42. The implementation and new adversarial tests are
still awaiting final review and integration. See compiler/COMPOSED-VALUES.md for
the four-level/64-leaf bounds and excluded resource/borrow operations.

## Recoverable results with composed values

The candidate std.decimal module implements closed DecimalStatus values and
DecimalAccumulator/DecimalResult. Its copied reports compose with ordinary value
classes and enum-constrained Value arguments in std::pair. The
[combined example](examples/enum_composition.au) returns 42 while preserving a
report across reset. See [the exact contract](../compiler/ENUM-RESULTS.md). Compact
text storage and general expected/optional remain deferred.

## Checked byte codec candidate

`import std.bytes;` supplies `std::Bytes4`, `std::ByteCodecStatus`,
`std::Encode32Result`, `std::encode_le32`, `std::encode_be32`,
`std::decode_le32` and `std::decode_be32`. Encoding checks the u64 input against
2^32-1 and returns a recoverable status; bytes_or_zero returns an independent
zero-filled value on failure, even for a publicly constructed nonzero error report.
Decoding accepts every four-byte pattern. Bytes4 owns a checked private four-byte
array; its representation gate is distinct from the numeric/API gate. See
[the contract](../compiler/BYTES.md) and [example](examples/byte_codec.au).
The milestone013 numeric and packed-representation gates are verified in the
recorded checkpoint. This is not a general text/runtime API, and no equivalent-C
performance claim is made.

## Borrowed binary reader candidate

`import std.binary;` supplies ByteReadStatus, ByteReadResult, read_le32 and
read_be32 in namespace std. Readers take builtin::span<const u8> plus an i64
offset and return a copied report. Negative offsets, inputs shorter than four
bytes, and offsets beyond length minus four report out_of_range before any read.
Every successful four-byte pattern produces a u64 value. status() and eager
value_or(u64) expose the result without exposing a stored error payload.

The [binary reader example](examples/binary_reader.au) forwards a whole local
array, reads two values and mutates the owner only after the temporary borrow
ends. [SPANS.md](../compiler/SPANS.md) states the static lifetime and private-call
contract. This candidate has no heap, returned views, mutable span, subspan or
private std.array storage borrowing. Independent compiler review and full compiler
gates passed on the corrected candidate; milestone014 parent/kernel integration
is verified in its recorded checkpoint.


## Storage fields and header-integrity candidate

`std.binary` now includes `read_le16`, `read_be16`, `read_le64` and `read_be64`
alongside its 32-bit readers. All return existing copied `ByteReadResult` reports
and carry field values in u64 with explicit width-dependent mathematical ranges.
`std.checksum` supplies recoverable `crc32c` and `crc32c_extend` over readonly
spans; the latter accepts a prior finalized 32-bit checksum carried in u64.

`fs.xfs_probe` supplies `probe_xfs_v5_512`, a bounded header/integrity fact report
for the exact 512-byte profile. Raw feature masks are uninterpreted observations;
CRC success does not establish mountability, clean-log state or feature support.
See [the API contract](../docs/checksum-xfs-probe.md),
[the real offline fixture](../docs/offline-xfs-fixture.md) and
[the running example](examples/storage_fields.au). The isolated implementation
passed independent review and milestone015 combined acceptance. These are header
facts, not a filesystem mount or operational feature-support claim.

Run `make -C compiler test-storage` for synthetic/native model checks and replay
of the preserved real mkfs-generated header. This test does not create or mount
an image, and does not require installed xfsprogs.


## Bounded primary-header geometry candidate

Import both `fs.xfs_geometry` and `fs.xfs_probe` to use
`fs::inspect_xfs_v5_512_geometry`. The direct probe import is required by the
existing type-visibility rules because the public copied report contains a probe
value. The original probe implementation and statuses remain unchanged.

The inspector returns a closed status/first-issue report, raw feature observations,
unsupported/unknown masks and 24 grouped geometry facts. Failure facts are all zero;
raw diagnostics are untrusted observations. The narrow admitted-feature policy
permits only these header calculations and is never a mount-support allowlist.
It checks encoded AG-relative log addresses, final-AG ranges and u64 byte-size
representability without following any metadata or reading a device.

The [exact contract and precedence addendum](../docs/xfs-geometry-contract.md)
retain the approved pinned-source proposal and its boundaries. The
[running example](examples/xfs_geometry.au) consumes the preserved real header and
checks its claimed byte size and internal log placement. Source/functional review
and focused author gates passed; final integrated milestone acceptance is pending.
Run `make -C compiler test-xfs-geometry` for the bigint/native corpus and bounded
mutation controls. The explicit `--sanitized-compiler` flag is supplied through
`XFS_GEOMETRY_TEST_FLAGS` only when testing an instrumented compiler.

## Explicit copied pair factory (M021 candidate)

`std.utility` also provides `std::make_pair<T,U>(first,second)` with explicit
Scalar/Value-compatible types. It constructs a complete independent pair through
Aurora code; class arguments are readonly left-to-right snapshots and the result
initializes a fresh typed local. There is no deduction, reference-pair, heap or ABI
addition. `examples/function_token_values.au` combines `std::array<u8,16>` and a
source-range class. See `compiler/FUNCTION-TEMPLATES.md` for candidate limits and
verification gates.
