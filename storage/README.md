# Aurora storage

The native NVMe object/extent filesystem and separate XFS compatibility backend
remain project targets. Neither is a working target filesystem.

The [requirements](design/requirements.md), [traceability](design/traceability.md)
and [staged roadmap](design/roadmap.md) preserve all 56 supplied sections and the
additional XFS request. XFS read-write is the destination; validated read-only
access and log replay are prerequisite gates.

Current [byte and sector storage](../docs/storage.md) includes checked binary
buffers, owned sectors and a runtime-capacity volatile RAM sector device.
The [offline XFS readers](../docs/xfs.md) cover bounded header, geometry,
shortform-root and inline-extent/file fixtures. They do not mount a filesystem.
The [host-only crash model](design/model/README.md) checks a bounded transaction
and deliberately broken persistence protocols.

Real DMA/IOMMU authority, NVMe transport, persistent filesystem I/O and hardware
qualification remain open. Tests never open, mount, repair or format a user disk.
