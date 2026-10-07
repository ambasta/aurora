> Historical checkpoint. These APIs were removed by the
> [storage consolidation](../storage-consolidation.md).

# Bounded owned binary writer

`import std.binary_writer;` supplies `std::BinaryWriter64` and the closed
`std::ByteWriteStatus` enum. The writer owns a private, completely initialized
64-byte array. It uses the existing `std.bytes` field encoders; no compiler change,
host serializer, raw pointer, returned view or allocation is involved.

The next dependency is a reusable owned record buffer that can reject a whole
field write before changing its destination. Its acceptance gate is native Aurora
execution against independently generated complete byte vectors, including every
failure preserving all old bytes, independent copies and readonly-reader use.

## API and failure ordering

- `BinaryWriter64()` initializes all 64 bytes to zero.
- `size() const -> i64` returns 64.
- `at(i64 offset) const -> u8` returns a copied byte. Invalid offsets fail at the
  language's existing checked bounds trap, like `std::Bytes2/4/8::at`.
- `write_u8(i64 offset, u8 value) -> ByteWriteStatus` writes one byte.
- `write_le16`, `write_be16`, `write_le32`, `write_be32`, `write_le64` and
  `write_be64` take `(i64 offset, u64 value)` and return `ByteWriteStatus`.

Writes have three possible outcomes, in this order:

1. `out_of_range`: the offset is negative or greater than 64 minus the field
   width in bytes. This check occurs without adding the width to the offset,
   so even the signed minimum/maximum cannot overflow. It takes precedence
   when the value also exceeds the requested width.
2. `value_out_of_range`: a 16-bit value exceeds 65535 or a 32-bit value exceeds
   4294967295. Every u64 fits a 64-bit field; every exact u8 fits a byte.
3. `success`: all field bytes are overwritten in the requested explicit order.

Either failure leaves every one of the 64 bytes unchanged. The complete bounds
and value checks happen before the first store; the subsequent fixed-length
loop only indexes the proven destination range and the encoded field. Successful
writes preserve every byte outside that range. Arguments retain ordinary eager
left-to-right evaluation before method entry. This is per-call all-or-nothing
failure behavior, not concurrency atomicity, crash consistency or a transaction
spanning several successful calls.

There is no cursor or implicit append position. Callers supply explicit offsets
and check each status. Ordinary class copies, function arguments and returned
values are independent byte snapshots. Const receivers cannot write. No mutable
span or reference to the private array escapes. To use the readonly readers,
copy the needed bytes to a local array as in the
[running example](https://github.com/ambasta/aurora/blob/129d5337da8513ad0f5be92b7700c62482f64293/library/examples/binary_writer.au).

## Why this bound is explicit

The existing compiler admits private array fields with capacities 1..64 and
copied class values with at most 64 scalar leaves. This writer uses that existing
limit directly, with packed byte size 64. It is a small record buffer, not a
512-byte hardware sector or a generic/dynamic buffer. A sector-sized owned-byte
API requires a separately reviewed language/storage extension; the library does
not simulate it with unsafe pointers or claim a new general borrowing facility.

## Validation and limits

`python3 -B tests/compiler/binary_writer.py build/aurorac` is the focused native
gate. It checks full independent byte vectors, offset and width endpoints,
simultaneous errors, overlapping sequences, all bytes after failed writes,
zero initialization, exact packed size, copied function inputs/results, reader
interoperation, exact read-bounds traps and privacy/const/type rejections.
The compiler test aggregate includes this gate beside the existing codec tests.

Focused native writer execution passed in normal and Python optimized modes,
along with the existing byte-codec and storage-reader regression gates. See the
[exact results](binary-writer-results.md). Independent final review accepted this focused scope.
No full native aggregate, sanitizer, kernel, filesystem, NVMe or hardware
qualification is implied.
