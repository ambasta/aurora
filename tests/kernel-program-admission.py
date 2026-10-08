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

    class Decoder:
        Instruction = instruction

    row = instruction(0x9380, 9, "andq", "$0xfffffffffffffdff,0x50(%rsp)")
    need(
        admission.normalize_copied_flag_clear(Decoder, row) == instruction(0x9380, 9, "and", row.args),
        "Exact copied-IF memory clear normalization",
    )
    for args in (
        "$0xfffffffffffffdff,%rsp",
        "$0xfffffffffffffdff,0x58(%rsp)",
        "$0xfffffffffffffbff,0x50(%rsp)",
        "$0xfffffffffffffdff,0x50(%rbp)",
    ):
        reject(
            lambda: admission.normalize_copied_flag_clear(Decoder, row._replace(args=args)),
            "unreviewed qword destination or mask",
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

    prior_pin = os.environ.pop("PROGRAM_CONSOLE_REVIEW_SHA256", None)
    with tempfile.TemporaryDirectory(prefix="aurora-program-admission-") as directory:
        root = Path(directory)
        source = root / "source.cpp"
        source.write_text("original source\n")
        output = root / "image.bin"
        output.write_bytes(b"original linked bytes")
        executable = root / "compiler"
        executable.write_bytes(b"fixture compiler bytes, never executed")
        admission.ROOT = root
        admission.BUILD = root
        admission.RECEIPT = root / "program-console-admission.json"
        admission.source_files = lambda: [source]
        admission.build_files = lambda: [output]
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
        receipt = dict(
            schema="aurora-program-console-admission-v1",
            mode="program-console",
            build=manifest,
            status="requires-independent-review",
            clock="tcg-original-clock",
            sha256=admission.hashes([source, output, root / "program-build.json"]),
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
