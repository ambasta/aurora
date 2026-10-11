# Frontend, typed IR and native backend boundary

The typed-IR milestone established behavior-preserving compiler phase boundaries. The subsequent native-module stage adds explicit-root imports, namespaces, scoped reflection and hardened host I/O, while preserving existing scalar/ownership behavior. `aurorac INPUT.au -o OUTPUT.s` remains valid; imports additionally require `--module-root DIR`. This is not an optimizer, a new general ownership language, or a proof of compiler soundness.

## Pipeline and ownership of checks

1. `host_sources.hpp` owns the trusted Linux descriptor-relative source reader and atomic artifact writer. `modules.hpp` loads explicit-root module graphs and resolves names/exports in defining-module contexts; MODULES.md specifies that boundary.
2. `types.hpp` defines source types and common tokens/errors.
3. `lexer.hpp` turns bytes into tokens; `syntax.hpp` defines the untyped source AST; `parser.hpp` accepts the restricted safe C++ grammar.
4. `semantics.hpp` performs source-level name resolution, scalar/aggregate type checking, initialization rules, const/private access checking, ownership moves, lexical borrow checks and conservative branch/loop joins. It emits typed instructions, not assembly strings.
5. `ir.hpp` defines a target-independent accumulator/value-stack instruction model. Its operations include checked integer arithmetic, typed loads/stores, explicit control flow, metadata queries and array guard/access operations.
6. `ir_verify.hpp` validates a complete module and creates an immutable `ValidatedModule`. Only this validated wrapper can be passed to the emitter. It checks lower-level type, initialization, control-flow, operand-stack, frame and bounds-token invariants.
7. `x86.hpp` lowers validated operations to GNU x86-64 assembly. It has no source AST, scope lookup, const policy, owner-liveness state or borrow-state checker. Target registers, ABI argument placement, stack alignment and machine trap sequences exist only here.
8. `main.cpp` coordinates file I/O and those stages. GNU assembler/linker remain the bootstrap native toolchain.

The implementation uses internal header units and one translation unit so existing bootstrap commands that compile `main.cpp` continue to work. These are actual phase boundaries rather than separately named files wrapping the old assembly-text emitter. This packaging is not a stable external compiler-library API.

## Hosted Aurora expression parser

`expression_parser.au` parses complete statement expressions containing integer,
byte and bool literals, unqualified names, grouping, unary `-`/`!`/`~`, and all
existing binary precedence tiers. Initializers, return/static-assert expressions,
if/while conditions, expression statements and assignment operands enter this
path. An iterative Pratt state machine stores copied frames and AST nodes in
`expression_arena.au`; parser nesting and AST depth retain their separate bounds
of 128. Grouping retains the inner node's original token span.

The parser calls `lexer.au::next_lexeme` for every token and trivia boundary.
A local eligibility pass returns Unsupported for calls, qualified names,
member/index access, construction, strings and arrays. Existing non-consuming
host template lookahead protects template/call ambiguity, including exact `>>`
closer behavior. No supported prefix is committed: Unsupported falls back for
the whole expression with tokens and position unchanged. Empty/truncated or
otherwise malformed supported grammar, allocation/depth failure and malformed
private results reject. Constructor initializer expressions and recursive parsing
inside unsupported constructs remain on the C++ reference path.

`hosted_parser.cpp` and `hosted_parser.S` are trusted bootstrap adapters. Aurora
creates and consumes the arena; C++ only reserves opaque storage and imports the
same immutable source snapshot used by the lexer. Copied results contain named
status values, indices and source offsets. The adapter checks token/spelling/span
bounds, exact stopping delimiter, unique complete non-parenthesis token coverage,
subtree source order, child-before-parent order, arity, independently recomputed
depth and one connected non-sharing tree before committing position.
It constructs the existing `Expression` objects iteratively. All exits, including
fallback, syntax errors and host allocation exceptions, consume the Aurora owner
before the host Region closes. Semantic checking, typed IR and backend emission
consume this returned AST unchanged.

The hosted build stages exact exported lexer/arena files under their module paths,
then emits one parser/arena/lexer graph with `--local-symbols`; no overlapping
lexer object, second scanner or source concatenation is used. The existing C++
stage-0 seed remains able to build the graph. Compiler, source fixtures, formatter
and optional LSP link the same graph and hosted owner runtime. Standalone lexer
bootstrap regression remains separate. Focused parser/ABI and multi-stage corpus
checks do not replace final integrated GCC 16 full/image/guest qualification.

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

## CFG and frame invariants

The verifier follows all statically reachable successors, including both sides of conditional branches. It retains worklist snapshots only at basic-block entries (function entry, labels and conditional fallthrough), then walks each straight-line block with one mutable state. Reachability is recorded separately for every instruction. A loop is handled by worklist propagation until incoming abstract states stabilize. Source owner-liveness backedge rules remain the responsibility of semantic analysis; this lower pass tracks runtime initialization and value shapes.

- Function symbols must be identifiers and cannot collide with backend helper names. Calls must target a known function.
- Parameter bindings form the exact entry prefix in parameter order. They cannot be repeated later after calls have clobbered argument registers.
- Every slot access matches an allocated slot type, alignment and frame range.
- Loads and borrow handles require initialization. Array accesses require initialization of every element. Initialized-slot sets intersect at control-flow joins.
- Arithmetic, comparisons, calls, stores and returns require correct operand types. Bool constants must be zero/one.
- Labels are unique; all jump/branch targets exist, including targets in unreachable structural instructions.
- Temporary value/token stacks match at joins. Statement labels and jumps do not carry temporary stack entries. Returns have balanced stacks and correct result types.
- Reachable fallthrough without a return is rejected.
- Unreachable semantic instructions are rejected. Only unreachable structural `Jump`/`Label` artifacts are removed after analysis; this removes harmless jumps emitted after a returning branch and prevents invisible unreachable push/pop operations from confusing backend linear stack accounting.

Given those invariants, the backend's expression-stack depth agrees with reachable execution. It aligns the machine stack at each nested call. The semantic analyzer and verifier cap local frame storage at 65536 bytes; that bound does not eliminate target-stack exhaustion from call depth or expression temporaries.

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
