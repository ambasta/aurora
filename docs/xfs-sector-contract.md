> The [storage consolidation](storage-consolidation.md) migrates this consumer and its fixture constructors.
> Its fresh 110-case/five-rejection gate passed in both Python modes on the owned-field compiler.
> The older results below still describe the earlier PR54 source.

# Checked XFS sector-header consumer

The next dependency after copied sector I/O is preserving I/O failures while
checking an XFS header against the source's advertised capacity. The acceptance
gate is native execution of the preserved real superblock through checked RAM
I/O, independent Python geometry expectations, capacity boundaries and failed
report masking. This increment changes no compiler or existing XFS validator.

## Operation and ordering

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

## Reports and masking

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

## Fixture and scope

The real preserved 512-byte mkfs superblock claims 1,048,576 sectors. Loading that
header into `RamSectorDevice`, freezing it and reading it through the public API
must return `source_too_small`: the implemented RAM device advertises one sector.
It is never described as a filesystem mount or a usable volume.

Success/capacity-boundary tests construct geometry values and copied read
reports around the same header. Such values exercise the arithmetic contract;
they are not evidence of an implemented million-sector device. CRC-repaired
mutations remain synthetic headers. No missing image or file bytes are invented.

This consumer does not verify root placement, inode allocation, log cleanliness,
filesystem consistency, later reads, file contents or persistent storage. A
successful header check does not establish mountability or readonly filesystem
safety. CRC is not authentication. No kernel, physical device, sanitizer or full
native aggregate qualification follows from focused hosted execution.

## Separate dependency: a scoped multi-sector window

The proposed readonly window is now implemented as a separate focused candidate
on the consolidated API. Its [contract](sector-window-contract.md) defines the
single free function, length/address error order, signed-request limits,
independent owned result and boundary/copy tests. It provides window bytes, not
a full-device handle or source-capacity provenance. Its verification is separate
from the historical XFS consumer results below.

A complete small-file read also needs genuine child-inode and file-data fixtures,
a checked inode-to-sector request plan, v3 regular-file validation and the
supported extent-mapping subset. Existing recovered fixtures contain only two
superblocks and two root inodes. A new disposable mkfs image and readonly
extraction can provide missing bytes; existing checks do not establish them.

## Validation

Run `python3 -B tests/compiler/xfs_sector.py build/aurorac`, or select
`xfs-sector` in the Meson `bytes` suite. The runner preserves full-width scalar
checks and rejection/output-preservation checks in optimized Python too. The
existing `xfs_geometry.py`, `block_io.py` and `sector.py` runners remain the
focused dependencies. Registration in the complete compiler recipe does not
claim that aggregate was rerun.

All 110 native cases and five rejection fixtures passed in normal and optimized
Python modes. This includes the real one-sector rejection, exact/either-side
capacity checks, a large synthetic claim of 36,028,797,018,963,960 sectors,
full-width source counts, every geometry status/issue, actual backend signed
endpoint failures, copied reports and nonzero-diagnostic masking. Source review
accepted the corrected candidate before execution.

The complete unchanged geometry dependency passed 586 headers and 25,198 raw
observations, 40 layout observations, eight copied/fabricated cases, 17 rejection
fixtures and 51 detected mutations. Its 24 source-audited redundant guards remain
source audits. Block I/O passed 38 cases/13 rejections and its example; owned
sectors passed 43 cases/nine rejections and their example, both in optimized Python.

The outer process exited zero. All 681 tested source-file hashes and the reused
PR51 compiler hash remained unchanged through completion:
`e97baada523ec30ac49e7f3e4c17b13ae6d30b79d9f157f07f9a87c2bd4ab8ba`.
All 18 compiler-directory C++ source/header files matched the PR52 base; no
compiler was rebuilt. Owned temporary outputs were cleaned and no test children remained.
The new runner retains reviewed source and pass logs, not a per-case native
product corpus. The geometry runner retains its detailed existing receipts.
Independent final evidence review accepted this original focused result. It does
not qualify a full aggregate or the subsequent separate multi-sector-window
implementation.

### PR53 compiler compatibility

The final source preserves the merged PR53 stack-probe implementation and its
registrations/docs. A separate focused replay passed the new consumer's 110
cases and five rejection fixtures in both Python modes on the qualified probe
compiler `762ba74b8b58d4c6ae7c335507a7b06560a90f44c98d268defa36e086fa41630`.
The outer process exited zero; all 685 composed source hashes and the compiler
hash held through completion, with empty owned temporary storage and no remaining
test children. No compiler was rebuilt. The complete geometry, block-I/O and
owned-sector dependency results above belong to the earlier compiler, not this
compatibility replay. Independent review accepted the composition and compatibility
evidence.
