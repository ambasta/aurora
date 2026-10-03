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

Safe code must not manufacture dangling references, access uninitialized values, violate aliasing, or create data races. All indexing checks bounds unless a verified optimization proves the check redundant. Nullable values use an explicit optional type. Numeric conversions are explicit when information may be lost. The proposed target default for ordinary arithmetic overflow is a checked failure; wrapping and saturating operations would have explicit names. The current compiler checks signed addition, subtraction, multiplication, unary negation and division; overflow emits a fail-stop invalid-opcode trap. Division and remainder require i64 operands, evaluate them left-to-right exactly once, and share multiplication precedence with left associativity. Division truncates toward zero; remainder has the dividend sign or is zero. Both reject a zero divisor at a distinct defined invalid-opcode site. Minimum i64 divided by -1 overflows, while minimum i64 remainder -1 is explicitly zero without executing overflowing hardware division. Local fixed-array indexing checks bounds before address calculation. This replaces the earlier checkpoint’s wrapping scalar behavior without a compatibility mode. General memory-address arithmetic is not a source feature. Future allocation sizing, address calculations and DMA range calculations must likewise check overflow and bounds. Wrapping/saturating source operations are not currently implemented. Division by zero is implemented as a defined failure; the unsigned shift contract below defines invalid-count and representability failures. The exact error/trap boundary is part of each execution profile and must be tested consistently across backends.

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

## Bootstrap subset

This minimal scalar program illustrates the supported source form:

```aurora
module kernel;
auto aurora_kernel_value() -> i64 {
    const i64 x = 40;
    return x + 2;
}
```

The implemented compiler uses `auto name(Type parameter) -> Result` for functions, typed local declarations, `const` for immutable local values, and ordinary typed locals for mutation. Parameters are currently immutable. Local `auto` inference is not implemented. The old `fn`/`let` and colon-typed declarations are rejected; their earlier milestone receipts remain historical.

The subset includes `i64`/`u64`/`bool`, local bindings, expressions, branches, `while` loops and direct x86-64 assembly emission. There is no `break` or `continue`. Loop checking conservatively accounts for zero iterations and requires outer owner state to remain live on continuing backedges; moves on terminating return paths are distinct. This restricted rule is not a general loop/lifetime proof.

Scoped `own<i64>`, `ref<i64>`, and `mutref<i64>` demonstrate moves and shared/exclusive borrowing of local owned integers only. Ownership bindings are non-rebindable. A const owner cannot be mutably borrowed or moved into a mutable owner; a const mutable-reference binding cannot write. These checks cannot establish heap or cross-function borrow safety. The kernel sample exercises local ownership operations and returns 42.

Local class values have independent stack storage, same-type value copies and access-checked field reads/writes. Fields are private by default. Since milestone005, a class can declare one constructor with a complete initializer list and empty body, plus scalar methods using `auto get() const -> i64` or mutable `auto add(i64 amount) -> i64`. Constructor arguments evaluate left-to-right; field initializers then run in declaration order without receiver access. Declaring a constructor disables designated construction, so private state cannot be manufactured through aggregate syntax. Classes without constructors retain the earlier public-field designated initialization rules. Fields are limited to `i64`, `u64` and `bool`. Nested/resource fields, class parameters/results on methods and constructors, and source-visible class references remain unsupported. Ordinary functions support the bounded value-only contract below. Padded eight-byte field slots are internal bootstrap layout, not a C-compatible promise.

Method receivers are local class values or implicit sibling-call reborrows. All scalar argument evaluation finishes before acquiring the call-duration receiver capability; `counter.add(counter.get())` is therefore defined. Const receivers allow readonly methods only. No source `this` pointer, receiver conversion, escaping borrow or arbitrary offset is available. Private members bind in the declaring class/module. Typed IR checks nominal layouts, lexical object lifetimes, full initialization and readonly/exclusive receiver permission. Every call-graph cycle containing a constructor or method is conservatively rejected, including scalar-helper intermediaries; ordinary scalar recursion still works and no whole-program termination/stack bound is claimed. See [the exact class contract](../compiler/CLASSES.md).

The verified milestone006 compiler adds by-value class parameters and results on ordinary functions. Parameters are immutable independent copies. Class arguments must be complete local names and are snapshotted at their position in left-to-right argument evaluation; a later mutation cannot alter an earlier argument. Class-returning calls initialize typed locals, and a class return names a complete local or parameter. Each boundary class is limited to 64 scalar fields and a function still accepts at most six total parameters. This does not bound whole-program stack use. No ownership/reference transport, caller alias, or class result on a method is introduced.

Exported function signatures cannot expose private nominal types. Every caller must directly see all class types in the signature, so a factory import does not implicitly reexport its dependencies' types. The private native call-record/result-storage convention is distinct from the scalar bootstrap seam: explicit IR verifies nominal layouts, immutable argument snapshots, complete returns, active lifetimes and disjoint storage. Hidden addresses never become scalar IR values or source references. See [the exact value-call contract](../compiler/VALUE-CALLS.md).

`std.numeric` now has an Aurora scalar-specialized `std::minmax` returning `std::MinMax`, plus checked `std::range_width` consuming a value copy. The milestone006 checkpoint passed 59 value-call cases, 206 direct IR cases and four injected-variant exhaustive-dispatch compile checks, as well as existing suites, sanitizers and final integration verification. Those receipts remain historical. No generic-library completeness or equivalent-C performance result is claimed.

The reviewed milestone007 compiler implements `std.integer`: nonnegative `std::gcd` and `std::lcm`, checked for representability, plus `std::div` returning an independent `std::DivResult` with private quotient/remainder and readonly `quot()`/`rem()`. `gcd(0,0)` is zero; `lcm` is zero if either argument is zero. Signed Euclid avoids premature absolute-value overflow, and lcm divides before multiplication. The result-pair constructor performs checked division, so minimum/-1 cannot construct a pair even though remainder alone would be zero. These are i64-specialized freestanding APIs. The candidate passes 84 integer cases, 216 direct IR cases, six exhaustive-dispatch checks and 1,510 independent integer-oracle cases with 181 exact trap-site checks, including sanitizer runs. Independent compiler review passed; final milestone007 integration verification passed. The oracle uses unbounded mathematics and explicit truncation, and rejects hardware divide exceptions as compiler defects. See [the integer contract](../compiler/INTEGERS.md). General constant-expression arithmetic, broader numeric conversions and generic numeric APIs remain deferred.

The reviewed milestone008 compiler adds `u64`, exact decimal `u64`-suffixed literals, checked unsigned arithmetic and explicit cross-type `u64(i64)`/`i64(u64)` conversions. Values never implicitly mix with i64 or bool; unsigned unary minus is rejected. `~`, `&`, `|` and `^` operate on exactly 64 bits. Shifts require a u64 operand and i64 count, evaluated left-to-right once. Counts outside 0..63 reach a distinct shift-count trap before hardware masking; left shift traps if its mathematical result is unrepresentable, while right shift zero-fills. No wrapping arithmetic, reinterpretation or source address conversion is added. U64 fields, arrays and ordinary class-value calls preserve exact types and existing initialization/const/copy rules. Builtin type ID8 and `array<u64,N>` IDs `2000000+N` preserve earlier IDs and eight-byte storage. Ownership/reference types remain i64-only. See [UNSIGNED.md](../compiler/UNSIGNED.md).

`std.bit` supplies scalar-specialized `std::popcount(u64)->i64`, `std::bit_width(u64)->i64` and `std::has_single_bit(u64)->bool`, compiled from real freestanding Aurora source. The candidate passes 95 unsigned source cases, 385 direct IR cases, ten exhaustive-dispatch checks and a default independent oracle with 4,219 native cases, 501 exact trap-site checks and 67 rejection fixtures. Independent alternate-seed runs cover 6,665/766 and 8,959/1,044 native cases/traps, with overlapping coverage; counts must not be summed. Existing suites and sanitizer gates pass. Independent compiler review passed; final milestone008 integration verification passed. This is no general generics, global resource-bound or performance claim.

The reviewed milestone009 compiler implements explicit Scalar-constrained class templates: `template <Scalar T, Scalar U> class pair { ... };`, with one or two parameters and concrete arguments restricted to i64/u64/bool. Type placeholders substitute into scalar fields, method/constructor signatures, locals and reflected types before ordinary checking. Every requested specialization's methods are checked; unrequested body semantics are not claimed valid. Bodies retain their defining module's helper bindings and privacy. One defining declaration and ordered scalar tuple has one nominal identity, distinct from other tuples even when layouts match. Reflection describes concrete graph-local types, and cannot instantiate a type at runtime. Limits are 64 template definitions and 256 requested specializations per graph, in addition to existing depth/frame and 64-field/six-argument value-call bounds. These are not global compiler memory or stack guarantees.

`import std.utility;` supplies the real `std::pair<T,U>` with complete constructor initialization, public exact-type first/second values, const enforcement and independent copies across ordinary function boundaries. All nine scalar tuples are tested. There is no deduction, function template, nested template argument, recursive instantiation, specialization override, general concept or dependent `T(value)` conversion. Explicit template-id references inside template bodies are rejected; the injected self-class name refers only to the same concrete class. This stage passes 117 template tests, 393 IR cases, ten exhaustive-dispatch checks and existing suites/sanitizers. Independent compiler review passed; final milestone009 integration verification is pending. See [TEMPLATES.md](../compiler/TEMPLATES.md).

Local fixed arrays use forms such as `const array<i64, 4> values = {10, 20, 5, 7};`. Elements are scalar, storage copies by value, `len(values)` reports length, and indexing is checked for reads and stores. Current limits are 1–4096 elements, eight-byte element slots including bool, and a 65536-byte frame cap. Arrays are not general generics, heap collections or interprocedural aggregate borrowing. Deep recursion can still exhaust the stack; a frame cap alone cannot prevent it.

`size_of`, `type_id`, and `field_count` provide compile-time information for supported types; `static_assert` checks a restricted constant expression. `reflect_size` and `reflect_field_count` perform runtime lookup from IDs, returning zero for unknown IDs. Metadata includes declared classes and mentioned array types. Class field counts expose public fields only, while class size includes private storage layout; size is deliberately an observable representation property, not permission to access private fields. Class/type IDs are compilation-graph-local metadata, not globally stable identities; defining-module views constrain availability. These queries do not implement member-name/type traversal, mapped/conditional types, typed code generation, dynamic loading, reflective field access or safe reflective invocation.

The syntax, arrays, loop and checked-arithmetic expansion is implemented; independent review and fresh aggregate integration verification passed for this checkpoint. See the [compiler reference](../compiler/README.md) for exact grammar and the [verification record](verification.md) for tested snapshots. Historical results do not establish the new semantics.

General constructor bodies, method overloads, inheritance, nested/general classes, heap ownership, destructor insertion, general generics, the safe type algebra, interprocedural lifetime checking, concurrency soundness, runtime reflective invocation, effect checking and a verified optimizer remain future work. Metadata lookup is not full runtime reflection. Rejection tests and fail-stop checks are not a proof of Rust-like safety.
