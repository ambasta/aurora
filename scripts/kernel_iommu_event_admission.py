#!/usr/bin/env python3
"""Exact finite Event image/stack evidence. No guest execution or review minting.

The existing fail-closed linked decoder and .su/.ci/source/object association
establish fresh stack facts for this image. No console frame measurements,
runtime interrupt allowances, or previous profile receipts are inherited.
"""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
RECEIPT = BUILD / "iommu-event-admission.json"
MODES = (
    "iommu-event-denial",
    "iommu-event-success",
    "iommu-event-overflow",
    "iommu-event-command-error",
    "iommu-event-observe",
)
ENTRY = "__au_v_m1_26kernel_iommu_event_service_n0__d18iommu_event_intake"
BRIDGE = "__au_runtime_iommu_event_entry"
VALUE_BRIDGE = "__au_runtime_iommu_event_value"
BOOTSTRAP = "_ZN6aurora4uefi16run_event_intakeEmRKNS0_5BytesERKNS0_14EventAdmissionE"
CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "event-intake")
ASSEMBLY_OBJECTS = ("payload-entry", "language", "memory")
TERMINAL_FIELDS = dict(
    magic=0,
    version=8,
    selector=16,
    phase=24,
    failure=32,
    completion=40,
    backing=48,
    ring=56,
    before_ring=64,
    after_ring=72,
    ring_bytes=80,
    dma_submitted=88,
    dma_completed=96,
    readiness_reads=104,
    polls=112,
    acknowledgements=120,
    output_bytes=128,
    exposed=136,
    producer_quiet=144,
    entered=152,
    serial_failed=160,
    before_valid=168,
    after_valid=176,
    checks=184,
    before_registers=192,
    after_registers=288,
    before_data=384,
    after_data=528,
)
BACKING_FIELDS = dict(
    device_table=0, page_table=8192, command_ring=12288, secret=16384, target=20480, helper=24576, sink=28672
)
RETAINED = {
    "terminal": ("uefi_event_terminal", 672, 8),
    "backing": ("uefi_event_backing", 32768, 4096),
    "ring": ("_ZN6aurora11iommu_event16BootLifetimeRing6bytes_E", 4096, 4096),
    "before_ring": ("uefi_event_before_ring", 4096, 4096),
    "after_ring": ("uefi_event_after_ring", 4096, 4096),
}


def need(value, reason):
    if not value:
        raise ValueError(reason)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("iommu_event_admission_common", ROOT / "scripts/kernel_program_console_admission.py")
console = load("iommu_event_noreturn", ROOT / "scripts/kernel_console_service_admission.py")
image = load("iommu_event_image", ROOT / "scripts/kernel_uefi_image.py")
digest = common.digest


def configure_paths(build_dir, source_root=None):
    global ROOT, BUILD, RECEIPT
    common.configure_paths(build_dir, source_root or ROOT)
    ROOT, BUILD = common.ROOT, common.BUILD
    RECEIPT = BUILD / "iommu-event-admission.json"
    console.configure_paths(BUILD, ROOT)


read_json = common.read_json


def cpp_objects(mode):
    return CPP_OBJECTS[:-1] if mode == "iommu-event-observe" else CPP_OBJECTS


def build_files(mode):
    names = [
        "payload.ld",
        "payload.elf",
        "payload.bin",
        "esp/EFI/BOOT/BOOTX64.EFI",
        "uefi-payload.hpp",
        "language.s",
        "language.stack.json",
    ]
    names += [name + ".o" for name in sorted(image.event_objects(mode))]
    names += [name + suffix for name in cpp_objects(mode) + ("loader",) for suffix in (".su", ".ci")]
    return common.build_artifacts(names)


def verify_bridge(decoder, rows, starts):
    need(
        len(rows) == 6
        and [(row.op, row.args) for row in rows[:3]] == [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("mov", "%rdi,%r11")]
        and rows[3].op == "call"
        and starts.get(decoder.target_of(rows[3])) == ENTRY
        and [(row.op, row.args) for row in rows[4:]] == [("leave", ""), ("ret", "")],
        "Changed six-qword private Event entry bridge",
    )


def verify_value_bridge(decoder, rows, starts):
    need(
        len(rows) == 1 and rows[0].op == "jmp" and starts.get(decoder.target_of(rows[0])) == "aurora_kernel_value",
        "Changed private Event value bridge",
    )


def verify_stack_budgets(normal, consumer, fault):
    need(
        all(type(value) is int and value >= 0 for value in (normal, consumer, fault)), "Invalid Event stack measurement"
    )
    # Preserve the existing 15-KiB admission cap and at least the existing
    # 512-byte exception reserve inside the unchanged 16-KiB boot stack.
    reserve = max(512, fault)
    need(normal + reserve <= 15360 and consumer + reserve <= 15360, "Event mixed stack/fault reserve exhausted")
    return reserve


def backing_evidence(linked, directory):
    symbols = {}
    for symbol in linked.symbols:
        if symbol.name in {item[0] for item in RETAINED.values()} | {"__payload_read_end", "__payload_memory_end"}:
            need(symbol.name not in symbols, "Ambiguous retained Event symbol: " + symbol.name)
            symbols[symbol.name] = symbol
    begin, end = symbols["__payload_read_end"].address, symbols["__payload_memory_end"].address
    need(0 < begin < end <= 0x20000 and begin % 4096 == end % 4096 == 0, "Invalid retained payload RW bound")
    owner = load("iommu_event_backing_decoder", ROOT / "scripts/kernel_stack.py").Elf(
        directory / "objects" / "event-intake.o"
    )
    result = {}
    for role, (name, size, alignment) in RETAINED.items():
        symbol = symbols[name]
        section = linked.sections[symbol.section]
        need(
            symbol.kind == 1
            and symbol.size == size
            and symbol.address % alignment == 0
            and begin <= symbol.address
            and symbol.address + size <= end,
            "Changed retained Event object extent/alignment: " + role,
        )
        need(
            section[1] == 8
            and section[2] == 3
            and section[8] >= alignment
            and section[3] <= symbol.address
            and symbol.address + size <= section[3] + section[5],
            "Retained Event object must occupy allocated writable non-executable zero-initialized BSS: " + role,
        )
        originals = [row for row in owner.symbols if row.name == name and row.section]
        need(
            len(originals) == 1
            and originals[0].kind == 1
            and originals[0].size == size
            and owner.sections[originals[0].section][1] == 8,
            "Retained Event object lacks exact native owner: " + role,
        )
        for other in result.values():
            need(
                symbol.address + size <= other["offset"] or other["offset"] + other["bytes"] <= symbol.address,
                "Overlapping retained Event allocations",
            )
        result[role] = dict(
            symbol=name, offset=symbol.address, bytes=size, alignment=alignment, arena_offset=0x22000 + symbol.address
        )
    return dict(
        objects=result,
        retained_bytes=sum(row["bytes"] for row in result.values()),
        payload_rw_begin=begin,
        payload_memory_end=end,
        terminal_fields=TERMINAL_FIELDS,
        backing_fields=BACKING_FIELDS,
        lifetime="complete allocations retained for this boot, including failure; no reclamation authority",
    )


def stack_evidence(directory, mode):
    need(mode in MODES, "Unsupported Event stack mode")
    decoder = load("iommu_event_stack_decoder", ROOT / "scripts/kernel_stack.py")
    decoder.CPP_OBJECTS = cpp_objects(mode)
    linked = decoder.Elf(directory / "payload.elf")
    need(linked.type == 2, "Expected linked Event executable")
    need(
        not subprocess.check_output(["nm", "-u", directory / "payload.elf"], text=True).strip(),
        "Unresolved Event payload",
    )
    code, disassembly = decoder.disassemble(directory / "payload.elf")
    for row in code.values():
        need(
            row.op not in ("sti", "iret", "iretq", "syscall", "sysenter", "sysexit", "sysret", "int", "int3"),
            "Event image enables IRQs or crosses a user/interrupt boundary",
        )
    compiler_edges = set()
    frames, associations = decoder.cpp_frames(directory, linked, edges=compiler_edges, source_root=ROOT)
    language, memory = (decoder.Elf(directory / "objects" / (name + ".o")) for name in ("language", "memory"))
    for obj in (language, memory):
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = [item for name in ASSEMBLY_OBJECTS for item in decoder.linked_assembly(linked, directory, name)]
    fixed = {"uefi_payload_entry", "uefi_payload_fault", "uefi_payload_page_fault", "fault_common"}
    need(
        set(linked.functions) == set(frames) | set(language.functions) | set(memory.functions) | fixed,
        "Unaccounted Event linked function/frame inventory",
    )
    need(
        (
            {"aurora_kernel_value"}
            if mode == "iommu-event-observe"
            else {ENTRY, BRIDGE, VALUE_BRIDGE, "aurora_kernel_value"}
        )
        <= language.functions.keys(),
        "Missing private Event source/bridge inventory",
    )
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    need(len(starts) == len(linked.functions), "Ambiguous Event linked function starts")
    decoder.NORETURN = frozenset(
        name for name in linked.functions if name == "uefi_payload_fail" or "4failE" in name or name == BOOTSTRAP
    )
    bridges = () if mode == "iommu-event-observe" else (BRIDGE, VALUE_BRIDGE)
    functions = decoder.compiled_stack_functions(
        directory, linked, language, code, starts, frames, compiler_edges, bridges
    )
    functions.update(
        decoder.assembly_stack_functions(linked.functions, code, starts, set(memory.functions) | fixed | set(bridges))
    )
    console.verify_noreturn(functions, decoder.NORETURN)
    body = lambda name: [
        row
        for address, row in sorted(code.items())
        if linked.functions[name].address <= address < linked.functions[name].address + linked.functions[name].size
    ]
    if mode != "iommu-event-observe":
        verify_bridge(decoder, body(BRIDGE), starts)
        verify_value_bridge(decoder, body(VALUE_BRIDGE), starts)
    for name in functions:
        decoder.calculate(functions, name)
    normal = decoder.calculate(functions, "uefi_payload_entry")
    consumer = decoder.calculate(functions, "aurora_kernel_value" if mode == "iommu-event-observe" else ENTRY)
    bootstrap = decoder.calculate(functions, "uefi_event_observation" if mode == "iommu-event-observe" else BOOTSTRAP)
    fault = 48 + max(
        decoder.calculate(functions, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    reserve = verify_stack_budgets(normal["peak"], consumer["peak"], fault)
    if mode == "iommu-event-observe":
        need(
            "uefi_event_observation" in normal["closure"] and BOOTSTRAP not in functions,
            "Readonly observation missing or producer reachable",
        )
    else:
        need(BOOTSTRAP in normal["closure"], "Event bootstrap unreachable from actual payload entry")
    need(
        (ENTRY in normal["closure"]) == (mode not in ("iommu-event-overflow", "iommu-event-observe")),
        "Event source entry reachability disagrees with exact mode",
    )
    return dict(
        stack_bytes=16384,
        cap_bytes=15360,
        exception_reserve_bytes=reserve,
        normal=normal,
        bootstrap=bootstrap,
        consumer=consumer,
        boot_fault=fault,
        normal_with_exception=normal["peak"] + reserve,
        consumer_with_exception=consumer["peak"] + reserve,
        compiler_frames=associations,
        linked_functions=functions,
        assembly_objects=assembly,
        page_verifier=dict(traversal_slots=4, recursion="rejected"),
        disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
    )


def image_evidence(directory, mode):
    need(
        {path.stem for path in (directory / "objects").glob("*.o")} == image.event_objects(mode),
        "Foreign or missing Event build object",
    )
    binary = (directory / "payload.bin").read_bytes()
    elf = (directory / "payload.elf").read_bytes()
    image.pe_validate((directory / "esp/EFI/BOOT/BOOTX64.EFI").read_bytes(), binary)
    image.elf_validate(elf, binary)
    result = image.event_image_policy(directory, mode=mode)
    for name in cpp_objects(mode) + ASSEMBLY_OBJECTS:
        relocations = subprocess.check_output(["readelf", "-rW", directory / "objects" / (name + ".o")], text=True)
        kinds = set(re.findall(r"R_X86_64_\w+", relocations))
        need(kinds <= {"R_X86_64_PC32", "R_X86_64_PLT32"}, "Non-PIC Event object: " + name)
        need(name != "memory" or not kinds, "Memory primitives acquired a helper/relocation")
    decoder = load("iommu_event_image_decoder", ROOT / "scripts/kernel_stack.py")
    if mode != "iommu-event-observe":
        result["backing"] = backing_evidence(decoder.Elf(directory / "payload.elf"), directory)
    return result


def emit(mode):
    RECEIPT.unlink(missing_ok=True)
    need(mode in MODES, "Unsupported Event mode")
    before = common.hashes(build_files(mode))
    result = dict(
        schema="aurora-iommu-event-admission-v1",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        image=image_evidence(BUILD, mode),
        stack=stack_evidence(BUILD, mode),
    )
    common.write_admission(RECEIPT, result, build_files(mode), before)
    print("PASS: exact finite Event image/stack checks; independent review and guest qualification remain separate.")
    return result


def checked(mode):
    need(mode in MODES, "Unsupported iommu event profile")
    receipt = common.check_admission(RECEIPT, "aurora-iommu-event-admission-v1", mode, build_files(mode))
    need(
        receipt["image"] == image_evidence(BUILD, mode)
        and receipt["stack"] == json.loads(json.dumps(stack_evidence(BUILD, mode))),
        "Event image/stack evidence does not reproduce",
    )
    return receipt


def main():
    parser = argparse.ArgumentParser()
    common.path_arguments(parser)
    parser.add_argument("action", choices=("emit", "checked", "diagnose"))
    parser.add_argument("--mode", required=True, choices=MODES)
    args = parser.parse_args()
    configure_paths(args.build_dir or args.source_root / "build/uefi", args.source_root)
    if args.action == "emit":
        emit(args.mode)
    elif args.action == "diagnose":
        print(json.dumps(stack_evidence(BUILD, args.mode), indent=2, sort_keys=True))
    else:
        checked(args.mode)
        print("PASS: current image admission; independent qualification not claimed.")


if __name__ == "__main__":
    try:
        main()
    except common.Blocked as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit("FAIL: finite Event admission: " + str(error)) from error
