#!/usr/bin/env python3
"""Exact ordinary overload selection, native results and rejections.

Cases are data on one native_runner.Suite: complete 64-bit results, exact trap
sites and diagnostic fragments (matched case-insensitively).
"""

import argparse
from itertools import product
from pathlib import Path

from native_runner import Suite, Trap

SCALARS = ("i64", "u64", "u8", "bool")
VALUES = {"i64": "-7", "u64": "18446744073709551615u64", "u8": "255u8", "bool": "true"}
COUNTER = (
    "class Counter{i64 value;public:Counter(i64 n):value(n){}auto get()const->i64{return value;}auto add(i64 n)"
    "->i64{value=value+n;return value;}};"
)


def p(body, definitions="", imports="", result="i64"):
    return "module app;" + imports + definitions + f"auto test()->{result}{{{body}}}"


def cases(s):
    definitions = "".join(f"auto pick({t} x)->i64{{return {i + 39};}}" for i, t in enumerate(SCALARS))
    for i, t in enumerate(SCALARS):
        s.check("four exact scalars " + t, p(f"return pick({VALUES[t]});", definitions), i + 39)
    for left, right in product(SCALARS, repeat=2):
        defs = "".join(
            f"auto pick({a} x,{b} y)->i64{{return {n};}}" for n, (a, b) in enumerate(product(SCALARS, repeat=2))
        )
        expected = list(product(SCALARS, repeat=2)).index((left, right))
        s.check(
            "ordered scalar tuple " + left + "/" + right,
            p(f"return pick({VALUES[left]},{VALUES[right]});", defs),
            expected,
        )
    for number, declarations in enumerate(
        (
            definitions,
            "".join(reversed([f"auto pick({t} x)->i64{{return {i + 39};}}" for i, t in enumerate(SCALARS)])),
        )
    ):
        s.check(f"declaration permutation {number}", p("return pick(true);", declarations))
    for count in (31, 32):
        defs = "".join(f"class C{i}{{public:C{i}(){{}}}};auto pick(C{i} x)->i64{{return {i};}}" for i in range(count))
        s.check("overload budget " + str(count), p(f"C{count - 1} c=C{count - 1}();return pick(c);", defs), count - 1)
    module = (
        "export module helpers;export namespace api{auto pick(i64 n)->i64{return 0;}auto pick(u8 n)->i64{return"
        " i64(n);}}"
    )
    s.check(
        "imported exported set", p("return api::pick(42u8);", imports="import helpers;"), modules={"helpers": module}
    )
    module = (
        "export module helpers;namespace api{auto pick(i64 n)->i64{return n;}export auto pick(u8 n)->i64{return"
        " pick(i64(n));}}"
    )
    for name, defs, body, error in [
        (
            "same tuple duplicate",
            "auto pick(i64 x)->i64{return x;}auto pick(i64 y)->i64{return y;}",
            "return 42;",
            "duplicate",
        ),
        (
            "return cannot discriminate",
            "auto pick(i64 x)->i64{return x;}auto pick(i64 x)->u8{return 1u8;}",
            "return 42;",
            "duplicate",
        ),
        (
            "no implicit conversion",
            "auto pick(u64 x)->i64{return 42;}auto pick(u8 x)->i64{return 42;}",
            "return pick(42);",
            "no exact",
        ),
        (
            "nominal class mismatch",
            (
                "class A{public:A(){}};class B{public:B(){}};class C{public:C(){}};auto pick(A a)->i64{return 1"
                ";}auto pick(B b)->i64{return 2;}"
            ),
            "C c=C();return pick(c);",
            "no exact",
        ),
        (
            "wrong arity before unknown argument",
            "auto pick(i64 a)->i64{return a;}auto pick(u8 a)->i64{return 0;}",
            "return pick(missing,missing);",
            "wrong argument count",
        ),
        (
            "wrong arity before invalid literal",
            "auto pick(i64 a)->i64{return a;}auto pick(u8 a)->i64{return 0;}",
            "return pick(999999999999999999999999999999,1);",
            "wrong argument count",
        ),
        (
            "scalar result cannot initialize class",
            COUNTER + "auto pick(i64 x)->i64{return x;}auto pick(u8 x)->Counter{const Counter c=Counter(42);return c;}",
            "Counter c=pick(42);return c.get();",
            "expected",
        ),
        (
            "class result cannot be scalar",
            COUNTER
            + "auto pick(i64 x)->Counter{const Counter c=Counter(x);return c;}auto pick(u8 x)->i64{return i64(x);}",
            "return pick(42);",
            "typed local",
        ),
        (
            "private field remains inaccessible",
            (
                "class C{i64 secret;public:C():secret(42){}};auto pick(i64 c)->i64{return c;}auto pick(u8 c)->i"
                "64{return i64(c);}"
            ),
            "C c=C();return pick(c.secret);",
            "private",
        ),
        (
            "ordinary template collision",
            "template<Scalar T>auto pick(T x)->T{return x;}auto pick(i64 x)->i64{return x;}",
            "return 42;",
            "duplicate",
        ),
        (
            "ordinary template set collision",
            (
                "template<Scalar T>auto pick(T x)->T{return x;}auto pick(i64 x)->i64{return x;}auto pick(u8 x)-"
                ">i64{return i64(x);}"
            ),
            "return 42;",
            "duplicate",
        ),
        (
            "method overload remains rejected",
            "class C{public:C(){}auto run(i64 x)->i64{return x;}auto run(u8 x)->i64{return i64(x);}};",
            "return 42;",
            "duplicate",
        ),
        (
            "overloaded root answer",
            "auto answer()->i64{return 42;}auto answer(i64 x)->i64{return x;}",
            "return 42;",
            "entrypoint",
        ),
        (
            "seventh parameter remains rejected",
            "auto pick(i64 a,i64 b,i64 c,i64 d,i64 e,i64 f,i64 g)->i64{return 42;}auto pick()->i64{return 42;}",
            "return 42;",
            "six",
        ),
        (
            "namespace name collision",
            "namespace pick{}auto pick(i64 a)->i64{return a;}auto pick(u8 a)->i64{return 0;}",
            "return 42;",
            "collide",
        ),
        (
            "nonmatching narrower scope blocks outer",
            definitions
            + (
                "namespace n{auto pick(u8 a)->i64{return 0;}auto pick(u64 a)->i64{return 0;}auto run()->i64{ret"
                "urn pick(true);}}"
            ),
            "return n::run();",
            "no exact",
        ),
    ]:
        s.reject(name, p(body, defs), error)
    defs = "".join(f"class C{i}{{public:C{i}(){{}}}};auto pick(C{i} x)->i64{{return {i};}}" for i in range(33))
    s.reject("33 declaration budget rejected", p("return 42;", defs), "32")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    suite = Suite(args.compiler, "function overloads", ignore_case=True)
    suite.load(Path(__file__).with_suffix(".cases"), COUNTER=COUNTER)
    cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
