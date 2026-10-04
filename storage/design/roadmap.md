# Storage implementation roadmap and observable gates

2026-10-03. Stages are dependencies, not delivery dates or completion percentages.
S0 is integrated and independently reviewed: the requirement traceability and
bounded host-only crash model are exercised by the aggregate test target.
Milestone014 verifies readonly byte spans and read-only PCI BAR admission.
Milestone015 integrates checked endian readers, CRC32C and the restricted XFS
512-byte v5 header-integrity probe, with independently reviewed library tests and
an offline real-header fixture. Combined parent milestone acceptance is tracked
in [the verification record](../../docs/verification.md).

This is only the initial byte/parsing slice of S1 and X0. General resource
ownership, asynchronous buffer leases and complete XFS parsing remain open.
Read-only AMD-Vi discovery is an observation gate, not DMA isolation. There is
still no active IOMMU/NVMe queue driver, mounted target filesystem, XFS log replay
or read-write support, or physical hardware qualification. A host model or header
checksum result does not establish any of those capabilities.

## S0. Preserve requirements and test the durability idea

Dependencies: user input and current project contract.

Deliverables: verbatim input/hash; all-56-section adaptation and traceability;
separate XFS requirement; source-backed ordering/format contract; a bounded
in-memory crash model with positive and deliberately broken protocols.

Acceptance:
- Verify exact input bytes and one mapping per numbered section, plus XFS.
- Enumerate every represented crash image at every modeled protocol cut.
- Safe protocol must recover exactly old or new state, never a mixed transaction;
  acknowledged commits must recover new, and valid unacknowledged commits may
  recover new. Missing/corrupt committed dependencies must be diagnosed.
- Removing the dependency-durable fence must yield a reproduced counterexample.
  Removing the commit-durable fence must violate acknowledged durability.
- Document finite state/idealizations and lack of target, device or proof coverage.
- Independent review reproduces the tests and challenges assumptions.

Next useful implementation: S1 checked binary/integrity libraries and X0 parser
fixtures may proceed alongside the kernel's read-only hardware work. Storage DMA
cannot proceed merely because a BAR mapping succeeds.

## S1. Native checked bytes, parsing and resource foundations

Dependencies: reviewed readonly span compiler candidate; explicit integer,
range and failure semantics; kernel/user library profiles.

First narrow slice: real Aurora endian readers and CRC32C over source-owned byte
arrays, with explicit lengths, offsets and virtual zeroing of a checksum field.
Native u64 may carry bounded 16/32-bit decoded values; do not invent unsupported
u16/u32 types. Add 64-bit readers only with checked shift/range tests. The library
must not expose raw pointers, mutable aliased spans or compiler-layout casting.
This slice can support X0 without waiting for full async resource classes.

Further prerequisites for target storage: move/drop ownership, borrowed buffers,
checked allocator/quota capabilities, async lease retention/cancellation and a
defined atomic memory model. Keep these distinct from a simple readonly parser.

Acceptance:
- Positive, truncated, misaligned, overflow and malicious-offset parser tests;
  known-answer CRC32C vectors, split updates and checksum-field substitution;
  cross-check through independent scalar/oracle implementations.
- Native executable fixtures consume actual library results, including rejection
  and status cases. No unused module stubs count.
- Lifetime/source/IR rejection tests prevent escape, mutation conflicts, stale
  views and unchecked narrowing. Exact bytes, endian and offsets match fixtures.
- For resource interfaces: failure/partial construction, cancellation and service
  death reclaim authority once; borrowed pages cannot be reused early.
- Record native link dependencies and independently review the extended language
  contracts. Passing a reader does not prove general async memory safety.

## S2. DMA-safe device authority before NVMe activation

Dependencies: validated PCI resources and inactive-state policy, ACPI/IOMMU
topology, memory ownership, complete interrupt/context isolation needed by the
driver profile, timer/timeout contract and service supervision.

Implement a broker with range-scoped device ownership, IOMMU mappings, queue
epochs, bounded pinned leases and deny-by-default administrative commands.

Acceptance:
- Prove untrusted services cannot program DMA outside leased pages/ranges.
- Inject stale mappings, malformed SG lists, invalid direction, double submit,
  duplicate completion and generation wrap/exhaustion.
- Stop submission, quiesce device, invalidate IOMMU/TLB/interrupt state, then
  scrub/reuse pages. Repeat service death, reset, hot-unplug and resume paths.
- A failed quiescence/invalidation path quarantines memory/device rather than
  pretending cancellation is complete.
- Negative emulator gates and independent review precede enabling bus mastering.

## S3. One emulated NVMe transport with durable primitives

Dependencies: S2; pinned Base/NVM/PCIe spec revisions; disposable guest namespace.

Implement Identify-based capabilities, queue setup and checked read/write/flush
or FUA, bounded split I/O, completion, timeouts/reset and explicit error states.

Acceptance:
- Record namespace/LBA/metadata formats, transfer limits, queue limits, volatile
  write-cache, PI and power-fail atomicity/boundary properties.
- Read/write known patterns on only the disposable image; detect out-of-range
  requests, phase/tag/queue-generation errors and partial completions.
- Inject write failure, flush failure, timeout, controller reset and completion
  loss. No durable receipt on an unsupported or failed persistence contract.
- Run reorder/lost/torn-write simulation in addition to QEMU; QEMU command
  success alone does not model real SSD firmware or sudden power loss.
- Confirm normal image restoration and rerun existing kernel emulator gates.

## S4. Single-shard native extent/object transactions

Dependencies: S1 resource interfaces, S3, reviewed A2 fault model and A3 record
format. A file-backed host engine may precede the target, labeled separately.

Implement checked extent allocation, create/read/write/delete object operations,
integrity, manifest/redo log and two-fence durable commit with outcome tokens.

Acceptance:
- Execute actual target object operations, persist, restart and recover bytes.
- Crash at every I/O boundary and tear each permitted record region; vary
  completion and media-persistence ordering independently.
- Atomic two-object updates always recover old/old or new/new. Every returned
  LocalPersistent receipt survives modeled power loss. Unknown outcome retry
  uses the same digest/result rather than allocating/charging a second object.
- Validate stale/foreign filesystem, object, extent and request generations;
  checksummed wrong-owner records fail. Failed transactions release reservations
  without freeing reachable extents.
- Freeze a versioned format only after independent review and golden-wire tests.

## S5. Namespace, large writes and bounded small deltas

Dependencies: S4; checked text/byte naming and capability file-service semantics.

Implement directories, create/remove/rename, sparse files, truncated ranges,
large immutable extents, bounded delta logs and explicit cache policy.

Acceptance:
- Same-shard rename/replace and multi-object namespace updates are crash atomic;
  cross-domain operations fail explicitly until S8.
- Test UTF-8/name byte policy, symlink/cycle bounds, directory enumeration,
  open-unlink, permission changes and access denial across two principals.
- Overlapping deltas, holes/truncate/zero extension, threshold transitions and
  consolidation return identical logical bytes to a simple independent model.
- High delta count/low memory produces bounded backpressure or failure, not
  unbounded read amplification or a silently inconsistent result.
- Count actual copied/pinned bytes for large I/O before claiming zero-copy.

## S6. Checkpoints and bounded restart

Dependencies: S4/S5; root-slot atomicity or reviewed torn-detection scheme;
bounded demand-loadable metadata index.

Acceptance:
- Concurrent checkpointing captures a precise committed cut; new transactions
  remain recoverable from the checkpoint plus retained log tail.
- Crash during pages, manifest, slot publication and old-log reclamation; repeat
  crashes during recovery. Never lose an acknowledged commit via fallback.
- Detect corrupt or mismatched newer roots/dependencies and report recovery mode
  explicitly. No full-device scan on the normal path.
- Sweep total dataset size above RAM while holding the replay-tail bound;
  record bytes read, records processed, peak RAM and time separately.
- Stop checkpoint progress under load; log bounds trigger admission control
  before a budget is exceeded. Emergency diagnostic mode is clearly separate.

## S7. Resource-safe GC, retention and multi-user operation

Dependencies: S5/S6; durable reachability/refcount or tracing protocol;
epoch-safe readers, quotas and background scheduling.

Implement asynchronous consolidation/cleaning, snapshots, reflinks, reserve
accounting, cache eviction, integrity scanning and bounded maintenance budgets.

Acceptance:
- Readers/snapshots/reflinks/inflight I/O/recovery roots never reference freed
  storage across relocation, interrupted GC and reboot.
- Fill user capacity while snapshots pin old data; remaining emergency reserves
  stay usable for supported cleanup/recovery. No false success, unbounded spin
  or unauthorized retention deletion occurs.
- Snapshot/clone charging, quota exhaustion and shared extents cannot transfer
  another tenant's data or consume its allocation authority.
- No-space, low-RAM, stuck reader, maintenance starvation and policy mistakes
  produce the specified Normal/Pressure/Throttled/ReadOnly behavior.
- Complete the optional encrypted-volume design/implementation gate for any
  release profile claiming at-rest protection, with key lifecycle and recovery
  tests. Unencrypted and encrypted performance profiles remain explicit.

## S8. SMP shards, topology and cross-shard atomicity

Dependencies: actual SMP, complete context isolation, a language memory model,
S7 and bounded IPC. The current three-domain single-CPU fixture is insufficient.

Acceptance:
- Parallel independent shards show no shared contended normal-path journal or
  allocator bottleneck; measure rather than infer scalability.
- Stress queue ownership/migration, CPU/NUMA placement, shutdown and restart;
  no stale capability or completion can cross epochs.
- Cross-shard prepare/decision/install recovery passes every participant and
  coordinator crash, including lost decision replies and resource exhaustion.
- Multi-shard snapshots and atomic rename meet the declared consistency cut;
  pending decisions cannot expose mixed namespace state.
- Demonstrate fairness for latency-sensitive, bulk and minimum-maintenance work.

## S9. Optional placement, replicas and tiering

Dependencies: qualified capabilities on the actual devices, S7/S8, metrics.

Acceptance:
- FDP configuration/mapping checks, invalid/changed-hint handling and ordinary
  fallback preserve identical correctness; compare steady-state WA and tails.
- PI errors are propagated while end-to-end identity/integrity remains enforced.
- Replicated acknowledgements require the declared independent persistent domains;
  test failed replica, repair, stale generation and policy/membership changes.
- Tier migration persists replacement data/metadata before retiring the original;
  failure cannot downgrade an already promised durability class.
- No optional capability becomes a hidden minimum requirement for Framework.

## S10. Performance and physical-device qualification

Dependencies: correctness stages for each measured feature, independent review,
dedicated media and explicit authorization for destructive physical tests.

Acceptance:
- Run the full requirements §51 workload matrix against applicable §52 baselines.
  Record exact hardware/firmware, clocks/power settings, thermal state, RAM,
  filesystem/tool versions, usable capacity/reserves, cache, integrity/encryption,
  durability and queue depths. Use repeated trials and raw histograms.
- Document steady-state convergence/preconditioning and the observation interval;
  include old/fragmented data, high occupancy, retained snapshots and low RAM.
- Report bandwidth/IOPS, cycles, memory, WA, all requested percentiles and failures,
  plus laptop idle/load energy and polling cost. Unknown counters stay unknown.
- Derive numeric release budgets from measured baselines and intended workloads;
  do not retroactively choose thresholds only to label a result successful.
- Power-loss and reset testing on the exact controller/firmware tuple validates
  the declared persistence assumptions. QEMU/model results are separate evidence.

## S11. Whole-system integration and later personalities

Dependencies: mature native runtime, allocator/VM, file-service capabilities,
accounts, boot/update trust and operational tooling; backend-specific earlier gates.

Acceptance:
- Boot/use the native system with recoverable package and format updates,
  backup/restore, scrub/diagnostics, quota/permission tools and repair review.
- Optional POSIX semantics name exact supported operations and exclusions through
  safe native APIs; no C ABI compatibility is smuggled in.
- Mutable mapping/CXL/remote backends each pass their own persistence, isolation,
  poison/reset and interrupted-operation model before advertising support.
- All Framework storage/security/power profile rows pass on named hardware;
  broader whole-laptop and Zen/RDNA targets remain separately tracked.

## X0. XFS wire-format inspection fixtures

Dependencies: S1 readonly byte/CRC slice, pinned XFS format references; no DMA or
mount capability required. Can run in parallel with S2/S3.

Acceptance:
- Decode source-owned or copied disposable-image bytes with explicit endian and
  bounds; verify v5 CRC across its declared covered buffer and zeroed CRC field.
- Reject malformed magic, truncated data, checksum/length errors, unsupported
  versions/features and arithmetic overflow as recoverable statuses.
- Cross-check with a pinned xfsprogs fixture producer and independent schema/
  known-answer vectors. Forbid claims of mount support from superblock probing.
- Keep XFS-specific format interpretation outside general std.binary/std.integrity
  mechanisms; no global mutable state or unsafe class casting.

## X1. Validated clean read-only XFS

Dependencies: X0, protected volume reads, S1 parsers/resources, explicit feature
allowlist and bounded validated clean-log recognition.

Acceptance:
- Read the advertised inode/directory/extent forms, sparse/unwritten data,
  symlinks and supported security metadata from disposable mkfs.xfs images.
- Compare tree inventory, names/attributes, logical contents and sparse behavior
  with pinned Linux/XFS and xfsprogs. Hash the image before/after; identical.
- Dirty log, unsupported incompatible/log features, cycles, forged ownership,
  invalid geometry and corrupt CRCs reject safely without writes.
- Negative permission checks and bounded traversal survive adversarial images.
- Unknown read-only-compatible bits never authorize writes; initial conservative
  refusal is allowed and reported honestly.

## X2. Safe XFS log replay

Dependencies: X1, S3 verified write ordering, full supported log/deferred-operation
formats and write authority to only a disposable overlay.

Acceptance:
- Replay every transaction/log item required by the advertised feature profile,
  including cancellation, intent/completion and unlinked/orphan processing.
- Interrupt each replay write and replay again; outcome equals the reference
  supported recovery result and remains structurally valid/interoperable.
- Unknown/corrupt/inconsistent logs stop without partial unsafe replay. No
  automated log zeroing. Read-only requested mount cannot secretly write without
  recovery authority.
- Differential replay against Linux's matching format architecture, followed by
  clean-image xfs_repair -n, plus semantic file/namespace comparison.

## X3. Read-write XFS and broader feature profiles

Dependencies: X2; checked allocator/free-space and inode/namespace mutation;
native security/quota integration and XFS journal reservations/forcing.

Acceptance:
- Bidirectional Linux↔Aurora round trips for all advertised read/write features;
  Linux accepts, recovers and checks every successfully committed image.
- Crash/no-space/low-memory/timeout tests at allocation, rename, truncate,
  unwritten conversion, orphan cleanup, quota and log-force boundaries.
- Versioned read/replay/write matrix for all features named in requirements §57;
  add each common/advanced feature only with its recovery/interop tests.
- Execute selected/adapted xfstests plus native isolated multi-user tests. Record
  unsupported cases and actual execution counts; don't call skipped tests passed.
- Clean read-only and replay are milestones; only this gate delivers the requested
  read-write XFS profile. Broad XFS compatibility remains scoped to tested features.

## Evidence, review and stop conditions

For each stage archive source/input hashes, tools/specs, command/logs, seeds,
expected assertions, actual failures and independent review. Kernel-affecting
changes also require the project aggregate and actual emulator gates; parser-only
model results cannot substitute. Failed tests remain evidence, not overwritten
with a passing summary. Missing tools are blocked tests.

Never touch user disks, reuse a mounted host volume for experiments, update host
bootloaders or publish this package remotely without the corresponding authority.
No calendar estimate is given for the whole filesystem or XFS implementation.
