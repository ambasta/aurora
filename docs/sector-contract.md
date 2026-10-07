# Owned 512-byte sectors and copied record windows

The next library dependency after sector-sized compiler values is a checked,
owned sector buffer that reuses the existing binary codecs. The acceptance gate
is hosted native execution against independent complete 512-byte models,
including every valid window offset, copy boundaries and unchanged failures.

Import `storage.sector` and `storage.block` for `storage::Sector512` and its
existing copied result types. A sector owns a private, zero-initialized
`builtin::array<u8,512>` and has exactly 512 canonical storage bytes. Copies,
ordinary function arguments and returned sectors have independent storage.

## API

- `size() const -> i64` returns 512.
- `read_byte(i64 offset) const -> BlockByteResult` reads offsets 0 through 511.
  Other offsets return `out_of_range`; `value_or` returns the caller's fallback.
- `write_byte(i64 offset, u8 value) -> BlockStatus` writes one copied byte at
  offsets 0 through 511, returning `success` or `out_of_range`.
- `read_window(i64 offset) const -> BlockReadResult` copies exactly 64 bytes
  beginning at offsets 0 through 448. Other offsets return `out_of_range`, with
  an all-zero `block_or_zero()` result. A window is an owned `Block64` snapshot;
  neither later sector writes nor extracted-block mutation changes the report.
- `write_window(i64 offset, Block64 block) -> BlockStatus` replaces exactly
  those 64 bytes with a complete input snapshot. Other sector bytes are preserved.

Offsets are byte positions, not record numbers, and need not be aligned.
Every operation checks the full offset range before indexing or changing data.
The upper check uses 448 rather than `offset + 64`, so both signed-i64 endpoints
are recoverable failures. Invalid writes leave all 512 bytes unchanged. An exact
`u8` and a `Block64` contain only valid byte values, so offset rejection is the
only recoverable write failure. Arguments retain ordinary eager evaluation
before method entry. Per-call all-or-nothing failure is not concurrency
atomicity, a multi-call transaction or crash consistency.

## Binary fields without another writer

Use `storage.block_codec` to convert a copied window to/from the existing
`std::BinaryWriter64`. Its LE/BE16/32/64 field writes keep their offset-first,
then value-width validation and unchanged-on-failure contract. Check the writer's
status before submitting a window: a failed field write does not implicitly
cancel a later, explicitly requested window write. Full windows replace all
64 bytes, so read the old window first when preserving other record fields.
Decode local copied bytes with the existing `std.binary` readers.

The [volume-record example](../library/examples/sector_record.au) encodes a
magic, version, sector size/count and root index in a header, plus a signature at
bytes 510 and 511. It decodes retained snapshots after overwriting the sector's
header. The example illustrates a format; it neither implements a filesystem
nor treats class representation as wire layout. No generic framework or duplicate
512-byte writer is added; compiler template capacity remains unchanged.

## Validation and scope

Run `python3 -B tests/compiler/sector.py build/aurorac`, or select `owned-sector`
with Meson's two-worker `bytes` suite. The runner uses the existing native
full-width observation and rejection/output-preservation checks. It covers zero
initialization, all 512 byte positions, all 449 valid read/write windows, signed
boundaries, complete neighbor/failure preservation, independent copies, overlapping
sequences, every field width/endian, privacy/const/type rejections and the example.
Existing block, writer, codec, RAM and reader tests remain dependencies.

This is a hosted library API, not a device. No disk access, flush, persistence,
512-byte hardware atomicity, filesystem mount, mutable view, heap or C interface
is supplied. No multi-sector RAM array is introduced. The sector-value compiler
limits and stack costs still apply. Hosted tests do not admit these values into
the kernel; generated stack protection and kernel stack qualification are separate.

## Focused results — 2026-10-07

All 43 sector cases, nine rejection fixtures and the volume-record example passed
in normal and optimized Python modes. The exhaustive cases traverse all 512 byte
positions and all 449 valid window offsets. All six selected Meson tests passed
with two workers: owned-sector, byte-codec (789 cases), binary-writer (278),
block-value (264), ram-blocks (39) and storage-binary (254). Existing rejection,
exact writer bounds-trap and example checks remained enabled.

The run reused the accepted main compiler (`e97baada523ec30a` SHA256 prefix),
with all 18 C++ source/header inputs unchanged. Meson 1.12.1 configured GCC 14.2
and binutils 2.44; no compiler target was rebuilt. Source and binary hashes held
through execution. No full aggregate, sanitizer or kernel qualification was run.

Two initial fixtures were corrected to respect existing compiler rules: ordinary
function parameters are readonly, and class arguments must be named locals.
Explicit local copies preserved every original byte check without relaxing
compiler or library semantics. A workspace reset lost the earlier raw logs;
the exact executable source hashes were recovered and all focused checks above
were rerun successfully with fresh logs before final review.
