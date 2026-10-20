#!/usr/bin/env python3
"""No-guest adversarial checks for artifact admission and shared stack semantics."""

from copy import deepcopy
from pathlib import Path
import importlib.util
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("program_admission", ROOT / "scripts/kernel_program_console_admission.py")
admission = importlib.util.module_from_spec(spec)
spec.loader.exec_module(admission)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def reject(operation, message):
    try:
        operation()
    except (ValueError, OSError, KeyError):
        return
    raise ValueError("Accepted invalid case: " + message)


def body(frame, *calls):
    return dict(local_peak=frame, calls=[dict(target=target, live_bytes=live) for target, live in calls])


def main():
    from collections import namedtuple

    # Renaming emitted symbols leaves source-selected bridges unchanged; absent
    # or ambiguous declarations must never fall back to a mangling recipe.
    sys.path.insert(0, str(ROOT / "scripts"))
    from meson_aurora_assembly import render_bridge

    facts = {"version": 2, "functions": {"compiler_chosen_name": {"source_name": "update_note"}}}
    template = "call @update_note@\n.type bridge,@function\n"
    need(
        render_bridge(template, facts) == "call compiler_chosen_name\n.type bridge,@function\n",
        "Compiler symbol lookup",
    )
    for version in (1, 3):
        need(
            render_bridge(template, dict(facts, version=version)) == render_bridge(template, facts),
            "Supported ABI versions must preserve source-symbol lookup",
        )
    for changed in (
        {"version": 4, "functions": facts["functions"]},
        {"version": True, "functions": facts["functions"]},
        {"version": 1, "functions": {}},
        {"version": 1, "functions": {"wrong": {"source_name": "project_note"}}},
        {
            "version": 1,
            "functions": {"first": {"source_name": "update_note"}, "second": {"source_name": "update_note"}},
        },
        {"version": 1, "functions": {"name\nret": {"source_name": "update_note"}}},
    ):
        reject(lambda changed=changed: render_bridge(template, changed), "Missing/ambiguous/invalid compiler symbol")
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "language.abi.json"
        path.write_text(json.dumps(facts))
        need(admission.source_symbol(path, "update_note") == "compiler_chosen_name", "Admission source identity")
        reject(lambda: admission.source_symbol(path, "missing"), "Missing native source declaration")
        path.write_text('{"version":1,"functions":{},"functions":{}}')
        reject(lambda: admission.source_symbol(path, "update_note"), "Duplicate ABI-fact JSON key")

    instruction = namedtuple("Instruction", "address size op args")

    # The class-returning service uses the existing full ABI, without pretending
    # its capability is an ordinary copied_record or extending stack facts.
    input_abi = {
        "version": 2,
        "records": {
            "buffer_type": dict(
                source_name="std::BinaryBuffer64",
                size=64,
                alignment=1,
                reserved=64,
                fields=[dict(name="elements", offset=0, bytes=64, array_length=64, kind="u8")],
            ),
            "submission_type": dict(
                source_name="console::ProgramSubmission",
                size=88,
                alignment=8,
                reserved=88,
                fields=[
                    dict(name="bytes", offset=0, bytes=64, array_length=0, kind="class", type_name="buffer_type"),
                    dict(name="count", offset=64, bytes=8, array_length=0, kind="i64"),
                    dict(name="action", offset=72, bytes=8, array_length=0, kind="enum", type_name="action_type"),
                    dict(name="after_cr", offset=80, bytes=8, array_length=0, kind="u64"),
                ],
            ),
        },
        "enums": {
            "action_type": dict(
                source_name="console::ProgramInputAction",
                cases=dict(command=0, upper_payload=1, requested_exit=2, output_failure=3),
            ),
        },
        "functions": {
            "selected_reader": dict(
                source_name="read_program_input",
                receiver=None,
                receiver_mutable=None,
                borrowed_roots=[],
                borrowed_root_count=0,
                borrowed_root_abi=dict(
                    kind="none",
                    register=None,
                    tuple_payload_bytes=0,
                    tuple_reserved_bytes=0,
                    saved_root_reserved_bytes=0,
                ),
                parameter_bytes=24,
                parameters=[dict(offset=0, bytes=16, kind="service"), dict(offset=16, bytes=8, kind="bool")],
                result=dict(bytes=88, kind="class", type_name="submission_type"),
            ),
        },
    }
    need(admission.check_program_console_abi(input_abi) == "selected_reader", "Source-selected input ABI")
    for path, value in (
        (("version",), 1),
        (("version",), True),
        (("records", "submission_type", "size"), 80),
        (("records", "submission_type", "reserved"), 96),
        (("records", "submission_type", "fields", 0, "type_name"), "other_buffer"),
        (("records", "submission_type", "fields", 1, "kind"), "u64"),
        (("records", "submission_type", "fields", 2, "offset"), 80),
        (("records", "submission_type", "fields", 2, "type_name"), "other_enum"),
        (("records", "submission_type", "fields", 3, "kind"), "bool"),
        (("records", "buffer_type", "fields", 0, "array_length"), 63),
        (("records", "buffer_type", "fields", 0, "kind"), "service"),
        (("enums", "action_type", "cases", "command"), False),
        (("enums", "action_type", "cases", "output_failure"), 2),
        (("functions", "selected_reader", "parameter_bytes"), 16),
        (("functions", "selected_reader", "parameters", 0, "bytes"), 8),
        (("functions", "selected_reader", "parameters", 0, "kind"), "u64"),
        (("functions", "selected_reader", "parameters", 1, "offset"), 8),
        (("functions", "selected_reader", "parameters", 1, "kind"), "u64"),
        (("functions", "selected_reader", "result", "bytes"), 80),
        (("functions", "selected_reader", "result", "type_name"), "other_result"),
        (("functions", "selected_reader", "borrowed_root_count"), 1),
        (("functions", "selected_reader", "borrowed_root_count"), False),
        (
            ("functions", "selected_reader", "borrowed_roots"),
            [dict(ordinal=0, selector=0, type_name="buffer_type", mutable=False)],
        ),
        (("functions", "selected_reader", "borrowed_root_abi", "tuple_payload_bytes"), 8),
        (("functions", "selected_reader", "borrowed_root_abi", "saved_root_reserved_bytes"), 16),
        (("functions", "selected_reader", "second_receiver"), None),
    ):
        changed = deepcopy(input_abi)
        selected = changed
        for key in path[:-1]:
            selected = selected[key]
        selected[path[-1]] = value
        reject(lambda: admission.check_program_console_abi(changed), "program input full ABI mismatch")

    response_abi = deepcopy(input_abi)
    response_abi["records"]["response_type"] = dict(
        source_name="console::ProgramResponse",
        size=80,
        alignment=8,
        reserved=80,
        fields=[
            dict(name="bytes", offset=0, bytes=64, array_length=0, kind="class", type_name="buffer_type"),
            dict(name="count", offset=64, bytes=8, array_length=0, kind="i64"),
            dict(name="kind", offset=72, bytes=8, array_length=0, kind="enum", type_name="kind_type"),
        ],
    )
    response_abi["enums"]["kind_type"] = dict(
        source_name="console::ProgramResponseKind",
        cases=dict(
            ready=0,
            output=1,
            note_missing=2,
            file_missing=3,
            note_saved=4,
            file_saved=5,
            file_reply=6,
            stopped=7,
            unknown=8,
        ),
    )
    response_abi["functions"]["selected_presenter"] = dict(
        source_name="present_program_response",
        receiver=None,
        receiver_mutable=None,
        borrowed_roots=[],
        borrowed_root_count=0,
        borrowed_root_abi=dict(
            kind="none", register=None, tuple_payload_bytes=0, tuple_reserved_bytes=0, saved_root_reserved_bytes=0
        ),
        parameter_bytes=96,
        parameters=[
            dict(offset=0, bytes=16, kind="service"),
            dict(offset=16, bytes=80, kind="class", type_name="response_type"),
        ],
        result=dict(bytes=8, kind="bool"),
    )
    need(
        admission.check_program_console_abi(response_abi, response=True) == "selected_presenter",
        "Source-selected response ABI",
    )
    for path, value in (
        (("records", "response_type", "size"), 72),
        (("records", "response_type", "alignment"), 1),
        (("records", "response_type", "reserved"), 96),
        (("records", "response_type", "fields", 0, "bytes"), 63),
        (("records", "response_type", "fields", 0, "type_name"), "other_buffer"),
        (("records", "response_type", "fields", 1, "offset"), 72),
        (("records", "response_type", "fields", 1, "kind"), "u64"),
        (("records", "response_type", "fields", 2, "offset"), 64),
        (("records", "response_type", "fields", 2, "type_name"), "action_type"),
        (("records", "buffer_type", "fields", 0, "array_length"), 63),
        (("enums", "kind_type", "cases", "ready"), False),
        (("enums", "kind_type", "cases", "output"), 1.0),
        (("enums", "kind_type", "cases", "unknown"), 9),
        (("enums", "kind_type", "cases", "extra"), 9),
        (("functions", "selected_presenter", "parameter_bytes"), 80),
        (("functions", "selected_presenter", "parameters", 0, "offset"), 80),
        (("functions", "selected_presenter", "parameters", 0, "bytes"), 8),
        (("functions", "selected_presenter", "parameters", 0, "kind"), "u64"),
        (("functions", "selected_presenter", "parameters", 1, "offset"), 0),
        (("functions", "selected_presenter", "parameters", 1, "bytes"), 72),
        (("functions", "selected_presenter", "parameters", 1, "kind"), "service"),
        (("functions", "selected_presenter", "parameters", 1, "type_name"), "submission_type"),
        (("functions", "selected_presenter", "result", "bytes"), 1),
        (("functions", "selected_presenter", "result", "kind"), "u64"),
        (("functions", "selected_presenter", "receiver"), "response_type"),
        (("functions", "selected_presenter", "borrowed_parameter"), True),
        (("functions", "selected_presenter", "borrowed_root_count"), 1),
        (("functions", "selected_presenter", "borrowed_root_abi", "kind"), "direct"),
        (("functions", "selected_presenter", "borrowed_root_abi", "register"), "r10"),
        (("functions", "selected_presenter", "borrowed_root_abi", "tuple_reserved_bytes"), 16),
    ):
        changed = deepcopy(response_abi)
        selected = changed
        for key in path[:-1]:
            selected = selected[key]
        selected[path[-1]] = value
        reject(
            lambda: admission.check_program_console_abi(changed, response=True), "program response full ABI mismatch"
        )

    bridge_name = admission.PROGRAM_INPUT_BRIDGE
    response_bridge = admission.PROGRAM_RESPONSE_BRIDGE
    console_next, console_put = "__au_runtime_console_next", "__au_runtime_console_put"
    input_graph = {
        bridge_name: body(16, ("reader", 16)),
        response_bridge: body(16, ("presenter", 16)),
        "reader": body(16, ("reader_body", 16)),
        "presenter": body(16, ("writer", 16)),
        "reader_body": body(16, (console_next, 16), ("writer", 16), ("__au_reflect_s1_size", 16)),
        "writer": body(16, (console_put, 16)),
        "policy": body(16),
        "__au_reflect_s1_size": body(8),
    }
    input_graph["writer"]["service_abi"] = dict(record=None, calls={console_put: dict(sysv_arguments=3, result_max=1)})
    for function in input_graph.values():
        for index, call in enumerate(function["calls"]):
            call["address"] = index
    public = {bridge_name, response_bridge, "policy", "__au_reflect_s1_size"}
    calls = admission.check_program_console_calls(input_graph, set(input_graph), public, "reader", "presenter")
    need(
        len(calls["reader"]) == 2 and len(calls["presenter"]) == 1,
        "Input and response follow shared helpers but response only reaches Console put",
    )
    for changed in (
        dict(input_graph, policy=body(16, ("writer", 16))),
        dict(input_graph, policy=body(16, ("presenter", 16))),
        dict(input_graph, rogue=body(16, (console_next, 16))),
        dict(input_graph, rogue=body(16, (console_put, 16))),
        dict(input_graph, reader_body=body(16, ("foreign_host", 16))),
        dict(input_graph, presenter=body(16, ("reader", 16))),
        dict(input_graph, presenter=body(16, (console_next, 16), ("writer", 16))),
        dict(input_graph, presenter=body(16, ("foreign_host", 16))),
        dict(input_graph, presenter=body(16)),
        dict(input_graph, writer=body(16, (console_put, 16))),
        dict(
            input_graph, writer=dict(input_graph["writer"], calls=[dict(target=console_put, live_bytes=8, address=0)])
        ),
    ):
        reject(
            lambda: admission.check_program_console_calls(changed, set(changed), public, "reader", "presenter"),
            "Console authority escaped its input/output closure or changed its host operation contract",
        )

    wait_graph = {
        "uefi_payload_entry": body(16, (bridge_name, 16)),
        bridge_name: body(16, ("reader", 16)),
        "reader": body(16, ("helper", 16)),
        "helper": body(16, (console_next, 16)),
        console_next: body(16, ("wait", 16)),
        "wait": body(16),
    }
    admission.check_program_input_wait(wait_graph, "wait", "reader")
    for changed in (
        dict(wait_graph, uefi_payload_entry=body(16, (bridge_name, 16), ("wait", 16))),
        dict(wait_graph, helper=body(16, ("wait", 16))),
        dict(wait_graph, **{bridge_name: body(16, (console_next, 16))}),
        dict(wait_graph, uefi_payload_entry=body(16)),
    ):
        reject(lambda: admission.check_program_input_wait(changed, "wait", "reader"), "retained reader wait bypass")

    closed = {"root": body(16)}
    admission.check_referenced_reflection(closed, {"root"})
    closed = {"root": body(16, ("__au_reflect_s1_size", 16)), "__au_reflect_s1_size": body(8)}
    admission.check_referenced_reflection(closed, set(closed))
    for functions, generated, bridges in (
        (dict(closed, aurora_reflect_field_count=body(8)), set(closed) | {"aurora_reflect_field_count"}, ()),
        (closed, {"__au_reflect_s1_size"}, ()),
        (closed, set(closed), ("root",)),
        ({"root": body(16, ("aurora_reflect_size", 16))}, {"root"}, ()),
        (dict(closed, __au_reflect_invalid=body(8)), set(closed) | {"__au_reflect_invalid"}, ()),
    ):
        reject(
            lambda: admission.check_referenced_reflection(functions, generated, bridges),
            "closed reflection provenance or exact reference inventory",
        )

    # The Call trap remains handwritten: only generated caller code may
    # reference generated reflection helpers, never the trap bridge itself.
    call_stub = "__au_runtime_call"
    helper = "__au_reflect_s1_size"
    caller_graph = {"caller": body(16, (call_stub, 16)), call_stub: body(8)}
    admission.check_referenced_reflection(caller_graph, {"caller"}, {call_stub})
    reflected_caller = dict(caller_graph, caller=body(16, (call_stub, 16), (helper, 16)))
    reflected_caller[helper] = body(8)
    generated = {"caller", helper}
    admission.check_referenced_reflection(reflected_caller, generated, {call_stub})
    for functions, names in (
        (dict(caller_graph, **{helper: body(8)}), generated),
        ({name: value for name, value in reflected_caller.items() if name != helper}, generated),
        (reflected_caller, {"caller"}),
        (dict(reflected_caller, **{call_stub: body(8, (helper, 8))}), generated | {call_stub}),
        (dict(caller_graph, __au_reflect_unknown=body(8)), {"caller", "__au_reflect_unknown"}),
    ):
        reject(
            lambda: admission.check_referenced_reflection(functions, names, {call_stub}),
            "Call caller closed reflection helper provenance and reference set",
        )

    bridge = [
        ("push", "%rbp"),
        ("mov", "%rsp,%rbp"),
        ("mov", "%rdi,%r11"),
        ("mov", "%rsi,%r10"),
        ("call", "private"),
        ("leave", ""),
        ("ret", ""),
    ]
    admission.check_note_bridge(bridge, "private")
    for index, replacement in (
        (2, ("mov", "%rsi,%r11")),
        (3, ("mov", "%rdi,%r10")),
        (4, ("call", "foreign")),
        (5, ("add", "$0x8,%rsp")),
    ):
        changed = list(bridge)
        changed[index] = replacement
        reject(lambda: admission.check_note_bridge(changed, "private"), "copied note bridge binding")

    response_wrapper = [row for row in bridge if row != ("mov", "%rsi,%r10")]
    admission.check_response_bridge(response_wrapper, "private")
    for changed in (
        bridge,
        response_wrapper[:2] + [("mov", "%rsi,%r11")] + response_wrapper[3:],
        response_wrapper[:3] + [("call", "foreign")] + response_wrapper[4:],
        response_wrapper[:-2] + [("xor", "%rax,%rax")] + response_wrapper[-2:],
    ):
        reject(lambda: admission.check_response_bridge(changed, "private"), "response argument/scalar return binding")

    # Native widths and their order are independent of trusted compiler facts.
    copied = dict(parameter_bytes=[272, 64, 8], result_bytes=520)
    admission.check_copied_record(copied, [272, 64, 8], 520)
    for changed in (
        None,  # V1 or unsupported V2 ABI must not admit a native boundary.
        dict(parameter_bytes=[64, 272, 8], result_bytes=520),
        dict(parameter_bytes=[272, 64], result_bytes=520),
        dict(parameter_bytes=[272, 64, 8, 8], result_bytes=520),
        dict(parameter_bytes=[264, 64, 8], result_bytes=520),
        dict(parameter_bytes=[272, 64, 8], result_bytes=512),
        dict(parameter_bytes=[272, 64, 8]),
        dict(copied, extra=True),
    ):
        reject(
            lambda changed=changed: admission.check_copied_record(changed, [272, 64, 8], 520),
            "exact compiler ABI/native boundary mismatch",
        )

    # The copied stream has two 64-byte buffers and eight qwords. Neither the
    # native object identity nor its nonwrapping run generation crosses this ABI.
    stream_parameters = [192, 8, 64, 8, 8]
    stream = dict(parameter_bytes=stream_parameters, result_bytes=280)
    admission.check_copied_record(stream, stream_parameters, 280)
    for changed in (
        None,
        dict(parameter_bytes=[184, 8, 64, 8, 8], result_bytes=280),
        dict(parameter_bytes=[200, 8, 64, 8, 8], result_bytes=280),
        dict(parameter_bytes=[192, 64, 8, 8, 8], result_bytes=280),
        dict(parameter_bytes=[192, 8, 64, 8], result_bytes=280),
        dict(parameter_bytes=[192, 8, 64, 8, 8, 8], result_bytes=280),
        dict(parameter_bytes=stream_parameters, result_bytes=272),
        dict(parameter_bytes=stream_parameters, result_bytes=288),
        dict(stream, extra=True),
    ):
        reject(
            lambda changed=changed: admission.check_copied_record(changed, stream_parameters, 280),
            "exact copied stream boundary mismatch",
        )

    cases = {
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
    typed_stream = {
        "version": 1,
        "enums": {"emitted_operation": dict(source_name="CommandOperation", cases=cases)},
        "functions": {
            "emitted_stream": {
                "source_name": "update_stream",
                "parameters": [
                    dict(offset=0, bytes=192, kind="class", type_name="emitted_stream_class"),
                    dict(offset=192, bytes=8, kind="enum", type_name="emitted_operation"),
                    dict(offset=200, bytes=64, kind="class", type_name="emitted_buffer"),
                    dict(offset=264, bytes=8, kind="u64"),
                    dict(offset=272, bytes=8, kind="u64"),
                ],
            }
        },
    }
    admission.check_stream_operation(typed_stream)
    for replacement in (
        dict(cases, begin=1, begin_read=0),
        {name: value for name, value in cases.items() if name != "finish"},
        dict(cases, extra=11),
        dict(cases, begin=False),
        dict(cases, begin_read=1.0),
    ):
        changed = deepcopy(typed_stream)
        changed["enums"]["emitted_operation"]["cases"] = replacement
        reject(lambda: admission.check_stream_operation(changed), "native stream operation mapping drift")
    for replacement in ({}, dict(typed_stream["enums"], duplicate=typed_stream["enums"]["emitted_operation"])):
        changed = deepcopy(typed_stream)
        changed["enums"] = replacement
        reject(lambda: admission.check_stream_operation(changed), "missing or ambiguous stream enum")
    for field, value in (("kind", "u64"), ("type_name", "foreign_enum"), ("offset", 200), ("bytes", 16)):
        changed = deepcopy(typed_stream)
        changed["functions"]["emitted_stream"]["parameters"][1][field] = value
        reject(lambda: admission.check_stream_operation(changed), "wrong nominal stream operation parameter")

    # Scalar AND semantics and hostile destinations are covered by the shared
    # decoder's self-test, not a program-only compiler-layout normalization.
    decoder = admission.load("program_switch_decoder", ROOT / "scripts/kernel_stack.py")
    # Actual handwritten boundary calls: extra stack reservation or a transfer
    # cannot hide behind the historical count of eleven pushes.
    entry = [decoder.Instruction(i, 1, "push", "%rax") for i in range(6)]
    entry.append(decoder.Instruction(6, 7, "mov", "%rsp,0xf3(%rip)"))
    entry.extend(decoder.Instruction(i, 1, "push", "%rax") for i in range(13, 18))
    entry.append(decoder.Instruction(18, 2, "iretq", ""))
    entry_bytes = b"\x50" * 6 + bytes.fromhex("488925f3000000") + b"\x50" * 5 + b"\x48\xcf"
    need(decoder.protected_entry_peak(entry, entry_bytes, 0x100) == 96, "Protected entry bound")
    for op, args in (("sub", "$0x1000,%rsp"), ("jmp", "b <return>"), ("mov", "%rax,%rsp")):
        changed = entry[:5] + [decoder.Instruction(5, 1, op, args)] + entry[5:]
        reject(
            lambda changed=changed: decoder.protected_entry_peak(changed, entry_bytes, 0x100),
            "unmodeled entry stack/control effect",
        )
    reject(
        lambda: decoder.protected_entry_peak(entry, b"\x66" + entry_bytes[1:], 0x100),
        "16-bit push changes privilege frame",
    )
    reject(
        lambda: decoder.protected_entry_peak(entry[:6] + entry[7:-1] + [entry[6], entry[-1]], entry_bytes, 0x100),
        "saved RSP includes discarded privilege words",
    )
    reject(lambda: decoder.protected_entry_peak(entry, entry_bytes, 0x101), "wrong saved kernel stack storage")

    # Exact deferred restore must retain its fresh kernel anchor and complete
    # register/privilege frame; mutations exercise the existing decoder.
    resume_ops = [("push", "%" + r) for r in "rbx rbp r12 r13 r14 r15".split()]
    resume_ops += [
        ("mov", "%rsp,0xef(%rip)"),
        ("mov", "$0x23,%ax"),
        ("mov", "%eax,%ds"),
        ("mov", "%eax,%es"),
        ("mov", "%rdi,%rsp"),
    ]
    resume_ops += [("pop", "%" + r) for r in "r15 r14 r13 r12 r11 r10 r9 r8 rdi rsi rbp rdx rcx rbx rax".split()]
    resume_ops += [("add", "$0x10,%rsp"), ("iretq", "")]
    resume_bytes = bytes.fromhex("53554154415541564157488925ef000000")
    addresses = (0, 1, 2, 4, 6, 8, 10)
    restore = [
        decoder.Instruction(addresses[i], (1 if i < 2 else 2) if i < 6 else 7, *op)
        if i < 7
        else decoder.Instruction(17 + i - 7, 1, *op)
        for i, op in enumerate(resume_ops)
    ]
    need(decoder.protected_resume_peak(restore, resume_bytes, 0x100) == 56, "Deferred restore bound")
    for index, op, args in (
        (11, "pop", "%r14"),
        (26, "add", "$0x8,%rsp"),
        (27, "ret", ""),
        (6, "mov", "%rsp,0xf0(%rip)"),
    ):
        changed = restore.copy()
        old = changed[index]
        changed[index] = decoder.Instruction(old.address, old.size, op, args)
        reject(lambda: decoder.protected_resume_peak(changed, resume_bytes, 0x100), "changed deferred restore")
    reject(
        lambda: decoder.protected_resume_peak(restore[:11] + restore[12:], resume_bytes, 0x100),
        "missing deferred register",
    )

    # The exception ABI is checked separately from compiler-generated dispatch.
    registers = "rax rbx rcx rdx rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
    irq_ops = [("cld", "")] + [("push", "%" + name) for name in registers]
    irq_ops += [
        ("mov", args)
        for args in (
            "0x78(%rsp),%rdi",
            "0x80(%rsp),%rsi",
            "0x88(%rsp),%rdx",
            "0x90(%rsp),%rcx",
            "%rsp,%r8",
            "0x70(%rsp),%r9",
            "%rsp,%rbx",
        )
    ]
    irq_ops += [
        ("and", "$0xfffffffffffffff0,%rsp"),
        ("call", "100 <dispatch>"),
        ("cmp", "$0x1,%rax"),
        ("je", "200 <leave>"),
        ("mov", "%rbx,%rsp"),
    ]
    irq_ops += [("pop", "%" + name) for name in reversed(registers)] + [("add", "$0x10,%rsp"), ("iretq", "")]
    irq_rows = [decoder.Instruction(index, 1, op, args) for index, (op, args) in enumerate(irq_ops)]
    irq_names = {
        name: decoder.Symbol(name, address, 1, 1, 0)
        for name, address in (("aurora_exception_dispatch", 0x100), ("aurora_leave_user", 0x200))
    }
    irq_bytes = bytes(0x50 if row.op == "push" else 0x90 for row in irq_rows)
    need(
        decoder.protected_irq_frame(irq_rows, irq_names, irq_bytes) == dict(frame_bytes=176, alignment_bytes=15),
        "Protected exception frame",
    )
    for op, args in (("sub", "$0x1000,%rsp"), ("jmp", "100 <dispatch>")):
        changed = irq_rows[:24] + [decoder.Instruction(24, 1, op, args)] + irq_rows[24:]
        reject(
            lambda changed=changed: decoder.protected_irq_frame(changed, irq_names, irq_bytes),
            "unmodeled IRQ stack/control effect",
        )

    leave_ops = [
        ("mov", "$0x10,%ax"),
        ("mov", "%eax,%ds"),
        ("mov", "%eax,%es"),
        ("mov", "%eax,%ss"),
        ("mov", "0x4fb(%rip),%rsp"),
        ("movq", "$0x0,0x4fa(%rip)"),
    ]
    leave_ops += [("pop", "%" + name) for name in ("r15", "r14", "r13", "r12", "rbp", "rbx")]
    leave_ops += [("mov", "$0x1,%eax"), ("ret", "")]
    leave_rows = [decoder.Instruction(index, 1, op, args) for index, (op, args) in enumerate(leave_ops)]
    saved = {"uefi_runtime_saved_rsp": decoder.Symbol("uefi_runtime_saved_rsp", 0x500, 8, 1, 0)}
    decoder.protected_leave(leave_rows, saved)
    for op, args in (("sub", "$0x1000,%rsp"), ("jmp", "d <return>")):
        changed = leave_rows[:6] + [decoder.Instruction(6, 1, op, args)] + leave_rows[6:]
        reject(lambda changed=changed: decoder.protected_leave(changed, saved), "unmodeled resumed kernel-stack effect")

    for base in ("%rsi", "%rdx"):
        switch = [
            instruction(0, 4, "cmp", "$0x5,%rax"),
            instruction(4, 2, "ja", "100 <reject>"),
            instruction(6, 7, "lea", "0x100(%rip)," + base),
            instruction(13, 4, "movslq", f"({base},%rax,4),%rax"),
            instruction(17, 3, "add", base + ",%rax"),
            instruction(20, 2, "jmp", "*%rax"),
        ]
        need(decoder.switch_envelope(switch) == 269, "Register-independent bounded switch table")
        for index, op, operands in (
            (0, "cmp", "$0x100,%rax"),
            (0, "cmp", "$0x5,%eax"),
            (1, "jg", "100 <reject>"),
            (2, "lea", "0x100(%rip),%rax"),
            (2, "lea", "0x100(%rip),%rsp"),
            (3, "movslq", f"({base},%rax,8),%rax"),
            (3, "mov", f"({base},%rax,4),%rax"),
            (4, "add", "%rsp,%rax"),
            (5, "jmp", "*%rdx"),
        ):
            changed = list(switch)
            changed[index] = changed[index]._replace(op=op, args=operands)
            reject(lambda changed=changed: decoder.switch_envelope(changed), "changed bounded switch envelope")
        for insertion in range(1, 6):
            for operands in ("0x8(%rsp),%r8", "0x38(%rsp),%r10", "%r11,%r9"):
                scheduled = list(switch)
                scheduled.insert(insertion, instruction(0, 4, "mov", operands))
                scheduled = [row._replace(address=index * 8) for index, row in enumerate(scheduled)]
                envelope = decoder.switch_window(scheduled)
                table_load = next(row for row in scheduled if row.op == "lea")
                need(envelope["table"] == table_load.address + table_load.size + 256, "Scheduled switch table")
                need(len(envelope["independent"]) == 1, "Scheduled move omitted from evidence")
                decoder.switch_no_bypass(scheduled, envelope["guard"], envelope["jump"], [0, 96])
        for op, operands in (
            ("mov", "$0x1,%r8"),
            ("mov", "%r8,%rax"),
            ("mov", "%r8," + base),
            ("mov", "%r8,%rsp"),
            ("mov", "%r8d,%eax"),
            ("mov", "%r8b,%spl"),
            ("mov", "%r8,0x8(%rsp)"),
            ("mov", "-0x8(%rsp),%r8"),
            ("mov", "%rsp,%r8"),
            ("mov", "(%rdi),%r8"),
            ("xor", "%r8,%r8"),
            ("call", "100 <helper>"),
            ("jmp", "100 <other>"),
        ):
            changed = list(switch)
            changed.insert(3, instruction(0, 4, op, operands))
            changed = [row._replace(address=index * 8) for index, row in enumerate(changed)]
            reject(lambda changed=changed: decoder.switch_window(changed), "unsafe switch interleaving")
        envelope = decoder.switch_window(scheduled)
        guard, jump = envelope["guard"], envelope["jump"]
        for target in (scheduled[1].address, envelope["independent"][0].address, jump.address):
            reject(
                lambda target=target: decoder.switch_no_bypass(scheduled, guard, jump, [target]),
                "jump table enters switch after bound",
            )
            entry = instruction(100, 4, "jmp", f"{target:x} <interior>")
            reject(
                lambda entry=entry: decoder.switch_no_bypass([entry, *scheduled], guard, jump, [96]),
                "direct edge enters switch after bound",
            )
    # Real NVMe lowering: the bounded dword index is explicitly zero-extended
    # before a qword table address. Counts and register choices are not pins.
    for index, narrow, target, count in (("%rcx", "%ecx", "%rax", 5), ("%r8", "%r8d", "%r10", 9)):
        ops = [
            ("cmp", f"$0x{count - 1:x},{narrow}"),
            ("ja", "100 <reject>"),
            ("lea", "0x100(%rip),%rdx"),
            ("mov", f"{narrow},{narrow}"),
            ("movslq", f"(%rdx,{index},4),{target}"),
            ("add", f"%rdx,{target}"),
            ("jmp", "*" + target),
        ]
        rows = [decoder.Instruction(at * 8, 4, op, args) for at, (op, args) in enumerate(ops)]
        need(decoder.switch_window(rows)["entries"] == count, "Bounded table count/register relation")
        reject(lambda: decoder.switch_window(rows[:3] + rows[4:]), "missing switch index zero extension")

    # The immutable mapping boundary is page-aligned beyond the raw file;
    # the complete table itself must exist within both independent bounds.
    from types import SimpleNamespace

    code = [
        decoder.Instruction(address, size, op, args)
        for address, size, op, args in (
            (0, 4, "cmp", "$0x5,%rax"),
            (4, 2, "ja", "70 <reject>"),
            (6, 7, "lea", "0xf3(%rip),%rdx"),
            (13, 4, "movslq", "(%rdx,%rax,4),%rax"),
            (17, 3, "add", "%rdx,%rax"),
            (20, 2, "jmp", "*%rax"),
            (112, 1, "ret", ""),
        )
    ]
    linked = SimpleNamespace(
        functions={"switch": decoder.Symbol("switch", 0, 128, 1, 2)},
        symbols=[
            decoder.Symbol("__payload_text_end", 128, 0, 1, 0),
            decoder.Symbol("__payload_read_end", 4096, 0, 1, 0),
        ],
    )
    raw = bytes(256) + (-144).to_bytes(4, "little", signed=True) * 6
    instructions = {row.address: row for row in code}
    need(
        decoder.bounded_switches(linked, instructions, {"switch": 8}, raw)[1] == {20},
        "Page-aligned immutable boundary incorrectly requires raw padding",
    )
    reject(lambda: decoder.bounded_switches(linked, instructions, {"switch": 8}, raw[:-1]), "truncated switch table")
    for text_end, read_end in ((257, 4096), (128, 279)):
        bad = SimpleNamespace(
            functions=linked.functions,
            symbols=[
                decoder.Symbol("__payload_text_end", text_end, 0, 1, 0),
                decoder.Symbol("__payload_read_end", read_end, 0, 1, 0),
            ],
        )
        reject(
            lambda bad=bad: decoder.bounded_switches(bad, instructions, {"switch": 8}, raw),
            "switch table escapes immutable mapping",
        )

    graph = {
        "root": body(24, ("worker", 24)),
        "worker": body(32, ("leaf", 32)),
        "leaf": body(8),
        "unrelated": body(999999),
    }
    need(admission.graph_peak(graph, "root")["peak"] == 64, "Exact live path sum")
    need(admission.graph_peak(graph, "root", target="worker")["peak"] == 56, "Exact interruptible path")
    reject(lambda: admission.graph_peak(graph, "root", target="unrelated"), "unreachable IRQ target")
    recursive = {"root": body(8, ("walk", 8)), "walk": body(16, ("walk", 16))}
    reject(lambda: admission.graph_peak(recursive, "root"), "unbounded cycle")

    # Snapshot and owned images share the production nonreturn inventory.
    console = admission.load("program_noreturn_controls", ROOT / "scripts/kernel_console_service_admission.py")
    noreturn = admission.stack_facts.OWNED_NORETURN
    stops = {name: dict(calls=[], returns=0) for name in noreturn}
    console.verify_noreturn(stops, noreturn)
    changed = dict(stops)
    changed[next(iter(noreturn))] = dict(calls=[], returns=1)
    reject(lambda: console.verify_noreturn(changed, noreturn), "shared nonreturn function returns")

    # Compiler-to-symbol metadata is mandatory in every hosted UEFI admission
    # inventory, including the loader whose output enters the same boot image.
    for module in (
        admission,
        admission.load("console_inventory", ROOT / "scripts/kernel_console_service_admission.py"),
        admission.load("framebuffer_inventory", ROOT / "scripts/kernel_framebuffer_admission.py"),
    ):
        names = {path.name for path in module.build_files()}
        need(any(name.endswith(".su") for name in names), "Missing stack inventory")
        for name in names:
            if name.endswith(".su"):
                need(name.removesuffix(".su") + ".ci" in names, "Missing mandatory compiler-symbol inventory")

    with tempfile.TemporaryDirectory(prefix="aurora-program-admission-") as directory:
        root = Path(directory)
        output = root / "image.bin"
        output.write_bytes(b"original linked bytes")
        callgraph = root / "runtime.ci"
        callgraph.write_text("original compiler-symbol metadata\n")
        stack = root / "runtime.su"
        stack.write_text("original compiler stack metadata\n")
        admission.ROOT = root
        admission.BUILD = root
        admission.RECEIPT = root / "program-console-admission.json"
        admission.build_files = lambda file_call=False: [output, callgraph, stack]
        receipt = dict(
            schema="aurora-program-console-admission-v1",
            mode="program-console",
            status="requires-independent-review",
            clock="tcg-original-clock",
            sha256=admission.hashes(admission.build_files()),
        )
        admission.RECEIPT.write_text(json.dumps(receipt, sort_keys=True))
        need(admission.checked("program-console") == receipt, "Exact artifact admission")
        reject(lambda: admission.checked("program-pending"), "profile mismatch")
        for changed in (
            dict(receipt, schema="changed"),
            dict(receipt, sha256={}),
            dict(receipt, sha256={**receipt["sha256"], "../escape": "0" * 64}),
            dict(receipt, clock="accelerated"),
            dict(receipt, status="independently-approved"),
        ):
            admission.RECEIPT.write_text(json.dumps(changed, sort_keys=True))
            reject(lambda: admission.checked("program-console"), "incomplete/foreign inventory or false assurance")
        admission.RECEIPT.write_text(json.dumps(receipt, sort_keys=True))
        output.write_bytes(b"changed image")
        reject(lambda: admission.checked("program-console"), "image mutated after admission")
        output.write_bytes(b"original linked bytes")
        callgraph.unlink()
        reject(lambda: admission.checked("program-console"), "missing mandatory compiler-symbol metadata")
        callgraph.write_text("replacement compiler-symbol metadata\n")
        reject(lambda: admission.checked("program-console"), "replaced compiler-symbol metadata")
        stack.write_text("coherently replaced compiler stack metadata\n")
        reject(lambda: admission.checked("program-console"), "coherently replaced metadata pair")
        callgraph.write_text("original compiler-symbol metadata\n")
        stack.write_text("original compiler stack metadata\n")
        need(admission.checked("program-console") == receipt, "Restored exact artifact inventory")
        admission.RECEIPT.unlink()
        before = admission.hashes(admission.build_files())
        output.write_bytes(b"changed during semantic checks")
        reject(
            lambda: admission.write_admission(admission.RECEIPT, dict(receipt), admission.build_files(), before),
            "artifact changed during semantic checks",
        )
        need(not admission.RECEIPT.exists(), "Changed artifact left a successful admission report")
    print("PASS: exact stack/ABI controls and artifact admission mutation rejection")


if __name__ == "__main__":
    main()
