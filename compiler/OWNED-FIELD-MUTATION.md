# Direct owned class-field mutation

Status: the [focused native checks](../docs/owned-field-mutation-results.md)
passed, and independent source, machine-code and final claim review accepted
this bounded scope. This increment does not qualify a complete compiler or kernel.

## Next dependency and acceptance

Owned library wrappers currently reconstruct private scalar arrays to update a
nested class value. The next dependency is synchronous access to one owned
class field without exposing a reference, pointer or new lifetime. Acceptance
requires the source, malformed-IR and handwritten-boundary tests below, existing
composition/method/sector/stack-probe regression checks, and independent review.
Storage API consolidation remains a separate design decision.

## Supported subset

A mutable named class local may replace one direct class-valued field from a
complete same-nominal-type named local, including a readonly copied parameter:

```cpp
holder.payload = replacement;
```

Within a mutable method, the same operation can target an unqualified private
class field. It copies the complete value, preserving source independence,
root lifetime and neighboring storage. It does not call the child constructor.
The source expression is a name with no side effects, so no staging allocation
is needed. A constant root, a readonly parameter or a const receiver cannot
supply mutable authority. Existing visibility checks still apply.

Const or mutable methods can receive that same direct owned field:

```cpp
holder.payload.write_byte(511, 42u8);
const ByteResult result = payload.read_byte(511);
```

The caller resolves the root and logical field identity, evaluates arguments
left-to-right with independent readonly class snapshots, then obtains the
synchronous child receiver. A later scalar argument may mutate or replace the
field; the call receives the value then present at that same field location.
Passing the containing object as a class argument copies it before later side
effects. A result uses a separate fresh local, even when the new binding shadows
the receiver's local name. Existing no-receiver-call-cycle rules remain.

The child may itself own further bounded values, but one expression cannot walk
multiple fields. Temporary receivers, `a.b.c.method()`, chained scalar access or
mutation, whole-class local reassignment, array replacement, direct projection
arguments and direct class-call replacement expressions remain unsupported.
Copy a result into a typed local before replacing a field with it. No new
`this` syntax, mutable span, resource owner, heap or C compatibility is added.

## Independent IR boundary

`AssignObjectField` names a root object slot (zero denotes the bound receiver),
a logical direct class-field index and a distinct complete source object slot.
It requires an already complete mutable root and exact nominal source type.
It cannot initialize an incomplete field or mint logical completion evidence.

`MethodCall.receiverFieldIndex` defaults to -1 for existing whole-root calls.
A nonnegative index selects one declared direct class field. The verifier
independently checks active complete root lifetime, root mutability where needed,
logical class-field shape, exact receiver nominal type and disjoint argument and
result storage. Other negative selectors, interior object offsets, scalar/array
selectors, constructor targets and constructor-time field access are rejected.
Source privacy remains the frontend's responsibility.

An empty child requires the same logical completion evidence despite containing
no scalar payload. It can share a canonical byte position with a sibling or
padding without creating independently addressable object storage. No operation
exports its hidden capability. Existing object-slot reservations prohibit a
forged standalone slot overlapping a parent.

The emitter uses only canonical class layout metadata validated from logical
shape. Assignment copies typed leaves; receiver selection adds the canonical
field byte offset to the existing hidden root address. Padding and sibling
payloads are not copied. The calling convention, registers, hidden-save slots,
frame limits and outgoing record reservations do not change. Existing per-page
stack probes remain on every allocation path. No copy-elision or performance
comparison is claimed.

## Focused checks and legacy transitions

- `tests/compiler/owned_mutation.py`: independent copies, private forwarding,
  packed bytes/bool/enums/u64, empty fields, all 512 bytes, actual Sector512 use,
  root snapshots, later field replacement, fresh-result shadowing, readonly and
  privacy/nominal/temporary/deeper-path rejections, and exact bounds traps
- `tests/compiler/owned_mutation_ir.cpp`: accepted local/implicit modes and
  adversarial logical field selectors, lifetime/completion, empty evidence,
  aliases, canonical layout, constructor and scalar-store bypass attempts
- `tests/compiler/owned_mutation_abi.py`: literal offset/byte expectations and
  handwritten entry and exit sides for scalar, result-only and combined
  argument-record/result calls; checks neighbors, independent snapshots,
  untouched source bytes, result guards and stack alignment

Five old explicit rejections become positive coverage: direct const/mutable
child method calls and whole child replacement in `composed_values.py`, plus
nested generic child const calls and replacement in `nested_values.py`. Their
readonly, private, deeper scalar mutation, argument and other rejection cases
remain. A separate previous-output preservation fixture now uses a const root
so the newly supported replacement remains invalid and the output guard stays
covered. The method-value suite's separate reassignment rejection likewise uses
a const root, preserving both absent/existing-output checks. Historical
milestone evidence does not qualify this extension.
