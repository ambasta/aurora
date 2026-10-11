# Aurora language design

This is a proposed language contract and a map of unresolved work. Only the explicitly identified bootstrap subset should be expected to compile. The confirmed design brief is the performance of C, the safety of Rust, the object-oriented design of Java, TypeScript-style type-level expressiveness alongside compile-time and runtime reflection, and a recognizable modern C++ API and identity. Extreme safety, elegant modern design, and high performance are priorities. These are design and measurement targets, not guarantees already established. C source/ABI compatibility and unsafe legacy features are explicitly excluded; recognizable C++ syntax does not promise existing C++ source or library compatibility.

## Source model

Modules replace headers and textual inclusion. Declarations have one spelling and explicit visibility; there are no preprocessor macros, `struct` declarations, C-style casts, pointer arithmetic, unions that expose unchecked overlapping storage, or implicit foreign interfaces. Generic classes and functions are constrained by interfaces. Compile-time reflection and typed generation replace textual metaprogramming. Operator overloading, where admitted, obeys declared effects and cannot change evaluation or ownership rules.

All aggregate data uses `class`. A class describes fields and behavior; it does not imply heap allocation, reference identity, a virtual table, or garbage collection. Java-inspired encapsulation and interfaces organize APIs, while inline value semantics, deterministic lifetimes, and explicit ownership preserve systems-programming control. Interfaces do not mandate boxed objects, heap allocation, garbage collection, or implicit virtual dispatch. Static interface dispatch is preferred when a concrete type is known; dynamic dispatch must be explicit and its object lifetime checked. Composition is the default reuse tool; unrestricted implementation inheritance is deferred.

The current source form uses C++-recognizable typed declarations and designated initialization:

```aurora
module graphics;

class Point {
public:
    i64 x;
    i64 y;
};

auto answer() -> i64 {
    const Point p = Point{.x = 20, .y = 22};
    return p.x + p.y;
}
```

Class values can live inline rather than requiring allocation. The current compiler provides local scalar-field values; future storage policies may include stacks, arenas and explicitly owned allocations. Value semantics do not mean implicit copying of every future type: copyability must be checked and resource-owning classes must move. A future reference-oriented class model may have explicit identity through ownership-bearing handles, but identity must not require a particular allocation policy. Escaping stack identity is rejected. Final identity/lifetime rules require an RFC before implementation.

## Ownership and destruction

The target model distinguishes an owning value, an immutable borrow, and an exclusive mutable borrow. A move transfers responsibility and invalidates the source. Borrowing neither transfers ownership nor extends the owner's lifetime. Multiple readers or one writer may access a region, with a formal exception mechanism for validated synchronization primitives. Borrowing across asynchronous suspension needs explicit lifetime and mobility rules; it is not accepted merely because the syntax looks safe.

Every value must be initialized before observation. Scope exit destroys initialized owned values deterministically in reverse declaration order; partial construction unwinds only initialized fields. A moved value is not destroyed twice. Fallible cleanup uses an explicit operation before destruction. Destructors must not throw, await, or hide an unbounded operation. Forced process termination does not promise to execute destructors, so the kernel reclaims capabilities independently.

Shared ownership is an explicit library type with checked synchronization and a declared cycle policy. An optional managed runtime may collect objects within its own domain; garbage collection is not required for ordinary classes or the kernel profile. Ownership must remain valid across reflection, callbacks, generics, optimization, and shared-buffer IPC, not merely in direct local code.

## Defined behavior

Safe code must not manufacture dangling references, access uninitialized values, violate aliasing, or create data races. All indexing checks bounds unless a verified optimization proves the check redundant. Nullable values use an explicit optional type. Numeric conversions are explicit when information may be lost. The proposed target default for ordinary arithmetic overflow is a checked failure; wrapping and saturating operations would have explicit names. The current compiler checks signed addition, subtraction, multiplication, unary negation and division; overflow emits a fail-stop invalid-opcode trap. Division and remainder require i64 operands, evaluate them left-to-right exactly once, and share multiplication precedence with left associativity. Division truncates toward zero; remainder has the dividend sign or is zero. Both reject a zero divisor at a distinct defined invalid-opcode site. Minimum i64 divided by -1 overflows, while minimum i64 remainder -1 is explicitly zero without executing overflowing hardware division. Local fixed-array indexing checks bounds before address calculation. General memory-address arithmetic is not a source feature. Future allocation sizing, address calculations and DMA range calculations must likewise check overflow and bounds. Wrapping/saturating source operations are not currently implemented. Division by zero is implemented as a defined failure; the scalar reference defines invalid-count and representability failures. The exact error/trap boundary is part of each execution profile and must be tested consistently across backends.

Resource exhaustion and logic errors remain possible in safe programs. The public language target has no general-purpose unsafe escape hatch: unchecked casts, arbitrary pointer manufacture and access-control bypasses are excluded. Necessary machine operations belong to a minimal trusted implementation boundary with documented preconditions, capability checks and audited safe interfaces. The temporary C++/assembly bootstrap is such a trust boundary, not permission for source programs to disable safety. Its callers cannot turn off checks for unrelated code. Interrupts, MMIO, atomics, and DMA need semantic rules in addition to ordinary language memory semantics.

The [Rust Reference's undefined-behavior discussion](https://doc.rust-lang.org/reference/behavior-considered-undefined.html) is a useful checklist: it identifies data races, dangling or misaligned access, invalid values, and aliasing violations, and emphasizes that unsafe code must preserve soundness for safe callers. Aurora needs its own formal semantics and evidence; borrowing vocabulary does not provide these properties.

## Safe type-level algebra

The requested TypeScript inspiration means a future safe type algebra, including `keyof`-like member-key sets, mapped types and conditional types. These complement rather than replace compile-time reflection and Java-like runtime reflection. Their final Aurora spelling remains an RFC decision; no TypeScript source or runtime compatibility is intended.

A key query sees only members accessible in its declaration context. A mapped type constructs a new type description from eligible keys; it does not read, copy or transfer live fields. Materializing a value of that type still requires ordinary initialization, ownership and access checks. A transformation cannot copy an owning resource, turn a shared borrow into an exclusive one, remove a lifetime or expose a private representation. Immutable-to-mutable transformations of live storage are not implicit type operations.

Conditional types select a type under checked constraints, without evaluating runtime values or treating a type predicate as authorization. Generic instantiations must retain lifetime/effect obligations on every branch; variance rules must reject substitution that enables invalid writes. Type unions, optional members and shape refinement need explicit presence/discriminant checks before field access. Nominal resource identities and capability rights must not collapse into structurally similar public field shapes.

There is no `any`-like unchecked top type, assertion that forces an incompatible value into a type, or non-null assertion that suppresses validation. An unknown/dynamic value must be narrowed by checked evidence before use, with failure represented explicitly. Recursion and expansion limits make type computation resource-bounded and diagnostics tractable. Define normalization, equality and termination rules before promising broad expressive coverage. None of this general type algebra is implemented in the bootstrap.

## Compile-time reflection

A type descriptor can expose field names/types, declared interfaces, attributes, and eligible methods to a typed, deterministic compile-time evaluator. Private details remain module-private unless explicitly exported. Generated declarations go through the same type, ownership, visibility, and effect checks as handwritten source. Reflection must not forge lifetimes, expose raw offsets as unrestricted pointers, bypass initialization, or generate capabilities.

Resource limits prevent unbounded compilation. Generated source locations and expansion traces must survive into diagnostics. Compile-time execution is separate from host scripting; reproducible builds require declared inputs.

## Runtime reflection

The goal is Java-like runtime discovery and invocation with Aurora's ownership and authority rules. A module explicitly exports a reflection surface. Metadata distinguishes read-only inspection from invocation and mutation. A type identifier includes module identity and schema version; a matching display name is insufficient.

Reflective invocation requires a descriptor for an exported method, a receiver handle of the correct type, valid argument ownership modes, and every required effect/capability. The runtime validates these before dispatch and returns a typed success/error envelope. Dynamic arguments retain move/borrow state; invocation cannot duplicate an owning value. Returned borrows cannot outlive the receiver or arguments. Early implementations should prohibit dynamically returned borrows until their lifetime representation is specified and verified.

Reflective field mutation uses an exclusive borrow and cannot write private or immutable fields, violate class invariants, or skip constructors. There is no unrestricted accessibility override. Inspection alone grants no invocation authority. Missing metadata is a normal error, particularly in stripped kernel builds. Unloading must wait for descriptor and invocation leases to end, then invalidate the generation of all remaining handles.

Effects such as allocation, blocking, I/O, privilege, and asynchronous suspension are represented in signatures and descriptors. Kernel IRQ profiles prohibit effects they cannot safely execute. A dynamic call cannot erase those restrictions. Reflection is not a kernel debugger's arbitrary memory access API.

## Performance evidence

C-like performance is a benchmark goal, not a blanket zero-cost/no-overhead claim. Compare equivalent algorithms, layouts, semantics and error handling against optimized C implementations on named hardware and compiler versions. A C baseline with undefined behavior or missing validation does not establish a fair equivalent. Report throughput, latency distributions, memory use, binary size and build cost, including regressions and confidence limits.

Account separately for data layout/padding, allocations and lifetime bookkeeping, atomic operations and contention, static/dynamic dispatch, bounds/overflow checks, reflection metadata and invocation. Demonstrate when analysis removes a check without invalidating safety; do not remove checks just to win a benchmark. Kernel/real-time profiles need worst-case and interruption costs as well as averages. No comparative performance result has been established by returning 42 in an emulator.

## Implemented language

Use the [compiler reference](../compiler/README.md) for exact current syntax, supported values, ownership, modules, services and tool behavior. The goals above are design requirements; general type algebra, effects, concurrency and reflective invocation remain unimplemented.
