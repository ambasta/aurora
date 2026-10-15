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


def paired_cases(mode):
    result = []
    for arity in range(5):
        values = [101 + index for index in range(arity)]
        for depth in ([0] if mode == "direct" else range(3)):
            direct = mode == "direct"
            result.append(
                {
                    "name": f"paired {mode} arity {arity} retained depth {depth}",
                    "target": f"paired_target_{arity}" if direct else f"paired_forward_{arity}_{depth}",
                    "input": [],
                    # Literal first-root field 73 and second-root field 239.
                    # Targets read the second through a copied getter and a
                    # legacy single-root helper. Forwarders read it once more.
                    "answer": (551 + sum(values) if direct else
                               (281 if mode == "outgoing" else 790 + sum(values)) + abi.retained(depth)),
                    "probes": int(mode == "outgoing"),
                    "registers": values,
                }
            )
    return result


def paired_target(arity):
    code = abi.align()
    code += "    cmpq $receiver, (%r10)\n    jne .Labi_record_fail\n"
    code += "    cmpq $second_receiver, 8(%r10)\n    jne .Labi_record_fail\n"
    for index, register in enumerate(abi.REGISTERS[:arity]):
        code += f"    cmpq ${101 + index}, {register}\n    jne .Labi_record_fail\n"
    return code + "    incq probe_calls(%rip)\n" + abi.clobber(42) + "    ret\n"


def paired_harness(text, selected):
    incoming = "    leaq receiver(%rip), %r10\n"
    abi.require(text.count(incoming) == len(selected), "one paired incoming record per case")
    text = text.replace(incoming, "    leaq paired_record(%rip), %r10\n")
    marker = "    incq completed(%rip)\n"
    parts = text.split(marker)
    abi.require(len(parts) == len(selected) + 1, "one paired completion observation per case")
    text = parts[0]
    for index, part in enumerate(parts[1:]):
        for actual, expected, size in (
            ("second_receiver_left", "literal_second_receiver", 64),
            ("paired_record_left", "literal_paired_record", 32),
        ):
            text += f"    leaq {actual}(%rip), %rdi\n"
            text += abi.compare("%rdi", expected, size, f"paired_{index}_{actual}", "canary")
        text += marker + part
    second = [181, abi.REGION + 1, abi.ALLOCATION + 1, 37, 1, 239]
    text += "\n.data\n.balign 16\n"
    text += abi.blob("second_receiver_left", [abi.LEFT])
    text += abi.blob("second_receiver", second)
    text += abi.blob("second_receiver_right", [abi.RIGHT])
    text += abi.blob("literal_second_receiver", [abi.LEFT, *second, abi.RIGHT])
    text += abi.blob("paired_record_left", [abi.LEFT])
    text += abi.blob("paired_record", ["receiver", "second_receiver"])
    text += abi.blob("paired_record_right", [abi.RIGHT])
    text += abi.blob("literal_paired_record", [abi.LEFT, "receiver", "second_receiver", abi.RIGHT])
    return text


def bounded_shapes():
    return [(roots, mutable, tail) for roots in range(1, 4)
            for mutable in range(2) for tail in range(7 - roots)]


def bounded_value(ordinal):
    return 97 if ordinal == 0 else 239 + 71 * (ordinal - 1)


def bounded_cases(mode):
    result = []
    for roots, mutable, tail in bounded_shapes():
        suffix = f"{roots}_{mutable}_{tail}"
        for depth in ([0] if mode == "direct" else range(3)):
            answer = sum(bounded_value(index) for index in range(roots)) + sum(range(101, 101 + tail))
            if mode != "direct":
                answer = (42 if mode == "outgoing" else answer) + bounded_value(roots - 1) + abi.retained(depth)
            result.append({
                "name": f"bounded {mode} roots {roots} mutable {mutable} tail {tail} depth {depth}",
                "target": f"bounded_target_{suffix}" if mode == "direct" else f"bounded_forward_{suffix}_{depth}",
                "input": [], "answer": answer, "probes": int(mode == "outgoing"),
                "registers": list(range(101, 101 + tail)), "roots": roots,
            })
    return result


def bounded_target(roots, tail):
    code = abi.align()
    if roots == 1:
        code += "    cmpq $receiver, %r10\n    jne .Labi_record_fail\n"
    else:
        for ordinal in range(roots):
            label = "receiver" if ordinal == 0 else f"bounded_receiver_{ordinal}"
            code += f"    cmpq ${label}, {ordinal * 8}(%r10)\n    jne .Labi_record_fail\n"
    for index, register in enumerate(abi.REGISTERS[:tail]):
        code += f"    cmpq ${101 + index}, {register}\n    jne .Labi_record_fail\n"
    return code + "    incq probe_calls(%rip)\n" + abi.clobber(42) + "    ret\n"


def bounded_harness(text, selected):
    incoming = "    leaq receiver(%rip), %r10\n"
    chunks = text.split(incoming)
    abi.require(len(chunks) == len(selected) + 1, "one bounded root input per case")
    text = chunks[0]
    for case, chunk in zip(selected, chunks[1:]):
        label = "receiver" if case["roots"] == 1 else f"bounded_record_{case['roots']}"
        text += f"    leaq {label}(%rip), %r10\n" + chunk
    marker = "    incq completed(%rip)\n"
    chunks = text.split(marker)
    abi.require(len(chunks) == len(selected) + 1, "one bounded completion per case")
    text = chunks[0]
    for index, (case, chunk) in enumerate(zip(selected, chunks[1:])):
        for ordinal in range(1, case["roots"]):
            text += f"    leaq bounded_receiver_{ordinal}_left(%rip), %rdi\n"
            text += abi.compare("%rdi", f"literal_bounded_receiver_{ordinal}", 64,
                                f"bounded_{index}_{ordinal}", "canary")
        if case["roots"] > 1:
            roots = case["roots"]
            reserved = (8 * roots + 15) & ~15
            text += f"    leaq bounded_record_{roots}_left(%rip), %rdi\n"
            text += abi.compare("%rdi", f"literal_bounded_record_{roots}", reserved + 16,
                                f"bounded_record_{index}", "canary")
        text += marker + chunk
    text += "\n.data\n.balign 16\n"
    for ordinal in range(1, 6):
        words = [181 + ordinal, abi.REGION + ordinal, abi.ALLOCATION + ordinal, 37 + ordinal, 1,
                 bounded_value(ordinal)]
        text += abi.blob(f"bounded_receiver_{ordinal}_left", [abi.LEFT])
        text += abi.blob(f"bounded_receiver_{ordinal}", words)
        text += abi.blob(f"bounded_receiver_{ordinal}_right", [abi.RIGHT])
        text += abi.blob(f"literal_bounded_receiver_{ordinal}", [abi.LEFT, *words, abi.RIGHT])
    for roots in range(2, 4):
        words = ["receiver", *(f"bounded_receiver_{ordinal}" for ordinal in range(1, roots))]
        if roots % 2:
            words.append(0xABABABABABABABAB)
        text += abi.blob(f"bounded_record_{roots}_left", [abi.LEFT])
        text += abi.blob(f"bounded_record_{roots}", words)
        text += abi.blob(f"bounded_record_{roots}_right", [abi.RIGHT])
        text += abi.blob(f"literal_bounded_record_{roots}", [abi.LEFT, *words, abi.RIGHT])
    return text


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
    # Separate observations enter the paired ABI with a literal two-pointer
    # record, then observe generated forwarding through handwritten callees.
    # An ordinary nested helper clobbers every caller-saved register so keeping
    # the second pointer live in R11 cannot accidentally pass the getter cases.
    paired_observed = abi.replace_body(
        raw, "paired_scalar_clobber", abi.align() + abi.clobber(0) + "    ret\n"
    )
    paired_outgoing = paired_observed
    for arity in range(5):
        paired_outgoing = abi.replace_body(paired_outgoing, f"paired_target_{arity}", paired_target(arity))
    paired_assembly, paired_selected = {}, {}
    for mode in ("direct", "generated", "outgoing"):
        selected = paired_cases(mode)
        assembly = paired_outgoing if mode == "outgoing" else paired_observed
        assembly += paired_harness(harness(selected), selected)
        paired_assembly[mode], paired_selected[mode] = assembly, selected
        abi.execute(args.artifacts, "paired-" + mode, assembly, selected)
    paired_controls = [
        ("second-entry-selector", "direct", "paired_target_0",
         "    movq 8(%r10), %r11", "    movq (%r10), %r11", 93),
        ("first-outgoing-pointer", "outgoing", "paired_forward_0_0",
         "    movq %r10, 0(%rsp)", "    movq $0, 0(%rsp)", 91),
        ("second-outgoing-pointer", "outgoing", "paired_forward_0_0",
         "    movq %r10, 8(%rsp)", "    movq $0, 8(%rsp)", 91),
        ("paired-odd-alignment", "outgoing", "paired_forward_0_1",
         "    subq $8, %rsp\n    call paired_target_0", "    nop\n    call paired_target_0", 92),
        ("paired-retained-operand", "outgoing", "paired_forward_0_1",
         "    call paired_target_0", "    addq $1, 24(%rsp)\n    call paired_target_0", 93),
    ]
    for name, mode, function, old, new, status in paired_controls:
        changed = abi.mutate_body(paired_assembly[mode], function, old, new)
        abi.execute(args.artifacts, "mutant-" + name, changed, paired_selected[mode], status, function)
    bounded_outgoing = paired_observed
    for roots, mutable, tail in bounded_shapes():
        bounded_outgoing = abi.replace_body(bounded_outgoing, f"bounded_target_{roots}_{mutable}_{tail}",
                                           bounded_target(roots, tail))
    bounded_assembly, bounded_selected = {}, {}
    for mode in ("direct", "generated", "outgoing"):
        selected = bounded_cases(mode)
        assembly = bounded_outgoing if mode == "outgoing" else paired_observed
        assembly += bounded_harness(harness(selected), selected)
        bounded_assembly[mode], bounded_selected[mode] = assembly, selected
        abi.execute(args.artifacts, "bounded-" + mode, assembly, selected)
    bounded_controls = []
    for roots in range(2, 4):
        for ordinal in range(roots):
            function = f"bounded_forward_{roots}_0_0_0"
            old = f"    movq %r10, {ordinal * 8}(%rsp)"
            bounded_controls.append((f"root-{roots}-lane-{ordinal}", "outgoing", function,
                                     old, f"    movq $0, {ordinal * 8}(%rsp)", 91))
        if roots % 2:
            reserved = (roots * 8 + 15) & ~15
            function = f"bounded_forward_{roots}_0_0_1"
            bounded_controls.append((f"odd-tuple-{roots}-retained", "outgoing", function,
                                     f"    call bounded_target_{roots}_0_0",
                                     f"    addq $1, {reserved + 8}(%rsp)\n    call bounded_target_{roots}_0_0", 93))
    for name, mode, function, old, new, status in bounded_controls:
        changed = abi.mutate_body(bounded_assembly[mode], function, old, new)
        abi.execute(args.artifacts, "mutant-" + name, changed, bounded_selected[mode], status, function)
    native_cases = len(direct_cases) + len(forward_cases) + sum(map(len, paired_selected.values())) + sum(map(len, bounded_selected.values()))
    rejected_mutants = len(controls) + 2 + len(paired_controls) + len(bounded_controls)
    summary = (
        f"PASS borrowed object ABI: {native_cases} native cases, "
        f"{rejected_mutants} exact rejected mutants"
    )
    abi.require(args.ir_tests.read_bytes() == fixture_before, "fixture changed during ABI gate")
    for path, content in bound_inputs.items():
        abi.require(path.read_bytes() == content, f"bound ABI source changed: {path}")
    receipt = {
        "status": "passed",
        "native_cases": native_cases,
        "rejected_mutants": rejected_mutants,
        "python": sys.version,
        "python_optimization": sys.flags.optimize,
        "fixture_sha256": hashlib.sha256(args.ir_tests.read_bytes()).hexdigest(),
        "sources": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
    }
    (args.artifacts / "run.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (args.artifacts / "cases.json").write_text(
        json.dumps({"incoming": direct_cases, "outgoing": forward_cases, "paired": paired_selected, "bounded": bounded_selected}, indent=2) + "\n"
    )
    (args.artifacts / "summary.txt").write_text(summary + "\n")
    print(summary)
    print(f"Artifacts: {args.artifacts}")


if __name__ == "__main__":
    main()
