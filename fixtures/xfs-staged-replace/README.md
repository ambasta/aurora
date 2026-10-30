# Staged one-block XFS replacement witness

Generated with Linux 6.12.107 x86_64 and xfsprogs 6.13.0 on a disposable
512 MiB image. Both existing regular files occupy one written 4 KiB block.
Linux wrote 777 bytes to staging inode100, fsynced it, exchanged the existing
hello/pattern names, fsynced the directory, and shut down without unmounting.
A separate Linux boot recovered the image, verified the bytes and cleanly
unmounted; xfs_repair -n passed. No allocation changed during replacement.

The live log has inode100 CORE at LSN(1,22), then root96 CORE+LOCAL at
LSN(1,24), with tail22/head26. The sectors and CORE payload are exact
Linux input/output bytes. The stage-only focused case is explicitly synthetic:
it restores the original clean image's stale sectors24/25, excluding the root
transaction while retaining the genuine stage transaction and its Linux golden.

The compressed image contains only generated test files. hashes.json pins
archive, expanded image and decoded hexadecimal fixture bytes. Focused tests
may reduce log geometry to64 sectors; that is not a Linux-valid filesystem.

clean.img.xz is the genuinely clean, two-one-block source used before the
replacement. stage-only.img.xz is a separately captured Linux dirty shutdown
after inode99 grew64→777 and fsync completed, before any directory exchange;
its independent recovery golden is stage-only-inode-after.hex. These are not
inferred from Aurora output. This clean image also exercises the recovery
plan's copied clean snapshot. The later reserved-name source described below
is the input to the bounded mounted-writer formatter.

The mounted-*.hex metadata is copied from the clean renamed
hello/.aurora-stage reference image (Linux 6.12.107), before any Aurora writes.
It supports the deliberately fixed mounted allocation profile: AG0 tree roots
1..4, active AGFL blocks5..8, data blocks9/20, and the complete inode chunk
12..19. Both free-space leaves contain [10,12) and [21,32768); both inode
leaves describe inodes96..159 with only96..100 allocated. Special inodes97/98
are empty. Full clean recovery separately checks every AG and global counters;
these local copied facts alone are not a clean-volume or ownership assertion.

The reserved-name clean source and actual Aurora append records are described
separately in [append provenance](append-provenance.md). Component tests verify
the archive and full expanded logical-image hashes before applying synthetic
mutations. Extraction and private copies preserve sparse zero extents without
changing any logical disk byte; sparseness is not an additional filesystem
assumption. Formatter tests retain the genuine full-ring geometry, while the
explicitly shortened recovery fixtures are only parser/recovery test inputs.
