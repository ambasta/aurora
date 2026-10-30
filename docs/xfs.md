# Read-only offline XFS interpretation

Aurora interprets a deliberately narrow clean, read-only XFS profile from supplied bytes and copied sectors. Recognition is not mount, replay, repair, writable-filesystem support, authentication or device provenance. Exact format references and reproducible real fixture construction are in [the offline fixture guide](offline-xfs-fixture.md) and the checked-in XFS provenance inputs.

## Checksums and primary-header probes

### Checksum API

`import std.checksum;` exports these Aurora-specific names in namespace `std`:

```text
enum class ChecksumStatus { success, out_of_range, invalid_previous };

ChecksumResult(ChecksumStatus status, u64 number)
ChecksumResult.status() const -> ChecksumStatus
ChecksumResult.value_or(u64 fallback) const -> u64

crc32c(builtin::span<const u8> bytes, i64 offset, i64 count) -> ChecksumResult
crc32c_extend(u64 previous_finalized, builtin::span<const u8> bytes,
              i64 offset, i64 count) -> ChecksumResult
```

`ChecksumResult` is an independent copied value with private fields. `value_or`
returns the stored value only for `success`; either error returns the supplied
fallback, including for an error report publicly constructed with a nonzero
payload. Arguments, including the fallback, are evaluated eagerly under the
ordinary language rules. A public result constructor is a report constructor,
not a validation certificate: a caller can construct a success report containing
an arbitrary u64. Every successful result produced by these checksum functions
is in the range 0 through 4294967295.

Both functions process exactly `count` bytes beginning at `offset`. Validation
precedes all byte reads. `crc32c_extend` first rejects `previous_finalized` above
4294967295 as `invalid_previous`, including when the requested range is empty or
also invalid. Range validation then checks, in order:

1. `offset >= 0`;
2. `count >= 0`;
3. `offset <= bytes.size()`;
4. `count <= bytes.size() - offset`.

Failure at any range check produces `out_of_range`. The checks do not compute
`offset + count`, so extreme signed inputs cannot overflow validation arithmetic.
An empty range is valid at every offset from zero through the span's length,
inclusive. A span remains a readonly whole-array borrow; allowing a zero count
does not add empty-array construction or a subspan operation to the language.

The checksum is reflected Castagnoli CRC32C, using the reflected polynomial
0x82f63b78 (decimal 2197175160), a 32-bit all-ones seed, and a 32-bit all-ones
final XOR. The recurrence uses u64 shifts and XORs while preserving a 32-bit
remainder. There is no u32 type, unsigned wraparound or full-width complement.
`crc32c` is `crc32c_extend(0, bytes, offset, count)`.

`crc32c_extend` takes the previous *finalized* checksum. It removes the final XOR,
processes the new bytes, and applies the same final XOR again. Consequently:

- CRC32C of an empty range is zero.
- Extending any valid prior checksum with an empty range returns that prior value.
- Extending the checksum of A with B equals the checksum of A followed by B.
- ASCII `123456789` has checksum 0xe3069283 (decimal 3808858755).

The implementation is a straightforward eight-bit-steps-per-byte recurrence. It
does not allocate heap storage or copy the borrowed input. Ordinary function and checked-span
access overhead remains; there is no throughput or equivalent-C performance claim.
CRC32C detects accidental corruption within its limits. It is not authentication,
a cryptographic integrity guarantee, or evidence that an input is trustworthy.

### XFS probe API

`import fs.xfs_probe;` exports these names in namespace `fs`:

```text
enum class XfsProbeStatus {
    wrong_length, unrecognized, unsupported_profile, checksum_mismatch,
    header_integrity_valid
};

XfsProbeResult(XfsProbeStatus status, u64 compat_bits, u64 ro_compat_bits,
               u64 incompat_bits, u64 log_incompat_bits)
XfsProbeResult.status() const -> XfsProbeStatus
XfsProbeResult.features_compat() const -> u64
XfsProbeResult.features_ro_compat() const -> u64
XfsProbeResult.features_incompat() const -> u64
XfsProbeResult.features_log_incompat() const -> u64

probe_xfs_v5_512(builtin::span<const u8> bytes) -> XfsProbeResult
```

The report and its four scalar observations are copied. It stores no span and
confers no capability. Its public constructor permits arbitrary reports; a status
alone is not proof that the function inspected any bytes.

The function checks the following conditions in order and stops on failure:

| Condition | Failure status |
|---|---|
| Input length is exactly 512 bytes | `wrong_length` |
| Big-endian u32 at byte 0 is 0x58465342 (`XFSB`) | `unrecognized` |
| Low four bits of big-endian u16 at byte 100 equal 5 | `unsupported_profile` |
| Big-endian u16 at byte 102 equals 512 | `unsupported_profile` |
| Byte 121 equals 9, the sector-size logarithm for 512 bytes | `unsupported_profile` |
| Computed CRC equals little-endian u32 at byte 224 | `checksum_mismatch` |

Only after these checks does the function report `header_integrity_valid`.
Version bits above the low four are not interpreted or rejected. Lengths above
512 are rejected rather than silently checking a prefix. Other XFS sector sizes
are outside this deliberately narrow profile.

Checksum coverage is the complete 512-byte input, including the bytes after the
defined superblock fields. Bytes 224 through 227 are treated as four zero bytes.
The implementation obtains the same CRC without mutating or copying the input:

1. `crc32c(bytes, 0, 224)` processes bytes 0 through 223.
2. `crc32c_extend(prefix, borrow_bytes(local_four_zeros), 0, 4)` inserts the zeros.
3. `crc32c_extend(zeroed, bytes, 228, 284)` processes bytes 228 through 511.

The stored checksum at 224 is decoded little-endian, independently of the
big-endian fields around it. The preceding exact-length check establishes every
fixed reader and checksum range. The checksum API cannot report a range or prior
error for those fixed calls when its stated contract holds.

After length and magic match, the result preserves four raw big-endian u32
observations, widened to u64:

| Accessor | Byte offset |
|---|---:|
| `features_compat()` | 208 |
| `features_ro_compat()` | 212 |
| `features_incompat()` | 216 |
| `features_log_incompat()` | 220 |

`wrong_length` and `unrecognized` results contain zero for all four observations.
Other results contain the raw field values, even for an unsupported version or a
checksum mismatch. Such values are untrusted diagnostic observations. The
function neither interprets their bits nor decides feature compatibility. All
bit patterns are preserved, and none changes the result by itself.

`header_integrity_valid` means only that this bounded profile and its CRC matched.
It does not mean the superblock is valid under the full XFS specification, that
the filesystem is supported or mountable, that geometry or metadata relationships
are consistent, that a log is clean, or that replay, recovery, writable access,
or durability is safe. Feature support, geometry checks, device size, UUIDs,
allocation groups, log state and all other filesystem acceptance conditions
remain outside this API. A deliberately recomputed CRC can accompany arbitrary
or malicious contents; the status must never authorize filesystem use.

## Primary-header geometry

### Reviewed clarification of first-error order

This ordering is Aurora's local API priority, not a claim about universal XFS
error ordering or every upstream mount validator:

1. Run the unchanged old probe. A rejected probe produces `probe_rejected/none`;
   the nested probe copy retains its original status and raw diagnostic behavior.
   All new raw observations, mask diagnostics and geometry facts are zero.
2. After successful integrity probing, decode raw observations and every extended
   unsupported/unknown mask before selecting a new error.
3. Required legacy version bits, then required features2 bits.
4. Excluded legacy version bits, then excluded features2 bits.
5. NEEDSREPAIR, then other extended mask exclusions and missing local FTYPE.
6. features2 mirror mismatch, then inprogress.
7. Nonzero realtime data, external log, stripe fields, quota/misc flags.
8. Block, inode and directory scalar geometry.
9. AG count/size/address-bit geometry and final-AG length.
10. Representability of claimed data bytes.
11. Zero-realtime ancillary geometry, then inode alignment.
12. Log sector declarations, log size, encoded address/range and AG-header exclusion.
13. `imax_pct` and `shared_vn`, together as `inconsistent_header/misc_geometry`.
14. Success only after all checks pass.

The final miscellaneous check intentionally follows log geometry and data-size
errors. Multiple faults are tested to pin this order. The final miscellaneous check has this exact priority.

With SECTORBIT present, **any** stored log-sector pair other than 512/9 yields
`unsupported_layout/log_geometry`. This is deliberately only profile admission,
not a diagnosis of whether some other pair is coherent in general XFS. With the
bit absent, any nonzero log-sector size/log pair yields
`inconsistent_header/log_geometry`. Absent-bit zero/zero reports effective 512.
There is no general-sector validator hidden behind this narrow rule.

### Source-level API and reports

Callers must directly import both modules because the public report includes the
existing independently defined probe class:

```cpp
import fs.xfs_geometry;
import fs.xfs_probe;

// Exported from fs.xfs_geometry, in namespace fs:
auto inspect_xfs_v5_512_geometry(builtin::span<const u8> bytes)
    -> fs::XfsGeometryReport;
```

No implicit re-export or compiler visibility exception is introduced.

`XfsGeometryStatus` cases:

- `probe_rejected`: return the unchanged old probe result; no new decoding claim
- `unsupported_feature_profile`: known-but-excluded or unknown feature bits
- `unsupported_layout`: format/layout outside this deliberately narrow contract
- `offline_state_indicated`: in-progress operation or NEEDSREPAIR indication
- `inconsistent_header`: contradiction among the particular fields checked here
- `size_unrepresentable`: consistent counts cannot be represented as u64 bytes
- `header_geometry_consistent`: exactly the listed facts/checks succeeded

A separate closed issue enum identifies the first failing group: `none`,
`legacy_required_bits`, `legacy_excluded_bits`, `features2_required_bits`,
`features2_excluded_bits`, `extended_feature_masks`, `features2_mirror`,
`needs_repair`, `offline_operation`, `realtime`, `external_log`, `striping`,
`quota_or_misc_flags`, `block_geometry`, `inode_geometry`, `directory_geometry`,
`ag_geometry`, `data_byte_size`, `realtime_zero_geometry`, `inode_alignment`,
`log_geometry`, `misc_geometry`.


The 24 facts are all u64, with names that state their units:

`block_bytes`, `sector_bytes`, `inode_bytes`, `inodes_per_block`, `block_log`,
`sector_log`, `inode_log`, `inodes_per_block_log`, `ag_block_log`, `data_blocks`,
`claimed_data_bytes`, `claimed_data_sectors`, `ag_blocks`, `ag_count`, `ag_bytes`,
`last_ag_blocks`, `last_ag_start_bytes`, `directory_block_bytes`,
`log_start_encoded`, `log_ag`, `log_ag_block`, `log_start_bytes`, `log_bytes`,
`effective_log_sector_bytes`.

Fact groups use ordinary copied constructors; every listed field is u64:

- `XfsBlockFacts(block_bytes, sector_bytes, block_log, sector_log,
  directory_block_bytes, effective_log_sector_bytes)` (6 parameters)
- `XfsInodeFacts(inode_bytes, inodes_per_block, inode_log,
  inodes_per_block_log)` (4)
- `XfsDataFacts(data_blocks, claimed_data_bytes, claimed_data_sectors)` (3)
- `XfsAgFacts(ag_block_log, ag_blocks, ag_count, ag_bytes, last_ag_blocks,
  last_ag_start_bytes)` (6)
- `XfsLogFacts(log_start_encoded, log_ag, log_ag_block, log_start_bytes,
  log_bytes)` (5)
- `XfsGeometryFacts(blocks, inodes, data, ags, log)` (5 copied class parameters)
- `XfsHeaderObservations(versionnum, features2, bad_features2)` (3)
- `XfsFeatureMasks(compat, ro_compat, incompat, log_incompat)` (4)
- `XfsFeatureDiagnostics(unsupported, unknown)` (2 copied mask-class parameters)
- `XfsGeometryReport(status, issue, probe, raw, masks, facts)` (6 parameters)


Report const accessors are `status()`, `issue()`, `probe()`, `raw()`, `masks()` and
`facts()`. Raw observations expose `versionnum()`, `features2()`,
`bad_features2()`. Diagnostics expose copied `unsupported()`/`unknown()` mask
groups with `compat()`, `ro_compat()`, `incompat()`, `log_incompat()` getters.
Facts expose copied `blocks()`, `inodes()`, `data()`, `ags()` and `log()` groups;
scalar getters use the unit-bearing names listed above.

Use named typed locals for copied projections, as required by the existing
language subset. Classes have private fields and ordinary complete public
constructors, at most six source parameters each. The public report has 42 scalar
leaves and three levels of class containment; source/runtime layout observations
are part of acceptance rather than inferred proof from this count.

`facts()` masks every non-success status to a newly constructed all-zero value,
even when a caller manually constructs a failed report with nonzero facts.
Raw observations, masks and nested probe copies remain explicitly untrusted
report data. A freely constructed success report can still hold arbitrary facts;
it is neither a validation certificate nor an I/O capability.

### Implementation boundary

The old probe runs once. Two private helpers return only a two-field verdict:
profile admission first, geometry checks second. This avoids allocating a full
42-leaf report at every rejection branch and keeps the validation frame bounded
under the existing compiler limits.

Only after both verdicts succeed does a private builder re-read fixed fields and
construct the fact groups. These reads use the **same immutable borrowed span**;
there are no callbacks, external reads, mutation or retained/returned references.
The span obeys the current array/owner lifetime rules. This reasoning does not cover asynchronously mutable or device-backed
buffers; any future I/O layer needs a separate stable-snapshot contract.
The builder's arithmetic preconditions are established by those checks; it is not
an exported alternative entry point. Tests must reject direct source access to
private helpers. This is a library reasoning boundary, not a new compiler proof
that arbitrary calls to an unchecked helper would be safe.

Every untrusted byte read is at a fixed offset after the old probe establishes
exact 512-byte length. Only CRC and bounded bit-width loops inspect repeated
input; no loop iterates over the declared AG count or data size. Checked arithmetic
remains enabled throughout. Intended malformed-input behavior is a recoverable
report; any signal, compiler crash or timeout fails the test gate. Finite tests
are not exhaustive enumeration of all 4096-bit headers or a total compiler proof.

Some explicit product bounds are mathematically redundant after u32 fields or
prior data-size bounds; no test claims to observe them. Every observable guard
has a header case in `tests/compiler/storage/xfs_geometry.py` whose complete
report is pinned in the golden file beside it.

### Meaning of an admitted header

The field mask policy admits only the listed header calculations. It does not
promise operations on finobt, rmapbt, refcount, sparse inode, timestamp, extent,
directory, log or any other metadata. It must never become a mount allowlist.
Claimed device sizes are arithmetic facts, not observations of device length.
A correct CRC is error detection, not authentication. No log cleanliness,
transaction reservation, allocation non-overlap, secondary-header applicability,
mountability, recovery, repair or read/write filesystem support follows.

Real fixture provenance remains unchanged: the original mkfs exit code was not
retained, later read-only xfs_db succeeded, package-index hashes matched but the
Debian Release signature was not independently checked. Synthetic CRC-repaired
headers are never described as real filesystems. The canonical ASCII hex and
strict decoder are used without introducing a binary source-transport copy.

## Local root directory

### Mechanism and interface

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

### Profile, bytes and order

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

Queries must name 1..255 raw bytes; empty or oversized names reject. Tests must use supported array/owner spans rather than forge private ABI capabilities.

## Indexed directory entries

### Admitted format

All [existing root-profile restrictions](xfs.md) remain in force:
the exact admitted v5 geometry, a 512-byte v3 local-format root inode, four-byte
entry inode numbers, at most 16 entries, the same feature/flag exclusions, and
the same complete checks for CRC, identity, names, duplicate entries, saved
offsets, exact payload consumption and projected directory-block footprint.
There is no new feature-mask admission or on-disk format interpretation.

The implementation shares validation with name lookup. Every directory entry,
including entries after the requested index, must validate before returning an
entry or end marker. An early valid entry cannot hide a malformed later entry,
duplicate name or trailing payload bytes.

### Status and precedence

`XfsRootEntryStatus` has `found`, `end`, `invalid_index`, `geometry_rejected`,
`unsupported_profile`, `invalid_inode` and `invalid_directory` outcomes.
`issue()` returns the existing `XfsRootIssue`; `entry_index` is appended without
renumbering the existing issues.

Checks run in this order:

1. Existing geometry, inode-size/directory profile, root address and input inode
   length checks. These failures take precedence over an invalid index.
2. Negative index: `invalid_index` / `entry_index`, before inspecting inode core
   or directory contents, matching the old lookup's query-validation position.
3. Complete existing inode and directory validation. Its first issue takes
   precedence over an oversized nonnegative index or an end marker.
4. Index greater than validated entry count: `invalid_index` / `entry_index`.
5. Index equal to validated entry count: `end` / `none`.
6. Index below validated entry count: `found` / `none`.

Thus an empty admitted directory returns `end` for index zero; a nonempty one
returns `end` exactly one past its last entry. Negative values and values beyond
that end position are errors. Both signed i64 endpoints are handled without
overflow or a bounds trap. No index arithmetic occurs before admission.

### Copied result and raw names

`XfsRootEntryReport` supplies `status()`, `issue()`, `facts()` and `entry()`.
`facts()` returns the existing five root facts for `found` and `end`, and zeros
for every error. `entry()` returns an `XfsRootEntry` only for `found`; it returns
all zeros for `end` and every error, even if a caller constructs a failed report
with a nonzero payload.

An entry exposes four u64 values:

- `inode_number()` and `file_type()` retain the existing raw-directory meanings.
- `name_offset_bytes()` is the start of the name relative to the input inode.
- `name_length_bytes()` is the raw byte length, between 1 and 255 for a match.

Name coordinates refer only to the same unchanged inode snapshot passed to the
operation. They are copied integers, not a retained span, reference, lifetime
token or provenance certificate. The caller must keep that snapshot and use
checked indexing when consuming its bytes. Mutating or replacing the snapshot
invalidates the relationship between those coordinates and the validated name.
The report's copied numeric values remain independent of later input mutation.
Public report constructors can fabricate success values and grant no authority.
Names are opaque bytes; no UTF-8 or Unicode interpretation is imposed.

The entry is 32 bytes and the report is 88 bytes under the existing copied-value
layout. No new compiler, heap, borrowing or class-capacity mechanism is needed.

## Sector-backed metadata

### Operation and ordering

`fs::inspect_xfs_v5_512_sector(source, first_sector)` accepts copied
`storage::SectorGeometry` and `storage::SectorReadResult` values. The caller must
supply sector zero of the same source described by the geometry. These public
values contain no source identity or sector address; this API cannot establish
that provenance or detect a caller who lies about the source capacity.

The operation returns a copied `XfsSectorHeaderReport` with four outcomes:

1. `read_failed`: the read status is not `success`. The actual I/O status is
   preserved, and no supplied payload byte is parsed. This takes precedence
   over metadata validity and source capacity.
2. `geometry_rejected`: the successfully read bytes fail the complete existing
   XFS probe/geometry validator. Its status, issue and diagnostics are retained.
   This takes precedence over a small or zero source capacity.
3. `source_too_small`: valid header geometry claims more 512-byte data sectors
   than the supplied source count. No byte-size multiplication or narrowing of
   that count is performed.
4. `header_fits_source`: the validated claimed data-sector count fits, including
   equality. This is an arithmetic observation about supplied values.

The fixed sector size is 512 bytes. Source writability has no effect on readonly
inspection. Counts up to the full u64 maximum are compared without conversion to
signed indices. Existing geometry validation has already checked the claimed
byte-size arithmetic before the capacity comparison.

After a successful read, a bounded loop copies the sector through checked byte
access into a local 512-byte array. Only a call-scoped readonly span of that array
is passed to the existing parser. No view, receiver reference or mutable alias
escapes; neither input is changed. No new span construction or lifetime rule is
introduced.

### Reports and masking

`status()` and `io_status()` preserve the two separate error domains.
`geometry_or_empty()` returns the complete copied parser report after successful
I/O. On `read_failed`, or any non-success I/O status, it returns an empty report:
`probe_rejected`, issue `none`, probe `wrong_length`, and zero observations,
masks and facts. That empty diagnostic is a sentinel for "not inspected", not a
claim that a failed device returned a short sector.

`facts()` returns geometry facts only for `header_fits_source` with successful
I/O; every other outcome returns zero facts. Thus the nested parser report can
explain the required size of an oversized source while the top-level accessor
cannot expose those facts as capacity-admitted. Both masking rules also apply to
caller-constructed reports with nonzero payloads. Public constructors can still
fabricate success reports and grant no device authority or validation proof.

The report is 352 canonical bytes, below the existing 520-byte copied-value cap.
It owns no sector data and remains independent of later changes to the device,
source arrays or other copies.

## Inline-extent file sectors

### Operations and copied reports

`fs::XfsFileRequest(inode_number, file_sector)` holds a u64 inode number and exact
i64 file-relative sector index. `plan_xfs_v5_512_file_sector(source, superblock,
inode, request)` returns copied status, issue, facts and mapping information.
`read_xfs_v5_512_file_sector(source, superblock, inode, request, window, base_lba)`
revalidates those metadata inputs and returns the existing owned
`storage::SectorReadResult`. It never accepts a public plan as authority to read.

`XfsFileFacts` exposes `inode_number()`, `inode_lba()`, `size_bytes()`,
`extent_count()` and `allocated_blocks()`. The latter is the sum of all declared
written and unwritten record counts. The public API has no single-extent compatibility wrappers or duplicate storage representations.

`XfsFileSector.kind()` returns `none`, `written`, `hole` or `unwritten` from
`XfsFileSectorKind`. `source_lba()` is nonzero only for a written mapping and is
masked to zero for every other kind, including caller-fabricated coordinates.
`valid_bytes()` is 1..512 for an admitted file sector and zero for kind `none`.
Ready/end reports expose facts; only ready exposes a coordinate. Other reports
mask their facts and coordinate, even when constructed with nonzero inputs.
These freely constructible reports remain data, not validation certificates.

Native layout checks confirm bounded inline values: request 16, facts 40,
coordinate 24, report 80 bytes; the existing sector result remains 520 bytes.

### Profile admission and complete extent validation

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

### Mapping and owned bytes

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

### Arithmetic and bounded work

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


## Geometry field and feature policy

### Exact input fields

Offsets are from the observed first byte, not compiler layout. Multi-byte values
below are big-endian except the existing little-endian checksum at 224. The
existing probe establishes all fixed read bounds before new interpretation.

| Byte offset | Width | Field / purpose |
|---:|---:|---|
| 4 | 4 | blocksize, bytes |
| 8 | 8 | dblocks, raw data-block count |
| 16, 24 | 8 each | rblocks, rextents |
| 48 | 8 | logstart, **encoded** filesystem block address |
| 80, 84, 88, 92, 96 | 4 each | rextsize, agblocks, agcount, rbmblocks, logblocks |
| 100, 102, 104, 106 | 2 each | versionnum, sectsize, inodesize, inopblock |
| 120..127 | 1 each | blocklog, sectlog, inodelog, inopblog, agblklog, rextslog, inprogress, imax_pct |
| 152 | 8 | frextents, only for the zero-realtime consistency check |
| 176, 178, 179 | 2, 1, 1 | qflags, flags, shared_vn |
| 180, 184, 188 | 4 each | inoalignmt, unit, width |
| 192, 193, 194, 196 | 1, 1, 2, 4 | dirblklog, logsectlog, logsectsize, logsunit |
| 200, 204 | 4 each | features2, bad_features2 |
| 208, 212, 216, 220 | 4 each | compat, ro_compat, incompat, log_incompat, via old report |
| 228 | 4 | spino_align |

No need to decode rootino, rbmino, rsumino, UUID/meta_uuid, LSN, ordinary free-
space/inode counters, quota inode numbers or later superblock fields in this
slice. Bytes not interpreted still remain covered by the original full-sector
CRC. Do not impose a new requirement that all uninterpreted bytes be zero.

### Feature policy: recognition is not operational support

Pinned v6.16 known masks are compat=0, ro_compat=0x0f,
incompat=0x7ff, log_incompat=0x01. The header-fact profile admits only masks
compat=0, ro_compat within 0x0f, incompat within 0x2b, log_incompat=0.
Require incompat FTYPE (0x01) for this local profile; its absence is
`unsupported_feature_profile`, not a universal claim of corrupt XFS.

- RO bits 0x01/0x02/0x04/0x08 name FINOBT/RMAPBT/REFLINK/INOBTCNT.
- Admitted incompat bits 0x01/0x02/0x08/0x20 name FTYPE/SPINODES/BIGTIME/NREXT64.
- Known but excluded incompat bits include META_UUID 0x04, NEEDSREPAIR 0x10,
  EXCHRANGE 0x40, PARENT 0x80, METADIR 0x100, ZONED 0x200, ZONE_GAPS 0x400.
- Known log bit 0x01 is delayed attributes. It is excluded here, just like all
  other nonzero log-incompat bits. Zero does not prove a clean log.

For each 32-bit word W, report `unsupported = W & (0xffffffff XOR allowed)`
and `unknown = W & (0xffffffff XOR known)`. Do not confuse unknown-to-v6.16 with
recognized-but-outside-Aurora's-profile. Report every mask even if a different
first-error status wins. Never sign-extend a 32-bit mask or accidentally apply a
64-bit unbounded complement. No option for callers to override the allowlist.

Legacy fields matter as well. v5 requires version feature flags 0xb4a0 and
features2 flags 0x18a in the pinned read validator. Low version bits remain 5.
For the smallest canonical profile admit versionnum only 0xb4a5 or 0xbca5
(the latter additionally declares log-sector fields), and features2 only 0x18a.
Thus additional legacy ATTR/QUOTA/DALIGN/ASCII-CI flags are honestly reported
unsupported rather than quietly implying their downstream semantics. The pinned
known version mask is 0xfdff; SHAREDBIT 0x0200 is excluded by Linux too. The pinned
known v5 features2 mask is 0x38a, so features2 FTYPE 0x200 is known but excluded by
this initial profile. Missing required legacy flags are `inconsistent_header`;
additional bits are `unsupported_feature_profile`. The canonical mirror must
equal features2; a mismatch is `unsupported_layout`, not claimed universally
corrupt because historical readers reconcile this legacy duplicate.

These admitted feature bits mean only that their superblock fields can undergo
the listed calculations. They do not advertise reading finobt/rmapbt/refcount
trees, sparse inode records, timestamps, extent counters or directory entries.
X1 must have its own independently reviewed operation/read/replay/write matrix;
this allowlist must never be reused as a mount-support allowlist.

### Geometry relations

5. Block geometry: 10 <= blocklog <= 16 for v5, blocksize = 2^blocklog, and
   blocksize >= sector size. Sectsize=512/sectlog=9 were already established.
   First validate the inode scalar relation over logs8..11 and the matching
   power-of-two sizes. A consistent 256-byte/log8 inode is unsupported by this
   local profile; an inconsistent size/log pair is inconsistent_header. Admit
   inode sizes 512, 1024 or 2048 (logs 9..11), inodesize=2^inodelog,
   inodesize <= blocksize, inopblock=blocksize/inodesize and
   inopblog=blocklog-inodelog. A 256-byte inode is deliberately outside this
   initial profile; label it unsupported, not a claim that the common upstream
   scalar validator universally rejects 256. Other size/log contradictions are
   inconsistent. Validate dirblklog <= 16-blocklog before adding or shifting;
   directory_block_bytes=blocksize*2^dirblklog <=65536.
6. AG/data geometry: agblocks>0, agcount>0, dblocks>0; nominal AG byte size
   agblocks*blocksize is in [2^24,2^40]. agblklog equals bit_width(agblocks-1),
   i.e. ceil(log2(agblocks)). **AG length need not be a power of two.**
   agcount equals ceil(dblocks/agblocks), evaluated safely below. Last AG has
   64..agblocks blocks. Nominal AGs have the declared fixed size; the last may
   be shorter and need not be at least 16 MiB. imax_pct <=100, including 0;
   shared_vn=0.
7. Convert dblocks to claimed_data_bytes only if it fits u64, otherwise
   `size_unrepresentable`. Claimed bytes are not an observation of actual device
   length. Derive sector count, nominal AG bytes and last-AG start safely.
8. For the admitted no-realtime layout require rextents=rbmblocks=rextslog=
   frextents=0, and 4096 <= rextsize*blocksize <=1073741824. rextsize is not
   required to be zero; nor are rbmino/rsumino, which this slice does not read.
9. With SPINODES, inoalignmt must equal floor(64*inodesize/blocksize). If
   spino_align!=0 require spino_align<=inoalignmt and
   inoalignmt%spino_align=0. Without SPINODES require spino_align=0. These are
   the pinned header relations; no sparse inode tree is checked. No modulo is
   evaluated for a zero divisor.
10. With SECTORBIT absent, require logsectsize=logsectlog=0 and report effective
    log sector size 512. With it present, require 512/9 for this profile. Do not
    reject absent-sector-bit zeroes just because the log's effective sector is
    512. Require logblocks>0, logblocks<=1048576 and
    logblocks*blocksize<=2136997888 (2 GiB minus 10 MiB).
11. Decode logstart as AG number plus AG-relative block number using agblklog;
    apply the safe address checks below. The log extent must remain wholly
    inside one actual AG and beyond the AG header sectors. Derive byte offset
    using **linear AG placement**, not logstart*blocksize.

The admitted header does not establish minimum feature-dependent log reservation, allocation non-overlap, mounted validity or a clean log.

### Overflow-safe arithmetic contract

Use u64 for decoded counts and products; convert to i64 only for a shift count
already proved <=63. Never allow a language overflow/division/shift/bounds trap
to become the response to a hostile input. Do not use kernel C integer narrowing
or wrapping operations as a model for Aurora implementation.

That is a library-validation contract over fixed512-byte inputs and bounded
length rejection, not a proof that arbitrary compiler/host failures cannot occur.
Finite native/adversarial tests provide evidence for the contract, not exhaustive
enumeration of all4096-bit inputs. Any compiler crash, harness failure or native
signal fails the gate and remains separately reported rather than being called
an input rejection or a library no-trap proof.

Let B=blocksize, S=512, A=agblocks, N=agcount, D=dblocks, M=2^64-1.

- Precheck every divisor nonzero. Addition a+b requires a<=M-b; subtraction
  a-b requires a>=b; product a*b requires b=0 or a<=M/b before evaluating it.
- After A>0 and D>0, compute q=D/A and r=D%A. If q>0xffffffff, or q equals
  0xffffffff with r!=0, the header cannot match its 32-bit agcount. Otherwise
  expectedN=q when r=0 and q+1 otherwise. Never use (D+A-1)/A.
- After N matches, tailBase=(N-1)*A; require tailBase<=D; tail=D-tailBase;
  require 64<=tail<=A. Check products explicitly, even when encoded u32 bounds
  make them mathematically safe. Do not truncate expectedN to u32.
- Require D<=M/B before dataBytes=D*B. Sector count is D*(B/S), guarded the same
  way; alternatively derive dataBytes/S only after the first product succeeds.
- lastAgStartBytes=tailBase*B. This is bounded by validated dataBytes. Nominal
  agBytes=A*B fits after its 1 TiB bound. Do not iterate over N AGs.
- For any AG g<N, raw base=g*A and actual length=(g=N-1 ? tail : A).
  Each derived range is a half-open interval. Final-AG endpoint equals D.
- agblklog=bit_width(A-1) is computed only after A>0; this loop costs at most
  32 iterations here. Validate stored agblklog equality before using it as a
  shift count. For the admitted geometry it is <=30; prove the bound in tests.
- For encoded F=logstart, g=F>>agblklog and
  a=F & ((1<<agblklog)-1). Keep g as u64 and compare g<N before any narrowing.
  Require a<actualAgLength and logblocks<=actualAgLength-a. Require
  a>floor(3*S/B), the filesystem block containing the AGFL header sector.
  Then rawStart=g*A+a, logStartBytes=rawStart*B and logBytes=logblocks*B.
  Check rawStart<=D and logblocks<=D-rawStart as an independent postcondition.
  Never compare the encoded F directly to D as if it were a linear block count.
- A count is not an encoded address: dblocks and agblocks remain raw counts.
  The ordinary byte/block scaling formula must not be applied to encoded
  filesystem block addresses or inode numbers.

## Fresh-format read-only mount state

`fs.xfs_mount` adds `XfsReadonlyMount`, a linear owner with a private
1536-byte `OwnedBytes` cache (superblock, root and last returned sector). Construct
it with a region, a moved allocation of exactly that size, the observed volume
length in 512-byte sectors, and an explicit `XfsReadonlyProfile`. Production
callers select `fresh_format`; unknown profiles are refused. No constructor accepts an admission result or
clean-log boolean. `needs_read()` and `requested_lba()` request one sector;
`accept(lba, io_status, bytes)` accepts only that LBA, a successful read and
exactly 512 bytes. Failed or out-of-order reads permanently prevent admission.

The backend must hold the same **stable, exclusive read-only volume** for the
object's lifetime, including all subsequent file reads. Copied sector contents
cannot establish hardware provenance, exclude another writer, or grant device
access. The mount never writes, flushes, repairs or replays. `ready` describes
this narrow profile only; it is not full roadmap X1 completion.

The profile first runs the existing geometry/CRC validator, then requires:

- 4096-byte blocks, 512-byte sectors/inodes, one-block directories; existing
  geometry exclusions still apply (no realtime, external log, striping or quotas).
- Exactly FINOBT in read-only-compatible features, exactly FTYPE in incompatible
  features, and zero compatible/log-incompatible features. This does not promote
  the geometry parser's broader masks into a mount allowlist.
- Non-null filesystem UUID, zero superblock/inode LSNs, and an internal log at
  most 64 MiB. FINOBT allocation trees are not traversed or claimed verified.
- The exact little-endian fresh-format log produced by the recorded xfsprogs
  fixture: a two-sector version-2 record at log offset zero, cycle 1, record/tail
  LSN `(1,0)`, 512 data bytes, one UNMOUNT operation, matching filesystem UUID,
  Linux-LE format, 32 KiB record capacity and the userspace packed transaction ID.
  Reserved/padding bytes and **every byte of the rest of the declared log** must
  be zero. The fresh record's CRC field is zero: this is an exact-content check,
  **not a record-CRC verification**. A zeroed entire log is rejected.
- The existing validated shortform root, at most 16 entries, each a nonempty
  regular file supported by the bounded inline-extent reader. All entries and
  every advertised inode are checked before `ready`. Empty files, subdirectories,
  symlinks, attributes, btree forks and other inode formats are refused. No
  permission/ACL policy or allocation-tree cross-check is claimed.

The unmount marker, packed cycle and record layout follow Linux **v6.13**
[`xfs_log_format.h`](https://github.com/torvalds/linux/blob/v6.13/fs/xfs/libxfs/xfs_log_format.h)
and the clean-unmount/head relationship in
[`xfs_log_recover.c`](https://github.com/torvalds/linux/blob/v6.13/fs/xfs/xfs_log_recover.c).
The exact fresh bytes are preserved in `fixtures/xfs-file/fresh-*.hex`; their
creation is described in that fixture's existing README. The full zero-tail
scan establishes the head immediately after the unmount record for this subset.
Reused/wrapped logs—even clean Linux logs—dirty logs, torn writes and any state
requiring replay fail closed. There is no generic head/tail recovery algorithm.

### Pinned-Linux clean-log profile

`linux_6_12_x86_64_clean` is a separate explicit profile of
this same state machine. `xfs-fresh-cat IMAGE ROOT_FILENAME
--linux-6.12-x86_64-clean` selects it explicitly; disk contents cannot select it.
It targets Linux **6.12.107 x86_64**, 512-byte log sectors and 32-KiB records,
with the same filesystem feature and namespace restrictions as above.

The complete bounded log scan accepts only one current-cycle prefix followed
by the preceding cycle, or a complete single cycle. It derives a logical
cycle/block head, distinguishes exact zero-length stale-clear headers from real
records, and never trims a newer incomplete record back to an older clean one.
The latest nonempty record must end exactly at that head and contain one exact
Linux UNMOUNT operation. Its CRC32C covers the 328-byte producer header (CRC
field cleared) and the still cycle-stamped payload, including opaque padding.
A record crossing the physical end carries the payload/head cycle. UUID,
physical record LSNs, record geometry and tail bounds are checked; superblock
and advertised inode LSNs must not exceed the proven logical head. Earlier
transaction payloads are not replayed or claimed CRC-verified.

These rules follow the pinned producer's
[`xfs_log.c`](https://github.com/gregkh/linux/blob/v6.12.107/fs/xfs/xfs_log.c),
[`xfs_log_recover.c`](https://github.com/gregkh/linux/blob/v6.12.107/fs/xfs/xfs_log_recover.c)
and [`xfs_log_priv.h`](https://github.com/gregkh/linux/blob/v6.12.107/fs/xfs/xfs_log_priv.h).
A genuine isolated Linux overwrite/fsync/unmount of the existing prototype file
passes this complete hosted gate: the 64-byte changed file and the untouched
9001-byte file match their producer inputs, and the whole image remains unchanged
by Aurora reads and `xfs_repair -n`. Exact observed sectors and construction are
in the existing XFS fixture directory. An earlier image that created a new inode
remains refused at ATTRBIT, and also has an unsupported attribute fork. A separate
genuine write/fsync/sync followed by guest poweroff without unmount is DIRTY in
`xfs_logprint` and produces `log_not_clean` with zero Aurora output; no replay is
attempted and the image remains unchanged. Two further 70,000-write/fsync
sessions continued one private image's history, with a clean unmount between
them. The first remained cycle 1; the second genuinely wrapped to cycle 2 with
head/tail 40591, including a record crossing the physical log boundary. Both
whole images pass the hosted reader, exact file comparisons and `xfs_repair -n`
without changing their hashes. Synthetic wrap tests do not replace this history.
The same source owner also passes separate protected-NVMe used/wrapped reads and
genuine dirty-log refusal on those whole images. Both binary files are checked
across clients; dirty opens expose no bytes or identities while the independent
RAM namespace remains usable. Every read-only private image remains unchanged.
Whole-suite and budget acceptance are separate from these component results.
Additional stale-clear cycle transitions, other producer
ABIs/record sizes, dirty/replay-required logs and unsupported namespaces remain
closed. This is not general clean-XFS or replay support.

The file service accepts a closed profile word only in its authenticated initial
source0 bootstrap: 0 is fresh-format, 1 is this pinned Linux profile. All other
values and nonzero reserved words are refused before allocation or block reads.
The existing process fixture's separate case 11 selects 1; case 10 and the existing
production `nvme` selector remain 0. A refused disk stays unavailable under `/disk`,
never falls back to RAM, and does not discard the independent RAM namespace.

The same production image has an explicit boot opt-in for the clean profile:

```text
-fw_cfg name=opt/aurora/storage,string=nvme-linux-6.12-clean
```

An absent selector remains RAM-only; exact `nvme` remains fresh-format. Unknown
strings, trailing NULs and malformed selectors fail closed, not back to RAM or a
different filesystem profile. Tag 4 retains the existing read-only authority and
handoff layout; word 152 is a closed profile 0/1 only under that tag. Production RAM
still requires zero there, and fixture case meanings are unchanged. Older
production v10 consumers reject profile 1 rather than interpreting it as fresh.
The admitted profile is captured once per boot, checked on runtime reattachment,
and retained across file-owner loss/restart. Clients cannot change it.
Clean-profile restart retention is source-reviewed; the actual owner-loss guest
checks currently use the default profile.

The short `6.12` selector names this format contract, not all Linux 6.12 releases
or an on-disk producer identity. Genuine producer evidence is pinned to
**Linux 6.12.107 x86_64**. Actual production used/wrapped boots exercise the
shipped cat/sort tools, cross-client committed copies and write denial with exact
serial/framebuffer checks; a genuine dirty boot refuses `/disk` while RAM remains
usable. All attached private images remain unchanged. Exact binary-byte
comparisons belong to the separate process-device case, not merely the production
file-size/line-length transcript. Default RAM and fresh-format guests also pass.

#### Reproducing the reference-media gates

These are opt-in tests of supplied reference media, not shipped 512-MiB images
or dependencies of the default suite. Start each independent history with a new
regular file:

```sh
python3 scripts/xfs_image.py IMAGE --mkfs /path/to/mkfs.xfs
```

The producer requires xfsprogs 6.13.0 and creates the bounded prototype above.
Attach only this disposable image to an isolated Linux 6.12.107 x86_64 VM, with
no NIC or host mount. Mount in the guest with `logbufs=2,logbsize=32k`. Open the
existing `hello` without creating/replacing its inode; for iteration `j`, write
64 bytes at offset zero, byte `i = (i * 37 + j + 11) % 256`, and `fsync` after
each write. Preserve `pattern` (9001 bytes, byte `i = (i * 37 + 11) % 256`) and
the supported root/inode features.

- `used`: one iteration (`j=0`), then `sync` and clean unmount.
- `wrapped`: sessions of 70,000 iterations (`j=0..69999`), cleanly unmounting
  between sessions and continuing the same image without reformatting until
  offline log inspection demonstrates wrap. A write count alone is not proof.
  The qualified history needed two sessions; its final UNMOUNT did not itself
  straddle the boundary (that case has separate synthetic coverage).
- `dirty`: one iteration, `sync`, then BusyBox `poweroff -f` in the minimal
  guest initramfs without unmounting (normal distribution shutdown may unmount).

Retain the guest write/fsync/unmount events and before/after image hashes. Use
`xfs_logprint` offline to distinguish CLEAN from DIRTY and inspect cycle/head
topology; clean histories must also pass `xfs_repair -n`. The dirty image is not
repaired before the refusal test. Synthetic sector rewrites are not genuine
Linux history. Hashes must remain unchanged by subsequent read-only checks.

With the existing images already built under `BUILD`, the supported NVMe model
under `NVME_PREFIX`, the production NVMe/graphics model
(`aurora-amdvi-command-stop-nvme-graphics-v1`) under `GRAPHICS_PREFIX`, and
`AURORA_BOOT_FIXTURE_PREFIX` pointing to clean firmware:

```sh
python3 scripts/kernel_nvme_smoke.py --tool-prefix NVME_PREFIX \
  --run-only BUILD/kernel-images/uefi/process-fixture \
  --process-xfs-clean IMAGE --xfs-history used
python3 scripts/kernel_production_smoke.py \
  --build-dir BUILD/kernel-images/uefi/production \
  --renderer BUILD/tests/graphical-terminal-host --nvme-prefix GRAPHICS_PREFIX \
  --xfs-image IMAGE --xfs-history used
```

Repeat with the corresponding image and `wrapped` or `dirty`. The history label
selects the expected oracle, not filesystem admission or producer provenance.
Both runners accept only a regular 512-MiB source, copy its held read-only file
descriptor into a new private image, attach only that copy read-only and verify
its whole-image hash after the guest is reaped. They never attach a caller's
path directly or accept a block device.

### Mounted reads

After admission, `read_file(name, sector_index)` selects a root name and requests
its inode again. The existing complete inode/extent checks run before requesting
file data. Holes/unwritten sectors return zero without reading backing data;
partial EOF sectors mask the tail. `sector_or_zero()` and `valid_bytes()` expose
nothing until `file_sector_ready`. End, absent names and invalid requests are
recoverable; metadata, protocol and I/O failures are terminal.

`open_file(name)` performs the same complete inode validation without reading
payload sectors; `file_size()` and `file_inode()` are available only after that
validation. `service.xfs` uses these facts for its separately owned 16-handle
table (device 3, handle slots 40–55). Its 504-byte reply buffer publishes no
partial result: a later sector failure or volume-generation change quarantines
the disk and suppresses all previously assembled bytes. Closing a handle or
ending a client preserves slot generations, so old IDs cannot alias a reopen.
The mount and table remain sibling owners; neither stores a device capability.
The `/disk` root is reserved even when the mount is absent or fails. This does
not disable the independent boot/overlay Store. Disk create/write operations
are denied; only supported root files are exposed.

`examples/xfs-fresh-cat.au IMAGE ROOT_FILENAME` is a running, source-owned hosted
consumer of this state machine through read-only `HostFiles` reads. Its operator
must keep the image stable; HostFiles does not itself grant exclusive volume
ownership. Tests compile this consumer once and use sparse **synthetic** images
assembled from the retained sectors, plus protocol/ownership cases in the
existing `block_io` driver. These sparse test inputs are not complete XFS images.
An actual populated mkfs image was separately read without mounting it on Linux.
The protected process fixture also connects this exact mount state to the sealed
`ReadOnlyBlock` grant and retained file owner: two clients read the 9001-byte
binary file over the protected QEMU NVMe transport, reject writes, and leave the
whole disposable image unchanged. This qualifies only the named fresh profile,
not general clean Linux XFS or read-write storage.

Authenticated supervisor control 15 requests startup admission with no active
file client and an empty request. It uses the same sector pump as lazy opens;
success is returned only after the complete log/root/inode gate. Missing,
unsupported, dirty or quarantined storage returns unavailable, never a fresh
mount grant or a reset. The production storage composition must complete this
operation within its explicit startup budget before advertising disk readiness;
ordinary runtime budgets and the RAM-only composition are unchanged.

`scripts/xfs_image.py IMAGE --mkfs /path/to/mkfs.xfs` creates a new disposable
512 MiB regular image using xfsprogs 6.13.0 and a prototype, without a host mount.
It holds the exclusively created inode open while mkfs uses its inherited fd;
an existing file or device path is never formatted. `/hello` contains 64 bytes;
`/pattern` contains 9001 binary fixture bytes, crossing 504/512/4096-byte read
boundaries. The hosted service driver is also run against this actual image;
its fast component rows use explicitly synthetic shortened-log sparse inputs.

Next dependencies remain broader supported clean-log/inode/namespace forms
and permission policy (X1). X2 must
then implement every advertised replay
item and cancellation/intent/orphan semantics against a disposable overlay with
interruption/replay idempotence checks. X3 requires transaction reservations,
allocation validation, ordered durable commit/flush, crash injection and
interoperability checks before exposing any read-write mount. Neither X2 nor X3
can be replaced by raw NVMe writes or the fresh-format read-only gate.


### Bounded inode recovery preflight

`fs.xfs_recovery` owns a 48 KiB copied-byte plan for one strict Linux 6.12.107
x86-64 profile. One complete log scan precedes at most 16 complete,
non-interleaved CORE-only transactions in a non-wrapped live interval of at most 1 MiB.
The root contains at most 16 supported regular files. Every root inode and home
inode is checked; every AG summary and orphan bucket is admitted, with exact
superblock summary equality and single-leaf INOBT allocation proof. Unknown
records, unsupported metadata changes, torn homes, missing commits and protocol
failures yield no planned writes, including failures after earlier conversions.
The unchanged read-only profile does not accept a dirty log.

A separate closed live-log mode admits exactly one root CORE+LOCAL transaction
that permutes the inode numbers of existing shortform directory entries. Names,
entry layout/type, parent, size, inode set and allocation remain unchanged; mixed
root/file transactions and duplicate or foreign references refuse. The original
and proposed root pass the same directory parser. The entire padded LOCAL region
is copied as Linux does, then the inode CRC is regenerated. This uses the existing
root cache and publishes one home sector, without increasing write authority.
The [Linux exchange fixture](../fixtures/xfs-root-exchange/README.md) supplies the
independent recovered-root golden. Actual disposable NVMe guests exercise forward
production recovery with shipped commands and the graphical console, plus reverse
recovery, clean/refused entry, root-home and orphan-body reentry. Four completed-
command cuts (first home write and each of three Flushes) recover on a fresh boot
from the captured disk. Each successful image matches the independently Linux-
accepted completion; only the root and two completion sectors change. The forward
production output also mounts cleanly in Linux without replay and passes repair.
These are emulator completed-command boundaries, not torn-write or physical
power-loss qualification.
This is recovery support, not a writable mount or an ordinary file commit API.

The pure converter restores only supported timestamp/change-count fields,
sets the committed record LSN and regenerates the complete inode CRC. It ignores
the logged dinode LSN, reapplies equal record LSNs and skips newer valid homes.
A ready plan exposes copied home sectors and deterministic clean-UNMOUNT body
then header sectors. Publication requires home writes and Flush, body and Flush,
then header and Flush, writer retirement, and independent read-only admission.
The caller must retain an exclusive stable volume and reserve the finite NVMe
command budget before its first write. Copied plan values carry no authority.

The [fixture recipe](../fixtures/xfs-core-redo/README.md#decompress-and-run)
provides small archived full-image inputs and independent completion goldens for
the opt-in device checks.

`services/xfs-recover.au` is the separate source consumer of the singleton
`WritableBlock` role. Its object and executable use Aurora's emitter/linker.
Private-copy modeling changes only the two expected inode homes and two
completion sectors; the unchanged Aurora reader accepts the result, and pinned
Linux mounts it clean without replay. Private NVMe process guests also pass
dirty recovery, completed-marker reentry and controlled refusal. Completed-command
cuts after the first home write and each of the three Flush boundaries pass
fresh-process reentry; the second Flush cut produces the actual orphan body,
and reentry changes only its header. These are emulator command-boundary checks,
not physical power-loss or general XFS recovery qualification. Explicit production
recovery also passes dirty, completed-marker and late-record-refusal rows through
the independent readonly source owner, shipped file commands and graphical
console; ordinary execution cannot obtain the writer. A private console-owner
fixture also performs two real full mounts around one actual commit/exit loss,
with a fresh owner generation, missing volatile note, healthy console and
unchanged image. The writer and backend are initialized only once. This is a
readonly-remount/no-remint check, not full HostFiles continuity across loss.
Further full scans can exhaust finite command IDs; the backend quarantines
rather than resetting the queue or reminting authority.
Recovery recognizes only the exact
full-sector orphan completion body immediately after its admitted old header.
A recovery-only topology overlay then repeats all original log, allocation and
home checks; the unchanged read-only mount still refuses that intermediate disk.
Other torn or unsupported states refuse without output. A valid completed marker
also undergoes full metadata admission, returns no data writes, and requires one
successful Flush before writer retirement and independent read-only admission.
