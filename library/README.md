# Aurora native core library: scalar seed

The library is authored in Aurora's safe C++ dialect and compiled freestanding by the native module pipeline. It is the first small working library module, not a complete C++ standard library or libc replacement.

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

All parameters/results are scalar `i64` values; there are no implicit conversions, reference returns or overloads.

- `std::min(i64 left, i64 right) -> i64`: returns the smaller mathematical value. Equal inputs return that same value. Both signed endpoints are supported.
- `std::max(i64 left, i64 right) -> i64`: returns the larger mathematical value, including both signed endpoints.
- `std::abs(i64 value) -> i64`: returns the nonnegative magnitude when representable. Zero returns zero. The minimum signed value (`-9223372036854775808`) triggers the language's defined checked-overflow fail-stop trap; it does not wrap or invoke undefined arithmetic behavior.

Calls evaluate their arguments left to right under the existing language rules. These implementations use no allocation, system call, libc symbol or foreign-function interface. The `std::detail` helper is module-private, and caller declarations cannot hijack its binding.

The implementations are intentionally simple and currently retain ordinary function-call overhead. There is no unmeasured zero-cost or equivalent-C performance claim. Inlining and other optimizations must preserve checked arithmetic, module identity and reflection scope.

## Deliberately absent

There are no placeholder implementations of allocator, memory-copy, string, vector, streams, threading, filesystem, locale or process services. General templates, heap ownership, aggregate arguments/results and interprocedural borrowing have not been implemented soundly yet. Those mechanisms must precede the corresponding library contracts.

The long-term goal remains a native runtime responsible for the useful roles currently served by libc, and a broad safe C++ standard-library ecosystem without C source/ABI compatibility. This module establishes actual imports, private implementation helpers, typed calls and executable scalar contracts toward that goal.
