#!/usr/bin/env python3
"""Literal-layout, handwritten method-span ABI oracle (no compiler invocation).

The separate C++ IR producer is supplied prebuilt. The older logical-span oracle
provides assembly execution/canary plumbing only; parameter shapes, records,
method registers, results and corruption controls below are independently stated.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import logical_spans_abi as abi


def shapes():
    return [(n, 1 << p) for n in range(1, 7) for p in range(n)] + [(6, 63), (6, 21), (6, 42)]


def record(n, mask, domain, transform=0, incoming=False):
    words = []
    for p in range(n):
        if mask & (1 << p):
            kind = int(domain == "owner" or (domain == "mixed" and p % 2 == 0))
            payload = [abi.REGION + p, abi.ALLOCATION + p, 29 + p, 1] if kind else ["array_bytes", 0, 0, 0]
            words += [kind, *payload, 2 + p + 2 * transform, 0 if transform else 17 + p]
        elif p % 3 == 1:
            words += [(0xA5A5A5A5A5A5A500 if incoming else 0) + 197 + p]
        else:
            words += [(1 << 40) + 31 + p]
    if not incoming and len(words) % 2:
        words.append(0)
    return words


def target(mode):
    code = abi.align() + "    cmpq $receiver, %r10\n    jne .Labi_record_fail\n"
    code += "    movq %rax, method_hidden(%rip)\n"
    code += "    movq expected_record(%rip), %rsi\n    xorq %rcx, %rcx\n"
    # Unique per function labels are supplied by the caller.
    code += """.Lmethod_compare_SUFFIX:
    movzbq (%r11,%rcx), %rdx
    cmpb (%rsi,%rcx), %dl
    jne .Labi_record_fail
    incq %rcx
    cmpq expected_size(%rip), %rcx
    jne .Lmethod_compare_SUFFIX
    incq probe_calls(%rip)
"""
    if mode:
        code += "    movq method_hidden(%rip), %rdi\n"
        if mode == 1:
            code += "    movq $123, (%rdi)\n"
        else:
            for i, value in enumerate([1, abi.REGION, abi.ALLOCATION, 29, 1, 0, 29]):
                code += f"    movabsq ${value}, %rdx\n    movq %rdx, {8 * i}(%rdi)\n"
    return code + abi.clobber(42 if mode == 0 else 0) + "    ret\n"


def observer():
    return (
        abi.align()
        + abi.compare("%r11", "method_result_expected", 56, "method_observe")
        + "    cmpq $0, 56(%r11)\n    jne .Labi_record_fail\n"
        + abi.clobber()
        + "    ret\n"
    )


def cases(direct=False):
    result = []
    for n, mask in shapes():
        for mode in range(3):
            suffix = f"{n}_{mask}_{mode}"
            for domain in ("array", "owner", "mixed"):
                if direct:
                    case = {
                        "name": f"generated result {suffix} {domain}",
                        "target": f"method_span_target_{suffix}",
                        "input": record(n, mask, domain, incoming=True),
                        "answer": 42 if mode == 0 else 0,
                    }
                    if mode:
                        case["combined"] = True
                        case["result"] = (
                            [123] + [0xCDCDCDCDCDCDCDCD] * 6
                            if mode == 1
                            else [1, abi.REGION, abi.ALLOCATION, 29, 1, 0, 29]
                        )
                    if mode == 2:
                        case["borrow"] = 1
                    result.append(case)
                    continue
                for depth in range(3):
                    for transform in range(2):
                        result.append(
                            {
                                "name": f"{domain} {suffix} depth {depth} empty-window {transform}",
                                "target": f"method_span_forward_{suffix}_{depth}_{transform}",
                                "input": record(n, mask, domain, incoming=True),
                                "output": record(n, mask, domain, transform),
                                "answer": (123 if mode == 1 else 42) + abi.retained(depth),
                                "probes": 1,
                            }
                        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ir_tests", type=Path)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    if args.artifacts is None:
        args.artifacts = Path(tempfile.mkdtemp(prefix="method-spans-abi-"))
    else:
        args.artifacts.mkdir(parents=True, exist_ok=False)
    raw = abi.command([args.ir_tests.resolve()]).stdout.decode()
    (args.artifacts / "generated.s").write_text(raw)
    extra = abi.blob("method_hidden", [0]) + abi.blob(
        "method_result_expected", [1, abi.REGION, abi.ALLOCATION, 29, 1, 0, 29]
    )
    observed = abi.replace_body(raw, "method_span_observe", observer())
    outgoing = observed
    for n, mask in shapes():
        for mode in range(3):
            suffix = f"{n}_{mask}_{mode}"
            outgoing = abi.replace_body(
                outgoing, f"method_span_target_{suffix}", target(mode).replace("SUFFIX", suffix)
            )
    direct_cases = cases(True)
    forward_cases = cases()
    direct = observed + abi.harness(direct_cases, True) + "\n.data\n" + extra
    full = outgoing + abi.harness(forward_cases, True) + "\n.data\n" + extra
    abi.execute(args.artifacts, "incoming-generated-results", direct, direct_cases)
    abi.execute(args.artifacts, "outgoing-handwritten-methods", full, forward_cases)
    # Every control must produce the oracle's exact failure status and case,
    # rather than an accidental trap, crash, or an always-failing baseline.
    controls = []
    target_name = "method_span_forward_1_1_0_0_0"
    controls += [
        ("incoming-seventh-word", target_name, "    movq %rax, -8(%rbp)", "    movq $0, -8(%rbp)", 91),
        ("outgoing-seventh-word", target_name, "    movq %rax, 48(%rsp)", "    movq $0, 48(%rsp)", 91),
        (
            "receiver-register",
            target_name,
            "    call method_span_target_1_1_0",
            "    xorq %r10, %r10\n    call method_span_target_1_1_0",
            91,
        ),
    ]
    # Independently corrupt every complete record word, including opaque owner
    # payload words, so accidental truncation cannot hide behind length checks.
    for word in range(7):
        controls.append(
            (
                f"packed-word-{word}",
                target_name,
                f"    movq %rax, {8 * word}(%rsp)",
                f"    movq $-1, {8 * word}(%rsp)",
                91,
            )
        )
    odd = "method_span_forward_1_1_0_1_0"
    controls += [
        (
            "odd-stack-alignment",
            odd,
            "    subq $8, %rsp\n    call method_span_target_1_1_0",
            "    nop\n    call method_span_target_1_1_0",
            92,
        ),
        (
            "saved-operand",
            odd,
            "    call method_span_target_1_1_0",
            "    addq $1, 72(%rsp)\n    call method_span_target_1_1_0",
            93,
        ),
    ]
    for name, function, old, new, status in controls:
        changed = abi.mutate_body(full, function, old, new)
        abi.execute(args.artifacts, "mutant-" + name, changed, forward_cases, status, function)
    # Overcopy is checked against complete hidden-result canaries in direct calls.
    function = "method_span_target_1_1_2"
    changed = abi.mutate_body(
        direct, function, "    movq %rcx, 48(%r10)", "    movq %rcx, 48(%r10)\n    movq $0, 56(%r10)"
    )
    abi.execute(args.artifacts, "mutant-result-overcopy", changed, direct_cases, 94, function)
    for mode, offset in ((1, 88), (2, 136)):
        function = f"method_span_target_1_1_{mode}"
        changed = abi.mutate_body(
            direct, function, f"    movq %rax, -{offset}(%rbp)", f"    movq %r11, -{offset}(%rbp)"
        )
        abi.execute(args.artifacts, f"mutant-hidden-result-register-{mode}", changed, direct_cases, 94, function)
    summary = (
        f"PASS method span ABI: {len(direct_cases) + len(forward_cases)} native cases, "
        f"{len(controls) + 3} exact rejected mutants"
    )
    root = Path(__file__).resolve().parents[2]
    sources = [Path(__file__).resolve(), Path(__file__).resolve().with_suffix(".cpp"), Path(abi.__file__).resolve()] + [
        root / "compiler" / x for x in ("ir.hpp", "ir_verify.hpp", "x86.hpp", "ir_layout.hpp")
    ]
    receipt = {
        "status": "passed",
        "native_cases": len(direct_cases) + len(forward_cases),
        "rejected_mutants": len(controls) + 3,
        "python": sys.version,
        "python_optimization": sys.flags.optimize,
        "fixture_sha256": hashlib.sha256(args.ir_tests.read_bytes()).hexdigest(),
        "sources": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    }
    (args.artifacts / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (args.artifacts / "cases.json").write_text(
        json.dumps({"incoming": direct_cases, "outgoing": forward_cases}, indent=2) + "\n"
    )
    (args.artifacts / "summary.txt").write_text(summary + "\n")
    print(summary)
    print(f"Artifacts: {args.artifacts}")


if __name__ == "__main__":
    main()
