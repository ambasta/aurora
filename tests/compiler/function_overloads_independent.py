#!/usr/bin/env python3
"""Independent safe ordinary-function overload acceptance. No implementation imports.

Uses the established full-width native observer and byte-preserving rejection
harness. Every negative runs with absent and pre-existing output. Python -O does
not disable assertions. Failed cases are preserved; successful temporary native
artifacts are removed. Declaration-order permutations overlap, not new language
coverage. This is bounded evidence, not a memory-safety or equivalence proof.
"""

from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from composed_values import Trap, program as p, require
from function_templates import Suite

ROOT = Path(__file__).resolve().parents[2]
SCALARS = ("i64", "u64", "u8", "bool")
VALUES = ("42", "42u64", "42u8", "true")
SPAN = "builtin::span<const u8>"
COUNTER = (
    "class Counter{i64 value;public:Counter(i64 x):value(x){}"
    "auto get()const->i64{return value;}"
    "auto add(i64 x)->i64{value=value+x;return value;}};"
)
PAIR = "class Pair{public:i64 value;Pair(i64 x):value(x){}};class Other{public:i64 value;Other(i64 x):value(x){}};"
ENUMS = "enum class First{ready,bad};enum class Second{ready,bad};"
SPAN_OVERLOADS = f"auto pick({SPAN} b)->i64{{return i64(b.at(0));}}auto pick(i64 x)->i64{{return x;}}"


def scalar_cases(s):
    definitions = "".join(f"auto pick({t} x)->i64{{return {index + 1};}}" for index, t in enumerate(SCALARS))
    for i, value in enumerate(VALUES):
        s.check("exact scalar category " + SCALARS[i], p("return pick(" + value + ");", definitions), i + 1)
    for order in itertools.permutations(range(4)):
        # All 24 source declaration orders must select the same nominal tuple.
        definitions = "".join(f"auto pick({SCALARS[i]} x)->i64{{return {i + 1};}}" for i in order)
        s.check(
            "declaration order " + "".join(map(str, order)),
            p("return pick(42)+pick(42u64)*10+pick(42u8)*100+pick(true)*1000;", definitions),
            4321,
        )
    for arity in range(7):
        definitions = "".join(
            "auto count(" + ",".join(f"i64 x{i}" for i in range(n)) + ")->i64{" + f"return {n};" + "}" for n in range(7)
        )
        s.check(
            "exact arity " + str(arity),
            p("return count(" + ",".join("1" for _ in range(arity)) + ");", definitions),
            arity,
        )
    definitions = "".join(
        f"auto pick({a} a,{b} b)->i64{{return {i};}}" for i, (a, b) in enumerate(itertools.product(SCALARS, repeat=2))
    )
    calls = [f"pick({VALUES[i]},{VALUES[j]})" for i in range(4) for j in range(4)]
    s.check("ordered scalar tuples sixteen-way", p("return " + "+".join(calls) + ";", definitions), sum(range(16)))
    for scalar, value, expected in [
        ("i64", "-9223372036854775808", -(1 << 63)),
        ("u64", "18446744073709551615u64", (1 << 64) - 1),
        ("u8", "255u8", 255),
        ("bool", "true", 1),
    ]:
        definitions = "".join(f"auto exact({t} x)->{t}{{return x;}}" for t in SCALARS)
        s.check(
            "full width selected return " + scalar, p(f"return exact({value});", definitions, result=scalar), expected
        )
    s.check(
        "nested overload selection",
        p(
            "return outer(inner(40u8));",
            "auto inner(u8 n)->i64{return i64(n)+2;}auto inner(bool b)->bool{return b;}"
            "auto outer(i64 n)->i64{return n;}auto outer(bool b)->i64{return 1;}",
        ),
    )
    s.check(
        "ordinary call from explicit specialization",
        p(
            "return relay<u8>(42u8);",
            "auto pick(i64 x)->i64{return 1;}auto pick(u8 x)->i64{return i64(x);}"
            "template<Scalar T>auto relay(T x)->i64{return pick(x);}",
        ),
    )
    s.check(
        "ordinary overload from concrete class template body",
        p(
            "const Box<u8> value=Box<u8>(42u8);return value.get();",
            "auto pick(i64 x)->i64{return 1;}auto pick(u8 x)->i64{return i64(x);}"
            "template<Scalar T>class Box{T v;public:Box(T x):v(x){}"
            "auto get()const->i64{return pick(v);}};",
        ),
    )
    s.check(
        "constructor initializer overload",
        p(
            "const C c=C(42u8);return c.get();",
            "auto pick(i64 x)->i64{return 1;}auto pick(u8 x)->i64{return i64(x);}"
            "class C{i64 v;public:C(u8 n):v(pick(n)){}auto get()const->i64{return v;}};",
        ),
    )
    s.check(
        "implicit method shadows ordinary overload set",
        p(
            "C c=C();return c.get();",
            "auto pick(i64 x)->i64{return 1;}auto pick(bool x)->i64{return 2;}"
            "class C{public:C(){}auto pick(i64 x)const->i64{return x;}"
            "auto get()const->i64{return pick(42);}};",
        ),
    )
    s.check(
        "qualified function call bypasses method same leaf",
        p(
            "C c=C();return c.get();",
            "namespace tools{auto pick(i64 x)->i64{return x;}auto pick(bool x)->i64{return 1;}}"
            "class C{public:C(){}auto pick(i64 x)const->i64{return 1;}"
            "auto get()const->i64{return tools::pick(42);}};",
        ),
    )


def value_cases(s):
    s.check(
        "overload consumes nested template and named method results",
        p(
            "Source source=Source();return pick(copy<Pair>(source.make()));",
            PAIR + "class Source{public:Source(){}auto make()const->Pair{return Pair(42);}};"
            "template<Value T>auto copy(T value)->T{return value;}"
            "auto pick(Pair value)->i64{return value.value;}auto pick(Other value)->i64{return 0;}",
        ),
    )
    s.check(
        "nested copied overload results select actual nominal types",
        p(
            "return pick(make(20))+pick(make(22u8));",
            PAIR + "auto make(i64 n)->Pair{return Pair(n);}auto make(u8 n)->Other{return Other(i64(n));}"
            "auto pick(Pair x)->i64{return x.value;}auto pick(Other x)->i64{return x.value;}",
        ),
    )
    s.check(
        "nested copied overload staging never replays effects",
        p(
            "Counter c=Counter(0);return take(make(c.add(1)),make(c.add(1)))+c.get();",
            COUNTER + PAIR + "auto make(i64 n)->Pair{return Pair(n);}auto make(bool n)->Other{return Other(99);}"
            "auto take(Pair a,Pair b)->i64{return a.value*38+b.value;}auto take(Other a,Other b)->i64{return 0;}",
        ),
    )
    for first, second, trap in (
        ("9223372036854775807+1", "1/0", Trap.OVERFLOW),
        ("1/0", "9223372036854775807+1", Trap.ZERO),
    ):
        s.check(
            "copied producer first trap wins " + trap.name,
            p(
                "return take(make(" + first + "),Pair(" + second + "));",
                PAIR + "auto make(i64 n)->Pair{return Pair(n);}auto make(bool n)->Other{return Other(0);}"
                "auto take(Pair a,Pair b)->i64{return 0;}auto take(Other a,Other b)->i64{return 0;}",
            ),
            trap,
        )
    s.reject(
        "copied outer context cannot choose inner result overload",
        p(
            "return take(make(42));",
            PAIR + "auto make(i64 n)->Other{return Other(n);}auto make(u8 n)->Pair{return Pair(i64(n));}"
            "auto take(Pair x)->i64{return x.value;}",
        ),
        error="expected Pair",
    )
    s.check(
        "nominal class equal-layout selection",
        p(
            "Pair a=Pair(40);Other b=Other(2);return pick(a)+pick(b);",
            PAIR + "auto pick(Pair x)->i64{return x.value;}auto pick(Other x)->i64{return x.value;}",
        ),
    )
    s.check(
        "nominal empty classes remain distinct",
        p(
            "A a=A();B b=B();return pick(a)+pick(b);",
            "class A{public:A(){}};class B{public:B(){}};"
            "auto pick(A x)->i64{return 20;}auto pick(B x)->i64{return 22;}",
        ),
    )
    s.check(
        "nominal enums same ordinals remain distinct",
        p(
            "return pick(First::ready)+pick(Second::ready);",
            ENUMS + "auto pick(First x)->i64{return 20;}auto pick(Second x)->i64{return 22;}",
        ),
    )
    s.check(
        "enum and integer same representation distinct",
        p(
            "return pick(First::ready)+pick(0);",
            ENUMS + "auto pick(First x)->i64{return 20;}auto pick(i64 x)->i64{return 22;}",
        ),
    )
    s.check(
        "different result classes selected by argument tuple",
        p(
            "Pair a=make(40);Other b=make(2u8);return a.value+b.value;",
            PAIR + "auto make(i64 x)->Pair{const Pair r=Pair(x);return r;}"
            "auto make(u8 x)->Other{const Other r=Other(i64(x));return r;}",
        ),
    )
    s.check(
        "class result inner binding keeps outer source",
        p(
            "Pair value=Pair(42);if(true){Pair value=copy(value);value.value=1;}return value.value;",
            PAIR + "auto copy(Pair x)->Pair{const Pair r=x;return r;}"
            "auto copy(Other x)->Other{const Other r=x;return r;}",
        ),
    )
    s.check(
        "class arguments immutable independent copies",
        p(
            "Pair a=Pair(20);Pair b=clone(a,a);a.value=0;return b.value;",
            PAIR + "auto clone(Pair x,Pair y)->Pair{Pair z=x;z.value=z.value+y.value+2;return z;}"
            "auto clone(Other x,Other y)->Other{const Other z=x;return z;}",
        ),
    )
    s.check(
        "six argument class snapshots once left to right",
        p(
            "Counter c=Counter(1);return inspect(c,c.add(1),c,c.add(1),c,true);",
            COUNTER + "auto inspect(Counter a,i64 b,Counter c,i64 d,Counter e,bool f)->i64{"
            "if(a.get()!=1){return 1;}if(b!=2){return 2;}if(c.get()!=2){return 3;}"
            "if(d!=3){return 4;}if(e.get()!=3){return 5;}if(!f){return 6;}return 42;}"
            "auto inspect(i64 a,i64 b,i64 c,i64 d,i64 e,bool f)->i64{return 9;}",
        ),
    )
    s.check(
        "scalar effects evaluated once left to right",
        p(
            "Counter c=Counter(0);i64 result=inspect(c.add(1),c.add(1),c.add(1));"
            "if(c.get()!=3){return 1;}return result;",
            COUNTER + "auto inspect(i64 a,i64 b,i64 c)->i64{return a*100+b*10+c;}"
            "auto inspect(u8 a,u8 b,u8 c)->i64{return 1;}",
        ),
        123,
    )
    s.check(
        "nested selected calls do not replay effects",
        p(
            "Counter c=Counter(0);return combine(pick(c.add(1)),pick(c.add(1)));",
            COUNTER + "auto pick(i64 x)->i64{return x;}auto pick(bool b)->i64{return 9;}"
            "auto combine(i64 a,i64 b)->i64{return a*10+b;}auto combine(bool a,bool b)->i64{return 9;}",
        ),
        12,
    )
    s.check(
        "first argument overflow dominates later division trap",
        p(
            "return take(9223372036854775807+1,1/0);",
            "auto take(i64 a,i64 b)->i64{return 0;}auto take(u8 a,u8 b)->i64{return 0;}",
        ),
        Trap.OVERFLOW,
    )
    s.check(
        "first argument division trap dominates later overflow",
        p(
            "return take(1/0,9223372036854775807+1);",
            "auto take(i64 a,i64 b)->i64{return 0;}auto take(u8 a,u8 b)->i64{return 0;}",
        ),
        Trap.ZERO,
    )
    s.check(
        "span temporary releases after overloaded call",
        p(
            "array<u8,1> bytes={40u8};i64 a=pick(borrow_bytes(bytes));bytes[0]=2u8;return a+pick(borrow_bytes(bytes));",
            SPAN_OVERLOADS,
        ),
    )
    s.check(
        "named span forwarded through overloaded calls",
        p(
            f"array<u8,1> bytes={{42u8}};const {SPAN} v=borrow_bytes(bytes);return forward(v);",
            SPAN_OVERLOADS + f"auto forward({SPAN} v)->i64{{return pick(v);}}auto forward(u8 b)->i64{{return i64(b);}}",
        ),
    )
    s.check(
        "span and class mixed copied return",
        p(
            "array<u8,1> bytes={2u8};Pair source=Pair(40);Pair result=join(source,borrow_bytes(bytes));"
            "source.value=0;bytes[0]=0u8;return result.value;",
            PAIR + f"auto join(Pair x,{SPAN} b)->Pair{{const Pair r=Pair(x.value+i64(b.at(0)));return r;}}"
            "auto join(Other x,i64 b)->Other{const Other r=x;return r;}",
        ),
    )
    s.check(
        "selected span bounds trap",
        p(
            "array<u8,1> bytes={42u8};return inspect_bytes(borrow_bytes(bytes),1);",
            f"auto inspect_bytes({SPAN} b,i64 i)->i64{{return i64(b.at(i));}}"
            "auto inspect_bytes(i64 a,i64 b)->i64{return 42;}",
        ),
        Trap.BOUNDS,
    )


def module_cases(s):
    both = "export module lib;export auto pick(i64 x)->i64{return x;}export auto pick(bool x)->i64{return 1;}"
    s.check("imported exported ordinary set", p("return pick(42);", imports="import lib;"), modules={"lib": both})
    for reverse in (False, True):
        public = "export auto pick(i64 x)->i64{return x;}"
        private = "auto pick(bool x)->i64{return 1;}"
        lib = "export module lib;" + (private + public if reverse else public + private)
        s.check(
            "mixed private public member selection " + str(reverse),
            p("return pick(42);", imports="import lib;"),
            modules={"lib": lib},
        )
        s.reject(
            "private member inaccessible " + str(reverse),
            p("return pick(true);", imports="import lib;"),
            modules={"lib": lib},
        )
    s.check(
        "hidden private signature does not poison visible overload",
        p("return pick(42);", imports="import lib;"),
        modules={
            "lib": "export module lib;class Secret{public:i64 x;};"
            "auto pick(Secret x)->i64{return x.x;}export auto pick(i64 x)->i64{return x;}"
        },
    )
    s.check(
        "defining module helper binding preserved",
        p("return wrap();", imports="import lib;"),
        modules={
            "lib": "export module lib;auto pick(i64 x)->i64{return x;}auto pick(u8 x)->i64{return 1;}"
            "export auto wrap()->i64{return pick(42);}"
        },
    )
    s.check(
        "nominal imported classes same layout distinct",
        p(
            "left::Item a=left::Item(20);right::Item b=right::Item(22);return pick(a)+pick(b);",
            "auto pick(left::Item x)->i64{return x.x;}auto pick(right::Item x)->i64{return x.x;}",
            imports="import left;import right;",
        ),
        modules={
            n: "export module " + n + ";export namespace " + n + "{class Item{public:i64 x;Item(i64 a):x(a){}};}"
            for n in ("left", "right")
        },
    )
    s.reject(
        "two imports collide eagerly despite disjoint tuples",
        p("return 42;", imports="import left;import right;"),
        modules={
            "left": "export module left;export auto pick(i64 x)->i64{return x;}",
            "right": "export module right;export auto pick(u8 x)->i64{return i64(x);}",
        },
    )
    s.reject(
        "local and import collide eagerly despite disjoint tuples",
        p("return 42;", "auto pick(u8 x)->i64{return i64(x);}", imports="import lib;"),
        modules={"lib": both},
    )
    s.reject(
        "transitive overload set unavailable",
        p("return pick(42);", imports="import bridge;"),
        modules={"lib": both, "bridge": "export module bridge;import lib;export auto wrap()->i64{return pick(42);}"},
    )
    s.reject(
        "exported overload exposes private parameter unused",
        p("return 42;", imports="import lib;"),
        modules={
            "lib": "export module lib;class Secret{public:i64 x;};"
            "export auto pick(Secret x)->i64{return x.x;}export auto pick(i64 x)->i64{return x;}"
        },
    )
    s.reject(
        "private-only set unavailable",
        p("return pick(42);", imports="import lib;"),
        modules={"lib": "export module lib;auto pick(i64 x)->i64{return x;}auto pick(bool x)->i64{return 1;}"},
    )
    s.check(
        "nearest lexical overload set selected",
        p(
            "return outer::inner::run();",
            "namespace outer{auto pick(i64 x)->i64{return 1;}auto pick(bool x)->i64{return 2;}"
            "namespace inner{auto pick(i64 x)->i64{return x;}auto pick(u8 x)->i64{return 3;}"
            "auto run()->i64{return pick(42);}}}",
        ),
    )
    s.reject(
        "nearest lexical set does not fall back on no match",
        p(
            "return outer::inner::run();",
            "namespace outer{auto pick(i64 x)->i64{return x;}auto pick(bool x)->i64{return 1;}"
            "namespace inner{auto pick(u8 x)->i64{return 2;}auto pick(u64 x)->i64{return 3;}"
            "auto run()->i64{return pick(42);}}}",
        ),
    )


def rejected_cases(s):
    base = "auto pick(i64 x)->i64{return x;}auto pick(u64 x)->i64{return 1;}"
    for val in ("true", "42u8", "1u8+2u8"):
        s.reject("no implicit conversion " + val, p("return pick(" + val + ");", base))
    s.reject("wrong arity no overload", p("return pick();", base))
    s.reject("more than six actual arguments", p("return pick(1,2,3,4,5,6,7);", base))
    for result in ("i64", "bool"):
        s.reject(
            "duplicate parameter tuple with return " + result,
            p(
                "return 42;",
                "auto pick(i64 x)->i64{return x;}auto pick(i64 y)->"
                + result
                + "{return "
                + ("true" if result == "bool" else "1")
                + ";}",
            ),
        )
    s.reject(
        "duplicate resolved qualified class tuple",
        p(
            "return 42;",
            "namespace n{class C{public:i64 x;};auto pick(C x)->i64{return 1;}auto pick(n::C y)->bool{return true;}}",
        ),
    )
    s.reject("root answer overloaded", "module app;auto answer()->i64{return 42;}auto answer(i64 x)->i64{return x;}")
    s.reject(
        "result context cannot select scalar overload",
        p("return pick(42);", "auto pick(i64 x)->bool{return true;}auto pick(u8 x)->i64{return 42;}"),
    )
    s.reject(
        "result context cannot select class overload",
        p(
            "Pair x=make(42);return x.value;",
            PAIR + "auto make(i64 x)->Other{const Other r=Other(x);return r;}"
            "auto make(u8 x)->Pair{const Pair r=Pair(i64(x));return r;}",
        ),
    )
    s.check(
        "class temporary argument selects exact overload",
        p(
            "return pick(Pair(42));",
            PAIR + "auto pick(Pair x)->i64{return x.value;}auto pick(Other x)->i64{return x.value;}",
        ),
    )
    s.reject(
        "class parameter remains readonly",
        p(
            "Pair x=Pair(42);return pick(x);",
            PAIR + "auto pick(Pair x)->i64{x.value=1;return x.value;}auto pick(i64 x)->i64{return x;}",
        ),
    )
    s.reject(
        "span cannot escape overloaded result",
        p("return 42;", f"auto pick({SPAN} b)->{SPAN}{{return b;}}auto pick(i64 x)->i64{{return x;}}"),
    )
    s.reject(
        "named span borrowing remains live after call",
        p(f"array<u8,1> b={{42u8}};const {SPAN} v=borrow_bytes(b);i64 x=pick(v);b[0]=1u8;return x;", SPAN_OVERLOADS),
    )
    s.reject("own cannot be implicit overload argument", p("own value=own(42);return pick(value);", base))
    s.reject("array cannot be overload argument", p("array<i64,1> value={42};return pick(value);", base))
    s.reject(
        "functions and class names remain exclusive",
        p("return 42;", "class pick{public:i64 x;};auto pick(i64 x)->i64{return x;}auto pick(bool b)->i64{return 1;}"),
    )
    s.reject(
        "functions and namespace names remain exclusive",
        p("return 42;", "namespace pick{}auto pick(i64 x)->i64{return x;}auto pick(bool b)->i64{return 1;}"),
    )
    for order in (False, True):
        ordinary = "auto pick(i64 x)->i64{return x;}auto pick(bool b)->i64{return 1;}"
        template = "template<Scalar T>auto pick(T x)->T{return x;}"
        s.reject(
            "function template exclusive name " + str(order),
            p("return 42;", ordinary + template if order else template + ordinary),
        )
    s.reject("explicit template args do not select ordinary overload", p("return pick<i64>(42);", base))
    s.reject(
        "function template deduction remains unavailable",
        p("return pick(42);", "template<Scalar T>auto pick(T x)->T{return x;}"),
    )
    s.reject(
        "method overloading remains unavailable",
        p("return 42;", "class C{public:C(){}auto pick(i64 x)->i64{return x;}auto pick(bool b)->i64{return 1;}};"),
    )
    s.reject(
        "constructor overloading remains unavailable",
        p("return 42;", "class C{i64 x;public:C(i64 n):x(n){}C(bool b):x(1){}};"),
    )


def budget_cases(s):
    tuples = list(itertools.product(SCALARS, repeat=3))

    def declaration(index):
        a, b, c = tuples[index]
        return f"auto pick({a} a,{b} b,{c} c)->i64{{return {index};}}"

    defs = "".join(declaration(i) for i in range(32))
    calls = ["pick(" + ",".join(VALUES[SCALARS.index(t)] for t in tup) + ")" for tup in tuples[:32]]
    s.check("exact 32 declarations accepted", p("return " + "+".join(calls) + ";", defs), sum(range(32)))
    s.reject("33 declarations rejected", p("return 42;", defs + declaration(32)))
    s.reject(
        "duplicate tuple at declaration 32 rejected",
        p("return 42;", "".join(declaration(i) for i in range(31)) + declaration(0)),
    )


def artifact_checks(compiler, baseline, root):
    """Repeatability, old-single-function differential, and host entry seam."""
    records = []
    fixtures = {
        "overloaded-private-symbols": p(
            "return pick(42);", "auto pick(i64 x)->i64{return x;}auto pick(u8 x)->i64{return 1;}"
        ),
        "single-scalar-symbol": p("return identity(42);", "auto identity(i64 x)->i64{return x;}"),
        "single-class-call": p("Pair x=Pair(42);return pick(x);", PAIR + "auto pick(Pair x)->i64{return x.value;}"),
        "single-wrong-arity": p("return pick();", "auto pick(i64 x)->i64{return x;}"),
        "single-wrong-type": p("return pick(true);", "auto pick(i64 x)->i64{return x;}"),
    }
    for name, source in fixtures.items():
        directory = root / name
        directory.mkdir(exist_ok=True)
        inp = directory / "input.au"
        inp.write_text(source)
        output = directory / "candidate.s"
        cmd = [str(compiler), str(inp), "-o", str(output)]
        first = subprocess.run(cmd, capture_output=True, timeout=10)
        first_bytes = output.read_bytes() if output.exists() else None
        again = subprocess.run(cmd, capture_output=True, timeout=10)
        require(
            (first.returncode, first.stdout, first.stderr, first_bytes)
            == (again.returncode, again.stdout, again.stderr, output.read_bytes() if output.exists() else None),
            name + ": repeated compilation differs",
        )
        if name == "overloaded-private-symbols":
            require(first.returncode == 0, name + ": compilation failed: " + first.stderr.decode())
            assembly = first_bytes.decode()
            public = [line.split()[1] for line in assembly.splitlines() if line.startswith(".globl ")]
            require(
                "pick" not in public and not any("pick" in x for x in public),
                "overload scalar implementation has public linkage: " + repr(public),
            )
            require(
                any(line.startswith(".local ") and "pick" in line for line in assembly.splitlines()),
                "no private overload symbol found",
            )
        elif baseline:
            old = directory / "baseline.s"
            result = subprocess.run([str(baseline), str(inp), "-o", str(old)], capture_output=True, timeout=10)
            require(
                (first.returncode, first.stdout, first.stderr, first_bytes)
                == (result.returncode, result.stdout, result.stderr, old.read_bytes() if old.exists() else None),
                name + ": single-declaration baseline differential failed",
            )
        records.append(
            {
                "fixture": name,
                "status": first.returncode,
                "assembly_sha256": hashlib.sha256(first_bytes).hexdigest() if first_bytes else None,
            }
        )
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "evidence/function-overloads/independent/source-run")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--fixture", default="")
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args()
    require(args.plan_only or args.compiler is not None, "compiler required")
    compiler = args.compiler.resolve() if args.compiler else None
    baseline = args.baseline.resolve() if args.baseline else None
    args.artifacts.mkdir(parents=True, exist_ok=True)
    work = args.artifacts / "cases"
    work.mkdir(exist_ok=True)
    start = time.monotonic()
    pin = hashlib.sha256(compiler.read_bytes()).hexdigest() if compiler else None
    suite = Suite(work, compiler, args.keep_going, args.fixture, args.plan_only)
    for group in (scalar_cases, value_cases, module_cases, rejected_cases, budget_cases):
        group(suite)
    extra = []
    if not args.plan_only and not args.fixture:
        try:
            extra = artifact_checks(compiler, baseline, args.artifacts)
        except (AssertionError, OSError, subprocess.TimeoutExpired) as error:
            suite.failures.append(str(error))
            print("FAIL artifact checks:", error, flush=True)
    summary = {
        "compiler": str(compiler),
        "compiler_sha256": pin,
        "selected_fixtures": suite.selected_fixtures,
        "completed_executions": suite.count,
        "rejection_executions": suite.rejections,
        "negative_fixtures": suite.negative_fixtures,
        "exact_traps": suite.traps,
        "artifact_checks": extra,
        "failures": suite.failures,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "plan_only": args.plan_only,
    }
    (args.artifacts / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if compiler:
        require(hashlib.sha256(compiler.read_bytes()).hexdigest() == pin, "compiler changed during run")
    print(json.dumps(summary, indent=2), flush=True)
    require(not suite.failures, f"{len(suite.failures)} independent overload checks failed")


if __name__ == "__main__":
    main()
