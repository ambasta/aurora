#!/usr/bin/env python3
"""Independent literal-layout native oracle for readonly logical span boundaries.

The prebuilt C++ fixture constructs verified IR without parsing source. Handwritten
assembly supplies every incoming record and observes every outgoing record. Seven
literal words, including the entire immutable owner descriptor, are checked; no
production ABI/layout helper supplies expectations. Runtime stubs intentionally
clobber caller-saved registers and check actual entry stack alignment. They model
only the private calling boundary, not allocator correctness (covered separately).

No C++ compilation or hosted runtime is performed here. as/ld build freestanding
native executables. All assertions use explicit require() under python -O too.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import subprocess
import sys
import tempfile

REGION = 0x1122334455667788
ALLOCATION = 0x2132435465768798
SAVED = 4294967313
LEFT = 0x5152535455565758
RIGHT = 0x6162636465666768
REGISTERS = ("%rdi", "%rsi", "%rdx", "%rcx", "%r8", "%r9")
CALLEE_SAVED = ("%rbx", "%rbp", "%r12", "%r13", "%r14", "%r15")


def require(value, message):
    if not value:
        raise AssertionError(message)


def command(args, expected=0):
    result = subprocess.run(
        [str(arg) for arg in args],
        capture_output=True,
        timeout=90,
        check=False,
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
    )
    require(
        result.returncode == expected,
        f"{args}: expected {expected}, got {result.returncode}; stdout={result.stdout!r}; stderr={result.stderr!r}",
    )
    return result


def body(assembly, name):
    pattern = rf"(?m)^{re.escape(name)}:\n([\s\S]*?)^\.size {re.escape(name)},[^\n]*\n"
    matches = list(re.finditer(pattern, assembly))
    require(len(matches) == 1, f"one private body for {name}, got {len(matches)}")
    return matches[0]


def replace_body(assembly, name, code):
    match = body(assembly, name)
    return assembly[: match.start(1)] + code + assembly[match.end(1) :]


def mutate_body(assembly, name, old, new):
    match = body(assembly, name)
    code = match[1]
    require(code.count(old) == 1, f"{name}: exact unique mutant site {old!r}")
    return replace_body(assembly, name, code.replace(old, new))


def shape_cases():
    # This separately authored enumeration is intentionally not read from IR.
    shapes = [(arity, 1 << position) for arity in range(1, 7) for position in range(arity)]
    return shapes + [(2, 3), (3, 5), (4, 10), (6, 63), (6, 21)]


def retained(depth):
    return sum(SAVED + i for i in range(depth))


def record(arity, mask, transform=0, domain="array", incoming=False):
    words = []
    for position in range(arity):
        if mask & (1 << position):
            kind = int(domain == "owner" or (domain == "mixed" and position % 2 == 0))
            start = (7 if transform == 2 else 2) + position
            length = 3 if transform == 2 else 17 + position
            payload = [REGION + position, ALLOCATION + position, 29 + position, 1] if kind else ["array_bytes", 0, 0, 0]
            words.extend([kind, *payload, start, length])
        elif position % 3 == 0:
            words.append((1 << 40) + 31 + position)
        elif position % 3 == 1:
            # Deliberately dirty input padding must be zero in the packed output.
            words.append((0xA5A5A5A5A5A5A500 if incoming else 0) + 197 + position)
        else:
            words.append(1)
    if not incoming and len(words) % 2:
        words.append(0)
    return words


def blob(label, words):
    return label + ":\n" + "".join(f"    .quad {word}\n" for word in words)


def align():
    return "    testq $7, %rsp\n    jne .Labi_alignment_fail\n    testq $8, %rsp\n    je .Labi_alignment_fail\n"


def clobber(result=42):
    return "".join(f"    movq ${-201 - i}, {register}\n" for i, register in enumerate((*REGISTERS, "%r10", "%r11"))) + (
        f"    movq ${result}, %rax\n"
    )


def compare(pointer, expected, size, suffix, failure="record"):
    return f"""    leaq {expected}(%rip), %rsi
    xorq %rcx, %rcx
.Lcompare_{suffix}:
    movzbq ({pointer},%rcx), %rdx
    cmpb (%rsi,%rcx), %dl
    jne .Labi_{failure}_fail
    incq %rcx
    cmpq ${size}, %rcx
    jne .Lcompare_{suffix}
"""


def probe():
    # Dynamic-array mint cases also verify all bytes behind the local pointer;
    # every other case compares all eight bytes of the literal pointer itself.
    return (
        align()
        + """    cmpq $0, dynamic_array(%rip)
    je .Lprobe_literal
    cmpq $0, 0(%r11)
    jne .Labi_record_fail
    movq 8(%r11), %rdi
    leaq array_bytes(%rip), %rsi
    xorq %rcx, %rcx
.Lprobe_array_bytes:
    movzbq (%rdi,%rcx), %rdx
    cmpb (%rsi,%rcx), %dl
    jne .Labi_record_fail
    incq %rcx
    cmpq $32, %rcx
    jne .Lprobe_array_bytes
    movq expected_record(%rip), %rsi
    xorq %rcx, %rcx
    jmp .Lprobe_compare
.Lprobe_literal:
    movq expected_record(%rip), %rsi
    xorq %rcx, %rcx
.Lprobe_compare:
    cmpq $0, dynamic_array(%rip)
    je .Lprobe_byte
    cmpq $8, %rcx
    jb .Lprobe_byte
    cmpq $16, %rcx
    jb .Lprobe_next
.Lprobe_byte:
    movzbq (%r11,%rcx), %rdx
    cmpb (%rsi,%rcx), %dl
    jne .Labi_record_fail
.Lprobe_next:
    incq %rcx
    cmpq expected_size(%rip), %rcx
    jne .Lprobe_compare
    incq probe_calls(%rip)
"""
        + clobber()
        + "    ret\n"
    )


def instrument(assembly):
    for name in [f"abi_probe_{arity}_{mask}" for arity, mask in shape_cases()] + ["abi_probe_one"]:
        # Tail transfer retains exactly the real generated caller's entry RSP.
        assembly = replace_body(assembly, name, "    jmp handwritten_probe\n")
    return assembly + "\n.text\nhandwritten_probe:\n" + probe()


def runtime():
    # Literal descriptor validation deliberately does not read production headers.
    code = "\n.text\n__au_runtime_bytes_borrow_span:\n" + align()
    code += "    movq %rsi, %r10\n"
    code += compare("%rdi", "literal_owner", 32, "borrow_descriptor", "runtime")
    code += "    movq $1, 0(%r10)\n"
    for offset in range(0, 32, 8):
        code += f"    movq {offset}(%rdi), %rax\n    movq %rax, {offset + 8}(%r10)\n"
    code += "    movq $0, 40(%r10)\n    movq $29, 48(%r10)\n"
    code += "    incq borrow_calls(%rip)\n" + clobber(29) + "    ret\n"
    code += "__au_runtime_bytes_at:\n" + align()
    code += "    cmpq $6, %rsi\n    jne .Labi_runtime_fail\n"
    code += compare("%rdi", "literal_owner", 32, "at_descriptor", "runtime")
    code += "    incq at_calls(%rip)\n" + clobber(231) + "    ret\n"
    return code


def handwritten_result(mode):
    code = align()
    code += "    cmpq $receiver, %r10\n    jne .Labi_record_fail\n"
    if mode == 3:
        code += "    movq %rax, %r9\n"
        code += compare("%r11", "literal_class_arguments", 48, "class_arguments")
    else:
        values = [] if mode == 0 else [3] if mode == 1 else [71, 72, 73, 74, 75, 3]
        for register, value in zip(REGISTERS, values):
            code += f"    cmpq ${value}, {register}\n    jne .Labi_record_fail\n"
        code += "    movq %r11, %r9\n"
    # Require separate receiver/result and, for combined mode, record/result ranges.
    code += """    leaq 48(%r10), %rdx
    cmpq %r9, %rdx
    jbe .Lresult_receiver_disjoint_MODE
    leaq 56(%r9), %rdx
    cmpq %r10, %rdx
    ja .Labi_record_fail
.Lresult_receiver_disjoint_MODE:
""".replace("MODE", str(mode))
    if mode == 3:
        code += """    leaq 48(%r11), %rdx
    cmpq %r9, %rdx
    jbe .Lresult_record_disjoint
    leaq 56(%r9), %rdx
    cmpq %r11, %rdx
    ja .Labi_record_fail
.Lresult_record_disjoint:
"""
    for offset, word in enumerate([1, REGION, ALLOCATION, 29, 1, 3, 7]):
        code += f"    movabsq ${word}, %rdx\n    movq %rdx, {offset * 8}(%r9)\n"
    return code + clobber(0) + "    ret\n"


def cases(owner=False, handwritten=False):
    result = []
    for domain in ("owner", "mixed") if owner else ("array",):
        for arity, mask in shape_cases():
            for transform in range(3):
                for depth in range(3):
                    result.append(
                        {
                            "name": f"{domain} forwarding {arity}/{mask} transform {transform} depth {depth}",
                            "target": f"abi_forward_{arity}_{mask}_{transform}_{depth}",
                            "input": record(arity, mask, domain=domain, incoming=True),
                            "output": record(arity, mask, transform, domain),
                            "answer": 42 + retained(depth),
                            "probes": 1,
                        }
                    )
    for domain in ("array", "owner") if owner else ("array",):
        for depth in range(4):
            result.append(
                {
                    "name": f"{domain} checked read depth {depth}",
                    "target": f"abi_read_{depth}",
                    "input": record(1, 1, domain=domain, incoming=True),
                    "answer": (231 if domain == "owner" else 53) + retained(depth),
                    "at": int(domain == "owner"),
                }
            )
    for depth in range(3):
        result.append(
            {
                "name": f"local array mint/copy/window depth {depth}",
                "target": f"abi_array_mint_{depth}",
                "output": [0, 0, 0, 0, 0, 3, 7, 0],
                "dynamic": True,
                "answer": 42 + retained(depth),
                "probes": 1,
            }
        )
    if not owner:
        return result
    for mode in range(4):
        values = [] if mode == 0 else [3] if mode == 1 else [71, 72, 73, 74, 75, 3]
        incoming = [7, 72, 19, 74, 3, 1] if mode == 3 else []
        result.append(
            {
                "name": f"receiver result incoming hidden mode {mode}",
                "target": f"abi_result_{mode}",
                "input": incoming,
                "result": [1, REGION, ALLOCATION, 29, 1, 3, 7],
                "registers": values if mode != 3 else [],
                "combined": mode == 3,
                "answer": 0,
                "borrow": int(not handwritten),
            }
        )
        for depth in range(3):
            result.append(
                {
                    "name": f"receiver result outgoing hidden mode {mode} depth {depth}",
                    "target": f"abi_use_result_{mode}_{depth}",
                    "output": [1, REGION, ALLOCATION, 29, 1, 3, 7, 0],
                    "answer": 42 + retained(depth),
                    "probes": 1,
                    "borrow": int(not handwritten),
                }
            )
    for depth in range(4):
        result.append(
            {
                "name": f"borrow preserves current scalar and saved depth {depth}",
                "target": f"abi_borrow_{depth}",
                "output": [1, REGION, ALLOCATION, 29, 1, 3, 7, 0],
                "answer": 123456789 + retained(depth),
                "borrow": 1,
                "probes": 1,
            }
        )
    return result


def harness(test_cases, owner):
    code = "\n.text\n.globl _start\n_start:\n"
    data = "\n.data\n.balign 16\n"
    for index, case in enumerate(test_cases):
        prefix = f"case_{index}"
        code += f"    movq ${index}, active_case(%rip)\n"
        code += f"    leaq {prefix}_expected(%rip), %rdx\n    movq %rdx, expected_record(%rip)\n"
        expected = case.get("output", [0])
        code += f"    movq ${8 * len(expected)}, expected_size(%rip)\n"
        code += f"    movq ${int(case.get('dynamic', False))}, dynamic_array(%rip)\n"
        for counter in ("borrow_calls", "at_calls", "probe_calls"):
            code += f"    movq $0, {counter}(%rip)\n"
        code += "    movq %rsp, saved_rsp(%rip)\n"
        for i, register in enumerate(CALLEE_SAVED):
            code += f"    movabsq ${0x7172737475767778 + i}, {register}\n"
        code += clobber(-17)
        for register, value in zip(REGISTERS, case.get("registers", [])):
            code += f"    movq ${value}, {register}\n"
        code += "    leaq receiver(%rip), %r10\n"
        code += f"    leaq {prefix}_input(%rip), %r11\n"
        code += f"    leaq {prefix}_result(%rip), %rax\n"
        if "result" in case and not case.get("combined"):
            code += f"    leaq {prefix}_result(%rip), %r11\n"
        code += f"    call {case['target']}\n"
        code += f"    movabsq ${case['answer']}, %rdx\n    cmpq %rdx, %rax\n    jne .Labi_result_fail\n"
        code += "    cmpq saved_rsp(%rip), %rsp\n    jne .Labi_canary_fail\n"
        for i, register in enumerate(CALLEE_SAVED):
            code += f"    movabsq ${0x7172737475767778 + i}, %rdx\n"
            code += f"    cmpq %rdx, {register}\n    jne .Labi_canary_fail\n"
        for counter, key in (("borrow_calls", "borrow"), ("at_calls", "at"), ("probe_calls", "probes")):
            code += f"    cmpq ${case.get(key, 0)}, {counter}(%rip)\n    jne .Labi_runtime_fail\n"
        incoming = case.get("input", [])
        data += blob(prefix + "_input_left", [LEFT]) + blob(prefix + "_input", incoming)
        data += blob(prefix + "_input_right", [RIGHT])
        data += blob(prefix + "_original", [LEFT, *incoming, RIGHT])
        data += blob(prefix + "_expected", expected)
        data += blob(prefix + "_result_left", [LEFT])
        data += prefix + "_result:\n    .fill 56, 1, 205\n"
        data += blob(prefix + "_result_right", [RIGHT])
        result = case.get("result", [0xCDCDCDCDCDCDCDCD] * 7)
        data += blob(prefix + "_expected_result", [LEFT, *result, RIGHT])
        for actual, want, size, suffix in (
            (prefix + "_input_left", prefix + "_original", 16 + len(incoming) * 8, "input"),
            (prefix + "_result_left", prefix + "_expected_result", 72, "result"),
            ("receiver", "literal_receiver", 48, "receiver"),
        ):
            code += f"    leaq {actual}(%rip), %rdi\n"
            code += compare("%rdi", want, size, prefix + "_" + suffix, "canary")
        code += "    incq completed(%rip)\n"
    code += """    movq $1, %rax
    movq $1, %rdi
    leaq completed(%rip), %rsi
    movq $8, %rdx
    syscall
    movq $60, %rax
    xorq %rdi, %rdi
    syscall
"""
    for status, kind in ((91, "record"), (92, "alignment"), (93, "result"), (94, "canary"), (95, "runtime")):
        code += f".Labi_{kind}_fail:\n    movq ${status}, %r8\n    jmp .Labi_failure\n"
    code += """.Labi_failure:
    movq $1, %rax
    movq $1, %rdi
    leaq active_case(%rip), %rsi
    movq $8, %rdx
    syscall
    movq $60, %rax
    movq %r8, %rdi
    syscall
"""
    owner_words = [REGION, ALLOCATION, 29, 1]
    data += blob("receiver", [73, *owner_words, 97])
    data += blob("literal_receiver", [73, *owner_words, 97])
    data += blob("literal_owner", owner_words)
    data += blob("literal_class_arguments", [7, 72, 19, 74, 3, 1])
    data += "array_bytes:\n    .byte " + ",".join(str((11 + i * 7) % 256) for i in range(32)) + "\n"
    for label in (
        "active_case",
        "completed",
        "saved_rsp",
        "expected_record",
        "expected_size",
        "dynamic_array",
        "borrow_calls",
        "at_calls",
        "probe_calls",
    ):
        data += blob(label, [0])
    return code + (runtime() if owner else "") + data + '\n.section .note.GNU-stack,"",@progbits\n'


def private_symbols(symbols):
    # Preserve the lowercase-t presence check, including duplicate entries.
    return set(re.findall(r"\bt (\S+)$", symbols, re.M))


def execute(directory, name, assembly, test_cases, expected=0, rejected_target=None):
    source = directory / (name + ".s")
    obj = directory / (name + ".o")
    executable = directory / (name + ".elf")
    source.write_text(assembly)
    command(["as", "--64", source, "-o", obj])
    undefined = command(["nm", "-u", obj]).stdout
    require(not undefined.strip(), f"{name}: unresolved imports: {undefined!r}")
    symbols = private_symbols(command(["nm", obj]).stdout.decode())
    for target in {case["target"] for case in test_cases if not case["target"].startswith("abi_array_mint_")}:
        require(target in symbols, f"{target}: private boundary linkage")
    command(["ld", "-o", executable, obj])
    result = command([executable], expected)
    require(len(result.stdout) == 8, f"{name}: exactly one complete native observation")
    observed = int.from_bytes(result.stdout, "little")
    if expected == 0:
        require(observed == len(test_cases), f"{name}: all boundaries ran ({observed}/{len(test_cases)})")
    else:
        require(observed < len(test_cases), f"{name}: mutant failed inside a known boundary")
        require(test_cases[observed]["target"] == rejected_target, f"{name}: exact targeted boundary rejected")
    receipt = {
        "status": result.returncode,
        "observation": observed,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    if expected:
        receipt["rejected_case"] = test_cases[observed]["name"]
    (directory / (name + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"PASS logical span ABI {name}: {len(test_cases) if not expected else receipt['rejected_case']}", flush=True)
    return observed


def main():
    require(
        private_symbols(
            "0 t target\n0 t target\n0 T public\n0 d datum\n0 t target_suffix\n0 t prefix_target\n0 t target.suffix\n"
        )
        == {"target", "target_suffix", "prefix_target", "target.suffix"},
        "private symbol presence, duplicates and exact names",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ir_tests", type=Path)
    parser.add_argument(
        "--artifacts", type=Path, help="new artifact directory; default: unique directory beneath TMPDIR"
    )
    args = parser.parse_args()
    if args.artifacts is None:
        args.artifacts = Path(tempfile.mkdtemp(prefix="aurora-logical-span-abi-"))
    else:
        args.artifacts.mkdir(parents=True, exist_ok=False)
    raw = {}
    for graph in ("array", "owner"):
        raw[graph] = command([args.ir_tests.resolve(), "--emit-" + graph]).stdout.decode()
        require("validated typed IR" in raw[graph], "verified backend output required")
        (args.artifacts / (graph + "-generated.s")).write_text(raw[graph])
    require("__au_runtime_bytes_" not in raw["array"], "complete array-only graph has zero owner-runtime references")
    assembled = {}
    all_cases = {}
    count = 0
    for name, owner, handwritten in (
        ("array", False, False),
        ("owner", True, False),
        ("handwritten-results", True, True),
    ):
        emitted = instrument(raw["owner" if owner else "array"])
        if handwritten:
            for mode in range(4):
                emitted = replace_body(emitted, f"abi_result_{mode}", handwritten_result(mode))
        selected = cases(owner, handwritten)
        full = emitted + harness(selected, owner)
        assembled[name], all_cases[name] = full, selected
        execute(args.artifacts, name, full, selected)
        count += len(selected)
    # Deliberately corrupt separate full-width copy/save boundaries. The baseline
    # executes first, so an always-failing oracle cannot satisfy these controls.
    mutants = [
        ("bind-seventh-word", "owner", "abi_forward_1_1_0_0", "    movq %rax, -8(%rbp)", "    movq $0, -8(%rbp)", 91),
        (
            "reborrow-owner-word",
            "owner",
            "abi_forward_1_1_1_0",
            "    movq %rcx, -88(%rbp)",
            "    movq $0, -88(%rbp)",
            91,
        ),
        ("window-start", "owner", "abi_forward_1_1_2_0", "    movq %rcx, -184(%rbp)", "    movq $0, -184(%rbp)", 91),
        ("packed-seventh-word", "owner", "abi_forward_1_1_0_0", "    movq %rax, 48(%rsp)", "    movq $0, 48(%rsp)", 91),
        ("returned-seventh-word", "owner", "abi_result_0", "    movq %rcx, 48(%r10)", "    movq $0, 48(%r10)", 94),
        (
            "result-overcopy",
            "owner",
            "abi_result_0",
            "    movq %rcx, 48(%r10)",
            "    movq %rcx, 48(%r10)\n    movq $0, 56(%r10)",
            94,
        ),
        ("current-value-save", "owner", "abi_borrow_0", "    popq %rax", "    popq %rdx", 93),
        ("saved-operand", "owner", "abi_borrow_1", "    popq %rax", "    popq %rax\n    addq $1, (%rsp)", 93),
        (
            "runtime-alignment",
            "owner",
            "abi_borrow_0",
            "    subq $8, %rsp\n    call __au_runtime_bytes_borrow_span",
            "    nop\n    call __au_runtime_bytes_borrow_span",
            92,
        ),
    ]
    for name, graph, target, old, new, status in mutants:
        changed = mutate_body(assembled[graph], target, old, new)
        execute(args.artifacts, "mutant-" + name, changed, all_cases[graph], status, target)
    # Corrupt the expected hidden-result mode while retaining writable decoy
    # storage, so this is an exact oracle failure rather than a generic crash.
    wrong = mutate_body(assembled["owner"], "abi_result_3", "    movq %rax, -248(%rbp)", "    movq %r11, -248(%rbp)")
    execute(args.artifacts, "mutant-hidden-result-register", wrong, all_cases["owner"], 94, "abi_result_3")
    summary = f"PASS logical span ABI: {count} handwritten boundary cases, {len(mutants) + 1} exact rejected mutants"
    (args.artifacts / "cases.json").write_text(json.dumps(all_cases, indent=2) + "\n")
    (args.artifacts / "summary.txt").write_text(summary + "\n")
    root = Path(__file__).resolve().parents[2]
    sources = [Path(__file__).resolve(), Path(__file__).with_suffix(".cpp").resolve()]
    sources += [
        root / "compiler" / name
        for name in ("ir.hpp", "ir_verify.hpp", "ir_verify.cpp", "ir_layout.hpp", "types.hpp", "x86.hpp")
    ]
    manifest = {
        "status": "passed",
        "native_boundary_executions": count,
        "rejected_mutants": len(mutants) + 1,
        "array_owner_runtime_references": 0,
        "python": sys.version,
        "python_optimization": sys.flags.optimize,
        "fixture_sha256": hashlib.sha256(args.ir_tests.read_bytes()).hexdigest(),
        "sources": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        "tools": {name: command([name, "--version"]).stdout.decode().splitlines()[0] for name in ("as", "ld", "nm")},
    }
    (args.artifacts / "run.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(summary)
    print(f"Artifacts: {args.artifacts}")


if __name__ == "__main__":
    main()
