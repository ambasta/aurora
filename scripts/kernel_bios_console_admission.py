#!/usr/bin/env python3
"""Console-only BIOS mixed native/Aurora stack admission, not general BIOS proof.

Compiler facts are trusted and bound to the linked objects. The live console
closure and complete conservative exception-dispatch closure are composed, with
main's retained frame. Unrelated boot/user-test paths are not qualified here.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import kernel_stack as stack
from bootstrap_frontend import abi_function_symbol
from kernel_profiles import bios_profile
from meson_aurora_assembly import validate_uart_policy_abi

CONSOLE_BRIDGE = "__au_runtime_console_entry"
UART_BRIDGES = tuple("__au_runtime_uart_" + name for name in ("initialize", "next", "put"))
RUN = "_ZN6aurora7console11Interactive3runEv"
MAIN = "aurora_kernel_main"
DISPATCH = "aurora_exception_dispatch"


def unique(pairs):
    result = {}
    for key, value in pairs:
        stack.require(key not in result, "Duplicate admission fact key")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=unique)


def merge_functions(*maps):
    result = {}
    for mapping in maps:
        stack.require(not result.keys() & mapping.keys(), "Overlapping mixed-stack function ownership")
        result.update(mapping)
    return result


def closure(roots, edges):
    found, pending = set(), list(roots)
    while pending:
        name = pending.pop()
        if name in found:
            continue
        found.add(name)
        pending.extend(target for caller, target in edges if caller == name)
    return found


def bridge_contract(rows, starts, target, copied_result):
    expected = [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("mov", "%rdi,%r11")]
    if copied_result:
        expected.append(("mov", "%rsi,%r10"))
    stack.require(
        len(rows) == len(expected) + 3
        and [(r.op, r.args) for r in rows[: len(expected)]] == expected
        and rows[-3].op == "call"
        and starts.get(stack.target_of(rows[-3])) == target
        and [(r.op, r.args) for r in rows[-2:]] == [("leave", ""), ("ret", "")],
        "Changed BIOS service bridge",
    )


def verify_uart_record(record, bridge):
    stack.require(bridge in UART_BRIDGES, "Unknown UART bridge")
    expected = [["builtin::Com1UartGrant", 16], ["copied_class", 48]]
    if bridge.endswith("_put"):
        expected.append(["scalar", 8])
    stack.require(
        record == {"parameters": expected, "result_bytes": 48, "result_kind": "copied_class"},
        "UART stack/ABI copied-service record mismatch",
    )


def check_budget(normal, fault, main_frame):
    # Existing Protection ranges: main [0x88000,0x90000), IST [0x7c000,0x80000).
    # CPU frame 40 + vector/error 16 + 15 saved GPRs 120 + alignment at most15.
    fault_peak = 191 + fault["peak"]
    total = main_frame + normal["peak"] + 63 + fault_peak
    stack.require(fault_peak <= 0x4000, "BIOS emergency stack exhausted")
    stack.require(total <= 0x8000, "BIOS console main stack exhausted")
    return dict(
        main_stack_bytes=0x8000,
        emergency_stack_bytes=0x4000,
        retained_main_bytes=main_frame,
        serial_irq_bytes=63,
        synchronous_fault_bytes=fault_peak,
        peak_with_fault=total,
        minimum_unused=0x8000 - total,
    )


def admission(directory, source_root):
    directory, source_root = directory.resolve(strict=True), source_root.resolve(strict=True)
    stack.require(
        directory.parent.name == "bios" and directory.name == "console" and stack.native_profile(directory),
        "Requires original BIOS console profile directory",
    )
    # Reuse the BIOS image gate even for standalone admission invocation: exact
    # ELF/flat bytes, load sectors and packaged disk must agree before graph use.
    stack.command(
        sys.executable,
        "-B",
        str(source_root / "tests/kernel-image.py"),
        "--root",
        str(source_root),
        "--build-dir",
        str(directory),
        "--console",
        "--check-only",
    )
    profile = bios_profile("console", {"KERNEL_CONSOLE": "1"})
    linked = stack.Elf(directory / "kernel.elf")
    stack.require(linked.type == 2, "Expected linked BIOS executable")
    code, _ = stack.disassemble(linked.path)
    binary = (directory / "kernel.bin").read_bytes()
    stack.require(0 < len(binary) <= 127 * 512, "BIOS 127-sector image budget exhausted")
    payload = bytes(0x10000) + binary  # Linked virtual addresses, not file offsets.
    named = {symbol.name: symbol for symbol in linked.symbols if symbol.section}
    stack.require(named["__text_begin"].address == 0x10000, "Changed BIOS load address")
    edges = set()
    frames, associations = stack.cpp_frames(directory, linked, tuple(profile["cpp"]), edges, source_root)
    # Some unrelated boot/user assembly entries have NOTYPE labels. They are
    # address witnesses for main's direct transfers, never invented stack facts.
    for name in {target for _, target in edges} - linked.functions.keys():
        stack.require(
            name in named and linked.sections[named[name].section][2] & 4, "Missing executable compiler callee"
        )
        symbol = named[name]
        linked.functions[name] = stack.Symbol(name, symbol.address, symbol.size, symbol.section, symbol.kind)
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    stack.require(len(starts) == len(linked.functions), "Ambiguous linked mixed-stack entries")
    language_maps = []
    bridges = (CONSOLE_BRIDGE,) + UART_BRIDGES
    for stem, owned_bridges in (("kernel-language", (CONSOLE_BRIDGE,)), ("kernel-uart", UART_BRIDGES)):
        obj = stack.Elf(directory / (stem + ".o"))
        stack.require(
            obj.type == 1 and not obj.functions.keys() & frames.keys(), "Overlapping native/language ownership"
        )
        language_maps.append(stack.language_stack_functions(directory, linked, obj, code, starts, owned_bridges, stem))
    language = merge_functions(*language_maps)
    abi = read_json(directory / "kernel-uart.abi.json")
    validate_uart_policy_abi(abi)
    targets = {bridge: abi_function_symbol(abi, "uart_" + bridge.rsplit("_", 1)[1]) for bridge in UART_BRIDGES}
    targets[CONSOLE_BRIDGE] = abi_function_symbol(read_json(directory / "kernel-language.abi.json"), "console_service")

    def body(begin, end):
        rows = [row for address, row in sorted(code.items()) if begin <= address < end]
        stack.require(
            rows
            and rows[0].address == begin
            and rows[-1].next == end
            and all(a.next == b.address for a, b in zip(rows, rows[1:])),
            "Assembly extent gap",
        )
        return rows

    for bridge, target in targets.items():
        symbol = linked.functions[bridge]
        bridge_contract(body(symbol.address, symbol.address + symbol.size), starts, target, bridge in UART_BRIDGES)
        if bridge in UART_BRIDGES:
            verify_uart_record(language[target]["service_abi"]["record"], bridge)
    handwritten = stack.assembly_stack_functions(linked.functions, code, starts, bridges)
    memory = stack.Elf(directory / "kernel-memory.o")
    stack.require(set(memory.functions) == {"memcpy", "memset", "memmove", "memcmp"}, "Changed memory inventory")
    for symbol in memory.functions.values():
        stack.associate_object(linked, memory, symbol)
    handwritten = merge_functions(
        handwritten, stack.assembly_stack_functions(linked.functions, code, starts, memory.functions)
    )
    source_edges = {
        (name, call["target"])
        for name, row in merge_functions(language, handwritten).items()
        for call in row["calls"]
        if call["target"] is not None
    }
    console_names, uart_names = (set(mapping) for mapping in language_maps)
    port_hosts = {"__au_runtime_port_read8", "__au_runtime_port_write8"}
    uart_imports = {target for caller, target in source_edges if caller in uart_names and target not in uart_names}
    stack.require(
        uart_imports & port_hosts == port_hosts and uart_imports <= port_hosts | memory.functions.keys(),
        "Changed UART source imports",
    )
    console_imports = {
        target for caller, target in source_edges if caller in console_names and target not in console_names
    }
    stack.require(
        console_imports <= {"__au_runtime_console_next", "__au_runtime_console_put"} | memory.functions.keys(),
        "Console source bypasses native session",
    )
    for caller, target in edges | source_edges:
        if target in uart_names:
            stack.require(
                caller in uart_names or caller in UART_BRIDGES and targets[caller] == target,
                "UART source called outside its exact bridge",
            )
        if target == targets[CONSOLE_BRIDGE]:
            stack.require(caller == CONSOLE_BRIDGE, "Console entry called outside its exact bridge")
        if target in port_hosts:
            stack.require(caller in uart_names, "Raw Port primitive called outside UART source")
        if target in UART_BRIDGES:
            stack.require(
                caller in associations
                and all(row["object"] == "kernel-interactive-console.o" for row in associations[caller]),
                "UART bridge called outside native transport",
            )
    for host in port_hosts:
        stack.require(
            host in associations and all(row["object"] == "kernel-interactive-console.o" for row in associations[host]),
            "Raw Port primitive lacks native transport ownership",
        )
    selected = closure((RUN, DISPATCH), edges | source_edges)
    stack.require(
        selected <= frames.keys() | language.keys() | handwritten.keys(),
        "Console/fault closure reaches an unaccounted function",
    )
    native_names = (selected & frames.keys()) | {MAIN}
    native = stack.cpp_stack_functions(
        linked.functions,
        code,
        starts,
        payload,
        {name: frames[name] for name in native_names},
        {(a, b) for a, b in edges if a in native_names},
    )
    functions = merge_functions(native, language, handwritten)
    stack.require((MAIN, RUN) in edges, "Missing retained main-to-console call")
    normal = stack.calculate(functions, RUN)
    fault = stack.calculate(functions, DISPATCH)
    # Require both native raw operations to be reached through the source UART,
    # and the console source to remain on the live synchronous nested path.
    stack.require(targets[CONSOLE_BRIDGE] in normal["closure"], "Console source not reachable")
    nested = {}
    for primitive in ("__au_runtime_port_read8", "__au_runtime_port_write8"):
        path = stack.calculate(functions, targets[CONSOLE_BRIDGE], primitive)
        stack.require(any(name in UART_BRIDGES for name in path["path"]), "Port primitive bypasses UART source")
        nested[primitive] = path
    stack.require(all(target in normal["closure"] for target in targets.values()), "Missing UART workload")
    evidence = []
    for obj in ("start", "serial-input", "exceptions"):
        evidence += stack.linked_assembly(linked, directory, obj, payload)
    serial = named["aurora_serial_interrupt"]
    serial_object = stack.Elf(directory / "serial-input.o")
    original = next(s for s in serial_object.symbols if s.name == serial.name)
    serial_end = serial.address + serial_object.sections[original.section][5] - original.address
    stack.require(
        [(r.op, r.args) for r in body(serial.address, serial_end)]
        == [("push", "%rax"), ("mov", "$0x20,%al"), ("out", "%al,$0x20"), ("pop", "%rax"), ("iretq", "")],
        "Changed BIOS wake-only IRQ",
    )
    # Bind the boot entry's only call and prove that it retains no stack frame.
    entry_object = stack.Elf(directory / "start.o")
    entry_symbol = next(row for row in entry_object.symbols if row.name == "_start")
    begin = named["_start"].address
    entry = body(begin, begin + entry_object.sections[entry_symbol.section][5] - entry_symbol.address)
    stack.require(
        len(entry) == 10
        and entry[0].op == "cld"
        and entry[1].op == entry[2].op == "lea"
        and entry[1].args.endswith(",%rdi")
        and entry[2].args.endswith(",%rcx")
        and [(r.op, r.args) for r in entry[3:6]]
        == [("sub", "%rdi,%rcx"), ("xor", "%eax,%eax"), ("rep", "stos %al,%es:(%rdi)")]
        and entry[6].op == "call"
        and stack.target_of(entry[6]) == named[MAIN].address
        and [(r.op, r.args) for r in entry[7:9]] == [("cli", ""), ("hlt", "")]
        and entry[9].op == "jmp"
        and stack.target_of(entry[9]) == entry[7].address,
        "Changed BIOS stack-neutral main entry",
    )
    # Every vector contributes exactly two words before the shared save path;
    # hardware error codes replace a synthetic zero, they do not add a third.
    errors = {8, 10, 11, 12, 13, 14, 17, 21, 29, 30}
    vectors = [("aurora_exception_" + str(i), i, i in errors) for i in range(32)]
    vectors += [
        ("aurora_timer_interrupt", 64, False),
        ("aurora_program_return", 129, False),
        ("aurora_user_return", 128, False),
        ("aurora_unexpected_interrupt", 255, False),
    ]
    ordered = sorted((named[name].address, name, vector, error) for name, vector, error in vectors)
    common = named["exception_common"].address
    for index, (address, name, vector, error) in enumerate(ordered):
        end = ordered[index + 1][0] if index + 1 < len(ordered) else common
        rows = body(address, end)
        pushes = rows if name == "aurora_unexpected_interrupt" else rows[:-1]
        values = [vector] if error else [0, vector]
        stack.require(len(pushes) == len(values), "Changed BIOS vector/error extent")
        for row, value in zip(pushes, values):
            stack.qword_push(row, payload)
            stack.require(row.args == "$0x" + format(value, "x"), "Changed BIOS vector/error value")
        stack.require(
            name == "aurora_unexpected_interrupt" or rows[-1].op == "jmp" and stack.target_of(rows[-1]) == common,
            "Changed BIOS vector target",
        )
    stack.qword_push(body(serial.address, serial_end)[0], payload)
    irq = stack.protected_irq_frame(
        body(named["exception_common"].address, named["aurora_breakpoint_probe"].address), named, payload
    )
    stack.require(irq == {"frame_bytes": 176, "alignment_bytes": 15}, "Changed BIOS fault frame")
    # Compiler-trusted protection setup still uses the existing physical bounds.
    protection = (source_root / "kernel/protection.hpp").read_text()
    for name, value in (
        ("main_stack_bottom", "0x88000"),
        ("main_stack_top", "0x90000"),
        ("emergency_stack_bottom", "0x7c000"),
        ("emergency_stack_top", "0x80000"),
    ):
        stack.require(" " + name + " = " + value + ";" in protection, "Changed BIOS stack range")
    boot = (directory / "boot.bin").read_bytes()
    boot_symbols = {}
    for line in stack.command("nm", "-n", str(directory / "boot.o")).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in {"long_mode", "disk_error", "_boot"}:
            stack.require(fields[2] not in boot_symbols, "Duplicate BIOS boot anchor")
            boot_symbols[fields[2]] = int(fields[0], 16)
    stack.require(
        set(boot_symbols) == {"long_mode", "disk_error", "_boot"} and boot_symbols["_boot"] == 0,
        "Missing BIOS boot anchors",
    )
    long_mode = boot_symbols["long_mode"]
    jump = bytes.fromhex("66 ea") + (0x7C00 + long_mode).to_bytes(4, "little") + bytes.fromhex("08 00")
    sequence = bytes.fromhex("66 b8 10 00 8e d8 8e c0 8e d0 48 c7 c4 00 00 09 00 48 31 ed 48 c7 c0 00 00 01 00 ff e0")
    stack.require(
        boot[boot_symbols["disk_error"] - len(jump) : boot_symbols["disk_error"]] == jump
        and boot[long_mode : long_mode + len(sequence)] == sequence,
        "Changed BIOS long-mode transfer/stack anchor",
    )
    budget = check_budget(normal, fault, native[MAIN]["local_peak"])
    return dict(
        version=1,
        scope="BIOS console closure plus full conservative exception-dispatch closure; not boot/user tests",
        image_sha256=hashlib.sha256(binary).hexdigest(),
        normal=normal,
        fault=fault,
        nested=nested,
        budget=budget,
        compiler_frames=associations,
        assembly_objects=evidence,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("emit",))
    parser.add_argument("--mode", choices=("console",), required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args()
    result = admission(args.build_dir, args.source_root)
    (args.build_dir / "bios-console-admission.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
