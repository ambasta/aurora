# Explicit scalar-constrained class templates

The current candidate adds reusable class-value definitions with one or two
explicit type parameters, each constrained by the builtin `Scalar` domain.
Scalar means exactly i64, u64 or bool. It is not a user-defined concept, wildcard,
unchecked top type or permission to treat a scalar as a capability.

```text
export module std.utility;
export namespace std {
    template <Scalar T, Scalar U>
    class pair {
    public:
        T first;
        U second;
        pair(T first_value, U second_value)
            : first(first_value), second(second_value) {}
    };
}
```

A client imports `std.utility` through the explicit library module root:

```text
module application;
import std.utility;

auto copy(std::pair<i64, u64> input) -> std::pair<i64, u64> {
    return input;
}

auto answer() -> i64 {
    const std::pair<i64, u64> original = std::pair<i64, u64>(-1, 42u64);
    std::pair<i64, u64> result = copy(original);
    result.first = 0;
    return i64(result.second);
}
```

This is an actual freestanding Aurora template definition compiled into concrete
native class code. No host C++ template, foreign pair layout, heap allocation or
runtime type-erasure machinery implements its behavior.

## Deliberately bounded language

Type parameters may occupy scalar field, constructor/method parameter, method
result and local declaration positions, and reflected type operands. Concrete
specializations may occur in ordinary function parameters/results, local bindings,
construction and reflection. Instantiation substitutes types before ordinary
semantic/lifetime checking. Operators are checked for the resulting scalar type;
for example, a dependent addition method may instantiate for i64/u64 and fail for
bool. There is no implicit conversion to make an invalid specialization work.

Arguments are explicit `i64`, `u64` or `bool` spellings. Missing/wrong-arity
arguments, class/array/owner/reference arguments, partial/explicit specialization,
function templates and deduction are rejected. A template definition cannot name
an explicit template-id, including itself; recursive/nested instantiation and
nested template arguments are not available. Plain injected self-class names
inside an instantiated class refer to that same concrete class under ordinary
class rules. This does not authorize a constructor/method call cycle.

Dependent scalar conversion syntax such as `T(value)` is not supported.
Type parameters cannot be embedded in array/ownership/reference type constructors;
those require the previously supported concrete element spellings. General
concepts, constraints, variadic templates, default type arguments, compile-time
values and template-driven code generation remain deferred. The parser accepts
only `template <Scalar T>` or the corresponding two-parameter form.

Syntactic and expansion-shape restrictions are checked when a definition loads.
Body name binding and type-dependent semantics are checked for each requested
specialization, including all of its methods, not universally for every possible
argument tuple. An unrequested specialization
is not emitted or claimed valid. Definition bytes alone do not create runtime
metadata for every possible specialization.

## Nominal identity and visibility

A specialization's identity includes its defining module, template declaration
and ordered scalar argument tuple. `pair<i64,u64>` and `pair<u64,i64>` are distinct,
even when physical sizes match. Different templates/modules are also distinct,
even if every instantiated field is identical. Copies and function calls require
exact nominal types; layout equality does not permit conversion.

Repeated references to one defining declaration and argument tuple share one
concrete class and method set within the compilation graph. Native symbols encode
that identity. Source spelling is never repurposed as an unchecked assembler
symbol. Importing aliases through different direct paths does not manufacture a
new type or reexport a hidden one.

Templates obey the existing module export, direct-import and namespace lookup
rules. Instance bodies resolve helpers in the defining module and lexical scope.
A caller's similarly named helper cannot replace that binding. Private templates
cannot be named by external clients; exported ordinary function signatures cannot
expose private specialization types. Specializations inherit template visibility
for defining-module reflection views. An API author can intentionally reveal its
own private metadata, as with ordinary classes; privacy is lexical authority,
not secrecy against the author of an exported API.

Class IDs remain deterministic for repeated compilation of the same source graph,
and graph-local rather than stable serialized identifiers. Metadata reports the
concrete padded layout and public field count. Reordering or changing the graph
may change IDs. Runtime metadata does not instantiate new types.

## Expansion and verified lowering

The module resolver registers definitions, collects concrete requests without
mutating the traversed class vectors, then appends deduplicated concrete classes
to their defining units. Each specialization receives an independent deep AST copy;
substituting one cannot mutate another. Type parameters and unresolved argument
vectors must disappear before the ordinary semantic/IR boundary.

The existing concrete class path checks complete construction, private members,
const receivers, lexical object lifetimes, independent copies, call-cycle
restrictions and scalar-field function boundaries. Explicit templates do not
relax any of those checks. The native backend gains no unchecked generic operation:
it receives the same nominal class layouts and receiver/value-call capabilities
as before. Direct IR rejection tests cover unexpanded parameter/argument metadata
and same-layout cross-specialization argument, result and receiver forgery.

Each graph permits at most 64 class template declarations and 256 distinct
requested specializations. Repeated identical requests do not consume additional
specializations. Existing source-byte/depth/frame limits, 64-field value-boundary
and six-parameter limits still apply. These bounds prevent recursive expansion
and unbounded specialization counts within this subset; they are not a global
compiler memory/work or target-stack guarantee. Compact verifier facts and
compiler-wide resource budgets remain separate hardening work.

## Library usefulness and evidence limits

`std::pair<T,U>` provides initialized public `first`/`second` values through its
complete constructor. Const pairs are immutable; mutable pairs permit field writes
of the exact field type. Copies and ordinary function arguments/results are
independent values. All nine scalar combinations are meaningful concrete APIs.
There is no comparison overload, deduction guide, make_pair helper, tuple protocol,
reference pair, nested pair or general standard-library compatibility claim.

Acceptance requires native execution across scalar tuples and ordinary class
boundaries, wrong-type/privacy/initialization rejection, defining-module helper
checks, reflection identity/layout consistency, cap boundaries, malformed IR,
existing regression/oracle suites and sanitizer runs. Independent review and final
integration must identify the new source hash. Archived milestone008 evidence
remains historical and does not validate this new template implementation.
