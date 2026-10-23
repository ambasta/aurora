#!/usr/bin/env python3
"""Exact simple-UEFI service image and stack admission.

Reuses the reviewed fail-closed instruction/CFG decoder and object/.su association,
not another profile's measured frames, call graph, image or admission receipt.
"""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
RECEIPT = BUILD / "console-service-admission.json"
# Image profiles; the four service faults are boot-selected console-fixture cases.
MODES = ("console", "console-fixture")
ENTRY = "__au_v_m1_22kernel_console_service_n0__d15console_service"
BRIDGE = "__au_runtime_console_entry"
VALUE_BRIDGE = "__au_runtime_console_value"
BRIDGES = (BRIDGE, VALUE_BRIDGE)


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


common = load("console_service_admission_common", ROOT / "scripts/kernel_program_console_admission.py")


def configure_paths(build_dir, source_root=None):
    global ROOT, BUILD, RECEIPT
    common.configure_paths(build_dir, source_root or ROOT)
    ROOT, BUILD = common.ROOT, common.BUILD
    RECEIPT = BUILD / "console-service-admission.json"


def verify_noreturn(functions, noreturn):
    returning = {name for name, body in functions.items() if body["returns"]}
    while True:
        enlarged = returning | {
            name
            for name, body in functions.items()
            if any(row["kind"] == "tail" and row["target"] in returning for row in body["calls"])
        }
        if enlarged == returning:
            break
        returning = enlarged
    need(
        noreturn <= functions.keys() and not noreturn & returning,
        "Designated non-returning diagnostic or console returns",
    )


def verify_irq_reachability(functions, language_functions):
    pending = ["uefi_console_interrupt_dispatch"]
    irq_reachable = set()
    while pending:
        name = pending.pop()
        if name in irq_reachable:
            continue
        irq_reachable.add(name)
        need(
            name not in language_functions and not name.startswith("__au_"),
            "IRQ callback reaches Aurora or a service bridge",
        )
        pending.extend(row["target"] for row in functions[name]["calls"] if row["target"] is not None)
    return sorted(irq_reachable)


def verify_irq_body(decoder, body, starts):
    registers = ("rax", "rbx", "rcx", "rdx", "rbp", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15")
    prefix = [("push", "$0x0"), ("push", "$0x40"), ("cld", "")] + [("push", "%" + r) for r in registers]
    prefix += [("mov", "%rsp,%rdi"), ("mov", "%rsp,%rbx"), ("and", "$0xfffffffffffffff0,%rsp")]
    suffix = (
        [("mov", "%rbx,%rsp")]
        + [("pop", "%" + r) for r in reversed(registers)]
        + [("add", "$0x10,%rsp"), ("iretq", "")]
    )
    need(len(body) == len(prefix) + 1 + len(suffix), "Changed console IRQ instruction count")
    need([(row.op, row.args) for row in body[: len(prefix)]] == prefix, "Changed exact IRQ save/alignment")
    need([(row.op, row.args) for row in body[-len(suffix) :]] == suffix, "Changed exact IRQ restore")
    call = body[len(prefix)]
    need(
        call.op == "call" and starts.get(decoder.target_of(call)) == "uefi_console_interrupt_dispatch",
        "IRQ must call only the trusted wake dispatcher",
    )


def verify_bridge_body(decoder, bridge_body, starts):
    need(
        [(row.op, row.args) for row in bridge_body[:3]]
        == [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("mov", "%rdi,%r11")],
        "Changed private service bridge prologue",
    )
    need(
        len(bridge_body) == 6
        and bridge_body[3].op == "call"
        and starts.get(decoder.target_of(bridge_body[3])) == ENTRY
        and [(row.op, row.args) for row in bridge_body[4:]] == [("leave", ""), ("ret", "")],
        "Changed private service entry target or return",
    )


def verify_stack_budgets(normal_peak, wait_peak, irq_peak, boot_fault):
    need(
        all(type(value) is int and value >= 0 for value in (normal_peak, wait_peak, irq_peak, boot_fault)),
        "Invalid stack budget measurement",
    )
    need(
        normal_peak + boot_fault <= 15360 and wait_peak + irq_peak + boot_fault <= 15360,
        "Existing console mixed-stack/fault/IRQ budget exhausted",
    )
    need(irq_peak + boot_fault <= 4096, "Existing separate console IRQ/fault reserve exhausted")


def stack_evidence(directory):
    decoder = load("console_service_stack_decoder", ROOT / "scripts/kernel_stack.py")
    decoder.CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "console")
    old_rows = decoder.stack_rows
    decoder.stack_rows = lambda text: old_rows(
        text, allow_bounded=lambda signature: "aurora::uefi::run_console(" in signature
    )
    linked = decoder.Elf(directory / "payload.elf")
    need(linked.type == 2, "Expected linked executable payload")
    need(not subprocess.check_output(["nm", "-u", directory / "payload.elf"], text=True).strip(), "Unresolved payload")
    code, disassembly = decoder.disassemble(directory / "payload.elf")
    payload = (directory / "payload.bin").read_bytes()
    named = {symbol.name: symbol for symbol in linked.symbols if symbol.section}
    irq = named["uefi_console_interrupt"]
    irq_object = decoder.Elf(directory / "objects" / "console-entry.o")
    original_irq = next(row for row in irq_object.symbols if row.name == irq.name)
    extent = irq_object.sections[original_irq.section][5] - original_irq.address
    linked.functions[irq.name] = decoder.Symbol(irq.name, irq.address, extent, irq.section, 2)
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    need(len(starts) == len(linked.functions), "Ambiguous linked function starts")
    compiler_edges = set()
    frames, associations = decoder.cpp_frames(directory, linked, edges=compiler_edges, source_root=ROOT)
    language = decoder.Elf(directory / "objects" / "language.o")
    memory = decoder.Elf(directory / "objects" / "memory.o")
    for obj in (language, memory):
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = []
    for name in ("console-entry", "payload-entry"):
        assembly += decoder.linked_assembly(linked, directory, name)
    accounted = (
        set(frames)
        | set(language.functions)
        | set(memory.functions)
        | {"uefi_payload_entry", "uefi_payload_fault", "uefi_payload_page_fault", "fault_common", irq.name}
    )
    need(set(linked.functions) == accounted, "Unaccounted linked function/frame inventory")
    decoder.NORETURN = frozenset(
        name
        for name in linked.functions
        if name == "uefi_payload_fail" or "4failE" in name or name == "_ZN6aurora4uefi11run_consoleEmRKNS0_5BytesE"
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
    verify_noreturn(functions, decoder.NORETURN)
    body = [row for address, row in sorted(code.items()) if irq.address <= address < irq.address + extent]
    verify_irq_body(decoder, body, starts)
    # Prove the private bridge is exactly the selected grant-record forwarding
    # sequence; no public scalar ABI or replacement callback can reach the entry.
    bridge = linked.functions[BRIDGE]
    bridge_body = [
        row for address, row in sorted(code.items()) if bridge.address <= address < bridge.address + bridge.size
    ]
    verify_bridge_body(decoder, bridge_body, starts)
    value = linked.functions[VALUE_BRIDGE]
    decoder.verify_tail_bridge(
        [row for address, row in sorted(code.items()) if value.address <= address < value.address + value.size],
        starts,
        "aurora_kernel_value",
    )
    for name in functions:
        common.graph_peak(functions, name)
    normal = common.graph_peak(functions, "uefi_payload_entry")
    session_peak = common.graph_peak(functions, ENTRY)
    dispatch = common.graph_peak(functions, "uefi_console_interrupt_dispatch")
    boot_fault = 48 + max(
        common.graph_peak(functions, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    irq_peak = 176 + 15 + dispatch["peak"]
    begin, end = named["uefi_console_poll_begin"].address, named["uefi_console_poll_end"].address
    need(payload[begin:end] == bytes.fromhex("fbf4fa"), "Changed exact timer wait interval")
    owners = [
        name
        for name, symbol in linked.functions.items()
        if symbol.address <= begin < end <= symbol.address + symbol.size
    ]
    need(len(owners) == 1, "Ambiguous wait frame")
    waiting = common.graph_peak(functions, "uefi_payload_entry", target=owners[0])
    waiting["peak_with_interrupt"] = waiting["peak"] + irq_peak
    waiting["peak_with_interrupt_and_fault"] = waiting["peak_with_interrupt"] + boot_fault
    verify_stack_budgets(normal["peak"], waiting["peak"], irq_peak, boot_fault)
    need(
        ENTRY in waiting["path"] and BRIDGE in waiting["path"] and "__au_runtime_console_next" in waiting["path"],
        "Wait path does not retain the persistent Aurora service frame",
    )
    irq_reachable = verify_irq_reachability(functions, language.functions)
    return dict(
        stack_bytes=16384,
        cap_bytes=15360,
        normal=normal,
        session=session_peak,
        boot_fault=boot_fault,
        irq_frame_bytes=176,
        irq_alignment_bytes=15,
        irq_fault_reserve_bytes=4096,
        irq_dispatch=dispatch,
        irq_peak=irq_peak,
        irq_reachable=sorted(irq_reachable),
        wait=waiting,
        bridge=dict(symbol=BRIDGE, entry=ENTRY),
        compiler_frames=associations,
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
            "console",
            "console-entry",
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
        for name in ("payload", "acpi", "pci", "runtime", "console", "loader")
        for suffix in (".su", ".ci")
    ]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    return common.build_artifacts(names)


def emit(mode):
    RECEIPT.unlink(missing_ok=True)
    need(mode in MODES, "Unsupported console service profile")
    before = common.hashes(build_files())
    subprocess.run(
        [sys.executable, "-B", ROOT / "scripts/kernel_uefi_image.py", "--build-dir", BUILD], cwd=ROOT, check=True
    )
    result = dict(
        schema="aurora-console-service-admission-v1",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        stack=stack_evidence(BUILD),
    )
    common.write_admission(RECEIPT, result, build_files(), before)
    print(
        "PASS automated native-console image/stack checks; "
        "first-change qualification still requires independent review."
    )


def checked(mode):
    need(mode in MODES, "Unsupported console service profile")
    return common.check_admission(RECEIPT, "aurora-console-service-admission-v1", mode, build_files())


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
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        raise SystemExit("FAIL: native console admission: " + str(error))
