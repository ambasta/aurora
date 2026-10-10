#!/usr/bin/env python3
"""No-guest adversarial checks for local admission and separate external review pins."""

from pathlib import Path
import hashlib
import importlib.util
import json
import os
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("program_admission", ROOT / "scripts/kernel_program_console_admission.py")
admission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admission)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def reject(operation, message):
    try:
        operation()
    except (ValueError, OSError, KeyError):
        return
    raise ValueError("Accepted invalid case: " + message)


def body(frame, *calls):
    return dict(local_peak=frame, calls=[dict(target=target, live_bytes=live) for target, live in calls])


def main():
    from collections import namedtuple

    instruction = namedtuple("Instruction", "address size op args")

    bridge = [
        ("push", "%rbp"),
        ("mov", "%rsp,%rbp"),
        ("mov", "%rdi,%r11"),
        ("mov", "%rsi,%r10"),
        ("call", "private"),
        ("leave", ""),
        ("ret", ""),
    ]
    admission.check_note_bridge(bridge, "private")
    for index, replacement in (
        (2, ("mov", "%rsi,%r11")),
        (3, ("mov", "%rdi,%r10")),
        (4, ("call", "foreign")),
        (5, ("add", "$0x8,%rsp")),
    ):
        changed = list(bridge)
        changed[index] = replacement
        reject(lambda: admission.check_note_bridge(changed, "private"), "copied note bridge binding")

    # Scalar AND semantics and hostile destinations are covered by the shared
    # decoder's self-test, not a program-only compiler-layout normalization.
    decoder = admission.load("program_switch_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    for base in ("%rsi", "%rdx"):
        switch = [
            instruction(0, 4, "cmp", "$0x5,%rax"),
            instruction(4, 2, "ja", "100 <reject>"),
            instruction(6, 7, "lea", "0x100(%rip)," + base),
            instruction(13, 4, "movslq", f"({base},%rax,4),%rax"),
            instruction(17, 3, "add", base + ",%rax"),
            instruction(20, 2, "jmp", "*%rax"),
        ]
        need(admission.switch_envelope(switch) == 269, "Register-independent bounded switch table")
        for index, op, operands in (
            (0, "cmp", "$0x6,%rax"),
            (0, "cmp", "$0x5,%eax"),
            (1, "jg", "100 <reject>"),
            (2, "lea", "0x100(%rip),%rax"),
            (2, "lea", "0x100(%rip),%rsp"),
            (3, "movslq", f"({base},%rax,8),%rax"),
            (3, "mov", f"({base},%rax,4),%rax"),
            (4, "add", "%rsp,%rax"),
            (5, "jmp", "*%rdx"),
        ):
            changed = list(switch)
            changed[index] = changed[index]._replace(op=op, args=operands)
            reject(lambda changed=changed: admission.switch_envelope(changed), "changed bounded switch envelope")
        for insertion in range(1, 6):
            for operands in ("0x8(%rsp),%r8", "0x38(%rsp),%r10", "%r11,%r9"):
                scheduled = list(switch)
                scheduled.insert(insertion, instruction(0, 4, "mov", operands))
                scheduled = [row._replace(address=index * 8) for index, row in enumerate(scheduled)]
                envelope = admission.switch_window(scheduled, decoder)
                table_load = next(row for row in scheduled if row.op == "lea")
                need(envelope["table"] == table_load.address + table_load.size + 256, "Scheduled switch table")
                need(len(envelope["independent"]) == 1, "Scheduled move omitted from evidence")
                admission.switch_no_bypass(scheduled, envelope["guard"], envelope["jump"], [0, 96], decoder)
        for op, operands in (
            ("mov", "$0x1,%r8"),
            ("mov", "%r8,%rax"),
            ("mov", "%r8," + base),
            ("mov", "%r8,%rsp"),
            ("mov", "%r8d,%eax"),
            ("mov", "%r8b,%spl"),
            ("mov", "%r8,0x8(%rsp)"),
            ("mov", "-0x8(%rsp),%r8"),
            ("mov", "%rsp,%r8"),
            ("mov", "(%rdi),%r8"),
            ("xor", "%r8,%r8"),
            ("call", "100 <helper>"),
            ("jmp", "100 <other>"),
        ):
            changed = list(switch)
            changed.insert(3, instruction(0, 4, op, operands))
            changed = [row._replace(address=index * 8) for index, row in enumerate(changed)]
            reject(lambda changed=changed: admission.switch_window(changed, decoder), "unsafe switch interleaving")
        envelope = admission.switch_window(scheduled, decoder)
        guard, jump = envelope["guard"], envelope["jump"]
        for target in (scheduled[1].address, envelope["independent"][0].address, jump.address):
            reject(
                lambda target=target: admission.switch_no_bypass(scheduled, guard, jump, [target], decoder),
                "jump table enters switch after bound",
            )
            entry = instruction(100, 4, "jmp", f"{target:x} <interior>")
            reject(
                lambda entry=entry: admission.switch_no_bypass([entry, *scheduled], guard, jump, [96], decoder),
                "direct edge enters switch after bound",
            )
    graph = {
        "root": body(24, ("worker", 24)),
        "worker": body(32, ("leaf", 32)),
        "leaf": body(8),
        "unrelated": body(999999),
    }
    need(admission.graph_peak(graph, {}, "root", set())["peak"] == 64, "Exact live path sum")
    need(admission.graph_peak(graph, {"worker": 64}, "root", set())["peak"] == 96, "Retained compiler upper bound")
    need(admission.graph_peak(graph, {}, "root", set(), target="worker")["peak"] == 56, "Exact interruptible path")
    reject(lambda: admission.graph_peak(graph, {}, "root", set(), target="unrelated"), "unreachable IRQ target")
    recursive = {"root": body(8, ("walk", 8)), "walk": body(16, ("walk", 16))}
    reject(lambda: admission.graph_peak(recursive, {}, "root", set()), "unbounded cycle")
    need(admission.graph_peak(recursive, {}, "root", {"walk"})["peak"] == 72, "Four-frame reviewed recursion contract")

    # Compiler-to-symbol metadata is mandatory in every hosted UEFI admission
    # inventory, including the loader whose output enters the same boot image.
    for module in (
        admission,
        admission.load("console_inventory", ROOT / "scripts/kernel_console_service_admission.py"),
        admission.load("framebuffer_inventory", ROOT / "scripts/kernel_framebuffer_admission.py"),
    ):
        names = {path.name for path in module.build_files()}
        need(any(name.endswith(".su") for name in names), "Missing stack inventory")
        for name in names:
            if name.endswith(".su"):
                need(name.removesuffix(".su") + ".ci" in names, "Missing mandatory compiler-symbol inventory")

    prior_pin = os.environ.pop("PROGRAM_CONSOLE_REVIEW_SHA256", None)
    with tempfile.TemporaryDirectory(prefix="aurora-program-admission-") as directory:
        root = Path(directory)
        source = root / "source.cpp"
        source.write_text("original source\n")
        output = root / "image.bin"
        output.write_bytes(b"original linked bytes")
        callgraph = root / "runtime.ci"
        callgraph.write_text("original compiler-symbol metadata\n")
        stack = root / "runtime.su"
        stack.write_text("original compiler stack metadata\n")
        executable = root / "compiler"
        executable.write_bytes(b"fixture compiler bytes, never executed")
        admission.ROOT = root
        admission.BUILD = root
        admission.RECEIPT = root / "program-console-admission.json"
        admission.source_files = lambda: [source]
        admission.build_files = lambda: [output, callgraph, stack]
        flags = [
            "-DAURORA_UEFI_" + name
            for name in ("ACPI", "PCI", "RUNTIME", "IPC", "SERVICE_BUDGET", "USER_BUDGET", "PROGRAM_CONSOLE")
        ]
        admission.begin_build("program-console", str(executable), str(executable), flags)
        source.write_text("changed during build\n")
        reject(lambda: admission.end_build("program-console"), "mid-build source mutation")
        source.write_text("original source\n")
        admission.end_build("program-console")
        manifest = admission.provenance("program-console")
        for foreign in ("SNAPSHOT", "OWNED_BYTES", "DISPATCH", "CONSOLE", "GRAPHICAL_CONSOLE"):
            mixed = dict(manifest, flags=manifest["flags"] + ["-DAURORA_UEFI_" + foreign])
            reject(lambda: admission.verify_inputs(mixed, "program-console"), "foreign note profile authority")
        receipt = dict(
            schema="aurora-program-console-admission-v1",
            mode="program-console",
            build=manifest,
            status="requires-independent-review",
            clock="tcg-original-clock",
            sha256=admission.hashes([source, output, callgraph, stack, root / "program-build.json"]),
        )
        admission.RECEIPT.write_text(json.dumps(receipt, sort_keys=True))
        pin = admission.digest(admission.RECEIPT)
        need(admission.checked("program-console") == receipt, "Routine admission requires no external pin")
        reject(lambda: admission.checked("program-pending"), "routine profile mismatch")
        for changed in (
            dict(receipt, sha256={}),
            dict(receipt, sha256={**receipt["sha256"], "../escape": "0" * 64}),
            dict(receipt, clock="accelerated"),
            dict(receipt, status="independently-approved"),
        ):
            admission.RECEIPT.write_text(json.dumps(changed, sort_keys=True))
            reject(lambda: admission.checked("program-console"), "incomplete/foreign inventory or false assurance")
        admission.RECEIPT.write_text(json.dumps(receipt, sort_keys=True))
        reject(lambda: admission.reviewed("program-console"), "missing external pin")
        os.environ["PROGRAM_CONSOLE_REVIEW_SHA256"] = "0" * 64
        reject(lambda: admission.reviewed("program-console"), "wrong external pin")
        os.environ["PROGRAM_CONSOLE_REVIEW_SHA256"] = pin
        need(admission.reviewed("program-console") == receipt, "Correct fixture review pin")
        reject(lambda: admission.reviewed("program-pending"), "different reviewed profile")
        source.write_text("changed after review\n")
        reject(lambda: admission.reviewed("program-console"), "source mutated after review")
        reject(lambda: admission.checked("program-console"), "source mutated after automatic admission")
        source.write_text("original source\n")
        output.write_bytes(b"changed image")
        reject(lambda: admission.reviewed("program-console"), "image mutated after review")
        reject(lambda: admission.checked("program-console"), "image mutated after automatic admission")
        output.write_bytes(b"original linked bytes")
        callgraph.unlink()
        reject(lambda: admission.checked("program-console"), "missing mandatory compiler-symbol metadata")
        callgraph.write_text("replacement compiler-symbol metadata\n")
        reject(lambda: admission.checked("program-console"), "replaced compiler-symbol metadata")
        stack.write_text("coherently replaced compiler stack metadata\n")
        reject(lambda: admission.checked("program-console"), "coherently replaced metadata pair")
        callgraph.write_text("original compiler-symbol metadata\n")
        stack.write_text("original compiler stack metadata\n")
        executable.write_bytes(b"changed compiler")
        reject(lambda: admission.reviewed("program-console"), "compiler changed after build")
        reject(lambda: admission.checked("program-console"), "compiler changed after automatic admission")
        executable.write_bytes(b"fixture compiler bytes, never executed")
        need(admission.reviewed("program-console") == receipt, "Restored exact fixture")
        admission.RECEIPT.write_text(admission.RECEIPT.read_text() + " ")
        reject(lambda: admission.reviewed("program-console"), "receipt byte mutation")
    if prior_pin is None:
        os.environ.pop("PROGRAM_CONSOLE_REVIEW_SHA256", None)
    else:
        os.environ["PROGRAM_CONSOLE_REVIEW_SHA256"] = prior_pin
    print(
        "PASS: exact stack call paths, four-frame contract, local admission, "
        "build provenance and separate external review pin rejection"
    )


if __name__ == "__main__":
    main()
