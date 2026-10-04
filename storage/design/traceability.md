# Requirements traceability

Every source section has a one-to-one adapted section in `requirements.md`.
All target features below are requirements, not delivered filesystem support.
S0 includes a limited executable host model; its evidence does not close S1 onward.
Gate definitions and status are in `roadmap.md`. The exact original bytes are
preserved in `original-requirements.md`; SHA-256 is verified by the checker.

| ID | Original source section | Adaptation / substantive qualification | Gates |
|---|---|---|---|
| R01 | 1. Core Architecture | §1. Retained; native engine and XFS are peer backends. | S4,S5,X1,X3 |
| R02 | 2. Native API | §2. Retained with rights, leases, cancellation, bounded batching and errors. | S1,S4 |
| R03 | 3. POSIX Compatibility | §3. Optional safe semantic personality; no C ABI or binary promise. | S8,S11 |
| R04 | 4. Sharded Architecture | §4. Retained after SMP; stable shard identity and bounded coordination. | S8 |
| R05 | 5. NVMe-Native I/O Path | §5. Adapted to mediated shared queues; no raw untrusted NVMe commands. | S2,S3,S4 |
| R06 | 6. Zero-Copy Data Path | §6. Conditional zero-copy with pinned directional leases and safe teardown. | S2,S3,S4 |
| R07 | 7. Extent-Based Storage | §7. Retained variable extents; physical LBA/atomicity constraints remain. | S3,S4 |
| R08 | 8. Immutable Extents | §8. Retained with generations and all reader/recovery references before reclaim. | S4,S7 |
| R09 | 9. Small Write Delta Log | §9. Retained; bounded deltas, overlap/truncate semantics and pressure control. | S5,S7 |
| R10 | 10. Separate Large and Small Write Paths | §10. Retained; measured tunable policy under common correctness semantics. | S5,S10 |
| R11 | 11. Log-Structured Metadata | §11. Retained for native logs; allocation/quota changes included; XFS separate. | S4,S6,X2 |
| R12 | 12. RAM-First Metadata | §12. Adapted to RAM hot set plus demand-loaded cold indexes and hard budgets. | S6,S7 |
| R13 | 13. Checkpointing | §13. Retained with durable root publication, retained logs and tail bounds. | S6 |
| R14 | 14. Transactions | §14. Retained local transactions; explicit isolation and unsupported cross-domain state. | S4,S8 |
| R15 | 15. Commit Model | §15. Corrected to dependency-durable fence before commit, then commit-durable fence. | S0,S3,S4,S6 |
| R16 | 16. MVCC | §16. Retained; checked versions, pinning, reclamation and memory-model prerequisites. | S4,S7,S8 |
| R17 | 17. Snapshots | §17. Retained; defined snapshot scope, retention accounting and coordinated cuts. | S7,S8 |
| R18 | 18. Reflinks | §18. Retained; transactional references, quotas and security-domain restrictions. | S7,X3 |
| R19 | 19. Lifetime-Aware Allocation | §19. Retained as bounded untrusted placement hints, never authority. | S7,S9 |
| R20 | 20. NVMe Flexible Data Placement | §20. Capability-gated FDP with discovered mappings and ordinary-NVMe fallback. | S9 |
| R21 | 21. Avoid Double Garbage Collection | §21. Cooperation goal retained; no promise to eliminate opaque device GC. | S7,S9,S10 |
| R22 | 22. Capacity Overprovisioning | §22. Retained configurable reserve; distinct filesystem/FTL reserve accounting. | S7 |
| R23 | 23. Garbage Collection | §23. Retained asynchronous GC; progress, reference safety and backpressure required. | S7 |
| R24 | 24. Background Work | §24. Retained with bounded background work and minimum maintenance service. | S6,S7,S10 |
| R25 | 25. Cache Architecture | §25. Retained explicit cache policy; pinning quotas and cross-path coherence. | S5,S7 |
| R26 | 26. Memory-Mapped Interface | §26. Deferred optional memory view; VM lifetime and persistence contract first. | S11 |
| R27 | 27. CXL Support | §27. Deferred optional CXL; coherence/load-store does not imply persistence. | S11 |
| R28 | 28. Heterogeneous Storage | §28. Retained future tiering; no silent durability downgrade during migration. | S9,S11 |
| R29 | 29. Checksumming and Integrity | §29. Strengthened to end-to-end checksum plus identity/generation; PI is complementary. | S4,S6,S7 |
| R30 | 30. Replication | §30. Retained replicas/coding; explicit durable acknowledgement and failure domains. | S9,S11 |
| R31 | 31. Device Parallelism | §31. Retained parallel fanout under transfer/credit bounds and full completion accounting. | S3,S8,S10 |
| R32 | 32. CPU Affinity | §32. Retained locality; safe migration and laptop power-aware polling choice. | S8,S10 |
| R33 | 33. NUMA Awareness | §33. Retained capability-discovered NUMA; no hardcoded multi-socket requirement. | S8,S10 |
| R34 | 34. Locking | §34. Retained low contention; lock-free/progress claims require actual algorithms. | S8 |
| R35 | 35. Namespace Design | §35. Adapted RAM hot lookups to bounded cold lookups, naming and security checks. | S5,S7,X1 |
| R36 | 36. Object IDs | §36. Retained stable IDs plus generation/exhaustion; identifiers are not capabilities. | S4,S5,X1 |
| R37 | 37. Metadata/Data Separation | §37. Retained independent placement, preserving cross-tier commit dependencies. | S4,S9 |
| R38 | 38. Hot/Cold Separation | §38. Retained measured hot/cold policy with bounded tracking/migration cost. | S7,S9,S10 |
| R39 | 39. Learned Policies | §39. Retained learned-policy extension; outputs constrained by correctness and budgets. | S9,S10 |
| R40 | 40. Recovery | §40. Retained bounded normal restart; explicit corruption, demand paging and salvage. | S6 |
| R41 | 41. fsync Equivalent | §41. Replaced ambiguous PROCESS/HOST labels with precise receipt/failure-domain contracts. | S4,S9 |
| R42 | 42. Failure Atomicity | §42. Retained atomicity; distinguish unacknowledged commits, failures and unknown outcome. | S0,S4,S6,S8 |
| R43 | 43. Metadata Operations | §43. Retained metadata focus plus authority, conflict and namespace edge-case tests. | S5,S7,S8 |
| R44 | 44. Small Files | §44. Retained small-object packing with independent integrity/security/accounting. | S5,S7,S10 |
| R45 | 45. Large Files | §45. Retained large extents/requests split by transport limits; bounded partial reads. | S4,S5,S10 |
| R46 | 46. Direct I/O as the Normal Case | §46. Retained explicit buffering; direct path remains capability-mediated. | S3,S4,S5,S7 |
| R47 | 47. Scheduling | §47. Retained priority scheduling plus fairness, bounded overload and maintenance progress. | S3,S7,S8 |
| R48 | 48. Tail Latency | §48. Retained tail goals; publish admission/failure costs, no blanket real-time guarantee. | S7,S10 |
| R49 | 49. Metrics | §49. All requested metrics retained; unavailable device WA explicit; safety/energy metrics added. | S4,S7,S10 |
| R50 | 50. Primary Performance Goals | §50. Adapted performance-first goal to safety-first, equivalent-semantics measurement. | S10 |
| R51 | 51. Benchmarking Requirements | §51. Full source matrix retained; occupancy, RAM, retention, energy and fault dimensions added. | S10 |
| R52 | 52. Baselines | §52. All four filesystem and raw/SPDK baselines retained, with controlled semantics. | S10 |
| R53 | 53. Design Philosophy | §53. All20 source principles retained as goals under safety and XFS-specific exceptions. | S0,S4,S7,S8,S10 |
| R54 | 54. Non-Goals | §54. XFS request overrides format non-goal; broader whole-OS goals not silently removed. | X1,X2,X3,S11 |
| R55 | 55. Initial Prototype Scope | §55. Reordered by real compiler/DMA/durability dependencies; host model is not filesystem. | S0,S1,S2,S3,S4,S5,S6,S7,S8,S9 |
| R56 | 56. Long-Term Direction | §56. Retained cooperative object architecture, preserving typed containment boundaries. | S11 |
| USER-XFS | Additional explicit user request, 2026-10-03 | §57. Separate XFS on-disk service; clean read-only → safe replay → declared read-write profile. No Linux C embedding. | X0,X1,X2,X3 |

## Aurora-derived cross-cutting requirements

These additions follow the custom kernel/language and whole-system requirements;
they are not attributed to the attached source or inferred as user-selected defaults.

| Contract | Why it is required | Main source sections affected |
|---|---|---|
| A1 | Capabilities, DMA leases, queues and revocation prevent unchecked device access. | 2,5,6,31,32,46,47 |
| A2 | Persistence ordering, outcome uncertainty and retry identity define honest durability. | 11,14,15,40,41,42 |
| A3 | Stable wire formats, hostile parsing and root/log retention separate disk ABI from compiler layout. | 11,12,13,29,40,57 |
| A4 | Bounded memory, pinning, log, GC and retention prevent resource-based correctness failures. | 9,12,13,17,22,23,24,25,47 |
| A5 | Cross-shard atomicity requires coordination; unsupported is not non-atomic substitution. | 3,4,14,17,42,43 |
| A6 | Multi-user namespace rights/quotas and an optional encryption design support whole-system use. | 1,2,18,29,35,43,57 |
| A7 | Independent, fault-injected and exact-profile evidence prevents unearned support claims. | All; especially40,48,50,51,52,55,57 |
| A8 | Research provides hypotheses, not inherited safety/performance guarantees. | 12,23,27,28,34,39,50,56 |

## Explicitly preserved source examples

The variable-extent and large/direct versus small/delta paths remain requirements.
The lifetime class names, cache choices, extra-capacity tradeoff, requested
latency/throughput metrics, every benchmark size and mix, and all requested
comparison filesystems remain present. Illustrative RUH numbers, extent sizes
and 8 TB capacity split remain examples to validate rather than mandatory device
geometry or defaults. No source section is dropped because its target is late.
