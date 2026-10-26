#!/usr/bin/env python3
"""Exact-bool logical operators against Python's boolean AST.

Python's independent boolean AST supplies values and observable call traces.
Cases are data on one native_runner.Suite: complete 64-bit results, exact trap
sites and diagnostic fragments (matched case-insensitively).
"""

import argparse
import ast
from itertools import product
from pathlib import Path
import random

from function_overloads import p, COUNTER
from native_runner import Suite, Trap

TRACE = """class Trace { i64 value; public: Trace():value(0){}
auto mark(i64 digit,bool answer)->bool{value=value*10+digit;return answer;}
auto get()const->i64{return value;} };"""
SPAN = "builtin::span<const u8>"
MAX_I64 = (1 << 63) - 1


def boolean(value):
    return "true" if value else "false"


def model(expression, values):
    """A different parser/evaluator: Python AST, no Aurora metadata or assembly."""
    tree = ast.parse(expression.replace("&&", " and ").replace("||", " or ").replace("!", " not ").strip(), mode="eval")
    trace = []

    def visit(node):
        if isinstance(node, ast.Name):
            index = int(node.id[1:])
            trace.append(index + 1)
            return values[index]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not visit(node.operand)
        if isinstance(node, ast.BoolOp):
            for child in node.values:
                result = visit(child)
                if isinstance(node.op, ast.And) and not result:
                    return False
                if isinstance(node.op, ast.Or) and result:
                    return True
            return result
        raise AssertionError("unsupported oracle node " + ast.dump(node))

    result = visit(tree.body)
    encoded = 0
    for digit in trace:
        encoded = encoded * 10 + digit
    return result, encoded


def truth_and_order(s, seed):
    for operator in ("&&", "||"):
        for left, right in product((False, True), repeat=2):
            want = left and right if operator == "&&" else left or right
            expression = f"{boolean(left)} {operator} {boolean(right)}"
            s.check("truth " + expression, p("return " + expression + ";", result="bool"), want)
            helper = "auto logic(bool left,bool right)->bool{return left " + operator + " right;}"
            s.check(
                "dynamic truth " + expression,
                p(f"return logic({boolean(left)},{boolean(right)});", helper, result="bool"),
                want,
            )
    expressions = [
        "v0 || v1 && v2",
        "v0 && v1 || v2",
        "(v0 || v1) && v2",
        "v0 && (v1 || v2)",
        "!v0 || !v1 && !v2",
        "!(v0 || v1) && !v2",
        "v0 || (v1 && v2) || v3",
        "v0 && (v1 || v2) && v3",
        "v0 && v1 && v2 && v3",
        "v0 || v1 || v2 || v3",
    ]
    for number, expression in enumerate(expressions):
        for values in product((False, True), repeat=4):
            expected, trace = model(expression, values)
            source = expression
            for index, value in enumerate(values):
                source = source.replace("v" + str(index), f"c.mark({index + 1},{boolean(value)})")
            body = "Trace c=Trace();const bool result=" + source + ";"
            body += "if(result){return 100000000+c.get();}return c.get();"
            s.check(f"trace model {number} {values}", p(body, TRACE), trace + 100000000 * expected)
    rng = random.Random(seed)
    for number in range(32):
        values = tuple(bool(rng.randrange(2)) for _ in range(7))
        expression = "v0"
        for index in range(1, 7):
            operator = rng.choice(("&&", "||"))
            operand = ("!" if rng.randrange(3) == 0 else "") + f"v{index}"
            expression = ("(" + expression + ")" if rng.randrange(3) == 0 else expression) + f" {operator} " + operand
        expected, trace = model(expression, values)
        source = expression
        for index, value in enumerate(values):
            source = source.replace("v" + str(index), f"c.mark({index + 1},{boolean(value)})")
        body = "Trace c=Trace();const bool result=" + source + ";if(result){return 100000000+c.get();}return c.get();"
        s.check(f"seeded mixed trace {number}", p(body, TRACE), trace + 100000000 * expected)


def contexts(s):
    for expression, expected in [
        ("false || true && false", False),
        ("true || false && false", True),
        ("false && false == false", False),
        ("true || false == false", True),
        ("!false && true == true", True),
        ("!true == false || false", True),
        ("1<2 && 3>=3 || 4!=4", True),
        ("(1u64|2u64)==3u64 && (7u64&3u64)==3u64", True),
        ("false || (6u64^3u64)==5u64 && (8u64>>2)==2u64", True),
        ("1+2*3==7 && 12/3%3==1", True),
        ("false == (true || false)", False),
        ("true != false && false == !true", True),
    ]:
        s.check("precedence " + expression, p("return " + expression + ";", result="bool"), expected)
    defs = TRACE + "auto choose(bool b)->i64{if(b){return 1;}return 0;}"
    for prefix in range(6):
        params = ",".join(f"i64 a{i}" for i in range(prefix)) + ("," if prefix else "") + "bool last"
        total = "+".join(f"a{i}" for i in range(prefix)) or "0"
        helper = f"auto combine({params})->i64{{if(last){{return {total}+1;}}return 0;}}"
        arguments = ",".join(str(i + 1) for i in range(prefix)) + ("," if prefix else "") + "false || c.mark(1,true)"
        s.check(
            f"logical final argument with {prefix} pending scalars",
            p("Trace c=Trace();return combine(" + arguments + ");", defs + helper),
            sum(range(1, prefix + 1)) + 1,
        )
    s.check("nested binary saved operands", p("return 11+choose(3==3 && (false||true))*31;", defs), 42)
    for left in ("true", "false"):
        s.check(
            "temporary whole span cleanup " + left,
            p(
                f"array<u8,1> a={{41u8}};const bool b={left} || see(borrow_bytes(a));a[0]=42u8;return i64(a[0]);",
                f"auto see({SPAN} a)->bool{{return a.at(0)==41u8;}}",
            ),
            42,
        )
        s.check(
            "temporary subspan cleanup " + left,
            p(
                f"array<u8,2> a={{1u8,41u8}};{{const {SPAN} v=borrow_bytes(a);co"
                f"nst bool b={left} || see(v.subspan(1,1));}}a[1]=42u8;return i6"
                f"4(a[1]);",
                f"auto see({SPAN} a)->bool{{return a.at(0)==41u8;}}",
            ),
            42,
        )
    s.check(
        "subspan count contains lazy call",
        p(
            f"array<u8,2> a={{41u8,42u8}};const {SPAN} v=borrow_bytes(a);con"
            f"st {SPAN} w=v.subspan(1,choose(false||true));return i64(w.at(0"
            f"));",
            defs,
        ),
        42,
    )
    helper = COUNTER + "auto check(Counter snapshot,bool b)->bool{return snapshot.get()==41&&b;}"
    s.check(
        "class snapshot before later lazy receiver mutation",
        p("Counter c=Counter(41);if(check(c,false||c.add(1)==42)){return c.get();}return 0;", helper),
        42,
    )
    helper = COUNTER + "auto check(bool b,Counter snapshot)->bool{return b&&snapshot.get()==42;}"
    s.check(
        "class snapshot after earlier lazy receiver mutation",
        p("Counter c=Counter(41);if(check(false||c.add(1)==42,c)){return c.get();}return 0;", helper),
        42,
    )
    helper = COUNTER + "auto copied(Counter a,bool b)->Counter{return a;}"
    s.check(
        "class-return aggregate args",
        p("Counter c=Counter(42);Counter d=copied(c,true&&true);return d.get();", helper),
        42,
    )
    helper = "class Box{bool value;public:Box(bool a,bool b):value(a&&b){}auto get()const->bool{return value||false;}};"
    s.check(
        "constructor and readonly receiver result",
        p("Box b=Box(true,false||true);return b.get();", helper, result="bool"),
        True,
    )
    helper = (
        "class Box{array<bool,2> bits;public:Box():bits{}{}auto run()->bool{bits[0]=true&&(false||true);return "
        "bits[0]&& !bits[1];}};"
    )
    s.check("receiver index guard crossing logical RHS", p("Box b=Box();return b.run();", helper, result="bool"), True)
    s.check(
        "loop condition and short-circuit termination",
        p("Counter c=Counter(0);while(c.get()<42&&c.add(1)<=42){}return c.get();", COUNTER),
        42,
    )


def traps(s):
    payloads = [
        ("signed overflow", f"({MAX_I64}+1)==0", Trap.OVERFLOW, ""),
        ("zero division", "(1/0)==0", Trap.ZERO, ""),
        ("bounds", "a[2]==0", Trap.BOUNDS, "array<i64,1> a={0};"),
        ("unsigned overflow", "(18446744073709551615u64+1u64)==0u64", Trap.OVERFLOW, ""),
        ("byte overflow", "(255u8+1u8)==0u8", Trap.OVERFLOW, ""),
    ]
    for name, rhs, trap, prelude in payloads:
        for op, left in [("&&", False), ("||", True)]:
            s.check(
                "skipped " + name + " " + op, p(prelude + f"return {boolean(left)} {op} ({rhs});", result="bool"), left
            )
        for op, left in [("&&", True), ("||", False)]:
            s.check(
                "required " + name + " " + op, p(prelude + f"return {boolean(left)} {op} ({rhs});", result="bool"), trap
            )
    for rhs in ("(1u64<<64)==0u64", "u8(256)==0u8"):
        s.check("skipped shift or conversion " + rhs, p("return true||" + rhs + ";", result="bool"), True)
        s.check("skipped shift or conversion and " + rhs, p("return false&&" + rhs + ";", result="bool"), False)
    s.check("left trap wins over right trap", p(f"return ({MAX_I64}+1==0) || (1/0==0);", result="bool"), Trap.OVERFLOW)
    s.check("short-circuit does not suppress later trap", p("const bool b=false&&(1/0==0);return 1/0;"), Trap.ZERO)


def rejections(s):
    for operand in ("0", "1u64", "1u8"):
        for op in ("&&", "||"):
            for left, right in [(operand, "true"), ("false", operand)]:
                s.reject(
                    "no numeric truthiness " + left + op + right,
                    p("return " + left + op + right + ";", result="bool"),
                    "expected bool",
                )
    cases = [
        ("unknown skipped name", "return true||missing;", "", "unknown"),
        ("unknown skipped call", "return false&&missing();", "", "unknown"),
        ("overflowing literal skipped", "return true||(9223372036854775808==0);", "", "literal out of range"),
        ("dead illtyped comparison", "return true||(1==true);", "", "expected"),
        ("move cannot be expression", "own<i64> x=own(42);return false&&(move(x)==0);", "", "typed local"),
        ("borrow cannot be expression", "own<i64> x=own(42);return false&&(borrow(x)==0);", "", "typed local"),
        (
            "moved owner remains unavailable",
            "own<i64> x=own(42);own<i64> y=move(x);return true||(read(x)==42);",
            "",
            "use after move",
        ),
        (
            "exclusive owner read skipped",
            "own<i64> x=own(42);mutref<i64> r=borrow_mut(x);return true||(read(x)==42);",
            "",
            "exclusively borrowed",
        ),
        (
            "const reference write skipped",
            "own<i64> x=own(42);const mutref<i64> r=borrow_mut(x);return true||(write(r,0)==0);",
            "",
            "non-const",
        ),
        (
            "private field skipped",
            "Box b=Box();return true||b.secret;",
            "class Box{bool secret;public:Box():secret(true){}};",
            "private",
        ),
        (
            "mutable receiver skipped on const",
            "const Counter c=Counter(0);return true||(c.add(1)==1);",
            COUNTER,
            "mutable receiver",
        ),
        (
            "span truthiness skipped",
            f"array<u8,1> a={{1u8}};const {SPAN} v=borrow_bytes(a);return true||v;",
            "",
            "owned values",
        ),
        ("enum truthiness skipped", "return true||E::yes;", "enum class E{yes,no};", "expected bool"),
        ("class truthiness skipped", "Counter c=Counter(1);return true||c;", COUNTER, "class values"),
        ("skipped static arithmetic", "static_assert(true||(1+1==2));return true;", "", "static_assert supports"),
        (
            "skipped static call",
            "static_assert(true||f());return true;",
            "auto f()->bool{return true;}",
            "static_assert supports",
        ),
        ("static false", "static_assert(false&&true);return true;", "", "static assertion failed"),
        (
            "nonbool generic use",
            "return logic<i64>(0,1);",
            "template<Scalar T>auto logic(T a,T b)->bool{return a||b;}",
            "expected bool",
        ),
    ]
    for name, body, definitions, error in cases:
        s.reject(name, p(body, definitions, result="bool"), error)
    for op in ("&", "|", "^"):
        s.reject(
            "bitwise bool remains rejected " + op, p("return true" + op + "false;", result="bool"), "bitwise operands"
        )
    for text in ("true &&", "|| true", "true ||| false", "true &&& false"):
        s.reject("malformed logical " + text, p("return " + text + ";", result="bool"), "expected expression")


def resource_cases(s):
    for size in (1, 8, 64, 128, 256):
        values = ",".join("false||true" for _ in range(size))
        s.check(
            "scaled logical array " + str(size),
            p(f"const array<bool,{size}> a={{{values}}};return a[{size - 1}];", result="bool"),
            True,
        )
    values = ",".join("true" for _ in range(4096))
    s.check(
        "unchanged straight line maximum array",
        p(f"const array<bool,4096> a={{{values}}};return a[4095];", result="bool"),
        True,
    )
    values = ",".join("false||true" for _ in range(1024))
    s.reject(
        "logical array deterministic retention cap",
        p(f"const array<bool,1024> a={{{values}}};return a[1023];", result="bool"),
        "block-entry operand retention limit",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--seed", type=int, default=24024)
    args = parser.parse_args()
    suite = Suite(args.compiler, "short circuit", ignore_case=True)
    suite.load(Path(__file__).with_suffix(".cases"))
    truth_and_order(suite, args.seed)
    contexts(suite)
    traps(suite)
    rejections(suite)
    resource_cases(suite)
    suite.finish()


if __name__ == "__main__":
    main()
