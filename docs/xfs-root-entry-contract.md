# Indexed read-only XFS root entries

`fs::entry_at_xfs_v5_512_root(superblock, inode, index)` extends the existing
offline root lookup with indexed access to the same restricted shortform root
directory. The two input arguments are readonly whole-array byte spans; `index`
is an exact i64. It returns a copied `XfsRootEntryReport` and retains no view.

The dependency is the existing complete header, geometry, inode and directory
validator. The acceptance gate is the full affected 203-case lookup regression,
the existing copied-report API gate and new independent indexed-entry checks.
The old lookup's statuses, issues and first-error ordering must remain unchanged.
Focused native execution and independent review passed on the explicitly reused
compiler. See the [results and limits](#focused-validation-results).

## Admitted format

All [existing root-profile restrictions](xfs-root-contract.md) remain in force:
the exact admitted v5 geometry, a 512-byte v3 local-format root inode, four-byte
entry inode numbers, at most 16 entries, the same feature/flag exclusions, and
the same complete checks for CRC, identity, names, duplicate entries, saved
offsets, exact payload consumption and projected directory-block footprint.
There is no new feature-mask admission or on-disk format interpretation.

The implementation shares validation with name lookup. Every directory entry,
including entries after the requested index, must validate before returning an
entry or end marker. An early valid entry cannot hide a malformed later entry,
duplicate name or trailing payload bytes.

## Status and precedence

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

## Copied result and raw names

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

## Test and qualification boundaries

The preserved empty/named superblocks and inodes keep their exact historical
fixture hashes. The named fixture independently identifies `alpha` as inode 131,
type 1 and `docs` as inode 132, type 2. The new gate also exercises all existing
203 reference inputs, every admitted synthetic entry, malformed late entries,
end/error precedence, raw name bytes, copies, masking, layout and API rejection.

The ordinary root runner now checks the current module and records its input
hashes, instead of requiring one historical implementation hash. Compiler
identity selection and fixture hashes remain mandatory in that runner. The
historical implementation hash and its prior qualification remain recorded in
the original contract; this changed implementation needs fresh scoped results.

This is an offline metadata operation. It does not read file contents, follow
paths, establish allocation or actual target type, open a device, mount a
filesystem, replay a log or provide persistent storage. CRC is not authentication.

## Focused validation results

Independent source review and two explicitly scoped native runs passed.

- Earlier compiler: complete 203-case lookup regression (2,233 u64 observations),
  the 77-observation/12-negative API gate, and all 912 indexed-entry cases plus
  five rejection fixtures in both normal and Python optimized modes.
- Current shared-frontend/lossless-lexer compiler, built by Meson: all 912 entry
  cases/five rejection fixtures under Python optimized mode, six lookup
  compatibility cases (66 observations), and the 77-observation/12-negative API
  gate. The full 203-case result is not attributed to this newer compiler.

The 912 cases include 905 calls to indexed access and seven copied-report, layout
and masking checks. Every rejection fixture checks both an absent and an existing
output. Source and compiler pins matched throughout; all commands and outer
processes exited zero and owned child cleanup was quiescent. Independent evidence
review verified every retained lookup/API scalar and rejection product. Indexed
entry products are temporary: its retained evidence is the reviewed runner,
passed manifests and logs, rather than a separate per-case raw corpus.

The current-compiler replay was composed on `46743cd1`. The final join preserves
the subsequent `78d265fd` fast-profile changes; those affect routing/docs rather
than this library, its runners or compiler implementation. Result wording and
that routing/docs join do not borrow additional test coverage. Exact source,
compiler and receipt identities are retained with the checkpoint backup.

No full aggregate, sanitizer, emulator, filesystem, device or hardware
qualification was repeated for this library increment.
