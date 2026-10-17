#!/usr/bin/env python3
"""Compact generated/linked fixture checks, using the existing disassembler.

This does not execute the production wrapper or qualify a complete kernel stack.
"""

from pathlib import Path
import importlib.util
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("snapshot_stack", ROOT / "scripts/kernel_stack.py")
stack = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stack
spec.loader.exec_module(stack)
SERVICE = "__au_v_m1_16snapshot_service_n0__d16aurora_user_main"


def check_wrapper(actual, mode="normal", service=SERVICE):
    expected = [("or", f"%{register},%rax") for register in ("rbx", "rbp", "r10", "r11", "r12", "r13", "r14", "r15")]
    expected += [("jne", "bad_entry"), ("cmpq", "$0x0,-0x8(%rsp)"), ("jne", "bad_entry"), ("sub", "$0x70,%rsp")]
    expected += [("push", f"%{register}") for register in ("rdi", "rdx", "rcx", "r8", "r9")]
    expected += [
        ("sub", "$0x8,%rsp"),
        ("mov", "%r9,%rdx"),
        ("lea", "0x30(%rsp),%r11"),
        ("call", service),
        ("add", "$0x8,%rsp"),
    ]
    expected += [("pop", f"%{register}") for register in ("r9", "r8", "rcx", "rdx", "rdi")]
    expected += [("add", "$0x70,%rsp")]
    if mode == "reply-reserved":
        expected += [("movabs", "$0x8000000000000000,%r10"), ("or", "%r10,%rax")]
    elif mode == "reply-byte":
        expected += [("xor", "$0x100,%rax")]
    expected += [("mov", "$0x1,%esi")]
    if mode == "transaction":
        expected += [("inc", "%r8")]
    expected += [("int", "$0x81"), ("ud2", ""), ("ud2", "")]
    stack.require(actual == expected, "Changed copied wrapper record/envelope/restoration")


def copied_payload(source_base, source_offset, destination_base, destination_offset, extent, *, assembly=False):
    """Exact emitted idiom for a known contiguous initialized copied payload.

    Callers supply independently fixed layout extents, not decoded instructions.
    The existing disassembler validates REP opcode/spelling. This expectation
    checks all address, count, direction and save/restore instructions verbatim.
    The assembly option renders the same fixed form with emitter spelling; it
    never parses or normalizes source instructions. This is not an instruction
    interpreter or proof of arbitrary copy semantics.
    """
    stack.require(source_base in ("rbp", "r10", "r11"), "Copied source must have a stable base")
    stack.require(destination_base in ("rbp", "r10", "r11", "rsp"), "Unknown copied destination base")
    stack.require(destination_base != "rsp" or source_base == "rbp", "Packed copy source must be frame based")
    stack.require(type(extent) is int and 64 <= extent <= 65536, "Unsupported compact copied extent")
    stack.require(type(source_offset) is int and type(destination_offset) is int, "Copied offsets must be integers")

    def memory(base, offset):
        if assembly:
            return f"{offset}(%{base})"
        displacement = ("-" if offset < 0 else "") + f"0x{abs(offset):x}" if offset else ""
        return displacement + f"(%{base})"

    stack.require(type(assembly) is bool, "Copied payload format must be explicit")
    separator = ", " if assembly else ","
    source = memory(source_base, source_offset)
    destination = memory(destination_base, destination_offset)
    expected = [("lea", destination + separator + "%rax")] if destination_base == "rsp" else []
    expected += [("push", "%rsi"), ("push", "%rdi"), ("push", "%rcx"), ("lea", source + separator + "%rsi")]
    expected += (
        [("mov", "%rax" + separator + "%rdi")]
        if destination_base == "rsp"
        else [("lea", destination + separator + "%rdi")]
    )
    expected += [
        ("mov", (f"${extent}" if assembly else f"$0x{extent:x}") + separator + "%rcx"),
        ("cld", ""),
        ("rep", "movsb" if assembly else "movsb %ds:(%rsi),%es:(%rdi)"),
        ("pop", "%rcx"),
        ("pop", "%rdi"),
        ("pop", "%rsi"),
    ]
    if assembly:
        suffixes = {"lea": "leaq", "mov": "movq", "push": "pushq", "pop": "popq"}
        return [suffixes.get(op, op) + (" " + args if args else "") for op, args in expected]
    return expected


def check_bindings(actual, expected):
    stack.require(actual == expected, "Changed scalar/byte bindings or hidden record save")


def check_composition(directory):
    spec = importlib.util.spec_from_file_location("snapshot_images", ROOT / "scripts/kernel-uefi-ipc-images.py")
    images = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(images)
    cases = [("reply-reserved", {}), ("reply-byte", {}), ("context", {"snapshot": True})]
    cases += [
        ("normal", {"snapshot": True, field: True})
        for field in ("service_budget", "dispatcher", "user_budget", "program_console")
    ]
    cases += [
        ("normal", {"program_console": True}),
        ("normal", {"program_console": True, "service_budget": True}),
        ("normal", {"program_console": True, "service_budget": True, "user_budget": True, "dispatcher": True}),
        ("context", {"program_console": True, "service_budget": True, "user_budget": True}),
    ]
    for mode, options in cases:
        try:
            images.validate_composition(mode, **options)
        except ValueError:
            pass
        else:
            raise ValueError("Unsupported snapshot image composition accepted")


def main(directory, uefi_mode=None, note=False, checksum=False):
    check_composition(directory)
    service = directory / ("user-bounds" if uefi_mode else "service")
    client = directory / ("user-clean" if uefi_mode else "client")
    entry = SERVICE
    if note:
        metadata = importlib.util.spec_from_file_location(
            "snapshot_compiler_abi", ROOT / "scripts/bootstrap_frontend.py"
        )
        compiler_abi = importlib.util.module_from_spec(metadata)
        metadata.loader.exec_module(compiler_abi)
        entry = compiler_abi.abi_function_symbol(
            json.loads(service.with_suffix(".abi.json").read_text()), "aurora_user_main"
        )
    mode = uefi_mode or "normal"
    if note:
        stack.require(mode in ("normal", "owner", "ordinal", "unknown", "transaction"), "Exact note mode")
        if mode != "transaction":
            mode = "normal"
    linked = stack.Elf(service.with_suffix(".elf"))
    symbols = {symbol.name: symbol for symbol in linked.symbols}
    instructions, _ = stack.disassemble(service.with_suffix(".elf"))
    wrapper = []
    targets = {symbols[name].address: name for name in ("bad_entry", entry)}
    for address in sorted(instructions):
        if symbols["aurora_program_entry"].address <= address < symbols["bad_entry"].address + 2:
            insn = instructions[address]
            operand = targets.get(stack.target_of(insn)) if insn.op in ("call", "jne") else insn.args
            wrapper.append((insn.op, operand))
    check_wrapper(wrapper, mode, entry)
    # Four directed changed-record/restoration controls, without another decoder.
    for original, changed in (
        ("$0x70,%rsp", "$0x60,%rsp"),
        ("0x30(%rsp),%r11", "0x20(%rsp),%r11"),
        (entry, "wrong_entry"),
        ("%r9", "%r8"),
    ):
        bad = list(wrapper)
        index = next(index for index, (_, operand) in enumerate(bad) if operand == original)
        bad[index] = (bad[index][0], changed)
        try:
            check_wrapper(bad, mode, entry)
        except ValueError:
            pass
        else:
            raise ValueError("Malformed copied wrapper admitted")

    function = linked.functions[entry]
    body = [
        instructions[address]
        for address in sorted(instructions)
        if function.address <= address < function.address + function.size
    ]
    source = service.with_suffix(".s").read_text().split(entry + ":\n", 1)[1].split(".size " + entry, 1)[0]
    frame, prefix = stack.private_frame_layout([line.strip() for line in source.splitlines()], body)
    stack.require(frame == (144 if note else 192 if checksum else 112), "Changed copied service frame")
    hidden = "-0x88(%rbp)" if note else "-0xb8(%rbp)" if checksum else "-0x68(%rbp)"
    expected = [("mov", "%r11," + hidden)]
    for offset in (0, 8, 16):
        address = "(%r11)" if offset == 0 else f"0x{offset:x}(%r11)"
        expected += [("mov", hidden + ",%r11"), ("mov", address + ",%rax"), ("mov", f"%rax,-0x{offset + 8:x}(%rbp)")]
    expected += [("mov", hidden + ",%r11")]
    # The snapshot record ends in separately checked zero padding. Only the
    # explicit note record binds its final qword as the signed length.
    extent = 72 if note else 64
    expected += copied_payload("r11", 24, "rbp", -(24 + extent), extent)
    actual = [(row.op, row.args) for row in body[prefix : prefix + len(expected)]]
    check_bindings(actual, expected)
    # Source-layout independence: corrupt every scalar, address, extent,
    # direction and save/restore instruction. The final note qword is payload.
    for index in range(len(actual)):
        changed = list(actual)
        changed[index] = ("mov", "0x100(%r11),%rax")
        try:
            check_bindings(changed, expected)
        except ValueError:
            pass
        else:
            raise ValueError("Malformed copied binding admitted")
    service_object = directory / "objects" / service.with_suffix(".o").name if uefi_mode else service.with_suffix(".o")
    nm = subprocess.check_output(["nm", "-a", str(service_object)], text=True)
    stack.require(
        any(line.split()[1:] == ["t", entry] for line in nm.splitlines()), "Aggregate entry escaped local linkage"
    )
    stack.require(
        not subprocess.check_output(["nm", "-u", str(service_object)], text=True),
        "Protected service acquired an external import",
    )
    result = {
        "record_type": "NoteRead64" if note else "Snapshot64",
        "record_bytes": 96,
        "stack_reservation": 112,
        "pre_call_depth": 160,
        "record_offset": -112,
        "service_frame": frame,
        "service_bytes": service.with_suffix(".bin").stat().st_size,
        "client_bytes": client.with_suffix(".bin").stat().st_size,
        "mode": mode,
        "scope": "actual linked wrapper structure; execution and complete kernel stack remain pending",
    }
    (directory / ("note-abi.json" if note else "abi.json")).write_text(json.dumps(result, indent=2) + "\n")
    print(
        "PASS: fixed copied bindings, local aggregate entry and exact linked wrapper; "
        "four wrapper and exact scalar/copy binding mutation controls"
    )
