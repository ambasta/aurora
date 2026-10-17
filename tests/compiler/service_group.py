#!/usr/bin/env python3
"""Distinct sealed service group source/ABI probe; no native or guest claim."""

import argparse
import os
import signal
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
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    compiler = args.compiler.resolve()
    if args.artifacts:
        work = args.artifacts.resolve()
        work.mkdir(parents=True)
    else:
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
    call_assembly = work / "call.s"
    result = run([compiler, ROOT / "tests/compiler/call_service.au", "-o", call_assembly])
    require(result.returncode == 0, result.stderr.decode())
    call_text = call_assembly.read_text()
    call_symbol = "__au_v_m1_12call_service_n0__d12call_service"
    require(".local " + call_symbol in call_text, "call entry must remain private")
    call_assembly.write_text(
        call_text
        + f"""
.text
.globl __au_runtime_group_entry
.hidden __au_runtime_group_entry
.type __au_runtime_group_entry,@function
__au_runtime_group_entry:
    pushq %rbp
    movq %rsp, %rbp
    movq %rdi, %r11
    call {call_symbol}
    leave
    ret
.size __au_runtime_group_entry,.-__au_runtime_group_entry
"""
    )
    call_binary = work / "call"
    result = run(
        [
            os.environ.get("CXX", "g++"),
            "-std=c++23",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            ROOT / "tests/compiler/call_service_host.cpp",
            ROOT / "tests/compiler/service_group_abi.S",
            call_assembly,
            "-o",
            call_binary,
        ]
    )
    require(result.returncode == 0, result.stderr.decode())
    for mode in range(7):
        result = run([call_binary, mode])
        require(
            result.returncode == (0 if mode < 3 else -signal.SIGILL),
            f"call result ABI/canonicality failed ({mode}): " + result.stderr.decode(),
        )
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
    call = "builtin::CallSession& c"
    negative.update(
        {
            "call-mixed-console": f"auto f({call}, builtin::ConsoleSession& s) -> i64 {{ return 0; }}",
            "call-mixed-event": f"auto f({call}, builtin::IommuEventSession& s) -> i64 {{ return 0; }}",
            "call-mixed-display": f"auto f({call}, builtin::DisplaySession& s) -> i64 {{ return 0; }}",
            "call-duplicate": f"auto f({call}, builtin::CallSession& s) -> i64 {{ return 0; }}",
            "call-owned-values": f"auto f({call}, builtin::OwnedValues<u64> v) -> i64 {{ return 0; }}",
            "call-wrong-signed": f"auto f({call}) -> builtin::CallResult {{ return c.call(1); }}",
            "call-wrong-byte": f"auto f({call}) -> builtin::CallResult {{ return c.call(1u8); }}",
            "call-extra": f"auto f({call}) -> builtin::CallResult {{ return c.call(1u64, 2u64); }}",
            "call-absent": f"auto f({call}) -> builtin::CallResult {{ return c.call(); }}",
            "call-value": "auto f(builtin::CallSession c) -> i64 { return 0; }",
            "call-const": "auto f(const builtin::CallSession& c) -> i64 { return 0; }",
            "call-return-capability": f"auto f({call}) -> builtin::CallSession {{ return c; }}",
            "call-forge": "auto f() -> i64 { builtin::CallSession c; return 0; }",
            "call-raw": "auto __au_runtime_call() -> i64 { return 0; }",
        }
    )
    for name, body in negative.items():
        source = work / (name + ".au")
        source.write_text("module rejected; " + body)
        result = run([compiler, source, "-o", work / "rejected.s"])
        require(result.returncode == 1 and result.stderr, "invalid group source was not cleanly rejected: " + name)
    print(f"PASS distinct service group source/ABI: {len(negative)} negative cases; {work}")


if __name__ == "__main__":
    main()
