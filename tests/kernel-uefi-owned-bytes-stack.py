#!/usr/bin/env python3
"""Fail-closed linked stack proof for the exclusive kernel owned-byte profile.

No compilation or guest execution is performed. GNU binutils disassemble the
retained ELF; compiler facts bind exact object symbols and direct edges. Only
explicit handwritten assembly has instruction-level stack interpretation.
Page-table traversal uses four local slots; every linked call cycle rejects.
"""

from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

ENTRY = "__au_v_m1_18kernel_owned_bytes_n0__d24kernel_owned_bytes_entry"
CONSUMER = "__au_v_m1_18kernel_owned_bytes_n0__d13consume_bytes"
TRANSFER = "__au_v_m1_18kernel_owned_bytes_n0__d10pass_bytes"
BRIDGE = "__au_runtime_bytes_kernel_entry"
PRODUCER = "__au_v_m1_18kernel_owned_bytes_n0__d14produce_record"
PRODUCER_BRIDGE = "__au_runtime_bytes_kernel_produce"
CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "owned-bytes-runtime", "owned-bytes-profile")
STACK_BYTES = 16384
STACK_CAP = 15360
FAULT_RESERVE = 512
spec = importlib.util.spec_from_file_location("owned_stack_shared", ROOT / "scripts/kernel_stack.py")
stack = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = stack
spec.loader.exec_module(stack)
OWNED_NORETURN = stack.OWNED_NORETURN
require = stack.require
command = stack.command
Instruction = stack.Instruction
normalize_repeat_spelling = stack.normalize_repeat_spelling
disassemble = stack.disassemble
Symbol = stack.Symbol
Elf = stack.Elf
associate_object = stack.associate_object
stack_rows = stack.stack_rows
callgraph_frames = stack.callgraph_frames
source_frame_symbol = stack.source_frame_symbol
cpp_frames = stack.cpp_frames
target_of = stack.target_of
analyze_function = stack.analyze_function
compiled_stack_functions = stack.compiled_stack_functions
assembly_stack_functions = stack.assembly_stack_functions
calculate = stack.calculate
private_frame_layout = stack.private_frame_layout
spec = importlib.util.spec_from_file_location("owned_copy_abi", ROOT / "scripts/kernel_snapshot_abi.py")
copy_abi = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = copy_abi
spec.loader.exec_module(copy_abi)


def producer_source_contract(source):
    source = re.sub(r"//[^\n]*|/\*.*?\*/", "", source, flags=re.S)
    compact = re.sub(r"\s+", "", source)
    declaration = (
        "class ProducedRecord { storage::SectorIoStatus outcome; std::BinaryBuffer64 payload; public: "
        "ProducedRecord(storage::SectorIoStatus status, std::BinaryBuffer64 record) "
        ": outcome(status), payload(record) {} };"
    )
    require(compact.count(re.sub(r"\s+", "", declaration)) == 1, "Changed copied producer class/layout")
    signature = "auto produce_record(builtin::ByteRegion region, i64 selector) -> ProducedRecord {"
    require(compact.count(re.sub(r"\s+", "", signature)) == 1, "Changed copied producer signature")
    return {"input_bytes": 16, "result_bytes": 72, "status_offset": 0, "payload_offset": 8, "payload_bytes": 64}


def generated_producer(body, linked, local_bytes, prefix, constructor):
    """Check this one copied boundary, retaining the ordinary stack/edge proof.

    The native caller supplies fresh output storage. The exact bridge keeps it
    separate from its own input record; the generated producer uses six fresh
    frame results and saves the two hidden addresses outside source storage.
    This is not a general pointer-provenance or compiler-verification framework.
    """
    require(len(body) == len(linked), "Copied boundary source/link instruction inventory mismatch")
    decoded = [(row.op, row.args) for row in linked]

    def moves(position, pairs):
        # Only exact MOVQ pairs at the named boundary are normalized. There is
        # no admission of other operands, instruction forms or arbitrary code.
        source = [f"movq {left}, {right}" for left, right in pairs]

        def operand(value):
            return re.sub(r"(-?)([0-9]+)(?=\(%r)", lambda m: "" if int(m[2]) == 0 else m[1] + hex(int(m[2])), value)

        expected = [("mov", operand(left) + "," + operand(right)) for left, right in pairs]
        require(body[position : position + len(pairs)] == source, "Changed copied boundary source moves")
        require(decoded[position : position + len(pairs)] == expected, "Changed copied boundary linked moves")

    def copied(position, source_base, source_offset, destination_base, destination_offset, extent):
        layout = (source_base, source_offset, destination_base, destination_offset, extent)
        expected = copy_abi.copied_payload(*layout)
        source = copy_abi.copied_payload(*layout, assembly=True)
        require(body[position : position + len(source)] == source, "Changed copied boundary source payload")
        require(decoded[position : position + len(expected)] == expected, "Changed copied boundary linked payload")
        return position + len(expected)

    if constructor:
        require(local_bytes == 96, "Changed copied result constructor frame")
        pairs = [
            ("%r10", "-88(%rbp)"),
            ("%r11", "-96(%rbp)"),
            ("-96(%rbp)", "%r11"),
            ("0(%r11)", "%rax"),
            ("%rax", "-8(%rbp)"),
            ("-96(%rbp)", "%r11"),
        ]
        moves(prefix, pairs)
        end = copied(prefix + len(pairs), "r11", 8, "rbp", -72, 64)
        pairs = [("-8(%rbp)", "%rax"), ("-88(%rbp)", "%r10"), ("%rax", "0(%r10)"), ("-88(%rbp)", "%r10")]
        moves(end, pairs)
        end = copied(end + len(pairs), "rbp", -72, "r10", 8, 64)
        require(
            len(body) == end + 4
            and body[end] == "movabsq $0, %rax"
            and decoded[end] == ("movabs", "$0x0,%rax")
            and body[end + 1].startswith("jmp .Lreturn")
            and linked[end + 1].op == "jmp"
            and target_of(linked[end + 1]) == linked[-2].address,
            "Changed copied result constructor completion",
        )
        return {"result_bytes": 72, "status_offset": 0, "payload_offset": 8}

    input_save, output_save = f"-{local_bytes - 8}(%rbp)", f"-{local_bytes}(%rbp)"
    moves(
        prefix,
        [
            ("%r11", input_save),
            ("%r10", output_save),
            (input_save, "%r11"),
            ("(%r11)", "%rax"),
            ("%rax", "-8(%rbp)"),
            (input_save, "%r11"),
            ("8(%r11)", "%rax"),
            ("%rax", "-16(%rbp)"),
        ],
    )
    allocation = prefix + 8
    require(
        body[allocation : allocation + 9]
        == [
            "movabsq $512, %rax",
            *[f"movq $0, -{offset}(%rbp)" for offset in (48, 40, 32, 24)],
            "movq %rax, %rsi",
            "movq -8(%rbp), %rdi",
            "leaq -48(%rbp), %rdx",
            "call __au_runtime_bytes_allocate",
        ]
        and decoded[allocation : allocation + 8]
        == [
            ("movabs", "$0x200,%rax"),
            *[("movq", f"$0x0,-0x{offset:x}(%rbp)") for offset in (48, 40, 32, 24)],
            ("mov", "%rax,%rsi"),
            ("mov", "-0x8(%rbp),%rdi"),
            ("lea", "-0x30(%rbp),%rdx"),
        ]
        and body.count("call __au_runtime_bytes_allocate") == 1,
        "Copied producer must allocate exactly one 512-byte owner",
    )
    ctor = load_admission().GENERATED["ProducedRecord.new"]
    calls = [index for index, line in enumerate(body) if line == "call " + ctor]
    returns = [index for index, line in enumerate(body) if line == f"movq {output_save}, %r10"]
    require(len(calls) == len(returns) == 6, "Changed copied producer result-path count")
    slots, result_accesses = [], {prefix + 1}
    for call, returned in zip(calls, returns):
        match = re.fullmatch(r"leaq -([0-9]+)\(%rbp\), %r10", body[call - 1])
        require(match and call < returned, "Missing fresh copied result constructor destination")
        slot = int(match[1])
        require(
            72 <= slot <= local_bytes - 16
            and body[call - 2] == "movq %rsp, %r11"
            and decoded[call - 2 : call] == [("mov", "%rsp,%r11"), ("lea", f"-0x{slot:x}(%rbp),%r10")],
            "Copied result aliases hidden saves or outgoing argument storage",
        )
        slots.append((slot - 72, slot))
        cleanup = ["addq $80, %rsp"]
        linked_cleanup = [("add", "$0x50,%rsp")]
        for owner in (120, 48):
            cleanup += [
                "pushq %rax",
                f"leaq -{owner}(%rbp), %rdi",
                "subq $8, %rsp",
                "call __au_runtime_bytes_drop",
                "addq $8, %rsp",
                "popq %rax",
            ]
            linked_cleanup += [
                ("push", "%rax"),
                ("lea", f"-0x{owner:x}(%rbp),%rdi"),
                ("sub", "$0x8,%rsp"),
                ("call", decoded[call + len(linked_cleanup) + 4][1]),
                ("add", "$0x8,%rsp"),
                ("pop", "%rax"),
            ]
        require(body[call + 1 : returned] == cleanup, "Copied result published before complete owner cleanup")
        require(decoded[call + 1 : returned] == linked_cleanup, "Linked copied result cleanup changed")
        moves(returned, [(output_save, "%r10")])
        end = copied(returned + 1, "rbp", -slot, "r10", 0, 72)
        require(
            body[end] == "xorq %rax, %rax"
            and decoded[end] == ("xor", "%rax,%rax")
            and body[end + 1].startswith("jmp .Lreturn")
            and linked[end + 1].op == "jmp"
            and target_of(linked[end + 1]) == linked[-2].address,
            "Copied result has an incomplete or redirected return",
        )
        result_accesses.add(returned)
    require(all(left[1] <= right[0] for left, right in zip(sorted(slots), sorted(slots)[1:])), "Copied results overlap")
    require(
        {index for index, line in enumerate(body) if output_save in line} == result_accesses
        and sum("(%r10)" in line for line in body) == 6
        and sum(line.startswith("jmp .Lreturn") for line in body) == 6,
        "Copied output address escaped or gained an unaccounted access/return",
    )
    return {"input_bytes": 16, "result_bytes": 72, "fresh_result_slots": slots, "return_paths": 6}


def copied_producer_evidence(source, functions, symbols, instructions):
    """Retain only the native copied-return ABI, not generated stack replay."""
    admission = load_admission()
    evidence = {}
    for name in (PRODUCER, admission.GENERATED["ProducedRecord.new"]):
        begin = source.index(name + ":\n") + len(name) + 2
        body = [
            line.strip()
            for line in source[begin : source.index(".size " + name, begin)].splitlines()
            if line.strip() and not line.strip().startswith(".") and not line.strip().endswith(":")
        ]
        symbol = symbols[name]
        rows = [
            row
            for address, row in sorted(instructions.items())
            if symbol.address <= address < symbol.address + symbol.size
        ]
        local, prefix = private_frame_layout(body, rows)
        evidence[name] = generated_producer(body, rows, local, prefix, name != PRODUCER)
    return evidence


def validate_bridge(symbols, instructions, functions, copied=False):
    name, target, allocation = (PRODUCER_BRIDGE, PRODUCER, 16) if copied else (BRIDGE, ENTRY, 32)
    expected = [
        ("push", "%rbp"),
        ("mov", "%rsp,%rbp"),
        ("sub", f"$0x{allocation:x},%rsp"),
        ("mov", "%rdi,(%rsp)"),
        ("mov", "%rsi,0x8(%rsp)"),
    ]
    expected += [("mov", "%rdx,%r10")] if copied else [("mov", "%rdx,0x10(%rsp)"), ("movq", "$0x0,0x18(%rsp)")]
    expected += [
        ("mov", "%rsp,%r11"),
        ("call", target),
        ("leave", ""),
        ("ret", ""),
    ]
    symbol = symbols[name]
    actual = []
    for address in sorted(instructions):
        if symbol.address <= address < symbol.address + symbol.size:
            insn = instructions[address]
            operand = target if insn.op == "call" and target_of(insn) == symbols[target].address else insn.args
            actual.append((insn.op, operand))
    require(actual == expected, "Private bridge instruction/frame/callee profile changed")
    require(functions[name]["local_peak"] == allocation + 16, "Wrong bridge stack extent")
    return {
        "frame_allocation": allocation,
        "saved_rbp_and_return": 16,
        "local_peak": allocation + 16,
        "calls": functions[name]["calls"],
    }


def load_admission():
    spec = importlib.util.spec_from_file_location(
        "owned_byte_admission", ROOT / "scripts/kernel_owned_bytes_admission.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(directory):
    global NORETURN
    elf = Elf(directory / "payload.elf")
    require(elf.type == 2, "Expected linked executable payload")
    require(not command("nm", "-u", str(directory / "payload.elf")).strip(), "Unresolved linked payload symbol")
    admission = load_admission().validate_symbols(command("nm", "-a", str(directory / "objects" / "language.o")))
    instructions, disassembly = disassemble(directory / "payload.elf")
    starts = {symbol.address: name for name, symbol in elf.functions.items()}
    require(len(starts) == len(elf.functions), "Ambiguous linked function aliases")
    compiler_edges = set()
    frames, associations = cpp_frames(directory, elf, edges=compiler_edges)
    diagnostic = source_frame_symbol(
        associations, "payload.o", "kernel/uefi/payload.cpp", "void {anonymous}::fail(std::string_view)"
    )
    NORETURN = OWNED_NORETURN | {diagnostic}
    stack.NORETURN = NORETURN
    language = Elf(directory / "objects" / "language.o")
    for symbol in language.functions.values():
        associate_object(elf, language, symbol)
    memory = Elf(directory / "objects" / "memory.o")
    for symbol in memory.functions.values():
        associate_object(elf, memory, symbol)
    fixed = {"uefi_payload_entry", "uefi_payload_fault", "uefi_payload_page_fault", "fault_common"}
    require(
        set(elf.functions) == set(frames) | set(language.functions) | set(memory.functions) | fixed,
        "Unaccounted linked function/frame",
    )
    functions = compiled_stack_functions(
        directory, elf, language, instructions, starts, frames, compiler_edges, (BRIDGE, PRODUCER_BRIDGE)
    )
    handwritten = set(memory.functions) | {
        BRIDGE,
        PRODUCER_BRIDGE,
        "uefi_payload_entry",
        "uefi_payload_fault",
        "uefi_payload_page_fault",
        "fault_common",
    }
    functions.update(assembly_stack_functions(elf.functions, instructions, starts, handwritten))
    returning = {name for name, body in functions.items() if body["returns"]}
    while True:
        enlarged = returning | {
            name
            for name, body in functions.items()
            if any(row["kind"] == "tail" and row["target"] in returning for row in body["calls"])
        }
        if enlarged == returning:
            break
        returning = enlarged
    require(NORETURN <= functions.keys() and not NORETURN & returning, "Changed non-returning diagnostic")
    bridge = validate_bridge(elf.functions, instructions, functions)
    producer_bridge = validate_bridge(elf.functions, instructions, functions, copied=True)
    producer_source = ROOT / "examples/kernel-owned-bytes.au"
    producer_contract = producer_source_contract(producer_source.read_text())
    producer_contract["source_sha256"] = hashlib.sha256(producer_source.read_bytes()).hexdigest()
    generated = copied_producer_evidence((directory / "language.s").read_text(), functions, elf.functions, instructions)
    normal = calculate(functions, "uefi_payload_entry")
    # Evaluate every linked function as well: dormant text may not hide unknown
    # call cycles, indirect transfers, or an unsupported recursion entry.
    for name in functions:
        calculate(functions, name)
    required = {
        "uefi_payload_main",
        BRIDGE,
        PRODUCER_BRIDGE,
        PRODUCER,
        ENTRY,
        TRANSFER,
        CONSUMER,
        *load_admission().RUNTIME,
        *(
            load_admission().GENERATED[name]
            for name in (
                "record",
                "ProducedRecord.new",
                "check_ram_sectors",
                "RamSectorDevice.new",
                "RamSectorDevice.read_sector",
                "RamSectorDevice.write_sector",
                "RamSectorDevice.make_read_only",
                "RamSectorDevice.flush",
                "Sector512.read_record",
                "Sector512.write_record",
                "SectorReadResult.sector_or_zero",
                "read_be32",
                "read_le64",
                "encode_be32",
                "encode_le64",
            )
        ),
        "_ZN6aurora4uefi15run_owned_bytesEmRNS_6memory13PhysicalPagesE",
    }
    require(required <= set(normal["closure"]), "Dedicated owned-byte call chain is missing")
    require(
        not any(
            "discover_acpi" in name or "discover_pci" in name or "run_protected" in name for name in normal["closure"]
        ),
        "Non-owned-byte workload reachable in dedicated profile",
    )
    faults = [calculate(functions, name) for name in ("uefi_payload_fault", "uefi_payload_page_fault")]
    fault_peak = 48 + max(item["peak"] for item in faults)  # CPU frame including possible error code.
    require(fault_peak <= FAULT_RESERVE, "Synchronous fault path exceeds its exact 512-byte reserve")
    peak = normal["peak"] + FAULT_RESERVE
    require(peak <= STACK_CAP, "Unchanged 16 KiB stack admission cap exceeded")
    files = ["payload.elf", "language.s", "language.stack.json", "language.o", "memory.o", "payload-entry.o"]
    files += [name + suffix for name in CPP_OBJECTS for suffix in (".o", ".su", ".ci")]
    files = ["objects/" + name if name.endswith((".o", ".su", ".ci")) else name for name in files]
    return {
        "schema": 1,
        "stack_bytes": STACK_BYTES,
        "cap_bytes": STACK_CAP,
        "normal_peak": normal["peak"],
        "peak_with_fault_reserve": peak,
        "fault_reserve": FAULT_RESERVE,
        "decoded_fault_peak": fault_peak,
        "minimum_unused": STACK_BYTES - peak,
        "maximum_path": normal["path"],
        "reachable_functions": normal["closure"],
        "compiler_frames": associations,
        "linked_functions": functions,
        "generated": generated,
        "bridge": bridge,
        "producer_bridge": producer_bridge,
        "producer_contract": producer_contract,
        "verifier": {"traversal_slots": 4, "recursion": "rejected"},
        "object_admission": admission,
        "sha256": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in files},
        "disassembly_sha256": hashlib.sha256(disassembly.encode()).hexdigest(),
    }


def self_test():
    """Synthetic instruction/graph mutations; no compiler or guest is launched."""
    from copy import deepcopy

    positives = 0
    rejected = 0

    def rejects(label, action):
        nonlocal rejected
        try:
            action()
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError("Stack proof accepted mutant: " + label)

    def fixture(specification):
        starts = {100 * index: name for index, name in enumerate(specification)}
        addresses = {name: address for address, name in starts.items()}
        symbols, code = {}, {}
        for name, rows in specification.items():
            base = addresses[name]
            symbols[name] = Symbol(name, base, len(rows), 1, 2)
            for index, (op, operands) in enumerate(rows):
                if operands.startswith("@"):
                    target, _, offset = operands[1:].partition("+")
                    address = addresses[target] + int(offset or 0)
                    operands = f"{address:x} <{target}>"
                code[base + index] = Instruction(base + index, 1, op, operands)
        bodies = {name: analyze_function(symbol, code, starts) for name, symbol in symbols.items()}
        return bodies, symbols, code, starts

    bridge_rows = [
        ("push", "%rbp"),
        ("mov", "%rsp,%rbp"),
        ("sub", "$0x10,%rsp"),
        ("mov", "%rdi,(%rsp)"),
        ("mov", "%rsi,0x8(%rsp)"),
        ("mov", "%rdx,%r10"),
        ("mov", "%rsp,%r11"),
        ("call", "@" + PRODUCER),
        ("leave", ""),
        ("ret", ""),
    ]
    bodies, symbols, code, _ = fixture({PRODUCER_BRIDGE: bridge_rows, PRODUCER: [("ret", "")]})
    validate_bridge(symbols, code, bodies, copied=True)
    positives += 1
    for index, changed in (
        (2, ("sub", "$0x20,%rsp")),
        (3, ("mov", "%rsi,(%rsp)")),
        (4, ("mov", "%rsi,0x10(%rsp)")),
        (5, ("mov", "%rsp,%r10")),
        (5, ("mov", "%rdx,%r11")),
        (6, ("mov", "%r10,%r11")),
        (7, ("call", "0 <wrong>")),
    ):
        changed_code = dict(code)
        changed_code[index] = Instruction(index, 1, *changed)
        rejects("copied bridge operand/extent/alias", lambda c=changed_code: validate_bridge(symbols, c, bodies, True))
    changed_bodies = deepcopy(bodies)
    changed_bodies[PRODUCER_BRIDGE]["local_peak"] = 24
    rejects("copied bridge stack bound", lambda: validate_bridge(symbols, code, changed_bodies, True))

    source = (
        "class ProducedRecord { storage::SectorIoStatus outcome; std::BinaryBuffer64 payload; public: "
        "ProducedRecord(storage::SectorIoStatus status, std::BinaryBuffer64 record) "
        ": outcome(status), payload(record) {} }; "
        "auto produce_record(builtin::ByteRegion region, i64 selector) -> ProducedRecord {}"
    )
    producer_source_contract(source)
    positives += 1
    for old, new in (
        ("SectorIoStatus outcome", "i64 outcome"),
        ("BinaryBuffer64 payload", "Sector512 payload"),
        ("payload(record)", "payload()"),
        ("ByteRegion region, i64 selector", "i64 selector, ByteRegion region"),
        ("-> ProducedRecord", "-> i64"),
    ):
        rejects(
            "copied source signature/layout",
            lambda old=old, new=new: producer_source_contract(source.replace(old, new)),
        )

    def copy_fixture(source, destination, extent):
        # Independent fixed source form; production checks use the shared helper.
        return [
            "pushq %rsi",
            "pushq %rdi",
            "pushq %rcx",
            f"leaq {source}, %rsi",
            f"leaq {destination}, %rdi",
            f"movq ${extent}, %rcx",
            "cld",
            "rep movsb",
            "popq %rcx",
            "popq %rdi",
            "popq %rsi",
        ]

    # Small handwritten boundary fixture, independent of compiler execution.
    body = [
        "movq %r11, -632(%rbp)",
        "movq %r10, -640(%rbp)",
        "movq -632(%rbp), %r11",
        "movq (%r11), %rax",
        "movq %rax, -8(%rbp)",
        "movq -632(%rbp), %r11",
        "movq 8(%r11), %rax",
        "movq %rax, -16(%rbp)",
        "movabsq $512, %rax",
        *[f"movq $0, -{offset}(%rbp)" for offset in (48, 40, 32, 24)],
        "movq %rax, %rsi",
        "movq -8(%rbp), %rdi",
        "leaq -48(%rbp), %rdx",
        "call __au_runtime_bytes_allocate",
    ]
    for slot in (192, 264, 336, 408, 480, 552):
        body += [
            "movq %rsp, %r11",
            f"leaq -{slot}(%rbp), %r10",
            "call " + load_admission().GENERATED["ProducedRecord.new"],
        ]
        body += ["addq $80, %rsp"]
        for owner in (120, 48):
            body += [
                "pushq %rax",
                f"leaq -{owner}(%rbp), %rdi",
                "subq $8, %rsp",
                "call __au_runtime_bytes_drop",
                "addq $8, %rsp",
                "popq %rax",
            ]
        body += ["movq -640(%rbp), %r10"]
        body += copy_fixture(f"-{slot}(%rbp)", "0(%r10)", 72)
        body += ["xorq %rax, %rax", "jmp .Lreturn0"]
    body += ["leave", "ret"]

    def boundary_rows(lines):
        rows = []
        for index, line in enumerate(lines):
            op, _, args = line.partition(" ")
            args = args.replace(" ", "")
            args = re.sub(r"-?\d+", lambda match: ("-" if int(match[0]) < 0 else "") + hex(abs(int(match[0]))), args)
            # Register names contain digits; only memory offsets/immediates
            # need hex spelling in this synthetic GNU-disassembly fixture.
            args = re.sub(r"%r0x([0-9a-f]+)", lambda match: "%r" + str(int(match[1], 16)), args)
            args = args.replace("0x0(%", "(%")
            op = {
                "movabsq": "movabs",
                "leaq": "lea",
                "subq": "sub",
                "addq": "add",
                "pushq": "push",
                "popq": "pop",
                "xorq": "xor",
                "movq": "movq" if args.startswith("$") and args.endswith(")") else "mov",
            }.get(op, op)
            if op == "rep" and args == "movsb":
                args = "movsb %ds:(%rsi),%es:(%rdi)"
            if op == "jmp":
                args = f"{len(lines) - 2:x} <return>"
            rows.append(Instruction(index, 1, op, args))
        return rows

    linked = boundary_rows(body)
    generated_producer(body, linked, 640, 0, False)
    positives += 1
    for old, new in (
        ("movq %r10, -640(%rbp)", "movq %r10, -632(%rbp)"),
        ("movq 8(%r11), %rax", "movq 16(%r11), %rax"),
        ("movabsq $512, %rax", "movabsq $513, %rax"),
        ("leaq -192(%rbp), %r10", "leaq -640(%rbp), %r10"),
        ("leaq -264(%rbp), %r10", "leaq -192(%rbp), %r10"),
        ("leaq -120(%rbp), %rdi", "leaq -48(%rbp), %rdi"),
        ("leaq 0(%r10), %rdi", "leaq 8(%r10), %rdi"),
        ("leaq -192(%rbp), %rsi", "leaq -200(%rbp), %rsi"),
        ("movq $72, %rcx", "movq $71, %rcx"),
        ("movq $72, %rcx", "movq $80, %rcx"),
        ("cld", "std"),
        ("rep movsb", "rep movsq"),
        ("pushq %rsi", "pushq %rax"),
        ("popq %rdi", "popq %rsi"),
    ):
        changed = list(body)
        changed[changed.index(old)] = new
        rejects("copied source boundary mutation", lambda b=changed: generated_producer(b, linked, 640, 0, False))
        changed_linked = boundary_rows(changed)
        rejects("copied linked boundary mutation", lambda c=changed_linked: generated_producer(body, c, 640, 0, False))
        rejects(
            "matched copied boundary mutation",
            lambda b=changed, c=changed_linked: generated_producer(b, c, 640, 0, False),
        )

    ctor = [
        "movq %r10, -88(%rbp)",
        "movq %r11, -96(%rbp)",
        "movq -96(%rbp), %r11",
        "movq 0(%r11), %rax",
        "movq %rax, -8(%rbp)",
        "movq -96(%rbp), %r11",
    ]
    ctor += copy_fixture("8(%r11)", "-72(%rbp)", 64)
    ctor += ["movq -8(%rbp), %rax", "movq -88(%rbp), %r10", "movq %rax, 0(%r10)", "movq -88(%rbp), %r10"]
    ctor += copy_fixture("-72(%rbp)", "8(%r10)", 64)
    ctor += ["movabsq $0, %rax", "jmp .Lreturn0", "leave", "ret"]
    ctor_linked = boundary_rows(ctor)
    generated_producer(ctor, ctor_linked, 96, 0, True)
    positives += 1
    for old, new in (
        ("movq %r11, -96(%rbp)", "movq %r11, -88(%rbp)"),
        ("leaq 8(%r11), %rsi", "leaq 16(%r11), %rsi"),
        ("movq %rax, 0(%r10)", "movq %rax, 8(%r10)"),
        ("leaq 8(%r10), %rdi", "leaq 16(%r10), %rdi"),
        ("movq $64, %rcx", "movq $63, %rcx"),
        ("popq %rcx", "popq %rax"),
    ):
        changed = [new if line == old else line for line in ctor]
        changed_linked = boundary_rows(changed)
        rejects("copied ctor source layout", lambda b=changed: generated_producer(b, ctor_linked, 96, 0, True))
        rejects("copied ctor linked layout", lambda c=changed_linked: generated_producer(ctor, c, 96, 0, True))
        rejects("matched copied ctor layout", lambda b=changed, c=changed_linked: generated_producer(b, c, 96, 0, True))

    for original, frame, constructor in ((body, 640, False), (ctor, 96, True)):
        for instruction in ("pushq %rsi", "cld", "rep movsb", "popq %rsi"):
            index = original.index(instruction)
            for changed in (
                original[:index] + original[index + 1 :],
                original[:index] + [instruction] + original[index:],
            ):
                rows = boundary_rows(changed)
                rejects(
                    "coherent copied sequence omission/duplication",
                    lambda b=changed, c=rows, f=frame, k=constructor: generated_producer(b, c, f, 0, k),
                )

    leaf = [("ret", "")]
    root = [
        ("push", "%rbp"),
        ("mov", "%rsp,%rbp"),
        ("sub", "$0x20,%rsp"),
        ("push", "%rax"),
        ("pop", "%rax"),
        ("call", "@leaf"),
        ("leave", ""),
        ("ret", ""),
    ]
    bodies, symbols, code, starts = fixture({"root": root, "leaf": leaf})
    require(calculate(bodies, "root")["peak"] == 56, "Wrong handwritten bridge stack sum")
    positives += 1
    for index, op, operands in [
        (5, "call", "*%rax"),
        (5, "call", "1 <root+1>"),
        (4, "jmp", "3 <root+3>"),
        (2, "sub", "%rax,%rsp"),
        (2, "sub", "$0x1,%rsp"),
        (3, "push", "%ax"),
        (4, "pop", "%bp"),
        (3, "enter", "$0x20,$0"),
        (6, "nop", ""),
    ]:
        mutant = dict(code)
        mutant[index] = Instruction(index, 1, op, operands)
        rejects("unsupported handwritten stack effect", lambda: analyze_function(symbols["root"], mutant, starts))
    for graph in [
        {"root": [("call", "@root"), ("ret", "")]},
        {"root": [("call", "@leaf"), ("ret", "")], "leaf": [("jmp", "@root")]},
    ]:
        mutant, *_ = fixture(graph)
        rejects("call cycle", lambda: calculate(mutant, "root"))
    unknown = deepcopy(bodies)
    unknown["root"]["calls"][0]["target"] = "missing"
    rejects("unassociated helper", lambda: calculate(unknown, "root"))

    stack_row = "source.cpp:1:1:void function()\t16\tstatic"
    record = next(iter(stack_rows(stack_row).values()))
    require(record.size == 16 and record.location == "source.cpp:1:1", "Compiler record association failed")
    positives += 1
    for mutant in (
        stack_row.replace("static", "dynamic"),
        stack_row.replace("static", "dynamic,bounded"),
        stack_row.replace("16", "-1"),
        stack_row.replace("16", "0"),
        stack_row.replace("16", "32768"),
        stack_row + "\n" + stack_row,
        "malformed",
        stack_row.replace("source.cpp:1:1:", ""),
        stack_row.replace("source.cpp:1:1:", "source.cpp:0:1:"),
    ):
        rejects("compiler record mutation", lambda mutant=mutant: stack_rows(mutant))

    for raw, spelling, canonical in (
        (b"\xf3\xa4", "movsb (%rsi),(%rdi)", "movsb %ds:(%rsi),%es:(%rdi)"),
        (b"\xf3\xaa", "stos %al,(%rdi)", "stos %al,%es:(%rdi)"),
    ):
        require(normalize_repeat_spelling(raw, spelling) == canonical, "Implicit-segment spelling mismatch")
        positives += 1
        for changed in (b"\x67" + raw, b"\x64" + raw, b"\x48" + raw, raw + b"\x90", b"\xf3\xa5"):
            rejects(
                "changed repeat opcode/width",
                lambda changed=changed, spelling=spelling: normalize_repeat_spelling(changed, spelling),
            )
    source_record = {
        "object": "payload.o",
        "source": "kernel/uefi/payload.cpp",
        "record": "void {anonymous}::fail(std::string_view)",
    }
    identity = {"gcc_mangled_symbol": [source_record]}
    require(
        source_frame_symbol(identity, "payload.o", source_record["source"], source_record["record"])
        == "gcc_mangled_symbol",
        "Source-bound helper identity lost",
    )
    positives += 1
    for changed in (
        {},
        {"first": [source_record], "second": [source_record]},
        {"other": [dict(source_record, object="runtime.o")]},
        {"other": [dict(source_record, source="kernel/other.cpp")]},
    ):
        rejects(
            "missing or ambiguous source-bound helper",
            lambda changed=changed: source_frame_symbol(
                changed, "payload.o", source_record["source"], source_record["record"]
            ),
        )

    def graph_node(symbol, location, signature, size=16, kind="static"):
        label = f"{signature}\n{location}\n{size} bytes ({kind})"
        return "node: { title: " + json.dumps(symbol) + " label: " + json.dumps(label) + " }"

    def graph(*nodes, source="source.cpp"):
        return "\n".join(["graph: { title: " + json.dumps(source), *nodes, "}"])

    retired = graph_node("source.cpp:_ZL6retirej.constprop.0", "source.cpp:191:20", "0(unsigned int)")
    created = graph_node("source.cpp:_ZL6createj.constprop.0", "source.cpp:221:20", "0(unsigned int)")
    # Equal-sized, identically printed clones remain distinct through exact
    # source locations and assembler symbols; reversing node order is harmless.
    clone_rows = stack_rows(
        "source.cpp:191:20:0(unsigned int)\t16\tstatic\nsource.cpp:221:20:0(unsigned int)\t16\tstatic"
    )
    clone_symbols = {"_ZL6retirej.constprop.0", "_ZL6createj.constprop.0"}
    # Compiler-introduced libcalls have no source label; linked decoding still
    # establishes the actual call edge, independent of this metadata.
    clone_graph = graph(created, retired, 'edge: { sourcename: "_ZL6createj.constprop.0" targetname: "memset" }')
    bound = callgraph_frames(clone_graph, clone_rows, clone_symbols, "source.cpp")
    require(bound["_ZL6retirej.constprop.0"].line == 191, "Unnamed retire clone guessed as create")
    require(bound["_ZL6createj.constprop.0"].line == 221, "Unnamed create clone lost its location")
    positives += 1
    # Template instantiations can share a location and a frame size. Preserve
    # their complete signatures as well as the exact assembler identity.
    int_node = graph_node("_Z4callIiEvT_", "source.cpp:7:5", "void call(T) [with T = int]")
    long_node = graph_node("_Z4callIlEvT_", "source.cpp:7:5", "void call(T) [with T = long int]")
    template_rows = stack_rows(
        "source.cpp:7:5:void call(T) [with T = int]\t16\tstatic\n"
        "source.cpp:7:5:void call(T) [with T = long int]\t16\tstatic"
    )
    require(
        len(
            callgraph_frames(
                graph(int_node, long_node), template_rows, {"_Z4callIiEvT_", "_Z4callIlEvT_"}, "source.cpp"
            )
        )
        == 2,
        "Same-location template instantiations collapsed",
    )
    positives += 1
    for label, changed, records, symbols, source in (
        ("wrong translation unit", clone_graph, clone_rows, clone_symbols, "other.cpp"),
        (
            "wrong source file",
            clone_graph.replace("source.cpp:191", "other.cpp:191"),
            clone_rows,
            clone_symbols,
            "source.cpp",
        ),
        ("wrong source line", clone_graph.replace(":191:20", ":192:20"), clone_rows, clone_symbols, "source.cpp"),
        ("wrong source column", clone_graph.replace(":191:20", ":191:21"), clone_rows, clone_symbols, "source.cpp"),
        (
            "wrong display signature",
            clone_graph.replace("0(unsigned", "1(unsigned", 1),
            clone_rows,
            clone_symbols,
            "source.cpp",
        ),
        ("wrong frame bound", clone_graph.replace("16 bytes", "24 bytes", 1), clone_rows, clone_symbols, "source.cpp"),
        (
            "wrong frame kind",
            clone_graph.replace("(static)", "(dynamic,bounded)", 1),
            clone_rows,
            clone_symbols,
            "source.cpp",
        ),
        ("duplicate node", graph(created, retired, retired), clone_rows, clone_symbols, "source.cpp"),
        ("missing node", graph(created), clone_rows, clone_symbols, "source.cpp"),
        ("missing object symbol", clone_graph, clone_rows, {"_ZL6createj.constprop.0"}, "source.cpp"),
        ("extra object symbol", clone_graph, clone_rows, clone_symbols | {"missing"}, "source.cpp"),
        (
            "wrong object source prefix",
            clone_graph.replace("source.cpp:_Z", "other.cpp:_Z", 1),
            clone_rows,
            clone_symbols,
            "source.cpp",
        ),
        ("location collapse", clone_graph.replace(":221:20", ":191:20"), clone_rows, clone_symbols, "source.cpp"),
        ("truncated graph", clone_graph[:-1], clone_rows, clone_symbols, "source.cpp"),
    ):
        rejects(
            label,
            lambda changed=changed, records=records, symbols=symbols, source=source: callgraph_frames(
                changed, records, symbols, source
            ),
        )
    external = created[:-2] + " shape : ellipse }"
    rejects(
        "defined object symbol marked external",
        lambda: callgraph_frames(graph(external, retired), clone_rows, clone_symbols, "source.cpp"),
    )
    normalized_duplicate = graph(created, retired, retired.replace("source.cpp:_Z", "_Z"))
    rejects(
        "duplicate normalized assembler symbol",
        lambda: callgraph_frames(normalized_duplicate, clone_rows, clone_symbols, "source.cpp"),
    )
    dynamic = "source.cpp:1:1:void approved()\t16\tdynamic,bounded"
    approved = stack_rows(dynamic, allow_bounded=lambda signature: signature == "void approved()")
    approved_graph = graph(graph_node("approved", "source.cpp:1:1", "void approved()", kind="dynamic,bounded"))
    require(
        callgraph_frames(approved_graph, approved, {"approved"}, "source.cpp")["approved"].kind == "dynamic,bounded",
        "Approved bounded frame lost its original kind",
    )
    positives += 1
    rejects("unapproved bounded frame", lambda: stack_rows(dynamic, allow_bounded=lambda _: False))
    rejects(
        "bounded policy does not admit unbounded frame",
        lambda: stack_rows(dynamic.replace("dynamic,bounded", "dynamic"), allow_bounded=lambda _: True),
    )

    shared_location = graph(
        retired,
        graph_node("source.cpp:_ZL6retirej.constprop.1", "source.cpp:191:20", "0(unsigned int)"),
    )
    rejects(
        "two exact-signature clones share one record",
        lambda: callgraph_frames(
            shared_location,
            stack_rows("source.cpp:191:20:0(unsigned int)\t16\tstatic"),
            {"_ZL6retirej.constprop.0", "_ZL6retirej.constprop.1"},
            "source.cpp",
        ),
    )

    class ObjectFixture:
        def __init__(self, data, size=None, relocations=()):
            self.data = data
            self.functions = {"test": Symbol("test", 0, len(data) if size is None else size, 1, 2)}
            self.relocations = relocations

        def function_bytes(self, _symbol):
            return self.data

    original = ObjectFixture(b"\x90\xc3")
    associate_object(original, original, original.functions["test"])
    positives += 1
    for label, changed in (
        ("linked body mismatch", ObjectFixture(b"\x50\xc3")),
        ("linked extent mismatch", ObjectFixture(b"\xc3")),
    ):
        rejects(label, lambda changed=changed: associate_object(changed, original, original.functions["test"]))
    bad_relocation = ObjectFixture(b"\x90\xc3", relocations=[(1, 0, 99, 0, 0)])
    rejects("unknown relocation", lambda: associate_object(original, bad_relocation, original.functions["test"]))
    bad_relocation.relocations = [(1, 1, 2, 0, 0)]
    rejects("relocation boundary", lambda: associate_object(original, bad_relocation, original.functions["test"]))
    # Real COMDAT selection may discard a different register spelling. Only
    # exact same-signature candidates matching linked bytes supply stack facts.
    original.comdat = {1: "test"}
    discarded = ObjectFixture(b"\x50\xc3")
    discarded.comdat = {1: "test"}
    row = stack.StackRecord("source.cpp", 1, 1, "test()", 16, "static")
    candidates = [(original, row, set()), (discarded, row, {("test", "discarded_only")})]
    require(stack.compiler_witnesses(original, "test", candidates) == candidates[:1], "Discarded COMDAT facts leaked")
    positives += 1
    rejects("no exact COMDAT witness", lambda: stack.compiler_witnesses(original, "test", candidates[1:]))
    discarded.comdat = {1: "other"}
    rejects("different COMDAT group", lambda: stack.compiler_witnesses(original, "test", candidates))
    discarded.comdat = {}
    rejects("non-COMDAT duplicate", lambda: stack.compiler_witnesses(original, "test", candidates))
    rejects(
        "conflicting matched edges",
        lambda: stack.compiler_witnesses(original, "test", [candidates[0], (original, row, {("test", "foreign")})]),
    )
    changed_row = stack.StackRecord("source.cpp", 1, 1, "test()", 8, "static")
    rejects(
        "smaller competing witness",
        lambda: stack.compiler_witnesses(original, "test", [candidates[0], (original, changed_row, set())]),
    )
    # A matching opcode stream with a different relocation target is not a witness.
    call = ObjectFixture(b"\xe8\0\0\0\0", relocations=[(1, 1, 4, 0, -4)])
    call.relocation_symbols = {(1, 1): Symbol("callee", 0, 0, 0, 0)}
    installed = ObjectFixture(b"\xe8\x03\0\0\0")
    installed.symbols = [Symbol("callee", 8, 1, 1, 2)]
    require(
        stack.object_matches(installed, call, call.functions["test"], relocation_targets=True), "Exact rel32 witness"
    )
    installed.symbols = [Symbol("callee", 9, 1, 1, 2)]
    require(
        not stack.object_matches(installed, call, call.functions["test"], relocation_targets=True),
        "Changed COMDAT callee relocation accepted",
    )
    positives += 1
    print(f"PASS: owned-byte linked stack proof, {positives} positives and {rejected} negative controls")


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    args = parser.parse_args()
    require(bool(args.directory) != bool(args.build_dir), "Select exactly one artifact directory")
    ROOT = args.source_root.resolve(strict=True)
    stack.ROOT = ROOT
    directory, output = args.build_dir or args.directory, args.output
    # Remove a prior receipt before any validation so failure cannot leave a
    # stale PASS. The caller supplies the dedicated build output location.
    output.unlink(missing_ok=True)
    result = validate(directory)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        f"PASS: owned-byte linked stack {result['normal_peak']} + {FAULT_RESERVE} fault reserve = "
        f"{result['peak_with_fault_reserve']} <= {STACK_CAP} of unchanged {STACK_BYTES} bytes"
    )


if __name__ == "__main__":
    main()
