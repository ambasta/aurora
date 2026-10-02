# Aurora language design

This is a proposed language contract and a map of unresolved work. Only the explicitly identified bootstrap subset should be expected to compile. The objective is modern C++-inspired expressiveness with memory-safety guarantees comparable in ambition to Rust, without C/C++ compatibility or inherited unsafe defaults. Those guarantees have not been established.

## Source model

Modules replace headers and textual inclusion. Declarations have one spelling and explicit visibility; there are no preprocessor macros, `struct` declarations, C-style casts, pointer arithmetic, unions that expose unchecked overlapping storage, or implicit foreign interfaces. Generic classes and functions are constrained by interfaces. Compile-time reflection and typed generation replace textual metaprogramming. Operator overloading, where admitted, obeys declared effects and cannot change evaluation or ownership rules.

All aggregate data uses `class`. A class describes fields and behavior; it does not imply heap allocation, reference identity, a virtual table, or garbage collection. Composition and interfaces are the default abstraction tools; unrestricted implementation inheritance is deferred.

Illustrative target syntax, not accepted bootstrap input. The current compiler already accepts a smaller `class Point { x: i64; y: i64; }` form with local named initialization and scalar-field copies; it does not accept the ownership/function features in this target example:

```aurora
module graphics;

value class Point {
    let x: i64;
    let y: i64;
}

fn translated(p: borrow Point, dx: i64) -> Point {
    return Point(x: p.x + dx, y: p.y);
}
```

`value class` instances live inline, on a stack, in an arena, or inside an explicitly owned allocation. Value semantics do not mean implicit copying of every value. Copyability requires a compiler-checked property; resource-owning classes move. A proposed `reference class` has explicit identity and is accessed through ownership-bearing handles, but its storage policy remains explicit: it may be arena-managed or heap-owned. Escaping stack identity is rejected. Final spelling and identity/lifetime rules require an RFC before implementation.

## Ownership and destruction

The target model distinguishes an owning value, an immutable borrow, and an exclusive mutable borrow. A move transfers responsibility and invalidates the source. Borrowing neither transfers ownership nor extends the owner's lifetime. Multiple readers or one writer may access a region, with a formal exception mechanism for validated synchronization primitives. Borrowing across asynchronous suspension needs explicit lifetime and mobility rules; it is not accepted merely because the syntax looks safe.

Every value must be initialized before observation. Scope exit destroys initialized owned values deterministically in reverse declaration order; partial construction unwinds only initialized fields. A moved value is not destroyed twice. Fallible cleanup uses an explicit operation before destruction. Destructors must not throw, await, or hide an unbounded operation. Forced process termination does not promise to execute destructors, so the kernel reclaims capabilities independently.

Shared ownership is an explicit library type with checked synchronization and a declared cycle policy. An optional managed runtime may collect objects within its own domain; garbage collection is not required for ordinary classes or the kernel profile. Ownership must remain valid across reflection, callbacks, generics, optimization, and shared-buffer IPC, not merely in direct local code.

## Defined behavior

Safe code must not manufacture dangling references, access uninitialized values, violate aliasing, or create data races. All indexing checks bounds unless a verified optimization proves the check redundant. Nullable values use an explicit optional type. Numeric conversions are explicit when information may be lost. The proposed target default for ordinary arithmetic overflow is a checked failure; wrapping and saturating operations would have explicit names. This differs from the current bootstrap: its supported scalar arithmetic intentionally wraps modulo 2^64. No general indexing or memory-address arithmetic is implemented. Future indexing, allocation sizing, address calculations, and DMA range calculations must check overflow and bounds; wrapping scalar behavior must never silently authorize out-of-range memory access. In the target, division by zero and invalid shifts are defined failures. The exact error/trap boundary is part of each execution profile and must be tested consistently across backends.

Resource exhaustion and logic errors remain possible in safe programs. Unsafe machine operations are restricted to small privileged modules with documented preconditions and audited safe interfaces. Their callers cannot turn off checks for unrelated code. Interrupts, MMIO, atomics, and DMA need semantic rules in addition to ordinary language memory semantics.

The [Rust Reference's undefined-behavior discussion](https://doc.rust-lang.org/reference/behavior-considered-undefined.html) is a useful checklist: it identifies data races, dangling or misaligned access, invalid values, and aliasing violations, and emphasizes that unsafe code must preserve soundness for safe callers. Aurora needs its own formal semantics and evidence; borrowing vocabulary does not provide these properties.

## Compile-time reflection

A type descriptor can expose field names/types, declared interfaces, attributes, and eligible methods to a typed, deterministic compile-time evaluator. Private details remain module-private unless explicitly exported. Generated declarations go through the same type, ownership, visibility, and effect checks as handwritten source. Reflection must not forge lifetimes, expose raw offsets as unrestricted pointers, bypass initialization, or generate capabilities.

Resource limits prevent unbounded compilation. Generated source locations and expansion traces must survive into diagnostics. Compile-time execution is separate from host scripting; reproducible builds require declared inputs.

## Runtime reflection

The goal is Java-like runtime discovery and invocation with Aurora's ownership and authority rules. A module explicitly exports a reflection surface. Metadata distinguishes read-only inspection from invocation and mutation. A type identifier includes module identity and schema version; a matching display name is insufficient.

Reflective invocation requires a descriptor for an exported method, a receiver handle of the correct type, valid argument ownership modes, and every required effect/capability. The runtime validates these before dispatch and returns a typed success/error envelope. Dynamic arguments retain move/borrow state; invocation cannot duplicate an owning value. Returned borrows cannot outlive the receiver or arguments. Early implementations should prohibit dynamically returned borrows until their lifetime representation is specified and verified.

Reflective field mutation uses an exclusive borrow and cannot write private or immutable fields, violate class invariants, or skip constructors. There is no unrestricted accessibility override. Inspection alone grants no invocation authority. Missing metadata is a normal error, particularly in stripped kernel builds. Unloading must wait for descriptor and invocation leases to end, then invalidate the generation of all remaining handles.

Effects such as allocation, blocking, I/O, privilege, and asynchronous suspension are represented in signatures and descriptors. Kernel IRQ profiles prohibit effects they cannot safely execute. A dynamic call cannot erase those restrictions. Reflection is not a kernel debugger's arbitrary memory access API.

## Bootstrap subset

This minimal scalar program illustrates the supported source form:

```aurora
module kernel;
fn aurora_kernel_value() -> i64 {
    let x: i64 = 40;
    return x + 2;
}
```

The implemented compiler supports `i64`/`bool`, local bindings, expressions, branches, and direct x86-64 assembly emission. Scoped `own<i64>`, `ref<i64>`, and `mutref<i64>` demonstrate moves and shared/exclusive borrowing of local owned integers only. They are not a complete lifetime system and cannot establish heap or cross-function borrow safety. The kernel sample exercises these local ownership operations and returns 42.

Local class values now have actual independent stack storage, named field initialization, same-type value copies, direct field reads, and field writes through mutable local bindings. Fields are limited to `i64` and `bool`; every field is initialized exactly once. Classes cannot yet be nested, borrowed, used as function arguments/results, or contain owners/references. This is a real aggregate-value implementation, not a scalar alias, but it does not establish general class lifetime safety. The bootstrap uses padded eight-byte field slots and an internal layout, not a C-compatible layout promise.

`size_of`, `type_id`, and `field_count` provide compile-time information for builtins and declared classes; `static_assert` checks a restricted compile-time expression. `reflect_size` and `reflect_field_count` perform runtime lookups from IDs, returning zero for unknown IDs. Class IDs are declaration-order/module-local values, not globally stable identities. These queries do not implement member-name/type traversal, typed code generation, dynamic loading, reflective field access, or safe reflective invocation. Ordinary class field access is implemented; reflective field access is not. Supported scalar arithmetic intentionally wraps. See the [compiler reference](../compiler/README.md) for exact syntax and limitations, and the [verification record](verification.md) for final results; the latest class/reflection changes await final integration verification.

Methods, nested/general classes, heap ownership, destructor insertion, generics, interprocedural lifetime checking, concurrency soundness, runtime reflective invocation, effect checking, and a verified optimizer remain future work. A metadata dump is not Java-like runtime reflection. Rejection of a few use-after-move examples is not a proof of Rust-like safety.
