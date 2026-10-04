# Primary sources and research notes

Accessed 2026-10-03. The requirements in this package are Aurora proposals;
citations establish underlying device/format facts or prior research, not that
Aurora already implements them. No third-party implementation code is copied
into the target. Any future code/test reuse requires a pinned source and license
review. Changing upstream master branches are background, not frozen baselines.

## NVMe

### N1. NVM Express NVM Command Set Specification 1.3

[Official ratified PDF, 2026-07-31](https://nvmexpress.org/wp-content/uploads/NVM-Express-NVM-Command-Set-Specification-Revision-1.3-Ratified-2026.07.31.pdf).
Sections 2.1.4, 3.3.6 and 5.3 cover write atomicity, Write/FUA and protection
information. Power-fail atomicity has size and boundary conditions. FUA completion
establishes persistence for its associated data/metadata. PI behavior depends on
format and command fields; it is not a native object-version protocol.
Aurora's two-fence transaction and identity-bound integrity are derived designs.

### N2. NVMe Base specification and Flush semantics

[Official version catalog](https://nvmexpress.org/specification/nvm-express-base-specification/)
lists Base 2.4 (2026-07-31 ratification) as current at the access date.
[The Base 2.4 PDF](https://nvmexpress.org/wp-content/uploads/NVM-Express-Base-Specification-Revision-2.4-Ratified-2026.07.31.pdf)
exceeded the web reader's size limit; its full text was **not** inspected here.
Before driver implementation, obtain and pin the complete applicable Base,
NVM Command Set and PCIe transport revisions and errata.

[Official NVMe 1.1 errata, Flush correction](https://www.nvmexpress.org/wp-content/uploads/2013/04/NVM_Express_1_1_errata.pdf)
explicitly scopes flush coverage to commands completed before flush submission.
This is a historical primary reference for the ordering issue, not a claim that
Aurora's supported controller profile is NVMe 1.1. The proposed conservative
protocol waits for writes before flushing and waits for the dependency fence
before issuing a commit. CPU ordering alone cannot provide that protocol.

### N3. Flexible Data Placement

[NVM Express technical introduction](https://nvmexpress.org/nvmeflexible-data-placement-fdp-blog/)
describes lifetime-related host placement hints and reducing write amplification.
The [Base 2.1 specification](https://nvmexpress.org/wp-content/uploads/NVM-Express-Base-Specification-Revision-2.1-2024.08.05-Ratified.pdf)
has publicly indexed normative excerpts describing placement-handle to reclaim
unit-handle mappings and invalid placement identifiers. Full retrieval of that
PDF was unavailable in the web reader; use the complete pinned specification
for implementation. FDP support on the target laptop's SSD is unverified.

## XFS

### X1. On-disk structures and compatibility flags

[XFS Algorithms & Data Structures](https://www.kernel.org/pub/linux/utils/fs/xfs/docs/xfs_filesystem_structure.pdf)
documents superblock/feature masks (chapter 13), logs (chapter 14), inode/extent
and directory representations. The format uses field-specific endian rules;
log item payloads have architecture-related format distinctions. This living
document is not alone a complete current feature oracle.

[Linux v6.16 xfs_format.h](https://raw.githubusercontent.com/torvalds/linux/v6.16/fs/xfs/libxfs/xfs_format.h)
is a pinned upstream cross-check for on-disk field types and expanded feature
definitions. [Its verifier](https://raw.githubusercontent.com/torvalds/linux/v6.16/fs/xfs/libxfs/xfs_sb.c)
illustrates the breadth of geometry and feature validation needed beyond magic
and checksum. No Linux implementation reuse or C ABI is implied.

For the proposed narrow X0 header/checksum fixture, a coherent source set was
subsequently retrieved through the read-only GitHub connector at exact commit
`038d61fd642278bab63ee8ef722c50d10ab01e8f` (v6.16, tag object
`8ec6d99a41e3d1dbdff2bdb3aa42951681e1e76c`). The five files and Git blob hashes
are recorded in `evidence/xfs-v6.16-provenance.json`. Together the
[CRC helper](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/libxfs/xfs_cksum.h),
[buffer helper](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/xfs_buf.h),
[superblock read path](https://github.com/torvalds/linux/blob/038d61fd642278bab63ee8ef722c50d10ab01e8f/fs/xfs/xfs_mount.c),
format and verifier establish CRC32C seeded with all 32 bits set, the stored
checksum field treated as four zero bytes, final complement and little-endian
storage, covering the complete declared superblock sector. The version mask is
0x000f. This does not make a checksum-valid header a mountable filesystem.
Earlier mixed-version references were research leads, not this fixture's oracle.

### X2. Self-describing metadata

[Kernel XFS self-describing metadata design](https://docs.kernel.org/filesystems/xfs/xfs-self-describing-metadata.html)
explains CRC32C, filesystem/owner/location identity and LSN validation, including
the distinction between individual-block and cross-structure correctness.
The native engine's checksum/identity/generation requirements are Aurora design
choices informed by this lesson, not copied XFS disk formats.

### X3. Logging and deferred operations

[Kernel XFS logging design](https://docs.kernel.org/filesystems/xfs/xfs-delayed-logging-design.html)
describes write-ahead logging, logical/physical records, reservations, log forcing
and intent-based completion of larger operations.
[Online fsck design](https://www.kernel.org/doc/html/v6.12/filesystems/xfs/xfs-online-fsck-design.html)
adds useful discussion of replaying deferred work and log-incompatible features.
These establish why a native append-only commit parser is insufficient for XFS
recovery. They do not select the future Aurora feature allowlist.

### X4. No-recovery mounts

[Upstream xfs(5) manual as rendered by man7](https://www.man7.org/linux/man-pages/man5/xfs.5.html)
warns that skipping replay on a dirty log may expose inconsistent/unavailable
files and requires a read-only mount. This is why the proposed initial Aurora
gate rejects dirty logs rather than claiming clean read-only support for them.

### X5. Repair versus replay

[Upstream xfs_repair manual source at a pinned xfsprogs tag](https://kernel.googlesource.com/pub/scm/linux/kernel/git/dgc/xfsprogs-dev/+/refs/tags/v5.7.0-rc1/man/man8/xfs_repair.8)
documents no-modify checking, failure on a dirty log, and possible data loss
from log zeroing. [The current rendered manual](https://man7.org/linux/man-pages/man8/xfs_repair.8.html)
was cross-checked. A host Linux mount/recovery is a separate replay oracle;
xfs_repair is not a replay implementation.

### X6. Filesystem test tooling

[xfstests README at a pinned upstream developer revision](https://kernel.googlesource.com/pub/scm/linux/kernel/git/djwong/xfstests-dev/+/c74266f99d1f6322da4d1009c85c6e2556ec1d38/README)
describes tests that destroy scratch contents. Aurora testing therefore confines
such tools to disposable guest images, records the chosen version/scenario set,
and adapts semantics deliberately. This package does not run xfstests or claim
its Linux dependencies run natively on Aurora.

## CXL and comparison transport

### C1. CXL memory persistence

[CXL 3.0 specification, section 9.8](https://computeexpresslink.org/wp-content/uploads/2024/02/CXL-3.0-Specification.pdf)
specifies a persistent flush protocol and persistence-domain responsibilities.
[Consortium persistent-memory explanation](https://computeexpresslink.org/blog/questions-from-the-compute-express-link-cxl-supporting-persistent-memory-webinar-2407/)
provides context. A load/store-accessible CXL region is not automatically durable;
the actual region/platform persistence contract must be qualified. Aurora has
no implemented CXL backend or qualified CXL hardware.

### P1. SPDK NVMe driver documentation

[Official SPDK NVMe documentation](https://spdk.io/doc/nvme.html)
describes asynchronous queue pairs, exclusive queue ownership and direct data
transfer. It is useful for the performance-baseline methodology. SPDK is neither
Aurora's target implementation nor evidence of safe unrestricted userspace DMA.
Its benchmark numbers cannot be transplanted to an unmeasured Aurora system.

## Research, with limits on applicability

### R1. NOVA (FAST 2016)

[Authors' USENIX paper/presentation](https://www.usenix.org/conference/fast16/technical-sessions/presentation/xu).
Study per-file logs, volatile indexes and crash recovery on byte-addressable
nonvolatile memory. This motivates separating durable representation from hot
indexes. The medium and persistence primitives differ from NVMe NAND.

### R2. Strata (SOSP 2017)

[Author-hosted paper](https://homes.cs.washington.edu/~tom/pubs/sosp17-final207.pdf).
Study cross-media placement and digestion of logs into shared storage. Aurora
may experiment with analogous policy separation but does not inherit Strata's
security model, prototype performance or Linux interfaces.

### R3. SplitFS (SOSP 2019)

[Authors' paper](https://arxiv.org/abs/1909.10123).
Study reducing software overhead for persistent-memory operations by splitting
the data and metadata paths. This informs measurements; it does not establish
that native NVMe operations can safely omit capability checks or persistence
ordering.

### R4. SquirrelFS (OSDI 2024)

[Authors' USENIX paper/presentation](https://www.usenix.org/conference/osdi24/presentation/leblanc).
Study typestate-based update ordering for persistent-memory crash consistency.
Aurora may investigate ownership/state transitions for durability evidence after
its resource/type system supports them. The paper does not prove Aurora's
compiler or a new NVMe/XFS implementation correct.

### R5. ScaleLFS (FAST 2025)

[Authors' USENIX paper/presentation](https://www.usenix.org/conference/fast25/presentation/ha).
Study parallel cleaning and contention on commodity SSDs. Its CPU and workload
tradeoffs motivate aged, sustained measurements. It does not justify a blanket
claim of zero foreground GC cost or better laptop battery behavior.

## Local provenance and limits

The input copy is byte-identical to the attached requirements. Aurora baseline
facts come from the inspected local project documentation listed in README.md.
Those facts are checked against the recorded milestone, not assumed from a
future roadmap. The directory is not a Git checkout, so no Git revision can
honestly identify it; source hashes are recorded in local evidence instead.
At research time Python 3.12.14 and pdftotext were present; mkfs.xfs and xfs_db
were absent. No xfsprogs, NVMe command, block device or physical disk test ran.
