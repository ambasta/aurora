# Bounded generics and fixed storage

Expansion is finite and explicit. These facilities do not provide type deduction, arbitrary metaprogramming, lifetime-generic containers or reference escape. Every generated body retains its defining module’s visibility and all normal source/IR safety checks.

## Class templates

### Deliberately bounded language

Type parameters may occupy scalar field, constructor/method parameter, method
result and local declaration positions, and reflected type operands. Concrete
specializations may occur in ordinary function parameters/results, local bindings,
construction and reflection. Instantiation substitutes types before ordinary
semantic/lifetime checking. Operators are checked for the resulting scalar type;
for example, a dependent addition method may instantiate for i64/u64 and fail for
bool. There is no implicit conversion to make an invalid specialization work.

Scalar arguments are explicit `i64`, `u64`, `u8` or `bool` spellings. Missing/wrong-arity
arguments, non-scalar arguments to Scalar parameters, builtin array/owner/reference
arguments to Value parameters, partial/explicit specialization,
deduction are rejected. Namespace-level function templates have the separate bounded
function-template rules in [GENERICS.md](GENERICS.md). A class
template definition cannot name
an explicit user-template specialization, including itself. Fully concrete source
argument trees may contain up to four template-id levels; inner instances are
resolved first. Dependent body expansion and recursive instantiation remain unavailable. Plain injected self-class names
inside an instantiated class refer to that same concrete class under ordinary
class rules. This does not authorize a constructor/method call cycle.

Dependent scalar conversion syntax such as `T(value)` is not supported.
Type parameters may now appear in builtin array storage under the separate
[fixed-container contract](GENERICS.md); ownership/reference constructors
still require their supported concrete i64 spelling. General
concepts, constraints, variadic templates, default type arguments, general compile-time
values and template-driven code generation remain deferred. The parser accepts
`template <Scalar T>`, the corresponding two-Scalar form, or the explicitly bounded
`template <Scalar T, i64 N>` capacity form specified in GENERICS.md.

Syntactic and expansion-shape restrictions are checked when a definition loads.
Body name binding and type-dependent semantics are checked for each requested
specialization, including all of its methods, not universally for every possible
argument tuple. An unrequested specialization
is not emitted or claimed valid. Definition bytes alone do not create runtime
metadata for every possible specialization.

### Nominal identity and visibility

A specialization's identity includes its defining module, template declaration
and ordered resolved argument tuple, including exact inner nominal identities. `pair<i64,u64>` and `pair<u64,i64>` are distinct,
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

### Expansion and verified lowering

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

Each graph permits at most 64 combined class/function template declarations and 256 distinct
requested specializations, counting every inner instance. Repeated identical requests do not consume additional
specializations. Existing source-byte/depth/frame limits, 64-scalar-leaf value-boundary
and six-parameter limits still apply. These bounds prevent recursive expansion
and unbounded specialization counts within this subset; they are not a global
compiler memory/work or target-stack guarantee. Compact verifier facts and
compiler-wide resource budgets remain separate hardening work.

## Concrete nested specializations

### Concrete surface

Value-constrained template arguments may now be fully concrete template-ids:

```cpp
std::pair<std::array<u8,16>, SourceRange>
std::pair<Status, std::pair<i64,u64>>
```

These types are usable in ordinary typed locals, complete constructors, function
parameters/results, ordinary class fields/constructor signatures, copied method
results, and compile-time/runtime reflection. An executable bounded token-byte
and source-range example is in `examples/nested_token_values.au`.

Every existing class rule still applies: class-valued constructor arguments and
results require complete named local values, public class-field projections
produce independent fresh-local copies, and the [direct owned-field extension](VALUES.md) permits complete
direct class-field replacement and synchronous child method receivers. Deeper
chained receivers remain unsupported. Array storage remains private;
`size()`, checked copied `at()`, and mutable `set()` retain their original APIs.

### Independent bounds

- A source argument tree has at most four template-id levels, counting its root.
  `Box<Box<Box<Box<i64>>>>` is exactly four. This cap applies even when a template
  does not store its parameter and therefore has a shallower class layout.
- Existing class containment is independently limited to four levels and
  64 flattened scalar leaves. Array elements each count as a leaf; empty classes
  retain their logical initialization and existing minimum storage rules.
- The module graph admits 64 template definitions and 256 distinct requested
  specializations, including all inner instances. Identical requests reuse one
  instance. Capacity spellings such as `03` and `3` retain their canonical value
  identity and the existing inclusive 1 through 64 limit.
- Existing module, source, frame and parameter limits are unchanged. These are
  bounded language admission rules, not a whole-compiler memory or stack proof.

### Resolution and authority

The parser retains a bounded unresolved argument tree. It consumes adjacent `>>`
contextually only while closing a template-id, preserving arithmetic shift tokens
and precedence. Declaration and construction lookahead balance the complete tree.

The module resolver resolves/interns children before their parent and uses exact
resolved nominal identities in the parent's ordered argument tuple. Template and
ordinary-class declarations are never held through invalidating class-vector
traversals. Repeated request resolution does not create another specialization.

All child/parent lookups use the requesting module's lexical scope and direct
imports; instantiated bodies retain their defining module's helper bindings.
Visibility checks follow inner argument identities and public signatures
transitively. Exported templates alone cannot launder a private or transitively
imported child type. Same-layout inner types are not interchangeable.

The unresolved tree is erased before substitution. Existing resolved instance
argument identities remain available to trusted frontend visibility checks.
Unresolved argument metadata is rejected at the concrete IR boundary; no new IR
instruction, backend operation, calling convention, foreign layout or ABI is
introduced. Native construction, copies and metadata use existing validated
class storage shapes.

### Still excluded

Template definitions cannot name any explicit user-template specialization,
including fully concrete ones or themselves. There is no dependent body
expansion, recursive instantiation, deduction, function template, generic method,
resource/reference argument, owner field, builtin-array argument, struct or C
compatibility surface. `Scalar` still rejects classes and enums, including
nested `std::array` wrappers. Nested arguments do not make arrays of classes.

## Function templates

### Finite grammar and expansion

Types may be bare parameters or existing concrete types. In function template
signatures, local declarations, construction and compile-time reflection, a
statically named class template may use bare function parameters or fully concrete
concrete argument trees. Thus `pair<T,U>` and `pair<array<u8,16>,T>` are admitted, but
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

### Independent limits and identity

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

### Scope and authority

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

## Ordinary overloads

### Selection and bounds

One defining module may contain up to 32 ordinary declarations with one qualified
name. Parameter count and ordered exact concrete nominal parameter types uniquely
select a declaration. Scalars i64/u64/u8/bool remain distinct; equal physical class
layouts or enum representations do not imply equal types. Existing copied-class
and readonly byte-span boundaries are retained. Return types never select an
overload. Repeated parameter tuples reject even if results or export flags differ.
No implicit conversion, ranking, default argument, variadic or method/constructor
overloading is added. All existing six-parameter/value/frame limits still apply.

Argument count is checked against the visible candidate set before argument
lowering. Actual arguments are evaluated exactly once left to right, with existing
class snapshots and span borrow lifetimes at each source argument position. The
exact accumulated types select one candidate, and its result/signature authority
is checked before emitting the call. Failed compilation publishes no partial
output; ordinary atomic-output guarantees and immutable source inputs remain.
This is bounded linear candidate search, not a whole-compiler resource proof.

### Scope, identity and privacy

Overloads combine only within one defining module and qualified source name.
Lexical namespace lookup stops at the first occupied name. Cross-module visible
name collisions remain eager ambiguity errors even if parameter types differ or
the name is unused. Private declarations are considered in their defining module
only; direct import sees just exported overloads. A selected signature must satisfy
existing direct-import/public-type visibility; an inaccessible exact match does
not fall back to a different declaration. Body lookup and reflection retain the
original defining module; overloading grants no extra type/member authority.

A single ordinary declaration keeps its prior source/native identity and diagnostic
path. Every member of a true overloaded set has a private length-prefixed native
identity based on defining module, namespace/name, and resolved parameter tuple;
results and source order do not affect it. An overloaded root-global answer is
rejected to preserve the bootstrap entry seam. Other overloaded names have no
unmangled bootstrap entrypoint; ordinary source calls remain supported.

### Templates and exclusions

Function-template names remain exclusive: ordinary/template collisions reject,
and template definitions cannot overload each other. Existing explicit function
calls and class specializations keep their budgets/authority. Calls from template
bodies to ordinary overloads use the defining module and substituted concrete
argument types; no function-template calls inside template bodies are enabled.
Methods and constructors remain non-overloadable. No optional, raw pointer, C ABI,
heap/resource/reference API, struct declaration or conversion ranking is added.

## Fixed arrays

### Copied class storage arrays

Concrete `array<C,N>` storage also accepts a complete copied class `C`, with
capacity 1 through 64. This extends builtin storage; the `std::array<Scalar,N>`
wrapper and scalar template substitution keep their existing constraints.
Classes containing owners, references, spans, regions or service capabilities
cannot be elements. Enum arrays, nested arrays and whole-array call parameters
or results remain unsupported.

```cpp
class Records {
    array<Record, 4> entries;
public:
    Records(Record empty) : entries{empty, empty, empty, empty} {}
    auto replace(i64 slot, Record value) -> bool {
        entries[slot] = value;
        return true;
    }
    auto at(i64 slot) const -> Record {
        const Record copy = entries[slot];
        return copy;
    }
};
```

A local uses the existing braced array literal, for example
`array<Record,2> entries = {first, second};`, or a same-type complete named array
copy. Each initializer element must be a complete exact-type named value; a
private field's constructor lists exactly one named parameter per element.
Repeated names make independent copies. Empty braces, missing elements,
constructor temporaries and default/zero construction of class elements reject.
Private field constructors initialize the whole array exactly once in field
order. Even empty elements require named source values at the source level;
empty array fields and carriers require explicit logical initialization, while
standalone empty sources retain the [vacuous complete-field convention](VALUES.md).

`Record copy = entries[index];` checks the signed index once and creates an
independent typed value. `entries[index] = replacement;` checks the index once
and replaces one complete element from an exact-type named local. It does not
rerun a constructor or affect neighboring elements. Const locals and const
receivers permit copies but reject replacement. Fields remain private and are
indexed by their implicit name only inside the declaring class. There are no
indexed method receivers, field chains, escaped element references, projection
arguments or direct indexed returns; stage a typed local first.

Elements use canonical inline child layout, including packed bytes and internal
padding, with stride equal to the child's size. Empty children keep the existing
nested-value zero-payload convention, while standalone arrays reserve at least
eight bytes. A class-array edge counts toward the existing four-level containment
limit. Local arrays and composed fields retain the copied bounds of 512 byte
leaves, 64 non-byte leaves, 513 total leaves and 520 reserved bytes, plus the
ordinary 65536-byte frame limit. Counts, products, offsets and full extents are
validated before indexed storage access; the bounds trap precedes the runtime
stride multiplication. Reflection describes the array's storage size and zero
public fields without exposing private members or widening type visibility.

IR keeps an explicit element count separate from the flattened leaf count.
Dedicated initialization, bounds-guard, element-copy and element-replacement
operations check exact nominal element type, logical field identity, active root,
complete initialization, const permission and disjoint copied storage. Scalar
array zero/load/store operations cannot address class elements. Local arrays use
verified private carrier layouts with the ordinary object lifetime/copy machinery;
carriers cannot appear in function signatures, receiver signatures or nested
class fields. No source reference or capability denotes an element.

`console.session_files` is the first consumer: four BinaryBuffer64 records become
one private array. Listing and search copy each selected record once per iteration;
readback copies the found record once, and commits replace a complete record.
The content/name algorithms and RAM-only lifetime remain unchanged. Source and
hostile-IR tests cover this bounded mechanism; final integrated native, linked
stack/image and actual console guest gates remain required.

### Unambiguous storage names

`builtin::array<T,N>` is the canonical compiler storage type. The namespace
`builtin` is reserved to the compiler. The existing unqualified `array<T,N>` is a
fixed alias for that same storage type in every scope, including namespace std
and inside the std::array class. It never denotes the user class template and does
not fall back to namespace or injected-self lookup. Existing local storage syntax
and its 1..4096 concrete length range remain available.

The wrapper is explicitly `std::array<T,N>`. Only the std namespace may declare
a class template with basename array; other declarations and local shadow attempts
cannot claim the unqualified storage name. Bare `array(...)` is rejected everywhere.
The constructor name `array` inside the wrapper declaration is a dedicated
constructor syntax position, not a type lookup. Other class templates retain their
existing injected self-class behavior. Qualified `builtin::array` may occur in
storage type/reflection positions, not as a callable wrapper constructor.

Module path components such as `std.array` are module identities, not type lookup;
they remain valid. They do not grant permission to declare the builtin namespace.

### Capacity parameters

The newly accepted parameter form is `template <Scalar T, i64 N>`. Previous one-
or two-Scalar-parameter classes remain supported. Capacity arguments are decimal
literals only, from 1 through 64, without general expressions, suffixes, negative
values, defaults or deduction. Leading-zero spellings normalize numerically, so
3 and 003 request the same specialization. Value and type argument kinds cannot
be exchanged.

N becomes an immutable i64 constant in the concrete body and builtin storage
dimension. It cannot be shadowed, assigned or moved. T/N may parameterize builtin
storage without enabling recursive user-template instantiation or nested class
arguments. Defining module, declaration and ordered type/value tuple determine
nominal identity and native symbols. Existing graph caps of 64 templates and 256
specializations apply; repeated requests reuse a specialization.

### Private array fields and complete construction

Private concrete u8 array fields admit length 1..512; non-u8 private fields and class-template capacities remain 1..64. Array fields require a declared complete constructor. The explicit
initializer `elements{}` initializes every element to zero/false in field declaration
order. Nonempty lists, scalar fill shorthand, omitted/duplicate initialization,
public array fields and constructor access to the receiver are rejected. Scalar
fields retain their existing explicit scalar initialization rules.

Array fields can be indexed or queried with len by their implicit name inside a
method. A same-named ordinary local follows normal lexical lookup, without
changing the field's identity or privacy. No whole-array field value, address,
reference, direct external field traversal or field-array reassignment is exposed.
Const non-template methods may borrow their implicit private fixed-u8 field under
the exact receiver-bound rules in [ownership/views](OWNERSHIP.md). Later nested class composition follows VALUES.md; copied
class arrays follow the bounded section above. Resource arrays remain unsupported.

A field access evaluates its index once, checks signed-negative and upper bounds,
then performs the load. Field element assignment checks the index before evaluating
its right-hand expression, preserves the checked index through nested calls, and
stores once. The containing receiver's nominal identity and lifetime are unchanged
during this operation. Const methods cannot write; mutable methods require an
exclusive call-duration receiver capability. Zero-initialized storage removes no
subsequent bounds or const check.

### Logical fields, flattened storage and IR

A logical array field contains multiple scalar leaves. U8 leaves occupy one byte; numeric/bool/enum non-u8 leaves occupy eight. Canonical layout includes necessary padding; an empty standalone class reserves at least eight bytes.
field_count continues to count public logical fields, never array elements.
Private array fields therefore do not increase a public field count, though total
size remains an intentionally observable representation property. Builtin storage
reflection IDs retain their earlier element/length mapping; wrapper classes have
distinct nominal class IDs.

The frontend assigns logical field indices and contiguous flattened byte offsets.
Class copies, left-to-right argument snapshots, immutable parameters and complete
results copy all initialized leaves into independent storage. The copied boundary permits at most 512 u8 leaves, 64 non-u8 leaves, 513 total leaves and 520 canonical reserved bytes. These are independent limits, not counts of public source fields. Local classes retain
the separate 65536-byte layout/frame constraints; these are not global stack bounds.

IR records each logical field's element type, first leaf, length and scalar/array
shape separately from the flat class layout. Verification requires exact contiguous
coverage without gaps, overlaps, wrong types or overflow. ReceiverArrayZero is
constructor-only and initializes each leaf exactly once. ReceiverBoundsGuard binds
an i64 index to the nominal receiver and precise logical array field. ReceiverIndexLoad
and ReceiverIndexStore require that evidence; scalar receiver operations cannot
address an array field. Mutation requires receiver permission. Local-array and
receiver-field guard tokens cannot substitute for one another or survive a
transforming arithmetic/conversion operation.

The backend derives offsets from validated shapes and tests bounds before any
indexed address calculation. The existing .Laurora_bounds_trap UD2 label handles
failure; no new raw-pointer operation or trap category is introduced. Public
source metadata cannot manufacture these hidden capabilities.
