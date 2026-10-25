#!/usr/bin/env python3
"""Checked u64 arithmetic, conversions, shifts and std.bit against Python integers.

Python integers are unbounded: arithmetic is checked for representability only
after computing its mathematical result, so overflowing arithmetic and shifts
never silently wrap. Counts are signed i64; invalid counts are distinct from
arithmetic overflow and division by zero. Results are complete 64-bit values,
and traps must reach the exact named UD2 (native_runner.py).

Run: python3 tests/compiler/unsigned_oracle.py build/aurorac [--seed 8008 --random-count 200]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.util
from pathlib import Path
import random
import sys

if importlib.util.find_spec("native_runner") is None:
    # Loaded by path from another directory (tests/kernel-unsigned-source.py), or as
    # a copy by fixtures/xfs-offline/verify_native.py, whose checkout is two levels up.
    sys.path.append(str(Path(__file__).resolve().parent))
    sys.path.append(str(Path(sys.argv[0]).resolve().parents[2] / "tests" / "compiler"))

from native_runner import (  # noqa: E402, F401 - re-exported for library tests not yet migrated
    DIAGNOSTIC,
    ROOT,
    UD2,
    NativeRunner,
    Observation,
    Rejection,
    Suite,
    Trap,
    command,
    rejected,
    require,
    validate_case_values as validate_values,
    validate_trap,
)


MAX = (1 << 64) - 1
SIGN = 1 << 63
SIGNED_MIN = -(1 << 63)
SIGNED_MAX = (1 << 63) - 1


@dataclass(frozen=True)
class Case:
    name: str
    body: str
    expected: int | Trap
    result_type: str = "u64"
    prelude: str = ""
    imports: tuple[str, ...] = ()


def representable(value):
    return value if 0 <= value <= MAX else Trap.OVERFLOW


def signed(value):
    return value if SIGNED_MIN <= value <= SIGNED_MAX else Trap.OVERFLOW


def division(a, b):
    return Trap.ZERO if b == 0 else a // b


def remainder(a, b):
    return Trap.ZERO if b == 0 else a % b


def left_shift(value, count):
    if not 0 <= count < 64:
        return Trap.COUNT
    return representable(value * (2**count))


def right_shift(value, count):
    if not 0 <= count < 64:
        return Trap.COUNT
    return value // (2**count)


def complement(value):
    return (~value) & MAX


def operand_pairs(seed, count):
    edges = [0, 1, 2, 3, 17, (1 << 32) - 1, 1 << 32, SIGNED_MAX, 1 << 63, (1 << 63) + 1, MAX - 1, MAX]
    pairs = {(a, b) for a in edges for b in edges}
    # Exact multiplication boundary and nontrivial high-bit quotient/remainders.
    pairs.update(
        [(4294967295, 4294967297), (4294967296, 4294967296), (MAX, 3), (MAX, 7), (MAX, 1 << 63), (MAX - 3, MAX - 2)]
    )
    random_source = random.Random(seed)
    for index in range(count):
        if index % 4 == 0:
            a, b = [random_source.randrange(MAX + 1) for _ in range(2)]
        elif index % 4 == 1:
            a, b = random_source.randrange(MAX + 1), random_source.randrange(1001)
        elif index % 4 == 2:
            a, b = [random_source.randrange(1 << 32) for _ in range(2)]
        else:
            a, b = MAX - random_source.randrange(256), random_source.choice(edges)
        pairs.add((a, b))
    return sorted(pairs)


def generated_cases(seed, count):
    pairs = operand_pairs(seed, count)
    binary = [
        ("+", lambda a, b: representable(a + b)),
        ("-", lambda a, b: representable(a - b)),
        ("*", lambda a, b: representable(a * b)),
        ("/", division),
        ("%", remainder),
        ("&", lambda a, b: a & b),
        ("|", lambda a, b: a | b),
        ("^", lambda a, b: a ^ b),
    ]
    comparisons = [
        ("<", lambda a, b: a < b),
        ("<=", lambda a, b: a <= b),
        (">", lambda a, b: a > b),
        (">=", lambda a, b: a >= b),
        ("==", lambda a, b: a == b),
        ("!=", lambda a, b: a != b),
    ]
    for a, b in pairs:
        for operator, oracle in binary:
            expression = f"{a}u64 {operator} {b}u64"
            yield Case("operator " + expression, "return " + expression + ";", oracle(a, b))
        for operator, oracle in comparisons:
            expression = f"{a}u64 {operator} {b}u64"
            yield Case("unsigned comparison " + expression, "return " + expression + ";", int(oracle(a, b)), "bool")

    values = sorted(
        {value for pair in pairs for value in pair}
        | {1 << bit for bit in range(64)}
        | {(1 << bit) - 1 for bit in range(65)}
    )
    for value in values:
        yield Case(f"literal {value}", f"return {value}u64;", value)
        yield Case(f"complement {value}", f"return ~{value}u64;", complement(value))
        yield Case(f"double complement {value}", f"return ~~{value}u64;", value)
        for name, expected, kind in [
            ("popcount", value.bit_count(), "i64"),
            ("bit_width", value.bit_length(), "i64"),
            ("has_single_bit", int(value != 0 and value.bit_count() == 1), "bool"),
        ]:
            yield Case(
                f"std::{name}({value})", f"return std::{name}({value}u64);", expected, kind, imports=("std.bit",)
            )

    shift_values = [0, 1, 2, 3, (1 << 32) - 1, 1 << 32, SIGNED_MAX, 1 << 63, MAX - 1, MAX]
    counts = [SIGNED_MIN, -65, -1, 0, 1, 2, 31, 32, 62, 63, 64, 65, SIGNED_MAX]
    shift_pairs = {(value, amount) for value in shift_values for amount in counts}
    random_source = random.Random(seed ^ 0xB17)
    for index in range(count):
        value = random_source.randrange(MAX + 1)
        amount = random_source.randrange(64) if index % 2 else random_source.randrange(-4, 68)
        shift_pairs.add((value, amount))
    for value, amount in sorted(shift_pairs):
        for operator, oracle in [("<<", left_shift), (">>", right_shift)]:
            expression = f"{value}u64 {operator} ({amount})"
            yield Case("checked shift " + expression, "return " + expression + ";", oracle(value, amount))
    # Every valid count, including the high-bit count 63, has a successful case.
    for amount in range(64):
        yield Case(f"unit shift {amount}", f"return 1u64 << {amount};", 1 << amount)
        yield Case(f"logical shift {amount}", f"return {MAX}u64 >> {amount};", MAX // (2**amount))

    for value in [SIGNED_MIN, SIGNED_MIN + 1, -1, 0, 1, 2, SIGNED_MAX - 1, SIGNED_MAX]:
        yield Case(f"i64 to u64 {value}", f"return u64({value});", representable(value))
    for value in [0, 1, 2, SIGNED_MAX - 1, SIGNED_MAX, 1 << 63, (1 << 63) + 1, MAX - 1, MAX]:
        yield Case(f"u64 to i64 {value}", f"return i64({value}u64);", signed(value), "i64")
    for _ in range(count):
        value = random_source.randrange(MAX + 1)
        yield Case(f"random u64 conversion {value}", f"return i64({value}u64);", signed(value), "i64")
        value = random_source.randrange(SIGNED_MIN, SIGNED_MAX + 1)
        yield Case(f"random i64 conversion {value}", f"return u64({value});", representable(value))

    for expression, expected in [
        ("2u64+21u64/4u64*3u64", 17),
        ("20u64/3u64/2u64", 3),
        ("20u64%6u64%3u64", 2),
        ("1u64+2u64<<3", 24),
        ("32u64>>1+2", 4),
        ("1u64<<1<<2", 8),
        ("128u64>>2>>1", 16),
        ("8u64|6u64^3u64&1u64", 15),
        ("~0u64^1u64", MAX - 1),
        ("1u64<<3|2u64", 10),
        ("8u64>>1&3u64", 0),
        (f"({MAX}u64+1u64)/0u64", Trap.OVERFLOW),
        (f"(1u64/0u64)+({MAX}u64+1u64)", Trap.ZERO),
        ("0u64*(1u64/0u64)", Trap.ZERO),
        ("0u64&(1u64%0u64)", Trap.ZERO),
        ("0u64<<64", Trap.COUNT),
        ("0u64>>64", Trap.COUNT),
        (f"({MAX}u64+1u64)<<64", Trap.OVERFLOW),
        (f"0u64<<({SIGNED_MAX}+1)", Trap.OVERFLOW),
        ("(1u64<<64)/0u64", Trap.COUNT),
        ("(1u64/0u64)<<64", Trap.ZERO),
        ("(1u64<<64)<<(0-1)", Trap.COUNT),
        ("u64(-1)<<64", Trap.OVERFLOW),
        ("u64(i64(9223372036854775808u64))", Trap.OVERFLOW),
        ("u64(i64(9223372036854775807u64))", SIGNED_MAX),
    ]:
        yield Case("precedence/trap order " + expression, "return " + expression + ";", expected)

    trace = (
        "class Trace{u64 n;public:Trace():n(0u64){}"
        "auto next()->u64{n=n+1u64;return n;}"
        "auto count()->i64{n=n+1u64;return i64(n);}"
        "auto get()const->u64{return n;}};"
    )
    for expression, expected in [
        ("t.next()+t.next()", 302),
        ("t.next()*t.next()", 202),
        ("t.next()/t.next()", 2),
        ("t.next()%t.next()", 102),
        ("t.next()&t.next()", 2),
        ("t.next()|t.next()", 302),
        ("t.next()^t.next()", 302),
        ("t.next()<<t.count()", 402),
        ("t.next()>>t.count()", 2),
    ]:
        yield Case(
            "left-to-right once " + expression,
            f"Trace t=Trace();u64 value={expression};return value*100u64+t.get();",
            expected,
            prelude=trace,
        )
    yield Case(
        "nested calls preserve unsigned dividend",
        f"return id({MAX}u64)/id(3u64)+id({MAX}u64)%id(3u64);",
        MAX // 3,
        prelude="auto id(u64 value)->u64{return value;}",
    )
    yield Case(
        "receiver survives unsigned division",
        f"Cell c=Cell({MAX}u64);return c.result();",
        MAX // 5,
        prelude="class Cell{u64 n;public:Cell(u64 x):n(x){}auto result()const->u64{return n/5u64+n%5u64;}};",
    )
    yield Case(
        "u64 class copied through function",
        f"const Cell a=Cell({MAX}u64);Cell b=copy(a);return b.get();",
        MAX,
        prelude="class Cell{u64 n;public:Cell(u64 x):n(x){}auto get()const->u64{return n;}};"
        "auto copy(Cell x)->Cell{return x;}",
    )
    yield Case(
        "u64 array independent copy and checked access",
        f"array<u64,2> a={{0u64,{MAX}u64}};const array<u64,2> b=a;a[1]=1u64;return b[len(b)-1]-a[1];",
        MAX - 1,
    )
    yield Case(
        "library argument evaluated before call",
        f"return std::popcount({MAX}u64+1u64);",
        Trap.OVERFLOW,
        "i64",
        imports=("std.bit",),
    )
    yield Case(
        "bit and integer modules coexist",
        f"return std::popcount({MAX}u64)+std::gcd(-84,30);",
        70,
        "i64",
        imports=("std.bit", "std.integer"),
    )


def rejection_cases():
    def app(body, result_type="u64", prelude="", imports=""):
        return f"module test;{imports}{prelude}auto test()->{result_type}{{{body}}}"

    for literal in (
        "18446744073709551616u64",
        "999999999999999999999999999999999999u64",
        "18446744073709551615",
        "1u",
        "1u65",
        "1U64",
        "1u64u64",
    ):
        result_type = "i64" if literal.isdecimal() else "u64"
        yield Rejection("invalid literal " + literal, app("return " + literal + ";", result_type))
    for expression in (
        "-0u64",
        "-1u64",
        "-18446744073709551615u64",
        "~1",
        "~true",
        "1u64<<1u64",
        "1u64>>1u64",
        "1<<1",
        "1>>1",
        "1u64<<true",
        "1u64>>false",
        "u64(1u64)",
        "i64(1)",
        "u64(true)",
        "i64(false)",
        "u64()",
        "i64()",
        "u64(1,2)",
        "i64(1u64,2u64)",
    ):
        # Match the otherwise-natural result type so an unrelated return type
        # error cannot conceal incorrect acceptance of the forbidden operation.
        result_type = "u64"
        if expression.startswith("i64(") or expression in ("~1", "1<<1", "1>>1"):
            result_type = "i64"
        elif expression == "~true":
            result_type = "bool"
        yield Rejection("forbidden expression " + expression, app("return " + expression + ";", result_type))
    for operator in ("+", "-", "*", "/", "%", "&", "|", "^", "<", "<=", ">", ">=", "==", "!="):
        for left, right in (("1u64", "1"), ("1", "1u64")):
            expression = left + operator + right
            result_type = "bool" if operator in ("<", "<=", ">", ">=", "==", "!=") else "u64"
            yield Rejection("mixed signedness " + expression, app("return " + expression + ";", result_type))
    for source in [
        app("u64 value=1;return value;"),
        app("i64 value=1u64;return 0u64;"),
        app("return 1;"),
        app("return 1u64;", "i64"),
        app("return take(1);", prelude="auto take(u64 n)->u64{return n;}"),
        app("return 0u64;", prelude="auto take(i64 n)->i64{return n;}auto bad()->i64{return take(1u64);}"),
        app("array<u64,1> a={1};return a[0];"),
        app("array<u64,1> a={1u64};return a[0u64];"),
        app("u64 n=0u64;n=1;return n;"),
        app("const u64 n=0u64;n=1u64;return n;"),
        app("return std::popcount(1);", "i64", imports="import std.bit;"),
        app("return std::bit_width(true);", "i64", imports="import std.bit;"),
        app("return std::has_single_bit(1);", "bool", imports="import std.bit;"),
    ]:
        yield Rejection("type boundary " + source, source)


def app(body, imports="", result="u64"):
    return "module app; " + imports + " auto test() -> " + result + " { " + body + " }"


def surface_cases(suite):
    """Typed-surface programs: literals, classes, arrays, calls and modules."""
    for name, expression, result in [
        ("maximum literal", f"{MAX}u64", MAX),
        ("leading zero decimal", "010u64", 10),
        ("leading zero eight", "08u64", 8),
        ("complement high bit", f"~{SIGN}u64", SIGN - 1),
        ("add high", f"{SIGN}u64 + 42u64", SIGN + 42),
        ("subtract maximum", f"{MAX}u64 - {SIGN}u64", SIGN - 1),
        ("multiply high", "9223372036854775807u64 * 2u64", MAX - 1),
        ("remainder high", f"{MAX}u64 % {SIGN}u64", SIGN - 1),
        ("bit and", "85u64 & 51u64", 17),
        ("bit or", "85u64 | 51u64", 119),
        ("bit xor", "85u64 ^ 51u64", 102),
        ("logical high shift", f"{SIGN}u64 >> 1", SIGN // 2),
        ("bit precedence", "1u64 | 2u64 ^ 3u64 & 6u64", 1),
        ("shift addition precedence", "1u64 << 1 + 2", 8),
        ("shift left associativity", "16u64 >> 1 >> 2", 2),
        ("conversion to unsigned", "u64(42)", 42),
    ]:
        suite.check(name, app("return " + expression + ";"), result)
    for name, expression, result_type, trap in [
        ("subtraction underflow", "0u64-1u64", "u64", Trap.OVERFLOW),
        ("multiplication overflow", f"{SIGN}u64*2u64", "u64", Trap.OVERFLOW),
        ("left overflow", "2u64<<63", "u64", Trap.OVERFLOW),
        ("left negative", "0u64<<-1", "u64", Trap.COUNT),
        ("right negative", "0u64>>-1", "u64", Trap.COUNT),
        ("conversion high", f"i64({SIGN}u64)", "i64", Trap.OVERFLOW),
    ]:
        suite.check(name, app("return " + expression + ";", result=result_type), trap)
    for name, source, error in [
        ("signed literal overflow", app(f"return {SIGN};"), "integer literal"),
        ("unknown suffix", app("return 1ul;"), "integer literal"),
        ("partial minimum literal suffix", app("return -9223372036854775808abc;", result="i64"), "integer literal"),
        ("negative unsigned minimum", app(f"return -{SIGN}u64;"), "expected"),
        ("signed bitwise", app("return 1&2;", result="i64"), "expected"),
        ("signed shift", app("return 1<<2;", result="i64"), "expected"),
        ("unsigned owner unsupported", app("own<u64> a=own(1u64); return 0u64;"), "expected 'i64'"),
        ("unsigned index rejected", app("const array<u64,1> a={42u64};return a[0u64];"), "expected"),
        ("metadata index unsigned", app("return reflect_size(8u64);", result="i64"), "expected"),
        ("private builtin conversion name", "module app;auto u64(i64 x)->i64{return x;}", "reserved function"),
        ("literal static assert mismatch", app("static_assert(1u64==1);return 0u64;"), "expected"),
    ]:
        suite.reject(name, source, error)
    suite.check(
        "unsigned class value boundary",
        "module app;\n"
        "class Box {u64 value;public:Box(u64 n):value(n){} auto get() const->u64{return value;} "
        "auto add(u64 n)->u64{value=value+n;return value;}};\n"
        "auto copy(Box b,u64 n)->Box{const Box result=Box(b.get()+n);return result;}\n"
        "auto test()->u64{Box b=Box(9223372036854775808u64);const Box c=copy(b,b.add(42u64)-b.get());"
        "return c.get();}\n",
        SIGN,
    )
    # Full-width fields across the private aggregate ABI.
    fields = " ".join(f"u64 f{i};" for i in range(64))
    initializers = ",".join(f".f{i}={MAX - i}u64" for i in range(64))
    suite.check(
        "six maximum-width unsigned value parameters",
        "module app;class Wide{public:" + fields + "};"
        "auto select(Wide a,Wide b,Wide c,Wide d,Wide e,Wide f)->Wide{const Wide result=f;return result;}"
        "auto test()->u64{const Wide a=Wide{" + initializers + "};const Wide b=select(a,a,a,a,a,a);return b.f63;}",
        MAX - 63,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=8008)
    parser.add_argument("--random-count", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    require(0 <= args.random_count <= 10000, "random-count must be between 0 and 10000")
    suite = Suite(args.compiler, "unsigned oracle", timeout=args.timeout)
    suite.load(Path(__file__).with_suffix(".cases"))
    for case in generated_cases(args.seed, args.random_count):
        suite.value(case.name, case.body, case.expected, case.result_type, case.prelude, case.imports)
    for case in rejection_cases():
        suite.reject(case.name, case.source, pattern=DIAGNOSTIC)
    surface_cases(suite)
    suite.finish()


if __name__ == "__main__":
    sys.exit(main())
