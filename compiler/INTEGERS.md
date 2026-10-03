# Checked signed division and scalar integer algorithms

The current candidate adds i64 `/` and `%`, with the same multiplicative
precedence and left associativity as `*`. Both operands evaluate left-to-right
exactly once, and both must be i64. No implicit conversion or unchecked variant
is available. Restricted `static_assert` expressions do not gain general
arithmetic evaluation through this change.

## Defined results and failures

Division truncates toward zero. For nonzero divisor `b`, remainder has the sign
of dividend `a` (or is zero), and its absolute value is less than `abs(b)`.
Mathematically, `a = trunc(a/b) * b + (a % b)` using unbounded integers; evaluating
that identity in checked i64 arithmetic may itself overflow.

| Operands | `/` | `%` |
|---|---|---|
| `85, 2` | `42` | `1` |
| `-85, 2` | `-42` | `-1` |
| `85, -2` | `-42` | `1` |
| `-85, -2` | `42` | `-1` |
| `INT64_MIN, -1` | checked overflow trap | `0` |
| any i64, `0` | division-zero trap | division-zero trap |

Remainder at minimum/-1 is explicitly zero because the remainder is representable,
although the corresponding quotient is not. The implementation does not execute
an overflowing hardware division to compute it.

Zero divisors branch to `.Laurora_division_zero_trap`, a defined UD2 site.
Unrepresentable quotients use the existing `.Laurora_overflow_trap`. Each native
IDIV is preceded by both zero and minimum/-1 checks. A hardware divide exception
(`#DE` / hosted SIGFPE) is a compiler defect, not an accepted language outcome.
Fail-stop behavior still promises no recovery or destructor unwinding.

## Typed lowering

CheckedDivide and CheckedRemainder are explicit typed binary operations. The
verifier requires initialized i64 operands and produces an i64 with no inherited
array-bound token. These operations cannot be forged from bool/reference values.
The backend operation owns its complete guard and IDIV sequence; source code and
IR provide no unchecked divide instruction. Arithmetic dispatch uses exhaustive
enum switches, complementing the exhaustive instruction-variant dispatch gates.
Unknown internal enum values are rejected by verification.

The backend uses RAX/RDX for the signed quotient/remainder and R11 for the divisor.
Value-call record pointers and receivers are already saved in separate private
frame slots before expression execution. Division does not change source layout,
calling conventions, class visibility or reflection views.

## Executable `std.integer` module

Compile with an explicit library root and `import std.integer;`.

- `std::gcd(i64, i64)` returns the nonnegative mathematical greatest common divisor;
  `gcd(0,0)` is zero. Signed Euclid avoids taking the absolute value of minimum i64
  prematurely. Checked final normalization traps only when the result itself
  exceeds maximum i64, such as gcd(minimum,0) or gcd(minimum,minimum).
- `std::lcm(i64, i64)` returns zero if either argument is zero. Otherwise it divides
  by gcd before checked multiplication and final sign normalization. It returns
  the mathematical nonnegative result if representable and traps on overflow.
- `std::div(i64, i64)` returns an independent inline `std::DivResult` whose private
  quotient/remainder are exposed through readonly quot()/rem() methods. Its public
  constructor takes numerator/denominator and performs the same checked operations;
  designated initialization cannot manufacture arbitrary private results. A
  representable quotient is required, so minimum/-1 traps even if only rem() would
  later be queried.

These APIs are i64 specializations, not generic standard-library completeness or
C div_t/source/ABI compatibility. They allocate no heap memory and require no
foreign runtime. Their ordinary class result uses the verified native value-call
convention. Existing integer arithmetic remains checked, never silently wrapping.

## Acceptance evidence

`tests/compiler/integers.py` covers native edge results, exact SIGILL rather than
arbitrary crashes, source typing, evaluation order, parsing and library behavior.
The independent integer oracle uses unbounded arithmetic and explicitly implements
truncation toward zero instead of inheriting Python's negative floor division.
Its trap observer checks the precise retained UD2 site and actual process signal.
Direct IR tests reject mistyped operands and verify guards precede IDIV; mutation
checks reject unhandled instruction variants and binary enum additions.

Passing this bounded suite does not establish a complete numeric standard library,
formal compiler correctness, a global stack/resource bound or an equivalent-C
performance result. Archived milestone006 source and historical receipts remain
unchanged; this candidate requires its own final integrated verification.
