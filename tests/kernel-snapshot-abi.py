#!/usr/bin/env python3
"""Copied snapshot ABI CLI and controls; implementation is a production module."""

from pathlib import Path
import argparse
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snapshot_abi", ROOT / "scripts/kernel_snapshot_abi.py")
abi = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = abi
spec.loader.exec_module(abi)
stack = abi.stack
main = abi.main


def copy_controls():
    stable = [
        ("push", "%rsi"),
        ("push", "%rdi"),
        ("push", "%rcx"),
        ("lea", "0x18(%r11),%rsi"),
        ("lea", "-0x58(%rbp),%rdi"),
        ("mov", "$0x40,%rcx"),
        ("cld", ""),
        ("rep", "movsb %ds:(%rsi),%es:(%rdi)"),
        ("pop", "%rcx"),
        ("pop", "%rdi"),
        ("pop", "%rsi"),
    ]
    packed = [
        ("lea", "0x20(%rsp),%rax"),
        ("push", "%rsi"),
        ("push", "%rdi"),
        ("push", "%rcx"),
        ("lea", "-0x200(%rbp),%rsi"),
        ("mov", "%rax,%rdi"),
        ("mov", "$0x200,%rcx"),
        ("cld", ""),
        ("rep", "movsb %ds:(%rsi),%es:(%rdi)"),
        ("pop", "%rcx"),
        ("pop", "%rdi"),
        ("pop", "%rsi"),
    ]
    rejected = 0

    def reject(operation):
        nonlocal rejected
        try:
            operation()
        except ValueError:
            rejected += 1
        else:
            raise ValueError("Changed compact copied payload admitted")

    for rows, layout in (
        (stable, ("r11", 24, "rbp", -88, 64)),
        (packed, ("rbp", -512, "rsp", 32, 512)),
    ):
        expected = abi.copied_payload(*layout)
        abi.check_bindings(rows, expected)
        for index in range(len(rows)):
            for replacement in (("ud2", ""), (rows[index][0], rows[index][1] + ",%rax")):
                changed = list(rows)
                changed[index] = replacement
                reject(lambda: abi.check_bindings(changed, expected))
            reject(lambda: abi.check_bindings(rows[:index] + rows[index + 1 :], expected))
            reject(lambda: abi.check_bindings(rows[:index] + [rows[index]] + rows[index:], expected))
        for index in (1, 3, 4):
            for delta in (-1, 1):
                changed_layout = list(layout)
                changed_layout[index] += delta
                reject(lambda: abi.check_bindings(rows, abi.copied_payload(*changed_layout)))
    for extent in (0, 63, 65537, True):
        reject(lambda: abi.copied_payload("r11", 0, "rbp", -72, extent))
    for source, destination in (("rsp", "rbp"), ("rax", "rbp"), ("rbp", "rsi"), ("r11", "rsp")):
        reject(lambda: abi.copied_payload(source, 0, destination, 0, 64))
    print(f"PASS: compact copied payload two exact forms and {rejected} mutation controls")


if __name__ == "__main__":
    copy_controls()
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
    abi.ROOT = ROOT
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
