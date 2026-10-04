# Aurora storage

The native NVMe object/extent filesystem and a separate XFS on-disk compatibility
backend are required project targets. Neither is a working target filesystem yet.

The reviewed [requirements](design/requirements.md), [traceability](design/traceability.md)
and [staged roadmap](design/roadmap.md) preserve all 56 supplied sections and the
additional XFS request. XFS read-write remains the destination; clean read-only
access and validated replay are prerequisite gates. No C ABI or Linux kernel
implementation is introduced by this plan.

The [host-only crash model](design/model/README.md) is executable design evidence,
not a disk driver, durable storage engine, mount implementation or hardware proof.
It models a bounded transaction and checks deliberately broken persistence
protocols. See [parent checks](design/evidence/parent-final-verification.txt).

Current next work is checked endian/CRC32C parsing and a narrowly scoped XFS
header-integrity probe, alongside kernel DMA/IOMMU and NVMe prerequisites.
No user disk is opened, mounted, repaired or formatted by these tests.
