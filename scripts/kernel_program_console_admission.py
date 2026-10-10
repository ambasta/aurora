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
    parser.add_argument("--build-dir", type=Path, required=True, help="exact native profile output directory")


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
    decoder = load("reflection_decoder", ROOT / "scripts/kernel_stack.py")
    language, linked = decoder.Elf(directory / "objects/language.o"), decoder.Elf(directory / "payload.elf")
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
        else ("__au_runtime_note_update", "__au_runtime_note_project")
    )
    graph = decoder.image_stack_graph(
        directory, units, ROOT, protected=True, bridges=bridges, noreturn=decoder.OWNED_NORETURN if snapshot else ()
    )
    functions = graph["functions"]
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
    for name in () if snapshot else ("uefi_program_poll_begin", "uefi_service_drain_begin"):
        pc = named[name].address
        owners = [
            key for key, symbol in linked.functions.items() if symbol.address <= pc < symbol.address + symbol.size
        ]
        need(len(owners) == 1, "Ambiguous interruptible function: " + name)
        path = graph_peak(functions, "uefi_payload_entry", target=owners[0])
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
                else "__au_v_m1_22program_stream_service_n0__d16aurora_user_main"
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


def note_evidence(directory, mode="program-console"):
    """Exact private note composition; reuses the existing ELF/CFG decoder."""
    decoder = load("note_bridge_decoder", ROOT / "scripts/kernel_stack.py")
    abi = load("note_record_abi", ROOT / "scripts/kernel_snapshot_abi.py")
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
        actual_frame, prefix = decoder.private_frame_layout([line.strip() for line in source.splitlines()], body)
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
        "language.o",
        "runtime-entry.o",
        "runtime-exceptions.o",
        "payload-entry.o",
    ]
    names += [name + ".o" for name in ("payload", "acpi", "pci", "runtime", "loader", "memory", "embed", "transition")]
    names += [name + suffix for name in ("payload", "acpi", "pci", "runtime", "loader") for suffix in (".su", ".ci")]
    names += [name + "-pe.o" for name in ("loader", "memory", "embed", "transition")]
    names += [
        "user-" + name + suffix
        for name in ("clean", "bounds")
        for suffix in (".s", ".stack.json", ".o", ".elf", ".bin")
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
        [sys.executable, "-B", ROOT / "scripts/kernel_uefi_image.py", "--build-dir", BUILD, "--ipc-policy"],
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
        user_images=metadata,
        poll=json.loads((BUILD / "program-poll-metadata.json").read_text()),
        timer=json.loads((BUILD / "service-timer-metadata.json").read_text()),
        stack=stack_evidence(BUILD),
        note=note_evidence(BUILD, mode),
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
    need(receipt["sha256"] == hashes(files), "Admitted image/object/sidecar inventory or bytes changed")
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
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        raise SystemExit("FAIL: program console admission: " + str(error)) from error
