#!/usr/bin/env python3
"""Automated local image admission and separate review-pinned qualification."""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/uefi"
RECEIPT = BUILD / "program-console-admission.json"
SOURCE_DIRECTORIES = ("kernel", "kernel-images", "compiler", "library", "examples", "scripts", "tests")
MODES = (
    "program-console",
    "program-request-fault",
    "program-service-fault",
    "program-completion-fault",
    "program-request-budget",
    "program-service-budget",
    "program-completion-budget",
    "program-pending",
    "program-owner",
    "program-ordinal",
    "program-unknown",
    "program-transaction",
)


class Blocked(ValueError):
    """An explicit prerequisite is unavailable; never an image/check failure."""


def need(value, reason):
    if not value:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def configure_paths(build_dir, source_root=None):
    """Select trusted command-line roots; receipts never select their own roots."""
    global ROOT, BUILD, RECEIPT
    root = Path(source_root or ROOT).resolve(strict=True)
    build = Path(build_dir).absolute()
    need(build.resolve() == build, "Build directory contains a symlink or noncanonical component")
    need(not root.is_relative_to(build), "Build directory cannot contain the source root")
    ROOT, BUILD = root, build
    RECEIPT = BUILD / "program-console-admission.json"


def path_arguments(parser):
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--depfile", type=Path)
    parser.add_argument("--depfile-target", type=Path)
    parser.add_argument("--build-dir", type=Path, help="exact profile output directory (default: build/uefi)")


def check_depfile_options(args):
    need(bool(args.depfile) == bool(args.depfile_target), "Both depfile and target are required")
    need(not args.depfile or args.action in ("begin", "begin-build"), "Depfiles belong only to build-begin actions")


def write_build_depfile(args, name):
    if not args.depfile:
        return
    destination, target = args.depfile.absolute(), args.depfile_target.absolute()
    need(destination.resolve() == destination and destination.is_relative_to(BUILD), "Depfile escaped selected build")
    need(target == BUILD / name, "Depfile target is not the exact build-begin output")
    directories = {ROOT}
    for name in SOURCE_DIRECTORIES:
        base = ROOT / name
        if base.is_dir():
            directories.add(base)
            directories.update(path for path in base.rglob("*") if path.is_dir())
    inputs = sorted(set(source_files()) | directories)
    need(
        all(path.resolve(strict=True).is_relative_to(ROOT) for path in inputs),
        "Depfile source escaped selected checkout",
    )
    escaped = load("admission_depfile_escape", ROOT / "scripts/meson-native-fixture.py").escaped
    args.depfile.write_text(escaped(args.depfile_target) + ": " + " ".join(map(escaped, inputs)) + "\n")


def native_directory(directory):
    return directory.parent.name == "uefi" and directory.parent.parent.name == "kernel-images"


def include_directory():
    return "-I" + (
        BUILD.relative_to(BUILD.parents[2]).as_posix()
        if native_directory(BUILD)
        else str(BUILD.relative_to(ROOT))
        if BUILD.is_relative_to(ROOT)
        else str(BUILD)
    )


def build_artifacts(names):
    """Keep exact inventories, including native same-compilation associations."""
    cpp = [name.removesuffix(".su") for name in names if name.endswith(".su")]
    if native_directory(BUILD):
        names += [name + ".source.json" for name in cpp]
    return [
        BUILD / ("objects/" + name if name.endswith((".o", ".su", ".ci", ".source.json")) else name) for name in names
    ]


def verify_object_exports(paths):
    """Bind loader as well as payload exports to the selected compile directory."""
    records = [path for path in paths if path.name.endswith(".source.json")]
    if records:
        decoder = load("native_export_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
        for path in records:
            decoder.object_source(BUILD, path.name.removesuffix(".source.json"), ROOT)


def is_reflection_helper(name):
    return re.fullmatch(r"(?:aurora_reflect_|__au_reflect_s[1-9][0-9]*_)(?:size|field_count)", name) is not None


def verify_reflection_body(decoder, symbol, rows, payload):
    """Closed constant lookup: exact bytes, complete coverage, no authority/memory."""
    need(
        is_reflection_helper(symbol.name) and rows and symbol.address >= 0 and symbol.size > 0,
        "Unknown or empty reflection helper",
    )
    cursor = symbol.address
    for row in rows:
        need(row.address == cursor and row.size > 0, "Reflection instruction coverage gap/overlap")
        cursor += row.size
    need(cursor == symbol.address + symbol.size <= len(payload), "Reflection extent/coverage mismatch")

    def raw(row):
        return payload[row.address : row.address + row.size]

    def immediate(row, op, register):
        match = re.fullmatch(r"\$(0x[0-9a-f]+|[0-9]+),%" + register, row.args)
        need(row.op == op and match, "Reflection operand is not an immediate scalar")
        value = int(match[1], 0)
        need(0 <= value <= 0x7FFFFFFF, "Reflection scalar exceeds closed imm32 range")
        if op == "cmp":
            expected = [bytes.fromhex("4883ff") + bytes([value])] if value <= 127 else []
            expected += [bytes.fromhex("4881ff") + value.to_bytes(4, "little")]
        else:
            expected = [bytes.fromhex("48c7c0") + value.to_bytes(4, "little")]
        need(raw(row) in expected, "Reflection immediate opcode/bytes mismatch")
        return value

    index, keys, targets = 0, [], []
    while index < len(rows) and rows[index].op == "cmp":
        value = immediate(rows[index], "cmp", "rdi")
        need(value not in keys and index + 1 < len(rows), "Duplicate/truncated reflection comparison")
        branch = rows[index + 1]
        need(branch.op == "je", "Reflection comparison must have an equality branch")
        target = decoder.target_of(branch)
        branch_bytes = raw(branch)
        if branch.size == 6 and branch_bytes[:2] == bytes.fromhex("0f84"):
            displacement = int.from_bytes(branch_bytes[2:], "little", signed=True)
        elif branch.size == 2 and branch_bytes[:1] == b"\x74":
            displacement = int.from_bytes(branch_bytes[1:], "little", signed=True)
        else:
            raise ValueError("Reflection equality-branch opcode/bytes mismatch")
        need(
            type(target) is int
            and target == branch.address + branch.size + displacement
            and target > branch.address
            and target not in targets,
            "Reflection external/backward/duplicate or misdecoded branch",
        )
        keys.append(value)
        targets.append(target)
        index += 2
    need(keys, "Reflection helper lacks a closed lookup ladder")
    arms = []
    while index < len(rows):
        row = rows[index]
        arms.append(row.address)
        if row.op == "ud2":
            need(not row.args and raw(row) == bytes.fromhex("0f0b"), "Reflection trap bytes/operands mismatch")
            index += 1
            continue
        if row.op == "xor":
            need(
                row.args == "%rax,%rax" and raw(row) == bytes.fromhex("4831c0"),
                "Reflection zero return must be exact register self-zeroing",
            )
        else:
            immediate(row, "mov", "rax")
        need(
            index + 1 < len(rows)
            and rows[index + 1].op == "ret"
            and not rows[index + 1].args
            and raw(rows[index + 1]) == b"\xc3",
            "Reflection return arm must terminate exactly",
        )
        index += 2
    need(
        len(arms) == len(targets) + 1 and targets == arms[1:],
        "Reflection branches must cover only complete internal return arms",
    )
    return dict(
        symbol=symbol.name,
        address=symbol.address,
        bytes=symbol.size,
        cases=len(keys),
        arms=len(arms),
        calls=0,
        data_accesses=0,
    )


def verify_reflection_image(directory):
    """Reuse closed lookup validation for imported modules, never a name-only allowance."""
    decoder = load("reflection_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    language, linked = decoder.Elf(directory / "objects/language.o"), decoder.Elf(directory / "payload.elf")
    names = {name for name in language.functions if name.startswith(("aurora_reflect_", "__au_reflect_"))}
    need({"aurora_reflect_size", "aurora_reflect_field_count"} <= names, "Missing root reflection helpers")
    for obj in (language, linked):
        helpers = [row for row in obj.symbols if row.name.startswith(("aurora_reflect_", "__au_reflect_"))]
        need(
            len(helpers) == len(names)
            and {row.name for row in helpers} == names
            and all(row.section and row.kind == 2 for row in helpers),
            "Reflection helper escaped generated function ownership",
        )
    code, _ = decoder.disassemble(directory / "payload.elf")
    payload = (directory / "payload.bin").read_bytes()
    results = []
    for name in sorted(names):
        original = language.functions[name]
        need(
            not any(
                section == original.section
                and address < original.address + original.size
                and address + 4 > original.address
                for section, address, *_ in language.relocations
            ),
            "Reflection helper acquired a relocation",
        )
        decoder.associate_object(linked, language, original)
        symbol = linked.functions[name]
        rows = [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]
        results.append(verify_reflection_body(decoder, symbol, rows, payload))
    return results


def symbols(path):
    return {
        row[2]: int(row[0], 16)
        for line in subprocess.check_output(["nm", "-a", path], text=True).splitlines()
        if len(row := line.split()) == 3
    }


def linked_assembly(stack, linked, directory, name):
    """Check whole executable sections, allowing only the actual rel32 slots."""
    obj = stack.Elf(directory / "objects" / (name + ".o"))
    names = {symbol.name: symbol for symbol in linked.symbols if symbol.section}
    evidence = []
    for index, section in enumerate(obj.sections):
        if section[1] != 1 or not section[2] & 4 or not section[5]:
            continue
        candidates = [symbol for symbol in obj.symbols if symbol.section == index and symbol.name in names]
        need(candidates, "Assembly lacks linked anchor: " + name)
        anchor = candidates[0]
        begin = names[anchor.name].address - anchor.address
        expected = bytearray(obj.section_data(index))
        installed = bytearray((directory / "payload.bin").read_bytes()[begin : begin + len(expected)])
        need(len(installed) == len(expected), "Assembly exceeds payload")
        for symbol in candidates:
            need(names[symbol.name].address == begin + symbol.address, "Assembly symbol moved: " + symbol.name)
        for target, offset, kind, _, _ in obj.relocations:
            if target == index:
                need(kind in (2, 4) and offset + 4 <= len(expected), "Unsupported assembly relocation")
                expected[offset : offset + 4] = installed[offset : offset + 4] = b"\0" * 4
        need(expected == installed, "Assembly object/link mismatch: " + name)
        evidence.append(dict(object=name + ".o", begin=begin, bytes=len(expected)))
    return evidence


def graph_peak(functions, frames, root, target=None):
    """Actual live call-site depth; every call cycle rejects."""

    def visit(name, path):
        need(name not in path, "Unknown call/control-flow cycle: " + name)
        body = functions[name]
        frame = max(body["local_peak"], frames.get(name, 0))
        best = (frame, [name]) if target is None or name == target else None
        if name == target:
            return best
        for call in body["calls"]:
            if call["target"] is None:
                continue
            child = visit(call["target"], path + [name])
            if child is None:
                continue
            value = call["live_bytes"] + max(0, frame - body["local_peak"]) + child[0]
            if best is None or value > best[0]:
                best = value, [name] + child[1]
        return best

    result = visit(root, [])
    need(result is not None, "Unreachable stack path: " + str(target))
    return dict(peak=result[0], path=result[1])


def switch_envelope(rows):
    """Resolve one bounded six-entry PIC switch without fixing its base register."""
    need(len(rows) == 6, "Missing switch guard")
    guard, reject, table_load, offset_load, addition, jump = rows
    displacement = re.fullmatch(r"(0x[0-9a-f]+)\(%rip\),(%[a-z0-9]+)", table_load.args)
    need(displacement, "Unknown PIC switch table")
    base = displacement[2]
    need(
        base in {"%" + name for name in "rbx rcx rdx rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()},
        "Switch base aliases index or stack register",
    )
    need(
        (guard.op, guard.args) == ("cmp", "$0x5,%rax")
        and reject.op == "ja"
        and table_load.op == "lea"
        and (offset_load.op, offset_load.args) == ("movslq", f"({base},%rax,4),%rax")
        and (addition.op, addition.args) == ("add", f"{base},%rax")
        and (jump.op, jump.args) == ("jmp", "*%rax"),
        "Unknown indirect switch envelope",
    )
    return table_load.address + table_load.size + int(displacement[1], 16)


def switch_window(rows, decoder):
    """Find the ordered switch proof across independent, flag-preserving MOVs."""
    position = len(rows) - 1
    core, independent = [], []
    for mnemonic in ("jmp", "add", "movslq", "lea", "ja", "cmp"):
        while position >= 0 and rows[position].op != mnemonic:
            row = rows[position]
            need(row.op == "mov", "Unsupported switch interleaving")
            independent.append(row)
            position -= 1
        need(position >= 0, "Missing switch operation: " + mnemonic)
        core.append(rows[position])
        position -= 1
    core.reverse()
    table = switch_envelope(core)
    base = decoder.arguments(core[2].args)[-1]
    registers = {"%" + name for name in "rax rbx rcx rdx rsi rdi rbp r8 r9 r10 r11 r12 r13 r14 r15".split()}
    for row in independent:
        operands = decoder.arguments(row.args)
        need(
            len(operands) == 2
            and operands[1] in registers - {"%rax", base}
            and (operands[0] in registers or re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)?\(%rsp\)", operands[0])),
            "Interleaved move changes switch state or has unsupported operands",
        )
    return dict(table=table, guard=core[0], jump=core[-1], independent=independent)


def switch_no_bypass(body, guard, jump, targets, decoder):
    """No direct or table edge may enter the guarded envelope after its bound."""
    for target in targets:
        need(not guard.address < target <= jump.address, "Switch table target bypasses bound")
    for row in body:
        if (row.op in decoder.BRANCHES or row.op == "call") and row is not jump:
            target = decoder.target_of(row)
            need(not guard.address < target <= jump.address, "Transfer bypasses switch bound")


def stack_evidence(directory, *, snapshot=False):
    decoder = load("program_stack_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    decoder.CPP_OBJECTS = ("payload", "acpi", "pci", "runtime")
    if snapshot:
        decoder.CPP_OBJECTS += ("owned-bytes-runtime", "snapshot")
        decoder.configure_owned_bytes()
    decoder.configure_console("program")
    original_rows = decoder.stack_rows
    # The CFG decoder independently accounts for every stack adjustment below.
    # GCC dynamic,bounded here denotes call arguments, not an unbounded VLA.
    decoder.stack_rows = lambda text: original_rows(text, allow_bounded=lambda _: True)
    linked = decoder.Elf(directory / "payload.elf")
    code, disassembly = decoder.disassemble(directory / "payload.elf")
    normalized_stack_immediates = []
    for address, row in list(code.items()):
        if row.op == "push" and re.fullmatch(r"(?:0x[0-9a-f]+)?\(%r(?:sp|ip)\)", row.args):
            code[address] = decoder.Instruction(address, row.size, row.op, "%rax")
            normalized_stack_immediates.append(
                dict(address=address, original=row.args, equivalent="qword push, +8 stack bytes")
            )
        match = re.fullmatch(r"\$(0x[0-9a-f]+),%rsp", row.args)
        if row.op in ("add", "sub") and match and int(match[1], 16) >= 1 << 63:
            count = (1 << 64) - int(match[1], 16)
            replacement = decoder.Instruction(
                address, row.size, "sub" if row.op == "add" else "add", f"$0x{count:x},%rsp"
            )
            code[address] = replacement
            normalized_stack_immediates.append(dict(address=address, original=row.args, equivalent=replacement.args))
    frames, associations = decoder.cpp_frames(directory, linked, source_root=ROOT)
    named = {symbol.name: symbol for symbol in linked.symbols if symbol.section}
    enter, leave, handler = [named[key] for key in ("uefi_runtime_enter", "aurora_leave_user", "uefi_runtime_handler")]
    # Bound the assembly handler by the original object's exact text extent.
    entry_object = decoder.Elf(directory / "objects" / "runtime-entry.o")
    object_handler = next(row for row in entry_object.symbols if row.name == handler.name)
    handler_size = entry_object.sections[object_handler.section][5] - object_handler.address
    linked.functions[enter.name] = decoder.Symbol(
        enter.name, enter.address, leave.address - enter.address, enter.section, 0
    )
    linked.functions[handler.name] = decoder.Symbol(handler.name, handler.address, handler_size, handler.section, 0)
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    need(len(starts) == len(linked.functions), "Ambiguous linked functions")
    decoder.NORETURN = frozenset(
        name for name in linked.functions if name == "uefi_payload_fail" or "4stopE" in name or "4failE" in name
    )
    if snapshot:
        decoder.NORETURN |= decoder.OWNED_NORETURN
    for object_name in ("language", "memory"):
        obj = decoder.Elf(directory / "objects" / (object_name + ".o"))
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = []
    for name in ("runtime-entry", "runtime-exceptions", "payload-entry"):
        assembly += linked_assembly(decoder, linked, directory, name)
    entry_ops = [insn for address, insn in sorted(code.items()) if enter.address <= address < leave.address]
    need(
        sum(row.op == "push" for row in entry_ops) == 11
        and entry_ops[-1].op == "iretq"
        and not any(row.op == "call" for row in entry_ops),
        "Runtime entry stack contract",
    )
    switches = []

    def analyze_checked(symbol):
        body = [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]
        indirect = [index for index, row in enumerate(body) if row.op in ("jmp", "call") and row.args.startswith("*")]
        if not indirect:
            return decoder.analyze_function(symbol, code, starts, fault=symbol.name == "fault_common")
        need(len(indirect) == 1, "Unexpected indirect branch inventory")
        index = indirect[0]
        envelope = switch_window(body[: index + 1], decoder)
        table, guard, jump = (envelope[key] for key in ("table", "guard", "jump"))
        raw = (directory / "payload.bin").read_bytes()
        need(
            named["__payload_text_end"].address <= table and table + 24 <= named["__payload_read_end"].address,
            "Switch table is not immutable payload data",
        )
        targets = [
            table + int.from_bytes(raw[table + i * 4 : table + i * 4 + 4], "little", signed=True) for i in range(6)
        ]
        need(
            all(symbol.address <= value < symbol.address + symbol.size and value in code for value in targets),
            "Switch targets leave exact function",
        )
        switch_no_bypass(body, guard, jump, targets, decoder)
        results = []
        for target in sorted(set(targets)):
            selected = dict(code)
            selected[jump.address] = decoder.Instruction(jump.address, jump.size, "jmp", f"{target:x} <bounded-switch>")
            results.append(decoder.analyze_function(symbol, selected, starts))
        calls = {}
        for result in results:
            for call in result["calls"]:
                prior = calls.get(call["address"])
                need(prior is None or prior == call, "Switch changes copied call-site facts")
                calls[call["address"]] = call
        switches.append(
            dict(
                function=symbol.name,
                guard=guard.address,
                table=table,
                targets=targets,
                independent_moves=[row.address for row in envelope["independent"]],
            )
        )
        return dict(
            local_peak=max(item["local_peak"] for item in results),
            push_peak=max(item["push_peak"] for item in results),
            calls=list(calls.values()),
            instructions=sum(item["instructions"] for item in results),
            returns=sum(item["returns"] for item in results),
        )

    functions = {}
    for name, symbol in linked.functions.items():
        if name == enter.name:
            functions[name] = dict(local_peak=96, push_peak=96, calls=[], instructions=len(entry_ops), returns=1)
        else:
            try:
                functions[name] = analyze_checked(symbol)
            except ValueError as error:
                raise ValueError(name + ": " + str(error)) from error
    # Both reviewed page-table traversals use four local slots. Every linked
    # call cycle now rejects; compiler metadata does not establish termination.
    for name in functions:
        graph_peak(functions, frames, name)
    normal = graph_peak(functions, frames, "uefi_payload_entry")
    dispatch = graph_peak(functions, frames, "aurora_exception_dispatch")
    boot_fault = 48 + max(
        graph_peak(functions, frames, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    irq_peak = 176 + 15 + dispatch["peak"]
    points = {}
    for name in () if snapshot else ("uefi_program_poll_begin", "uefi_service_drain_begin"):
        pc = named[name].address
        owners = [
            key for key, symbol in linked.functions.items() if symbol.address <= pc < symbol.address + symbol.size
        ]
        need(len(owners) == 1, "Ambiguous interruptible function: " + name)
        path = graph_peak(functions, frames, "uefi_payload_entry", target=owners[0])
        path["peak_with_interrupt"] = path["peak"] + irq_peak
        points[name] = path
    reserve = decoder.FAULT_RESERVE if snapshot else boot_fault
    need(boot_fault <= reserve, "Synchronous fault path exceeds retained fault reserve")
    need(normal["peak"] + reserve <= 15360, "Kernel normal/fault stack cap exhausted")
    need(
        irq_peak <= 15360 and all(value["peak_with_interrupt"] <= 15360 for value in points.values()),
        "IRQ or kernel poll/drain stack cap exhausted",
    )
    users = {}
    for name in ("clean", "bounds"):
        user = decoder.Elf(directory / ("user-" + name + ".elf"))
        instructions, _ = decoder.disassemble(user.path)
        user_starts = {symbol.address: key for key, symbol in user.functions.items()}
        bodies = {
            key: decoder.analyze_function(symbol, instructions, user_starts) for key, symbol in user.functions.items()
        }
        copied = name == "bounds"
        root = (
            (
                "__au_v_m1_16snapshot_service_n0__d16aurora_user_main"
                if snapshot
                else "__au_v_m1_22program_stream_service_n0__d16aurora_user_main"
            )
            if copied
            else "aurora_user_main"
        )
        path = graph_peak(bodies, {}, root)
        path["entry_saved_bytes"] = 160 if copied else 48
        path["peak_with_entry"] = path["peak"] + path["entry_saved_bytes"]
        need(path["peak_with_entry"] <= 15360, "CPL3 stack cap exhausted")
        users[name] = path
    return dict(
        stack_bytes=16384,
        cap_bytes=15360,
        normal=normal,
        boot_fault=boot_fault,
        fault_reserve=reserve,
        normal_with_fault_reserve=normal["peak"] + reserve,
        irq_frame_bytes=176,
        irq_alignment_bytes=15,
        irq_dispatch=dispatch,
        irq_peak=irq_peak,
        interruptible_paths=points,
        user_paths=users,
        runtime_entry_peak=96,
        bounded_switches=switches,
        normalized_stack_immediates=normalized_stack_immediates,
        compiler_frames=associations,
        linked_functions=functions,
        page_verifier=dict(traversal_slots=4, recursion="rejected"),
        assembly_objects=assembly,
        disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
    )


def note_evidence(directory, mode="program-console"):
    """Exact private note composition; reuses the existing ELF/CFG decoder."""
    decoder = load("note_bridge_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    abi = load("note_record_abi", ROOT / "tests/kernel-snapshot-abi.py")
    linked = decoder.Elf(directory / "payload.elf")
    generated = decoder.Elf(directory / "objects" / "language.o")
    code, _ = decoder.disassemble(directory / "payload.elf")
    names = {row.name: row for row in linked.symbols if row.section}
    bridges = {"__au_runtime_note_update", "__au_runtime_note_project"}
    need({name for name in names if name.startswith("__au_runtime_")} == bridges, "Closed note runtime inventory")
    need(
        not any(name.startswith(("__cxa_", "_GLOBAL__sub_I", "_Zn", "_Zd")) for name in names),
        "Note acquired constructor or heap machinery",
    )
    need(
        not subprocess.check_output(["nm", "-u", directory / "objects" / "language.o"], text=True),
        "Note graph acquired authority",
    )
    expected_objects = {
        "payload",
        "payload-entry",
        "language",
        "acpi",
        "pci",
        "runtime",
        "memory",
        "runtime-entry",
        "runtime-exceptions",
        "user-clean",
        "user-clean-entry",
        "user-bounds",
        "loader",
        "embed",
        "transition",
        "loader-pe",
        "embed-pe",
        "transition-pe",
        "memory-pe",
    }
    need(
        {path.stem for path in (directory / "objects").glob("*.o")} == expected_objects,
        "Exact protected-note object composition",
    )
    public = {
        row.split()[2]
        for row in subprocess.check_output(
            ["nm", "-g", "--defined-only", directory / "objects" / "language.o"], text=True
        ).splitlines()
        if len(row.split()) == 3
    }
    policies = {
        "aurora_kernel_value",
        "aurora_kernel_budget_tick",
        "aurora_kernel_round_robin_next",
        "aurora_kernel_ipc_transition",
        "aurora_kernel_client_disposal",
        "aurora_kernel_terminal_event",
        "aurora_console_byte",
        "aurora_console_command",
        "__au_v_m2_6kernel7console_n1_6kernel_d12console_byte",
        "__au_v_m2_6kernel7console_n1_6kernel_d15console_command",
        "__au_v_m2_6kernel14terminal_event_n1_6kernel_d14terminal_event",
    }
    need({name for name in public if not is_reflection_helper(name)} == policies | bridges, "Exact note native exports")
    assembly = (directory / "language.s").read_text()
    evidence = []

    def memory(offset, register):
        return (f"-0x{-offset:x}" if offset < 0 else f"0x{offset:x}" if offset else "") + f"(%{register})"

    for action, frame, argument_save, result_save, parameters, result_start, result_bytes in (
        ("update", 464, -456, -464, ((0, -72, 72), (72, -136, 64), (136, -144, 8)), -448, 80),
        ("project", 176, -168, -176, ((0, -72, 72),), -144, 72),
    ):
        private = "__au_v_m1_22kernel_program_console_n0__d" + (
            "11update_note" if action == "update" else "12project_note"
        )
        bridge = "__au_runtime_note_" + action
        need(private not in public and private in generated.functions, "Private note source entry")
        symbol = linked.functions[bridge]
        wrapper = []
        for address, row in sorted(code.items()):
            if symbol.address <= address < symbol.address + symbol.size:
                operand = (
                    private
                    if row.op == "call" and decoder.target_of(row) == linked.functions[private].address
                    else row.args
                )
                wrapper.append((row.op, operand))
        check_note_bridge(wrapper, private)
        # The linked bridge must be the same complete object function.
        decoder.associate_object(linked, generated, generated.functions[bridge])
        function = linked.functions[private]
        body = [
            row
            for address, row in sorted(code.items())
            if function.address <= address < function.address + function.size
        ]
        source = assembly.split(private + ":\n", 1)[1].split(".size " + private, 1)[0]
        actual_frame, prefix = decoder.generated_frame([line.strip() for line in source.splitlines()], body)
        need(actual_frame == frame, "Exact copied note helper frame")
        expected = [("mov", "%r11," + memory(argument_save, "rbp")), ("mov", "%r10," + memory(result_save, "rbp"))]
        for offset, local, extent in parameters:
            expected += [("mov", memory(argument_save, "rbp") + ",%r11")]
            for byte in range(0, extent, 8):
                expected += [
                    ("mov", memory(offset + byte, "r11") + ",%rax"),
                    ("mov", "%rax," + memory(local + byte, "rbp")),
                ]
        need(
            [(row.op, row.args) for row in body[prefix : prefix + len(expected)]] == expected,
            "Exact note copied input binding",
        )
        result = [("mov", memory(result_save, "rbp") + ",%r10")]
        for byte in range(0, result_bytes, 8):
            result += [("mov", memory(result_start + byte, "rbp") + ",%rax"), ("mov", "%rax," + memory(byte, "r10"))]
        rows = [(row.op, row.args) for row in body]
        starts = [i for i, row in enumerate(rows) if row == result[0]]
        need(
            len(starts) == 1 and rows[starts[0] : starts[0] + len(result)] == result, "Exact note copied result binding"
        )
        evidence.append(
            dict(
                bridge=bridge,
                private_entry=private,
                frame=frame,
                input_bytes=sum(p[2] for p in parameters),
                result_bytes=result_bytes,
            )
        )
    abi.main(directory, "transaction" if mode == "program-transaction" else "normal", note=True)
    return dict(bridges=evidence, record=json.loads((directory / "note-abi.json").read_text()))


def check_note_bridge(actual, private):
    need(
        actual
        == [
            ("push", "%rbp"),
            ("mov", "%rsp,%rbp"),
            ("mov", "%rdi,%r11"),
            ("mov", "%rsi,%r10"),
            ("call", private),
            ("leave", ""),
            ("ret", ""),
        ],
        "Exact copied note bridge",
    )


def source_files():
    paths = {
        ROOT / name
        for name in (
            "Makefile",
            "meson.build",
            "meson_options.txt",
            "compiler/Makefile",
            "tests/meson.build",
            "tests/compiler-test-inventory.json",
        )
    }
    for directory in SOURCE_DIRECTORIES:
        paths.update(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file()
            and path.suffix in (".cpp", ".hpp", ".h", ".inc", ".S", ".au", ".ld", ".py", ".sh", ".build")
        )
    return sorted(paths)


def build_files():
    names = [
        "payload.ld",
        "payload.elf",
        "payload.bin",
        "esp/EFI/BOOT/BOOTX64.EFI",
        "program-poll-metadata.json",
        "service-timer-metadata.json",
        "user-images.json",
        "note-abi.json",
        "uefi-user-images.hpp",
        "uefi-payload.hpp",
        "language.s",
        "language.o",
        "runtime-entry.o",
        "runtime-exceptions.o",
        "payload-entry.o",
    ]
    names += [name + ".o" for name in ("payload", "acpi", "pci", "runtime", "loader", "memory", "embed", "transition")]
    names += [name + suffix for name in ("payload", "acpi", "pci", "runtime", "loader") for suffix in (".su", ".ci")]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    names += ["user-" + name + suffix for name in ("clean", "bounds") for suffix in (".s", ".o", ".elf", ".bin")]
    names += ["user-clean-entry.o"]
    return build_artifacts(names)


def hashes(paths):
    result = {}
    for path in paths:
        path = Path(path).absolute()
        base, prefix = (BUILD, "build:") if path.is_relative_to(BUILD) else (ROOT, "source:")
        need(
            path.is_relative_to(base) and path.resolve(strict=True).is_relative_to(base),
            "Hash input escaped selected root",
        )
        key = prefix + path.relative_to(base).as_posix()
        need(key not in result, "Duplicate hash input: " + key)
        result[key] = digest(path)
    return result


def executable(path):
    resolved = Path(shutil.which(path) or path).resolve(strict=True)
    return dict(path=str(resolved), sha256=digest(resolved))


def begin_build(mode, compiler, cxx, flags):
    need(mode in MODES and compiler and cxx and flags, "Missing exact build controls")
    RECEIPT.unlink(missing_ok=True)
    (BUILD / "program-build.json").unlink(missing_ok=True)
    manifest = dict(
        schema="aurora-program-build-v1",
        mode=mode,
        flags=flags,
        source_sha256=hashes(source_files()),
        compiler=executable(compiler),
        cxx=executable(cxx),
        translation_unit_flags={
            "payload/acpi/pci": ["-fpie", "-fvisibility=hidden"],
            "runtime": ["-fpie", "-fvisibility=hidden", include_directory()],
            "loader": ["-fpie", "-maccumulate-outgoing-args", include_directory()],
        },
        assembly_runtime_flags=["--64", "--defsym", "AURORA_IPC=1", "--defsym", "AURORA_SERVICE_BUDGET=1"],
    )
    (BUILD / "program-build-start.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def verify_inputs(manifest, mode):
    need(
        manifest["schema"] == "aurora-program-build-v1" and manifest["mode"] == mode,
        "Build provenance profile mismatch",
    )
    need(manifest["source_sha256"] == hashes(source_files()), "Source inventory/bytes changed since build began")
    for name in ("compiler", "cxx"):
        item = manifest[name]
        need(digest(Path(item["path"])) == item["sha256"], "Build executable changed: " + name)
    required = {
        "-DAURORA_UEFI_ACPI",
        "-DAURORA_UEFI_PCI",
        "-DAURORA_UEFI_RUNTIME",
        "-DAURORA_UEFI_IPC",
        "-DAURORA_UEFI_SERVICE_BUDGET",
        "-DAURORA_UEFI_USER_BUDGET",
        "-DAURORA_UEFI_PROGRAM_CONSOLE",
    }
    need(
        required == {flag for flag in manifest["flags"] if flag.startswith("-DAURORA_UEFI_")},
        "Unexpected program profile flags",
    )
    injection = {flag for flag in manifest["flags"] if flag.startswith("-DAURORA_PROGRAM_")}
    need(
        injection
        == (set() if mode == "program-console" else {"-DAURORA_PROGRAM_" + mode[8:].upper().replace("-", "_")}),
        "Build fault/budget mode does not match exact flags",
    )


def end_build(mode):
    manifest = json.loads((BUILD / "program-build-start.json").read_text())
    verify_inputs(manifest, mode)
    verify_object_exports(build_files())
    manifest["output_sha256"] = hashes(build_files())
    (BUILD / "program-build.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def provenance(mode):
    manifest = json.loads((BUILD / "program-build.json").read_text())
    verify_inputs(manifest, mode)
    verify_object_exports(build_files())
    need(manifest["output_sha256"] == hashes(build_files()), "Build output changed after compilation")
    return manifest


def emit(mode):
    need(mode in MODES, "Unsupported program console profile")
    RECEIPT.unlink(missing_ok=True)
    manifest = provenance(mode)
    subprocess.run(
        [sys.executable, "-B", ROOT / "tests/kernel-uefi-image.py", "--build-dir", BUILD, "--ipc-policy"],
        cwd=ROOT,
        check=True,
    )
    metadata = json.loads((BUILD / "user-images.json").read_text())
    need(set(metadata) == {"clean", "bounds"}, "Expected exactly two compiled user images")
    builder = load("program_image_admission", ROOT / "scripts/kernel-uefi-ipc-images.py")
    for index, name in enumerate(("clean", "bounds")):
        prefix = BUILD / ("user-" + name)
        names = symbols(prefix.with_suffix(".elf"))
        actual = builder.verify(
            prefix.with_suffix(".elf").read_bytes(),
            prefix.with_suffix(".bin").read_bytes(),
            builder.BASE + index * 4096,
            names,
            copied_note=index == 1,
        )
        for key, value in actual.items():
            need(metadata[name][key] == value, "Stale user metadata: " + key)
    payload = (BUILD / "payload.bin").read_bytes()
    names = symbols(BUILD / "payload.elf")
    for begin, end, opcode in (
        ("uefi_program_poll_begin", "uefi_program_poll_end", "fbf4fa"),
        ("uefi_service_drain_begin", "uefi_service_drain_end", "fb9090fa"),
    ):
        need(payload[names[begin] : names[end]] == bytes.fromhex(opcode), "Changed exact poll/drain window")
    result = dict(
        schema="aurora-program-console-admission-v1",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        build=manifest,
        user_images=metadata,
        poll=json.loads((BUILD / "program-poll-metadata.json").read_text()),
        timer=json.loads((BUILD / "service-timer-metadata.json").read_text()),
        stack=stack_evidence(BUILD),
        note=note_evidence(BUILD, mode),
    )
    result["sha256"] = hashes(source_files() + build_files() + [BUILD / "program-build.json"])
    RECEIPT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        "PASS: automated protected-console image/stack checks; first-change qualification requires independent review."
    )
    return result


def checked(mode):
    """Recheck complete current-source/build identity without claiming review."""
    need(mode in MODES, "Unsupported program console profile")
    if not RECEIPT.is_file():
        raise Blocked("Build this program profile first; automatic admission receipt is missing")
    receipt = json.loads(RECEIPT.read_text())
    need(
        receipt["schema"] == "aurora-program-console-admission-v1" and receipt["mode"] == mode,
        "Admission covers another profile",
    )
    need(
        receipt["status"] == "requires-independent-review" and receipt["clock"] == "tcg-original-clock",
        "Unexpected admission status or clock",
    )
    need(receipt["build"] == provenance(mode), "Admitted build provenance changed")
    expected = hashes(source_files() + build_files() + [BUILD / "program-build.json"])
    need(receipt["sha256"] == expected, "Admission source/output inventory or bytes changed")
    return receipt


def reviewed(mode):
    supplied = os.environ.get("PROGRAM_CONSOLE_REVIEW_SHA256", "")
    if not supplied:
        raise Blocked("Qualification needs an independent PROGRAM_CONSOLE_REVIEW_SHA256 receipt digest")
    need(re.fullmatch("[0-9a-f]{64}", supplied), "Malformed independent review digest")
    need(RECEIPT.is_file() and digest(RECEIPT) == supplied, "Admission receipt does not match external review")
    return checked(mode)


def main():
    parser = argparse.ArgumentParser()
    path_arguments(parser)
    parser.add_argument("action", choices=("emit", "checked", "reviewed", "diagnose", "begin-build", "end-build"))
    parser.add_argument("--mode", choices=MODES, default="program-console")
    parser.add_argument("--compiler")
    parser.add_argument("--cxx")
    parser.add_argument("--flag", action="append", default=[])
    args = parser.parse_args()
    check_depfile_options(args)
    configure_paths(args.build_dir or args.source_root / "build/uefi", args.source_root)
    if args.action == "begin-build":
        begin_build(args.mode, args.compiler, args.cxx, args.flag)
        write_build_depfile(args, "program-build-start.json")
    elif args.action == "end-build":
        end_build(args.mode)
    elif args.action == "emit":
        emit(args.mode)
    elif args.action == "checked":
        checked(args.mode)
        print("PASS: current-source protected-console admission; independent qualification not claimed.")
    elif args.action == "diagnose":
        result = stack_evidence(BUILD)
        print(
            json.dumps(
                {key: result[key] for key in ("normal", "boot_fault", "irq_peak", "interruptible_paths", "user_paths")},
                indent=2,
            )
        )
    else:
        reviewed(args.mode)
        print("Verified externally reviewed exact-source/image receipt.")


if __name__ == "__main__":
    try:
        main()
    except Blocked as error:
        print("BLOCKED: program console admission: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit("FAIL: program console admission: " + str(error)) from error
