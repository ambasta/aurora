# Hosted growable byte buffer

`std.byte_buffer` implements `std::ByteBuffer` in Aurora using one private
`builtin::OwnedBytes` field and an `i64` logical length. It is a small allocating
collection prerequisite for native library consumers. It adds no compiler builtin,
raw address, borrowed owning parameter or kernel dependency. Receiver-bound readonly views use the current ownership rules.
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
and normal-scope cleanup use the existing [owning-class contract](../compiler/OWNERSHIP.md).

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
See the [lifetime/representation contract](../compiler/OWNERSHIP.md)
.

## Checked operations

| Operation | Contract |
|---|---|
| `read_u8(i64 offset) const -> ByteReadResult` | Returns a copied successful byte only for `0 <= offset < size()`. Otherwise returns `out_of_range`; `value_or` uses its supplied fallback. |
| `try_write_u8(i64 offset, u8 value) -> bool` | Writes only inside the logical size. Invalid owner or offset returns false unchanged. |
| `try_reserve(i64 minimum_capacity) -> bool` | Invalid owner or negative minimum returns false. A minimum at/below capacity succeeds without allocation. Larger requests allocate exactly the requested capacity, preserving logical size and all prior bytes. |
| `try_append(u8 value) -> bool` | Appends one byte, growing when full. Successful writes precede the logical length increment. |
| `try_append_bytes(builtin::span<const u8> input) -> bool` | Appends disjoint readonly input with one growth attempt; rejects self-views at compile time, including empty views. See the [method-span contract](../compiler/OWNERSHIP.md). |
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
[owned-byte resize](../compiler/OWNERSHIP.md#failure-safe-replacement-resize).

## Bulk append

`try_append_bytes` checks overflow before computing its required size. Growth
requests the larger of that required size and saturated doubled capacity (one
for zero capacity), with no retry at a smaller target. It reserves before copying
and commits logical length only after every byte is written. Invalid buffers
return false even for empty input; valid empty input succeeds allocation-free.
All recoverable failures preserve size, capacity, logical bytes and committed
allocation accounting. The complete operation requires current-source byte and lifetime regressions.
