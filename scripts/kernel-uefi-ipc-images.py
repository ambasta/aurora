#!/usr/bin/env python3
"""Validate staged IPC images and emit their bounded metadata/header."""

from pathlib import Path
import argparse, json, subprocess

ROOT = Path(__file__).resolve().parent.parent
BASE = 0x10000000000


def need(value, message):
    if not value:
        raise ValueError(message)


import importlib.util

_spec = importlib.util.spec_from_file_location("uefi_image_builder", ROOT / "scripts/kernel-uefi-user-images.py")
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)


def verify(
    data,
    blob,
    base,
    symbols,
    probe_opcode=b"\x0f\x0b",
    *,
    dispatcher=False,
    copied_snapshot=False,
    copied_note=False,
    note_entry=None,
    call_entry=None,
):
    result = _base.verify(
        data,
        blob,
        base,
        symbols,
        image_count=3 if dispatcher else 2,
        copied_snapshot=copied_snapshot,
        copied_note=copied_note,
        note_entry=note_entry,
        call_entry=call_entry,
    )
    need(result["probe_offset"] == 0, "IPC has no address literal authority")
    probe = result["probe_pc"]
    if probe:
        need(
            base <= probe <= base + len(blob) - 2
            and blob[probe - base : probe - base + len(probe_opcode)] == probe_opcode,
            "IPC exact hostile probe",
        )
        need(
            probe
            not in [result[k] for k in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")],
            "IPC probe aliases accepted site",
        )
    call_pc = symbols.get("aurora_call_return_pc", 0)
    call_stub = symbols.get("__au_runtime_call", 0)
    if call_entry is not None:
        need(
            base + 2 <= call_pc < base + len(blob)
            and call_stub == call_pc - 2
            and blob[call_stub - base : call_pc - base + 1] == b"\xcd\x82\xc3",
            "Exact INT82 returning call stub",
        )
        need(
            all(
                not (call_stub < result[k] + 2 and result[k] < call_pc + 1)
                for k in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc")
                if result[k]
            ),
            "Call stub aliases terminal site",
        )
        result["call_pc"] = call_pc
    else:
        need(call_pc == call_stub == 0, "Call authority outside singleton client")
    return result


def service_metadata(meta, blob, symbols, function_size, compiled="aurora_user_main"):
    base = meta["entry"]
    begin = symbols.get(compiled, 0)
    need(type(function_size) is int and function_size > 0, "Nonempty compiled function")
    end = begin + function_size
    need(
        base <= meta["return_pc"] < begin < end <= base + len(blob) and end <= meta["bounds_pc"],
        "Bounded compiled function",
    )
    probe_begin = symbols.get("aurora_budget_context_begin", 0)
    probe_end = symbols.get("aurora_budget_context_end", 0)
    need(
        (probe_begin == probe_end == 0) or base <= probe_begin < probe_end <= meta["return_pc"],
        "Bounded register probe",
    )
    if probe_begin:
        need(
            blob[probe_begin - base : probe_end - base] == b"\x48\xff\x0c\x24\x75\xfa",
            "Exact register-preservation loop",
        )
    return dict(meta, compiled_begin=begin, compiled_end=end, context_begin=probe_begin, context_end=probe_end)


def validate_composition(
    mode,
    service_budget=False,
    dispatcher=False,
    user_budget=False,
    program_console=False,
    snapshot=False,
    blocking_call=False,
    file_call=False,
):
    need(
        not blocking_call
        or service_budget
        and user_budget
        and not any((dispatcher, snapshot))
        and program_console == file_call
        and mode == "normal",
        "Call requires exact two-domain timer composition",
    )
    need(not file_call or blocking_call and program_console, "File call requires exact console/call composition")
    need(
        not snapshot or not any((service_budget, dispatcher, user_budget, program_console, blocking_call)),
        "Snapshot requires its exclusive IPC composition",
    )
    need(mode != "resume" or (user_budget and dispatcher and not program_console), "Resume requires client dispatcher")
    need(not snapshot or mode in ("normal", "owner", "reply-reserved", "reply-byte"), "Unsupported snapshot mode")
    need(mode not in ("reply-reserved", "reply-byte") or snapshot, "Snapshot reply probe requires snapshot")
    need(
        not program_console or service_budget and user_budget and not dispatcher,
        "Protected console requires its exact two-domain timer composition",
    )
    need(
        not program_console or mode in ("normal", "owner", "ordinal", "unknown", "transaction"),
        "Unsupported protected console mode",
    )
    need(not user_budget or dispatcher or program_console or blocking_call, "User budgets require dispatcher profile")
    need(not dispatcher or service_budget, "Dispatcher requires service timer profile")


def call_entry_abi(facts):
    from bootstrap_frontend import abi_function_symbol

    symbol = abi_function_symbol(facts, "aurora_user_main")
    expected = dict(
        source_name="aurora_user_main",
        receiver=None,
        receiver_mutable=None,
        borrowed_root_count=0,
        borrowed_roots=[],
        borrowed_root_abi=dict(
            kind="none", register=None, tuple_payload_bytes=0, tuple_reserved_bytes=0, saved_root_reserved_bytes=0
        ),
        parameter_bytes=40,
        parameters=[dict(offset=0, bytes=16, kind="service")]
        + [dict(offset=offset, bytes=8, kind="u64") for offset in (16, 24, 32)],
        result=dict(bytes=8, kind="u64"),
    )
    need(facts.get("version") == 2 and facts["functions"][symbol] == expected, "Exact copied call entry ABI")
    return symbol


def emit_metadata(
    out,
    mode,
    service_budget=False,
    dispatcher=False,
    user_budget=False,
    program_console=False,
    snapshot=False,
    blocking_call=False,
    file_call=False,
):
    validate_composition(
        mode, service_budget, dispatcher, user_budget, program_console, snapshot, blocking_call, file_call
    )
    records = {}
    header = ["#pragma once", "#include <array>", "#include <cstddef>", "namespace aurora::uefi::images {"]
    for index, name in enumerate(("clean", "bounds", "peer") if dispatcher else ("clean", "bounds")):
        prefix = out / f"user-{name}"
        elf = prefix.with_suffix(".elf")
        binary = prefix.with_suffix(".bin")
        base = BASE + index * 4096
        need(
            "There are no relocations" in subprocess.check_output(["readelf", "-rW", elf], text=True),
            "Unresolved image relocations",
        )
        symbols = {
            line.split()[2]: int(line.split()[0], 16)
            for line in subprocess.check_output(["nm", "-a", elf], text=True).splitlines()
            if len(line.split()) == 3
        }
        blob = binary.read_bytes()
        opcode = {"mmio": b"\x8b\x00", "softint": b"\xcd\x40", "fpu": b"\xd9\xd0", "peer-code": b"\x49\x8b\x02"}.get(
            mode, b"\x0f\x0b"
        )
        compiled = (
            "__au_v_m1_16snapshot_service_n0__d16aurora_user_main"
            if blocking_call and not file_call and index == 1
            else "aurora_user_main"
        )
        if (program_console and index == 1) or (blocking_call and index == 0):
            from bootstrap_frontend import abi_function_symbol

            compiled = abi_function_symbol(json.loads(prefix.with_suffix(".abi.json").read_text()), "aurora_user_main")
        if blocking_call and index == 0:
            compiled = call_entry_abi(json.loads(prefix.with_suffix(".abi.json").read_text()))
        meta = verify(
            elf.read_bytes(),
            blob,
            base,
            symbols,
            opcode,
            dispatcher=dispatcher,
            copied_snapshot=(snapshot or (blocking_call and not file_call)) and index == 1,
            copied_note=program_console and index == 1,
            note_entry=compiled if program_console and index == 1 else None,
            call_entry=compiled if blocking_call and index == 0 else None,
        )
        if service_budget:
            functions = [
                line.split()
                for line in subprocess.check_output(["readelf", "-sW", elf], text=True).splitlines()
                if line.split() and line.split()[-1] == compiled
            ]
            need(len(functions) == 1 and functions[0][3] == "FUNC", "Exact compiled function symbol")
            need(int(functions[0][1], 16) == symbols[compiled], "Consistent function entry")
            meta = service_metadata(meta, blob, symbols, int(functions[0][2]), compiled)
        records[name] = meta
        header.append(
            f"inline constexpr std::array<std::byte,{len(blob)}> {name}_bytes = {{"
            + ",".join(f"std::byte{{{value}}}" for value in blob)
            + "};"
        )
        for key, value in meta.items():
            header.append(f"inline constexpr unsigned long long {name}_{key}={value}ULL;")
    header.append("}")
    (out / "uefi-user-images.hpp").write_text("\n".join(header) + "\n")
    (out / "user-images.json").write_text(json.dumps(records, indent=2) + "\n")
    print("PASS: " + str(len(records)) + " independently compiled staged IPC RX images")


def call_stack_profile(graph):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import kernel_stack as stack

    return stack.profile_stack(
        graph,
        {"discover_acpi(": 128, "prepare_service_acpi(": 5120, "discover_pci(": 11264},
        default_limit=11264,
        fault_reserve=512,
        separated=(("prepare_service_acpi(", "discover_pci("),),
    )


def call_client_stack(directory):
    import kernel_stack as stack
    from kernel_program_console_admission import check_referenced_reflection

    result = {}
    prefix = directory / "user-clean"
    user = stack.Elf(prefix.with_suffix(".elf"))
    symbols = {symbol.name: symbol for symbol in user.symbols}
    code, _ = stack.disassemble(user.path)
    entry = call_entry_abi(json.loads(prefix.with_suffix(".abi.json").read_text()))
    facts = json.loads(prefix.with_suffix(".stack.json").read_text())["functions"]
    need(
        facts[entry]["service_abi"]["record"]
        == dict(parameters=[["builtin::CallSession", 16]] + [["scalar", 8]] * 3, result_bytes=8),
        "Exact singleton CallSession entry fact",
    )
    starts = {symbol.address: name for name, symbol in user.functions.items()}
    functions = stack.aurora_stack_functions(prefix.with_suffix(".stack.json"), user.functions, code, starts, facts)
    need(set(user.functions) == set(facts) | {"__au_runtime_call"}, "Closed call client function inventory")
    stub = user.functions["__au_runtime_call"]
    need(
        stub.size == 3
        and [(code[stub.address].op, code[stub.address].args), (code[stub.address + 2].op, code[stub.address + 2].args)]
        == [("int", "$0x82"), ("ret", "")],
        "Exact linked returning call stub",
    )
    functions["__au_runtime_call"] = dict(local_peak=8, calls=[], returns=1)
    check_referenced_reflection(functions, set(facts), bridges={"__au_runtime_call"})
    # The only handwritten user frame is the fixed envelope and copied record.
    targets = {symbols[name].address: name for name in ("bad_entry", entry)}
    wrapper = []
    for address, insn in sorted(code.items()):
        if symbols["aurora_program_entry"].address <= address < stub.address:
            wrapper.append((insn.op, targets.get(stack.target_of(insn)) if insn.op in ("call", "jne") else insn.args))
    expected = [("or", f"%{reg},%rax") for reg in ("rbx", "rbp", "r10", "r11", "r12", "r13", "r14", "r15")]
    expected += [("jne", "bad_entry"), ("cmpq", "$0x0,-0x8(%rsp)"), ("jne", "bad_entry")]
    expected += [("push", f"%{reg}") for reg in ("rdi", "rdx", "rcx", "r8", "r9")]
    expected += [("sub", "$0x8,%rsp"), ("mov", "%r9,%rdx"), ("sub", "$0x30,%rsp")]
    for source, target in (("0x50", ""), ("0x48", "0x8"), ("0x58", "0x10")):
        expected += [("mov", f"{source}(%rsp),%rax"), ("mov", f"%rax,{target}(%rsp)")]
    expected += [
        ("mov", "%rsi,0x18(%rsp)"),
        ("mov", "%r9,0x20(%rsp)"),
        ("mov", "%rsp,%r11"),
        ("call", entry),
        ("add", "$0x30,%rsp"),
        ("add", "$0x8,%rsp"),
    ]
    expected += [("pop", f"%{reg}") for reg in ("r9", "r8", "rcx", "rdx", "rdi")]
    expected += [("mov", "$0x1,%esi"), ("int", "$0x81"), ("ud2", ""), ("ud2", "")]
    need(wrapper == expected, "Exact call wrapper record/envelope and stack depth")
    result["user"] = stack.calculate(functions, entry)
    result["user"]["peak_with_wrapper"] = 96 + result["user"]["peak"]
    need(result["user"]["peak_with_wrapper"] <= stack.STACK_CAP, "Call user stack reserve")
    return result["user"]


def call_stack(directory):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import kernel_stack as stack

    graph = stack.image_stack_graph(
        directory,
        ("payload", "acpi", "pci", "runtime", "snapshot", "owned-bytes-runtime"),
        ROOT,
        protected=True,
        bridges=(
            "__au_runtime_snapshot_produce",
            "aurora_kernel_value",
            "aurora_kernel_ipc_transition",
            "aurora_kernel_terminal_event",
            "aurora_kernel_budget_tick",
        ),
        noreturn=stack.OWNED_NORETURN,
    )
    import kernel_snapshot_abi

    kernel_snapshot_abi.main(directory, "normal", checksum=True)
    result = call_stack_profile(graph)
    linked = graph["linked"]
    site = next(s.address for s in linked.symbols if s.name == "uefi_service_drain_begin")
    owner = next(n for n, s in linked.functions.items() if s.address <= site < s.address + s.size)
    result["drain"] = stack.calculate(graph["functions"], "uefi_payload_entry", target=owner)
    result["drain_irq_fault_peak"] = result["drain"]["peak"] + result["irq_dispatch"]["peak_with_entry"] + 512
    need(result["drain_irq_fault_peak"] <= stack.STACK_CAP, "Call drain interrupt/fault reserve")
    result["user"] = call_client_stack(directory)
    service = directory / "user-bounds"
    service_elf = stack.Elf(service.with_suffix(".elf"))
    service_code, _ = stack.disassemble(service_elf.path)
    service_facts = json.loads(service.with_suffix(".stack.json").read_text())["functions"]
    need(set(service_elf.functions) == set(service_facts), "Closed checksum service function inventory")
    service_functions = stack.aurora_stack_functions(
        service.with_suffix(".stack.json"),
        service_elf.functions,
        service_code,
        {symbol.address: name for name, symbol in service_elf.functions.items()},
        service_facts,
    )
    result["service"] = stack.calculate(service_functions, kernel_snapshot_abi.SERVICE)
    result["service"]["peak_with_wrapper"] = 160 + result["service"]["peak"]
    need(result["service"]["peak_with_wrapper"] <= stack.STACK_CAP, "Checksum service stack reserve")
    (directory / "call-stack.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: call linked kernel/IRQ/drain and user stack; kernel peak " + str(result["peak_with_fault_reserve"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build/uefi")
    parser.add_argument(
        "--mode",
        default="normal",
        choices=[
            "normal",
            "resume",
            "owner",
            "stale",
            "version",
            "phase",
            "transaction",
            "site",
            "unknown",
            "mmio",
            "softint",
            "fpu",
            "context",
            "peer-code",
            "ordinal",
            "reply-reserved",
            "reply-byte",
        ],
    )
    parser.add_argument("--service-budget", action="store_true")
    parser.add_argument("--dispatcher", action="store_true")
    parser.add_argument("--user-budget", action="store_true")
    parser.add_argument("--program-console", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--blocking-call", action="store_true")
    parser.add_argument("--file-call", action="store_true")
    parser.add_argument("--call-stack", action="store_true")
    args = parser.parse_args()
    if args.call_stack:
        call_stack(Path(args.output).resolve())
        raise SystemExit(0)
    emit_metadata(
        Path(args.output).resolve(),
        args.mode,
        args.service_budget,
        args.dispatcher,
        args.user_budget,
        args.program_console,
        args.snapshot,
        args.blocking_call,
        args.file_call,
    )
