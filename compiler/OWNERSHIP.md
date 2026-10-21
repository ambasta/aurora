# Owners, readonly views and synchronous loans

Authority is explicit, checked by the semantic frontend and independently validated typed IR. Lifetimes are lexical and calls synchronous. No general references, mutable spans, asynchronous escaped loans or exception unwinding are supported. Every live descendant view, including an empty one, retains root authority. Fail-stop faults require reclamation outside ordinary scope cleanup.

Current spans use the 56-byte tagged array/owner representation documented below. Runtime owner lengths are not limited to the fixed-array 4096-byte cap. Nonconstructor methods accept readonly span arguments, and returned views use only the narrow const receiver-field rules below.

## Runtime-sized byte ownership

### Source contract

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
six-parameter limit still applies. The [owning-class extension](OWNERSHIP.md)
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
raw addresses and integer/capability conversions are absent; readonly views use the checked operations below.

### Failure-safe replacement resize

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

### Normal lifetimes and control flow

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

### Independent typed-IR boundary

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

### Hosted bootstrap boundary

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
whose old lengths later recur. A successful lookup moves its allocation to the front
of the region's list, so the few hot owners are found first; membership and every
check are unchanged. Unique live ownership is
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

## Runtime-sized copied-class ownership

`builtin::OwnedValues<Node>` owns a runtime count of one named concrete,
non-owning copied class. `Node` must satisfy the existing canonical copied-class
leaf, containment and 520-byte limits. Each element has complete independent
storage. Resource classes, capabilities, references, class-array carriers,
scalar elements and dependent/generic owner types are not admitted. This does
not add generic resource classes, nested owning fields or mutable views.

```cpp
Node fill = Node(...);
builtin::OwnedValues<Node> nodes = region.try_allocate(count, fill);
if (!nodes.ok()) { return -1; }
Node copied = nodes.at(index);
bool written = nodes.set(index, copied);
bool resized = nodes.try_resize(new_count, fill);
```

The allocator and resize require an explicit complete, same-nominal-type named
fill value. Count and index are signed i64. `.size()` returns element count,
including zero on allocation failure; `.ok()` distinguishes success with zero
capacity. Every slot is initialized, including spare capacity. `.at()` returns
one copied value into a fresh explicitly typed local or direct copied return,
and fail-stops on negative,
out-of-range, failed or empty access. `.set()` requires a mutable owner and an
exact nominal copied value; invalid bounds return false without writing.

Operands are evaluated left-to-right. Count/index evaluation completes before
the named fill/value is copied into an independent readonly snapshot; owner and
containing-object liveness are rechecked before access. Scalar side effects
already completed are not rolled back. Fill expressions cannot manufacture
resource authority, and equal-layout classes are not interchangeable.

Resize preserves the complete retained prefix and explicitly fills new elements.
Shrinking then growing never resurrects discarded values. Same-count success
preserves identity, contents and accounting, even when a different fill is given.
A failed owner stays failed. Invalid count, count/stride overflow, quota/resource
exhaustion or host allocation failure leaves the old owner and committed state
unchanged. Existing byte-region final-logical-quota and transient replacement
bounds apply to payload bytes. Kernel page hygiene failures remain terminal and
retain authority for reclamation rather than reporting recoverable failure.

Owners move, bind, return and drop through the existing resource operations and
region provenance rules. A direct private typed-owner field makes a concrete
class move-only, just as a byte-owner field does. Its constructor explicitly
moves a matching owner; synchronous methods may read, set and resize the field.
No typed-owner byte borrow, raw byte mutation, reinterpretation, escaping element
reference or owner copy exists.

The compiler reuses the canonical copied layout, including its initialized
padding, and uses `classStorage.sizeBytes` as the positive element stride. Empty
classes therefore use eight bytes per element, preserving count and identity.
The private descriptor remains 32 bytes with a byte length; runtime helpers
check signed multiplication before allocation and descriptor divisibility before
typed payload access. Hosted storage is contiguous; the kernel adapter traverses
page boundaries without exporting addresses. Both share existing allocation,
replacement, cleanup, identity and accounting mechanisms.

Typed IR records exact nominal element types on an independently checked subset
of owner slots and on declared fields. Every move, parameter, call/result,
constructor field initialization and return checks that type. Typed payload
instructions derive their layout from validated class metadata; no instruction
supplies an arbitrary stride, pointer or reinterpretation. Old byte allocation,
access, resize and span instructions reject typed owners. Copied reads require
fresh exact destinations and establish complete logical initialization, including
empty descendants. Empty copied values require explicit complete-value evidence,
not merely a begun storage reservation, even through copies and control-flow joins.

`compiler/syntax_arena.au` is the concrete bootstrap consumer. Its private
owners and logical counts store copied `AstNode`, `ParseFrame` and `ChildEdge`
records beyond the fixed 64-element
and 520-byte aggregate limits. Appends check local child-before-parent indices
and the existing 128-node expression depth bound before growth; successful set
precedes count publication. Reads check logical count, and growth is explicit
Aurora code, with distinct invalid/depth/allocation outcomes. The second direct
owner stores an explicit parser stack; the third stores reverse-linked argument
edges with checked count/depth summaries, without nesting owning classes or
adding borrow rules. Argument arity grows with checked input/resource limits.
Nodes retain original-token indices, qualified-name endpoints and closing
delimiters; the hosted expression adapter recovers existing spelling/spans
without a second decoder. A synchronous mutable
`AstArena&` helper builds the graph, const helpers return copied observations, and
an owning helper consumes the arena before its host region closes. The host
reserves opaque arena storage and never fabricates an owner or payload pointer.
See the [parser boundary](ARCHITECTURE.md#hosted-aurora-expression-parser).

## Move-only classes

### Source and ownership

```cpp
class Device {
    builtin::OwnedBytes payload;
public:
    Device(builtin::ByteRegion region, i64 length)
        : payload(region.try_allocate(length)) {}

    auto size() const -> i64 {
        return payload.size();
    }
};

auto pass(builtin::ByteRegion region, Device device) -> Device {
    return move(device);
}
```

A concrete class containing a private direct OwnedBytes field is inferred to be
move-only. No annotation can make it copyable. Scalar, enum, fixed scalar-array
and copyable nested fields retain their existing behavior. An owning class cannot
be nested in another class or supplied as a template argument. OwnedBytes arrays,
public byte-owner fields, ByteRegion fields and resource class templates reject.
Canonical owning-class storage, including descriptors, is bounded to 520 bytes;
existing copied-leaf limits remain.

An owning constructor requires exactly one ByteRegion parameter, first. Later
parameters may be scalar/enum, direct owners or copyable class snapshots. A private
OwnedBytes or OwnedValues field accepts move(named_parameter), region.try_allocate,
or an ordinary region-first function returning its exact owner type. Typed
allocation still requires a named copied fill. Each producer executes once in
field declaration order, using the constructor's first region; a hidden mutable
owner holds its result until field transfer consumes it. Copyable child fields
retain named snapshot initialization. Constructor bodies stay empty, every field
must initialize exactly once, and initializers cannot read the partial receiver.

Unneeded parameters and consumed temporary bindings close normally. A failed
allocation is an initialized inert owner: later initializers still run, and the
completed object retains successful siblings until reverse-order destruction.
Safety traps remain fail-stop without partial-construction exception unwinding.

Whole-class transfer requires move(named_local), into a fresh typed local, an
ordinary owning parameter or an owning return. Owning ordinary functions require
one first ByteRegion and otherwise accept scalar/enum, OwnedBytes or owning class
parameters; their result is scalar/enum, OwnedBytes, an owning class or an
existing bounded copied class. [Copied resource results](OWNERSHIP.md#source-contract)
use named typed initializers and retain independent storage after owner cleanup. All moved
fields must belong to the supplied region. Owning parameters are mutable. Const
owners may be read and dropped, but cannot be moved or written.

Methods borrow the receiver synchronously. Existing scalar/enum and copied-class
parameters/results remain supported. Nonconstructor methods additionally accept
[readonly span parameters](OWNERSHIP.md); mutable receiver calls require a root
disjoint from every live input view, including empty views. Methods can read payload.ok(), size() and
at(index); mutable methods can call payload.set(index, value) and
payload.try_resize(length). Resize preserves the field's ownership token and region,
with failure-safe replacement behavior from the owned-byte contract. Scalar arguments
are evaluated before checking that the resolved receiver and containing object
are still live. Consuming that root in a nested argument rejects. The borrowed
receiver does not grant new region authority or expose its descriptor. Resizing uses
the existing field's region. RamSectorDevice intentionally exposes no resize method;
its private backing preserves the whole-sector invariant.

No implicit owning copy, owner extraction, resource-field replacement, whole
owning reassignment, explicit owning method parameter/result, temporary receiver,
resource overload or template, payload view, pointer or new `this` syntax is added.
Existing copyable fields and Sector512/results still copy independently.

### Normal cleanup and control flow

One reverse-declaration-order cleanup walk closes standalone byte owners and
owning class locals/parameters. EndObject drops direct resource fields in reverse
field order, preserving pending scalar results and operand stacks. Moved and
pristine descriptors are inert. Returning an owning result transfers only that
result; every other owning binding must close. All continuing branches,
short-circuit paths and loop backedges require matching resource states. Loop
conditions cannot consume an outer owning class, even if the body always returns.

Partial field initialization has separate verifier state. Constructors cannot
return normally while incomplete. Fail-stop traps do not unwind constructors or
other scopes, matching the existing runtime boundary. No exceptions, arbitrary
destructors or rollback promise are introduced.

### Representation and independent IR

Each direct byte-owner field occupies the existing opaque four-word descriptor:
32 bytes, aligned to eight. Descriptor words are not scalar leaves or independent
byte spills. Canonical field offsets determine descriptor extents; metadata cannot
mint a lifetime, token or region. Resource-only classes are nonempty, and padding
clearing excludes every descriptor extent. Old copyable layouts stay unchanged.

The verifier derives owning status from canonical logical shape. CopyObject,
ObjectFieldCopy, InitializeObjectField, AssignObjectField, BindObjectParameter,
ReturnObject and copied call paths reject resource-bearing copies. MoveObject,
BindOwnedObjectParameter and ReturnOwnedObject transfer unique per-field tokens.
ResourceCall transports moved owners and may initialize a pristine exact-nominal
copied result without owner tokens; its constructor mode also accepts distinct
readonly copied-class snapshots. Constructor initialization consumes each source
once. Explicit byte access selectors name an exact root and logical direct field,
never an interior offset or exposed hidden address.

Tokens retain region provenance through local moves. Call results use internally
minted site/field identities. Ordinary receiver access carries only symbolic
borrowed provenance; it cannot allocate a separate owner, move a field, end the receiver or return
ownership. Every consumed-root access rejects, including scalar fields.

The private x86 convention keeps R11 as the resource argument-record address and
R10 as ordinary owning/copied result destination or constructor receiver. Methods retain
their existing copied-value conventions. Transfer clears source descriptors;
scalar payload moves never fabricate resource words. Resource-bearing shapes and
operations trigger the existing private graph linkage and runtime helper boundary.

## Readonly array views

### Source contract

A named local `builtin::array<u8,N>` (including its fixed `array` alias) may be
borrowed with `const builtin::span<const u8> bytes = borrow_bytes(storage);`.
Local builtin arrays retain their existing 1..4096 element limit. Private array fields and std::array wrappers retain their existing limits. The
implicit private fixed-u8 receiver-field case is separately specified below;
explicit copied-field expressions and array wrappers remain unsupported origins.

A span provides readonly `size() -> i64` and bounds-checked `at(i64) -> u8`.
Whole-array borrowing and checked named-span subspans, including zero-length windows, share the lifetime rules below.
A local span copy reborrows readonly storage instead of copying bytes. Its lifetime
is conservatively bounded by the source span binding's lexical scope, even when
an underlying owner might live longer. Local bindings must be const, initialized
and non-rebindable. Multiple readonly reborrows coexist.

While a span or any descendant reborrow is live, original-owner element mutation
is rejected. Owner reads and independent by-value array copies remain allowed.
After all corresponding borrows end, a mutable owner may be written again.
There is no runtime borrow counter or GC: the analyzer checks lexical borrow
state and IR validates explicit capability lifetimes before native emission.

Ordinary functions may receive `builtin::span<const u8>` parameters and forward
reborrows synchronously. A parameter's capability lasts only for its invocation.
Nonconstructor methods also accept synchronous parameters under the
[method-span contract](OWNERSHIP.md). Ordinary functions cannot return spans. Spans cannot be stored in classes or assigned into outer bindings,
passed as constructor parameters, used as template arguments,
reflected, compared, converted or treated as scalar values. No global storage,
mutable span, raw base address or arbitrary pointer/length constructor exists.
Private OwnedBytes fields and implicit private fixed-u8 receiver fields use
the bounded receiver rules below.

Arguments evaluate left-to-right. Acquiring a direct temporary borrow at an
argument position keeps it live through later argument evaluation and the complete
call. Callee forwarding cannot widen that authority. Current source syntax has
statement-only array assignment and no shared global/array-reference mutation
path, so a valid later argument cannot directly mutate that local owner. Direct
IR nevertheless rejects a write during that interval. A source assignment-expression
syntax rejection is not evidence that a lifetime checker analyzed such an expression.

Branches and loop backedges must preserve the same continuing borrow state.
Branch-local borrows end before joins; returning paths release invocation borrows
before return and do not constrain a continuing sibling. Scope exit releases
children before parents, then ends local array lifetimes. Unsupported escaping or
divergent states reject rather than extending a borrow by inference.

### Typed IR and private invocation representation

Local byte-array origins have explicit metadata and BeginArray/EndArray lifetimes.
BorrowSpan requires a fully initialized active array; ReborrowSpan requires an
active parent capability. The verifier preserves exact local-array or parameter
origin, static creation sites and direct-parent authority, and refuses to end a parent with live descendants or an
array with outstanding borrows. Writes to any borrowed owner byte reject.

SpanLength reveals only the length. SpanLoad combines signed-index bounds checking
and a typed byte load: negative/out-of-range indices fail at the existing bounds
UD2 before loading the base pointer or calculating the payload address. Span
capabilities never inhabit scalar value/operand slots. A declared spill alone
cannot manufacture a capability or establish initialized entry authority.

Every span has a 56-byte tagged capability reservation described below. Spill bytes are disjoint from scalar, object and other capability
storage. The signature still permits at most six source parameters; spans do not
expand into extra scalar argument registers. Scalar positions retain their existing
indexed registers before packing; class and span positions use explicit record
offsets. Complete mixed records are passed through the existing internal hidden
record convention. BindSpanParameter must appear in the canonical entry prefix
and match an exact span parameter/spill. No plain scalar Call/BindParameter can
substitute for this boundary. Class results retain separate complete result storage.

Span-bearing functions have native value-boundary names and local linkage. They
are unavailable through the global host/kernel scalar bootstrap entry seam. All
callers establishing span records belong to the validated Aurora module graph;
this is not a foreign-language ABI accepting externally supplied pointer pairs.
Reflection and value conversions cannot observe capability spill contents.

## Checked child windows

### Source semantics

    const builtin::span<const u8> region = bytes.subspan(offset, count);
    const std::ByteReadResult word = std::read_le32(bytes.subspan(offset, 4), 0);

The receiver must be a named live readonly byte span. Both arguments must be
exactly i64. Parent validation happens first, then offset and count evaluate
left-to-right exactly once. Both evaluations finish before window bounds checks;
an arithmetic failure in count precedes an invalid-offset bounds failure. Parent
borrow authority remains live throughout. Call argument evaluation remains
left-to-right, and a temporary child lives through later arguments and the call.

Required conditions are 0 <= offset <= parent.size() and
0 <= count <= parent.size() - offset. No offset+count arithmetic is used. Violations
trap at the existing named bounds UD2 before loading or adjusting the payload base
address. The new window reads exactly the selected bytes, with index zero relative
to its own start. The subtraction cannot overflow after the offset check because
the admitted offset and nonnegative parent length bound the subtraction.

Zero-length windows are valid, including at the parent endpoint. They retain
parent/root provenance; they provide no byte-access authority. Every at() on an
empty window traps before any payload load. There is no null pointer convention
or source-visible address, and an empty window cannot be widened.

### Lifetimes and restrictions

Each child is an immutable reborrow, conservatively bounded by its direct parent's
lexical scope, and transitively by the local-array or invocation root. A window
may itself be forwarded, copied as a readonly reborrow, or be a named receiver for
another window. Descendants must end before parents. All parent and root borrows
exclude owner mutation, including empty views, until their release. Branch and
loop joins retain exact static lifetime sites just as whole-span reborrows do.

Windows can be initialized only into const span locals or passed directly as
ordinary-function span arguments. They cannot be returned by ordinary functions or stored in class fields,
assigned into outer bindings, compared, reflected, converted, passed to constructors, or used as generic type arguments. Temporary-receiver chains
are intentionally rejected; name the intermediate view. No mutable authority,
raw pointer, heap, reference-return or C ABI is introduced.

The builtin operation is recognized only on actual span receivers. User-defined
class methods named subspan and ordinary overload sets keep their previous meaning.
Explicit single-span and multiple-span function signatures are unchanged.

### Typed IR and native implementation

Subspan{sourceOffset,resultOffset} requires an active exact typed source spill, a
fresh exact typed destination spill, current i64 count, and a saved i64 offset on
the scalar operand stack. It consumes the offset, preserves the scalar count but
clears its unrelated bounds evidence, and creates no scalar capability. The
result records the parent's exact root kind, root slot/site and direct parent
slot/site, plus its own creation site. No malformed source scalar, spill interior,
ended parent, overlapping reservation, return escape, borrowed-owner write or
incompatible control-flow lifetime is accepted.

Native emission uses unsigned comparisons to reject negative signed operands as
well as excessive positive values. The parent length is loaded first; offset is
checked against it, count against the remainder. Only then is the parent’s tagged array/owner record copied with checked logical
start/length into the disjoint capability spill. It uses the same private validated call records as whole spans.
No externally supplied pointer/length record can enter this language boundary.

## Runtime-owned views and receiver results

### Source and lifetime contract

`borrow_bytes(owner)` accepts a live named OwnedBytes or direct accessible private
OwnedBytes field, including the implicit receiver field. Copied array wrappers
and explicit copied fixed-array-field expressions are unsupported origins. Allocation identity is
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

### Narrow receiver-bound results

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
[method-span contract](OWNERSHIP.md). Class span fields, generic span type
arguments, reflected capabilities and asynchronous escape remain unsupported.

### Private fixed-byte receiver fields

Inside a const non-template method, `borrow_bytes(field)` also accepts an implicit
private fixed `u8` array field of that receiver. The method may return the view
or a checked child window. The result retains the exact named receiver creation
and binding lifetime plus field identity. A copied object has an independent
root, and sibling fields remain independent. Live views prevent root mutable
method calls, destruction and overlapping writes.

This permits `BinaryBuffer64.bytes(offset,count)` without staging an array copy.
It does not permit local-array returns, ordinary-function or parameter-derived
returns, temporary or nested receivers, mutable views, stored spans, or explicit
borrowing from copied-field expressions. Return paths must agree on one receiver
field; generic span escape and arbitrary reference-returning methods remain absent.

### Private representation and independent verification

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

A function's receiverSpanField summary names one exact direct OwnedBytes or
private fixed-u8 field under its admitted const receiver. Every reachable ReturnSpan independently verifies that
origin and rejects unrelated live resources. Appropriate receiver-derived views
end with invocation. MethodCall derives caller-side authority from its own actual
receiver token and requires a fresh result spill. Hidden-result calling modes
transport the entire record without owner transfer or cleanup.

## Borrowed owning-object helpers

An ordinary free helper accepts one leading named `T&` or `const T&` for an
already supported concrete owning class. Later parameters retain scalar/enum,
readonly-span and copied-class semantics; results are scalar/enum or copied
classes. No temporary/projected argument, reference local/
field/result, reference template/overload or ownership transfer is added.

A bounded multi-root form accepts a leading sequence of up to three borrowed
owning roots. A mutable prefix may contain zero, one or two roots; every
remaining root is readonly. Thus `(T&, U&)` and `(T&, U&, const V&)` are
supported, but readonly-then-mutable and three-mutable signatures are not.
Roots and trailing parameters together fit the existing six-parameter limit.
With two or more roots, trailing parameters and the result are scalar/enum values.
The single-root copied/span argument and copied-result rules above are unchanged.
This enables algorithms that update a workspace while reading independent owners,
including the verifier's instruction and metadata owners. Two mutable roots also
support independently updating two complete owners; this does not add compiler
adoption, a new bootstrap stage, nested owners or mixed builtin root signatures.

Every actual root is complete, named and pairwise distinct, even when all borrows
are readonly or the classes are empty. Different instances of the same class are
permitted. Distinctness means separate complete owner identities, not unequal
variable names, nominal types or physical regions. Forwarded formals inherit
separation from their checked caller. Each formal has its own loan and binding
identity. None of the formal roots may produce a span in the multi-root form; public scalar and copied-value
getters remain usable. Independent local spans are unaffected. No owning-reference
method parameters, reference locals or general lifetime syntax are added.

### Authority and argument evaluation

Each root argument names a complete owning root or the current named borrowed
formal. Its loan begins before any later argument is evaluated, and remains live
through the synchronous call. A mutable loan excludes every other access to its
root during argument evaluation. Precompute a size or other observation before
passing it as a later argument. Shared loans permit readonly aliasing but cannot
mutate, move or end their root. Distinct owners in the same region are disjoint;
empty or disjoint windows of one owner retain the same root identity.

Callees can invoke public methods and forward the named formal synchronously.
Nested mutable reborrows suspend the parent's independent access until release.
Const authority cannot be upgraded. Views produced by public const methods remain
tied to the borrowed root and must expire before mutation or function exit.
The formal grants no lexical private-field or private-method privilege.

A loan never transfers ownership, creates region authority or registers the formal
for cleanup. No extraction, reassignment, move, drop, field storage or borrowed
return is added. Local owners and copied argument snapshots retain existing
normal cleanup. Fail-stop faults do not unwind.

### Typed IR and machine boundary

`AcquireObjectLoan` and `ReleaseObjectLoan` are verifier-only operations with
positive loan identities, exact root/lifetime provenance, nominal class identity
and mutable/shared authority. A loan may authorize one `BorrowedCall`, then must
be released. It is not a scalar value or stack address. Active loans must match
at control-flow joins. No normal return may retain one.

The bound formal reuses receiver-like hidden storage, marked explicitly as a
borrowed free parameter. Direct receiver-field instructions are forbidden for
that mode. Method access uses actual visibility metadata. Only a verified public
span-returning method may derive the formal's internal owner-field provenance.

The existing private method ABI is reused: R10 holds the root; packed copied/span
arguments use R11; copied results use RAX with a packed record, or R11 without
one. Scalar arguments retain their existing registers. Hidden saves, stack
alignment/probes, 56-byte spans and 32-byte owned descriptors remain unchanged.
Source symbols cannot expose this as a scalar C-callable boundary. Existing
resource-graph checks and receiver call-cycle restrictions include borrowed calls.

For two or more roots, R10 points to an ordered private pointer tuple: root i is
at byte offset 8*i. The callee saves every root before nested calls; outgoing tuple
storage is aligned to sixteen bytes. Typed IR uses selectors 0 through -5 for
bound formals and positive exact owner slots for locals. Selectors are bounded
before negation and never interpreted as ordinary frame offsets. One ordered
root/loan/field range replaces separate first/second call lanes. Aurora static
admission checks pairwise root/loan distinctness and nominal receiver binding.
Native verification checks each admitted lane's live loan, authority and dynamic
root/lifetime provenance; it does not independently repeat those static checks.
The existing single-root direct-pointer, two-root sixteen-byte and three-root thirty-two-byte
tuple reservations are preserved. The existing i64 permission lane records the
mutable-prefix count (0, 1 or 2, never greater than the root count); source and
native readers reject invalid counts before granting mutable authority. It is
not a boolean, and the record layout is not widened. Borrowed entries remain
private: the trusted host must construct genuinely separate live complete
owners and payloads, not pass arbitrary raw tuples or rely on pointer inequality.

Canonical callable metadata stores every explicit formal in source order, with a
bounded borrowed-root prefix and a tail-only value-parameter view. Genuine method
receivers remain separate; derived receiver-like observations grant no private
access. Version-2 ABI facts describe ordered roots and distinguish tuple payload
from aligned reservation. The bootstrap reader narrowly normalizes the selected
version-1 predecessor facts and new facts for the unchanged frontend.

### Borrowed typed buffers

A single leading mutable `builtin::OwnedValues<T>&` may borrow a named owner or
an implicit private field of the mutable lexical receiver for a synchronous
free-function call. Explicit `object.member` arguments remain unsupported. The helper
may inspect, resize and store copied elements; it cannot move, destroy, return or
retain the owner. Results are scalar and remaining arguments are scalar or copied
values. Readonly builtin borrows, mixed roots and typed views remain unsupported.
A field loan excludes access to its entire containing object during argument
staging and the call. Compute receiver-derived tail arguments before lending it.
Allocation failure preserves the existing descriptor and contents; the caller
still owns cleanup. The private ABI passes the actual descriptor address in R10.

The formatter now uses this signature in one shared `append_row` helper for
pieces, tokens, findings, breakpoints and braces. Each caller snapshots its count
and prepares copied arguments before lending the private owner, then updates the
count after the loan ends. Growth limits and terminal allocation failure are
unchanged. The [source-bootstrap recipe](README.md#source-bootstrap) selects a
replacement sixth checkpoint with this capability and the native C++ emitter;
no seventh predecessor is introduced. Focused route/consumer convergence is not
final-source qualification: the integrated GCC 16 `full` and applicable
boot/emulator gates remain required, with exact receipts retained in the accompanying PR.

## Readonly method arguments

This extension adds nonconstructor methods with readonly byte-span parameters.
Fresh focused source/native, malformed-IR, handwritten-ABI and direct regression
results are recorded [separately](OWNERSHIP.md). Runtime layout
and helpers are unchanged. No new kernel capability or general object reference
is introduced.

Arguments evaluate left-to-right after resolving receiver identity. Each span
acquires authority at its evaluation position and retains it through the call.
After all arguments, the receiver must still be live and mutable calls require
an unborrowed root. Self-append rejects even for empty views and disjoint windows.
Readonly arguments may alias one another; const receivers may receive their own
views. Distinct buffers may share a region without aliasing their owners.

Callee parameters are invocation-only capabilities with exact parent provenance.
They can be read and synchronously forwarded but never stored in fields, rebound,
returned as argument-derived views or converted to ownership. Existing span
results remain tied exclusively to one verified direct receiver owner field.
Constructors, ordinary owning-function span signatures, mutable spans, owning
method parameters, nested owning fields and method overloads remain unsupported.

MethodCall records positional span spills independently from copied-object
snapshots. The verifier checks exact types, active roots and parents, vector
shape, zero entries at other positions, and final receiver authority. Every
span record remains 56 bytes. Packed methods use R10 for receiver and R11 for
arguments; class/span results additionally use RAX for their hidden destination.
These private entry points are never exported as scalar C-callable boundaries.
