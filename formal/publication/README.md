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
schema. Known human-display tags (including the producer's `array` tag) are
non-authoritative; their payload never supplies canonical fields. Unknown tags reject.
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

Supported forms: scalar constants/load/push, boolean not, u64 subtraction, bitwise
AND/OR, comparison and the bounded signed-literal-12 shift profile below,
receiver scalar loads/stores, ordinary method calls, labels/jumps/
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
unsigned payload. Checked u64 subtraction has an explicit underflow fault; the
leaf-policy extension below adds explicit shift overflow, not general signed arithmetic.
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
The optional `GuardedCallPrefix` checker ties this preservation result to the
actual rejecting-guard/ordinary-callee/resource-call source prefix and lookup-
selected callee. It derives the callee run and its argument readiness, but is
conditional on the caller state and successful argument evaluation; it does not
assume or prove that the root reached that call. The separate checked
`RequestShape.first_request` corollary starts instead from an actual finite local
execution from fresh PC0 to the first external Waiting state. It derives guard
acceptance and actual callee return, then the exact epoch/offset/zero/count request,
positive count, offset ≤ bytes, count ≤ bytes − offset, offset + count ≤ bytes,
and bounded unsigned-word values. All operand evaluations use the frozen
request.before receiver (after the ordinary callee) and saved root parameters.
The optional checker requires the exact repeated typed range-expression operands
and parameter argument pattern, without fixing names, ordinals or PCs. This is a
first-request/no-prior-response result, not a bound on later external mutations,
authority validity or a native resource effect.

This remains a sequential mathematical interface model: no physical-memory,
weak-memory, locking, DMA/GPU, distributed authority, `A.Enabled`, native pre-call
scope/pinning, backend or hardware safety theorem follows. Large actual-source/IR
acceptance and executable scenarios remain native receipts, **not concrete kernel
acceptance proofs**. The generic Lean correspondence and local progress proofs
are kernel-checked with audited `propext`/`Quot.sound` dependencies.

### Restricted free functions and returning forwarders

The free-function profile retains the same complete raw source graph, namespace
selection, signature and published artifact. It does not synthesize a receiver
or claim the older class-only D2 closure certificate. `LocalFreeBinding` composes
exact free-callable identity with the existing complete local-body certificate.
Root unqualified symbols use raw names; imported symbols use length-encoded
module/namespace/name linkage. Callable module index zero iff source is the root
is a restricted consumer convention, not compiler module-resolution correctness.

`ForwardWrapper` checks a genuine free Call19: a direct imported, exported
namespace function, six word parameters forwarded in declaration order, bool
result, and complete entry/argument-push/call/return coverage. It uses the original
`ParsedMethod` and certifies the callee in the SAME graph and decoded tables.
`ForwardWrapper.returned_run` is an internal conditional helper; the exact-policy
`ForwardWrapper.numeric_run` discharges its premises using the SAME `LeafShape`,
for both true and false bounded inputs. `accepted_true` applies to arbitrary
actual modeled true-returning runs, not only the constructed run. Local termination
excludes infinite local running steps, not environmental liveness. Acquisition,
lowering, backend instructions, copied-record scalar ABI and authority remain
outside this theorem.

Complete unselected source coverage additionally admits one opaque quoted token
containing printable ASCII without backslashes. Both quotes and every interior
byte occur in the independent lexical relation. Escapes, controls, non-ASCII and
unterminated strings reject; quoted braces/comment markers cannot create
declarations. Selected string expressions still reject. The nonauthoritative
producer display tag `array` conveys no structural or semantic payload authority.

Use the existing driver on either complete process-root capture:

```sh
.lake/build/bin/source-binding-probe --forward-leaf process_snapshot_writable_leaf \
  --ir FULL_IR ROOT_MODULE kernel.snapshot_mapping kernel snapshot_writable_leaf SOURCE...
python3 probe-source-leaf.py FULL_IR ROOT_MODULE SOURCE...
```

Generic forward correspondence and exact policy shape are reported separately.
A coherently weakened source/IR policy may satisfy only the former. The runner
retains hashes of every full source input and artifact and uses D1, not the
unsupported class-only D2 entry point. Executions are native receipts, not kernel
certificates for concrete multi-megabyte inputs.

The optional `LeafShape` certificate checks the actual free function's entire
typed body against the snapshot leaf predicate, using its six actual `u64`
formal names and positions. Generic correspondence alone does not establish
this policy: coherent source/IR policy changes must still pass the exact shape
check. `LeafShape.evaluates` derives total evaluation from the bounded actual
argument map; `executes_numeric` constructs the complete canonical IR run;
`accepted_true` derives `LeafAccepted` for any same-entry run returning true.
The numerical facts include flags modulo accessed/dirty bits, physical address
identity/alignment/nonzero/52-bit width/limit, prefix alignment and slot bound,
and the no-carry identity `prefix | (slot<<12) |3 = prefix + slot*4096 +3`.
Shift non-overflow follows on the checked `slot < 512` continuation, rather than
being a caller premise. The fixed low-21-bit mask proof is constructive.

Bitwise AND/OR act on bounded unsigned words. The earlier leaf/scalar profile
admits only the signed literal shift count `12`, represented by a distinct transient marker, never
as a `u64`. Its next checked instruction must consume it as the checked left
shift: it cannot be pushed, stored, returned, called with, or carried across
control flow. Overflow traps are explicit. This is not general signed arithmetic.
The source/published-IR numerical result does not prove native scalar transport,
backend lowering, page-table authenticity, mapping stability, A/B authority,
or payload-copy effects. Large captured-input acceptance is a native receipt,
not a concrete kernel reduction of the entire source graph/publication.

## Frame-lifecycle prerequisites (Stage 1)

The shared mathematical machine now supports closed nominal enum values, private
local stores, checked u64 addition, and signed literal shift counts 4, 12 and 32.
Enums retain their canonical nominal name and ordinal; `readRuntime` checks the
same checked declaration's case cardinality. They are not coerced to u64 or bool.
`Publication.Scalar`, `GuardType` and `readScalar` retain the old bool/u64 profile.
The existing canonical effect decoder checks the additional raw operand roles,
nominal types, slots and CFG facts. This does **not** turn the earlier D2 scalar
checker into a complete nominal/local-variable verifier.

Selector 8 has one context-independent checked left-shift semantics; selector 9
is zero-filling right shift. Counts are signed literal markers, not numerically
equal u64 operands. The old signed-12 numerical equation is recovered exactly
by `leftShift_twelve`, and the existing source/IR proofs retain their statements.
Checked addition and left shift trap on overflow rather than wrapping.

`RuntimeLocals` separates declared type, source mutability, lexical scope and
initialization from the machine's raw private slots. Fresh monotone scope IDs
and unique active scopes prevent a departed scope from being re-entered.
Well-formedness is preserved by scope entry/exit, initialization and assignment.
`local_initialization_simulates` and `local_assignment_simulates` relate one
accepted source-local operation to the actual shared machine's local store,
with the RHS already evaluated. The step preserves receiver, arguments, stack
and accumulator and emits no receiver-store event. Source constness is **not**
inferred from canonical slot mutability flags.

The source metadata certificate selects from the SAME complete byte-backed graph:
actual enum declarations and case ordinals, nominal signature types, source
local initialization order, constness, lexical scope and visible names. It checks
the complete formal/private-local slot metadata and genuine `__au_v` linkage for
nominal signatures (including its precedence over the root-entry convention).
`--runtime-identity` exposes this metadata-only stage. `ExpressionNames` is a
scope relation, not expression typing: initializer typing, source-use to `Load`
correspondence, nested call execution and whole-body execution are not established
by accepting that mode.

These are reusable primitive and declaration/slot-binding prerequisites. They
do not yet establish execution correspondence for the complete `frame_transition`
helper DAG, root totality, or its lifecycle policy. Nested value-returning call
composition and attachment of the numeric result specification are separate
obligations. No ledger update, persistent retirement, ABA freedom, native enum
cast, ABI/backend correctness, or A/B authority theorem follows from this stage.

`FramePolicySpec` is a **separate independent numerical specification**, with its
own 20-export audit (distinct from the primary source-binding/primitive audit).
It models prioritized rejection, canonical packed results, allocation-generation
preservation, matching release increment or retirement, and rejection when the
retired record is supplied again. Packing bounds and no-carry OR identities are
proved mathematically. These results are not yet attached to the actual source
or its 10-helper execution. They do not prove that a caller stores the result or
retains a retired record; earlier guards may reject with a reason other than
`retired`. The complete source/IR lifecycle correspondence remains outstanding.

### Generic runtime expressions and single-return free functions

The next bounded slice uses the **same raw `SourceExpr` and canonical effect
machine**, not a second policy AST or interpreter. `RuntimeExprTyped` and
`RuntimeExpressionCode` independently check exact formal/local/enum declaration
identity, private-slot uses, scalar/nominal types, signed literal shift counts,
operator order and short-circuit control flow. Counts are transient shift
operands, never variable, argument or return types. This slice admits no calls
inside expressions and no local declarations or assignments in its complete-body
endpoint.

`RuntimeEvaluates` is an independent inductive source judgement using the shared
scalar and nominal primitives. Reads check the exact retained declaration and
active scope before inspecting its value. Missing and malformed values remain
faults. `TypedGuard.runtime_compatible` embeds the entire earlier field-free
scalar fragment **including faults**, without requiring successful or bounded
formal inputs. `RuntimeExpressionCode.evaluates_and_runs` constructively derives
one source outcome and a matching canonical run for every caller accumulator and
residual stack. `RuntimeArgumentsCode.evaluates_and_runs` preserves left-to-right
first-fault behavior and reversed argument pushes over that residual stack.
Successful expressions restore their caller stack; faults retain the actual
terminal machine rather than fabricating a restored PC/stack. Both outcomes
preserve private locals, receiver and arguments and emit no receiver stores.
These generic expression APIs expose their local declaration/scope relation;
they do not independently establish its selected-function provenance.

`RuntimeReturnCertificate` closes that provenance obligation for a **complete
single-return free function**. It uses the same byte-backed selected declaration,
nominal/scalar signature and canonical tables, requires exactly one parsed return
and no declared locals, checks actual PC0 parameter bindings, derives the
immutable scope-zero formal environment, checks the whole expression against the
declared result type, and requires the final return to end the entire code array.
`executes` covers both values and expression traps from runtime-typed initial
arguments; it assumes neither expression success nor safe packing bounds.
`terminal_correspondence` uses deterministic machine terminal uniqueness to
relate **any actual terminal run** to a constructed source outcome and an empty
store trace. It is not a general source-derivation determinism or bidirectional
source semantics theorem. The existing `--runtime-expression` consumer selects this
bounded certificate; native acceptance of a full source/artifact input is still
not a kernel proof over those concrete megabytes.

This supports the actual arithmetic bodies of `kernel_owner` and `frame_record`
without changing their source to fit the checker. In particular, arbitrary
bounded arguments to `frame_record` may overflow a checked shift; the theorem
preserves that trap rather than assuming a total successful packing function.
At this earlier single-return checkpoint there was no nested-call simulation
(the bounded extension below supplies that); complete ten-helper/local-body
execution, attachment to `FramePolicySpec`, allocator ledger mutation, ABA,
A/B authority, native enum-cast and backend correctness remain unproved.

The focused gate retains all 273 preceding primary exports and appends 25 for
this slice: **298 primary reports plus 20 separate, unattached specification
reports**, each restricted to `propext` and `Quot.sound`.

## Bounded nested calls to actual single-return leaves

The next contextual expression profile supports nested ordinary calls to the
same graph/table's checked complete single-return leaves. `OrdinaryDescriptor`
has one full `RuntimeType` signature; `ScalarOrdinary` is an exact proof-carrying
view for the earlier scalar source profiles, not a second runtime descriptor.
Nominal identity/cardinality remain in signatures and machine events. The old
MethodCall38 recognizer remains scalar-only; the new free Call19 recognizer checks
the complete runtime signature, actual target and canonical operand/CFG fields.
Conflicting source-key/target descriptors fail closed.

There is still one judgement over the existing raw `SourceExpr`:
`RuntimeEvaluatesWith` evaluates ordered arguments, then the actual source leaf's
parsed return expression in source-only formal storage. Its events contain source
keys and unchanged values, not IR results. `RuntimeEvaluates` is its empty-function,
empty-trace specialization. All earlier outcomes, including malformed/missing-value
faults and arbitrary external responses, retain their old theorem strength.
`RuntimeCallExpressionCode.evaluates_and_runs` constructively supplies a finite
matching run in the existing `CallMachine`, with exact ordered source/machine
invoke-return correspondence. Successful calls restore caller locals, arguments
and residual stack. A fault is an actual machine terminal state: no caller frame
is fabricated and no unwinding/return event is invented. The separate trace-stack
algebra is **not** a theorem equating source unmatched calls with `ActiveCall.saved`.

`FormalRuntimeCallInterval.executes` attaches this to the SAME complete parsed
caller, scoped return occurrence, selected canonical interval and leaf bodies.
The first profile requires no visible local declarations, derives the source
formal metadata and machine formal cells from the actual signature, and checks
actual parameter-binding rows. It starts at the selected interval with that
constructed formal state; it does **not** prove the caller's preceding branches
reach the PC, nor that source statement lowering places the occurrence there.
It assumes neither expression success nor packing bounds; arbitrary initial
formal values may fault. Successful completion is a running state at the interval
end, not a terminal boundary. No arbitrary-run interval reflection or full caller
execution is claimed. The existing `--runtime-call-expression PATH START` mode
checks this optional formal-only profile, without extracting another source body.

The actual selected occurrence is the initializer branch's nested
`frame_record(frame_kernel(), 0u64, owner)` return expression. Full-input native
binding controls remain runtime evidence, not kernel proofs over megabyte inputs.
Synthetic same-machine overflow controls check the precise active packing callee,
retained saved caller and residual operand, ordered invokes, and absence of a
fabricated return. No complete ten-helper DAG, local-statement/call simulation,
attachment to the independent lifecycle specification, native/backend correctness,
ledger mutation or A/B authority result follows from this contextual slice.

The focused primary audit retains all 298 preceding exports and adds 58:
**356 primary reports**, plus the unchanged **20 separately labelled independent
specification reports**, with the same `propext`/`Quot.sound` allowlist.

### Complete scoped bodies with bounded leaf calls

`RuntimeBodyCertificate.executes` now checks and executes complete selected
ordinary bodies, rather than a caller-selected expression interval. The SAME
parsed `SourceStatement` list supplies declarations, mutable assignments,
conditionals and returns. `RuntimeStateAt` relates their lexical cursor to
initialized, runtime-typed private storage. Skipped branches reserve only fresh
scope identifiers: they do not initialize skipped declarations. Normal branch
exit hides child bindings while preserving current surviving values. Return and
fault paths retain their actual state without invented cleanup.

The certificate covers the actual parameter-binding prefix, every body row and
all source suffixes, including unreachable suffixes. Both branch layouts use
checked targets and generic label-only suffixes. The theorem starts at PC0 with
`RuntimeEntryArguments` (typed, bounded initial parameters), derives formal
metadata and initialized cells, executes nested calls to actual complete
call-free leaf certificates, and executes the actual final/early `ret`.
It constructively produces a source outcome and matching finite `CallRuns`,
with ordered source-key/full-descriptor call events. Expression overflow and
callee faults remain outcomes; neither body success nor a chosen return value
is a premise. A fault retains a genuine active machine state, possibly a nested
callee. This theorem does not assert source determinism or arbitrary-run
reflection, and the independent trace-stack algebra still is not an equality
to the machine's saved-frame stack.

The existing native `--runtime-body` mode accepts the complete actual
`record_valid` (60 rows, private locals and leaf calls) and `frame_reject`
(98 rows, nominal comparisons and mutable local assignments), over the complete
source graph and publication. Native full-input and synthetic execution controls
are distinct from kernel-checked generic proofs. This extends the earlier
contextual slice, without claiming the complete ten-helper DAG, the root
`frame_transition` lifecycle specification, ledger writes, native/backend
correctness, or A/B ownership authority. The independent specification remains
unattached.

The primary audit retains all 356 preceding exports and adds 48 scoped-body
exports: **404 primary reports**, plus **20 separate independent specification
reports**, under the unchanged `propext`/`Quot.sound` allowlist.
