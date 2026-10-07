# One record value and one sector-device contract

## Current runtime-owned device

The single `RamSectorDevice` now consumes a runtime-sized `OwnedBytes` allocation
under explicit `ByteRegion` authority. Its count comes only from successful
whole-sector storage. Devices move explicitly; `Sector512` and `SectorReadResult`
remain independent copied values. Successful empty storage is valid, while
failed/partial-sector allocations propagate `invalid_source`. Range precedes
readonly and offset multiplication. Valid visibility flush remains volatile;
durability and invalid-source flush are unsupported. See the updated
[I/O contract](block-io-contract.md).

This replaces the inline-sector representation below without adding a second
backend. Two direction-specific byte-copy loops now bridge runtime-owned bytes
and copied sectors; no safe mutable view exists to merge that boundary. Fresh
compiler admission and both Python modes passed the focused 57-case I/O and
121-case XFS runners, their strict rejections and six device-example invocations.
The [current I/O contract](block-io-contract.md#example-and-validation-scope)
records compiler identities and the preserved/fixed diagnostic-location failure.
The historical compiler digest, counts and results below apply only to the
original inline-sector source and are not evidence for this migration.

## Historical inline-sector consolidation

The dependency is removal of parallel owned-record and RAM-device APIs before
adding another storage source. The acceptance gate is a fresh focused replay of
the migrated record, sector, I/O and XFS consumers on the reviewed owned-field
compiler, plus independent source/evidence review. This is an intentional API
break: no aliases, adapters or deprecated production wrappers preserve the old
stack. The new borrowed multi-sector window remains paused.

### Historical concrete shape

- `std.binary_buffer`: `BinaryBuffer64` owns exactly 64 u8 bytes and provides
  byte access plus the existing LE/BE16/32/64 writes. It is a serialization value,
  with no geometry, device index, flush or shared identity.
- `storage.sector`: `Sector512` owns exactly 512 bytes. Its byte operations use
  the existing standard byte read/write vocabulary. Its `read_record` and
  `write_record` methods transfer `BinaryBuffer64` directly. A copied
  `RecordReadResult` is 72 bytes; its payload is zero-masked on read failure.
- `storage.block_io`: the single device contract retains `SectorGeometry`,
  `SectorReadResult` (520 bytes), `SectorIoStatus`, and explicit volatile versus
  unsupported-durability flush outcomes.
- `storage.ram_sector`: `RamSectorDevice` owns a `Sector512` plus one readonly
  flag (520 bytes). It copies an explicit initial sector in its constructor,
  returns whole owned snapshots and replaces its payload through checked
  owned-field assignment after range/readonly preflight.

Read bounds use `std::ByteReadStatus` and `ByteReadResult`; the byte getter returns
u64 values in 0..255. Buffer/encoding writes use `std::ByteWriteStatus` so numeric
width errors remain expressible. Device I/O retains `SectorIoStatus` and its
readonly failure. Durability remains its own outcome domain. There is no bloated
universal error enum and no competing `BlockStatus` vocabulary.

Template capacities remain 1..64; copied values remain capped at 512 u8 leaves,
513 total leaves and 520 bytes. No `Buffer<512>` specialization, heap, mutable
span or generic device framework is added. The only compiler dependency is the
separately reviewed direct owned-class-field assignment; no default-construction
or borrowed-field exception is presumed.

### Historical API removals and transfers

Removed, without aliases:

- `storage.block`: `Block64`, `BlockStatus`, `BlockByteResult`, `BlockReadResult`
- `storage.block_codec`: `block_from_writer` and `writer_from_block`
- `storage.ram_blocks`: `RamBlockStore`, `BlockGeometry`, `BlockFlushStatus`
- `std.binary_writer`: replaced by the actual moved `BinaryBuffer64`
  implementation, not a wrapper around a second byte representation

Six transfer operations disappear:

1. Writer to packed Block64 conversion
2. Packed Block64 to writer conversion
3. Four-record RAM read unpacking
4. Four-record RAM write packing
5. RAM-sector array to Sector512 copying
6. Sector512 to RAM-sector array copying

The first four disappear with their redundant representation/backend. The last
two become ordinary checked owned-value copies, with no handwritten byte loop.
This is source and API simplification, not a measured performance claim.

Three necessary transfers remain as explicit boundaries:

- `Sector512.read_record`: one checked 64-byte extraction primitive
- `Sector512.write_record`: one checked 64-byte replacement primitive
- XFS's owned-sector to local readonly-parser array bridge

The record primitives are shared by all record consumers. Full-range preflight
precedes every store, and their copied arguments/results retain snapshot semantics.
The parser bridge remains because the language does not expose a borrowed view
of a private owned array or return a builtin array. Direct owned-field mutation
does not grant either capability. Removing that boundary requires a separate
checked ownership/lifetime contract; another ad hoc wrapper does not solve it.

### Historical consumer migration

The sole end-to-end device example is `library/examples/ram_sector_record.au`.
It writes a `BinaryBuffer64` header/trailer directly into a sector, constructs the
RAM device from that owned value, and validates retained snapshots after later
writes. The old four-record and duplicate offline-sector examples are removed.
The standard buffer example remains a distinct serialization-only demonstration.

`fs.xfs_sector` retains its I/O/metadata/capacity ordering and copied-result API.
Its byte copy now uses the common `std::ByteReadResult`; its test fixture devices
use explicit initial sectors. A real XFS header in one RAM sector still fails the
capacity check. No mount or new file-data interpretation is introduced.

### Historical safety-test migration

- `binary_buffer.py`: 542 case definitions, ten rejections, three checked `at`
  traps and one example. Retains the 278 original encoding cases and migrates
  the exhaustive record-byte permutations, recoverable reads and independent
  copies from the removed block-value runner.
- `sector.py`: 46 case definitions and nine rejections. Retains every sector byte,
  every one of 449 record offsets, full failure/neighbor preservation, copies,
  overlap and codec tests. New record-report checks cover the removed result's
  72-byte layout, masking and argument/return copying. A four-record sequence
  verifies shared sector placement and unchanged unused bytes.
- `block_io.py`: 38 cases, 13 rejections and the single device example retain
  full-sector transport, constructor snapshots, readonly/range order, cloned
  geometry and both flush modes. The old four-record device's obsolete geometry
  and flush operations are not artificially retained.
- `xfs_sector.py`: all 110 cases/five rejections retain error-domain separation,
  independent geometry expectations, full-width capacity and failure masking.

`block_value.py` and `ram_blocks.py` and their Make/Meson registrations are removed.
The binary writer runner is moved and expanded under the buffer name. Relevant
byte-codec and binary-reader dependencies remain selected. Retained historical
contracts/results live under `docs/history`; they qualify only their original
source and do not establish results for this consolidation.

### Historical focused verification — 2026-10-07

Independent source review accepted the API deletion/migration and composition on
PR55 plus the reviewed owned-field compiler. Migration and review corrected inherited negative-test isolation problems:
bare borrowing calls, class-call binding contexts and a const receiver that
masked a privacy check. Current registration
counts and historical qualification wording were checked separately.

The five changed runners passed in normal Python, then passed again through
Meson in optimized Python with two workers:

- Binary buffer: 542 cases, ten rejections, three exact bounds traps and example
- Sector: 46 cases and nine rejections
- Device I/O: 38 cases, 13 rejections and the sole device example
- XFS sector: 110 cases and five rejections
- Complete owned-mutation source runner: 50 reported cases, 32 rejection checks
  and two exact traps, including its migrated real-sector consumer

All seven selected Meson runners passed; the other two were complete byte-codec
(789 cases/19 rejections, example and layout checks) and storage-binary dependency
runners. This is a selected seven-runner result, not the complete 24-test `dev`
suite or full native aggregate. Existing temporary-product semantics are retained;
no new per-case native archive is claimed.

The reused compiler is
`f44ecd5ae4cad266ca8cff62d42cd3970c61a4bcc04e025cd68e2b5f0656cdbd`.
All 18 compiler-directory C++ source/header files matched its reviewed source.
The compiler was not rebuilt; Meson used a checked copy with `--no-rebuild`.
GCC 14.2, binutils 2.44, Python 3.12.14 and Meson 1.12.1 were used.

The actual outer process exited zero. All 703 frozen source hashes and both
compiler copies remained unchanged through completion. There were no extra or
missing source files, no owned temporary children and no remaining test processes.
Independent final evidence review accepted these results. Documentation-only final wording
and exact merged-main composition do not borrow new execution credit.

No full aggregate, new sanitizer, guest, real device, filesystem mount,
persistence, performance or hardware qualification is implied. The borrowed
multi-sector source remains a separate, unimplemented next increment.
