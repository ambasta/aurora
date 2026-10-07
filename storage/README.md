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

The Aurora library now provides checked endian/CRC32C parsing, narrow offline
XFS header/root probes and owned sector buffers. A bounded
[sector-I/O candidate](../docs/block-io-contract.md) adds one copied RAM sector,
checked write failures and explicit unsupported durability. Focused native
validation passed; independent final source and evidence review accepted this
focused scope. Kernel
DMA/IOMMU, NVMe and actual filesystem I/O remain prerequisites.
No user disk is opened, mounted, repaired or formatted by these tests.
