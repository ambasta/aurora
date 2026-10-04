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
    result = subprocess.run([str(x) for x in command], capture_output=True, timeout=5,
                            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
    if good:
        require(result.returncode == 0, f"{command}: {result.returncode}: {result.stderr!r}")
    return result


def check(name, source, modules=None, expected=42, error=None, library=False,
          root_sets=None, setup=None, roots=True, trap=False, existing_output=None, calls_in_order=None):
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
                require(executed.returncode == -signal.SIGILL and not executed.stdout,
                        name + ": expected exact SIGILL")
            else:
                require(len(executed.stdout) == 8, name + ": missing scalar result")
                require(int.from_bytes(executed.stdout, "little", signed=True) == expected,
                        name + ": wrong scalar result")
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
    return "module app;"+definition+helpers+"auto test()->i64{"+body+"}"

check("private-field factory result", program("Counter c=make(42);return c.get();", "auto make(i64 n)->Counter{const Counter c=Counter(n);return c;}"))
check("class parameter snapshot", program("Counter c=Counter(42);return get(c);", "auto get(Counter c)->i64{return c.get();}"))
check("copy result independent", program("Counter a=Counter(40);Counter b=copy(a);b.add(2);return a.get()+b.get()-40;", "auto copy(Counter c)->Counter{return c;}"))
check("callee mutable copy cannot alias caller", program("Counter a=Counter(40);return increment(a)+a.get()-40;", "auto increment(Counter c)->i64{Counter local=c;return local.add(2);}"))
check("argument snapshot before later mutation", program("Counter c=Counter(20);return sum(c,c.add(2));", "auto sum(Counter c,i64 n)->i64{return c.get()+n;}"))
check("argument snapshot after earlier mutation", program("Counter c=Counter(20);return sum(c.add(2),c);", "auto sum(i64 n,Counter c)->i64{return c.get()+n-2;}"))
check("same source independent argument snapshots", program("Counter c=Counter(20);return sum(c,c.add(2),c);", "auto sum(Counter a,i64 ignored,Counter b)->i64{return a.get()+b.get();}"))
check("six mixed arguments preserve order", program("Counter a=Counter(10);Counter b=Counter(20);return sum(a,id(1),b,id(2),a,id(-1));", "auto id(i64 n)->i64{return n;}auto sum(Counter a,i64 b,Counter c,i64 d,Counter e,i64 f)->i64{return a.get()+b+c.get()+d+e.get()+f;}"))
check("odd scalar expression depth", program("Counter c=Counter(20);return 2+sum(c,c);", "auto sum(Counter a,Counter b)->i64{return a.get()+b.get();}"))
check("class return branch", program("Counter c=make(true);return c.get();", "auto make(bool yes)->Counter{Counter a=Counter(42);if(yes){return a;}Counter b=Counter(0);return b;}"))
check("class return other branch", program("Counter c=make(false);return c.get();", "auto make(bool yes)->Counter{Counter a=Counter(0);if(yes){return a;}Counter b=Counter(42);return b;}"))
check("class result lifetime in loop", program("i64 n=0;i64 sum=0;while(n<2){const Counter c=make(21);sum=sum+c.get();n=n+1;}return sum;", "auto make(i64 n)->Counter{Counter c=Counter(n);return c;}"))
check("parameter snapshot lifetime in loop", program("Counter c=Counter(21);i64 n=0;i64 sum=0;while(n<2){sum=sum+get(c);n=n+1;}return sum;", "auto get(Counter c)->i64{return c.get();}"))
check("class result shadows earlier binding after args", program("Counter c=Counter(21);{Counter c=copy(c);return c.get()*2;}", "auto copy(Counter c)->Counter{return c;}"))
check("class result through intermediate local", program("Counter c=outer(42);return c.get();", "auto make(i64 n)->Counter{Counter c=Counter(n);return c;}auto outer(i64 n)->Counter{const Counter c=make(n);return c;}"))
check("bool fields across boundary", program("Flag f=make();if(get(f)){return 42;}return 0;", "auto make()->Flag{const Flag f=Flag(true);return f;}auto get(Flag f)->bool{return f.get();}", "class Flag{bool b;public:Flag(bool v):b(v){}auto get()const->bool{return b;}};"))
check("empty class value boundary", program("Empty e=make();return use(e);", "auto make()->Empty{Empty e=Empty();return e;}auto use(Empty e)->i64{return 42;}", "class Empty{public:Empty(){}};"))
check("public aggregate class return", program("Pair p=make();return sum(p);", "auto make()->Pair{Pair p=Pair{.a=20,.b=22};return p;}auto sum(Pair p)->i64{return p.a+p.b;}", "class Pair{public:i64 a;i64 b;};"))
check("class return checked overflow", program("Counter c=make(9223372036854775807);return c.get();", "auto make(i64 n)->Counter{Counter c=Counter(n+1);return c;}"), trap=True)
check("scalar result with class input checked overflow", program("Counter c=Counter(9223372036854775807);return overflow(c);", "auto overflow(Counter c)->i64{return c.get()+1;}"), trap=True)
check("ordinary class-value recursion", program("Counter c=Counter(40);Counter r=step(c,2);return r.get();", "auto step(Counter c,i64 n)->Counter{if(n==0){return c;}Counter next=c;next.add(1);Counter result=step(next,n-1);return result;}"))
check("method calls class consumer and preserves receiver", program("Counter c=Counter(21);return c.twice();", "auto copy_value(Counter c)->i64{return c.get();}", COUNTER.replace("};", "auto twice()const->i64{Counter local=Counter(value);return copy_value(local)+value;}};")))

for name, body, helpers, error in [
    ("class parameter immutable field", "Counter c=Counter(42);return change(c);", "auto change(Counter c)->i64{c.value=0;return 42;}", "mutable class local"),
    ("class parameter mutable method denied", "Counter c=Counter(42);return change(c);", "auto change(Counter c)->i64{return c.add(1);}", "mutable receiver"),
    ("class parameter private field denied", "Counter c=Counter(42);return change(c);", "auto change(Counter c)->i64{return c.value;}", "private class field"),
    ("return scalar as class denied", "Counter c=make();return c.get();", "auto make()->Counter{const i64 c=42;return c;}", "expected Counter"),
    ("constructor temporary return denied", "Counter c=make();return c.get();", "auto make()->Counter{return Counter(42);}", "complete local name"),
    ("forwarded class call return needs local", "Counter c=outer();return c.get();", "auto make()->Counter{Counter c=Counter(42);return c;}auto outer()->Counter{return make();}", "complete local name"),
    ("temporary class argument denied", "return get(Counter(42));", "auto get(Counter c)->i64{return c.get();}", "complete local name"),
    ("class-return call argument needs local", "return get(make());", "auto make()->Counter{Counter c=Counter(42);return c;}auto get(Counter c)->i64{return c.get();}", "complete local name"),
    ("discard class-return call denied", "make();return 42;", "auto make()->Counter{Counter c=Counter(42);return c;}", "typed local initializer"),
    ("class return missing path", "Counter c=make(true);return c.get();", "auto make(bool yes)->Counter{Counter c=Counter(42);if(yes){return c;}}", "every path"),
    ("wrong scalar argument to class parameter", "return get(42);", "auto get(Counter c)->i64{return c.get();}", "complete local name"),
    ("class value cannot enter scalar argument", "Counter c=Counter(42);return get(c);", "auto get(i64 c)->i64{return c;}", "class values"),
]:
    check(name, program(body, helpers), error=error)

check("nominal class parameter mismatch", program("Other c=Other{.value=42};return get(c);", "auto get(Counter c)->i64{return c.get();}", COUNTER+"class Other{public:i64 value;};"), error="expected Counter")
check("nominal class return mismatch", program("Counter c=make();return c.get();", "auto make()->Counter{Other c=Other{.value=42};return c;}", COUNTER+"class Other{public:i64 value;};"), error="expected Counter")
check("method class parameter makes independent typed result", program("Counter c=Counter(42);Counter result=c.copy(c);c.add(1);return result.get();", definition=COUNTER.replace("};", "auto copy(Counter source)const->Counter{return source;}};")))
check("class method result cannot return scalar field", program("return 42;", definition=COUNTER.replace("get() const -> i64", "get() const -> Counter")), error="unknown local")

LIB = "export module counters;export "+COUNTER+"export auto make(i64 n)->Counter{Counter c=Counter(n);return c;}export auto consume(Counter c)->i64{return c.get();}"
check("cross-module factory consumer", app("Counter c=make(42);return consume(c);", "import counters;"), {"counters":LIB})
check("namespace factory nominal type", app("items::Counter c=items::make(42);return items::consume(c);", "import counters;"), {"counters":"export module counters;export namespace items{"+COUNTER+"auto make(i64 n)->Counter{Counter c=Counter(n);return c;}auto consume(Counter c)->i64{return c.get();}}"})
check("exported private return type rejected", app("return 42;", "import counters;"), {"counters":LIB.replace("export class Counter", "class Counter")}, error="exposes private type")
check("exported private parameter type rejected", app("return 42;", "import counters;"), {"counters":"export module counters;"+COUNTER+"export auto consume(Counter c)->i64{return c.get();}"}, error="exposes private type")
TRANSITIVE = {"values":"export module values;export "+COUNTER, "factory":"export module factory;import values;export auto make()->Counter{Counter c=Counter(42);return c;}"}
check("transitive result type not implicitly exported", app("return make();", "import factory;"), TRANSITIVE, error="direct visible import")
check("direct type import permits factory", app("Counter c=make();return c.get();", "import factory;import values;"), TRANSITIVE)
check("private value function allowed within defining module", app("return answer();", "import counters;"), {"counters":"export module counters;"+COUNTER+"auto make()->Counter{Counter c=Counter(42);return c;}export auto answer()->i64{Counter c=make();return c.get();}"})
check("public factory cannot bypass designated restriction", app("Counter c=make();return c.get();", "import counters;"), {"counters":"export module counters;export "+COUNTER+"export auto make()->Counter{Counter c=Counter{.value=42};return c;}"}, error="designated")
check("minmax standard-shaped scalar algorithm", app("const std::MinMax limits=std::minmax(42,0);return std::range_width(limits);", "import std.numeric;"), library=True)
check("minmax signed endpoint preservation", app("const std::MinMax limits=std::minmax(9223372036854775807,-9223372036854775808);return limits.min();", "import std.numeric;"), library=True, expected=-9223372036854775808)
check("range width checked overflow", app("const std::MinMax limits=std::minmax(9223372036854775807,-9223372036854775808);return std::range_width(limits);", "import std.numeric;"), library=True, trap=True)
check("minmax private representation", app("const std::MinMax limits=std::minmax(42,0);return limits.lower;", "import std.numeric;"), library=True, error="private class field")

for size, error in [(64,None),(65,"64 scalar fields")]:
    fields="".join(f"i64 f{i};" for i in range(size))
    initializers=",".join(f".f{i}={42 if i==size-1 else 0}" for i in range(size))
    definition="class Large{public:"+fields+"};"
    helper="auto value(Large x)->Large{return x;}"
    check(f"boundary {size} fields", program(f"Large x=Large{{{initializers}}};Large y=value(x);return y.f{size-1};", helper, definition), error=error)

wide_fields="".join(f"i64 f{i};" for i in range(64))
wide_init=",".join(f".f{i}={7 if i==63 else i}" for i in range(64))
wide_class="class Wide{public:"+wide_fields+"};"
check("six maximum-width class arguments", program("Wide x=Wide{"+wide_init+"};return sum(x,x,x,x,x,x);", "auto sum(Wide a,Wide b,Wide c,Wide d,Wide e,Wide f)->i64{return a.f63+b.f63+c.f63+d.f63+e.f63+f.f63;}", wide_class))
check("maximum-width result with mixed arguments", program("Wide x=Wide{"+wide_init+"};Wide result=select(x,true,x,21,x,14);return result.f63+35;", "auto select(Wide a,bool yes,Wide b,i64 n,Wide c,i64 extra)->Wide{if(yes){return b;}return c;}", wide_class))
check("receiver survives class-result hidden pointer", program("Counter c=Counter(21);return c.twice();", "auto copy(Counter c)->Counter{return c;}", COUNTER.replace("};", "auto twice()const->i64{Counter local=Counter(value);Counter result=copy(local);return result.get()+value;}};")))
check("returned parameter survives clobbering helper", program("Counter c=Counter(42);Counter result=copy(c);return result.get();", "auto clobber()->i64{Counter x=Counter(999);return x.get();}auto copy(Counter c)->Counter{clobber();return c;}"))
check("class parameter copied mutable local in loop", program("Counter c=Counter(20);return twice(c);", "auto twice(Counter c)->i64{i64 n=0;i64 sum=0;while(n<2){Counter x=c;sum=sum+x.add(1);n=n+1;}return sum;}"))
check("class result reflection layout preserved", program("Counter c=make();static_assert(size_of(Counter)==8);return reflect_size(type_id(Counter))+c.get();", "auto make()->Counter{Counter c=Counter(34);return c;}"))
check("seven class arguments rejected", program("return 42;", "auto too_many(Counter a,Counter b,Counter c,Counter d,Counter e,Counter f,Counter g)->i64{return 0;}"), error="at most six")

print(f"{COUNT} class value function-boundary checks passed")
