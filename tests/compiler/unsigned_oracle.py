#!/usr/bin/env python3
"""Independent bounded native mathematical oracle for u64 and std.bit.

Python integers are unbounded: arithmetic is checked for representability only
after computing its mathematical result. Only complement uses a 64-bit mask;
overflowing arithmetic and shifts never silently wrap. Counts are signed i64,
and invalid counts are distinct from arithmetic overflow and division by zero.

Generated Aurora functions execute as Linux/x86-64 machine code. A freestanding
syscall bridge returns all eight bytes, decoded according to each result type.
The existing integer_signal.cpp host adapter records the signal, instruction
pointer, and instruction bytes before restoring the actual terminating fault.
Trap checks require actual SIGILL at the exact retained, named UD2 instruction;
hardware divide faults, generic failures, and timeouts never count as success.

Run: python3 tests/compiler/unsigned_oracle.py build/aurorac
Optional deterministic stress: --seed 8008 --random-count 200
Use --self-test-only to validate the harness without a compiler implementation.
This is bounded test evidence, not a language-equivalence or safety proof.
"""

from __future__ import annotations

import re
import argparse
from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import os
from pathlib import Path
import random
import resource
import shlex
import signal
import struct
import subprocess
import sys
import tempfile
import time


MAX = (1 << 64) - 1
SIGNED_MIN = -(1 << 63)
SIGNED_MAX = (1 << 63) - 1
ROOT = Path(__file__).resolve().parents[2]
UD2 = 0x0B0F


class Trap(Enum):
    ZERO = ".Laurora_division_zero_trap"
    OVERFLOW = ".Laurora_overflow_trap"
    COUNT = ".Laurora_shift_count_trap"


@dataclass(frozen=True)
class Case:
    name: str
    body: str
    expected: int | Trap
    result_type: str = "u64"
    prelude: str = ""
    imports: tuple[str, ...] = ()


@dataclass(frozen=True)
class Rejection:
    name: str
    source: str


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
    return value if 0 <= value <= MAX else Trap.OVERFLOW


def signed(value):
    return value if SIGNED_MIN <= value <= SIGNED_MAX else Trap.OVERFLOW


def division(a, b):
    return Trap.ZERO if b == 0 else a // b


def remainder(a, b):
    return Trap.ZERO if b == 0 else a % b


def left_shift(value, count):
    if not 0 <= count < 64:
        return Trap.COUNT
    return representable(value * (2**count))


def right_shift(value, count):
    if not 0 <= count < 64:
        return Trap.COUNT
    return value // (2**count)


def complement(value):
    return (~value) & MAX


def validate_values(observed, cases):
    names = [case.name for case in cases]
    require(
        observed.exit_code == 0 and observed.terminal_signal is None,
        f"{names}: expected normal return, observed {observed}",
    )
    require(
        len(observed.output) == len(cases) * 8,
        f"{names}: expected {len(cases) * 8} result bytes, got {len(observed.output)}",
    )
    for index, case in enumerate(cases):
        require(case.result_type in ("u64", "i64", "bool"), "unknown oracle result type")
        actual = int.from_bytes(
            observed.output[index * 8 : (index + 1) * 8], "little", signed=case.result_type == "i64"
        )
        require(actual == case.expected, f"{case.name}: expected {case.expected}, got {actual} ({case.result_type})")


def validate_trap(observed, expected, symbols, name):
    require(expected.value in symbols, f"{name}: missing named trap {expected.value}")
    require(
        observed.exit_code is None
        and observed.terminal_signal == signal.SIGILL
        and observed.delivery_signal == signal.SIGILL,
        f"{name}: expected actual SIGILL termination, observed {observed}",
    )
    require(not observed.output, f"{name}: trap unexpectedly returned scalar bytes")
    require(
        observed.pc == symbols[expected.value],
        f"{name}: wrong trap PC {observed.pc!r}; expected {expected.value} at {symbols[expected.value]:#x}",
    )
    require(observed.instruction == UD2, f"{name}: trap instruction is not UD2")
    require(
        observed.signal_code is not None and observed.signal_code > 0,
        f"{name}: SIGILL was not a kernel-generated instruction fault",
    )


def command(args, timeout=5, allow_signal=False, allow_rejection=False):
    try:
        result = subprocess.run(
            [str(arg) for arg in args],
            capture_output=True,
            timeout=timeout,
            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"timeout is a failure, not a trap: {args}") from error
    require(
        result.returncode == 0
        or (allow_signal and result.returncode < 0)
        or (allow_rejection and result.returncode == 1),
        f"command failed ({result.returncode}): {args}\n{result.stderr.decode(errors='replace')}",
    )
    return result


def entry(functions):
    # Each write exposes the entire returned scalar, never only an exit status.
    # Pop the result after writing so every call retains the same ABI alignment.
    instructions = [
        ".text",
        ".globl _start",
        "_start:",
        "    call aurora_install_integer_signal_observer",
        "    testq %rax, %rax",
        "    jz .Lobserver_installed",
        "    movq $60, %rax",
        "    movq $125, %rdi",
        "    syscall",
        ".Lobserver_installed:",
    ]
    for function in functions:
        instructions.extend(
            [
                f"    call {function}",
                "    pushq %rax",
                "    movq $1, %rax",
                "    movq $1, %rdi",
                "    movq %rsp, %rsi",
                "    movq $8, %rdx",
                "    syscall",
                "    addq $8, %rsp",
            ]
        )
    instructions.extend(
        [
            "    movq $60, %rax",
            "    xorq %rdi, %rdi",
            "    syscall",
            '.section .note.GNU-stack,"",@progbits',
            "",
        ]
    )
    return "\n".join(instructions)


class NativeRunner:
    def __init__(self, directory, compiler, timeout):
        self.directory = directory
        self.compiler = compiler
        self.timeout = timeout
        self.observer = directory / "integer_signal.o"
        command(
            shlex.split(os.environ.get("CXX", "c++"))
            + [
                "-std=c++23",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-c",
                "-ffreestanding",
                "-fno-stack-protector",
                "-fno-exceptions",
                "-fno-rtti",
                "-fno-asynchronous-unwind-tables",
                "-fno-pie",
                ROOT / "tests/compiler/integer_signal.cpp",
                "-o",
                self.observer,
            ],
            timeout=30,
        )

    def assemble(self, assembly, functions):
        program = self.directory / "program.s"
        program.write_text(assembly)
        (self.directory / "entry.s").write_text(entry(functions))
        # -L retains compiler-local trap labels for exact instruction attribution.
        command(["as", "--64", "-L", program, "-o", self.directory / "program.o"])
        command(["as", "--64", self.directory / "entry.s", "-o", self.directory / "entry.o"])
        binary = self.directory / "program"
        command(["ld", "-o", binary, self.directory / "entry.o", self.directory / "program.o", self.observer])
        symbols = {}
        for line in command(["nm", "--defined-only", "--numeric-sort", binary]).stdout.decode().splitlines():
            fields = line.split()
            if len(fields) == 3:
                symbols[fields[2]] = int(fields[0], 16)
        result = command([binary], timeout=self.timeout, allow_signal=True)
        if result.returncode == 0:
            require(not result.stderr, "normal return unexpectedly reported a fault")
            return Observation(result.stdout, exit_code=0), symbols
        require(
            len(result.stderr) == 40, f"signal {result.returncode} without one complete fault record: {result.stderr!r}"
        )
        identity, delivered, pc, instruction, code = struct.unpack("<QQQQq", result.stderr)
        require(identity == 0x4155524F52414654, "malformed native fault record identity")
        return Observation(
            result.stdout,
            terminal_signal=-result.returncode,
            delivery_signal=delivered,
            pc=pc,
            instruction=instruction,
            signal_code=code,
        ), symbols

    def cases(self, cases):
        require(
            cases and (len(cases) == 1 or all(not c.prelude for c in cases)),
            "only independent scalar cases may be batched",
        )
        require(
            all(not isinstance(c.expected, Trap) for c in cases) or len(cases) == 1, "trap batch would hide later cases"
        )
        source = "module test;\n"
        for module in sorted({module for case in cases for module in case.imports}):
            source += f"import {module};\n"
        functions = []
        for index, case in enumerate(cases):
            function = f"oracle_{index}"
            functions.append(function)
            source += case.prelude + f"\nauto {function}()->{case.result_type}{{{case.body}}}\n"
        input_path = self.directory / "input.au"
        input_path.write_text(source)
        output = self.directory / "compiled.s"
        output.unlink(missing_ok=True)
        try:
            command([self.compiler, "--module-root", ROOT / "library", input_path, "-o", output], timeout=self.timeout)
            require(input_path.read_text() == source, "compiler modified its input")
            observed, symbols = self.assemble(output.read_text(), functions)
            if isinstance(cases[0].expected, Trap):
                validate_trap(observed, cases[0].expected, symbols, cases[0].name)
            else:
                validate_values(observed, cases)
        except AssertionError as error:
            raise AssertionError(f"{error}\nReproduction source:\n{source}") from error

    def rejection(self, case):
        input_path = self.directory / "invalid.au"
        input_path.write_text(case.source)
        output = self.directory / "rejected.s"
        # Exercise both absent and already-present artifacts. A rejection must
        # neither publish assembly nor damage an existing user-owned output.
        sentinel = b"unsigned oracle existing output\n"
        for existing in (False, True):
            output.unlink(missing_ok=True)
            if existing:
                output.write_bytes(sentinel)
            result = command(
                [self.compiler, "--module-root", ROOT / "library", input_path, "-o", output],
                timeout=self.timeout,
                allow_rejection=True,
            )
            require(
                result.returncode == 1
                and re.fullmatch(
                    rf"(?:{re.escape(str(input_path))}:[1-9][0-9]*:[1-9][0-9]*|aurorac): error "
                    r"AU(?:100[12]|200[123]|3001|4001): [^\n]+\n",
                    result.stderr.decode(errors="strict"),
                )
                is not None,
                f"{case.name}: expected normal compiler rejection, got {result.returncode}: "
                f"{result.stderr!r}\nReproduction source:\n{case.source}",
            )
            require(input_path.read_text() == case.source, f"{case.name}: compiler modified input")
            if existing:
                require(output.read_bytes() == sentinel, f"{case.name}: rejection changed output")
            else:
                require(not output.exists(), f"{case.name}: rejection created an artifact")


def rejected(check, label):
    try:
        check()
    except AssertionError:
        return
    raise AssertionError(f"harness self-test accepted {label}")


def self_tests(runner):
    for a in range(25):
        for b in range(1, 25):
            q, r = division(a, b), remainder(a, b)
            require(a == q * b + r and 0 <= r < b, "bad reference division identity")
    require(
        representable(MAX) == MAX and representable(MAX + 1) is Trap.OVERFLOW and representable(-1) is Trap.OVERFLOW,
        "bad unsigned representability",
    )
    require(signed(SIGNED_MAX) == SIGNED_MAX and signed(1 << 63) is Trap.OVERFLOW, "bad signed conversion reference")
    require(
        division(MAX, 2) == SIGNED_MAX
        and remainder(MAX, 2) == 1
        and division(MAX, 0) is Trap.ZERO
        and remainder(0, 0) is Trap.ZERO,
        "bad full-width division reference",
    )
    require(
        left_shift(1, 63) == 1 << 63
        and left_shift(2, 63) is Trap.OVERFLOW
        and right_shift(MAX, 63) == 1
        and left_shift(0, 64) is Trap.COUNT
        and right_shift(0, -1) is Trap.COUNT,
        "bad shift reference",
    )
    require(
        complement(0) == MAX and complement(MAX) == 0 and complement(1 << 63) == SIGNED_MAX, "bad complement reference"
    )

    scalar = Observation(MAX.to_bytes(8, "little"), exit_code=0)
    validate_values(scalar, [Case("correct unsigned scalar", "", MAX)])
    validate_values(scalar, [Case("correct signed scalar", "", -1, "i64")])
    rejected(lambda: validate_values(scalar, [Case("wrong value", "", MAX - 1)]), "wrong value")
    rejected(lambda: validate_values(scalar, [Case("wrong signedness", "", -1)]), "wrong signedness")
    rejected(lambda: validate_values(Observation(b"*", exit_code=0), [Case("short", "", 42)]), "short output")
    rejected(
        lambda: validate_values(
            Observation((2).to_bytes(8, "little"), exit_code=0), [Case("noncanonical bool", "", 1, "bool")]
        ),
        "noncanonical bool",
    )
    symbols = {Trap.ZERO.value: 4096, Trap.OVERFLOW.value: 8192, Trap.COUNT.value: 12288}
    trap = Observation(
        b"", terminal_signal=signal.SIGILL, delivery_signal=signal.SIGILL, pc=4096, instruction=UD2, signal_code=2
    )
    validate_trap(trap, Trap.ZERO, symbols, "correct synthetic trap")
    for expected in (Trap.OVERFLOW, Trap.COUNT):
        rejected(lambda: validate_trap(trap, expected, symbols, "wrong PC"), "wrong trap PC")
    for wrong in (signal.SIGFPE, signal.SIGSEGV, signal.SIGABRT):
        result = replace(trap, terminal_signal=wrong, delivery_signal=wrong)
        rejected(lambda: validate_trap(result, Trap.ZERO, symbols, "wrong signal"), f"signal {wrong}")
    for result in (
        replace(trap, delivery_signal=signal.SIGFPE),
        replace(trap, instruction=0x9090),
        replace(trap, signal_code=0),
        replace(trap, output=b"returned"),
        replace(trap, exit_code=1),
    ):
        rejected(lambda: validate_trap(result, Trap.ZERO, symbols, "bad metadata"), "bad trap metadata")
    rejected(lambda: validate_trap(trap, Trap.ZERO, {}, "missing symbol"), "missing trap symbol")

    def native(code):
        return runner.assemble(
            ".text\n.globl test\ntest:\n" + code + '\n.section .note.GNU-stack,"",@progbits\n', ["test"]
        )

    observed, _ = native(f"movabsq ${MAX}, %rax\nret")
    validate_values(observed, [Case("native unsigned maximum", "", MAX)])
    rejected(lambda: validate_values(observed, [Case("native wrong value", "", 0)]), "native wrong value")
    observed, _ = native(f"movabsq ${SIGNED_MIN}, %rax\nret")
    validate_values(observed, [Case("native signed minimum", "", SIGNED_MIN, "i64")])
    for expected in Trap:
        sites = "\n".join(label.value + ":\nud2" for label in Trap)
        observed, symbols = native(f"jmp {expected.value}\n" + sites)
        validate_trap(observed, expected, symbols, "native exact UD2")
        for wrong in Trap:
            if wrong is not expected:
                rejected(lambda: validate_trap(observed, wrong, symbols, "native wrong site"), "native wrong trap site")
    for setup in ("xorq %rdx, %rdx\nxorq %rcx, %rcx", "movq $1, %rdx\nmovq $1, %rcx"):
        observed, symbols = native("xorq %rax, %rax\n" + setup + "\ndivq %rcx\n.Laurora_division_zero_trap:\nud2")
        require(observed.terminal_signal == signal.SIGFPE, "native #DE self-test did not execute")
        rejected(lambda: validate_trap(observed, Trap.ZERO, symbols, "native #DE"), "hardware divide fault")
    rejected(lambda: command([sys.executable, "-c", "while True: pass"], timeout=0.05), "timeout")
    print(
        "PASS unsigned oracle self-tests: full-width u64/i64, wrong values/signals, "
        "three exact UD2 sites, hardware #DE and timeout rejection",
        flush=True,
    )


def operand_pairs(seed, count):
    edges = [0, 1, 2, 3, 17, (1 << 32) - 1, 1 << 32, SIGNED_MAX, 1 << 63, (1 << 63) + 1, MAX - 1, MAX]
    pairs = {(a, b) for a in edges for b in edges}
    # Exact multiplication boundary and nontrivial high-bit quotient/remainders.
    pairs.update(
        [(4294967295, 4294967297), (4294967296, 4294967296), (MAX, 3), (MAX, 7), (MAX, 1 << 63), (MAX - 3, MAX - 2)]
    )
    random_source = random.Random(seed)
    for index in range(count):
        if index % 4 == 0:
            a, b = [random_source.randrange(MAX + 1) for _ in range(2)]
        elif index % 4 == 1:
            a, b = random_source.randrange(MAX + 1), random_source.randrange(1001)
        elif index % 4 == 2:
            a, b = [random_source.randrange(1 << 32) for _ in range(2)]
        else:
            a, b = MAX - random_source.randrange(256), random_source.choice(edges)
        pairs.add((a, b))
    return sorted(pairs)


def generated_cases(seed, count):
    pairs = operand_pairs(seed, count)
    binary = [
        ("+", lambda a, b: representable(a + b)),
        ("-", lambda a, b: representable(a - b)),
        ("*", lambda a, b: representable(a * b)),
        ("/", division),
        ("%", remainder),
        ("&", lambda a, b: a & b),
        ("|", lambda a, b: a | b),
        ("^", lambda a, b: a ^ b),
    ]
    comparisons = [
        ("<", lambda a, b: a < b),
        ("<=", lambda a, b: a <= b),
        (">", lambda a, b: a > b),
        (">=", lambda a, b: a >= b),
        ("==", lambda a, b: a == b),
        ("!=", lambda a, b: a != b),
    ]
    for a, b in pairs:
        for operator, oracle in binary:
            expression = f"{a}u64 {operator} {b}u64"
            yield Case("operator " + expression, "return " + expression + ";", oracle(a, b))
        for operator, oracle in comparisons:
            expression = f"{a}u64 {operator} {b}u64"
            yield Case("unsigned comparison " + expression, "return " + expression + ";", int(oracle(a, b)), "bool")

    values = sorted(
        {value for pair in pairs for value in pair}
        | {1 << bit for bit in range(64)}
        | {(1 << bit) - 1 for bit in range(65)}
    )
    for value in values:
        yield Case(f"literal {value}", f"return {value}u64;", value)
        yield Case(f"complement {value}", f"return ~{value}u64;", complement(value))
        yield Case(f"double complement {value}", f"return ~~{value}u64;", value)
        for name, expected, kind in [
            ("popcount", value.bit_count(), "i64"),
            ("bit_width", value.bit_length(), "i64"),
            ("has_single_bit", int(value != 0 and value.bit_count() == 1), "bool"),
        ]:
            yield Case(
                f"std::{name}({value})", f"return std::{name}({value}u64);", expected, kind, imports=("std.bit",)
            )

    shift_values = [0, 1, 2, 3, (1 << 32) - 1, 1 << 32, SIGNED_MAX, 1 << 63, MAX - 1, MAX]
    counts = [SIGNED_MIN, -65, -1, 0, 1, 2, 31, 32, 62, 63, 64, 65, SIGNED_MAX]
    shift_pairs = {(value, amount) for value in shift_values for amount in counts}
    random_source = random.Random(seed ^ 0xB17)
    for index in range(count):
        value = random_source.randrange(MAX + 1)
        amount = random_source.randrange(64) if index % 2 else random_source.randrange(-4, 68)
        shift_pairs.add((value, amount))
    for value, amount in sorted(shift_pairs):
        for operator, oracle in [("<<", left_shift), (">>", right_shift)]:
            expression = f"{value}u64 {operator} ({amount})"
            yield Case("checked shift " + expression, "return " + expression + ";", oracle(value, amount))
    # Every valid count, including the high-bit count 63, has a successful case.
    for amount in range(64):
        yield Case(f"unit shift {amount}", f"return 1u64 << {amount};", 1 << amount)
        yield Case(f"logical shift {amount}", f"return {MAX}u64 >> {amount};", MAX // (2**amount))

    for value in [SIGNED_MIN, SIGNED_MIN + 1, -1, 0, 1, 2, SIGNED_MAX - 1, SIGNED_MAX]:
        yield Case(f"i64 to u64 {value}", f"return u64({value});", representable(value))
    for value in [0, 1, 2, SIGNED_MAX - 1, SIGNED_MAX, 1 << 63, (1 << 63) + 1, MAX - 1, MAX]:
        yield Case(f"u64 to i64 {value}", f"return i64({value}u64);", signed(value), "i64")
    for _ in range(count):
        value = random_source.randrange(MAX + 1)
        yield Case(f"random u64 conversion {value}", f"return i64({value}u64);", signed(value), "i64")
        value = random_source.randrange(SIGNED_MIN, SIGNED_MAX + 1)
        yield Case(f"random i64 conversion {value}", f"return u64({value});", representable(value))

    for expression, expected in [
        ("2u64+21u64/4u64*3u64", 17),
        ("20u64/3u64/2u64", 3),
        ("20u64%6u64%3u64", 2),
        ("1u64+2u64<<3", 24),
        ("32u64>>1+2", 4),
        ("1u64<<1<<2", 8),
        ("128u64>>2>>1", 16),
        ("8u64|6u64^3u64&1u64", 15),
        ("~0u64^1u64", MAX - 1),
        ("1u64<<3|2u64", 10),
        ("8u64>>1&3u64", 0),
        (f"({MAX}u64+1u64)/0u64", Trap.OVERFLOW),
        (f"(1u64/0u64)+({MAX}u64+1u64)", Trap.ZERO),
        ("0u64*(1u64/0u64)", Trap.ZERO),
        ("0u64&(1u64%0u64)", Trap.ZERO),
        ("0u64<<64", Trap.COUNT),
        ("0u64>>64", Trap.COUNT),
        (f"({MAX}u64+1u64)<<64", Trap.OVERFLOW),
        (f"0u64<<({SIGNED_MAX}+1)", Trap.OVERFLOW),
        ("(1u64<<64)/0u64", Trap.COUNT),
        ("(1u64/0u64)<<64", Trap.ZERO),
        ("(1u64<<64)<<(0-1)", Trap.COUNT),
        ("u64(-1)<<64", Trap.OVERFLOW),
        ("u64(i64(9223372036854775808u64))", Trap.OVERFLOW),
        ("u64(i64(9223372036854775807u64))", SIGNED_MAX),
    ]:
        yield Case("precedence/trap order " + expression, "return " + expression + ";", expected)

    trace = (
        "class Trace{u64 n;public:Trace():n(0u64){}"
        "auto next()->u64{n=n+1u64;return n;}"
        "auto count()->i64{n=n+1u64;return i64(n);}"
        "auto get()const->u64{return n;}};"
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
            f"Trace t=Trace();u64 value={expression};return value*100u64+t.get();",
            expected,
            prelude=trace,
        )
    yield Case(
        "nested calls preserve unsigned dividend",
        f"return id({MAX}u64)/id(3u64)+id({MAX}u64)%id(3u64);",
        MAX // 3,
        prelude="auto id(u64 value)->u64{return value;}",
    )
    yield Case(
        "receiver survives unsigned division",
        f"Cell c=Cell({MAX}u64);return c.result();",
        MAX // 5,
        prelude="class Cell{u64 n;public:Cell(u64 x):n(x){}auto result()const->u64{return n/5u64+n%5u64;}};",
    )
    yield Case(
        "u64 class copied through function",
        f"const Cell a=Cell({MAX}u64);Cell b=copy(a);return b.get();",
        MAX,
        prelude="class Cell{u64 n;public:Cell(u64 x):n(x){}auto get()const->u64{return n;}};"
        "auto copy(Cell x)->Cell{return x;}",
    )
    yield Case(
        "u64 array independent copy and checked access",
        f"array<u64,2> a={{0u64,{MAX}u64}};const array<u64,2> b=a;a[1]=1u64;return b[len(b)-1]-a[1];",
        MAX - 1,
    )
    yield Case(
        "library argument evaluated before call",
        f"return std::popcount({MAX}u64+1u64);",
        Trap.OVERFLOW,
        "i64",
        imports=("std.bit",),
    )
    yield Case(
        "bit and integer modules coexist",
        f"return std::popcount({MAX}u64)+std::gcd(-84,30);",
        70,
        "i64",
        imports=("std.bit", "std.integer"),
    )


def rejection_cases():
    def app(body, result_type="u64", prelude="", imports=""):
        return f"module test;{imports}{prelude}auto test()->{result_type}{{{body}}}"

    for literal in (
        "18446744073709551616u64",
        "999999999999999999999999999999999999u64",
        "18446744073709551615",
        "1u",
        "1u65",
        "1U64",
        "1u64u64",
    ):
        result_type = "i64" if literal.isdecimal() else "u64"
        yield Rejection("invalid literal " + literal, app("return " + literal + ";", result_type))
    for expression in (
        "-0u64",
        "-1u64",
        "-18446744073709551615u64",
        "~1",
        "~true",
        "1u64<<1u64",
        "1u64>>1u64",
        "1<<1",
        "1>>1",
        "1u64<<true",
        "1u64>>false",
        "u64(1u64)",
        "i64(1)",
        "u64(true)",
        "i64(false)",
        "u64()",
        "i64()",
        "u64(1,2)",
        "i64(1u64,2u64)",
    ):
        # Match the otherwise-natural result type so an unrelated return type
        # error cannot conceal incorrect acceptance of the forbidden operation.
        result_type = "u64"
        if expression.startswith("i64(") or expression in ("~1", "1<<1", "1>>1"):
            result_type = "i64"
        elif expression == "~true":
            result_type = "bool"
        yield Rejection("forbidden expression " + expression, app("return " + expression + ";", result_type))
    for operator in ("+", "-", "*", "/", "%", "&", "|", "^", "<", "<=", ">", ">=", "==", "!="):
        for left, right in (("1u64", "1"), ("1", "1u64")):
            expression = left + operator + right
            result_type = "bool" if operator in ("<", "<=", ">", ">=", "==", "!=") else "u64"
            yield Rejection("mixed signedness " + expression, app("return " + expression + ";", result_type))
    for source in [
        app("u64 value=1;return value;"),
        app("i64 value=1u64;return 0u64;"),
        app("return 1;"),
        app("return 1u64;", "i64"),
        app("return take(1);", prelude="auto take(u64 n)->u64{return n;}"),
        app("return 0u64;", prelude="auto take(i64 n)->i64{return n;}auto bad()->i64{return take(1u64);}"),
        app("array<u64,1> a={1};return a[0];"),
        app("array<u64,1> a={1u64};return a[0u64];"),
        app("u64 n=0u64;n=1;return n;"),
        app("const u64 n=0u64;n=1u64;return n;"),
        app("return std::popcount(1);", "i64", imports="import std.bit;"),
        app("return std::bit_width(true);", "i64", imports="import std.bit;"),
        app("return std::has_single_bit(1);", "bool", imports="import std.bit;"),
    ]:
        yield Rejection("type boundary " + source, source)


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path, nargs="?", default=ROOT / "build/aurorac")
    parser.add_argument("--seed", type=int, default=8008)
    parser.add_argument("--random-count", type=int, default=32)
    parser.add_argument("--self-test-only", action="store_true")
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args()
    require(0 <= args.random_count <= 10000, "random-count must be between 0 and 10000")
    require(args.timeout > 0, "timeout must be positive")
    if not args.self_test_only:
        compiler = args.compiler.resolve()
        print(
            f"INFO unsigned oracle compiler={compiler} sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}",
            flush=True,
        )
        for module in ("bit", "integer"):
            module_path = ROOT / f"library/std/{module}.au"
            print(
                f"INFO unsigned oracle std.{module} sha256={hashlib.sha256(module_path.read_bytes()).hexdigest()}",
                flush=True,
            )
    with tempfile.TemporaryDirectory(prefix="aurora-unsigned-oracle-") as temporary:
        runner = NativeRunner(Path(temporary), args.compiler.resolve(), args.timeout)
        self_tests(runner)
        if args.self_test_only:
            return
        cases = list(generated_cases(args.seed, args.random_count))
        values = [case for case in cases if not isinstance(case.expected, Trap) and not case.prelude]
        singletons = [case for case in cases if isinstance(case.expected, Trap) or case.prelude]
        for start in range(0, len(values), 32):
            runner.cases(values[start : start + 32])
        for case in singletons:
            runner.cases([case])
        negatives = list(rejection_cases())
        for case in negatives:
            runner.rejection(case)
        traps = sum(isinstance(case.expected, Trap) for case in cases)
        print(
            f"PASS unsigned oracle: {len(cases)} native cases, {traps} exact-site traps, "
            f"{len(negatives)} rejection cases with absent/existing output checks; "
            f"seed={args.seed}, random-count={args.random_count}; "
            f"elapsed={time.monotonic() - started:.2f}s"
        )


if __name__ == "__main__":
    main()
