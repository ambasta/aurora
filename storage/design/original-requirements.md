# High-Performance NVMe-Native Filesystem Requirements

## Objective

Design and implement a new filesystem and storage stack from first principles for modern NVMe storage.

The design is not constrained by:

- Linux
- POSIX internals
- the traditional kernel block layer
- the page cache
- VFS
- existing filesystem formats
- conventional 4 KiB block-oriented architectures

POSIX compatibility may be provided as an optional compatibility layer, but it must not dictate the internal architecture.

The primary design goal is **maximum storage performance on modern NVMe hardware**, particularly:

- high IOPS
- high sequential and random throughput
- low median latency
- low tail latency
- high scalability with CPU cores and NVMe queues
- low write amplification
- low CPU overhead per I/O operation

Storage capacity should be considered inexpensive. The filesystem may intentionally trade additional physical capacity for lower latency, reduced garbage collection, simpler metadata handling, and lower write amplification.

---

# 1. Core Architecture

The native storage abstraction should be an **object/extent engine**, not a traditional inode/block filesystem.

Conceptually:

```text
Application / runtime
        |
        | async storage API
        |
        v
+--------------------------+
|    Storage/Object API    |
+------------+-------------+
             |
             v
+--------------------------+
| Per-CPU Storage Shards   |
|                          |
| metadata                 |
| extent maps              |
| transactions             |
| caches                   |
| allocation               |
+------------+-------------+
             |
             v
+--------------------------+
| Immutable Extents        |
| + Small Delta Logs       |
+------------+-------------+
             |
             v
+--------------------------+
| NVMe Placement Layer     |
| FDP / lifetime classes   |
+------------+-------------+
             |
             v
           NVMe
```

Files and directories should be implemented as views over this lower-level object store.

For example:

```text
object {
    object_id
    metadata
    logical_size
    extents[]
    versions[]
}
```

A directory should conceptually be a mapping:

```text
name -> object_id
```

---

# 2. Native API

The native API must be asynchronous and batch-oriented.

Example conceptual interface:

```text
storage.read(
    object,
    ranges[],
    destination_buffers[],
    completion
)

storage.write(
    object,
    ranges[],
    buffers[],
    placement_hint,
    completion
)

storage.commit(transaction)

storage.prefetch(object, ranges[])

storage.discard(object, ranges[])
```

The API should support multiple ranges in a single logical request.

It should expose storage characteristics that conventional POSIX hides, including:

```text
expected_lifetime
temperature
access_pattern
cache_policy
durability
priority
```

Applications should optionally be able to provide these hints explicitly.

---

# 3. POSIX Compatibility

POSIX must be implemented as a compatibility personality over the native storage system.

Architecture:

```text
POSIX API
    |
    v
POSIX compatibility layer
    |
    v
native object API
```

POSIX semantics must not impose global serialization or force the internal system into inode/page/block abstractions.

Native applications should be able to bypass POSIX entirely.

---

# 4. Sharded Architecture

The storage system must be fundamentally decentralized.

Storage ownership should be partitioned between CPU-local shards.

Each shard should independently own, where practical:

- metadata
- free-space allocation
- transaction state
- write logs
- caches
- garbage-collection state
- NVMe submission queues
- NVMe completion queues

Conceptually:

```text
CPU 0        CPU 1        CPU 2          CPU N
  |            |            |              |
shard 0      shard 1      shard 2        shard N
  |            |            |              |
NVMe Q0      NVMe Q1      NVMe Q2        NVMe QN
```

The design should avoid global structures wherever possible.

Specifically avoid:

- global inode locks
- global journal locks
- global allocator locks
- global dirty-page queues
- global LRU locks
- global free-space trees on the write path
- filesystem-wide transactions for ordinary operations

Cross-shard operations may be slower than local operations.

That tradeoff is acceptable.

---

# 5. NVMe-Native I/O Path

The system should avoid the traditional stack:

```text
syscall
 -> VFS
 -> page cache
 -> filesystem
 -> block layer
 -> scheduler
 -> driver
 -> NVMe
```

Instead, storage shards should communicate directly with NVMe submission/completion queues.

The desired path is:

```text
task
  |
submit I/O
  |
NVMe SQ
  |
SSD
  |
NVMe CQ
  |
scheduler resumes task
```

Requirements:

- no mandatory syscall per I/O
- no mandatory context switch
- no generic block scheduler
- no mandatory intermediate buffer
- no mandatory page cache
- support direct DMA into application-owned buffers
- queue ownership should preferably be CPU-local

Storage completions should integrate directly with the runtime/task scheduler.

---

# 6. Zero-Copy Data Path

Large reads and writes should be zero-copy whenever possible.

The target read path is:

```text
object lookup
    |
metadata lookup in RAM
    |
physical extent resolution
    |
NVMe DMA
    |
application buffer
```

Avoid:

```text
NVMe
 -> kernel buffer
 -> page cache
 -> memcpy
 -> application
```

Scatter/gather operations must be first-class.

Large logical reads should be split into independent NVMe commands and submitted concurrently.

---

# 7. Extent-Based Storage

The primary durable storage unit should be a variable-sized extent.

The internal format must not fundamentally revolve around 4 KiB filesystem blocks.

Example:

```text
File

0          256M         512M         768M          1G
| extent A | extent B   | extent C   | extent D    |
```

Extent sizes may be adaptive.

Large sequential data should ideally use large extents.

Small-object workloads may use smaller extent classes.

---

# 8. Immutable Extents

Large extents should normally be immutable after creation.

Updates should create new extents rather than modify existing extents in place.

Benefits expected from this model include:

- simple crash consistency
- simple checksumming
- efficient snapshots
- cheap copy-on-write
- easy versioning
- simpler concurrent readers
- elimination of read/write locking on immutable data

Old extents become garbage only after all references disappear.

---

# 9. Small Write Delta Log

Small or unaligned writes must not require rewriting a large extent.

Instead:

```text
base extent
    +
delta records
```

Example:

```text
delta {
    object
    logical_offset
    length
    payload
    sequence
}
```

Small writes should be appended to a sequential per-shard log.

Reads logically compose:

```text
base extent + applicable deltas
```

When a threshold is reached, the system may compact:

```text
base extent + deltas
           |
           v
      new extent
```

Compaction must preferably happen asynchronously.

Foreground application writes should not normally wait for extent consolidation.

---

# 10. Separate Large and Small Write Paths

Large aligned writes should bypass the small-write log and be written directly as extents.

Example:

```text
write request
     |
     +---- large/aligned ----> immutable extent
     |
     +---- small/unaligned --> delta log
```

The threshold should be dynamically tunable.

The filesystem should be able to learn optimal thresholds based on workload and device properties.

---

# 11. Log-Structured Metadata

Metadata durability should primarily use append-only logs.

Ordinary metadata updates should not synchronously rewrite durable B-trees or other complex indexes.

Example:

```text
{
    txid
    operation
    object
    parent
    name
    attributes
}
```

The durable metadata representation should optimize for sequential append performance.

The runtime representation should separately optimize for fast lookup.

---

# 12. RAM-First Metadata

Frequently accessed metadata should primarily live in RAM.

Possible structures include:

- hash tables
- radix trees
- ART
- tries
- learned indexes
- compact object maps

Persistent metadata should consist mainly of:

```text
checkpoint
+
subsequent log
```

Recovery:

```text
load latest checkpoint
        |
replay log tail
        |
reconstruct RAM indexes
```

Metadata lookup structures therefore do not need to have the same format as persistent structures.

---

# 13. Checkpointing

The filesystem should periodically produce compact immutable metadata checkpoints.

Checkpoints should:

- allow bounded recovery time
- be written asynchronously
- avoid stopping foreground writes
- allow older log segments to be reclaimed

Multiple checkpoint generations should be retained temporarily for crash safety.

---

# 14. Transactions

Transactions should be scoped as narrowly as possible.

Prefer:

```text
per shard
per directory
per object group
```

over:

```text
filesystem-wide transaction
```

Most operations should involve only one transaction domain.

Cross-domain operations should use explicit distributed transaction mechanisms only when unavoidable.

For example, cross-shard rename may be more expensive than same-shard rename.

This is acceptable.

---

# 15. Commit Model

Durable state should use a commit-record model.

Example:

```text
1. write immutable data

2. write commit record

3. issue persistence barrier

4. publish new state
```

The commit record might contain:

```text
transaction ID
object ID
logical range
physical extent
length
checksum
version
```

Crash semantics:

```text
extent without valid commit
    => garbage

valid commit
    => durable state
```

Avoid undo logging where possible.

Prefer redo/MVCC-style recovery.

---

# 16. MVCC

Readers should normally be lock-free.

Objects should have monotonically increasing versions.

For example:

```text
object 42

version 100
    -> extent A
    -> extent B

version 101
    -> extent A
    -> extent B'
```

Readers may retain references to older versions while writers construct newer versions.

Garbage collection can reclaim versions when no readers or snapshots reference them.

---

# 17. Snapshots

Snapshots should be cheap enough to be treated as ordinary operations.

Creating a snapshot should primarily involve capturing a metadata/root version.

It should not copy file contents.

Snapshots should naturally follow from immutable extents and MVCC.

---

# 18. Reflinks

Copying an object should initially create additional references to existing extents.

Actual data copying should occur only on modification.

The native object API should expose cloning directly.

---

# 19. Lifetime-Aware Allocation

The allocator must understand expected data lifetime.

Allocation should conceptually support:

```text
allocate(
    size,
    expected_lifetime,
    temperature,
    rewrite_frequency,
    durability_class
)
```

Objects with similar expected invalidation times should be physically colocated.

Possible classes:

```text
ephemeral
short
medium
long
permanent
```

The classification may be:

- supplied by applications
- inferred from history
- predicted automatically
- adapted dynamically

---

# 20. NVMe Flexible Data Placement

NVMe FDP should be supported as a first-class feature where available.

Lifetime classes should map naturally to FDP Reclaim Unit Handles.

Example:

```text
temporary data -> RUH 0
hot data       -> RUH 1
metadata       -> RUH 2
cold data      -> RUH 3
```

The filesystem should attempt to ensure that data placed in the same reclaim unit has similar invalidation behavior.

The goal is to minimize device-level write amplification.

---

# 21. Avoid Double Garbage Collection

The filesystem should avoid a design where:

```text
filesystem GC
+
SSD FTL GC
```

both repeatedly move the same data.

Where FDP or equivalent device interfaces exist, filesystem placement and SSD reclamation should cooperate.

When such hardware support is unavailable, the filesystem should still group writes based on lifetime to improve FTL behavior.

---

# 22. Capacity Overprovisioning

The design should explicitly trade spare capacity for predictable performance.

Maximum space utilization is not a goal.

The filesystem should be able to reserve substantial unused capacity.

Example:

```text
physical capacity: 8 TB
usable capacity:   5-6 TB
```

This reserve should be used to:

- reduce foreground garbage collection
- reduce write amplification
- allow large sequential allocation
- reduce fragmentation
- make cleaning asynchronous
- improve tail latency

The design principle is:

> Space may be spent to buy latency.

---

# 23. Garbage Collection

Garbage collection must preferably run asynchronously.

Foreground writes should rarely or never need to synchronously trigger cleaning.

GC should prioritize segments/extents using factors such as:

```text
percentage dead
age
remaining live bytes
predicted future invalidation
device reclaim-unit boundaries
```

GC resources should be shard-local where possible.

---

# 24. Background Work

The system should treat the following as asynchronous background activities:

- compaction
- delta consolidation
- checkpoint generation
- garbage collection
- lifetime reclassification
- metadata packing
- cold-data migration
- integrity scanning

Foreground operations should not wait for these unless required by a strict durability request.

---

# 25. Cache Architecture

Do not implement a mandatory generic page cache.

Instead, support explicit cache policies.

For example:

```text
CACHE_NONE
CACHE_METADATA
CACHE_RANDOM
CACHE_SEQUENTIAL
CACHE_PINNED
CACHE_APPLICATION_MANAGED
```

Applications should be able to opt out of caching entirely.

Large sequential workloads should not pollute caches used for random workloads.

---

# 26. Memory-Mapped Interface

Consider providing a memory-oriented API for appropriate objects.

The system may expose objects through a virtual-memory-like interface while retaining control over persistence and caching.

This should not require reproducing traditional `mmap()` semantics internally.

---

# 27. CXL Support

The architecture should allow future use of CXL memory-semantic storage.

If CXL-capable storage is available, the filesystem may expose:

```text
hot metadata
small writes
transaction logs
small objects
```

through load/store-accessible device memory.

Large or cold data may remain on NAND.

The filesystem architecture should therefore avoid assuming that all persistent storage is block-addressed.

---

# 28. Heterogeneous Storage

The storage engine should support multiple storage classes.

Potential hierarchy:

```text
DRAM
CXL memory
SCM / persistent memory
high-end NVMe
capacity NVMe
remote storage
```

Placement should depend on:

```text
latency requirement
temperature
object lifetime
size
durability
cost
```

Migration between classes should be transparent to the object API.

---

# 29. Checksumming and Integrity

Every durable extent should have integrity protection.

Checksums may be stored:

- in extent descriptors
- alongside metadata
- through NVMe Protection Information
- through storage-device-native integrity mechanisms

Where NVMe PI is available, the filesystem should exploit it rather than redundantly performing all integrity operations in software.

---

# 30. Replication

Redundancy should preferably operate at the object or extent level rather than through traditional RAID semantics.

For example:

```text
extent A
  -> NVMe 0
  -> NVMe 1
```

or erasure-coded groups.

Replication should be compatible with:

- immutable extents
- versioning
- checksums
- asynchronous repair

---

# 31. Device Parallelism

The storage system should exploit all available device queues and multiple NVMe devices concurrently.

A single logical operation may fan out across many device requests.

Example:

```text
128 MiB logical read

 -> command 0
 -> command 1
 -> command 2
 -> ...
 -> command N
```

Completion order should not need to match submission order.

---

# 32. CPU Affinity

Where possible:

```text
application task
      |
CPU N
      |
storage shard N
      |
NVMe queue N
```

should remain on the same CPU.

Avoid bouncing:

- cache lines
- queue ownership
- completion handling
- metadata structures

between cores.

---

# 33. NUMA Awareness

On multi-socket systems:

- metadata should preferably live on the NUMA node that owns it
- NVMe queues should be driven by CPUs local to the device
- DMA buffers should be allocated from appropriate NUMA nodes
- cross-node operations should be minimized

NUMA topology should be part of storage placement decisions.

---

# 34. Locking

The ideal fast path should not require contended locks.

Prefer:

- ownership
- message passing
- immutable structures
- per-core data
- RCU-style reads
- atomic publication
- MVCC

over shared mutexes.

Locks may exist, but they should not be routinely shared between CPU cores.

---

# 35. Namespace Design

The filesystem namespace must not require walking persistent on-disk directory trees for every lookup.

Directory indexes should be RAM-resident where possible.

Path resolution should target approximately:

```text
path lookup
    -> DRAM namespace lookup
    -> object ID
```

rather than multiple dependent storage reads.

---

# 36. Object IDs

Objects should use stable identifiers independent of physical placement.

Example:

```text
object_id = 128-bit identifier
```

Physical extent locations may change without changing object identity.

This allows:

- relocation
- GC
- tier migration
- replication
- defragmentation

without rewriting namespace references.

---

# 37. Metadata/Data Separation

Metadata and data must be independently placeable.

They should not be forced into the same allocation policy.

Metadata may benefit from:

- smaller allocation units
- stronger replication
- lower latency media
- longer retention
- different FDP classes

---

# 38. Hot/Cold Separation

The filesystem should dynamically identify:

```text
hot
warm
cold
```

objects or extents.

Hot and cold data should not be repeatedly mixed in the same physical reclaim regions.

---

# 39. Learned Policies

The system should be designed so that policy components can later be replaced by adaptive or learned mechanisms.

Candidates include:

- lifetime prediction
- hot/cold classification
- cache admission
- cache eviction
- extent sizing
- compaction thresholds
- device placement
- prefetching
- GC scheduling

Policy must remain separate from correctness mechanisms.

A poor prediction must degrade performance, not corrupt data.

---

# 40. Recovery

Crash recovery should avoid full-device scans.

Normal recovery should consist primarily of:

```text
load checkpoint
      +
replay bounded log
```

Uncommitted extents can be reclaimed later.

Recovery time should depend primarily on the amount of metadata written since the last checkpoint, not total filesystem size.

---

# 41. fsync Equivalent

The native durability primitive should be more explicit than POSIX `fsync()`.

Possible durability levels:

```text
VOLATILE
PROCESS
HOST
DEVICE
REPLICATED
```

For example:

```text
commit(tx, DEVICE)
```

means the transaction is confirmed durable on local persistent media.

This avoids forcing every application into the ambiguous semantics of traditional `fsync()`.

---

# 42. Failure Atomicity

A committed transaction must be observable either entirely before or entirely after a crash.

Partial namespace or metadata updates must not appear.

The implementation should preferably achieve this through immutable records and atomic publication rather than rollback.

---

# 43. Metadata Operations

The architecture should specifically optimize metadata-heavy workloads such as:

```text
create
unlink
rename
stat
open
directory enumeration
small-file creation
small-file deletion
```

Metadata scalability must remain high as CPU count increases.

---

# 44. Small Files

Small files should not necessarily receive independent large extents.

Potential implementation strategies include:

- packing small objects into log segments
- storing very small data inline with object metadata
- grouping similar-lifetime objects
- promoting objects into standalone extents as they grow

Small-object placement must remain lifetime-aware.

---

# 45. Large Files

Large files should use very large extents where possible.

Sequential workloads should produce near-device-optimal large I/O requests.

Large file performance should not be constrained by structures optimized around 4 KiB updates.

---

# 46. Direct I/O as the Normal Case

The distinction between:

```text
buffered I/O
direct I/O
```

should largely disappear internally.

Applications or runtime policies decide whether data should be cached.

Storage itself should fundamentally support direct device interaction.

---

# 47. Scheduling

Storage request scheduling should understand:

- latency-sensitive requests
- background GC
- bulk sequential workloads
- metadata requests
- prefetch
- durability barriers

Foreground latency-sensitive I/O must take priority over background maintenance.

---

# 48. Tail Latency

The design must explicitly optimize p99 and p99.9 latency, not only average throughput.

In particular, avoid synchronous:

- garbage collection
- large metadata checkpoints
- compaction
- device-wide locks
- global journal commits

on foreground paths.

---

# 49. Metrics

The system should continuously expose at least:

```text
read IOPS
write IOPS
read bandwidth
write bandwidth

p50 latency
p95 latency
p99 latency
p99.9 latency

CPU cycles / read
CPU cycles / write

host write amplification
device write amplification

GC bytes moved
GC CPU cost

cache hit rate

metadata lookup latency

queue depth
queue utilization

cross-shard operations
cross-NUMA operations
```

---

# 50. Primary Performance Goals

The implementation should aim to approach hardware limits before optimizing secondary functionality.

The desired high-level objective is:

```text
application-visible performance
≈
raw NVMe performance
-
minimal filesystem overhead
```

For sufficiently large direct operations, filesystem overhead should ideally become negligible compared with the device.

---

# 51. Benchmarking Requirements

Benchmarks must include:

### Large sequential I/O

```text
1 MiB
4 MiB
16 MiB
128 MiB
```

### Random I/O

```text
4 KiB
16 KiB
64 KiB
256 KiB
```

### Mixed workloads

```text
70/30 read/write
50/50 read/write
30/70 read/write
```

### Metadata workloads

- create-heavy
- delete-heavy
- stat-heavy
- rename-heavy
- directory traversal
- millions of small files

### Durability workloads

- sync write per operation
- batched commits
- group commits

### Long-running workloads

Long-running tests must measure:

- steady-state performance
- write amplification
- GC behavior
- fragmentation
- tail latency

Short fresh-filesystem benchmarks are insufficient.

---

# 52. Baselines

At minimum compare against:

- ext4
- XFS
- Btrfs
- F2FS

where applicable.

Also compare the native object API against raw NVMe/SPDK access.

This allows measurement of actual filesystem overhead.

---

# 53. Design Philosophy

The filesystem should follow these principles:

1. **No global locks on normal data paths.**
2. **No global journal.**
3. **No mandatory page cache.**
4. **No mandatory 4 KiB internal abstraction.**
5. **No unnecessary copies.**
6. **No synchronous durable index rewriting for normal metadata changes.**
7. **Large immutable extents.**
8. **Small writes go to append-only delta logs.**
9. **Metadata is RAM-first and log-backed.**
10. **Readers should normally be lock-free.**
11. **Transactions should be local.**
12. **NVMe parallelism must be exposed rather than hidden.**
13. **Storage lifetime should influence physical placement.**
14. **Space should be traded for performance where beneficial.**
15. **Background maintenance should remain off foreground paths.**
16. **POSIX is a compatibility interface, not the native architecture.**
17. **Device capabilities such as FDP and PI should be exposed upward.**
18. **The storage stack should understand hardware topology.**
19. **Policy should remain separable from correctness.**
20. **The objective is to approach raw-device performance while retaining filesystem semantics.**

---

# 54. Non-Goals

The first implementation does not need to prioritize:

- compatibility with existing filesystem formats
- minimal storage overhead
- maximum disk utilization
- mechanical-disk performance
- legacy kernels
- POSIX as the primary interface
- compatibility with the traditional Linux block layer
- minimum implementation complexity
- old hardware
- removable storage
- network filesystem semantics

These may be added later if they do not compromise the core architecture.

---

# 55. Initial Prototype Scope

A useful first prototype should implement:

```text
object create/delete
directory namespace
large immutable extents
small-write delta log
RAM-resident metadata indexes
append-only metadata log
checkpoints
single-shard transactions
NVMe queue access
zero-copy reads/writes
crash recovery
basic checksumming
```

The prototype should intentionally omit complex features until the core architecture has been benchmarked.

Recommended implementation order:

```text
raw NVMe async I/O
        ↓
extent allocator
        ↓
object store
        ↓
metadata log
        ↓
RAM index
        ↓
transactions
        ↓
namespace
        ↓
delta writes
        ↓
checkpoint/recovery
        ↓
GC
        ↓
multi-core sharding
        ↓
FDP placement
        ↓
POSIX compatibility
```

---

# 56. Long-Term Direction

The long-term system should increasingly blur the boundaries between:

```text
filesystem
virtual memory
storage scheduler
NVMe driver
SSD placement policy
runtime scheduler
```

Rather than treating these as independent layers, they should cooperate around a common object-oriented storage model.

The desired end state is a storage system designed for modern NVMe/CXL hardware rather than one carrying assumptions inherited from disks and 1980s Unix filesystem architecture.