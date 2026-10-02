# Aurora bootstrap compiler

A genuine, deliberately small compiler written in C++23. It lexes and parses Aurora source into an AST, checks types and lexical ownership while emitting x86-64 GNU assembly, and uses the system assembler/linker. It does not translate Aurora to C or C++. Standard C++ library headers bootstrap the implementation; Aurora has no includes, macros, or C/C++ source-compatibility layer.

Build from the repository root:

```sh
make -C compiler
make -C compiler test
build/aurorac examples/kernel.au -o build/kernel-language.s
as --64 build/kernel-language.s -o build/kernel-language.o
```

## Implemented surface

```text
module demo;

fn plus(a: i64, b: i64) -> i64 {
    return a + b;
}

fn answer() -> i64 {
    static_assert(size_of(i64) == 8);
    let token: own<i64> = own(40);
    {
        let edit: mutref<i64> = borrow_mut(token);
        write(edit, read(edit) + 2);
    }
    let final: own<i64> = move(token);
    return read(final);
}
```

- One mandatory module declaration per source file. It is currently a label, not a separate-compilation/import system.
- `fn`, explicit parameter/result types, up to six scalar parameters, forward calls and recursion.
- `i64`, `bool`, `own<i64>`, `ref<i64>`, `mutref<i64>` and user-defined scalar-field class locals.
- Immutable `let` bindings; `let mut` for scalar reassignment and class field assignment. Initialization is mandatory. Lexical shadowing is allowed, duplicate names in one scope are rejected.
- Lexical blocks, `if (bool) { ... } else { ... }`, return statements. Functions must return on every path. Unreachable statements are rejected.
- Decimal literals, booleans, parentheses, unary `-` and `!`, `+`, `-`, `*`, `==`, `!=`, `<`, `>`, `<=`, `>=`.
- Arithmetic currently wraps modulo 2^64; ordering is signed. There is no division, shift, pointer arithmetic, or implicit scalar conversion. Positive literals must fit signed i64; the minimum value can be expressed as `-9223372036854775807 - 1`.
- `//` line comments.

## Actual safety boundary

`own<i64>` is an affine, stack-resident scalar capability. It is not a heap allocation or a general resource implementation. `own(value)` initializes it; `move(name)` transfers it and invalidates the old binding. No implicit owned-value copies are permitted. Dropping unused owners is allowed.

`borrow(owner)` creates a lexically scoped shared reference; `borrow_mut(owner)` creates an exclusive reference. Multiple shared references are permitted. Shared and exclusive borrows cannot overlap. Owners cannot move while borrowed, and cannot be read through the owner while exclusively borrowed. `read` copies the scalar value through an owner or reference; `write` changes it through a mutable reference and returns the written i64. Borrow lifetimes end at the declaring block's end, even if their last use was earlier.

References cannot be returned, passed to functions, copied, rebound, or stored in another value. Borrowing references is unsupported. This deliberate restriction avoids reference escape in this subset. References may only target already-declared owners. At conditional joins, an owner is considered moved if any continuing path moved it; terminated return paths do not contaminate continuing paths. Constants do not eliminate branches during checking.

These checks are meaningful within this restricted scalar language. They are not a claim of a production-complete Rust-equivalent safety system. Classes currently contain only copyable scalar fields. There are no methods, inheritance, nested class fields, arrays, heap allocation, destructors, generics, threads, concurrency rules, unsafe blocks, or foreign calls yet. Stack exhaustion through deep recursion remains possible. Hardware/bootstrap assembly is outside these language checks.

## Class values

```text
class Point {
    x: i64;
    y: i64;
}

fn class_demo() -> i64 {
    let mut p: Point = Point { y: 22, x: 20 };
    let snapshot: Point = p;
    p.x = 40;
    return snapshot.x + snapshot.y;
}
```

Class declarations may precede or follow functions. Fields must be `i64` or `bool`, and field names must be unique. Every field must be initialized exactly once; named fields may appear in any order. Initializer expressions evaluate in written order, before the new local enters scope. Uninitialized field reads, unknown fields, type mismatches and mismatched constructors are rejected.

A same-type class local initializer copies every scalar field into independent stack storage. Mutating the original does not change the copy. Field writes require `let mut`; the field's type cannot change. Whole-class reassignment is not yet supported. Class values cannot currently be function arguments/results, contain ownership/reference fields, or be borrowed. `own<Point>` is rejected. These restrictions prevent silently inventing aggregate ownership/escape semantics.

Each scalar field currently occupies an aligned eight-byte slot, including bool fields. Fields appear in declaration order. The complete class size is eight times its field count, with a minimum of eight bytes for empty classes. This padded bootstrap layout is internal to Aurora, not a C-compatible layout guarantee. The compiler generates direct offset-based field loads, stores and copies; classes are not a cosmetic alias for i64.

See `examples/class_values.au` for a runnable function combining immutable snapshots, field mutation and reflection. Methods, generics, nested values and general ownership are later language stages.

## Working reflection

`size_of(Type)`, `type_id(Type)` and `field_count(Type)` are compile-time values for builtins and user-defined classes. `static_assert(bool_expression)` verifies a restricted constant expression: literals, these reflection queries, comparisons and logical negation. Arithmetic in static assertions is currently rejected.

Stable bootstrap type IDs: i64 = 1, bool = 2, own<i64> = 3, ref<i64> = 4, mutref<i64> = 5. Sizes are respectively 8, 1, 8, 8, 8 bytes. The backend uses eight-byte stack slots even for bool; reflected bool size is the language value size, not a promise of a packed user layout.

`reflect_size(id)` and `reflect_field_count(id)` perform actual runtime lookups for dynamic i64 IDs; unknown IDs return zero. Scalar/ownership builtins have zero fields. Class IDs begin at 100 in declaration order and are deterministic within this module, not globally stable identifiers. Class size/count metadata is derived from the same definitions as actual field code generation. Member names/type traversal and compile-time code generation are deferred.

## Machine interface

The temporary freestanding bridge uses the scalar subset of the x86-64 System V register convention: arguments RDI, RSI, RDX, RCX, R8, R9; result RAX. Functions preserve RBP and do not touch RBX/R12–R15. RSP is aligned to sixteen bytes immediately before each call; callers must enter with the corresponding standard alignment. No red-zone use, stack protector, runtime library, SIMD, dynamic allocation, or libc dependency is generated. Bool values are canonical zero/one; external assembly callers must uphold that invariant.

Function names are exported without mangling for the bootstrap bridge. Runtime reflection exports `aurora_reflect_size` and `aurora_reflect_field_count`, so separately compiling and linking multiple modules is not supported yet. The compiler emits no source-level C ABI or compatibility syntax; the register convention is purely the current assembly integration contract.

`examples/kernel.au` exports `aurora_kernel_value()`, which returns 42 after a real mutable borrow and ownership move. Assembly entry/exit and hardware I/O remain in the kernel bootstrap.

## Long-term scope

This compiler is a staged bootstrap toward a self-hosted, safe-by-default systems language and a native operating-system ecosystem. Full modern C++ expressiveness, self-hosting, assembler/linker tools, package tooling, graphical composition and terminal applications are goals, not implemented capabilities of this milestone. The kernel's planned Zen/RDNA hardware coverage likewise does not establish physical-device support. No source-level unsafe blocks or C foreign-function compatibility feature is provided.
