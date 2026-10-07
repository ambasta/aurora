# Checked one-sector block I/O

The next dependency after owned sector values is a real, bounded sector-I/O
consumer contract. Its acceptance gate is hosted native execution against
independent complete 512-byte models, exact layout checks, copy boundaries,
recoverable errors and an encoded metadata round trip through the public API.
This candidate adds no compiler semantics.

## Types and geometry

Import `storage.block`, `storage.sector`, `storage.block_io` and
`storage.ram_sector` when using the complete API. Explicit imports preserve the
current direct-import visibility rules. `storage.block_io` defines:

- `SectorIoStatus`: `success`, `out_of_range`, `read_only`
- `SectorFlushMode`: `visibility`, `durable`
- `SectorFlushStatus`: `volatile_complete`, `unsupported`
- `SectorGeometry`: copied `sector_size_bytes()`, `sector_count()` and
  `can_write()` observations
- `SectorReadResult`: copied `status()` and `sector_or_zero()` observations

The sector-based contract fixes sector size at 512 bytes. Geometry carries a
full-width u64 sector count rather than making consumers assume one address.
A publicly constructed geometry is a value, not validation or authority for an
actual device. The implemented device advertises exactly one sector, 512 bytes,
and its current writability. A geometry snapshot does not change after a device
is made readonly.

`SectorReadResult` is a complete owned snapshot. `sector_or_zero()` copies all
512 payload bytes for `success` and returns all-zero bytes for every other
status, including a caller-constructed error report containing nonzero data.
A status plus sector has exactly 520 canonical bytes. No view or mutable
reference escapes either operation.

## One-sector RAM implementation

`RamSectorDevice()` initializes a private `builtin::array<u8,512>` to zero and
starts writable. It has exactly 520 canonical bytes: 512 byte leaves and one
8-byte readonly flag. Its API is:

- `geometry() const -> SectorGeometry`
- `read_sector(i64 index) const -> SectorReadResult`
- `write_sector(i64 index, Sector512 sector) -> SectorIoStatus`
- `make_read_only() -> SectorIoStatus`
- `flush(SectorFlushMode mode) const -> SectorFlushStatus`

Only index zero is valid. Reads and writes reject negative and positive out-of-
range indices before indexing or changing state; both signed-i64 endpoints are
recoverable failures. Write range checks take precedence over readonly checks.
A valid-index write on a readonly device returns `read_only`; every failed write
preserves all sector bytes and the readonly flag. Successful writes replace
exactly 512 bytes from the already-copied argument and are synchronously visible
to subsequent calls on that same object.

`make_read_only()` succeeds even when already readonly and never changes data.
It is one-way for that object. To create a seeded readonly device, initialize a
fresh device, call `write_sector(0, initial)`, check `success`, then call
`make_read_only()` and check `success`. No constructor or factory discards a
potential write failure. The [record example](../library/examples/ram_sector_record.au)
uses checked public I/O and the existing writer/window/reader composition.

Copies of a device own independent bytes and flags. Copying is a snapshot clone,
not another handle to one shared device. Freezing one clone does not freeze an
existing writable clone. A caller can read a readonly instance and explicitly
write those copied bytes to another writable instance. Readonly is local API
state, not a security capability or kernel permission boundary.

## Flush and failure scope

`flush(visibility)` returns `volatile_complete`. Prior successful synchronous
writes are visible through subsequent operations on this object. The call does
not add concurrency synchronization, CPU/device barriers, persistence or an
ordering guarantee between different device clones. Bytes can be lost with the
process or machine.

`flush(durable)` returns `unsupported` on writable and readonly instances,
including an untouched device. It never changes bytes or mode and never reports
durable completion. A failed durable flush does not undo already-visible writes.
Callers that require persistence must reject this backend rather than interpreting
`volatile_complete` as a durable commit. Range and readonly errors belong to
sector I/O; unsupported durability belongs to the distinct flush result domain.
There is no fabricated transient hardware-error, async or cancellation path.

Arguments retain ordinary eager, left-to-right evaluation before method entry.
Recoverable per-call failure preservation is not multi-call transactional rollback,
concurrent atomicity, crash consistency or 512-byte hardware atomicity.

## Existing limits and next language dependency

The implementation uses a byte array rather than a nested `Sector512` field
because current Aurora cannot mutate a nested class receiver or assign a whole
nested field after construction. Supporting a scoped checked mutable receiver
for a private nested value would let a device reuse owned storage directly;
whole-field replacement would be a separate useful extension. Such a feature
needs explicit receiver authority, const/lifetime, initialization and IR tests.
It is not part of this increment, and no unsafe pointer bypass is used here.

One sector is the useful bounded backend admitted by current copied-value caps.
Two inline sectors exceed the 512-u8-leaf limit; a device plus a status word
would exceed the 520-byte copied-storage cap. The pre-existing `RamBlockStore`
remains four 64-byte records, not four 512-byte sectors. Template capacities,
value caps and compiler stack costs are unchanged.

The common contract is a set of concrete value types and public operation
semantics, not dynamic dispatch, a trait, a generic driver framework or heap
ownership. This hosted RAM implementation does not access disks, NVMe, DMA or
kernel authority. No filesystem mount, multi-sector transaction, persistent
storage, kernel admission, sanitizer, full native aggregate or hardware
qualification follows.

## Validation

Run `python3 -B tests/compiler/block_io.py build/aurorac`, or select `block-io`
with Meson's two-worker `bytes` suite. The existing native runner observes full
u64 results and validates rejection/output preservation. The new corpus covers
exact layouts, zero data, every single byte position through whole-sector I/O,
complete independent patterns, both signed endpoints, readonly/range precedence,
error masking, copied reports and devices, mode/geometry independence, repeated
flushes and mixed write/flush/freeze sequences. The example encodes a one-sector
volume header and trailer, writes and rereads them through the device, then
decodes the retained read after overwriting the device.

All 38 native cases, 13 rejection fixtures and the metadata example passed in
normal and optimized Python modes. The exhaustive transport case checks every
single-byte position and all 512 returned bytes for each position. Both flush
modes are checked on an untouched device as well as seeded writable and readonly
instances. Exact enum, geometry, read-report and device sizes passed.

All seven selected Meson runners passed with two workers: block-io, owned-sector
(43 cases), block-value (264), ram-blocks (39), binary-writer (278), byte-codec
(789) and storage-binary (254). Existing rejection/output-preservation, writer
bounds-trap and example checks remained enabled. Meson ran the optimized Python
mode with `--no-rebuild`, using a verified copy of the existing PR51 compiler:
`e97baada523ec30ac49e7f3e4c17b13ae6d30b79d9f157f07f9a87c2bd4ab8ba`.
All 18 C++ compiler inputs matched that base; no compiler target was rebuilt.
GCC 14.2, GNU binutils 2.44, Python 3.12.14 and Meson 1.12.1 were recorded.
The 678-file tested source and compiler hashes held through the corrected run.

The initial attempt failed at compile admission before any case ran: the
block-I/O module imported `storage.sector` but also needed `storage.block` for
Sector512's recursive public-signature visibility closure. Adding the direct
block import fixed admission without changing compiler policy. The original
failure log and source hashes are retained separately from the successful replay.
The corrected outer process exited zero and its temporary children were reaped.

Independent final source and evidence review accepted this focused scope. These
are focused hosted library results, not a full aggregate or kernel qualification. Registration in the full
compiler recipe does not claim that aggregate has been rerun.
