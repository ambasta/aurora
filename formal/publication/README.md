# Checked published-IR consumer

This standalone Lean project consumes the actual version-2
[published listing](../../compiler/IR-PUBLICATION.md). The current D1 checkpoint
checks wire syntax and the specific structural predicates below. An optional
root selection additionally checks the `scalar-receiver-v1` instruction/type/CFG
and call-closure profile. A separate D3a layer below checks bounded raw-source
guard/IR semantic correspondence; D3b1 below adds complete scalar stateful bodies.
These layers do not prove complete Aurora verifier
admission, compiler correctness or kernel safety.

## Byte-backed chain

`AsciiRun`/`Frames` specify printable ASCII payloads and LF terminators with
consecutive spans covering the entire input. `Words`, `Digits`, `HexRun` and
`FieldText` specify exact token boundaries, canonical bounded integers and
lowercase hex. `RecordText` specifies the version-2 fixed tag/arity/field-kind
schema. Known human-display tags are nonauthoritative; unknown tags reject.
`WireDocument` relates all decoded records to the **same input and exact spans**
used by framing. No host parser, golden AST or digest stands in for this relation.

These independent relations do not invoke the decoder. Total decoder functions
construct their witnesses in Lean; proofs are erased in native execution.
Generic length/field-access lemmas establish that numeric schema fields have
actual integer values rather than the convenience accessor's default.

`CheckedStructure` checks:
- unique header/count/name/literal/trailer records, section ordering and no
  leading/trailing display records outside the envelope;
- published pool counts, dense pool identities and declared operational limits;
- name/type/slot/payload ranges listed explicitly in `poolReferences`;
- complete canonical field/leaf and resource-method keyed groups, including
  nonempty ASCII identifier source-method spellings unique within each resource;
- exact retained-body framing, consecutive positions, repeated counts and
  trailer count through the independent `BodyTrace` relation.

`CheckedArtifact`/`artifact_sound` compose wire grammar and structural checking:
tables are definitionally projected from the very decoded record sequence bound
to the input. `CheckedStructure` alone is a predicate on arbitrary tables and
must not be confused with this byte-backed endpoint.

## Deliberate restrictions and remaining obligations

This consumer currently requires strictly increasing original instruction IDs
and body callable IDs, nonempty retained bodies and the canonical section order.
Sparse original IDs and adjacent labels remain permitted. Strict increase is a
sufficient uniqueness restriction; rejecting a reordered listing does **not**
prove that listing invalid under the publisher format. Version 2 rejects old
headers and missing source-method spelling columns. The
exact spelling bytes, native linkage and signature are retained separately;
name uniqueness does not prove that a producer published the right spelling or
that source resolution/native effects implement it. Source-call binding remains
a separate obligation.

No linear complexity claim is made for the whole consumer (class/resource grouping scans pools).

D1 is not full metadata or global IR verification. Operand-role-dependent nested
references, instruction forms/flags/targets, type constructors, leaf expansion,
physical nonoverlap, receiver/frame/borrow rules and external effects are not
proved by these range checks. Unknown numeric forms outside a selected closure
remain raw data, not accepted executable behavior.

## Selected scalar-receiver profile (D2)

Roots are exact callable-name byte strings supplied to the consumer, not compiler
snapshot-policy special cases. Candidate discovery is independently checked:
`ClosedSlice` requires uniquely bound roots, unique selected IDs, checked complete
bodies and every ordinary method callee in the selected set. `CheckedSlice` and
`slice_sound` bind this to the same raw-byte artifact; no host-selected excerpts
replace any stage. The result may be a closed superset, not a proved minimal set.

The initial profile admits mutable receivers with scalar bool/u64 explicit
parameters/results, no borrowed roots, constructors, local slots, array or nested
aggregate fields. Every referenced scalar descriptor and leaf descriptor must
have canonical empty name/tail fields. Scalar equivalence compares descriptors,
not numerical TypeId identity. Canonical field indices are bound to their scalar
leaf types and offsets; scalar eight-byte ranges are pairwise nonoverlapping.
Frame offsets are eight-byte scalar **end offsets**, field offsets are **start
offsets**. Retained kind26 nominal fields must match a unique catalogue resource.
Its catalogue scalar/class/enum mapping is explicitly -1, not a fabricated scalar.
Opaque resource physical extents are not published and are **not** certified.

Supported forms: scalar constants/load/push, boolean not, u64 subtraction and
comparison, receiver scalar loads/stores, ordinary method calls, labels/jumps/
boolean branches, scalar return, parameter binding, retained-resource operations
and Require. Operand arities/roles, unused payloads, signature/frame/receiver
bindings and catalogue argument/result types are checked. Unsupported selected
forms, type constructors, tails and flag bits reject. Catalogue effect categories
are recognized identities, not trusted frame/authority guarantees.

Branches must target later positions and matching unique labels; backward edges
are an explicit consumer restriction, not a compiler-format prohibition. Adjacent
labels are valid. Leader/fallthrough flags are recomputed. Independent predecessor
coverage plus a strong-induction theorem establishes **syntactic normal-CFG
reachability** for every selected position, not feasible value-level execution.
Require additionally may fail; native/external failure behavior is not modeled.

Candidate accumulator/argument-stack types are checked independently against
`TypeTransfer`, `TypedRows` and every normal CFG edge. Joins may forget accumulator
information but never stack types; reads require a known matching scalar, and
an overwrite can restore information. `FlowsTo.known` proves that an incoming
known type agrees with each predecessor. Require consumes its boolean current
value. Retained calls with one scalar argument read current; zero/multiple-argument
retained calls and ordinary method calls follow their separately checked scalar
stack conventions. These are source/admission IR conventions, **not native ABI**.

This profile does not reproduce ownership, permissions, initialization, lifetime
or provenance facts from the full compiler verifier. It provides neither a
value-level IR execution semantics nor authority/no-mutation theorems by itself. Typed
external occurrences are collected from every complete selected body; they may
fail or have arbitrary effects. Recursion is not unfolded, and no call termination
claim is made. Numeric schema/form meanings were independently reviewed against
the compiler sources; their adequacy for compiler execution remains unproved.

D1/D2 alone parse no source declarations. Same-typed field-use swaps cannot be detected
by structural typing alone. Capture authenticity, publisher fidelity, source-to-IR
semantics, primitive behavior, native ABI, listing-to-object binding, backend
correctness and hardware semantics remain separate obligations. Catalogue checks
establish supplied-record consistency, not native behavior or authority.

## Checks and trust

Use the official pinned Lean 4.24.0 release, without additional packages:

```sh
./verify.sh
.lake/build/bin/publication-probe /path/to/complete-production-listing.ir [ROOT_SYMBOL ...]
python3 probe.py /path/to/complete-production-listing.ir [FILL_SNAPSHOT_SYMBOL]
```

The generic proofs and small grammar fixtures are kernel-checked, with no
`native_decide` or admitted-result axioms. `verify.sh` audits exported theorem
dependencies, allowing only `propext`/`Quot.sound`. Complete-document fixtures and
production mutations are **native execution tests, not concrete kernel proofs**.
The optional production mutation workload addresses fill/enter records only to
alter input bytes, never to certify them. It includes the expected acceptance of
a same-typed field-use swap, exposing the absent source-use check in D1/D2 alone.
Abnormal termination is a failed test, never a successful refusal.
Attempting direct kernel reduction of complete-document acceptance was not
viable in the first probe; it is not silently replaced by compiler-backed proof.

Default framing limits: 16 MiB input, 1 MiB per line **including LF**, 300,000
lines; tokens are additionally bounded and numerals inspect at most twenty
digits. Selected bodies are limited to 4,096 instructions, selected closures to
128 callables and discovery to 65,536 visits. Arithmetic is unbounded Nat/Int followed by explicit i64/u64 bounds.
Exhaustion rejects; no partial success is returned. The driver acquires at most
the byte limit plus one sentinel byte before refusing oversized input. These
are operational ceilings, not proved output-size or native complexity bounds.

Production execution uses the entire file. Generic soundness does not turn a
native success receipt into a kernel theorem about those concrete bytes. Native
receipts additionally trust Lean code generation/runtime, standard byte-array
primitives, file IO, OS and acquired file identity. Hashes record provenance,
not semantic correspondence. Resource probes establish implementation feasibility,
not authority safety. Huge artifact constants are not compiled into Lean proofs.

## D3a: bounded source-guard semantic correspondence

`SourceBinding` supplies a reusable raw-source boundary. Its independent byte
grammar covers every byte, including trivia, with maximal words and adjacent
two-byte punctuation. The narrow literal profile admits canonical decimal
i64/u64/u8 spellings. Strings, character literals, block comments, non-ASCII
bytes and other literal forms reject even in unselected code. These are profile
restrictions, not changes to Aurora's language. Whitespace is space or ASCII
9–13; line comments end before LF or at EOF. Scanner fuel is a resource ceiling,
not a proved exact maximum lexeme byte length.

The complete shell consumes module/import headers, namespace/class/enum and
field declarations, ordinary/const/consuming method signatures, and constructor
headers with initializer targets. Every field is retained in declared order,
including fields before and after a selected method. Supported type syntax
includes qualified names, const/reference forms and single-argument type
applications. `SourceType` is a surface-syntax tree, **not resolved or normalized
cv/ref semantics**. Opaque bodies and constructor argument expressions consume
properly nested parentheses, brackets and braces over the same checked tokens;
angle brackets are not treated as body delimiters. This does not establish their
Aurora grammatical validity, constructor effects, initialization, local-variable
binding or other unselected semantics.

Independent binding relations reject duplicate scope names, enum cases,
parameters and initializer targets, unknown initializer targets, predefined-name
shadowing, and formal/field shadowing. The conservative supplied-graph check
requires unique module identities/imports, a present root, closed imports and
reachability of every supplied file. Tagged qualified symbol inventories permit
namespace merging but reject namespace/terminal and terminal/terminal collisions.
General type-name resolution, import visibility, compiler filesystem search
precedence and capture authenticity are not proved.

`CheckedSelection` combines the graph certificate with selection by externally
supplied module, namespace/class path and member name over **the same files**.
Selection traverses only declarations, never opaque bodies or textual header
matches. `FieldAt` binds names to exact field-list ordinals/types. The selected body is parsed over that exact interval, with full syntax consumption
and an independently typed pure leading rejection guard. Tail statements are
syntax only: resource calls, local effects and whole-body typing are not proved.
`SelectedGuard` retains the same graph-backed selection and resolves each guard
name to its formal index or complete field-list ordinal/type.

`BoundIR` checks a non-template, non-overloaded source/linkage profile against
the actual decoded publication: derived class/method names, receiver mode,
visibility, all formals/result, and every ordered field type. Builtin resource
source spellings must uniquely join the published resource/native catalogue.
This is a checked profile convention, not a compiler layout, catalogue fidelity
or lowering proof. **Same-typed field-use swaps remain accepted by identity
alone; the semantic layer below rejects such mismatched uses.**

`SemanticBinding` composes that **same** selected raw-source guard and decoded IR
closure with independent source evaluation and deterministic IR small-step rules.
`ExprCode.simulates` connects each resolved field/formal use to its actual operand,
stack use, comparison and short-circuit edge. Unsigned constants use their actual
unsigned payload. Checked u64 subtraction has an explicit underflow fault.
The entry certificate checks every actual parameter bind and derives the value
relation; the leading-if certificate checks the false constant, return and closing
label. Its continuation is exactly the boundary after that matched lowering.
It does **not** prove the instruction there implements the next source statement.

`SafeSemanticBinding.refusal_or_continuation` proves, for every admitted bounded
scalar argument/receiver valuation, that a true rejection guard returns exactly
`false`, while a false rejection guard reaches that continuation. The checked
range-guard idiom derives subtraction safety from short-circuiting; initial
offset≤bytes and the rejection result are not assumptions. `no_fault`, exact
first-exit uniqueness and absence of divergence **before** the continuation are
proved separately. The finite fuel witness is existential, not a uniform numeric
resource bound. This starts at PC0 with empty accumulator/stack and all locals
absent, not an arbitrary existing native frame. Reads are sequential and stable;
there is no concurrent-environment/SMP snapshot theorem.

`NoCallStore` covers every actual normalized prefix row, including unreachable
ones; checked successor bounds prevent escaping above the cut. The admitted
forms exclude calls and receiver stores. `preterminal_frame` preserves receiver
and argument maps throughout every finite preterminal prefix trace. Return/trap
outcomes erase machine state, so no terminal-machine preservation is asserted.
This is a model/actual-listing statement, **not native API purity**: native input
pinning and authority scope setup can occur before the source call.

The D3a selected tail remains syntax-only. The separate D3b1 endpoint below
checks `enter` and `leave` individually, not their invocation from `fill_snapshot`.
Resource `fill_snapshot_chunk` arguments/effects have no execution proof here;
external calls may fail or mutate the receiver. No constructor/initialization,
producer/capture fidelity, listing-to-object, ABI, backend/ISA, hardware or
A.Enabled/authority theorem follows. Source/IR semantics and linkage/catalogue
conventions are explicit bounded models, not a verified Aurora compiler.

The focused gate audits 82 theorem exports, allowing only `propext`/`Quot.sound`.
Full eight-file source/current 5 MB publication acceptance and production
mutations are **native receipts, not kernel proofs about those concrete bytes**.
`probe-source-semantics.py` checks the same native executable on complete inputs;
its workload-specific mutation addressing is not part of any proof or checker.
Same-typed field/formal use, literal/comparison and real source-name mutations
that D1/D2 accept are rejected by semantic correspondence. Unsupported arithmetic
can already fail D2 and is labeled separately. Hashes record inputs, not proofs.

Run `./verify-source-binding.sh` for the generic audit, tiny kernel fixtures and
explicitly native shell/graph, guard/identity and operational-semantics fixtures. The native driver is:

```sh
.lake/build/bin/source-binding-probe [--ir PUBLICATION] ROOT_MODULE SELECT_MODULE CLASS_PATH MEMBER SOURCE ...
```

For the snapshot workload, optional `--snapshot-examples` before `--ir`
executes seven concrete actual-source/IR value controls, including admission,
refusal and offset-beyond-bytes short-circuiting. These named workload fixtures
are outside checker/proof logic and do not certify the large concrete inputs.

Complete-graph native acceptance is not a concrete kernel theorem. Initial
concrete header reductions did not complete in the first probe; tiny kernel
fixtures use small explicit bounds without weakening generic theorems or the
production profile. No `native_decide` or admitted acceptance axiom is used.


## D3b1: complete scalar stateful bodies

`BodyBinding` connects the same selected raw-source method, metadata identity,
actual parameter-entry instructions and the entire canonical IR body. The body
starts immediately after its declared argument binds; its checked endpoint must
equal the complete instruction count. Syntactic suffixes after returns are still
checked. Independent `BodyCode` rules cover sequence, pure scalar expressions,
field assignment, exact `builtin::require` with one bool argument, return and both
single-label and jump/false-label/join-label conditional layouts. Ordinary and
resource calls remain rejected. Field targets resolve to actual declared scalar
ordinals/types; mutable ordinary receiver identity comes from `BoundIR`/D2.
This is not general name-resolution or borrowed-mutability soundness. The receiver
is an ordinal-to-optional-scalar map, not a native heap/layout model; opaque
resource fields participate in metadata identity, not resource-value semantics.

The stateful semantics delegates pure operations to D3a's existing scalar rules.
A conservative erasure/lift connects the models without recreating arithmetic.
Successful stores validate their scalar value, update exactly one field and emit
an ordered store event. Require true clears the accumulator; false is an explicit
assertion fault. Returns and faults retain the actual current machine state.
Source evaluation reads the current receiver after each preceding assignment.
`EffectRuns.store_frame` derives receiver changes by replaying completed events,
including after faults, and derives argument preservation—no callee frame axiom.

`BodyBinding.executes` constructs a finite terminal run from PC0 for declared,
bounded scalar arguments and a fresh empty callee frame. Receiver readiness and
assertion success are not premises: malformed receiver values can produce matched
scalar faults. `terminal_correspondence` equates the source return value or fault,
current terminal receiver and exact ordered store events. Successful returns have
an empty callee stack; failure correspondence does not equate a source PC or
expression temporaries with the IR's fault frame. Deterministic terminal uniqueness
fixes the actual IR terminal machine/events, and `terminates` separately excludes
an alternative infinite local execution. These are not native caller-frame or
concurrent-environment guarantees.

The production workload checks complete `enter` and `leave` independently.
Enter's actual require precedes `active_slot := slot`, `operation := 1`, and the
conditional audit write `operation := 2`. Leave's actual require precedes
`operation := 0`, `active_slot := 3`. Failed entry/leave assertions therefore
perform no stores in those bodies. A separate parsed-source write/read/failing-
require fixture demonstrates that earlier writes/events survive failure; this is
not a rollback rule. This D3b1 stage adds no full `fill_snapshot` call-stack/resource trace theorem,
external-effect contract, authority/A.Enabled result, native pre-call scope/pinning
purity, serializer/backend/ABI fidelity or hardware theorem is added.

The expanded focused gate includes tiny kernel fixtures and native source/body,
mutation and stateful execution controls. Full production source/publication
acceptance remains **native execution evidence, not a concrete kernel theorem**.
The independent generic proofs remain kernel-checked with only the audited
`propext`/`Quot.sound` dependencies. Mutation addressing and workload expectations
are test data, never checker rules or golden instruction sequences.

Use `--body --ir PUBLICATION` before the selection arguments for the complete-body
endpoint, or `--body-examples --ir PUBLICATION` for actual selected `enter`/`leave`
value controls as well. Existing `--snapshot-examples` still selects D3a and cannot
be combined with body mode. `probe-source-bodies.py` records native production
mutations with D2 structural acceptance reported separately from D3b1 rejection.

## D3b2: complete bounded call composition

`CallBinding` extends the same byte-backed selection to the complete
`fill_snapshot` body and its actual call-free ordinary callees. It reuses the
existing parsed statement/expression AST, scalar evaluator, `EffectBody`, typed
entry and body proofs. The bounded profile adds top-level self-method calls with
discarded scalar results and exact `builtin::require(resource-field.method(args))`.
Arguments are pure, evaluated left-to-right; calls nested elsewhere remain
unsupported. Every source statement, callee body and canonical instruction is
checked, including unreachable suffixes and finite label-only gaps. In particular,
the administrative label after the old guard cut is executed, not silently
identified with the first call.

Ordinary calls retain the same source class, declaration/signature and decoded
publication tables. Their actual entry and entire body are executed; no assumed
callee summary, assertion truth or receiver frame condition is used. Resource
identity joins the declared field/type, catalogue resource, version-2 unique
source method spelling, method ordinal, ordered signature, effect tag and native
linkage bytes. This profile supports effect tag 1 only; the tag supplies **no**
authority, ownership, preservation or progress fact. Coherent nonempty linkage
changes describe a different accepted interface, not a producer-fidelity failure.
Conflicting matching descriptors are rejected by an independently checked finite
ambiguity guard. Neither source-method publication nor these joins prove compiler
resolver/serializer or native implementation fidelity.

There is one shared optional-scalar receiver map and an abstract world. Saved
caller frames contain only control state, locals, arguments and residual operand
stack, never a receiver snapshot. Ordinary return restores the protected caller
context with the returned accumulator and the *current* shared state. Callee
faults retain completed stores and the active/saved machine frames. External
invocation freezes its complete descriptor, evaluated argument list and pre-state
in a `Waiting` occurrence. The parameterized external relation may replace every
receiver field and the entire world and return a raw optional scalar or an opaque
fault. Both source and IR use the same response witness. Frame protection is an
explicit abstract interface boundary, not a proved native ABI or memory-safety
property. An external fault retains the post-invocation suspended continuation
(advanced PC, consumed arguments), not a native fault-site PC.

The actual following require handles raw true, false, missing and wrong-kind
results. True clears the IR accumulator; false assertion-faults; malformed results
type-fault. All completed enter stores and external mutations remain. There is no
automatic leave, rollback or cleanup. A true external result can still cause the
actual leave body to fail after mutation of its checked fields. Events record
ordinary invocation/return, completed local stores and external invocation/response
with the actual post-state; environmental changes are not fabricated local stores.

`CallBinding.finite_correspondence` equates the exact sets of finite observable
traces ending in return, fault or a suspended request, from fresh PC0 with bounded
supplied root arguments. Callee argument readiness, actual source-body lookup,
projection and complete body coverage are derived internally. Receiver values may
be malformed, producing matched faults. Forward simulation and converse reflection
preserve the same external choices; there is no global unique-outcome theorem for
nondeterministic environments. Terminal observations equate value/fault, current
receiver/world and ordered events, not a source PC or temporary stack. A stronger
internal continuation relation makes repeated invocation/resumption compositional.

`first_boundary` constructs finite local progress to the next suspension or
terminal result; `not_locally_diverges` excludes an infinite local running path
before that boundary. Neither demands a response exists. Blocked/divergent external
behavior can only be classified by explicitly supplied predicates on the same
pending request; absence of a response proves neither classification. Classification
transport is not an external execution or divergence-equivalence theorem, and
ongoing external activity has no invented final receiver state.

Structural read/write footprints and ordered-store replay prove preservation of
disjoint guard fields across actual local callee execution, including fault
prefixes. The fixed parameter map for the root guard is the saved caller map,
not the enter callee's different arguments. This fact is conditional on the reached
local prefix and says nothing about later external effects or authority validity.
The actual admitted source has disjoint guard reads and enter writes.

This remains a sequential mathematical interface model: no physical-memory,
weak-memory, locking, DMA/GPU, distributed authority, `A.Enabled`, native pre-call
scope/pinning, backend or hardware safety theorem follows. Large actual-source/IR
acceptance and executable scenarios remain native receipts, **not concrete kernel
acceptance proofs**. The generic Lean correspondence and local progress proofs
are kernel-checked with audited `propext`/`Quot.sound` dependencies.
