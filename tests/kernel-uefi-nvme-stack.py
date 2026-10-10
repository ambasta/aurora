#!/usr/bin/env python3
"""Compiler-metadata stack bound for the fixed BAR-preparation profile.

GCC's complete emitted call graph, including tail calls, is trusted here just as
its .su frame bounds are. This is not an independent instruction/CFG proof.
The shared parser binds every frame to its exact object and linked function;
linked direct transfers additionally cross-check the finite preparation graph.
"""

from graphlib import TopologicalSorter
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

spec = importlib.util.spec_from_file_location(
    "nvme_stack_shared", Path(__file__).with_name("kernel-uefi-owned-bytes-stack.py")
)
shared = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = shared
spec.loader.exec_module(shared)
require = shared.require
BOUNDED = ("prepare_bar_acpi(", "discover_pci(", "inspect_bar(", "prepare_nvme_pages(")
parse_rows = shared.stack_rows
shared.stack_rows = lambda text: parse_rows(text, lambda name: any(part in name for part in BOUNDED))
MEMORY = frozenset(("memcpy", "memmove", "memset", "memcmp"))


def load(directory, units=("payload", "acpi", "pci"), source_root=None):
    linked = shared.Elf(directory / "payload.elf")
    require(linked.type == 2, "Expected linked preparation ELF")
    edges = set()
    _, receipts = shared.cpp_frames(directory, linked, units, edges, source_root)
    identity = ("source", "line", "column", "record", "bytes", "kind")
    require(
        all(len({tuple(row[key] for key in identity) for row in rows}) == 1 for rows in receipts.values()),
        "Conflicting preparation COMDAT frame",
    )
    records = {name: rows[0] for name, rows in receipts.items()}
    sources = {row["source"]: row["source_sha256"] for row in records.values()}
    return linked, records, edges, sources


def queue_bound(directory, linked, records, edges):
    def symbol(fragment):
        found = [name for name, row in records.items() if fragment in row["record"]]
        require(len(found) == 1, "Missing or ambiguous preparation helper: " + fragment)
        return found[0]

    root = symbol("prepare_nvme_pages(")
    create = symbol("NvmeQueueBundle::prepare(")
    discard = symbol("NvmeQueueBundle::discard_unpublished(")
    page = symbol("NvmeQueueBundle::page(")
    code, _ = shared.disassemble(directory / "payload.elf")
    starts = {value.address: name for name, value in linked.functions.items()}
    frames = {name: row["bytes"] for name, row in records.items()}
    # These existing assembly primitives are independently checked with the
    # existing decoder, not assigned a guessed external leaf allowance.
    memory = shared.Elf(directory / "objects" / "memory.o")
    require(memory.type == 1 and set(memory.functions) == MEMORY, "Unexpected memory primitive inventory")
    for name, function in memory.functions.items():
        require(name in linked.functions, "Missing linked memory primitive")
        shared.associate_object(linked, memory, function)
        proof = shared.analyze_function(linked.functions[name], code, starts)
        require(not proof["calls"], "Memory primitive acquired a subordinate call")
        frames[name] = proof["local_peak"]
    # GCC describes emitted calls/tail calls; cycles would invalidate summing
    # distinct frames. A local switch jump adds no frame under this trust model.
    visited, pending = set(), [root]
    calls = {name: {b for a, b in edges if a == name} for name in frames}
    while pending:
        name = pending.pop()
        require(name in frames, "Unknown or unaccounted preparation callee: " + name)
        if name not in visited:
            visited.add(name)
            pending.extend(calls[name])
    tuple(TopologicalSorter({name: calls[name] for name in visited}).static_order())
    require(all(8 <= frames[name] <= 1024 for name in visited), "Invalid preparation helper frame")
    bound = sum(frames[name] for name in visited)
    require({create, discard, page} <= visited, "Missing emitted preparation path")
    require(
        all(name in visited for name, row in records.items() if "NvmeQueueBundle::" in row["record"]),
        "Unaccounted emitted queue helper",
    )
    compiler = {(a, b) for a, b in edges if a in visited}
    direct = set()
    for name in visited:
        function = linked.functions[name]
        for address, insn in code.items():
            if not function.address <= address < function.address + function.size:
                continue
            if insn.op != "call" and insn.op not in shared.BRANCHES:
                continue
            if insn.args.startswith("*"):
                require(insn.op == "jmp", "Indirect preparation call")
                # GCC reports indirect calls AND tail calls as __indirect_call;
                # Closure lookup rejects that unresolved target. Local switch
                # jumps do not appear as calls and do not add a stack frame.
                # Their destinations are trusted compiler output, not proved here.
                continue
            target = shared.target_of(insn)
            if insn.op != "call" and function.address <= target < function.address + function.size:
                continue
            require(target in starts, "Preparation transfer lacks exact function entry")
            direct.add((name, starts[target]))
    require(direct == compiler, "Compiler/linked preparation call edges disagree")
    require((root, create) in compiler, "Missing preparation creation edge")
    cancelled = [name for name, row in records.items() if "NvmeQueueBundle::cancel(" in row["record"]]
    require(len(cancelled) <= 1, "Ambiguous cancellation helper")
    require((root, cancelled[0] if cancelled else discard) in compiler, "Missing preparation cancellation edge")
    return dict(
        bytes=bound,
        frames={name: frames[name] for name in sorted(visited)},
        compiler_edges=len(compiler),
        basis="GCC complete call graph and stack usage; exact object/link association",
    )


def calculate(rows, queue_bytes):
    def size(fragment, predicate=lambda name: True):
        found = [value for name, value in rows.items() if fragment in name and predicate(name)]
        if not found:
            raise ValueError("Missing preparation stack frame: " + fragment)
        return max(found)

    payload = size("payload_main(")
    wrapper = size("discover_acpi(")
    acpi = size("prepare_bar_acpi(")
    topology = size("Topology::parse(")
    pci = size("discover_pci(")
    bar = size("inspect_bar(", lambda name: "lambda" not in name)
    prepare = size("prepare_nvme_pages(")
    verify = size("PageTables::verify(", lambda name: "lambda" not in name)
    resource = size("PciResources::parse_as(")
    ecam = size("EcamWindow::read(")
    if payload > 512 or wrapper > 128 or acpi > 5120 or topology > 4096 or pci > 11000 or bar > 3072:
        raise ValueError("Reviewed preparation frame limit exceeded")
    if max(prepare, verify, resource, ecam) > 1024:
        raise ValueError("Reviewed preparation helper limit exceeded")
    modeled = (
        "payload_main(",
        "discover_acpi(",
        "prepare_bar_acpi(",
        "Topology::parse(",
        "discover_pci(",
        "inspect_bar(",
        "prepare_nvme_pages(",
        "NvmeQueueBundle::prepare(",
        "NvmeQueueBundle::cancel(",
        "NvmeQueueBundle::discard_unpublished(",
        "NvmeQueueBundle::scrub_all(",
        "NvmeQueueBundle::page(",
        "PageTables::verify(",
        "PciResources::parse_as(",
        "EcamWindow::read(",
    )
    if any(
        value < 0 or (value > 512 and not any(fragment in name for fragment in modeled)) for name, value in rows.items()
    ):
        raise ValueError("Unmodeled large preparation frame")
    # The verifier uses a fixed four-slot local traversal. 512
    # covers subordinate small callees; a separate 512 covers synchronous fault
    # delivery, stack alignment and the existing fail-stop serial diagnostics.
    leaf = 512
    fault = 512
    verifier = verify
    require(type(queue_bytes) is int and queue_bytes >= prepare, "Missing finite preparation bound")
    queues = queue_bytes
    paths = {
        "acpi": payload + wrapper + acpi + topology + leaf,
        "pci": payload + wrapper + pci + max(verifier, ecam) + leaf,
        "bar": payload + wrapper + pci + bar + max(queues, resource, verifier, ecam) + leaf,
    }
    peak = max(paths.values()) + fault
    if peak > 15360:
        raise ValueError("16 KiB preparation stack reserve exhausted")
    return dict(
        paths=paths, peak_with_fault_reserve=peak, fault_reserve=fault, stack_bytes=16384, minimum_unused=16384 - peak
    )


def linked_edges(disassembly):
    current = None
    edges = []
    for line in disassembly.splitlines():
        heading = re.match(r"^[0-9a-f]+ <(.+)>:$", line)
        if heading:
            current = heading[1]
        branch = re.search(r"\b(?:call|jmp)\s+[0-9a-f]+ <(.+)>", line)
        if current and branch:
            edges.append((current, branch[1]))
    if any("prepare_bar_acpi(" in caller and "discover_pci(" in callee for caller, callee in edges):
        raise ValueError("ACPI parsing retains its frame through PCI discovery")
    for caller, callee in [
        ("payload_main", "discover_acpi("),
        ("discover_acpi(", "prepare_bar_acpi("),
        ("discover_acpi(", "discover_pci("),
        ("discover_pci(", "inspect_bar("),
        ("inspect_bar(", "prepare_nvme_pages("),
        ("prepare_nvme_pages(", "NvmeQueueBundle::prepare("),
    ]:
        if not any(caller in source and callee in target for source, target in edges):
            raise ValueError("Missing reviewed linked preparation edge: " + caller + " -> " + callee)
    return edges


def self_test():
    rows = dict(
        zip(
            (
                "payload_main(",
                "discover_acpi(",
                "prepare_bar_acpi(",
                "Topology::parse(",
                "discover_pci(",
                "inspect_bar(",
                "prepare_nvme_pages(",
                "PageTables::verify(",
                "PciResources::parse_as(",
                "EcamWindow::read(",
            ),
            (240, 48, 3504, 3184, 10592, 2416, 208, 208, 640, 232),
        )
    )
    if calculate(rows, 456)["peak_with_fault_reserve"] != 14960:
        raise RuntimeError("Incorrect explicit preparation stack sum")
    rejected = 0
    for key in rows:
        for remove in (False, True):
            candidate = dict(rows)
            if remove:
                del candidate[key]
            else:
                candidate[key] = 32768
            try:
                calculate(candidate, 456)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError("Invalid preparation frame accepted")
    try:
        calculate(dict(rows, unmodeled_subordinate=513), 456)
    except ValueError:
        rejected += 1
    else:
        raise RuntimeError("Unmodeled large subordinate accepted")
    required = [
        ("payload_main", "discover_acpi("),
        ("discover_acpi(", "prepare_bar_acpi("),
        ("discover_acpi(", "discover_pci("),
        ("discover_pci(", "inspect_bar("),
        ("inspect_bar(", "prepare_nvme_pages("),
        ("prepare_nvme_pages(", "NvmeQueueBundle::prepare("),
    ]
    text = "".join(f"100 <{caller}>:\n 100: call 200 <{callee}>\n" for caller, callee in required)
    linked_edges(text)
    for index in range(len(required)):
        candidate = "".join(f"100 <{a}>:\n 100: call 200 <{b}>\n" for at, (a, b) in enumerate(required) if at != index)
        try:
            linked_edges(candidate)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("Missing linked preparation edge accepted")
    try:
        linked_edges(text + "100 <prepare_bar_acpi(>:\n 100: call 200 <discover_pci(>\n")
    except ValueError:
        rejected += 1
    else:
        raise RuntimeError("Nested ACPI lifetime accepted")
    print(f"PASS: preparation stack/frame/edge controls, 2 positives and {rejected} rejections")


def emission_check(directory):
    """One real emitted closure and six representative corruptions."""
    from unittest import TestCase

    linked, records, edges, _ = load(directory, ("pci",))
    result = queue_bound(directory, linked, records, edges)
    # Existing console/Event callers choose their inventory after importing the
    # shared module. Exercise that default as well as load()'s explicit inventory.
    previous, shared.CPP_OBJECTS = shared.CPP_OBJECTS, ("pci",)
    try:
        _, selected = shared.cpp_frames(directory, linked)
        require({name: rows[0] for name, rows in selected.items()} == records, "Late-bound object inventory changed")
    finally:
        shared.CPP_OBJECTS = previous
    root = next(name for name, row in records.items() if "prepare_nvme_pages(" in row["record"])
    # Choose a shared callee from this compiler's graph, without requiring ready()
    # or another optimization-dependent helper to remain a standalone function.
    caller, callee = next(
        (a, b)
        for a, b in sorted(edges)
        if a in result["frames"]
        and a != root
        and (root, b) not in edges
        and sum(y == b and x in result["frames"] for x, y in edges) > 1
    )
    for changed, error in (
        (edges - {(caller, callee)}, "Compiler/linked preparation call edges disagree"),
        (edges | {(root, callee)}, "Compiler/linked preparation call edges disagree"),
        (edges | {(callee, root)}, "cycle"),
        (edges | {(root, "__indirect_call")}, "Unknown or unaccounted"),
    ):
        with TestCase().assertRaisesRegex(ValueError, error):
            queue_bound(directory, linked, records, changed)
    function = linked.functions[root]
    section = linked.sections[function.section]
    offset = section[4] + function.address - section[3]
    mutated = bytearray(linked.data)
    mutated[offset] ^= 1
    su = directory / "objects" / "pci.su"
    for path, contents in ((su, b"\n".join(su.read_bytes().splitlines()[1:])), (directory / "payload.elf", mutated)):
        original = path.read_bytes()
        try:
            path.write_bytes(contents)
            with TestCase().assertRaises(ValueError):
                current, rows, calls, _ = load(directory, ("pci",))
                queue_bound(directory, current, rows, calls)
        finally:
            path.write_bytes(original)
    print(f"PASS: fresh PCI emission, {len(result['frames'])} finite frames, 6 corruptions; optimized={not __debug__}")


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
        "-fpie -fvisibility=hidden"
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
        subprocess.run(["ld", "-e", "0", "-o", str(directory / "payload.elf"), *objects], check=True)
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
        parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
        args = parser.parse_args()
        require(bool(args.directory) != bool(args.build_dir), "Select exactly one artifact directory")
        directory = args.build_dir or args.directory
        linked, records, compiler_edges, sources = load(directory, source_root=args.source_root)
        queues = queue_bound(directory, linked, records, compiler_edges)
        result = calculate(
            {
                f"{row['source']}:{row['line']}:{row['column']}:{row['record']}": row["bytes"]
                for row in records.values()
            },
            queues["bytes"],
        )
        result.update(preparation=queues, source_hashes=sources)
        elf = directory / "payload.elf"
        disassembly = subprocess.check_output(["objdump", "-drwC", str(elf)], text=True)
        edges = linked_edges(disassembly)
        result.update(payload_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(), linked_edges=len(edges))
        if args.output:
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        print("PASS: bounded preparation stack paths " + json.dumps(result, sort_keys=True))
