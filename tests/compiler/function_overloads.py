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
    s.check(
        "class temporary selects copied overload",
        p(
            "return pick(Counter(42));",
            COUNTER + "auto pick(Counter c)->i64{return c.get();}auto pick(i64 c)->i64{return c;}",
        ),
        42,
    )
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
    s.check(
        "zero through six parameters",
        p(
            "return pick()+pick(1,2,3,4,5,6);",
            "auto pick()->i64{return 21;}auto pick(i64 a,i64 b,i64 c,i64 d,i64 e,i64 f)->i64{return a+b+c+d+e+f;}",
        ),
    )
    s.check(
        "nested exact selection",
        p(
            "return pick(inc(41));",
            (
                "auto inc(i64 x)->i64{return x+1;}auto inc(u8 x)->u8{return x;}auto pick(i64 x)->i64{return x;}"
                "auto pick(u8 x)->i64{return 0;}"
            ),
        ),
    )
    s.check(
        "scalar arguments evaluate once left to right",
        p(
            "Counter c=Counter(0);return pick(c.add(1),c.add(10),c.add(100));",
            COUNTER
            + (
                "auto pick(i64 a,i64 b,i64 c)->i64{if(a==1){if(b==11){if(c==111){return 42;}}}return 0;}auto pi"
                "ck(u8 a,u8 b,u8 c)->i64{return 1;}"
            ),
        ),
    )
    s.check(
        "class snapshot before later mutation",
        p(
            "Counter c=Counter(41);return pick(c,c.add(1));",
            COUNTER
            + (
                "auto pick(Counter c,i64 v)->i64{if(c.get()==41){return v;}return 0;}auto pick(i64 c,i64 v)->i6"
                "4{return 0;}"
            ),
        ),
    )
    s.check(
        "class snapshot after earlier mutation",
        p(
            "Counter c=Counter(41);return pick(c.add(1),c);",
            COUNTER
            + (
                "auto pick(i64 v,Counter c)->i64{if(c.get()==42){return v;}return 0;}auto pick(i64 v,i64 c)->i6"
                "4{return 0;}"
            ),
        ),
    )
    s.check(
        "copied class results",
        p(
            "Counter c=Counter(42);Counter result=pick(c);c.add(1);return result.get();",
            COUNTER + "auto pick(Counter c)->Counter{return c;}auto pick(i64 c)->i64{return c;}",
        ),
    )
    s.check(
        "result type irrelevant but distinct arguments",
        p(
            "Counter c=pick(42);return c.get();",
            COUNTER
            + "auto pick(i64 n)->Counter{const Counter c=Counter(n);return c;}auto pick(u8 n)->bool{return true;}",
        ),
    )
    s.check(
        "nominal enums",
        p(
            "return pick(B::ready);",
            "enum class A{ready};enum class B{ready};auto pick(A x)->i64{return 0;}auto pick(B x)->i64{return 42;}",
        ),
    )
    s.check(
        "nominal empty classes",
        p(
            "B b=B();return pick(b);",
            "class A{public:A(){}};class B{public:B(){}};auto pick(A x)->i64{return 0;}auto pick(B x)->i64{return 42;}",
        ),
    )
    s.check(
        "readonly span and scalar dispatch",
        p(
            "array<u8,1> a={42u8};return pick(borrow_bytes(a));",
            "auto pick(builtin::span<const u8> a)->i64{return i64(a.at(0));}auto pick(i64 x)->i64{return x;}",
        ),
    )
    s.check(
        "readonly span reborrow cleanup",
        p(
            (
                "array<u8,1> a={41u8};{const builtin::span<const u8> b=borrow_bytes(a);pick(b);}a[0]=42u8;retur"
                "n pick(borrow_bytes(a));"
            ),
            "auto pick(builtin::span<const u8> a)->i64{return i64(a.at(0));}auto pick(i64 x)->i64{return x;}",
        ),
    )
    s.check(
        "ordinary calls in generic body",
        p(
            "return relay<u8>(42u8);",
            (
                "auto pick(i64 x)->i64{return 0;}auto pick(u8 x)->i64{return i64(x);}template<Scalar T>auto rel"
                "ay(T x)->i64{return pick(x);}"
            ),
        ),
    )
    s.check(
        "ordinary overload calls explicit generic result",
        p(
            "return pick(identity<u8>(42u8));",
            (
                "auto pick(i64 x)->i64{return 0;}auto pick(u8 x)->i64{return i64(x);}template<Scalar T>auto ide"
                "ntity(T x)->T{return x;}"
            ),
        ),
    )
    s.check(
        "constructor initializer uses overload",
        p(
            "Counter c=Counter(pick(40u8));return c.get();",
            COUNTER + "auto pick(i64 x)->i64{return 0;}auto pick(u8 x)->i64{return i64(x)+2;}",
        ),
    )
    s.check(
        "ordinary overload call from method",
        p(
            "Box b=Box();return b.run();",
            (
                "auto pick(i64 x)->i64{return x;}auto pick(u8 x)->i64{return 0;}class Box{public:Box(){}auto ru"
                "n()const->i64{return pick(42);}};"
            ),
        ),
    )
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
    s.check(
        "private overload available to defining body",
        p("return api::pick(42u8);", imports="import helpers;"),
        modules={"helpers": module},
    )
    s.reject(
        "private overload unavailable to importer",
        p("return api::pick(42);", imports="import helpers;"),
        "no exact",
        modules={"helpers": module},
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
    s.reject(
        "unused cross-module overload collision",
        p("return 42;", imports="import left;import right;"),
        "ambiguous",
        modules={
            "left": "export module left;export auto pick(i64 n)->i64{return n;}",
            "right": "export module right;export auto pick(u8 n)->i64{return i64(n);}",
        },
    )
    s.check(
        "nested argument overflow exact trap",
        p(
            "return pick(9223372036854775807+1);",
            "auto pick(i64 n)->i64{return n;}auto pick(u8 n)->i64{return i64(n);}",
        ),
        Trap.OVERFLOW,
    )
    s.check(
        "nested argument bounds exact trap",
        p(
            "array<i64,1> a={42};return pick(a[1]);",
            "auto pick(i64 n)->i64{return n;}auto pick(u8 n)->i64{return i64(n);}",
        ),
        Trap.BOUNDS,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    args = parser.parse_args()
    suite = Suite(args.compiler, "function overloads", ignore_case=True)
    cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
