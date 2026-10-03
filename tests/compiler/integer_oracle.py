#!/usr/bin/env python3
"""Independent bounded native oracle for checked i64 and std.integer.

Expectations use unbounded Python arithmetic, not compiler IR or generated code.
Division is defined explicitly from positive magnitudes, with truncation toward
zero; remainder is then a - q*b. gcd/lcm use mathematical nonnegative integers
and apply the signed-64 representability check only to the final result.

The generated Aurora functions execute as native Linux/x86-64 machine code. A
freestanding assembly syscall bridge writes eight little-endian bytes per scalar.
The narrow freestanding C++ signal adapter records the delivered signal, RIP, and
instruction bytes, then restores the same fault with its default signal action.
Python separately checks the actual terminating signal. Trap cases require
SIGILL at the exact named UD2 site, never
merely a nonzero exit, a generic crash, or a timeout. No Aurora C surface is added.

Run: python3 tests/compiler/integer_oracle.py build/aurorac
Optional deterministic stress: --seed 7043 --random-count 200
Use --self-test-only to validate the harness without a compiler implementation.
This is bounded test evidence, not a language-equivalence or safety proof.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import hashlib
import math
import os
import random
import resource
import shlex
import signal
import struct
import subprocess
import tempfile
import time


MIN = -(1 << 63)
MAX = (1 << 63) - 1
ROOT = Path(__file__).resolve().parents[2]
UD2 = 0x0B0F  # The two instruction bytes interpreted little-endian.


class Trap(Enum):
    ZERO = ".Laurora_division_zero_trap"
    OVERFLOW = ".Laurora_overflow_trap"


@dataclass(frozen=True)
class Case:
    name: str
    body: str
    expected: int | Trap
    prelude: str = ""
    library: bool = False


@dataclass(frozen=True)
class Observation:
    output: bytes
    exit_code: int | None = None
    terminal_signal: int | None = None
    delivery_signal: int | None = None
    pc: int | None = None
    instruction: int | None = None
    signal_code: int | None = None


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def representable(value):
    return value if MIN <= value <= MAX else Trap.OVERFLOW


def mathematical_divrem(a, b):
    """Unbounded mathematical result; // is applied only to positive operands."""
    require(b != 0, "reference division requires nonzero denominator")
    magnitude = abs(a) // abs(b)
    quotient = -magnitude if (a < 0) != (b < 0) else magnitude
    return quotient, a - quotient * b


def division(a, b):
    return Trap.ZERO if b == 0 else representable(mathematical_divrem(a, b)[0])


def remainder(a, b):
    return Trap.ZERO if b == 0 else mathematical_divrem(a, b)[1]


def gcd(a, b):
    return representable(math.gcd(a, b))


def lcm(a, b):
    if a == 0 or b == 0:
        return 0
    # Divide before multiplying, in unbounded positive arithmetic. In particular,
    # neither abs(MIN) nor an oversized intermediate product is itself an error.
    return representable((abs(a) // math.gcd(a, b)) * abs(b))


def validate_values(observed, expected, names):
    require(observed.exit_code == 0 and observed.terminal_signal is None,
            f"{names}: expected normal return, observed {observed}")
    require(len(observed.output) == len(expected) * 8,
            f"{names}: expected {len(expected) * 8} result bytes, got {len(observed.output)}")
    for index, (value, name) in enumerate(zip(expected, names)):
        actual = int.from_bytes(observed.output[index * 8:(index + 1) * 8],
                                "little", signed=True)
        require(actual == value, f"{name}: expected {value}, got {actual}")


def validate_trap(observed, expected, symbols, name):
    require(expected.value in symbols, f"{name}: missing named trap {expected.value}")
    require(observed.exit_code is None and observed.terminal_signal == signal.SIGILL
            and observed.delivery_signal == signal.SIGILL,
            f"{name}: expected actual SIGILL termination, observed {observed}")
    require(not observed.output, f"{name}: trap unexpectedly returned scalar bytes")
    require(observed.pc == symbols[expected.value],
            f"{name}: wrong trap PC {observed.pc!r}; expected {expected.value} "
            f"at {symbols[expected.value]:#x}")
    require(observed.instruction == UD2, f"{name}: trap instruction is not UD2")
    require(observed.signal_code is not None and observed.signal_code > 0,
            f"{name}: SIGILL was not a kernel-generated instruction fault")


def command(args, timeout=5, allow_signal=False):
    try:
        result = subprocess.run(
            [str(arg) for arg in args], capture_output=True, timeout=timeout,
            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"timeout is a failure, not a trap: {args}") from error
    require(result.returncode == 0 or (allow_signal and result.returncode < 0),
            f"command failed ({result.returncode}): {args}\n{result.stderr.decode(errors='replace')}")
    return result


def entry(functions):
    # Restore stack alignment after each write, so every call starts from the
    # same ABI-aligned stack. Each output is the entire i64, not an exit status.
    instructions = [".text", ".globl _start", "_start:",
                    "    call aurora_install_integer_signal_observer",
                    "    testq %rax, %rax", "    jz .Lobserver_installed",
                    "    movq $60, %rax", "    movq $125, %rdi", "    syscall",
                    ".Lobserver_installed:"]
    for function in functions:
        instructions.extend([
            f"    call {function}", "    pushq %rax", "    movq $1, %rax",
            "    movq $1, %rdi", "    movq %rsp, %rsi", "    movq $8, %rdx",
            "    syscall", "    addq $8, %rsp",
        ])
    instructions.extend([
        "    movq $60, %rax", "    xorq %rdi, %rdi", "    syscall",
        '.section .note.GNU-stack,"",@progbits', "",
    ])
    return "\n".join(instructions)


class NativeRunner:
    def __init__(self, directory, compiler, timeout):
        self.directory = directory
        self.compiler = compiler
        self.timeout = timeout
        self.observer = directory / "integer_signal.o"
        command(shlex.split(os.environ.get("CXX", "c++")) + [
            "-std=c++23", "-O2", "-Wall", "-Wextra", "-Werror", "-c",
            "-ffreestanding", "-fno-stack-protector", "-fno-exceptions", "-fno-rtti",
            "-fno-asynchronous-unwind-tables", "-fno-pie",
            ROOT / "tests/compiler/integer_signal.cpp", "-o", self.observer,
        ], timeout=30)

    def assemble(self, assembly, functions):
        program = self.directory / "program.s"
        program.write_text(assembly)
        (self.directory / "entry.s").write_text(entry(functions))
        # Preserve compiler-local symbols for exact fault-site attribution.
        command(["as", "--64", "-L", program, "-o", self.directory / "program.o"])
        command(["as", "--64", self.directory / "entry.s", "-o", self.directory / "entry.o"])
        binary = self.directory / "program"
        command(["ld", "-o", binary, self.directory / "entry.o", self.directory / "program.o",
                 self.observer])
        symbols = {}
        for line in command(["nm", "--defined-only", "--numeric-sort", binary]).stdout.decode().splitlines():
            fields = line.split()
            if len(fields) == 3:
                symbols[fields[2]] = int(fields[0], 16)
        result = command([binary], timeout=self.timeout, allow_signal=True)
        if result.returncode == 0:
            require(not result.stderr, "normal return unexpectedly reported a fault")
            return Observation(result.stdout, exit_code=0), symbols
        require(len(result.stderr) == 40,
                f"signal {result.returncode} without one complete fault record: {result.stderr!r}")
        identity, delivered, pc, instruction, code = struct.unpack("<QQQQq", result.stderr)
        require(identity == 0x4155524F52414654, "malformed native fault record identity")
        return Observation(result.stdout, terminal_signal=-result.returncode,
                           delivery_signal=delivered, pc=pc,
                           instruction=instruction, signal_code=code), symbols

    def cases(self, cases):
        require(cases and (len(cases) == 1 or all(not c.prelude for c in cases)),
                "only independent scalar cases may be batched")
        source = "module test;\n"
        if any(c.library for c in cases):
            source += "import std.integer;\n"
        functions = []
        for index, case in enumerate(cases):
            function = f"oracle_{index}"
            functions.append(function)
            source += case.prelude + f"\nauto {function}()->i64{{{case.body}}}\n"
        input_path = self.directory / "input.au"
        input_path.write_text(source)
        output = self.directory / "compiled.s"
        output.unlink(missing_ok=True)
        try:
            command([self.compiler, "--module-root", ROOT / "library", input_path, "-o", output])
            require(input_path.read_text() == source, "compiler modified its input")
            observed, symbols = self.assemble(output.read_text(), functions)
            if isinstance(cases[0].expected, Trap):
                require(len(cases) == 1, "trap batch would hide later cases")
                validate_trap(observed, cases[0].expected, symbols, cases[0].name)
            else:
                validate_values(observed, [c.expected for c in cases], [c.name for c in cases])
        except AssertionError as error:
            raise AssertionError(f"{error}\nReproduction source:\n{source}") from error


def rejected(check, label):
    try:
        check()
    except AssertionError:
        return
    raise AssertionError(f"harness self-test accepted {label}")


def self_tests(runner):
    for a in range(-12, 13):
        for b in range(-12, 13):
            if b == 0:
                continue
            q, r = mathematical_divrem(a, b)
            require(a == q * b + r and abs(r) < abs(b), "bad reference division identity")
            require(r == 0 or (r < 0) == (a < 0), "bad reference remainder sign")
    for a, b, q, r in [(7, 3, 2, 1), (-7, 3, -2, -1),
                        (7, -3, -2, 1), (-7, -3, 2, -1), (MIN, -1, 1 << 63, 0)]:
        require(mathematical_divrem(a, b) == (q, r), "bad explicit reference case")
    require(division(MIN, -1) is Trap.OVERFLOW and remainder(MIN, -1) == 0,
            "quotient and remainder overflow semantics were conflated")
    require(gcd(MIN, 0) is Trap.OVERFLOW and gcd(MIN, 2) == 2 and gcd(0, 0) == 0,
            "bad wide gcd reference")
    require(lcm(MIN, 0) == 0 and lcm(MIN, -1) is Trap.OVERFLOW and lcm(MAX, MAX) == MAX,
            "bad wide lcm reference")

    scalar = Observation((42).to_bytes(8, "little", signed=True), exit_code=0)
    validate_values(scalar, [42], ["correct synthetic scalar"])
    rejected(lambda: validate_values(scalar, [41], ["wrong value"]), "wrong scalar value")
    rejected(lambda: validate_values(Observation(b"*", exit_code=0), [42], ["short"]), "short output")
    symbols = {Trap.ZERO.value: 4096, Trap.OVERFLOW.value: 8192}
    trap = Observation(b"", terminal_signal=signal.SIGILL, delivery_signal=signal.SIGILL,
                       pc=4096, instruction=UD2, signal_code=2)
    validate_trap(trap, Trap.ZERO, symbols, "correct synthetic trap")
    rejected(lambda: validate_trap(trap, Trap.OVERFLOW, symbols, "wrong PC"), "wrong trap PC")
    for wrong in [signal.SIGFPE, signal.SIGSEGV, signal.SIGABRT]:
        result = Observation(b"", terminal_signal=wrong, delivery_signal=wrong,
                             pc=4096, instruction=UD2, signal_code=2)
        rejected(lambda: validate_trap(result, Trap.ZERO, symbols, "wrong signal"), f"signal {wrong}")
    for result in [
        Observation(b"", terminal_signal=signal.SIGILL, delivery_signal=signal.SIGFPE,
                    pc=4096, instruction=UD2, signal_code=2),
        Observation(b"", terminal_signal=signal.SIGILL, delivery_signal=signal.SIGILL,
                    pc=4096, instruction=0x9090, signal_code=2),
        Observation(b"", terminal_signal=signal.SIGILL, delivery_signal=signal.SIGILL,
                    pc=4096, instruction=UD2, signal_code=0),
    ]:
        rejected(lambda: validate_trap(result, Trap.ZERO, symbols, "bad trap metadata"), "bad trap metadata")

    def native(code):
        return runner.assemble('.text\n.globl test\ntest:\n' + code +
                               '\n.section .note.GNU-stack,"",@progbits\n', ["test"])

    observed, _ = native("movabsq $-9223372036854775808, %rax\nret")
    validate_values(observed, [MIN], ["native full-width value"])
    rejected(lambda: validate_values(observed, [0], ["native wrong value"]), "native wrong value")
    observed, symbols = native(".Laurora_division_zero_trap:\nud2\n.Laurora_overflow_trap:\nud2")
    validate_trap(observed, Trap.ZERO, symbols, "native exact UD2")
    rejected(lambda: validate_trap(observed, Trap.OVERFLOW, symbols, "native wrong site"), "native wrong site")
    observed, symbols = native("xorq %rdx, %rdx\nxorq %rax, %rax\nxorq %rcx, %rcx\n"
                               "idivq %rcx\n.Laurora_division_zero_trap:\nud2")
    require(observed.terminal_signal == signal.SIGFPE, "native SIGFPE self-test did not execute")
    rejected(lambda: validate_trap(observed, Trap.ZERO, symbols, "native SIGFPE"), "native hardware divide fault")
    print("PASS integer oracle self-tests: full-width output, wrong values, wrong signals, exact UD2 sites", flush=True)


def operand_pairs(seed, count):
    # Cartesian signs/boundaries plus exact square/product and long-Euclid cases.
    edges = [MIN, MIN + 1, -3037000500, -17, -2, -1, 0, 1, 2, 17, 3037000499, MAX - 1, MAX]
    pairs = set((a, b) for a in edges for b in edges)
    for a, b in [(3037000499, 3037000500), (3037000500, 3037000500),
                 (1 << 62, 2), (MAX, 3), (MIN, 1 << 62),
                 (7540113804746346429, 4660046610375530309),
                 (MAX, MAX // 2), (MIN + 1, MAX)]:
        for left_sign in (-1, 1):
            for right_sign in (-1, 1):
                left, right = a * left_sign, b * right_sign
                if MIN <= left <= MAX and MIN <= right <= MAX:
                    pairs.add((left, right))
                    pairs.add((right, left))
    random_source = random.Random(seed)
    for index in range(count):
        if index % 4 == 0:
            a, b = [random_source.randrange(MIN, MAX + 1) for _ in range(2)]
        elif index % 4 == 1:
            a, b = random_source.randrange(MIN, MAX + 1), random_source.randrange(-1000, 1001)
        elif index % 4 == 2:
            a, b = [random_source.randrange(-10**9, 10**9 + 1) for _ in range(2)]
        else:
            a = random_source.choice([MIN, MAX])
            a += random_source.randrange(256) * (1 if a == MIN else -1)
            b = random_source.choice(edges)
        pairs.add((a, b))
    return sorted(pairs)


def generated_cases(seed, count):
    for a, b in operand_pairs(seed, count):
        for operator, oracle in [("/", division), ("%", remainder)]:
            yield Case(f"operator {a} {operator} {b}", f"return ({a}){operator}({b});", oracle(a, b))
        for name, oracle in [("gcd", gcd), ("lcm", lcm)]:
            yield Case(f"std::{name}({a},{b})", f"return std::{name}({a},{b});",
                       oracle(a, b), library=True)
        for accessor in ["quot", "rem"]:
            expected = division(a, b)
            if not isinstance(expected, Trap) and accessor == "rem":
                expected = remainder(a, b)
            yield Case(f"std::div({a},{b}).{accessor}",
                       f"const std::DivResult result=std::div({a},{b});return result.{accessor}();",
                       expected, library=True)

    for expression, expected in [
        ("20/3*2", 12), ("20*3/2%7", 2), ("2+21/4*3", 17),
        ("-17%5*-3", 6), ("-17/5*3+2", -7), ("20/3/2", 3),
        ("20%6%3", 2), ("20/(3*2)", 3), ("(7/3)+(7%3)", 3),
        ("7/-3", -2), ("7%-3", 1),
        (f"{MAX}+1", Trap.OVERFLOW), (f"({MIN})-1", Trap.OVERFLOW),
        (f"{MAX}*2", Trap.OVERFLOW), (f"-({MIN})", Trap.OVERFLOW),
        (f"({MAX}+1)/0", Trap.OVERFLOW), (f"(1/0)/({MAX}+1)", Trap.ZERO),
        (f"({MIN})/-1/0", Trap.OVERFLOW), (f"({MIN})%-1/0", Trap.ZERO),
        (f"({MIN})/-1%0", Trap.OVERFLOW), ("0*(1/0)", Trap.ZERO),
        ("0*(1%0)", Trap.ZERO), ("(1%0)/0", Trap.ZERO),
    ]:
        yield Case("precedence/trap order " + expression, "return " + expression + ";", expected)

    trace = ("class Trace{i64 value;public:Trace():value(0){}"
             "auto next()->i64{value=value+1;return value;}"
             "auto get()const->i64{return value;}};")
    for expression, expected in [("t.next()/t.next()", 2), ("t.next()%t.next()", 102),
                                  ("20/t.next()/t.next()", 1002),
                                  ("t.next()*t.next()/t.next()%t.next()", 4)]:
        yield Case("left-to-right once " + expression,
                   f"Trace t=Trace();i64 value={expression};return value*100+t.get();",
                   expected, prelude=trace)
    yield Case("nested calls preserve dividend", "return id(-87)/id(9)+id(-87)%id(9);", -15,
               prelude="auto id(i64 x)->i64{return x;}")
    yield Case("receiver survives checked division", "Cell c=Cell(-17);return c.result();", -5,
               prelude="class Cell{i64 n;public:Cell(i64 x):n(x){}auto result()const->i64{return n/5+n%5;}};")
    yield Case("DivResult independent copies and class boundary",
               "const std::DivResult a=std::div(-17,5);std::DivResult b=a;"
               "std::DivResult c=copy(b);return a.quot()+b.rem()+c.quot()+c.rem();", -10,
               prelude="auto copy(std::DivResult x)->std::DivResult{return x;}", library=True)
    yield Case("DivResult remains alive across subsequent call",
               f"std::DivResult a=std::div({MIN},3);std::DivResult b=std::div({MAX},2);"
               "return a.rem()+b.rem();", -1, library=True)
    yield Case("DivResult loop local", "i64 n=0;i64 sum=0;while(n<7){"
               "const std::DivResult d=std::div(n,3);sum=sum+d.quot()+d.rem();n=n+1;}return sum;",
               11, library=True)
    for function in ["gcd", "lcm"]:
        yield Case(function + " arguments evaluated before zero shortcut",
                   f"return std::{function}(0,{MAX}+1);", Trap.OVERFLOW, library=True)


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=7043)
    parser.add_argument("--random-count", type=int, default=32)
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    require(0 <= args.random_count <= 10000, "random-count must be between 0 and 10000")
    require(args.timeout > 0, "timeout must be positive")
    if not args.self_test_only:
        compiler = args.compiler.resolve()
        print(f"INFO integer oracle compiler={compiler} "
              f"sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
        integer_module = ROOT / "library/std/integer.au"
        print(f"INFO integer oracle std.integer sha256="
              f"{hashlib.sha256(integer_module.read_bytes()).hexdigest()}", flush=True)
    with tempfile.TemporaryDirectory(prefix="aurora-integer-oracle-") as temporary:
        runner = NativeRunner(Path(temporary), args.compiler.resolve(), args.timeout)
        self_tests(runner)
        if args.self_test_only:
            return
        cases = list(generated_cases(args.seed, args.random_count))
        values = [case for case in cases if not isinstance(case.expected, Trap) and not case.prelude]
        singletons = [case for case in cases if isinstance(case.expected, Trap) or case.prelude]
        # Batching independent successful functions keeps the default gate quick;
        # every trapping function still gets its own executable and exact PC check.
        for start in range(0, len(values), 32):
            runner.cases(values[start:start + 32])
        for case in singletons:
            runner.cases([case])
        traps = sum(isinstance(case.expected, Trap) for case in cases)
        print(f"PASS integer oracle: {len(cases)} native cases, {traps} exact-site traps; "
              f"seed={args.seed}, random-count={args.random_count}; "
              f"elapsed={time.monotonic() - started:.2f}s")


if __name__ == "__main__":
    main()
