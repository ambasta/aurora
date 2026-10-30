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
