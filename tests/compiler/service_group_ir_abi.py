#!/usr/bin/env python3
"""Run cumulative hostile IR, then execute its nonlexical/reused-loan assembly."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def run(command):
    result = subprocess.run(list(map(str, command)), cwd=ROOT, capture_output=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {command}\n" + result.stdout.decode() + result.stderr.decode()
        )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ir_binary", type=Path)
    binary = parser.parse_args().ir_binary.resolve()
    (ROOT / "build").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="service-group-ir-abi-", dir=ROOT / "build"))
    assembly = work / "nonlexical.s"
    result = run([binary, assembly])
    print(result.stdout.decode(), end="")
    text = assembly.read_text()
    if ".local group_caller" not in text:
        raise RuntimeError("nonlexical IR entry lost private linkage")
    assembly.write_text(
        text
        + """
.text
.globl __au_runtime_group_entry
.hidden __au_runtime_group_entry
.type __au_runtime_group_entry,@function
__au_runtime_group_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call group_caller
    leave
    ret
.size __au_runtime_group_entry,.-__au_runtime_group_entry
"""
    )
    executable = work / "nonlexical"
    run(
        [
            os.environ.get("CXX", "g++"),
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/compiler/service_group_ir_host.cpp",
            ROOT / "tests/compiler/service_group_abi.S",
            assembly,
            "-o",
            executable,
        ]
    )
    print(run([executable]).stdout.decode(), end="")
    print(f"PASS grouped IR execution artifacts: {work}")


if __name__ == "__main__":
    main()
