# Hosted runtime-sized byte ownership candidate

The [readonly owned-view extension](READONLY-OWNED-SPANS.md) now adds runtime
owner origins and narrow const receiver-field results using the same span type.
Historical qualification and representation details on this page describe their
original checkpoints; the extension's source/ABI contract and fresh results are
separate. Existing array-only temporary-chain restrictions remain unchanged.

This checkpoint adds one allocation/lifetime prerequisite. Independent source
review and the [focused native composite](../docs/owned-bytes-results.md) passed. It does not replace the fixed-record BinaryBuffer64 or
Sector512 APIs. The resize extension below has passed [focused checks](../docs/owned-bytes-resize-results.md); it adds
no element collection, borrowed payload view or kernel physical allocator.

## Source contract

```cpp
module owned_example;

auto pass(builtin::ByteRegion region, builtin::OwnedBytes input) -> builtin::OwnedBytes {
    input.set(0, 42u8);
    return move(input);
}

auto example(builtin::ByteRegion region, i64 length) -> i64 {
    builtin::OwnedBytes bytes = region.try_allocate(length);
    if (!bytes.ok()) {
        return -1;
    }
    builtin::OwnedBytes result = pass(region, move(bytes));
    return result.size();
}
```

The trusted host supplies ByteRegion authority. Aurora cannot manufacture a region
from an integer quota, construct a local region, rebind/copy/return it, store it in
a class, or inspect it through reflection. The region parameter is borrowed for
synchronous calls. Its granting host must outlive every associated owner.

A resource-aware ordinary function has exactly one ByteRegion parameter, first.
The remaining parameters are scalar/enum values, OwnedBytes or bounded move-only
classes; its result is scalar/enum, an existing bounded pointer-free copied class,
or one of those owning types. The existing
six-parameter limit still applies. The [owning-class extension](OWNING-CLASSES.md)
defines private direct fields, owning constructors and borrowed methods. Other
resource signatures do not support methods, overloads, templates, copied-class
parameters or spans. Owning parameters are deliberately mutable bindings, unlike the existing
readonly scalar/copied-class parameters. Source region identity cannot change.

Copied resource results require a named typed local initializer, for example
`Record record = produce(region);`. The destination is fresh, active and exactly
nominally typed; the ordinary copied-class size/leaf limits still apply. The
callee completes an independent local value, ends owner and view lifetimes, then
`ReturnObject` copies its scalar payload to caller result storage. A copied
result carries no region provenance or ownership token and remains usable after
the trusted caller closes the region. Direct resource-call return expressions,
resource copied parameters and general class-valued expressions remain unsupported.

`region.try_allocate(length)` requires an i64 byte count and initializes a typed
OwnedBytes local. Negative length, unrepresentable layout, quota exhaustion,
allocation-ID exhaustion and host allocation failure all produce the same inert
failure result. `.ok()` returns false and `.size()` returns zero. There is no
failure-cause enum, retry promise or silent fallback to another region.

Success initializes every payload byte to zero and `.size()` returns the requested
runtime count. Successful zero-length allocations have their own nonzero identity
and metadata allocation. They use zero payload quota, but metadata allocation can
still fail. `.ok()` distinguishes successful empty ownership from failure.

`.at(index)` returns a copied u8. A negative index, index at/above length, failed
owner or empty owner fail-stops before payload access. `.set(index, value)` requires
a mutable owner and u8 value; it returns bool. Invalid indices and failed/empty
owners return false without that operation writing payload bytes. Arguments are
evaluated left-to-right before the check; their already-completed side effects
are not rolled back. Receiver ownership is rechecked after argument evaluation.
For example, an index expression that moves the receiver is rejected.

Only `move(named_local)` transfers ownership, into another typed local, an owning
argument, or an owning return. A const owner may be read and dropped but cannot
be moved or written. Implicit copies, owner assignment, discarded owner results,
raw addresses, integer/capability conversions and borrowed payload views are absent.

## Failure-safe replacement resize

`owner.try_resize(length)` accepts exactly one i64 and returns bool. The receiver
must be a mutable initialized standalone owner or a direct private OwnedBytes field
of a live mutable owning class. Borrowed mutable methods may resize their own field;
no new region authority or payload view is exposed. Its length operand is evaluated
once before receiver ownership is rechecked. An expression that consumes the
receiver or its containing object is rejected; consuming another owner during length
evaluation is allowed.
Completed operand side effects are not rolled back when resizing returns false.

A canonical failed allocation returns false unchanged, even for length zero.
A valid live owner with unchanged length returns true without allocating/freeing,
changing identity or changing any metric, including after ID exhaustion. This fast
path remains inside the validating runtime helper: forged/stale descriptors always
fail-stop before the length request is considered. Const or consumed bindings are
rejected by source and typed-IR validation.

Every changed-size success builds a replacement allocation, preserves the first
`min(old_length, new_length)` bytes, initializes every new byte to zero, then commits
a fresh nonzero, never-reused allocation identity and releases the old block exactly
once. Shrinking discards the suffix permanently: a later regrow produces zeroes in
that extension. Shrinking to zero creates a successful empty owner with its own
metadata and identity. Local/function moves after resizing preserve the latest
identity. Normal cleanup still belongs to the original binding lifetime.

Negative length, unrepresentable header-plus-payload size, final logical quota
exhaustion, identity/counter exhaustion and host allocation failure return false
with the old descriptor, bytes and all committed accounting unchanged. Shrink and
zero requests may fail too: their replacement metadata needs a host allocation and
a new identity. No retry promise or allocation failure-cause enum is introduced.

The region quota charges final committed payload, checked as
`new_length <= quota - (used - old_length)`. This allows growth to the quota even
when old and replacement blocks coexist temporarily. At most one staging block is
allocated per call; transient payload is at most `used + new_length`, mathematically
at most twice the region quota. Metadata, allocator overhead and other host memory
are outside this bound. The logical quota therefore does not bound instantaneous
physical memory. There is no concurrent or reentrant use of the adapter.

Replacement staging is not a second live logical owner. Successful replacement
increments the successful-allocation and release observations, updates both last
IDs and committed used/peak-used payload, and leaves live/peak-live owner counts
unchanged. The old block is freed after the descriptor/registry commit. All fallible
work finishes before that nonthrowing commit; no C++ exception crosses generated
frames. Same-size and failed requests change none of these observations.

The `BytesResize` instruction consumes current i64 and returns bool, leaving saved
scalar operands and the unique logical verifier token intact. Runtime allocation
identity and verifier binding authority remain separate. The existing reserved
runtime symbol boundary and compiler-owned private linkage apply to the helper
`__au_runtime_bytes_resize`; source cannot call it directly or forge its descriptor.

## Normal lifetimes and control flow

Each local declaration or owning parameter has a binding lifetime separate from
its allocation identity. Moving preserves the identity and consumes the source.
An allocation failure remains an initialized owning result with normal cleanup
obligations. Moved bindings carry no resource authority.

Normal scope exit and return close bindings in reverse declaration order. A return
transfers only its explicitly moved result and closes every other owning binding,
including parameters. Cleanup preserves the pending scalar return and expression
stack. Loop-local allocations close on every completed iteration, allowing quota
reuse. Continuing if branches and short-circuit logical paths must agree exactly
on ownership state; conditional consumption is rejected. A returning branch does
not constrain a continuing sibling. Loop conditions cannot transfer outer owners,
even if the body always returns; read, set and resize operations remain allowed.

No arbitrary user destructor, exception unwinding, break/continue extension,
region reset/revocation or concurrent access is introduced.
Fail-stop traps do not run cleanup. Process/service reclamation of abandoned
resources remains a separate runtime boundary.

## Independent typed-IR boundary

Region spills reserve eight bytes; standalone owner spills reserve 32 bytes. Both
are non-scalar, disjoint from every scalar, class, array and span reservation.
The owning-class extension separately reserves opaque descriptors inside the
canonical class extent, with no overlapping standalone owner spills. Only
entry-prefix parameter binding can introduce region authority. Metadata describing
storage never grants an active lifetime or allocation capability.

Dedicated operations begin, allocate, resize, move, access, end, bind, call and return
owners. Validation tracks binding creation sites, pristine/live/consumed state,
internally minted ownership tokens and exact region origins. Moves preserve a
token and leave their source consumed. Allocation/call results require pristine
destinations. End closes one existing binding; it cannot revive a consumed token.
Complete resource states must match at control-flow joins and backedges. Repeating
a creation site in a loop is allowed only after its earlier token is gone.

Calls stage moved arguments at their left-to-right evaluation points, consume
distinct owners and tie returned ownership to the supplied region. Copied results
require pristine exact-nominal object storage disjoint from arguments; successful
return marks complete copied initialization without minting an owner token. Every normal
return must close or transfer all owner bindings. Scalar operations cannot access
capability words or forge IDs. The runtime helper symbol prefix is reserved even
for directly supplied IR; ordinary Call/AggregateCall cannot bypass ResourceCall.

## Hosted bootstrap boundary

The private descriptor is four eight-byte words: region ID, allocation ID, signed
byte length and canonical success flag. Failed descriptors contain the correct
region, zero allocation/length/success. Payload pointers live only in the trusted
adapter's registry. Runtime IDs and verifier identity tokens are different facts.

The single-thread adapter uses actual runtime `malloc`-compatible storage for a
header plus requested bytes, including replacement resize staging. It checks size
addition and quota subtraction before
allocation, initializes payload, then commits the registry, counters and ID. Each
region accounts payload bytes; host metadata/allocator overhead is outside that
quota. Failure preserves existing payloads, ownership and committed accounting.
Successful allocations and regions receive nonzero IDs that never wrap or reuse.

Adapter helpers are nonthrowing. They validate region, allocation identity and
canonical descriptor shape before access/release, and bounds before payload
access. Stale and cross-region descriptors fail closed, including pre-resize descriptors
whose old lengths later recur. Unique live ownership is
enforced by source/IR validation; the adapter does not defend against malicious
trusted host code cloning a currently valid descriptor. Its raw host pointers and
allocator callbacks are trusted bootstrap machinery, never an Aurora source API.

Test-only assembly bridges grant a region to private generated functions and
exercise scalar, owning and copied result storage under the documented private
ABI. Owner-returning calls are exercised while the
grant remains live. The bridge checks no allocation remains before teardown;
region close refuses while allocations remain. No general external owner ABI,
program startup, C compatibility or native kernel allocation is claimed.

Every Aurora function definition in a resource-bearing graph is local, including
scalar helpers. Thus a source helper named malloc, free, memcpy, memset or abort cannot
interpose the trusted adapter dependencies. This linkage rule is derived from
validated signatures and lifetime IR; no source/IR flag can disable it. The test
bridge uses the source/IR-reserved runtime prefix. Fixed generated reflection
helpers also have verifier-reserved names and cannot name allocator dependencies.

Scalar-only generated programs retain their old symbol visibility and gain no
runtime symbols. Resource programs link the explicit hosted adapter; those host
dependencies have not been removed.

## Focused acceptance plan

The existing test graph includes a source/native runner, independently authored
malformed-IR fixtures and an isolated hosted-adapter test. The native runner uses
runtime lengths including 0, 1, 65, 513 and 4097, real allocation counters, two live
owners, function/local moves, normal exit/return/branch/loop cleanup, quota and
injected host failures, and exact emitted bounds UD2 observations. Rejection tests
check existing-output preservation. Host tests cover ID/shape validation and quota
conservation; sanitizer execution is isolated to that trusted adapter.

The [dated results](../docs/owned-bytes-results.md) record the exact composite,
source corrections, original failed fixture and LeakSanitizer environment limit. Generated Aurora assembly is not sanitizer-instrumented.
These bounded tests do not establish general memory safety, Rust equivalence,
complete native runtime, performance, kernel integration or self-hosting.
