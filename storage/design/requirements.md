# Aurora native storage and XFS requirements

Status: proposed engineering contract, 2026-10-03. No target storage driver,
filesystem, XFS reader, or durable mount is implemented by this package.
`original-requirements.md` preserves the input; `traceability.md` records every
adaptation. MUST means a release-blocking correctness or explicitly requested
capability requirement at its stated stage. SHOULD means a measured design goal
that may need a justified, visible exception. MAY marks an optional extension.

## Scope and priorities

Aurora's order is extreme safety, a modern and understandable design, then
measured high performance. The source's performance-first objective is therefore
adapted: throughput never justifies unchecked memory, raw device authority,
ambiguous durability, unbounded resource consumption or silent loss of data.
The destination remains a native whole-system Linux replacement, beginning with
the Framework Laptop 13 / Ryzen 7 7840U qualification profile. Its SSD model,
firmware, LBA format, power-loss behavior and optional features remain unknown.
No FDP, PI, CXL, power-loss protection or physical-machine support is assumed.

There are two filesystem engines:

1. A new object/extent engine with a native asynchronous, capability-based API.
2. A separate XFS **on-disk compatibility** implementation offering ordinary
   filesystem operations through Aurora services. Read-write is the destination;
   validated clean read-only mounts and replay are prerequisite stages.

Both use a checked storage service/transport boundary. XFS keeps its own disk
structures and journal. Neither requires importing the Linux VFS, Linux C source,
Linux modules, a C ABI or unsafe pointers into the Aurora language. An optional
POSIX semantic personality is independent of XFS format compatibility.

## Architecture and trusted boundary

An application owns object/directory capabilities, request credits and buffer
leases. A protected filesystem service resolves them into authorized extent
operations. A device broker owns controller administration, namespace/range
authority, DMA mapping, queue epochs and reset. CPU-local service queues can
avoid a syscall for each I/O without giving clients hardware queue descriptors,
doorbells, arbitrary LBAs or physical addresses. Safety validation is amortized,
not eliminated. The initial implementation is single-shard and single-device;
the design leaves sharding explicit without pretending SMP already exists.

Cross-cutting contracts A1–A8 below are Aurora-derived safety and integration
requirements; they are not attributed to the attached source. Their mandatory
clauses supersede any literal
reading of the source that conflicts with safety or physical persistence.
Numbered sections retain the source numbering for direct comparison.

## 1. Core Architecture

The native engine MUST represent stable objects, versions, logical ranges and
immutable physical extents. Directories are authorized name-to-object mappings,
with transactional link/unlink and lifetime rules. Object metadata, extent maps,
namespace state, allocation ownership and durable commit records are distinct
concepts. A file-service view MUST NOT leak physical placement as authority.
XFS is a peer backend behind the service boundary, not an alternative encoding
of native immutable extents. Gate: S4, S5, X1–X3.

## 2. Native API

Requests SHOULD batch checked logical ranges and buffer leases, report partial
transfer counts and per-range errors, and return explicit asynchronous outcomes.
Read, write, commit, prefetch, discard and clone require the corresponding rights.
Cancellation, deadline, revocation, service restart and retry identities MUST be
specified before async borrowing is exposed. Placement, temperature, lifetime,
cache, priority and durability hints are bounded inputs; they cannot elevate
rights or weaken a promised durability class. Do not publish pseudocode as
compilable Aurora until the needed ownership/async features exist. Gate: S1, S4.

## 3. POSIX Compatibility

A later opt-in semantic personality MAY translate file operations to native
capability calls. It MUST name supported semantics, including rename, link,
permissions, open-unlink, append, descriptor lifetime, fsync and mapping behavior.
It is not a C API/ABI or Linux binary-compatibility commitment. It cannot
silently turn an unsupported cross-shard atomic rename into copy-and-delete.
Native applications bypass it. XFS on-disk support does not depend on it.
Gate: S8, X3, S11.

## 4. Sharded Architecture

Eventually shard metadata ownership, logs, transaction state, cache admission,
allocation, maintenance and queue credits. Shard identity MUST be independent
of a CPU number so migration, CPU hotplug and service restart can preserve
authority. Global configuration/recovery coordination may exist outside ordinary
data paths. No claim of per-core scaling is permitted before SMP, memory-model
and cross-shard failure gates pass. Cross-shard changes require A5. Gate: S8.

## 5. NVMe-Native I/O Path

Use capability-mediated shared request queues between clients and storage
services, with broker-owned hardware queues. A validated descriptor MUST bind
principal, object/range rights, lease generation, operation, byte count, credits
and completion epoch. Copy or otherwise stabilize untrusted descriptor fields
before validation/use. Untrusted clients MUST NOT submit raw NVMe/admin commands
or edit trusted SQ entries. IOMMU and teardown gates precede DMA. Avoid redundant
layers where measurement supports it; never make a missing syscall a safety
claim. Gate: S2–S4; A1.

## 6. Zero-Copy Data Path

Large transfers SHOULD DMA into pinned, direction-appropriate leased storage.
A read destination is inaccessible for conflicting CPU use while the device can
write it; a write source cannot mutate before the device finishes consuming it.
Leases cover scatter/gather pages, mapping and completion lifetime. Cancellation
does not free pages until device quiescence and IOMMU invalidation are established.
Small/unaligned I/O, encryption, integrity or unsupported mappings may require a
bounded bounce buffer. Report actual copies and pinning cost. Gate: S2–S4; A1.

## 7. Extent-Based Storage

Use variable-sized logical extents and checked range arithmetic. Native layout
MUST NOT require one metadata entry per 4 KiB unit. Physical I/O still respects
the device's logical blocks, DMA alignment, maximum transfer and atomic-write
boundaries; CPU page size is a separate constraint. Partial reads SHOULD verify
bounded integrity chunks rather than fetch an entire huge extent. Maximum
extent/descriptor sizes and sparse-hole semantics are versioned. Gate: S3, S4.

## 8. Immutable Extents

New writes normally allocate new generations. Extents become reachable only
through an atomic committed manifest. Readers, snapshots, reflinks, pending I/O,
repair and recovery roots retain references. Reclamation MUST prove that all
such references and old DMA/reader epochs are gone. Reused locations receive a
new generation so stale descriptors cannot name replacement data. Immutability
helps concurrency but does not by itself ensure persistence. Gate: S4–S7.

## 9. Small Write Delta Log

Append bounded records with object identity, generation, range, transaction,
sequence, length, payload integrity and ordering. Define overlap as ordered
committed versions, including truncate, hole punching and zero extension.
Readers compose only committed applicable deltas. Cap deltas per read/range,
log space and merge work. Consolidation is asynchronous normally; admission
control or explicit retry is required when budgets are exhausted. It is unsafe
to promise unlimited writes while deferring all consolidation. Gate: S5, S7.

## 10. Separate Large and Small Write Paths

Aligned large writes SHOULD create extents directly; small and unaligned writes
use deltas or packing. Both paths obey one transaction/durability contract.
Thresholds are measured policies with conservative defaults and configured
bounds, not adaptive correctness rules. Test writes straddling thresholds,
alignment boundaries and the end of an object; identical bytes/versions must
result under any allowed threshold. Gate: S5, S10.

## 11. Log-Structured Metadata

Normal native mutations SHOULD append self-describing redo/MVCC records instead
of synchronously rewriting persistent lookup indexes. Allocation claims, quota
changes, namespace changes and object manifests MUST participate in the same
declared transaction outcome. Logs need segment identity, sequence continuity,
bounded lengths, integrity, generation and format checks. A checksum-valid
fragment is not a complete transaction. XFS's separate journal is not governed
by the native no-global-journal design goal. Gate: S4–S6, X2.

## 12. RAM-First Metadata

Keep the hot working set in RAM. Correctness MUST survive a metadata set larger
than available memory. Checkpoints need bounded, demand-loadable indexes; cache
eviction and replay cannot require loading the whole filesystem. Reserve RAM for
recovery, completion processing and maintenance before admitting new work.
Hash/ART/radix/learned structures are choices to benchmark, not established
winners. Specify per-object and per-shard overhead and exhaustion behavior.
Gate: S6, S7.

## 13. Checkpointing

Produce immutable checkpoint generations from a consistent committed cut while
new writes continue. Persist checkpoint contents before publishing a new durable
root. Retain the prior valid checkpoint and its required logs until the new
checkpoint is independently discoverable and verified under A3. Bound replay
tail bytes, record count and memory. If checkpoint progress stalls, throttle
writes before those bounds break. No unbounded recovery-time promise follows
merely from periodic background scheduling. Gate: S6.

## 14. Transactions

Prefer single-shard, single-directory or object-group transactions with explicit
size and reservation limits. Define isolation separately from crash atomicity;
initially serialize conflicting writes at the owner and provide snapshot reads.
Validate expected versions at commit and report conflict without hidden retry
of non-idempotent actions. Cross-domain atomicity uses A5 and its extra durable
coordination; until implemented, return a distinct unsupported-domain result.
Gate: S4, S8.

## 15. Commit Model

MUST use **data and manifest durable before commit publication**, followed by
commit durability before the requested durable acknowledgement. Submission order
and a final flush alone are insufficient during an interrupted flush. Implement
the precise A2 protocol, including all involved devices/namespaces, checksum and
identity validation, media atomicity, replay sequence, lost replies and duplicate
requests. Uncommitted allocations are reclaimable only after recovery ownership
is resolved. The host model illustrates this ordering, not a hardware proof.
Gate: S0, S3, S4, S6.

## 16. MVCC

Versions MUST have checked monotonic generation/epoch semantics with explicit
exhaustion instead of wraparound. Readers pin a consistent committed version
and can run without ordinary read/write locks once the language memory model,
publication ordering and reclamation proof exist. Bound retained reader epochs
and account their capacity. Revocation may stop a stalled reader; it must never
reclaim memory or extents still accessible to that reader. Gate: S4, S7, S8.

## 17. Snapshots

Snapshot creation captures committed roots without copying contents. Define its
scope: an object/shard snapshot first; a consistent multi-shard snapshot requires
a coordinated cut. Snapshot creation/deletion and reference retention are durable
transactions. Charge retained capacity, enforce retention quotas and reserve
space for deleting/compacting snapshot metadata. Snapshot deletion never implies
immediate physical reuse or secure erase. Gate: S7, S8.

## 18. Reflinks

Expose capability-checked cloning that initially shares extents and isolates
later writes. Define ownership, quota charging, clone failure cleanup and limits
on sharing across encryption/security domains. Reference changes and namespace
publication must be transactional. Native clone is not automatically XFS reflink;
the XFS feature must be separately implemented and tested. Gate: S7, X3.

## 19. Lifetime-Aware Allocation

Support bounded placement hints for lifetime, temperature, rewrite frequency and
durability. Physical allocation remains authoritative and cannot be directed to
another tenant's extents. Group similar invalidation behavior when beneficial;
misclassification must affect only performance and space efficiency. Hints are
estimates, including the label "permanent"; no hint can bypass retention or
durability. Gate: S7, S9.

## 20. NVMe Flexible Data Placement

FDP is a capability-gated optimization with a correct ordinary-NVMe fallback.
Discover the controller/endurance-group configuration, namespace placement
handles, reclaim groups, limits and permitted directives; validate their mapping
before use. Do not hardcode source examples as physical RUH assignments. Control
configuration changes separately from ordinary writes. Measure placement events,
host and device write amplification and effects under changing lifetimes.
FDP does not confer filesystem transaction atomicity. [N2, N3] Gate: S9.

## 21. Avoid Double Garbage Collection

Coordinate placement and reclamation where capabilities permit; otherwise group
by measured lifetime without assuming insight into an opaque FTL. Logical
discard/deallocation follows committed unreachability, never merely unlink intent.
Its completion is neither secure erasure nor permission to read stale contents.
No design can promise elimination of device GC, and unknown device write
amplification MUST be reported as unavailable rather than estimated as fact.
Gate: S7, S9, S10.

## 22. Capacity Overprovisioning

Expose a configured usable-capacity limit and separate reservations for foreground
transactions, checkpoint/recovery, GC relocation and snapshot retention. The
source's 8 TB physical / 5–6 TB usable example is an experiment, not a default
guarantee. Logical filesystem free space and SSD factory overprovisioning differ.
Account on-device allocation, outstanding reservations, replica cost and quotas
without double spending. Admission MUST fail or backpressure before emergency
reserve is consumed. Gate: S7; A4.

## 23. Garbage Collection

Use asynchronous shard-local cleaning with bounded CPU, memory and I/O credits.
Candidate selection may use dead fraction, age, live bytes and placement geometry.
Relocate through the same data-before-manifest durability protocol, then retire
old extents only after reader and recovery barriers. GC MUST make progress under
sustained load when reclaimable space exists; snapshots can legitimately prevent
that progress, requiring visible backpressure rather than corruption. Gate: S7.

## 24. Background Work

Compaction, checkpointing, GC, integrity scans, metadata packing and migration
SHOULD be budgeted asynchronous jobs. Define cancellation, restart idempotency,
reserved credits and progress metrics. Foreground deadlines need priority, while
maintenance needs a minimum service share to prevent eventual space/log
exhaustion. Background classification is not evidence that work has no latency
or energy cost. Gate: S6, S7, S10.

## 25. Cache Architecture

No mandatory generic data page cache. Support bounded policies for uncached,
metadata, random, sequential, pinned and application-managed access. Pinning
requires quota and revocable authority; "application-managed" still obeys
isolation and coherent versioning. All access paths to an object must see the
declared version; stale cached data cannot bypass integrity or authorization.
Measure scan pollution, hit ratios and memory pressure. Gate: S5, S7.

## 26. Memory-Mapped Interface

A future memory-oriented view MAY expose readonly immutable versions or checked
transactional write regions. Specify page-fault handling, permission changes,
truncation, snapshot visibility, writeback, cancellation and mapping retirement.
Persistence requires an explicit commit primitive. A CPU store or cache-coherent
load does not itself establish media durability. Defer mutable mappings until
VM ownership and persistent-write contracts are verified. Gate: S11.

## 27. CXL Support

Keep the storage abstraction open to memory-semantic devices. CXL is neither a
required Framework dependency nor proof of persistence. Before using a region
for durable logs/data, qualify its volatile/persistent identity, persistence
domain, cache flush/fence path, poison/error handling, power-loss behavior and
reset/revocation rules. CXL DRAM may be only a volatile tier. Its backend needs
its own crash model; NVMe barriers cannot be mechanically reused. [C1] Gate: S11.

## 28. Heterogeneous Storage

Placement may span DRAM, qualified persistent memory, performance/capacity NVMe
and later remote media. Every tier reports its actual durability/failure domain.
Migration must preserve object identity and the requested durability before
retiring the old location. An unavailable tier returns a specified error or
degraded mode; it cannot quietly downgrade durability. Remote storage requires
an explicit network/authentication/consistency contract. Gate: S9, S11.

## 29. Checksumming and Integrity

Protect every durable data/metadata unit with end-to-end integrity covering its
type, length, filesystem/object identity, logical range and generation, as
appropriate. Validate relationships as well as individual checksums. PI can
protect the transfer/media path but MUST NOT be assumed to bind native object
versions or replace end-to-end integrity without an equivalent end-to-end proof.
CRC is error detection, not authentication. Encrypted formats need reviewed
authenticated-encryption and nonce/key rules. [N1, X2] Gate: S4, S6, S7; A6.

## 30. Replication

Prefer object/extent-level replicas or later erasure coding. A replicated
durability receipt MUST identify replica count, fault-domain independence,
metadata/commit durability and tolerated failures. Two extents on one SSD are
not independent device replicas. Repair verifies identity/integrity, never copies
unchecked bytes, and is bounded/idempotent. Membership change and partitions
need a separate protocol; asynchronous replication cannot satisfy a synchronous
replicated acknowledgement before it completes. Gate: S9, S11.

## 31. Device Parallelism

Split logical I/O according to validated transport constraints and bounded
scatter/gather descriptors; track every child completion. Completion order is
independent of submission order. Aggregate success only after all required
children meet the requested contract. Bound queue depth and fanout and preserve
fairness; do not allocate all available queues merely because they exist.
Cross-device durability fences cover every dependency. Gate: S3, S8, S10.

## 32. CPU Affinity

Prefer locality among a task, storage owner and queue, subject to CPU/energy
budgets and fairness. Queue ownership is exclusive or explicitly synchronized.
Migration transfers ownership through a quiescent handover with generation
checks. Dedicated busy-poll cores are an optional measured profile, not the
default on a battery-powered Framework. Compare polling, interrupt and adaptive
completion policies under idle and loaded conditions. Gate: S8, S10.

## 33. NUMA Awareness

After topology and SMP are verified, place metadata, DMA buffers and queue
workers using the discovered locality graph. Cross-node operations remain
correct and accounted. The first laptop target must work without multiple NUMA
nodes, and emulator topology must not become a hardcoded physical assumption.
Test queue migration, memory exhaustion and device reset across nodes before
claiming NUMA scaling. Gate: S8, S10.

## 34. Locking

Use single-owner state, message passing, immutable versions and checked atomic
publication to minimize contention. "Lock-free" must describe a demonstrated
algorithm/progress property, not the absence of a mutex in pseudocode. RCU-like
reclamation requires explicit epochs and memory ordering. Bounded locks are
acceptable where safer and off ordinary contended paths; measure contention.
Do not add atomics before the language concurrency model exists. Gate: S8.

## 35. Namespace Design

Optimize hot lookup with RAM indexes while supporting demand-loaded cold state.
Specify byte/Unicode naming, comparison/normalization, length/path limits,
case policy, reserved names, directory enumeration versions, symlink loop bounds
and mount-boundary authority. Initial proposal: native names are valid UTF-8,
case-sensitive byte sequences with no implicit normalization; exact byte-oriented
XFS names remain available without lossy conversion. Namespace caching must
invalidate on permission and generation changes. Gate: S5, S7, X1; A6.

## 36. Object IDs

Use a specified stable identifier independent of extent location, proposed as
128 bits plus a non-reused object generation where required. Define generation,
collision handling, allocation exhaustion, import/export and filesystem identity;
randomness alone is not a proof of uniqueness. IDs are names, not authority.
Guessing or observing an ID never grants access. XFS inode numbers retain their
own generation/lifetime rules behind the adapter. Gate: S4, S5, X1.

## 37. Metadata/Data Separation

Allow independent placement, allocation sizes, integrity and replication of
metadata and payload. Their durability dependencies stay coupled by transactions.
Faster metadata media cannot publish references to data that is not yet durable.
Loss of the metadata tier must have a declared recoverability/failure contract;
the existence of data extents alone does not guarantee namespace reconstruction.
Gate: S4, S9.

## 38. Hot/Cold Separation

Track temperature/lifetime in bounded policy state and isolate placement classes
when measurements justify it. Reclassification cannot mutate immutable bytes or
drop references. Charge migration/learning CPU and bytes to the same maintenance
budgets as GC. Test changing and adversarial hints, cold-data pinning, noisy
neighbors and cache thrashing. Gate: S7, S9, S10.

## 39. Learned Policies

Adaptive cache, placement, prefetch, extent sizing and cleaning may be added after
deterministic baselines. Policy outputs are constrained suggestions validated by
the correctness layer. Bound memory, compute, retry rate and model state; record
policy/version/configuration in experiments and allow safe rollback. Wrong
predictions, malicious hints and missing telemetry must never change permissions,
durability, transaction atomicity or retained-data reachability. Gate: S9, S10.

## 40. Recovery

Normal recovery locates a valid bounded checkpoint/root chain and replays a
bounded committed tail. Demand-load metadata instead of rebuilding everything
in RAM before mount. Sequence gaps, invalid lengths/identities and committed
references to corrupt/missing dependencies fail closed. An incomplete uncommitted
tail may be ignored under the format's torn-record rules. A slow offline salvage
tool may scan more; it must not masquerade as normal successful recovery or
silently discard acknowledged data. Gate: S6; A3.

## 41. fsync Equivalent

Offer explicit receipt contracts rather than undefined ordinal labels:
`VolatileVisible` means the version is published in volatile service state and
can be lost on service/host failure; `LocalPersistent` covers the named local
media persistence domain; `ReplicatedPersistent(policy)` covers that policy's
qualified failure domains. Process/host-survival variants are deferred until
their recovery mechanisms exist. Report object/namespace dependencies covered,
commit identity and outcome-query token. Never label a queued write durable.
Gate: S4, S9; A2.

## 42. Failure Atomicity

A recovered committed transaction exposes all its metadata/namespace changes
or none, under the declared fault model. An acknowledged local durable commit
must survive the modeled host power loss; an unacknowledged request may already
have committed. Distinguish failed, cancelled-before-commit and outcome-unknown.
No subset is published because only some child writes completed. Larger
transactions use a manifest and single commit decision within bounded limits.
Gate: S0, S4, S6, S8; A2, A5.

## 43. Metadata Operations

Create, remove, stat, open, enumerate and rename require explicit rights,
version/atomicity rules and resource reservations. Test rename replacement,
directory cycles, hard links if supported, open-unlink retention, concurrency,
permission changes and name races. Native same-shard operations should scale
with independent owners; report cross-shard cost separately. Metadata throughput
does not excuse missing multi-user isolation. Gate: S5, S7, S8.

## 44. Small Files

Pack small objects or inline tiny contents when beneficial, preserving independent
identity, generation, encryption and checksum boundaries. A damaged pack must
not be treated as silently valid neighboring objects. Define packing overhead,
read amplification, migration/promotion thresholds and deletion accounting.
Use bounded deltas and lifetime classes; compare millions-of-small-file memory
cost against a realistically constrained machine. Gate: S5, S7, S10.

## 45. Large Files

Use large extents and large logical requests without requiring a huge contiguous
RAM allocation or a single huge NVMe command. Split safely at transport limits;
support sparse large offsets, checked length arithmetic and partial failures.
Measure fragmented and aged files as well as fresh contiguous ones. Integrity
granularity and read cancellation remain bounded even for very large extents.
Gate: S4, S5, S10.

## 46. Direct I/O as the Normal Case

Make explicit buffering policy part of the native API, with a common version
and durability model for all paths. Direct data transfer means mediated DMA
leases, not unrestricted client device access. Cache bypass cannot bypass
authorization, checksum validation, quota accounting or encryption. Report
alignment/bounce behavior explicitly instead of silently changing API semantics.
Gate: S3–S5, S7; A1.

## 47. Scheduling

Schedule latency-sensitive work, bulk transfer, metadata, barriers and maintenance
using bounded credits, fairness and deadline-aware admission. A durability fence
cannot be reordered away for priority. Reserve sufficient maintenance progress
to avoid starvation-driven exhaustion. Priority hints are constrained by the
principal's authority. Test queue overload, completion storms, hung devices and
service restart; cancellation must not invalidate active DMA buffers. Gate: S3,
S7, S8.

## 48. Tail Latency

Optimize p99 and p99.9 under steady-state occupancy, snapshot retention and
multi-user pressure. Publish latency distributions including admission delay,
retry, timeout and failure rates. Checkpoint, GC and compaction should not
normally block foreground operations, but bounded overload backpressure is a
correct result. No hard real-time bound is promised by an empirical percentile.
Gate: S7, S10.

## 49. Metrics

Expose read/write IOPS and bandwidth; p50/p95/p99/p99.9; cycles per completed
operation; host write amplification; device write amplification when reliable
telemetry exists; GC bytes/CPU; cache hits; metadata lookup latency; queue
depth/utilization; cross-shard/NUMA counts. Add retries, integrity failures,
unknown outcomes, discarded work, durable-commit latency, reserved/free/pinned
bytes, log tail, snapshot retention and energy/idle cost. Define units, windows,
denominators, histogram limits and counter overflow. Gate: S4, S7, S10.

## 50. Primary Performance Goals

Minimize overhead relative to raw transport with equivalent queueing, integrity,
durability and workload semantics. Establish a measured baseline before choosing
numeric release budgets. State what raw measurements omit: namespace, permission,
checksum, encryption, retention and crash guarantees. Native object performance
and file-personality performance are separate results. No near-raw claim is
made by this requirements package or by a host simulation. Gate: S10.

## 51. Benchmarking Requirements

Include sequential 1/4/16/128 MiB, random 4/16/64/256 KiB, read/write mixes of
70/30, 50/50 and 30/70, create/delete/stat/rename/traversal and millions of small
files. Test per-operation durable, batched and group commits. Sweep queue depth,
threads, occupancy, RAM budgets, cold/warm state, retained snapshots, alignment
and dataset larger than RAM. Long runs must reach documented steady state and
measure fragmentation, GC, write amplification, tail latency and thermal/energy
effects. Include correctness checks throughout. Gate: S10.

## 52. Baselines

Compare applicable Linux ext4, XFS, Btrfs and F2FS configurations, plus raw NVMe
and SPDK, on separately authorized disposable media. Linux/SPDK are comparison
systems, not target dependencies. Hold SSD/firmware, dataset, usable capacity,
durability, integrity, cache policy, CPU/power and preconditioning comparable;
report unavoidable differences. Version and preserve scripts/results and include
confidence intervals/repeated trials. SPDK's queue ownership model informs
experiments but does not establish Aurora isolation. [P1] Gate: S10.

## 53. Design Philosophy

Retain the source's 20 principles as optimization goals under the safety contract:
local ownership/logs/transactions; explicit caching; variable extents; minimal
copies; log-backed hot metadata; immutable versions; low contention; device
parallelism, lifetime placement and topology; reserved capacity; asynchronous
maintenance; optional POSIX semantics; capability-gated FDP/PI; policy separated
from correctness; measured low overhead. "No global journal" applies to native
normal paths, not XFS compatibility or rare distributed decisions. Necessary
validation, persistence fences and emergency backpressure are never removed to
satisfy a slogan. Gate: all relevant stages.

## 54. Non-Goals

Native design need not mimic Linux internals, fixed 4 KiB metadata, maximum
utilization or HDD optimization. However, the user's explicit XFS addition
overrides the source's blanket existing-format non-goal. Safety, maintainability,
multi-user isolation and first-laptop needs cannot be deferred as "secondary"
performance concerns. Broader Zen/RDNA hardware remains the system destination;
storage optimization for one device does not discard it. Removable and remote
storage are staged, not silently declared outside the whole-OS goal. Gate: X1–X3.

## 55. Initial Prototype Scope

Begin with executable fault models and checked parsers, then DMA-safe transport,
single-device extents, object transactions, namespace, bounded deltas,
checkpoint/recovery and resource-safe GC. Object create/delete, checksums and
the correct durable protocol are required before performance benchmarking can
support a filesystem claim. Zero-copy, sharding and FDP wait for their safety
dependencies. Develop the XFS read-only parser in parallel on disposable images;
never write XFS before replay/allocation/journal gates. See roadmap.md.

## 56. Long-Term Direction

Let the VM, runtime scheduler, filesystem, placement policy and driver cooperate
through typed, versioned capability interfaces. Cooperation does not dissolve
fault-containment or ownership boundaries. Each backend preserves its actual
hardware and persistence contract, including future CXL. Evolve toward an
Aurora-authored whole-system stack, retaining only documented audited hardware
intrinsics. Future optimization must pass the same safety/recovery tests and
equivalent-semantics benchmarks. Gate: S11 and whole-system assurance.

## 57. Added requirement: XFS on-disk compatibility

This requirement comes from the user's explicit request alongside the attachment.
It is not a feature claimed by the original 56-section native design.

### XFS service boundary

- Implement parsing and operations in Aurora's safe dialect as its dependencies
  mature. A temporary host reference/test tool is not target support.
- Use a range-restricted, read-only or read-write volume capability. The native
  allocator and XFS allocator MUST never own the same sectors simultaneously.
  Mount arbitration prevents two writers or host/guest concurrent modification.
- Support ordinary Aurora file-service handles without pretending XFS supplies
  native MVCC transactions, native checksummed payloads or native snapshot APIs.
  Unsupported backend operations return explicit capability results.
- Decode XFS fields according to the pinned on-disk specification, with explicit
  endian handling. In particular, most metadata fields and some checksum fields
  differ in byte order, while journal payloads have a declared architecture/log
  format. Never cast media into compiler class layouts. [X1]

### Declared feature matrix

The first candidate profile is v5 CRC-enabled XFS, one data device, an internal
v2 log, non-realtime files, declared block/sector/inode sizes, and an explicitly
enumerated compatible feature set generated by a pinned mkfs.xfs version.
This is a proposed profile, not present support. Do not rely on changing mkfs
defaults. Each feature row needs read, replay and write status independently.
Track at least: v4/v5, ftype, finobt, sparse inodes, metadata UUID, rmapbt,
reflink/refcount, bigtime, inobtcount, large extent counts, parent pointers,
log-incompatible features, quotas, extended attributes/ACLs, external log and
realtime allocation. Add future flags explicitly rather than silently accepting
them. Reject unrecognized incompatible features; read-only-compatible features
never authorize writes. A stricter initial allowlist may reject additional
images with a clear unsupported-feature error. [X1]

### X1: clean read-only stage

Validate superblock/geometry and feature masks, allocation-group boundaries,
inode formats, extent maps, directories and readonly contents. Include sparse
and unwritten extents, short/local forms, btrees, symlinks and bounded traversal
for every advertised profile. Reject cycles, overlapping/impossible ranges,
overflow, forged owners, UUID mismatches and integrity failures. Do not expose
device special files as ambient device authority. Preserve supported xattrs/ACL
meaning and reject access when a needed security attribute is unsupported.

Prove the log is clean with a bounded validated log reader; do not infer this
from a superblock bit or a happy pathname lookup. Dirty/unsupported logs are
rejected in the ordinary clean read-only stage. A future forensic no-replay mode
must be explicitly marked potentially inconsistent and is not clean-mount
support. Linux's norecovery contract also warns that dirty images may be
inconsistent. [X4] The image must remain byte-identical after all X1 tests.

### X2: replay and recovery stage

Implement the exact supported log format, cyclic record/head-tail discovery,
sequence/checksum validation, transaction assembly, buffer cancellation, inode
and quota updates, intents/completions, orphan/unlinked processing and deferred
work used by the allowed feature set. No partial log replay of unknown records.
Recovery requires write authority even if the eventual mount is read-only.
It must be restartable after every interrupted write and leave an interoperable
XFS image. XFS logging combines physical and logical records and deferred
intents; translating only native commit records is insufficient. [X3]

Replay first into disposable copy-on-write image overlays. Compare resulting
contents and invariants with a pinned Linux/XFS implementation in an isolated VM.
`xfs_repair -n` is a consistency check, not a journal-replay oracle, and cannot
be expected to replay a dirty log. Never erase a dirty log as automatic recovery
or use `xfs_repair -L` to manufacture a passing gate. [X5]

### X3: read-write stage and completion target

Implement allocation/free space, inode lifecycle, namespace operations,
data/truncate/unwritten conversion, journal reservations and forcing, timestamp
and quota/security semantics for the declared profile. Add reflink/refcount,
other common features and broader profiles only with their recovery mechanisms.
Support interrupted operations, no-space conditions, failed writes/flushes,
power loss, service restart and clean unmount. Never mark unsupported bits
supported to get an image to mount.

Acceptance requires round trips: Linux creates, Aurora reads/modifies, Linux
recovers/checks/reads; Aurora creates/modifies supported images, Linux validates;
repeat with injected interruption and exact feature/version records. Use
xfsprogs, selected/adapted xfstests scenarios and native multi-user tests on
disposable images only. Ported tests need licensing review and an explicit
semantic adapter; Linux-only shell helpers are not an Aurora ABI. [X6]
Clean read-only does not close the user's read-write XFS requirement.

## A1. Authority, buffer and queue lifetime contract

Capabilities bind resource identity/incarnation, rights, namespace/range, owner
and quota. Disk bytes, user-provided integers and reflected metadata cannot mint
them. Shared request descriptors are hostile until validated; control fields
are stabilized to avoid validation/use races. Clients never possess raw PRP/SGL,
IOMMU table or controller-admin authority. Scatter/gather arithmetic and overlap
are checked before any DMA map is installed.

The conceptual lease states are Owned → Prepared → Mapped → Submitted →
Completed/OutcomeUnknown → Quiesced → Unmapped → Reusable. Transitions require
evidence, not an enum cast. Read/write direction and CPU access restrictions
remain valid throughout DMA. Aborting or timing out an NVMe command does not
prove the device stopped accessing memory. Revocation stops admissions, retires
queue epochs, establishes device quiescence/reset as needed, drains completions
and interrupts, completes IOMMU invalidation and only then scrubs/reuses pages.
If quiescence cannot be established, quarantine mappings/pages and fail closed.
Device/queue/tag reuse cannot turn a stale completion into another operation's
success. The same discipline covers service death, hot unplug and suspend/resume.

The kernel/broker may contain a small audited hardware-specific trusted base;
there is no source-language raw-pointer escape. Native resource classes need
verified move/drop, borrowing, async retention, atomics and checked interfaces
before they replace temporary host models. Current u8 and proposed readonly
spans alone do not supply those prerequisites.

## A2. Native local durable transaction protocol

### Fault and trust model

Assume compliant devices whose documented completed persistence operations
survive the declared power failure, and detection of the modeled torn/corrupt
records. Submitted ordinary writes may reach media in any order or only partly;
command completion may precede persistence with a volatile write cache. A CPU
memory fence, SQ order, interrupt delivery or process survival is not a storage
persistence barrier. Media atomicity depends on discovered size/alignment/boundary
rules, not a universal 4 KiB assumption. FUA pertains to its own command; wait
for dependencies rather than treating it as a global ordering fence. [N1, N2]

Firmware that lies about persistence, malicious storage, checksum collisions,
unrecoverable later media failure and destruction of all replicas are outside a
single-device power-loss guarantee. Detect/report corruption rather than silently
asserting durability; authenticated storage and replicated fault domains need
their own threat models.

### Required state transitions

1. Reserve worst-case data, delta, metadata, commit, recovery and quota resources;
   validate capability and expected versions. Assign a unique request/transaction
   identity and payload digest. No externally visible mutation yet.
2. Write new immutable payload and the complete transaction manifest/dependencies
   to unused generation-bound locations. Await all relevant ordinary write
   completions. Then issue and successfully complete the needed namespace/device
   flushes. Alternatively use FUA for every dependency and await each successful
   completion. This establishes the **dependency-durable fence**.
3. Only now submit a checksummed, identity/sequence-bound commit record naming
   the manifest. Its placement/encoding follows the verified atomic or
   torn-detectable record contract. Commit records must not overwrite the sole
   previously recoverable root. Persist the record with FUA and await success,
   or await its ordinary completion then issue/complete the applicable flush.
4. Publish the complete new root/version atomically to readers. Return a
   `LocalPersistent` receipt only after the **commit-durable fence**. A batch may
   share the two fences but preserves every transaction's dependencies and
   declared publication ordering. A failed fence cannot create a success reply.
5. Retire old storage later using durable reachability, snapshot/read epochs and
   recovery roots. Cancellation after commit cannot undo it.

For multiple devices, stage 2 waits for all required dependency domains; stage 3
must satisfy the declared commit/metadata replica policy. Namespace-scoped flush
effects may cause unavoidable physical coupling between shards; measure this
rather than promising per-shard hardware flush isolation. Exact command rules
must be pinned to the supported NVMe revision and controller profile. [N2]

### Crash outcomes and idempotency

Before a valid commit, the prior state remains visible after recovery; unreachable
new records can be reclaimed later. With a complete valid commit, recovery
validates the manifest and all dependencies and exposes the complete new state.
A valid committed reference to invalid data is corruption, not permission to
silently revert an acknowledged transaction. An incomplete terminal commit may
be ignored according to the record format; a sequence gap or invalid interior
record is not casually skipped.

The server may persist and publish before the client receives a reply. Therefore
timeout/connection loss produces `OutcomeUnknown` unless non-commit is proved.
Clients can query/retry a stable identity. A retained durable result records the
request digest and terminal result; the same identity with different contents is
rejected. Retention and acknowledgement of result-token expiry are bounded and
specified; after expiry, return `OutcomeExpired` rather than guessing or executing
a duplicate. No unbounded exactly-once history is promised. Checkpointing must
preserve live outcome records and version preconditions.

## A3. Format, checkpoints and bounded recovery

Specify a native on-disk format independently of the compiler ABI: magic, format
version, little-endian fixed-width fields, record type, header/total length,
feature masks, filesystem identity, owner, sequence/generation, bounded counts,
checksum algorithm/coverage and explicit reserved fields. No raw class images,
padding, host pointers, runtime type IDs or native enum ordinal assumptions.
Parsers return checked values only after validation; integer overflow, excessive
depth/counts, cycles, overlapping extents and out-of-volume addresses are errors.
XFS has its own field-specific format and endian rules, never this native schema.

Proposed root scheme: independently checksummed generation slots point to
immutable checkpoint descriptors. Publish a new slot only after all referenced
checkpoint pages are durable; preserve another proven complete generation and
its replay tail. A root-slot write must fit a qualified power-fail atomic unit,
or use a separately reviewed torn-detectable redundant publication protocol.
Checksums give probabilistic detection, not universal atomicity. A selected newer
root referring to bad contents is a corruption event, not silent rollback.
Define which failures permit older-root fallback without losing acknowledged
commits and retain all logs needed to recover those commits. Test root loss,
torn slot updates and interrupted reclamation explicitly before freezing format.

Bound normal recovery by mount-profile limits on root slots, descriptor reads,
tail bytes/records, parser allocations and transaction size. Recovery work still
depends on checkpoint indexing, the loaded working set and device speed; it is
not constant time independent of all filesystem metadata. Emergency read-only
or diagnostic recovery and full offline salvage are separate states.

## A4. Bounded resources and space-pressure behavior

Every mount profile fixes maximum inflight requests, pinned bytes, queue entries,
scatter/gather length, transaction bytes, deltas per read, recovery tail,
cache memory and background credits. Admission reserves the full worst-case
resources before mutation. Maintain a non-consumable emergency margin adequate
for supported checkpoint, rollback-of-unpublished-work, unlink and GC protocols;
quantify it before implementation rather than choosing a magic percentage.

Define Normal → Pressure → Throttled/ReadOnly states with hysteresis, telemetry
and recovery transitions. Retained snapshots/readers may pin all useful space;
then reject new allocation explicitly, continue safe reads and permitted cleanup,
and report what retains capacity. Never delete retained snapshots merely to
relieve pressure without an explicit authorized retention/expiry policy, borrow
another user's quota, spin indefinitely or falsely acknowledge a write. Reserve
maintenance CPU/I/O even under foreground overload; correctness permits bounded
foreground waiting or a retry/error when progress cannot be guaranteed.

## A5. Cross-shard operations

Same-shard transaction semantics do not imply multi-shard atomicity. A future
protocol needs ordered participant identities, durable prepare/reservations,
a durable decision, idempotent completion and restart recovery. Prepared
transactions retain their resources and cannot be unilaterally aborted merely
because a timeout fired after an unknown decision. Publish either a consistent
shared decision view or block dependent reads until participant installation is
complete. Define bounded coordination state and a faulted-coordinator policy.

Until that gate passes, a cross-shard atomic operation returns
`CrossDomainUnsupported`; applications may explicitly request a different
non-atomic workflow, but the service never substitutes one invisibly. Namespace
shard placement should make common renames local without assuming all future
workloads can avoid coordination. Cross-volume operations, including native↔XFS,
do not acquire atomicity just because both expose file handles.

## A6. Whole-system security and multi-user semantics

Durable ownership, rights/ACL policy, directory traversal checks, delegated
capabilities, revoke/unlink behavior and quota accounting are required. Specify
mount namespaces, symlink resolution and privileged operations so shared object
IDs or cached lookup results do not bypass per-user checks. Two concurrent users
must be isolated through data, snapshots, reflinks, cache, IPC and DMA. Read
newly allocated/unwritten regions as zeros or defined holes; never disclose old
tenant bytes. Diagnostic tools and metrics must not expose unauthorized names
or contents.

Design support for optional per-volume at-rest encryption with reviewed algorithms, authenticated
metadata/payload policy, key isolation, entropy readiness, recovery-key handling,
rotation, revocation and interrupted-change recovery. Define leakage and limits
for an unlocked system, sleep/hibernation, swap and crash dumps. Encryption cannot
be silently disabled to reach a benchmark. Native encrypted volumes and possible
encrypted block containers holding XFS are separate format/interop decisions;
do not invent a nonstandard encrypted XFS extension and call it compatible.
This is an Aurora security integration option, not a claim that the user requested
always-on encryption or selected an encryption/performance default. That choice
must be explicit when a release profile is agreed.
Checksums do not prevent malicious tampering or rollback by themselves.

## A7. Verification, operations and hardware qualification

All success claims require source identity, commands, tool/spec versions,
profile, generated data seed, exact pass/fail results and independent review.
Combine unit/property/parser-fuzz tests, crash-state exploration, differential
interop, fault-injected emulator runs and eventually dedicated-hardware power
loss. Safety tests cover stale capabilities/completions, DMA after revocation,
host/service/device reset, torn/lost/reordered writes, read errors, full space,
low RAM, snapshot pinning and repeated restart. Recovery is itself interrupted.

Provide read-only inspection, integrity scrub, repair proposals, backups/restore,
format migration and recoverable update tooling. Destructive repair never
silently changes user data. Durable format upgrades require an explicit
compatibility/rollback plan. User disks and host bootloaders are out of scope for
these experiments. An emulator result does not qualify any physical Framework
SSD/controller/firmware tuple.

## A8. Research and open design choices

Research informs experiments, not inherited guarantees. NOVA studies per-inode
logs with volatile indexes on persistent memory; Strata studies log digestion
across media; SplitFS reduces persistent-memory software overhead; SquirrelFS
uses typestate for persistent-memory ordering; ScaleLFS studies scalable cleaning
on commodity SSDs. None proves this new NVMe protocol, Aurora compiler safety,
or XFS interoperability. [R1], [R2], [R3], [R4], [R5]

Resolve by measured prototypes: extent/integrity granularity, concrete RAM
indexes, checksum/authentication algorithms, root-record encoding, resource
budgets, polling thresholds, usable-capacity reserve, policy learning and
cross-shard protocol. These choices cannot weaken A1–A7. A proposed typed
`DurableManifest`→`CommittedVersion` transition may help make ordering explicit
once resource classes exist, but typestate is not a substitute for modeling
device reorder, power failure and trusted driver behavior.

Reference keys link to verified primary sources and limitations in `sources.md`.

[N1]: sources.md#n1-nvm-express-nvm-command-set-specification-13
[N2]: sources.md#n2-nvme-base-specification-and-flush-semantics
[N3]: sources.md#n3-flexible-data-placement
[X1]: sources.md#x1-on-disk-structures-and-compatibility-flags
[X2]: sources.md#x2-self-describing-metadata
[X3]: sources.md#x3-logging-and-deferred-operations
[X4]: sources.md#x4-no-recovery-mounts
[X5]: sources.md#x5-repair-versus-replay
[X6]: sources.md#x6-filesystem-test-tooling
[C1]: sources.md#c1-cxl-memory-persistence
[P1]: sources.md#p1-spdk-nvme-driver-documentation
[R1]: sources.md#r1-nova-fast-2016
[R2]: sources.md#r2-strata-sosp-2017
[R3]: sources.md#r3-splitfs-sosp-2019
[R4]: sources.md#r4-squirrelfs-osdi-2024
[R5]: sources.md#r5-scalelfs-fast-2025
