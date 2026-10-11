# Scalar values, literals and evaluation

Integer arithmetic, conversion, indexing and evaluation have checked semantics rather than C/C++ undefined behavior. The supported numeric types are `i64`, `u64` and `u8`, with distinct `bool` and closed nominal enums. No floating-point or Unicode character type is implemented.

## Checked signed integers

### Defined results and failures

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

### Typed lowering

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

## Unsigned integers

### Source contract

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

### Storage, identity and typed lowering

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

## Byte values and literals

### Numeric contract

`u8` denotes integers from 0 through 255. Decimal `255u8` literals have that exact
type; larger literals reject. Explicit `u8(i64)` and `u8(u64)` conversions fail at
the existing arithmetic-overflow site outside that range. `i64(u8)` and `u64(u8)`
widen exactly. There are no implicit promotions, identity casts, boolean/enum
casts, truncating casts or source address conversions.

Addition, subtraction and multiplication check mathematical representability.
Division/remainder check zero before native division. Bitwise complement is exactly
eight bits; and/or/xor preserve u8. Both shift operators require a signed i64 count
from 0 through 7, with the existing distinct shift-count failure outside that range.
Left shift checks the mathematical result; right shift zero-fills. Unsigned unary
minus rejects. Comparisons require the same type on both sides.

Scalar deliberately expands to i64/u64/u8/bool; Value includes these plus the
existing named class and closed enum types. Enums still do not satisfy Scalar.
The appended builtin ID is 11; byte-array IDs are 3000000+N. Old type IDs and old
specializations retain their identities. There is no new constant-evaluation language.

### ASCII byte character literals

Single-quoted literals such as `'['`, `'"'` and `'a'` have exactly type `u8`,
just like `91u8`, `34u8` and `97u8`. No suffix is required or accepted. They work
in scalar expressions, comparisons, static assertions, array initializers,
constructor arguments and returns under the existing exact-type rules. Explicit
`i64(...)` or `u64(...)` conversion is still required to widen them; unary minus,
implicit promotions and identity conversions remain rejected.

An unescaped body is exactly one printable ASCII byte (`0x20` through `0x7e`),
other than single quote or backslash. The complete escape set is `\'`, `\\`,
`\0`, `\a`, `\b`, `\f`, `\n`, `\r`, `\t`, `\v` and `\xHH`. The hex escape
requires exactly two hexadecimal digits, accepts either digit case and denotes
any byte from `0x00` through `0xff`. Double quote is written directly as `'"'`;
`\"` is not an additional escape.

Empty or multibyte bodies, suffixes, raw control bytes, raw non-ASCII text,
unterminated literals, malformed escapes and extra hexadecimal digits reject
with lexical diagnostic AU1002. Octal escapes, Unicode escapes, code points,
grapheme literals and string values are not introduced. `\xFF` is byte value 255,
not a Unicode character or a UTF-8 encoder.

The shared lexer retains the exact source spelling and half-open byte span;
formatting never replaces a character spelling with a number or splits it.
Malformed literal spans start at the opening quote and end after the attempted
spelling, stopping before an unescaped or escaped CR/LF or at EOF when no closing
quote exists. Constants lower through the existing typed-u8 IR and checked
arithmetic. The two quote append calls in `std.json_write` exercise the new
spelling without changing the writer's transactional behavior.

### Bounded byte-string array initializers

Double-quoted text initializes an explicitly typed, named local `array<u8, N>`:

```cpp
const array<u8, 6> prefix = "IOMMU ";
const builtin::span<const u8> text = borrow_bytes(prefix);
```

The decoded byte count must equal `N` exactly. The existing capacity range is
1–4096; there is no inferred length, padding or hidden NUL terminator. Mutable
arrays, same-type array copies, indexing and lexical readonly borrows retain
their existing rules. Outside the readonly call-argument case below, a string
spelling cannot itself be borrowed, returned, passed as a value, assigned to an existing array or used to initialize a scalar,
non-`u8` array, class field or span. It creates no temporary backing object,
heap string type, pointer conversion or new lifetime rule.
Length mismatches report both the expected capacity and actual decoded byte
count, including UTF-8 bytes and decoded escapes, at the literal's source span.

Raw printable ASCII is copied exactly, except that double quote and backslash
need escapes. Raw non-ASCII text must be valid UTF-8 and contributes its original
encoded bytes, without normalization: `"é"` requires two bytes and `"😀"` four.
This is byte-array storage, not a Unicode character type or a guarantee that the
resulting bytes form UTF-8. Escapes support the existing byte-character set
(`\'`, `\\`, `\0`, `\a`, `\b`, `\f`, `\n`, `\r`, `\t`, `\v`, `\xHH`)
plus `\"` for the delimiter. Each escape contributes one byte; `\xHH` consumes
exactly two hex digits, so `"\x4142"` stores `A42`. `"\01"` stores zero then
`1`, not an octal escape. Escaped `\xFF` and embedded `\0` are ordinary bytes.
Single-quoted character literals remain ASCII-only with their existing escapes.

Raw ASCII controls/DEL, malformed UTF-8, unknown/Unicode/octal escapes, suffixes,
unterminated text and literals longer than 4096 decoded bytes fail lexically with
AU1003. CR/LF, including after a backslash, terminate a malformed spelling rather
than introducing multiline text. Adjacent strings are not concatenated. The
empty spelling is lexically valid but cannot initialize a positive-length array.

The shared lexer preserves one exact spelling/span for the formatter and LSP.
Lowering emits the same typed-byte constants and array stores as an explicit
brace initializer; IR, backend, storage layout and authority are unchanged.
Event reporting and the native serial console use these initializers immediately.
The existing byte-literal, lossless lexer, formatter and LSP-position tests cover
this extension, including decoded lengths, UTF-8/escapes, rejected escapes and
local borrow escape/mutation. Exact assembly comparisons cover explicit arrays.
Final-source full/image/guest qualification remains required by AGENTS.md; old
source-bound receipts cannot admit the migrated sources.

#### Readonly literal call arguments

A byte-string literal may directly supply a `builtin::span<const u8>` parameter
of a synchronous ordinary function, exact overload, nonconstructor method or
service helper, for example `std::starts_with(bytes, "write ")`. The existing
literal decoder supplies 0–4096 exact bytes, including UTF-8, embedded NUL and
high-byte escapes; neither this case nor array initialization adds a terminator.
Empty literals are valid zero-length spans. The backing is immutable module data,
while the temporary span capability lasts only through argument evaluation and
the complete call. Callees can read or forward it through existing span rules.

This adds no string value type, mutable view, address conversion, span field or
escaping result. Literal span locals, `borrow_bytes("...")`, constructor span
arguments and scalar literal arguments still reject. Typed IR records literal
bytes and their exact creation site independently of array, parameter and owned
origins. The verifier checks the existing literal-size bound, typed spills,
reborrow lifetime and return restrictions before emission. The backend emits
readonly bytes and the existing 56-byte span record; native calling conventions,
allocation and service authority do not change.

## Exact-bool short circuit

### Source behavior

Both operands must be exactly `bool`; the result is canonical `bool`. No numeric,
enum, class, owner or span truthiness or overloaded operator is provided. Operands
evaluate once, left to right. `a && b` executes `b` only if `a` is true; `a || b`
executes `b` only if `a` is false. Executed calls, writes and checks retain their
existing order. A skipped runtime arithmetic/bounds failure does not trap.

From lowest to highest binary precedence: `||`, `&&`, bitwise `|`, `^`, `&`,
`== !=`, `< > <= >=`, `<< >>`, `+ -`, `* / %`. Each level is left associative.
Existing unary `!`, numeric unary operators and postfix operations retain their
higher precedence and exact typing. Parentheses override grouping.

The complete RHS is always parsed and semantically checked, including after
literal `false &&` or `true ||`. Unknown/private names, type errors, illegal
borrows/moves, invalid literals and unsupported expressions still reject.
`static_assert` admits logical combinations of its existing closed constant
subset (literals, reflection, comparisons and `!`). Both constant operands are
checked; skipped arithmetic/calls do not become allowed constant expressions.

### Ownership and initialization

No ownership constructor becomes a general expression. Outer locals keep equal
shared/exclusive borrow counts, owner and span-origin facts across continuing
paths; live state is intersected. Unsupported conditional authority changes fail
closed. Synchronous readonly span arguments and copied class argument snapshots
created by RHS calls close before the join. Values may be mutated only through
existing authorized mutable receivers/references. Logical conditions do not
relax surrounding `if`/loop move rules, constness, initialization or privacy.

### Verified IR contract

Lowering uses existing `BranchFalse`, `Jump`, and `Label`. Both paths leave a bool
current value and preserve the prior operand-stack prefix. Nonempty expression
stacks may cross control flow only with exact ordered type and bounds-evidence
equality at joins. Active object lifetimes, array creation sites and complete span
origin/direct-parent/site facts must still agree; must-initialization intersects
and may-initialization unions. Returns still require empty operand stacks.

The verifier also records only transient incoming/outgoing depths per reachable
instruction. After convergence it checks the actual filtered emission sequence,
starting at zero: every instruction's incoming depth must match the previous
emitted instruction's outgoing depth. Unreachable semantic instructions reject;
only the previously allowed unreachable labels/jumps are filtered. Depth is never
reset at a label. This explicitly certifies unchanged backend linear stack/call
alignment accounting. Arbitrarily reordered stack-carrying CFGs may reject even
when CFG-valid; no general nonlinear IR support is claimed. No opcode, public IR
metadata, x86 implementation, source pointer or ABI is added.

### Bounded snapshot retention

Each function permits at most 65536 retained block-entry states (including entry)
and 262144 operand Values summed across those states. Both limits are checked
before a first snapshot is allocated, using overflow-safe subtraction. Existing
snapshot stack equality is checked before a merge copy, and revisits do not charge
again. Enforcement is independent of diagnostic metrics. Overflowing either bound
produces an explicit compiler diagnostic and preserves existing output files.

These aggregate limits coexist with array capacity and source/frame limits.
Straight-line 4096-element initialization is unchanged; a large initializer with
many logical branches can exceed retained-operand limits. Operand payload depends
on host type layout. Current/merge copies, vector capacity, strings, lifetime and
initialization sets, instruction-sized arrays and other compilation state remain
outside this count limit. This is not a whole-compiler memory/time bound, denial-
of-service guarantee, safety proof or equivalent-C performance claim.


## Byte layout and lowering


The implemented representation uses size/alignment one for u8 and stride
one for `builtin::array<u8,N>`. Existing numeric, bool and enum field/array storage
stays eight bytes; standalone bool reflection continues its historical size one.
All layouts lacking u8 retain their prior offsets, size and alignment rules.
Class fields use explicit byte offsets, natural storage alignment and tail padding.
For example Bytes4 has size four; the enum-plus-Bytes4 Encode32Result has size sixteen.

Logical ClassField ranges and scalar leaf counts remain separate from byte offsets.
A canonical recursive layout records leaf/field byte offsets, logical size,
alignment and actual reserved storage extent. The verifier derives it from checked
nominal shape and rejects conflicting supplied metadata. Physical stack and private
call allocations round to eight bytes; disjointness uses these reservations, not
only reflected size. Local frames remain sixteen-byte aligned. Empty standalone
objects retain an eight-byte reservation; nested zero-leaf values retain logical
completion without widening old parents. No empty payload can establish completion
for another field.

Byte loads zero-extend and byte stores require an exact initialized u8 value.
Checks retain the declared length, exact element type, stride and storage provenance
before addressing. Copies traverse complete typed fields. The x86 backend coalesces
exact groups of eight initialized u8 leaves only when both canonical source and
destination byte offsets are consecutive within the selected copied range. Each
group uses one unaligned-capable qword load/store pair with RAX alone; remaining
bytes retain exact byte operations. No qword group includes padding, a non-u8 leaf
or an owning descriptor. For copied payloads, contiguous initialized
scalar payload runs of at least 64 bytes instead use forward `REP MOVSB`. Both
canonical offset ranges must be consecutive at every leaf's storage width; padding
and descriptor gaps split runs. RSI/RDI/RCX are saved and restored, and the exact
24-byte transient stack peak is included in emitted stack facts. `CLD` establishes
the existing clear-direction ABI without changing arithmetic flags. The RSP-based call-record destination is captured in scratch RAX before saves;
all sources retain stable RBP/R10/R11 bases. This is bounded code-size lowering, not
copy elision or a runtime-speed claim. Representation padding is zeroed separately;
no source expression
can address it. Stack-reservation slack outside
an object's representation is not a source field or copied payload. Scalar private
calls carry canonical values in registers; aggregate records/results remain distinct
from receiver storage. This is an internal native convention, not a C ABI or an
external wire layout for arbitrary classes.
