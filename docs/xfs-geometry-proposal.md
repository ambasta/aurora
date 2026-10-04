# Next executable XFS slice: bounded header geometry facts

2026-10-03. Proposal only. No Aurora implementation, compiler, kernel, main-tree
source, device or image changes are part of this assignment. M018 stays frozen.

## Decision and acceptance boundary

Add one original Aurora library module, `fs.xfs_geometry`, after M018. It consumes
the same exact 512-byte readonly span as `fs.xfs_probe`, checks a conservative
v5 header profile, and returns copied field/geometry facts with recoverable
failure reasons. It does not read a device, traverse any metadata or open a file.
The existing `fs.xfs_probe` source, exports, report behavior and tests stay intact.

The dependency is already present: readonly whole-array byte spans, checked
LE/BE16/32/64 readers, CRC32C, u64 division/remainder/bit operations, bounded
`std.bit_width`, closed enums and copied composed class values. No compiler
language extension, general allocator, DMA, NVMe, mutable span, C ABI or C code
port is needed. Only the new module uses the new profile policy.

The observable gate is native Aurora execution of the inspector, consuming all
returned fields and errors, against an independent unbounded-integer oracle and
the preserved real header, with repaired-CRC malicious headers, recoverable
library validation instead of input-triggered arithmetic/bounds traps,
byte-preservation checks and independent review. This document has not
implemented or passed that gate. It advances part of X0, not X1.

## Public API shape

Recommended exported entry point:

`inspect_xfs_v5_512_geometry(builtin::span<const u8> bytes) -> XfsGeometryReport`

Recommended status enum:

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

Use private fields and ordinary public constructors/accessors, as existing
reports do. The report contains:

1. status and issue (2 scalar leaves)
2. the unchanged `XfsProbeResult`, returned by value from `probe()` (5 leaves)
3. raw `versionnum`, `features2`, `bad_features2` observations (3 leaves)
4. four `unsupported_*` masks and four `unknown_*` masks (8 leaves)
5. one copied `XfsGeometryFacts` value (24 leaves, listed below)

This is 42 scalar leaves. The grouping below uses three class levels and at most
six source parameters per constructor, respecting the existing parameter limit
as well as the 64-leaf/four-level limit. Check actual generated layout and metadata
rather than accepting the arithmetic here as evidence. All constructor arguments
are ordinary values; there is no borrowed span stored in a result or returned view.

The 24 facts are all u64, with names that state their units:

`block_bytes`, `sector_bytes`, `inode_bytes`, `inodes_per_block`, `block_log`,
`sector_log`, `inode_log`, `inodes_per_block_log`, `ag_block_log`, `data_blocks`,
`claimed_data_bytes`, `claimed_data_sectors`, `ag_blocks`, `ag_count`, `ag_bytes`,
`last_ag_blocks`, `last_ag_start_bytes`, `directory_block_bytes`,
`log_start_encoded`, `log_ag`, `log_ag_block`, `log_start_bytes`, `log_bytes`,
`effective_log_sector_bytes`.

Do not implement a 24-argument facts constructor or an oversized report
constructor. Use these ordinary copied groups, with each listed field an u64:

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

The deepest containment is report -> facts -> scalar-fact group, or report ->
diagnostics -> masks. Return copied groups with const accessors and use explicit
typed locals for intermediate method results, matching the current class-value
subset. Empty/failed facts are made from fully initialized all-zero groups.
No constructor, helper function, generic result or callback may exceed the
existing source parameter count to accommodate this API. No compiler change.

`facts()` returns a copy. Library-produced unsuccessful reports contain an
all-zero facts value; accessors never project partially checked geometry. Raw
observations and diagnostic masks remain explicitly untrusted. After a rejected
old probe, new raw observations/masks are zero; the nested old probe preserves
its existing diagnostic behavior. A caller can construct arbitrary reports, so
even a success enum is not a validation certificate or an I/O capability. Do not
add APIs that accept one of these reports as authority to access a volume.

## Exact input fields

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

## Feature policy: recognition is not operational support

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

## Check order and fact invariants

Specify and test first-error precedence; no diagnostic scan of arbitrary length.

1. Run the old probe once. If it fails, stop new interpretation. In particular,
   changed geometry with an unrepaired CRC must remain `probe_rejected`.
2. Decode the bounded new observations and all mask diagnostics. Check required
   legacy flags, then excluded legacy/features2 bits. Report NEEDSREPAIR as
   `offline_state_indicated/needs_repair`; otherwise reject extended masks outside
   the policy and missing local FTYPE. This ordering is part of the API.
3. Reject mirror mismatch; report nonzero inprogress as `offline_state_indicated`
   (offline operation indication). This function is for a caller-provided primary
   header. It cannot verify the caller actually obtained bytes at device offset 0.
   Do not apply this primary-only rule to secondary-superblock APIs later: mkfs
   can leave secondary inprogress fields set.
4. Reject nonzero rblocks as unsupported realtime and zero logstart as unsupported
   external log. Reject unit/width nonzero, logsunit greater than 1, nonzero
   qflags or nonzero miscellaneous flags as unsupported layouts. These conservative
   exclusions are Aurora scope choices, not an assertion the fields are invalid
   in XFS. Both logsunit 0 and 1 are accepted unstriped representations.
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
12. Return `header_geometry_consistent` only after every above check succeeds.

There is intentionally no assertion that a fixed 10 MiB log is large enough.
Linux's v5 mount performs a separate feature-dependent transaction-reservation
minimum-log calculation. That and the full static metadata allocation map are
not implemented here. The header-range check excludes AG header sectors but
does not establish non-overlap with allocation trees, inodes or allocated data.

## Overflow-safe arithmetic contract

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

## Preserved real fixture and canonical transport

The only real mkfs-generated input available here is the preserved primary
512-byte header. Do not relabel synthetic CRC-repaired variations as real
filesystems. The full image and unseen log/AG/inode bytes were not inspected by
this assignment, and are unnecessary to this proposal.

Canonical source transport remains `fixtures/xfs-offline/superblock-v5-512.hex`:
exactly 1728 ASCII bytes, 32 rows, 16 lowercase two-digit bytes per row, ordered
four-digit offsets 0000..01f0, two spaces after offsets, one space between byte
tokens, final LF on every row. Read at most 1729 bytes. Reject missing, excess,
duplicate, unordered, malformed-width, non-ASCII and noncanonical rows. Reuse
the existing bounded transport checker and all its 17 negative controls.

- Decoded bytes: 512; SHA256
  `55ad821909c312048d9936a74c8904cd25f97aa190b48ae0004b03eaffdc6586`
- Canonical transport SHA256
  `d1d3fbc3f8b693d1c0ddf395e92b136a81b2a5d30b9e3cdec36addd580d42986`
- Producer: recorded xfsprogs Debian package 6.13.0-2+deb13u1, mkfs.xfs 6.13.0;
  existing provenance retains package/executable hashes and exact command.
- Preserve the provenance caveats: original mkfs exit code was not separately
  retained; the later read-only xfs_db exited 0. Package-index hashes matched;
  Debian Release signatures were not independently verified. The original
  command explicitly chose CRC/UUID/block/sector/label but used other defaults;
  preserve these observed bytes rather than pretending all options were pinned.

Expected observations, freshly decoded from the canonical bytes:

- B=4096, S=512, inode=512, inopblock=8, logs 12/9/9/3
- D=131072, A=32768, N=4, agblklog=15
- data bytes=536870912, data sectors=1048576, AG bytes=134217728
- last AG blocks=32768, last AG byte start=402653184
- versionnum=0xb4a5, features2=bad_features2=0x18a
- extended masks=0/0x0f/0x2b/0; unsupported and unknown masks all zero
- internal logstart=65543, encoded as AG 2/block 7; logblocks=16384
- log byte start=268464128, log bytes=67108864, effective sector=512
- logsectsize/logsectlog=0/0; logsunit=1; unit=width=0
- rextsize=1; rblocks/rextents/rbmblocks/rextslog/frextents=0
- inoalignmt=8, spino_align=4, inprogress=0, imax_pct=25
- qflags/flags/shared_vn/dirblklog=0; directory bytes=4096
- rbmino=129 and rsumino=130 are nonzero despite no realtime area; don't reject
  them or infer anything about their pointed-to inodes.
- CRC raw bytes c7 13 71 b6; little-endian numeric CRC 0xb67113c7.

The accompanying `observed-fixture-facts.json` records the read-only extraction
and arithmetic, not a native implementation acceptance receipt.

## Required acceptance cases

All geometry mutations below must recompute CRC using the independent whole-
message GF(2) oracle, with bytes 224..227 zeroed. Also retain paired mutations
without repairing CRC, which must stop at the original probe. A case passing
CRC does not make its imagined remainder of filesystem valid.

Positive native cases:

1. Exact preserved real header, every 24-field output plus diagnostics and old
   probe unchanged; complete input equality after calls, including repeat calls.
2. Synthetic non-power-of-two AG: A=30000, N=4, D=120000, agblklog=15,
   log encoded AG2/block7=65543, length16384. Expected physical start block60007,
   byte start245788672. This catches treating logstart as a linear address.
3. Synthetic short last AG: A=32768, N=4, D=98368, last length64; log stays AG2.
   Last start402653184, data bytes402915328. Also test last length A and A-1.
4. All admitted block/inode exponent pairs, adjusting inopblock, AG size,
   realtime-extent size, sparse alignment and log placement consistently.
   Test inopblog0 when inode equals block. Do not claim these are real images.
5. Valid log declarations both absent-SECTORBIT 0/0 and present-SECTORBIT 512/9;
   logsunit0 and1. imax_pct0/100. Directory exponent endpoints. SPINODES absent
   with zero spino_align and present with zero or valid divisor spino_align.

Negative/adversarial native cases:

- Every original probe outcome, lengths below and above512, wrong endian magic,
  v4/unsupported sector sizes, bad CRC/padding. Existing probe still accepts any
  raw masks when only integrity is valid; new rejection cannot alter that ABI.
- Each required legacy/features2 bit removed; each excluded bit added;
  mismatched features2 mirror; every single bit of all four masks; NEEDSREPAIR;
  known log0x1 vs unknown log0x2; unknown high bit0x80000000 in every mask.
- Nonzero inprogress stays an offline-state diagnostic, never a dirty-log result.
  External log, realtime, stripes, quota/misc flags are unsupported layouts.
- Block/inode size/log mismatch, zero sizes, byte logs63/64/255; inode>B;
  inopblock/inopblog disagreement; directory sum beyond16. No invalid shift can
  execute before its guard. 256-byte inode produces the documented unsupported
  status instead of a fabricated general-format corruption claim.
- A/N/D zero; A bytes below16MiB or above1TiB; agblklog floor-vs-ceil mismatch;
  D just below/above each count boundary; final length0,1,63,64,A,A+1; quotient
  above u32 and q=max-u32 with remainder. No division by zero or truncation.
- Consistent enormous geometry with B4096,A=268435456,N=4294967295,
  D=1152921504338411520 must return size_unrepresentable before D*B; nominal
  AG is exactly1TiB and counts fit their disk fields. Also test D=2^64-1 to
  catch the tempting ceil-add overflow, plus U64_MAX in logstart.
- Log g=N, huge high AG bits, a=A or a beyond short tail, log end crossing AG,
  log length0/max/max+1, maximum byte-size edge, log beginning in AG header
  blocks, last valid one-block tail range and one-past end. Adversarial F with
  low address bits in the encoded gap of a non-power-of-two AG must fail even
  when a naive linear check appears in range.
- Realtime count contradictions with rblocks0, invalid rextsize0 or product
  limits, invalid sparse alignment/divisor, shared_vn nonzero, imax_pct101/255.
- Multi-fault inputs verify first-error precedence. All loops and reads remain
  bounded by512 input bytes, fixed field count and at most32 AG bit-width steps.

Harness and integration gates:

- Use a separately authored Python unbounded-integer/schema oracle, raw u64
  native outputs and expected closed-enum predicates. Consume every result field;
  merely compiling the new module is not a test. Test release and instrumented
  bootstrap compilers; retain their source/compiler hashes and limits (generated
  Aurora code is not thereby sanitizer-instrumented).
- Generate bounded deterministic and seeded hostile512-byte samples, repaired
  CRC variants and targeted boundaries. Native termination by SIGILL, SIGFPE,
  SIGSEGV, timeout or unrelated error always fails; no trap is an acceptable
  malformed-header result. Record seed/count and retain minimal failures.
- Check class privacy, copied-value independence, result size/layout metadata,
  no span escape, and unmodified input. Publicly fabricated reports grant no I/O.
- Mutation controls must catch deleting each overflow/zero/shift/range guard,
  replacing ceil with floor, truncating expected AG count, treating encoded log
  address as linear, accepting unknown bits, ignoring legacy feature requirements,
  discarding last-AG shortening and mistaking log flags for cleanliness.
- Run old `make -C compiler test-storage`, existing real-fixture/transport tests,
  new focused native/oracle tests, then `make test` on the final candidate.
  Independent review must reproduce the hostile boundaries and real fixture.
  No kernel change is planned; if scope reaches kernel code, the project's actual
  emulator gates become mandatory. Missing/not-run stages stay explicit.

## Smallest implementation delta for the compiler owner

After M018 closes, an isolated candidate needs: one Aurora module, one focused
native/oracle suite plus a make-test hook, a running example that consumes the
report, this API contract and a factual provenance/fixture receipt. Update the
library README, storage README/roadmap and completeness matrix in the eventual
integration. Fix the stale wording that describes all geometry as future work,
without promoting the result to an X1 mount capability.

Do not touch old probe status values, its raw-mask semantics or constructor;
do not change std.binary/std.checksum/compiler syntax; do not add unused resource
scaffolding, device reads, mounts, repair, formatting, replay or writing. Keep
generic AG-range queries and arbitrary sector sizes for a later reviewed slice.

## Primary sources, all exact Linux v6.16 commit

Commit: `038d61fd642278bab63ee8ef722c50d10ab01e8f`. Retrieval: authorized
read-only GitHub fetches at that commit, 2026-10-03. Existing provenance was
checked and matching blob identities retained. Third-party implementation bodies
are research references only; no upstream implementation is copied to Aurora.

| Source | Git blob SHA | Relevant facts/locations |
|---|---|---|
| [xfs_format.h](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_format.h) | 9566a76233654004d54f47aac17ac60dd8a6629a | Disk fields193..285; legacy bits29..87; v5 feature categories/masks348..444; AGFL688..689; encoded/linear address distinction702..711; inode size1081..1084; RT extent limits1306..1308; inode chunk1574..1576 |
| [xfs_sb.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_sb.c) | 711e180f9ebb835296afda1949f320d3425ecca6 | Required v5 legacy flags42..73; unknown feature policy196..244; RT geometry275..307; avoid read-time summary/LSN claims313..379; sparse relations500..550; scalar/AG/log geometry593..757; decoding801 onward; CRC first1076..1111 |
| [xfs_types.h](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_types.h) | f6f4f2d4b5dbf50012d0041cc6685421a3e2e07b | Count/address type distinctions11..39; block/sector bounds68..83 |
| [xfs_fs.h](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_fs.h) | 12463ba766da053530e19b34c6a8344c67da3cd8 | Nominal AG bounds, final64-block minimum, max log blocks/bytes259..282 |
| [xfs_ag.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_ag.c) | e6ba914f6d060711806cd60d9e6a77c6c02b835b | Short final-AG calculation137..157; internal-log treatment338 onward |
| [xfs_types.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_types.c) | 1faf04204c5ddca5f45ff00c5dfaf893b5848b1c | AG address and same-AG extent bounds20..76 |
| [xfs_log.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/xfs_log.c) | 793468b4d30d42dc368602770be97eda424919cc | Separate reservation-derived minimum log615..644; default log-sector and logsunit0/1 behavior1398..1433 |
| [xfs_super.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/xfs_super.c) | bb0a82635a770d48a8562b994fe13eb28b922069 | NEEDSREPAIR and primary-only inprogress treatment1803..1823 |
| [xfs_mount.c](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/xfs_mount.c) | 0b690bc119d7caae1e33f03b7b0d038b2d856e6d | Historical features2/bad_features2 reconciliation849..854; not copied into the readonly inspector |

One exploratory request for `fs/xfs/scrub/sb.c` returned404; it is not used as a
source. No access denial was bypassed. Original CRC/source pins remain in the
repository's existing provenance. The checksum is error detection, not
authentication, and correct geometry facts say nothing about unseen bytes.
