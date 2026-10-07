# Aurora native core library: scalar seed

The library is authored in Aurora's safe C++ dialect and compiled freestanding by the native module pipeline. These are small working library modules, not a complete C++ standard library or libc replacement.

Current Make test invocations use the [shared developer-test contract](../docs/developer-test-contract.md):
one fresh run-owned compiler for developer tests, or an explicitly externally
pinned acceptance compiler. No historical binary pin is imposed on an ordinary
developer build. Full aggregates reject coverage-reducing test flags; focused or
compiler-free diagnostic runs do not qualify the root native aggregate. This
tooling candidate is unqualified, and historical library receipts remain evidence
only for their recorded source/tool checkpoints.

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

## Owned 16- and 64-bit storage-field codecs

`std.bytes` extends its 32-bit codec with checked owned `Bytes2` / `Bytes8` values
and LE/BE16/64 encode/decode functions. Sixteen-bit encoding returns a recoverable
`Encode16Result`, rejecting values above 65535 and masking failure bytes to zero.
All u64 inputs fit the 64-bit encoding, which returns `Bytes8` directly. Decoding
accepts every two- or eight-byte pattern. Bytes stay private and copies independent.

The [contract](../compiler/BYTES.md#owned-storage-field-codec-extension)
and [wire-record example](examples/storage_codec.au) describe the bounded API.
Focused native checks, independent review and a fresh complete `make test` passed
on the source identified in the contract. No general writer, mutable span,
filesystem write or new language feature is implied.

## Owned serialization record

`std.binary_buffer` supplies `BinaryBuffer64`, a zero-initialized owned 64-byte
record with the existing endian-write operations, recoverable `read_u8`, and
checked `at`. It is the sole owned record representation. There is no block/writer
conversion layer, geometry or flush operation on a record.

The [buffer contract](../docs/binary-buffer-contract.md) and
[example](examples/binary_buffer.au) distinguish read bounds from write bounds
and numeric-width errors. Fresh focused normal/optimized native checks passed; see the
[results and scope](../docs/storage-consolidation.md#focused-verification--2026-10-07).

## Owned sectors and one device contract

`storage.sector` supplies `Sector512`, checked bytes and copied `BinaryBuffer64`
records at byte offsets 0 through 448. Full-range preflight preserves every byte
on failure. The [sector contract](../docs/sector-contract.md) uses the same record
value directly, without conversions or a second serializer.

`storage.block_io` and `storage.ram_sector` supply the sole device contract and a
one-sector `RamSectorDevice`. Construct it from a named owned sector snapshot.
Reads return copied sectors; range and readonly failures preserve the entire
device. Visibility flush is volatile; durable flush is unsupported.

The [I/O contract](../docs/block-io-contract.md) and single
[end-to-end record example](examples/ram_sector_record.au) cover this interface.
The device stores a `Sector512` directly and requires checked owned-field
assignment. There is no four-record device façade, real disk, mount, persistent
backend or new borrowing facility. See the [migration and results](../docs/storage-consolidation.md).

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


## Indexed read-only root entries

`fs::entry_at_xfs_v5_512_root(superblock, inode, index)` returns a copied root
entry or an explicit end/error status under the same restricted profile as
name lookup. Both operations share complete metadata validation, including
entries after the selected one. Results provide inode/type and raw-name byte
coordinates into the same unchanged input snapshot, with no retained view.

The [contract](../docs/xfs-root-entry-contract.md) defines negative/oversized
index precedence, end markers and zero-masked failures. The preserved fixture
hashes stay exact; ordinary root tests record the current implementation hash
rather than requiring one historical module. [Focused execution and independent
review passed](../docs/xfs-root-entry-contract.md#focused-validation-results): the complete lookup corpus and
API checks, plus 912 indexed-entry cases in normal and Python optimized modes.
This adds no file-data read, path traversal or mount.

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
`XFS_GEOMETRY_TEST_FLAGS` only for a focused developer run of an instrumented
compiler; full aggregates and acceptance reject test-flag overrides.

## Verified milestone021: explicit copied pair factory

`std.utility` also provides `std::make_pair<T,U>(first,second)` with explicit
Scalar/Value-compatible types. It constructs a complete independent pair through
Aurora code; class arguments are readonly left-to-right snapshots and the result
initializes a fresh typed local. There is no deduction, reference-pair, heap or ABI
addition. `examples/function_token_values.au` combines `std::array<u8,16>` and a
source-range class. Complete release/fatal host ASan/UBSan compiler targets,
independent review/replay and parent aggregate/integration gates passed.
See [the contract](../compiler/FUNCTION-TEMPLATES.md) and
[M021 evidence](https://github.com/ambasta/aurora/blob/2b1776f13cd02df6588f9e3213815f13c28a71e0/docs/evidence/milestone-021/README.md) for finite grammar,
combined graph budgets, preserved failures and verified pins. This is a copied
value factory, not general standard-library, text-consumer or self-hosting completion.

## Verified milestone022: copied exchange

std::array<T,N>::exchange(array replacement) returns the old complete contents
and replaces its receiver from an immutable argument snapshot. Self-exchange is
valid. Caller replacement, receiver and result remain independent values. This
is an Aurora convenience member, not the standard C++ std::array API or an atomic
operation. Complete release/fatal host ASan/UBSan compiler gates, independent
source/native ABI review, fresh parent aggregate and all 166 existing emulator
modes passed, followed by both normal-image restoration boots. See
[method values](../compiler/METHOD-VALUES.md) and [M022 evidence](https://github.com/ambasta/aurora/blob/2b1776f13cd02df6588f9e3213815f13c28a71e0/docs/evidence/milestone-022/README.md)
for exact source and binary pins, preserved failures and bounded coverage.

## Read-only XFS local root lookup

`import fs.xfs_root;` adds `fs::lookup_xfs_v5_512_root(superblock, inode, name)`
for checked readonly byte spans. It returns copied `XfsRootReport`, `XfsRootFacts`
and `XfsRootMatch` class values. This bounded offline parser accepts a CRC-valid
v5 512-byte local root inode with 32-bit shortform entries, at most 16 entries,
and the supported geometry/profile in [the contract](../docs/xfs-root-contract.md).
It validates the entire directory before returning found/not_found. Error facts
and non-found matches are zero, including fabricated public reports. Names are
raw bytes; inode addresses establish geometry only. It does not mount, replay,
read file data, establish inode allocation/existence, or access devices.

`make -C compiler test-xfs-root` runs 203 lookup
cases with 2,233 full u64 observations and 77 API observations plus 12 rejection
controls. The aggregate compiler `test` depends on this gate. The shared supervisor
fresh-builds one run-owned compiler and passes its validated developer receipt to
both bytecode-disabled Python runners. It records the observed hash separately
from any externally supplied pin. For a reviewed prebuilt use the shared acceptance
selectors; `OUT` alone no longer selects a test compiler. `XFS_ROOT_COMPILER_SHA256`
remains an explicit focused pin selector. `XFS_ROOT_REPO`, `XFS_ROOT_FIXTURES`, and
`XFS_ROOT_ARTIFACT_PARENT` select existing explicit roots; fixtures default to
`REPO/fixtures/xfs-root`, artifacts to the compiler directory. Each run creates
fresh lookup/API leaves under an owned mktemp directory.
The owned-output budget is 128 MiB, with a 1 GiB free floor and
24 MiB reserved before each output-producing command. Run serially when sharing
a tighter task-level budget.

On a focused developer invocation, `XFS_ROOT_TEST_FLAGS=--representative` selects
the labeled 56-case/616-observation subset. Full aggregates and acceptance reject
these overrides. For a focused fatal host-instrumented compiler run, select
supported instrumented `CXXFLAGS`, set `ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`,
`UBSAN_OPTIONS=halt_on_error=1`, and `--sanitized-compiler` in both
`XFS_ROOT_TEST_FLAGS` and `XFS_ROOT_API_TEST_FLAGS`. This exempts only the compiler's
address-space cap for sanitizer shadow memory; generated target code is not
instrumented. Fixture slices were exactly hash-recovered after a workspace reset;
the original full images and pre-reset receipts remain unavailable.

## Read-only UTF-8 scalar-range checkpoint

`std.utf8_range` adds scalar-indexed substring byte observations over readonly
spans. The entire selected window must be valid final UTF-8 before a copied
relative byte offset/count is returned; errors expose zero coordinates.
It preserves the previous UTF-8 APIs and accepted M022 compiler/kernel sources.
Independent native review and the fresh full top-level `make test` passed on
the frozen implementation. No string container, grapheme/normalization/display-width
support, returned view,
new emulator qualification, or performance guarantee is claimed. See [the exact
contract](../docs/utf8-range-contract.md).

## Bounded package identity candidate

`import package.identity; import std.array;` provides a real freestanding
`package::parse_identity(bytes,offset,count)` over a readonly byte span. It owns
and validates a canonical 1..24-byte ASCII package name and three 0..4294967295
numeric version components from `name@major.minor.patch`, exposing recoverable
errors, independent copied names, exact identity equality and version ordering.
The explicit `std.array` import is required by the current compiler's direct
visibility rule for composed class values. No input view escapes.

This restricted grammar is not full SemVer or a complete manifest format. Public
reports are forgeable data, never parsing certificates or trust/install authority.
The candidate has no allocation, network, source resolver, build recipe, installer,
filesystem operation, source integrity mechanism or dependency policy. See the
[exact contract and gate](../docs/package-identity-contract.md) and
[runnable example](examples/package_identity.au). Independent oracle/source review and the full focused Make recipe passed; parent
aggregate acceptance remains pending.

## Read-only UTF-8 line-scanning checkpoint

`std.utf8_lines` observes the first LF/CRLF-terminated or unterminated final line
of a readonly byte window. Strict UTF-8 validation covers consumed bytes including
the terminator; later lines are checked on later calls. Copied masked counts
support progress through empty lines without retained views or mutable storage.
This explicitly differs from whole-window `utf8_subrange` validation. Independent
native review and a fresh full top-level aggregate passed on the frozen source.
Compiler/kernel, old APIs, terminal behavior and hardware qualification are unchanged. See [the exact
contract](../docs/utf8-lines-contract.md).


## Bounded declarative package manifest candidate

`package.manifest` reads an exact versioned ASCII metadata profile containing one
package.identity token and zero to eight pinned direct dependency identities. It
rejects duplicate canonical dependency names, self-dependencies, unknown fields and
trailing bytes. The complete manifest is validated before any copied summary or
selected-dependency observation is returned. Imports of package.identity and std.array
are also required by existing visibility rules. Results own their facts and survive
input mutation; separate calls are independent observations, not one transaction.
See the [grammar/API](../docs/package-manifest-contract.md) and
[example](examples/package_manifest.au). This is a candidate pending the independent
oracle, distinct review and full aggregate recorded in its evidence index.

The eight-entry limit is a supported profile bound. Exact version pins are not
version ranges; this metadata parser supplies no resolver, build scripts, source
retrieval, installation, authentication, network, process or filesystem authority.


## Bounded exact-manifest graph candidate

`package.graph` validates a caller-supplied catalog of zero to eight existing
manifests using readonly byte windows and copied offset/length arrays. It rejects
missing packages, mismatched exact versions, duplicate canonical root names and
transitive cycles before exposing an order. Dependencies precede dependents;
lexicographically smallest ready names make the identity order independent of
catalog/dependency-line ordering. Copied order indices and selected identities
retain no input view. Empty catalogs have a successful empty order.

See the [exact API and precedence](../docs/package-graph-contract.md) and
[native example](examples/package_graph.au). Full independent native oracle and
corrected actual Make gates pass 5,548 cases/333,671 complete u64 observations plus
60 rejection runs; separate focused source/native review also passes. Fresh
aggregate and final integration seal remain required before acceptance.
The entire supplied catalog is checked; the module performs no source retrieval,
version-range solving, recipe execution, installation, trust or filesystem operation.


## Verified bounded ASCII next-token scanner

`std.token_scan` implements an Aurora-authored readonly final-window scanner for
the host lexer's explicit C-locale ASCII profile. `std::next_token` returns an
independent `TokenResult` with lexical kind, supplied-span-relative coordinates,
consumed-byte count and skipped-LF count. Opaque `//` comments can contain arbitrary
bytes. Recoverable unsupported bytes consume one byte after trivia; invalid
windows expose no coordinates. No source borrow escapes and no heap is required.

The [frozen contract](../docs/token-scan-contract.md) describes the exact grammar,
public-report shape checks and acceptance requirements. The
[example](../examples/token_scan.au) observes identifier, operator-pair, digit-word
and EOF reports and retains a copied result after owner mutation. The focused
entry is `make -C compiler test-token-scan`; `make test` includes it under the
shared build-once compiler contract. A fresh full root release native aggregate
and separate focused fatal host ASan/UBSan scanner gate passed independent review.
See the [qualification results](../docs/token-scan-results.md) for the preserved
initial diagnostic-expectation failure, exact scope and evidence. Generated Aurora
assembly is not sanitizer-instrumented; no complete compiler sanitizer run or
leak-clean result is claimed.
This adds no parser integration, numeric validation, strings, heap or native
self-hosting compiler and does not change any kernel qualification.

## Call-scoped readonly sector windows

`storage.sector_window` supplies `read_sector_window(bytes, base_lba, requested_lba)`.
It reads one owned `SectorReadResult` from a checked readonly 1–8-sector window,
using the same `Sector512` and `SectorIoStatus` as RAM I/O. The span is never
retained. Invalid length precedes invalid address; failed results expose zero
bytes. A window is not a full-device capacity claim. See the
[contract and focused acceptance gate](../docs/sector-window-contract.md).

## XFS headers over copied sector I/O

`fs.xfs_sector` preserves failed read statuses, parses successfully copied sector
bytes through the existing XFS geometry checks, and rejects a header whose
claimed data area exceeds the supplied source sector count. Its copied report
keeps I/O and metadata errors separate and masks capacity-admitted facts on
failure. A real preserved header in the one-sector RAM backend is correctly too
large; success tests use explicitly constructed geometry values.

The [contract](../docs/xfs-sector-contract.md) records error precedence, provenance
limits and the separate scoped multi-sector-window contract. This is hosted header
inspection, not a mount, file-data reader or complete device implementation.
