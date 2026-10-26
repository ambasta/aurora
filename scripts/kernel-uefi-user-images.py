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


def image_metadata(prefix, base, budget, owned, console):
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
    facts = json.loads(abi.read_text()) if abi.exists() else None
    compiled = abi_function_symbol(facts, "aurora_user_main") if facts else None
    if budget or owned:
        compiled = compiled or "aurora_user_main"
        need(compiled in elf.functions, f"{prefix.name}: compiled entry {compiled} is not a linked function")
        function = elf.functions[compiled]
        meta.update(compiled_begin=function.address, compiled_end=function.address + function.size)
        append_roots = [
            name
            for name in ("append_candidate", "append_producer")
            if facts and any(value["source_name"] == name for value in facts["functions"].values())
        ]
        if append_roots:
            # Each combined production role retains its scalar entry and one
            # live append root. Admit every reachable compiled timer PC from
            # emitted graph facts, not merely the old scalar entry's interval.
            graph = json.loads(prefix.with_suffix(".stack.json").read_text())["functions"]
            pending = [compiled] + [abi_function_symbol(facts, name) for name in append_roots]
            reached = set()
            while pending:
                name = pending.pop()
                if name in reached or name in ("__au_runtime_call", "__au_runtime_serve_exchange"):
                    continue
                need(name in graph and name in elf.functions, f"{prefix.name}: missing compiled append node {name}")
                reached.add(name)
                pending.extend(graph[name]["calls"])
            ranges = [elf.functions[name] for name in reached]
            meta.update(
                compiled_begin=min(value.address for value in ranges),
                compiled_end=max(value.address + value.size for value in ranges),
            )
            need(
                meta["return_pc"] < meta["compiled_begin"] < meta["compiled_end"] <= meta["bounds_pc"],
                f"{prefix.name}: compiled append graph crosses its wrapper/trap boundary",
            )
    if budget:
        meta.update(context_begin=at("aurora_budget_context_begin"), context_end=at("aurora_budget_context_end"))
    if owned:
        meta.update(("bytes_" + name + "_pc", at("aurora_bytes_" + name + "_pc")) for name in BYTE_OPERATIONS)
        if console:
            meta.update(console_next_pc=at("aurora_console_next_pc"), console_put_pc=at("aurora_console_put_pc"))
    return meta, blob


OWNED = ("owned-text", "console-region", "console-region-fixture")
# Domain image role names, as the oracles' metadata sets name them.
ROLES = ("clean", "bounds", "peer")
RANGES = ("compiled_begin", "compiled_end", "context_begin", "context_end")
# Kernel-read sites of each slot of a packed bank, whose rows run several former
# images: the call/serve exchange sites, timer ranges, owned-byte and Console sites.
SITES_FIELDS = ("call_pc", "serve_pc", *RANGES, *("bytes_" + name + "_pc" for name in BYTE_OPERATIONS))
SITES_FIELDS += ("console_next_pc", "console_put_pc")
FLAGS = ("budget", "owned", "console")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", default="normal")
    parser.add_argument("--service-budget", action="store_true")
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
    # A bank image installs every --image NAME:ROLE[:FLAG...] in its own slot,
    # linked for domain image ROLE (budget: its metadata carries the service-timer
    # ranges; owned/console: its owned-byte and Console sites; pages=N: a packed
    # slot of N pages, one per image of the bank, laid out in order); a
    # --set MODE:VALUE:NAME0,NAME1[,NAME2] names the slots acting as images 0, 1
    # (and 2) when the boot selector is VALUE, else each role's first.
    parser.add_argument("--image", action="append", default=[])
    parser.add_argument("--set", action="append", default=[])
    arguments = parser.parse_args()
    out = arguments.output.resolve()
    records = {}
    header = ["#pragma once", "#include <array>", "#include <cstddef>", "namespace aurora::uefi::images {"]
    bank, pages = [], []
    for name, role, *extra in (entry.split(":") for entry in arguments.image):
        sized = [int(flag[6:]) for flag in extra if flag.startswith("pages=") and flag[6:].isdigit()]
        flags = [flag for flag in extra if not flag.startswith("pages=")]
        need(len(sized) == len(extra) - len(flags) <= 1 and set(flags) <= set(FLAGS), "invalid bank image")
        bank.append((name, int(role), {flag: flag in flags for flag in FLAGS}))
        pages += sized
    need(not pages or (len(pages) == len(bank) and all(0 < count <= 3 for count in pages)), "invalid packed slots")
    roles = sorted({role for _, role, _ in bank})
    need(roles == list(range(len(roles))) and len(roles) in (0, 2, 3), "bank roles are not images 0, 1 (and 2)")
    owned_mode = arguments.mode in OWNED
    ordinary = [
        (name, index, dict(budget=arguments.service_budget, owned=owned_mode and index == 0))
        for index, name in enumerate(ROLES[:2])
    ]
    for name, role, flags in bank or ordinary:
        need(name not in records, f"{name}: duplicate bank image")
        console = flags.get("console", arguments.mode.startswith("console-region") and flags["owned"])
        meta, blob = image_metadata(
            out / f"user-{name}", LAYOUT.user_code + role * LAYOUT.code_stride, flags["budget"], flags["owned"], console
        )
        if pages:
            need(len(blob) <= pages[len(records)] * LAYOUT.page_size, f"{name}: image exceeds its packed slot")
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
        for slot, (name, role, _) in enumerate(bank):
            symbol = name.replace("-", "_")
            values = ", ".join(f"{symbol}_{key}" for key in fields + ("probe_offset",))
            header.append(
                f"    install({slot}U, {role}U, {symbol}_bytes, std::array<unsigned long long, 8>{{{values}}});"
            )
        header.append("}")
        # Service-timer ranges per slot (compiled begin/end, context begin/end); zero when absent.
        ranges = ["{" + ", ".join(f"{records[name].get(key, 0)}ULL" for key in RANGES) + "}" for name, _, _ in bank]
        header.append(
            f"inline constexpr std::array<std::array<unsigned long long, 4>, {len(bank)}> slot_ranges{{{{"
            + ", ".join(ranges)
            + "}};"
        )
        # Every kernel-read site of each slot; zero when its image has none.
        header += [
            "class Sites final {",
            "public:",
            "    unsigned long long " + ", ".join(SITES_FIELDS) + ";",
            "};",
            f"inline constexpr std::array<Sites, {len(bank)}> slot_sites{{{{"
            + ", ".join(
                "{" + ", ".join(f"{records[name].get(key, 0)}ULL" for key in SITES_FIELDS) + "}" for name, _, _ in bank
            )
            + "}};",
        ]
        if pages:
            offsets = [sum(pages[:slot]) * LAYOUT.page_size for slot in range(len(bank))]
            header += [
                f"inline constexpr std::size_t bank_pages = {sum(pages)};",
                f"inline constexpr std::array<std::size_t, {len(bank)}> slot_offsets{{"
                + ", ".join(f"{offset}U" for offset in offsets)
                + "};",
                f"inline constexpr std::array<std::size_t, {len(bank)}> slot_pages{{"
                + ", ".join(f"{count}U" for count in pages)
                + "};",
            ]
        slots = [name for name, _, _ in bank]
        first = [next(slot for slot, entry in enumerate(bank) if entry[1] == role) for role in roles]
        sets = {"default": {ROLES[role]: slots[slot] for role, slot in enumerate(first)}}
        header.append(
            f"inline constexpr std::array<std::size_t, {len(roles)}> default_slots{{"
            + ", ".join(f"{slot}U" for slot in first)
            + "};"
        )
        rows = []
        for entry in arguments.set:
            mode, value, chosen = entry.split(":")
            chosen = chosen.split(",")
            need(
                2 <= len(chosen) <= len(roles) and all(name in slots for name in chosen) and 0 < int(value) < 256,
                f"{mode}: invalid image set",
            )
            need(
                [bank[slots.index(name)][1] for name in chosen] == list(range(len(chosen))),
                f"{mode}: set roles are not its images in order",
            )
            sets[mode] = dict(zip(ROLES, chosen))
            # A set naming fewer images than the bank has roles leaves the rest unbound.
            picked = [slots.index(name) for name in chosen] + [len(bank)] * (len(roles) - len(chosen))
            rows.append("{" + ", ".join(f"{item}U" for item in [int(value), *picked]) + "}")
        header.append(
            f"inline constexpr std::array<std::array<unsigned, {1 + len(roles)}>, {len(rows)}> sets{{{{"
            + ", ".join(rows)
            + "}};"
        )
        (out / "user-sets.json").write_text(json.dumps(sets, indent=2) + "\n")
    header.append("}")
    (out / "uefi-user-images.hpp").write_text("\n".join(header) + "\n")
    (out / "user-images.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    main()
