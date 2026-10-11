# Offline XFS superblock fixture

`superblock-v5-512.hex` is the canonical ASCII transport for the first 512 bytes
of a disposable, unmounted 512 MiB regular-file XFS image. It is a parser input,
not a mounted-filesystem or device qualification result.

- Raw bytes SHA-256: `55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586`
- Hex transport: 1,728 bytes, SHA-256 `d1d3fbc3f8b693d1c0ddf395e92b136a81b2a5d30b9e3cdec36addd580d42986`
- Source image SHA-256: `28fb4dc1d02717c836624d2d368f71b554f03e5b7c4d56affef2d2246faa5a3e`
- Creation tool: xfsprogs 6.13.0, Debian package `6.13.0-2+deb13u1`.
  Package SHA-256: `79e00160bfc45d25a46d2709edd364afb41723d9b96713de8f6c80b6a17f2d74`;
  `mkfs.xfs` executable SHA-256: `72453d0e64fd521be11f49efc9a54ad8e6db77f9660295843ffe76336c80f8ac`.
- Creation parameters: file-backed size `512m`, sector size 512, block size 4096,
  metadata CRC enabled, UUID `5cdfd5a7-110e-4cd7-8e31-fc36b74c265f`, label `AURORA_X0`.
- Stored CRC bytes: `c7 13 71 b6`, numeric little-endian CRC32C `0xb67113c7`.
  Feature words (compat, readonly-compat, incompat, log-incompat): `0, 15, 43, 0`.

Creation used locally extracted tools without system installation. Package hashes
were checked against an HTTPS Debian index; Release signatures were not
independently verified. The original mkfs exit status was not separately retained.
The read-only `xfs_db -r -f` inspection reported a correct superblock CRC. Exact
historical commands and receipts remain in Git history; no new creation run is
implied by this documentation.

`verify_native.py` strictly decodes the transport, checks raw and transport
identities, and uses an independent GF(2) CRC oracle before observing the Aurora
endian/checksum/probe APIs. It uses disposable native outputs and never opens a
device or mounts the image. The [XFS component reference](../../docs/xfs.md)
defines the bounded parser scope and unsupported filesystem features.
