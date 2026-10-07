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
