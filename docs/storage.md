# Binary records and sector I/O

These are volatile, checked byte/sector interfaces. They provide no mounted filesystem, persistent completion, hardware atomicity or physical-device qualification. Fixed copied records and runtime-owned devices have different ownership and purpose; the device count derives from its allocation.

## BinaryBuffer64

Import `std.binary_buffer` and `std.binary` for `std::BinaryBuffer64`,
`ByteWriteStatus`, `ByteReadStatus` and `ByteReadResult`. Public signature types
must be directly visible under the current module rules.

The buffer owns one private 64-byte array. It is the sole owned record value,
with no device geometry, flush or second block representation. No compatibility
alias or block/writer conversion function remains.

### Operations

- `BinaryBuffer64()` zero-initializes all 64 bytes; `size()` returns 64.
- `at(i64 offset) const -> u8` returns a copied byte and retains the existing
  checked bounds trap for invalid offsets.
- `bytes(i64 offset, i64 count) const -> builtin::span<const u8>` borrows a
  checked readonly range without copying. Invalid ranges trap through ordinary
  bounds checks; an empty range at the end is valid.
- `equal(i64 offset, i64 count, builtin::span<const u8> value) const -> bool`
  rejects invalid ranges with false, then delegates to `std::equal` over that view.
- `starts_with(i64 count, builtin::span<const u8> prefix) const -> bool`
  rejects an invalid logical count, then delegates to `std::starts_with` over
  the prefix of storage. Byte comparison has one shared implementation.
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

Ordinary copies, arguments and results own independent bytes. A returned view is
bound to its exact named receiver and private field for that binding's lexical
lifetime. It prevents overlapping writes and mutable receiver calls while live;
copies have independent roots. It is not a mutable view or a stored capability.
See [ownership and receiver views](../compiler/OWNERSHIP.md) for the exact scope.

## Sector512

Import `std.binary`, `std.binary_buffer` and `storage.sector`.
`storage::Sector512` owns a private zero-initialized 512-byte array. It has no
geometry, flush or device identity. Ordinary copied values have independent bytes.

### Operations and copied reports

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

## RAM sector device

`storage.block_io` is the sole storage-device contract. Import `std.binary`,
`std.binary_buffer`, `storage.sector`, `storage.block_io` and `storage.ram_sector`
for its concrete RAM implementation and directly visible public signature types.

### Values and operations

- `SectorIoStatus`: `success`, `out_of_range`, `read_only`, `invalid_source`
- `SectorFlushMode`: `visibility`, `durable`
- `SectorFlushStatus`: `volatile_complete`, `unsupported`
- `SectorGeometry`: fixed 512-byte sectors, copied u64 count and writability
- `SectorReadResult`: copied I/O status and `sector_or_zero()` snapshot

`Sector512` remains a copied 512-byte value. A failed read report masks all 512
payload bytes, including publicly constructed error reports containing nonzero
bytes. The report remains exactly 520 canonical bytes. Geometry/read-report
constructors are ordinary values, not allocation provenance or authority.

### Runtime-owned RAM device

Allocate `builtin::OwnedBytes` using a host-granted `builtin::ByteRegion`, then
transfer the named owner into `RamSectorDevice(region, move(bytes))`. The device
owns those runtime-sized bytes and a readonly flag. Device transfers require
`move(device)`, including ordinary function arguments/returns; implicit copies
and owner-field extraction are rejected. Methods borrow the device synchronously.
The supplying region must outlive its owners.

`status()` reports `success` only when the allocation succeeded and its byte
length is a multiple of 512. A successful zero-length allocation is a valid
zero-sector device. Failed allocation, including failed zero-length metadata
allocation, and non-whole-sector lengths report `invalid_source`. No length is
rounded and no caller-provided capacity or fixed sector cap is trusted.

- `geometry()` derives count from successful byte length divided by 512 and
  reports current writability. Invalid sources report zero/unwritable.
- `read_sector(i64 index)` returns a complete independent copied sector.
- `write_sector(i64 index, Sector512 sector)` copies all 512 argument bytes.
- Both operations reject invalid sources before access. On valid sources they
  check signed range before offset multiplication; writes check range before
  readonly state. A valid empty device rejects every index as `out_of_range`.
- `make_read_only()` succeeds repeatedly on valid devices without changing
  payload bytes; invalid sources return `invalid_source`.
- `flush(visibility)` returns `volatile_complete` on valid devices, including
  empty/readonly ones. Successful writes are already synchronously visible.
- `flush(durable)` returns `unsupported`. Either mode returns `unsupported` on
  an invalid source; no persistent completion is claimed.

Both signed index endpoints are rejected recoverably. For successful aligned
length L, the preflight `0 <= index < L/512` proves `index*512 + offset < L` for
all copied byte offsets 0..511, without signed overflow. Every failed write
preserves the entire payload and readonly flag. Sector arguments, extracted
sectors and copied reports retain independent snapshots after later device
writes or moves. Distinct devices require distinct allocations; they are not
implicit snapshot clones or shared handles.

The two direction-specific copy loops are the necessary boundary between owned
runtime bytes and copied sectors. The language exposes no suitable mutable view
or owner-field borrow for combining them safely. No second backend, borrowed
payload escape, concurrency barrier, transaction, kernel capability or hardware
atomicity is introduced.

## Call-scoped sector windows

### One operation on the existing contract

`storage::read_sector_window(bytes, base_lba, requested_lba)` in
`storage.sector_window` takes a call-scoped `builtin::span<const u8>`, a `u64`
absolute base LBA and an exact `i64` requested absolute LBA. It returns the
existing owned `SectorReadResult` (520 bytes), containing one copied `Sector512`.
There is no handle, retained span, new backend, geometry or write operation.
The span describes only this window; its length is not full-device capacity.

The error domain remains `SectorIoStatus`, with one appended `invalid_source`
outcome. Existing `success`, `out_of_range` and `read_only` meanings are unchanged.
`SectorReadResult.sector_or_zero()` already masks every non-success outcome;
`fs.xfs_sector` preserves that exact I/O status and rejects it before parsing.
The focused regressions exercise nonzero failure payloads and every public XFS
report status with the new outcome, including fabricated success reports.

### Ordered preflight and copying

1. An empty span, a length not divisible by 512, or a length greater than 4096
   returns `invalid_source` before any request conversion, subtraction or read.
2. A negative request returns `out_of_range` before conversion to `u64`.
3. An unsigned request below the base returns `out_of_range` before subtraction.
4. Subtract the base and compare the relative index against `length / 512`.
   An index outside the window returns `out_of_range` before multiplication.
5. Convert only the admitted relative index (0 through 7), multiply by 512,
   and copy 512 bytes through checked span reads and `Sector512.write_byte`.

No `base_lba + count` is computed. Bases above signed-i64 maximum have no
addressable request. Negative requests never wrap into that range. A window
beginning at signed maximum may still supply its first sector; later sectors
are simply not expressible through this signed request API. Source alignment
is relative to the span: a 512-byte subspan can start at any valid owner offset.

The one byte loop is the necessary readonly-span-to-owned-value boundary. It
is not a second RAM transport loop or an adapter between duplicate storage
values. Full length and address preflight precede it. The source remains
unchanged, and report/sector copies survive owner mutation and destruction.
All failures return a zero-initialized owned sector. No view escapes the call.

## Tests

`tests/compiler/storage` holds one Aurora driver per library family (byte values,
binary readers and CRC32C, block I/O, XFS geometry, root and file). Each driver is
compiled once and run over every case as a data record; its results are compared
with the reviewed `.golden` file beside it. After an intended behavior change,
rerun the family with `--update-golden` and review the diff.
