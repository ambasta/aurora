#!/usr/bin/env python3
"""Invocation-only mutable parameters: actual copy consumer and rejected source forms.

One source probe and the real kernel copy object share one native driver. The
host supplies independently stated literal ABI records and standard-library copy
expectations; no generated function body is rewritten. Unsupported forms use the
existing diagnostic/artifact-preservation runner.
"""

import argparse
import os
from pathlib import Path
import re
import shlex
import tempfile

from native_runner import DIAGNOSTIC, ROOT, Suite, Trap, check_trap, command, observe, require, symbols_of

MUTABLE = "builtin::span<u8>"
READONLY = "builtin::span<const u8>"
PROBE = """module invocation_bytes;
auto probe(builtin::span<u8> destination, builtin::span<const u8> source, i64 index, u8 value) -> u64 {
    if (source.size() != 0) { return 257u64; }
    if (!destination.set(index, value)) { return 256u64; }
    return u64(destination.at(index));
}
"""
BRIDGE = """
.text
.global .Laurora_bounds_trap
.global invocation_bytes_probe
.type invocation_bytes_probe,@function
invocation_bytes_probe:
    pushq %rbp
    movq %rsp,%rbp
    pushq %rbx
    pushq %r12
    pushq %r13
    pushq %r14
    pushq %r15
    subq $8,%rsp
    movq $17,%rbx
    movq $34,%r12
    movq $51,%r13
    movq $68,%r14
    movq $85,%r15
    movq %rdi,%r11
    call @PROBE@
    cmpq $17,%rbx
    jne .Linvocation_abi_failure
    cmpq $34,%r12
    jne .Linvocation_abi_failure
    cmpq $51,%r13
    jne .Linvocation_abi_failure
    cmpq $68,%r14
    jne .Linvocation_abi_failure
    cmpq $85,%r15
    jne .Linvocation_abi_failure
    addq $8,%rsp
    popq %r15
    popq %r14
    popq %r13
    popq %r12
    popq %rbx
    leave
    ret
.Linvocation_abi_failure:
    ud2
.size invocation_bytes_probe,.-invocation_bytes_probe
.section .note.GNU-stack,"",@progbits
"""


def rejected_sources():
    def function(body, parameters=f"{MUTABLE} output"):
        return f"auto rejected({parameters})->bool{{{body}}}"

    cases = {
        "mutable-local": f"auto test()->i64{{{MUTABLE} output;return 42;}}",
        "copy-parameter": function(f"const {MUTABLE} copy=output;return true;"),
        "readonly-conversion": function(f"const {READONLY} copy=output;return true;"),
        "mutable-subspan": function("output.subspan(0,0);return true;"),
        "mutable-field": f"class Box{{{MUTABLE} bytes;}};",
        "mutable-result": f"auto rejected({MUTABLE} output)->{MUTABLE}{{return output;}}",
        "mutable-forward": function("return helper(output);") + f"auto helper({MUTABLE} output)->bool{{return true;}}",
        "readonly-store": function("return output.set(0,1u8);", f"{READONLY} output"),
        "readonly-as-writable-argument": f"auto target({MUTABLE} output)->bool{{return true;}}"
        + f"auto rejected({READONLY} input)->bool{{return target(input);}}",
        "mutable-source-issuance": f"auto target({MUTABLE} output)->bool{{return true;}}"
        + "auto test()->bool{builtin::array<u8,1> bytes={0u8};return target(borrow_bytes(bytes));}",
        "mutable-to-readonly-call": f"auto sink({READONLY} input)->bool{{return true;}}"
        + function("return sink(output);"),
        "mutable-recursion": function("return rejected(output);"),
        "mutable-word-parameter": "auto rejected(builtin::span<u64> output)->bool{return true;}",
        "mutable-scalar-call": "auto helper()->bool{return true;}" + function("return helper();"),
    }
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--formatter", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--copy-object", type=Path, required=True)
    parser.add_argument("--observer", type=Path, required=True)
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="aurora-invocation-bytes-") as scratch:
        root = Path(scratch)
        source, assembly = root / "probe.au", root / "probe.s"
        source.write_text(PROBE)
        formatter = args.formatter.resolve(strict=True)
        formatted = command([formatter, source]).stdout
        source.write_bytes(formatted)
        require(command([formatter, source]).stdout == formatted, "mutable parameter formatter idempotence")
        command([formatter, "--check", source])
        helper = ROOT / "examples/kernel-snapshot-copy.au"
        command([formatter, "--check", helper])
        command([compiler, source, "-o", assembly])
        text = assembly.read_text()
        symbols = re.findall(r"^\.type (\w+__d5probe), @function$", text, re.M)
        require(len(symbols) == 1, "one private source probe")
        assembly.write_text(text + BRIDGE.replace("@PROBE@", symbols[0]))
        executable = root / "test"
        cxx = shlex.split(os.environ.get("CXX", "g++"))
        command(
            [
                *cxx,
                "-no-pie",
                assembly,
                args.copy_object.resolve(strict=True),
                args.host.resolve(strict=True),
                args.observer.resolve(strict=True),
                "-o",
                executable,
            ]
        )
        result = command([executable])
        require(result.stdout.startswith(b"PASS invocation byte views: "), "native acceptance marker")
        print(result.stdout.decode(), end="")
        symbols = symbols_of(executable)
        require(".Laurora_bounds_trap" in symbols, "exact probe bounds site")
        for base in (0, 7):
            for field in (0, 2, 3, 4, 5, 6):
                value = (1 << 63) if field == 6 else 1
                result = command([executable, base + field, value], allow_signal=True)
                observed = observe(result)
                check_trap(observed, Trap.BOUNDS, symbols, f"parameter {base}, field {field}")
    suite = Suite(compiler, "invocation byte rejection", pattern=DIAGNOSTIC)
    for name, source in rejected_sources().items():
        suite.reject(name, "module invocation_rejected;" + source)
    suite.finish()


if __name__ == "__main__":
    main()
