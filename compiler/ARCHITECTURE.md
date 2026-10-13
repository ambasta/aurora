# Frontend, typed IR and native backend boundary

The typed-IR milestone established behavior-preserving compiler phase boundaries. The subsequent native-module stage adds explicit-root imports, namespaces, scoped reflection and hardened host I/O, while preserving existing scalar/ownership behavior. `aurorac INPUT.au -o OUTPUT.s` remains valid; imports additionally require `--module-root DIR`. This is not an optimizer, a new general ownership language, or a proof of compiler soundness.

## Pipeline and ownership of checks

1. `host_sources.hpp` owns the trusted Linux descriptor-relative source reader and atomic artifact writer. `modules.hpp` loads explicit-root module graphs; `resolver.au`, over the `resolution_*` Session modules, resolves module names/exports, nominal identities and templates in defining-module contexts. MODULES.md specifies that boundary.
2. `types.hpp` defines source types and common tokens/errors.
3. The hosted Aurora lexer turns bytes into tokens; `syntax.hpp` defines the untyped source AST. `parser.hpp` is a compatibility entrypoint for one complete hosted Aurora module parse; all declaration/container grammar lives in `parser.au`.
4. `lowering_types.au`, `lowering_values.au` and the `lowering_frames`, `lowering_calls`, `lowering_expressions`, `lowering_statements` and `lowering_body` modules perform resolved layout/signature analysis, local/member resolution, exact argument-type overload selection, initialization and const/private checks, ownership moves, lexical borrow checks and conservative branch/loop joins. `lowering.au` publishes typed instructions and metadata from the same resolved Session.
5. `hosted_lowering.cpp` mechanically fills the durable Aurora metadata and instruction owners from generated typed records. One instruction field walk serves source ingress, hostile native fixtures and borrowed native observations. Instruction/operator enums come from predecessor-generated Aurora facts.
6. `ir_metadata.au` independently validates module metadata, callable signatures and frame declarations, deriving physical class layouts. `ir_instructions.au` admits instruction storage and canonical type payloads, then derives and normalizes structural control flow after codec shape checks. `ir_verify.hpp` checks instruction types, initialization, operand-stack and bounds-token invariants using those source-owned flow facts. After native value-state verification, `ir_graph.au` independently checks the complete call graph and selects retained functions. Only the resulting immutable `ValidatedModule` can be passed to the emitter.
7. `x86.hpp` lowers validated operations to GNU x86-64 assembly. It has no source AST, scope lookup, const policy, owner-liveness state or borrow-state checker. Target registers, ABI argument placement, stack alignment and machine trap sequences exist only here. Two local forms avoid stack and copy traffic without changing any check: a pushed left operand followed directly by a constant, local or receiver-field load stays in `%rcx` for the arithmetic or comparison that would pop it, and an element read that the next instruction returns is copied straight into the caller's result storage.
8. `main.cpp` coordinates file I/O and those stages. GNU assembler/linker remain the bootstrap native toolchain.

The C++ host uses internal header units and one main translation unit, linked with the generated Aurora frontend through Meson. Raw `main.cpp` compilation no longer builds a compiler. These are actual phase boundaries, not a stable external compiler-library API.

The graph, metadata and instruction-owner migrations are source-only candidates.
Their fixed paired-root
[source-bootstrap dependency](README.md#source-bootstrap), current-stage convergence
and final-source qualification remain unexecuted.

## Hosted Aurora parser

`parser.au` parses complete expressions containing integer, byte,
byte-string and bool literals, qualified names, ordinary function/constructor-shaped
calls, explicit template calls/construction, type-taking reflection,
member/method/index chains, array literals, designated named construction,
grouping, unary `-`/`!`/`~`, and all existing binary precedence tiers. Local and
constructor field initializers, return/static-assert expressions, if/while
conditions, expression statements and assignment operands enter this path. An
iterative Pratt state machine stores copied frames and AST nodes in
`syntax_arena.au`; parser nesting and AST depth retain their separate bounds
of 128. A third copied-owner store holds reverse-linked argument edges with
checked child indices, count/depth summaries and optional designator-token indices.
Argument arity grows within source/resource bounds; parsing adds no fixed
argument-count limit. Grouping
retains the inner node's original token span; index nodes retain their base token.

The parser calls `lexer.au::next_lexeme` for every token and trivia boundary.
A single linear candidate pass uses the existing frame scratch to preserve the
reference's template/call ambiguity, then one iterative type parser produces an
unresolved `TypeSyntax` forest for declaration/local types, explicit template
arguments and `size_of`/`type_id`/`field_count`. A fourth checked owner holds these copied records.
Type nesting retains its limit of 64; template nesting retains four levels and
the existing explicit-call allowance. Declaration parsing passes the original
type/capacity parameter tokens and class/function-template mode. No resolved
nominal identity or visibility authority crosses this syntax boundary.
The hosted path accepts the complete existing expression grammar directly;
Unsupported is an invalid production result. Malformed syntax, depth/allocation
failure and invalid private results reject without falling back.
Byte strings retain their complete original token,
without a second decoder or new owned
payload; existing lexer validation and semantic decoding remain unchanged.
The constructor-brace entry starts at the original field token and ends after its
closing brace. It preserves field-anchored `array_zero` for an empty initializer;
ordinary `{}` remains `array_literal`.

Ordinary function and non-constructor method bodies use one iterative body
state machine in the same arena: nested blocks, initialized local declarations,
return/static-assert, if/else, while, expression statements and supported
assignments. A fifth owner stores reverse-linked `SyntaxNode` records;
local types reuse `TypeSyntax`. Nested expression/type parsing restores its saved
frame base on every exit. Block nesting remains independently bounded at 128;
empty bodies need no expression nodes.

A production module enters Aurora once, including its preamble, imports,
namespace/class/template headers, enums, fields and complete callables. Shared
callable parsing consumes parameters, result types and bodies; constructors retain
their initializer lists and required literal empty bodies. The same syntax owner
holds explicit module/container/declaration-wrapper and template-parameter tags.
Source-backed name intervals and copied template context carry no resolved identity.
Two scratch frames per active namespace preserve its parent list and header; the
32-component namespace guard bounds these to 64 additional frames during leaf
parsing. No extra arena owner or host grammar fallback is needed.

After complete grammar, Aurora visits declarations in source order and admits
unresolved callable signatures, borrowed parameters, field storage and required
module contents. One forward lexer cursor reads the few needed spellings; existing
token ordinals locate diagnostics without a coordinate table. Pending declaration
and parameter frames reuse the syntax arena scratch after grammar continuations
finish. Each frame is charged to its unique syntax record, including a class-end
marker charged to the class, so this phase fits the existing per-token scratch bound.
The current six-parameter ceiling requires a small copied scope value; copied
field getters return through named locals. These are concrete language-ergonomics
dependencies, not a permanent semantic protocol.
The frontend uses direct copied constructor/call arguments through the shared
semantic materializer where that removes single-use argument locals. Saved values
that must precede an exclusive arena borrow, mutable records and copied-field getter
locals remain explicit. The selected source-built predecessor includes this
capability; record layouts, source state and semantic policies are unchanged.

The host supplies one copied configuration derived from the canonical array limits
and service-group helper still shared with later semantic/IR checks. Aurora selects
the admission failure; the host renders its bounded token range and, when needed,
formats the converted type. Host conversion reconstructs declarations, scopes,
access and export spelling for formatter and syntax fixtures. Production transfers
the forest into the Aurora resolution session; module file loading remains host-side.
Complete-module grammar errors precede admission errors. Besides the existing
within-declaration rule, a syntax error in a later member/declaration or an enclosing
container ending can now precede an earlier admission error in a multiply-invalid
file. Exact cross-declaration contracts are tested separately from the earlier
within-declaration cases. Valid behavior, single-error diagnostics, syntax-vs-syntax
order and admission-vs-admission order remain unchanged.

The standalone type utility returns a value cursor with an original token ordinal
and a consumed-half flag for `>>`. It never rewrites caller tokens. Whole-declaration
success consumes its delimiters and leaves a whole-token cursor; extra closers
reject in Aurora. Source snapshots and caller cursors remain unchanged on failure.

The formatter and syntax fixtures use `hosted_parser.cpp` to convert Aurora
syntax records into the existing C++ AST. It checks bounded counts, tags, indices,
backward ownership and construction depth without replaying grammar. Fragment
utilities commit their caller position only after successful conversion. Production
loading transfers the parsed forest into the resolution Session and lowers that
Session directly to typed IR; it no longer reconstructs a resolved C++ AST.
The host publishes only complete, independently validated IR. RAII releases every
Aurora owner before closing its host Region, including errors and exceptions.
The syntax AST remains a formatter/tooling representation, not a second semantic
input or a production fallback.

The selected predecessor emits the lexer/parser/resolver graph with `--local-symbols`
and `--abi-facts`. The latter describes the same validated module's physical class
layouts, resolved enum values, function symbols and argument/result extents.
The bootstrap driver generates the private C++ records/enums and opaque arena
storage from those facts, with size and field-offset assertions. Records and enums
retain their Aurora namespace, field and case names; no hand-maintained alias map
mirrors their fields. This is a closed
frontend binding, not a general C ABI generator. Only the builtin readonly-span
encoding and tiny register-move bridges remain explicit trusted ABI conventions.
Bridge targets use compiler-reported symbols rather than handwritten mangling.

The predecessor is a normal executable dependency. Current C1 links frontend A,
emits B, and C2 links B using the same host C++ objects. The bootstrap test checks
A/B generated-header equality, regenerates B and C, and compares assembly, raw
output, ABI facts, headers and objects, including the B actually linked into C2.
The source-build route in [README.md](README.md#source-bootstrap) includes the
fact-capable predecessor stage, preserved by tag `bootstrap-abi-facts-v1` at source
commit `17f4f1440e6faa9cdaf8711c04400854bdb60d9e`, followed by the copied-argument
checkpoint under `bootstrap-copied-arguments-v1` at source commit
`c0ef02cc105de2b7699d8565f6a53f1dea9e1205`, then the owner-field checkpoint under
`bootstrap-owner-field-initializers-v1` at source commit
`bbf18f40d73b0f7b862a4b23d77b03dfb3f3d0e4`. These add two source-build hops after
the facts stage before the current compiler can build its adopted frontend. The
register-carry checkpoint under `bootstrap-register-carry-v1` at source commit
`f89e0c9eb199ba482fcce20f1783a52ceae8b1b8` adds a third, so that the backend which
emits the frontend is the one that keeps operands in registers. The graph candidate
adds a fourth source-build hop at immutable commit
`052f79d7995be93053f73659bcfc37687b00b341`, merged in PR #166, to be compiled by register-carry
for paired borrowed roots and their generated ABI facts. This dependency is
included in the source recipe above.
Advance the predecessor only
when it cannot build the current frontend, to shorten the source-bootstrap
chain, or for a measured compile-speed gain recorded below, each after
reproducible source rebuild, current-stage convergence and full
qualification. Preserve earlier source refs; ordinary features do not require a
predecessor hop. No generated binary or layout snapshot is checked
in. Focused conversion/ABI and multi-stage corpus checks do not replace the final
integrated GCC 16 full/image/guest qualification.

### Resolved module boundary

`frontend.au` is the explicit root bridge surface. Its forwarding entries retain
the imported parser and resolver implementations under ordinary dead-code rules;
the bridge selects their compiler-produced symbols and layouts directly.

`resolution_arena.au` owns one flat session: source bytes, syntax, metadata,
resolved decorations, reusable work rows and a compact typed AVL index pool.
Session keeps only storage (including the five lowering pools and the lowering
diagnostic), sticky failure, checked row access, source appends, byte comparisons
and the index; tree mutation stays private. An owning class cannot nest in
another, so the code built on those primitives lives in free functions over
`Session&`: `resolution_names.au` interns names, atoms and prefixes, orders
modules and binds imports, and `resolution_ingest.au` copies parsed modules in.
The copied row classes are in `resolution_rows.au`.
The ten-i64 index rows keep private node IDs separate from heterogeneous payload
IDs; metadata retains its original append order. The sixth owner is created by a
region-backed field factory, and generated facts govern its layout and transfers.
Source requests use a held-root heap sift: larger children move upward and the
original copied row fills the final hole. The exact source-coordinate ordering
and sticky failure cleanup remain unchanged.
Host projection reads metadata, not the index pool. Loading transfers each parsed arena
once, preserving immutable host snapshots for diagnostics. Aurora registers module
and nominal identities, checks direct-import/export visibility, interns and
substitutes concrete templates, resolves signatures/bodies, and publishes explicit
reflection views in the existing phase order. The old C++ module resolver and
template expansion helpers are removed; there is no production fallback or query bridge.

The host spells already-chosen native identities and supplies fixed scalar/service
descriptors, shared limits and the canonical initial class-layout order. It cannot
select declarations or grant visibility. Setup reserves a diagnostic payload, then
seals fifteen typed prelude rows before lowering. All semantic decisions remain in
Aurora. Generated argument layouts govern owner transfer: two alternating records
hold the live Session and optional parser arena, with paired cleanup before transfer
and Session cleanup afterward. Owners stay armed through lowering and diagnostic
or IR projection. Once the projected values own their data and shared source
snapshots, temporary projection views are destroyed and Session is released before
independent verification. The outer cleanup guard still covers earlier failures;
Region verifies that its owners were released before it closes.

Pool growth is checked and on demand. The arithmetic quota includes existing graph,
source and instance bounds plus geometric spare capacity; it is deliberately loose,
not a usable RSS reservation. Qualification also applies external memory/disk limits.
Five additional typed pools hold output rows, flat operands, locals, snapshots and
continuations. Generated facts bind the complete eleven-owner Session to 520 bytes
and each continuation to 496 bytes. Fixed diagnostic storage is reserved before
work, so a selected error needs no further allocation. Local/snapshot/continuation
bounds and checked geometric growth are part of the quota; partial IR never
publishes. `hosted_lowering.cpp` checks bounded roles, slices and unique ownership,
then fills pending Aurora-owned metadata and instruction storage directly.
Variable-length instruction payloads are borrowed while copying into the durable
owner, rather than reconstructed as native vectors. Projection does not repeat
source legality checks. Each Aurora-selected error's message is the `//:`
text above its reason in `lowering_errors.au`; the frontend generator turns those
into a table in the generated ABI header and fails if a reason lacks one.
`hosted_lowering_diagnostics.cpp` checks the payload against that entry and fills
its placeholders, preserving real source spans and synthetic empty spans.

### C++ expression parser retirement

Current source has removed `expr`, `primary`, `postfix`, precedence parsing,
`templateExpressionAhead`, `templateStatementExpressionAhead`, and the reference
selection switch. Current source also removes C++ `block`, `statement`,
`startsDeclaration` and `templateArgumentEnd`; ordinary bodies and constructor
initializers enter Aurora directly. Declaration `type`, `templateArguments`,
parameter-list and constructor-initializer grammar is also removed. The complete
module/container migration removes the remaining namespace/class/template grammar
and context sets; `parser.hpp` only forwards the module entry. Unresolved
declaration admission, complete module resolution, local/member resolution and
resolved type/lifetime analysis also live in Aurora. The production `semantics.hpp`
path is removed. C++ retains source loading, mechanical record/name/diagnostic
projection, the independent IR verifier and native backend.

Targeted fixtures state expected ASTs, token spans, child/designator order and
exact diagnostics directly. The independent raw ABI, bounded-conversion, depth and
allocation-failure controls remain. Actual-source whole-vs-direct expression
checks establish dispatch consistency, not an independent parser oracle.
Retirement qualification additionally compares the current compiler with a
freshly source-built historical C++ seed on valid and malformed source. Historical
source/binaries stay outside the current tree; there is no copied parser snapshot.
The predecessor-backed C1/C2 frontend and whole-corpus reproducibility gates
remain required, followed by final integrated qualification.

## Typed instruction model

The current value and temporary operand stack carry explicit scalar/reference payload types. Source owners lower to scalar payload slots after the source ownership checks succeed. Borrow bindings lower to typed compiler-internal stack handles. No instruction offers arbitrary address arithmetic, arbitrary indirect stores, source-level raw pointers or opaque assembly injection.

The IR records typed byte-addressed slots and complete frame size. U8 fields/elements use width one; previous scalar storage stays width eight, including canonical bool values. Logical class shapes and canonical byte offsets/alignment/reserved extents are distinct. The verifier recomputes physical metadata from nominal shape, rejects conflicting supplied maps and checks occupied-byte disjointness. The backend consumes the validated map; packed loads zero-extend and padding is initialized without making it a source field. See SCALARS.md for the developing representation gate.

`CheckedAdd`, `CheckedSubtract`, `CheckedMultiply` and `CheckedNegate` retain their fail-stop overflow requirement through lowering. Comparison and logical-not operations are distinct. The backend always emits the appropriate overflow branch for checked arithmetic. There is no unguarded arithmetic operation in this IR for source numeric expressions.

Call instructions identify validated local functions. Signature lookup establishes argument/result types, and typed value-stack entries carry arguments. Metadata queries are a closed enum with a fixed defining-module scope, not arbitrary external symbol calls. The verifier requires a query to use its containing function's module view and checks that descriptor views reference known descriptors. The resolver remains trusted for import/export visibility and immutable defining-module assignment; this is not an independent re-proof of source authority. Reflection descriptor contents are produced by source semantic analysis; the verifier checks descriptor shape, not a second derivation of class reflection metadata.

## Bounds tokens and dominance

`BoundsGuard(base_slot, length, element_type)` consumes an i64 index value and produces a tagged checked-index value. The backend performs the unsigned comparison before computing any element address. Negative i64 indexes fail that same comparison.

`IndexLoad` requires a current checked-index token matching exactly the array base, length and element type. `IndexStore` requires the corresponding token on the temporary stack below the right-hand side value. The index itself is saved on the machine stack, so calls or expression evaluation in the right-hand side cannot replace it.

The verifier tracks token identity through the current value, push/pop operations, branches and joins. Replacing a checked value with a new constant/load/calculation loses its token. A guard for another array or length cannot authorize access. Reloading an index from an ordinary local does not recreate a token. A path that bypasses the guard cannot merge into a checked access. Removing a guard or moving an access to a non-dominated path therefore makes the module fail verification; a future optimizer must rerun validation before emission.

This is a small checked-index token discipline, not a general theorem about arbitrary future pointer/aliasing constructs. Arrays are still fixed-shape, scalar-only locals with no exposed alias/escape facility.

## Independent module call graph

The host derives call-graph input from the durable instruction owner after
source CFG normalization and native value-state verification, never from
lowering Session summaries. `FunctionRow`
carries call ranges, receiver/service presence and scope-zero status; target indices
cover `Call`, `MethodCall`, `BorrowedCall`, `AggregateCall`, `ServiceCall` and `ResourceCall`.

`ir_graph.au` uses paired immutable `Input` / mutable `Workspace` roots for iterative
O(V + E) service reachability, complete SCC checks, then scope-zero root retention.
Every component, including unused imports, is checked before pruning. Receiver or
service-reachable cycles reject with `invalid typed IR: recursive receiver call cycle`;
unrelated scalar recursion remains legal. Host filtering preserves original order,
with no native graph fallback. Generated row sizes bound O(V + E) storage; paired
owner cleanup precedes region closure.

Function value-state/provenance checks remain C++. They reject missing or
malformed calls before graph processing; Aurora rejects unreachable semantic
instructions before native value-state analysis.

## Durable metadata and instructions

`ir_metadata_storage.au` owns metadata, callable signatures and frame declarations,
plus canonical class fields, offsets and layouts. `ir_metadata.au` admits names,
module layouts, every callable header and every frame before publication.
Instruction storage/types and exact codec shapes follow, then all structural CFG
checks and normalization, source entry-parameter admission, native dynamic
value-state/provenance checks, call-graph checks and publication. A later structural
or entry-binding error can therefore precede an earlier dynamic value-state error;
no per-function diagnostic-order replay is retained. Malformed raw Type tails reject before canonical Type observation.

Production lowering fills one move-only pending ingress that binds both owners.
`FunctionBody` contains a stable callable ID and a borrowed instruction range.
Raw `Function` maps and instruction vectors remain for hostile `Module` fixtures;
they enter the same owners and are destroyed before body checking. Session is
released before admission. The verifier, graph pass, x86 emitter and ABI facts borrow the same
immutable metadata. Graph pruning never renumbers callable IDs.

Each callable owns a sorted range of eight existing slot-record kinds. Aurora
checks frame bounds/alignment, types, exact object/array leaves, padding and
cross-category overlap, including capability spills and owner annotations.
Native instruction analysis retains only derived leaf-origin/initialization
indexes; it does not reserve frame storage or re-admit declarations.

Pool lengths replace six redundant stored counts. Four raw-prefix counts remain
because field/storage/index pools also hold normalization tails. Adding the slot
owner and instruction-type boundary after that compaction predicts a 512-byte
MetadataStore; emitted facts still need qualification. Declaration types contain
class leaves and supplied field types, then each callable's signature and typed
slots. Instruction type occurrences follow in a separate suffix of that same
pool. Declaration references cannot reach the suffix. Every slot/type range has
exact coverage; the raw index suffix holds sorted callable IDs for lookup.

The host binds named pools to generated row shapes and descriptor offsets.
Readonly Region observations stay inside the capsule; record reads copy values,
and borrowed views die before owner cleanup. The closed pool-to-row binding is
source-reviewed because predecessor facts lack owned element identity. No native
metadata/signature/frame cache or per-pass summary serializer is retained.

`ir_instruction_storage.au` owns raw instruction and operand rows, literal bytes,
code-order IDs and body intervals. The generic source admission checks bounded,
exclusive payload coverage and canonical raw type tails; the sole native codec
checks ordered instruction shapes. Dynamic value-state semantics remain native.
Malformed instruction type tails now reject before opcode-specific errors, with
`invalid typed IR: noncanonical instruction type payload`.

Instruction IDs are immutable and one-based; function-local code positions are
separate. Native provenance uses IDs, while CFG worklists use positions. Aurora
normalizes code order before native State snapshots are created. Argument lists and
literal bytes remain borrowed from the owner; the emitter revisits literals for
rodata rather than retaining a second byte pool. Literal labels use stable IDs,
so incidental assembly label numbering changes. Existing graph scratch remains
separate until its own migration; this owner adds no unused graph workspace.

This migration claims no net source-line, peak-memory or speed reduction.
Destination allocation overlaps Session lifetime; sorting may reorder Internal
errors among multiply-malformed transport records. Generated ABI, source-bootstrap,
convergence and runtime qualification remain unexecuted.

## Entry-parameter admission

Aurora checks the complete normalized entry prefix against the admitted signature
and frame: scalar, copied-class, span, region, owner and sealed-service bindings.
It checks exact positions, nominal types, slot kinds, mutability, distinct roots,
region dependencies and permitted origins, and rejects bindings after the prefix.
The combined structural/entry bridge borrows both existing owners and returns
`structured` only after both checks; entry failure makes the owner terminally
invalid before native state construction or publication. Individual owner methods
are trusted compiler mechanisms, not unforgeable admission tokens.

The signature has at most six formals, so the existing leading instructions are
also the binding index. Native queries borrow those rows instead of retaining
parameter sets/maps or another summary. Native `Bind*` handlers establish dynamic
initial state; subsequent initialization, lifetime, ownership, loan and CFG-join
checks remain native. The separate service-loan identity scan is unchanged.
This migration remains source-only pending generated ABI and execution checks.

## CFG and frame invariants

Aurora resolves every label target, follows both conditional successors and
rejects reachable end-of-body fallthrough. Return-free cycles remain legal.
It rejects every unreachable semantic instruction, removes only unreachable
Label/Jump artifacts and remaps retained targets before copying code rows forward.
The source-controlled `structured` state closes mutation and gates publication.

Each CodeRow stores a stable ID, resolved target, flow flags and one scratch word.
Scratch is reused for sorted sparse-label lookup, the reachability queue and the
old-to-normalized position map. The predicted row grows from 8 to 32 bytes; the
five-pool InstructionStore remains 176 bytes. This adds 24 bytes per original
instruction and no pool or retained native CFG snapshot. Layout and cost remain
unqualified.

Native value analysis consumes the source-owned target, fallthrough and block-entry
facts. It retains State snapshots only at entries (function entry, labels and
conditional fallthrough), preserving target-before-fallthrough scheduling, and
walks straight-line blocks with one mutable State. Loop states propagate until
abstract joins stabilize. Native code keeps value/lifetime checks and linear
emission-depth certification, with no label map, block-entry/reached vectors or
compaction interface. Source owner-liveness backedges remain semantic-analysis
policy; this lower value pass tracks runtime initialization and value shapes.

- Function symbols must be identifiers and cannot collide with backend helper names. Calls must target a known function.
- Parameter bindings form the exact entry prefix in parameter order. They cannot be repeated later after calls have clobbered argument registers.
- Every slot access matches an allocated slot type, alignment and frame range.
- Loads and borrow handles require initialization. Array accesses require initialization of every element. Initialized-slot sets intersect at control-flow joins.
- Arithmetic, comparisons, calls, stores and returns require correct operand types. Bool constants must be zero/one.
- Labels are unique; all jump/branch targets exist, including targets in unreachable structural instructions.
- Temporary value/token stacks match at joins. Statement labels and jumps do not carry temporary stack entries. Returns have balanced stacks and correct result types.
- Reachable fallthrough without a return is rejected.
- Unreachable semantic instructions are rejected. Only unreachable structural `Jump`/`Label` artifacts are removed before native value analysis; this removes harmless jumps emitted after a returning branch and prevents invisible unreachable push/pop operations from confusing backend linear stack accounting.

Given those invariants, the backend's expression-stack depth agrees with reachable execution. It aligns the machine stack at each nested call. The semantic analyzer and verifier cap local frame storage at 65536 bytes; that bound does not eliminate target-stack exhaustion from call depth or expression temporaries.

## Compile speed

Each frontend migration so far has cost compile time. Record it with the change
instead of letting it compound unseen: for a compiler change, run
`scripts/compiler-speed.py OLD_AURORAC NEW_AURORAC` on one host, at one time, and
add a row here. The script fails if the two builds compile any input differently.
There is no automated time budget, because host load on development machines
varies too much for a stable threshold.

`aurorac` links the frontend that the predecessor compiler emitted, so a backend
change reaches its own speed only once a predecessor carrying it is selected.
Measure such a change as `aurorac-stage2` against `aurorac` from the same build:
both share the new backend and must compile identically, and only the frontend's
generated code differs.

| Change | Measured | CPU ratio |
|---|---|---|
| `bootstrap-register-carry-v1` predecessor, whose backend emits the frontend | `scripts/compiler-speed.py`, `aurorac` built with it against the owner-field predecessor: `compiler/frontend.au` 0.83x, library inputs 0.88-0.94x, identical output | 0.90x |
| x86 backend keeps a pushed operand in `%rcx` before a plain load and copies a returned element straight into the result | `aurorac-stage2` against `aurorac` from the same build (see above): `compiler/frontend.au` 0.78x, library inputs 0.86-0.95x, identical output | 0.87x for a frontend it emits |
| Hosted runtime moves a looked-up allocation to the front of its region's list | `scripts/compiler-speed.py` against the previous build: `compiler/frontend.au` 0.85x, library inputs 0.87-0.93x, identical output | 0.90x |
| Enum cases named once, one copy per heap child, index values from the lookup loop | `scripts/compiler-speed.py` against the Session split: `compiler/frontend.au` 0.88x, library inputs 0.95-1.00x, identical output | 0.95x |
| `resolution_arena.au` split into Session, rows, names and ingest; shared pool growth | `scripts/compiler-speed.py` against the `lowering_body.au` split: 0.98-1.03x per input, identical output | 1.01x |
| Generated lowering messages and the `lowering_body.au` split | `scripts/compiler-speed.py` against #162: 0.96-1.03x per input, identical output | 1.00x |
| #162, typed lowering in Aurora | five library/example inputs 1.24-1.48x wall; `std/json.au` 125 -> 184 ms; peak RSS 22 -> 22-27 MiB; full suite +16.8% (commit message) | about 1.44x |
| Parser and resolver migrations before #162 | not recorded per step; `std/json.au` went from about 40 ms at the expression-parser stage to 125 ms before #162, on loaded hosts | - |

## Trusted boundaries and limits

The semantic/lifetime analyzer remains trusted for ownership, const, visibility, source scope and restrictions on unsupported syntax. Those policies are discharged before lowering; slot-level IR verification does not independently re-prove them. Mutating arbitrary internal C++ objects using casts or undefined host behavior is outside this interface's threat model.

The verifier protects the backend against malformed instruction modules through its normal internal API. It is not a verified compiler, a complete optimizer validator, a replacement for code review or a Rust-equivalent safety proof. The emitter and host C++ implementation remain trusted. Hardware/assembly callers must still uphold the documented bootstrap calling convention and canonical bool inputs.

## Regression evidence

`make -C compiler test` runs the existing source acceptance/rejection/execution cases and direct typed-IR tests. The latter include guard deletion/bypass/mismatch, uninitialized slots, invalid types, malformed symbols, unknown targets, parameter rebinding, unreachable stack effects, shrinking predecessor/loop states and control-flow joins. A maximum-size 4096-element initializer test also bounds retained snapshot facts deterministically rather than increasing a wall-clock timeout. See ARCHITECTURE.md for the reproduced resource failure, repair and remaining scaling limit.

`python3 tests/compiler/equivalence.py BASELINE CANDIDATE` compares deterministic accepted programs, exact eight-byte integer results, SIGILL failure paths and rejection diagnostics against a saved previous compiler. This bounded differential test is not an equivalence proof. The independent `tests/semantics` oracle predicts results without relying on either compiler.

Historical verification manifests are preserved. A previous executable used for differential checks is a temporary local artifact, not vendored source or a new runtime dependency.

## Remaining resource scaling

Basic-block snapshots remove the quadratic retained history of straight-line aggregate initialization. Currently, `State.initialized` and `State.maybeInitialized` use dense bits over the function's validated scalar-slot universe. Must-initialized joins use intersection and may-initialized joins use union. Other receiver/logical/object/capability facts, stacks, CFG and semantic decisions are unchanged. Negative/unknown offsets cannot become unchecked bit indices; slot-domain and allocation arithmetic follow existing frame limits.

Each of the two bitsets reserves `8 * ceil(declared_scalar_slots / 64)` logical payload bytes per retained state, even when its current facts are empty. `peakRetainedInitializationPayloadBytes` measures these word payloads only: it excludes the shared universe, container/allocator overhead, temporary states and every other fact collection. The original logical fact metric continues counting facts, not bits allocated. This representation improves dense-fact snapshots but can use more memory for sparse or empty states.

Dense storage depends on the complete declared universe even for empty facts,
so many sparse block-entry states can use more memory than node-based sets.
Other state, operand stacks, ASTs and allocations still scale with input. There
is no compiler-wide memory/time budget or universal improvement claim.

## Source-depth implementation limits

Parser-produced trees have bounded recursive depth: expression parsing128, block nesting128, type parsing64 and namespace components32. Constructed expression ASTs independently cap depth at128, including left-associative chains and postfix member/index chains that have shallow parser recursion. Child attachment checks precede retention of an over-deep tree, so normal rejection cannot leave an unbounded destructor chain. These caps address reproduced small-file stack overflows, not arbitrary internally forged ASTs or a general compiler-wide memory/work bound. Deep rejection tests disable core dumps and require normal exit1, no output and unchanged inputs.

## Capability and value boundaries

[Classes and values](VALUES.md), [bounded generics](GENERICS.md), [scalars](SCALARS.md), [ownership/views](OWNERSHIP.md) and [sealed services](SERVICES.md) specify current source and independent IR obligations. Every receiver, argument/result record, span, loan, owner and service grant has dedicated typed storage and lifetime operations; no scalar or layout metadata can manufacture authority. Spans use the current 56-byte tagged array/owner representation. Logical nested/empty fields still require complete initialization.

[Generated stack probes](STACK-GUARDS.md) touch each at-most-4096-byte downward reservation step. They require a valid starting stack and existing inaccessible guard; they do not bound recursion or establish kernel image admission.

Const non-template methods can expose a checked readonly view of their implicit
private fixed-u8 field. Source analysis and typed IR preserve the exact named
receiver binding/creation lifetime and field provenance; copies have independent
roots. This does not introduce general returned references or stored spans.
