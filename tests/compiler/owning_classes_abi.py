#!/usr/bin/env python3
"""Literal-layout handwritten owning-class boundaries with the real hosted adapter.

The direct-IR fixture is compiled separately. This runner checks handwritten
entry records, transferred descriptor clearing, padding/canaries, callee-saved
registers, runtime-helper alignment, mixed positions and exact release order.
Resize cases also check literal field addresses, preserved prefixes, zero extension,
unchanged siblings and failed requests, plus odd/even saved scalar stacks.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from unsigned_oracle import require

ROOT = Path(__file__).resolve().parents[2]


ALIGN = "movq %rsp,%r9\nandq $15,%r9\ncmpq $8,%r9\njne .Lowning_abi_fail\n"


def bridge(mode):
    resize_method = mode.startswith("resize-") and mode != "resize-move"
    target = "owning_resize_method" if resize_method else "owning_method" if mode == "method" else "owning_entry"
    text = "\n.text\n.globl __au_runtime_bytes_test_entry\n__au_runtime_bytes_test_entry:\n"
    text += "pushq %rbp\npushq %rbx\npushq %r12\npushq %r13\npushq %r14\npushq %r15\nsubq $8,%rsp\n"
    text += "movq $111,%rbp\nmovq $222,%rbx\nmovq $333,%r12\nmovq $444,%r13\nmovq $555,%r14\nmovq $666,%r15\n"
    text += "movq %rdi,%r10\n" if mode == "method" or resize_method else "movq %rdi,%r11\nmovq %rsi,%r10\n"
    text += f"call {target}\n"
    for register, value in [("rbp", 111), ("rbx", 222), ("r12", 333), ("r13", 444), ("r14", 555), ("r15", 666)]:
        text += f"cmpq ${value},%{register}\njne .Lowning_abi_fail\n"
    text += "addq $8,%rsp\npopq %r15\npopq %r14\npopq %r13\npopq %r12\npopq %rbx\npopq %rbp\nret\n"
    for name in ("allocate", "drop", "at", "set", "resize"):
        text += f"owning_abi_{name}:\n{ALIGN}"
        if mode == "copied-resource" or mode.startswith("construct-produced"):
            # Force each runtime cleanup/allocation to destroy caller-saved hidden capabilities.
            text += f"subq $8,%rsp\ncall __au_runtime_bytes_{name}\naddq $8,%rsp\n"
            text += "movabsq $0x1111222233334444,%r10\nmovabsq $0x5555666677778888,%r11\nret\n"
        else:
            text += f"jmp __au_runtime_bytes_{name}\n"
    return text + '.Lowning_abi_fail:\nud2\n.section .note.GNU-stack,"",@progbits\n'


def move_descriptor(source, destination, source_base=0, destination_base=0):
    code = ""
    for byte in range(0, 32, 8):
        code += f"movq {source_base + byte}({source}),%rcx\nmovq %rcx,{destination_base + byte}({destination})\n"
        code += f"movq $0,{source_base + byte}({source})\n"
    return code


def compare_byte(base, offset, value):
    return f"cmpb ${value},{offset}({base})\njne .Lowning_abi_fail\n"


def handwritten_constructor():
    code = ALIGN
    code += "cmpq %r10,%r11\nje .Lowning_abi_fail\n"
    code += compare_byte("%r11", 40, 197) + compare_byte("%r11", 88, 223)
    code += "cmpq $123456789,80(%r11)\njne .Lowning_abi_fail\n"
    for offset, size in [(8, 3), (48, 5)]:
        code += f"movq (%r11),%rcx\ncmpq %rcx,{offset}(%r11)\njne .Lowning_abi_fail\n"
        code += f"cmpq ${size},{offset + 16}(%r11)\njne .Lowning_abi_fail\n"
        code += f"cmpq $1,{offset + 24}(%r11)\njne .Lowning_abi_fail\n"
        for word in range(0, 32, 8):
            code += f"cmpq $0,{offset + word}(%r10)\njne .Lowning_abi_fail\n"
        code += move_descriptor("%r11", "%r10", offset, offset)
    code += "movb $197,(%r10)\nmovq $123456789,40(%r10)\nmovb $223,80(%r10)\nxorq %rax,%rax\nret\n"
    return code


def handwritten_six():
    code = ALIGN + "cmpq %r10,%r11\nje .Lowning_abi_fail\n"
    code += compare_byte("%r11", 96, 201)
    code += "movabsq $0x123456789,%rcx\ncmpq %rcx,136(%r11)\njne .Lowning_abi_fail\n"
    code += "cmpq $7,120(%r11)\njne .Lowning_abi_fail\n"
    for parcel_base, n in [(8, 0), (144, 1)]:
        code += compare_byte("%r11", parcel_base, 197 + n)
        code += compare_byte("%r11", parcel_base + 80, 223 + n)
        code += f"cmpq ${123456789 + n},{parcel_base + 40}(%r11)\njne .Lowning_abi_fail\n"
        for i in list(range(1, 8)) + list(range(81, 88)):
            code += compare_byte("%r11", parcel_base + i, 0)
        for offset, size in [(8, 3 + n), (48, 5 + n)]:
            code += f"movq (%r11),%rcx\ncmpq %rcx,{parcel_base + offset}(%r11)\njne .Lowning_abi_fail\n"
            code += f"cmpq ${size},{parcel_base + offset + 16}(%r11)\njne .Lowning_abi_fail\n"
            code += f"cmpq $1,{parcel_base + offset + 24}(%r11)\njne .Lowning_abi_fail\n"
    for i in range(97, 104):
        code += compare_byte("%r11", i, 0)
    for i in range(232, 240):
        code += compare_byte("%r11", i, 0)
    # Save private input/result pointers across real runtime drops.
    code += "pushq %rbp\npushq %r12\npushq %r13\nmovq %r11,%r12\nmovq %r10,%r13\n"
    code += "movb 8(%r12),%cl\nmovb %cl,(%r13)\nmovq 48(%r12),%rcx\nmovq %rcx,40(%r13)\n"
    code += "movb 88(%r12),%cl\nmovb %cl,80(%r13)\n"
    code += move_descriptor("%r12", "%r13", 16, 8) + move_descriptor("%r12", "%r13", 56, 48)
    for offset in (104, 192, 152):
        code += f"leaq {offset}(%r12),%rdi\ncall owning_abi_drop\n"
    code += "popq %r13\npopq %r12\npopq %rbp\nxorq %rax,%rax\nret\n"
    return code


def handwritten_copied():
    code = ALIGN
    for left, right in [("%r10", "%r11"), ("%r10", "%rax"), ("%r11", "%rax")]:
        code += f"cmpq {left},{right}\nje .Lowning_abi_fail\n"
    for offset, value in [(16, 3), (24, 1), (40, 99)]:
        code += f"cmpq ${value},{offset}(%r10)\njne .Lowning_abi_fail\n"
    code += compare_byte("%r10", 32, 17) + compare_byte("%r10", 48, 77)
    code += compare_byte("%r11", 0, 17)
    code += "cmpq $99,8(%r11)\njne .Lowning_abi_fail\ncmpq $42,16(%r11)\njne .Lowning_abi_fail\n"
    for i in list(range(1, 8)) + list(range(24, 32)):
        code += compare_byte("%r11", i, 0)
    code += "movb $17,(%rax)\nmovq $42,8(%rax)\nxorq %rax,%rax\nret\n"
    return code


def command(args, timeout=60):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, check=False)
    require(
        result.returncode == 0,
        f"command failed ({result.returncode}): {' '.join(str(arg) for arg in args)}\n"
        + result.stdout.decode(errors="replace")
        + result.stderr.decode(errors="replace"),
    )
    return result.stdout


MODES = (
    "move",
    "construct",
    "construct-odd",
    "construct-even",
    "construct-produced",
    "construct-produced-odd",
    "construct-produced-even",
    "six",
    "method",
    "copied",
    "copied-resource",
    "resize-first",
    "resize-odd",
    "resize-even",
    "resize-failed",
    "resize-move",
)
HANDWRITTEN = {
    "construct": ("owning_constructor", handwritten_constructor),
    "copied": ("copy_method", handwritten_copied),
    "six": ("owning_six", handwritten_six),
}


def boundary(fixture, driver, cxx, directory, mode, handwritten):
    """Link one emitted (or handwritten-target) boundary with the hosted driver and run it."""
    candidate = command([fixture, "--emit-abi", mode]).decode()
    if handwritten:
        symbol, body = HANDWRITTEN[mode]
        pattern = rf"(?m)^{symbol}:\n[\s\S]*?^\.size {symbol},[^\n]*\n"
        candidate, replaced = re.subn(pattern, lambda _: f"{symbol}:\n{body()}.size {symbol},.-{symbol}\n", candidate)
        require(replaced == 1, "exactly one private emitted target replaced")
    candidate = re.sub(r"call __au_runtime_bytes_(allocate|drop|at|set|resize)\b", r"call owning_abi_\1", candidate)
    stem = f"{mode}-{int(handwritten)}"
    source = directory / (stem + ".s")
    source.write_text(candidate + bridge(mode))
    executable = directory / (stem + ".elf")
    command([*cxx, "-no-pie", source, driver, "-o", executable])
    symbols = command(["nm", executable]).decode()
    if mode.startswith("resize-") and mode != "resize-move":
        entry_symbol = "owning_resize_method"
    else:
        entry_symbol = "owning_method" if mode == "method" else "owning_entry"
    require(re.search(rf"\bt {entry_symbol}$", symbols, re.M), "resource entry retains private binding")
    output = command([executable, mode]).decode()
    require(output.startswith("PASS hosted owning ABI"), "hosted adapter observation recorded")
    return f"PASS owning class ABI {mode} handwritten-target={handwritten}: {output.strip()}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("driver", type=Path, help="Meson-built driver and hosted byte adapter library")
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    cxx = shlex.split(os.environ.get("CXX", "g++"))
    fixture, driver = args.fixture.resolve(strict=True), args.driver.resolve(strict=True)
    jobs = [
        (mode, handwritten) for mode in MODES for handwritten in ((False, True) if mode in HANDWRITTEN else (False,))
    ]
    with tempfile.TemporaryDirectory(prefix="aurora-owning-abi-") as temporary:
        directory = args.work_dir or Path(temporary)
        directory.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=len(os.sched_getaffinity(0))) as pool:
            for line in pool.map(lambda job: boundary(fixture, driver, cxx, directory, *job), jobs):
                print(line, flush=True)
    print(f"PASS owning class ABI: {len(jobs)} literal-layout hosted boundary cases")


if __name__ == "__main__":
    main()
