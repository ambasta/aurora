# Aurora native core library: scalar seed

The library is authored in Aurora's safe C++ dialect and compiled freestanding by the native module pipeline. These are small working library modules, not a complete C++ standard library or libc replacement.

```text
module application;
import std.core;

auto answer() -> i64 {
    return std::min(42, 100) + std::max(-1, 0) + std::abs(0);
}
```

Compile with an explicit source-module root:

```sh
build/aurorac --module-root library application.au -o build/application.s
```

## Implemented API

The std.core parameters/results are scalar `i64` values; there are no implicit conversions, reference returns or overloads.

- `std::min(i64 left, i64 right) -> i64`: returns the smaller mathematical value. Equal inputs return that same value. Both signed endpoints are supported.
- `std::max(i64 left, i64 right) -> i64`: returns the larger mathematical value, including both signed endpoints.
- `std::abs(i64 value) -> i64`: returns the nonnegative magnitude when representable. Zero returns zero. The minimum signed value (`-9223372036854775808`) triggers the language's defined checked-overflow fail-stop trap; it does not wrap or invoke undefined arithmetic behavior.

Calls evaluate their arguments left to right under the existing language rules. These implementations use no allocation, system call, libc symbol or foreign-function interface. The `std::detail` helper is module-private, and caller declarations cannot hijack its binding.

The implementations are intentionally simple and currently retain ordinary function-call overhead. There is no unmeasured zero-cost or equivalent-C performance claim. Inlining and other optimizations must preserve checked arithmetic, module identity and reflection scope.

## Deliberately absent

There are no placeholder implementations of allocator, memory-copy, string, vector, streams, threading, filesystem, locale or process services. General templates, heap ownership and interprocedural borrowing remain deferred; ordinary scalar-field class arguments/results have a bounded implemented value contract. Those mechanisms must precede the corresponding library contracts.

The long-term goal remains a native runtime responsible for the useful roles currently served by libc, and a broad safe C++ standard-library ecosystem without C source/ABI compatibility. This module establishes actual imports, private implementation helpers, typed calls and executable scalar contracts toward that goal.

## Encapsulated scalar accumulation

`import std.numeric;` supplies `std::Accumulator(initial)`, `.add(amount)` and
`.value() const`. This is a small Aurora-specific scalar API, not a claim that
standard C++ defines `std::Accumulator` or that generic numeric algorithms are
complete. It keeps the checked signed total private, uses no allocation, and
traps on overflow before updating the total. Copies have independent totals.

The compiler supports `std.numeric` with scalar-specialized
`std::minmax(i64, i64) -> std::MinMax` and `std::range_width(std::MinMax) -> i64`.
MinMax keeps ordered endpoints private and exposes readonly min()/max() methods.
The returned value and consumed argument are independent copies. Width traps on
signed overflow, including the full minimum-to-maximum i64 range. This is an
Aurora value API, not standard C++ pair/reference ABI compatibility or a generic
container implementation. See compiler/VALUE-CALLS.md for its current restrictions.

## Checked scalar integer algorithms

`import std.integer;` adds i64-specialized `std::gcd`, `std::lcm` and `std::div`.
The latter returns an independent private-field `std::DivResult` with readonly
quot()/rem() methods. Division truncates toward zero; remainder follows the
dividend sign. Zero divisors and unrepresentable quotients trap at defined UD2
sites. Minimum i64 % -1 is explicitly zero. Gcd/lcm return nonnegative mathematical
results when representable, otherwise checked overflow; lcm is zero when either
input is zero. These are freestanding Aurora value APIs, not C runtime or generic
standard-library compatibility. See compiler/INTEGERS.md for edge cases and bounds.

## Unsigned bit algorithms

`import std.bit;` adds `std::popcount(u64) -> i64`, `std::bit_width(u64) -> i64` and `std::has_single_bit(u64) -> bool`. Zero has count/width zero and is not a single bit; maximum u64 has count/width 64. The real Aurora implementations require no allocation or target host runtime. Their loops are bounded by 64 iterations, while ordinary call overhead remains. These are scalar-specialized APIs, with checked arithmetic and exact 64-bit operations defined in compiler/UNSIGNED.md; no unsigned wrapping, generic implementation or performance claim is implied.

## Reusable scalar pairs

The current template candidate supplies `import std.utility;` and `std::pair<T,U>` for explicit i64/u64/bool type arguments. A complete constructor initializes public first/second fields; exact-type mutation and independent ordinary-function value copies use the existing safe class semantics. All nine scalar tuples compile from one actual Aurora template definition. No deduction, nested/reference pairs, operator overloads or foreign pair ABI is provided. See compiler/TEMPLATES.md for nominal identity, module privacy and bounded instantiation.
