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
The source entry stays local, and only a scalar status crosses the private bridge.
No descriptor, pointer, span or physical address is exported to Aurora.

The next acceptance gate is focused native ownership/failure coverage, explicit
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
supports allocation, copied read/write and normal drop only. `try_resize` is
explicitly rejected by object-import admission and unresolved at the actual
kernel link; there is no resize success/failure stub. General payload borrowing,
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
