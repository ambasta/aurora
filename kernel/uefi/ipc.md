# Staged request/reply IPC foundation

## Protected snapshot profile

The optional `snapshot-client` and `snapshot-service` sources exercise one
immutable copied 64-byte RAM record, after its real producer's owners and region
close. The service accepts operation/absolute-offset words, selects the actual
byte in protected Aurora and returns closed byte/EOF/error encodings. The client
is relaunched with a fresh scrubbed stack for every request/completion; its actual
completion return supplies the next absolute offset. This is a finite snapshot
consumer, not persistent Aurora locals, mutable files or general process lifetime.

`scripts/kernel-snapshot-tests.sh` compiles those sources, the minimal combined
supervisor root and existing Mailbox for a bounded native replay. It also links
the two user fixtures under the unchanged 4 KiB limit. Native SIGILL observation
of the actual service bounds read is not protected fault containment evidence.
The fixed copied service record is 96 bytes at user stack top minus112, with
phase/operation/offset at0/8/16, Snapshot64 bytes at24..87 and zero tail padding.
The conditional IPC wrapper reserves the record before saving its envelope and
restores exact RSP before the existing INT0x81. The source record and wrapper are
assembled together to keep the aggregate entry local.

`UEFI_MODE=snapshot` composes only the existing ACPI/PCI discovery, protected IPC
runtime and a closed-region copied producer. It keeps the allocator and protected
stack pools separate. After authenticated receive and complete stack scrubbing,
the runtime verifies the retained final stack PageLease and its exact user and
supervisor mappings, then copies only the fixed record through the supervisor
mapping. Publication is bound once to the current endpoint generation; clearing,
revocation and fresh production precede a restarted service incarnation.

The adapter validates only the closed reply encoding. The compiled client checks
each actual returned byte and supplies the next offset; malformed or incorrect
actual replies fail closed. Explicit output-buffer, retained-slot and lease
clearing does not promise erasure of all compiler-created supervisor stack copies.
Finite fault/cancel/restart, foreign owner, stale/revoked generation, producer
selector/quota/page failure and actual malformed/wrong-byte reply image variants
are selected with `snapshot-*` modes in `scripts/kernel-uefi-build.sh`.

Every image variant requires exact private bridge/user-wrapper, image and combined native/Aurora stack admission. The supervisor normal path plus 512-byte fault reserve must fit 15,360 bytes of the 16 KiB stack; current bounds must be recalculated after every rebuild. Native/transcript tests belong to full/slow/integration. Actual snapshot guests use the original clock, strict ordered transcripts and normal restoration. Focused/previous runs do not qualify a changed image.

This optional UEFI profile runs two independently compiled Aurora images under
separate owned CR3 roots. The client produces a two-word request `(40, 2)`, the
service computes 42, and the client checks the copied reply. It is a bounded
cooperative transaction, not arbitrary suspended-call IPC or a scheduler.

## Authority and copying

The existing UEFI arena, immutable virtual layouts, RX images, private page
tables, guarded user/RSP0/IST stacks, integer-only profile and exact compiler
trap metadata remain the boundary described in [runtime.md](runtime.md).
No firmware/ECAM window or writable image alias enters either user root.

The trusted launcher selects request, service or completion phase. Six scalar
input registers carry phase, first word, endpoint slot, endpoint generation,
transaction generation and second word. Other integer registers are cleared,
and all four stack pages are scrubbed before every entry. A small assembly
wrapper calls the compiled three-i64 function and returns a versioned scalar
envelope through the existing exact `int 0x81` return site. There is no source
language syscall, unchecked pointer, shared page or foreign-call facility.
The wrapper and temporary C++ policy are trusted bootstrap components.

Endpoint slots and generations are untrusted claims. `Mailbox` looks up fixed
client/service rights and compares the caller's live `DomainHandle` with the
stored owner through `DomainRegistry`. The adapter obtains that caller from its
kernel-owned active slot only after validating actual CR3, active incarnation,
CPL, selectors, flags, complete RSP0 frame and saved kernel continuation. Neither
the phase nor the caller identity is selected from the envelope. Exact call-site
validation complements capability checks; it does not replace them.

A single kernel-owned record copies two 64-bit words from the captured request.
Delivery copies them into the service's launch arguments and erases the queued
request. Reply stores one copied word. Consumption copies a typed replied or
cancelled outcome and erases the record. The compiled fixture interprets payload
words as i64 values; endpoint/transaction scalars are never payload pointers.
The service need not share an address space, stack or writable memory with the
client. This profile deliberately provides no variable-length buffer operation.

## Lifetime and cancellation

The fixed state machine is idle → pending → delivered → replied → consumed.
A pending or delivered transaction can instead become cancelled. Reply and
cancel are first-terminal-wins: a replied transaction cannot be cancelled, and
a cancelled transaction cannot accept a reply. Invalid operations leave the
record unchanged. Recycling requires consumed and scrubbed state.

Endpoint bind epochs and transaction IDs share a monotonically increasing global
sequence. Zero is invalid; overflow denies new authority. Revocation clears both
grants. Rebinding, domain-slot reuse and mailbox reconstruction cannot resurrect
old claims. The pure policy is single-CPU, has no allocation, and requires its
registry to outlive it. It does not independently establish hardware privilege;
that is the adapter's responsibility.

After request submission the client is logically blocked. The kernel runs the
service, then relaunches the client at the validated entry with a completion
phase. No arbitrary user PC or stack continuation is retained. Cancellation runs
only under the owned kernel root with no active domain. There is no deadline,
timeout or interruption of a non-yielding program in this profile.

The service-fault gate executes an actual bounds failure in the compiled service.
The exact known user UD2 is contained, the kernel root is restored, and the
transaction is cancelled once. The compiled client verifies a cancelled outcome.
The kernel then revokes endpoint authority, scrubs and retires the service,
reuses its zeroed stack frames, creates a fresh domain incarnation and grants,
and runs a new successful client/service transaction. Unexpected fault origins
or sites remain fatal. A client fault is not given the service cancellation path.

## Gates

- `meson test -C build/meson --suite full`: pure policy/model, image authority and strict
  ordered transcript tests. `SANITIZE=1` enables ASan/UBSan.
- `meson test -C build/meson --suite guest-ipc`: fifteen real OVMF modes; each restores a normal
  UEFI image afterward. Use the existing QEMU/OVMF dependency environment.
- `ipc`: request/delivery/reply/client verification and zero final records/leases.
- `ipc-fault`: actual service bounds fault, cancellation, client error handling,
  service retirement/rebind/scrubbed reuse and a successful fresh transaction.
- `ipc-cancel`: cancel a pending request, reject late reply and duplicate cancel,
  deliver the error, recycle the zero record and complete a fresh request.
- `ipc-owner`, `ipc-stale`: a client claims the service endpoint, or presents an
  actually revoked bind epoch after rebind. Both fail before submission.
- `ipc-version`, `ipc-phase`: malformed protocol version or user-forged phase.
- `ipc-transaction`, `ipc-duplicate`, `ipc-late`: wrong reply generation, a second
  actual user reply, or an actual user reply after cancelled completion.
- `ipc-site`, `ipc-unknown`: forged return site or unknown user UD2.

All IPC fault modes boot the one `ipc-fixture` image and pick their case from the
serial selector. The owner, version, phase, transaction, site and unknown cases
used to be separate images with a hostile client binary each; the fixture kernel
now applies the same corruption to the trapped exit before validating it (claimed
slot, version, phase, reply transaction, a trapped return PC off the registered
site, or resuming the client at its wrapper's unregistered `bad_entry` `ud2`). The kernel checks that reject
them are unchanged, and each mode keeps its own guest run and transcript oracle.
- `ipc-root`, `ipc-kernel-trap`: otherwise plausible return under the wrong actual
  root, or exact known compiler trap reached at CPL0.
- `ipc-exhausted`: a restrictive generation ceiling permits binding but denies
  transaction minting. Host tests separately exercise the uint64 maximum checked
  successor; the emulator does not loop through 2^64 generations.

The previous 80 modes remain acceptance gates. This mechanism adds no timer,
preemption, general service registry, persistent process, SMP, IPC buffering,
DMA/controller activation or physical Framework support. Firmware trust and
physical device isolation remain separate unfinished requirements.

## Protected-console copied note

The two-domain protected console admits one additional explicit typed service
composition under its existing client/service timer budgets. It does not combine
the separate snapshot/owned-region profile with Console, Display or other owners.
The normal scalar upper protocol remains phases 0/1/2. Note reads use phases
12/11/13 for request/service/completion with byte, EOF and missing replies from
actual compiled Aurora. See the [program-console contract](../../docs/program-console-contract.md#session-local-protected-note).

`kernel.note_read::NoteRead64` contains 64 bytes and one signed length. Together
with three scalar launch words it occupies 96 initialized bytes at user S-112;
its final qword is data, unlike the separate Snapshot64 profile's zero padding.
The service reserves 112 bytes before saving its 48-byte envelope. Only the
verified retained last stack lease is used to stage this record after an
authenticated receive, and only the fresh bound service generation matches.
No source pointer, endpoint, owner or view crosses the copied-value bridge.

The supervisor's ordinary Aurora update returns an 80-byte closed note/event
record; its projection returns 72 bytes. Native code retains the saved value and
per-read generation, checks closed representation and quiescence, and supplies
no command/content policy. Snapshot publication, byte-region lifetime, general
file service authority and persistent storage remain separate contracts.
