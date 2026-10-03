# Scalar-field values across function boundaries

This candidate extends ordinary functions with by-value class parameters/results.
It does not add aggregate references, ownership transfer, nested/resource fields,
class parameters/results on methods or constructors, general templates, or a stable
external ABI. The existing scalar entrypoint and method contracts remain unchanged.

```cpp
module example;
import std.numeric;
auto answer() -> i64 {
    const std::MinMax bounds = std::minmax(42, 0);
    return std::range_width(bounds);
}
```

## Source contract

A function may take and return a named class whose fields are all `i64`/`bool`.
Each boundary class may contain at most 64 scalar fields; the total parameter
count remains at most six. Larger classes are still permitted as local values
under the existing frame-size cap. Arrays, owners and references cannot cross
these boundaries. There are no implicit conversions between nominal classes,
including classes with identical fields or spellings from different modules.

Parameters are immutable independent values, as with existing scalar parameters.
Their fields cannot be assigned and they permit only const methods. A callee can
make a separate mutable local copy. Returning a complete local or parameter copies
its scalar state; it neither re-runs its constructor nor transfers a reference.
A checked trap is fail-stop and does not publish a partially produced result.

The intentionally small expression grammar requires:

- A class argument is a complete local name.
- A class-returning function call occurs in a typed local initializer.
- A class return expression is a complete local name.

For example, `const Box result = make(); return result;` is accepted, whereas
`return make();`, `consume(make());`, and `return Box(42);` remain unsupported.
They need additional expression/lifetime lowering before being admitted.

Arguments evaluate left-to-right. Each class is copied at its position, before
later argument side effects. In `f(object, object.add(1))`, the first argument
contains the pre-add value. Repeated use of one source object creates distinct
snapshots. The new result binding enters scope after argument evaluation, so
`Box box = copy(box);` inside an inner scope can read the outer binding.

## Modules, encapsulation and reflection

Every signature type resolves in its defining module. Exported functions cannot
expose private nominal types. Each caller must directly see every class in the
signature; importing a factory does not implicitly reexport types from its own
imports. Import the exported type's module explicitly when necessary.

Public factories may return exported classes with private fields. Field/method
access still requires normal class visibility and const permission. Copying a
complete value grants no private field access. Runtime metadata retains the
callee's defining-module view; carrying a value does not widen that view or expose
its fields to reflective access.

## Typed lowering and native call record

`BindObjectParameter` copies an incoming complete value into a fresh readonly
local object lifetime. It occupies the ordinary parameter-entry prefix;
`BeginObject` must not precede it. Scalar parameters retain explicit binding
operations, with the ABI selected by the complete function signature.

`AggregateCall` refers to one distinct, readonly, initialized snapshot object
per class argument and the scalar argument values on the operand stack. A class
result uses a separate active, pristine object slot. The verifier checks exact
nominal types, layouts, lifetime, initialization and disjoint argument/result
storage. Successful return establishes result initialization. `ReturnObject`
requires a complete active local matching the result type and a balanced scalar
operand stack. Scalar call/return operations cannot stand in for value-boundary
operations, and receiver-method calls retain their own separate contract.

The backend marshals copied fields into a bounded private call record. Hidden
record/result addresses are kept outside source-addressable slots and scalar IR
values. Aggregate-signature entrypoints are native-mangled local symbols. There
is no scalar-number-to-capability conversion or foreign-call surface. Callees
copy parameters into their own frames; no mutable alias into caller storage is
retained or returned.

Empty classes retain the existing vacuous complete-field convention. Result
initialization still has a completion marker so a second result/constructor
initialization cannot be hidden by an empty field list.

The compiler's frame, field and argument limits bound these individual layouts,
not whole-program stack use, recursion, total compiler work, or retained
control-flow facts. Existing receiver-cycle restrictions include aggregate calls;
pure ordinary-function recursion remains possible.

## Executable library scope and evidence

`std.numeric` now adds `std::minmax(i64, i64)` returning a scalar-specialized
`std::MinMax`, and `std::range_width(MinMax)` consuming an independent copy.
MinMax's constructor orders its private endpoints using the existing scalar
`std::min`/`std::max`; readonly min()/max() expose values. Width uses checked signed
subtraction and traps when the mathematical difference does not fit i64.
This is a small Aurora API, not generic C++ std::pair compatibility or a complete
numeric library.

`tests/compiler/value_calls.py` exercises native execution, snapshot timing,
copy independence, modules/privacy, lifetime loops, limits and exact SIGILL
failures. Direct IR tests target malformed capabilities, signatures and returns.
The ordinary scalar oracle and baseline differential tests remain separate.
No equivalent-semantics performance comparison is claimed yet: this bootstrap
copies each field at staging, parameter binding and result return, and has no
copy-elision optimizer.

During integration, an interrupted partial build contained new IR variants but
not their backend cases; its first value-return execution failed. The final
candidate must use exhaustive compile-time instruction dispatch in both the
verifier and emitter so future additions cannot silently emit successful partial
artifacts. This was an incomplete development state, not a published release.
