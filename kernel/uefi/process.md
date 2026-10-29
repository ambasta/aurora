# Process image: boot volume, frames and export

`uefi/process-fixture` is the UEFI test image for running programs as
processes. It carries the boot volume, a physical frame allocator over all
usable conventional memory, kernel mappings beyond the arena's fixed table pages
and a serial export of volume files. It does not run user processes yet. Other
images and `uefi/production` do not change; their image bytes are identical
with and without this image.

The decisions are Aurora (`examples/kernel-process.au` over
`kernel/policies/kernel/{memory_map,frames,boot_volume,export_text}.au`),
reached through the private bridge `process-entry.S`. The build checks every
argument record, result class and enum against the compiler's ABI facts
(`PROCESS_POLICY_ABI` in `scripts/meson_aurora_assembly.py`). Trusted C++ keeps
only what the kernel bridge cannot express yet: firmware file reads in the
loader, page-table writes, the frame-record storage and free-list head, the
range table, and serial output. Each C++ decoder rejects a result outside its
closed encoding before using it.

## Handoff

Version 8 is version 1 (no RSDP, no record word) plus the loader fixture word at
128, the boot volume's page address at 136 and its byte length at 144 (header
152). `Handoff::valid` checks the words structurally: nonzero page address,
1..64 MiB, below the 52-bit limit. Only the final memory map grants the pages.
The kernel admits the copied map in Aurora (`map_admit`: version 1, stride
40..256 in multiples of 8, at most 512 descriptors, aligned nonempty ranges
below 2^52, no overlap). Every type is admitted, including the OEM and OS
ranges above 15, but only conventional memory is ever used. `volume_grant` then requires the volume
pages to lie wholly inside one non-runtime EfiLoaderData descriptor and outside
the arena. The loader also reserves the arena-owned window path
(`PageTables::prepare_window`). The boot verifier admits it because it has no
leaves.

## Boot volume

The loader opens `\aurora\volume` on its own ESP through the loaded image's
`EFI_SIMPLE_FILE_SYSTEM_PROTOCOL`. It requires a regular file of 1 byte to
64 MiB and reads it into fresh EfiLoaderData pages. It zeroes the last page's
tail and closes both handles before the final map. The format has one canonical
layout, little-endian (`scripts/kernel_volume.py` writes it):

- header, 64 bytes: magic `AURORAVL`, version 1, header bytes 64, entry count
  (at most 4096), entry bytes 32, names offset (`64 + 32 * count`), names bytes,
  data offset (names end rounded up to 8), data bytes (the rest of the volume),
  CRC32C of bytes 0..56 then 64..end, and a zero reserved word;
- entries in strictly increasing bytewise path order: name offset, name length
  (1..255), zero flags, data offset, size. Names and data follow index order
  without gaps, with each file padded to 8 bytes with zeros;
- paths are relative components of `[A-Za-z0-9._-]` joined by `/`, never empty,
  `.` or `..`. No path may also be the directory of another (`a` with `a/b`):
  such a volume is rejected as `nesting`.

`volume_admit` returns the first violated rule as a closed verdict.
`volume_find` binary-searches an admitted volume and `volume_entry` returns an
entry's absolute extent. The C++ wrapper also checks that extent lies inside the
volume. The kernel maps the volume read-only/NX and admits it before using it.

## Frames

Usable frames come from conventional descriptors without the runtime or
specific-purpose (`EFI_MEMORY_SP`, soft-reserved as Linux treats it) attribute,
above the first MiB (reserved, as Linux reserves it on x86). Each
must be disjoint from the arena and the volume (`frame_range`) and below the
CPU's physical width. Boot-services memory is not reclaimed. Ranges are sorted
and indexed densely. Each frame has one 8-byte record: bits 0..3 state (free,
allocated, kernel, retired), 4..31 generation, 32..63 owner, or for a free frame
its free-list link (next index + 1). `frame_transition` decides every record
change: initialize free or kernel, allocate, or release with the holder's owner
and generation. A release with a stale generation, the wrong owner, a kernel
owner, a kernel, free or retired frame, or a noncanonical record is rejected with
its reason and leaves the record unchanged. A generation that would wrap retires
the frame. Owners 1..15 are kernel uses (1 tables, 2 metadata); allocation
starts at 16. `Table::audit` walks every record and the free list.

## Kernel space

The window table at `0xffff800000000000` lives in the arena. Slot 0 is the
transient frame window, unmapped before reuse. Slot 1 is an absent guard, and
slots 2.. are RW/NX views of dynamic table pages. Root slot 384 (`0xffffc00000000000`) maps the frame
metadata RW/NX at its base and the volume read-only/NX at +1 GiB. Its tables
come from the lowest frame indices, followed by the metadata pages; all are kernel
frames. `KernelSpace::verify` walks the complete extension. Every entry must be
exact, every table and metadata page must be a kernel frame of its owner, volume
pages must lie outside the inventory, the window must be closed and the other
root entries must be the boot-verified ones. It runs after construction and after
the frame cases. The baseline row then checks that it rejects four single-entry
edits: a user bit on a table link, an executable metadata leaf, a writable volume
leaf and an open window.

## Export

```
AURORA_EXPORT_BEGIN: path=<volume path> bytes=<n>
AURORA_EXPORT_DATA: <padded base64 of the next 57 bytes, or fewer on the last line>
AURORA_EXPORT_END: path=<volume path> lines=<k>
```

`base64_group` encodes each group of 3 bytes. `kernel_uefi_oracle.exports`
decodes the records and rejects stray, truncated, misframed or duplicate ones.

## Tests

`kernel-process` (merge suite) links the generated policies with
`frames.hpp`. Its memory-map, inventory, record and policy cases are
`tests/kernel-process/frames.cases`. The volume cases are built by the writer
from `volumes.cases`; each edits one field of a canonical volume. Verdicts are
compared with the golden files beside them. The `guest-process` family boots the
image's four rows (`meson test --suite guest-process`, about 2.5 s each on TCG):

- `process-volume` allocates every free frame and writes and reads back a pattern
  and then zero through the window. It checks six misuse rejections, releases
  every frame and audits with zero leaks. It checks that the exit walk rejects the
  four edits above, then exports `examples/host-sort.au`, whose bytes must equal
  the repository file;
- `process-volume-corrupt` boots a volume with an unsorted index and a valid
  checksum (`order`);
- `process-volume-empty` boots an empty file, which the loader rejects;
- `process-volume-map` names the arena as the volume after ExitBootServices
  (`arena`).

Limits:

- one CPU, interrupts disabled, no user processes, no SMAP, no PCID;
- map admission is quadratic over at most 512 descriptors, and boot-services
  memory is not reclaimed;
- the plan stops the boot above about 505 GiB of usable memory (510 table views,
  one metadata PD);
- the physical width comes from CPUID 0x80000008 alone. On Zen with memory
  encryption, CPUID 0x8000001F EBX[11:6] reduces it, which Zen qualification must
  add;
- CRC32C in `std.checksum` is bitwise;
- no physical device is qualified.
