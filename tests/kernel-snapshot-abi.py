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


def check_wrapper(actual, mode="normal"):
    expected = [("or", f"%{register},%rax") for register in ("rbx", "rbp", "r10", "r11", "r12", "r13", "r14", "r15")]
    expected += [("jne", "bad_entry"), ("cmpq", "$0x0,-0x8(%rsp)"), ("jne", "bad_entry"), ("sub", "$0x70,%rsp")]
    expected += [("push", f"%{register}") for register in ("rdi", "rdx", "rcx", "r8", "r9")]
    expected += [
        ("sub", "$0x8,%rsp"),
        ("mov", "%r9,%rdx"),
        ("lea", "0x30(%rsp),%r11"),
        ("call", SERVICE),
        ("add", "$0x8,%rsp"),
    ]
    expected += [("pop", f"%{register}") for register in ("r9", "r8", "rcx", "rdx", "rdi")]
    expected += [("add", "$0x70,%rsp")]
    if mode == "reply-reserved":
        expected += [("movabs", "$0x8000000000000000,%r10"), ("or", "%r10,%rax")]
    elif mode == "reply-byte":
        expected += [("xor", "$0x100,%rax")]
    expected += [("mov", "$0x1,%esi"), ("int", "$0x81"), ("ud2", ""), ("ud2", "")]
    stack.require(actual == expected, "Changed snapshot wrapper record/envelope/restoration")


def check_composition(directory):
    spec = importlib.util.spec_from_file_location("snapshot_images", ROOT / "scripts/kernel-uefi-ipc-images.py")
    images = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(images)
    rejected = directory / "rejected-composition"
    stack.require(not rejected.exists(), "Stale composition control output")
    cases = [("reply-reserved", {}), ("reply-byte", {}), ("context", {"snapshot": True})]
    cases += [
        ("normal", {"snapshot": True, field: True})
        for field in ("service_budget", "dispatcher", "user_budget", "program_console")
    ]
    for mode, options in cases:
        try:
            images.build(Path("/nonexistent-snapshot-compiler"), rejected, mode, **options)
        except ValueError:
            pass
        else:
            raise ValueError("Unsupported snapshot image composition accepted")
    stack.require(not rejected.exists(), "Rejected composition started generating artifacts")


def main(directory, uefi_mode=None):
    check_composition(directory)
    service = directory / ("user-bounds" if uefi_mode else "service")
    client = directory / ("user-clean" if uefi_mode else "client")
    mode = uefi_mode or "normal"
    linked = stack.Elf(service.with_suffix(".elf"))
    symbols = {symbol.name: symbol for symbol in linked.symbols}
    instructions, _ = stack.disassemble(service.with_suffix(".elf"))
    wrapper = []
    targets = {symbols[name].address: name for name in ("bad_entry", SERVICE)}
    for address in sorted(instructions):
        if symbols["aurora_program_entry"].address <= address < symbols[SERVICE].address:
            insn = instructions[address]
            operand = targets.get(stack.target_of(insn)) if insn.op in ("call", "jne") else insn.args
            wrapper.append((insn.op, operand))
    check_wrapper(wrapper, mode)
    # Four directed changed-record/restoration controls, without another decoder.
    for original, changed in (
        ("$0x70,%rsp", "$0x60,%rsp"),
        ("0x30(%rsp),%r11", "0x20(%rsp),%r11"),
        (SERVICE, "wrong_entry"),
        ("%r9", "%r8"),
    ):
        bad = list(wrapper)
        index = next(index for index, (_, operand) in enumerate(bad) if operand == original)
        bad[index] = (bad[index][0], changed)
        try:
            check_wrapper(bad, mode)
        except ValueError:
            pass
        else:
            raise ValueError("Malformed copied wrapper admitted")

    function = linked.functions[SERVICE]
    body = [
        instructions[address]
        for address in sorted(instructions)
        if function.address <= address < function.address + function.size
    ]
    source = service.with_suffix(".s").read_text().split(SERVICE + ":\n", 1)[1].split(".size " + SERVICE, 1)[0]
    frame, prefix = stack.generated_frame([line.strip() for line in source.splitlines()], body)
    stack.require(frame == 112, "Changed copied service frame")
    expected = [("mov", "%r11,-0x68(%rbp)")]
    for offset in (0, 8, 16):
        address = "(%r11)" if offset == 0 else f"0x{offset:x}(%r11)"
        expected += [("mov", "-0x68(%rbp),%r11"), ("mov", address + ",%rax"), ("mov", f"%rax,-0x{offset + 8:x}(%rbp)")]
    expected += [("mov", "-0x68(%rbp),%r11")]
    for byte in range(0, 64, 8):
        expected += [("mov", f"0x{24 + byte:x}(%r11),%rax"), ("mov", f"%rax,-0x{88 - byte:x}(%rbp)")]
    stack.require(
        [(row.op, row.args) for row in body[prefix : prefix + len(expected)]] == expected,
        "Changed scalar/byte bindings or hidden record save",
    )
    nm = subprocess.check_output(["nm", "-a", str(service.with_suffix(".o"))], text=True)
    stack.require(
        any(line.split()[1:] == ["t", SERVICE] for line in nm.splitlines()), "Aggregate entry escaped local linkage"
    )
    stack.require(
        not subprocess.check_output(["nm", "-u", str(service.with_suffix(".o"))], text=True),
        "Protected service acquired an external import",
    )
    result = {
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
    (directory / "abi.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: fixed copied bindings, local aggregate entry and exact linked wrapper; four hostile controls")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--uefi-mode", choices=("normal", "owner", "reply-reserved", "reply-byte"))
    parser.add_argument("--kernel-stack", action="store_true")
    args = parser.parse_args()
    if args.kernel_stack:
        stack.require(args.uefi_mode is None, "Separate linked user ABI and kernel stack checks")
        spec = importlib.util.spec_from_file_location(
            "snapshot_linked_stack", ROOT / "scripts/kernel_program_console_admission.py"
        )
        admission = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(admission)
        result = admission.stack_evidence(args.directory, snapshot=True)
        (args.directory / "snapshot-stack.json").write_text(json.dumps(result, indent=2) + "\n")
        print(
            f"PASS: snapshot linked stack {result['normal']['peak']} + {result['fault_reserve']} fault reserve "
            f"= {result['normal_with_fault_reserve']} <= {result['cap_bytes']}; exact user wrappers included"
        )
    else:
        main(args.directory, args.uefi_mode)
