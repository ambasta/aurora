# Checked sector I/O

`storage.block_io` is the sole storage-device contract. Import `std.binary`,
`std.binary_buffer`, `storage.sector`, `storage.block_io` and `storage.ram_sector`
for its concrete RAM implementation and directly visible public signature types.

## Values and operations

- `SectorIoStatus`: `success`, `out_of_range`, `read_only`, `invalid_source`
- `SectorFlushMode`: `visibility`, `durable`
- `SectorFlushStatus`: `volatile_complete`, `unsupported`
- `SectorGeometry`: fixed 512-byte sectors, copied u64 count and writability
- `SectorReadResult`: copied I/O status and `sector_or_zero()` snapshot

`Sector512` remains a copied 512-byte value. A failed read report masks all 512
payload bytes, including publicly constructed error reports containing nonzero
bytes. The report remains exactly 520 canonical bytes. Geometry/read-report
constructors are ordinary values, not allocation provenance or authority.

## Runtime-owned RAM device

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

## Example and validation scope

The [single example](../library/examples/ram_sector_record.au) receives a region
and runtime sector count, checks count multiplication before allocating, writes
header/trailer records through the same sector API and checks retained snapshots.
Its header records the actual runtime count. The explicit hosted test adapter
grants authority; there is no implicit allocation grant for a standalone main.

The focused I/O runner defines 57 native cases, 18 rejection fixtures and six
example invocations. It covers runtime counts 1/2/3/17/129, complete byte patterns,
last-sector access, independently seeded linear backing, copied result
independence, explicit device transfers, zero versus failed allocation, partial
sectors, allocator/quota failure, extreme indices and range-before-readonly.
The 121-case/five-rejection XFS sector consumer uses the same owning device while
preserving its copied reports and metadata/capacity error ordering.

Fresh compile-only admission passed 181 positive fixtures (167 distinct emitted
programs) and 23 rejection fixtures. Both native runners and all six example
invocations passed in normal and optimized Python, with retained source,
assembly, executables, raw return/allocation/release observations and strict
input/output-preserving rejection diagnostics. The stricter replay first exposed
an implicit-copy diagnostic incorrectly pointing at the imported class; that
failed run is retained, the compiler now identifies the offending expression,
and corrected replays passed without relaxing the location matcher.

The XFS native runs used compiler SHA256
`f7f6b81ddb93750ee5235205b1b9b1e0c8e23987ac5906e01f9b97854f235a06`;
the corrected block-I/O runs used
`3653897d2c9780eaec83dc29eb156529bb167de334cad7dd72c2e7dd09985b90`.
Canonical formatting and the final diagnostic-only compiler refresh were
separately checked against all 167 admitted assemblies; emitted bytes were
unchanged. These are focused hosted results, not a full native aggregate. Earlier
inline-sector results in the [consolidation history](storage-consolidation.md)
do not qualify this representation. Copied-value caps remain unchanged; runtime
capacity is bounded by successful allocation and representation. No guest,
physical device, filesystem mount, durability or performance claim follows.
