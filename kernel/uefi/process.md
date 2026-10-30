# Process image: boot volume, frames and processes

`uefi/process-fixture` is the UEFI test image for running programs as
processes. It carries the boot volume, a physical frame allocator over all
usable conventional memory, kernel mappings beyond the arena's fixed table pages,
a serial export of volume files, and runs static ELF programs from the volume as
CPL 3 processes with their own page tables, a watchdog, and exit, print,
memory and copied service calls through the INT 0x83 gate. Production uses the
same process lifetime, retained file owner and validated command loader; its
old console/framebuffer architecture is restored at the command boundary.

The decisions are Aurora (`examples/kernel-process.au` over
`kernel/policies/kernel/{memory_map,frames,boot_volume,export_text,elf,process_space,process_memory,process_events,process_runs}.au`
and the existing `interrupt_budget`), reached through the private bridge
`process-entry.S`. The build checks every argument record, result class and
enum against the compiler's ABI facts (`PROCESS_POLICY_ABI` in
`scripts/meson_aurora_assembly.py`). Trusted C++ still owns resident lifecycle,
endpoint/transaction records and persistent-service startup/loss policy, as well
as firmware file reads, page-table writes/walks, CR3, frame-record storage and
free-list head, range and memory records, bounded messages, LAPIC and output. `services/service/files.au` owns filesystem tables, records and
bytes in its own process. The former native file-store adapter and its ABI are
now test-only references beneath `tests/`, never kernel image inputs. Assembly keeps the
trap entry (`kernel/exceptions.S`) and the CPL 3 transition (`process-user.S`).
Each C++ decoder rejects a result outside its closed encoding before using it.


### Production command orchestration

A production `run` invokes `kernel.execution_session` once with an exclusive
`builtin::ExecutionEffects` loan. Its local scalar session retains command
sequencing, terminal status/value and the obligation to finish across synchronous
`prepare`, `advance`, `output`, `request` and `finish` effects. The ordinary class
is not an affine child handle; authority belongs to the compiler-sealed loan.
No reference, child handle, address or authority-bearing result escapes it.

Native preparation still starts the file owner and loads the committed image.
The preparation report distinguishes a loaded client from a failed load, and
reports whether cleanup remains due. A terminal advance report means native
retirement already happened; its result is copied before subsequent cleanup can
replace the shared trap observation. Output failure and caller expiry request
specific retirement, checked against the actual native effect state. Service
loss follows the existing abandonment path. A failed final close overrides the
command result to unavailable. No failed request is replayed.

During a caller's file request, the session retains a separate request phase.
Each `request` effect enters the server at most once and may report `pending`;
Aurora repeats that effect without advancing the parked client. Timer parks do
not renew the transport transaction or server allowance. A full 64 KiB write
still uses two bounded messages, with a fresh per-message server allowance but
one cumulative caller budget. The second message is staged only after a valid
successful first reply and is not dispatched after caller expiry. An already
delivered operation drains to reply or server termination even after expiry;
no client completion or rollback promise is manufactured. Native code retains
the endpoint identity, copied bytes and physical accounting. Loader/control and
fixture consumers still pump the same transport primitives natively.

This removes the native production command loop, not the resident scheduler,
physical resource accounting or persistent owner policy. Native effect receipts authenticate the
live grant/generation, prevent reentry and duplicate physical effects, and keep
pending I/O distinct from command decisions. The grant is revoked before return
to the console. The retained source frame stays on the supervisor stack while
CPL3 traps use the separate guarded RSP0 stack; the existing whole-image stack
check and 15,360-byte bound apply without an increased allowance. The private
entry/report layouts are checked against emitted compiler facts in the same
bridge admission as the existing process policies.

## Handoff

The process image and production use the fixed 184-byte v10 handoff. Fields are
runtime metadata at 120, framebuffer at 128, volume at 136, volume length at 144,
case at 152, BAR record at 160, fixture selector at 168 and composition at 176.
The closed composition tag is 1 for RAM-backed production, 2 for process RAM,
3 for the process image's separately enabled NVMe path, and 4 for explicitly
selected production NVMe. All unused fields must be zero: process rows have no
runtime/framebuffer, RAM rows have no BAR record, and production has no
case/fixture. Future tags reject. A BAR record is only copied
observation, not live device or DMA authority. The existing older profiles keep
their exact layouts; the process image no longer emits v9.

`Handoff::valid` bounds the volume's nonzero page address and 1..64 MiB length
below the 52-bit limit, and the case at 255. Only the final memory map grants the
pages. Every row runs ACPI discovery; its copied MADT admits the watchdog LAPIC.
The kernel admits the copied map in Aurora (`map_admit`: version 1, stride
40..256 in multiples of 8, at most 512 descriptors, aligned nonempty ranges
below 2^52, no overlap). Every type is admitted, including the OEM and OS
ranges above 15, but only conventional memory is ever used. `volume_grant` then requires the volume
pages to lie wholly inside one non-runtime EfiLoaderData descriptor and outside
the arena. The loader also reserves the arena-owned window path
(`PageTables::prepare_window`). The boot verifier admits it because it has no
leaves.

## Boot volume

The loader opens `\aurora\volume` on its own ESP through the loaded image's
`EFI_SIMPLE_FILE_SYSTEM_PROTOCOL` (`\aurora\compiler` for case words 3
and 5, whose run lists need the multi-MiB compiler image, `\aurora\selfhost`
for 6; every boot checksums its whole volume). It requires a regular file of 1 byte to
64 MiB and reads it into fresh EfiLoaderData pages. It zeroes the last page's
tail and closes both handles before the final map. The format has one canonical
layout, little-endian (`scripts/kernel_volume.py` writes it):

- header, 64 bytes: magic `AURORAVL`, version 1, header bytes 64, entry count
  (at most 4096), entry bytes 32, names offset (`64 + 32 * count`), names bytes,
  data offset (names end rounded up to 8), data bytes (the rest of the volume),
  CRC32C of bytes 0..56 then 64..end, and a zero reserved word;
- entries in strictly increasing bytewise path order: name offset, name length
  (1..255), zero flags, data offset, size. Names and data follow index order
  without gaps, with each file padded to 8 bytes with zeros;
- paths are relative components of `[A-Za-z0-9._-]` joined by `/`, never empty,
  `.` or `..`. No path may also be the directory of another (`a` with `a/b`):
  such a volume is rejected as `nesting`.

`volume_admit` returns the first violated rule as a closed verdict.
`volume_find` binary-searches an admitted volume and `volume_entry` returns an
entry's absolute extent. The C++ wrapper also checks that extent lies inside the
volume. The kernel maps the volume read-only/NX and admits it before using it.

## Frames

Usable frames come from conventional descriptors without the runtime or
specific-purpose (`EFI_MEMORY_SP`, soft-reserved as Linux treats it) attribute,
above the first MiB (reserved, as Linux reserves it on x86). Each
must be disjoint from the arena and the volume (`frame_range`) and below the
CPU's physical width. Boot-services memory is not reclaimed. Ranges are sorted
and indexed densely. Each frame has one 8-byte record: bits 0..3 state (free,
allocated, kernel, retired), 4..31 generation, 32..63 owner, or for a free frame
its free-list link (next index + 1). `frame_transition` decides every record
change: initialize free or kernel, allocate, or release with the holder's owner
and generation. A release with a stale generation, the wrong owner, a kernel
owner, a kernel, free or retired frame, or a noncanonical record is rejected with
its reason and leaves the record unchanged. A generation that would wrap retires
the frame. Owners 1..15 are kernel uses (1 tables, 2 metadata); allocation
starts at 16. `Table::audit` walks every record and the free list.

## Kernel space

The window table at `0xffff800000000000` lives in the arena. Slot 0 is the
transient frame window, unmapped before reuse. Slot 1 is an absent guard, and
slots 2.. are RW/NX views of dynamic table pages. Root slot 384 (`0xffffc00000000000`) maps the frame
metadata RW/NX at its base and the volume read-only/NX at +1 GiB. Its tables
come from the lowest frame indices, followed by the metadata pages; all are kernel
frames. `KernelSpace::verify` walks the complete extension. Every entry must be
exact, every table and metadata page must be a kernel frame of its owner, volume
pages must lie outside the inventory, the window must be closed and the other
root entries must be the boot-verified ones. It runs after construction and after
the frame cases. The baseline row then checks that it rejects four single-entry
edits: a user bit on a table link, an executable metadata leaf, a writable volume
leaf and an open window.

The metadata is one 8-byte record per frame and, from the next page, one
8-byte mapping word per frame (`KernelSpace::mappings`), zero unless a process maps the
frame, then 96 pages per resident slot for its 16384 memory records. Case 0
needs one slot; process rows and production admit exactly two slots (an extra
384 KiB), without widening image, stack or user mapping bounds.

## Export

```
AURORA_EXPORT_BEGIN: path=<volume path> bytes=<n>
AURORA_EXPORT_DATA: <padded base64 of the next 57 bytes, or fewer on the last line>
AURORA_EXPORT_END: path=<volume path> lines=<k>
```

`base64_group` encodes each group of 3 bytes. `kernel_uefi_oracle.exports`
decodes the records and rejects stray, truncated, misframed or duplicate ones.
A run's committed files leave the same way when it ends ([files](#files)),
with each path byte outside the volume's name characters and `/` written as
`%XX` (`kernel.export_text` `path_text`).

## Processes

A row with a nonzero case word runs the run list `runs/<case>` of the volume,
one program after another, after the volume is admitted; case 0 runs the frame
and export cases above. Each run: the program path's entry is admitted as an ELF
program, its layout and regions are mapped into a fresh address space, the
complete walk checks it, the process runs until it exits, faults, makes an
invalid call or exhausts its watchdog budget, the walk runs again, every frame
of the process is released and the frame table is audited against all remaining
resident owners. After the final service exits no allocated frame remains.
The kernel reports each step:

```
AURORA_PROCESS_RUN: run=<n> path=<volume path> ticks=<budget>
AURORA_PROCESS_REJECTED: run=<n> reason=<missing | ELF verdict | layout verdict>
AURORA_PROCESS_LOADED: run=<n> regions=<r> pages=<p> tables=<t> quota=<memory frames>
AURORA_STDOUT: run=<n> <padded base64 of one print>   (AURORA_STDERR likewise)
AURORA_PROCESS_END: run=<n> reason=exit status=<s> | reason=watchdog ticks=<t>
  | reason=call operation=<rax> rip=<a> | reason=<trap class> vector= error= rip= cr2=
AURORA_EXPORT_BEGIN: path=<committed file> bytes=<n> ... (one record per committed file)
AURORA_PROCESS_RELEASED: run=<n> frames=<all> memory=<memory pages + tables>
  calls=<memory calls> commits=<committing faults> peak=<largest charge in frames>
AURORA_PROCESS_RUNS_OK: runs=<n> free=<frames>
```

A fault with a frame the kernel does not verify as the running process's own
(any kernel-mode fault) prints `AURORA_PROCESS_KERNEL_FAULT: vector= error= rip=
cs= cr2=` and stops the machine; only a verified process frame ends just that
process.

### Resident lifetimes

The lifecycle row (case 7) loads two ordinary ELF processes together, then uses
the existing Aurora `kernel.round_robin` policy to select a runnable slot.
A timer tick first consumes that process's cumulative watchdog budget. If any
budget remains, the kernel copies its authenticated 22-word RSP0 frame into
that slot's private continuation and returns to the supervisor. Only then may
another process enter: `process_enter` is never nested. Resume restores the
same root and all integer registers, flags and user stack. The shared kernel
continuation is empty between entries; slot retirement scrubs the saved user
frame and startup arguments. There is still no SMP, extended-state switching,
unbounded process table or general scheduler API.

Each slot owns a distinct memory-record span. Every HostFiles client uses the
separate source owner. Rows 1..6 retain their original independent-case semantics:
a fresh source-service companion runs beside each client, exports its committed
files after authenticated cleanup, then exits. Client ordinals/goldens stay
unchanged; companion LOADED/END/RELEASED records report their own generation,
root and frame accounting. The admitted list has at most 64 clients; companion
owner runs 64 + ordinal cannot alias client runs 1..64. Case 7 is only two memory/print
processes and has no filesystem binding. Cases 8..10 retain a service across clients.

### Command loader boundary

The production supervisor API `run_program` uses the same retained owner and
HostFiles protocol to open a committed file, pin that version, copy a bounded
loader snapshot and close the handle before startup. The snapshot is at most
64 MiB plus 33 paging frames, reserved from unpromised free frames. Its unique
mapping words and exact supervisor-only walk account for every future-client
frame before a process exists. After copying it becomes RO/NX; the existing
full-span ELF/layout/quota policies admit it unchanged. Mapping the process
copies fresh pages, then unmaps, scrubs and releases the snapshot before the
process's own frame-equality walk. Loader RPCs share a cumulative budget.

The console yields with no live protected grant. After the command, all clients
and snapshots are gone, the server is parked, timer/interrupts are quiet, and
full audits precede restoring the exact original root/window entries. Reattach
checks those exact entries and audits retained owners before any resumption.
Child output is copied and delivered only under the supervisor root. Fault,
watchdog, malformed/missing image and service loss return a typed result; the
failed command is never replayed. A subsequent command may start a fresh service
incarnation after explicit volatile-loss reporting. The combined production
image, return-to-prompt and same-boot build/link/run still require actual guest
qualification; the API's presence is not that result.

### Retained source budget roots

`kernel.process_budget::BudgetLedger` is the sole owner of each resident's
allowance, charged ticks, partial quantum and next-message profile. The loader
has a separate root shared across its whole bounded operation. A native
noncopyable wrapper retains opaque aligned storage initialized by a source
factory; a copied class value is not execution authority. `Running` copies only
the binding, never a second allowance tuple. Single leading plain-class loans
use complete-object lifetime facts, distinct from resource ownership.

Each source access is synchronous, allocation/effect-free, IRQ-excluded and
nonreentrant. No loan survives LAPIC operations, CPL3 entry, device I/O or a
callback. This is the single-CPU maskable-interrupt contract; no NMI path enters
the ledger. The dedicated object must have no imports, and the whole-image
call-cycle and stack checks still apply. These are bounded artifact guarantees,
not a general language effect system. Native code retains measured/armed timer
counts and authenticated process identities, not source policy fields.

A new transport transaction restarts only the server's configured allowance;
parks and request continuation never renew it or the caller. Mounted startup
can configure the next message without erasing current diagnostics if admission
fails. Voluntary zero-count progress consumes one count in source. Retirement
captures immutable terminal ticks with run/service identity before stopping and
scrubbing the root; those observations cannot resume execution.

### Retained service incarnation policy

One `kernel.service_incarnation::ServiceIncarnation` root owns the file owner's
incarnation ordinal, startup/ready/stopping/retiring phase, disk readiness and
frozen terminal observation. Native code retains the actual resident, endpoint
binding, transport and cleanup effects, not a second readiness flag or generation
allocator. An ordinal copied into a reply is not authority to create a service.

Each existing runtime API entry opens an operation after attachment and recovery;
its exit closes only after the physical boundary audit and settled source phase.
This is an API operation, not necessarily a whole console command. At most one
fresh incarnation is attempted per operation. Reusing a live incarnation also
consumes that operation's incarnation opportunity. Loss cannot refund it after
cleanup; only a later operation may start another owner. Generation-pinned
operations never start a replacement. The largest ordinal remains usable while
its owner is ready; only the next allocation is refused rather than wrapping.

Readiness is published after the existing authenticated startup controls. A
usable RAM file owner may report disk unavailable. Loss revokes logical readiness
before physical retirement; only verified removal of residents, snapshots and
pending endpoint authority acknowledges cleanup. Normal fixture shutdown requires
prior shutdown intent and an authenticated successful exit; an unexpected exit,
even status zero, remains service loss. Failed requests and uncertain commits are
not replayed. Existing one-way mounted/recovery grants are unchanged.

The root uses the same bounded plain-class lifetime foundation as the budget
ledger: unique opaque native storage, exact emitted ABI admission, short exclusive
loans and an import-free object. No loan crosses process/device/cleanup effects.
This is bounded service lifecycle policy, not a general async child capability,
restart manager, scheduler or init system.

### Retained file service

Case 8 designates one `services/file-service.au` ELF as the file owner and runs
successive ordinary HostFiles clients beside it. `service.files::Store` owns the
copied boot volume, handle/output tables, committed records and bytes in its own
ByteRegion. It reuses the existing Aurora path/status decisions; the kernel does
not keep a second namespace or committed-byte copy in this path. The owner has
an 8 MiB page-index allocation, about 22 KiB of tables, the volume copy and a
growable payload arena capped at 256 MiB; its actual frame quota may refuse
before that ceiling. Growth reserves at most 16 pages at once, falling back to
one page on refusal; the at-most-60-KiB unused capacity is charged to the same
service quota. Payload copies update file metadata once per page fragment before
any further allocation can fail. These are ordinary checked owners, not physical
pointers. Payload words are checked eight-byte class values; partial writes
preserve the other bytes in a word, while complete words use the checked
little-endian codec and reads remain bounded by file size. Ordinary writes of
1..4096 bytes use a zero-initialized 512-byte value on the guarded user stack.
The same total-count policy admits the whole message before any chunk is
appended; no endpoint exchange or reply occurs between chunks. A failed chunk
poisons the pending output, preserving the old committed destination. Empty,
large raw, disk and non-write requests retain their existing copied path.

The separate sealed Serve entry receives its generation in RDX. INT83 operation
15 accepts its fixed 131136-byte request/reply window, bounded reply count,
generation and previous transaction. Only the kernel-designated incarnation may
receive; a filename, main signature or numeric value grants no role. The kernel
copies before parking, authenticates the implicit reply target, then publishes
canonical metadata and copied bytes before resuming the full saved frame. User
pointers never survive a switch. Requests are bounded at 64 KiB; the admitted
raw 64 KiB write uses two internal messages without changing the client ABI.

A terminal client gets one authenticated cleanup: pending outputs and handles
end, while linked files and generation/inode history remain. A delivered request
is at-most-once: if its caller expires, the owner may finish it under its separate
operation budget, but the caller cannot resume or be reused before completion
and cleanup. A commit can therefore survive an unknown response; there is no
replay or rollback claim. Server failure invalidates the endpoint and explicitly
reports `AURORA_FILE_SERVICE_LOST` with `volatile_data=lost`. Production returns
unavailable to the console, and a later command starts a new incarnation without
replaying the failed request. The hostile endpoint fixture exercises the same
teardown and fresh-incarnation path.

Voluntary exchanges carry the remaining LAPIC counts instead of renewing a tick.
The timer covers validation, copies and execution; server execution also consumes
the waiting caller's budget. A pending expiration belongs to the outgoing slice,
and its drain only acknowledges it. Synchronous kernel polling is independently
bounded; after timer saturation it charges the full armed slice, not an invented
exact wall-clock count beyond that expiry. Bootstrap and cleanup have independent
bounded service budgets. Full frame/root audits remain at lifecycle boundaries, not on
every file request.

The same compiled HostFiles/lifecycle/raw drivers exercise retained replacement
with old-open handles, cross-client reads, stale handles, pending-output cleanup,
page reuse, 64 KiB bytes, rapid RPC watchdogs, ungranted receive and a Serve main
loaded as an ordinary client. Case 9 exercises stale/forged generations, changed
window, replayed transaction, oversized count, malformed reply, server fault and
watchdog, followed by a fresh real service and committed-file reads. Final aggregate
qualification remains required; these focused rows do not replace it.

Quota admission reserves all of each resident's granted quota, not just frames
already allocated. The next load sees `free - sum(quota - held)` over live
residents, with checked subtraction. This prevents two clients from promising
the same free frame to their first-touch mappings. A fault, invalid call or
exhausted watchdog ends only that slot, closes its files, walks and releases its
frames and audits all surviving owners. A healthy sibling then continues.

### Programs

`kernel.elf` admits ELF64 little-endian x86-64 `ET_EXEC` images (System V ABI 0,
64-byte header, 56-byte program headers, 1..16 of them) and returns the first
violated rule: `truncated`, `magic`, `format`, `type`, `machine`, `header`, then
per program header `interpreter` (PT_INTERP), `dynamic`, `tls`, `stack` (an
executable or second PT_GNU_STACK) or `segment` (any other type), then per
PT_LOAD (at most 8) `permissions` (not readable, unknown flag bits),
`writable_executable`, `alignment` (alignment not a power of two of at least a
page, offset not congruent to the address), `file` (bytes beyond the image),
`memory` (zero size or file size above memory size), `address` (outside [4 MiB,
64 TiB)), then `overlap` (two segments sharing a page) and `entry` (outside
every executable segment), or `empty` without load segments.

### Address space

`kernel.process_space` lays out the regions: each load segment's pages with leaf
flags read-only/NX, read-execute or read-write/NX, copied from the image with
the rest zero (BSS); an 8 MiB read-write/NX stack ending at `0x7fffff000000`
above an unmapped guard page; and the argument block (1..64 KiB of
NUL-terminated words, read-only/NX) at `0x7fffff001000`. `process_layout`
rejects a segment entering the kernel's shared 2 MiB slots (`kernel`) or an
empty or oversized argument block (`arguments`).

`process-space.hpp` builds the address space from frames allocated to the
process's own owner (16 + run). The root shares the kernel's root entries
256..511 (frame window, LAPIC, frame metadata and volume) and the
supervisor-only page tables of the arena's one or two 2 MiB slots, so traps and
calls run under the process root. Tables are written and pages filled through the
transient frame window, which is closed before a page's own leaf is written: no
frame is ever reachable writable and executable at once. Each table and page frame
gets a mapping word naming its one place (a page's address, or a table's level
and first address, with a table's count of present entries in bits 4..13). The
walk at load and at exit checks every entry of every table reachable from the
root: shared entries equal to the kernel's, links exactly user-writable to a
table of this owner with the expected mapping word, leaves inside a region or a
memory mapping with its exact flags and a page of this owner with the expected
mapping word, and each table's count; that the memory records are in address
order inside their reservations below the bump address; that the walk saw every
recorded table and region page and every committed page; and that every frame
allocated to this owner is among the ones walked, within its charge. File bytes
are ordinary user mappings of the service, with no special kernel file-frame class. The frame table maintains
counts for at most two live owners and its full audit reconstructs them from
every record. At admission and retirement the supervisor audits all resident
roots and requires their total to equal every allocated frame, so an orphan or
unknown owner cannot disappear from the check.
It opens the frame window once per table and once per link, so its cost
follows the space's tables and pages, not its address range. At exit the
space is released by walking its tables.

### User memory

A kernel call reads or writes the process's bytes under its own root, after
`ProcessSpace::access` admits the whole range: inside one region (a write
only into a read-write one: the stack or a writable segment) or inside one
memory mapping's pages. A mapping's absent pages are committed first, each
admitted by the Aurora fault policy (`memory_fault`) and committed with
frames its map already charged, as a first touch would commit them, so the
kernel can read into or out of a heap the process never touched. Anything
else (a gap, a mapping's reservation past its pages, a read-only page for a
write, a range that crosses into another region, the kernel's half) ends the
process as an invalid call before the call has any effect: print reads its
buffer, read writes its 504-byte chunk, the file calls read their path
(copied into the kernel before any decision sees it) and write their
48-byte result record, write reads its bytes.

### Memory

`kernel.process_memory` decides the memory service behind the hosted memory
runtime (`runtime/linux/aurora/memory.au`, the one source both runtime roots
compile, compiler/SERVICES.md#hosted-memory):

- map(bytes) reserves the next power of two of the pages at a bump address in
  the memory area [64 TiB, 96 TiB) and leaves one unmapped page after it; the
  bump address never goes back, so no address is reused within a process;
- remap(base, bytes, new bytes) grows or shrinks in place within the
  reservation (a shrink releases the pages past the new end), and otherwise
  moves the committed pages' entries to a fresh reservation (mremap with
  MREMAP_MAYMOVE; no byte is copied, the old range no longer translates);
- unmap(base, bytes) releases the mapping's pages;
- a base naming no mapping, or a length the mapping does not have, ends the
  process as an invalid call (`length`); the area full (`space`), 16384 live
  mappings (`records`) or the quota (`quota`) refuse with the HostStatus
  `exhausted` (-6) and change nothing, which the runtime turns into a failed
  owner (`ok false`), as an ENOMEM does on Linux. Unlike Linux, the area is
  never reused: every map and move uses up its reservation and a page of the
  32 TiB for the rest of the process (a 4 GiB map and unmap repeated about 8191
  times, or a 1 MiB one about 2^25 times, then refuses with `space`).

Every frame a process may hold is charged against its quota first: the load
(root, regions, two tables per shared kernel slot) and each mapping's pages
plus one page table per 2 MiB, 1 GiB and 512 GiB slot it touches (a move also
needs room for its new tables beside the old ones). The quota is the run's
(`quota` frames, 0 for all) on top of the load, at most the frames free when
the process loads (`memory_budget`; a load that does not fit is `rejected
reason=quota`). A mapping is committed on first touch: a user read or write of
an absent page inside a mapping's pages (`memory_fault`) commits that page and
the other absent pages of its aligned 64 KiB block in the mapping, with frames
the charge already covers, so a touch never fails (but see the limits on
retired frames) and the process sees eager
commit's behaviour without its cost (one memory case maps 4 GiB and touches
one page). Every frame is zeroed through the window before it is mapped, so no
frame reaches a process with an earlier holder's bytes. A page table left
empty by an unmap, shrink or move is released (its parent's count drops, up
to the root); each cleared leaf and released table is invalidated with
INVLPG before the process runs again.

### Files

`kernel.process_files` decides the file service behind the HostFiles binding
of `--target aurora` (`runtime/aurora/aurora/host.au`,
compiler/SERVICES.md#hosted-files) with the Linux binding's semantics, so a
program sees the same statuses, limits and identities as on Linux:

- one tree: the volume root is `/` and the working directory; volume entries
  are regular files and a directory is a path prefix of some entry (no
  symlinks, FIFOs or devices exist); paths walk component by component as
  Linux walks them (empty and `.` stay, `..` stops at the root, a file takes
  no further component, a component above 255 bytes is `invalid_path`), and
  each Linux error maps as `host.au` maps it (ENOENT `not_found`, ENOTDIR
  `not_regular` for `open_directory` and `not_found` otherwise);
- `open_beneath` refuses an absolute path or any `..` component (`escape`);
- 32 handles (directories and files) and 4 outputs, with ids `generation * 64
  + slot + 1` from the source owner's table, each claim advancing its slot's
  generation, so an id is never reused within a run; a stale, forged,
  mistyped or made-up id is `invalid_handle`, and a full table `exhausted`;
- read returns up to 504 bytes, none at or after the end, `failed` beyond
  pread's signed offsets;
- create_output refuses a leaf that is empty, `.`, `..`, above 255 bytes or
  in the `.aurora-output-` namespace, a missing or non-directory parent and a
  directory destination, and reports the existing destination's and the
  directory's identities; its bytes go to a pending overlay record of up to
  64 MiB (past it the output fails, `too_large`), allocated from the source
  service's own quota (a write that does not fit fails, `failed`, as a full
  disk fails on Linux); commit links the record for the service lifetime, shadowing a volume file or replacing an overlay file (whose
  bytes stay readable through handles already open on it), discard and a
  failed commit drop it;
- identities: the volume is device 1 (a file's inode its index + 1, a
  directory's 65536 + first entry * 256 + depth), the overlay device 2
  (inodes in commit order);
- when a client ends, its pending outputs end and handles close (Linux's
  `finish`), while committed files survive in the source service. Only the
  independent golden cases deliberately end that service after export.

The supervisor validates and copies paths/results but keeps no namespace or
committed bytes. The source owner applies `kernel.process_files` decisions to
its private state. The binding coalesces output bytes in a 4096-byte buffer;
raw 64 KiB writes are copied through two bounded messages. File allocations now
consume the service's quota, not the departed client's quota.

Supervisor-only export controls 7/8/9 require no active client: select a linked
record, copy its path, then copy its data. The source pins revision/inode identity
for the selection. Replies have closed 64-byte headers and at most 504 copied bytes;
selection returns path length and file size. The kernel bounds 64 records, 4095-byte
paths and 64 MiB files, preserves 57-byte base64 framing, and carries one 16-long-tick
budget across service work and serial emission. Incomplete exports and deadline exhaustion fail the run; the existing framing
oracle rejects partial artifacts.

Production's legacy note and four named files are private state in the same
Aurora service (`service.console`), not a second kernel namespace or visible
HostFiles paths. Supervisor controls 10..14 copy commands, projections and frozen
selections only. Mutations require the previously observed service generation;
note replacement additionally checks its nonreused revision. The kernel keeps
only the current projection/selection and protected-grant retirement ledger.
Both append workers must retire before replacement publication. A malformed
inner policy reply revokes only the observed service incarnation; conflicts and
unknown outcomes never trigger automatic retry. Session exit clears the private
state or invalidates that old incarnation if clearing fails.

### Read-only NVMe/XFS

Composition 3/cases 10 and 11 independently grant the designated service a sealed
`ReadOnlyBlock`, with nonreused generation in R8 and copied sector count in R9.
INT83 operation 16 accepts only that current incarnation/generation, a writable
512-byte destination and an in-range LBA; R10 must be zero. The trusted broker
checks current root, closed shared window and immutable namespace extent before
every read, including cache hits. Failed reads return zero bytes/count and backend
quarantine is absorbing; a restarted service cannot regrant a quarantined device.

The source service lazily admits the strict fresh-format XFS mount on `/disk`,
including the full clean 64 MiB log and supported root/inode set. Disk handles have
disjoint slots 40..55 and device identity 3. Reads are on demand through copied
sectors, not a preloaded fake tree. Unsupported, dirty or quarantined mounts stay
unavailable without falling back into the boot namespace. `/disk` remains read-only;
this grant exposes no XFS writes. Boot-only recovery is separate below; general
replay and production writable disks remain open. The actual
case 10 uses a fresh private 512 MiB image opened O_RDONLY by QEMU and verifies its
whole hash unchanged, full 9001-byte file contents, EOF, write denial, revoked grants
and successful fresh service incarnation.

The authenticated initial source0 control 1 has operation at 0, boot-volume length
at 8 and a closed XFS profile at 16; bytes 24..63 must be zero. The source validates
this copied shape before allocation or disk reads. Case 11 selects profile 1,
the bounded Linux 6.12.107 clean-log reader; case 10 and companion services select
fresh profile 0. No client or on-disk field can change that selection.
The existing process image and runner accept a private copy of a genuine used,
wrapped or dirty reference image for case 11, with unchanged read-only authority
and deadlines. Actual used/wrapped cases read both binary files across clients;
the dirty case exposes no disk bytes or identities and preserves retained RAM.
All private images remain unchanged; whole-suite and budget acceptance are
separate from these component results.

### Boot-only XFS recovery fixture

Case 12 is a separate closed role in the existing process image, not a production
storage selector. Only its first boot-selected program receives `WritableBlock`;
ordinary `run`, a pathname, arguments or a sealed main signature cannot mint it.
Operations 17/18 copy one checked 512-byte read/write sector, 19 flushes and 20
observes remaining commands. Each authenticates the writer's owner, root and
nonreused generation independently of its private user-side staging window.

The Aurora recovery program preflights the supported complete log, allocation
metadata and homes before writing. It flushes homes, then the completion body,
then the clean header. The kernel permits at most 18 sector writes and three
Flushes and reserves 32768 commands for the independent read-only consumer.
Successful exit requires an acknowledged final Flush before the one-shot
write-data DMA-leaf revocation. Actual root/frame release, continuation scrubbing
and grant destruction precede read-only promotion; failures close both paths.
Backing remains pinned and command identifiers never reset.

The explicit `kernel_nvme_smoke.py --process-xfs-recover IMAGE` route attaches
only a new private copy writable and retains its before image. It checks Linux
home-sector goldens, the exact changed-sector set, stale writer-generation
write/Flush denial, fresh read-only admission and complete frame reclamation.
This is bounded emulator recovery, not arbitrary torn-sector recovery, mounted
XFS writes or physical power-loss qualification.

Cases 13–16 reuse the exact case-12 run list and source executable. In the
process-fixture build only, they stop immediately after acknowledged Flush
1/2/3 or sector write 1 and after the backend restores its window. The cut trace
binds the actual writer generation and operation counts. No source exit,
retirement, cleanup or read-only promotion is claimed in that VM. The explicit
`--recovery-cut` runner compares every changed sector against a read-only
`--recovery-reference` completed image and preserves the captured prefix. A
fresh ordinary case-12 VM then receives a new private copy of that exact prefix.
These are completed-command interruption tests, not torn-command or physical
power-loss simulations; production builds contain no cut hook.

### Production storage selection

Production composition 1 remains RAM-backed. Exact `opt/aurora/storage=nvme`
selects fresh profile 0; exact `nvme-linux-6.12-clean` selects the pinned clean
profile 1. Exact `nvme-linux-6.12-recover` selects boot mode 2 and the same
source `bin/xfs-recover` used by the private recovery composition. All three
use composition 4 in the same image. Word 152 is a closed boot storage mode
only under tag 4, remains zero for tag 1, and keeps its fixture-case meaning
elsewhere. The runtime captures this selection once, checks it on reattachment
and sends the same profile through every owner bootstrap after loss; there is no
client setter or on-disk fallback. Older production v10 consumers reject profile 1.
The short selector label is not qualification of every Linux 6.12 producer.
Explicit composition 4 grants the same readonly backend to the
retained owner and calls source control 15 before the first prompt. This one
startup admission has cumulative 16-long-tick loader and server limits; every
normal server operation returns to 64 short ticks, and client limits do not
change. A canonical unavailable mount preserves boot and console state without
falling back for `/disk`; malformed replies or service death use the shared
volatile-loss path. Actual used/wrapped production guests exercise shipped
cat/sort clients, committed copies and exact serial/framebuffer output; genuine
dirty refusal preserves RAM. The exact binary comparisons remain in case 11.

Recovery is explicitly selected, never the default or an automatic fallback from
readonly refusal. Before the first prompt, the runtime marks its boot-global
attempt before looking up the fixed executable in the immutable boot volume.
It uses the shared writer mint/run/retire path with the existing 16 long ticks
and 16,384-page quota. Only successful sealed retirement permits a fresh readonly
file owner, always with source profile 1 and its independent complete mount check.
Controlled recovery refusal abandons the backend without reinitializing it;
RAM files and the console remain available. Ownership or cleanup audit failures
remain fatal rather than exposing a possibly live writer.

Repeated preparation and later file-owner restart cannot retry recovery, reset
queue/CID/invalidation state or look up the recovery executable again. Ordinary
`run`, caller arguments and retained mutable files never grant write authority.
The boot selection is immutable across runtime attachment. The dirty production
guest passes source recovery, independent readonly mount, shipped file commands,
ordinary writer-execution denial and the graphical/console oracle, with only the
four expected sectors changed. Completed-marker reentry passes with zero writes
and one Flush; controlled late-record refusal passes with zero writes/Flushes,
an unavailable disk and healthy RAM/console. Both leave the whole image unchanged.
The private console-commit owner also passes one actual commit/exit loss and
a fresh incarnation's full readonly remount, without another writer or backend
initialization. This does not qualify ordinary HostFiles continuity after loss.
The finite nonreused command-ID budget bounds repeated full mounts; exhaustion
quarantines disk access instead of resetting its queues.

### Entries

The process runs at CPL 3 with IF set: RIP at the entry point, RSP 16 bytes below
the stack top (a zero qword), RDI the argument block and RSI its length, other
registers zero. The GDT and TSS page, the 16 KiB RSP0 stack and the double-fault
IST stack live in the arena between unmapped guard pages. SYSCALL is disabled
(EFER.SCE clear), CR0.TS is set, and FS, GS and kernel GS bases are zero. Every
vector enters `kernel/exceptions.S`; only INT 0x83 is a DPL 3 gate.
`process_trap` (`kernel.process_events`) classifies the copied frame: it must be
the exact RSP0 frame under the process root with CS 0x1b, SS 0x23, RIP below
2^47 and RFLAGS with IF and bit 1 and only CPL 3 bits, or it is `kernel`. Then
vector 64 is `timer`, 0x83 `call`, #UD `system_call` when the two bytes at RIP
(read when executable) are SYSCALL or SYSENTER and `invalid_opcode` otherwise,
#PF `stack_guard` in the guard page and `page_fault` otherwise, and
`protection`, `divide`, `debug`, `breakpoint`, `overflow`, `bound`, `fpu`,
`alignment` and `simd`; NMI, double fault, machine check and the rest are
`kernel`.

`process_call` decodes RAX: 1 exit(RDI status 0..255); 2 print(RDI stream 1 or
2, RSI buffer, RDX length up to 64 KiB), returning 0; 3 read(RDI file, RSI
offset, RDX chunk), returning a count up to 504 or a negative HostStatus;
4 map(RDI bytes), 5 remap(RDI base, RSI bytes, RDX new bytes) and 6 unmap(RDI
base, RSI bytes) with whole-page lengths up to 64 TiB, returning the base (0
for unmap) or -6 ([memory](#memory)); the file calls ([files](#files)) 7
open_directory, 8 open_beneath, 9 open_file and 11 create_output (RDI the
directory for open_beneath, RSI path, RDX length up to 64 KiB, R10 the result
record: id, size, device, inode, directory device and inode), 10 close(RDI),
12 write(RDI output, RSI buffer, RDX length up to 64 KiB), 13 commit(RDI) and
14 discard(RDI), returning 0 or a negative HostStatus; arguments a call does
not use are ignored. Anything else ends the process with `call`. A page fault the memory service commits resumes the process. The watchdog arms the LAPIC one-shot
timer (2^24 counts, divide by 16, about 0.27 s under QEMU; 2^31 counts, about
34 s, for a run with flag 8) per tick; each timer interrupt is charged by
`kernel.interrupt_budget` and ends the process when its run's 1..128 ticks are
spent. A timer interrupt pending when a process ends is taken in a kernel
`sti; hlt` window before the next process starts.

### Run lists

`kernel.process_runs` admits a run list: header `AURORUNS`, version 2, count
1..64; per run a 24-byte record of ticks 1..128, path bytes 1..255, argument
bytes 1..65536, flags 0..15 and the memory quota in frames (0 for all), then the
path, the NUL-terminated arguments and zero padding to 8
bytes, ending at the entry's end (`truncated`, `magic`, `version`, `count`,
`ticks`, `path`, `arguments`, `flags`, `padding`, `trailing`). Flag 8 makes
each tick 128 times longer, for runs of minutes. The other flags are
fixtures: 4 runs the complete walk after every memory call, commit and
kernel access to the process's memory (it
stops the machine if one fails), 1 faults the kernel during the run's first kernel call (the
kernel-fault row), 2 checks after the load walk that it rejects each of four
single-entry edits, each undone before the next: a no-execute code leaf, a code
leaf aliasing the argument page's frame, an extra leaf after the argument block
and a user bit on the shared arena slot's entry (`AURORA_PROCESS_WALK_OK:
rejected=4`).
`scripts/kernel_volume.py --run` writes run lists.

## Tests

`kernel-process` (merge suite) links the generated policies with
`frames.hpp`. Its memory-map, inventory, record and policy cases are
`tests/kernel-process/frames.cases`. The volume cases are built by the writer
from `volumes.cases`; each edits one field of a canonical volume. Program and
run-list cases are `programs.cases`: each edits one field of the writer's
header-only ELF image (or of a run list) and prints the ELF and layout verdicts
and the regions, the load charge and quota, or the run-list verdict and runs.
Trap frames and kernel calls are `events.cases`; memory decisions
(reservation, growth, move, quota, release, record lookup, committed faults,
the memory calls and misuse) are `memory.cases`; `files.cases` runs file-service
scripts (the Aurora decisions and test-only `tests/kernel-process-files.hpp`
reference adapter over heap pages) over a
volume of the HostFiles cases' tree: path walks and confinement, ids and their
generations, exhaustion, reads, creation, overlay shadowing and replacement
under open handles, the 64 MiB limit, the quota, export and misuse. Verdicts
are compared with the golden files beside them. The `guest-process` family
boots the image's process rows (`meson test --suite guest-process`):

- `process-volume` allocates every free frame and writes and reads back a pattern
  and then zero through the window. It checks six misuse rejections, releases
  every frame and audits with zero leaks. It checks that the exit walk rejects the
  four edits above, then exports `examples/host-sort.au`, whose bytes must equal
  the repository file;
- `process-volume-corrupt` boots a volume with an unsorted index and a valid
  checksum (`order`);
- `process-volume-empty` boots an empty file, which the loader rejects;
- `process-volume-map` names the arena as the volume after ExitBootServices
  (`arena`);
- `process-run` (case 1) runs the `--target aurora` host-files probe with `print
  hello eprint oops exit failure` (with the walk probes of flag 2), the Linux build of the probe (ends at its
  first SYSCALL, `system_call`), `recurse` (a GNU as program, since the compiler
  rejects recursion reachable from a HostFiles main; ends at the guard,
  `stack_guard`), `hostile spin` (ended by the watchdog after 4 ticks), the
  seventeen isolation programs of `tests/kernel-process/isolation.S` (writing its
  code page, running its stack, `cli`, `in`, reading the kernel half, an unknown
  kernel call, printing a kernel address, `int 14`, touching a mapping's
  reservation past its pages, unmapping with a wrong length, reading a moved
  mapping's old address after checking its byte moved, reading a volume file
  into a mapping's untouched pages and printing it from there (allowed),
  reading into a mapping's reservation past its pages and into its code page,
  opening a path at a kernel address, writing an output from an unmapped
  address, and stale, forged and mistyped ids, each `invalid_handle`) and the
  probe with `print 'two words' exit success`, which shows the kernel continues
  after each, then once more with one long tick (flag 8);
- `process-lifecycle` (case 7) uses one compiled Aurora driver for pairs of
  finite heap consumers, a checked bounds fault and a watchdog spin. Both finite
  consumers retain different byte patterns at the same virtual addresses; one
  moves and shrinks its mapping while the other remains parked. The transcript
  requires real parks/resumes with peer execution between them, distinct live
  roots and owners, the expected process outcomes and full final reclamation.
  The final pair gives the first resident every available frame of quota and
  rejects the second load despite the first's largely unallocated reservation.
  These mechanisms require final-source guest qualification, not registration
  alone;
- `process-hostile` (case 2) rejects ELF images with a writable and executable
  segment, an interpreter, an entry outside code and overlapping segments and a
  missing path, runs `hostile` to exit 0, then faults in the kernel during the
  probe's first call, which stops the machine;
- `process-memory` (case 3, 5 GiB guest, the compiler volume) runs the
  `--target aurora` memory probe once per case of
  `tests/host-files/memory.golden` (the first, second and fourth with the walk
  after every memory call), the `--target aurora` compiler with no arguments
  (usage, exit 2), the probe under a 140-frame quota (its 100000-byte owner
  fails, its 10-byte one does not) and the compiler under a 1-frame quota (its
  memory runtime cannot start: exit 1). Guest time per run is about 40 ms,
  4 s for the 768 MiB of triples one case fills and 3.5 s for the case that
  churns 100000 owners; 60 ms for the compiler;
- `process-files` (case 4, 256 MiB guest) runs the `--target aurora` cat,
  probe and sort programs once per case of `tests/host-files/cases.golden`
  and `limits.golden` (`kernel_profiles.FILES_RUNS`) over the volume's copy
  of the cases' tree (`kernel_volume.py --host-files-tree`), except the six
  that need what the volume lacks by design (symlinks, a FIFO, `/dev`, a
  closed standard stream). Guest time is about 40 ms per run and 4 s for the
  64 MiB output;
- `process-compile` (case 5, the compiler volume, which also holds
  `runtime/linux`, `examples/host-sort.au` and the sources of
  `tests/kernel-process/compile.golden` as `rejections/case-NNNN.au`) runs
  the `--target aurora` compiler as `aurorac --emit-object --target linux
  --runtime-root /runtime/linux examples/host-sort.au -o host-sort.o`: it
  reads the program and its imports from the volume, writes the object to the
  overlay in the working directory (the volume root; HostFiles creates no
  directory, on Linux either) and exits 0, and the exported object must equal
  the hosted build's `host-sort.o` (from the build root, three levels above
  the image directory) byte for byte. A second run uses `--emit-executable
  --target aurora --runtime-root /runtime/aurora` to compile and statically
  link the same source in the guest to `host-sort-aurora-native`, with no
  host linker. Its exported bytes must equal the hosted compiler's native-linked
  target executable; the `static-link` merge test admits that executable with
  the kernel's own ELF and address-space policies through `kernel-process`.
  This proves guest compilation and linking, not execution of the newly written
  file: the per-run overlay still ends with the compiler. It then compiles each rejected source with
  the same flags: exit 1, no output and the diagnostics of
  `compile.golden`, which `kernel-process-compile` (merge suite) checks
  against the hosted compiler with `golden.py --reject`. Guest time is about
  2.7 s for the host-sort compile and up to 1 s per rejection.

The `guest-self-host` family, also in the release suite, boots one row:

- `process-self-host` (case 6, 1 GiB guest, the `\aurora\selfhost` volume:
  the `--target aurora` compiler, the build's configured `aurorac.au`,
  `runtime/linux` and the compiler modules beneath `modules/` as the build
  stages them, `kernel_volume.py --module`) runs the compiler on itself with
  C1's flags (`--emit-object --local-symbols --referenced-reflection-only
  --target linux --runtime-root /runtime/linux --module-root /modules
  aurorac.au -o aurorac-stage2.o`, 16 ticks of flag 8). The exported object
  must equal the hosted build's `aurorac-stage2.o`, the object C1 emits of the
  compiler, byte for byte. The compile takes about 3 minutes under TCG and
  charges about the native peak RSS (575 MiB); file reads and writes are well
  under a second of it. The Aurora static linker can link the exported object;
  this self-host row still measures object convergence, not a linked compiler run.

`tests/kernel-process-smoke.py` reduces each run to one line compared with
`tests/kernel-process/<row>.golden` (a fault keeps its vector and architectural
error code, which tell the refusing check: page-fault present/write/user/fetch
bits, or the gate's vector, and the output before it; a refused call keeps its operation); each probe run must also equal its hosted
line in `tests/host-files/cases.golden` without the file tree, each memory
probe run with the whole quota its line in `tests/host-files/memory.golden`
(the runtime's `ud2` trap is SIGILL there) and the compiler with no arguments
the Linux compiler's (`tests/host-files/usage.golden`), and each
`process-files` run, with the `tree:` listing of the volume's tree and the
files it exported, its hosted line but for the hosted tree's symlinks and
FIFO (no reviewed difference remains), and the `process-compile` runs as
above. A run of another row that exports
names its files. Every released run must return its load's frames plus the
memory frames it held. The case word is
the fw_cfg file `opt/aurora/case` (`kernel_profiles.PROCESS_CASES`), read by the
loader beside the fixture selector, so rows that differ only by run list share
one selector and one volume.

The independent memory/files rows run 28/35 fresh source-service lifetimes from
one compiled image. Their original 60-second outer deadline expired during
healthy progress, so only those outer bounds are 180 seconds; process budgets
remain unchanged. The full 64-MiB boundary retains its 128-tick client budget.
Profiling identified checked byte-owner stores and byte packing as substantial
copy costs; checked payload words and bounded value staging reduce that work
without increasing file, memory or watchdog limits. The raw large and ordinary
4096-byte quota probes both exercise unaligned partial failure, poisoned output,
previous-version preservation and page reuse.

Meson runs `process-files` and `process-service` without other tests running
concurrently: their full-capacity workloads qualify deadlines under exclusive
test scheduling, not throughput under competing emulators. Both retain QEMU's
original clock, the same process budgets
and their existing 180/60-second outer bounds. Other guest families and builds
remain parallel.

Limits:

- one CPU executes one process at a time, with at most two resident processes;
  no SMAP, SMEP or PCID (every kernel entry
  stays under the process root, but every process switch flushes the TLB);
- eager commit of the image, stack and arguments: every region page,
  including the whole 8 MiB stack (about 2050 frames), is allocated, zeroed
  and walked at load; memory mappings commit on first touch;
- the source file service holds at most 64 overlay records per service lifetime (pending
  outputs, committed files and replaced files still open): while 64 are
  held, create_output is `exhausted` where Linux has no such limit; the volume has
  no symlinks, FIFOs, devices or empty directories, and the overlay creates no
  directory; a kernel call's buffer must lie in one region or one mapping
  (a valid range crossing into the next region is refused); reads copy 504
  bytes per call and outputs reach the kernel 4096 bytes per call, through the
  session block;
- the frame table is audited after every run, over every frame (about 25 ms
  per run at 5 GiB under TCG);
- the quota holds the frames free at load, but a frame whose generation would
  wrap (its 2^28th release in one boot) retires during the run; a process
  that then uses its whole quota can meet a failing frame allocation at a
  touch or a kernel access, which stops the machine;
- map admission is quadratic over at most 512 descriptors, and boot-services
  memory is not reclaimed;
- the plan stops the boot above about 250 GiB of usable memory (one metadata PD
  for 16 bytes of records and mapping words per frame, 510 table views);
- every process root maps the kernel's arena, frame metadata, mapping words and
  volume supervisor-only, so a Meltdown-class read on an affected Intel CPU
  could expose them (Zen is not affected); SMEP, SMAP and UMIP are not enabled
  (the qemu64 model has none), so `sgdt`/`sidt` reveal the arena's address;
- `int3` and `into` meet DPL 0 gates and end as `protection`, not `breakpoint`
  or `overflow`; SYSENTER on an Intel-vendor CPU (zeroed MSRs) ends as
  `protection`, on AMD as `system_call`;
- the physical width comes from CPUID 0x80000008 alone. On Zen with memory
  encryption, CPUID 0x8000001F EBX[11:6] reduces it, which Zen qualification must
  add;
- CRC32C in `std.checksum` is bitwise (about 1 s per boot for the 6 MiB
  self-host volume);
- no physical device is qualified.
