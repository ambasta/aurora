# Bounded concrete nested generic values

Milestone020 closes a composition gap in the existing inline class-value subset.
Independent review, complete release/fatal ASan/UBSan compiler gates, fresh parent
`make test` and three existing UEFI integration profiles passed. M019 remains the
historical full 166-mode kernel run; no fresh full suite is claimed here.
[Verification](../docs/verification.md) and [M020 evidence](../docs/evidence/milestone-020/README.md)
identify the exact compiler pins, inputs, finite coverage and preserved failures.

## Concrete surface

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
produce independent fresh-local copies, and class-valued fields cannot be
reassigned or called through as chained receivers. Array storage remains private;
`size()`, checked copied `at()`, and mutable `set()` retain their original APIs.

## Independent bounds

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

## Resolution and authority

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

## Still excluded

Template definitions cannot name any explicit user-template specialization,
including fully concrete ones or themselves. There is no dependent body
expansion, recursive instantiation, deduction, function template, generic method,
resource/reference argument, owner field, builtin-array argument, struct or C
compatibility surface. `Scalar` still rejects classes and enums, including
nested `std::array` wrappers. Nested arguments do not make arrays of classes.

## Acceptance

The focused suite covers native values and metadata, exact independent bounds,
nominal/type/privacy failures, copied boundaries and malformed syntax. Existing
compiler regressions and numeric oracle suites remain required, including direct
malformed-IR, exhaustive operation-dispatch and native ABI checks. The final
candidate also requires release/ASan/UBSan runs, an unchanged-source assembly
comparison with a frozen baseline, and independent review. Kernel image changes
and new physical-hardware qualification are outside this candidate.
