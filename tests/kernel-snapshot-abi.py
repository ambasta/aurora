#!/usr/bin/env python3
"""Compact generated/linked fixture checks, using the existing disassembler.

This does not execute the production wrapper or qualify a complete kernel stack.
"""

from pathlib import Path
import argparse
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snapshot_stack", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
stack = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stack
spec.loader.exec_module(stack)
SERVICE = "__au_v_m1_16snapshot_service_n0__d16aurora_user_main"
NOTE_SERVICE = "__au_v_m1_22program_stream_service_n0__d16aurora_user_main"


def check_wrapper(actual, mode="normal", service=SERVICE):
    expected = [("or", f"%{register},%rax") for register in ("rbx", "rbp", "r10", "r11", "r12", "r13", "r14", "r15")]
    expected += [("jne", "bad_entry"), ("cmpq", "$0x0,-0x8(%rsp)"), ("jne", "bad_entry"), ("sub", "$0x70,%rsp")]
    expected += [("push", f"%{register}") for register in ("rdi", "rdx", "rcx", "r8", "r9")]
    expected += [
        ("sub", "$0x8,%rsp"),
        ("mov", "%r9,%rdx"),
        ("lea", "0x30(%rsp),%r11"),
        ("call", service),
        ("add", "$0x8,%rsp"),
    ]
    expected += [("pop", f"%{register}") for register in ("r9", "r8", "rcx", "rdx", "rdi")]
    expected += [("add", "$0x70,%rsp")]
    if mode == "reply-reserved":
        expected += [("movabs", "$0x8000000000000000,%r10"), ("or", "%r10,%rax")]
    elif mode == "reply-byte":
        expected += [("xor", "$0x100,%rax")]
    expected += [("mov", "$0x1,%esi")]
    if mode == "transaction":
        expected += [("inc", "%r8")]
    expected += [("int", "$0x81"), ("ud2", ""), ("ud2", "")]
    stack.require(actual == expected, "Changed copied wrapper record/envelope/restoration")


def check_bindings(actual, expected):
    stack.require(actual == expected, "Changed scalar/byte bindings or hidden record save")


def check_composition(directory):
    spec = importlib.util.spec_from_file_location("snapshot_images", ROOT / "scripts/kernel-uefi-ipc-images.py")
    images = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(images)
    cases = [("reply-reserved", {}), ("reply-byte", {}), ("context", {"snapshot": True})]
    cases += [
        ("normal", {"snapshot": True, field: True})
        for field in ("service_budget", "dispatcher", "user_budget", "program_console")
    ]
    cases += [
        ("normal", {"program_console": True}),
        ("normal", {"program_console": True, "service_budget": True}),
        ("normal", {"program_console": True, "service_budget": True, "user_budget": True, "dispatcher": True}),
        ("context", {"program_console": True, "service_budget": True, "user_budget": True}),
    ]
    for mode, options in cases:
        try:
            images.validate_composition(mode, **options)
        except ValueError:
            pass
        else:
            raise ValueError("Unsupported snapshot image composition accepted")


def main(directory, uefi_mode=None, note=False):
    check_composition(directory)
    entry = NOTE_SERVICE if note else SERVICE
    service = directory / ("user-bounds" if uefi_mode else "service")
    client = directory / ("user-clean" if uefi_mode else "client")
    mode = uefi_mode or "normal"
    if note:
        stack.require(mode in ("normal", "owner", "ordinal", "unknown", "transaction"), "Exact note mode")
        if mode != "transaction":
            mode = "normal"
    linked = stack.Elf(service.with_suffix(".elf"))
    symbols = {symbol.name: symbol for symbol in linked.symbols}
    instructions, _ = stack.disassemble(service.with_suffix(".elf"))
    wrapper = []
    targets = {symbols[name].address: name for name in ("bad_entry", entry)}
    for address in sorted(instructions):
        if symbols["aurora_program_entry"].address <= address < symbols[entry].address:
            insn = instructions[address]
            operand = targets.get(stack.target_of(insn)) if insn.op in ("call", "jne") else insn.args
            wrapper.append((insn.op, operand))
    check_wrapper(wrapper, mode, entry)
    # Four directed changed-record/restoration controls, without another decoder.
    for original, changed in (
        ("$0x70,%rsp", "$0x60,%rsp"),
        ("0x30(%rsp),%r11", "0x20(%rsp),%r11"),
        (entry, "wrong_entry"),
        ("%r9", "%r8"),
    ):
        bad = list(wrapper)
        index = next(index for index, (_, operand) in enumerate(bad) if operand == original)
        bad[index] = (bad[index][0], changed)
        try:
            check_wrapper(bad, mode, entry)
        except ValueError:
            pass
        else:
            raise ValueError("Malformed copied wrapper admitted")

    function = linked.functions[entry]
    body = [
        instructions[address]
        for address in sorted(instructions)
        if function.address <= address < function.address + function.size
    ]
    source = service.with_suffix(".s").read_text().split(entry + ":\n", 1)[1].split(".size " + entry, 1)[0]
    frame, prefix = stack.generated_frame([line.strip() for line in source.splitlines()], body)
    stack.require(frame == (144 if note else 112), "Changed copied service frame")
    hidden = "-0x88(%rbp)" if note else "-0x68(%rbp)"
    expected = [("mov", "%r11," + hidden)]
    for offset in (0, 8, 16):
        address = "(%r11)" if offset == 0 else f"0x{offset:x}(%r11)"
        expected += [("mov", hidden + ",%r11"), ("mov", address + ",%rax"), ("mov", f"%rax,-0x{offset + 8:x}(%rbp)")]
    expected += [("mov", hidden + ",%r11")]
    # The snapshot record ends in separately checked zero padding. Only the
    # explicit note record binds its final qword as the signed length.
    extent = 72 if note else 64
    for byte in range(0, extent, 8):
        expected += [("mov", f"0x{24 + byte:x}(%r11),%rax"), ("mov", f"%rax,-0x{24 + extent - byte:x}(%rbp)")]
    actual = [(row.op, row.args) for row in body[prefix : prefix + len(expected)]]
    check_bindings(actual, expected)
    # Source-layout independence: corrupt the scalar, first byte and final qword
    # bindings individually. The final note qword must never become padding.
    for index in (2, 12, len(actual) - 2):
        changed = list(actual)
        changed[index] = ("mov", "0x100(%r11),%rax")
        try:
            check_bindings(changed, expected)
        except ValueError:
            pass
        else:
            raise ValueError("Malformed copied binding admitted")
    service_object = directory / "objects" / service.with_suffix(".o").name if uefi_mode else service.with_suffix(".o")
    nm = subprocess.check_output(["nm", "-a", str(service_object)], text=True)
    stack.require(
        any(line.split()[1:] == ["t", entry] for line in nm.splitlines()), "Aggregate entry escaped local linkage"
    )
    stack.require(
        not subprocess.check_output(["nm", "-u", str(service_object)], text=True),
        "Protected service acquired an external import",
    )
    result = {
        "record_type": "NoteRead64" if note else "Snapshot64",
        "record_bytes": 96,
        "stack_reservation": 112,
        "pre_call_depth": 160,
        "record_offset": -112,
        "service_frame": frame,
        "service_bytes": service.with_suffix(".bin").stat().st_size,
        "client_bytes": client.with_suffix(".bin").stat().st_size,
        "mode": mode,
        "scope": "actual linked wrapper structure; execution and complete kernel stack remain pending",
    }
    (directory / ("note-abi.json" if note else "abi.json")).write_text(json.dumps(result, indent=2) + "\n")
    print(
        "PASS: fixed copied bindings, local aggregate entry and exact linked wrapper; "
        "four wrapper and three binding mutation controls"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument(
        "--uefi-mode", choices=("normal", "owner", "ordinal", "unknown", "transaction", "reply-reserved", "reply-byte")
    )
    parser.add_argument("--kernel-stack", action="store_true")
    parser.add_argument("--note", action="store_true")
    args = parser.parse_args()
    stack.require(bool(args.directory) != bool(args.build_dir), "Select exactly one artifact directory")
    args.directory = args.build_dir or args.directory
    ROOT = args.source_root.resolve(strict=True)
    stack.ROOT = ROOT
    if args.kernel_stack:
        stack.require(args.uefi_mode is None, "Separate linked user ABI and kernel stack checks")
        spec = importlib.util.spec_from_file_location(
            "snapshot_linked_stack", ROOT / "scripts/kernel_program_console_admission.py"
        )
        admission = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(admission)
        admission.configure_paths(args.directory, ROOT)
        result = admission.stack_evidence(args.directory, snapshot=True)
        (args.directory / "snapshot-stack.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            f"PASS: snapshot linked stack {result['normal']['peak']} + {result['fault_reserve']} fault reserve "
            f"= {result['normal_with_fault_reserve']} <= {result['cap_bytes']}; exact user wrappers included"
        )
    else:
        main(args.directory, args.uefi_mode, args.note)
