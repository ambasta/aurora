#!/usr/bin/env python3
"""Execute checked signed division and the freestanding integer algorithms."""
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
        print("PASS integer", name)


def app(body, imports=""):
    return "module app; " + imports + " auto test() -> i64 { " + body + " }"


MIN = -9223372036854775808
MAX = 9223372036854775807
for a, b, q, r in [(85,2,42,1),(-85,2,-42,-1),(85,-2,-42,1),(-85,-2,42,-1),
                   (1,2,0,1),(-1,2,0,-1),(1,-2,0,1),(-1,-2,0,-1),
                   (MIN,1,MIN,0),(MIN,2,-4611686018427387904,0),
                   (MIN,MAX,-1,-1),(MAX,MIN,0,MAX),(0,-1,0,0)]:
    check(f"quotient {a} {b}", app(f"return ({a}) / ({b});"), expected=q)
    check(f"remainder {a} {b}", app(f"return ({a}) % ({b});"), expected=r)
check("minimum remainder negative one", app(f"return ({MIN}) % -1;"), expected=0)
check("minimum quotient negative one traps", app(f"return ({MIN}) / -1;"), trap=True)
for a in [0,1,-1,MIN,MAX]:
    for operation in ["/","%"]:
        check(f"zero divisor {a} {operation}", app(f"return ({a}) {operation} 0;"), trap=True)
check("multiplicative left associativity", app("return 48 / 8 * 7;"))
check("remainder multiplication precedence", app("return 20 % 6 * 21;"))
check("arithmetic precedence", app("return 2 + 80 / 4 * 2;"))
check("comment and division lexing", "module app;auto test()->i64{return 84 / // denominator follows\n 2;}")
check("nested function division", "module app;auto id(i64 x)->i64{return x;}auto test()->i64{return 1+id(83)/id(2);}")
COUNTER="class Counter{i64 n;public:Counter():n(0){}auto next()->i64{n=n+1;return n;}auto get()const->i64{return n;}};"
check("quotient evaluates once left to right", "module app;"+COUNTER+"auto test()->i64{Counter c=Counter();const i64 q=c.next()/c.next();return q*10+c.get();}",expected=2)
check("remainder evaluates once left to right", "module app;"+COUNTER+"auto test()->i64{Counter c=Counter();const i64 r=c.next()%c.next();return r*10+c.get();}",expected=12)
for expression in ["true / false", "true % false", "1 / true", "false % 1"]:
    check("division operand type "+expression, app("return "+expression+";"), error="expected")
check("owned integer not implicitly divisible", app("own<i64> x=own(42);return x/1;"),error="cannot be implicitly copied")
check("division in checked index", app("array<i64,2> a={0,42};return a[3/2];"))
check("division through class result ABI", app("const std::DivResult result=std::div(85,2);return result.quot();", "import std.integer;"),library=True)
check("class result remainder", app("const std::DivResult result=std::div(-85,2);return result.rem();", "import std.integer;"),library=True,expected=-1)
check("div result private field", app("const std::DivResult result=std::div(85,2);return result.quotient;", "import std.integer;"),library=True,error="private class field")
check("div result designated construction denied", app("const std::DivResult result=std::DivResult{.quotient=42,.remainder=1};return result.quot();", "import std.integer;"),library=True,error="designated")
check("library div zero traps", app("const std::DivResult result=std::div(42,0);return result.quot();", "import std.integer;"),library=True,trap=True)
check("library div quotient overflow traps", app(f"const std::DivResult result=std::div({MIN},-1);return result.rem();", "import std.integer;"),library=True,trap=True)
for a,b,g,l in [(0,0,0,0),(0,42,42,0),(42,0,42,0),(-6,21,3,42),(6,-21,3,42),
                 (-6,-21,3,42),(21,6,3,42),(MIN,2,2,None),(MIN,-1,1,None),
                 (MIN,MAX,1,None),(MAX,MAX,MAX,MAX),(MIN,0,None,0),(MIN,MIN,None,None)]:
    for function,value in [("gcd",g),("lcm",l)]:
        check(f"library {function} {a} {b}",app(f"return std::{function}({a},{b});", "import std.integer;"),library=True,expected=value if value is not None else 0,trap=value is None)
check("lcm divides before multiplication", app("return std::lcm(9223372036854775807,9223372036854775807);", "import std.integer;"),library=True,expected=MAX)
print(f"{COUNT} checked integer and library checks passed")
