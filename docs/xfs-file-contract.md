# Bounded XFS inline-extent file sectors

The bounded inline-extent reader passed its focused native gate on the retained
qualified compiler. Both Python modes passed all 841 cases and 11 rejections,
including every sector of the authentic sparse and written fixtures. Independent
source and retained-evidence review accepted the bounded implementation and final claims.
The historical single-written-extent result below remains scoped to PR59.

## Operations and copied reports

`fs::XfsFileRequest(inode_number, file_sector)` holds a u64 inode number and exact
i64 file-relative sector index. `plan_xfs_v5_512_file_sector(source, superblock,
inode, request)` returns copied status, issue, facts and mapping information.
`read_xfs_v5_512_file_sector(source, superblock, inode, request, window, base_lba)`
revalidates those metadata inputs and returns the existing owned
`storage::SectorReadResult`. It never accepts a public plan as authority to read.

`XfsFileFacts` exposes `inode_number()`, `inode_lba()`, `size_bytes()`,
`extent_count()` and `allocated_blocks()`. The latter is the sum of all declared
written and unwritten record counts. This deliberately replaces the earlier
single-extent `first_data_lba()` and `extent_blocks()` accessors. There are no
compatibility wrappers or duplicate storage representations.

`XfsFileSector.kind()` returns `none`, `written`, `hole` or `unwritten` from
`XfsFileSectorKind`. `source_lba()` is nonzero only for a written mapping and is
masked to zero for every other kind, including caller-fabricated coordinates.
`valid_bytes()` is 1..512 for an admitted file sector and zero for kind `none`.
Ready/end reports expose facts; only ready exposes a coordinate. Other reports
mask their facts and coordinate, even when constructed with nonzero inputs.
These freely constructible reports remain data, not validation certificates.

Native layout checks confirm bounded inline values: request 16, facts 40,
coordinate 24, report 80 bytes; the existing sector result remains 520 bytes.

## Profile admission and complete extent validation

Run the existing v5/512-byte superblock geometry validator, then compare its
claimed data sectors with supplied source capacity. Require 512-byte inodes and
inode numbers 1..0xffffffff; zero is invalid and larger numbers unsupported.
Decode inode AG/block/slot and exclude AG headers, encoded gaps, actual final-AG
tail and internal log. Require exactly 512 input inode bytes before byte access.

The v3 inode requires magic 0x494e, CRC32C over all 512 bytes with bytes 100..103
zeroed, embedded number equal to the request and UUID equal to the superblock.
Only BIGTIME/NREXT64 flags2 are admitted, each requiring its superblock feature.
Only PREALLOC is allowed in legacy flags; PREALLOC does not itself mark a record
unwritten. Mode must be regular, data format extents, forkoff zero and attribute
format extents. Extent-size/cow hints are excluded. Nonzero metadata type,
absent/excessive link count, DM fields, count-layout padding, reserved bytes
132..143 or an unlinked-list value other than 0xffffffff fail the core checks.
Timestamps, IDs, permissions, generation/change count and LSN remain opaque.

With NREXT64, data extent count is BE64 at 24 and bytes 76..81 are zero. Otherwise
it is BE32 at 76, bytes 24..31 and 80..81 are zero. Admit 0..21 records, the complete
capacity of the 336-byte attribute-free data fork at 176..511. Larger declared
counts are `invalid_inode/extent_count`. Undeclared fork bytes stay opaque but
CRC-covered. Positive-size zero-record files are fully sparse and must have
nblocks zero. Empty files remain `unsupported_profile/file_size`; sizes above
signed-i64 maximum are `invalid_inode/file_size`.

Each 16-byte BMBT record encodes state bit 127, logical start 126..73, physical
start 72..21 and block count 20..0. Decode and validate every declared record before
handling any request index. Positive counts are required. Each logical start
must be at least the previous logical end: overlap, duplicate starts and reverse
order are `invalid_extent/file_offset`; adjacency and gaps are valid. All count
sums must equal di_nblocks, otherwise `invalid_extent/block_count`.

Every entire physical extent, including unselected and unwritten records, must
fit one actual AG, avoid its first four sectors and avoid the internal log.
Reject the complete delayed-allocation encoded band [2^52-2^17,2^52), including
an extent starting below it and intersecting it. Invalid ranges yield
`invalid_extent/extent_address`. No record is accepted merely because its bytes
will be returned as zeros or because a preceding record satisfies the request.

Trailing allocation deliberately remains unsupported. After record validation
and the nblocks sum check, any logical end above ceil(EOF/block_bytes) yields
`unsupported_profile/trailing_allocation`, for either extent state. This is a
narrow local profile, not a claim that XFS preallocation is malformed. A final
allocated partial block is admitted; holes after the last extent within EOF are
also admitted. Btrees, attributes and hint/feature exclusions stay unsupported.

Validation order is geometry/capacity, inode address/length/core, record count,
file size, then per-record count/order/physical interval in record order,
nblocks sum, trailing allocation, and finally index classification. Thus a later
malformed physical extent outranks earlier unsupported trailing allocation.
An earlier selected mapping never bypasses a later record's checks.

## Mapping and owned bytes

Only after full metadata admission, a negative index or index beyond the rounded
file-sector count yields `invalid_index`; equality yields `end`. End and invalid
index map to `SectorIoStatus::out_of_range`, metadata rejection to
`invalid_source`. This precedence also applies to holes and unwritten targets.

For a ready index, select its filesystem block from the validated intervals.
An absent record means `hole`; a state-one record means `unwritten`. Both return
success with a newly zero-initialized owned `Sector512`, without inspecting the
window or invoking the shared window reader. Their coordinate has LBA zero and
the same EOF-bounded valid-byte count as a written mapping. An empty, malformed,
unrelated or poisoned window cannot supply bytes for these mappings. No zero
sector is returned successfully at or beyond EOF.

A written mapping computes its LBA inside the selected physical interval and
uses the one existing `storage::read_sector_window` copy boundary. A missing
written sector remains an I/O failure, never a synthetic hole. Window failures
pass through. In the final partial sector, overwrite bytes after `valid_bytes`
with zero in the owned copy; leave the source unchanged. No additional backend,
representation-conversion loop, heap or escaping view is introduced.

The caller still supplies matching immutable snapshots, source capacity and an
absolute window base. These values carry no source identity. Claimed capacity
is distinct from the supplied 1..8-sector window. Embedded IDs and CRCs do not
establish provenance, snapshot consistency or allocation ownership.

## Arithmetic and bounded work

Count is bounded before calculating 176+16*i, so every record fits the inode.
A 54-bit logical start plus 21-bit length is below 2^55; summing at most 21 lengths
also fits u64. Validate logical intervals in block units, without multiplying
untrusted logical offsets by block size. Round positive size with
`(size - 1) / unit + 1`. File-relative index is admitted before multiplying by 512.

The second bounded scan maps an admitted index by division/remainder of sectors
per block. A selected displacement is below its validated extent length. The
existing subtraction-first physical address guards prove every byte interval
fits u64; resulting LBAs are below 2^55 and convert exactly to i64. At most two
21-record scans run; no work scales with file length, AG count or nblocks.

## References and evidence

Format and read semantics were checked against Linux v6.16 commit
`038d61fd642278bab63ee8ef722c50d10ab01e8f`:

- [xfs_format.h](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_format.h): inode layout, BMBT fields and delayed-allocation band.
- [xfs_bmap_btree.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_bmap_btree.c): record decode and ordered half-open logical intervals.
- [xfs_inode_fork.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_inode_fork.c): inline fork capacity and extent validation.
- [xfs_iomap.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/xfs_iomap.c) and [buffered-io.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/iomap/buffered-io.c): hole/unwritten mappings return zeros before disk-read construction.

The original Aurora implementation copies no upstream code. Preserved source
identities are listed in [the reference record](xfs-file-reference-provenance.json).
The interrupted historical parser and execution claims are not acceptance.

The [fixtures](../fixtures/xfs-file/README.md) preserve producer bytes from the
historical disposable regular image. Fresh read-only streaming revalidation
matched all 11 saved image slices and the full 335,544,320-byte decompressed digest.
No expanded image, mount, host device, new mkfs or tool installation was used.
The unchanged 17,003-byte single-extent payload supplies 34 sector regressions.
The authentic 32,769-byte three-extent sparse file supplies 65 complete sector
comparisons, including its one-byte EOF sector. Authentic unwritten inode 133
has EOF zero and supplies only an unchanged unsupported-empty regression.
Within-EOF unwritten and mixed-record cases are explicitly synthetic CRC-correct
mutations; they are never represented as real-image output.

## Test scope and limits

The existing runner extends its independent bigint model and descriptor-based
mapping anchors. It covers both extent count layouts, all 21 records, overlaps,
reverse order, later-record rejection before earlier selection, full-range
unwritten physical validation, sparse/unwritten EOF, poisoned/invalid windows,
high logical offsets, maximum signed file size, maximum lengths across 21
records, high physical LBAs, copied/masked reports and exact API types.

Run `python3 -B tests/compiler/xfs_file.py build/aurorac`, or select `xfs-file`
in Meson's `bytes` suite. `--source-only` checks the Python model and generated
inputs without invoking a compiler; it is not native acceptance. The focused
native results below qualify the tested source; they do not establish a full aggregate.

This remains an offline bounded consumer. It does not establish inode
allocation, physical allocation ownership/non-overlap, absence of overlap with
other metadata/files, log cleanliness, whole-filesystem integrity, mountability
or hardware safety. Cross-record physical ownership is not independently
verified. No filesystem service, Btree/path traversal, empty-file support,
write/replay/recovery, compiler semantics, performance, full aggregate,
sanitizer, kernel, emulator or physical-device qualification is added.


## Focused inline-extent validation — 2026-10-07

On the independently source-reviewed implementation, compile-only admission
passed all 841 positive cases and 11 compiler-rejection fixtures before any new
Aurora program was executed. The existing runner then passed 841 native cases
and 11 rejections in normal Python, and again in optimized Python. Rejection
controls preserve absent and preexisting output files. All returned sector bytes,
source immutability, report/value copies and new 80/24-byte layouts were checked.

The existing direct dependency runners passed:

- Sector window: 110 cases / nine rejections.
- Owned sector: 46 cases / nine rejections.
- Block I/O: 39 cases / 13 rejections and its example.
- XFS sector: 121 cases / five rejections.
- Geometry: 586 headers / 25,198 raw observations; 40 layout observations,
  eight copied-report cases, 17 rejections and 51 detected mutation regressions.
  The 24 redundant guards remain source audits, not claimed detected mutations.
- Root lookup: 203 cases; root API: 77 observations / 12 negatives;
  indexed root: 912 cases / five rejections.

The original serial outer session 67089 exited zero after all 11 phases. All
771 source file hashes/modes and the exact compiler held through completion;
native-source manifest SHA256 is
`b8aebbee6b7cf15d150f5922b49acb01f3ec46164b02d3b47c19217ee6e190f3`.
The retained qualified PR66/67 compiler SHA256 is
`ac24f09edbb6298e6be7cd23bb235434acd326c627041e3ed812f3c334b2a252`;
its 16-file project include closure matched the accepted tested source. No
compiler was rebuilt. Recorded host tools remained unchanged. The last observed
owned outputs were 271,134,720 bytes under the 1 GiB invocation limit, and its
temporary directory was empty. Disk checks were between-phase observations,
not a hard quota or proof of peak storage use.

One initial source-model fixture incorrectly combined 64 KiB blocks with an
oversized allocation group. Its explicit model anchor failed. The corrected
synthetic fixture uses valid geometry and spreads the 21 maximum-length records
across AG0, AG1 and AG3. No production guard was relaxed and no compiler ran in
that failed source-only preparation. Both corrected source-only modes passed.

Retained logs, compile-only sources and dependency artifacts support these
results. The unchanged reader/window batcher recycles native outputs, so no
complete per-case native product archive is claimed for those runners. These
are direct focused runner passes, not a Meson suite or full native aggregate.
No new sanitizer, kernel/emulator, mount, hardware or allocation-ownership
qualification is implied. The final documentation overlay does not claim a
second execution of changed code.


## Historical PR59 single-written-extent validation — 2026-10-07

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
