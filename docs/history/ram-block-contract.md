> Historical checkpoint. These APIs were removed by the
> [storage consolidation](../storage-consolidation.md).

# Four-record volatile RAM block API

This API supplies an Aurora-authored `storage::RamBlockStore` with four
independent, initially zeroed, 64-byte logical blocks. It builds on the owned
`Block64` value proof, which passed 264 native cases and four rejection fixtures.
The full store API, conversions and record example passed focused native tests
and independent source/result review.

Import `storage.block` and `storage.ram_blocks` to use the store and its copied
reports. Import `storage.block_codec` and `std.binary_writer` for the independent
`block_from_writer` / `writer_from_block` conversions. Keeping these helpers
outside the core classes avoids requiring writer types for ordinary RAM reads.

## Geometry and operations

`geometry()` returns copied `BlockGeometry` with `block_size_bytes() == 64` and
`block_count() == 4`. Total logical capacity is 256 bytes. These are small record
blocks, not hardware sectors. Geometry is fixed; no public packing or capacity
parameter is introduced to bypass the language's existing class-value bound.

- `read_block(i64 index) const -> BlockReadResult` returns an independent owned
  snapshot for indices zero through three. Other indices return `out_of_range`;
  `block_or_zero()` then returns an all-zero block.
- `write_block(i64 index, Block64 block) -> BlockStatus` copies a complete block
  into that position. Invalid indices return `out_of_range` before any mutation;
  every old block remains unchanged. Success preserves the other three blocks.
- `flush() const -> BlockFlushStatus` returns `volatile_complete`. Writes are
  already synchronously visible to subsequent reads of this same store value.
  Flush neither changes the contents nor writes to persistent storage.

Negative and too-large indices are checked before word-index multiplication or
array access, including both signed i64 endpoints. After preflight, all fixed
copy-loop indices and shifts fit. Recoverable failures are all-or-nothing per
call; this is not concurrency atomicity, a multi-call transaction or a hardware
fault guarantee. The language has no general concurrent storage memory model.

The store owns private numeric words and exposes only checked byte/block values.
Packing uses explicit shifts and masks; no source address, pointer, physical
layout reinterpretation or foreign serializer is used. Source arguments, read
reports, extracted blocks and whole store copies have independent storage.
Public report/geometry constructors are ordinary values, not I/O capabilities or
proof that metadata was validated.

## Durability and authority

This is volatile local RAM. Contents do not survive destruction or reset.
`volatile_complete` is deliberately distinct from a durable acknowledgement.
There is no delayed writeback, filesystem mount, NVMe queue, device authority,
crash recovery, sector atomicity or DMA claim. No user disk is opened or changed.

The [record example](https://github.com/ambasta/aurora/blob/129d5337da8513ad0f5be92b7700c62482f64293/library/examples/ram_record.au) serializes explicit
big-/little-endian fields with `BinaryWriter64`, writes and reads a RAM block,
then changes the store while decoding the retained copied snapshot with existing
readonly readers. Class representation is never treated as wire layout.

## Acceptance gate

Native tests must check independent complete byte vectors for every block,
zero initialization, all valid indices, both signed index endpoints, unchanged
contents after failed writes, error masking, geometry, volatile flush, overwrites,
copied store/function/report boundaries and the serialization example. Existing
block-value and owned-writer checks remain dependencies. No full system or device
qualification is implied by these focused library tests.

## Focused validation and retained failure

The corrected implementation passed the RAM model gate in normal and Python
optimized modes: 39 native cases, five rejection fixtures and the record example
per run. Each of eight repeated sequences checks all 256 bytes after every write
or flush. The 264-case/four-rejection block-value proof and 278-case/eight-rejection
writer gate also passed, including the writer's three exact bounds traps.

The first attempt failed at compile admission before any RAM case executed:
putting writer conversion in a public Block64 method exposed a transitive writer
type through the read-report signature. The separate `storage.block_codec` module
fixed this without changing compiler rules. Core block tests now import only
`storage.block`; RAM tests need only the block and RAM modules. The original
failed source and diagnostic remain preserved beside the corrected results.

These checks reused the accepted Meson compiler identified by the `993c9456`
SHA256 prefix. All four corrected commands and the outer process exited zero;
source/compiler pins held and owned child cleanup was quiescent. Independent
review checked the frozen source and receipts. Temporary per-case native products
are not retained; evidence is the reviewed runners, manifests and logs.

This is focused library coverage. No full aggregate, sanitizer, emulator, actual
storage device or durability qualification is implied.

## Current-main registration and replay

The final composition preserves PR48's package controls and adds the two block
tests to bytes/dev, giving 17 registered tests. A fresh Meson configuration used
a verified private copy of the current overlay compiler (`fa426eb2` SHA256
prefix). Only the registered `ram-blocks` test ran, with `--no-rebuild`: all
39 cases, five rejection fixtures and the record example passed in 2.96 seconds.
The compiler was reused; neither a fresh compiler build nor the full 17-test
suite is claimed. Its 16-file compiler source closure matched current main.

The test passed and cleanup was quiescent, but the first post-run audit expected
a bare test name instead of Meson's exact suite-qualified identity. Its outer
exit 1 remains preserved. A separate read-only check verified the exact named
result, registration, counts, compiler/source pins and lack of Ninja target
builds. This audit correction did not rerun or relabel the earlier failed attempt.
