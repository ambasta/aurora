# Owned sectors and copied serialization records

Import `std.binary`, `std.binary_buffer` and `storage.sector`.
`storage::Sector512` owns a private zero-initialized 512-byte array. It has no
geometry, flush or device identity. Ordinary copied values have independent bytes.

## Operations and copied reports

- `size() const -> i64` returns 512.
- `read_byte(i64 offset) const -> std::ByteReadResult` admits 0..511 and returns
  a u64 byte value in 0..255; invalid offsets return `ByteReadStatus::out_of_range`.
- `write_byte(i64 offset, u8 value) -> std::ByteWriteStatus` admits 0..511.
- `read_record(i64 offset) const -> RecordReadResult` copies 64 bytes from an
  admitted offset 0..448 into a `std::BinaryBuffer64` snapshot.
- `write_record(i64 offset, std::BinaryBuffer64 record) -> ByteWriteStatus`
  replaces those 64 bytes from the already-copied record argument.

Read errors use `ByteReadStatus`; writes use the existing `ByteWriteStatus`.
Sector writes can return only `success` or `out_of_range` because their values
already consist of valid bytes. These are buffer/encoding operations, distinct
from device I/O's readonly error and from flush/durability outcomes.

`RecordReadResult` has exactly 72 bytes and returns a copied `status()` plus
`record_or_zero()`. The latter masks every failure to an all-zero record, including
caller-constructed failures containing nonzero data. Later source/record mutation
cannot alter a retained report. Public constructors grant no authority.

Offsets are byte positions and need not be aligned. Full-range preflight occurs
before indexing or mutation. Checking against 448 avoids adding 64 to untrusted
signed offsets. Both signed endpoints fail recoverably, without changing any
sector byte. Successful writes preserve every neighboring byte. Snapshot arguments
make aliasing behavior explicit; this is not a multi-call transaction, concurrent
atomicity, crash consistency or hardware atomicity guarantee.

The read/write record methods are the two shared, checked transfer primitives
between the distinct 64-byte record and 512-byte sector values. They perform real
copies; no writer/block conversion or duplicate backing buffer is involved.
Callers pass a `BinaryBuffer64` directly. No 512-capacity class template is invented.

## Validation and scope

`python3 -B tests/compiler/sector.py build/aurorac` defines 46 cases and nine
rejections. It retains all 512 byte positions, all 449 possible record offsets,
neighbor/error preservation, copied values, overlapping sequences and field-codec
checks. Added checks preserve the removed block result's 72-byte layout, masking
and argument/result copying, plus several records sharing one sector without
changing unused bytes. The single device example is exercised by the I/O runner.
Native execution passed in normal and optimized Python on the reviewed owned-field
compiler; see [the focused results](storage-consolidation.md#focused-verification--2026-10-07).
Independent final evidence review accepted these results.

[Historical sector results](history/sector-contract-pr54.md) remain dated evidence
for the previous API. Current consolidation adds no disk, mount, mutable borrow,
heap or kernel admission. See [the migration](storage-consolidation.md).
