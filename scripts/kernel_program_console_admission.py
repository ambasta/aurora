#!/usr/bin/env python3
"""Semantic native image admission with bounded artifact integrity checks."""

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
RECEIPT = BUILD / "program-console-admission.json"
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
PROGRAM_INPUT_BRIDGE = "__au_runtime_program_input"
PROGRAM_RESPONSE_BRIDGE = "__au_runtime_program_response"
CONSOLE_OPERATIONS = frozenset(("__au_runtime_console_next", "__au_runtime_console_put"))


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
    need(
        build.resolve() == build,
        "Build directory contains a symlink or noncanonical component",
    )
    need(not root.is_relative_to(build), "Build directory cannot contain the source root")
    ROOT, BUILD = root, build
    RECEIPT = BUILD / "program-console-admission.json"


def path_arguments(parser):
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument(
        "--build-dir",
        type=Path,
        required=True,
        help="exact native profile output directory",
    )


def native_directory(directory):
    return directory.parent.name == "uefi" and directory.parent.parent.name == "kernel-images"


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
        decoder = load("native_export_decoder", ROOT / "scripts/kernel_stack.py")
        for path in records:
            decoder.object_source(BUILD, path.name.removesuffix(".source.json"), ROOT)


compiler_abi = load("program_compiler_abi", ROOT / "scripts/bootstrap_frontend.py")


def source_symbol(path, name):
    return compiler_abi.abi_function_symbol(read_json(path), name)


stack_facts = load("admission_stack_facts", ROOT / "scripts/kernel_stack.py")
is_reflection_helper = stack_facts.is_reflection_helper


def verify_reflection_body(decoder, symbol, rows, payload):
    """Closed constant lookup: exact bytes, complete coverage, no authority/memory."""
    need(
        is_reflection_helper(symbol.name) and rows and symbol.address >= 0 and symbol.size > 0,
        "Unknown or empty reflection helper",
    )
    cursor = symbol.address
    for row in rows:
        need(
            row.address == cursor and row.size > 0,
            "Reflection instruction coverage gap/overlap",
        )
        cursor += row.size
    need(
        cursor == symbol.address + symbol.size <= len(payload),
        "Reflection extent/coverage mismatch",
    )

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
        need(
            value not in keys and index + 1 < len(rows),
            "Duplicate/truncated reflection comparison",
        )
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
            need(
                not row.args and raw(row) == bytes.fromhex("0f0b"),
                "Reflection trap bytes/operands mismatch",
            )
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
    decoder = load("reflection_decoder", ROOT / "scripts/kernel_stack.py")
    language, linked = (
        decoder.Elf(directory / "objects/language.o"),
        decoder.Elf(directory / "payload.elf"),
    )
    names = stack_facts.reflection_inventory(language.functions)
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


graph_peak = stack_facts.calculate


def check_referenced_reflection(functions, generated_names, bridges=()):
    """Closed supervisor policy over the already validated linked call graph."""
    helpers = {name for name in functions if name.startswith(("aurora_reflect_", "__au_reflect_"))}
    need(all(is_reflection_helper(name) for name in helpers), "Unknown reflection helper")
    need(helpers <= set(generated_names), "Reflection helper is not generated Aurora code")
    referenced = set()
    for owner, function in functions.items():
        for call in function["calls"]:
            target = call["target"]
            if target is not None and is_reflection_helper(target):
                need(
                    owner in generated_names and owner not in bridges and owner not in helpers,
                    "Native or handwritten code references closed reflection helper",
                )
                referenced.add(target)
    need(helpers == referenced, "Closed supervisor reflection helper/reference inventory mismatch")


def stack_evidence(directory, *, snapshot=False):
    decoder = load("program_stack_decoder", ROOT / "scripts/kernel_stack.py")
    units = ("payload", "acpi", "pci", "runtime")
    if snapshot:
        units += ("owned-bytes-runtime", "snapshot")
    bridges = (
        (
            "__au_runtime_snapshot_produce",
            "aurora_kernel_value",
            "aurora_kernel_ipc_transition",
            "aurora_kernel_terminal_event",
        )
        if snapshot
        else (
            "__au_runtime_note_update",
            "__au_runtime_note_project",
            "__au_runtime_files_update",
            "__au_runtime_files_replace",
            "__au_runtime_stream_update",
            PROGRAM_INPUT_BRIDGE,
            PROGRAM_RESPONSE_BRIDGE,
        )
    )
    graph = decoder.image_stack_graph(
        directory,
        units,
        ROOT,
        protected=True,
        bridges=bridges,
        noreturn=decoder.OWNED_NORETURN if snapshot else (),
    )
    functions = graph["functions"]
    if not snapshot:
        generated_names = decoder.Elf(directory / "objects/language.o").functions
        check_referenced_reflection(functions, generated_names, bridges)
    linked = graph["linked"]
    named = {symbol.name: symbol for symbol in linked.symbols if symbol.section}
    normal = graph_peak(functions, "uefi_payload_entry")
    dispatch = graph_peak(functions, "aurora_exception_dispatch")
    boot_fault = 48 + max(
        graph_peak(functions, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    irq = graph["protected_irq"]
    irq_peak = irq["frame_bytes"] + irq["alignment_bytes"] + dispatch["peak"]
    points = {}
    input_entry = None if snapshot else source_symbol(directory / "language.abi.json", "read_program_input")
    response_entry = None if snapshot else source_symbol(directory / "language.abi.json", "present_program_response")
    for name in () if snapshot else ("uefi_program_poll_begin", "uefi_service_drain_begin"):
        pc = named[name].address
        owners = [
            key for key, symbol in linked.functions.items() if symbol.address <= pc < symbol.address + symbol.size
        ]
        need(len(owners) == 1, "Ambiguous interruptible function: " + name)
        path = graph_peak(functions, "uefi_payload_entry", target=owners[0])
        path["peak_with_interrupt"] = path["peak"] + irq_peak
        points[name] = path
        if name == "uefi_program_poll_begin":
            check_program_input_wait(functions, owners[0], input_entry)
    if not snapshot:
        need(
            not ({PROGRAM_INPUT_BRIDGE, PROGRAM_RESPONSE_BRIDGE, input_entry, response_entry} | CONSOLE_OPERATIONS)
            & set(dispatch["closure"]),
            "Protected IRQ dispatcher acquired console authority",
        )
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
        generated = decoder.Elf(directory / "objects" / ("user-" + name + ".o"))
        bodies = decoder.language_stack_functions(
            directory, user, generated, instructions, user_starts, stem="user-" + name
        )
        need(set(bodies) == set(user.functions), "Unaccounted CPL3 generated function")
        copied = name == "bounds"
        root = (
            (
                "__au_v_m1_16snapshot_service_n0__d16aurora_user_main"
                if snapshot
                else source_symbol(directory / "user-bounds.abi.json", "aurora_user_main")
            )
            if copied
            else "aurora_user_main"
        )
        path = graph_peak(bodies, root)
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
        irq_frame_bytes=irq["frame_bytes"],
        irq_alignment_bytes=irq["alignment_bytes"],
        irq_dispatch=dispatch,
        irq_peak=irq_peak,
        interruptible_paths=points,
        user_paths=users,
        runtime_entry_peak=graph["runtime_entry_peak"],
        bounded_switches=graph["bounded_switches"],
        compiler_frames=graph["compiler_frames"],
        linked_functions=functions,
        page_verifier=dict(traversal_slots=4, recursion="rejected"),
        assembly_objects=graph["assembly_objects"],
        disassembly_sha256=hashlib.sha256(graph["disassembly"].encode()).hexdigest(),
    )


def note_evidence(directory, functions, mode="program-console"):
    """Bind native boundaries to the already validated stack graph and ABI facts."""
    decoder = load("note_bridge_decoder", ROOT / "scripts/kernel_stack.py")
    abi = load("note_record_abi", ROOT / "scripts/kernel_snapshot_abi.py")
    linked = decoder.Elf(directory / "payload.elf")
    generated = decoder.Elf(directory / "objects" / "language.o")
    code, _ = decoder.disassemble(directory / "payload.elf")
    names = {row.name: row for row in linked.symbols if row.section}
    bridges = {
        "__au_runtime_note_update",
        "__au_runtime_note_project",
        "__au_runtime_files_update",
        "__au_runtime_files_replace",
        "__au_runtime_stream_update",
        PROGRAM_INPUT_BRIDGE,
        PROGRAM_RESPONSE_BRIDGE,
    }
    need(
        {name for name in names if name.startswith("__au_runtime_")} == bridges | CONSOLE_OPERATIONS,
        "Closed protected-console runtime inventory",
    )
    need(
        not any(name.startswith(("__cxa_", "_GLOBAL__sub_I", "_Zn", "_Zd")) for name in names),
        "Note acquired constructor or heap machinery",
    )
    need(
        {row.name for row in generated.symbols if row.name and row.section == 0} == CONSOLE_OPERATIONS,
        "Protected console acquired imports beyond Console next/put",
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
            ["nm", "-g", "--defined-only", directory / "objects" / "language.o"],
            text=True,
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
    }
    need(
        {name for name in public if not is_reflection_helper(name)} == policies | bridges,
        "Exact note native exports",
    )
    evidence = []
    facts = read_json(directory / "language.abi.json")
    check_stream_operation(facts)
    input_entry = check_program_console_abi(facts)
    response_entry = check_program_console_abi(facts, response=True)
    console_calls = check_program_console_calls(functions, set(generated.functions), public, input_entry, response_entry)
    # Native boundary contracts stay independent of compiler-emitted facts.
    for action, entry, parameters, result_bytes in (
        ("note_update", "update_note", [72, 64, 8], 80),
        ("note_project", "project_note", [72], 72),
        ("files_update", "update_files", [272, 64, 8], 520),
        ("files_replace", "replace_files", [272, 88, 64, 8], 352),
        ("stream_update", "update_stream", [192, 8, 64, 8, 8], 280),
    ):
        private = source_symbol(directory / "language.abi.json", entry)
        bridge = "__au_runtime_" + action
        need(
            private not in public and private in generated.functions,
            "Private note source entry",
        )
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
        check_copied_record(functions[private]["copied_record"], parameters, result_bytes)
        evidence.append(
            dict(
                bridge=bridge,
                private_entry=private,
                local_peak=functions[private]["local_peak"],
                input_bytes=sum(parameters),
                result_bytes=result_bytes,
            )
        )
    for bridge, entry, input_bytes, result_bytes, check in (
        (PROGRAM_INPUT_BRIDGE, input_entry, 24, 88, check_note_bridge),
        (PROGRAM_RESPONSE_BRIDGE, response_entry, 96, 8, check_response_bridge),
    ):
        need(entry not in public and entry in generated.functions, "Private program Console source entry")
        symbol = linked.functions[bridge]
        wrapper = [
            (
                row.op,
                entry if row.op == "call" and decoder.target_of(row) == linked.functions[entry].address else row.args,
            )
            for address, row in sorted(code.items())
            if symbol.address <= address < symbol.address + symbol.size
        ]
        check(wrapper, entry)
        decoder.associate_object(linked, generated, generated.functions[bridge])
        evidence.append(
            dict(
                bridge=bridge,
                private_entry=entry,
                local_peak=functions[entry]["local_peak"],
                input_bytes=input_bytes,
                result_bytes=result_bytes,
                console_calls=console_calls[entry],
                abi_basis="full compiler ABI plus object-bound call/stack facts; sealed Console kind checked by compiler",
            )
        )
    abi.main(
        directory,
        "transaction" if mode == "program-transaction" else "normal",
        note=True,
    )
    return dict(bridges=evidence, record=json.loads((directory / "note-abi.json").read_text()))


def check_copied_record(actual, parameters, result_bytes):
    need(
        actual == dict(parameter_bytes=parameters, result_bytes=result_bytes),
        "Expected compiler v2 copied-record ABI with exact native parameter/result sizes",
    )


def exact_abi(actual, expected, reason):
    # JSON identity also rejects bool/float substitutions for integer facts.
    need(json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True), reason)


def check_program_console_abi(facts, *, response=False):
    """Full existing ABI binds both service entries without a service-record sidecar."""
    source, copied, enum, field, size = (
        ("present_program_response", "console::ProgramResponse", "console::ProgramResponseKind", "kind", 80)
        if response else
        ("read_program_input", "console::ProgramSubmission", "console::ProgramInputAction", "action", 88)
    )
    entry, function = compiler_abi.abi_declaration(facts, "functions", source)
    record, value = compiler_abi.abi_declaration(facts, "records", copied)
    kind, operation = compiler_abi.abi_declaration(facts, "enums", enum)
    buffer, storage = compiler_abi.abi_declaration(facts, "records", "std::BinaryBuffer64")
    cases = (
        dict(ready=0, output=1, note_missing=2, file_missing=3, note_saved=4,
             file_saved=5, file_reply=6, stopped=7, unknown=8)
        if response else dict(command=0, upper_payload=1, requested_exit=2, output_failure=3)
    )
    exact_abi(operation["cases"], cases, source + ": named kinds must match the native mapping")
    exact_abi(
        storage,
        dict(
            source_name="std::BinaryBuffer64", size=64, alignment=1, reserved=64,
            fields=[dict(name="elements", offset=0, bytes=64, array_length=64, kind="u8")],
        ),
        source + ": exact ordinary 64-byte buffer",
    )
    fields = [
        dict(name="bytes", offset=0, bytes=64, array_length=0, kind="class", type_name=buffer),
        dict(name="count", offset=64, bytes=8, array_length=0, kind="i64"),
        dict(name=field, offset=72, bytes=8, array_length=0, kind="enum", type_name=kind),
    ]
    if not response:
        fields.append(dict(name="after_cr", offset=80, bytes=8, array_length=0, kind="u64"))
    exact_abi(
        value, dict(source_name=copied, size=size, alignment=8, reserved=size, fields=fields),
        source + ": exact ordinary copied record",
    )
    # Facts identify service storage; compiler typing and the closed next/put
    # graph enforce the sealed Console kind without any new metadata schema.
    exact_abi(
        function,
        dict(
            source_name=source, receiver=None, receiver_mutable=None,
            borrowed_parameter=False, second_receiver=None, root_count=0,
            root_tuple_bytes=0, root_order=[], parameter_bytes=96 if response else 24,
            parameters=[dict(offset=0, bytes=16, kind="service"),
                        dict(offset=16, bytes=80, kind="class", type_name=record) if response
                        else dict(offset=16, bytes=8, kind="bool")],
            result=dict(bytes=8, kind="bool") if response else dict(bytes=88, kind="class", type_name=record),
        ),
        source + ": exact service argument, copied value and canonical bool layout",
    )
    return entry


def check_program_console_calls(functions, generated, public, input_entry, response_entry):
    """Input may read/write; response may only write; copied policies have no authority."""
    def closure(root):
        pending, reached, imports = [root], set(), set()
        while pending:
            name = pending.pop()
            if name in reached:
                continue
            need(name in generated, "Program Console call escaped generated ownership")
            reached.add(name)
            for call in functions[name]["calls"]:
                target = call["target"]
                if target in CONSOLE_OPERATIONS:
                    imports.add(target)
                else:
                    need(
                        target in generated and (target not in public or is_reflection_helper(target)),
                        "Generated call acquired a native/public target",
                    )
                    pending.append(target)
        return reached, imports

    reader, imports = closure(input_entry)
    need(imports == CONSOLE_OPERATIONS, "Program reader must use only Console next/put")
    presenter, imports = closure(response_entry)
    need(imports == {"__au_runtime_console_put"}, "Program response must use only Console put")
    for root in public - {PROGRAM_INPUT_BRIDGE, PROGRAM_RESPONSE_BRIDGE}:
        _, authority = closure(root)
        need(not authority, "Copied policy/store graph acquired Console authority")
    sites = []
    for name in generated:
        for call in functions[name]["calls"]:
            if call["target"] not in CONSOLE_OPERATIONS:
                continue
            need(name in reader | presenter and call["live_bytes"] % 16 == 0, "Unowned or misaligned Console host call")
            if call["target"] == "__au_runtime_console_put":
                fact = (functions[name].get("service_abi") or {}).get("calls", {}).get(call["target"])
                need(fact == dict(sysv_arguments=3, result_max=1), "Changed native Console put service ABI")
            sites.append(dict(function=name, **call))
    sites.sort(key=lambda row: (row["function"], row["address"]))
    return {entry: [site for site in sites if site["function"] in reached]
            for entry, reached in ((input_entry, reader), (response_entry, presenter))}


def check_program_input_wait(functions, owner, entry):
    """Every path to the timer wait retains the private reader and Console call."""
    required = (PROGRAM_INPUT_BRIDGE, entry, "__au_runtime_console_next")
    reaches = {owner}
    while True:
        larger = reaches | {
            name for name, body in functions.items() if any(call["target"] in reaches for call in body["calls"])
        }
        if larger == reaches:
            break
        reaches = larger
    need("uefi_payload_entry" in reaches, "Unreachable program input timer wait")
    pending, visited = [("uefi_payload_entry", 0)], set()
    while pending:
        name, index = pending.pop()
        if (name, index) in visited:
            continue
        visited.add((name, index))
        if name in required:
            need(index < len(required) and name == required[index], "Program timer wait bypasses retained input entry")
            index += 1
        if name == owner:
            need(index == len(required), "Program timer wait lacks retained Console authority")
        else:
            pending.extend((call["target"], index) for call in functions[name]["calls"] if call["target"] in reaches)


def check_stream_operation(facts):
    symbol, operation = compiler_abi.abi_declaration(facts, "enums", "CommandOperation")
    # These fixed values are the native Stream::Operation bridge mapping.
    expected = {
        "begin": 0,
        "begin_read": 1,
        "awaiting_read": 2,
        "next_input": 3,
        "accept_request": 4,
        "accept_reply": 5,
        "acknowledge": 6,
        "ready_to_finish": 7,
        "finish": 8,
        "cancel": 9,
        "scrubbed": 10,
    }
    cases = operation["cases"]
    need(
        cases == expected and all(type(value) is int for value in cases.values()),
        "Named stream operations must match the native bridge values",
    )
    _, function = compiler_abi.abi_declaration(facts, "functions", "update_stream")
    need(
        len(function["parameters"]) == 5
        and function["parameters"][1] == dict(offset=192, bytes=8, kind="enum", type_name=symbol),
        "Stream bridge operation must use its exact nominal enum",
    )


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


def check_response_bridge(actual, private):
    need(
        actual == [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("mov", "%rdi,%r11"),
                   ("call", private), ("leave", ""), ("ret", "")],
        "Exact copied response/scalar bool bridge",
    )


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
        "language.stack.json",
        "language.abi.json",
        "language.o",
        "runtime-entry.o",
        "runtime-exceptions.o",
        "payload-entry.o",
    ]
    names += [
        name + ".o"
        for name in (
            "payload",
            "acpi",
            "pci",
            "runtime",
            "loader",
            "memory",
            "embed",
            "transition",
        )
    ]
    names += [name + suffix for name in ("payload", "acpi", "pci", "runtime", "loader") for suffix in (".su", ".ci")]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    names += [
        "user-" + name + suffix
        for name in ("clean", "bounds")
        for suffix in (".s", ".stack.json", ".abi.json", ".o", ".elf", ".bin")
    ]
    names += ["user-clean-entry.o"]
    return build_artifacts(names)


def hashes(paths):
    result = {}
    for path in paths:
        path = Path(path).absolute()
        need(
            path.is_relative_to(BUILD) and path.resolve(strict=True).is_relative_to(BUILD),
            "Artifact escaped selected build directory",
        )
        key = "build:" + path.relative_to(BUILD).as_posix()
        need(key not in result, "Duplicate hash input: " + key)
        result[key] = digest(path)
    return result


def emit(mode):
    RECEIPT.unlink(missing_ok=True)
    need(mode in MODES, "Unsupported program console profile")
    before = hashes(build_files())
    subprocess.run(
        [
            sys.executable,
            "-B",
            ROOT / "scripts/kernel_uefi_image.py",
            "--build-dir",
            BUILD,
            "--ipc-policy",
        ],
        cwd=ROOT,
        check=True,
    )
    metadata = json.loads((BUILD / "user-images.json").read_text())
    need(
        set(metadata) == {"clean", "bounds"},
        "Expected exactly two compiled user images",
    )
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
            note_entry=source_symbol(BUILD / "user-bounds.abi.json", "aurora_user_main") if index == 1 else None,
        )
        for key, value in actual.items():
            need(metadata[name][key] == value, "Stale user metadata: " + key)
    payload = (BUILD / "payload.bin").read_bytes()
    names = symbols(BUILD / "payload.elf")
    for begin, end, opcode in (
        ("uefi_program_poll_begin", "uefi_program_poll_end", "fbf4fa"),
        ("uefi_service_drain_begin", "uefi_service_drain_end", "fb9090fa"),
    ):
        need(
            payload[names[begin] : names[end]] == bytes.fromhex(opcode),
            "Changed exact poll/drain window",
        )
    stack = stack_evidence(BUILD)
    result = dict(
        schema="aurora-program-console-admission-v1",
        status="requires-independent-review",
        mode=mode,
        clock="tcg-original-clock",
        user_images=metadata,
        poll=json.loads((BUILD / "program-poll-metadata.json").read_text()),
        timer=json.loads((BUILD / "service-timer-metadata.json").read_text()),
        stack=stack,
        note=note_evidence(BUILD, stack["linked_functions"], mode),
    )
    write_admission(RECEIPT, result, build_files(), before)
    print(
        "PASS: automated protected-console image/stack checks; first-change qualification requires independent review."
    )
    return result


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result

    return json.loads(
        path.read_text(),
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Non-finite JSON: " + value)),
    )


def write_admission(path, result, files, before):
    """Bind semantic admission to its actual image, objects and compiler sidecars."""
    verify_object_exports(files)
    need(before == hashes(files), "Image/object/sidecar changed during admission")
    result["sha256"] = before
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


def check_admission(path, schema, mode, files):
    if not path.is_file():
        raise Blocked("Build this profile first; automatic admission is missing")
    receipt = read_json(path)
    need(
        receipt["schema"] == schema
        and receipt["mode"] == mode
        and receipt["status"] == "requires-independent-review"
        and receipt["clock"] == "tcg-original-clock",
        "Admission profile/status/clock mismatch",
    )
    verify_object_exports(files)
    need(
        receipt["sha256"] == hashes(files),
        "Admitted image/object/sidecar inventory or bytes changed",
    )
    return receipt


def checked(mode):
    need(mode in MODES, "Unsupported program console profile")
    return check_admission(RECEIPT, "aurora-program-console-admission-v1", mode, build_files())


def main():
    parser = argparse.ArgumentParser()
    path_arguments(parser)
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
    except Blocked as error:
        print("BLOCKED: program console admission: " + str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.CalledProcessError,
    ) as error:
        raise SystemExit("FAIL: program console admission: " + str(error)) from error
