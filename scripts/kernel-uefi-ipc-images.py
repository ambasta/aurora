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


PROBE_OPCODES = {
    "mmio": b"\x8b\x00",
    "softint": b"\xcd\x40",
    "fpu": b"\xd9\xd0",
    "peer_code": b"\x49\x8b\x02",
    "unknown": b"\x0f\x0b",
}


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
    copied_call=False,
    serve_entry=None,
):
    result = _base.verify(
        data,
        blob,
        base,
        symbols,
        image_count=3 if dispatcher else 2,
        max_pages=2 if call_entry is not None else 1,
        copied_snapshot=copied_snapshot,
        copied_note=copied_note,
        note_entry=note_entry,
        call_entry=call_entry,
        copied_call=copied_call,
        serve_entry=serve_entry,
    )
    need(result["probe_offset"] == 0, "IPC has no address literal authority")
    # A fixture wrapper carries one exact instruction per selectable probe.
    probes = result.get("probes", {})
    need(not probes or set(probes) == set(PROBE_OPCODES), "IPC exact selectable probe set")
    for kind, pc in probes.items():
        opcode = PROBE_OPCODES.get(kind)
        need(
            opcode is not None and blob[pc - base : pc - base + len(opcode)] == opcode,
            "IPC exact selectable hostile probe",
        )
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
    serve_pc = symbols.get("aurora_serve_return_pc", 0)
    serve_stub = symbols.get("__au_runtime_serve_exchange", 0)
    if serve_entry is not None:
        need(
            base + 2 <= serve_pc < base + len(blob)
            and serve_stub == serve_pc - 2
            and blob[serve_stub - base : serve_pc - base + 1] == b"\xcd\x82\xc3",
            "Exact INT82 returning Serve stub",
        )
        need(
            all(
                not (serve_stub < pc + 2 and pc < serve_pc + 1)
                for pc in [
                    result[k]
                    for k in ("return_pc", "bounds_pc", "overflow_pc", "division_zero_pc", "shift_count_pc", "probe_pc")
                ]
                + list(result.get("probes", {}).values())
                if pc
            ),
            "Serve stub aliases terminal or hostile site",
        )
        result["serve_pc"] = serve_pc
    else:
        need(serve_pc == serve_stub == 0, "Serve authority outside singleton service")
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
    ram_file=False,
    ram_scratchpad_console=False,
    ram_scratchpad_fixture=False,
):
    need(mode in ("normal", "resume", "probes"), "Unsupported IPC image mode")
    need(
        not ram_scratchpad_fixture or ram_scratchpad_console,
        "Scratchpad fixture requires its exact copied console composition",
    )
    need(
        not ram_scratchpad_console or ram_file,
        "Scratchpad requires the exact retained RAM-file composition",
    )
    need(
        not ram_file
        or service_budget
        and user_budget
        and not any((dispatcher, program_console, snapshot, blocking_call, file_call))
        and mode == "normal",
        "RAM file requires its exclusive two-domain timer composition",
    )
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
    need(not snapshot or mode == "normal", "Unsupported snapshot mode")
    need(mode != "probes" or service_budget and not snapshot, "Selectable probes require a timer fixture")
    need(
        not program_console or service_budget and user_budget and not dispatcher,
        "Protected console requires its exact two-domain timer composition",
    )
    need(
        not program_console or mode == "normal",
        "Unsupported protected console mode",
    )
    need(
        not user_budget or dispatcher or program_console or blocking_call or ram_file,
        "User budgets require an admitted protected profile",
    )
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


def serve_entry_abi(facts):
    """Bind copied entry/result facts to the independently fixed native ABI."""
    from bootstrap_frontend import abi_declaration

    def exact(actual, expected, reason):
        # Unlike Python equality, this also distinguishes booleans from integers.
        need(json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True), reason)

    need(type(facts.get("version")) is int and facts["version"] == 2, "Expected current Serve ABI facts v2")
    symbol, function = abi_declaration(facts, "functions", "aurora_user_main")
    _, request = abi_declaration(facts, "records", "__au_serve_request")
    status_name, status = abi_declaration(facts, "enums", "__au_serve_status")
    exact(
        status,
        dict(source_name="__au_serve_status", cases=dict(request=0, cancelled=1)),
        "Exact Serve status ordinals",
    )
    exact(
        request,
        dict(
            source_name="__au_serve_request",
            size=16,
            alignment=8,
            reserved=16,
            fields=[
                dict(name="status", offset=0, bytes=8, array_length=0, kind="enum", type_name=status_name),
                dict(name="value", offset=8, bytes=8, array_length=0, kind="u64"),
            ],
        ),
        "Exact two-register ServeRequest layout",
    )
    exact(
        function,
        dict(
            source_name="aurora_user_main",
            receiver=None,
            receiver_mutable=None,
            borrowed_root_count=0,
            borrowed_roots=[],
            borrowed_root_abi=dict(
                kind="none", register=None, tuple_payload_bytes=0, tuple_reserved_bytes=0, saved_root_reserved_bytes=0
            ),
            parameter_bytes=16,
            parameters=[dict(offset=0, bytes=16, kind="service", type_name="builtin::ServeSession")],
            result=dict(bytes=8, kind="u64"),
        ),
        "Exact singleton Serve entry ABI",
    )
    return symbol


def ram_file_facts(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, "Duplicate RAM-file fact key")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=unique)


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
    ram_file=False,
    ram_scratchpad_console=False,
    ram_scratchpad_fixture=False,
):
    validate_composition(
        mode,
        service_budget,
        dispatcher,
        user_budget,
        program_console,
        snapshot,
        blocking_call,
        file_call,
        ram_file,
        ram_scratchpad_console,
        ram_scratchpad_fixture,
    )
    records = {}
    header = ["#pragma once", "#include <array>", "#include <cstddef>", "namespace aurora::uefi::images {"]
    for index, name in enumerate(("clean", "bounds", "peer") if dispatcher else ("clean", "bounds")):
        prefix = out / f"user-{name}"
        elf = prefix.with_suffix(".elf")
        binary = prefix.with_suffix(".bin")
        base = BASE + index * 16384
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
        opcode = b"\x0f\x0b"
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
        if ram_file:
            abi = ram_file_facts(prefix.with_suffix(".abi.json"))
            compiled = (
                scratchpad_call_entry_abi(abi)
                if ram_scratchpad_console and index == 0
                else call_entry_abi(abi)
                if index == 0
                else scratchpad_service_entry_abi(abi, fixture=ram_scratchpad_fixture)
                if ram_scratchpad_console
                else serve_entry_abi(abi)
            )
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
            call_entry=compiled if (blocking_call or ram_file) and index == 0 else None,
            copied_call=ram_scratchpad_console and index == 0,
            serve_entry=compiled if ram_file and index == 1 else None,
        )
        if ram_file:
            need(meta["probe_pc"] == 0, "RAM-file has no hostile-PC authority")
            if ram_scratchpad_console and index == 0:
                scratchpad_user_stack(prefix)
            else:
                ram_file_user_stack(
                    prefix,
                    service=index == 1,
                    scratchpad_fixture=ram_scratchpad_fixture if ram_scratchpad_console else None,
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
            if ram_file:
                need(meta["context_begin"] == meta["context_end"] == 0, "RAM-file has no register-probe authority")
        records[name] = meta
        header.append(
            f"inline constexpr std::array<std::byte,{len(blob)}> {name}_bytes = {{"
            + ",".join(f"std::byte{{{value}}}" for value in blob)
            + "};"
        )
        # The kernel loads only scalar facts; the probe set is guest-oracle evidence.
        for key, value in ((key, value) for key, value in meta.items() if key != "probes"):
            header.append(f"inline constexpr unsigned long long {name}_{key}={value}ULL;")
    header.append("}")
    (out / "uefi-user-images.hpp").write_text("\n".join(header) + "\n")
    (out / "user-images.json").write_text(json.dumps(records, indent=2) + "\n")
    print("PASS: " + str(len(records)) + " independently compiled staged IPC RX images")


def call_stack_profile(graph):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import kernel_stack as stack

    return stack.service_discovery_stack(graph)


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


def ram_file_user_stack(prefix, *, service, scratchpad_fixture=None):
    """Closed role-specific code graph and exact retained-stack entry envelope."""
    import kernel_stack as stack
    from kernel_program_console_admission import check_referenced_reflection

    user = stack.Elf(prefix.with_suffix(".elf"))
    need(not any(symbol.name and not symbol.section for symbol in user.symbols), "RAM-file undefined import")
    symbols = {symbol.name: symbol for symbol in user.symbols}
    code, _ = stack.disassemble(user.path)
    abi = ram_file_facts(prefix.with_suffix(".abi.json"))
    need(
        scratchpad_fixture is None or service and type(scratchpad_fixture) is bool,
        "Scratchpad service selection applies only to the retained Serve role",
    )
    entry = (
        scratchpad_service_entry_abi(abi, fixture=scratchpad_fixture)
        if scratchpad_fixture is not None
        else serve_entry_abi(abi)
        if service
        else call_entry_abi(abi)
    )
    facts = ram_file_facts(prefix.with_suffix(".stack.json"))["functions"]
    kind = "builtin::ServeSession" if service else "builtin::CallSession"
    parameters = [[kind, 16]] + ([] if service else [["scalar", 8]] * 3)
    need(
        facts[entry]["service_abi"]["record"] == dict(parameters=parameters, result_bytes=8),
        "Exact RAM-file role entry fact",
    )
    host = "__au_runtime_serve_exchange" if service else "__au_runtime_call"
    need(set(user.functions) == set(facts) | {host}, "Closed RAM-file role function inventory")
    starts = {symbol.address: name for name, symbol in user.functions.items()}
    need(len(starts) == len(user.functions), "Ambiguous RAM-file function starts")
    functions = stack.aurora_stack_functions(prefix.with_suffix(".stack.json"), user.functions, code, starts, facts)
    stub = user.functions[host]
    return_symbol = "aurora_serve_return_pc" if service else "aurora_call_return_pc"
    need(
        stub.size == 3
        and symbols[return_symbol].address == stub.address + 2
        and user.function_bytes(stub) == b"\xcd\x82\xc3"
        and [(code[stub.address].op, code[stub.address].args), (code[stub.address + 2].op, code[stub.address + 2].args)]
        == [("int", "$0x82"), ("ret", "")],
        "Exact linked role-specific exchange stub",
    )
    functions[host] = dict(local_peak=8, calls=[], returns=1)
    check_referenced_reflection(functions, set(facts), bridges={host})
    # Admission independently checks every handwritten push, record copy, and
    # transfer. Generated facts account for the call's return address and locals.
    targets = {symbols[name].address: name for name in ("bad_entry", entry)}
    wrapper = [
        (row.op, targets.get(stack.target_of(row)) if row.op in ("call", "jne") else row.args)
        for address, row in sorted(code.items())
        if symbols["aurora_program_entry"].address <= address < stub.address
    ]
    expected = [("or", f"%{reg},%rax") for reg in ("rbx", "rbp", "r10", "r11", "r12", "r13", "r14", "r15")]
    expected += [("jne", "bad_entry"), ("cmpq", "$0x0,-0x8(%rsp)"), ("jne", "bad_entry")]
    expected += [("push", f"%{reg}") for reg in ("rdi", "rdx", "rcx", "r8", "r9")]
    expected += [("sub", "$0x8,%rsp"), ("mov", "%r9,%rdx")]
    expected += [("sub", "$0x10,%rsp" if service else "$0x30,%rsp")]
    copies = (("0x30", ""), ("0x28", "0x8")) if service else (("0x50", ""), ("0x48", "0x8"), ("0x58", "0x10"))
    for source, target in copies:
        expected += [("mov", f"{source}(%rsp),%rax"), ("mov", f"%rax,{target}(%rsp)")]
    if not service:
        expected += [("mov", "%rsi,0x18(%rsp)"), ("mov", "%r9,0x20(%rsp)")]
    expected += [("mov", "%rsp,%r11"), ("call", entry)]
    expected += [("add", "$0x10,%rsp" if service else "$0x30,%rsp"), ("add", "$0x8,%rsp")]
    expected += [("pop", f"%{reg}") for reg in ("r9", "r8", "rcx", "rdx", "rdi")]
    expected += [("mov", "$0x1,%esi"), ("int", "$0x81"), ("ud2", ""), ("ud2", "")]
    need(wrapper == expected, "Exact RAM-file role wrapper record/envelope and stack depth")
    for name in functions:
        stack.calculate(functions, name)
    result = stack.calculate(functions, entry)
    need(host in result["closure"], "RAM-file role must execute its exchange operation")
    result["peak_with_wrapper"] = (64 if service else 96) + result["peak"]
    need(result["peak_with_wrapper"] <= stack.STACK_CAP, "RAM-file user stack reserve")
    return result


def scratchpad_call_entry_abi(facts):
    from kernel_program_console_admission import check_scratchpad_abi

    return check_scratchpad_abi(facts, role="call")


def scratchpad_service_entry_abi(facts, *, fixture=False):
    """The fixture substitutes only its named Serve source, never the caller ABI."""
    import kernel_stack as stack

    need(type(fixture) is bool, "Exact scratchpad service variant")
    entry = serve_entry_abi(facts)
    need(
        stack.aurora_module(entry) == ("scratchpad_service_fixture" if fixture else "ram_file_service"),
        "Exact source-selected scratchpad Serve variant",
    )
    return entry


def scratchpad_user_stack(prefix):
    """Exact fixed copies plus compiler-verified singleton Call loan provenance.

    Current generic ABI gives the prefix storage, not its nominal service kind.
    A closed reachable Call-only graph binds that singleton prefix to Call; the
    compiler's loan/type checking is trusted. No new service-record fact is used.
    """
    import kernel_stack as stack
    from kernel_program_console_admission import check_referenced_reflection

    user = stack.Elf(prefix.with_suffix(".elf"))
    generated = stack.Elf(prefix.parent / "objects" / (prefix.name + ".o"))
    need(not any(symbol.name and not symbol.section for symbol in user.symbols), "Scratchpad undefined import")
    need(
        not any(symbol.name and not symbol.section for symbol in generated.symbols),
        "Scratchpad object undefined import",
    )
    symbols = {symbol.name: symbol for symbol in user.symbols}
    code, _ = stack.disassemble(user.path)
    abi = ram_file_facts(prefix.with_suffix(".abi.json"))
    entry = scratchpad_call_entry_abi(abi)
    facts = ram_file_facts(prefix.with_suffix(".stack.json"))["functions"]
    need(set(abi["functions"]) == set(facts), "Copied Call generic/stack function inventory mismatch")
    host = "__au_runtime_call"
    need(
        set(user.functions) == set(generated.functions) == set(facts) | {host}, "Closed copied Call function inventory"
    )
    need(
        {name for name in symbols if name.startswith("__au_runtime_")} == {host},
        "Copied Call rejects unused or hidden foreign runtime imports",
    )
    for symbol in generated.functions.values():
        stack.associate_object(user, generated, symbol)
    starts = {symbol.address: name for name, symbol in user.functions.items()}
    need(len(starts) == len(user.functions), "Ambiguous copied Call function starts")
    functions = stack.aurora_stack_functions(prefix.with_suffix(".stack.json"), user.functions, code, starts, facts)
    need(
        functions[entry]["copied_record"] is None,
        "Copied Call uses full generic ABI, not a scalar copied-record shortcut",
    )
    service = functions[entry].get("service_abi")
    need(service is None or service["record"] is None, "Copied Call must not invent a service entry record")
    stub = user.functions[host]
    need(
        stub.size == 3
        and symbols["aurora_call_return_pc"].address == stub.address + 2
        and user.function_bytes(stub) == b"\xcd\x82\xc3",
        "Exact unchanged copied Call INT82/ret stub",
    )
    functions[host] = dict(local_peak=8, calls=[], returns=1)
    stack.singleton_service_graph(functions, set(facts), entry, host, "builtin::CallSession")
    check_referenced_reflection(functions, set(facts), bridges={host})
    base = symbols["aurora_program_entry"].address
    targets = {symbols[name].address: name for name in ("bad_entry", entry)}
    rows = [row for address, row in sorted(code.items()) if base <= address < stub.address]
    wrapper = [(row.op, targets.get(stack.target_of(row)) if row.op in ("call", "jne") else row.args) for row in rows]
    expected = [("or", f"%{reg},%rax") for reg in ("rbx", "rbp", "r10", "r11", "r12", "r13", "r14", "r15")]
    expected += [("jne", "bad_entry"), ("cmpq", "$0x0,-0x8(%rsp)"), ("jne", "bad_entry"), ("sub", "$0xc0,%rsp")]
    expected += [("push", f"%{reg}") for reg in ("rdi", "rdx", "rcx", "r8", "r9")]
    expected += [
        ("sub", "$0x8,%rsp"),
        ("mov", "0x20(%rsp),%rax"),
        ("mov", "%rax,0x30(%rsp)"),
        ("mov", "0x18(%rsp),%rax"),
        ("mov", "%rax,0x38(%rsp)"),
        ("lea", "0x30(%rsp),%r11"),
        ("lea", "0x90(%rsp),%r10"),
        ("call", entry),
        ("add", "$0x8,%rsp"),
    ]
    expected += [("pop", f"%{reg}") for reg in ("r9", "r8", "rcx", "rdx", "rdi")]
    expected += [
        ("add", "$0xc0,%rsp"),
        ("mov", "$0x1,%eax"),
        ("mov", "$0x1,%esi"),
        ("int", "$0x81"),
        ("ud2", ""),
        ("ud2", ""),
    ]
    need(wrapper == expected, "Exact copied Call wrapper reservations, fixed LEAs, private prefix, restore and marker")
    need(
        rows[0].address == base
        and rows[-1].next == stub.address
        and all(left.next == right.address for left, right in zip(rows, rows[1:]))
        and symbols["aurora_program_return_pc"].address == rows[-2].address
        and symbols["bad_entry"].address == rows[-1].address,
        "Copied Call exact wrapper coverage and terminal PCs",
    )
    need(
        stub.address + stub.size <= min(symbol.address for name, symbol in user.functions.items() if name != host),
        "Copied Call wrapper/stub overlaps generated code",
    )
    result = stack.calculate(functions, entry)
    # local_peak already includes each generated CALL return address. The
    # wrapper adds exactly the upper 192 plus the 48-byte launch envelope.
    result["peak_with_wrapper"] = 240 + result["peak"]
    need(result["peak_with_wrapper"] <= stack.STACK_CAP, "Copied Call full fixed/generated stack reserve")
    result["fixed_regions"] = dict(argument=[-192, -96], result=[-96, -16], sentinel=[-16, 0], envelope=[-240, -192])
    return result


def scratchpad_stack(directory, *, fixture=False):
    import kernel_stack as stack
    from kernel_program_console_admission import (
        SCRATCHPAD_INPUT_BRIDGE,
        SCRATCHPAD_RESPONSE_BRIDGE,
        CONSOLE_OPERATIONS,
        scratchpad_console_evidence,
        check_program_input_wait,
    )

    bridges = (SCRATCHPAD_INPUT_BRIDGE, SCRATCHPAD_RESPONSE_BRIDGE)
    graph = stack.image_stack_graph(
        directory, ("payload", "acpi", "pci", "runtime"), ROOT, protected=True, bridges=bridges
    )
    result = stack.service_discovery_stack(graph)
    result["console"] = scratchpad_console_evidence(directory, graph)
    need(
        set(bridges) <= set(result["normal"]["closure"]),
        "Both scratchpad Console turns must be reachable from the actual kernel entry",
    )
    functions, linked = graph["functions"], graph["linked"]
    forbidden = (
        set(bridges)
        | CONSOLE_OPERATIONS
        | {
            result["console"]["input_entry"],
            result["console"]["response_entry"],
        }
    )
    need(not forbidden.intersection(result["irq_dispatch"]["closure"]), "Scratchpad IRQ acquired Console authority")
    points = {}
    for label in ("uefi_program_poll_begin", "uefi_service_drain_begin"):
        sites = [symbol.address for symbol in linked.symbols if symbol.name == label]
        need(len(sites) == 1, "Exact scratchpad interruptible site " + label)
        owners = [
            name
            for name, symbol in linked.functions.items()
            if symbol.address <= sites[0] < symbol.address + symbol.size
        ]
        need(len(owners) == 1, "Exact scratchpad interruptible owner " + label)
        path = stack.calculate(functions, "uefi_payload_entry", target=owners[0])
        path["irq_fault_peak"] = path["peak"] + result["irq_dispatch"]["peak_with_entry"] + result["fault_reserve"]
        need(path["irq_fault_peak"] <= stack.STACK_CAP, "Scratchpad complete poll/drain/IRQ/fault stack reserve")
        if label == "uefi_program_poll_begin":
            check_program_input_wait(
                functions, owners[0], result["console"]["input_entry"], bridge=SCRATCHPAD_INPUT_BRIDGE
            )
        points[label] = path
    result["interruptible_paths"] = points
    result["user"] = scratchpad_user_stack(directory / "user-clean")
    result["service"] = ram_file_user_stack(directory / "user-bounds", service=True, scratchpad_fixture=fixture)
    (directory / "ram-scratchpad-stack.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        "PASS: copied scratchpad caller, exact Serve variant, Console and full linked kernel/IRQ/drain stack admission"
    )


def ram_file_stack(directory):
    import kernel_stack as stack

    graph = stack.image_stack_graph(directory, ("payload", "acpi", "pci", "runtime"), ROOT, protected=True)
    result = stack.service_discovery_stack(graph)
    linked = graph["linked"]
    site = next(s.address for s in linked.symbols if s.name == "uefi_service_drain_begin")
    owner = next(n for n, s in linked.functions.items() if s.address <= site < s.address + s.size)
    result["drain"] = stack.calculate(graph["functions"], "uefi_payload_entry", target=owner)
    result["drain_irq_fault_peak"] = result["drain"]["peak"] + result["irq_dispatch"]["peak_with_entry"] + 512
    need(result["drain_irq_fault_peak"] <= stack.STACK_CAP, "RAM-file drain interrupt/fault reserve")
    result["user"] = ram_file_user_stack(directory / "user-clean", service=False)
    result["service"] = ram_file_user_stack(directory / "user-bounds", service=True)
    (directory / "ram-file-stack.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: RAM-file linked kernel/IRQ/drain and role-specific user stack admission")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="build/uefi")
    parser.add_argument(
        "--mode",
        default="normal",
        choices=["normal", "resume", "probes"],
    )
    parser.add_argument("--service-budget", action="store_true")
    parser.add_argument("--dispatcher", action="store_true")
    parser.add_argument("--user-budget", action="store_true")
    parser.add_argument("--program-console", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--blocking-call", action="store_true")
    parser.add_argument("--file-call", action="store_true")
    parser.add_argument("--ram-file", action="store_true")
    parser.add_argument("--ram-scratchpad-console", action="store_true")
    parser.add_argument("--ram-scratchpad-stack", action="store_true")
    parser.add_argument("--ram-scratchpad-fixture", action="store_true")
    parser.add_argument("--call-stack", action="store_true")
    parser.add_argument("--ram-file-stack", action="store_true")
    args = parser.parse_args()
    need(sum((args.call_stack, args.ram_file_stack, args.ram_scratchpad_stack)) <= 1, "Select one stack profile")
    need(
        not args.ram_scratchpad_fixture or not (args.call_stack or args.ram_file_stack),
        "Scratchpad fixture cannot select a legacy stack gate",
    )
    if args.ram_scratchpad_stack:
        scratchpad_stack(Path(args.output).resolve(), fixture=args.ram_scratchpad_fixture)
        raise SystemExit(0)
    if args.call_stack:
        call_stack(Path(args.output).resolve())
        raise SystemExit(0)
    if args.ram_file_stack:
        ram_file_stack(Path(args.output).resolve())
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
        args.ram_file,
        args.ram_scratchpad_console,
        args.ram_scratchpad_fixture,
    )
