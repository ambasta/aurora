#!/usr/bin/env python3
"""Regression bound for the explicitly reviewed IVRS bootstrap call paths."""

from pathlib import Path
import argparse
import json, sys


def validate(rows):
    def frame(fragment, required=True):
        values = [size for name, size in rows.items() if fragment in name]
        if not values:
            if required:
                raise ValueError("Missing compiler stack-usage record: " + fragment)
            return 0
        return max(values)

    payload = frame("payload_main(")
    wrapper = frame("discover_acpi(")
    pci = frame("discover_pci(")
    prepare = frame("prepare_ivrs_acpi(")
    scan = frame("PciInventory::scan(")
    helper = frame("::scan_ivrs_inventory(", False)
    # The template signature also names its lambda owner: use the small helper
    # record separately, never count the scan's frame as its wrapper a second time.
    helpers = [
        size for name, size in rows.items() if "::scan_ivrs_inventory(" in name and "PciInventory::scan(" not in name
    ]
    if not helpers:
        raise ValueError("Missing separated scan helper")
    helper = max(helpers)
    inspect = frame("inspect_ivrs(")
    bar_values = [size for name, size in rows.items() if "inspect_bar(" in name and "lambda" not in name]
    if not bar_values:
        raise ValueError("Missing separated BAR observation frame")
    bar = max(bar_values)
    parser = frame("Ivrs::parse_qemu_10_0_13(")
    topology = frame("Topology::parse(")
    ecam = frame("EcamWindow::read(")
    cap = frame("EcamWindow::iommu_capability(")
    verify = frame("PageTables::verify(", False)
    if (
        wrapper > 128
        or prepare > 5120
        or pci > 8192
        or scan > 6144
        or helper > 64
        or inspect > 4096
        or bar > 3072
        or parser > 1536
        or topology > 4096
        or max(ecam, cap) > 512
        or verify > 592
    ):
        raise ValueError("Reviewed IVRS frame bound exceeded")
    # 512 bytes cover bounded small callees beneath the explicit leaves, and
    # another512 are reserved for synchronous diagnostic exception delivery.
    leaf = 512
    paths = {
        "prepare": payload + wrapper + prepare + max(parser, topology) + leaf,
        "scan": payload + wrapper + pci + helper + scan + ecam + leaf,
        "observe": payload + wrapper + pci + inspect + max(parser, cap + leaf, verify + leaf),
        "bar": payload + wrapper + pci + bar + 1024,
    }
    peak = max(paths.values()) + 512
    if peak > 15360:
        raise ValueError("IVRS call-path stack reserve exhausted")
    return dict(paths=paths, peak_with_fault_reserve=peak, stack_bytes=16384, minimum_unused=16384 - peak)


def load(directory, source_root=None):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "ivrs_stack_shared", Path(__file__).with_name("kernel-uefi-owned-bytes-stack.py")
    )
    shared = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = shared
    spec.loader.exec_module(shared)
    parse = shared.stack_rows
    shared.stack_rows = lambda text: parse(text, lambda _: True)
    linked = shared.Elf(directory / "payload.elf")
    _, associations = shared.cpp_frames(directory, linked, ("payload", "acpi", "pci"), source_root=source_root)
    rows = {}
    for records in associations.values():
        for row in records:
            key = (
                row["object"]
                + ":"
                + row["source"]
                + ":"
                + str(row["line"])
                + ":"
                + str(row["column"])
                + ":"
                + row["record"]
            )
            if key in rows and rows[key] != row["bytes"]:
                raise ValueError("Conflicting compiler frame")
            rows[key] = row["bytes"]
    return rows


def self_test():
    rows = {
        "payload_main(": 224,
        "discover_acpi(": 48,
        "prepare_ivrs_acpi(": 4096,
        "discover_pci(": 5552,
        "PciInventory::scan(": 5664,
        "::scan_ivrs_inventory(": 32,
        "inspect_ivrs(": 2784,
        "Ivrs::parse_qemu_10_0_13(": 1184,
        "Topology::parse(": 3184,
        "EcamWindow::read(": 232,
        "EcamWindow::iommu_capability(": 152,
        "PageTables::verify(": 208,
        "inspect_bar(": 2272,
    }
    result = validate(rows)
    if result["peak_with_fault_reserve"] != 12776:
        raise ValueError("Wrong reviewed path calculation")
    cases = []
    for key in rows:
        changed = dict(rows)
        del changed[key]
        cases.append(changed)
        changed = dict(rows)
        changed[key] = 32768
        cases.append(changed)
    # Regress both diagnosed causes: a live ACPI parser frame or PCI scan
    # temporary storage folded into the long-lived discovery frame.
    for key, value in [("discover_acpi(", 4096), ("discover_pci(", 10688)]:
        changed = dict(rows)
        changed[key] = value
        cases.append(changed)
    rejected = 0
    for candidate in cases:
        try:
            validate(candidate)
        except ValueError:
            rejected += 1
    # PageTables verify may be inlined; its absent standalone record is valid.
    if rejected != len(cases) - 1:
        raise ValueError("Stack mutation unexpectedly accepted")
    print(f"PASS: IVRS stack budget regression1 positive/{rejected} rejection cases")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("directory", nargs="?", type=Path)
        parser.add_argument("output", nargs="?", type=Path)
        parser.add_argument("--build-dir", type=Path)
        parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
        args = parser.parse_args()
        if args.directory and args.build_dir:
            parser.error("select one artifact directory")
        directory = args.build_dir or args.directory or args.source_root / "build/uefi"
        result = validate(load(directory, args.source_root))
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        print("PASS: bounded IVRS stack paths " + json.dumps(result, sort_keys=True))
