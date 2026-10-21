#!/usr/bin/env python3
"""Profile budgets over the shared compiler-fact and handwritten-assembly graph."""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("nvme_stack_shared", ROOT / "scripts/kernel_stack.py")
shared = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shared
spec.loader.exec_module(shared)
require = shared.require
BOUNDED = ("prepare_bar_acpi(", "discover_pci(", "inspect_bar(", "prepare_nvme_pages(")


def bounded(name):
    return any(part in name for part in BOUNDED)


LIMITS = {
    "payload_main(": 512,
    "discover_acpi(": 128,
    "prepare_bar_acpi(": 5120,
    "Topology::parse(": 4096,
    "discover_pci(": 11000,
    "inspect_bar(": 3072,
    "prepare_nvme_pages(": 1024,
    "PageTables::verify(": 1024,
    "PciResources::parse_as(": 1024,
    "EcamWindow::read(": 1024,
    "NvmeQueueBundle::prepare(": 1024,
    "NvmeQueueBundle::discard_unpublished(": 1024,
    "NvmeQueueBundle::page(": 1024,
    "NvmeQueueBundle::cancel(": 1024,
    "NvmeQueueBundle::scrub_all(": 1024,
}
OPTIONAL = ("NvmeQueueBundle::cancel(", "NvmeQueueBundle::scrub_all(")
EXCLUDED = {"inspect_bar(": ("lambda",), "PageTables::verify(": ("lambda",)}


def validate(graph):
    result = shared.profile_stack(
        graph,
        LIMITS,
        optional=OPTIONAL,
        excluded=EXCLUDED,
        default_limit=512,
        fault_reserve=512,
        separated=(("prepare_bar_acpi(", "discover_pci("),),
    )
    result["preparation"] = queue_bound(graph)
    return result


def queue_bound(graph):
    records, functions = graph["compiler_frames"], graph["functions"]
    roots = shared.frame_names(records, "prepare_nvme_pages(")
    require(len(roots) == 1, "Missing or ambiguous preparation root")
    result = shared.calculate(functions, next(iter(roots)))
    closure = set(result["closure"])
    for fragment in ("NvmeQueueBundle::prepare(", "NvmeQueueBundle::discard_unpublished(", "NvmeQueueBundle::page("):
        names = shared.frame_names(records, fragment)
        require(names and names <= closure, "Missing reachable preparation operation: " + fragment)
    require(all(8 <= functions[name]["local_peak"] <= 1024 for name in closure), "Invalid preparation helper frame")
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
    functions["prepare_nvme_pages("]["calls"] = [
        dict(target=name, live_bytes=8)
        for name in ("NvmeQueueBundle::prepare(", "NvmeQueueBundle::discard_unpublished(", "NvmeQueueBundle::page(")
    ]
    result = validate(graph)
    require(result["normal"]["peak"] == 24, "Independent profile paths were added together")
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
    bad["functions"]["prepare_bar_acpi("]["calls"] = [dict(target="discover_pci(", live_bytes=8)]
    with TestCase().assertRaisesRegex(ValueError, "retains its frame"):
        validate(bad)
    print("PASS nvme shared stack adapter: branch maximum, frame cap, workload reachability, separated lifetime")


def emission_check(directory):
    """Exercise the actual shared composition and reject corrupted sidecars/object bytes."""
    from unittest import TestCase

    def read():
        return shared.image_stack_graph(
            directory, ("pci",), ROOT, generated=False, payload_entry=False, allow_bounded=bounded
        )

    graph = read()
    result = queue_bound(graph)
    linked = graph["linked"]
    root = next(iter(shared.frame_names(graph["compiler_frames"], "prepare_nvme_pages(")))
    function = linked.functions[root]
    section = linked.sections[function.section]
    offset = section[4] + function.address - section[3]
    mutated = bytearray(linked.data)
    mutated[offset] ^= 1
    su = directory / "objects/pci.su"
    ci = directory / "objects/pci.ci"
    lines = ci.read_text().splitlines(keepends=True)
    edge = next(line for line in lines if line.startswith("edge:"))
    for path, contents in (
        (su, b"\n".join(su.read_bytes().splitlines()[1:])),
        (ci, "".join(line for line in lines if line != edge).encode()),
        (directory / "payload.elf", mutated),
    ):
        original = path.read_bytes()
        try:
            path.write_bytes(contents)
            with TestCase().assertRaises(ValueError):
                queue_bound(read())
        finally:
            path.write_bytes(original)
    print(
        f"PASS fresh PCI shared graph: {len(result['closure'])} reachable functions, "
        f"3 corruptions; optimized={not __debug__}"
    )


def emission_test():
    import os
    import shlex
    import tempfile

    root = Path(__file__).resolve().parents[1]
    cxx = shlex.split(os.environ.get("CXX", "g++"))
    # Production BAR PCI O2 policy; no retained snapshot, no guest or executable run.
    flags = (
        "-std=c++23 -O2 -fstack-usage -fcallgraph-info=su -Wall -Wextra -Werror "
        "-ffreestanding -fcf-protection=none -mstringop-strategy=libcall "
        "-fno-exceptions -fno-rtti -fno-stack-protector -fno-asynchronous-unwind-tables "
        "-fno-unwind-tables -mno-red-zone -mgeneral-regs-only -fno-tree-loop-distribute-patterns "
        "-fpie -fvisibility=hidden -DAURORA_RUNTIME_IMAGE_POLICY=one_page"
    ).split()
    flags += ["-DAURORA_UEFI_" + name for name in ("ACPI", "PCI", "BAR_CAPTURE", "BAR_EDK2", "NVME_PREPARE")]
    with tempfile.TemporaryDirectory(prefix="aurora-nvme-stack-") as temporary:
        directory = Path(temporary)
        (directory / "objects").mkdir(exist_ok=True)
        subprocess.run(
            cxx + flags + ["-c", "kernel/uefi/pci.cpp", "-o", str(directory / "objects" / "pci.o")],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["as", "--64", "kernel/uefi/memory.S", "-o", str(directory / "objects" / "memory.o")], cwd=root, check=True
        )
        objects = [str(directory / "objects" / name) for name in ("pci.o", "memory.o")]
        script = directory / "fixture.ld"
        script.write_text(
            "SECTIONS { . = 0; .text : { *(.text .text.*) } __payload_text_end = .; "
            ".rodata : { *(.rodata .rodata.*) } __payload_read_end = .; "
            ".data : { *(.data .data.*) } .bss : { *(.bss .bss.*) } }\n"
        )
        subprocess.run(["ld", "-T", str(script), "-e", "0", "-o", str(directory / "payload.elf"), *objects], check=True)
        subprocess.run(
            ["objcopy", "-O", "binary", str(directory / "payload.elf"), str(directory / "payload.bin")], check=True
        )
        emission_check(directory)
        subprocess.run([sys.executable, "-B", "-O", __file__, "--emission-check", temporary], check=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif sys.argv[1:] == ["--emission-test"]:
        emission_test()
    elif len(sys.argv) == 3 and sys.argv[1] == "--emission-check":
        emission_check(Path(sys.argv[2]))
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
        graph = shared.image_stack_graph(
            directory, ("payload", "acpi", "pci"), args.source_root, protected=False, allow_bounded=bounded
        )
        result = validate(graph)
        result["elf_sha256"] = hashlib.sha256((directory / "payload.elf").read_bytes()).hexdigest()
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        print("PASS nvme shared stack bound", result["peak_with_fault_reserve"], "of", result["stack_bytes"])
