# Checked sector I/O

`storage.block_io` is the sole storage-device contract. Import `std.binary`,
`std.binary_buffer`, `storage.sector`, `storage.block_io` and `storage.ram_sector`
for its concrete RAM implementation and directly visible public signature types.

## Values and operations

- `SectorIoStatus`: `success`, `out_of_range`, `read_only`
- `SectorFlushMode`: `visibility`, `durable`
- `SectorFlushStatus`: `volatile_complete`, `unsupported`
- `SectorGeometry`: fixed 512-byte sectors, copied u64 count and writability
- `SectorReadResult`: copied I/O status and `sector_or_zero()` snapshot

A failed read report masks all 512 payload bytes, including publicly constructed
error reports containing nonzero bytes. The report is exactly 520 canonical
bytes. Geometry/read-report constructors are ordinary values, not source
provenance or authority.

`RamSectorDevice(Sector512 initial)` takes a named complete sector snapshot and
starts writable. A zero device uses a named zero-initialized `Sector512`. There
is no hidden seed write or discarded I/O result. Initializing an owned class
field requires this explicit constructor parameter; no nested-default-construction
extension is assumed.

The backend owns one `Sector512 payload` and one readonly flag, exactly 520 bytes.
Its complete-field assignment uses the separately reviewed owned-field compiler
mechanism. No handwritten byte loop or second raw byte array is present here.

- `geometry()` advertises exactly one sector and current writability.
- `read_sector(i64 index)` admits only zero and returns a complete independent copy.
- `write_sector(i64 index, Sector512 sector)` rejects range before readonly state,
  then replaces the owned field from the complete copied argument.
- `make_read_only()` succeeds repeatedly and never changes payload bytes.
- `flush(visibility)` returns `volatile_complete`; successful writes are already
  synchronously visible through the same device object.
- `flush(durable)` returns `unsupported` and never claims persistent completion.

Both signed index endpoints fail recoverably. Every failed write preserves the
full payload and readonly flag. Copies are independent snapshot clones, not
shared handles; freezing one does not freeze another. Argument snapshots retain
ordinary eager left-to-right evaluation. No concurrency barrier, transaction,
hardware atomicity, kernel capability or durability follows.

## Removed parallel API

There is no `RamBlockStore`, 64-byte device geometry or separate block flush
vocabulary. A 64-byte `BinaryBuffer64` is a serialization value that can occupy a
record position within an owned sector. Device operations always transfer sectors.
The [single example](../library/examples/ram_sector_record.au) writes header/trailer
records directly, constructs a device from the finished sector, then checks retained
read snapshots after overwriting the device.

## Validation and limits

The migrated `tests/compiler/block_io.py` retains 38 native case definitions,
13 privacy/type/rejection fixtures and the one device example. Complete patterns,
every byte position, range-before-readonly ordering, explicit initial-value copies,
retained reports/devices, geometry independence and both flush modes remain covered.
Native execution passed in normal and optimized Python on the reviewed owned-field
compiler; see [the focused results](storage-consolidation.md#focused-verification--2026-10-07).
Independent final evidence review accepted these results.

The value cap remains 512 byte leaves and 520 copied bytes. Two inline sectors
still do not fit; there is no generic driver framework, borrowed multi-sector
backend, heap, real device or filesystem mount. The existing XFS sector consumer
is migrated to the same buffer/status vocabulary. Historical PR52 qualification
is preserved [separately](history/block-io-contract-pr54.md); it is not a pass for
this representation change. See [the consolidation](storage-consolidation.md).
