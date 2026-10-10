# Encapsulated scalar classes

This extension adds constructors and statically dispatched methods to Aurora's
safe C++ subset. It does not add inheritance, virtual dispatch, overloads,
general generics, destructors or reference parameters. Later copied method
parameters/results follow [METHOD-VALUES.md](METHOD-VALUES.md).
Ordinary functions separately support bounded by-value classes under [VALUE-CALLS.md](VALUE-CALLS.md). Classes
remain inline values with scalar `i64`/`u64`/`bool` fields and independent copies.
The later [fixed-container extension](FIXED-CONTAINERS.md) also permits private
scalar-array fields with complete zero initialization, copied-class arrays with
explicit complete-value initialization, and checked receiver indexing;
logical field identity stays separate from flattened storage. Explicit class
templates are specified in [TEMPLATES.md](TEMPLATES.md).

```cpp
module example;
class Counter {
    i64 value;
    auto increment(i64 amount) -> i64 {
        value = value + amount;
        return value;
    }
public:
    Counter(i64 initial) : value(initial) {}
    auto get() const -> i64 { return value; }
    auto add(i64 amount) -> i64 { return increment(amount); }
};
auto answer() -> i64 {
    Counter counter = Counter(21);
    return counter.add(counter.get());
}
```

## Construction and visibility

- Access is private by default; `public:` and `private:` apply to fields,
  constructors and methods. Access from methods of the same nominal class is
  permitted. Namespace membership or importing a class does not grant private
  access. Reflection reports public field counts and never returns field access.
- A class can declare one constructor, named exactly as its class, with at most
  six scalar parameters. Its initializer list must name every field exactly once.
  Unknown, missing and repeated field initializers reject. The body must be empty.
- Arguments evaluate left-to-right. Initializer expressions evaluate in field
  declaration order, regardless of list spelling order. They can use scalar
  parameters and ordinary scalar functions. They cannot access the receiver,
  its fields or methods, even after some fields have been initialized.
- Only after every initializer completes is the local value available. A checked
  arithmetic/bounds trap terminates execution rather than exposing partial state.
- A declared constructor disables designated aggregate initialization, including
  for public fields. A class without a constructor retains the earlier designated
  initialization rules, requiring every field to be public and initialized.
- Complete values can be copied, including classes with private fields and a
  private constructor. Copying duplicates scalar state; it does not manufacture
  a state unavailable from an existing complete value. Const applies to a binding,
  so an independent copy of a const scalar-field value may be mutable.

## Receiver and calls

- Methods use `auto name(parameters) const -> Scalar` for readonly access and omit
  `const` for mutation. The original explicit parameters/results were scalar; subsequent copied class
  boundaries follow [METHOD-VALUES.md](METHOD-VALUES.md);
  at most six explicit parameters are supported. Method names cannot overload or
  collide with fields. A method must return on every continuing path.
- Source code has no `this` pointer, object-reference conversion, pointer arithmetic
  or receiver escape. An unqualified field name accesses the current receiver,
  unless a local/parameter shadows that name. Calling a shadowing local or field
  fails because scalar values are not callable.
- An external method receiver must be a live class local. Temporary receivers
  and method-value extraction are unsupported. Const locals permit only const
  methods. Const methods cannot write receiver fields or call mutable siblings.
- Receiver identity is determined first, then all scalar arguments evaluate
  left-to-right, and only then is the synchronous call's borrow acquired. Thus
  `counter.add(counter.get())` completes the readonly call before the mutable call.
  Earlier argument results remain snapshots if a later argument changes the object.
- Unqualified sibling calls bind to the declaring class. They synchronously
  reborrow its receiver: readonly to readonly, exclusive to readonly/exclusive.
  Original authority is suspended during that call and resumes on normal return.
  No scalar argument/result can carry receiver authority, and no receiver can be
  stored beyond the call. Checked faults are fail-stop, with no exception unwinding.
- A call-graph cycle containing any constructor or method is rejected, including
  cycles through scalar helper functions. Pure scalar recursion is still accepted.
  This restriction does not prove whole-program termination or bounded stack use.
- Public constructors/methods of a directly imported exported class are usable;
  their bodies retain defining-module/class resolution and reflection views.
  Private sibling functions cannot be hijacked by root or namespace functions.

## Lowering boundary

IR has nominal scalar class layouts, local object-slot declarations, lexical
`BeginObject`/`EndObject` lifetimes, and a separate receiver signature. Receiver
load/store operations identify a field in that signature. A combined method-call
operation selects an initialized local object or forwards the caller's bound
receiver with checked permission. It cannot target an ordinary scalar function;
ordinary scalar calls cannot target a receiver entrypoint.

The receiver is never a scalar operand-stack value, ordinary slot or reflection
result. The backend transports it in a private hidden register and saves it in a
separate frame region, not an advertised source-addressable slot. Internal method
entrypoints use native mangled local symbols; the scalar bootstrap seam is unchanged.

The verifier checks layout, lifetime, initialization, receiver type/permissions,
call shape and constructor completion. Lexical private visibility and source name
resolution remain responsibilities of the trusted semantic frontend. Passing
these tests is not a proof of general Rust-like lifetimes or full language safety.

## Bounded composed values in development

[COMPOSED-VALUES.md](COMPOSED-VALUES.md) extends complete constructors with readonly
by-value class parameters and exact nominal class-field copies. Composed classes
are acyclic, at most four class levels and 64 scalar leaves. Public class fields
(and private fields inside their declaring class) project into fresh independent
locals. The [direct owned-field extension](OWNED-FIELD-MUTATION.md) admits
complete direct class-field replacement and synchronous child method receivers;
deeper chained mutation remains rejected. Empty
nested fields require logical initialization even without payload leaves. Ordinary method copied class boundaries are specified separately in
[METHOD-VALUES.md](METHOD-VALUES.md).

Milestone012's [enum/result candidate](ENUM-RESULTS.md) admits closed enum leaves
and copied class-valued method results, including the composed descendants above.
The later [verified M022 method-value contract](METHOD-VALUES.md) admits copied class-valued
ordinary method arguments and preserves complete constructor snapshots.
