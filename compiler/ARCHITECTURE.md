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

## Typed instruction model

The current value and temporary operand stack carry explicit scalar/reference payload types. Source owners lower to scalar payload slots after the source ownership checks succeed. Borrow bindings lower to typed compiler-internal stack handles. No instruction offers arbitrary address arithmetic, arbitrary indirect stores, source-level raw pointers or opaque assembly injection.

The IR records typed byte-addressed slots and complete frame size. U8 fields/elements use width one; previous scalar storage stays width eight, including canonical bool values. Logical class shapes and canonical byte offsets/alignment/reserved extents are distinct. The verifier recomputes physical metadata from nominal shape, rejects conflicting supplied maps and checks occupied-byte disjointness. The backend consumes the validated map; packed loads zero-extend and padding is initialized without making it a source field. See BYTES.md for the developing representation gate.

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

`make -C compiler test` runs the existing source acceptance/rejection/execution cases and direct typed-IR tests. The latter include guard deletion/bypass/mismatch, uninitialized slots, invalid types, malformed symbols, unknown targets, parameter rebinding, unreachable stack effects, shrinking predecessor/loop states and control-flow joins. A maximum-size 4096-element initializer test also bounds retained snapshot facts deterministically rather than increasing a wall-clock timeout. See RESOURCE-NOTE.md for the reproduced resource failure, repair and remaining scaling limit.

`python3 tests/compiler/equivalence.py BASELINE CANDIDATE` compares deterministic accepted programs, exact eight-byte integer results, SIGILL failure paths and rejection diagnostics against a saved previous compiler. This bounded differential test is not an equivalence proof. The independent `tests/semantics` oracle predicts results without relying on either compiler.

Historical verification manifests are preserved. A previous executable used for differential checks is a temporary local artifact, not vendored source or a new runtime dependency.

## Remaining resource scaling

Basic-block snapshots remove the quadratic retained history of straight-line aggregate initialization. In this isolated representation-only candidate, `State.initialized` and `State.maybeInitialized` use dense bits over the function's validated scalar-slot universe. Must-initialized joins use intersection and may-initialized joins use union. Other receiver/logical/object/capability facts, stacks, CFG and semantic decisions are unchanged. Negative/unknown offsets cannot become unchecked bit indices; slot-domain and allocation arithmetic follow existing frame limits.

Each of the two bitsets reserves `8 * ceil(declared_scalar_slots / 64)` logical payload bytes per retained state, even when its current facts are empty. `peakRetainedInitializationPayloadBytes` measures these word payloads only: it excludes the shared universe, container/allocator overhead, temporary states and every other fact collection. The original logical fact metric continues counting facts, not bits allocated. This representation improves dense-fact snapshots but can use more memory for sparse or empty states.

The sparse tradeoff is observable in valid source: 2,048 empty branch diamonds before four initialized 4,096-byte arrays used 189,692 KiB with the baseline and 210,048 KiB with this candidate in one bounded run, with identical assembly. An IR-only 65,536-unused-slot/1,537-state case reserves 25,182,208 payload bytes despite zero initialized facts. These counterexamples prohibit a universal memory or speedup claim. No compiler-wide memory/time budget is introduced; state count, stacks, remaining node-based facts, AST and other allocations still depend on program structure. See RESOURCE-NOTE.md for dense improvements, sparse costs, exact limits and pending acceptance.

## Source-depth implementation limits

Parser-produced trees have bounded recursive depth: expression parsing128, block nesting128, type parsing64 and namespace components32. Constructed expression ASTs independently cap depth at128, including left-associative chains and postfix member/index chains that have shallow parser recursion. Child attachment checks precede retention of an over-deep tree, so normal rejection cannot leave an unbounded destructor chain. These caps address reproduced small-file stack overflows, not arbitrary internally forged ASTs or a general compiler-wide memory/work bound. Deep rejection tests disable core dumps and require normal exit1, no output and unchanged inputs.

## Encapsulated receiver boundary

See [CLASSES.md](CLASSES.md) for the source and IR contract. Nominal class layouts, lexical object lifetimes, constructor completion and readonly/exclusive receiver permissions are explicit in IR. Methods use a separate capability-bearing call instruction; receiver addresses cannot enter the scalar operand stack or be stored in source-visible slots. Constructor/method entrypoints retain their defining-module reflection scope. The semantic frontend remains trusted for lexical privacy and name resolution.

## Ordinary class-value calls

[VALUE-CALLS.md](VALUE-CALLS.md) specifies immutable independent parameter copies and complete nominal class returns. AggregateCall, BindObjectParameter and ReturnObject preserve value boundaries explicitly; hidden record/result capabilities never enter scalar operands. The verifier rejects incomplete, mutable or aliasing snapshots/results and mismatched nominal layouts. Exported signature type privacy and direct-import availability are resolved by the frontend. Backend and verifier dispatch are compile-time exhaustive so an added instruction variant cannot silently produce partial successful output.

## Checked division boundary

CheckedDivide/CheckedRemainder retain zero and signed-overflow guards as part of the lowering operation. No native IDIV is issued for zero divisors or the minimum/-1 pair; remainder handles the latter as zero. The dedicated division-zero UD2 label is distinct from checked arithmetic overflow. Integer enum switches are exhaustive under warning-as-error builds, and mutation tests cover both future enum members and instruction variants. See [INTEGERS.md](INTEGERS.md).

## Unsigned arithmetic boundary

U64 is an exact scalar IR type. BinaryValue carries its operand type; shifts require u64 data and an i64 count. Convert accepts only checked cross-type i64/u64 conversions and clears bounds evidence. Unary complement is fixed to 64 bits. All array/class/value-call payload checks preserve the exact scalar type. Count validation and representability checks belong to the checked shift lowering operation, with distinct invalid-count and overflow UD2 sites. See [UNSIGNED.md](UNSIGNED.md); no scalar integer can become a receiver, record, result or borrow capability.

## Bounded class-template expansion

`templates.hpp` deep-copies and substitutes explicit scalar arguments into concrete class ASTs. Module resolution owns defining-module identity, visibility, deduplication and request caps. Unexpanded parameter and template-argument metadata are rejected at the concrete boundary; no generic operation enters native IR. Ordinary nominal class/receiver/value-call checks apply unchanged. See [TEMPLATES.md](TEMPLATES.md) for the precise restricted domain and remaining resource limits.

## Private fixed-array fields

ClassFields logical shapes partition the flat classLayouts leaves exactly. Constructor-only zero initialization accounts for every array leaf. Receiver-array guard evidence identifies nominal receiver, logical field, element type and range; indexed operations require it independently of local-array tokens. Whole-class value copies and ABI staging use the flattened leaf layout, with a64-leaf class boundary cap. Scalar receiver instructions cannot reinterpret array fields. Capacity parameters disappear during typed substitution; no source integer becomes an address. See [FIXED-CONTAINERS.md](FIXED-CONTAINERS.md).

## Composed-value boundary in development

Logical fields may name a concrete nominal child class with an exact flattened
leaf range. A bounded acyclic containment walk checks depth and layout; empty
children retain logical completion facts. CopyObject, ObjectFieldCopy and
InitializeObjectField are the only operations that establish nested value
completion. Scalar stores cannot forge it. Constructor class arguments use
readonly independent records, with a separately saved receiver capability.
[COMPOSED-VALUES.md](COMPOSED-VALUES.md) states the source and verification contract;
final validation is pending.

## Closed enums and composed method results

The milestone012 candidate adds declared enum types and EnumConstant, with exact
case/type checks through value slots, fields and calls. Arithmetic and array
elements keep their original numeric domains. MethodCall retains constructor
objectArguments and appends resultOffset, selecting separate saved receiver and
record/result slots. Recursive ClassField metadata and logical object completion
remain the basis of copies and returns. The fixed-instance nominal arguments
available to a generated template body do not widen runtime descriptor views.
See [ENUM-RESULTS.md](ENUM-RESULTS.md); compiler review passed and final integration is pending.

## Readonly span invocation boundary (milestone014 candidate)

Byte-array origins have explicit BeginArray/EndArray lifetimes. Typed span spills
are disjoint sixteen-byte capability reservations, never scalar slots. BorrowSpan
requires a complete active owner; ReborrowSpan preserves its root and direct
parent. EndSpan rejects live children, and EndArray rejects outstanding borrows.
Continuing CFG states must agree on all active origins and capabilities. Store
validation rejects mutation through any original array element while borrowed.

BindSpanParameter belongs to the canonical entry prefix. AggregateCall retains
its existing objectArguments/resultOffset contract and adds independent positional
spanArguments. All class/scalar/span record offsets are explicit; the six-source-
parameter limit does not become twelve scalar registers. Span-bearing functions
use private native identities/local linkage. SpanLoad combines the bounds check
and typed byte load; no separated pointer or length can bypass it. The analyzer
also enforces lexical scope and source-level restrictions described in SPANS.md.
This remains a narrow synchronous static-borrow candidate, not general lifetime
polymorphism or a runtime borrow checker.
