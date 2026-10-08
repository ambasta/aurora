#!/usr/bin/env python3
"""Independent direct-IR short-circuit and private-ABI native acceptance.

The C++ fixture supplies verified IR and emitted instructions, never expectations.
Handwritten assembly replaces only probe bodies and metadata helper bodies. It
checks actual entry RSP modulo 16, record payloads, receiver authority, span
bounds/data and class-result storage. Each executed probe counts an effect;
method probes additionally mutate a real receiver field. Full 64-bit results
are read through integer_oracle's freestanding signal/syscall bridge.

Harness controls deliberately violate alignment and arguments and require the
exact named UD2 site with actual SIGILL termination. Explicit require() checks
remain active under python -O. These are bounded bootstrap ABI observations,
not a public Aurora ABI or a safety/performance proof.
"""

from __future__ import annotations

import argparse
from enum import Enum
import itertools
from pathlib import Path
import re

from integer_oracle import NativeRunner, command, require, validate_trap, validate_values


class ProbeTrap(Enum):
    ALIGNMENT = ".Lsc_alignment_trap"
    ARGUMENT = ".Lsc_argument_trap"
    BOUNDS = ".Laurora_bounds_trap"
    OVERFLOW = ".Laurora_overflow_trap"
    ZERO = ".Laurora_division_zero_trap"
    SHIFT = ".Laurora_shift_count_trap"


KINDS = (
    "scalar",
    "aggregate",
    "aggregate_result",
    "method",
    "method_value",
    "method_result",
    "metadata",
    "span",
    "subspan",
)
PREFIX = (1 << 40) + 17


def align_check():
    # At a SysV-style x86-64 function entry the return address accounts for
    # eight bytes. No prologue, compiler-generated or handwritten, precedes it.
    return """    movq %rsp, %rcx
    andq $15, %rcx
    cmpq $8, %rcx
    jne .Lsc_alignment_trap
"""


def replace_body(assembly, symbol, body):
    pattern = rf"(^{re.escape(symbol)}:\n).*?(^\.size {re.escape(symbol)},[^\n]*\n)"
    result, count = re.subn(pattern, lambda match: match[1] + body + match[2], assembly, flags=re.MULTILINE | re.DOTALL)
    require(count == 1, f"expected exactly one generated body for {symbol}, got {count}")
    return result


def instrument(assembly):
    for kind in KINDS:
        if kind in ("metadata", "subspan"):
            continue
        body = align_check()
        if kind.startswith("method"):
            body += """    cmpq $23, 0(%r10)
    jne .Lsc_argument_trap
    cmpq $29, 8(%r10)
    jb .Lsc_argument_trap
    cmpq $30, 8(%r10)
    ja .Lsc_argument_trap
    incq 8(%r10)
"""
        if kind in ("aggregate", "aggregate_result", "method_value", "method_result"):
            body += """    cmpq $17, 0(%r11)
    jne .Lsc_argument_trap
    cmpq $19, 8(%r11)
    jne .Lsc_argument_trap
    movq 16(%r11), %rdx
    cmpq $1, %rdx
    ja .Lsc_argument_trap
"""
            if kind == "aggregate_result":
                body += "    movq %rdx, 0(%r10)\n    movq $0, 8(%r10)\n"
            elif kind == "method_result":
                body += "    movq %rdx, 0(%rax)\n    movq $0, 8(%rax)\n"
            else:
                body += "    movq %rdx, %rax\n"
        elif kind == "span":
            body += """    cmpq $0, 0(%r11)
    jne .Lsc_argument_trap
    cmpq $0, 16(%r11)
    jne .Lsc_argument_trap
    cmpq $0, 24(%r11)
    jne .Lsc_argument_trap
    cmpq $0, 32(%r11)
    jne .Lsc_argument_trap
    movq 8(%r11), %rdx
    addq 40(%r11), %rdx
    cmpq $3, 48(%r11)
    je .Lsc_full_span
    cmpq $1, 48(%r11)
    jne .Lsc_argument_trap
    cmpq $1, 40(%r11)
    jne .Lsc_argument_trap
    cmpb $22, 0(%rdx)
    jne .Lsc_argument_trap
    jmp .Lsc_span_boolean
.Lsc_full_span:
    cmpq $0, 40(%r11)
    jne .Lsc_argument_trap
    cmpb $11, 0(%rdx)
    jne .Lsc_argument_trap
    cmpb $22, 1(%rdx)
    jne .Lsc_argument_trap
    cmpb $33, 2(%rdx)
    jne .Lsc_argument_trap
.Lsc_span_boolean:
    movq 56(%r11), %rax
    cmpq $1, %rax
    ja .Lsc_argument_trap
"""
        else:
            body += """    movq %rdi, %rax
    cmpq $1, %rax
    ja .Lsc_argument_trap
"""
        body += "    incq sc_probe_count(%rip)\n    ret\n"
        assembly = replace_body(assembly, "sc_probe_" + kind, body)
    metadata = (
        align_check()
        + """    xorq %rax, %rax
    cmpq $18, %rdi
    je .Lsc_metadata_done
    cmpq $17, %rdi
    jne .Lsc_argument_trap
    movq $1, %rax
.Lsc_metadata_done:
    incq sc_probe_count(%rip)
    ret
"""
    )
    assembly = replace_body(assembly, "aurora_reflect_size", metadata)
    return (
        assembly
        + """
.data
.align 8
sc_probe_count:
    .quad 0
.text
.Lsc_alignment_trap:
    ud2
.Lsc_argument_trap:
    ud2
"""
    )


def model(shape, a, b, c):
    """Closed independent truth/effect model, with no compiler data as input."""
    if shape == "and":
        return bool(a and b), int(bool(a))
    if shape == "or":
        return bool(a or b), int(not a)
    require(shape == "nested", f"unknown shape {shape}")
    first = bool(a and b)
    return bool(first or c), int(bool(a)) + int(not first)


def wrapper(name, target, values, encoded=True):
    # The runner calls this wrapper with entry RSP%16 == 8. Its own explicit
    # alignment adjustment is independent of the generated caller under test.
    a, b, c = values
    result = f"""
.text
.globl {name}
{name}:
    movq $0, sc_probe_count(%rip)
    movq ${a}, %rdi
    movq ${b}, %rsi
    movq ${c}, %rdx
    subq $8, %rsp
    call {target}
    addq $8, %rsp
"""
    if encoded:
        result += "    imulq $1000, %rax\n    addq sc_probe_count(%rip), %rax\n"
    return result + "    ret\n"


def cases():
    tests = []
    for kind, shape, depth, values in itertools.product(
        KINDS, ("and", "or", "nested"), range(4), itertools.product((0, 1), repeat=3)
    ):
        truth, effects = model(shape, *values)
        result = sum(PREFIX + index for index in range(depth)) + int(truth)
        if kind.startswith("method"):
            result += 100 * (29 + effects)
        expected = result * 1000 + effects
        target = f"sc_{kind}_{shape}_{depth}"
        name = f"{target}{values}"
        tests.append((target, values, expected, name))
    for target in ("sc_guarded_store", "sc_receiver_guarded_store", "sc_window_count"):
        for values in itertools.product((0, 1), repeat=3):
            truth, effects = model("nested", *values)
            tests.append((target, values, int(truth) * 1000 + effects, f"{target}{values}"))
    for trap, shape, depth in itertools.product(("bounds", "overflow", "zero", "shift"), ("and", "or"), (1, 2)):
        target = f"sc_trap_{trap}_{shape}_{depth}"
        skip = int(shape == "or")
        value = (sum(PREFIX + index for index in range(depth)) + skip) * 1000
        tests.append((target, (skip, 0, 0), value, f"skipped {target}"))
    return tests


def required_traps(runner, assembly):
    count = 0
    for trap, shape, depth in itertools.product(("bounds", "overflow", "zero", "shift"), ("and", "or"), (1, 2)):
        target = f"sc_trap_{trap}_{shape}_{depth}"
        execute = int(shape == "and")
        code = wrapper("sc_required_trap", target, (execute, 0, 0))
        observed, symbols = runner.assemble(assembly + code, ["sc_required_trap"])
        validate_trap(observed, ProbeTrap[trap.upper()], symbols, target)
        count += 1
    return count


def harness_controls(runner, assembly):
    # This intentionally omits the wrapper's pre-call adjustment: the probe must
    # detect its wrong real entry alignment, rather than merely matching text.
    misaligned = """
.text
.globl sc_bad_alignment
sc_bad_alignment:
    movq $1, %rdi
    call sc_probe_scalar
    ret
"""
    observed, symbols = runner.assemble(assembly + misaligned, ["sc_bad_alignment"])
    validate_trap(observed, ProbeTrap.ALIGNMENT, symbols, "alignment oracle negative control")
    malformed = """
.text
.globl sc_bad_argument
sc_bad_argument:
    movq $2, %rdi
    subq $8, %rsp
    call sc_probe_scalar
    addq $8, %rsp
    ret
"""
    observed, symbols = runner.assemble(assembly + malformed, ["sc_bad_argument"])
    validate_trap(observed, ProbeTrap.ARGUMENT, symbols, "argument oracle negative control")
    # A well-aligned legal call is also a harness control, so an always-trapping
    # probe is not sufficient to claim successful fault detection.
    good = wrapper("sc_good_control", "sc_probe_scalar", (1, 0, 0))
    observed, _ = runner.assemble(assembly + good, ["sc_good_control"])
    validate_values(observed, [1001], ["legal probe control"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ir_tests", type=Path)
    parser.add_argument("--artifacts", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.artifacts.mkdir(parents=True, exist_ok=False)
    raw = command([arguments.ir_tests.resolve(), "--emit-native"], timeout=30).stdout.decode()
    require("validated typed IR" in raw, "fixture did not emit validated assembly")
    (arguments.artifacts / "generated.s").write_text(raw)
    assembly = instrument(raw)
    (arguments.artifacts / "instrumented.s").write_text(assembly)
    runner = NativeRunner(arguments.artifacts, None, 10)
    harness_controls(runner, assembly)
    tests = cases()
    names, expected, wrappers, functions = [], [], [], []
    for index, (target, values, result, name) in enumerate(tests):
        function = f"sc_case_{index}"
        names.append(name)
        expected.append(result)
        functions.append(function)
        wrappers.append(wrapper(function, target, values))
    full_assembly = assembly + "\n".join(wrappers)
    (arguments.artifacts / "all-cases.s").write_text(full_assembly)
    observed, _ = runner.assemble(full_assembly, functions)
    validate_values(observed, expected, names)
    traps = required_traps(runner, assembly)
    (arguments.artifacts / "cases.tsv").write_text(
        "case\texpected_i64\n" + "".join(f"{name}\t{value}\n" for name, value in zip(names, expected))
    )
    summary = (
        f"PASS short-circuit direct IR native: {len(tests)} value/effect cases; "
        "9 call kinds, 4 retained stack depths, full truth tables; "
        f"{traps} exact required-RHS traps; 2 exact fault controls and 1 legal alignment control"
    )
    (arguments.artifacts / "summary.txt").write_text(summary + "\n")
    print(summary)


if __name__ == "__main__":
    main()
