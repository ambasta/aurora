#!/usr/bin/env python3
"""Encapsulated class construction and scoped receiver execution (native_runner.py)."""

from pathlib import Path
import sys

from native_runner import Suite, Trap, require

SUITE = Suite(Path(sys.argv[1]), "classes")


def calls(assembly):
    return [line for line in assembly.splitlines() if line.startswith("    call ")]


def check(
    name,
    source,
    modules=None,
    expected=42,
    error=None,
    library=False,
    trap=False,
    existing_output=None,
    calls_in_order=None,
    inlined=(),
    called=(),
):
    def inspect(assembly):
        for method in inlined:
            require(not any(line.endswith(method) for line in calls(assembly)), "getter was not inlined")
        for method in called:
            require(any(line.endswith(method) for line in calls(assembly)), "non-getter body was inlined")
        if calls_in_order:
            positions = [assembly.index("call " + callee) for callee in calls_in_order]
            require(positions == sorted(positions), "wrong initializer call order")

    probes = inlined or called or calls_in_order
    SUITE.check(
        name,
        source,
        Trap.OVERFLOW if trap else expected,
        error,
        modules=modules,
        existing_output=existing_output,
        inspect=inspect if probes else None,
    )


def app(body, imports=""):
    return "module app; " + imports + " auto test() -> i64 { " + body + " }"


COUNTER = """class Counter {
    i64 value;
    auto checked_add(i64 amount) -> i64 { value = value + amount; return value; }
public:
    Counter(i64 initial) : value(initial) {}
    auto get() const -> i64 { return value; }
    auto add(i64 amount) -> i64 { return checked_add(amount); }
    auto doubled() const -> i64 { return get() + get(); }
};"""


def program(body, definition=COUNTER, helpers=""):
    return "module app; " + definition + helpers + " auto test() -> i64 {" + body + "}"


check("constructor and private mutation", program("Counter c = Counter(40); return c.add(2);"))
check("const accessor", program("const Counter c = Counter(42); return c.get();"))
check("argument before exclusive call", program("Counter c = Counter(21); return c.add(c.get());"))
# Numeric results and semantic call presence, not instruction encodings. The
# packed runner executes every boundary with the same native component driver.
for value, folded in [
    (0, True),
    (2147483647, True),
    (2147483648, True),
    (4294967295, True),
    (4294967296, False),
    (9223372036854775808, False),
    (18446744073709551615, False),
]:
    check(
        f"const u64 literal boundary {value}",
        program(
            f"Literal c=Literal(); if(c.literal()=={value}u64){{return 42;}}return 0;",
            f"class Literal{{public:Literal(){{}}auto literal()const->u64{{return {value}u64;}}}};",
        ),
        inlined=("_d7literal",) if folded else (),
        called=() if folded else ("_d7literal",),
    )
for name, signature, body, invocation in [
    ("mutable receiver", "auto literal()->u64", "return 42u64;", "c.literal()"),
    ("explicit parameter", "auto literal(u64 value)const->u64", "return 42u64;", "c.literal(9u64)"),
    ("extra local operation", "auto literal()const->u64", "const u64 copy=42u64;return copy;", "c.literal()"),
]:
    check(
        "literal fallback " + name,
        program(
            f"Literal c=Literal();return i64({invocation});",
            f"class Literal{{public:Literal(){{}}{signature}{{{body}}}}};",
        ),
        called=("_d7literal",),
    )
check(
    "literal does not discard checked effect",
    program(
        "Literal c=Literal();return i64(c.literal());",
        "class Literal{public:Literal(){}auto literal()const->u64{builtin::require(false);return 42u64;}};",
    ),
    expected=Trap.BOUNDS,
    called=("_d7literal",),
)
check(
    "literal subobject preserves constructor evaluation",
    program(
        "Counter count=Counter(20);const Literal child=Literal(count.add(1));"
        "const Outer outer=Outer(7,child);"
        "if(outer.value()!=42u64||count.get()!=21||outer.tag()!=7){return 0;}return 42;",
        COUNTER + "class Literal{i64 marker;public:Literal(i64 value):marker(value){}"
        "auto literal()const->u64{return 42u64;}};"
        "class Outer{i64 prefix;Literal child;public:Outer(i64 tag,Literal value):prefix(tag),child(value){}"
        "auto value()const->u64{return child.literal();}auto tag()const->i64{return prefix;}};",
    ),
    inlined=("_d7literal",),
    called=("_d5value",),
)
check(
    "literal receiver construction still traps",
    program(
        "Counter count=Counter(9223372036854775807);Literal c=Literal(count.add(1));return i64(c.literal());",
        COUNTER + "class Literal{i64 marker;public:Literal(i64 value):marker(value){}"
        "auto literal()const->u64{return 42u64;}};",
    ),
    trap=True,
    inlined=("_d7literal",),
)
# Single-field getters become a load at the call site; any other body stays a call.
check("inlined getter", program("const Counter c = Counter(42); return c.get();"), inlined=("_d3get",))
check(
    "inlined narrow and nested getters",
    program(
        "const Counter c = Counter(2); const Outer o = Outer(c); return i64(o.small()) * 2 + o.value();",
        definition=COUNTER
        + """class Outer {
    u8 tag;
    Counter inner;
public:
    Outer(Counter initial) : tag(20u8), inner(initial) {}
    auto small() const -> u8 { return tag; }
    auto value() const -> i64 { return inner.get(); }
};""",
    ),
    inlined=("_d5small", "_d3get"),
)
check(
    "two-statement getter stays a call",
    program(
        "const Twice t = Twice(21); return t.twice();",
        definition="""class Twice {
    i64 value;
public:
    Twice(i64 initial) : value(initial) {}
    auto twice() const -> i64 { const i64 copy = value; return copy + copy; }
};""",
    ),
    called=("_d5twice",),
)
check("readonly sibling reborrow", program("const Counter c = Counter(21); return c.doubled();"))
check(
    "complete private copies independent",
    program("Counter a = Counter(20); Counter b = a; b.add(2); return a.get() + b.get();"),
)
check(
    "mutable copy of const scalar-field value",
    program("const Counter a = Counter(20); Counter b = a; b.add(2); return a.get() + b.get();"),
)
check(
    "receiver preserved across ordinary call",
    program(
        "Counter c = Counter(40); return c.add(2);",
        COUNTER.replace("value + amount", "helper(value, amount)"),
        "auto helper(i64 x, i64 y)->i64{return x+y;}",
    ),
)
check(
    "receiver method branches loops",
    program(
        "Counter c = Counter(0); return c.add(42);",
        COUNTER.replace(
            "value = value + amount; return value;",
            "i64 n=0; while(n<amount){value=value+1;n=n+1;} if(value==42){return get();}return 0;",
        ),
    ),
)
check(
    "local shadows receiver field",
    program(
        "Counter c = Counter(8); return c.get();",
        COUNTER.replace("return value; }\n    auto add", "const i64 value=42; return value; }\n    auto add"),
    ),
)
check(
    "constructor parameter shadows field",
    program(
        "Counter c = Counter(42); return c.get();",
        COUNTER.replace("i64 initial) : value(initial)", "i64 value) : value(value)"),
    ),
)
check(
    "construction overflow traps",
    program(
        "Counter c = Counter(9223372036854775807); return c.get();",
        COUNTER.replace("value(initial)", "value(initial+1)"),
    ),
    trap=True,
)
check("method overflow traps", program("Counter c = Counter(9223372036854775807); return c.add(1);"), trap=True)
check(
    "empty constructor class",
    program("Empty e=Empty();return e.get();", "class Empty {public:Empty(){} auto get() const -> i64{return 42;}};"),
)
check(
    "nested argument snapshots",
    program("Counter c=Counter(20);return sum(c.get(),c.add(2));", helpers="auto sum(i64 a,i64 b)->i64{return a+b;}"),
)
check(
    "global name cannot hijack private helper",
    program("Counter c=Counter(40);return c.add(2);", helpers="auto checked_add(i64 x)->i64{return 999;}"),
)

bad = [
    ("const receiver mutation", "const Counter c=Counter(40);return c.add(2);", "mutable receiver"),
    ("private field read", "Counter c=Counter(42);return c.value;", "private class field"),
    ("private field write", "Counter c=Counter(42);c.value=0;return 42;", "private class field"),
    ("private method call", "Counter c=Counter(40);return c.checked_add(2);", "private method"),
    ("constructor designated bypass", "Counter c=Counter{.value=42};return c.get();", "designated"),
    ("constructor wrong argument", "Counter c=Counter(true);return c.get();", "expected i64"),
    ("constructor wrong count", "Counter c=Counter();return c.get();", "argument count"),
    ("method wrong argument", "Counter c=Counter(42);return c.add(true);", "expected i64"),
    ("method wrong count", "Counter c=Counter(42);return c.get(1);", "argument count"),
    ("temporary receiver denied", "return Counter(42).get();", "class local"),
    ("receiver does not escape", "Counter c=Counter(42);const ref<i64> r=borrow(c);return read(r);", "expected own"),
]
for name, body, error in bad:
    check(name, program(body), error=error)

for name, definition, error in [
    ("constructor missing field", COUNTER.replace(": value(initial)", ""), "every field"),
    (
        "constructor duplicate field",
        COUNTER.replace("value(initial)", "value(initial),value(initial)"),
        "duplicate constructor",
    ),
    ("constructor unknown field", COUNTER.replace("value(initial)", "missing(initial)"), "unknown constructor"),
    ("constructor self field forbidden", COUNTER.replace("value(initial)", "value(value)"), "receiver fields"),
    ("constructor self method forbidden", COUNTER.replace("value(initial)", "value(get())"), "receiver methods"),
    (
        "constructor nonempty body",
        COUNTER.replace("value(initial) {}", "value(initial) { value=0; }"),
        "AU3001: resource initialization or finalization violates its ownership contract",
    ),
    (
        "const method write",
        COUNTER.replace(
            "auto get() const -> i64 { return value; }", "auto get() const -> i64 { value=42;return value; }"
        ),
        "const method",
    ),
    ("const method exclusive reborrow", COUNTER.replace("return get() + get();", "return add(1);"), "mutable receiver"),
    (
        "private constructor denied",
        COUNTER.replace("public:\n    Counter", "private:\n    Counter").replace(
            "    auto get()", "public: auto get()"
        ),
        "private constructor",
    ),
    ("duplicate methods rejected", COUNTER.replace("auto doubled()", "auto get()"), "duplicate"),
    ("method field collision", COUNTER.replace("auto get()", "auto value()"), "duplicate"),
    ("method ownership parameter rejected", COUNTER.replace("i64 amount", "ref<i64> amount"), "only scalar"),
    (
        "method aggregate result requires typed initializer",
        COUNTER.replace("auto get() const -> i64", "auto get() const -> Counter"),
        "class-returning method requires a typed local initializer",
    ),
    ("method direct recursion rejected", COUNTER.replace("return get() + get();", "return doubled();"), "cycle"),
    (
        "method mutual recursion rejected",
        COUNTER.replace("return value; }\n    auto add", "return doubled(); }\n    auto add"),
        "cycle",
    ),
]:
    check(name, program("Counter c=Counter(42);return c.get();", definition), error=error)

LIB = "export module counters; export " + COUNTER
check(
    "imported encapsulated class", app("Counter c=Counter(40);return c.add(2);", "import counters;"), {"counters": LIB}
)
check(
    "imported private method denied",
    app("Counter c=Counter(40);return c.checked_add(2);", "import counters;"),
    {"counters": LIB},
    error="private method",
)
check(
    "imported private constructor denied",
    app("Counter c=Counter(40);return c.get();", "import counters;"),
    {
        "counters": LIB.replace("public:\n    Counter", "private:\n    Counter").replace(
            "    auto get()", "public: auto get()"
        )
    },
    error="private constructor",
)
check(
    "namespace class identity",
    app("math::Counter c=math::Counter(40);return c.add(2);", "import counters;"),
    {"counters": "export module counters;export namespace math {" + COUNTER + "}"},
)
check(
    "library method cannot call root helper",
    app("Counter c=Counter(40);return c.add(2);", "import counters;"),
    {"counters": LIB.replace("value + amount", "root_only(value)")},
    error="unknown function",
)

check(
    "loop-local receiver lifetimes",
    program("i64 n=0;i64 total=0;while(n<2){Counter c=Counter(20);total=total+c.add(1);n=n+1;}return total;"),
)
check("early return ends receiver lifetime", program("Counter c=Counter(42);if(true){return c.get();}return 0;"))
check(
    "method shadow not callable",
    program(
        "Counter c=Counter(42);return c.get();",
        COUNTER.replace("return get() + get();", "const i64 get=42;return get();"),
    ),
    error="not callable",
)
check(
    "field name prevents global hijack",
    program(
        "Counter c=Counter(42);return c.get();",
        COUNTER.replace("return get() + get();", "return value();"),
        "auto value()->i64{return 42;}",
    ),
    error="field is not callable",
)

check(
    "scalar intermediary method cycle denied",
    program(
        "Counter c=Counter(42);return c.get();",
        COUNTER.replace("return get() + get();", "return recurse();"),
        "auto recurse()->i64{Counter c=Counter(42);return c.doubled();}",
    ),
    error="cycle",
)
check(
    "constructor argument local shadowing uses prior object",
    program("Counter c=Counter(21);{Counter c=Counter(c.get());return c.doubled();}"),
)

check(
    "initializer calls follow declaration order",
    program(
        "Pair p=Pair();return p.sum();",
        (
            "class Pair{i64 first;i64 second;public:Pair():second(second_value()),first(first_value()){}auto su"
            "m()const->i64{return first+second;}};"
        ),
        "auto first_value()->i64{return 20;}auto second_value()->i64{return 22;}",
    ),
    calls_in_order=["first_value", "second_value"],
)
check(
    "method postfix depth bounded", program("Counter c=Counter(42);return c" + ".get()" * 200 + ";"), error="AST depth"
)
check(
    "constructor nesting depth bounded",
    program("Counter c=" + "Counter(" * 200 + "42" + ")" * 200 + ";return c.get();"),
    error="nesting exceeds",
)


# The graph has shallow ASTs but a long call chain: cycle analysis must not use
# unbounded host recursion. These are bounded regressions, not a resource proof.
CHAIN_SIZE = 2048
chain = "".join(f"auto hop{i}()->i64{{return hop{i + 1}();}}" for i in range(CHAIN_SIZE - 1))
chain += f"auto hop{CHAIN_SIZE - 1}()->i64{{return 42;}}"
chain_class = "class Chain{public:Chain(){}auto value()const->i64{return hop0();}};"
check("long acyclic receiver call graph", program("Chain c=Chain();return c.value();", chain_class, chain))
check(
    "long receiver cycle graph rejected",
    program(
        "Chain c=Chain();return c.value();",
        chain_class,
        chain.replace(
            f"auto hop{CHAIN_SIZE - 1}()->i64{{return 42;}}", f"auto hop{CHAIN_SIZE - 1}()->i64{{return test();}}"
        ),
    ),
    error="cycle",
)

SUITE.load(Path(__file__).with_suffix(".cases"), COUNTER=COUNTER)
SUITE.finish()
