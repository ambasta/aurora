#!/usr/bin/env python3
"""Exercise encapsulated class construction and scoped receiver execution."""

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
    inlined=(),
    called=(),
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
        assembly = base / "program.s"
        if existing_output is not None:
            assembly.write_text(existing_output)
        command = [COMPILER, input_path, "-o", assembly]
        if roots:
            for root in search:
                command.extend(["--module-root", root])
        compiled = run(command, good=error is None)
        require(input_path.read_text() == source, name + ": compiler changed input")
        if error:
            require(compiled.returncode == 1, name + ": invalid graph accepted")
            if existing_output is None:
                require(not assembly.exists(), name + ": output created on rejection")
            else:
                require(assembly.read_text() == existing_output, name + ": existing output changed on rejection")
            require(error.encode() in compiled.stderr, name + ": " + repr(compiled.stderr))
        else:
            calls = [line for line in assembly.read_text().splitlines() if line.startswith("    call ")]
            for method in inlined:
                require(not any(line.endswith(method) for line in calls), name + ": getter was not inlined")
            for method in called:
                require(any(line.endswith(method) for line in calls), name + ": non-getter body was inlined")
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
        print("PASS classes", name)


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
    "public aggregate method",
    program(
        "Pair p = Pair{.x=20,.y=22};return p.sum();",
        "class Pair {public:i64 x;i64 y;auto sum() const -> i64{return x+y;}};",
    ),
)
check(
    "empty constructor class",
    program("Empty e=Empty();return e.get();", "class Empty {public:Empty(){} auto get() const -> i64{return 42;}};"),
)
check(
    "bool receiver field canonical",
    program(
        "Flag f=Flag(true);if(f.get()){return 42;}return 0;",
        "class Flag {bool value;public:Flag(bool v):value(v){}auto get() const -> bool{return value;}};",
    ),
)
check(
    "six scalar method arguments",
    program(
        "Six x=Six(1);return x.sum(1,2,3,4,5,26);",
        (
            "class Six {i64 value;public:Six(i64 x):value(x){}auto sum(i64 a,i64 b,i64 c,i64 d,i64 e,i64 f)->i6"
            "4{return value+a+b+c+d+e+f;}};"
        ),
    ),
)
check(
    "nested argument snapshots",
    program("Counter c=Counter(20);return sum(c.get(),c.add(2));", helpers="auto sum(i64 a,i64 b)->i64{return a+b;}"),
)
check(
    "private public reflection count",
    program(
        (
            "Counter c=Counter(42);static_assert(field_count(Counter)==0);return reflect_field_count(type_id(Co"
            "unter))+c.get();"
        )
    ),
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
    ("constructor nonempty body", COUNTER.replace("value(initial) {}", "value(initial) { value=0; }"), "expected '}'"),
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
    "imported helper lexical identity",
    (
        "module app; import counters; auto checked_add(i64 x)->i64{return 999;}auto test()->i64{Counter c=Count"
        "er(40);return c.add(2);}"
    ),
    {"counters": LIB},
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
    "freestanding accumulator library",
    app(
        "std::Accumulator sum=std::Accumulator(0);i64 n=0;while(n<7){sum.add(n);n=n+1;}return sum.value()*2;",
        "import std.numeric;",
    ),
    library=True,
)
check(
    "accumulator private state",
    app("std::Accumulator sum=std::Accumulator(42);return sum.total;", "import std.numeric;"),
    library=True,
    error="private class field",
)
check(
    "accumulator checked overflow",
    app("std::Accumulator sum=std::Accumulator(9223372036854775807);return sum.add(1);", "import std.numeric;"),
    library=True,
    trap=True,
)
check(
    "loop-local receiver lifetimes",
    program("i64 n=0;i64 total=0;while(n<2){Counter c=Counter(20);total=total+c.add(1);n=n+1;}return total;"),
)
check(
    "loop-local const aggregate lifetimes",
    program(
        "i64 n=0;i64 total=0;while(n<2){const Point p=Point{.value=21};total=total+p.value;n=n+1;}return total;",
        "class Point{public:i64 value;};",
    ),
)
check(
    "branch constructor lifetimes",
    program(
        (
            "i64 total=0;if(true){Counter c=Counter(20);total=c.add(1);}else{Counter c=Counter(0);total=c.get()"
            ";}Counter c=Counter(total);return c.add(total);"
        )
    ),
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
    "six argument nested receiver calls",
    program(
        "Six x=Six(1);return 1+x.sum(id(1),id(2),id(3),id(4),id(5),id(25));",
        (
            "class Six {i64 value;public:Six(i64 x):value(x){}auto sum(i64 a,i64 b,i64 c,i64 d,i64 e,i64 f)->i6"
            "4{return value+a+b+c+d+e+f;}};"
        ),
        "auto id(i64 x)->i64{return x;}",
    ),
)
check(
    "constructor multiple declaration-order fields",
    program(
        "Pair p=Pair(20,22);return p.sum();",
        "class Pair {i64 a;i64 b;public:Pair(i64 x,i64 y):b(y),a(x){}auto sum() const -> i64{return a+b;}};",
    ),
)
check(
    "method caller owner lifetime preserved",
    program(
        (
            "own<i64> n=own(20);Counter c=Counter(read(n));{const ref<i64> r=borrow(n);c.add(read(r));}own<i64>"
            " moved=move(n);return c.get()+read(moved)-18;"
        )
    ),
)
check(
    "method private fields of independent same-class local",
    program(
        "Counter c=Counter(0);return c.get();",
        (
            "class Counter {i64 value;public:Counter(i64 x):value(x){}auto get() const -> i64{Counter other=Cou"
            "nter(40);other.value=other.value+2;return other.value;}};"
        ),
    ),
)
check(
    "const method cannot mutate const local",
    program(
        "Counter c=Counter(0);return c.get();",
        (
            "class Counter {i64 value;public:Counter(i64 x):value(x){}auto get() const -> i64{const Counter oth"
            "er=Counter(40);other.value=42;return other.value;}};"
        ),
    ),
    error="mutable class local",
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
    "pure scalar recursion preserved",
    program(
        "Counter c=Counter(sum(6));return c.doubled();",
        helpers="auto sum(i64 n)->i64{if(n==0){return 0;}return n+sum(n-1);}",
    ),
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

check(
    "constructor return type rejected",
    program("return 42;", "class Wrong {public:auto Wrong()->i64{return 42;}};"),
    error="constructor cannot have a return type",
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

print(f"{COUNT} class constructor and method checks passed")
