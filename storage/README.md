# Aurora storage

The native NVMe object/extent filesystem and separate XFS compatibility backend
remain project targets. The separate Aurora file service supports strict
read-only XFS profiles, bounded boot recovery, and an explicit clean-only
composition for one existing-file replacement per boot. This is not general
writable XFS.

The [requirements](design/requirements.md), [traceability](design/traceability.md)
and [staged roadmap](design/roadmap.md) preserve all 56 supplied sections and the
additional XFS request. XFS read-write is the destination; validated read-only
access and log replay are prerequisite gates.

Current [byte and sector storage](../docs/storage.md) includes checked binary
buffers, owned sectors and a runtime-capacity volatile RAM sector device.
The [XFS readers](../docs/xfs.md) cover bounded header, geometry, shortform-root
and inline-extent/file parsing. The owned mount scans the complete supported
log before exposing files. The default fresh-format profile refuses dirty or
reused logs; a separate Linux-clean profile admits its bounded used/wrapped
log subset. Unsupported features fail closed.
The [host-only crash model](design/model/README.md) checks a bounded transaction
and deliberately broken persistence protocols.

## Protected file-backed NVMe

The explicit `uefi/nvme` image runs real NVMe commands against a disposable raw
QEMU namespace. Its six-function profile replaces EDU with NVMe at 00:02.0;
separate typed admission requires exact IVRS/resource facts, cold controller
state and BME clear. It shares parsing and firmware AHCI quiescence with the
EDU profile, not that profile's device grant.

Before BME, the broker installs default-deny DTEs and six immutable-direction
queue/data mappings. Two-entry polled queues allow one outstanding command,
nonreused CIDs and checked phase/SQ identity/head/status. Identify admits one
512-byte-LBA namespace with no active metadata, protection or sharing. Read and
write buffers are separate. Completion errors and bounded-poll timeouts halt
with all DMA backing retained; no reset, retry or allocator release exists.
Successful closure disables the controller, clears BME, revokes its DTE and
observes its own fresh invalidation completion, still retaining every page.

The retained Aurora `kernel.nvme_transport` owner holds both queue ledgers,
command-ID consumption, completion selection and the absorbing transport failure
state. One global operation advances through reservation, publication, completion
selection and acknowledgment. Reservation spends its CID before SQ publication;
completion selection does not permit reuse until the exact CQ doorbell and
subsequent health/guard checks are acknowledged. No failure refunds a CID.
Native code retains immutable queue/backing bindings, volatile DMA observations,
fences and MMIO, not a second queue-policy ledger. Empty polling uses a frozen
head/phase projection; copied plans are not authority. Source validates the five
copied completion DWORD observations, including the repeated last word. This is
sampled protocol stability, not proof of immutable device-written memory.

The source root is boot-pinned outside DMA backing. Its synchronous borrows check
the exact admitted root, disabled interrupts and closed transient window, and end
before hardware effects. Process queries use the existing broker-authenticated
contexts; no arbitrary CR3 is admitted. Source or bridge faults fail-stop with
backing retained, without claiming that a poison transition necessarily ran.
Mounted/recovery write, fence, sealing and revocation policies remain separate.
This is bounded transport ownership, not asynchronous storage, SMP or DMA-page
reclamation; the device and emulator assumptions are unchanged.

The retained read-only broker uses the same queues with no write-data mapping.
Its aligned 4 KiB cache serves copied 512-byte sectors without reusing command
IDs; exhaustion or a device fault permanently quarantines the backend. The
process dispatcher must authenticate the service incarnation, immutable-volume
generation and current root on every call, including cache hits. It owns the
shared mapping window with interrupts disabled; the broker restores that slot
before returning. The process/XFS guest reads both populated files through the
retained Aurora service, including 9,001 patterned bytes across sector/chunk
boundaries, EOF and read-only denial. Run that gate with
`scripts/kernel-uefi-smoke.sh process-xfs` using the same model/firmware prefixes
and `mkfs.xfs 6.13.0` on PATH. It creates a populated private 512 MiB image,
opens it read-only, and checks the process oracle plus the whole disk hash.

Run `NVME_TOOL_PREFIX=/path/to/nvme-model make smoke-nvme`, with
`AURORA_BOOT_FIXTURE_PREFIX` naming the clean no-NvmExpressDxe firmware package.
The separate model uses the three existing AMD-Vi patches plus `CONFIG_NVME_PCI`;
the reference Event runtime remains unchanged. With the pinned build dependencies
and packaged Event sources available, build it offline into a new writable prefix:

```sh
./scripts/watchdog.sh python3 ci/build-event.py --nvme \
  --event-prefix /opt/aurora-event --prefix "$PWD/build/nvme-model"
NVME_TOOL_PREFIX="$PWD/build/nvme-model" make smoke-nvme
```

This does not change `ci/image` or the reference runtime. GNU mtools builds the raw ESP.
One image runs cold read, write/Flush/read, a new-QEMU cold read, range refusal,
and actual device-error quarantine. The runner owns a fresh 8 MiB raw file in
`build/aurora-nvme-*`, uses explicit `cache=writeback`, and checks every disk byte
after each row; only LBA 7 may change. Failures retain logs, successful scratch is
removed. No caller disk path or block device is accepted.

These rows pass on the patched QEMU 10.0.13 model, including successful Flush
and fresh-process readback. They establish emulator-backed persistence, not
physical SSD power-loss behavior. The existing CPU-only `NvmeQueueBundle` remains
a separate preparation API. General recovery and writable XFS beyond the
explicit profiles below, and physical-device qualification, remain open.

The production storage composition uses the same production image with explicit
`-fw_cfg name=opt/aurora/storage,string=nvme`; absence retains the RAM path without
PCI/NVMe probes. Its separate seven-function profile adds only std VGA at
00:03.0 and binds the restored GOP extent to that device's BAR0. A distinct
RO/NX capture page at arena+0xe1000 avoids the runtime metadata page. Build its
model with `ci/build-event.py --nvme-graphics --event-prefix /opt/aurora-event
--prefix "$PWD/build/nvme-graphics-model"` under the same watchdog and pinned
dependencies. This adds `CONFIG_VGA_PCI` and pixman without replacing either
reference model. The existing `scripts/kernel_production_smoke.py` accepts
`--nvme-prefix build/nvme-graphics-model` with its usual image/renderer arguments;
it checks both a fresh read-only mount and a synthetic missing-UNMOUNT-marker
refusal, with exact storage transcripts, graphical-terminal rendering and unchanged
disk bytes. The positive row reads `/disk` through shipped HostFiles programs;
the negative row keeps the RAM service usable without exposing `/disk`. These
production guest rows pass on the bounded model and clean firmware.

The exact `nvme-linux-6.12-recover` storage selection adds a separate bounded
boot recovery step, not writable mounting or automatic replay after read-only
refusal. The immutable `bin/xfs-recover` program receives a boot-only writer;
its successful Flush and retirement precede the independent source file owner's
Linux-clean read-only mount. The attempt is consumed before executable lookup
and cannot be renewed by ordinary `run`, runtime reattachment or service restart.
Controlled refusal leaves disk access unavailable while retaining RAM files and
the console. The existing queues, command IDs and invalidation state are never
reset for a retry. Production dirty recovery has passed the command/framebuffer
oracle on a private image, including denial of ordinary writer execution. Clean
reentry and late-record refusal also pass with unchanged disk bytes (zero writes/one Flush and zero writes/zero Flushes). Actual
source-owner commit/exit loss and one fresh full readonly remount also pass in
the private console-owner fixture, with no writer remint or backend reset. This
is not full HostFiles continuity; finite command IDs still bound repeated mounts.
The [fixture recipe](../fixtures/xfs-core-redo/README.md#production-console-and-one-owner-restart)
includes these opt-in production commands and their archived inputs.
The runner holds the original read-only and attaches only a fresh private copy.

## Bounded mounted replacement

The separate `nvme-linux-6.12-write` composition starts
`bin/file-service-mounted` with authenticated Serve and WritableBlock grants.
It requires a clean log; dirty media must first complete a separate recovery
boot. Recovery's irreversible writer revocation is never undone.

This profile replaces only existing `/disk/hello`, with exactly 1–4096 nonempty
bytes. It reserves `.aurora-stage` against ordinary path access in both mount
compositions. Both files must have one allocated written block, one link and
the supported fixed allocation geometry: inodes 99/100 own blocks 9/20;
complete single-leaf free/inode trees, AGFL, special inodes and all-AG summaries
must validate. Initial readiness also requires seven exact prior-cycle stale
headers covering the append range and its successor. New files, allocation, larger/empty output and general writable
XFS remain unsupported. Open readers retain the old inode; it is never reused
within that boot. A separate boot may replace the destination again.

One commit reserves 16 writes, five Flushes and the following checked-refresh
read budget before its first mutation. Staged data and CORE are fenced before
the root exchange; home checkpoint and the clean marker have their own fences.
Success follows the durable boundary and checked namespace refresh. A failed/lost reply
means publication is unconfirmed, not rolled back: inspect or recover before
retrying. Owner loss permanently quarantines disk access for the boot; a new
RAM service may start, but cannot remint a writer or replay the request.

After the final Flush, the same owner checks 18 ordered readbacks: all 16
written sectors, the unchanged log successor, and the original superblock.
The immutable prepared plan must match every byte. A typed continuation also
binds the original mount head, geometry and root, verifies the new completion
record, then rereads the root and both namespace inodes through the existing
validators. The initial full-ring and allocation proof remains required;
exclusive writer ownership and the exact write set establish that all other
sectors are unchanged. This avoids repeating the full log scan inside a client
request without increasing its watchdog budget. Any mismatch loses disk
availability; it never makes an indeterminate commit safe to retry.

### Orderly readonly continuation

The explicit production command `storage readonly` requests one orderly
transition after this mounted replacement. It is not crash recovery or a second
write opportunity. The mounted source owner must confirm its completed readback
and namespace validation, healthy idle disk, and absence of any live client,
handle or staged output. It also refuses if any RAM file exists (including an
empty file), or the legacy note/named-file state has changed. Refusal preserves
the original service and RAM bytes. This deliberately conservative interface
never silently discards an authored program or compiled RAM executable, and
provides no migration or force-discard option.

The authenticated readiness response is bound to the exact waiting incarnation
and immediately followed by retained-owner shutdown, without an intervening
service request. Successful source shutdown is required; a fifth Flush alone
is insufficient. The broker seals the writer irreversibly, removes its write
buffer's IOVA leaf and observes a fresh invalidation completion. Only verified
service reclamation, continuation clearing and old-grant disposal allow a new
readonly grant. The fresh service validates the complete supported log and
namespace again. Its readiness is reported only after that mount completes.
The writer claim remains spent. Failure during shutdown, invalidation or remount
leaves disk access unavailable; no reset, replay or attempted rollback occurs.

The admission bound remains 16,896 remaining command IDs. With admitted 4 KiB
blocks, an aligned log of at most 16,384 blocks and at most 16 namespace inodes,
a cold readonly mount needs at most 16,403 commands: one superblock, 16,384 log
blocks, one clean-record body reread, one root inode and 16 namespace inodes.
A first complete sequential read of the fixed root `/disk/hello` (at most 4096
bytes) adds at most 37 commands: one open inode plus nine 504-byte chunks, each
spanning at most two sectors and requiring at most one inode and one data read
per sector. Root traversal uses retained validated root bytes. EOF and close
issue no disk reads. The total is 16,440, leaving 456 commands in reserve without
assuming NVMe cache hits. The mounted profile's two-entry namespace is stricter.
Nested paths and arbitrary repeated offsets are outside this first-read bound.
Remaining reads are finite and exhaustion fails closed; the queue/CID lifetime
is never reset. Recovery retains its separate 32,768-command reservation.

This contract assumes the admitted device/requester and translation domain,
no bypass alias, coherent DMA ordering, conforming command/Flush completion and
effective invalidation. Queue and read mappings remain; all device backing stays
boot-pinned. Revoking the write leaf is not proof that the device has stopped all
DMA or that its pages may be reused. Qualification remains emulator-specific,
not a physical-hardware or arbitrary crash-recovery claim.

### Targeted acceptance

The actual source owner has replaced 64-byte contents with 777 bytes while a
held reader retained the old inode, then replaced those contents with 113 bytes
on a separate cold boot. Empty/oversized/missing outputs, discard, private-stage
paths and a second commit are rejected without losing the RAM service. An owner
loss after the final Flush leaves the caller unconfirmed and disk access
unavailable; a new RAM-only owner cannot renew the writer.

The production console's shipped compiler has written a 3,368-byte Aurora
object to the admitted destination, linked and run it, and linked/run the
persisted object again after a cold read-only boot. The 777-byte, 113-byte and
compiler-object disks independently passed Linux clean mounting, exact content
and allocation checks, and `xfs_repair -n` on private copies.

Completed-command interruption checks cover all 16 write boundaries and all
five Flush boundaries. Sixteen subsequent recovery boots retain the old
64-byte target through write 11 and expose the new 777-byte target from write
12 onward. Reentry checks the real read-only HostFiles service, staging privacy,
stale-writer denial and usable RAM files. Across the 37 guest invocations,
the 21 cut cases produce ten distinct interruption images: several early data
writes leave identical bytes, and each Flush image equals its corresponding
write-boundary image. This is
emulator command-completion evidence, not a torn-sector or physical-power-loss
model.

The [staged-replacement fixtures](../fixtures/xfs-staged-replace/README.md) and
[incomplete-append provenance](../fixtures/xfs-staged-replace/append-provenance.md)
distinguish Linux-authored transactions, actual Aurora formatter output and
synthetic mutation inputs. Incomplete append recovery never applies an
uncommitted body: it can discard the exact pending stage body, or replay only
the preceding committed stage before discarding the pending root body. Other
unrecognized trailing data still fails closed. Full revision qualification and
build-budget acceptance remain separate from these targeted storage gates.

### Bounded dual-readonly composition

The explicit `nvme-dual-readonly` composition admits one or two supported
namespaces on the same pinned controller. It exposes independently validated
fresh-format filesystems at `/disk` and `/disk2`. This is not multi-controller
isolation, hotplug, a broader XFS history profile, or permission to write either
namespace. Existing singleton recovery and mounted-writer compositions remain
separate and require their original namespace topology.

The sealed `ReadOnlyBlocks` grant binds its immutable slots to the service and
controller incarnation, namespace, extent and volume generation. A copied slot
index or descriptor does not confer authority. Every operation, including a
cache hit, authenticates the live grant; the cache also distinguishes volumes.
Both namespaces share the existing nonreusing command-ID lifetime and absorbing
transport quarantine. DMA backing remains pinned, not reclaimed.

Before either eager log scan, the service checks all source allocations and
actual remaining I/O command IDs. The conservative admission is 18,458 per
present volume: 16,403 for a maximal mount, 2,049 for a general relative open,
and six for one read returning at most 504 bytes. Thus two volumes need 36,916.
The mount term covers a superblock, 16,384 aligned log blocks, a clean-record
reread, a root inode and sixteen child inodes. The fresh-only composition does
not need the clean-record term; keeping it is conservative. Identify and queue
setup use the separate admin counter before this admission; any prior I/O is
already subtracted from the queried remaining I/O counter.

This bound requires sequential eager scans without unrelated I/O between their
sector reads. A namespace tag alone cannot preserve bytes overwritten in the
shared DMA cache. Interleaving every sector between namespaces would invalidate
the eight-sector cache credit. The initial lookup/read allowance is headroom,
not a guarantee of future reads after other requests spend the finite budget.

Later operations check their worst-case command cost before changing handles
or cursors: open 2,049, a read of at most 504 bytes six, and a next-entry request
one. Known zero-I/O operations, including close and denied writes, remain usable.
Known resource insufficiency returns the existing failed response directly;
it is not passed into the filesystem as a synthetic sector error. No exchange,
yield, reentrancy or other I/O consumer may intervene between the budget check
and that synchronous operation's terminal read. There is no command-ID refund
or reset.

Malformed filesystem contents disable only that mount, preserving its sibling
and RAM state without restarting the service. Failed mount prefixes remain
reserved and cannot fall through into boot or RAM files. Uncertain transport
outcomes disable both volumes, including cached reads. Existing integrity
fail-stop paths do not promise continued console execution. Dual mounts use
disjoint eight-handle ranges and distinct device identities; the singleton keeps
its sixteen handles.
