#!/usr/bin/env python3
"""Checked i64 arithmetic and std.integer against unbounded Python integers.

Division is defined explicitly from positive magnitudes, with truncation toward
zero; remainder is then a - q*b. gcd/lcm use mathematical nonnegative integers
and apply the signed-64 representability check only to the final result.
Results are complete 64-bit values, and traps must reach the exact named UD2
(native_runner.py).

Run: python3 tests/compiler/integer_oracle.py build/aurorac [--seed 7043 --random-count 200]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import random
import sys

from native_runner import (  # noqa: F401 - re-exported for tests not yet migrated
    ROOT,
    UD2,
    NativeRunner,
    Observation,
    Suite,
    Trap,
    command,
    rejected,
    require,
    validate_trap,
    validate_values,
)


MIN = -(1 << 63)
MAX = (1 << 63) - 1


@dataclass(frozen=True)
class Case:
    name: str
    body: str
    expected: int | Trap
    prelude: str = ""
    library: bool = False


def representable(value):
    return value if MIN <= value <= MAX else Trap.OVERFLOW


def mathematical_divrem(a, b):
    """Unbounded mathematical result; // is applied only to positive operands."""
    magnitude = abs(a) // abs(b)
    quotient = -magnitude if (a < 0) != (b < 0) else magnitude
    return quotient, a - quotient * b


def division(a, b):
    return Trap.ZERO if b == 0 else representable(mathematical_divrem(a, b)[0])


def remainder(a, b):
    return Trap.ZERO if b == 0 else mathematical_divrem(a, b)[1]


def gcd(a, b):
    return representable(math.gcd(a, b))


def lcm(a, b):
    if a == 0 or b == 0:
        return 0
    # Divide before multiplying, in unbounded positive arithmetic. In particular,
    # neither abs(MIN) nor an oversized intermediate product is itself an error.
    return representable((abs(a) // math.gcd(a, b)) * abs(b))


def operand_pairs(seed, count):
    # Cartesian signs/boundaries plus exact square/product and long-Euclid cases.
    edges = [MIN, MIN + 1, -3037000500, -17, -2, -1, 0, 1, 2, 17, 3037000499, MAX - 1, MAX]
    pairs = set((a, b) for a in edges for b in edges)
    for a, b in [
        (3037000499, 3037000500),
        (3037000500, 3037000500),
        (1 << 62, 2),
        (MAX, 3),
        (MIN, 1 << 62),
        (7540113804746346429, 4660046610375530309),
        (MAX, MAX // 2),
        (MIN + 1, MAX),
    ]:
        for left_sign in (-1, 1):
            for right_sign in (-1, 1):
                left, right = a * left_sign, b * right_sign
                if MIN <= left <= MAX and MIN <= right <= MAX:
                    pairs.add((left, right))
                    pairs.add((right, left))
    random_source = random.Random(seed)
    for index in range(count):
        if index % 4 == 0:
            a, b = [random_source.randrange(MIN, MAX + 1) for _ in range(2)]
        elif index % 4 == 1:
            a, b = random_source.randrange(MIN, MAX + 1), random_source.randrange(-1000, 1001)
        elif index % 4 == 2:
            a, b = [random_source.randrange(-(10**9), 10**9 + 1) for _ in range(2)]
        else:
            a = random_source.choice([MIN, MAX])
            a += random_source.randrange(256) * (1 if a == MIN else -1)
            b = random_source.choice(edges)
        pairs.add((a, b))
    return sorted(pairs)


def generated_cases(seed, count):
    for a, b in operand_pairs(seed, count):
        for operator, oracle in [("/", division), ("%", remainder)]:
            yield Case(f"operator {a} {operator} {b}", f"return ({a}){operator}({b});", oracle(a, b))
        for name, oracle in [("gcd", gcd), ("lcm", lcm)]:
            yield Case(f"std::{name}({a},{b})", f"return std::{name}({a},{b});", oracle(a, b), library=True)
        for accessor in ["quot", "rem"]:
            expected = division(a, b)
            if not isinstance(expected, Trap) and accessor == "rem":
                expected = remainder(a, b)
            yield Case(
                f"std::div({a},{b}).{accessor}",
                f"const std::DivResult result=std::div({a},{b});return result.{accessor}();",
                expected,
                library=True,
            )

    for expression, expected in [
        ("20/3*2", 12),
        ("20*3/2%7", 2),
        ("2+21/4*3", 17),
        ("-17%5*-3", 6),
        ("-17/5*3+2", -7),
        ("20/3/2", 3),
        ("20%6%3", 2),
        ("20/(3*2)", 3),
        ("(7/3)+(7%3)", 3),
        ("7/-3", -2),
        ("7%-3", 1),
        (f"{MAX}+1", Trap.OVERFLOW),
        (f"({MIN})-1", Trap.OVERFLOW),
        (f"{MAX}*2", Trap.OVERFLOW),
        (f"-({MIN})", Trap.OVERFLOW),
        (f"({MAX}+1)/0", Trap.OVERFLOW),
        (f"(1/0)/({MAX}+1)", Trap.ZERO),
        (f"({MIN})/-1/0", Trap.OVERFLOW),
        (f"({MIN})%-1/0", Trap.ZERO),
        (f"({MIN})/-1%0", Trap.OVERFLOW),
        ("0*(1/0)", Trap.ZERO),
        ("0*(1%0)", Trap.ZERO),
        ("(1%0)/0", Trap.ZERO),
    ]:
        yield Case("precedence/trap order " + expression, "return " + expression + ";", expected)

    trace = (
        "class Trace{i64 value;public:Trace():value(0){}"
        "auto next()->i64{value=value+1;return value;}"
        "auto get()const->i64{return value;}};"
    )
    for expression, expected in [
        ("t.next()/t.next()", 2),
        ("t.next()%t.next()", 102),
        ("20/t.next()/t.next()", 1002),
        ("t.next()*t.next()/t.next()%t.next()", 4),
    ]:
        yield Case(
            "left-to-right once " + expression,
            f"Trace t=Trace();i64 value={expression};return value*100+t.get();",
            expected,
            prelude=trace,
        )
    yield Case(
        "nested calls preserve dividend",
        "return id(-87)/id(9)+id(-87)%id(9);",
        -15,
        prelude="auto id(i64 x)->i64{return x;}",
    )
    yield Case(
        "receiver survives checked division",
        "Cell c=Cell(-17);return c.result();",
        -5,
        prelude="class Cell{i64 n;public:Cell(i64 x):n(x){}auto result()const->i64{return n/5+n%5;}};",
    )
    yield Case(
        "DivResult independent copies and class boundary",
        "const std::DivResult a=std::div(-17,5);std::DivResult b=a;"
        "std::DivResult c=copy(b);return a.quot()+b.rem()+c.quot()+c.rem();",
        -10,
        prelude="auto copy(std::DivResult x)->std::DivResult{return x;}",
        library=True,
    )
    yield Case(
        "DivResult remains alive across subsequent call",
        f"std::DivResult a=std::div({MIN},3);std::DivResult b=std::div({MAX},2);return a.rem()+b.rem();",
        -1,
        library=True,
    )
    yield Case(
        "DivResult loop local",
        "i64 n=0;i64 sum=0;while(n<7){const std::DivResult d=std::div(n,3);sum=sum+d.quot()+d.rem();n=n+1;}return sum;",
        11,
        library=True,
    )
    for function in ["gcd", "lcm"]:
        yield Case(
            function + " arguments evaluated before zero shortcut",
            f"return std::{function}(0,{MAX}+1);",
            Trap.OVERFLOW,
            library=True,
        )


def app(body, imports=""):
    return "module app; " + imports + " auto test() -> i64 { " + body + " }"


def surface_cases(suite):
    """Checked division and std.integer through literals, calls, classes and arrays."""
    for a, b, q, r in [
        (85, 2, 42, 1),
        (-85, 2, -42, -1),
        (85, -2, -42, 1),
        (-85, -2, 42, -1),
        (1, 2, 0, 1),
        (-1, 2, 0, -1),
        (1, -2, 0, 1),
        (-1, -2, 0, -1),
        (MIN, 2, -4611686018427387904, 0),
    ]:
        suite.check(f"quotient {a} {b}", app(f"return ({a}) / ({b});"), q)
        suite.check(f"remainder {a} {b}", app(f"return ({a}) % ({b});"), r)
    suite.check("multiplicative left associativity", app("return 48 / 8 * 7;"))
    suite.check("remainder multiplication precedence", app("return 20 % 6 * 21;"))
    suite.check("arithmetic precedence", app("return 2 + 80 / 4 * 2;"))
    suite.check("comment and division lexing", "module app;auto test()->i64{return 84 / // denominator follows\n 2;}")
    suite.check(
        "nested function division", "module app;auto id(i64 x)->i64{return x;}auto test()->i64{return 1+id(83)/id(2);}"
    )
    counter = (
        "class Counter{i64 n;public:Counter():n(0){}auto next()->i64{n=n+1;return n;}auto get()const->i64{return n;}};"
    )
    suite.check(
        "quotient evaluates once left to right",
        "module app;"
        + counter
        + "auto test()->i64{Counter c=Counter();const i64 q=c.next()/c.next();return q*10+c.get();}",
        2,
    )
    suite.check(
        "remainder evaluates once left to right",
        "module app;"
        + counter
        + "auto test()->i64{Counter c=Counter();const i64 r=c.next()%c.next();return r*10+c.get();}",
        12,
    )
    for expression in ["true / false", "true % false", "1 / true", "false % 1"]:
        suite.reject("division operand type " + expression, app("return " + expression + ";"), "expected")
    suite.reject(
        "owned integer not implicitly divisible",
        app("own<i64> x=own(42);return x/1;"),
        "cannot be implicitly copied",
    )
    suite.check("division in checked index", app("array<i64,2> a={0,42};return a[3/2];"))
    library = "import std.integer;"
    suite.check(
        "division through class result ABI",
        app("const std::DivResult result=std::div(85,2);return result.quot();", library),
    )
    suite.check(
        "class result remainder", app("const std::DivResult result=std::div(-85,2);return result.rem();", library), -1
    )
    suite.reject(
        "div result private field",
        app("const std::DivResult result=std::div(85,2);return result.quotient;", library),
        "private class field",
    )
    suite.reject(
        "div result designated construction denied",
        app("const std::DivResult result=std::DivResult{.quotient=42,.remainder=1};return result.quot();", library),
        "designated",
    )
    suite.check(
        "library div zero traps",
        app("const std::DivResult result=std::div(42,0);return result.quot();", library),
        Trap.ZERO,
    )
    for a, b in [(0, 42), (42, 0), (-6, 21), (6, -21), (-6, -21), (21, 6)]:
        for name, oracle in [("gcd", gcd), ("lcm", lcm)]:
            suite.check(f"library {name} {a} {b}", app(f"return std::{name}({a},{b});", library), oracle(a, b))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=7043)
    parser.add_argument("--random-count", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    require(0 <= args.random_count <= 10000, "random-count must be between 0 and 10000")
    suite = Suite(args.compiler, "integer oracle", timeout=args.timeout)
    for case in generated_cases(args.seed, args.random_count):
        imports = ("std.integer",) if case.library else ()
        suite.value(case.name, case.body, case.expected, "i64", case.prelude, imports)
    surface_cases(suite)
    suite.finish()


if __name__ == "__main__":
    sys.exit(main())
