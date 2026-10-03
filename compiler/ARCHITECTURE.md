# Frontend, typed IR and native backend boundary

This milestone changes implementation architecture without intentionally changing the accepted language, diagnostics, machine-level behavior or compiler CLI. `aurorac INPUT.au -o OUTPUT.s` remains the interface. This is not an optimizer, a new ownership language, or a proof of compiler soundness.

## Pipeline and ownership of checks

1. `types.hpp` defines source types and common tokens/errors.
2. `lexer.hpp` turns bytes into tokens; `syntax.hpp` defines the untyped source AST; `parser.hpp` accepts the restricted safe C++ grammar.
3. `semantics.hpp` performs source-level name resolution, scalar/aggregate type checking, initialization rules, const/private access checking, ownership moves, lexical borrow checks and conservative branch/loop joins. It emits typed instructions, not assembly strings.
4. `ir.hpp` defines a target-independent accumulator/value-stack instruction model. Its operations include checked integer arithmetic, typed loads/stores, explicit control flow, metadata queries and array guard/access operations.
5. `ir_verify.hpp` validates a complete module and creates an immutable `ValidatedModule`. Only this validated wrapper can be passed to the emitter. It checks lower-level type, initialization, control-flow, operand-stack, frame and bounds-token invariants.
6. `x86.hpp` lowers validated operations to GNU x86-64 assembly. It has no source AST, scope lookup, const policy, owner-liveness state or borrow-state checker. Target registers, ABI argument placement, stack alignment and machine trap sequences exist only here.
7. `main.cpp` coordinates file I/O and those stages. GNU assembler/linker remain the bootstrap native toolchain.

The implementation uses internal header units and one translation unit so existing bootstrap commands that compile `main.cpp` continue to work. These are actual phase boundaries rather than separately named files wrapping the old assembly-text emitter. This packaging is not a stable external compiler-library API.

## Typed instruction model

The current value and temporary operand stack carry explicit scalar/reference payload types. Source owners lower to scalar payload slots after the source ownership checks succeed. Borrow bindings lower to typed compiler-internal stack handles. No instruction offers arbitrary address arithmetic, arbitrary indirect stores, source-level raw pointers or opaque assembly injection.

Locals/fields/elements have assigned eight-byte frame slots. The IR records slot payload types and complete frame size. Logical bool values remain canonical zero/one even though their current slots are eight bytes. Source class layout, padding and metadata are computed in semantic analysis; no new ABI layout claim is introduced.

`CheckedAdd`, `CheckedSubtract`, `CheckedMultiply` and `CheckedNegate` retain their fail-stop overflow requirement through lowering. Comparison and logical-not operations are distinct. The backend always emits the appropriate overflow branch for checked arithmetic. There is no unguarded arithmetic operation in this IR for source numeric expressions.

Call instructions identify validated local functions. Signature lookup establishes argument/result types, and typed value-stack entries carry arguments. Metadata queries are a closed enum, not arbitrary external symbol calls. Reflection descriptor contents are produced by source semantic analysis; the verifier checks descriptor shape, not a second derivation of class reflection metadata.

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

`make -C compiler test` runs the existing 203 source acceptance/rejection/execution cases and direct typed-IR tests. The latter include guard deletion/bypass/mismatch, uninitialized slots, invalid types, malformed symbols, unknown targets, parameter rebinding, unreachable stack effects, shrinking predecessor/loop states and control-flow joins. A maximum-size 4096-element initializer test also bounds retained snapshot facts deterministically rather than increasing a wall-clock timeout. See RESOURCE-NOTE.md for the reproduced resource failure, repair and remaining scaling limit.

`python3 tests/compiler/equivalence.py BASELINE CANDIDATE` compares deterministic accepted programs, exact eight-byte integer results, SIGILL failure paths and rejection diagnostics against a saved previous compiler. This bounded differential test is not an equivalence proof. The independent `tests/semantics` oracle predicts results without relying on either compiler.

Historical verification manifests are preserved. A previous executable used for differential checks is a temporary local artifact, not vendored source or a new runtime dependency.

## Remaining resource scaling

Basic-block snapshots remove the quadratic retained history of straight-line aggregate initialization. This does not make the whole verifier globally linear or resource bounded: initialized-slot sets are still copied at block entries, with retained memory proportional to block count times live slot facts. Branch-dense inputs can therefore use substantially more memory than equally large straight-line inputs. Compact fact sets and explicit compiler-wide resource budgets remain future hardening. The current regression targets the specific reproduced failure; it is not a general denial-of-service proof.
