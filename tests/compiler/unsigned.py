#!/usr/bin/env python3
"""Execute typed unsigned scalars, checked conversions, bit operations and std.bit."""

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
                    int.from_bytes(executed.stdout, "little", signed=False) == expected % (1 << 64),
                    name + ": wrong scalar result",
                )
        COUNT += 1
        print("PASS unsigned", name)


def app(body, imports="", result="u64"):
    return "module app; " + imports + " auto test() -> " + result + " { " + body + " }"


MAX = (1 << 64) - 1
SIGN = 1 << 63
for name, expression, result in [
    ("maximum literal", f"{MAX}u64", MAX),
    ("leading zero decimal", "010u64", 10),
    ("leading zero eight", "08u64", 8),
    ("complement zero", "~0u64", MAX),
    ("complement maximum", f"~{MAX}u64", 0),
    ("complement high bit", f"~{SIGN}u64", SIGN - 1),
    ("add high", f"{SIGN}u64 + 42u64", SIGN + 42),
    ("subtract maximum", f"{MAX}u64 - {SIGN}u64", SIGN - 1),
    ("multiply high", "9223372036854775807u64 * 2u64", MAX - 1),
    ("divide high", f"{MAX}u64 / 2u64", SIGN - 1),
    ("remainder high", f"{MAX}u64 % {SIGN}u64", SIGN - 1),
    ("bit and", "85u64 & 51u64", 17),
    ("bit or", "85u64 | 51u64", 119),
    ("bit xor", "85u64 ^ 51u64", 102),
    ("left count 63", "1u64 << 63", SIGN),
    ("zero left 63", "0u64 << 63", 0),
    ("right count 63", f"{MAX}u64 >> 63", 1),
    ("logical high shift", f"{SIGN}u64 >> 1", SIGN // 2),
    ("left count zero", f"{MAX}u64 << 0", MAX),
    ("right count zero", f"{MAX}u64 >> 0", MAX),
    ("bit precedence", "1u64 | 2u64 ^ 3u64 & 6u64", 1),
    ("shift addition precedence", "1u64 << 1 + 2", 8),
    ("shift left associativity", "16u64 >> 1 >> 2", 2),
    ("conversion to unsigned", "u64(42)", 42),
]:
    check(name, app("return " + expression + ";"), expected=result)
check("conversion to signed", app("return i64(9223372036854775807u64);", result="i64"), expected=SIGN - 1)
for op in ["<", "<=", ">", ">=", "==", "!="]:
    a, b = SIGN, 42
    expected = {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b, "==": a == b, "!=": a != b}[op]
    check("unsigned comparison " + op, app(f"return {a}u64 {op} {b}u64;", result="bool"), expected=int(expected))
for name, expression, result_type in [
    ("addition overflow", f"{MAX}u64+1u64", "u64"),
    ("subtraction underflow", "0u64-1u64", "u64"),
    ("multiplication overflow", f"{SIGN}u64*2u64", "u64"),
    ("division zero", "42u64/0u64", "u64"),
    ("remainder zero", "42u64%0u64", "u64"),
    ("left overflow", "2u64<<63", "u64"),
    ("left negative", "0u64<<-1", "u64"),
    ("right negative", "0u64>>-1", "u64"),
    ("left 64", "0u64<<64", "u64"),
    ("right 64", "0u64>>64", "u64"),
    ("conversion negative", "u64(-1)", "u64"),
    ("conversion high", f"i64({SIGN}u64)", "i64"),
]:
    check(name, app("return " + expression + ";", result=result_type), trap=True)
for name, source, error in [
    ("literal overflow", app(f"return {MAX + 1}u64;"), "integer literal"),
    ("signed literal overflow", app(f"return {SIGN};"), "integer literal"),
    ("unknown suffix", app("return 1ul;"), "integer literal"),
    ("partial minimum literal suffix", app("return -9223372036854775808abc;", result="i64"), "integer literal"),
    ("negative unsigned minimum", app(f"return -{SIGN}u64;"), "expected"),
    ("negative unsigned", app("return -1u64;"), "expected"),
    ("mixed add", app("return 1u64+1;"), "expected"),
    ("mixed comparison", app("return 1u64==1;", result="bool"), "expected"),
    ("signed bitwise", app("return 1&2;", result="i64"), "expected"),
    ("signed complement", app("return ~1;", result="i64"), "expected"),
    ("signed shift", app("return 1<<2;", result="i64"), "expected"),
    ("unsigned shift count", app("return 1u64<<2u64;"), "expected"),
    ("bool conversion", app("return u64(true);"), "expected"),
    ("identity conversion", app("return u64(1u64);"), "expected"),
    ("implicit result conversion", app("return 1;"), "expected"),
    ("implicit local conversion", app("u64 a=1; return a;"), "expected"),
    ("unsigned owner unsupported", app("own<u64> a=own(1u64); return 0u64;"), "expected 'i64'"),
    ("unsigned index rejected", app("const array<u64,1> a={42u64};return a[0u64];"), "expected"),
    ("metadata index unsigned", app("return reflect_size(8u64);", result="i64"), "expected"),
    ("private builtin conversion name", "module app;auto u64(i64 x)->i64{return x;}", "reserved function"),
    ("literal static assert mismatch", app("static_assert(1u64==1);return 0u64;"), "expected"),
]:
    check(name, source, error=error)
check(
    "reflection and high static comparison",
    app(
        (
            "static_assert(type_id(u64)==8);static_assert(size_of(u64)==8);static_assert(field_count(u64)==0);s"
            "tatic_assert(18446744073709551615u64>9223372036854775807u64);static_assert(type_id(array<u64,2>)=="
            "2000002);return reflect_size(type_id(array<u64,2>))+reflect_size(type_id(u64));"
        ),
        result="i64",
    ),
    expected=24,
)
check(
    "array independent copy",
    app("const array<u64,2> a={18446744073709551615u64,42u64};array<u64,2> b=a;b[0]=0u64;return a[0]-b[0];"),
    expected=MAX,
)
check(
    "unsigned class value boundary",
    """module app;
class Box {u64 value;public:Box(u64 n):value(n){} auto get() const->u64{return value;} auto add(u64 n)->u64{value=value+n;return value;}};
auto copy(Box b,u64 n)->Box{const Box result=Box(b.get()+n);return result;}
auto test()->u64{Box b=Box(9223372036854775808u64);const Box c=copy(b,b.add(42u64)-b.get());return c.get();}
""",  # noqa: E501 - Preserve exact embedded Aurora source bytes.
    expected=SIGN,
)
for value in [0, 1, 2, 3, 42, SIGN, MAX]:
    for function, expected, result_type in [
        ("popcount", value.bit_count(), "i64"),
        ("bit_width", value.bit_length(), "i64"),
        ("has_single_bit", int(value != 0 and value & (value - 1) == 0), "bool"),
    ]:
        check(
            f"std.bit {function} {value}",
            app(f"return std::{function}({value}u64);", "import std.bit;", result_type),
            expected=expected,
            library=True,
        )
# Exercise full-width fields across the existing private aggregate ABI.
fields = " ".join(f"u64 f{i};" for i in range(64))
initializers = ",".join(f".f{i}={MAX - i}u64" for i in range(64))
check(
    "six maximum-width unsigned value parameters",
    "module app;class Wide{public:"
    + fields
    + "};"
    + "auto select(Wide a,Wide b,Wide c,Wide d,Wide e,Wide f)->Wide{"
    + "const Wide result=f;return result;}auto test()->u64{const Wide a=Wide{"
    + initializers
    + "};const Wide b=select(a,a,a,a,a,a);return b.f63;}",
    expected=MAX - 63,
)
check(
    "mixed six scalar unsigned arguments",
    (
        "module app;auto choose(i64 a,u64 b,bool c,u64 d,i64 e,u64 f)->u64{if(c){return b^d^f;}return 0u64;}aut"
        "o test()->u64{return 1u64+choose(0,18446744073709551615u64,true,1u64,0,9223372036854775808u64);}"
    ),
    expected=SIGN - 1,
)
check(
    "receiver high payload survives divide and shifts",
    (
        "module app;class C{u64 n;public:C(u64 x):n(x){}auto run(u64 divisor,i64 count)->u64{const u64 q=n/divi"
        "sor;n=q>>count;return n;}};auto test()->u64{C c=C(18446744073709551615u64);return c.run(3u64,1);}"
    ),
    expected=(MAX // 3) >> 1,
)
check(
    "unsigned recursive scalar",
    (
        "module app;auto sum(u64 n)->u64{if(n==0u64){return 0u64;}return n+sum(n-1u64);}auto test()->u64{return"
        " sum(9u64);}"
    ),
    expected=45,
)
check(
    "unsigned class result preserves snapshot",
    (
        "module app;class C{u64 n;public:C(u64 x):n(x){}auto get()const->u64{return n;}auto bump()->u64{n=n+1u6"
        "4;return n;}};auto save(C copy,u64 ignored)->C{return copy;}auto test()->u64{C c=C(9223372036854775808"
        "u64);const C snapshot=save(c,c.bump());return snapshot.get();}"
    ),
    expected=SIGN,
)
check(
    "cross-module u64 private field and result",
    app("const values::Cell c=values::make(18446744073709551615u64);return c.get();", "import values;"),
    modules={
        "values": (
            "export module values;export namespace values{class Cell{u64 n;public:Cell(u64 x):n(x){}auto get()c"
            "onst->u64{return n;}};auto make(u64 x)->Cell{const Cell result=Cell(x);return result;}}"
        )
    },
    expected=MAX,
)
check(
    "unsigned and signed array metadata separate",
    app(
        (
            "static_assert(type_id(array<u64,1>)!=type_id(array<i64,1>));static_assert(type_id(array<u64,1>)!=t"
            "ype_id(array<bool,1>));static_assert(type_id(u64)!=type_id(i64));return reflect_size(8)+reflect_fi"
            "eld_count(8);"
        ),
        result="i64",
    ),
    expected=8,
)

print(f"{COUNT} unsigned tests passed")
