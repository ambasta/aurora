#!/usr/bin/env python3
"""Fail-closed linked stack proof for the exclusive kernel owned-byte profile.

No compilation or guest execution is performed. GNU binutils disassemble the
retained ELF; every reachable instruction and direct edge is checked. Stack
usage records are associated with exact object symbols, never a leaf allowance.
The sole admitted recursion is the page verifier's checked levels 3, 2, 1, 0.
"""

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import struct
import subprocess
import sys

ENTRY = "__au_v_m1_18kernel_owned_bytes_n0__d24kernel_owned_bytes_entry"
CONSUMER = "__au_v_m1_18kernel_owned_bytes_n0__d13consume_bytes"
TRANSFER = "__au_v_m1_18kernel_owned_bytes_n0__d10pass_bytes"
BRIDGE = "__au_runtime_bytes_kernel_entry"
WALK = "_ZZNK6aurora4uefi10PageTables6verifyEmRKNS0_5BytesEPKNS0_18LocalApicAdmissionEENKUlOT_mjmE_clIRKSA_EEbS9_mjm"
CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "owned-bytes-runtime", "owned-bytes-profile")
STACK_BYTES = 16384
STACK_CAP = 15360
FAULT_RESERVE = 512
NORETURN = frozenset(
    (
        "__au_runtime_bytes_kernel_fault",
        "uefi_payload_fail",
        "_ZN6aurora6kernel5bytes6Region6retainERNS2_10AllocationE",
    )
)

OWNED_NORETURN = NORETURN


def require(condition, message):
    if not condition:
        raise ValueError(message)


def command(*args):
    return subprocess.check_output(args, text=True)


@dataclass(frozen=True)
class Instruction:
    address: int
    size: int
    op: str
    args: str

    @property
    def next(self):
        return self.address + self.size


def normalize_repeat_spelling(raw, args):
    # Binutils 2.47 omits the implicit DS/ES segment names. Only the already
    # admitted byte primitives may use this spelling alias, with exact opcodes;
    # address-size/segment overrides and other widths retain fail-closed decoding.
    aliases = {
        "movsb (%rsi),(%rdi)": (b"\xf3\xa4", "movsb %ds:(%rsi),%es:(%rdi)"),
        "stos %al,(%rdi)": (b"\xf3\xaa", "stos %al,%es:(%rdi)"),
    }
    if args not in aliases:
        return args
    expected, canonical = aliases[args]
    require(raw == expected, "Repeated-instruction spelling/opcode mismatch")
    return canonical


def disassemble(path):
    text = command("objdump", "-dw", str(path))
    instructions = {}
    for line in text.splitlines():
        match = re.fullmatch(r"\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*([^\s]+)\s*(.*?)\s*", line)
        if not match:
            continue
        address, raw, op, args = match.groups()
        address = int(address, 16)
        require(address not in instructions, "Duplicate instruction address")
        args = args.split("#", 1)[0].strip()
        if op == "rep":
            args = normalize_repeat_spelling(bytes.fromhex(raw), args)
        instructions[address] = Instruction(address, len(raw.split()), op, args)
    require(instructions, "Missing linked disassembly")
    return instructions, text


@dataclass(frozen=True)
class Symbol:
    name: str
    address: int
    size: int
    section: int
    kind: int


class Elf:
    """Small read-only ELF64 reader; retains exact symbols/relocation locations."""

    def __init__(self, path):
        self.path = path
        self.data = path.read_bytes()
        require(self.data[:6] == b"\x7fELF\x02\x01", "Expected little-endian ELF64")
        header = struct.unpack_from("<16sHHIQQQIHHHHHH", self.data)
        require(header[2] == 62, "Expected x86-64 ELF")
        self.type = header[1]
        offset, entry_size, count = header[6], header[11], header[12]
        require(entry_size == 64, "Unsupported section table")
        self.sections = [struct.unpack_from("<IIQQQQIIQQ", self.data, offset + i * entry_size) for i in range(count)]
        self.symbols = []
        self.relocations = []
        for section in self.sections:
            if section[1] == 2:
                strings = self.section_data(section[6])
                require(section[9] == 24, "Unsupported symbol table")
                for pos in range(section[4], section[4] + section[5], 24):
                    name, info, _, index, value, size = struct.unpack_from("<IBBHQQ", self.data, pos)
                    end = strings.find(b"\0", name)
                    require(end >= name, "Invalid symbol string")
                    self.symbols.append(Symbol(strings[name:end].decode(), value, size, index, info & 15))
            if section[1] == 4:
                require(section[9] == 24, "Unsupported relocation table")
                for pos in range(section[4], section[4] + section[5], 24):
                    address, info, addend = struct.unpack_from("<QQq", self.data, pos)
                    self.relocations.append((section[7], address, info & 0xFFFFFFFF, info >> 32, addend))
        self.functions = {}
        for symbol in self.symbols:
            if symbol.kind == 2 and symbol.section:
                require(symbol.name not in self.functions, "Duplicate function symbol: " + symbol.name)
                self.functions[symbol.name] = symbol
        # The existing entry assembly uses NOTYPE labels. Only these exact labels
        # are admitted; their boundaries come from the next linked text symbol.
        labels = {"uefi_payload_entry", "uefi_payload_fault", "uefi_payload_page_fault", "fault_common"}
        for symbol in self.symbols:
            if symbol.name in labels and symbol.section:
                self.functions[symbol.name] = symbol
        starts = sorted({s.address for s in self.functions.values()})
        if self.type == 2:
            for name, symbol in list(self.functions.items()):
                if not symbol.size:
                    following = [value for value in starts if value > symbol.address]
                    require(following, "Unbounded assembly label")
                    self.functions[name] = Symbol(
                        name, symbol.address, min(following) - symbol.address, symbol.section, symbol.kind
                    )

    def section_data(self, index):
        section = self.sections[index]
        return self.data[section[4] : section[4] + section[5]]

    def function_bytes(self, symbol):
        section = self.sections[symbol.section]
        start = symbol.address - (section[3] if self.type == 2 else 0)
        return self.section_data(symbol.section)[start : start + symbol.size]


def associate_object(linked, obj, symbol):
    """Only relocation slots may differ between the object and linked body."""
    target = linked.functions[symbol.name]
    require(target.size == symbol.size, "Object/link size mismatch: " + symbol.name)
    expected = bytearray(obj.function_bytes(symbol))
    actual = bytearray(linked.function_bytes(target))
    for section, address, kind, _, _ in obj.relocations:
        if section == symbol.section and symbol.address <= address < symbol.address + symbol.size:
            require(kind in (2, 4), "Unsupported text relocation")
            offset = address - symbol.address
            require(offset + 4 <= len(expected), "Relocation crosses function boundary")
            expected[offset : offset + 4] = actual[offset : offset + 4] = b"\0" * 4
    require(expected == actual, "Object/link instruction mismatch: " + symbol.name)


@dataclass(frozen=True)
class StackRecord:
    source: str
    line: int
    column: int
    signature: str
    size: int
    kind: str

    @property
    def identity(self):
        return self.source, self.line, self.column, self.signature

    @property
    def location(self):
        return f"{self.source}:{self.line}:{self.column}"


def stack_record(location, signature, size, kind, allow_bounded=None):
    match = re.fullmatch(r"(.+):([1-9][0-9]*):([1-9][0-9]*)", location)
    require(match, "Missing compiler source location")
    require(signature and "\n" not in signature and "\t" not in signature, "Invalid compiler frame signature")
    require(
        kind == "static" or (kind == "dynamic,bounded" and allow_bounded and allow_bounded(signature)),
        "Unbounded or unapproved dynamic compiler frame: " + signature,
    )
    require(re.fullmatch(r"[0-9]+", size), "Invalid compiler frame size")
    require(8 <= int(size) <= STACK_CAP, "Invalid compiler frame bound")
    return StackRecord(match[1], int(match[2]), int(match[3]), signature, int(size), kind)


def stack_rows(text, allow_bounded=None):
    """Keep complete locations and spellings, including unnamed GCC clones."""
    rows = {}
    for line in text.splitlines():
        fields = line.rsplit("\t", 2)
        require(len(fields) == 3, "Malformed compiler stack record")
        match = re.fullmatch(r"(.+?:[1-9][0-9]*:[1-9][0-9]*):(.*)", fields[0])
        require(match, "Missing compiler source location")
        row = stack_record(match[1], match[2], fields[1], fields[2], allow_bounded)
        require(row.identity not in rows, "Ambiguous compiler stack record: " + row.location)
        rows[row.identity] = row
    return rows


def callgraph_frames(text, rows, symbols, source):
    """Join .su to exact assembler names from GCC's per-object .ci nodes.

    VCG edges are not used for stack arithmetic: the linked instruction decoder
    still establishes every actual edge. Unknown node formats or many-to-one
    clone/location associations fail closed rather than guessing a display name.
    """
    quoted = r'"(?:[^"\\]|\\["\\n])*"'
    lines = text.splitlines()
    require(len(lines) >= 2 and lines[-1] == "}", "Malformed compiler callgraph")
    header = re.fullmatch(r"graph: \{ title: (" + quoted + r")", lines[0])
    require(header and json.loads(header[1]) == source, "Compiler callgraph source mismatch")
    associated, used, titles = {}, set(), set()
    for line in lines[1:-1]:
        if line.startswith("edge:"):
            require(
                re.fullmatch(
                    r"edge: \{ sourcename: " + quoted + r" targetname: " + quoted + r"(?: label: " + quoted + r")? \}",
                    line,
                ),
                "Malformed compiler callgraph edge",
            )
            continue
        node = re.fullmatch(r"node: \{ title: (" + quoted + r") label: (" + quoted + r")( shape : ellipse)? \}", line)
        require(node, "Malformed compiler callgraph node")
        title, label = json.loads(node[1]), json.loads(node[2])
        require(title not in titles, "Duplicate compiler callgraph symbol")
        titles.add(title)
        name = title.removeprefix(source + ":").removeprefix("*")
        require(re.fullmatch(r"[A-Za-z_.$][\w.$]*", name), "Unrecognized compiler assembler name")
        if node[3]:
            require(name not in symbols, "Object definition marked external in compiler callgraph")
            continue
        fields = label.split("\n")
        require(len(fields) == 3, "Missing compiler callgraph frame/location")
        signature, location, bound = fields
        match = re.fullmatch(r"([0-9]+) bytes \((static|dynamic,bounded)\)", bound)
        require(match, "Unbounded compiler callgraph frame")
        # The caller's .su policy has already admitted (or rejected) bounded
        # dynamic frames. Both compiler artifacts must retain the original kind.
        row = stack_record(location, signature, match[1], match[2], lambda _: True)
        require(row.identity in rows and rows[row.identity] == row, "Callgraph/stack source or frame mismatch")
        require(name in symbols, "Compiler frame lacks exact object definition: " + name)
        require(name not in associated and row.identity not in used, "Ambiguous object/source/frame association")
        associated[name] = row
        used.add(row.identity)
    require(set(associated) == set(symbols), "Object definitions lack exact compiler frames")
    require(used == set(rows), "Stack records lack exact object definitions")
    return associated


def object_stack_rows(directory, name, symbols):
    source = {
        "owned-bytes-runtime": "kernel/owned-bytes.cpp",
        "owned-bytes-profile": "kernel/uefi/owned-bytes.cpp",
    }.get(name, "kernel/uefi/" + name + ".cpp")
    rows = stack_rows((directory / (name + ".su")).read_text())
    return callgraph_frames((directory / (name + ".ci")).read_text(), rows, symbols, source)


def source_frame_symbol(associations, object_name, source, signature):
    candidates = [
        symbol
        for symbol, records in associations.items()
        if any(
            row["object"] == object_name and row["source"] == source and row["record"] == signature for row in records
        )
    ]
    require(len(candidates) == 1, "Missing or ambiguous source-bound helper: " + signature)
    return candidates[0]


def cpp_frames(directory, linked):
    associated = {}
    receipts = {}
    root = Path(__file__).resolve().parents[1]
    for name in CPP_OBJECTS:
        obj = Elf(directory / (name + ".o"))
        require(obj.type == 1, "Expected relocatable C++ object")
        rows = object_stack_rows(directory, name, obj.functions)
        for symbol_name, row in rows.items():
            require(symbol_name in linked.functions, "Object function omitted from linked profile")
            associate_object(linked, obj, obj.functions[symbol_name])
            if symbol_name in associated:
                require(associated[symbol_name] == row.size, "Conflicting COMDAT compiler frames")
            associated[symbol_name] = row.size
            source = (root / row.source).resolve()
            require(source.is_relative_to(root / "kernel"), "Compiler frame outside kernel source inventory")
            contents = source.read_bytes()
            lines = contents.decode().splitlines()
            require(row.line <= len(lines) and row.column <= len(lines[row.line - 1]) + 1, "Invalid frame location")
            receipts.setdefault(symbol_name, []).append(
                {
                    "object": name + ".o",
                    "callgraph": name + ".ci",
                    "source": row.source,
                    "source_sha256": hashlib.sha256(contents).hexdigest(),
                    "line": row.line,
                    "column": row.column,
                    "record": row.signature,
                    "bytes": row.size,
                    "kind": row.kind,
                }
            )
    return associated, receipts


BRANCHES = frozenset("ja jae jb jbe je jne jge jg jl jle jns js jo jno jp jnp jz jnz jmp".split())
# Stack-neutral instructions admitted by this bounded x86-64 profile. Unknown
# instruction semantics, implicit stack operations, calls and returns fail shut.
NEUTRAL = frozenset(
    (
        "add addl addq and bt cld cli cmova cmovae cmovbe cmove cmovne cmovns cmp cmpb cmpl cmpq cmpw cpuid cs data16 "
        "dec div hlt imul in inc invlpg lea mov movabs movb movl movq movslq movzbl movzbq movzwl "
        "mul neg nop nopl nopw "
        "not or orq out rdmsr rep sbb seta setae setb setbe sete setl setle setne shl shr sub subq test ud2 xchg xor"
    ).split()
)
READ_ONLY = frozenset("cmp cmpb cmpl cmpq cmpw test bt out invlpg".split())
PRESERVE_FLAGS = frozenset(
    (
        "mov movabs movb movl movq movslq movzbl movzbq lea push pop pushf nop nopl nopw cs data16 "
        "cld cli hlt in out invlpg rep not"
    ).split()
)


def target_of(insn):
    match = re.fullmatch(r"([0-9a-f]+) <([^>]+)>", insn.args)
    require(match, "Indirect or unresolved control transfer at " + hex(insn.address))
    return int(match[1], 16)


CALLEE_SAVED_REGISTERS = {
    "%rbx": ("%rbx", "%ebx", "%bx", "%bl", "%bh"),
    "%rbp": ("%rbp", "%ebp", "%bp", "%bpl"),
    **{f"%r{i}": (f"%r{i}", f"%r{i}d", f"%r{i}w", f"%r{i}b") for i in range(12, 16)},
}


def tracked_register(operand, carrier="%r14"):
    if operand in ("%rcx", "%ecx", "%cx", "%cl", "%ch"):
        return 0
    if operand in CALLEE_SAVED_REGISTERS[carrier]:
        return 1
    return None


def arguments(text):
    return re.split(r",(?![^()]*\))", text)


def analyze_function(symbol, instructions, starts, seed=None, fault=False, carrier="%r14", memory_pushes=None):
    """CFG fixed point. Different stack depths at a join reject growing loops.

    Tiny constant propagation is deliberately restricted to the verifier level
    argument (%ecx) and its selected callee-saved carrier. Every unrecognized write
    kills a fact. Calls kill %ecx. No data-dependent loop trip count is assumed.
    """
    begin, end = symbol.address, symbol.address + symbol.size
    authorized_pushes = {}
    if memory_pushes is not None:
        require(type(memory_pushes) is dict and set(memory_pushes) == {"owner", "sites"}
                and memory_pushes["owner"] == symbol.name,
                "Foreign or malformed memory-push authorization")
        authorized_pushes = memory_pushes["sites"]
        require(type(authorized_pushes) is dict and authorized_pushes,
                "Empty or malformed memory-push site inventory")
        for address, displacement in authorized_pushes.items():
            require(type(address) is int and type(displacement) is int and displacement in (8, 24, 40)
                    and begin <= address < end and address in instructions,
                    "Unproved memory-push address or displacement")
            row = instructions[address]
            require(row.op == "push" and row.size == 4 and row.args == hex(displacement) + "(%rsp)" and row.next <= end,
                    "Memory-push authorization does not match the original instruction")
    observed_pushes = {}
    wide_level_registers = ("%rcx", "%ecx", *CALLEE_SAVED_REGISTERS[carrier][:2])
    # State: consumed bytes, saved frame-pointer depth, ecx, r14, known ZF.
    states = {begin: (0, None, seed, None, None)}
    queue = deque([begin])
    peaks = 8
    push_peak = 8
    calls = {}
    visited = set()
    returns = 0

    def schedule(address, state):
        require(begin <= address < end, "Unmodeled function fallthrough: " + symbol.name)
        require(address in instructions, "Control flow enters non-instruction")
        prior = states.get(address)
        if prior is not None:
            require(prior[:2] == state[:2], "Inconsistent or unbounded stack at CFG join: " + symbol.name)
            state = prior[:2] + tuple(a if a == b else None for a, b in zip(prior[2:], state[2:]))
            if prior == state:
                return
        states[address] = state
        queue.append(address)

    while queue:
        address = queue.popleft()
        require(address in instructions, "Missing reachable instruction")
        insn = instructions[address]
        require(insn.next <= end, "Instruction crosses function extent")
        visited.add(address)
        depth, bp, cx, r14, zf = states[address]
        op, args = insn.op, arguments(insn.args)
        for operand in args:
            if "%rsp" in operand and "(" in operand:
                require(not re.search(r"-[^()]*\(%rsp", operand), "Unproven below-stack access")
            if bp is not None:
                local = re.fullmatch(r"-(0x[0-9a-f]+|[0-9]+)\(%rbp\)", operand)
                if local:
                    require(bp + int(local[1], 0) <= depth, "Frame access below allocated stack")
        if op in ("cs", "data16"):
            require(re.fullmatch(r"(?:cs )?nopw (?:0x0)?\([^)]*\)", insn.args), "Unsupported instruction prefix")
        if op == "rep":
            require(
                insn.args
                in (
                    "movsb %ds:(%rsi),%es:(%rdi)",
                    "stos %al,%es:(%rdi)",
                    "stos %eax,%es:(%rdi)",
                    "stos %rax,%es:(%rdi)",
                    "movsq %ds:(%rsi),%es:(%rdi)",
                    "movsl %ds:(%rsi),%es:(%rdi)",
                ),
                "Unsupported repeated instruction",
            )
        if op == "xchg":
            require(not any(arg in ("%rsp", "%esp", "%sp", "%spl") for arg in args), "Stack-pointer exchange")
        next_zf = zf if op in PRESERVE_FLAGS or op in BRANCHES else None
        old = (cx, r14)
        values = [cx, r14]
        if args and op not in READ_ONLY and op not in BRANCHES and op not in ("call", "ret", "ud2"):
            destination = tracked_register(args[-1], carrier)
            if destination is not None:
                value = None
                if op in ("mov", "movl", "movq", "movabs") and len(args) == 2 and args[1] in wide_level_registers:
                    source = tracked_register(args[0], carrier)
                    if source is not None and args[0] in wide_level_registers:
                        value = old[source]
                    elif re.fullmatch(r"\$(?:0x[0-9a-f]+|[0-9]+)", args[0]):
                        immediate = int(args[0][1:], 0)
                        value = immediate if immediate <= 3 else None
                if (
                    op == "lea"
                    and len(args) == 2
                    and args[0] == f"-0x1({carrier})"
                    and args[1] in wide_level_registers
                    and old[1] is not None
                ):
                    value = old[1] - 1
                values[destination] = value
        if op in ("cpuid", "rep"):
            values[0] = None
        if op == "cpuid" and carrier == "%rbx":
            values[1] = None
        if op == "xchg":
            for operand in args:
                register = tracked_register(operand, carrier)
                if register is not None:
                    values[register] = None
                if operand in ("%rbp", "%ebp", "%bp", "%bpl"):
                    bp = None
        if op == "test" and len(args) == 2 and args[0] == args[1]:
            register = tracked_register(args[0], carrier)
            if register is not None and args[0] in wide_level_registers and old[register] is not None:
                next_zf = old[register] == 0
        if op in ("push", "pushf"):
            if address in authorized_pushes:
                displacement = authorized_pushes[address]
                # x86 PUSH reads its source using the old RSP. Check the entire
                # qword before decrementing RSP; caller return bytes are excluded.
                require(op == "push" and insn.args == hex(displacement) + "(%rsp)"
                        and displacement + 8 <= depth,
                        "Memory push reads outside the pre-push live frame")
                observed_pushes[address] = dict(address=address, source_old_rsp=displacement,
                                                source_bytes=8, depth_before=depth, depth_after=depth + 8)
            else:
                require(
                    op == "pushf" or re.fullmatch(r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])", insn.args),
                    "Unsupported push operand width or stack pointer",
                )
            depth += 8
            push_peak = max(push_peak, 8 + depth)
        elif op == "pop":
            require(
                re.fullmatch(r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])", insn.args),
                "Unsupported pop operand width or stack pointer",
            )
            depth -= 8
            if args[0] == "%rbp":
                bp = None
        elif op == "leave":
            require(bp is not None and depth >= bp, "Unproven frame-pointer restoration")
            depth, bp = bp - 8, None
        elif op == "ret":
            require(not insn.args and depth == 0, "Unbalanced or unsupported return")
            returns += 1
            continue
        elif args and args[-1] in ("%rsp", "%esp", "%sp", "%spl"):
            match = re.fullmatch(r"\$(0x[0-9a-f]+|[0-9]+),%rsp", insn.args)
            if op in ("add", "sub") and match:
                count = int(match[1], 0)
                require(count % 8 == 0, "Unaligned stack adjustment")
                depth += count if op == "sub" else -count
            elif fault and op == "and" and insn.args == "$0xfffffffffffffff0,%rsp":
                depth += 15  # Concrete worst-case downward alignment, fault path only.
            else:
                raise ValueError("Unbounded or unknown stack adjustment: " + insn.args)
        elif op == "mov" and insn.args == "%rsp,%rbp":
            bp = depth
        elif args and args[-1] in ("%rbp", "%ebp", "%bp", "%bpl") and op not in READ_ONLY:
            bp = None
        require(0 <= depth <= STACK_CAP, "Unbalanced or excessive stack depth")
        peaks = max(peaks, 8 + depth)
        state = (depth, bp, *values, next_zf)
        if op == "call" or op in BRANCHES:
            target = target_of(insn)
            require(target in instructions, "Transfer to non-instruction")
            taken = None
            if op in ("je", "jz"):
                taken = zf
            elif op in ("jne", "jnz") and zf is not None:
                taken = not zf
            if op != "call" and taken is False:
                schedule(insn.next, state)
                continue
            if op != "call" and begin <= target < end:
                schedule(target, state)
            elif instructions[target].op == "ud2" and op != "call":
                calls[address] = dict(address=address, target=None, kind="trap", live_bytes=8 + depth, level=values[0])
            elif fault and target == 6 and instructions[target].op == "cli":
                halt = instructions.get(instructions[target].next)
                loop = instructions.get(halt.next) if halt else None
                require(
                    halt and halt.op == "hlt" and loop and loop.op == "jmp" and target_of(loop) == target,
                    "Unknown fault terminal",
                )
            else:
                require(target in starts, "Control flow enters another function interior")
                kind = "call" if op == "call" else "tail"
                require(kind == "call" or depth == 0, "Tail transfer retains an unmodeled frame")
                calls[address] = dict(
                    address=address,
                    target=starts[target],
                    kind=kind,
                    live_bytes=8 + depth if kind == "call" else 0,
                    level=values[0],
                )
            if op == "call" and starts.get(target) in NORETURN:
                continue
            if op == "call":
                state = (depth, bp, None, values[1], None)
            if op != "jmp" and (op == "call" or taken is not True):
                schedule(insn.next, state)
            continue
        require(op in NEUTRAL or op in ("push", "pushf", "pop", "leave"), "Unknown instruction semantics: " + op)
        if op == "ud2":
            continue
        if insn.next == end and symbol.name == "uefi_payload_page_fault":
            require(starts.get(end) == "fault_common", "Unexpected page-fault fallthrough")
            calls[address] = dict(address=address, target="fault_common", kind="tail", live_bytes=0, level=None)
        else:
            schedule(insn.next, state)
    require(set(observed_pushes) == set(authorized_pushes), "Unused memory-push authorization")
    result = dict(
        local_peak=peaks,
        calls=sorted(calls.values(), key=lambda row: row["address"]),
        instructions=len(visited),
        returns=returns,
        push_peak=push_peak,
    )
    if authorized_pushes:
        result["stack_memory_pushes"] = sorted(observed_pushes.values(), key=lambda row: row["address"])
    return result


def prove_carrier_preserved(symbol, instructions, starts, carrier, trusted_marker_stores=()):
    """Prove preservation on every return, including shrink-wrapped paths.

    The saved value is represented by its exact eight-byte entry-RSP-relative
    slot, not by a prologue spelling or assumed ABI preservation. This bounded
    profile admits register pushes/pops and direct allocated RSP-relative MOV
    spills. Stack-address escapes, indexed stack accesses and other stores are
    rejected. Only the separately identified visited-array marker may rely on
    the existing source/compiler memory-safety contract; its non-aliasing is
    not claimed to follow from this local machine-stack proof.
    """
    begin, end = symbol.address, symbol.address + symbol.size
    family = CALLEE_SAVED_REGISTERS[carrier]
    pending = deque([(begin, 0, True, None)])
    visited = set()
    depths = {begin: 0}

    def stack_offset(operand):
        match = re.fullmatch(r"(?:(0x[0-9a-f]+|[0-9]+))?\(%rsp\)", operand)
        return int(match[1] or "0", 0) if match else None

    def store_width(op, source):
        if op in ("movb", "movw", "movl", "movq"):
            return {"movb": 1, "movw": 2, "movl": 4, "movq": 8}[op]
        require(op == "mov", "Unknown write to verifier stack storage")
        if re.fullmatch(r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])", source):
            return 8
        if re.fullmatch(r"%(?:e(?:ax|bx|cx|dx|si|di|bp)|r(?:[89]|1[0-5])d)", source):
            return 4
        if re.fullmatch(r"%(?:ax|bx|cx|dx|si|di|bp|r(?:[89]|1[0-5])w)", source):
            return 2
        if re.fullmatch(r"%(?:[abcd][lh]|sil|dil|bpl|r(?:[89]|1[0-5])b)", source):
            return 1
        raise ValueError("Unknown verifier stack-store width")

    def enqueue(address, depth, original, slot):
        require(begin <= address < end and address in instructions, "Unknown verifier preservation edge")
        require(0 <= depth <= STACK_CAP, "Unbounded verifier preservation stack")
        require(address not in depths or depths[address] == depth, "Inconsistent verifier preservation stack")
        depths[address] = depth
        state = (address, depth, original, slot)
        if state not in visited:
            pending.append(state)

    while pending:
        state = pending.popleft()
        if state in visited:
            continue
        visited.add(state)
        address, depth, original, slot = state
        row = instructions[address]
        op, args = row.op, arguments(row.args)
        require(row.next <= end, "Verifier preservation instruction crosses extent")
        require(op != "rep", "Unmodeled implicit verifier memory write")
        require(not (op == "cpuid" and carrier == "%rbx"), "Implicit write to recursive level carrier")
        for operand in args:
            if re.search(r"%(?:rsp|esp|sp|spl)(?![a-z0-9])", operand):
                require(
                    (stack_offset(operand) is not None and op != "lea")
                    or (operand == "%rsp" and op in ("add", "sub") and args[-1] == operand),
                    "Verifier stack address escapes direct spill profile",
                )
        if (
            op not in READ_ONLY
            and op not in BRANCHES
            and op not in ("lea", "nop", "nopl", "nopw", "cs", "data16", "push", "pop", "ret", "call", "ud2")
        ):
            destinations = args if op == "xchg" else args[-1:]
            require(
                all(
                    not operand
                    or re.fullmatch(r"%[a-z][a-z0-9]*", operand)
                    or stack_offset(operand) is not None
                    or row.address in trusted_marker_stores
                    for operand in destinations
                ),
                "Unproven nonlocal write in verifier carrier proof",
            )
        if op == "xchg":
            require(not any(arg in family for arg in args), "Exchange clobbers recursive level carrier")
            require(not any(stack_offset(arg) is not None for arg in args), "Exchange writes verifier stack storage")
        if op == "push":
            require(re.fullmatch(r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])", row.args), "Unknown verifier push")
            depth += 8
            require(slot is None or not (-depth < slot + 8 and slot < -depth + 8), "Push overlaps saved carrier")
            if row.args == carrier:
                require(original and slot is None, "Carrier save is missing the entry value")
                slot = -depth
        elif op == "pop":
            require(depth >= 8, "Unbalanced verifier pop")
            if row.args == carrier:
                require(slot == -depth, "Carrier pop does not restore the saved entry value")
                original = True
            elif row.args in family:
                raise ValueError("Partial carrier pop")
            depth -= 8
        elif op in ("add", "sub") and args[-1:] == ["%rsp"]:
            match = re.fullmatch(r"\$(0x[0-9a-f]+|[0-9]+),%rsp", row.args)
            require(match and int(match[1], 0) % 8 == 0, "Unknown verifier stack allocation")
            depth += int(match[1], 0) * (1 if op == "sub" else -1)
        elif op in ("leave", "pushf"):
            raise ValueError("Unsupported verifier preservation stack operation")
        elif args and args[-1] in family and op not in READ_ONLY and op not in BRANCHES:
            if op == "mov" and row.args == f"%ecx,{family[1]}":
                require(slot is not None, "Level carrier overwritten before its entry value is saved")
                original = False
            else:
                offset = stack_offset(args[0]) if len(args) == 2 else None
                require(
                    op in ("mov", "movq") and args[-1] == carrier and offset is not None and slot == offset - depth,
                    "Unknown write or restore to recursive level carrier",
                )
                require(offset + 8 <= depth, "Carrier restore lies outside allocated stack")
                original = True
        elif (
            args
            and stack_offset(args[-1]) is not None
            and op not in READ_ONLY
            and op not in ("lea", "nop", "nopl", "nopw", "cs", "data16")
        ):
            require(len(args) == 2, "Unknown verifier stack store")
            offset = stack_offset(args[-1])
            width = store_width(op, args[0])
            require(offset + width <= depth, "Verifier spill lies outside allocated stack")
            location = offset - depth
            require(
                slot is None or not (location < slot + 8 and slot < location + width), "Write overlaps saved carrier"
            )
            if op in ("mov", "movq") and args[0] == carrier:
                require(original and slot is None and width == 8, "Carrier save is missing the entry value")
                slot = location
        if slot is not None and slot < -depth:
            slot = None  # The backing allocation was popped/deallocated.
        require(0 <= depth <= STACK_CAP, "Unbalanced verifier preservation stack")
        if op == "ret":
            require(depth == 0 and original, "Verifier return does not preserve the entry carrier")
            continue
        if op == "ud2":
            continue
        if op == "call" or op in BRANCHES:
            target = target_of(row)
            if op != "call":
                if begin <= target < end:
                    enqueue(target, depth, original, slot)
                elif instructions[target].op != "ud2":
                    require(depth == 0 and original, "Verifier tail transfer does not preserve entry carrier")
            if op == "jmp" or (op == "call" and starts.get(target) in NORETURN):
                continue
        enqueue(row.next, depth, original, slot)


VERIFIER_SOURCE_PINS = {
    "kernel/uefi/tables.hpp": "414dfd306bbbd0bcfc409981be3a998c81b7b9f94b201c8ddee3d3dde0688f23",
    "kernel/uefi/handoff.hpp": "b5a753a311a1408e5b8368acebb8bdd5b55d2681b186b9bffa63a350815e0f33",
}
# Full compiler display signatures remain unmodified receipt data. cpp_frames
# has already joined each complete .su signature to its matching .ci node and
# exact WALK assembler symbol; the reviewed source digest and lambda location
# identify the invariant without a compiler-specific pretty-print allowlist.


def verifier_source_contract(associations, source_hashes):
    """Bind the sole nonlocal marker allowance to independently reviewed source.

    Precondition: associations are the exact .su/.ci/object results returned by
    cpp_frames, including its full-signature and linked-body association gates.
    """
    require(source_hashes == VERIFIER_SOURCE_PINS, "Reviewed verifier memory-source contract changed")
    records = associations.get(WALK, ()) if associations else ()
    require(records, "Visited marker lacks exact WALK source/object association")
    for row in records:
        require(
            row["source"] == "kernel/uefi/tables.hpp"
            and row["source_sha256"] == VERIFIER_SOURCE_PINS["kernel/uefi/tables.hpp"]
            and (row["line"], row["column"]) == (166, 27)
            and row["kind"] == "static"
            and row["object"] in {name + ".o" for name in CPP_OBJECTS}
            and row["callgraph"] == row["object"][:-2] + ".ci",
            "Visited marker has an unreviewed WALK source/object identity",
        )
    return dict(
        source_sha256=dict(VERIFIER_SOURCE_PINS),
        symbol=WALK,
        source="kernel/uefi/tables.hpp",
        line=166,
        column=27,
        compiler_records=[{key: row[key] for key in ("object", "callgraph", "record")} for row in records],
        assumption=(
            "Trusted C++ compilation of the reviewed fresh caller-local visited array, "
            "bounded slot and closure ownership; non-aliasing is a source contract, "
            "not an independent machine-pointer proof"
        ),
    )


def trusted_verifier_marker_stores(body_code):
    """Narrow the existing trusted-C++ visited-array write; do not prove aliases.

    tables.hpp::PageTables::verify owns a separate caller-local visited array.
    Its guarded slot and closure ownership, together with trusted compilation
    and the checked source/object associations, remain the memory-safety
    boundary. The local carrier proof admits only the existing indexed byte
    marker with its preceding zero-test, never arbitrary pointer stores.
    """
    registers = r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])"
    marker = re.compile(r"\$0x1,(\(" + registers + "," + registers + r",1\))")
    admitted = []
    for index, row in enumerate(body_code):
        match = marker.fullmatch(row.args) if row.op == "movb" else None
        if not match:
            continue
        destination = match[1]
        guards = [
            prior
            for prior in range(index - 1)
            if (body_code[prior].op, body_code[prior].args) == ("cmpb", "$0x0," + destination)
            and body_code[prior + 1].op == "jne"
            and not body_code[prior + 1].next <= target_of(body_code[prior + 1]) <= row.address
        ]
        require(len(guards) == 1, "Visited marker lacks its unique zero-test guard")
        admitted.append(row.address)
    require(len(admitted) <= 1, "Multiple nonlocal verifier marker stores")
    return frozenset(admitted)


def recursion_proof(functions, symbols, instructions, starts, associations=None):
    require(WALK in functions, "Missing four-level page verifier")
    symbol = symbols[WALK]
    body_code = [
        instructions[address]
        for address in sorted(instructions)
        if symbol.address <= address < symbol.address + symbol.size
    ]
    assignments = [
        carrier
        for row in body_code
        for carrier, family in CALLEE_SAVED_REGISTERS.items()
        if (row.op, row.args) == ("mov", f"%ecx,{family[1]}")
    ]
    require(len(assignments) == 1, "Verifier lacks a unique callee-saved level carrier")
    carrier = assignments[0]
    marker_stores = trusted_verifier_marker_stores(body_code)
    source_contract = None
    if marker_stores:
        root = Path(__file__).resolve().parents[1]
        source_contract = verifier_source_contract(
            associations,
            {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in VERIFIER_SOURCE_PINS},
        )
    prove_carrier_preserved(symbol, instructions, starts, carrier, marker_stores)
    for call in functions[WALK]["calls"]:
        if call["target"] not in (None, WALK):
            leaf = symbols[call["target"]]
            require(not functions[call["target"]]["calls"], "Verifier helper is no longer a proven leaf")
            prove_carrier_preserved(leaf, instructions, starts, carrier)
            require(
                not any(
                    any(register in arguments(row.args) for register in CALLEE_SAVED_REGISTERS[carrier])
                    or (row.op == "cpuid" and carrier == "%rbx")
                    for address, row in instructions.items()
                    if leaf.address <= address < leaf.address + leaf.size
                ),
                "Verifier helper clobbers recursive level carrier",
            )
    roots = [
        (name, row)
        for name, body in functions.items()
        for row in body["calls"]
        if row["target"] == WALK and name != WALK
    ]
    require(roots, "No concrete page-verifier entry")
    require(
        all(row["kind"] == "call" and row["level"] == 3 for _, row in roots),
        "Page verifier must enter at proven level three",
    )
    levels = {}
    for level in range(4):
        body = analyze_function(symbols[WALK], instructions, starts, seed=level, carrier=carrier)
        recursive = [row for row in body["calls"] if row["target"] == WALK]
        if level == 0:
            require(not recursive, "Page verifier recurses at level zero")
        else:
            require(
                len(recursive) == 1 and recursive[0]["kind"] == "call" and recursive[0]["level"] == level - 1,
                "Page verifier lacks strictly decreasing bounded level",
            )
        body["level_carrier"] = carrier
        body["trusted_marker_stores"] = sorted(marker_stores)
        if source_contract is not None:
            body["trusted_source_contract"] = source_contract
        levels[level] = body
    return levels, [{"caller": name, "address": row["address"], "initial_level": 3} for name, row in roots]


def calculate(functions, frames, levels, root):
    visiting = set()
    cache = {}

    def peak(name, level=None):
        key = (name, level)
        require(key not in visiting, "Unbounded call/control-flow cycle: " + name)
        if key in cache:
            return cache[key]
        require(name in functions, "Unknown direct callee: " + name)
        visiting.add(key)
        body = levels[level] if name == WALK and level is not None else functions[name]
        require(name != WALK or level is not None, "Verifier called without a level proof")
        frame = max(body["local_peak"], frames.get(name, 0))
        best, path = frame, [name + (f"[level={level}]" if level is not None else "")]
        for call in body["calls"]:
            if call["target"] is None:
                continue
            target = call["target"]
            child_level = call["level"] if target == WALK else None
            if target == WALK:
                require(child_level in range(4), "Unknown recursive level")
            child, child_path = peak(target, child_level)
            # A .su record may conservatively exceed decoded stack use. Keep
            # that excess at each call; never replace a larger compiler bound.
            live = call["live_bytes"] + max(0, frame - body["local_peak"])
            if live + child > best:
                best, path = live + child, path[:1] + child_path
        visiting.remove(key)
        cache[key] = best, path
        return cache[key]

    total, path = peak(root)
    return {"peak": total, "path": path, "closure": sorted({name for name, _ in cache})}


def generated_records(source, functions, symbols, instructions):
    bodies = {}
    current = None
    for raw in source.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith(".type ") and line.endswith(", @function"):
            current = line[len(".type ") : -len(", @function")]
            require(current not in bodies, "Duplicate generated function")
            bodies[current] = []
        elif line.startswith(".size "):
            current = None
        elif current and line and not line.startswith(".") and not line.endswith(":"):
            bodies[current].append(line)
    require(
        set(bodies) == {ENTRY, TRANSFER, CONSUMER, "aurora_reflect_size", "aurora_reflect_field_count"},
        "Unexpected generated function inventory",
    )
    records = {}
    runtime = {
        "__au_runtime_bytes_" + suffix for suffix in ("allocate", "at", "set", "drop", "borrow_length", "resize")
    }
    for name in (ENTRY, TRANSFER, CONSUMER):
        body = bodies[name]
        require(body[:2] == ["pushq %rbp", "movq %rsp, %rbp"], "Unknown generated frame prologue")
        frame = re.fullmatch(r"subq \$([0-9]+), %rsp", body[2])
        require(frame, "Missing bounded generated frame allocation")
        local_bytes = int(frame[1])
        require(local_bytes % 16 == 0, "Unaligned generated frame")
        linked = [
            instructions[address]
            for address in sorted(instructions)
            if symbols[name].address <= address < symbols[name].address + symbols[name].size
        ]
        require(
            [(row.op, row.args) for row in linked[:3]]
            == [("push", "%rbp"), ("mov", "%rsp,%rbp"), ("sub", f"$0x{local_bytes:x},%rsp")],
            "Generated source/linked frame mismatch",
        )
        expected_calls = [line.removeprefix("call ") for line in body if line.startswith("call ")]
        actual_calls = [row for row in functions[name]["calls"] if row["kind"] == "call"]
        require(expected_calls == [row["target"] for row in actual_calls], "Generated source/linked call mismatch")
        allowed = runtime | ({TRANSFER, CONSUMER} if name == ENTRY else set())
        if name == CONSUMER:
            allowed = {"__au_runtime_bytes_at"}
        require(set(expected_calls) <= allowed, "Unknown generated resource/helper call")
        base = local_bytes + 16  # incoming return address and saved rbp
        resource = [row for row in actual_calls if row["target"] == TRANSFER]
        require((len(resource) == 1) if name == ENTRY else not resource, "Wrong generated resource-transfer count")
        source_allocations = [
            int(match[1]) for line in body[3:] if (match := re.fullmatch(r"subq \$([0-9]+), %rsp", line))
        ]
        require(all(count in (8, 48, 64) for count in source_allocations), "Unknown generated temporary allocation")
        if name == ENTRY:
            require(
                source_allocations.count(48) == 1 and resource[0]["live_bytes"] == base + 48,
                "Resource argument record no longer has its exact 48-byte extent",
            )
            consumers = [row for row in actual_calls if row["target"] == CONSUMER]
            require(
                source_allocations.count(64) == 3
                and len(consumers) == 3
                and all(row["live_bytes"] == base + 64 for row in consumers),
                "Span argument record no longer has its exact 64-byte extent",
            )
        else:
            require(not source_allocations, "Unexpected helper-function temporary record")
        runtime_calls = [row for row in actual_calls if row["target"] in runtime]
        expression = max(
            [row["live_bytes"] - base for row in runtime_calls] + [max(0, functions[name]["push_peak"] - base)]
        )
        records[name] = {
            "frame_allocation": local_bytes,
            "base_with_saved_rbp_and_return": base,
            "expression_and_cleanup_peak": expression,
            "resource_argument_bytes": 48 if resource else 0,
            "span_argument_bytes": 64 if name == ENTRY else 0,
            "linked_local_peak": functions[name]["local_peak"],
            "calls": actual_calls,
        }
    return records


def validate_bridge(symbols, instructions, functions):
    expected = [
        ("push", "%rbp"),
        ("mov", "%rsp,%rbp"),
        ("sub", "$0x20,%rsp"),
        ("mov", "%rdi,(%rsp)"),
        ("mov", "%rsi,0x8(%rsp)"),
        ("mov", "%rdx,0x10(%rsp)"),
        ("movq", "$0x0,0x18(%rsp)"),
        ("mov", "%rsp,%r11"),
        ("call", ENTRY),
        ("leave", ""),
        ("ret", ""),
    ]
    symbol = symbols[BRIDGE]
    actual = []
    for address in sorted(instructions):
        if symbol.address <= address < symbol.address + symbol.size:
            insn = instructions[address]
            operand = ENTRY if insn.op == "call" and target_of(insn) == symbols[ENTRY].address else insn.args
            actual.append((insn.op, operand))
    require(actual == expected, "Private bridge instruction/frame/callee profile changed")
    require(functions[BRIDGE]["local_peak"] == 48, "Wrong bridge stack extent")
    return {"frame_allocation": 32, "saved_rbp_and_return": 16, "local_peak": 48, "calls": functions[BRIDGE]["calls"]}


def load_admission():
    spec = importlib.util.spec_from_file_location(
        "owned_byte_admission", Path(__file__).with_name("kernel-uefi-owned-bytes-admission.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(directory):
    global NORETURN
    elf = Elf(directory / "payload.elf")
    require(elf.type == 2, "Expected linked executable payload")
    require(not command("nm", "-u", str(directory / "payload.elf")).strip(), "Unresolved linked payload symbol")
    admission = load_admission().validate_symbols(command("nm", "-a", str(directory / "language.o")))
    instructions, disassembly = disassemble(directory / "payload.elf")
    starts = {symbol.address: name for name, symbol in elf.functions.items()}
    require(len(starts) == len(elf.functions), "Ambiguous linked function aliases")
    frames, associations = cpp_frames(directory, elf)
    diagnostic = source_frame_symbol(
        associations, "payload.o", "kernel/uefi/payload.cpp", "void {anonymous}::fail(std::string_view)"
    )
    NORETURN = OWNED_NORETURN | {diagnostic}
    language = Elf(directory / "language.o")
    for symbol in language.functions.values():
        associate_object(elf, language, symbol)
    memory = Elf(directory / "memory.o")
    for symbol in memory.functions.values():
        associate_object(elf, memory, symbol)
    assembly = {
        ENTRY,
        TRANSFER,
        CONSUMER,
        BRIDGE,
        "aurora_reflect_size",
        "aurora_reflect_field_count",
        "memcpy",
        "memset",
        "memmove",
        "memcmp",
        "uefi_payload_entry",
        "uefi_payload_fault",
        "uefi_payload_page_fault",
        "fault_common",
    }
    require(set(elf.functions) == set(frames) | assembly, "Unaccounted linked function/frame")
    functions = {
        name: analyze_function(symbol, instructions, starts, fault=name == "fault_common")
        for name, symbol in elf.functions.items()
    }
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
    generated = generated_records((directory / "language.s").read_text(), functions, elf.functions, instructions)
    levels, roots = recursion_proof(functions, elf.functions, instructions, starts, associations)
    normal = calculate(functions, frames, levels, "uefi_payload_entry")
    # Evaluate every linked function as well: dormant text may not hide unknown
    # call cycles, indirect transfers, or an unsupported recursion entry.
    for name in functions:
        if name != WALK:
            calculate(functions, frames, levels, name)
    required = {
        "uefi_payload_main",
        BRIDGE,
        ENTRY,
        TRANSFER,
        CONSUMER,
        *load_admission().RUNTIME,
        "_ZN6aurora4uefi15run_owned_bytesEmRNS_6memory13PhysicalPagesE",
    }
    require(required <= set(normal["closure"]), "Dedicated owned-byte call chain is missing")
    require(
        not any(
            "discover_acpi" in name or "discover_pci" in name or "run_protected" in name for name in normal["closure"]
        ),
        "Non-owned-byte workload reachable in dedicated profile",
    )
    faults = [calculate(functions, frames, levels, name) for name in ("uefi_payload_fault", "uefi_payload_page_fault")]
    fault_peak = 48 + max(item["peak"] for item in faults)  # CPU frame including possible error code.
    require(fault_peak <= FAULT_RESERVE, "Synchronous fault path exceeds its exact 512-byte reserve")
    peak = normal["peak"] + FAULT_RESERVE
    require(peak <= STACK_CAP, "Unchanged 16 KiB stack admission cap exceeded")
    files = ["payload.elf", "language.s", "language.o", "memory.o", "payload-entry.o"]
    files += [name + suffix for name in CPP_OBJECTS for suffix in (".o", ".su", ".ci")]
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
        "verifier": {"entry_sites": roots, "levels": levels, "maximum_active_frames": 4},
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
    require(calculate(bodies, {}, {}, "root")["peak"] == 56, "Wrong call/return/temporary stack sum")
    positives += 1
    repeated, *_ = fixture({"root": [("rep", "movsl %ds:(%rsi),%es:(%rdi)"), ("ret", "")]})
    require(calculate(repeated, {}, {}, "root")["peak"] == 8, "Repeated dword copy changed stack")
    positives += 1
    tail, *_ = fixture({"root": [("jmp", "@leaf")], "leaf": leaf})
    require(calculate(tail, {}, {}, "root")["peak"] == 8, "Tail return address counted twice")
    positives += 1
    mutations = [
        ("indirect call", 5, "call", "*%rax"),
        ("unresolved call", 5, "call", "1234"),
        ("callee interior", 5, "call", "1 <root+1>"),
        ("unknown target", 5, "call", "fff <missing>"),
        ("growing loop", 4, "jmp", "3 <root+3>"),
        ("dynamic stack", 2, "sub", "%rax,%rsp"),
        ("unaligned stack", 2, "sub", "$0x1,%rsp"),
        ("oversize frame", 2, "sub", "$0x10000,%rsp"),
        ("stack exchange", 3, "xchg", "%rsp,%rax"),
        ("16-bit push", 3, "push", "%ax"),
        ("16-bit pop", 4, "pop", "%bp"),
        ("unproven leave", 1, "mov", "%rax,%rbp"),
        ("prefixed stack write", 3, "data16", "push %ax"),
        ("repeated transfer", 3, "rep", "ret"),
        ("unknown instruction", 3, "enter", "$0x20,$0"),
        ("below frame access", 3, "mov", "-0x100(%rbp),%rax"),
        ("red-zone access", 3, "mov", "-0x8(%rsp),%rax"),
        ("stack return immediate", 7, "ret", "$0x8"),
        ("unbalanced return", 6, "nop", ""),
    ]
    for label, index, op, operands in mutations:
        mutant = dict(code)
        mutant[index] = Instruction(index, 1, op, operands)
        rejects(label, lambda mutant=mutant: analyze_function(symbols["root"], mutant, starts))
    for label, graph in [
        ("self cycle", {"root": [("call", "@root"), ("ret", "")]}),
        ("mutual cycle", {"root": [("call", "@leaf"), ("ret", "")], "leaf": [("jmp", "@root")]}),
    ]:
        mutant, *_ = fixture(graph)
        rejects(label, lambda mutant=mutant: calculate(mutant, {}, {}, "root"))
    # Concrete recursive argument proof; the only arithmetic admitted for this
    # symbolic fact is the exact current machine's lea level-1 into ecx.
    saved = ["%r15", "%r14", "%r13", "%r12", "%rbp", "%rbx"]
    walk = [("push", register) for register in saved] + [
        ("mov", "%ecx,%r14d"),
        ("test", "%r14d,%r14d"),
        ("je", "@" + WALK + "+11"),
        ("lea", "-0x1(%r14),%ecx"),
        ("call", "@" + WALK),
    ]
    walk += [("pop", register) for register in reversed(saved)] + [("ret", "")]

    graph = {"root": [("mov", "$0x3,%ecx"), ("call", "@" + WALK), ("ret", "")], WALK: walk}
    functions, symbols, code, starts = fixture(graph)
    levels, roots = recursion_proof(functions, symbols, code, starts)
    require(
        calculate(functions, {}, levels, "root")["peak"] == 232 and roots[0]["initial_level"] == 3,
        "Wrong concrete four-level stack proof",
    )
    positives += 1
    interleaved_walk = list(walk)
    interleaved_walk.insert(2, interleaved_walk.pop(6))
    mixed_graph = {"root": graph["root"], WALK: interleaved_walk}
    mixed_functions, mixed_symbols, mixed_code, mixed_starts = fixture(mixed_graph)
    mixed_levels, _ = recursion_proof(mixed_functions, mixed_symbols, mixed_code, mixed_starts)
    require(
        calculate(mixed_functions, {}, mixed_levels, "root")["peak"] == 232, "Wrong interleaved-save four-level proof"
    )
    positives += 1
    for label, index, op, operands in [
        ("interleaved move before save", 1, "mov", "%ecx,%r14d"),
        ("interleaved wrong level source", 2, "mov", "%edx,%r14d"),
        ("interleaved wrong saved register", 1, "push", "%r13"),
        ("interleaved changed restore", 15, "pop", "%rax"),
        ("interleaved increment", 9, "lea", "0x1(%r14),%ecx"),
    ]:
        changed_code = dict(mixed_code)
        changed_code[100 + index] = Instruction(100 + index, 1, op, operands)

        def check_interleaved(changed_code=changed_code):
            changed_functions = {
                name: analyze_function(symbol, changed_code, mixed_starts) for name, symbol in mixed_symbols.items()
            }
            recursion_proof(changed_functions, mixed_symbols, changed_code, mixed_starts)

        rejects(label, check_interleaved)
    for label, address, op, operands in [
        ("entry level four", 0, "mov", "$0x4,%ecx"),
        ("unknown entry", 0, "mov", "%eax,%ecx"),
        ("partial entry write", 0, "mov", "$0x3,%cl"),
        ("no decrement", 109, "mov", "%r14d,%ecx"),
        ("partial decrement", 109, "lea", "-0x1(%r14),%cx"),
        ("missing level restore", 115, "pop", "%rax"),
        ("underflow at zero", 108, "jne", "6f <walk+11>"),
        ("unknown carrier", 106, "mov", "%ecx,%r14w"),
        ("no zero guard", 107, "cmp", "$0x1,%r14d"),
    ]:
        mutant = dict(code)
        mutant[address] = Instruction(address, 1, op, operands)

        def check(mutant=mutant):
            changed = {name: analyze_function(symbol, mutant, starts) for name, symbol in symbols.items()}
            recursion_proof(changed, symbols, mutant, starts)

        rejects(label, check)
    # Implicit and first-operand clobbers must kill constants, never prove them.
    for op, operands in [
        ("cpuid", ""),
        ("rep", "movsb %ds:(%rsi),%es:(%rdi)"),
        ("rep", "movsl %ds:(%rsi),%es:(%rdi)"),
        ("xchg", "%ecx,%eax"),
        ("mov", "$0x3,%cl"),
        ("mov", "$0x3,%cx"),
    ]:

        def check(op=op, operands=operands):
            changed, syms, insns, addrs = fixture(
                {"root": [("mov", "$0x3,%ecx"), (op, operands), ("call", "@" + WALK), ("ret", "")], WALK: walk}
            )
            recursion_proof(changed, syms, insns, addrs)

        rejects("level fact clobber " + op + operands, check)
    for op, operands in (("movzwl", "%ax,%ecx"), ("cmovns", "%eax,%ecx")):

        def check_scalar(op=op, operands=operands):
            changed, syms, insns, addrs = fixture(
                {"root": [("mov", "$0x3,%ecx"), (op, operands), ("call", "@" + WALK), ("ret", "")], WALK: walk}
            )
            recursion_proof(changed, syms, insns, addrs)

        rejects("scalar level clobber " + op, check_scalar)
        rejects("scalar stack-pointer write " + op, lambda op=op: fixture({"root": [(op, "%eax,%esp"), ("ret", "")]}))
    # GCC16 uses a direct stack spill and an untouched shrink-wrapped return.
    # Prove the carrier value, not a compiler-specific prologue byte sequence.
    spill_walk = [
        ("sub", "$0x18,%rsp"),
        ("test", "%eax,%eax"),
        ("je", "@" + WALK + "+13"),
        ("mov", "%r15,0x10(%rsp)"),
        ("mov", "%ecx,%r15d"),
        ("nop", ""),
        ("test", "%r15d,%r15d"),
        ("je", "@" + WALK + "+10"),
        ("lea", "-0x1(%r15),%ecx"),
        ("call", "@" + WALK),
        ("mov", "0x10(%rsp),%r15"),
        ("add", "$0x18,%rsp"),
        ("ret", ""),
        ("add", "$0x18,%rsp"),
        ("ret", ""),
    ]

    def check_spill(rows, helper=None):
        graph = {"root": [("mov", "$0x3,%ecx"), ("call", "@" + WALK), ("ret", "")], WALK: rows}
        if helper is not None:
            graph["helper"] = helper
        funcs, syms, insns, addrs = fixture(graph)
        level_bodies, _ = recursion_proof(funcs, syms, insns, addrs)
        return calculate(funcs, {}, level_bodies, "root")

    for carrier, family in CALLEE_SAVED_REGISTERS.items():
        changed_rows = [(op, args.replace("%r15d", family[1]).replace("%r15", carrier)) for op, args in spill_walk]
        require(check_spill(changed_rows)["peak"] == 136, "Wrong shrink-wrapped carrier proof: " + carrier)
        positives += 1
    disjoint = list(spill_walk)
    disjoint[5] = ("movb", "$0x0,0xf(%rsp)")
    require(check_spill(disjoint)["peak"] == 136, "Disjoint byte store changed saved carrier")
    positives += 1
    relocated = list(spill_walk)
    relocated[2] = ("je", "@" + WALK + "+14")
    relocated[10:13] = [
        ("sub", "$0x8,%rsp"),
        ("mov", "0x18(%rsp),%r15"),
        ("add", "$0x20,%rsp"),
        ("ret", ""),
    ]
    require(check_spill(relocated)["peak"] == 144, "Saved carrier slot was not entry-RSP relative")
    positives += 1
    for label, index, op, operands in (
        ("spill bypasses save", 2, "je", "@" + WALK + "+4"),
        ("spill bypasses restore", 7, "je", "@" + WALK + "+11"),
        ("wrong spill source", 3, "mov", "%r14,0x10(%rsp)"),
        ("partial spill source", 3, "mov", "%r15d,0x10(%rsp)"),
        ("wrong spill restore", 10, "mov", "0x8(%rsp),%r15"),
        ("partial spill restore", 10, "mov", "0x10(%rsp),%r15d"),
        ("partial carrier clobber", 5, "mov", "$0x0,%r15b"),
        ("carrier exchange source", 5, "xchg", "%r15,%rax"),
        ("carrier exchange destination", 5, "xchg", "%rax,%r15"),
        ("conditional carrier clobber", 5, "cmovns", "%rax,%r15"),
        ("full spill overwrite", 5, "mov", "%rax,0x10(%rsp)"),
        ("first-byte spill overlap", 5, "mov", "%rax,0x9(%rsp)"),
        ("last-byte spill overlap", 5, "movb", "$0x0,0x17(%rsp)"),
        ("unknown-width stack write", 5, "xor", "$0x0,0x10(%rsp)"),
        ("stack exchange first operand", 5, "xchg", "0x10(%rsp),%rax"),
        ("stack address LEA escape", 5, "lea", "0x10(%rsp),%rax"),
        ("stack address MOV escape", 5, "mov", "%rsp,%rdi"),
        ("indexed stack write", 5, "mov", "%rax,(%rsp,%rcx,1)"),
        ("out-of-frame spill", 3, "mov", "%r15,0x18(%rsp)"),
        ("out-of-frame store", 5, "mov", "%rax,0x18(%rsp)"),
        ("implicit repeated memory write", 5, "rep", "stos %al,%es:(%rdi)"),
        ("arbitrary nonlocal store", 5, "movq", "$0xff,(%rdi)"),
        ("arbitrary indexed nonlocal store", 5, "movb", "$0x1,(%rdi,%rax,1)"),
        ("nonlocal memory exchange", 5, "xchg", "%rax,(%rdi)"),
        ("nonlocal exchange source", 5, "xchg", "(%rdi),%rax"),
        ("segment nonlocal store", 5, "movq", "$0x3,%fs:(%rax)"),
        ("segment memory exchange", 5, "xchg", "%fs:(%rax),%rax"),
        ("duplicate carrier initialization", 5, "mov", "%ecx,%r15d"),
        ("ambiguous second level carrier", 5, "mov", "%ecx,%r14d"),
    ):
        changed_rows = list(spill_walk)
        changed_rows[index] = (op, operands)
        rejects(label, lambda changed_rows=changed_rows: check_spill(changed_rows))
    calls_helper = list(spill_walk)
    calls_helper[5] = ("call", "@helper")
    require(check_spill(calls_helper, [("ret", "")])["peak"] == 144, "Carrier-neutral helper changed spill proof")
    positives += 1
    for operands in ("%eax,%r15d", "$0x0,%r15w", "%r15,%rax"):
        op = "xchg" if operands == "%r15,%rax" else "mov"
        rejects(
            "helper carrier clobber " + operands,
            lambda op=op, operands=operands: check_spill(calls_helper, [(op, operands), ("ret", "")]),
        )
    for operands in ("$0x3,0x8(%rsp)", "$0x3,(%rax)", "$0x3,0x12345678", "$0x3,%fs:(%rax)"):
        rejects(
            "helper memory clobber " + operands,
            lambda operands=operands: check_spill(calls_helper, [("movq", operands), ("ret", "")]),
        )
    bxcalls = [(op, args.replace("%r15d", "%ebx").replace("%r15", "%rbx")) for op, args in calls_helper]
    rejects("helper implicit RBX clobber", lambda: check_spill(bxcalls, [("cpuid", ""), ("ret", "")]))
    bxclobber = [(op, args.replace("%r15d", "%ebx").replace("%r15", "%rbx")) for op, args in spill_walk]
    bxclobber[5] = ("cpuid", "")
    rejects("implicit RBX carrier clobber", lambda: check_spill(bxclobber))

    source_signature = "PageTables::verify::<lambda(auto:1&&, uint64_t, unsigned int, uint64_t)>"
    source_row = dict(
        object="payload.o",
        callgraph="payload.ci",
        source="kernel/uefi/tables.hpp",
        source_sha256=VERIFIER_SOURCE_PINS["kernel/uefi/tables.hpp"],
        line=166,
        column=27,
        record=source_signature,
        bytes=96,
        kind="static",
    )
    bound_source = {WALK: [source_row]}
    verifier_source_contract(bound_source, dict(VERIFIER_SOURCE_PINS))
    positives += 1
    runtime_source = dict(
        source_row, object="runtime.o", callgraph="runtime.ci", record=source_signature.replace("auto:1", "auto:2")
    )
    retained = verifier_source_contract({WALK: [source_row, runtime_source]}, dict(VERIFIER_SOURCE_PINS))
    require(
        [row["record"] for row in retained["compiler_records"]] == [source_row["record"], runtime_source["record"]],
        "Source contract normalized the full compiler signatures",
    )
    positives += 1
    for name in VERIFIER_SOURCE_PINS:
        drifted = dict(VERIFIER_SOURCE_PINS)
        drifted[name] = "0" * 64
        rejects(
            "reviewed source drift " + name, lambda drifted=drifted: verifier_source_contract(bound_source, drifted)
        )
    rejects("missing WALK source binding", lambda: verifier_source_contract({}, dict(VERIFIER_SOURCE_PINS)))
    for field, changed in (
        ("source", "kernel/uefi/payload.cpp"),
        ("source_sha256", "0" * 64),
        ("line", 167),
        ("column", 28),
        ("object", "invented.o"),
        ("callgraph", "other.ci"),
        ("kind", "dynamic,bounded"),
    ):
        row = dict(source_row, **{field: changed})
        rejects(
            "marker source identity " + field,
            lambda row=row: verifier_source_contract({WALK: [row]}, dict(VERIFIER_SOURCE_PINS)),
        )
    marker_rows = [
        ("cmpb", "$0x0,(%rdx,%rax,1)"),
        ("jne", "@marker+4"),
        ("movb", "$0x1,(%rdx,%rax,1)"),
        ("ret", ""),
        ("ret", ""),
    ]

    def check_marker(rows, bind=True):
        _, syms, insns, addrs = fixture({"marker": rows})
        admitted = trusted_verifier_marker_stores(list(insns.values()))
        if admitted:
            verifier_source_contract(bound_source if bind else {}, dict(VERIFIER_SOURCE_PINS))
        prove_carrier_preserved(syms["marker"], insns, addrs, "%r15", admitted)
        return admitted

    require(check_marker(marker_rows) == frozenset((2,)), "Source-bound byte marker was not admitted")
    positives += 1
    rejects("marker without source contract", lambda: check_marker(marker_rows, bind=False))
    for label, index, op, operands in (
        ("wider marker store", 2, "movq", "$0x1,(%rdx,%rax,1)"),
        ("different marker value", 2, "movb", "$0x2,(%rdx,%rax,1)"),
        ("missing marker zero test", 0, "test", "%eax,%eax"),
        ("mismatched marker zero test", 0, "cmpb", "$0x0,(%rdi,%rax,1)"),
        ("changed marker guard", 1, "je", "@marker+4"),
        ("guard enters marker", 1, "jne", "@marker+2"),
        ("extra nonlocal store", 3, "movb", "$0x2,(%rdi)"),
        ("duplicate marker store", 3, "movb", "$0x1,(%rdx,%rax,1)"),
        ("marker stack-base destination", 2, "movb", "$0x1,(%rsp,%rax,1)"),
    ):
        rows = list(marker_rows)
        rows[index] = (op, operands)
        rejects(label, lambda rows=rows: check_marker(rows))
    # An otherwise matched source-bound marker must not inherit an escaped
    # address of its own frame. The local proof rejects that escape first.
    stack_marker = [
        ("lea", "(%rsp),%rdx"),
        ("cmpb", "$0x0,(%rdx,%rax,1)"),
        ("jne", "@marker+5"),
        ("movb", "$0x1,(%rdx,%rax,1)"),
        ("ret", ""),
        ("ret", ""),
    ]
    rejects("stack-derived marker destination", lambda: check_marker(stack_marker))

    # An invented compiler bound must never disappear from path arithmetic.
    require(calculate(bodies, {"root": 256}, {}, "root")["peak"] == 256, "Compiler frame upper bound was ignored")
    positives += 1
    unknown = deepcopy(bodies)
    unknown["root"]["calls"][0]["target"] = "missing"
    rejects("unassociated helper", lambda: calculate(unknown, {}, {}, "root"))
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
    print(f"PASS: owned-byte linked stack proof, {positives} positives and {rejected} negative controls")


def main():
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        return
    if len(sys.argv) != 3:
        raise SystemExit("Expected artifact-directory output.json or --self-test")
    directory, output = map(Path, sys.argv[1:])
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
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, struct.error) as error:
        raise SystemExit("FAIL: owned-byte stack admission: " + str(error)) from error
