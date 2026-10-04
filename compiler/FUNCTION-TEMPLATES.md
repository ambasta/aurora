# Bounded explicit by-value function templates (verified milestone021)

Milestone021 implements namespace-level function templates with one or two
`Scalar` or `Value` type parameters and explicit concrete call arguments.
Complete release/fatal host ASan/UBSan compiler gates, independent review/replay,
fresh parent aggregate and three existing UEFI integration profiles passed.
[Verification](../docs/verification.md) and [M021 evidence](../docs/evidence/milestone-021/README.md)
identify exact inputs, pins, corrected defects and limits. No new IR instruction,
runtime generic representation, calling convention, heap, reference/span API or
foreign ABI is introduced.

```cpp
template <Value T, Value U>
auto make_pair(T first, U second) -> pair<T,U> {
    const pair<T,U> result = pair<T,U>(first, second);
    return result;
}
```

`std::make_pair<i64,u8>(42,7u8)` returns an independent `std::pair<i64,u8>`.
Arguments use existing readonly scalar/enum/complete-class value boundaries;
class snapshots are evaluated left to right and the copied result initializes a
fresh typed local. Six source parameters and 64 scalar leaves at class-value
boundaries remain the limits. Class-valued arguments still require named complete
locals. `examples/function_token_values.au` executes a byte-array/source-range
factory, independent copies, fresh projections, mutation and zero-filled storage.

## Finite grammar and expansion

Types may be bare parameters or existing concrete types. In function template
signatures, local declarations, construction and compile-time reflection, a
statically named class template may use bare function parameters or fully concrete
M020 argument trees. Thus `pair<T,U>` and `pair<array<u8,16>,T>` are admitted, but
`pair<array<T,16>,U>` is rejected. Dependent qualified names and `T(value)` or
`T{...}` construction/conversion are rejected. Class-template bodies keep their
previous stricter contract.

Function-template calls inside *any* template body are rejected, including
concrete calls and bare calls without explicit arguments. Structural restrictions
are checked when definitions load even if never requested; ordinary
specialization validity is checked only for each requested specialization. This
includes class-specialization arity/constraints in signatures and unresolved
concrete names in bodies; an unused invalid tuple need not be rejected. Fixed
exported-signature visibility is checked eagerly as described below. This does not
claim universal validity for all unrequested argument tuples. Deduction,
overloads, partial/explicit specialization, defaults, variadics, generic methods,
function capacity parameters, user concepts, resource/reference/span/builtin-array
arguments and recursive generic expansion remain unavailable. Existing ordinary
runtime recursion restrictions and stack limitations remain unchanged.

Phases are finite: register immutable definitions; validate body shapes; collect
ordinary requests without mutating traversed vectors; intern class requests and
function clones; substitute exact argument identities into independently deep
copied function ASTs; collect and instantiate only the resulting class requests;
freeze instances; resolve layouts/signatures/bodies; use existing semantic/IR
verification and lowering. Generated functions cannot request more functions.

## Independent limits and identity

The whole graph permits 64 combined class/function template definitions and 256
combined distinct class/function specializations, including nested and factory
class requests. Repeated identical requests are interned. Identity includes the
defining declaration and ordered resolved nominal arguments; same physical layout
does not allow substitution. Generated function symbols are internally mangled,
including scalar specializations, and are not ordinary exported entrypoints.

Class-template nominal ancestry remains at most four levels, checked again after
substitution. The function-call argument list does not consume a class-template
level. Identity of a depth-four zero-storage `Tag` chain is allowed; wrapping it
in `pair<T,u8>` rejects depth five even if containment remains shallow. Independent
containment depth four, 64 leaves, array capacities 1..64, six source parameters,
65,536-byte function frames, source/module limits and checked arithmetic remain.
These are admission rules, not a global compiler-memory or target-stack proof.

## Scope and authority

Explicit arguments resolve in each caller's lexical/direct-import scope and are
checked with their public signature/type closure. Fixed names and helpers bind
in the defining module. A caller-private class may be supplied to a generic
factory, with exact nominal compile-time authority carried by the specialization.
This authority permits copied values and the required generated classes, not
private fields/constructors, arbitrary caller lookup or caller imports. Generated
functions are not exported ordinary APIs. Ordinary exported wrappers still cannot
leak private argument/result types, and every call checks signature visibility.

Compile-time reflection can name explicitly supplied types. Runtime reflection
keeps the defining module's unchanged visibility view; specialization does not
create access to unrelated caller types. Unresolved parameters and argument trees
must disappear before the existing concrete IR verifier.

## Acceptance and scope

Required gates are focused native/copy/order/enum/empty/privacy/nominal/depth/budget
cases, complete existing compiler regressions and numeric oracles, malformed IR
and exhaustive dispatch/native ABI controls, fatal ASan/UBSan host runs, frozen
M020 assembly/status differential and independent review of frozen implementation.
Changed formerly-unsupported-function negatives are identified, and repeated runs
are overlapping coverage. Emitted native code is not itself ASan instrumented.
Parent source adoption, fresh `make test` and `runtime-span`, `runtime-pin-fault`,
`normal` UEFI profiles passed on the reviewed release pin; normal restored.
M019's full 166-mode run remains historical. No physical hardware or equivalent-C
performance claim follows.
