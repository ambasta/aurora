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
See [the results](kernel-owned-bytes-results.md) for the accepted evidence scope.

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
normal drop and failure-safe replacement resize. The
[resize contract](kernel-owned-resize.md) and [focused results](kernel-owned-resize-results.md)
cover fresh six-helper admission and bounded guest qualification; historical
five-helper evidence is not reused. Mutable/general escaping borrowing,
DMA/BAR/IOMMU activation, concurrency, exception unwinding and mixed graphs remain
out of scope.

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
command and serial transcript, then restores the ordinary image on exit. The
separately selected profile is not added to the historical 177-mode aggregate.
Before a guest, the linked gate must account for generated frames, expression
pushes, private resource call records, C++ stack-usage records, direct call edges
and the bounded four-level page-table verifier. It rejects unmodeled dependencies
and reserves 512 additional bytes for synchronous fault delivery/diagnostics;
the final peak may not exceed 15,360 bytes of the unchanged 16,384-byte stack.

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

The focused host command above additionally checks extreme sector indices and
rejects corruption of actual success/failure payloads, status and canaries.
Generated assembly is not host-sanitizer-instrumented. Source/object/linked
admission binds the private signature, canonical layout, cleanup/copy order and
call closure; independent exact-image review and a real owned-bytes guest plus
normal restoration remain separate required gates. This adds no protected reader,
IPC transport, persistent owner, filesystem, active device or physical-hardware
qualification.

## Reconstructed readonly-owner consumer

The earlier reconstructed readonly-owner checkpoint extended this same exclusive
profile to exactly five imports:
allocate, at, set, drop and borrow_length. A real Aurora consumer copies and
narrows the existing 56-byte logical span, reads every byte and checks logical
4,095/4,096 across a physical page boundary. Its return value is the observed
length, checked against the independently supplied owner length. An empty span
cannot masquerade as nonempty success. The consumer may call only copied read;
three exact aligned 64-byte span-call records are checked at source and link.

Eight even-page holders force two 4,097-byte owners onto pages 1/3 and 5/7.
Whole-page scrub, untouched neighbor poison and actual foreign lease identities
are checked before holder release and explicit region close. Existing length
cases remain; successful-empty ownership adds no page. Exact totals are nine
allocations and nine releases. Quota, pool, stack and region implementation do
not change. This historical checkpoint rejected resize and unrelated imports; no stubs were supplied.

The dependency is the freshly reconstructed owned-span compiler/runtime.
The exact image/import/linked-stack checks and independent source review passed
before the new guest. Actual owned-bytes, runtime-span and normal guests passed
with exact normal restoration. Historical results do not transfer.
See [current results and limits](kernel-owned-views-results.md).

Focused exact-source host replay, with an explicitly selected compiler:

```sh
AURORAC=/path/to/current/aurorac ./scripts/kernel-owned-views-tests.sh
AURORAC=/path/to/current/aurorac SANITIZE=1 ./scripts/kernel-owned-views-tests.sh
```

The adversarial host wrapper calls the real descriptor validator, then poisons
its length to zero. Nonempty input must reject with exact failure. It is never
linked into a guest. Host sanitizers do not instrument generated Aurora assembly.
