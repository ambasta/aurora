#!/usr/bin/env python3
"""No-guest adversarial checks for artifact admission and shared stack semantics."""

from pathlib import Path
import importlib.util
import json
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

    instruction = namedtuple("Instruction", "address size op args")

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
        admission.build_files = lambda: [output, callgraph, stack]
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
