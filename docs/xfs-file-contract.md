# Bounded XFS written-file sector candidate

The bounded reader passes its focused native gate on the existing compiler.
All 34 sectors of the preserved 17,003-byte payload are read through copied
readonly windows, including final-sector tail zeroing. Independent source and
retained-evidence review accepted the focused results. This does not establish
a general XFS mount or allocation ownership. The supported metadata profile and caller-supplied source limits
below are part of the operation's contract.

## Operations

`fs::XfsFileRequest(inode_number, file_sector)` holds a u64 inode number and exact
i64 file-relative sector index. `plan_xfs_v5_512_file_sector(source, superblock,
inode, request)` returns copied status, issue, file facts and a source-sector
coordinate. `read_xfs_v5_512_file_sector(source, superblock, inode, request,
window, base_lba)` validates those same metadata inputs and invokes
`storage::read_sector_window` itself. It returns the existing `SectorReadResult`.
It does not accept a substituted public plan as authority for a later read.

The caller supplies matching immutable snapshots, source geometry and absolute
window base. None of these values carries source identity. The reported source
capacity is a supplied claim, distinct from the actual 1–8-sector window size.
Matching embedded identifiers and CRCs do not establish provenance. Public
constructors can fabricate reports; reports are not validation certificates.

A successful read owns all 512 bytes. For the final partial sector, only the
reported `valid_bytes` belong to the file; remaining bytes are overwritten with
zero in the copied payload. The source window is unchanged. Missing sectors
remain `out_of_range`, never silently generated file bytes. Metadata rejection
maps to `invalid_source`; end/invalid index map to `out_of_range`. Window I/O
failure passes through. Call the planner separately for precise metadata issues.

No new storage representation, backend, compiler limit, heap or escaping view
is introduced. The report is 72 bytes, request 16 bytes, facts 40 bytes and sector
coordinate 16 bytes; the existing sector result remains 520 bytes.

## Deliberately narrow profile

First run the complete existing v5/512-byte superblock geometry validator, then
compare claimed data sectors to supplied capacity. Require 512-byte inodes and
inode numbers 1..0xffffffff (larger numbers are unsupported, zero is invalid). Decode inode AG/block/slot and exclude AG headers,
encoded gaps, actual final-AG tail and internal log. Require exactly 512 input
inode bytes before any inode byte access.

The v3 inode requires magic 0x494e, CRC32C over all 512 bytes with bytes 100..103
zeroed, embedded number equal to the request and UUID equal to the superblock.
Only BIGTIME/NREXT64 flags2 are admitted, each requiring its superblock feature.
Only PREALLOC is allowed in legacy flags. PREALLOC does not mark extent bytes
unwritten. Mode must be regular, data format extents, forkoff zero and attribute
format extents; extent-size/cow hints are excluded. Nonzero metadata type, absent
or excessive link count, DM fields, count-layout padding, reserved bytes 132..143
or an unlinked-list value other than 0xffffffff fail the core checks. Timestamps,
IDs, permission bits, generation/change count and LSN remain opaque.

With NREXT64, data count is BE64 at 24 and bytes 76..81 are zero. Otherwise data
count is BE32 at 76, bytes 24..31 and 80..81 are zero. Counts over the 21 records
that fit this inode are malformed; other counts except one are unsupported.
Zero size is unsupported; sizes above signed-i64 maximum are malformed.

The sole BMBT record begins at 176: state bit 127, logical start 126..73,
encoded physical start 72..21, block count 20..0. Require written state, logical
start zero, positive count and nblocks equal to count. A count shorter than the
file's rounded-up block requirement is malformed; extra allocated blocks are
unsupported trailing allocation. Unused bytes after the declared record remain
opaque but CRC-covered, consistent with the inode's extent-count boundary.
A declared second extent is rejected before selecting any file sector.

The full physical extent must fit one actual AG, avoid its first four sectors
and avoid the internal log. Reject the full delayed-allocation encoded band
[2^52−2^17, 2^52), including an extent that begins below and intersects it. Check
subtractions before multiplication. Admitted geometry proves all byte arithmetic
fits u64; every resulting 512-byte LBA is below 2^55 and safely converts to i64.
Use `(size - 1) / block_bytes + 1` for positive-size rounding, with no overflowing
addition. File-relative index is checked before multiplying by 512.

Complete metadata validation precedes negative, end or excessive index handling.
Index equal to the rounded-up file sector count yields `end`; larger or negative
indices yield `invalid_index`. Facts are available only for `ready`/`end`, and
sector coordinates only for `ready`, including for caller-constructed reports.
This distinguishes supported metadata from a selectable sector.

## Reference and fixture

Format facts were checked against Linux v6.16 commit
`038d61fd642278bab63ee8ef722c50d10ab01e8f`,
[`xfs_format.h`](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_format.h)
and
[`xfs_bmap_btree.c`](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_bmap_btree.c).
The original Aurora implementation copies no upstream code. The recovered
interrupted parser and its prior execution claims are not used as acceptance.

The [fixture](../fixtures/xfs-file/README.md) preserves exact historical producer
bytes, matched to the recovered complete image in a separate read-only streaming
recovery. No fresh mkfs, mount, tool installation or physical device is needed.
CRC-repaired test mutations are synthetic and never presented as producer output.

## Limits

This is a bounded offline sector consumer. It does not prove allocation ownership,
inode allocation, absence of overlap with other metadata/files, log cleanliness,
snapshot consistency, whole-filesystem integrity, mountability or hardware safety.
Btrees, empty files, holes, multiple extents, unwritten allocation, attributes and
path traversal remain excluded. Root-entry tests may compose the existing indexed
root API; they do not establish a general filesystem service.


## Focused validation — 2026-10-07

The new runner passes 267 native cases and eight compiler-rejection fixtures in
normal and optimized Python. It reads and byte-compares every sector of the
actual 17,003-byte payload and composes the existing indexed root entry with the
first file read. Synthetic cases cover both extent-count layouts, count/type/
flag exclusions, final-byte zeroing with nonzero source tail, complete metadata
precedence, copied reports, maximum extent count at 64KiB blocks, nonzero-AG
inode addresses and an actual one-sector read near the admitted u64 byte bound.
Reserved-band and internal-log intervals include exact allowed adjacency and
one-block intersection cases.

The first compile-only admission failed on missing direct imports in the public
class-type closure. Adding `std.binary_buffer` to the consumer and its test
callers, and `fs.xfs_probe` to the consumer, fixed that admission failure. The
failed log is retained. Fresh compile-only admission then passed all 267/eight
before any generated code was executed; no compiler semantics changed.

The reused qualified compiler is SHA256
`f44ecd5ae4cad266ca8cff62d42cd3970c61a4bcc04e025cd68e2b5f0656cdbd`.
No compiler was rebuilt. The selected Meson run passed `xfs-file`, `sector-window`
and `xfs-sector` with two workers; these three runners are not the complete
bytes/dev suite. The reader's normal replay passed separately.
Complete optimized dependency runs passed 586 geometry headers / 25,198 raw
observations, 40 layout observations, eight copied-report cases, 17 rejections
and 51 detected mutations (24 redundant guards remain source audits); 203 root
lookup cases; 77 root API observations / 12 negatives; and 912 indexed-root cases
/ five rejections. The first compile-only admission failure does not count as
native execution.

The actual focused outer process exited zero. All 723 frozen source hashes and
both invocation compiler copies held through completion. Owned outputs were
266,461,184 bytes under the 1GiB invocation cap; temporary storage was empty.
The existing new-reader runner retains source and logs, not a complete per-case
native product corpus. No new sanitizer, full native aggregate, kernel, emulator,
performance or hardware qualification is implied.

Run `python3 -B tests/compiler/xfs_file.py build/aurorac`, or select `xfs-file`
in Meson's `bytes` suite. `--source-only` generates/checks the independent model
without invoking a compiler and is not native acceptance.
