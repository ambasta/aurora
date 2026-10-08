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
        "_ZN12_GLOBAL__N_14failESt17basic_string_viewIcSt11char_traitsIcEE",
    )
)


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
        instructions[address] = Instruction(address, len(raw.split()), op, args.split("#", 1)[0].strip())
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


def frame_identity(signature):
    if "PageTables::verify(" in signature and ("<lambda(" in signature or "{lambda(" in signature):
        return WALK
    if "RuntimeLayoutProfile" in signature and "::valid(" in signature:
        return "aurora::uefi::RuntimeLayoutProfile::valid"
    signature = signature.replace("(anonymous namespace)", "{anonymous}")
    match = re.search(r"([\w:{}~]+)\(", signature)
    require(match, "Unknown compiler frame signature: " + signature)
    name = match[1]
    aliases = {"payload_main": "uefi_payload_main", "payload_fail": "uefi_payload_fail"}
    if name.startswith("aurora::hosted::bytes::__au_runtime_bytes_"):
        name = name.rsplit("::", 1)[1]
    return aliases.get(name, name)


def stack_rows(text):
    rows = {}
    for line in text.splitlines():
        fields = line.rsplit("\t", 2)
        require(len(fields) == 3, "Malformed compiler stack record")
        signature, size, kind = fields
        signature = re.sub(r"^.*?:\d+:\d+:", "", signature)
        require(kind == "static", "Unbounded or dynamic compiler frame: " + signature)
        require(re.fullmatch(r"[0-9]+", size), "Invalid compiler frame size")
        require(8 <= int(size) <= STACK_CAP, "Invalid compiler frame bound")
        identity = frame_identity(signature)
        require(identity not in rows, "Ambiguous compiler stack record: " + identity)
        rows[identity] = (int(size), signature)
    return rows


def cpp_frames(directory, linked):
    associated = {}
    receipts = {}
    for name in CPP_OBJECTS:
        obj = Elf(directory / (name + ".o"))
        require(obj.type == 1, "Expected relocatable C++ object")
        rows = stack_rows((directory / (name + ".su")).read_text())
        names = list(obj.functions)
        demangled = command("c++filt", *names).splitlines() if names else []
        require(len(names) == len(demangled), "Demangler record mismatch")
        used = set()
        for symbol_name, spelling in zip(names, demangled):
            identity = frame_identity(spelling) if symbol_name.startswith("_Z") else symbol_name
            require(identity in rows, "Missing exact compiler frame: " + symbol_name)
            require(identity not in used, "Ambiguous object/frame association: " + identity)
            used.add(identity)
            size, signature = rows[identity]
            require(8 <= size <= STACK_CAP, "Invalid compiler frame bound")
            require(symbol_name in linked.functions, "Object function omitted from linked profile")
            associate_object(linked, obj, obj.functions[symbol_name])
            if symbol_name in associated:
                require(associated[symbol_name] == size, "Conflicting COMDAT compiler frames")
            associated[symbol_name] = size
            receipts.setdefault(symbol_name, []).append({"object": name + ".o", "record": signature, "bytes": size})
        require(used == set(rows), "Stack records lack exact object definitions: " + name)
    return associated, receipts


BRANCHES = frozenset("ja jae jb jbe je jne jge jg jl jle jns js jo jno jp jnp jz jnz jmp".split())
# Stack-neutral instructions admitted by this bounded x86-64 profile. Unknown
# instruction semantics, implicit stack operations, calls and returns fail shut.
NEUTRAL = frozenset(
    (
        "add addl addq and bt cld cli cmova cmovae cmovbe cmove cmovne cmp cmpb cmpl cmpq cmpw cpuid cs data16 "
        "dec div hlt imul in inc invlpg lea mov movabs movb movl movq movslq movzbl movzbq mul neg nop nopl nopw "
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


def tracked_register(operand):
    if operand in ("%rcx", "%ecx", "%cx", "%cl", "%ch"):
        return 0
    if operand in ("%r14", "%r14d", "%r14w", "%r14b"):
        return 1
    return None


def arguments(text):
    return re.split(r",(?![^()]*\))", text)


def analyze_function(symbol, instructions, starts, seed=None, fault=False):
    """CFG fixed point. Different stack depths at a join reject growing loops.

    Tiny constant propagation is deliberately restricted to the verifier level
    argument (%ecx) and its callee-saved carrier (%r14d). Every unrecognized write
    kills a fact. Calls kill %ecx. No data-dependent loop trip count is assumed.
    """
    begin, end = symbol.address, symbol.address + symbol.size
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
            destination = tracked_register(args[-1])
            if destination is not None:
                value = None
                if (
                    op in ("mov", "movl", "movq", "movabs")
                    and len(args) == 2
                    and args[1] in ("%rcx", "%ecx", "%r14", "%r14d")
                ):
                    source = tracked_register(args[0])
                    if source is not None and args[0] in ("%rcx", "%ecx", "%r14", "%r14d"):
                        value = old[source]
                    elif re.fullmatch(r"\$(?:0x[0-9a-f]+|[0-9]+)", args[0]):
                        immediate = int(args[0][1:], 0)
                        value = immediate if immediate <= 3 else None
                if (
                    op == "lea"
                    and len(args) == 2
                    and args[0] == "-0x1(%r14)"
                    and args[1] in ("%rcx", "%ecx", "%r14", "%r14d")
                    and old[1] is not None
                ):
                    value = old[1] - 1
                values[destination] = value
        if op in ("cpuid", "rep"):
            values[0] = None
        if op == "xchg":
            for operand in args:
                register = tracked_register(operand)
                if register is not None:
                    values[register] = None
                if operand in ("%rbp", "%ebp", "%bp", "%bpl"):
                    bp = None
        if op == "test" and len(args) == 2 and args[0] == args[1]:
            register = tracked_register(args[0])
            if register is not None and args[0] in ("%rcx", "%ecx", "%r14", "%r14d") and old[register] is not None:
                next_zf = old[register] == 0
        if op in ("push", "pushf"):
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
    return dict(
        local_peak=peaks,
        calls=sorted(calls.values(), key=lambda row: row["address"]),
        instructions=len(visited),
        returns=returns,
        push_peak=push_peak,
    )


def recursion_proof(functions, symbols, instructions, starts):
    require(WALK in functions, "Missing four-level page verifier")
    symbol = symbols[WALK]
    body_code = [
        instructions[address]
        for address in sorted(instructions)
        if symbol.address <= address < symbol.address + symbol.size
    ]
    saves = ["%r15", "%r14", "%r13", "%r12", "%rbp", "%rbx"]
    ordinary = [("push", register) for register in saves]
    interleaved = ordinary[:2] + [("mov", "%ecx,%r14d")] + ordinary[2:]
    # GCC's framebuffer-aware body moves the level after saving r14, before
    # the remaining four saves. Both exact sequences preserve the same carrier;
    # all restoration, clobber, entry-level and decrement checks below remain.
    require(
        [(row.op, row.args) for row in body_code[:6]] == ordinary
        or [(row.op, row.args) for row in body_code[:7]] == interleaved,
        "Verifier level carrier lacks exact callee-saved prologue",
    )
    restored = [("pop", register) for register in reversed(saves)]
    for index, insn in enumerate(body_code):
        if insn.op == "ret":
            require(
                index >= 6 and [(row.op, row.args) for row in body_code[index - 6 : index]] == restored,
                "Verifier level carrier lacks exact return restoration",
            )
        args = arguments(insn.args)
        if args and args[-1] in ("%r14", "%r14d", "%r14w", "%r14b") and insn.op not in READ_ONLY:
            require(
                (insn.op, insn.args) in (("push", "%r14"), ("mov", "%ecx,%r14d"), ("pop", "%r14")),
                "Unknown write to recursive level carrier",
            )
        require(
            not (insn.op == "xchg" and any("r14" in arg for arg in args)), "Exchange clobbers recursive level carrier"
        )
    for call in functions[WALK]["calls"]:
        if call["target"] not in (None, WALK):
            leaf = symbols[call["target"]]
            require(not functions[call["target"]]["calls"], "Verifier helper is no longer a proven leaf")
            require(
                not any(
                    "r14" in row.args
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
        body = analyze_function(symbols[WALK], instructions, starts, seed=level)
        recursive = [row for row in body["calls"] if row["target"] == WALK]
        if level == 0:
            require(not recursive, "Page verifier recurses at level zero")
        else:
            require(
                len(recursive) == 1 and recursive[0]["kind"] == "call" and recursive[0]["level"] == level - 1,
                "Page verifier lacks strictly decreasing bounded level",
            )
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
    elf = Elf(directory / "payload.elf")
    require(elf.type == 2, "Expected linked executable payload")
    require(not command("nm", "-u", str(directory / "payload.elf")).strip(), "Unresolved linked payload symbol")
    admission = load_admission().validate_symbols(command("nm", "-a", str(directory / "language.o")))
    instructions, disassembly = disassemble(directory / "payload.elf")
    starts = {symbol.address: name for name, symbol in elf.functions.items()}
    require(len(starts) == len(elf.functions), "Ambiguous linked function aliases")
    frames, associations = cpp_frames(directory, elf)
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
    levels, roots = recursion_proof(functions, elf.functions, instructions, starts)
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
    files += [name + suffix for name in CPP_OBJECTS for suffix in (".o", ".su")]
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
    # An invented compiler bound must never disappear from path arithmetic.
    require(calculate(bodies, {"root": 256}, {}, "root")["peak"] == 256, "Compiler frame upper bound was ignored")
    positives += 1
    unknown = deepcopy(bodies)
    unknown["root"]["calls"][0]["target"] = "missing"
    rejects("unassociated helper", lambda: calculate(unknown, {}, {}, "root"))
    stack_row = "source.cpp:1:1:void function()\t16\tstatic"
    require(stack_rows(stack_row)["function"][0] == 16, "Compiler record association failed")
    positives += 1
    for mutant in (
        stack_row.replace("static", "dynamic"),
        stack_row.replace("static", "dynamic,bounded"),
        stack_row.replace("16", "-1"),
        stack_row.replace("16", "0"),
        stack_row.replace("16", "32768"),
        stack_row + "\n" + stack_row,
        "malformed",
        stack_row.replace("function()", "???"),
    ):
        rejects("compiler record mutation", lambda mutant=mutant: stack_rows(mutant))

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
