#!/usr/bin/env python3
"""Adapted literal-layout, handwritten borrowed-object ABI oracle (no compiler invocation).

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
    return (
        [(n, 1 << p) for n in range(1, 6) for p in range(n)] + [(5, 31), (5, 21), (5, 10)] + [(n, -1) for n in range(6)]
    )


def record(n, mask, domain, transform=0, incoming=False):
    if mask < 0:
        return []
    words = []
    for p in range(n):
        if mask & (1 << p):
            kind = int(domain == "owner" or (domain == "mixed" and p % 2 == 0))
            payload = [abi.REGION + p, abi.ALLOCATION + 101 + p, 29 + p, 1] if kind else ["array_bytes", 0, 0, 0]
            words += [kind, *payload, 2 + p + 2 * transform, 0 if transform else 17 + p]
        elif p % 3 == 1:
            words += [(0xA5A5A5A5A5A5A500 if incoming else 0) + 197 + p]
        else:
            words += [(1 << 40) + 31 + p]
    if not incoming and len(words) % 2:
        words.append(0)
    return words


def target(mode, n, mask):
    code = abi.align() + "    cmpq $receiver, %r10\n    jne .Labi_record_fail\n"
    if mask < 0:
        for i, register in enumerate(abi.REGISTERS[:n]):
            code += f"    cmpq ${101 + i}, {register}\n    jne .Labi_record_fail\n"
        code += "    movq %r11, method_hidden(%rip)\n"
    else:
        code += "    movq %rax, method_hidden(%rip)\n"
        code += "    movq expected_record(%rip), %rsi\n    xorq %rcx, %rcx\n"
        code += """.Lborrow_compare_SUFFIX:
    movzbq (%r11,%rcx), %rdx
    cmpb (%rsi,%rcx), %dl
    jne .Labi_record_fail
    incq %rcx
    cmpq expected_size(%rip), %rcx
    jne .Lborrow_compare_SUFFIX
"""
    code += "    incq probe_calls(%rip)\n"
    if mode:
        code += "    movq method_hidden(%rip), %rdi\n    movq $123, (%rdi)\n"
    return code + abi.clobber(42 if mode == 0 else 0) + "    ret\n"


def cases(direct=False):
    result = []
    for n, mask in shapes():
        for mode in range(2):
            suffix = f"{n}_{'scalar' if mask < 0 else mask}_{mode}"
            for domain in ("array", "owner", "mixed"):
                if direct:
                    case = {
                        "name": f"generated result {suffix} {domain}",
                        "target": f"borrow_object_target_{suffix}",
                        "input": record(n, mask, domain, incoming=True),
                        "answer": 42 if mode == 0 else 0,
                    }
                    if mode:
                        case["combined"] = mask >= 0
                        case["result"] = [123] + [0xCDCDCDCDCDCDCDCD] * 6
                    if mask < 0:
                        case["registers"] = [101 + i for i in range(n)]
                    result.append(case)
                    continue
                for depth in range(3):
                    for transform in range(2):
                        result.append(
                            {
                                "name": f"{domain} {suffix} depth {depth} empty-window {transform}",
                                "target": f"borrow_object_forward_{suffix}_{depth}_{transform}",
                                "input": record(n, mask, domain, incoming=True),
                                "output": record(n, mask, domain, transform),
                                "answer": (123 if mode == 1 else 42) + abi.retained(depth),
                                "probes": 1,
                                "registers": [101 + i for i in range(n)] if mask < 0 else [],
                            }
                        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ir_tests", type=Path)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    if args.artifacts is None:
        args.artifacts = Path(tempfile.mkdtemp(prefix="borrowed-objects-abi-"))
    else:
        args.artifacts.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    sources = [Path(__file__).resolve(), Path(__file__).resolve().with_suffix(".cpp"), Path(abi.__file__).resolve()]
    sources += sorted((root / "compiler").glob("*.hpp"))
    bound_inputs = {path: path.read_bytes() for path in sources}
    fixture_before = args.ir_tests.read_bytes()
    commands = []
    original_command = abi.command

    def recorded_command(argv, expected=0):
        ordinal = len(commands)
        entry = {"argv": [str(part) for part in argv], "expected_status": expected}
        commands.append(entry)
        (args.artifacts / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        result = original_command(argv, expected)
        for channel in ("stdout", "stderr"):
            (args.artifacts / f"command-{ordinal:03d}.{channel}.bin").write_bytes(getattr(result, channel))
        abi.require(not result.stderr, f"ABI command emitted unexpected stderr: {argv}: {result.stderr!r}")
        entry["actual_status"] = result.returncode
        (args.artifacts / "commands.json").write_text(json.dumps(commands, indent=2) + "\n")
        return result

    abi.command = recorded_command
    raw = abi.command([args.ir_tests.resolve()]).stdout.decode()
    (args.artifacts / "generated.s").write_text(raw)
    extra = abi.blob("method_hidden", [0])
    observed = raw
    outgoing = observed
    for n, mask in shapes():
        for mode in range(2):
            suffix = f"{n}_{'scalar' if mask < 0 else mask}_{mode}"
            outgoing = abi.replace_body(
                outgoing, f"borrow_object_target_{suffix}", target(mode, n, mask).replace("SUFFIX", suffix)
            )
    direct_cases = cases(True)
    forward_cases = cases()
    # The compiler is the one stack-note authority. The reused handwritten
    # harness's standalone footer must not duplicate it (GNU as 2.47 warns).
    stack_note = '.section .note.GNU-stack,"",@progbits\n'
    abi.require(raw.count(stack_note) == 1, "producer must emit one compiler-owned stack note")

    def harness(selected):
        text = abi.harness(selected, True)
        abi.require(
            text.endswith(stack_note) and text.count(stack_note) == 1,
            "standalone harness must have exactly one known stack-note footer",
        )
        return text[: -len(stack_note)]

    direct = observed + harness(direct_cases) + "\n.data\n" + extra
    full = outgoing + harness(forward_cases) + "\n.data\n" + extra
    abi.execute(args.artifacts, "incoming-generated-results", direct, direct_cases)
    abi.execute(args.artifacts, "outgoing-handwritten-helpers", full, forward_cases)
    # Every control must produce the oracle's exact failure status and case,
    # rather than an accidental trap, crash, or an always-failing baseline.
    controls = []
    target_name = "borrow_object_forward_1_1_0_0_0"
    controls += [
        ("incoming-seventh-word", target_name, "    movq %rax, -8(%rbp)", "    movq $0, -8(%rbp)", 91),
        ("outgoing-seventh-word", target_name, "    movq %rax, 48(%rsp)", "    movq $0, 48(%rsp)", 91),
        (
            "receiver-register",
            target_name,
            "    call borrow_object_target_1_1_0",
            "    xorq %r10, %r10\n    call borrow_object_target_1_1_0",
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
    odd = "borrow_object_forward_1_1_0_1_0"
    controls += [
        (
            "odd-stack-alignment",
            odd,
            "    subq $8, %rsp\n    call borrow_object_target_1_1_0",
            "    nop\n    call borrow_object_target_1_1_0",
            92,
        ),
        (
            "saved-operand",
            odd,
            "    call borrow_object_target_1_1_0",
            "    addq $1, 72(%rsp)\n    call borrow_object_target_1_1_0",
            93,
        ),
    ]
    for name, function, old, new, status in controls:
        changed = abi.mutate_body(full, function, old, new)
        abi.execute(args.artifacts, "mutant-" + name, changed, forward_cases, status, function)
    # A copied result occupies exactly one word; the remaining literal canaries stay unchanged.
    function = "borrow_object_target_1_1_1"
    changed = abi.mutate_body(
        direct, function, "    movq %rax, 0(%r10)", "    movq %rax, 0(%r10)\n    movq $0, 8(%r10)"
    )
    abi.execute(args.artifacts, "mutant-result-overcopy", changed, direct_cases, 94, function)
    changed = abi.mutate_body(direct, function, "    movq %rax, -88(%rbp)", "    movq %r11, -88(%rbp)")
    abi.execute(args.artifacts, "mutant-hidden-result-register", changed, direct_cases, 94, function)
    summary = (
        f"PASS borrowed object ABI: {len(direct_cases) + len(forward_cases)} native cases, "
        f"{len(controls) + 2} exact rejected mutants"
    )
    abi.require(args.ir_tests.read_bytes() == fixture_before, "fixture changed during ABI gate")
    for path, content in bound_inputs.items():
        abi.require(path.read_bytes() == content, f"bound ABI source changed: {path}")
    receipt = {
        "status": "passed",
        "native_cases": len(direct_cases) + len(forward_cases),
        "rejected_mutants": len(controls) + 2,
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
