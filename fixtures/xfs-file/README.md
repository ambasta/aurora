# Preserved written-file fixture

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
- Inode 131 at byte 67,072; size 17,003; nblocks 5; flags PREALLOC; flags2 0x18
- One written extent: file block 0, encoded FSB 24, five blocks, image byte 98,304
- 34 file sectors; last contains 107 file bytes and 405 bytes outside the file

Recovery compared all eleven saved image slices byte-for-byte while streaming
all 335,544,320 decompressed bytes. The expanded image was not written to disk.
The complete historical image remains in its original recovery archive; the
focused runner needs only the small slices checked into this directory.

Historical compressed image: 329,279 bytes,
SHA256 `b296caa7feb25ab0fdddb92dad370c9e3612546229a892989085218329ebe328`.
Full decompressed image SHA256:
`a763f544b8ef8ad2015ce1e23e82b9204310c3c5de0da82aafd9db6b6b74def1`.
Original early source/fixture archive SHA256:
`bd7f1193ebdb7d6328e59c14bf991d70cf5f710a62e7b3cf09c51f25887a317d`.
These hashes establish exact recovery identity and internal consistency, not
independent authentication of the historical producer or filesystem correctness.
