# Checked published-IR consumer

This standalone Lean project consumes the actual version-1
[published listing](../../compiler/IR-PUBLICATION.md). The current D1 checkpoint
checks wire syntax and the specific structural predicates below. An optional
root selection additionally checks the `scalar-receiver-v1` instruction/type/CFG
and call-closure profile. This is not source correspondence, a proof of complete
Aurora verifier admission, compiler correctness or kernel safety.

## Byte-backed chain

`AsciiRun`/`Frames` specify printable ASCII payloads and LF terminators with
consecutive spans covering the entire input. `Words`, `Digits`, `HexRun` and
`FieldText` specify exact token boundaries, canonical bounded integers and
lowercase hex. `RecordText` specifies the version-1 fixed tag/arity/field-kind
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
- complete canonical field/leaf and resource-method keyed groups;
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
prove that listing invalid under the publisher format. No linear complexity
claim is made for the whole consumer (class/resource grouping scans pools).

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
value-level IR execution semantics nor authority/no-mutation theorems. Typed
external occurrences are collected from every complete selected body; they may
fail or have arbitrary effects. Recursion is not unfolded, and no call termination
claim is made. Numeric schema/form meanings were independently reviewed against
the compiler sources; their adequacy for compiler execution remains unproved.

No source declarations are parsed. Same-typed field-use swaps cannot be detected
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
a same-typed field-use swap, explicitly exposing the absent source-use proof.
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
