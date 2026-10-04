# Bounded exact ordinary-function overloads (unaccepted candidate)

Dependency: safe reusable ordinary APIs need a name to dispatch on exact existing
value types, without adding implicit conversions, dynamic dispatch or new ABI.
This candidate extends ordinary namespace/global functions only. Acceptance needs
focused positive/negative/adversarial native tests, source/assembly differential,
existing direct IR/native controls, complete release/fatal ASan/UBSan compiler
checks, independent review, then separate parent integration. Isolated release/fatal
sanitizer gates and independent review have passed; parent integration remains pending.

## Selection and bounds

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

## Scope, identity and privacy

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

## Templates and exclusions

Function-template names remain exclusive: ordinary/template collisions reject,
and template definitions cannot overload each other. Existing explicit function
calls and class specializations keep their budgets/authority. Calls from template
bodies to ordinary overloads use the defining module and substituted concrete
argument types; no function-template calls inside template bodies are enabled.
Methods and constructors remain non-overloadable. No optional, raw pointer, C ABI,
heap/resource/reference API, struct declaration or conversion ranking is added.

## Isolated gate status

Complete release and fatal host ASan/UBSan compiler targets passed with unchanged
executable/test inputs. Independent source, malformed-IR and native review passed;
baseline assembly/status differential preserves the existing subset. The initial
duplicate-name diagnostic regression and all harness/resource failures remain
recorded. This candidate is still unaccepted until separate parent integration.
See [the exact receipts and limits](../evidence/function-overloads/README.md).


## Integrated verification update (2026-10-04)

The earlier pending-integration text records the isolated checkpoint. Fresh combined
native tests and all 166 emulator modes plus two actual normal restoration boots
have now completed with independent final review. The native test-success result
uses an exact reviewed supplement to a preserved bookkeeping-failed terminal.
See [the complete integration results and limits](../docs/function-overloads-integration-results.md).
