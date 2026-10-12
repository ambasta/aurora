# Classes and copied values

Classes are inline values with nominal identity, private-by-default access and explicit complete initialization. They need no heap or GC. Complete copied values carry no borrow or allocation authority. Resource-bearing classes follow [ownership](OWNERSHIP.md), and fixed storage/templates follow [generics and arrays](GENERICS.md). The size rules below include the byte-heavy extension; older 64-leaf limits apply only where not extended.

## Classes

### Construction and visibility

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

### Receiver and calls

- Methods use `auto name(parameters) const -> Scalar` for readonly access and omit
  `const` for mutation. The original explicit parameters/results were scalar; subsequent copied class
  boundaries follow [VALUES.md](VALUES.md);
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

### Explicit empty values

A zero-field class without a declared constructor remains explicitly initialized
with `Empty{}` and can be copied, returned or used as a typed-owner fill. Its
storage reservation does not by itself establish a complete value. The
`InitializeEmptyObject` instruction requires an exact active pristine class slot
whose canonical logical fields and scalar leaves are both empty; owning types
and internal class-array carriers reject. It establishes the same completion
facts as construction/copy and emits no machine code, because `BeginObject`
already clears canonical padding. Repeated or conditional-only initialization
cannot bypass the existing join rules. Nested empty children still require their
own logical initialization through ordinary construction/copy operations.

### Lowering boundary

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

## Composition

### Value types and construction

`Value` is a template constraint accepting i64, u64, u8, bool, a closed nominal enum,
or a named concrete class. `Scalar` includes numeric/bool types,  and excludes enums. `Value` is contextual in a template
constraint position, so existing classes named Value remain valid. A class argument has its defining
module's nominal identity; equal layouts do not make different classes
interchangeable. Arguments must be visible through the requesting module's own
scope or direct imports. Public nested fields and public constructor signatures
participate in that visibility closure. Exporting a specialization cannot expose
a private argument type; generated bodies retain their defining scope without
granting callers access to its private classes. Fully concrete nested template-id
arguments are supported up to four template-id levels under GENERICS.md.
Reference/resource types, deduction and dependent/recursive template-body
instantiation remain unsupported.

A class can contain a class-valued field. Such a class must declare a complete
constructor. Its initializer list copies a complete, exact-type named constructor
parameter into each class-valued field. Constructor parameters can be class
values: each is a readonly, independent snapshot taken left-to-right at its
argument position. All snapshots finish before the fresh destination receiver is
acquired. Initializers execute in field declaration order; constructor bodies
remain empty. There is no receiver access during initialization.

Containment is acyclic. A class containing another class is limited to four class
levels, counting itself, and the copied-value bounds below. Existing standalone
class and frame limits remain. Arrays contribute every element to that count;
empty child classes contribute no scalar leaves but still require explicit
logical initialization. Empty standalone values retain their existing minimum
storage size. These bounds do not establish whole-program stack safety or global
compiler memory bounds.

### Projection and independent copies

A public class-valued field can be copied into a fresh typed local:

```cpp
const std::MinMax bounds = values.first;
```

The receiver must be a named local, including a readonly function parameter.
Inside a class's own method, a private field can similarly be copied through its
unqualified name. The projection creates a complete independent value. Mutating
the extracted copy cannot change the containing object. Ordinary by-value
function arguments and results also copy all scalar leaves of composed values.

The [direct owned-field extension](VALUES.md) adds complete direct
class-field replacement and synchronous direct child method receivers. Deeper
chained field mutation, escaping subobject references,
resource fields, heap storage and inheritance remain unsupported. Constructors
accept class arguments. Methods accept scalar/enum and copied class parameters
and may return a complete copied class into a fresh typed local under the
[method-value contract](VALUES.md).

Reflection retains logical public field counts, including a class field as one
field even when it contains many leaves or none. Sizes include flattened payload
with the existing minimum size for an empty class. U8 payload leaves use one
byte; earlier scalar types, including bool, retain eight-byte storage. Canonical
byte offsets and padding are separate from leaf counts; see SCALARS.md. Nominal IDs
remain graph-local and visibility-scoped.

## Ordinary calls and returns

### Source contract

A function may take and return a named copied class whose leaves are exact numeric, bool or closed enum values.
Private array fields contribute all of their initialized elements under the
[fixed-container contract](GENERICS.md). Each boundary class obeys the byte/non-byte/canonical-extent limits below; the total parameter
count remains at most six. Larger classes are still permitted as local values
under the existing frame-size cap. Arrays, owners and references cannot cross
these boundaries. There are no implicit conversions between nominal classes,
including classes with identical fields or spellings from different modules.

Parameters are immutable independent values, as with existing scalar parameters.
Their fields cannot be assigned and they permit only const methods. A callee can
make a separate mutable local copy. Returning a complete local or parameter copies
its scalar state; it neither re-runs its constructor nor transfers a reference.
A checked trap is fail-stop and does not publish a partially produced result.

Copied argument and result expressions are bounded:

- A copied class argument is a complete local name, a copied constructor call,
  or an ordinary function/overload/template or method call producing that exact
  nominal class.
- A class-returning ordinary function or method call occurs in a typed local
  initializer, a direct copied-class return or an admitted copied argument.
- A copied class return expression is a complete local name, a direct constructor
  call, or an ordinary free-function/overload/template or method call with the
  exact declared result type.

For example, `return Box(42);` is accepted in an ordinary function or method
returning exactly `Box`. It constructs a fresh internal object using the same
constructor visibility, argument checks and left-to-right snapshots as a typed
local initializer, then copies its complete value through `ReturnObject`.
Constructor and argument traps remain fail-stop; existing cleanup runs after
successful construction and before return. [Resource functions](OWNERSHIP.md)
may also return these complete copied values after normal owner cleanup; calls to
those functions still require named typed initializers. Empty and composed copied
classes follow the same completeness rules. No heap allocation, reference escape,
new IR operation or copy-elision guarantee is introduced.

`return make();` and `return object.copy();` use the same checked call lowering
as a typed local initializer, with an unnamed, unbound destination whose explicit
local identity is passed to `ReturnObject`. Method receivers may be complete
named locals, the implicit receiver, or one direct copied-class field of either.
Private fields stay accessible only inside their declaring class; constness and
parent/field liveness checks are unchanged. Owning-class field receivers remain
outside this direct-return convenience. Each result slot is fresh, pristine and
disjoint from receiver/argument storage. Argument snapshots and synchronous span
loans finish before the usual return cleanup; the result is then copied through
the existing private ABI. This is source convenience, not copy elision.

`consume(make());` and `consume(Box(42));` materialize complete independent
readonly arguments using the same checked constructor/call paths as named
locals. Ordinary methods retain their existing receivers, including named owning
or borrowed objects, the implicit receiver and direct copied-class fields. Their
copied results carry no ownership or loan authority. Temporary receivers, direct field/index
arguments, designated construction arguments, direct returned field projections
and `return Box{.value=42};` remain unsupported. Resource calls, builtin owner and
service operations, service helpers and borrowed-object helpers still need their
typed result locals.
Owning results still require an explicit `move(named_local)` return. This narrow
convenience does not enable general class-valued expressions. `std.json` uses
direct copied call returns; `std.json_write` uses direct constructor returns for
its copied append reports.

Arguments evaluate left-to-right. Each class is copied at its position, before
later argument side effects. In `f(object, object.add(1))`, the first argument
contains the pre-add value. Repeated use of one source object creates distinct
snapshots. The new result binding enters scope after argument evaluation, so
`Box box = copy(box);` inside an inner scope can read the outer binding.
Nested calls evaluate once and finish their own argument lifetimes before the
next outer argument. Exact overload selection uses the actual staged argument
types, never the expected result type or speculative candidate evaluation.
An earlier borrowed argument retains its loan during later argument evaluation;
materializing a copied value cannot bypass that loan. Copied snapshots end after
their containing call. No new ownership, heap allocation or lifetime escape is
introduced, and existing frame limits still apply.

### Modules, encapsulation and reflection

Every signature type resolves in its defining module. Exported functions cannot
expose private nominal types. Each caller must directly see every class in the
signature; importing a factory does not implicitly reexport types from its own
imports. Import the exported type's module explicitly when necessary.

Public factories may return exported classes with private fields. Field/method
access still requires normal class visibility and const permission. Copying a
complete value grants no private field access. Runtime metadata retains the
callee's defining-module view; carrying a value does not widen that view or expose
its fields to reflective access.

### Typed lowering and native call record

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

The backend marshals copied fields into a bounded private call record. Its
[bounded byte-run lowering](SCALARS.md) combines only
exact groups of eight contiguous u8 payload leaves, using RAX alone so live scalar
argument registers remain intact. Copies also compact contiguous
initialized scalar runs of at least 64 bytes with forward REP, preserving the
additional scratch registers and accounting for their temporary stack saves.
RSP-based argument packing captures its destination before those saves. It changes neither snapshots nor copy ordering,
and never copies representation padding or owning descriptors. Hidden
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

## Method arguments

### Source and lifetime contract

Ordinary methods accept concrete class values alongside scalar and enum explicit
parameters. Six explicit parameters remain the maximum. Every boundary class has
at most 64 flattened scalar leaves. Nominal identity, class-depth four, template
instance/definition limits, literal capacities and the source frame cap remain
unchanged. Private signatures and direct-import visibility are checked as before.

Receiver identity resolves first. Arguments then evaluate left-to-right; each
copied argument is materialized into a fresh readonly snapshot at its argument
position under the ordinary-call contract above. Later arguments can mutate the
source or receiver without changing earlier snapshots. Repeated arguments and a
receiver supplied as an argument are legal because their snapshots are distinct.
Only after all argument evaluation is synchronous receiver authority acquired.

The callee binds each class argument into its own immutable complete local copy.
Const methods and explicit independent mutable copies are allowed. Mutating a
parameter or calling a mutable method on it is rejected. Copying never reruns a
constructor. Class results copy a complete named local or parameter into a fresh,
exact-type destination, disjoint from receiver and argument snapshots. The result
binding becomes visible only after all arguments are evaluated. Checked faults
are fail-stop and do not promise rollback of earlier receiver side effects.

Sibling calls preserve current const/exclusive forwarding rules and suspend then
resume the caller's receiver authority. All constructor rules remain: complete
initialization, readonly snapshots, empty body, field-declaration-order
initializers, and no receiver access during initialization. Any call-graph cycle
containing a method or constructor is still rejected.

The [direct owned-field extension](VALUES.md) separately permits
one owned class field as receiver and complete direct field replacement.
No temporary/deeper-chained receiver, projection argument, reference, resource
method parameter, generic method, overload or new
template-body grammar is added. Use a named local for an
intermediate projection. This is bounded value transport, not a general
heap/lifetime or optional/expected implementation.

### Typed IR contract

MethodCall retains objectArguments and resultOffset. When any parameter is a
class, objectArguments has one position per explicit parameter; scalar/enum
positions are zero. Otherwise the vector is empty. Every class position denotes
an active, complete, exact nominal, readonly, distinct snapshot. No snapshot may
alias the receiver. A class result must be an exact active pristine object slot,
separate from receiver and every argument snapshot. Logical completion remains
required for nested and empty classes, independently of payload bytes.

BindObjectParameter remains in the parameter entry prefix and creates an
immutable local lifetime. ReturnObject requires a complete exact-type local and
balanced scalar operand stack. Constructor forwarding, const-authority widening,
ordinary/scalar calls targeting receiver entrypoints and forged physical storage
continue to reject. Lexical privacy remains a trusted frontend responsibility.

### Frozen private x86-64 convention

All ordinary scalar/aggregate function conventions are unchanged. All constructor
conventions are unchanged, including their internal i64 result. Existing methods
with only scalar/enum parameters retain positional scalar registers and R10 as
receiver. Such a method returning a class continues to use R11 as result address.

A NEW class-parameter method returning scalar/enum uses R10 for receiver and R11
for a packed explicit-argument record. All its explicit parameters, including
scalars/enums, bind from that record using existing record offsets/padding.

A NEW method combining class parameters and a class result uses three hidden
inputs simultaneously: R10 receiver, R11 argument record, RAX result destination.
The caller finishes scalar pops and record packing before loading R10 and then
RAX. The record remains live until the call returns. Scalar argument positions
are not compacted around class entries. Existing call-site alignment is retained.

The callee saves hidden inputs before any binding/body operation. With source
frame size F, receiver is saved at F+8 and argument record at F+16. Combined mode
saves result at F+24, reserves 32 hidden bytes and preserves 16-byte alignment.
Noncombined receiver modes reserve the existing 16 bytes. A result-only method
retains F+8 receiver/F+16 result; ordinary aggregate saves remain unchanged.
The hidden overhead is separate from the unchanged 65,536-byte source frame cap.
No private capability is source-addressable, a scalar IR value, reflection data,
or an externally advertised scalar-callable symbol. There is no C ABI promise.

## Enums and copied method results

### Nominal enums and Value

A module or namespace can declare `enum class Status { ready, failed };`.
`Status::ready` is a named value of that exact nominal type. Enums support equality,
inequality, initialized local/field values, and function/method parameters and
results. There is no integer or boolean conversion, ordering, arithmetic,
explicit case ordinal, unspecified default value or source address conversion.
The graph permits at most 64 enum declarations, each with 1..256 unique cases.

Value explicitly accepts closed enum types as well as numeric/bool and named
concrete class types. Scalar is exactly i64/u64/u8/bool and excludes enums. Builtin arrays and
std::array continue to reject enum elements. Named enum arguments retain their
defining-module identity, so std::pair<Status,Report> is distinct from an otherwise
equal-layout pair using another enum. Fully concrete nested arguments follow the
bounded GENERICS.md contract; deduction and recursive template instantiation remain unsupported; explicit bounded function templates are documented in GENERICS.md.

Enum names and cases obey module visibility. Exported signatures, public member
signatures and template argument visibility include enum dependencies. A generated
template body may use its fixed instance and exact nominal arguments internally;
this does not import arbitrary names from the caller or widen runtime reflection
views. The same nominal identity is preserved in enum constants, slots, fields,
comparisons and calls through lowering.

Enum storage is eight bytes, size_of is eight and field_count is zero. Type IDs
are graph-local and allocated after the class descriptors. Existing programs
without enum declarations retain their descriptor behavior. Reflection does not
provide enumeration of case names, a runtime cast or an external serialization
contract.

### Complete copied method results

A method may return a complete named class local or a
[direct copied-class constructor](VALUES.md#source-contract). A caller uses a fresh explicitly typed local, an admitted direct copied return or a copied argument. This includes composed classes with
private array, enum and empty-class descendants. The result has independent
storage; changing the original receiver or the extracted copy cannot change the
other. Const receivers may return copies that the caller binds mutably.

Construction requires: exact nominal class-field copies,
complete logical initialization including empty children, left-to-right readonly
constructor snapshots, acyclic containment, four class levels and the copied-value size bounds below. Ordinary methods accept copied class-valued arguments.
Constructors still return the internal i64 status and have empty bodies; their
explicit class arguments remain supported.

A result call acquires receiver identity and evaluates explicit arguments before
making the new result binding visible. Direct copied calls, including ordinary
methods on one copied-class field, and constructors can be returned as described
above. Direct field-value returns such as `return item;` still require a complete
named local. The [direct owned-field extension](VALUES.md) also supports complete
direct field replacement. Deeper chained mutation, source references to subobjects
and general class-valued expressions remain outside this subset.

### Internal calling convention

MethodCall retains its objectArguments vector and adds a trailing resultOffset.
Constructor calls with class parameters use a receiver in R10 and packed argument
record in R11. Class-returning methods use a receiver in R10 and fresh result
destination in R11; their explicit arguments are scalar or enum register values.
The combined argument/result mode uses RAX for the result destination and three independent saved capabilities. The receiver and record/result are saved in
separate private frame slots before evaluating the body. Ordinary aggregate
functions retain their previous convention.

CopyObject, ObjectFieldCopy and InitializeObjectField retain recursive nominal
layout and logical-completion evidence. Result destinations must be exact, fresh
and separate from active inputs. ReturnObject copies a complete value. EnumConstant
retains a declared nominal enum and valid named case index; generic scalar
constants cannot create enum values. These mechanisms are compiler-private and do
not add a C ABI or source-visible pointers.

## Direct field replacement and methods

### Supported subset

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

### Independent IR boundary

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

## Larger byte-heavy copied values

### Representation and ownership

A concrete private `builtin::array<u8,512>` field can own a complete 512-byte
sector-sized payload. Its constructor must explicitly zero every byte with an
empty-brace initializer. Checked signed-i64 indices, exact-u8 stores, private
state and complete independent class copies retain their existing semantics.
The array itself cannot escape as a view, reference, pointer or direct argument.

A composed class, or a class used as an ordinary function, constructor or method
parameter/result, must satisfy all of these independent limits:

- At most 512 u8 leaves
- At most 64 non-u8 scalar leaves, including bool and enum leaves
- At most 513 total scalar leaves
- At most 520 canonical reserved storage bytes, including padding

This admits a 512-byte owned class and a copied report with one eight-byte status
enum plus that class. Either declaration order has 520-byte canonical storage.
The report can expose a recoverable status and copied success-or-zero payload
without an allocation, mutable span, raw reinterpretation or new unsafe operation.
Status masking remains a library responsibility; this compiler contract preserves
complete values and does not invent persistence, I/O or failure semantics.

Private non-u8 array fields and all class-template capacity arguments remain
1..64. Local builtin arrays retain 1..4096, class containment depth remains four,
and signatures retain six explicit parameters. A standalone noncomposed local
class retains its separate 8,192-leaf/65,536-byte layout limits. The source frame
is still limited to 65,536 bytes. No constant-sized class creates a heap object.

### One canonical layout and two checked boundaries

The parser and semantic analyzer apply the element-specific private-array bound.
Semantic class composition and every copied signature use the shared logical
leaf predicate and the canonical storage extent. Direct typed-IR validation
independently checks those same bounds, exact nominal nested ranges, initialized
leaves, object reservations, readonly argument snapshots and pristine results.
The canonical layout builder rejects a field with an invalid element-specific
extent before computing offsets. Supplied physical metadata must still exactly
match the shape-derived canonical layout.

U8 stride remains one byte. Earlier scalar/bool/enum storage remains eight bytes.
No IR instruction, private calling convention or ABI register assignment changes.
Copied payload lowering coalesces eight initialized contiguous u8 leaves into one
existing x86 MOVQ load/store pair. Both canonical source and destination offsets
must be consecutive inside the current operation's selected leaf range; there is
no alignment rounding, padding access or overread. Remaining bytes use the existing
byte operations, and short bool/enum/i64/u64 runs retain their existing operations.

This applies only to argument packing, local copies, nested-field projection,
assignment and initialization, copied returns and copied parameter binding. These
operations already require disjoint source/destination storage through verified
reservations, fresh snapshots/results and caller-versus-callee frames. RAX remains
the sole externally clobbered scratch register, preserving live scalar arguments,
hidden receiver/record addresses and arithmetic flags. Contiguous runs
of at least 64 initialized bytes use forward REP MOVSB with saved RSI/RDI/RCX and
an explicitly tracked 24-byte temporary stack peak. Padding and owner descriptors
are never included; RSP-based argument packing captures its destination in RAX
before saves and keeps its RBP-based source stable.
Ownership transfers, descriptor clearing, zeroing and checked indexed operations
are unchanged. Copies remain explicit and in IR order, with unchanged object
reservations, probes and hidden saves. No runtime copy call, copy elision or C ABI
is introduced.
