#!/usr/bin/env python3
"""Class values across function boundaries: copies, factories, snapshots (native_runner.py)."""

from pathlib import Path
import sys
import tempfile

from native_runner import LIBRARY, Suite, Trap, require, run

COMPILER = Path(sys.argv[1]).resolve()
SUITE = Suite(COMPILER, "value calls")


def check(
    name,
    source,
    modules=None,
    expected=42,
    error=None,
    library=False,
    trap=False,
    existing_output=None,
    equivalent_source=None,
):
    def inspect(assembly):
        # A direct return must lower exactly like its named-local form.
        with tempfile.TemporaryDirectory(prefix="aurora-named-") as directory:
            named_input, named_output = Path(directory) / "named.au", Path(directory) / "named.s"
            named_input.write_text(equivalent_source)
            result = run([COMPILER, "--module-root", LIBRARY, named_input, "-o", named_output])
            require(result.returncode == 0, f"named-local form failed: {result.stderr!r}")
            require(named_output.read_text() == assembly, "direct return differs from named-local assembly")

    SUITE.check(
        name,
        source,
        Trap.OVERFLOW if trap else expected,
        error,
        modules=modules,
        existing_output=existing_output,
        inspect=inspect if equivalent_source is not None else None,
    )


def app(body, imports=""):
    return "module app; " + imports + " auto test() -> i64 { " + body + " }"


COUNTER = """class Counter {
    i64 value;
public:
    Counter(i64 initial):value(initial){}
    auto get() const -> i64{return value;}
    auto add(i64 n)->i64{value=value+n;return value;}
};"""


def program(body, helpers="", definition=COUNTER):
    return "module app;" + definition + helpers + "auto test()->i64{" + body + "}"


check(
    "class parameter snapshot",
    program("Counter c=Counter(42);return get(c);", "auto get(Counter c)->i64{return c.get();}"),
)
check(
    "argument snapshot before later mutation",
    program("Counter c=Counter(20);return sum(c,c.add(2));", "auto sum(Counter c,i64 n)->i64{return c.get()+n;}"),
)
check(
    "argument snapshot after earlier mutation",
    program("Counter c=Counter(20);return sum(c.add(2),c);", "auto sum(i64 n,Counter c)->i64{return c.get()+n-2;}"),
)
check(
    "odd scalar expression depth",
    program("Counter c=Counter(20);return 2+sum(c,c);", "auto sum(Counter a,Counter b)->i64{return a.get()+b.get();}"),
)
check(
    "class result shadows earlier binding after args",
    program("Counter c=Counter(21);{Counter c=copy(c);return c.get()*2;}", "auto copy(Counter c)->Counter{return c;}"),
)
check(
    "method calls class consumer and preserves receiver",
    program(
        "Counter c=Counter(21);return c.twice();",
        "auto copy_value(Counter c)->i64{return c.get();}",
        COUNTER.replace("};", "auto twice()const->i64{Counter local=Counter(value);return copy_value(local)+value;}};"),
    ),
)


check(
    "method class parameter makes independent typed result",
    program(
        "Counter c=Counter(42);Counter result=c.copy(c);c.add(1);return result.get();",
        definition=COUNTER.replace("};", "auto copy(Counter source)const->Counter{return source;}};"),
    ),
)
check(
    "class method result cannot return scalar field",
    program("return 42;", definition=COUNTER.replace("get() const -> i64", "get() const -> Counter")),
    error="expected Counter",
)

LIB = (
    "export module counters;export "
    + COUNTER
    + (
        "export auto make(i64 n)->Counter{Counter c=Counter(n);return c;}export auto consume(Counter c)->i64{re"
        "turn c.get();}"
    )
)
check(
    "cross-module factory consumer", app("Counter c=make(42);return consume(c);", "import counters;"), {"counters": LIB}
)
check(
    "exported private return type rejected",
    app("return 42;", "import counters;"),
    {"counters": LIB.replace("export class Counter", "class Counter")},
    error="exposes private type",
)
TRANSITIVE = {
    "values": "export module values;export " + COUNTER,
    "factory": "export module factory;import values;export auto make()->Counter{Counter c=Counter(42);return c;}",
}
check(
    "transitive result type not implicitly exported",
    app("return make();", "import factory;"),
    TRANSITIVE,
    error="direct visible import",
)
check(
    "direct type import permits factory",
    app("Counter c=make();return c.get();", "import factory;import values;"),
    TRANSITIVE,
)

for size, error in [(64, None), (65, "64 scalar fields")]:
    fields = "".join(f"i64 f{i};" for i in range(size))
    initializers = ",".join(f".f{i}={42 if i == size - 1 else 0}" for i in range(size))
    definition = "class Large{public:" + fields + "};"
    helper = "auto value(Large x)->Large{return x;}"
    check(
        f"boundary {size} fields",
        program(f"Large x=Large{{{initializers}}};Large y=value(x);return y.f{size - 1};", helper, definition),
        error=error,
    )

wide_fields = "".join(f"i64 f{i};" for i in range(64))
wide_init = ",".join(f".f{i}={7 if i == 63 else i}" for i in range(64))
wide_class = "class Wide{public:" + wide_fields + "};"
check(
    "six maximum-width class arguments",
    program(
        "Wide x=Wide{" + wide_init + "};return sum(x,x,x,x,x,x);",
        "auto sum(Wide a,Wide b,Wide c,Wide d,Wide e,Wide f)->i64{return a.f63+b.f63+c.f63+d.f63+e.f63+f.f63;}",
        wide_class,
    ),
)
check(
    "six maximum-width temporary class arguments",
    program(
        "return sum(make(),make(),make(),make(),make(),make());",
        "auto make()->Wide{Wide value=Wide{" + wide_init + "};return value;}"
        "auto sum(Wide a,Wide b,Wide c,Wide d,Wide e,Wide f)->i64{return a.f63+b.f63+c.f63+d.f63+e.f63+f.f63;}",
        wide_class,
    ),
)
check(
    "maximum-width result with mixed arguments",
    program(
        "Wide x=Wide{" + wide_init + "};Wide result=select(x,true,x,21,x,14);return result.f63+35;",
        "auto select(Wide a,bool yes,Wide b,i64 n,Wide c,i64 extra)->Wide{if(yes){return b;}return c;}",
        wide_class,
    ),
)
check(
    "receiver survives class-result hidden pointer",
    program(
        "Counter c=Counter(21);return c.twice();",
        "auto copy(Counter c)->Counter{return c;}",
        COUNTER.replace(
            "};",
            (
                "auto twice()const->i64{Counter local=Counter(value);Counter result=copy(local);return result.g"
                "et()+value;}};"
            ),
        ),
    ),
)

check(
    "direct constructor checked argument overflow",
    program("Counter c=make(9223372036854775807);return c.get();", "auto make(i64 n)->Counter{return Counter(n+1);}"),
    trap=True,
)
check(
    "direct constructor checked initializer overflow",
    program(
        "Counter c=make(9223372036854775807);return c.get();",
        "auto make(i64 n)->Counter{return Counter(n);}",
        COUNTER.replace("value(initial)", "value(initial+1)"),
    ),
    trap=True,
)
check(
    "direct constructor method receiver and independent result",
    program(
        "Counter c=Counter(21);Counter r=c.fresh();c.add(21);return r.get()+21;",
        definition=COUNTER.replace("};", "auto fresh()const->Counter{return Counter(value);}};"),
    ),
)
check(
    "direct constructor mutable method side effect",
    program(
        "Counter c=Counter(20);Counter r=c.fresh();return r.get()+c.get();",
        definition=COUNTER.replace("};", "auto fresh()->Counter{return Counter(add(1));}};"),
    ),
)
empty = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
box = (
    "class Box{Counter item;i64 later;public:Box(Counter c,i64 n):item(c),later(n){}auto answer()const->i64{ret"
    "urn item.get()+later;}};"
)
box_after = (
    "class Box{i64 earlier;Counter item;public:Box(i64 n,Counter c):earlier(n),item(c){}auto answer()const->i64"
    "{return earlier+item.get()-2;}};"
)
check(
    "direct composed constructor snapshots after side effects",
    program(
        "Box b=make();return b.answer();",
        "auto make()->Box{Counter c=Counter(20);return Box(c.add(2),c);}",
        COUNTER + box_after,
    ),
)
repeated = (
    "class Box{Counter first;Counter last;i64 ignored;public:Box(Counter a,i64 n,Counter b):first(a),last(b),ig"
    "nored(n){}auto answer()const->i64{return first.get()+last.get();}};"
)
check(
    "direct repeated constructor arguments snapshot independently",
    program(
        "Box b=make();return b.answer();",
        "auto make()->Box{Counter c=Counter(20);return Box(c,c.add(2),c);}",
        COUNTER + repeated,
    ),
)
check(
    "direct constructor method copied parameter",
    program(
        "Counter c=Counter(21);Counter r=c.fresh(c);c.add(21);return r.get()+21;",
        definition=COUNTER.replace("};", "auto fresh(Counter c)const->Counter{return Counter(c.get());}};"),
    ),
)

# Direct ordinary calls retain the typed destination and complete-copy return.
# Compare representative lowerings byte-for-byte with their named-local forms.
factory = "auto make(i64 n)->Counter{const Counter c=Counter(n);return c;}"
forward = program("Counter c=outer(42);return c.get();", factory + "auto outer(i64 n)->Counter{return make(n);}")
check(
    "direct ordinary call matches named-local assembly",
    forward,
    equivalent_source=forward.replace("return make(n);", "const Counter result=make(n);return result;"),
)
overloaded_forward = program(
    "Counter result=forward();return result.get();",
    "auto combine(Counter first,i64 ignored,Counter last)->Counter{return Counter(first.get()+last.get());}"
    "auto combine(i64 first,i64 ignored,i64 last)->i64{return first+last;}"
    "auto forward()->Counter{Counter source=Counter(20);return combine(source,source.add(2),source);}",
)
check(
    "direct overloaded repeated arguments snapshot around mutation",
    overloaded_forward,
    equivalent_source=overloaded_forward.replace(
        "return combine(source,source.add(2),source);",
        "const Counter result=combine(source,source.add(2),source);return result;",
    ),
)
loan_forward = program(
    "i64 n=0;i64 total=0;while(n<2){Counter c=forward();total=total+c.get();n=n+1;}return total;",
    "auto inspect_bytes(builtin::span<const u8> bytes)->Counter{return Counter(i64(bytes.at(0)));}"
    "auto forward()->Counter{builtin::array<u8,1> bytes={21u8};"
    "const builtin::span<const u8> view=borrow_bytes(bytes);return inspect_bytes(view);}",
)
check(
    "direct ordinary call releases argument and return loans",
    loan_forward,
    equivalent_source=loan_forward.replace(
        "return inspect_bytes(view);", "const Counter result=inspect_bytes(view);return result;"
    ),
)

# Bounded copied arguments use the same observable behavior as explicit locals.
for label, expression, helpers in (
    ("constructor", "Counter(42)", ""),
    ("ordinary result", "make()", "auto make()->Counter{Counter c=Counter(42);return c;}"),
):
    consumer = "auto get(Counter c)->i64{return c.get();}"
    check("copied temporary argument " + label, program("return get(" + expression + ");", helpers + consumer))
    check(
        "copied explicit local " + label,
        program("const Counter value=" + expression + ";return get(value);", helpers + consumer),
    )
for label, expression, helpers in (
    ("class-result", "make(42)", factory),
    ("constructor", "Counter(42)", ""),
):
    check(
        "direct ordinary nested " + label + " argument",
        program(
            "return 42;",
            helpers + "auto identity(Counter source)->Counter{return source;}"
            "auto forward()->Counter{return identity(" + expression + ");}",
        ),
    )
    check(
        "nested ordinary return executes " + label,
        program(
            "Counter result=forward();return result.get();",
            helpers + "auto identity(Counter source)->Counter{return source;}"
            "auto forward()->Counter{return identity(" + expression + ");}",
        ),
    )
for label, body in (
    ("inline", "return sum(c,Counter(c.add(1)),make(c.add(1)),c);"),
    (
        "explicit locals",
        "const Counter first=c;const Counter second=Counter(c.add(1));"
        "const Counter third=make(c.add(1));const Counter last=c;return sum(first,second,third,last);",
    ),
):
    check(
        "nested argument snapshots once in order " + label,
        program(
            "Counter c=Counter(9);" + body,
            factory + "auto sum(Counter a,Counter b,Counter d,Counter e)->i64{"
            "if(a.get()!=9||b.get()!=10||d.get()!=11||e.get()!=11){return 0;}return 42;}",
        ),
    )
for expression in ("Other(42)", "make_other()"):
    check(
        "temporary exact nominal mismatch " + expression,
        program(
            "return get(" + expression + ");",
            "auto get(Counter c)->i64{return c.get();}auto make_other()->Other{return Other(42);}",
            COUNTER + COUNTER.replace("Counter", "Other"),
        ),
        error="expected Counter",
    )

SUITE.load(Path(__file__).with_suffix(".cases"), COUNTER=COUNTER)
SUITE.finish()
