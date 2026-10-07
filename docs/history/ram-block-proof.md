> Historical checkpoint. These APIs were removed by the
> [storage consolidation](../storage-consolidation.md).

# Owned block-value proof before a RAM block store

This value proof establishes the copied representation needed for the bounded
RAM storage increment. It passed 264 independent native cases and four compile
rejections using the reviewed existing compiler, after source inspection.
The subsequent [RAM store candidate](ram-block-contract.md) has its own API and
validation gate; this proof alone does not establish that backend.

`storage::Block64` owns exactly 64 logical bytes. Its private implementation packs
eight byte positions into each of eight u64 array elements, with the lower byte
position in lower numeric bits. Explicit shifts/masks define this mapping; the
class's physical layout is never exposed or reinterpreted as wire bytes.

`read_byte(i64)` returns a recoverable `BlockByteResult`. `write_byte(i64, u8)`
returns `BlockStatus`. Both reject negative and at-least-64 indices before any
division, shift or array access. Read failures hide stored payloads through
`value_or`; write failures preserve every byte. A valid update changes exactly
one selected byte while preserving the other seven bytes in that word and all
other words. No pointer, mutable view, heap or new compiler feature is needed.

The word representation uses eight scalar leaves, allowing a copied
`BlockReadResult` to contain a status and an independent complete block within
the existing class-value limit. Error `block_or_zero()` masks even fabricated
nonzero payloads. Public report constructors are not provenance certificates.
`storage.block_codec` provides `block_from_writer` and `writer_from_block`,
converting independent values through the existing `BinaryWriter64` byte API.
Packing remains a private detail. The initial class method form exposed the
writer through every composed report's public-signature visibility; the separate
conversion module keeps the core block and RAM APIs independent of that import.

The native proof gate demonstrates all byte positions and word edges,
both signed index endpoints, preservation after failure, upper-bit values,
copied report/argument/result boundaries and zero masking. Observed representation sizes
are 64 bytes for the block and 72 bytes for the status-plus-block report.
Independent byte vectors are primary; roundtrip checks alone are insufficient.

The four-record RAM store builds on this value proof with explicit geometry,
checked whole-block read/write and a volatile-only flush outcome. Its logical
records are 64 bytes, not hardware sectors. Four privately stored blocks fit
within the existing copied-class bound. RAM contents do not survive destruction
or reset; no filesystem, NVMe, crash consistency or durable flush is claimed.
