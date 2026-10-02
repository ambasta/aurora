#!/usr/bin/env python3
"""Compare a saved baseline with a candidate on deterministic source and machine outcomes.

This bounded differential test is not a semantics oracle or equivalence proof. It is
separate from tests/semantics, which independently predicts program behavior.
"""
from pathlib import Path
import argparse
import random
import resource
import signal
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("baseline", type=Path)
parser.add_argument("candidate", type=Path)
args = parser.parse_args()
compilers = [args.baseline.resolve(), args.candidate.resolve()]


def run(command):
    return subprocess.run(
        [str(value) for value in command], capture_output=True, timeout=5,
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
    )


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


bridge = """.text
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
"""
random.seed(7042)
cases = []
for _ in range(32):
    a, b, c, d = [random.randrange(-10000, 10000) for _ in range(4)]
    cases.append((f"return ({a} + {b}) * ({c} - {d});", "return"))
for length in range(1, 17):
    values = [random.randrange(-1000, 1000) for _ in range(length)]
    initializer = ",".join(map(str, values))
    cases.append((
        f"array<i64,{length}> a={{{initializer}}}; const array<i64,{length}> b=a; "
        "i64 i=0; i64 sum=0; while(i<len(a)){a[i]=a[i]+1;sum=sum+b[i];i=i+1;}return sum;",
        "return",
    ))
for expression in ["9223372036854775807+1", "-(-9223372036854775808)",
                   "(-9223372036854775808)-1", "9223372036854775807*2"]:
    cases.append((f"return {expression};", "trap"))
for index in ["-1", "3", "9223372036854775807", "-9223372036854775808"]:
    cases.append((f"array<i64,3> a={{1,2,3}}; return a[{index}];", "trap"))
for source in [
    "const i64 x=1;x=2;return x;",
    "own<i64> a=own(42);own<i64> b=move(a);return read(a);",
    "const own<i64> a=own(42);mutref<i64> r=borrow_mut(a);return 0;",
    "own<i64> a=own(42);while(false){own<i64> b=move(a);}return 0;",
    "array<i64,2> a={1};return 0;",
    "array<i64,2> a={1,2};return a[true];",
    "const array<bool,1> a={1};return 0;",
    "while(true){return 42;}",
]:
    cases.append((source, "reject"))

with tempfile.TemporaryDirectory(prefix="aurora-equivalence-") as directory:
    root = Path(directory)
    (root / "entry.s").write_text(bridge)
    assembled = run(["as", "--64", root / "entry.s", "-o", root / "entry.o"])
    require(assembled.returncode == 0, assembled.stderr.decode())
    for number, (body, expected) in enumerate(cases):
        (root / "input.au").write_text("module test; auto test()->i64 {" + body + "}")
        observations = []
        for index, compiler in enumerate(compilers):
            assembly = root / f"program{index}.s"
            assembly.unlink(missing_ok=True)
            result = run([compiler, root / "input.au", "-o", assembly])
            if expected == "reject":
                require(result.returncode > 0 and not assembly.exists(), f"case {number}: invalid source accepted")
                observations.append((result.returncode, result.stderr))
                continue
            require(result.returncode == 0, f"case {number}: {result.stderr!r}")
            result = run(["as", "--64", assembly, "-o", root / "program.o"])
            require(result.returncode == 0, result.stderr.decode())
            result = run(["ld", "-o", root / "program", root / "entry.o", root / "program.o"])
            require(result.returncode == 0, result.stderr.decode())
            result = run([root / "program"])
            if expected == "trap":
                require(result.returncode == -signal.SIGILL and not result.stdout,
                        f"case {number}: expected exact SIGILL")
            else:
                require(result.returncode == 0 and len(result.stdout) == 8,
                        f"case {number}: invalid machine result")
            observations.append((result.returncode, result.stdout, result.stderr))
        require(observations[0] == observations[1], f"case {number}: baseline/candidate mismatch")
print(f"{len(cases)} baseline/candidate equivalence cases passed")
