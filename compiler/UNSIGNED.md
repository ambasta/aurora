# Unsigned scalars and checked bit operations

The current candidate adds `u64`: an unsigned integer with mathematical range
0 through 18446744073709551615. It is a distinct scalar type, not a storage address,
resource handle or implicit replacement for i64. No cast syntax or pointer escape
is introduced. All existing scalar class, method, constructor and ordinary
value-call rules apply without weakening privacy, initialization or constness.

## Source contract

Decimal and `0b`/`0B` binary expression literals use the exact suffix `u64` or
`u8`, or no suffix for i64. For example, `0b10'1010u64`, `0B00101010u8` and
`0b101010` all denote 42 with distinct exact types. C++ apostrophe separators
are allowed only between binary digits; no leading, trailing or doubled separator
is accepted. Leading zeros do not change the base: `010` remains decimal ten.
Context never converts a literal. Invalid digits, other suffixes, out-of-range
magnitudes and unsigned unary minus are rejected. Unary minus admits exactly
`-2^63`, including its binary spelling; a positive `2^63` still requires `u64`.
Hexadecimal literals, decimal digit separators and binary array/template capacities
remain unsupported. Capacity grammar stays decimal-only. This spelling extension
adds no storage, implicit conversion, checked-operation or IR changes.

`u64(signed_expression)` checks that the i64 argument is nonnegative.
`i64(unsigned_expression)` checks that the u64 argument is at most INT64_MAX.
Failure reaches the existing checked-overflow UD2 site. These operations accept
only the opposite integer type: identity conversions, bool conversions, ownership
conversions and arbitrary reinterpretation are rejected. There is no implicit
signed/unsigned mixing in arithmetic, comparisons, bindings, calls or returns.

Unsigned addition, subtraction and multiplication check the mathematical result
against the u64 range; subtraction below zero traps. Division and remainder use
ordinary nonnegative integer mathematics, with zero divisors reaching the existing
`.Laurora_division_zero_trap`. No wrapping operation is available. Unsigned
comparisons use unsigned ordering across the high bit, including in restricted
literal-comparison static assertions.

`&`, `|`, `^` and unary `~` accept only u64. They operate on exactly 64 bits.
In particular, `~x` is mathematically `18446744073709551615 - x`; it is never an
unbounded negative integer. Both shift operators require a u64 left operand and
i64 count. Both operands evaluate left-to-right exactly once before validation.
Counts outside 0 through 63 reach `.Laurora_shift_count_trap` before the processor
can mask the count. This check applies even to a zero input.

`x << n` computes mathematical `x * 2^n`, trapping at the existing overflow site
if unrepresentable. It never silently discards high bits. `x >> n` computes
`floor(x / 2^n)` with zero fill. A count of zero is an identity; a count of 63 is
valid. No signed shift or signed bitwise operator is implemented.

Precedence follows the corresponding C++ operators, from lower to higher:
`|`, `^`, `&`, equality, ordering, shifts, addition/subtraction,
multiplication/division/remainder, unary operators. Binary operators associate
left-to-right. Comparisons return bool; bitwise operations cannot consume bool.
Parenthesize comparisons in conditions such as `(value & mask) == 0u64`.
General arithmetic, conversion and bitwise constant evaluation remains deferred;
static assertions still accept only literals, reflection, comparisons and `!`.

## Storage, identity and typed lowering

U64 occupies eight bytes in scalar slots, arrays and class fields. Local
`array<u64, N>` uses the existing fully initialized independent-copy semantics,
1..4096 length bound, signed i64 index checks and local-frame cap. Array lengths
and metadata-query IDs remain i64. Ownership/reference types remain i64-only;
this change does not add unsigned owners or interprocedural borrows.

Builtin type ID 8 identifies u64, preserving existing IDs 1..5. Its size is eight
and field count zero. Mentioned `array<u64, N>` IDs are `2000000 + N`, distinct
from existing i64/bool array IDs and graph-local class IDs. Type-ID equality does
not authorize conversion, memory access or receiver fabrication.

Constants retain all 64 payload bits and their exact scalar type. Typed binary
operations distinguish signed and unsigned arithmetic; shifts additionally
require a signed count. Convert carries explicit source/result types, and every
conversion/arithmetic operation drops any prior bounds token. The IR verifier
rejects mismatched operand types, arbitrary conversion types and capability
forgery before emission. Backend and verifier dispatch remain exhaustive.

Unsigned multiply checks its high product, and shifts check counts before using
hardware shifts. Left shift validates that reversing the shift recovers the
original bits, detecting all discarded high bits rather than relying on the
processor's overflow flag for multi-bit counts. No hardware divide exception is
an accepted language result. Fail-stop still implies no recovery or unwinding.

## Real freestanding bit library

`import std.bit;` exports scalar-specialized APIs in namespace `std`:

- `std::popcount(u64 value) -> i64`: number of set bits, from 0 through 64.
- `std::bit_width(u64 value) -> i64`: zero for zero; otherwise the least width
  representing the value, from 1 through 64.
- `std::has_single_bit(u64 value) -> bool`: true exactly for nonzero powers of two.

The implementations are Aurora source, use no heap or foreign runtime, and execute
through the ordinary module/native-call pipeline. Popcount clears one set bit per
iteration; bit_width shifts one bit per iteration. Both loops execute at most
64 times for valid u64 input. This specific algorithmic bound is not a global
compiler, call-stack or target-time bound. No instruction-selection optimization,
generic standard-library completeness or equivalent-C performance is claimed.

## Acceptance boundaries

Source tests cover native full-width results, rejection, evaluation order,
class/array copies, reflection and module APIs. The separate mathematical oracle
uses unbounded integers, explicit representability checks and 64-bit complement,
with raw eight-byte outputs. Failure checks require the exact retained UD2 site
and actual SIGILL; hardware divide exceptions and unrelated crashes fail.
Malformed IR and future-operation mutation tests exercise the backend boundary.
Final integration and independent review must identify their own candidate hash;
archived milestone007 receipts do not verify this new slice.
