# Hosted growable byte buffer

`std.byte_buffer` implements `std::ByteBuffer` in Aurora using one private
`builtin::OwnedBytes` field and an `i64` logical length. It is a small allocating
collection prerequisite for native library consumers. It adds no compiler builtin,
raw address, borrowed owning parameter or kernel dependency. The separately
qualified compiler extension adds receiver-bound readonly views.
`BinaryBuffer64` remains the copied fixed-record API; `Sector512` and
`RamSectorDevice` keep their existing contracts.

## Construction and state

Import both `std.binary` and `std.byte_buffer` directly under the current module
visibility rules. Construction takes one region and an explicitly moved owner:

```cpp
builtin::OwnedBytes allocation = region.try_allocate(initial_capacity);
std::ByteBuffer buffer = std::ByteBuffer(region, move(allocation));
```

The buffer starts logically empty, including when the supplied owner already
contains bytes. It retains that owner's capacity, allocation identity and region.
The granting host must outlive it. The class is move-only; ordinary owning calls
and normal-scope cleanup use the existing [owning-class contract](../compiler/OWNING-CLASSES.md).

- `ok() -> bool` distinguishes valid ownership from allocation failure.
- `size() -> i64` is the logical byte count.
- `capacity() -> i64` is the committed backing byte count.

Valid state satisfies `0 <= size() <= capacity()`. A failed initial allocation
produces an inert buffer with false `ok()` and zero size/capacity. It cannot recover
by reserving or appending. Successful zero-capacity ownership is distinct: it can
grow if later allocation succeeds. There is no ambient allocator or hidden region.

## Readonly logical prefix

`bytes() const -> builtin::span<const u8>` exposes exactly `[0,size())`, never
spare capacity or discarded suffix bytes. The result is tied to this precise
buffer and private owner; live descendants freeze all mutable buffer methods and
moves, even for zero length. Scope exit releases that view authority. Successful
empty allocation returns a valid empty view; borrowing an invalid buffer traps.
Existing UTF-8, binary and JSON consumers can take this view without copying.
See the [lifetime/representation contract](../compiler/READONLY-OWNED-SPANS.md)
and [fresh reconstructed results](readonly-owned-spans-results.md).

## Checked operations

| Operation | Contract |
|---|---|
| `read_u8(i64 offset) const -> ByteReadResult` | Returns a copied successful byte only for `0 <= offset < size()`. Otherwise returns `out_of_range`; `value_or` uses its supplied fallback. |
| `try_write_u8(i64 offset, u8 value) -> bool` | Writes only inside the logical size. Invalid owner or offset returns false unchanged. |
| `try_reserve(i64 minimum_capacity) -> bool` | Invalid owner or negative minimum returns false. A minimum at/below capacity succeeds without allocation. Larger requests allocate exactly the requested capacity, preserving logical size and all prior bytes. |
| `try_append(u8 value) -> bool` | Appends one byte, growing when full. Successful writes precede the logical length increment. |
| `try_append_bytes(builtin::span<const u8> input) -> bool` | Appends disjoint readonly input with one growth attempt; rejects self-views at compile time, including empty views. See the [method-span contract](../compiler/METHOD-SPANS.md). |
| `try_truncate(i64 new_size) -> bool` | Accepts only `0 <= new_size <= size()`, retaining allocation and capacity. A larger or negative size returns false. |
| `clear() -> bool` | Equivalent to truncating to zero; retains allocation and capacity. |

Every mutating operation on an invalid buffer returns false, including reserve(0),
truncate(0) and clear(). Read failure uses the existing `ByteReadStatus::out_of_range`;
callers can query `ok()` if they need to distinguish invalid ownership from an
invalid index. Read reports are independent values and survive later mutation.

Truncation and clear do not scrub discarded bytes. Those bytes are inaccessible
through this API; reserve does not expose them, and append overwrites each byte
before increasing size. There is no logical regrow operation that reveals an old
suffix. This is not a secure-erasure contract.

## Growth and failure

Append grows zero capacity to one; otherwise it doubles full capacity. Before
doubling a capacity above `4611686018427387903`, it instead requests the maximum
`i64` value `9223372036854775807`. At that maximum logical size append returns
false before addition. These branches cannot overflow signed arithmetic. Requests
may still fail because the runtime cannot represent or allocate the payload.

Growth makes one allocation attempt at the geometric target. It may fail even
when exact one-byte growth would fit the quota. For example, a full capacity-two
buffer with quota three cannot append directly: its target is four. An explicit
`try_reserve(3)` can succeed, after which append needs no allocation. There is no
implicit fallback that changes allocation or amortization behavior under pressure.

All recoverable failures preserve logical size, capacity, readable bytes and
committed allocation accounting. The existing failure-atomic resize helper does
the fallible replacement work before commit. After successful growth, private
state proves the append index is valid; its write has no recoverable failure.
Already-completed argument side effects are outside the operation's rollback
promise. Fail-stop faults do not unwind resources.

Reserve, truncate, clear and in-capacity append avoid allocation where stated.
Geometric growth bounds successful replacement frequency, but no measured
performance or equivalent-C claim is made. Region quotas count committed payload,
not transient old-plus-new storage or allocation metadata; see
[owned-byte resize](../compiler/OWNED-BYTES.md#failure-safe-replacement-resize).

## Example and focused verification

[The example](../library/examples/byte_buffer.au) reserves an exact runtime byte
count, appends byte values and reads a checksum. Its region is explicitly granted
by the hosted test bridge. The existing owner test harness supplies allocation
failure injection, allocation/release identity checks and complete normal cleanup.

```sh
python3 -B tests/compiler/byte_buffer.py /path/to/aurorac --compile-only
python3 -B tests/compiler/byte_buffer.py /path/to/aurorac
python3 -B -O tests/compiler/byte_buffer.py /path/to/aurorac
```

The runner covers invalid versus valid-empty allocation, preloaded hidden bytes,
copied reads, signed endpoint guards, exact and geometric capacity, quota failure
and recovery, host-allocation failure, allocation-free reuse, explicit moves,
loop/early-return cleanup and complete byte comparisons after repeated modeled
operations. Rejection fixtures protect privacy, ownership, const access and exact
argument types. It joins the existing Make compiler graph and Meson `bytes`/`dev`
suites; the example also has an explicit dependency-tracked Meson compile target.

Near-maximum doubling cannot be exercised with realistically allocated backing;
the overflow branch is checked by source arithmetic review. Native endpoint tests
exercise maximum reserve requests and invalid indices/truncations without claiming
an actual maximum-sized allocation. Generated Aurora assembly is not sanitizer
instrumented. No full native aggregate, sanitizer or emulator qualification is
implied by this focused gate.

The current kernel adapter deliberately rejects resize imports. This collection
is hosted-only until that separate integration exists. It is not an owned string,
Unicode API, JSON parser, generic vector, native program startup or self-hosting
toolchain, and does not remove the trusted C++ hosted allocator dependency.

### Historical PR76 focused result — 2026-10-07

The final corpus passed compile-only admission: 14 programs and 17 rejection
fixtures, with all 37 native invocations explicitly skipped. Separate normal and
optimized Python runs then each passed those 14 programs, 37 native invocations
and 17 rejection fixtures using the unchanged PR74 compiler, SHA-256
`6756e670ccfd2dc1d94a48672915852697ab2ec08df0c09da471e37491f8afc5`.
Three seeded models each compare complete visible bytes after 60 operations;
the larger append case checks all 4,097 bytes. The shared hosted observer checks
allocation/release identities, exact counters, selected cleanup order and no live
owners on return. Source, test, contract and routing received independent review.
The normal-Python direct dependency reruns passed 56 OwnedBytes native cases,
seven exact traps and 38 rejections, plus 49 owning-class native cases, four exact
traps and 42 rejections. Meson configuration confirmed the new `bytes`/`dev` test
and example target without building Aurora; its first setup lacked Ninja on PATH,
and the corrected setup used the already installed Ninja.

The example's initial compile-only rejection was corrected by adding its required
direct `std.binary` import. An older formatter without owning-field support also
rejected the module; the existing owning-class-capable formatter passed both
files with idempotent canonical layout. Ruff 0.16.7 passed the Python runner.
Neither tool was rebuilt, and no native failure was suppressed. This change does
not modify compiler, hosted-runtime or kernel implementation.

## Bulk append

`try_append_bytes` checks overflow before computing its required size. Growth
requests the larger of that required size and saturated doubled capacity (one
for zero capacity), with no retry at a smaller target. It reserves before copying
and commits logical length only after every byte is written. Invalid buffers
return false even for empty input; valid empty input succeeds allocation-free.
All recoverable failures preserve size, capacity, logical bytes and committed
allocation accounting. Fresh [method-span results](method-spans-results.md) qualify this operation
separately; no previous ByteBuffer receipt is evidence for the new operation.
