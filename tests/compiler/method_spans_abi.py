#!/usr/bin/env python3
"""Literal-layout, handwritten method-span ABI oracle (no compiler invocation).

The direct IR is a textual IR case (aurora-ir-check prints its assembly). The older logical-span oracle
provides assembly execution/canary plumbing only; parameter shapes, records,
method registers and results below are independently stated.
"""

import argparse
from pathlib import Path
import tempfile
import logical_spans_abi as abi

# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = Path(__file__).resolve().parent / "ir" / "method-spans-ir" / "abi.air"


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
    raw = abi.command([args.ir_tests.resolve(), "--output", AIR, "method-spans-abi"]).stdout.decode()
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
    abi.run_programs(
        args.artifacts,
        [("incoming-generated-results", direct, direct_cases), ("outgoing-handwritten-methods", full, forward_cases)],
    )
    summary = f"PASS method span ABI: {len(direct_cases) + len(forward_cases)} native cases"
    print(summary)
    print(f"Artifacts: {args.artifacts}")


if __name__ == "__main__":
    main()
