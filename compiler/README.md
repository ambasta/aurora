# Aurora safe C++ dialect bootstrap

Aurora is a deliberately incompatible, safe-by-default C++ dialect under development. This is a small executable subset, not a complete C++ implementation or a production safety guarantee. The C++23 bootstrap compiler has its own lexer, AST, type/lifetime checks and x86-64 assembly emitter. It does not translate Aurora into C. Host standard-library headers and the isolated Linux descriptor-I/O adapter are temporary implementation machinery; the language has no C header, macro, raw-pointer, unsafe-block or foreign-C-ABI feature.

```sh
make -C compiler
make -C compiler test
build/aurorac examples/kernel.au -o build/kernel-language.s
as --64 build/kernel-language.s -o build/kernel-language.o
```

## Current syntax

```text
module demo;

class Point {
public:
    i64 x;
    i64 y;
};

auto answer(i64 input) -> i64 {
    const Point origin = Point{.x = 20, .y = 22};
    i64 total = input;
    const array<i64, 2> values = {origin.x, origin.y};
    i64 index = 0;
    while (index < len(values)) {
        total = total + values[index];
        index = index + 1;
    }
    return total;
}
```

- Each file declares `module name;` or an importable `export module name;`. Named imports, export visibility and namespace blocks now work with explicit `--module-root` directories; see MODULES.md. Separate binary compilation/linking remains deferred.
- Functions use `auto name(Type parameter) -> ReturnType`. Up to six scalar or bounded scalar-field class parameters, forward calls and ordinary-function recursion work. Class values use a separate checked native value-call convention; see VALUE-CALLS.md. Parameters are immutable in this bootstrap subset; an explicit parameter `const` qualifier is not parsed yet. This restriction is intentionally narrower than standard C++. Local `auto` deduction is not implemented yet.
- Local declarations are `const Type name = initializer;` or `Type name = initializer;`. Initialization is mandatory. Const scalar/aggregate locals cannot be assigned; unqualified scalar locals and scalar fields/elements of unqualified aggregates can be assigned. Ownership binding rules are stricter below.
- Scalar types are `i64` and `bool`. There are explicit ownership/reference types, local class values and fixed-size scalar arrays.
- Blocks, `if (bool) { ... } else { ... }`, `while (bool) { ... }`, `return`, and `static_assert` are supported. `break`, `continue`, and `for` are deferred.
- Functions must return on every statically continuing path. A while-loop is conservatively allowed to run zero times even for literal `true`, so it does not by itself prove a function returns. Unreachable statements following an unconditional return are rejected.
- Decimal integers, booleans, parentheses, unary `-`/`!`, `+`, `-`, `*`, and comparisons `== != < > <= >=` are supported. There are no implicit scalar conversions, division, shifts, pointer arithmetic, increment operators, or short-circuit boolean operators yet.
- `//` comments are supported. Previous `fn`/`let` prototype syntax is rejected. This intentional source break follows the project's C++ identity; conventional C declarations such as `int main()` are also rejected.

## Defined integer and evaluation semantics

Signed i64 addition, subtraction, multiplication and negation are checked. Overflow branches to the compiler's fail-stop `UD2` trap rather than wrapping or executing with undefined arithmetic behavior. Both `9223372036854775807` and `-9223372036854775808` are expressible; an out-of-range positive literal is rejected. Negating the minimum value traps. No wrapping operation is currently offered.

Operands and function arguments evaluate left to right. Designated class and array initializers evaluate in written order before the new binding enters scope. Constructor arguments evaluate left-to-right; constructor field initializer expressions then evaluate in field declaration order. Class names and initializer fields are statically checked. Array assignment evaluates its index once, checks bounds, then evaluates the right-hand side once and stores. An invalid index traps before evaluating the right-hand side or computing a memory address.

Fail-stop means no recovery or unwinding is promised. On the hosted Linux test harness, `UD2` is observed as specifically SIGILL; other signals and timeouts fail the tests. In the bootstrap kernel, the hardware invalid-opcode exception must be handled by its trusted fail-stop exception path. No destructor or cleanup semantics are implied by these traps.

## Owned scalar safety and const

```text
own<i64> seed = own(40);
{
    mutref<i64> edit = borrow_mut(seed);
    write(edit, read(edit) + 2);
}
const own<i64> answer = move(seed);
```

`own<i64>` is an affine stack-resident scalar capability, not a heap allocation or a general resource implementation. `own(value)` initializes it; `move(name)` transfers its value and invalidates the old binding. Owners never support reassignment, even without `const`; unused owners may be dropped. Implicit owner copies are rejected.

`borrow(owner)` creates a shared reference. `borrow_mut(owner)` creates an exclusive reference and requires a non-const owner. Multiple shared references may coexist; shared/exclusive borrows cannot overlap. A borrowed owner cannot move, and an exclusively borrowed owner cannot be read through its original binding. `read` copies a scalar value through an owner/reference; `write` changes it through a non-const mutable-reference binding and returns the written value.

Const is deliberately stronger than shallow C++ smart-pointer constness: a const owner cannot be mutably borrowed, nor moved into a mutable owner. Moving it to another const owner is permitted. A `const mutref<i64>` binding cannot write through that binding. This does not provide arbitrary casts, type assertions or a way to remove constness.

Borrow lifetimes end at the declaring block's end, not at inferred last use. References cannot be returned, passed to functions, copied, rebound, placed in aggregates, or borrowed again. They target already-declared scalar owners only. At conditional joins an owner is unavailable if any continuing path moved it; return-only paths do not constrain later code. Unsupported reference escape and aggregate borrowing fail closed.

## Precise while-loop ownership rule

The compiler records incoming owner-liveness and borrow state before the condition. It checks the condition and body once under that state. Each continuing backedge must preserve every incoming local's owner-liveness and borrow counts; moving an outer owner on any continuing path is rejected, even if the condition is a constant or appears to permit just one iteration. Moves on paths that definitely return are permitted because those paths never take the backedge.

Body-local owners may be created, moved and dropped on each iteration. Body-local borrows expire at the iteration block's end. Existing outer references can be read/written according to their capability. Since the condition can initially be false, exit state restores incoming ownership facts; scalar/aggregate value mutations remain real runtime effects. Nested loops obey the same rule. There is no claimed general fixed-point lifetime solver, loop escape reference model or `break`/`continue` behavior yet.

## Class value types and visibility

Classes are private by default and end with `;`. `public:` and `private:` control fields, constructors and methods. Classes can now declare a single complete initializer-list constructor and scalar methods with readonly `const` or mutable receivers. See [the exact constructor, method and scoped receiver contract](CLASSES.md). Classes without constructors retain public-field designated construction; constructor-bearing classes reject that shortcut.

Fields must be `i64` or `bool` and have unique names. Named construction uses `Point{.x = 20, .y = 22}`. Each field must be initialized exactly once; named fields may appear in any order and evaluate in written order. Unknown fields, missing fields and type mismatches are rejected.

`const Point snapshot = current;` copies all scalar fields into independent storage. Mutating the original does not change the copy. Field writes require a non-const class local. Whole-class reassignment is deferred. Ordinary functions now accept and return bounded scalar-field class values as independent copies. Method and constructor signatures remain scalar-only. Nested/resource fields and class borrow targets remain unsupported. `own<Point>` is rejected.

Each field occupies eight bytes, including bool, in declaration order. Complete size is eight times total field count, minimum eight bytes for an empty class. This is an internal padded layout, not a C or C++ ABI promise. Private fields participate in size but are excluded from field-count reflection and cannot be read by external member syntax. Methods of the declaring class can access private fields.

## Fixed-size arrays

```text
array<i64, 4> values = {10, 20, 5, 7};
const array<i64, 4> snapshot = values;
values[0] = 11;
```

`array<ScalarType, N>` permits i64/bool elements and a decimal literal length from 1 through 4096. All elements must be initialized exactly once by an exact-length braced list, or by copying a same-type array. Copies have independent storage. No partial/uninitialized arrays or default fills are implied.

`len(array_local)` returns its fixed length as i64. Indexes must be i64. Every load/store checks the index using an unsigned comparison against length, which rejects negative signed indexes as well as indexes at/above the upper bound. The compiler computes the element address only after the guard. Stores require a non-const array local.

Elements occupy eight bytes each, including bool, matching actual generated loads/stores and reflected array size. Array length is statically capped to prevent layout overflow; combined local storage in a function is capped at 65536 bytes, including class/scalar/array slots. This limit is a compiler resource bound, not a promise that every target stack has that much space: expression temporaries and call depth need additional stack, and stack exhaustion remains possible.

Arrays cannot currently be borrowed, returned, passed to functions, nested, or placed inside classes. Arrays of class/owned/reference values are rejected. No raw pointer, slice, unchecked indexing, cast or `any` escape hatch is provided.

## Working reflection

`size_of(Type)`, `type_id(Type)` and `field_count(Type)` are compile-time queries. `static_assert(bool_expression)` accepts literals, these queries, comparisons and logical negation; general arithmetic constant evaluation and code generation remain deferred.

Builtin type IDs: i64=1, bool=2, own<i64>=3, ref<i64>=4, mutref<i64>=5. Builtin sizes are 8,1,8,8,8. Scalar bool's logical size is one byte, but its current stack slot is eight bytes. Class IDs begin at 100 in deterministic graph declaration order and are compilation-graph-local; defining-module/native names determine source type identity. Mentioned array types have IDs `1000000 + 2*N + B`, where B is one for bool and zero for i64. Class IDs cannot collide with the array range.

`reflect_size(id)` and `reflect_field_count(id)` execute runtime lookups. Unknown IDs return zero. Descriptor entries are emitted for builtins, declared classes and array types used in storage/size/type-ID queries. Array size is `8*N`; arrays and builtins have zero named fields. Class field counts include public fields only, and class size includes all fields. Reflection cannot expose private values or bypass lifetime checks. Runtime queries use the defining module's visible descriptor view; unavailable/private IDs return zero, and reflection cannot implicitly import a type. Member traversal, invocation, mapped/conditional types and `keyof`-style type algebra remain design goals.

## Temporary machine integration

The bootstrap assembly boundary currently passes six scalar arguments in RDI, RSI, RDX, RCX, R8, R9 and returns RAX. It preserves RBP, does not touch RBX/R12–R15, and aligns RSP to sixteen bytes immediately before calls. No red zone, libc, heap allocation, SIMD or runtime library is generated. External assembly callers must provide canonical zero/one bools and correct stack alignment.

These temporary register choices are implementation machinery, not a source-level C ABI or binary interoperability promise. Only scalar-signature unqualified root functions retain unmangled names for the temporary bootstrap assembly bridge. Imported/namespaced functions use length-prefixed Aurora-native symbols. The compiler emits a complete import graph with per-defining-module reflection helpers; separately linking overlapping compiled graphs is not supported yet. A versioned Aurora-native ABI remains to be designed.

`examples/kernel.au` performs a mutable borrow, releases it, moves ownership and returns 42. `examples/class_values.au` demonstrates class copies/visibility/reflection. `examples/loops_arrays.au` demonstrates checked traversal and independent arrays.

## Evidence and honest limits

Tests execute assembled/linked machine code without libc, check compiler rejection diagnostics, and distinguish bounds/overflow SIGILL from crashes or timeouts. Tests are evidence for this constrained implementation, not a soundness proof or a claim of complete Rust-equivalent safety.

Self-hosting, complete modern C++ expressiveness, constructor bodies, overloads, inheritance, destructors, nested values, general ownership, generics, heap storage, concurrency, typed compile-time generation, separate binary compilation and optimization remain substantial future work. The requested native toolchain/distribution and Zen/RDNA qualification are long-term goals, not capabilities established by this compiler milestone. Hardware/bootstrap assembly and temporary kernel C++ remain outside these language checks.

## Native library and host I/O

The real `library/std/core.au` module exports scalar `std::min`, `std::max` and checked `std::abs`. It is a small compiled library seed, not a complete libc/libc++ replacement. See library/README.md and compiler/MODULES.md for contracts, visibility, module-root budgets and native identity.

Source reads use pinned Linux directory/file descriptors and openat2 beneath-root/no-symlink policies, failing closed if unsupported. Outputs use exclusive temporaries and atomic replacement, with root/import-source inode-alias protection and one-shot failed transactions. There is no atomic file/repository snapshot or crash-durability claim. Native I/O fault tests require an unprivileged Linux user.

Source implementation limits include128 nested parser expressions/blocks,64 type parses,32 namespace components and128 constructed expression-tree levels. Deep source is rejected normally before retaining an unsafe recursive tree; these are separate from file-byte limits and do not constitute global compiler resource bounds.

The internal method ABI adds a non-source-visible receiver capability, with a private saved frame slot. It is validated separately from scalar operands; no source pointer or foreign-call API is introduced. `library/std/numeric.au` exercises private state through checked `std::Accumulator` methods.

The unpublished next candidate adds ordinary class-value function boundaries and the real scalar-specialized std::minmax/MinMax/range_width API. [VALUE-CALLS.md](VALUE-CALLS.md) specifies argument snapshot timing, complete results, signature privacy, implementation limits and the private native call-record convention. No copy-elision or equivalent-C performance result is claimed.
