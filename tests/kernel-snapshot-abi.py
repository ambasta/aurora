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
