# Recovered original XFS root lookup contract

Revision: post-reset reconstruction, 2026-10-04. Actual reconstructed Aurora module
SHA2568f669775ea7a5e850a314e50c37d90a5ba1ef30b1d60f6c8a54be5a6faef9e4f matches the
historical reviewed source exactly. Fresh host runners have new identities;
old receipts, complete images and native-product archives were lost.

## Current test invocation

`make -C compiler test-xfs-root` runs both native runners using one fresh run-owned
compiler and its validated developer receipt. See the
[shared test contract](developer-test-contract.md) for current provenance,
explicitly pinned acceptance and the tooling candidate's unqualified status.
There is no historical default compiler pin. Direct native runners require
exactly one `--compiler-sha256` or `--developer-build-receipt`. For a reviewed
prebuilt through Make, use the shared acceptance selectors rather than `OUT`
alone. The observed hash is recorded separately from any caller-supplied pin.
Representative or other reduced runs remain partial; full aggregates and
acceptance reject test-flag overrides. Historical reconstruction and fixture
provenance below retain their original meaning.

## Mechanism and interface

`fs::lookup_xfs_v5_512_root(superblock, inode, name)` accepts three readonly
whole-array byte spans and returns copied XfsRootReport. This is an offline
metadata lookup, not a mount, filesystem service, file-data read, path traversal,
allocation/existence check, replay, log-cleanliness claim, device capability or
physical-platform qualification. CRC is not authentication. Callers establish
snapshot provenance; matching embedded identifiers cannot prove byte origin.

The module directly imports fs.xfs_geometry, fs.xfs_probe, std.binary and
std.checksum. A caller imports only fs.xfs_root. No compiler extension, heap,
struct, pointer, retained span or source-visible foreign ABI is introduced.

Statuses: found, not_found, geometry_rejected, unsupported_profile, invalid_query,
invalid_inode, invalid_directory. A closed issue enum identifies the first group
that failed. XfsRootFacts exposes root_inode, inode_offset_bytes, parent_inode,
entry_count and payload_bytes, all u64. XfsRootMatch exposes inode_number and
file_type. The report exposes status(), issue(), found(), facts(), match().
For error statuses, facts() is zero; not_found preserves validated facts.
match() is zero except for found,
including fabricated failed reports. Public constructors can still fabricate
success data; a report is never a validation certificate or an I/O capability.
All results copy independently. Observed class sizes are40,16,72 bytes.

## Profile, bytes and order

Run unchanged superblock geometry admission first. Further require512-byte inode
and single directory block (dirblklog0). Inode numbers are1..0xffffffff. Decode
AG, AG-block and inode-slot using sb.agblklog and sb.inopblog. Reject invalid AG,
actual final-AG tail/gap, AG header block (agb<=1536/block_bytes), and internal
log block intersection. The returned offset is
(AG*agblocks+agb)*block_bytes+slot*512; admitted32-bit inode numbers bound it to
at most2^41-512. This is relative to the claimed data device, with no observation
of actual device capacity or allocated-inode status.

Dinode exact offsets, independent of Aurora class layout:
- magic BE16@0=0x494e; directory mode type0x4000 atBE16@2; version@4=3; format@5=1
- metatype BE16@6=0; nlink BE32@16 in1..0x7fffffff
- count/padding24..31=0, size BE64@56, nblocks BE64@64=0, extsize BE32@72=0
- count fields76..81=0, forkoff82=0, aformat83=2, DM84..89=0, flags BE16@90=0
- next_unlinked BE32@96=0xffffffff, CRC LE32@100
- flags2 BE64@120, cowextsize128..131=0, reserved132..143=0
- embedded inode BE64@152 equals rootino; UUID160..175 matches sb UUID32..47
- local data176..511

CRC32C covers all512 bytes, zeroing100..103. Only flags2 BIGTIME8/NREXT6416 are
allowed; when set they require sb incompat8/32 respectively. Superblock features
do not require every inode to set those flags. Timestamps remain opaque. Both
24..31 and76..81 must be zero for either extent-count layout, including padding.
Existing geometry excludes META_UUID. Uid/gid/project, permission bits,
generation/change count and LSN are opaque; not every upstream property is checked.

Payload6..336 bytes. Header: count byte0<=16, i8count byte1=0, parent BE32@2=rootino.
Record: namelen byte, BE16 saved offset, name bytes, filetype byte, BE32 inode;
length=namelen+8. Bounds precede variable reads. Names1..255 are raw bytes,
rejecting NUL, slash, dot and dotdot. No Unicode assumption. Raw ftype0..8 is
admitted. Validate entry inode address shape with the same geometry rule, not
its allocation or target type. Reject duplicate names. Saved offsets are aligned8,
start at least96, and do not overlap projected ceil((namelen+12)/8)*8 footprints;
holes are allowed. Final projected end (96 if empty)+(count+2)*8+8 fits the single
directory block. Exact shortform payload consumption is required; remaining
inode padding is opaque but CRC-covered. Full directory validation precedes lookup.

First-error priority: geometry; inode size/directory profile; root address;
inode span length; query syntax; magic/version/CRC/identity; flags2; core;
payload size; shortform width/count/parent; entries in order (bounds/name/type/
inode address/saved offset/duplicate); trailing bytes; projected block footprint.
Version, flags2, width and count exclusions are unsupported_profile; malformed
inode or directory fields are recoverable failures, not intended traps.

Public construction currently creates nonempty whole-array spans only. Native
queries cover lengths1,2,3,4,5,255,256;256 fails. The zero-length defensive branch
is source-audited, not a native empty-span test. No forged private-ABI span tests.

## Reference and fixture provenance

Format facts were independently checked against Linux v6.16 commit
038d61fd642278bab63ee8ef722c50d10ab01e8f, fs/xfs/libxfs/xfs_format.h,
xfs_da_format.h, xfs_dir2_sf.c, xfs_dir2.c and xfs_inode_buf.c. The implementation
is original Aurora; no upstream code was copied. Despite an inconsistent old
header comment, actual shortform accessors and real bytes put ftype BEFORE inode.
The initial verbal offsets160/176 were corrected before implementation to152/160,
with data176. Both old and fresh independent input reviews verify the correction.

Exactly2,048 bytes of two historical superblocks and two root inodes are recovered
and match their full known SHA256s. Empty root:128 at65536,size6,count0,parent128.
Named root:128 at65536,size31,count2, alpha131/type1/offset96 and docs132/type2/120.
The source recovery bundle and retained reconstruction receipts explain the
derivation; full hashes establish identity rather than a partial-field match. Complete images and old receipts remain unavailable.
Restored xfsprogs tools are independently package/signature verified, but no new
image generation, mount or xfs_db run against a complete recovered image is claimed.
