#!/usr/bin/env python3
"""Automatic graphics image/stack checks, separate from independent qualification."""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
MODES = ("framebuffer", "framebuffer-record", "framebuffer-permissions", "framebuffer-stale")
ENTRY = "__au_v_m1_22kernel_display_service_n0__d15display_service"
BRIDGE = "__au_runtime_display_entry"
VALUE_BRIDGE = "__au_runtime_display_value"
BRIDGES = (BRIDGE, VALUE_BRIDGE)


def need(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("framebuffer_common", ROOT / "scripts/kernel_program_console_admission.py")
console = load("framebuffer_decoder_controls", ROOT / "scripts/kernel_console_service_admission.py")
console.ENTRY, console.BRIDGE = ENTRY, BRIDGE


def configure_paths(build_dir, source_root=None):
    global ROOT, BUILD
    common.configure_paths(build_dir, source_root or ROOT)
    ROOT, BUILD = common.ROOT, common.BUILD
    console.configure_paths(BUILD, ROOT)


def verify_stack_budget(normal, fault):
    need(all(type(value) is int and value >= 0 for value in (normal, fault)), "Invalid stack measurement")
    need(normal + fault <= 15360, "Existing 16 KiB mixed-stack/fault reserve exhausted")


def verify_value_bridge(decoder, rows, starts):
    need(
        len(rows) == 1 and rows[0].op == "jmp" and starts.get(decoder.target_of(rows[0])) == "aurora_kernel_value",
        "Display value bridge must tail-call the exact scalar value root",
    )


def stack_evidence(directory):
    decoder = load("framebuffer_stack_decoder", ROOT / "scripts/kernel_stack.py")
    decoder.CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "framebuffer")
    original_rows = decoder.stack_rows
    original_bounded_rows = []

    def bounded_rows(text):
        original_bounded_rows.extend(line for line in text.splitlines() if line.endswith("\tdynamic,bounded"))
        return original_rows(text, allow_bounded=lambda signature: "FramebufferPayload::restore_fixture(" in signature)

    decoder.stack_rows = bounded_rows
    linked = decoder.Elf(directory / "payload.elf")
    need(linked.type == 2, "Expected linked payload")
    need(not subprocess.check_output(["nm", "-u", directory / "payload.elf"], text=True).strip(), "Unresolved payload")
    code, disassembly = decoder.disassemble(directory / "payload.elf")
    need(not any(row.op == "sti" for row in code.values()), "Output-only profile must not enable interrupts")
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    need(len(starts) == len(linked.functions), "Ambiguous function starts")
    compiler_edges = set()
    frames, associations = decoder.cpp_frames(directory, linked, edges=compiler_edges, source_root=ROOT)
    language, memory = (
        decoder.Elf(directory / "objects" / "language.o"),
        decoder.Elf(directory / "objects" / "memory.o"),
    )
    for obj in (language, memory):
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = decoder.linked_assembly(linked, directory, "payload-entry")
    accounted = (
        set(frames)
        | set(language.functions)
        | set(memory.functions)
        | {"uefi_payload_entry", "uefi_payload_fault", "uefi_payload_page_fault", "fault_common"}
    )
    need(set(linked.functions) == accounted, "Unaccounted linked function/frame inventory")
    need(
        not any(
            name in linked.functions
            for name in (
                "uefi_console_interrupt",
                "uefi_runtime_enter",
                "__au_runtime_console_put",
                "__au_runtime_console_next",
            )
        ),
        "Unexpected input/runtime capability",
    )
    need(not any(name.startswith("__au_runtime_bytes_") for name in linked.functions), "Unexpected allocator runtime")
    decoder.NORETURN = frozenset(
        name
        for name in linked.functions
        if name == "uefi_payload_fail" or "4failE" in name or name == "_ZN6aurora4uefi15run_framebufferEm"
    )
    functions = decoder.compiled_stack_functions(
        directory, linked, language, code, starts, frames, compiler_edges, BRIDGES
    )
    functions.update(
        decoder.assembly_stack_functions(
            linked.functions,
            code,
            starts,
            set(memory.functions)
            | {
                BRIDGE,
                VALUE_BRIDGE,
                "uefi_payload_entry",
                "uefi_payload_fault",
                "uefi_payload_page_fault",
                "fault_common",
            },
        )
    )
    console.verify_noreturn(functions, decoder.NORETURN)
    bridge = linked.functions[BRIDGE]
    body = [row for address, row in sorted(code.items()) if bridge.address <= address < bridge.address + bridge.size]
    console.verify_bridge_body(decoder, body, starts)
    value = linked.functions[VALUE_BRIDGE]
    verify_value_bridge(
        decoder,
        [row for address, row in sorted(code.items()) if value.address <= address < value.address + value.size],
        starts,
    )
    for name in functions:
        common.graph_peak(functions, name)
    normal = common.graph_peak(functions, "uefi_payload_entry")
    session = common.graph_peak(functions, ENTRY)
    fault = 48 + max(
        common.graph_peak(functions, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    verify_stack_budget(normal["peak"], fault)
    return dict(
        stack_bytes=16384,
        cap_bytes=15360,
        normal=normal,
        session=session,
        boot_fault=fault,
        bridge=dict(symbol=BRIDGE, entry=ENTRY),
        compiler_frames=associations,
        original_dynamic_bounded_rows=original_bounded_rows,
        bounded_row_explanation="Bounded GCC annotation retained; full compiler frame held at every call and tail",
        linked_functions=functions,
        assembly_objects=assembly,
        page_verifier=dict(traversal_slots=4, recursion="rejected"),
        disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
    )


def build_files():
    names = [
        "payload.ld",
        "payload.elf",
        "payload.bin",
        "esp/EFI/BOOT/BOOTX64.EFI",
        "uefi-payload.hpp",
        "language.s",
        "language.stack.json",
    ]
    names += [
        name + ".o"
        for name in (
            "payload",
            "acpi",
            "pci",
            "runtime",
            "framebuffer",
            "language",
            "payload-entry",
            "loader",
            "memory",
            "embed",
            "transition",
        )
    ]
    names += [
        name + suffix
        for name in ("payload", "acpi", "pci", "runtime", "framebuffer", "loader")
        for suffix in (".su", ".ci")
    ]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    return common.build_artifacts(names)


def emit(mode):
    (BUILD / "framebuffer-admission.json").unlink(missing_ok=True)
    need(mode in MODES, "Unsupported framebuffer profile")
    before = common.hashes(build_files())
    subprocess.run(
        [sys.executable, "-B", ROOT / "scripts/kernel_uefi_image.py", "--build-dir", BUILD], cwd=ROOT, check=True
    )
    result = dict(
        schema="aurora-framebuffer-admission-v1",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        stack=stack_evidence(BUILD),
    )
    common.write_admission(BUILD / "framebuffer-admission.json", result, build_files(), before)
    print("PASS: automated graphics image/mixed-stack checks; independent qualification still requires review")


def checked(mode):
    need(mode in MODES, "Unsupported framebuffer profile")
    return common.check_admission(
        BUILD / "framebuffer-admission.json", "aurora-framebuffer-admission-v1", mode, build_files()
    )


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
        print(json.dumps(stack_evidence(BUILD), indent=2, sort_keys=True))
    else:
        checked(args.mode)
        print("PASS: current image admission; independent qualification not claimed.")


if __name__ == "__main__":
    main()
