# One offline XFS v5/512 fixture

On 2026-10-03, one real `mkfs.xfs` filesystem was created in a disposable sparse
regular file. Its first 512 bytes are preserved through the canonical
[`hex transport`](../fixtures/xfs-offline/superblock-v5-512.hex), with the original
raw binary retained outside the versioned tree as recorded in the transport
update below.
The unchanged pinned M014 compiler executed the Aurora library against these
bytes. All **15 native observations passed**, including the bounded header probe,
raw fields, CRC, input preservation and two deliberately corrupted in-memory
variants. The normal Python verifier and `python3 -O` both passed with the
release compiler; all 15 observations also passed with the pinned sanitized
compiler.

This adds real-tool-generated header evidence to the synthetic tests. It does
not establish mounting, complete XFS support, geometry acceptance, feature
compatibility, journal replay, recovery, writes or durability. No filesystem was
mounted, no physical device was opened, and no kernel/emulator work occurred.
Fixture generation required no compiler or Aurora-language implementation changes.

## Observations and the CRC display distinction

| Observation | `xfs_db -r -f` | Bytes / independent Python / native Aurora |
|---|---|---|
| Magic | `0x58465342` | `XFSB`, BE32 `0x58465342` |
| Version | `0xb4a5`, V5 | BE16 `0xb4a5`; low four bits `5` |
| Sector size | `512` | BE16 `512` |
| Sector log | `9` | byte `9` |
| Compat features | `0` | BE32 `0` |
| Readonly-compat features | `0xf` | BE32 `15` |
| Incompat features | `0x2b` | BE32 `43` |
| Log-incompat features | `0` | BE32 `0` |
| CRC display | `0xc71371b6 (correct)` | stored bytes `c7 13 71 b6` |
| CRC numeric value | Display above is in byte-sequence order | LE32 `0xb67113c7` = `3060863943` |

The CRC values in the last two rows are different representations of the same
stored four bytes. The mathematical finalized CRC is **`0xb67113c7`**, not the
hexadecimal number displayed by this `xfs_db` command. Python independently
divides the complete reflected message polynomial over GF(2), using the normal
Castagnoli polynomial `0x11edc6f41`, rather than the library's reflected byte
recurrence. With bytes 224 through 227 treated as zero, its 512-byte CRC matches
both little-endian storage and the native Aurora calculation.

The raw masks are observations only. This probe deliberately does not interpret
them or certify that any advertised XFS feature is supported.

Native execution reported `header_integrity_valid`. Separate native cases
returned each feature mask, the magic/version/sector fields and the stored and
calculated CRC. An all-512-byte comparison confirmed that the probe preserved
its input. Flipping one bit in padding byte 511, or in stored CRC byte 224,
produced `checksum_mismatch`. These variants were generated from the saved
header in memory; they were not additional formatted images.

## Tools and provenance

The host is Debian GNU/Linux 13 (trixie), x86-64. `mkfs.xfs` and `xfs_db` were
initially absent. Official Debian packages were downloaded over HTTPS and
extracted with `dpkg-deb -x` under `/tmp/aurora-xfs-offline-tools/root`. No system
installation or package maintainer script was run.

- [xfsprogs 6.13.0-2+deb13u1, amd64](https://deb.debian.org/debian/pool/main/x/xfsprogs/xfsprogs_6.13.0-2+deb13u1_amd64.deb)
  SHA256: `79e00160bfc45d25a46d2709edd364afb41723d9b96713de8f6c80b6a17f2d74`.
- [liburcu8t64 0.15.2-2, amd64](https://deb.debian.org/debian/pool/main/libu/liburcu/liburcu8t64_0.15.2-2_amd64.deb)
  SHA256: `bf6d8fe515004a491947c72af8ce2c015c5f9b4e8d024b81952ee8f372d507e9`.

Both package hashes matched the exact package records retrieved from the
[Debian trixie amd64 index](https://deb.debian.org/debian/dists/trixie/main/binary-amd64/Packages.xz).
The index hash and relevant records are preserved. Debian Release signatures
were not independently verified in this task.

Both tools report version `6.13.0`. The locally extracted liburcu supplied the
one missing runtime library. The remaining loaded dependencies came from the
host. Full package dependency declarations, `ldd` output, executable and loaded
library SHA256 values, host tool versions, exact arguments and results are in
[`provenance.json`](../fixtures/xfs-offline/README.md). Declared dependencies
for other utilities within xfsprogs do not imply those utilities were installed
or executed.

The immutable native compiler was `/tmp/aurora-m014-compiler-corrected`, SHA256
`2d86780c0082d861e7031955737eef81bb36936c7971d5032b6a1abbb4a24bf8`.
The sanitized compiler was `/tmp/aurora-m014-compiler-corrected-sanitized`,
SHA256 `ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa`.
Its separate receipt is
[`native-sanitized-results.json`](../fixtures/xfs-offline/README.md).
The first sanitizer attempt stopped before native case execution because
LeakSanitizer cannot operate under this environment's tracing. The preserved
failure record contains the diagnostic excerpt and does not claim a passed
case. The successful run used the existing gate setting
`ASAN_OPTIONS=detect_leaks=0:halt_on_error=1`. Leak checking is excluded;
ASan/UBSan compiler checks remain active. The emitted native program itself is
not sanitizer-instrumented.
The native receipt also pins all three library modules and both reused native
runner source files by SHA256. The copied runner and native build products are
created in `/tmp`; the existing compiler test files are not edited.

## Exact creation and inspection

The file was created with `O_CREAT | O_EXCL | O_NOFOLLOW`, checked with
`S_ISREG`, and enlarged with `ftruncate` to 536,870,912 bytes (512 MiB).
Its allocated size before formatting was zero. Only this new file was passed
to `mkfs.xfs`, once, with these arguments:

```sh
LD_LIBRARY_PATH=/tmp/aurora-xfs-offline-tools/root/usr/lib/x86_64-linux-gnu \
  /tmp/aurora-xfs-offline-tools/root/usr/sbin/mkfs.xfs \
  -d file=1,name=fixtures/xfs-offline/.work/disk.img,size=512m \
  -s size=512 \
  -m crc=1,uuid=5cdfd5a7-110e-4cd7-8e31-fc36b74c265f \
  -b size=4096 -L AURORA_X0
```

The output reports `sectsz=512`, `crc=1`, 4 allocation groups, 4,096-byte blocks,
and a 64-MiB internal log. The original shell did not separately retain the
`mkfs.xfs` exit status, so provenance records that status as unknown rather than
inventing a zero. Complete stdout and empty stderr are retained. The subsequent
read-only inspection exited zero, emitted no stderr, and marked the CRC correct:

```sh
LD_LIBRARY_PATH=/tmp/aurora-xfs-offline-tools/root/usr/lib/x86_64-linux-gnu \
  /tmp/aurora-xfs-offline-tools/root/usr/sbin/xfs_db -r -f \
  -c 'sb 0' \
  -c 'p magicnum versionnum sectsize sectlog crc features_compat features_ro_compat features_incompat features_log_incompat' \
  -c version \
  fixtures/xfs-offline/.work/disk.img
```

The large disposable image was subsequently copied sparsely to
`/tmp/aurora-xfs-offline-disk.img`, the full-image SHA256 was verified, and the
original was removed from the evidence directory. It is not a publication
artifact. The image's size, allocated size and full SHA256 are in provenance.
The persistent fixture is only its first 512 bytes, SHA256
`55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586`.

To reproduce the native comparison using the preserved header, run from the
isolated storage workspace:

```sh
python3 fixtures/xfs-offline/verify_native.py
python3 -O fixtures/xfs-offline/verify_native.py
# Optional independent receipt, leaving the author's recorded receipt untouched:
python3 fixtures/xfs-offline/verify_native.py --receipt /tmp/xfs-review.json
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
  python3 fixtures/xfs-offline/verify_native.py \
  --compiler /tmp/aurora-m014-compiler-corrected-sanitized \
  --compiler-sha256 ca87388b07dd39207ab3342bed2b9cd4ad5212362b435289e7f97b93574476fa \
  --receipt /tmp/xfs-review-sanitized.json
```

The verifier uses explicit fatal checks, including compiler/fixture identity,
length, and GF(2) checks, which remain active under optimized Python. Default
runs print a summary and do not rewrite any receipt. `--receipt PATH` explicitly
writes the result JSON. `--compiler PATH --compiler-sha256 HASH` permits review
with another independently pinned compiler; the supplied hash must match its
bytes. The author's [`native-results.json`](../fixtures/xfs-offline/README.md)
records every expected and observed full-width scalar, the normal exit code,
source hashes, and generated source/assembly hashes. Repeating this check reads
only the small saved header; it does not need the filesystem image or extracted
tools.

## Source transport update

The source-controlled transport is now `superblock-v5-512.hex`, unchanged from
its original creation. Its SHA256 is
`d1d3fbc3f8b693d1c0ddf395e92b136a81b2a5d30b9e3cdec36addd580d42986`.
The verifier reads at most1729 bytes, requires exactly1728 bytes containing32
canonical rows of16 two-digit lowercase hex bytes, checks every row offset, and
then checks the decoded512-byte SHA256
`55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586`.
Neither UTF-8 normalization nor replacement encoding is permitted.

The original binary remains archived outside the versioned tree. Its creation
and native comparison records retain their historical scope; the source-controlled
hex transport is the portable replay input.

`--transport-self-test-only` runs17 explicit malformed/missing/oversized input
controls, including same-size incorrect byte widths, duplicate and reordered
row offsets, raw-byte changes and non-ASCII input. Guards remain active under
python -O. Normal native replay runs those controls before using decoded bytes.
