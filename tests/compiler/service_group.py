#!/usr/bin/env python3
"""Distinct sealed service group source/ABI probe; no native or guest claim."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def require(okay, message):
    if not okay:
        raise RuntimeError(message)


def run(command):
    return subprocess.run(list(map(str, command)), cwd=ROOT, capture_output=True, timeout=120)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    compiler = parser.parse_args().compiler.resolve()
    (ROOT / "build").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="service-group-", dir=ROOT / "build"))
    assembly = work / "group.s"
    result = run([compiler, ROOT / "tests/compiler/service_group.au", "-o", assembly])
    require(result.returncode == 0, result.stderr.decode())
    text = assembly.read_text()
    symbol = "__au_v_m1_13service_group_n0__d13group_service"
    require(".local " + symbol in text, "group entry must remain private")
    require("__au_runtime_bytes_" not in text, "service group acquired owner runtime")
    assembly.write_text(
        text
        + f"""
.text
.globl __au_runtime_group_entry
.hidden __au_runtime_group_entry
.type __au_runtime_group_entry,@function
__au_runtime_group_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call {symbol}
    leave
    ret
.size __au_runtime_group_entry,.-__au_runtime_group_entry
"""
    )
    binary = work / "group"
    result = run(
        [
            os.environ.get("CXX", "g++"),
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/compiler/service_group_host.cpp",
            ROOT / "tests/compiler/service_group_abi.S",
            assembly,
            "-o",
            binary,
        ]
    )
    require(result.returncode == 0, result.stderr.decode())
    for mode in range(4):
        result = run([binary, mode])
        require(result.returncode == 0, f"service group ABI/stop-prefix failed ({mode}): " + result.stderr.decode())
    pair = "builtin::ConsoleSession& c, builtin::DisplaySession& d"
    helper = f"auto g({pair}, bool flag) -> i64 {{ return 0; }} "
    negative = {
        "duplicate-console": "auto f(builtin::ConsoleSession& c, builtin::ConsoleSession& d) -> i64 { return 0; }",
        "duplicate-display": "auto f(builtin::DisplaySession& c, builtin::DisplaySession& d) -> i64 { return 0; }",
        "late": "auto f(builtin::ConsoleSession& c, i64 n, builtin::DisplaySession& d) -> i64 { return 0; }",
        "third": f"auto f({pair}, builtin::ConsoleSession& again) -> i64 {{ return 0; }}",
        "crossed": helper + f"auto f({pair}) -> i64 {{ return g(d, c, true); }}",
        "duplicate-argument": helper + f"auto f({pair}) -> i64 {{ return g(c, c, true); }}",
        "suspended-first": helper
        + f"auto f({pair}) -> i64 {{ return g(c, d, c.put('Q') == builtin::ConsolePutResult::success); }}",
        "suspended-second": helper + f"auto f({pair}) -> i64 {{ return g(c, d, d.pixel(0u64,0u64,0u8,"
        f"0u8,0u8) == builtin::DisplayPutResult::success); }}",
        "fake": helper + "auto f(i64 c, i64 d) -> i64 { return g(c, d, true); }",
        "second-by-value": "auto f(builtin::ConsoleSession& c, builtin::DisplaySession d) -> i64 { return 0; }",
        "second-const": "auto f(builtin::ConsoleSession& c, const builtin::DisplaySession& d) -> i64 { return 0; }",
        "region": f"auto f({pair}, builtin::ByteRegion r) -> i64 {{ return 0; }}",
        "owner": f"auto f({pair}, builtin::OwnedBytes b) -> i64 {{ return 0; }}",
        "mutable-span": f"auto f({pair}, builtin::span<u8> b) -> i64 {{ return 0; }}",
        "store": f"auto f({pair}) -> i64 {{ builtin::DisplaySession x = d; return 0; }}",
        "return": f"auto f({pair}) -> builtin::DisplaySession {{ return d; }}",
        "reflect": f"auto f({pair}) -> i64 {{ return size_of(builtin::DisplaySession); }}",
        "recursive": f"auto f({pair}) -> i64 {{ return f(c, d); }}",
        "seven": f"auto f({pair}, i64 a, i64 b, i64 e, i64 f, i64 g) -> i64 {{ return 0; }}",
    }
    for name, body in negative.items():
        source = work / (name + ".au")
        source.write_text("module rejected; " + body)
        result = run([compiler, source, "-o", work / "rejected.s"])
        require(result.returncode == 1 and result.stderr, "invalid group source was not cleanly rejected: " + name)
    print(f"PASS distinct service group source/ABI: {len(negative)} negative cases; {work}")


if __name__ == "__main__":
    main()
