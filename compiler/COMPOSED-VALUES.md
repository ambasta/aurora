# Bounded inline value composition

This is the milestone011 implementation contract. Exact verified source and
integration evidence are recorded in ../docs/verification.md; this contract is
not a proof of whole-language safety.

## Value types and construction

`Value` is a template constraint accepting i64, u64, u8, bool, a closed nominal enum,
or a named concrete class. `Scalar` includes numeric/bool types, including the milestone013 u8 addition, and excludes enums. `Value` is contextual in a template
constraint position, so existing classes named Value remain valid. A class argument has its defining
module's nominal identity; equal layouts do not make different classes
interchangeable. Arguments must be visible through the requesting module's own
scope or direct imports. Public nested fields and public constructor signatures
participate in that visibility closure. Exporting a specialization cannot expose
a private argument type; generated bodies retain their defining scope without
granting callers access to its private classes. Nested template-id arguments, reference/resource types,
deduction and recursive template instantiation remain unsupported.

A class can contain a class-valued field. Such a class must declare a complete
constructor. Its initializer list copies a complete, exact-type named constructor
parameter into each class-valued field. Constructor parameters can be class
values: each is a readonly, independent snapshot taken left-to-right at its
argument position. All snapshots finish before the fresh destination receiver is
acquired. Initializers execute in field declaration order; constructor bodies
remain empty. There is no receiver access during initialization.

Containment is acyclic. A class containing another class is limited to four class
levels, counting itself, and 64 flattened scalar leaves. Existing standalone
class and frame limits remain. Arrays contribute every element to that count;
empty child classes contribute no scalar leaves but still require explicit
logical initialization. Empty standalone values retain their existing minimum
storage size. These bounds do not establish whole-program stack safety or global
compiler memory bounds.

## Projection and independent copies

A public class-valued field can be copied into a fresh typed local:

```cpp
const std::MinMax bounds = values.first;
```

The receiver must be a named local, including a readonly function parameter.
Inside a class's own method, a private field can similarly be copied through its
unqualified name. The projection creates a complete independent value. Mutating
the extracted copy cannot change the containing object. Ordinary by-value
function arguments and results also copy all scalar leaves of composed values.

Chained field mutation, whole nested-field assignment after initialization,
escaping subobject references, nested receiver calls, class-valued method parameters,
resource fields, heap storage and inheritance remain unsupported. Constructors
accept class arguments. Methods accept scalar/enum parameters and may return a
complete copied class into a fresh typed local under the enum/result contract.

Reflection retains logical public field counts, including a class field as one
field even when it contains many leaves or none. Sizes include flattened payload
with the existing minimum size for an empty class. U8 payload leaves use one
byte; earlier scalar types, including bool, retain eight-byte storage. Canonical
byte offsets and padding are separate from leaf counts; see BYTES.md. Nominal IDs
remain graph-local and visibility-scoped.

## Reusable library deliverable

`std.utility` migrates `std::pair<T,U>` from Scalar to Value constraints while
preserving all existing scalar uses. A concrete example composes the existing
`std::MinMax` and `std::Accumulator` abstractions, transports the pair through an
ordinary function, projects both fields into fresh locals, and mutates the copied
accumulator independently. The library still provides explicit complete
construction with public first/second fields. This is inline value composition,
not a general container of resource owners.

## Lowering and verification obligations

Logical class fields retain their nominal child type and flat leaf range. Every
range must match the declared child's exact recursively validated layout;
equal-size but different logical shapes cannot be substituted. CopyObject moves
complete values between distinct exact-type active object slots. ObjectFieldCopy
projects a declared class field to a fresh exact-type destination.
InitializeObjectField performs one complete nested initialization through the
bound constructor receiver. Scalar stores cannot mint nested completion evidence by addressing leaves
individually.

Constructor calls use readonly snapshots in a bounded private argument record,
disjoint from the destination receiver and its saved capability. Scalar operands
and class arguments retain their source order. Missing/forged receiver authority,
nominal mismatch, incomplete sources, repeated initialization and overlapping
storage must be rejected before emission. Empty nested objects need explicit
logical completion even though they have no leaves. This is a lower-level IR
proof boundary; source privacy and lifetime checking remain trusted frontend
responsibilities.

## Required acceptance gates

Native tests must cover independent copies, private scalar-array descendants,
bool/u64 layout, readonly parameter projection, constructor argument side effects,
branch/return boundaries and preserved scalar pair behavior. Rejections must
cover cycles, depth/leaf caps, type/constraint mismatch, private exported signature
leaks, chained mutation, resources and unsupported template arguments.

Direct IR tests must exercise equal-byte/different-shape forgery, partial or
repeated initialization, overlap, const/receiver authority, and constructor record
clobbering. Existing suites, independent review, address/undefined-behavior
sanitizers and a protected-program integration gate remain required. No
zero-overhead or performance equivalence claim is made.
