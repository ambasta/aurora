# Hosted runtime-sized byte ownership candidate

This checkpoint adds one allocation/lifetime prerequisite. Independent source
review and the [focused native composite](../docs/owned-bytes-results.md) passed. It does not replace the fixed-record BinaryBuffer64 or
Sector512 APIs, and is not a growable collection or a kernel physical allocator.

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
classes; its result is scalar/enum or one of those owning types. The existing
six-parameter limit still applies. The [owning-class extension](OWNING-CLASSES.md)
defines private direct fields, owning constructors and borrowed methods. Other
resource signatures do not support methods, overloads, templates, copied classes
or spans. Owning parameters are deliberately mutable bindings, unlike the existing
readonly scalar/copied-class parameters. Source region identity cannot change.

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
even if the body always returns; content-only read/set operations remain allowed.

No arbitrary user destructor, exception unwinding, break/continue extension,
allocation resize, region reset/revocation or concurrent access is introduced.
Fail-stop traps do not run cleanup. Process/service reclamation of abandoned
resources remains a separate runtime boundary.

## Independent typed-IR boundary

Region spills reserve eight bytes; standalone owner spills reserve 32 bytes. Both
are non-scalar, disjoint from every scalar, class, array and span reservation.
The owning-class extension separately reserves opaque descriptors inside the
canonical class extent, with no overlapping standalone owner spills. Only
entry-prefix parameter binding can introduce region authority. Metadata describing
storage never grants an active lifetime or allocation capability.

Dedicated operations begin, allocate, move, access, end, bind, call and return
owners. Validation tracks binding creation sites, pristine/live/consumed state,
internally minted ownership tokens and exact region origins. Moves preserve a
token and leave their source consumed. Allocation/call results require pristine
destinations. End closes one existing binding; it cannot revive a consumed token.
Complete resource states must match at control-flow joins and backedges. Repeating
a creation site in a loop is allowed only after its earlier token is gone.

Calls stage moved arguments at their left-to-right evaluation points, consume
distinct owners and tie returned ownership to the supplied region. Every normal
return must close or transfer all owner bindings. Scalar operations cannot access
capability words or forge IDs. The runtime helper symbol prefix is reserved even
for directly supplied IR; ordinary Call/AggregateCall cannot bypass ResourceCall.

## Hosted bootstrap boundary

The private descriptor is four eight-byte words: region ID, allocation ID, signed
byte length and canonical success flag. Failed descriptors contain the correct
region, zero allocation/length/success. Payload pointers live only in the trusted
adapter's registry. Runtime IDs and verifier identity tokens are different facts.

The single-thread adapter uses actual runtime `malloc`-compatible storage for a
header plus requested bytes. It checks size addition and quota subtraction before
allocation, initializes payload, then commits the registry, counters and ID. Each
region accounts payload bytes; host metadata/allocator overhead is outside that
quota. Failure preserves existing payloads, ownership and committed accounting.
Successful allocations and regions receive nonzero IDs that never wrap or reuse.

Adapter helpers are nonthrowing. They validate region, allocation identity and
canonical descriptor shape before access/release, and bounds before payload
access. Stale and cross-region descriptors fail closed. Unique live ownership is
enforced by source/IR validation; the adapter does not defend against malicious
trusted host code cloning a currently valid descriptor. Its raw host pointers and
allocator callbacks are trusted bootstrap machinery, never an Aurora source API.

The test-only assembly bridge grants a region to a private generated function and
returns only scalars. Owner-returning calls are exercised inside Aurora while the
grant remains live. The bridge checks no allocation remains before teardown;
region close refuses while allocations remain. No general external owner ABI,
program startup, C compatibility or native kernel allocation is claimed.

Every Aurora function definition in a resource-bearing graph is local, including
scalar helpers. Thus a source helper named malloc, free, memset or abort cannot
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
