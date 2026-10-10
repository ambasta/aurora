# Bounded owning classes

The [readonly owned-view extension](READONLY-OWNED-SPANS.md) now adds runtime
owner origins and narrow const receiver-field results using the same span type.
Historical qualification and representation details on this page describe their
original checkpoints; the extension's source/ABI contract and fresh results are
separate. Existing array-only temporary-chain restrictions remain unchanged.

This candidate extends the [owned-byte contract](OWNED-BYTES.md) to direct private
class fields. Independent review and the [focused checks](../docs/owning-classes-results.md)
passed. It is not a general resource-class, user-destructor, borrowed-view or
kernel-allocation implementation.

## Source and ownership

```cpp
class Device {
    builtin::OwnedBytes payload;
public:
    Device(builtin::ByteRegion region, builtin::OwnedBytes initial)
        : payload(move(initial)) {}

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
parameters may be scalar/enum, OwnedBytes or copyable class snapshots. Each byte
field requires explicit move(named_parameter) initialization, in declaration
order. Copyable child fields use their existing named snapshot initialization.
Constructor bodies stay empty and every field must be initialized exactly once.
Unneeded owning parameters are closed normally. A failed byte allocation is an
initialized inert owner, not an incomplete constructor result.

Whole-class transfer requires move(named_local), into a fresh typed local, an
ordinary owning parameter or an owning return. Owning ordinary functions require
one first ByteRegion and otherwise accept scalar/enum, OwnedBytes or owning class
parameters; their result is scalar/enum, OwnedBytes, an owning class or an
existing bounded copied class. [Copied resource results](OWNED-BYTES.md#source-contract)
use named typed initializers and retain independent storage after owner cleanup. All moved
fields must belong to the supplied region. Owning parameters are mutable. Const
owners may be read and dropped, but cannot be moved or written.

Methods borrow the receiver synchronously. Existing scalar/enum and copied-class
parameters/results remain supported. Nonconstructor methods additionally accept
[readonly span parameters](METHOD-SPANS.md); mutable receiver calls require a root
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

## Normal cleanup and control flow

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

## Representation and independent IR

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

## Focused acceptance

Source/native cases cover runtime capacity, inert failure, resource-only layout,
constructor/local/function moves, const reads, reverse cleanup, branch/loop quota
reuse, mixed scalar/owner arguments, copied constructor/method boundaries, receiver
consumption, exact bounds traps and output-preserving rejection. Independent
malformed-IR and handwritten ABI cases cover descriptor extents, copy bypasses,
provenance, partial construction, call records and lifetime/cleanup enforcement.
Existing byte-owner, class/value, method, field-mutation and storage consumers are
required focused regressions. These checks do not claim a full native aggregate,
new sanitizer or guest qualification, performance equivalence or a safety proof.
