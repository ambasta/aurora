# Checked bytes and compact fixed values: milestone013

This work has two separate acceptance gates: exact u8 numeric behavior, and
byte-stride storage through verified layout/copy boundaries. Both gates are implemented. The final packed candidate passes the complete
author release and ASan/UBSan compiler targets, and independent compiler review
passed. Final parent and 139-mode kernel integration passed; see docs/verification.md. The earlier gate A execution evidence belongs to its
separately pinned padded compiler and does not establish compact representation. Historical milestone012 evidence is unchanged.

## Numeric contract

`u8` denotes integers from 0 through 255. Decimal `255u8` literals have that exact
type; larger literals reject. Explicit `u8(i64)` and `u8(u64)` conversions fail at
the existing arithmetic-overflow site outside that range. `i64(u8)` and `u64(u8)`
widen exactly. There are no implicit promotions, identity casts, boolean/enum
casts, truncating casts or source address conversions.

Addition, subtraction and multiplication check mathematical representability.
Division/remainder check zero before native division. Bitwise complement is exactly
eight bits; and/or/xor preserve u8. Both shift operators require a signed i64 count
from 0 through 7, with the existing distinct shift-count failure outside that range.
Left shift checks the mathematical result; right shift zero-fills. Unsigned unary
minus rejects. Comparisons require the same type on both sides.

Scalar deliberately expands to i64/u64/u8/bool; Value includes these plus the
existing named class and closed enum types. Enums still do not satisfy Scalar.
The appended builtin ID is 11; byte-array IDs are 3000000+N. Old type IDs and old
specializations retain their identities. There is no new constant-evaluation language.

## ASCII byte character literals

Single-quoted literals such as `'['`, `'"'` and `'a'` have exactly type `u8`,
just like `91u8`, `34u8` and `97u8`. No suffix is required or accepted. They work
in scalar expressions, comparisons, static assertions, array initializers,
constructor arguments and returns under the existing exact-type rules. Explicit
`i64(...)` or `u64(...)` conversion is still required to widen them; unary minus,
implicit promotions and identity conversions remain rejected.

An unescaped body is exactly one printable ASCII byte (`0x20` through `0x7e`),
other than single quote or backslash. The complete escape set is `\'`, `\\`,
`\0`, `\a`, `\b`, `\f`, `\n`, `\r`, `\t`, `\v` and `\xHH`. The hex escape
requires exactly two hexadecimal digits, accepts either digit case and denotes
any byte from `0x00` through `0xff`. Double quote is written directly as `'"'`;
`\"` is not an additional escape.

Empty or multibyte bodies, suffixes, raw control bytes, raw non-ASCII text,
unterminated literals, malformed escapes and extra hexadecimal digits reject
with lexical diagnostic AU1002. Octal escapes, Unicode escapes, code points,
grapheme literals and string values are not introduced. `\xFF` is byte value 255,
not a Unicode character or a UTF-8 encoder.

The shared lexer retains the exact source spelling and half-open byte span;
formatting never replaces a character spelling with a number or splits it.
Malformed literal spans start at the opening quote and end after the attempted
spelling, stopping before an unescaped or escaped CR/LF or at EOF when no closing
quote exists. Constants lower through the existing typed-u8 IR and checked
arithmetic. The two quote append calls in `std.json_write` exercise the new
spelling without changing the writer's transactional behavior.

### Byte spelling acceptance boundary

The focused native gate checks 366 values, four attributed checked traps,
157 lexical and nine exact-type rejections. All 361 accepted spellings emit
byte-identical assembly to their decimal `u8` equivalents. Lossless spans and
formatter token/comment preservation and idempotence cover 100 source files;
byte scanner checks also run in each available C, UTF-8, English and Turkish
locale. Both quote spellings produce identical assembly for the complete JSON
writer import closure, whose native string-append tests remain in force.

The joined compiler preserves exact assembly for all 38 predecessor kernel
policy, protected-program and kernel-example roots. This is compiler-output
preservation, not a new guest execution or physical-hardware qualification.
Typed IR, u8 representation and the backend are unchanged; no new ABI, cast,
Unicode type or ownership operation is introduced. The feature is registered
in the complete Meson developer/byte/full suites and compiler Make test graph.
The [canonical final-source merge gates](../AGENTS.md#workflow) and independent
review remain mandatory; focused results never substitute for those gates.

## Bounded byte-string array initializers

Double-quoted text initializes an explicitly typed, named local `array<u8, N>`:

```cpp
const array<u8, 6> prefix = "IOMMU ";
const builtin::span<const u8> text = borrow_bytes(prefix);
```

The decoded byte count must equal `N` exactly. The existing capacity range is
1–4096; there is no inferred length, padding or hidden NUL terminator. Mutable
arrays, same-type array copies, indexing and lexical readonly borrows retain
their existing rules. A string spelling cannot itself be borrowed, returned,
passed as a value, assigned to an existing array or used to initialize a scalar,
non-`u8` array, class field or span. It creates no temporary backing object,
heap string type, pointer conversion or new lifetime rule.

Raw printable ASCII is copied exactly, except that double quote and backslash
need escapes. Raw non-ASCII text must be valid UTF-8 and contributes its original
encoded bytes, without normalization: `"é"` requires two bytes and `"😀"` four.
This is byte-array storage, not a Unicode character type or a guarantee that the
resulting bytes form UTF-8. Escapes support the existing byte-character set
(`\'`, `\\`, `\0`, `\a`, `\b`, `\f`, `\n`, `\r`, `\t`, `\v`, `\xHH`)
plus `\"` for the delimiter. Each escape contributes one byte; `\xHH` consumes
exactly two hex digits, so `"\x4142"` stores `A42`. `"\01"` stores zero then
`1`, not an octal escape. Escaped `\xFF` and embedded `\0` are ordinary bytes.
Single-quoted character literals remain ASCII-only with their existing escapes.

Raw ASCII controls/DEL, malformed UTF-8, unknown/Unicode/octal escapes, suffixes,
unterminated text and literals longer than 4096 decoded bytes fail lexically with
AU1003. CR/LF, including after a backslash, terminate a malformed spelling rather
than introducing multiline text. Adjacent strings are not concatenated. The
empty spelling is lexically valid but cannot initialize a positive-length array.

The shared lexer preserves one exact spelling/span for the formatter and LSP.
Lowering emits the same typed-byte constants and array stores as an explicit
brace initializer; IR, backend, storage layout and authority are unchanged.
Event reporting and the native serial console use these initializers immediately.
The existing byte-literal, lossless lexer, formatter and LSP-position tests cover
this extension, including decoded lengths, UTF-8/escapes, rejected escapes and
local borrow escape/mutation. Exact assembly comparisons cover explicit arrays.
Final-source full/image/guest qualification remains required by AGENTS.md; old
source-bound receipts cannot admit the migrated sources.

## Physical representation gate

The implemented representation uses size/alignment one for u8 and stride
one for `builtin::array<u8,N>`. Existing numeric, bool and enum field/array storage
stays eight bytes; standalone bool reflection continues its historical size one.
All layouts lacking u8 retain their prior offsets, size and alignment rules.
Class fields use explicit byte offsets, natural storage alignment and tail padding.
For example Bytes4 has size four; the enum-plus-Bytes4 Encode32Result has size sixteen.

Logical ClassField ranges and scalar leaf counts remain separate from byte offsets.
A canonical recursive layout records leaf/field byte offsets, logical size,
alignment and actual reserved storage extent. The verifier derives it from checked
nominal shape and rejects conflicting supplied metadata. Physical stack and private
call allocations round to eight bytes; disjointness uses these reservations, not
only reflected size. Local frames remain sixteen-byte aligned. Empty standalone
objects retain an eight-byte reservation; nested zero-leaf values retain logical
completion without widening old parents. No empty payload can establish completion
for another field.

Byte loads zero-extend and byte stores require an exact initialized u8 value.
Checks retain the declared length, exact element type, stride and storage provenance
before addressing. Copies traverse complete typed fields. The x86 backend coalesces
exact groups of eight initialized u8 leaves only when both canonical source and
destination byte offsets are consecutive within the selected copied range. Each
group uses one unaligned-capable qword load/store pair with RAX alone; remaining
bytes retain exact byte operations. No group includes padding, a non-u8 leaf or an
owning descriptor. Representation padding is zeroed separately; no source expression
can address it. Stack-reservation slack outside
an object's representation is not a source field or copied payload. Scalar private
calls carry canonical values in registers; aggregate records/results remain distinct
from receiver storage. This is an internal native convention, not a C ABI or an
external wire layout for arbitrary classes.

## Compiled recoverable codec

`import std.bytes;` exports `std::Bytes4`, `std::ByteCodecStatus` and
`std::Encode32Result`. Bytes4 owns a private zero-initialized four-byte array.
`at(i64)` returns a checked byte copy; mutable `set(i64,u8)` stores and returns it.

`std::encode_le32(u64)` and `std::encode_be32(u64)` compare against 4294967295
before extracting bytes. Larger inputs return out_of_range with a zero value;
valid inputs return success and explicitly encoded bytes. There is no artificial
arithmetic trap used as a recoverable range check.

`status()` reports the closed enum. `bytes_or_zero()` returns an independent copy
on success and a newly initialized zero Bytes4 on failure. Even public construction
of an error report carrying nonzero bytes cannot reveal those bytes through this
accessor. Public report construction is not a provenance certificate. A successfully
encoded zero and a failure are distinguished by status. There is no unchecked
payload accessor or class-valued fallback method argument.

`std::decode_le32(Bytes4)` and `std::decode_be32(Bytes4)` consume immutable copies
and explicitly widen/shift/or their bytes. Every four-byte pattern is valid, so
decoding has no error case. All constructors retain complete initializer lists and
empty bodies; the codec needs no new constructor/method grammar.

## Owned storage-field codec extension

`std.bytes` also provides `Bytes2` and `Bytes8`, with the same checked `at(i64)`
and mutable exact-`u8` `set(i64,u8)` interface as `Bytes4`. They own fully
zero-initialized private arrays; their sizes are two and eight bytes. Construction,
class arguments, returned values and local copies retain independent storage.
Negative indices and indices at or above the fixed size fail at the language's
bounds trap; no pointer, mutable view or unchecked access is exposed.

- `encode_le16(u64)` / `encode_be16(u64)` return `Encode16Result`. Inputs through
  65535 succeed; larger inputs return `ByteCodecStatus::out_of_range`.
  `status()` and `bytes_or_zero()` follow the existing 32-bit report contract,
  including zero masking of fabricated nonzero error payloads. The enum-plus-two-
  byte report has size 16 under the existing packed-value rules.
- `encode_le64(u64)` / `encode_be64(u64)` return `Bytes8` directly. Every u64
  value is representable, so no always-success status wrapper is needed.
- `decode_le16(Bytes2)` / `decode_be16(Bytes2)` return u64 in 0..65535;
  `decode_le64(Bytes8)` / `decode_be64(Bytes8)` return the full u64 range.
  Every input byte pattern is valid. Decoders take immutable copied values.

Wire byte order is explicit; class layout is never reinterpreted as a packet.
Encoding narrows only masked 0..255 values, and decoding widens each byte before
shifting. Shift counts are fixed in 0..56 and every shifted byte fits u64.
The [example](../library/examples/storage_codec.au) copies encoded fields into
an ordinary local byte array and consumes them through `std.binary` readers.

The existing codec gate now retains its 32-bit regressions and adds independent
Python byte vectors, independently assembled decode inputs, full-width results,
range/status/masking, copied-value, reader-interoperability, layout and rejection
cases. The packed-value gate adds exact bounds-trap tests for all three owned
byte widths. Existing Make compiler/root aggregates already include both gates.
Validated on 2026-10-07: 789 codec cases, 19 rejection cases and the wire-record
example; 100 packed-value cases including 54 exact bounds traps and 18
rejections; and 254 existing storage cases covering 1,186 API calls. Focused
execution and source review were followed by a fresh complete public
`make --jobs=1 test`, which passed in 41m24s with independent terminal review.
The tested 610-file tree is `77a33b4e8dc7739232673c18bbb917df4d7f0fe9`, based
on main `8ce018ff271e3e0441e9d111f6c958c0df298d4d`. The final result SHA-256 is
`9ebece519e8ddbd564080248ee26b423b9c93ad696d9b9c783a989bad4897bfd`.
These result-document updates are the only later source changes.

Existing codec suites remove temporary native binaries and raw scalar outputs;
retained logs and source review do not establish independent per-binary replay.
No new sanitizer or emulator run was performed. The extension adds no compiler
semantics, general byte writer, borrowing or storage/device authority.

## Validation and limits

The numeric suite independently models all byte unary/conversion values and all
ordered pairs for selected binary operations, with excluded overflow domains
reported separately from executed arithmetic. Exact named UD2 checks cover failure
edges. Codec tests use Python integer/endian models, byte observations, status and
copy checks, and normal syntax/type rejections preserving existing artifacts.
The default codec suite includes packed size and mixed/nested layout checks;
`--without-layout` is only an interim numeric/API gate and cannot establish packing.

Acceptance also requires malformed typed-IR width/offset/stride/initialization
checks, mixed-width call/receiver/result copies including empty children, all prior
regressions, sanitizer runs and independent review. Existing depth/leaf/frame caps
are not a general compiler resource bound or a whole-program stack guarantee.

No text encoding, Unicode, heap collection, slice, pointer, reinterpretation,
serialization of arbitrary classes or general runtime is added. Compact byte data
is a prerequisite for subsequent text design, not a u64-per-character text API.
No equivalent-C throughput or zero-cost claim is made; code size/layout evidence
and future equivalent-semantics performance measurements are distinct.

## Candidate receipts

Release compiler `02771e0d94ad9fe9821041ee10081d31a4f4114dde81b7d476e16cba8d5c75d2`
and sanitizer compiler
`cbe0d747958892457131bb1175c61a3d8debf86c60d1decee55ce7429d118782`
identify the current source candidate. The numerical source suite has 923,136
observations, 37 source positives, 117 exact-site traps and 138 rejection fixtures.
The exhaustive arithmetic observations execute representable operand domains;
excluded inputs produce a sentinel, while separate boundary fixtures check traps.
They do not exhaust every failing instruction path. Codec tests cover 352 native
cases and seven rejections; packed source tests cover 75 native cases, including
30 bounds sites, and 19 rejections. Alternate seed counts overlap these suites.

The full author sanitized target passes 846 direct IR cases, ten exhaustive
dispatch controls, preserved native groups of 18/8/13, 2,627 direct u8 native
checks including 260 exact sites, and fourteen packed ABI/padding checks. Existing
source, module, depth, reader/writer and integer-oracle checks also pass. The
separate scalar oracle passes 630 default and 1,526 seed404 cases on both release
and sanitizer compilers; 64 comparisons against milestone012 agree. These are
bounded observations, not a proof or a performance benchmark. Independent compiler review additionally passed alternate codec/packed cases
and 64 constructor ABI cases on both compiler builds. Final milestone-wide
acceptance remains separate and pending.
