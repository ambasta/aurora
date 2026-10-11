#!/usr/bin/env python3
"""Profile budgets over the shared compiler-fact and handwritten-assembly graph."""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tables_stack_shared", ROOT / "scripts/kernel_stack.py")
shared = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shared
spec.loader.exec_module(shared)
require = shared.require

LIMITS = {
    "payload_main(": 11264,
    "discover_acpi(": 128,
    "prepare_table_acpi(": 5120,
    "Topology::parse(": 4096,
    "discover_pci(": 11264,
    "PageTables::verify(": 11264,
    "run_protected(": 2048,
    "pin_request(": 1024,
    "DormantTables::prepare(": 1024,
    "PinLedger::grant(": 1024,
    "PinLedger::release_reserved(": 1024,
    "DormantTables::ownership(": 1024,
    "table_readback(": 1024,
    "independent::validate(": 1024,
    "table_prepare(": 1024,
    "DormantTables::release(": 1024,
    "table_scrub(": 1024,
    "pin_fault_returned(": 1024,
    "pin_reborn(": 1024,
    "table_corruption(": 1024,
    "table_exhaustion(": 1024,
}
OPTIONAL = ("table_corruption(", "table_exhaustion(")
EXCLUDED = {"PageTables::verify(": ("lambda",)}


# The compiler reports only __indirect_call. This single binding is a reviewed
# source contract, mechanically guarded below, not compiler-derived alias proof.
CALLBACKS = (
    (
        ("runtime.o", "kernel/pin-ledger.hpp", "bool aurora::memory::PinLedger::release_reserved(Entry&)"),
        (
            "runtime.o",
            "kernel/uefi/dormant-runtime.inc",
            "bool aurora::uefi::{anonymous}::table_scrub(void*, U64, std::size_t)",
        ),
    ),
)


def callback_contract(runtime, profile, ledger):
    require(
        re.search(
            r'#ifdef AURORA_UEFI_TABLES\s*#include "dormant-runtime.inc"\s*#else\s*'
            r'#include "pin-runtime.inc"\s*#endif',
            runtime,
        ),
        "Changed exclusive table adapter selection",
    )
    require(
        len(re.findall(r"\bPinLedger\b", runtime + profile)) == 1
        and re.search(r"std::optional<memory::PinLedger>\s+table_ledger\s*;", profile),
        "Changed table ledger instance contract",
    )
    constructions = re.findall(r"\btable_ledger\s*\.\s*emplace\s*\(([^;]*)\)\s*;", profile)
    require(
        len(constructions) == 1
        and re.fullmatch(r"\s*frames\s*,\s*registry\s*,\s*table_scrub\s*,\s*nullptr\s*", constructions[0]),
        "Changed table scrub constructor target",
    )
    require(
        re.search(r"\bScrub\s+const\s+scrub_\s*;", ledger) and re.search(r"\bscrub_\s*\(\s*scrub\s*\)", ledger),
        "Changed immutable scrub field contract",
    )


def validate(graph):
    result = shared.profile_stack(
        graph,
        LIMITS,
        optional=OPTIONAL,
        excluded=EXCLUDED,
        default_limit=11264,
        fault_reserve=1024,
        separated=(("prepare_table_acpi(", "discover_pci("),),
    )
    return result


def self_test():
    from copy import deepcopy
    from unittest import TestCase

    runtime = '#ifdef AURORA_UEFI_TABLES\n#include "dormant-runtime.inc"\n#else\n#include "pin-runtime.inc"\n#endif'
    profile = (
        "std::optional<memory::PinLedger> table_ledger; table_ledger.emplace(frames,registry,table_scrub,nullptr);"
    )
    ledger = "Scrub const scrub_; PinLedger(Scrub scrub): scrub_(scrub) {}"
    callback_contract(runtime, profile, ledger)
    for changed in (profile.replace("table_scrub", "different_scrub"), profile + profile):
        with TestCase().assertRaises(ValueError):
            callback_contract(runtime, changed, ledger)
    with TestCase().assertRaises(ValueError):
        callback_contract(runtime, profile, ledger.replace(" const", ""))
    symbols = {
        name: shared.Symbol(name, address, size, 1, 2) for name, address, size in (("release", 0, 3), ("scrub", 4, 1))
    }
    code = {
        row.address: row
        for row in (
            shared.Instruction(0, 2, "call", "*%rax"),
            shared.Instruction(2, 1, "ret", ""),
            shared.Instruction(4, 1, "ret", ""),
        )
    }
    arguments = (
        symbols,
        code,
        {0: "release", 4: "scrub"},
        b"\xff\xd0\xc3\x90\xc3",
        {"release": 160, "scrub": 8},
        {("release", "__indirect_call")},
    )
    graph = shared.cpp_stack_functions(*arguments, callbacks={"release": "scrub"})
    require(
        shared.calculate(graph, "release")["peak"] == 168, "Callback closure was not charged to its full caller frame"
    )
    for callbacks in ({}, {"release": "foreign"}, {"scrub": "release"}):
        with TestCase().assertRaises(ValueError):
            shared.cpp_stack_functions(*arguments, callbacks=callbacks)
    code[0] = shared.Instruction(0, 2, "jmp", "*%rax")
    with TestCase().assertRaises(ValueError):
        shared.cpp_stack_functions(*arguments, callbacks={"release": "scrub"})

    # Independent work branches share a root; the bound is their maximum, not
    # the sum of every emitted frame. No real compiler/image evidence is claimed.
    names = set(LIMITS) - set(OPTIONAL)
    functions = {name: dict(local_peak=8, calls=[]) for name in names}
    functions["uefi_payload_entry"] = dict(
        local_peak=8, calls=[dict(target=name, live_bytes=8) for name in sorted(names)]
    )
    functions.update({name: dict(local_peak=8, calls=[]) for name in ("uefi_payload_fault", "uefi_payload_page_fault")})
    records = {name: [dict(record=name, bytes=8)] for name in names}
    graph = dict(functions=functions, compiler_frames=records, bounded_switches=[])
    result = validate(graph)
    require(result["normal"]["peak"] == 16, "Independent profile paths were added together")
    bad = deepcopy(graph)
    bad["compiler_frames"]["discover_acpi("][0]["bytes"] = 129
    with TestCase().assertRaisesRegex(ValueError, "frame ceiling"):
        validate(bad)
    bad = deepcopy(graph)
    bad["functions"]["uefi_payload_entry"]["calls"] = [
        row for row in bad["functions"]["uefi_payload_entry"]["calls"] if row["target"] != "discover_pci("
    ]
    with TestCase().assertRaisesRegex(ValueError, "Unreachable profile workload"):
        validate(bad)
    bad = deepcopy(graph)
    bad["functions"]["prepare_table_acpi("]["calls"] = [dict(target="discover_pci(", live_bytes=8)]
    with TestCase().assertRaisesRegex(ValueError, "retains its frame"):
        validate(bad)
    print("PASS tables shared stack adapter: branch maximum, frame cap, workload reachability, separated lifetime")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("directory", nargs="?", type=Path)
        parser.add_argument("output", nargs="?", type=Path)
        parser.add_argument("--build-dir", type=Path)
        parser.add_argument("--source-root", type=Path, default=ROOT)
        args = parser.parse_args()
        if args.directory and args.build_dir:
            parser.error("select one artifact directory")
        directory = args.build_dir or args.directory or args.source_root / "build/uefi"
        callback_contract(
            (args.source_root / "kernel/uefi/runtime.cpp").read_text(),
            (args.source_root / "kernel/uefi/dormant-runtime.inc").read_text(),
            (args.source_root / "kernel/pin-ledger.hpp").read_text(),
        )
        graph = shared.image_stack_graph(
            directory,
            ("payload", "acpi", "pci", "runtime"),
            args.source_root,
            protected=True,
            source_callbacks=CALLBACKS,
        )
        result = validate(graph)
        result["elf_sha256"] = hashlib.sha256((directory / "payload.elf").read_bytes()).hexdigest()
        out = args.output or directory / "table-stack"
        out.mkdir(parents=True, exist_ok=True)
        for name in ("payload", "acpi", "pci", "runtime"):
            (out / (name + ".su")).write_bytes((directory / "objects" / (name + ".su")).read_bytes())
        (out / "payload.disassembly.txt").write_text(graph["disassembly"])
        (out / "stack.json").write_text(json.dumps(result, indent=2) + "\n")
        print("PASS tables shared stack bound", result["peak_with_fault_reserve"], "of", result["stack_bytes"])
