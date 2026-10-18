# Bounded kernel owned-byte allocation

## Scope and dependency

The `owned-bytes` UEFI profile connects the existing Aurora `ByteRegion` and
`OwnedBytes` lowering to the kernel's real `PhysicalPages` leases. This is a
CPU-only, single-threaded bootstrap allocation milestone. The trusted C++ and
assembly adapter remains part of the small explicit trusted base; it is not a
language-native allocator, userspace runtime, device driver or safety proof.

The profile is deliberately exclusive. It compiles `examples/kernel-owned-bytes.au`
and a private grant bridge in one object instead of the ordinary scalar policy
graph. Each current generated graph exports the same reflection helper names;
mixed independently generated scalar/resource graphs remain unsupported.
The source entries stay local. The original bridge returns scalar status; a
second private bridge returns a pointer-free copied status and 64-byte record.
No owner descriptor, source pointer, span or physical address is returned.

The acceptance gate is focused native ownership/failure coverage, explicit
unsupported-import rejection, complete linked stack/authority/image admission,
independent review, and an actual bounded QEMU boot followed by normal restoration.
Qualification belongs to the exact final source, image and actual guest run; previous receipts do not qualify a changed image.

## Allocation authority and lifetime

The granting kernel validates the handoff, owned memory map, complete page-table
tree, supervisor RW/NX mapping, private stack and disabled interrupts before
opening one static `kernel::bytes::Region`. Its backing is exactly the existing
16-page pool at arena offset `0x50000`. No second allocator, bitmap, page mapping
or free list is introduced. Four fixed owner records each hold up to sixteen
move-only `PageLease` objects. The region metadata has a compiled 3,072-byte cap;
the 16 KiB stack, 1 MiB arena and `0x20000` payload image bounds are unchanged.

The trusted caller must establish exclusive CPU backing for the exact pool range.
Pool, backing and region storage must outlive every registered or retained owner.
Another allocator initialized fraudulently over the same physical range is outside
this contract. Region destruction intentionally performs no release; explicit
successful `close()` is required before reclaiming its storage. The actual UEFI
region and pool have static storage, including after fail-stop.

An open grant accepts logical payload quota from zero through 65,536 bytes.
Quota excludes page rounding and fixed metadata: two small allocations need two
separate pages even if their combined logical length would fit one. A successful
empty allocation consumes a unique owner slot but no page. Four live owners,
page availability, payload quota and monotonic ID exhaustion are independent
limits. Recoverable allocation failure returns the canonical failed descriptor
with the still-live region ID. It commits no owner identity, quota or live count.
The caller must clean up failed descriptors before closing their grant too.

Fragmented pages are supported. Every copied byte access resolves the logical
page index through its retained lease and validates current allocator identity;
physical contiguity is never assumed. Reads fail-stop on bounds, while valid-owner
out-of-range writes return false. Malformed, stale, foreign or closed-grant
descriptors fail-stop before an access shortcut. Native descriptor uniqueness is
a compiler ownership invariant, not a guarantee against malicious trusted C++
copying a live descriptor.

## Initialization, release and failure

Every leased page is zeroed and read back in full, including bytes beyond the
logical length. Allocation commits only after all requested leases and their
initialization succeed. Exhaustion after a partial acquisition scrubs and checks
the whole acquired prefix before releasing it. Normal compiler-generated cleanup
also scrubs and checks complete pages before returning their leases.

A bad lease, scrub/readback failure or unexpected release failure does not claim
success. The adapter retains all remaining leases, faults the grant permanently
and invokes its nonreturning fault endpoint. It does not unwind generated frames,
reclaim a faulted owner or fabricate a zero/false success result. The fault endpoint
must not reenter the adapter or release resources. Hosted failure tests observe
state read-only and terminate the isolated child without unwinding.

The shared `runtime/bytes_abi.hpp` is the unchanged 32-byte compiler-private owner
layout and helper declarations, including hosted resize. The hosted allocator
implementation and its resize semantics remain separate. The kernel profile
supports allocation, copied read/write, validated readonly logical borrowing and
normal drop and failure-safe replacement resize. Replacement resize is specified below and preserves the grant authority.

## Focused commands

From the repository root, with the usual GNU toolchain dependencies:

```sh
./scripts/kernel-owned-bytes-tests.sh
SANITIZE=1 ./scripts/kernel-owned-bytes-tests.sh
python3 -B tests/kernel-uefi-owned-bytes-admission.py --self-test
python3 -B tests/kernel-uefi-owned-bytes-stack.py --self-test
UEFI_MODE=owned-bytes ./scripts/kernel-uefi-build.sh
./scripts/kernel-uefi-smoke.sh owned-bytes
./scripts/kernel-uefi-smoke.sh normal
```

An explicit `AURORAC` may reuse a separately qualified compiler. Image build is
compile/link admission only. The smoke launcher checks the exact original-clock
command and serial transcript, then restores the ordinary image on exit. The profile is selected separately from normal UEFI.
Before a guest, the linked gate must account for generated frames, expression
pushes, private resource call records, C++ stack-usage records, direct call edges
and the bounded four-level page-table verifier. It rejects unmodeled dependencies
and reserves 512 additional bytes for synchronous fault delivery/diagnostics;
the final peak may not exceed 15,360 bytes of the 16,384-byte stack.

The guest exercises runtime lengths 65, 513 and 4,097, two simultaneous owners,
full logical read/write checks, explicit moves, negative allocation, bounds-write
rejection, compiler-driven cleanup, whole-page poison/readback and exact counters.
Host tests cover the wider fragmentation, metadata/page/quota exhaustion,
descriptor and fail-stop boundaries. Neither synthetic transcripts nor native
adapter passes establish a real guest result or physical-hardware support.

## Copied producer handoff

The same exclusive profile now calls a real resource-granted `produce_record`.
It allocates one 512-byte `RamSectorDevice`, writes a fixed 64-byte record at
sector offset 448 through the existing storage library, reads the sector back,
and returns `ProducedRecord`. Its canonical copied layout is eight status bytes
followed by all 64 payload bytes. Every storage operation is checked; recoverable
failure returns a closed `SectorIoStatus` and an actually zero payload.

The second private bridge sets R11 to a 16-byte-aligned region/selector record
and R10 to fresh disjoint 72-byte result storage. The native adapter requires
exact allocation/release counts and zero used bytes, live allocations, held pages
and retained pages before successfully closing the actual region. Only then does
it reacquire and poison released backing and inspect the complete copied status,
all payload bytes and surrounding canaries. Success and out-of-range read cases
allocate/release once; quota and physical-page exhaustion allocate/release zero
times. The success grant has exactly 512 logical bytes. All prior profile cases,
six runtime imports, page pool, stack and image caps remain unchanged.

`scripts/kernel-owned-views-tests.sh` additionally checks extreme sector indices and
rejects corruption of actual success/failure payloads, status and canaries.
Generated assembly is not host-sanitizer-instrumented. Source/object/linked
admission binds the private signature, canonical layout, cleanup/copy order and
call closure; independent exact-image review and a real owned-bytes guest plus
normal restoration remain separate required gates. This adds no protected reader,
IPC transport, persistent owner, filesystem, active device or physical-hardware
qualification.

## Replacement resize


The private 32-byte owner ABI, four fixed allocation records, sixteen PageLease
pool pages, 3,072-byte Region metadata cap, supervisor mapping, 16 KiB stack and
1 MiB arena remain unchanged. An empty existing record becomes private preparing
storage. Public allocation is not called: final logical quota is checked as
new_length <= quota - (used - old_length), and staging does not charge used or
live_allocations. Region::page validates backing and that record's actual lease;
it does not mistake preparing storage for a committed logical owner. Descriptor
lookup exposes only live records.

Validation precedes every shortcut. Canonical failed owners never revive;
negative requests return false; same-size valid requests return true unchanged,
even when all four records are occupied or identities have exhausted. Changed
sizes require a free metadata slot, a fresh identity and representable counters.
Old and new rounded page sets must coexist. Page or metadata exhaustion can reject
shrink as well as growth. Resize to zero needs a free metadata slot but no new page.

Every new page is fully zeroed/read back, including padding. Every old lease is
preflighted; copied prefixes use checked logical page spans without assuming
physical contiguity. The preserved prefix is min(old_length,new_length). Shrunk
suffixes cannot revive after regrowth. After all recoverable work succeeds, old
pages are scrubbed/read back and released, then replacement identity and logical
accounting commit in the synchronous, single-CPU, nonreentrant adapter.

A changed-size success increments successful_allocations and releases once,
keeps live_allocations constant, and updates last identities. peak_used observes
committed logical use; peak_held_pages includes successful old+new staging.
Recoverable failure leaves all committed metrics, old descriptor and old bytes
unchanged. It scrubs/releases any acquired staging prefix and restores empty
record hygiene. Free-page contents and allocator lease generations need not be
unchanged after rollback.

Bad lease, scrub or unexpected release failure is terminal: both transaction
records are retained, including a zero-page peer, the Region faults permanently,
and the endpoint never returns or unwinds. Old bytes are not promised unchanged
after terminal retirement failure. Remaining leases cannot be reclaimed or
forgotten; unrelated owners/foreign holders remain untouched. Hosted fault
observers inspect state only and exit without unwinding.

## Readonly views and RAM storage

The real Aurora consumer copies and narrows 56-byte readonly views, including the 4095/4096 logical boundary over fragmented physical pages. Empty views retain their owner lifetime and cannot produce nonempty success. The private graph admits exactly allocate, at, set, drop, borrow_length and resize helpers; no unrelated runtime imports or mixed scalar/resource graph is accepted.

The same profile exercises the unchanged `RamSectorDevice` on 16 sectors of page-backed ownership. It tests complete copied readback, readonly/range ordering, quota and page failures, fragmented leases, full-page scrub and exact cleanup. Its visibility flush is volatile and durable flush remains unsupported. This is CPU-only RAM storage, not a mounted/protected file service or persistent device.

## Protected Utf8Text consumer

The opt-in `runtime-owned-text` UEFI profile runs the existing `std::Utf8Text`
implementation in one CPL3 domain. It uses one private Region with a fixed
64-byte logical quota and the same PhysicalPages leases, descriptor validation,
transactional resize and whole-page scrub/release code. The reserved runtime
layout still has two slots; only slot zero is created or executed. The second
image supplies the existing closed loader metadata shape, not a second domain.

Six exact CPL3 stubs load/store the generated 32-byte owner in userspace and
transport its four words through RDI/RSI/RDX/RCX. R8/R9 carry scalar arguments;
RAX returns a copied scalar. The private entry wrapper constructs the compiler's
16-byte argument record on the user stack. R10 owner addresses never become
kernel pointers. The kernel authenticates the exact trap continuation, complete
integer frame, active domain incarnation/root, timer epoch and private Region
before calling the existing allocator once. Payload pages and allocator metadata
remain supervisor-only; byte access uses the existing copied accessors.

Allocator traps preserve the current hardware countdown and original cumulative
128-tick allowance. Normal return, an admitted source bounds fault, and hardware
budget exhaustion return to the kernel, stop/drain the timer and retire the run
before cleanup. `Region::revoke_quiescent` walks private records and shares normal
drop's release/accounting path; ordinary `close` still refuses live allocations.
No user descriptor supplies cleanup authority. A failed scrub retains remaining
leases and permanently faults the Region; neither backing nor metadata is reused.
Malformed/stale descriptors and wrong trap sites/regions fail-stop, rather than
claiming contained recovery from arbitrary hostile native code.

The source consumer covers UTF-8 append, invalid-scalar rollback, growth to the
64-byte quota and failed replacement rollback, then live-owner fault and budget
termination. `runtime-owned-text-site`, `runtime-owned-text-region` and
`runtime-owned-text-stale` are isolated negative profiles; the last replays the
old descriptor after a committed resize into the unchanged allocator validator.
The existing allocator harness also checks stale grants after revocation and
second-owner scrub failure after partial cleanup. The user image remains limited
to three RX pages (12288 bytes), with the unchanged 15360-byte stack admission.
No compiler feature, Call graph, general scheduler, device mapping or new
bootstrap stage is introduced. Qualification receipts belong to exact-source
logs and PRs, not this mechanism description.

The opt-in `runtime-console-region` profile composes a sealed ConsoleSession and
ByteRegion in the compiler's exact 24-byte entry record, reserved in 32 user-stack
bytes. It reuses the six byte operations and adds two instruction-checked console
stubs. The input sample address stays in CPL3 R10; only presence, byte and damage
cross the trap boundary. A private grant translates the opaque user slot and
generation. Console input performs one authenticated sample per trap. Empty input
charges the discarded partial timer quantum, saves the complete integer frame,
and unwinds to a quiescent supervisor boundary. The shared timer polling loop
runs there. A durable copied sample can resume only the exact ticket, incarnation,
root, Region, console generation, launch record and original budget epoch.
Resumption changes only the three sample result registers; live locals and byte
owners remain intact. It never renews the 128-unit allowance.

Cancellation invalidates the saved continuation/sample and revokes the grant
before quiescent owner reclamation. Retirement rejects remaining console or
polling authority. The first source consumer uppercases one LF-terminated line of
at most 32 printable ASCII bytes using a single 32-byte Utf8Text allocation; CR,
control bytes, overlong input and damage reject before output. Output failure may
leave a prefix. The smoke driver withholds each byte until a live-owner park.
Separate cancellation, ready-cancellation, damage, output-failure, exhaustion and
emitted-bounds-fault profiles exercise the same adapter. Cancellation also repeats
with a new incarnation to reject old tickets. The existing image admission
includes the retained supervisor wait/drain frame plus IRQ and fault reserve.
The image, stack and payload caps remain 12288, 15360 and 64 bytes. This is one
protected application contract; it adds no scheduler or bootstrap stage.
