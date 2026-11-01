# Checked published-IR consumer

This standalone Lean project consumes the actual version-1
[published listing](../../compiler/IR-PUBLICATION.md). The current D1 checkpoint
checks wire syntax and the specific structural predicates below. **Selected
instruction typing/CFG/call closure (D2) remains pending.** This is not source
correspondence, a compiler-correctness proof or a kernel safety proof.

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
proved by these range checks. Unknown numeric instruction forms outside future
selected semantics remain raw data, not accepted executable behavior. D2 must
establish its own supported signature/layout/operand/CFG/call obligations.

No source declarations are parsed. Same-typed field-use swaps cannot be detected
by structural typing alone. Capture authenticity, publisher fidelity, source-to-IR
semantics, primitive behavior, native ABI, listing-to-object binding, backend
correctness and hardware semantics remain separate obligations. Catalogue checks
establish supplied-record consistency, not native behavior or authority.

## Checks and trust

Use the official pinned Lean 4.24.0 release, without additional packages:

```sh
./verify.sh
.lake/build/bin/publication-probe /path/to/complete-production-listing.ir
python3 probe.py /path/to/complete-production-listing.ir
```

The generic proofs and small grammar fixtures are kernel-checked, with no
`native_decide` or admitted-result axioms. `verify.sh` audits exported theorem
dependencies, allowing only `propext`/`Quot.sound`. Complete-document fixtures and
production mutations are **native execution tests, not concrete kernel proofs**.
Attempting direct kernel reduction of complete-document acceptance was not
viable in the first probe; it is not silently replaced by compiler-backed proof.

Default framing limits: 16 MiB input, 1 MiB per line **including LF**, 300,000
lines; tokens are additionally bounded and numerals inspect at most twenty
digits. Arithmetic is unbounded Nat/Int followed by explicit i64/u64 bounds.
Exhaustion rejects; no partial success is returned. The driver acquires at most
the byte limit plus one sentinel byte before refusing oversized input. These
are operational ceilings, not proved output-size or native complexity bounds.

Production execution uses the entire file. Generic soundness does not turn a
native success receipt into a kernel theorem about those concrete bytes. Native
receipts additionally trust Lean code generation/runtime, standard byte-array
primitives, file IO, OS and acquired file identity. Hashes record provenance,
not semantic correspondence. Resource probes establish implementation feasibility,
not authority safety. Huge artifact constants are not compiled into Lean proofs.
