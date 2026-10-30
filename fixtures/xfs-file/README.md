# Preserved written and sparse file fixtures

These unchanged bytes were created on 2026-10-04 in a disposable regular XFS
image and recovered on 2026-10-07. `hashes.json` records transport and decoded
identities. Hex files use contiguous lowercase hex and one newline. `written.txt`
is the original 17,003-byte producer input; its bytes match the first 17,003 bytes
of the 20,480-byte extent sample. Historical commands and observations are in
`provenance/`; they are not a claim of new execution.

- Superblock at byte 0; 335,544,320-byte data device (655,360 sectors)
- Blocks 4,096 bytes; sectors and inodes 512 bytes
- Four AGs of 20,480 blocks with encoded stride 32,768
- Root inode 128 at byte 65,536; `written` entry names regular inode 131
- Inode 131 at byte 67,072; size 17,003; nblocks 5; flags PREALLOC; flags 2 0x 18
- One written extent: file block 0, encoded FSB 24, five blocks, image byte 98,304
- 34 file sectors; last contains 107 file bytes and 405 bytes outside the file

Recovery compared all eleven saved image slices byte-for-byte while streaming
all 335,544,320 decompressed bytes. The expanded image was not written to disk.
The complete historical image remains in its original recovery archive; the
focused runner needs only the small slices checked into this directory.

Historical compressed image: 329,279 bytes,
SHA 256 `b 296caa 7feb 25ab 0fdddb 92dad 370c 9e 3612546229a 892989085218329ebe 328`.
Full decompressed image SHA 256:
`a 763f 544b 8ef 8ad 2015ce 1e 23e 82b 9204310c 3c 5de 0da 82aafd 9db 6b 6b 74def 1`.
Original early source/fixture archive SHA 256:
`bd 7f 1193ebdb 7d 6328e 59c 14bf 991d 70cf 5f 710a 62e 7b 3cf 09c 51f 25887a 317d`.
These hashes establish exact recovery identity and internal consistency, not
independent authentication of the historical producer or filesystem correctness.


## Additional unchanged historical slices

The inline-extent extension also preserves exact historical producer bytes for:

- Sparse inode 134 at byte 68,608: EOF 32,769, nblocks 3, written one-block extents at
  logical blocks 1,6,8; encoded FSBs 15,29,31; image bytes 61,440,118,784,126,976.
  `sparse.txt` is the original producer input. Reconstructing those three extent
  slices with zero holes matches every byte through EOF. The runner compares
  all 65 sectors, including the final single file byte and 511 zero tail bytes.
- Empty inode 132 at byte 67,584, EOF 0 and nblocks 0, remains unsupported.
- Reserve inode 133 at byte 68,096, EOF 0 and nblocks 2, has one authentic unwritten
  extent at logical block 0/encoded FSB 13. It remains an unsupported-empty
  regression, not an example of reading unwritten bytes within EOF.

`provenance/extent-recovery-verification.json` records a new read-only streaming
comparison of all 11 saved image slices and the complete decompressed digest.
No expanded image was stored and no mount, physical device, mkfs or new producer
execution occurred. Source and decoded hashes for every added file are in
`hashes.json`; original read-only xfs_db observations are in `provenance/`.

All generated within-EOF unwritten, altered-size and mixed-record fixtures are
synthetic CRC-correct test mutations. The authentic reserve inode is never
silently resized or relabelled as a positive real-image unwritten read.

## Fresh-format mounted-reader inputs

The six `fresh-*.hex` slices were extracted from one new disposable regular-file
image made with **mkfs.xfs 6.13.0** on 2026-10-29; mkfs and read-only xfs_db both
exited zero. No Linux mount, physical disk or host boot configuration was used.
The prototype contained a single `hello` regular file with this exact input:

```text
Aurora reads a real XFS file through its checked block backend.
```

There is one trailing LF. The prototype is `dummy`, `0 0`, `d--755 0 0`, then
`hello ---644 0 0 PATH_TO_INPUT`, then `$`, each on its own line. Creation options:

```sh
mkfs.xfs -d file=1,name=NEW_IMAGE,size=512m -s size=512 \
  -m crc=1,reflink=0,rmapbt=0,bigtime=0,inobtcount=0,uuid=5cdfd5a7-110e-4cd7-8e31-fc36b74c265f \
  -i sparse=0,nrext64=0 -b size=4096 -p PROTOTYPE
```

The saved sectors are superblock LBA0, root inode LBA96 (inode96), regular inode
LBA99 (inode99), file data LBA72, log header LBA524328 and unmount LBA524329.
The complete 64-MiB log has exactly two nonzero sectors; all remaining log bytes
were read and checked, not inferred from the two slices. The root names `hello`
and its stored type is regular. `xfs-fresh-cat` read the original whole image and
returned the exact prototype payload. Only the slices are versioned; tests
reconstruct deliberately synthetic sparse inputs and never call them complete
filesystems. Header/inode mutations are synthetic even when their CRC is repaired.

This exact fresh record has `h_crc=0`; its complete content is admitted by a
strict profile, not by pretending that zero is a verified log checksum. The
Linux v6.13 clean-unmount semantics and format references are in `docs/xfs.md`.


## Pinned Linux clean-log inputs

The seven `linux-6.12-used-*.hex` slices are unchanged bytes from a new 512-MiB
image made by `scripts/xfs_image.py`, then used inside an isolated QEMU guest
running Debian's **Linux 6.12.107+deb13-cloud-amd64 (6.12.107-1), x86_64**.
No host mount or physical device was involved. The one-CPU, 512-MiB guest had no
NIC and mounted only that private image, with `logbufs=2,logbsize=32k`.

The writer opened the existing `/hello` (no create), wrote 64 bytes at offset0
with byte `i = (i * 37 + 11) % 256`, called `fsync`, and closed it. The guest
then synced, unmounted XFS successfully and powered off. `/pattern` remained the
original 9001-byte prototype input. Offline xfsprogs 6.13.0 `xfs_logprint -t`
reported **CLEAN, head=tail=13**; `xfs_repair -n` completed. The Aurora pinned-clean
consumer read both files exactly from the unchanged whole image. Its SHA256 was
`870bd5bae972742d01d5fbcf92d3bf43a196a8d8d2d92b5b1031d563adb9e96d`
before and after these read-only checks.

Saved sectors: superblock0, root96, hello inode99, pattern inode100, hello data72;
log prefix LBA524328 through524340 (13 sectors), and stale-clear header524341.
The final UNMOUNT header is relative sector11, its body12; the following
zero-cycle stale-clear headers are not commit records. The kernel's payload
padding is nonzero and covered by the log CRC. SB LSN is `(1,9)`, hello inode LSN
`(1,5)`, and the superblock version remains `0xb4a5`.

The driver reconstructs **synthetic shortened-log inputs** from these slices.
Cycle relocation, repaired-CRC bodies and all corruptions are explicitly
synthetic, not Linux history or a genuine wrap qualification. A separate genuine
new-inode image remains unsupported (ATTRBIT plus an attribute fork); it is not
silently normalized into a positive.

Whole-image wrap qualification separately continued one private image through
two 70,000-write/fsync guest sessions, each followed by clean unmount. Iteration
`j` writes byte `i = (i * 37 + j + 11) % 256`; `j` runs0..69999 in each session.
The first image remained cycle1, CLEAN head92955 (fsyncs need not emit one log
record each). The second has cycle2 sectors0..40590 and cycle1 thereafter;
sector131071 is an older header whose payload wraps to sector0 with cycle2.
Its latest UNMOUNT is header40589/body40590, CLEAN head=tail40591. Both files
match the producer inputs through the hosted Aurora gate and `xfs_repair -n`
completes. Final whole-image SHA256
`924106b968f9ae0376c25b906d3c4d460dea0c45df1d8e23bfcac208b2b04148`
is unchanged by these checks. These complete private histories are not replaced
by the component driver's synthetic shortened logs or copied into the repository.


The two `linux-6.12-dirty-*.hex` inputs come from a separate fresh image and the
same one-write guest, followed by `fsync`, `sync`, and guest poweroff **without
unmounting XFS**. The exact superblock and eight log sectors are retained (seven
current-cycle sectors and the first stale-clear header). `xfs_logprint -t`
reported **DIRTY, tail2/head7** with ordinary inode transactions; the Aurora
pinned-clean reader returned `log_not_clean` and no bytes on the whole image.
`xfs_repair -n` exited1 and warned about the un-replayed log; it was not a clean
repair pass. Whole-image SHA256
`14786e316d191c2a399460a116952a773d197e52efec5c0c74ccc4f153c6c7c6`
was unchanged by those offline checks. The component row still reconstructs a
synthetic shortened log and does not stand in for this genuine dirty history.
