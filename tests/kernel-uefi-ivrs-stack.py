#!/usr/bin/env python3
"""Profile budgets over the shared compiler-fact and handwritten-assembly graph."""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ivrs_stack_shared", ROOT / "scripts/kernel_stack.py")
shared = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shared
spec.loader.exec_module(shared)
require = shared.require

LIMITS = {
    "payload_main(": 15360,
    "discover_acpi(": 128,
    "prepare_ivrs_acpi(": 5120,
    "discover_pci(": 8192,
    "PciInventory::scan(": 6144,
    "::scan_ivrs_inventory(": 64,
    "inspect_ivrs(": 4096,
    "inspect_bar(": 3072,
    "Ivrs::parse_qemu_10_0_13(": 1536,
    "Topology::parse(": 4096,
    "EcamWindow::read(": 512,
    "EcamWindow::iommu_capability(": 512,
    "PageTables::verify(": 592,
}
OPTIONAL = ("PageTables::verify(",)
EXCLUDED = {"::scan_ivrs_inventory(": ("PciInventory::scan(",), "inspect_bar(": ("lambda",)}


def validate(graph):
    result = shared.profile_stack(
        graph,
        LIMITS,
        optional=OPTIONAL,
        excluded=EXCLUDED,
        default_limit=15360,
        fault_reserve=512,
        separated=(("prepare_ivrs_acpi(", "discover_pci("),),
    )
    return result


def self_test():
    from copy import deepcopy
    from unittest import TestCase

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
    bad["functions"]["prepare_ivrs_acpi("]["calls"] = [dict(target="discover_pci(", live_bytes=8)]
    with TestCase().assertRaisesRegex(ValueError, "retains its frame"):
        validate(bad)
    print("PASS ivrs shared stack adapter: branch maximum, frame cap, workload reachability, separated lifetime")


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
        graph = shared.image_stack_graph(directory, ("payload", "acpi", "pci"), args.source_root, protected=False)
        result = validate(graph)
        result["elf_sha256"] = hashlib.sha256((directory / "payload.elf").read_bytes()).hexdigest()
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        print("PASS ivrs shared stack bound", result["peak_with_fault_reserve"], "of", result["stack_bytes"])
