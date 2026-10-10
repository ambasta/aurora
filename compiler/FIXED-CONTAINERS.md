# Bounded fixed containers with private array storage

The [sector-sized value candidate](SECTOR-VALUES.md) narrowly extends
byte-array and copied-value limits below; its acceptance is separate from all
historical results recorded here. Non-byte and template-capacity bounds remain.

The current candidate provides a real Aurora `std::array<T,N>` value container.
Import `std.array` through an explicit module root. T is i64, u64, u8 or bool in the current development candidate; N is an
explicit decimal capacity literal from 1 through 64. This is an initialized fixed
container with copied element access, not a slice, reference-returning view,
dynamic vector, byte/string API or general allocator.

```text
module application;
import std.array;

auto answer() -> i64 {
    std::array<i64,4> values = std::array<i64,4>();
    values.set(3,42);
    const std::array<i64,4> snapshot = values;
    values.set(3,0);
    return snapshot.at(3);
}
```

- `array()` completely initializes every element to integer zero or bool false.
- `size() const -> i64` returns the fixed capacity.
- `at(i64 index) const -> T` returns an independent scalar copy after a bounds check.
- `set(i64 index,T value) -> T` requires a mutable receiver, checks bounds, stores
  the exact-type value and returns it. Arguments evaluate before method entry under
  ordinary call rules; this API does not delay evaluating its value argument.

The implementation is Aurora source in library/std/array.au. It uses a private
builtin storage field and the normal constructor/method/class-value pipeline.
There are no foreign library calls, heap allocations, implicit conversions,
unchecked accessors, element references or C-compatible layout promises.

## Copied class storage arrays

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
standalone empty sources retain the [vacuous complete-field convention](VALUE-CALLS.md).

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

## Unambiguous storage names

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

## Capacity parameters

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

## Private array fields and complete construction

An ordinary or instantiated class can contain private fixed scalar-array fields
of length 1..64. Array fields require a declared complete constructor. The explicit
initializer `elements{}` initializes every element to zero/false in field declaration
order. Nonempty lists, scalar fill shorthand, omitted/duplicate initialization,
public array fields and constructor access to the receiver are rejected. Scalar
fields retain their existing explicit scalar initialization rules.

Array fields can be indexed or queried with len by their implicit name inside a
method. A same-named ordinary local follows normal lexical lookup, without
changing the field's identity or privacy. No whole-array field value, address,
reference, borrow, direct external field traversal or field-array reassignment
is exposed. Later nested class composition follows COMPOSED-VALUES.md; copied
class arrays follow the bounded section above. Resource arrays remain unsupported.

A field access evaluates its index once, checks signed-negative and upper bounds,
then performs the load. Field element assignment checks the index before evaluating
its right-hand expression, preserves the checked index through nested calls, and
stores once. The containing receiver's nominal identity and lifetime are unchanged
during this operation. Const methods cannot write; mutable methods require an
exclusive call-duration receiver capability. Zero-initialized storage removes no
subsequent bounds or const check.

## Logical fields, flattened storage and IR

A logical array field contains multiple scalar leaves. Every leaf occupies eight
bytes, including bool, matching the existing padded storage model. Class size is
the total leaf count times eight, minimum eight bytes for an empty class.
field_count continues to count public logical fields, never array elements.
Private array fields therefore do not increase a public field count, though total
size remains an intentionally observable representation property. Builtin storage
reflection IDs retain their earlier element/length mapping; wrapper classes have
distinct nominal class IDs.

The frontend assigns logical field indices and contiguous flattened byte offsets.
Class copies, left-to-right argument snapshots, immutable parameters and complete
results copy all initialized leaves into independent storage. The ordinary
function-boundary limit is 64 total scalar leaves per class, not 64 source fields.
Mixed layouts exceeding that limit reject at the boundary. Local classes retain
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

## Evidence and remaining work

Validation covers native execution for every scalar type at capacities 1/2/63/64,
zero initialization, independent copies and class-call ABI, mixed flattened layouts,
const/privacy/name rejection, exact bounds trap sites and index/RHS evaluation order.
A seeded list model independently predicts sequences of container operations.
Malformed IR tests cover shape partitions, initialization, receiver permissions,
field-token identity and complete flattened copies. Historical milestone009
receipts remain unchanged; final review/integration must identify this candidate.

No generic iterator, span/slice, reference return, nested aggregate, dynamic
allocation, resizing, constructor body, text encoding or runtime service is added.
Per-file/depth/template limits do not establish a global compiler work/memory bound;
compact verifier facts and explicit global budgets remain future hardening.

The milestone013 packed-byte candidate supersedes the earlier all-eight-byte
layout described above only for new u8 storage: u8 elements have stride one,
while all prior scalar/bool representations remain unchanged. Logical leaf caps
remain independent of bytes. See BYTES.md for canonical offsets, padding,
reserved extents and the separate pending representation acceptance gate.
