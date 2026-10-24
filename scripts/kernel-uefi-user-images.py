#!/usr/bin/env python3
"""Emit the embedded UEFI user images and their kernel-read site metadata.

The kernel re-validates every site at load and trap time (ProgramImage::valid,
RuntimeLayout::valid and the INT 0x82 stub check); image format and stack
bounds are the build's kernel_image_check.py and kernel_stack_check.py steps.
"""

from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_frontend import abi_function_symbol  # noqa: E402
from kernel_elf import Elf  # noqa: E402
from kernel_layout import LAYOUT  # noqa: E402

SITES = (
    ("return_pc", "aurora_program_return_pc"),
    ("bounds_pc", ".Laurora_bounds_trap"),
    ("overflow_pc", ".Laurora_overflow_trap"),
    ("division_zero_pc", ".Laurora_division_zero_trap"),
    ("shift_count_pc", ".Laurora_shift_count_trap"),
)
BYTE_OPERATIONS = ("allocate", "borrow_length", "at", "set", "resize", "drop")


def need(value, message):
    if not value:
        raise SystemExit("FAIL: " + message)


def image_metadata(prefix, base, arguments, index):
    elf = Elf(prefix.with_suffix(".elf"))
    blob = prefix.with_suffix(".bin").read_bytes()
    symbols = {symbol.name: symbol for symbol in elf.symbols if symbol.name and symbol.section}

    def at(name):
        return symbols[name].address if name in symbols else 0

    need(elf.entry == base == at("aurora_program_entry"), f"{prefix.name}: entry is not its fixed slot")
    meta = dict(entry=base, size=len(blob))
    meta.update((key, at(name)) for key, name in SITES)
    need(meta["return_pc"] and meta["bounds_pc"] and meta["overflow_pc"], f"{prefix.name}: missing trap sites")
    probe = at("aurora_kernel_probe_target")
    meta["probe_offset"] = probe - base if probe else 0
    meta["probe_pc"] = at("aurora_probe_pc")
    probes = {
        name[len("aurora_probe_") : -len("_pc")]: symbol.address
        for name, symbol in symbols.items()
        if name.startswith("aurora_probe_") and name.endswith("_pc") and name != "aurora_probe_pc"
    }
    if probes:
        meta["probes"] = dict(sorted(probes.items()))
    if at("aurora_call_return_pc"):
        meta["call_pc"] = at("aurora_call_return_pc")
    if at("aurora_serve_return_pc"):
        meta["serve_pc"] = at("aurora_serve_return_pc")
    abi = prefix.with_suffix(".abi.json")
    compiled = abi_function_symbol(json.loads(abi.read_text()), "aurora_user_main") if abi.exists() else None
    if arguments.service_budget or (arguments.mode in OWNED and index == 0):
        compiled = compiled or "aurora_user_main"
        need(compiled in elf.functions, f"{prefix.name}: compiled entry {compiled} is not a linked function")
        function = elf.functions[compiled]
        meta.update(compiled_begin=function.address, compiled_end=function.address + function.size)
    if arguments.service_budget:
        meta.update(context_begin=at("aurora_budget_context_begin"), context_end=at("aurora_budget_context_end"))
    if arguments.mode in OWNED and index == 0:
        meta.update(("bytes_" + name + "_pc", at("aurora_bytes_" + name + "_pc")) for name in BYTE_OPERATIONS)
        if arguments.mode.startswith("console-region"):
            meta.update(console_next_pc=at("aurora_console_next_pc"), console_put_pc=at("aurora_console_put_pc"))
    return meta, blob


OWNED = ("owned-text", "console-region", "console-region-fixture")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--service-budget", action="store_true")
    parser.add_argument("--dispatcher", action="store_true")
    # Accepted composition selectors; the linked symbols carry their effect.
    for flag in (
        "--user-budget",
        "--program-console",
        "--snapshot",
        "--blocking-call",
        "--file-call",
        "--ram-file",
        "--ram-scratchpad-console",
        "--ram-scratchpad-fixture",
    ):
        parser.add_argument(flag, action="store_true")
    arguments = parser.parse_args()
    out = arguments.output.resolve()
    records = {}
    header = ["#pragma once", "#include <array>", "#include <cstddef>", "namespace aurora::uefi::images {"]
    for index, name in enumerate(("clean", "bounds", "peer") if arguments.dispatcher else ("clean", "bounds")):
        meta, blob = image_metadata(
            out / f"user-{name}", LAYOUT.user_code + index * LAYOUT.code_stride, arguments, index
        )
        records[name] = meta
        header.append(
            f"inline constexpr std::array<std::byte,{len(blob)}> {name}_bytes = {{"
            + ",".join(f"std::byte{{{value}}}" for value in blob)
            + "};"
        )
        # The kernel loads only scalar facts; the probe set is guest-oracle evidence.
        header += [
            f"inline constexpr unsigned long long {name}_{key}={value}ULL;"
            for key, value in meta.items()
            if key != "probes"
        ]
    header.append("}")
    (out / "uefi-user-images.hpp").write_text("\n".join(header) + "\n")
    (out / "user-images.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
