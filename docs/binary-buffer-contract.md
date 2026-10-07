# Owned binary serialization buffer

Import `std.binary_buffer` and `std.binary` for `std::BinaryBuffer64`,
`ByteWriteStatus`, `ByteReadStatus` and `ByteReadResult`. Public signature types
must be directly visible under the current module rules.

The buffer owns one private 64-byte array. It is the sole owned record value,
with no device geometry, flush or second block representation. No compatibility
alias or block/writer conversion function remains.

## Operations

- `BinaryBuffer64()` zero-initializes all 64 bytes; `size()` returns 64.
- `at(i64 offset) const -> u8` returns a copied byte and retains the existing
  checked bounds trap for invalid offsets.
- `read_u8(i64 offset) const -> ByteReadResult` returns a copied u64 in 0..255,
  or `ByteReadStatus::out_of_range`. Failed reports preserve fallback masking.
- `write_u8(i64 offset, u8 value) -> ByteWriteStatus` replaces one byte.
- `write_le16`, `write_be16`, `write_le32`, `write_be32`, `write_le64` and
  `write_be64` accept `(i64 offset, u64 value)` and reuse `std.bytes` encoders.

Writes first reject a negative offset or an offset greater than 64 minus the
field width. Only then reject a value too wide for a 16/32-bit field. Every u64
fits a 64-bit field; every u8 fits one byte. Failures are `out_of_range` or
`value_out_of_range`, preserve all 64 bytes and precede any store. Success changes
only the selected bytes. No offset-plus-width overflow is used for admission.

Ordinary copies, arguments and results own independent bytes. No retained source
view, mutable span, cursor, heap or reflection escape is introduced. Copying
selected bytes to a local array still permits the existing readonly binary
readers to decode them. The [example](../library/examples/binary_buffer.au) runs
that composition without another owned record type.

## Validation

`python3 -B tests/compiler/binary_buffer.py build/aurorac` retains the previous
278 encoding/copy/interoperation cases and adds the former exhaustive 256
byte-position patterns plus recoverable-read and complete-copy checks: 542
native cases, ten rejections, three exact `at` bounds-trap fixtures
and the updated example. Native execution passed in normal and optimized Python
on the reviewed owned-field compiler; see the [focused results](storage-consolidation.md#focused-verification--2026-10-07).
Independent final evidence review accepted these results.

[Historical writer results](history/binary-writer-results.md) describe the removed
API's original source and do not qualify the new API. The
[consolidation contract](storage-consolidation.md) records migration and limits.
