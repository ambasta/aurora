#!/usr/bin/env python3
"""Independent exhaustive byte arithmetic and source-boundary acceptance suite.

One small Aurora module is compiled for the numerical sweep. Bounded native
assembly loops call its scalar functions for every byte and every ordered pair,
writing every result as eight bytes. Python's unbounded integers provide the
expected mathematical answers; no expected arithmetic comes from compiler code
or another oracle. Checked operations exhaust their nontrapping domains, with
an explicit full-width sentinel for excluded overflow/zero-divisor inputs.
Separate failure-edge fixtures require SIGILL at the exact retained named UD2.

Source fixtures exercise byte literals, conversions, constness, classes, arrays,
Scalar/Value templates and copied value calls. Rejections leave no artifact and must
not change an existing one (native_runner.py).
No aggregate byte-layout assumption is made by this numerical suite.

Run: python3 tests/compiler/u8_numeric.py build/aurorac
This is exhaustive evidence for bounded numeric domains, not a safety proof.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import struct
import tempfile
from typing import Callable

from native_runner import DIAGNOSTIC, ROOT, Freestanding, Rejection, Suite, Trap, command, freestanding_glue, observe
from native_runner import require, run
from unsigned_oracle import Case


BYTE_MAX = 255
EXCLUDED = (1 << 64) - 1


@dataclass(frozen=True)
class Sweep:
    name: str
    body: str
    expected: Callable[[int, int], int]
    left_count: int = 256
    right_count: int = 256


def checked(value):
    return value if 0 <= value <= BYTE_MAX else EXCLUDED


def sweeps():
    prefix = "const u8 a=u8(left);const u8 b=u8(right);"
    specifications = [
        ("add", "if(left+right<=255){return u64(a+b);}", lambda a, b: checked(a + b)),
        ("subtract", "if(left>=right){return u64(a-b);}", lambda a, b: checked(a - b)),
        ("multiply", "if(left*right<=255){return u64(a*b);}", lambda a, b: checked(a * b)),
        ("divide", "if(right!=0){return u64(a/b);}", lambda a, b: a // b if b else EXCLUDED),
        ("remainder", "if(right!=0){return u64(a%b);}", lambda a, b: a % b if b else EXCLUDED),
        ("and", "return u64(a&b);", lambda a, b: a & b),
        ("or", "return u64(a|b);", lambda a, b: a | b),
        ("xor", "return u64(a^b);", lambda a, b: a ^ b),
    ]
    for name, expression, expected in specifications:
        fallback = f"return {EXCLUDED}u64;" if expression.startswith("if") else ""
        yield Sweep(name, prefix + expression + fallback, expected)
    for name, operator, expected in [
        ("less", "<", lambda a, b: int(a < b)),
        ("less_equal", "<=", lambda a, b: int(a <= b)),
        ("greater", ">", lambda a, b: int(a > b)),
        ("greater_equal", ">=", lambda a, b: int(a >= b)),
        ("equal", "==", lambda a, b: int(a == b)),
        ("not_equal", "!=", lambda a, b: int(a != b)),
    ]:
        yield Sweep(name, prefix + f"if(a{operator}b){{return 1u64;}}return 0u64;", expected)
    for name, expression, expected in [
        ("from_signed", "u64(u8(left))", lambda a, b: a),
        ("from_unsigned", "u64(u8(u64(left)))", lambda a, b: a),
        ("to_signed", "u64(i64(u8(left)))", lambda a, b: a),
        ("complement", "u64(~u8(left))", lambda a, b: BYTE_MAX - a),
        ("double_complement", "u64(~~u8(left))", lambda a, b: a),
    ]:
        yield Sweep(name, f"return {expression};", expected, right_count=1)
    # Each literal is observed separately, through four legal 64-element arrays.
    for block in range(4):
        start = block * 64
        literals = ",".join(f"{value}u8" for value in range(start, start + 64))
        yield Sweep(
            f"literals_{block}",
            f"const array<u8,64> values={{{literals}}};return u64(values[left]);",
            lambda a, b, start=start: start + a,
            left_count=64,
            right_count=1,
        )
    yield Sweep(
        "left_shift",
        "const u8 a=u8(left);i64 factor=1;i64 n=0;"
        "while(n<right){factor=factor*2;n=n+1;}"
        "if(left*factor<=255){return u64(a<<right);}"
        f"return {EXCLUDED}u64;",
        lambda a, b: checked(a * (2**b)),
        right_count=8,
    )
    yield Sweep("right_shift", "return u64(u8(left)>>right);", lambda a, b: a // (2**b), right_count=8)


def scan_assembly(specifications):
    # Loop state is stack-resident across calls. No compiler-specific scratch
    # register behavior or aggregate ABI is assumed. At most 2 KiB is buffered.
    lines = [".text", ".globl u8_scan", "u8_scan:", "pushq %rbp", "movq %rsp,%rbp", "subq $2080,%rsp"]
    for index, spec in enumerate(specifications):
        lines += [
            "movq $0,-8(%rbp)",
            f".Lu8_outer_{index}:",
            "movq $0,-16(%rbp)",
            f".Lu8_inner_{index}:",
            "movq -8(%rbp),%rdi",
            "movq -16(%rbp),%rsi",
            f"call byte_{spec.name}",
            "movq -16(%rbp),%rcx",
            "movq %rax,-2080(%rbp,%rcx,8)",
            "incq -16(%rbp)",
            f"cmpq ${spec.right_count},-16(%rbp)",
            f"jl .Lu8_inner_{index}",
            "movq $1,%rax",
            "movq $1,%rdi",
            "leaq -2080(%rbp),%rsi",
            f"movq ${spec.right_count * 8},%rdx",
            "syscall",
            f"cmpq ${spec.right_count * 8},%rax",
            "jne .Lu8_write_failed",
            "incq -8(%rbp)",
            f"cmpq ${spec.left_count},-8(%rbp)",
            f"jl .Lu8_outer_{index}",
        ]
    lines += [
        "xorq %rax,%rax",
        "leave",
        "ret",
        ".Lu8_write_failed:",
        "movq $60,%rax",
        "movq $70,%rdi",
        "syscall",
        '.section .note.GNU-stack,"",@progbits',
        "",
    ]
    return "\n".join(lines)


def validate_sweep(observed, specifications, report=True):
    require(
        observed.exit_code == 0 and observed.terminal_signal is None,
        f"numeric sweep did not return normally: {observed}",
    )
    count = sum(s.left_count * s.right_count for s in specifications)
    require(
        len(observed.output) == (count + 1) * 8,
        f"numeric sweep expected {(count + 1) * 8} bytes, got {len(observed.output)}",
    )
    values = iter(struct.iter_unpack("<Q", observed.output))
    reports = []
    for spec in specifications:
        included = 0
        for left in range(spec.left_count):
            for right in range(spec.right_count):
                actual = next(values)[0]
                expected = spec.expected(left, right)
                require(actual == expected, f"{spec.name}({left},{right}): expected {expected}, got {actual}")
                included += expected != EXCLUDED
        reports.append(
            f"PASS u8 sweep {spec.name}: {spec.left_count * spec.right_count} "
            f"inputs, {included} evaluated numeric results"
        )
    require(next(values)[0] == 0, "numeric sweep trailer was not the complete zero return")
    if report:
        for line in reports:
            print(line, flush=True)
    return count


def run_sweeps(compiler, directory, timeout):
    """One module and one scan loop for every byte and ordered byte pair."""
    specifications = list(sweeps())
    source = "module byte_oracle;\n" + "\n".join(
        f"auto byte_{s.name}(i64 left,i64 right)->u64{{{s.body}}}" for s in specifications
    )
    path, output, program = directory / "sweep.au", directory / "sweep.s", directory / "program.s"
    path.write_text(source)
    command([compiler, path, "-o", output], timeout=timeout)
    require(path.read_text() == source, "compiler changed numerical sweep input")
    program.write_text(
        output.read_text() + scan_assembly(specifications) + freestanding_glue(["u8_scan"], [0], note=True)
    )
    command(["as", "--64", program, "-o", directory / "program.o"])
    harness = Freestanding()
    harness.prepare(directory)
    harness.link([directory / "program.o"], directory / "program")
    return validate_sweep(observe(run([directory / "program"], timeout)), specifications)


CELL = (
    "class Cell{u8 value;public:Cell(u8 n):value(n){}"
    "auto get()const->u8{return value;}auto set(u8 n)->u8{value=n;return value;}"
    "auto snapshot()const->Cell{const Cell result=Cell(value);return result;}};"
)
BOX = (
    "template<Scalar T>class Box{T value;public:Box(T n):value(n){}"
    "auto get()const->T{return value;}auto set(T n)->T{value=n;return value;}};"
)


def positive_cases():
    for expression, expected in [
        ("010u8", 10),
        ("08u8", 8),
        ("000255u8", 255),
        ("2u8+21u8/4u8*3u8", 17),
        ("20u8/3u8/2u8", 3),
        ("20u8%6u8%3u8", 2),
        ("1u8+2u8<<3", 24),
        ("32u8>>1+2", 4),
        ("1u8<<1<<2", 8),
        ("128u8>>2>>1", 16),
        ("8u8|6u8^3u8&1u8", 15),
        ("~0u8^1u8", 254),
        ("1u8<<3|2u8", 10),
        ("8u8>>1&3u8", 0),
    ]:
        yield Case("literal/precedence " + expression, f"return u64({expression});", expected)
    yield Case(
        "byte reflection",
        "static_assert(type_id(u8)==11);"
        "static_assert(size_of(u8)==1);static_assert(field_count(u8)==0);"
        "static_assert(type_id(u8)!=type_id(u64));"
        "static_assert(type_id(u8)!=type_id(i64));"
        "return reflect_size(type_id(u8))+reflect_field_count(type_id(u8));",
        1,
        "i64",
    )
    yield Case(
        "byte static comparison",
        "static_assert(255u8>128u8);static_assert(0u8<255u8);static_assert(128u8==128u8);return 255u64;",
        255,
    )
    yield Case(
        "array copy and assignment",
        "array<u8,3> a={0u8,128u8,255u8};"
        "const array<u8,3> b=a;a[1]=1u8;a[2]=2u8;"
        "return u64(b[len(b)-1])*256u64+u64(b[1])+u64(a[1]);",
        65409,
    )
    yield Case(
        "maximum-capacity byte array",
        "array<u8,64> a={" + ",".join(["0u8"] * 64) + "};a[63]=255u8;return u64(a[0])+u64(a[63]);",
        255,
    )
    yield Case(
        "class copy and result",
        "Cell a=Cell(255u8);const Cell b=copy(a);a.set(0u8);return u64(b.get());",
        255,
        prelude=CELL + "auto copy(Cell x)->Cell{return x;}",
    )
    yield Case(
        "class method result",
        "Cell a=Cell(128u8);const Cell b=a.snapshot();a.set(255u8);return u64(b.get())*256u64+u64(a.get());",
        33023,
        prelude=CELL,
    )
    yield Case(
        "scalar template byte",
        "Box<u8> a=Box<u8>(255u8);const Box<u8> b=copy(a);a.set(1u8);return u64(b.get())*256u64+u64(a.get());",
        65281,
        prelude=BOX + "auto copy(Box<u8> x)->Box<u8>{return x;}",
    )
    yield Case(
        "Value template byte",
        "const Pair<u8,u64> p=Pair<u8,u64>(255u8,9223372036854775808u64);return u64(p.first)+p.second;",
        (1 << 63) + 255,
        prelude="template<Value T,Value U>class Pair{public:T first;U second;Pair(T a,U b):first(a),second(b){}};",
    )
    yield Case(
        "library pair byte",
        "const std::pair<u8,u64> p=std::pair<u8,u64>(255u8,18446744073709551360u64);return u64(p.first)+p.second;",
        EXCLUDED,
        imports=("std.utility",),
    )
    yield Case(
        "library array byte",
        "std::array<u8,64> a=std::array<u8,64>();"
        "a.set(63,255u8);const std::array<u8,64> b=copy(a);a.set(63,0u8);"
        "return u64(b.at(63))+u64(a.at(0));",
        255,
        prelude="auto copy(std::array<u8,64> x)->std::array<u8,64>{return x;}",
        imports=("std.array",),
    )
    yield Case(
        "six scalar byte arguments",
        "return u64(select(0u8,1,128u8,true,18446744073709551615u64,255u8));",
        255,
        prelude="auto select(u8 a,i64 b,u8 c,bool d,u64 e,u8 f)->u8{return f;}",
    )
    yield Case(
        "recursive byte return",
        "return u64(sum(20u8));",
        210,
        prelude="auto sum(u8 n)->u8{if(n==0u8){return 0u8;}return n+sum(n-1u8);}",
    )
    yield Case(
        "snapshot before mutating next argument",
        "Cell a=Cell(128u8);const Cell b=save(a,a.set(255u8));return u64(b.get());",
        128,
        prelude=CELL + "auto save(Cell c,u8 ignored)->Cell{return c;}",
    )
    yield Case(
        "byte loop",
        "u8 n=0u8;i64 total=0;while(n<255u8){total=total+i64(n);n=n+1u8;}return total+i64(n);",
        32640,
        "i64",
    )
    trace = (
        "class Trace{u8 n;public:Trace():n(0u8){}"
        "auto next()->u8{n=n+1u8;return n;}"
        "auto count()->i64{n=n+1u8;return i64(n);}auto get()const->u8{return n;}};"
    )
    for expression, expected in [
        ("t.next()+t.next()", 302),
        ("t.next()*t.next()", 202),
        ("t.next()/t.next()", 2),
        ("t.next()%t.next()", 102),
        ("t.next()&t.next()", 2),
        ("t.next()|t.next()", 302),
        ("t.next()^t.next()", 302),
        ("t.next()<<t.count()", 402),
        ("t.next()>>t.count()", 2),
    ]:
        yield Case(
            "left-to-right once " + expression,
            f"Trace t=Trace();const u8 result={expression};return u64(result)*100u64+u64(t.get());",
            expected,
            prelude=trace,
        )


def trap_cases():
    edges = (0, 1, 2, 3, 15, 16, 17, 127, 128, 129, 254, 255)
    for a in edges:
        if a:
            yield Case(f"addition overflow boundary {a}", f"return u64({a}u8+{256 - a}u8);", Trap.OVERFLOW)
        if a < 255:
            yield Case(f"subtraction underflow boundary {a}", f"return u64({a}u8-{a + 1}u8);", Trap.OVERFLOW)
        if a > 1:
            yield Case(f"multiplication overflow boundary {a}", f"return u64({a}u8*{255 // a + 1}u8);", Trap.OVERFLOW)
        for op in ("/", "%"):
            yield Case(f"zero divisor {a}{op}0", f"return u64({a}u8{op}0u8);", Trap.ZERO)
    for count in range(1, 8):
        yield Case(f"left overflow at count {count}", f"return u64({255 // (2**count) + 1}u8<<{count});", Trap.OVERFLOW)
    for count in (-(1 << 63), -9, -1, 8, 9, 63, 64, (1 << 63) - 1):
        for value in (0, 255):
            for op in ("<<", ">>"):
                yield Case(f"invalid shift {value}{op}{count}", f"return u64({value}u8{op}({count}));", Trap.COUNT)
    for value in (-(1 << 63), -256, -1, 256, 257, (1 << 63) - 1):
        yield Case(f"checked signed narrowing {value}", f"return u64(u8({value}));", Trap.OVERFLOW)
    for value in (256, 257, 65535, 1 << 32, 1 << 63, EXCLUDED):
        yield Case(f"checked unsigned narrowing {value}", f"return u64(u8({value}u64));", Trap.OVERFLOW)
    for expression, expected in [
        ("(255u8+1u8)/0u8", Trap.OVERFLOW),
        ("(1u8/0u8)+(255u8+1u8)", Trap.ZERO),
        ("0u8*(1u8/0u8)", Trap.ZERO),
        ("0u8&(1u8%0u8)", Trap.ZERO),
        ("(255u8+1u8)<<8", Trap.OVERFLOW),
        ("0u8<<(9223372036854775807+1)", Trap.OVERFLOW),
        ("(1u8<<8)/0u8", Trap.COUNT),
        ("(1u8/0u8)<<8", Trap.ZERO),
        ("u8(-1)<<8", Trap.OVERFLOW),
        ("u8(256u64)/0u8", Trap.OVERFLOW),
    ]:
        yield Case("trap evaluation order " + expression, f"return u64({expression});", expected)


def rejection_cases():
    def app(body, result="u8", prelude=""):
        return f"module app;{prelude}auto test()->{result}{{{body}}}"

    for literal in (
        "256u8",
        "999999999999999999999999999999999999u8",
        "1U8",
        "1u08",
        "1u8u8",
        "1u8foo",
        "1u9",
        "256",
        "1u64",
    ):
        yield Rejection("invalid byte literal/result " + literal, app(f"return {literal};"))
    for expression in (
        "-0u8",
        "-1u8",
        "-255u8",
        "u8(1u8)",
        "u8(true)",
        "u8(false)",
        "u8()",
        "u8(1,2)",
        "1u8<<1u8",
        "1u8>>1u8",
        "1u8<<1u64",
        "1u8>>1u64",
        "1u8<<true",
        "1u8>>false",
    ):
        # Use self-comparison so a forbidden operation cannot appear to reject
        # merely because its incorrectly inferred result type mismatches u8.
        yield Rejection(
            "forbidden byte expression " + expression,
            app(f"if(({expression})==({expression})){{return 0u8;}}return 1u8;"),
        )
    for op in ("+", "-", "*", "/", "%", "&", "|", "^", "<", "<=", ">", ">=", "==", "!="):
        for other in ("1", "1u64", "true"):
            for left, right in (("1u8", other), (other, "1u8")):
                result = "bool" if op in ("<", "<=", ">", ">=", "==", "!=") else "u8"
                expression = left + op + right
                body = (
                    f"return {expression};"
                    if result == "bool"
                    else f"if(({expression})==({expression})){{return 0u8;}}return 1u8;"
                )
                yield Rejection("mixed byte operation " + left + op + right, app(body, result))
    for body, result, prelude in [
        ("u8 n=1;return n;", "u8", ""),
        ("u8 n=1u64;return n;", "u8", ""),
        ("u64 n=1u8;return n;", "u64", ""),
        ("i64 n=1u8;return n;", "i64", ""),
        ("u8 n=0u8;n=1;return n;", "u8", ""),
        ("const u8 n=0u8;n=1u8;return n;", "u8", ""),
        ("array<u8,1> a={1};return a[0];", "u8", ""),
        ("array<u8,1> a={1u64};return a[0];", "u8", ""),
        ("array<u8,1> a={1u8};return a[0u8];", "u8", ""),
        ("const array<u8,1> a={1u8};a[0]=2u8;return a[0];", "u8", ""),
        ("array<u8,1> a={1u8};a[0]=1u64;return a[0];", "u8", ""),
        ("return take(1);", "u8", "auto take(u8 n)->u8{return n;}"),
        ("return take(1u64);", "u8", "auto take(u8 n)->u8{return n;}"),
        ("return take(1u8);", "u64", "auto take(u64 n)->u64{return n;}"),
        ("Cell a=Cell(1);return a.get();", "u8", CELL),
        ("Cell a=Cell(1u8);return a.set(1u64);", "u8", CELL),
        ("const Cell a=Cell(1u8);return a.set(2u8);", "u8", CELL),
        ("Cell a=Cell(1u8);return a.value;", "u8", CELL),
        ("Box<u8> a=Box<u8>(1);return a.get();", "u8", BOX),
        ("const Box<u8> a=Box<u8>(1u8);return a.set(2u8);", "u8", BOX),
        ("return u8(E::a);", "u8", "enum class E{a,b};"),
        ("return i64(E::a);", "i64", "enum class E{a,b};"),
        ("return u64(E::a);", "u64", "enum class E{a,b};"),
        ("return E(1u8);", "E", "enum class E{a,b};"),
        ("Box<E> a=Box<E>(E::a);return a.get();", "E", "enum class E{a,b};" + BOX),
        ("return 1u8==E::a;", "bool", "enum class E{a,b};"),
        ("static_assert(1u8==1u64);return 1u8;", "u8", ""),
        ("static_assert(1u8==1);return 1u8;", "u8", ""),
        ("return reflect_size(1u8);", "i64", ""),
        ("own<u8> n=own(1u8);return 0u8;", "u8", ""),
    ]:
        yield Rejection("byte source boundary " + body, app(body, result, prelude))
    yield Rejection("reserved byte conversion name", "module app;auto u8(i64 n)->i64{return n;}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    require(args.timeout > 0, "timeout must be positive")
    compiler = args.compiler.resolve()
    with tempfile.TemporaryDirectory(prefix="aurora-u8-numeric-") as temporary:
        count = run_sweeps(compiler, Path(temporary), args.timeout)
    print(f"PASS u8 numeric: {count} exhaustive observations", flush=True)
    suite = Suite(compiler, "u8 source", timeout=args.timeout)
    for case in [*positive_cases(), *trap_cases()]:
        suite.value(case.name, case.body, case.expected, case.result_type, case.prelude, case.imports)
    for case in rejection_cases():
        suite.reject(case.name, case.source, pattern=DIAGNOSTIC)
    suite.finish()


if __name__ == "__main__":
    main()
