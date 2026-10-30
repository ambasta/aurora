# Clean nested shortform XFS tree

`clean.img.xz` contains a genuine 512 MiB XFS filesystem created by Linux
6.12.107 x86_64 with xfsprogs 6.13.0. It retains the original 4 KiB block,
512-byte inode/sector, four-AG, 16,384-block log geometry. No metadata bytes
were synthesized or edited after Linux unmounted it. `hashes.json` records
both archive and full expanded logical-image hashes; materialize it sparsely.

The source was the reserved-name clean mounted-writer reference image,
SHA256 `a764493bba9ea4501ed0b8c73bf5af50c191bd22b4ef4578fc36c259f53a4406`.
Its root `/hello` (inode 99) and `/.aurora-stage` (inode 100) remain 64-byte
regular files. In a disposable, networkless QEMU 10.0.13 TCG guest, Linux
mounted the copy with `noatime,nodiratime,logbufs=2,logbsize=32k`, created
`s`, `s/deep`, `empty`, and `s/.aurora-stage`, then copied exactly the six
files recorded in `files.json`. After checking their SHA256 values, Linux
synced and cleanly unmounted. A read-only remount checked every payload hash
again and recorded inode identity, size and link count before clean shutdown.
The source image's full hash remained unchanged. Offline `xfs_repair -n`
completed successfully; `xfs_db -r` verified each directory's local format,
CRC, inode identity and parent. `directories.json` records those reference
facts; inode numbers equal their sector LBAs only for this fixture geometry.

Linux set the legacy ATTR-present marker and reserved an empty attribute fork
(`forkoff=24`, extent format, zero attribute extents) in newly created inodes.
The read-only parsers validate its boundary and zero tail; this is not support
for nonempty attributes. Strict writer/recovery admission still rejects it.
The genuine superblock counters are `icount=256`, `ifree=241`, unlike the fixed
mounted-writer profile's `64/59`.

This image exercises nested, cross-AG and empty directories, sibling module
imports, a standalone program, and hidden `.aurora-stage` components both as
a directory and a file. It is intentionally outside the fixed two-file
mounted-writer allocation profile. Read-only traversal must not confer write
or recovery authority. Production checks use the existing graphics/NVMe
runner with `--xfs-nested --xfs-image <expanded-image>` and its unchanged
command/framebuffer, source hash and terminal cleanup checks.

The sibling module sources were checked with the current hosted compiler
before generating this image. The image was regenerated through the same Linux
recipe after correcting the namespace terminator in `s/b.au` (now 87 bytes);
no filesystem metadata or payload sectors were patched offline.

The Linux-generated fixture is the reference, not Aurora output. Directory
parser mutations, if used by component tests, are explicitly negative cases;
they are not claimed to be Linux-created filesystems.
