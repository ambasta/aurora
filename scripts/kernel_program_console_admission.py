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


def symbols(path):
    return {
        row[2]: int(row[0], 16)
        for line in subprocess.check_output(["nm", "-a", path], text=True).splitlines()
        if len(row := line.split()) == 3
    }


def linked_assembly(stack, linked, directory, name):
    """Check whole executable sections, allowing only the actual rel32 slots."""
    obj = stack.Elf(directory / (name + ".o"))
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


def graph_peak(functions, frames, root, recursive, target=None):
    """Actual live call-site depth, bounded source-recursion contracts only."""

    def visit(name, path, counts):
        if name in recursive:
            count = counts.get(name, 0)
            if count == 4:
                return None
            counts = dict(counts, **{name: count + 1})
        else:
            need(name not in path, "Unknown call/control-flow cycle: " + name)
        body = functions[name]
        frame = max(body["local_peak"], frames.get(name, 0))
        best = (frame, [name]) if target is None or name == target else None
        if name == target:
            return best
        for call in body["calls"]:
            if call["target"] is None:
                continue
            child = visit(call["target"], path + [name], counts)
            if child is None:
                continue
            value = call["live_bytes"] + max(0, frame - body["local_peak"]) + child[0]
            if best is None or value > best[0]:
                best = value, [name] + child[1]
        return best

    result = visit(root, [], {})
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
            need(row.op == "mov" and row.op in decoder.PRESERVE_FLAGS, "Unsupported switch interleaving")
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


def stack_evidence(directory):
    decoder = load("program_stack_decoder", ROOT / "tests/kernel-uefi-owned-bytes-stack.py")
    decoder.CPP_OBJECTS = ("payload", "acpi", "pci", "runtime")
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
    frames, associations = decoder.cpp_frames(directory, linked)
    named = {symbol.name: symbol for symbol in linked.symbols if symbol.section}
    enter, leave, handler = [named[key] for key in ("uefi_runtime_enter", "aurora_leave_user", "uefi_runtime_handler")]
    # Bound the assembly handler by the original object's exact text extent.
    entry_object = decoder.Elf(directory / "runtime-entry.o")
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
    for object_name in ("language", "memory"):
        obj = decoder.Elf(directory / (object_name + ".o"))
        for symbol in obj.functions.values():
            decoder.associate_object(linked, obj, symbol)
    assembly = []
    for name in ("runtime-entry", "runtime-exceptions", "payload-entry"):
        assembly += linked_assembly(decoder, linked, directory, name)
    fixed = {
        "kernel/uefi/runtime-entry.S": "4eb746286de4390de61e559ad284ba74b0e671e3d59f1a83963874f95867e805",
        "kernel/exceptions.S": "c375958b8e813dadcf66c4f4113ba91f3ea6d5cc6c8f1cbda1bc480005d6c69f",
        "kernel/uefi/ipc-user-entry.S": "08c04296ebd57a2b9447d057eecdabc0088dd7372460f8ba204497279581a108",
        "kernel/uefi/runtime-tables.hpp": "c525ca83ff244c556b8196cf90e4ca18af42a5556caf2b298234f8a4a3543521",
    }
    for name, sha in fixed.items():
        need(digest(ROOT / name) == sha, "Changed bounded assembly/recursion contract: " + name)
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
    # Actual linked graph, not max-frame or sum-of-unrelated-.su estimates.
    # PageTables recursion additionally has emitted level-register proof. The two
    # RuntimeTables walkers use the pinned C++ contract: entry 3, recurse only at
    # nonzero level with level-1, hence no more than four live frames. Their exact
    # emitted bodies/call sites are retained for mandatory independent review.
    levels, roots = decoder.recursion_proof(functions, linked.functions, code, starts, associations)
    recursive = {name for name in functions if name == decoder.WALK or ("RuntimeTables7inspect" in name)}
    need(len(recursive) == 3, "Unexpected bounded walker inventory")
    for name in functions:
        graph_peak(functions, frames, name, recursive)
    normal = graph_peak(functions, frames, "uefi_payload_entry", recursive)
    dispatch = graph_peak(functions, frames, "aurora_exception_dispatch", recursive)
    boot_fault = 48 + max(
        graph_peak(functions, frames, name, recursive)["peak"]
        for name in ("uefi_payload_fault", "uefi_payload_page_fault")
    )
    irq_peak = 176 + 15 + dispatch["peak"]
    points = {}
    for name in ("uefi_program_poll_begin", "uefi_service_drain_begin"):
        pc = named[name].address
        owners = [
            key for key, symbol in linked.functions.items() if symbol.address <= pc < symbol.address + symbol.size
        ]
        need(len(owners) == 1, "Ambiguous interruptible function: " + name)
        path = graph_peak(functions, frames, "uefi_payload_entry", recursive, target=owners[0])
        path["peak_with_interrupt"] = path["peak"] + irq_peak
        points[name] = path
    need(normal["peak"] + boot_fault <= 15360, "Kernel normal/fault stack cap exhausted")
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
        path = graph_peak(bodies, {}, "aurora_user_main", set())
        path["entry_saved_bytes"] = 48
        path["peak_with_entry"] = path["peak"] + 48
        need(path["peak_with_entry"] <= 15360, "CPL3 stack cap exhausted")
        users[name] = path
    return dict(
        stack_bytes=16384,
        cap_bytes=15360,
        normal=normal,
        boot_fault=boot_fault,
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
        recursion_contracts=dict(maximum_live_frames=4, symbols=sorted(recursive), source_sha256=fixed),
        page_verifier=dict(roots=roots, levels=levels),
        assembly_objects=assembly,
        disassembly_sha256=hashlib.sha256(disassembly.encode()).hexdigest(),
    )


def source_files():
    paths = {ROOT / "Makefile"}
    for directory in ("kernel", "compiler", "library", "examples", "scripts", "tests"):
        paths.update(
            path
            for path in (ROOT / directory).rglob("*")
            if path.is_file() and path.suffix in (".cpp", ".hpp", ".h", ".inc", ".S", ".au", ".ld", ".py", ".sh")
        )
    return sorted(paths)


def build_files():
    names = [
        "payload.elf",
        "payload.bin",
        "esp/EFI/BOOT/BOOTX64.EFI",
        "program-poll-metadata.json",
        "service-timer-metadata.json",
        "user-images.json",
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
    names += [
        "user-" + name + suffix for name in ("clean", "bounds") for suffix in (".s", ".o", ".elf", ".bin", "-entry.o")
    ]
    return [BUILD / name for name in names]


def hashes(paths):
    return {str(path.relative_to(ROOT)): digest(path) for path in paths}


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
            "runtime": ["-fpie", "-fvisibility=hidden", "-Ibuild/uefi"],
            "loader": ["-fpie", "-maccumulate-outgoing-args", "-Ibuild/uefi"],
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
        required <= set(manifest["flags"])
        and "-DAURORA_UEFI_DISPATCH" not in manifest["flags"]
        and "-DAURORA_UEFI_CONSOLE" not in manifest["flags"],
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
    manifest["output_sha256"] = hashes(build_files())
    (BUILD / "program-build.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def provenance(mode):
    manifest = json.loads((BUILD / "program-build.json").read_text())
    verify_inputs(manifest, mode)
    need(manifest["output_sha256"] == hashes(build_files()), "Build output changed after compilation")
    return manifest


def emit(mode):
    need(mode in MODES, "Unsupported program console profile")
    RECEIPT.unlink(missing_ok=True)
    manifest = provenance(mode)
    subprocess.run([sys.executable, "-B", ROOT / "tests/kernel-uefi-image.py", "--ipc-policy"], cwd=ROOT, check=True)
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
    parser.add_argument("action", choices=("emit", "checked", "reviewed", "diagnose", "begin-build", "end-build"))
    parser.add_argument("--mode", choices=MODES, default="program-console")
    parser.add_argument("--compiler")
    parser.add_argument("--cxx")
    parser.add_argument("--flag", action="append", default=[])
    args = parser.parse_args()
    if args.action == "begin-build":
        begin_build(args.mode, args.compiler, args.cxx, args.flag)
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
