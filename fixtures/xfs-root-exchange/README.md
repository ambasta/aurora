# Root-only XFS name exchange reference

Pinned Linux 6.12.107, xfsprogs 6.13.0 and QEMU 10.0.13 produced this
512 MiB image by exchanging the existing root names `hello` and `pattern`
with `renameat2(RENAME_EXCHANGE)`, fsyncing the directory and shutting down
without unmounting. No allocation, file data mutation or inode reclamation
occurred. Pre-opened readers retained their original bytes. This is a dirty
shutdown after an acknowledged command, not physical power-loss testing.

The log starts at LBA 524328. Its sole live record at offset 13 has six
operations and one root inode 96 item: CORE|DDATA, 176-byte core, 34-byte
shortform directory padded to 36 bytes. The root home remains old on the
dirty image. Linux recovery replayed the transaction, exchanged the two
names and passed `xfs_repair -n`; `root-after.hex` is that exact recovered
512-byte inode, not an Aurora-generated oracle. Names, parent, saved entry
offsets, file types, inode set and all regular-file bytes remain unchanged.

`hashes.json` pins the complete archive, expanded image, captured superblock and both root
sectors. The test expands and verifies the genuine image once, then declares a
synthetic 64-sector ring for focused admission and mutation cases. The component
retains its original CORE full-ring witness; full-geometry root replay is covered
by the actual forward production and reverse process-device guests.
The smaller geometry is not a Linux-valid filesystem and is not used for
whole-device interoperability claims. Mutation CRCs use the shared scalar
CRC32C reference; recovery bytes are compared with the Linux golden.

Linux source correspondence:
- `fs/xfs/libxfs/xfs_dir2.c`: `xfs_dir_exchange_children`.
- `fs/xfs/libxfs/xfs_dir2_sf.c`: `xfs_dir2_sf_replace` logs DDATA.
- `fs/xfs/xfs_inode_item_recover.c`: core conversion and padded DDATA copy.
- `fs/xfs/xfs_file.c`: directory fsync forces the inode log.
All refer to Linux tag `v6.12.107`.
