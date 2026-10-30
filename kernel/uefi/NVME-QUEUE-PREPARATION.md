# CPU-only NVMe queue-page preparation

This is CPU-only page preparation, not a device driver, Identify command, disk
read or DMA-isolation gate. The separate active [NVMe broker](../../storage/README.md#protected-file-backed-nvme)
does not publish or reinterpret this API's CPU-only handles.

## Authority and fixed layout

`NvmeQueueBundle` owns exactly five move-only `PageLease` values acquired from
one existing `PhysicalPages` instance. It is not a second allocator, generic DMA
framework or extension of the CPU-only `PinLedger`. The prepared roles are:

- Admin submission page: intended device-read direction, two 64-byte entries
- Admin completion page: intended device-write direction, two 16-byte entries
- I/O submission page: intended device-read direction, two 64-byte entries
- I/O completion page: intended device-write direction, two 16-byte entries
- One shared Identify/read buffer page: intended device-write direction

Directions describe future intended use and grant no DMA permission. All five
pages are 4096-byte aligned, independently leased and distinct. The complete
page, including unused entries and padding, is zeroed and read back through
volatile CPU accesses. No command is encoded. The two-entry shape fits a page
and must fit the admitted CAP.MQES; this preparation profile requires
CAP.MPSMIN=0. Existing BAR admission independently requires an inactive NVMe 1.4
controller, BME clear, zero queue registers and a valid CAP page-size range.

The bundle constructor borrows the exact sixteen-page pool backing and physical
base; `arena_matches` and CPU-span alignment/extent checks are mandatory. Its
trusted adapter proves that this span actually maps that physical range with
exclusive CPU ownership. The C++ span cannot prove physical mapping identity,
exclude arbitrary trusted aliases, or establish DMA isolation. The pool and
backing must outlive all retained leases. Reinitializing/reconstructing their
allocator while pages remain held is forbidden.

Preparation additionally requires the exact endpoint 0000:00:02.0 and a live
`NvmeBarGrant`/`WindowAuthority` pair. Every `ready` query rechecks the complete
captured PCI snapshot and the original window ticket. Ticket revocation or a
new ticket for the same endpoint invalidates old readiness; copied receipt
bytes never restore authority. The bundle retains no authority pointer. A copied
stale receipt is inert and cannot pass a live-ticket check.

`NvmeQueueHandle` binds the noncopyable/nonmovable bundle address, globally unique
bundle epoch and monotonically increasing preparation generation. It contains
no page address or view. Even reconstruction at the same empty bundle address
cannot reuse a stale handle. Epoch/generation counters retire rather than wrap.
A failed allocation consumes its generation. Invalid role/direction enum values,
foreign handles, stale generations and repeated cancellation fail closed.

## Cancellation and retention

There is no callable publication, controller-write, activation, doorbell,
command, lease-import, address/view-export or completion operation. Therefore
all successful preparation is provably unpublished within this API. Cancellation
can still scrub after BAR revocation, without treating the expired BAR receipt
as live authority.

Before release, the bundle validates every owned lease, scrubs every allocated
byte and verifies zero. Only after all pages pass does it release any lease.
Partial acquisition failure performs the same operation on its actual prefix;
unrelated reservations are neither changed nor released. Successful preparation
also supports fragmented free pages without modifying intervening reservations. Failed preparation or
cancellation readback permanently retains the entire acquired prefix. There is
no retained-to-reusable transition. Destruction releases nothing, including an
accidentally dropped prepared bundle. Production exposes no failure injection;
explicit hosted test builds can corrupt one scrub readback, which only removes
release authority and never simulates a hardware completion.

A future potentially device-visible state must retain its leases after uncertain
publication, timeout, reset or owner death until authentic ordered device and
IOMMU quiescence/invalidation evidence is obtained. CPU scrub is not that
evidence. This increment intentionally provides no transition into that state.

## Guest integration

The payload initializes its existing pool at arena+0x50000 once, after owned-map
and page-table verification and before ACPI discovery. The same allocator is
passed explicitly through ACPI and PCI discovery into BAR preparation. The
separate protected-runtime stack allocator at arena+0xc0000 is unchanged.

The opt-in `bar-prepare` mode is a row of `platform-fixture` over the existing
clean, cold, namespace-free Q35 NVMe BAR fixture; no other row prepares pages.
The image cannot be combined with runtime or dormant-table profiles. BAR handoff version 4 and protected-runtime metadata version 3 share
arena+0x81000 with incompatible meanings; this change does not combine them and
does not invent a `DomainHandle` for the BAR-only profile.

Inside the still-live read-only BAR window, the guest poisons the empty pool's
first five pages, prepares them, checks every role and independently verifies
all 20,480 zero bytes. It then poisons those owned pages again, cancels the bundle,
checks duplicate cancellation fails and verifies all bytes and allocation counts.
The same page pool subsequently performs the existing payload allocation test.
The permanent optional bundle is never reconstructed over retained ownership.
All BAR mappings are then closed/revoked by the existing read-only teardown,
including preparation failure. The BAR ACPI parser now finishes before PCI
discovery begins. No arena or stack limit is changed.

Two exact records distinguish the CPU lifecycle from the seven BAR observations:

```
AURORA_NVME_PREPARED: pages=5 bytes=20480 generation=1 unpublished=1
AURORA_NVME_CANCELLED: pages=0 pool=0 scrubbed=20480
```

The guest issues no extra MMIO read, PCI configuration write, BME change, IOMMU
operation, address publication or device write. Existing serial, trace and
provenance validators require both records in order only for `bar-prepare` and
continue rejecting controller/queue/doorbell/DMA/interrupt events. The seven
historical BAR modes remain separately selectable and their aggregate is unchanged.

## Qualification commands and scope

Freeze source and tool hashes before execution, retain commands/status/logs, and use the shared native-resource
admission before starting any compilation or guest. A focused pass is not a
fresh full native aggregate or broad kernel qualification.

1. `make test-nvme-queues`: hosted lifecycle and production API tests; full and
   small generation limits; illegal test settings and incompatible profiles.
2. Repeat those tests in a `-Db_sanitize=address,undefined` build. Include the existing page-policy
   and PinLedger tests normally and under their sanitizer modes; their semantics
   must remain unchanged. No sanitizer credit applies to generated Aurora code.
3. `make test-uefi-bar`: all existing BAR/resource policy, serial/trace/provenance
   cases plus the new preparation transcript and trace adversaries. Repeat the
   three Python validators with and without `-O`.
4. Build `bar-prepare`, normal, BAR read/rejection/fault profiles and representative
   ACPI/PCI/runtime/IVRS/table profiles using the coordinated current compiler.
   Inspect actual linked call paths and `.su` frames for the unchanged 16 KiB
   bootstrap stack and guard. The preparation build invokes the focused stack
   validator against actual `.su` and linked call edges, using the existing frame
   reader. Independent linked review remains necessary. Do not infer safety from
   a hosted-only pass or widen stack, arena, payload or page-table limits.
5. With separately pinned QEMU/clean firmware and trace-coverage artifacts, run
   `make smoke-nvme-prepare AURORA_NVME_RECEIPTS=<fresh-directory>`. The receipt
   must contain the exact built image, cold pristine VARS, serial, complete trace,
   linked metadata and status 33. Use the existing namespace-free launch: no
   backing disk, host device, namespace, network or writable firmware source.
6. Re-run the existing clean BAR read and stock-active refusal controls on the
   changed adapter, along with negative write/revocation/alias checks when admitted.
   Restore/build the normal image, actually boot it, and retain matching evidence.
   Independent terminal source/artifact/claim review must close the gate.

Hosted coverage includes poisoned bytes, all roles/directions and invalid enum
values, complete-header mutations, foreign endpoint/authority/bundle, revocation
and same-endpoint ticket renewal, stale/reconstructed identity, generation
retirement, no free pages and all four partial prefixes, per-page preparation
and cancellation readback failure, partial rollback failure, unaffected independent
leases, zeroed reacquisition, repeated cancellation and destructor nonrelease.
The API compile checks reject publication/completion/address/activation/test
injection in production. Readback-failure fixtures are CPU models only.

## Explicit prerequisites beyond this increment

1. A real IOMMU observation/oracle gate, including positive access and negative
   blocked-translation/fault evidence on the pinned emulator profile.
2. Owned DMA page-table construction and real translation installation/readback,
   requester binding, invalidation ordering and authentic completion qualification.
3. Separately reviewed publication/quarantine lifecycle and controller activation,
   followed by actual Identify and bounded namespace reads.
4. Only then connect a kernel block backend to the existing copied sector-I/O API
   and the read-only XFS consumers. Host-file/XFS work does not supply this bridge.

Read-only BAR/IVRS observations, CPU PinLedger leases, dormant table bytes and
this preparation gate do not satisfy any of the first three prerequisites.
No IOMMU isolation, active NVMe device, real disk read, persistence, filesystem
mount, physical hardware support, throughput or full-system safety claim follows.
