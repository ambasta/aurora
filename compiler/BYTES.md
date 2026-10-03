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
before addressing. Copies traverse complete typed fields, and representation padding
is zeroed; no source expression can address padding. Stack-reservation slack outside
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
