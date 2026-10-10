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

All eleven finite image variants pass exact composition, private bridge/user
wrapper, image and combined native/Aurora stack checks. The measured supervisor
maximum is 14,768 bytes plus the existing 512-byte fault reserve, leaving only
80 bytes below the unchanged 15,360-byte admission cap in the 16 KiB stack. The
actual deepest path is ACPI/PCI discovery and four-level page verification.
Client/service totals including their wrappers are 112/352 bytes. Every rebuild
must re-establish these bounds; the thin margin is not an expanded budget.

The native runner and optimized ordered-transcript controls are registered in
`full`/`slow`/`integration`, with a private Meson output directory. The existing
UEFI smoke launcher selects the original clock for each explicit snapshot mode,
validates its exact transcript, and restores the normal image on success or
failure. Compiler-free launcher controls exercise those restoration exits.
All eleven modes passed actual QEMU/OVMF execution, including service fault and
cancel/restart, with exact launched EFI captures and normal-image restoration.
Fresh normal UEFI and BIOS smokes also passed. Final integrated `full` and
independent outcome review remain release gates. The exclusive owned-byte
profile is unchanged; this composition admits no arbitrary copied inputs.

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

- `scripts/kernel-uefi-ipc-tests.sh`: pure policy/model, image authority and strict
  ordered transcript tests. `SANITIZE=1` enables ASan/UBSan.
- `scripts/kernel-uefi-ipc-all.sh`: fifteen real OVMF modes; each restores a normal
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
- `ipc-root`, `ipc-kernel-trap`: otherwise plausible return under the wrong actual
  root, or exact known compiler trap reached at CPL0.
- `ipc-exhausted`: a restrictive generation ceiling permits binding but denies
  transaction minting. Host tests separately exercise the uint64 maximum checked
  successor; the emulator does not loop through 2^64 generations.

The previous 80 modes remain acceptance gates. This mechanism adds no timer,
preemption, general service registry, persistent process, SMP, IPC buffering,
DMA/controller activation or physical Framework support. Firmware trust and
physical device isolation remain separate unfinished requirements.

## Candidate verification

The independent fifteen-mode OVMF run passed on compiler
`d91e06fad144a89c1c836e16db20ef48b8a644bf4c23b22a1517e08f25e1d82c`.
The strict PIC/PE image gate remained enabled. Hosted ASan/UBSan checks passed
26,120 rejected envelope combinations and 262,144 six-operation sequences
against an independent state model, plus copied full-width/zero payloads,
revocation/rebirth and generation boundaries. Transcript checks have fifteen
positive and 1,732 negative cases; IPC image authority adds four positive and
26 negative cases to the existing three/64 image controls. These are bounded
tests and independent review, not a proof of general IPC safety. The parent
checkpoint records the complete previous-mode preservation run separately.
