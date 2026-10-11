#!/usr/bin/env python3
"""Execute independent by-value class arguments and complete typed results."""

from pathlib import Path
import resource
import os
import signal
import subprocess
import sys
import tempfile

COMPILER = Path(sys.argv[1]).resolve()
LIBRARY = Path(__file__).resolve().parents[2] / "library"
COUNT = 0


def require(value, message):
    if not value:
        raise AssertionError(message)


def run(command, good=True):
    result = subprocess.run(
        [str(x) for x in command],
        capture_output=True,
        timeout=5,
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
    )
    if good:
        require(result.returncode == 0, f"{command}: {result.returncode}: {result.stderr!r}")
    return result


def check(
    name,
    source,
    modules=None,
    expected=42,
    error=None,
    library=False,
    root_sets=None,
    setup=None,
    roots=True,
    trap=False,
    existing_output=None,
    calls_in_order=None,
    equivalent_source=None,
):
    global COUNT
    with tempfile.TemporaryDirectory(prefix="aurora-modules-") as directory:
        base = Path(directory)
        groups = root_sets if root_sets is not None else [modules or {}]
        search = []
        for index, files in enumerate(groups):
            root = base / f"root{index}"
            root.mkdir()
            search.append(root)
            for module, text in files.items():
                path = root / (module.replace(".", "/") + ".au")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
        if library:
            search.append(LIBRARY)
        if setup:
            setup(base, search)
        input_path = base / "input.au"
        input_path.write_text(source)
        inputs = {input_path: input_path.read_bytes()}
        for root in search:
            inputs.update({path: path.read_bytes() for path in root.rglob("*.au")})
        assembly = base / "program.s"
        if existing_output is not None:
            assembly.write_text(existing_output)
        command = [COMPILER, input_path, "-o", assembly]
        if roots:
            for root in search:
                command.extend(["--module-root", root])
        compiled = run(command, good=error is None)
        for path, before in inputs.items():
            require(path.read_bytes() == before, name + ": compiler changed input: " + str(path))
        if error:
            require(compiled.returncode == 1, name + ": invalid graph accepted")
            if existing_output is None:
                require(not assembly.exists(), name + ": output created on rejection")
            else:
                require(assembly.read_text() == existing_output, name + ": existing output changed on rejection")
            require(error.encode() in compiled.stderr, name + ": " + repr(compiled.stderr))
        else:
            if equivalent_source is not None:
                named_input, named_output = base / "named.au", base / "named.s"
                named_input.write_text(equivalent_source)
                named_command = [COMPILER, named_input, "-o", named_output]
                if roots:
                    for root in search:
                        named_command.extend(["--module-root", root])
                run(named_command)
                require(named_input.read_text() == equivalent_source, name + ": compiler changed named input")
                for path, before in inputs.items():
                    require(path.read_bytes() == before, name + ": compiler changed input: " + str(path))
                require(
                    assembly.read_bytes() == named_output.read_bytes(),
                    name + ": direct return differs from named-local assembly",
                )
            if calls_in_order:
                code = assembly.read_text()
                positions = [code.index("call " + name) for name in calls_in_order]
                require(positions == sorted(positions), name + ": wrong initializer call order")
            bridge = base / "entry.s"
            bridge.write_text(""".text
.globl _start
_start:
    call test
    pushq %rax
    movq $1, %rax
    movq $1, %rdi
    movq %rsp, %rsi
    movq $8, %rdx
    syscall
    movq $60, %rax
    xorq %rdi, %rdi
    syscall
.section .note.GNU-stack,"",@progbits
""")
            run(["as", "--64", assembly, "-o", base / "program.o"])
            run(["as", "--64", bridge, "-o", base / "entry.o"])
            run(["ld", "-o", base / "program", base / "entry.o", base / "program.o"])
            executed = run([base / "program"], good=not trap)
            if trap:
                require(executed.returncode == -signal.SIGILL and not executed.stdout, name + ": expected exact SIGILL")
            else:
                require(len(executed.stdout) == 8, name + ": missing scalar result")
                require(
                    int.from_bytes(executed.stdout, "little", signed=True) == expected, name + ": wrong scalar result"
                )
        COUNT += 1
        print("PASS values", name)


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
    "private-field factory result",
    program("Counter c=make(42);return c.get();", "auto make(i64 n)->Counter{const Counter c=Counter(n);return c;}"),
)
check(
    "class parameter snapshot",
    program("Counter c=Counter(42);return get(c);", "auto get(Counter c)->i64{return c.get();}"),
)
check(
    "copy result independent",
    program(
        "Counter a=Counter(40);Counter b=copy(a);b.add(2);return a.get()+b.get()-40;",
        "auto copy(Counter c)->Counter{return c;}",
    ),
)
check(
    "callee mutable copy cannot alias caller",
    program(
        "Counter a=Counter(40);return increment(a)+a.get()-40;",
        "auto increment(Counter c)->i64{Counter local=c;return local.add(2);}",
    ),
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
    "same source independent argument snapshots",
    program(
        "Counter c=Counter(20);return sum(c,c.add(2),c);",
        "auto sum(Counter a,i64 ignored,Counter b)->i64{return a.get()+b.get();}",
    ),
)
check(
    "six mixed arguments preserve order",
    program(
        "Counter a=Counter(10);Counter b=Counter(20);return sum(a,id(1),b,id(2),a,id(-1));",
        (
            "auto id(i64 n)->i64{return n;}auto sum(Counter a,i64 b,Counter c,i64 d,Counter e,i64 f)->i64{retur"
            "n a.get()+b+c.get()+d+e.get()+f;}"
        ),
    ),
)
check(
    "odd scalar expression depth",
    program("Counter c=Counter(20);return 2+sum(c,c);", "auto sum(Counter a,Counter b)->i64{return a.get()+b.get();}"),
)
check(
    "class return branch",
    program(
        "Counter c=make(true);return c.get();",
        "auto make(bool yes)->Counter{Counter a=Counter(42);if(yes){return a;}Counter b=Counter(0);return b;}",
    ),
)
check(
    "class return other branch",
    program(
        "Counter c=make(false);return c.get();",
        "auto make(bool yes)->Counter{Counter a=Counter(0);if(yes){return a;}Counter b=Counter(42);return b;}",
    ),
)
check(
    "class result lifetime in loop",
    program(
        "i64 n=0;i64 sum=0;while(n<2){const Counter c=make(21);sum=sum+c.get();n=n+1;}return sum;",
        "auto make(i64 n)->Counter{Counter c=Counter(n);return c;}",
    ),
)
check(
    "parameter snapshot lifetime in loop",
    program(
        "Counter c=Counter(21);i64 n=0;i64 sum=0;while(n<2){sum=sum+get(c);n=n+1;}return sum;",
        "auto get(Counter c)->i64{return c.get();}",
    ),
)
check(
    "class result shadows earlier binding after args",
    program("Counter c=Counter(21);{Counter c=copy(c);return c.get()*2;}", "auto copy(Counter c)->Counter{return c;}"),
)
check(
    "class result through intermediate local",
    program(
        "Counter c=outer(42);return c.get();",
        (
            "auto make(i64 n)->Counter{Counter c=Counter(n);return c;}auto outer(i64 n)->Counter{const Counter "
            "c=make(n);return c;}"
        ),
    ),
)
check(
    "bool fields across boundary",
    program(
        "Flag f=make();if(get(f)){return 42;}return 0;",
        "auto make()->Flag{const Flag f=Flag(true);return f;}auto get(Flag f)->bool{return f.get();}",
        "class Flag{bool b;public:Flag(bool v):b(v){}auto get()const->bool{return b;}};",
    ),
)
check(
    "empty class value boundary",
    program(
        "Empty e=make();return use(e);",
        "auto make()->Empty{Empty e=Empty();return e;}auto use(Empty e)->i64{return 42;}",
        "class Empty{public:Empty(){}};",
    ),
)
check(
    "public aggregate class return",
    program(
        "Pair p=make();return sum(p);",
        "auto make()->Pair{Pair p=Pair{.a=20,.b=22};return p;}auto sum(Pair p)->i64{return p.a+p.b;}",
        "class Pair{public:i64 a;i64 b;};",
    ),
)
check(
    "class return checked overflow",
    program(
        "Counter c=make(9223372036854775807);return c.get();",
        "auto make(i64 n)->Counter{Counter c=Counter(n+1);return c;}",
    ),
    trap=True,
)
check(
    "scalar result with class input checked overflow",
    program(
        "Counter c=Counter(9223372036854775807);return overflow(c);", "auto overflow(Counter c)->i64{return c.get()+1;}"
    ),
    trap=True,
)
check(
    "ordinary class-value recursion",
    program(
        "Counter c=Counter(40);Counter r=step(c,2);return r.get();",
        (
            "auto step(Counter c,i64 n)->Counter{if(n==0){return c;}Counter next=c;next.add(1);Counter result=s"
            "tep(next,n-1);return result;}"
        ),
    ),
)
check(
    "method calls class consumer and preserves receiver",
    program(
        "Counter c=Counter(21);return c.twice();",
        "auto copy_value(Counter c)->i64{return c.get();}",
        COUNTER.replace("};", "auto twice()const->i64{Counter local=Counter(value);return copy_value(local)+value;}};"),
    ),
)

for name, body, helpers, error in [
    (
        "class parameter immutable field",
        "Counter c=Counter(42);return change(c);",
        "auto change(Counter c)->i64{c.value=0;return 42;}",
        "mutable class local",
    ),
    (
        "class parameter mutable method denied",
        "Counter c=Counter(42);return change(c);",
        "auto change(Counter c)->i64{return c.add(1);}",
        "mutable receiver",
    ),
    (
        "class parameter private field denied",
        "Counter c=Counter(42);return change(c);",
        "auto change(Counter c)->i64{return c.value;}",
        "private class field",
    ),
    (
        "return scalar as class denied",
        "Counter c=make();return c.get();",
        "auto make()->Counter{const i64 c=42;return c;}",
        "expected Counter",
    ),
    (
        "temporary class argument denied",
        "return get(Counter(42));",
        "auto get(Counter c)->i64{return c.get();}",
        "complete local name",
    ),
    (
        "class-return call argument needs local",
        "return get(make());",
        "auto make()->Counter{Counter c=Counter(42);return c;}auto get(Counter c)->i64{return c.get();}",
        "complete local name",
    ),
    (
        "discard class-return call denied",
        "make();return 42;",
        "auto make()->Counter{Counter c=Counter(42);return c;}",
        "typed local initializer",
    ),
    (
        "class return missing path",
        "Counter c=make(true);return c.get();",
        "auto make(bool yes)->Counter{Counter c=Counter(42);if(yes){return c;}}",
        "every path",
    ),
    (
        "wrong scalar argument to class parameter",
        "return get(42);",
        "auto get(Counter c)->i64{return c.get();}",
        "complete local name",
    ),
    (
        "class value cannot enter scalar argument",
        "Counter c=Counter(42);return get(c);",
        "auto get(i64 c)->i64{return c;}",
        "class values",
    ),
]:
    check(name, program(body, helpers), error=error)

check(
    "nominal class parameter mismatch",
    program(
        "Other c=Other{.value=42};return get(c);",
        "auto get(Counter c)->i64{return c.get();}",
        COUNTER + "class Other{public:i64 value;};",
    ),
    error="expected Counter",
)
check(
    "nominal class return mismatch",
    program(
        "Counter c=make();return c.get();",
        "auto make()->Counter{Other c=Other{.value=42};return c;}",
        COUNTER + "class Other{public:i64 value;};",
    ),
    error="expected Counter",
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
    error="unknown local",
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
    "namespace factory nominal type",
    app("items::Counter c=items::make(42);return items::consume(c);", "import counters;"),
    {
        "counters": "export module counters;export namespace items{"
        + COUNTER
        + "auto make(i64 n)->Counter{Counter c=Counter(n);return c;}auto consume(Counter c)->i64{return c.get();}}"
    },
)
check(
    "exported private return type rejected",
    app("return 42;", "import counters;"),
    {"counters": LIB.replace("export class Counter", "class Counter")},
    error="exposes private type",
)
check(
    "exported private parameter type rejected",
    app("return 42;", "import counters;"),
    {"counters": "export module counters;" + COUNTER + "export auto consume(Counter c)->i64{return c.get();}"},
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
check(
    "private value function allowed within defining module",
    app("return answer();", "import counters;"),
    {
        "counters": "export module counters;"
        + COUNTER
        + (
            "auto make()->Counter{Counter c=Counter(42);return c;}export auto answer()->i64{Counter c=make();re"
            "turn c.get();}"
        )
    },
)
check(
    "public factory cannot bypass designated restriction",
    app("Counter c=make();return c.get();", "import counters;"),
    {
        "counters": "export module counters;export "
        + COUNTER
        + "export auto make()->Counter{Counter c=Counter{.value=42};return c;}"
    },
    error="designated",
)
check(
    "minmax standard-shaped scalar algorithm",
    app("const std::MinMax limits=std::minmax(42,0);return std::range_width(limits);", "import std.numeric;"),
    library=True,
)
check(
    "minmax signed endpoint preservation",
    app(
        "const std::MinMax limits=std::minmax(9223372036854775807,-9223372036854775808);return limits.min();",
        "import std.numeric;",
    ),
    library=True,
    expected=-9223372036854775808,
)
check(
    "range width checked overflow",
    app(
        (
            "const std::MinMax limits=std::minmax(9223372036854775807,-9223372036854775808);return std::range_w"
            "idth(limits);"
        ),
        "import std.numeric;",
    ),
    library=True,
    trap=True,
)
check(
    "minmax private representation",
    app("const std::MinMax limits=std::minmax(42,0);return limits.lower;", "import std.numeric;"),
    library=True,
    error="private class field",
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
    "returned parameter survives clobbering helper",
    program(
        "Counter c=Counter(42);Counter result=copy(c);return result.get();",
        "auto clobber()->i64{Counter x=Counter(999);return x.get();}auto copy(Counter c)->Counter{clobber();return c;}",
    ),
)
check(
    "class parameter copied mutable local in loop",
    program(
        "Counter c=Counter(20);return twice(c);",
        "auto twice(Counter c)->i64{i64 n=0;i64 sum=0;while(n<2){Counter x=c;sum=sum+x.add(1);n=n+1;}return sum;}",
    ),
)
check(
    "class result reflection layout preserved",
    program(
        "Counter c=make();static_assert(size_of(Counter)==8);return reflect_size(type_id(Counter))+c.get();",
        "auto make()->Counter{Counter c=Counter(34);return c;}",
    ),
)
check(
    "seven class arguments rejected",
    program(
        "return 42;",
        "auto too_many(Counter a,Counter b,Counter c,Counter d,Counter e,Counter f,Counter g)->i64{return 0;}",
    ),
    error="at most six",
)

# Direct constructor returns share the typed-local constructor lowering. They
# deliberately do not admit nested aggregate calls or arbitrary temporaries.
check(
    "direct constructor ordinary result",
    program("Counter c=make(42);return c.get();", "auto make(i64 n)->Counter{return Counter(n);}"),
)
check(
    "direct constructor branch and loop lifetime",
    program(
        "i64 n=0;i64 total=0;while(n<2){Counter c=make(n==0);total=total+c.get();n=n+1;}return total;",
        "auto make(bool first)->Counter{if(first){return Counter(20);}return Counter(22);}",
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
private_counter = (
    COUNTER.replace("public:\n    Counter", "    Counter")
    .replace("    auto get", "public:\n    auto get")
    .replace("};", "auto fresh(i64 n)const->Counter{return Counter(n);}};")
)
# No public construction is needed to validate the body of a same-class factory.
check("direct private constructor allowed in same class", program("return 42;", definition=private_counter))
empty = "class Empty{public:Empty(){}auto answer()const->i64{return 42;}};"
check(
    "direct empty constructor result",
    program("Empty e=make();return e.answer();", "auto make()->Empty{return Empty();}", empty),
)
box = (
    "class Box{Counter item;i64 later;public:Box(Counter c,i64 n):item(c),later(n){}auto answer()const->i64{ret"
    "urn item.get()+later;}};"
)
check(
    "direct composed constructor snapshots before side effects",
    program(
        "Box b=make();return b.answer();",
        "auto make()->Box{Counter c=Counter(20);return Box(c,c.add(2));}",
        COUNTER + box,
    ),
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
    "direct empty composed constructor result",
    program(
        "Holder h=make();const Empty e=h.item;return e.answer();",
        "auto make()->Holder{Empty e=Empty();return Holder(e);}",
        empty + "class Holder{public:Empty item;Holder(Empty e):item(e){}};",
    ),
)
check(
    "direct scalar arguments evaluate left to right",
    program(
        "Pair p=make();return p.answer();",
        "auto make()->Pair{Counter c=Counter(0);return Pair(c.add(1),c.add(1));}",
        COUNTER
        + "class Pair{i64 a;i64 b;public:Pair(i64 x,i64 y):a(x),b(y){}auto answer()const->i64{return a*40+b;}};",
    ),
)
check(
    "direct result copies constructor argument independently",
    program(
        "Counter c=Counter(21);Holder h=make(c);c.add(21);const Counter r=h.item;return r.get()+21;",
        "auto make(Counter c)->Holder{return Holder(c);}",
        COUNTER + "class Holder{public:Counter item;Holder(Counter c):item(c){}};",
    ),
)
check(
    "direct constructor return closes byte array and span",
    program(
        "Counter c=make();return c.get();",
        (
            "auto make()->Counter{builtin::array<u8,1> bytes={42u8};const builtin::span<const u8> view=borrow_b"
            "ytes(bytes);return Counter(i64(view.at(0)));}"
        ),
    ),
)
check(
    "direct qualified constructor result across module",
    app("items::Counter c=items::make(42);return c.get();", "import counters;"),
    {
        "counters": "export module counters;export namespace items{"
        + COUNTER
        + "auto make(i64 n)->Counter{return Counter(n);}}"
    },
)
check(
    "direct constructor method copied parameter",
    program(
        "Counter c=Counter(21);Counter r=c.fresh(c);c.add(21);return r.get()+21;",
        definition=COUNTER.replace("};", "auto fresh(Counter c)const->Counter{return Counter(c.get());}};"),
    ),
)
for label, source, diagnostic in [
    (
        "private constructor inaccessible",
        program("return 42;", "auto make()->Counter{return Counter(42);}", private_counter),
        "private constructor",
    ),
    (
        "direct constructor exact nominal result",
        program("return 42;", "auto make()->Counter{return Other(42);}", COUNTER + COUNTER.replace("Counter", "Other")),
        "expected Counter",
    ),
    (
        "direct constructor scalar type mismatch",
        program("return 42;", "auto make()->Counter{return Counter(true);}"),
        "expected i64",
    ),
    (
        "direct constructor argument count",
        program("return 42;", "auto make()->Counter{return Counter();}"),
        "argument count",
    ),
    (
        "direct nested constructor argument rejected",
        program("return 42;", "auto make()->Box{return Box(Counter(20),22);}", COUNTER + box),
        "requires a local name",
    ),
    (
        "direct temporary receiver rejected",
        program("return 42;", "auto make()->Counter{return Counter(Counter(42).get());}"),
        "method receiver",
    ),
    (
        "direct designated return still rejected",
        program("return 42;", "auto make()->Plain{return Plain{.n=42};}", "class Plain{public:i64 n;};"),
        "complete local name",
    ),
]:
    for prior in (None, "existing assembly must survive rejection\n"):
        check(label, source, error=diagnostic, existing_output=prior)

# Direct ordinary calls retain the typed destination and complete-copy return.
# Compare representative lowerings byte-for-byte with their named-local forms.
factory = "auto make(i64 n)->Counter{const Counter c=Counter(n);return c;}"
forward = program("Counter c=outer(42);return c.get();", factory + "auto outer(i64 n)->Counter{return make(n);}")
check(
    "direct ordinary call matches named-local assembly",
    forward,
    equivalent_source=forward.replace("return make(n);", "const Counter result=make(n);return result;"),
)
check(
    "direct ordinary call const parameter snapshot remains independent",
    program(
        "const Counter source=Counter(42);Counter result=forward(source);result.add(1);return source.get();",
        "auto identity(Counter c)->Counter{return c;}auto forward(Counter c)->Counter{return identity(c);}",
    ),
)
check(
    "direct ordinary call branch return and loop lifetimes",
    program(
        "i64 n=0;i64 total=0;while(n<2){Counter c=forward(n==0);total=total+c.get();n=n+1;}return total;",
        factory + "auto forward(bool first)->Counter{if(first){return make(20);}return make(22);}",
    ),
)
check(
    "direct ordinary recursive result",
    program(
        "Counter source=Counter(40);Counter result=step(source,2);return result.get();",
        "auto step(Counter source,i64 n)->Counter{if(n==0){return source;}"
        "Counter next=source;next.add(1);return step(next,n-1);}",
    ),
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
check(
    "direct ordinary scalar arguments evaluate once left to right",
    program(
        "Counter result=forward();return result.get();",
        "auto combine(i64 a,i64 b)->Counter{return Counter(a*40+b);}"
        "auto forward()->Counter{Counter source=Counter(0);return combine(source.add(1),source.add(1));}",
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
check(
    "direct ordinary call closes temporary argument span",
    program(
        "Counter result=forward();return result.get();",
        "auto inspect_bytes(builtin::span<const u8> bytes)->Counter{return Counter(i64(bytes.at(0)));}"
        "auto forward()->Counter{builtin::array<u8,1> bytes={42u8};return inspect_bytes(borrow_bytes(bytes));}",
    ),
)
check(
    "direct ordinary empty result",
    program(
        "Empty result=forward();return result.answer();",
        "auto make()->Empty{return Empty();}auto forward()->Empty{return make();}",
        empty,
    ),
)
check(
    "direct ordinary composed result remains independent",
    program(
        "Counter source=Counter(20);Box result=forward(source);source.add(99);return result.answer();",
        "auto make(Counter source,i64 n)->Box{return Box(source,n);}"
        "auto forward(Counter source)->Box{return make(source,22);}",
        COUNTER + box,
    ),
)
check(
    "direct ordinary overload selects exact argument tuple",
    program(
        "Counter source=Counter(42);Counter result=forward(source);return result.get();",
        "auto pick(Counter source)->Counter{return source;}auto pick(i64 source)->i64{return source;}"
        "auto forward(Counter source)->Counter{return pick(source);}",
    ),
)
check(
    "direct qualified ordinary calls across modules",
    app("items::Counter source=items::forward(42);return source.get();", "import counters;"),
    {
        "counters": "export module counters;export namespace items{"
        + COUNTER
        + factory
        + "auto forward(i64 n)->Counter{return make(n);}}"
    },
)
check(
    "direct ordinary call argument trap",
    program(
        "Counter result=forward(9223372036854775807);return result.get();",
        factory + "auto forward(i64 n)->Counter{return make(n+1);}",
    ),
    trap=True,
)
for label, source, diagnostic, use_library in [
    (
        "direct ordinary exact nominal result",
        program(
            "return 42;",
            "auto make()->Other{return Other(42);}auto forward()->Counter{return make();}",
            COUNTER + COUNTER.replace("Counter", "Other"),
        ),
        "expected Counter",
        False,
    ),
    (
        "direct ordinary scalar result cannot fill class",
        program("return 42;", "auto make()->i64{return 42;}auto forward()->Counter{return make();}"),
        "expected Counter",
        False,
    ),
    (
        "direct ordinary overload return type cannot select candidate",
        program(
            "return 42;",
            "auto pick(i64 n)->i64{return n;}auto pick(u8 n)->Counter{return Counter(i64(n));}"
            "auto forward()->Counter{return pick(42);}",
        ),
        "expected Counter",
        False,
    ),
    (
        "direct ordinary nested class-result argument",
        program(
            "return 42;",
            factory + "auto identity(Counter source)->Counter{return source;}"
            "auto forward()->Counter{return identity(make(42));}",
        ),
        "complete local name",
        False,
    ),
    (
        "direct ordinary nested constructor argument",
        program(
            "return 42;",
            "auto identity(Counter source)->Counter{return source;}"
            "auto forward()->Counter{return identity(Counter(42));}",
        ),
        "complete local name",
        False,
    ),
    (
        "direct ordinary return field projection",
        program(
            "return 42;",
            "auto forward(Box source)->Counter{return source.item;}",
            COUNTER + "class Box{public:Counter item;Box(Counter c):item(c){}};",
        ),
        "complete local name",
        False,
    ),
    (
        "direct owning ordinary result still requires move",
        app("return 42;", "import std.binary;import std.byte_buffer;")
        + "auto take(builtin::ByteRegion region,std::ByteBuffer value)->std::ByteBuffer{return move(value);}"
        "auto forward(builtin::ByteRegion region,std::ByteBuffer value)->std::ByteBuffer{"
        "return take(region,move(value));}",
        "move",
        True,
    ),
    (
        "direct borrowed-helper result dispatch remains rejected",
        app("return 42;", "import std.binary;import std.byte_buffer;")
        + "auto snapshot(const std::ByteBuffer& value)->std::ByteReadResult{"
        "const std::ByteReadResult result=value.read_u8(0);return result;}"
        "auto forward(const std::ByteBuffer& value)->std::ByteReadResult{return snapshot(value);}",
        "ordinary function call",
        True,
    ),
    (
        "direct service-helper result dispatch remains rejected",
        app("return 42;") + "auto snapshot(builtin::ConsoleSession& session)->builtin::ConsoleSample{"
        "const builtin::ConsoleSample result=session.next();return result;}"
        "auto forward(builtin::ConsoleSession& session)->builtin::ConsoleSample{return snapshot(session);}",
        "ordinary function call",
        False,
    ),
]:
    for prior in (None, "existing assembly must survive rejection\n"):
        check(label, source, error=diagnostic, existing_output=prior, library=use_library)

print(f"{COUNT} class value function-boundary checks passed")
