# Readonly logical views of runtime-owned bytes

This extension uses one `builtin::span<const u8>` source type and representation
for array-backed and owner-backed readonly views. It does not add mutable spans,
unchecked addresses, general returned borrowing or ownership transfer by view.
The bounded owning-class and readonly-window contracts otherwise still apply.

## Source and lifetime contract

`borrow_bytes(owner)` accepts a live named OwnedBytes or direct accessible private
OwnedBytes field, including the implicit receiver field. Private fixed-array
fields and copied array wrappers are unsupported origins. Allocation identity is
validated when acquiring a view. Failed allocation traps; successful empty owners
produce valid zero-length views.

Bindings are const, initialized and non-rebindable. Copies and subspans retain
exact parent and root provenance. Any live descendant, including empty views,
prevents mutation, resize, movement, consumption or destruction of its owner.
A borrowed field prevents mutable methods or movement of the containing object;
other direct owning fields remain independent. Sibling const methods and owner
reads are permitted. Scope exit releases views before their owners. Lifetime and
ownership state must agree across continuing control-flow paths and loop backedges.

Temporary argument borrows acquire authority at their left-to-right evaluation
point and retain it through the whole call. Later arguments may not mutate or
consume that root. Receiver arguments are evaluated before acquiring a returned
view, but consuming that receiver during argument evaluation rejects.

## Narrow receiver-bound results

A const nonconstructor method of a concrete owning class may return a readonly
view derived from exactly one direct OwnedBytes field of its receiver. All return
paths must agree on that field. Named subspans may narrow the visible logical
window; it need not equal allocation capacity. `ByteBuffer.bytes()` returns only
its logical prefix. A failed ByteBuffer allocation therefore cannot be borrowed.

The caller binds a const span or passes the temporary to an ordinary span parameter.
Authority is tied to the caller's exact root/field, never a callee stack address.
Named receivers and the implicit receiver are supported. Temporary receivers,
ordinary-function span results, local-array and local-owner returns reject.
Span-result methods must derive their result directly rather than forwarding
another span-result method; scalar-result const helpers may consume such views.
Nonconstructor methods now accept synchronous readonly span parameters under the
[method-span contract](METHOD-SPANS.md). Class span fields, generic span type
arguments, reflected capabilities and asynchronous escape remain unsupported.

## Private representation and independent verification

Every span spill and call-record position reserves 56 bytes, aligned to eight:
kind at byte0 (array0/owner1); array base plus zero padding or complete immutable
NativeOwner snapshot at bytes8–39; nonnegative logical start40 and length48.
The snapshot conveys no ownership and cannot be dropped, moved or bound as an
owner. Array-only complete module graphs retain direct checked loads and acquire
no owner-runtime imports. Owner reads call the checked adapter, which supports
both contiguous host payloads and independently leased fragmented kernel pages.

`BorrowOwnedSpan{offset,fieldIndex,resultOffset}` names standalone storage when
fieldIndex=-1, otherwise a direct owning field; offset0 is the implicit receiver.
The verifier requires an active owner token and region, with exact field and
binding identity. Native lowering calls `__au_runtime_bytes_borrow_length` before
copying the snapshot and preserves the current scalar and saved operand stack.
Copies transport all seven words. Subspan validates bounds before adjusting
start/length; index checks precede byte loads or adapter calls.

A function's receiverSpanField summary names one exact direct owner field under
a const owning receiver. Every reachable ReturnSpan independently verifies that
origin and rejects unrelated live resources. Appropriate receiver-derived views
end with invocation. MethodCall derives caller-side authority from its own actual
receiver token and requires a fresh result spill. Hidden-result calling modes
transport the entire record without owner transfer or cleanup.

## Reconstruction and qualification

The previous unpublished candidate was lost when its execution filesystem rolled
back. This source is a fresh reconstruction from accepted PR76; historical source
hashes and test evidence do not qualify it. Fresh native, ABI, malformed IR, adapter, sanitizer and affected existing guest
regressions are recorded in the [results](../docs/readonly-owned-spans-results.md).
No new guest-owned-span admission, kernel resize, JSON parser, self-hosting,
physical-hardware support or production memory-safety proof is claimed.
