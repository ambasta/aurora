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
    # A bank image installs every --image NAME:ROLE in its own slot, linked for
    # domain image ROLE; a --set MODE:VALUE:NAME0,NAME1 names the slots acting
    # as images 0 and 1 when the boot selector is VALUE (else slots 0 and 1).
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--set", action="append", default=[])
    arguments = parser.parse_args()
    out = arguments.output.resolve()
    records = {}
    header = ["#pragma once", "#include <array>", "#include <cstddef>", "namespace aurora::uefi::images {"]
    names = ("clean", "bounds", "peer") if arguments.dispatcher else ("clean", "bounds")
    bank = [(name, int(role)) for name, _, role in (entry.partition(":") for entry in arguments.image)]
    need(not bank or (bank[0] == ("clean", 0) and bank[1] == ("bounds", 1)), "bank must start with clean and bounds")
    for name, role in bank or list((name, index) for index, name in enumerate(names)):
        need(not bank or (role in (0, 1) and name not in records), f"{name}: invalid bank image")
        meta, blob = image_metadata(out / f"user-{name}", LAYOUT.user_code + role * LAYOUT.code_stride, arguments, role)
        records[name] = meta
        symbol = name.replace("-", "_")
        header.append(
            f"inline constexpr std::array<std::byte,{len(blob)}> {symbol}_bytes = {{"
            + ",".join(f"std::byte{{{value}}}" for value in blob)
            + "};"
        )
        # The kernel loads only scalar facts; the probe set is guest-oracle evidence.
        header += [
            f"inline constexpr unsigned long long {symbol}_{key}={value}ULL;"
            for key, value in meta.items()
            if key != "probes"
        ]
    if bank:
        fields = ("entry", "size", "return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")
        # Rip-relative calls, not a table of pointers needing load-time relocation.
        header += [
            f"inline constexpr std::size_t bank_size = {len(bank)};",
            "template <class Install> inline auto install_bank(const Install &install) -> void {",
        ]
        for slot, (name, role) in enumerate(bank):
            symbol = name.replace("-", "_")
            values = ", ".join(f"{symbol}_{key}" for key in fields + ("probe_offset",))
            header.append(
                f"    install({slot}U, {role}U, {symbol}_bytes, std::array<unsigned long long, 8>{{{values}}});"
            )
        header.append("}")
        sets = {"default": {"clean": "clean", "bounds": "bounds"}}
        rows = []
        slots = [name for name, _ in bank]
        for entry in arguments.set:
            mode, value, chosen = entry.split(":")
            chosen = chosen.split(",")
            need(
                len(chosen) == 2 and all(name in slots for name in chosen) and 0 < int(value) < 256,
                f"{mode}: invalid image set",
            )
            need([dict(bank)[name] for name in chosen] == [0, 1], f"{mode}: set roles are not images 0 and 1")
            sets[mode] = {"clean": chosen[0], "bounds": chosen[1]}
            rows.append(f"{{{int(value)}U, {slots.index(chosen[0])}U, {slots.index(chosen[1])}U}}")
        header.append(
            f"inline constexpr std::array<std::array<unsigned, 3>, {len(rows)}> sets{{{{" + ", ".join(rows) + "}};"
        )
        (out / "user-sets.json").write_text(json.dumps(sets, indent=2) + "\n")
    header.append("}")
    (out / "uefi-user-images.hpp").write_text("\n".join(header) + "\n")
    (out / "user-images.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
