#!/usr/bin/env python3
"""Exact object binding and compiler-fact stack graphs for kernel admission.

Aurora and GCC metadata are trusted compiler output. Only explicit handwritten
entry, bridge, memory and fault assembly uses instruction-level stack checks.
"""

from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CPP_OBJECTS = ("payload", "acpi", "pci", "runtime", "owned-bytes-runtime", "owned-bytes-profile")
STACK_BYTES = 16384
STACK_CAP = 15360
FAULT_RESERVE = 512
NORETURN = frozenset()
OWNED_NORETURN = frozenset(
    (
        "__au_runtime_bytes_kernel_fault",
        "uefi_payload_fail",
        "_ZN6aurora6kernel5bytes6Region6retainERNS2_10AllocationE",
    )
)
BRANCHES = frozenset("ja jae jb jbe je jne jge jg jl jle jns js jo jno jp jnp jz jnz jmp".split())
NEUTRAL = frozenset(
    (
        "add and cld cli cmp cmpq dec hlt inc lea mov movabs movb movq movslq movzbl "
        "nop nopl nopw or rep sub test ud2 xor"
    ).split()
)
READ_ONLY = frozenset("cmp cmpq test".split())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def is_reflection_helper(name):
    return re.fullmatch(r"(?:aurora_reflect_|__au_reflect_s[1-9][0-9]*_)(?:size|field_count)", name) is not None


def reflection_inventory(names):
    helpers = {name for name in names if name.startswith(("aurora_reflect_", "__au_reflect_"))}
    require({"aurora_reflect_size", "aurora_reflect_field_count"} <= helpers, "Missing root reflection helpers")
    require(all(is_reflection_helper(name) for name in helpers), "Unknown reflection helper")
    for name in helpers:
        stem = name.removesuffix("field_count").removesuffix("size")
        require({stem + "size", stem + "field_count"} <= helpers, "Incomplete reflection helper pair")
    return helpers


def aurora_module(name):
    """Read only the exact length-delimited source module from a private symbol."""
    head = re.match(r"__au_[vkmf]_m([1-9][0-9]*)_", name)
    if not head:
        return None
    cursor, parts = head.end(), []
    for _ in range(int(head[1])):
        length = re.match(r"[1-9][0-9]*", name[cursor:])
        if not length:
            return None
        cursor += length.end()
        component = name[cursor : cursor + int(length[0])]
        if len(component) != int(length[0]) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", component):
            return None
        parts.append(component)
        cursor += len(component)
    return ".".join(parts) if name[cursor:].startswith("_n") else None


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
        self.symbol_tables = {}
        for section_index, section in enumerate(self.sections):
            if section[1] == 2:
                strings = self.section_data(section[6])
                self.symbol_tables[section_index] = table = []
                require(section[9] == 24, "Unsupported symbol table")
                for pos in range(section[4], section[4] + section[5], 24):
                    name, info, _, index, value, size = struct.unpack_from("<IBBHQQ", self.data, pos)
                    end = strings.find(b"\0", name)
                    require(end >= name, "Invalid symbol string")
                    symbol = Symbol(strings[name:end].decode(), value, size, index, info & 15)
                    self.symbols.append(symbol)
                    table.append(symbol)
            if section[1] == 4:
                require(section[9] == 24, "Unsupported relocation table")
                for pos in range(section[4], section[4] + section[5], 24):
                    address, info, addend = struct.unpack_from("<QQq", self.data, pos)
                    self.relocations.append((section[7], address, info & 0xFFFFFFFF, info >> 32, addend))
        self.comdat = {}
        self.relocation_symbols = {}
        for section_index, section in enumerate(self.sections):
            if section[1] == 17:  # SHT_GROUP: only actual same-signature COMDAT may select a variant.
                raw = self.section_data(section_index)
                require(len(raw) >= 8 and len(raw) % 4 == 0, "Malformed ELF section group")
                flags, *members = struct.unpack("<" + "I" * (len(raw) // 4), raw)
                require(flags == 1, "Unsupported ELF section group")
                signature = self.symbol_tables[section[6]][section[7]].name
                require(signature, "Unnamed COMDAT signature")
                for member in members:
                    require(
                        0 < member < len(self.sections)
                        and member not in self.comdat
                        and self.sections[member][2] & 0x200,
                        "Invalid COMDAT member",
                    )
                    self.comdat[member] = signature
            if section[1] == 4:
                for pos in range(section[4], section[4] + section[5], 24):
                    address, info, _ = struct.unpack_from("<QQq", self.data, pos)
                    self.relocation_symbols[section[7], address] = self.symbol_tables[section[6]][info >> 32]
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


def relocation_matches(linked, obj, reference, address):
    """Bind a COMDAT witness's relocation target, including merged local constants."""
    if not reference.section or reference.kind == 2:
        targets = {row.address for row in linked.symbols if row.section and row.name == reference.name}
        return targets == {address}
    section = obj.sections[reference.section]
    # Named writable objects must retain their linked identity. Local read-only
    # constants may be merged/renamed by ld: compare the exact bounded contents.
    if section[2] & 1:
        targets = {row.address for row in linked.symbols if row.section and row.name == reference.name}
        return targets == {address}
    require(section[1] == 1 and section[2] & 2, "Unsupported COMDAT relocation target")
    contents = obj.section_data(reference.section)
    size = reference.size
    if not size and section[2] & 0x20 and section[9] == 1:
        end = contents.find(b"\0", reference.address)
        require(end >= reference.address, "Unterminated COMDAT string target")
        size = end + 1 - reference.address
    require(size > 0 and reference.address + size <= len(contents), "Unbounded COMDAT constant target")
    require(
        not any(
            sec == reference.section and reference.address <= off < reference.address + size
            for sec, off, *_ in obj.relocations
        ),
        "Relocated COMDAT constant is unsupported",
    )
    expected = contents[reference.address : reference.address + size]
    installed = [
        linked.section_data(index)[address - row[3] : address - row[3] + size]
        for index, row in enumerate(linked.sections)
        if row[1] == 1 and row[2] & 2 and not row[2] & 1 and row[3] <= address and address + size <= row[3] + row[5]
    ]
    return installed == [expected]


def object_matches(linked, obj, symbol, *, relocation_targets=False):
    target = linked.functions[symbol.name]
    if target.size != symbol.size:
        return False
    expected = bytearray(obj.function_bytes(symbol))
    actual = bytearray(linked.function_bytes(target))
    for section, address, kind, _, addend in obj.relocations:
        if section == symbol.section and symbol.address <= address < symbol.address + symbol.size:
            require(kind in (2, 4), "Unsupported text relocation")
            offset = address - symbol.address
            require(offset + 4 <= len(expected), "Relocation crosses function boundary")
            if relocation_targets:
                # Both admitted relocations encode S + A - P in a signed rel32.
                resolved = (
                    target.address
                    + offset
                    + int.from_bytes(actual[offset : offset + 4], "little", signed=True)
                    - addend
                )
                if not relocation_matches(linked, obj, obj.relocation_symbols[section, address], resolved):
                    return False
            expected[offset : offset + 4] = actual[offset : offset + 4] = b"\0" * 4
    return expected == actual


def associate_object(linked, obj, symbol):
    """Only relocation slots may differ between the object and linked body."""
    require(object_matches(linked, obj, symbol), "Object/link instruction mismatch: " + symbol.name)


def compiler_witnesses(linked, name, candidates):
    """Discarded same-signature COMDAT definitions are not linked frame witnesses."""
    duplicate = len(candidates) > 1
    if duplicate:
        signatures = {obj.comdat.get(obj.functions[name].section) for obj, _, _ in candidates}
        require(len(signatures) == 1 and None not in signatures, "Duplicate function is not one COMDAT group: " + name)
    matched = [
        (obj, row, calls)
        for obj, row, calls in candidates
        if object_matches(linked, obj, obj.functions[name], relocation_targets=duplicate)
    ]
    require(matched, "Object/link instruction mismatch: " + name)
    require(len({row.size for _, row, _ in matched}) == 1, "Conflicting matched COMDAT compiler frames")
    require(all(calls == matched[0][2] for _, _, calls in matched), "Conflicting matched COMDAT compiler edges")
    return matched


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


def callgraph_frames(text, rows, symbols, source, edges=None, compile_directory=None):
    """Join .su to exact assembler names from GCC's per-object .ci nodes.

    Compiler edges feed shared graph accounting and must match linked direct
    transfers. Unknown node formats or many-to-one clone/location associations
    fail closed rather than guessing a display name.
    """
    quoted = r'"(?:[^"\\]|\\["\\n])*"'
    lines = text.splitlines()
    require(len(lines) >= 2 and lines[-1] == "}", "Malformed compiler callgraph")
    header = re.fullmatch(r"graph: \{ title: (" + quoted + r")", lines[0])
    require(header, "Malformed compiler callgraph source")
    reported_source = json.loads(header[1])
    actual_source = (
        str((compile_directory / reported_source).resolve(strict=True)) if compile_directory else reported_source
    )
    require(actual_source == source, "Compiler callgraph source mismatch")
    associated, used, titles, calls = {}, set(), set(), set()

    def assembler_name(title):
        return title.removeprefix(reported_source + ":").removeprefix("*")

    for line in lines[1:-1]:
        if line.startswith("edge:"):
            edge = re.fullmatch(
                r"edge: \{ sourcename: (" + quoted + r") targetname: (" + quoted + r")(?: label: " + quoted + r")? \}",
                line,
            )
            require(edge, "Malformed compiler callgraph edge")
            calls.add(tuple(json.loads(value) for value in edge.groups()))
            continue
        node = re.fullmatch(r"node: \{ title: (" + quoted + r") label: (" + quoted + r")( shape : ellipse)? \}", line)
        require(node, "Malformed compiler callgraph node")
        title, label = json.loads(node[1]), json.loads(node[2])
        require(title not in titles, "Duplicate compiler callgraph symbol")
        titles.add(title)
        name = assembler_name(title)
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
    if edges is not None:
        require(
            all(a in titles and b in titles and assembler_name(a) in associated for a, b in calls),
            "Compiler edge lacks a defined caller or declared target",
        )
        edges.update((assembler_name(a), assembler_name(b)) for a, b in calls)
    return associated


def object_source(directory, name, source_root=None):
    """Bind native exports to one compile, never infer ownership by basename."""
    root = Path(source_root or ROOT).resolve(strict=True)
    directory = Path(directory).absolute()
    require(directory.resolve(strict=True) == directory, "Noncanonical or symlinked profile directory")
    source = {
        "owned-bytes-runtime": "kernel/owned-bytes.cpp",
        "owned-bytes-profile": "kernel/uefi/owned-bytes.cpp",
    }.get(name, "kernel/uefi/" + name + ".cpp")
    record = directory / "objects" / (name + ".source.json")
    native = directory.parent.name == "uefi" and directory.parent.parent.name == "kernel-images"
    if not native and not record.exists():
        return source, root
    require(native, "Native object association requires its original profile directory")
    require(record.resolve(strict=True).is_relative_to(directory), "Native source record escaped profile")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate native source record key")
            result[key] = value
        return result

    association = json.loads(record.read_text(), object_pairs_hook=unique)
    require(
        type(association) is dict and set(association) == {"source", "compile_directory", "native_object", "sidecars"},
        "Unexpected native source record",
    )
    require(
        all(type(association[key]) is str for key in ("source", "compile_directory", "native_object")),
        "Invalid native compile path",
    )
    expected = (root / source).resolve(strict=True)
    require(
        expected.is_relative_to(root / "kernel") and association["source"] == str(expected),
        "Native translation unit/source ownership mismatch",
    )
    compile_directory = directory.parents[2]
    require(association["compile_directory"] == str(compile_directory), "Foreign native compiler working directory")
    original = Path(association["native_object"])
    require(
        original.is_absolute()
        and original.resolve(strict=True) == original
        and original.is_relative_to(directory / "native")
        and original.suffix == ".o",
        "Native object escaped selected profile",
    )
    require(
        type(association["sidecars"]) is dict
        and association["sidecars"] == {suffix: str(original.with_suffix("." + suffix)) for suffix in ("su", "ci")},
        "Native metadata is not from the exact object compilation",
    )
    for suffix in (".o", ".su", ".ci"):
        actual = original.with_suffix(suffix)
        exported = directory / "objects" / (name + suffix)
        require(
            actual.resolve(strict=True) == actual and exported.resolve(strict=True) == exported,
            "Symlinked native object/sidecar",
        )
        require(actual.read_bytes() == exported.read_bytes(), "Changed native object/sidecar export: " + name + suffix)
    return str(expected), compile_directory


def object_stack_rows(directory, name, symbols, edges=None, source_root=None, allow_bounded=None):
    source, compile_directory = object_source(directory, name, source_root)
    text = (directory / "objects" / (name + ".su")).read_text()
    rows = stack_rows(text, allow_bounded) if allow_bounded else stack_rows(text)
    native = Path(source).is_absolute()
    associated = callgraph_frames(
        (directory / "objects" / (name + ".ci")).read_text(),
        rows,
        symbols,
        source,
        edges,
        compile_directory if native else None,
    )
    if native:
        root = Path(source_root or ROOT).resolve(strict=True)
        normalized, identities = {}, set()
        for name, row in associated.items():
            location = (compile_directory / row.source).resolve(strict=True)
            require(location.is_relative_to(root / "kernel"), "Compiler frame outside selected kernel sources")
            normalized[name] = replace(row, source=location.relative_to(root).as_posix())
            require(normalized[name].identity not in identities, "Aliased native compiler source record")
            identities.add(normalized[name].identity)
        return normalized
    return associated


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


def cpp_frames(directory, linked, objects=None, edges=None, source_root=None, allow_bounded=None):
    candidates, receipts, associated = {}, {}, {}
    root = Path(source_root or ROOT).resolve(strict=True)
    for name in CPP_OBJECTS if objects is None else objects:
        obj = Elf(directory / "objects" / (name + ".o"))
        require(obj.type == 1, "Expected relocatable C++ object")
        calls = set()
        rows = object_stack_rows(directory, name, obj.functions, calls, root, allow_bounded)
        for symbol, row in rows.items():
            require(symbol in linked.functions, "Object function omitted from linked profile")
            candidates.setdefault(symbol, []).append((obj, row, {(a, b) for a, b in calls if a == symbol}))
    for symbol, variants in candidates.items():
        matched = compiler_witnesses(linked, symbol, variants)
        associated[symbol] = matched[0][1].size
        if edges is not None:
            edges.update(matched[0][2])
        for obj, row, _ in matched:
            source = (root / row.source).resolve()
            require(source.is_relative_to(root / "kernel"), "Compiler frame outside kernel source inventory")
            contents = source.read_bytes()
            lines = contents.decode().splitlines()
            require(row.line <= len(lines) and row.column <= len(lines[row.line - 1]) + 1, "Invalid frame location")
            receipts.setdefault(symbol, []).append(
                {
                    "object": obj.path.name,
                    "callgraph": obj.path.with_suffix(".ci").name,
                    "compiler_symbol": symbol,
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


def target_of(insn):
    match = re.fullmatch(r"([0-9a-f]+) <([^>]+)>", insn.args)
    require(match, "Indirect or unresolved control transfer at " + hex(insn.address))
    return int(match[1], 16)


def arguments(text):
    return re.split(r",(?![^()]*\))", text)


def analyze_function(symbol, instructions, starts, fault=False):
    """Handwritten assembly only; mismatched stack depths at a join reject."""
    begin, end = symbol.address, symbol.address + symbol.size
    states = {begin: (0, None)}  # Consumed bytes and saved frame-pointer depth.
    queue = deque([begin])
    peaks = 8
    calls = {}
    visited = set()
    returns = 0

    def schedule(address, state):
        require(begin <= address < end, "Unmodeled function fallthrough: " + symbol.name)
        require(address in instructions, "Control flow enters non-instruction")
        prior = states.get(address)
        if prior is not None:
            require(prior == state, "Inconsistent or unbounded stack at CFG join: " + symbol.name)
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
        depth, bp = states[address]
        op, args = insn.op, arguments(insn.args)
        for operand in args:
            if "%rsp" in operand and "(" in operand:
                require(not re.search(r"-[^()]*\(%rsp", operand), "Unproven below-stack access")
            if bp is not None:
                local = re.fullmatch(r"-(0x[0-9a-f]+|[0-9]+)\(%rbp\)", operand)
                if local:
                    require(bp + int(local[1], 0) <= depth, "Frame access below allocated stack")
        if op == "rep":
            require(
                insn.args
                in (
                    "movsb %ds:(%rsi),%es:(%rdi)",
                    "stos %al,%es:(%rdi)",
                ),
                "Unsupported repeated instruction",
            )
        if op == "push":
            require(
                re.fullmatch(r"%r(?:ax|bx|cx|dx|si|di|bp|[89]|1[0-5])", insn.args),
                "Unsupported handwritten push operand",
            )
            depth += 8
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
        state = (depth, bp)
        if op == "call" or op in BRANCHES:
            target = target_of(insn)
            require(target in instructions, "Transfer to non-instruction")
            if op != "call" and begin <= target < end:
                schedule(target, state)
            elif instructions[target].op == "ud2" and op != "call":
                calls[address] = dict(address=address, target=None, kind="trap", live_bytes=8 + depth)
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
                )
            if op == "call" and starts.get(target) in NORETURN:
                continue
            if op != "jmp":
                schedule(insn.next, state)
            continue
        require(op in NEUTRAL or op in ("push", "pop", "leave"), "Unknown instruction semantics: " + op)
        if op == "ud2":
            continue
        if insn.next == end and symbol.name == "uefi_payload_page_fault":
            require(starts.get(end) == "fault_common", "Unexpected page-fault fallthrough")
            calls[address] = dict(address=address, target="fault_common", kind="tail", live_bytes=0)
        else:
            schedule(insn.next, state)
    result = dict(
        local_peak=peaks,
        calls=sorted(calls.values(), key=lambda row: row["address"]),
        instructions=len(visited),
        returns=returns,
    )
    return result


def cpp_stack_functions(symbols, code, starts, payload, frames, edges, internal_jumps=(), callbacks=None):
    """Trust GCC frame/call facts; cross-check direct transfers, not C++ semantics.

    Retain the full frame at every call AND tail call. GCC does not account for
    the reviewed inline PUSHFQ/POP pair, so add eight bytes to its owner's bound.
    Compiler-generated stack adjustments, register choices and local CFG are
    trusted. Reviewed C++ inline assembly must remain stack-neutral except for
    these adjacent flag-save pairs: GCC metadata does not bound arbitrary asm.
    Aurora uses emitted facts; standalone assembly retains its separate checks.
    """
    callbacks = callbacks or {}
    require(
        all(
            caller in frames and target in frames and (caller, "__indirect_call") in edges
            for caller, target in callbacks.items()
        ),
        "Invalid source-reviewed callback binding",
    )
    require(
        all(a in frames and (b in symbols or (b == "__indirect_call" and a in callbacks)) for a, b in edges),
        "Unknown compiler caller or callee",
    )
    pop_bytes = {
        "%" + name: bytes(([0x41] if index >= 8 else []) + [0x58 + index % 8])
        for index, name in enumerate("rax rcx rdx rbx rsp rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split())
        if name != "rsp"
    }
    functions, direct = {}, set()
    for name, frame in frames.items():
        symbol = symbols[name]
        rows = [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]
        require(rows and rows[0].address == symbol.address, "Missing C++ function instructions")
        pairs, calls, callback_sites = [], [], 0
        for row in rows:
            require(row.next <= symbol.address + symbol.size, "C++ instruction exceeds function")
            if row.op.startswith(("pushf", "popf")):
                pop = code.get(row.next)
                require(
                    row.op == "pushf"
                    and not row.args
                    and payload[row.address : row.next] == b"\x9c"
                    and pop is not None
                    and pop.op == "pop"
                    and pop.args in pop_bytes
                    and pop.next <= symbol.address + symbol.size
                    and payload[pop.address : pop.next] == pop_bytes[pop.args],
                    "Unsupported inline PUSHFQ/POP stack contract",
                )
                pairs.append(row.address)
            transfers = [
                token
                for token in (row.op + " " + row.args.split("<", 1)[0]).split()
                if re.fullmatch(r"(?:[bl]?call\w*|[bl]?jmp\w*|j\w+|loop\w*|l?ret\w*|iret\w*)", token)
            ]
            require(
                not transfers or (transfers == [row.op] and row.op in BRANCHES | {"call", "ret"}),
                "Unsupported C++ control-transfer spelling",
            )
            if row.op != "call" and row.op not in BRANCHES:
                continue
            if row.address in internal_jumps:
                require(row.op == "jmp" and row.args.startswith("*"), "Unexpected internal switch jump")
                continue
            if row.op == "call" and row.args.startswith("*"):
                require(name in callbacks, "Unbound indirect C++ call")
                callback_sites += 1
                direct.add((name, "__indirect_call"))
                calls.append(dict(address=row.address, target=callbacks[name], kind="source-reviewed-callback"))
                continue
            target = target_of(row)  # Other supported call/jump targets must resolve directly.
            require(target in code, "C++ transfer to non-instruction")
            if row.op != "call" and symbol.address <= target < symbol.address + symbol.size:
                continue
            require(target in starts, "C++ transfer lacks exact function entry")
            direct.add((name, starts[target]))
            calls.append(dict(address=row.address, target=starts[target], kind="call" if row.op == "call" else "tail"))
        require(callback_sites == int(name in callbacks), "Changed source-reviewed callback call-site inventory")
        bound = frame + (8 if pairs else 0)
        for call in calls:
            call["live_bytes"] = bound
        functions[name] = dict(
            local_peak=bound,
            calls=calls,
            returns=sum(row.op == "ret" for row in rows),
            compiler_frame_bytes=frame,
            inline_stack_bytes=bound - frame,
            inline_pushfq_sites=pairs,
            basis="GCC .su/.ci; full frame retained at calls and tails; direct-transfer cross-check",
        )
    require(direct == edges, "Compiler/linked C++ call edges disagree")
    return functions


def aurora_stack_functions(path, symbols, code, starts, generated_names):
    """Consume actual backend facts; bind exact emitted members and linked edges.

    These facts trust Aurora code generation. They do not independently prove
    arithmetic, local CFG, allocation, or memory safety. Duplicate JSON keys,
    unknown members/callees, hidden transfers, and every graph cycle reject.
    """

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate Aurora stack-fact key")
            result[key] = value
        return result

    document = json.loads(path.read_text(), object_pairs_hook=unique)
    require(type(document) is dict and set(document) == {"version", "functions"}, "Invalid Aurora stack facts")
    version = document["version"]
    require(type(version) is int and version in (1, 2), "Unknown Aurora stack-fact version")
    facts = document["functions"]
    require(type(facts) is dict and set(facts) == set(generated_names), "Aurora stack-fact/function inventory mismatch")
    require(set(facts) <= symbols.keys(), "Missing linked Aurora function")
    functions = {}
    for name, fact in facts.items():
        fields = {"local_bytes", "calls"} | ({"copied_record"} if version == 2 else set())
        require(type(fact) is dict and set(fact) == fields, "Invalid Aurora function fact")
        copied = fact.get("copied_record")
        # V1 describes stack use only. V2 may additionally describe this exact
        # R11-input/R10-result ABI; callers still supply their allowed symbols
        # and independently expected native record sizes. This is compiler trust,
        # not a proof of correct copies, nominal type identity or authority.
        if copied is not None:
            require(
                type(copied) is dict
                and set(copied) == {"parameter_bytes", "result_bytes"}
                and type(copied["parameter_bytes"]) is list
                and len(copied["parameter_bytes"]) <= 6
                and all(
                    type(size) is int and 8 <= size <= 65536 and size % 8 == 0
                    for size in [*copied["parameter_bytes"], copied["result_bytes"]]
                ),
                "Invalid Aurora copied-record ABI fact",
            )
        local, edges = fact["local_bytes"], fact["calls"]
        require(type(local) is int and 8 <= local <= STACK_CAP, "Invalid Aurora local stack bound")
        require(
            type(edges) is dict
            and all(target in symbols and type(live) is int and 8 <= live <= local for target, live in edges.items()),
            "Invalid Aurora callee/live stack bound",
        )
        symbol = symbols[name]
        rows = [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]
        require(rows and rows[0].address == symbol.address, "Missing linked Aurora instructions")
        calls = []
        for row in rows:
            require(row.next <= symbol.address + symbol.size, "Aurora instruction exceeds function")
            transfers = [
                token
                for token in (row.op + " " + row.args.split("<", 1)[0]).split()
                if re.fullmatch(r"(?:[bl]?call\w*|[bl]?jmp\w*|j\w+|loop\w*|l?ret\w*|iret\w*)", token)
            ]
            require(
                not transfers or (transfers == [row.op] and row.op in BRANCHES | {"call", "ret"}),
                "Unsupported Aurora control-transfer spelling",
            )
            if row.op != "call" and row.op not in BRANCHES:
                continue
            target = target_of(row)
            require(target in code, "Aurora transfer to non-instruction")
            if row.op != "call" and symbol.address <= target < symbol.address + symbol.size:
                continue
            if row.op != "call" and code[target].op == "ud2" and not code[target].args:
                continue  # Local trap label; the independent fault reserve covers entry.
            require(row.op == "call" and target in starts, "Unexpected Aurora tail/interior transfer")
            callee = starts[target]
            require(callee in edges, "Linked Aurora call missing from compiler facts")
            calls.append(dict(address=row.address, target=callee, kind="call", live_bytes=edges[callee]))
        require({row["target"] for row in calls} == set(edges), "Aurora compiler/linked call edges disagree")
        functions[name] = dict(
            local_peak=local,
            calls=calls,
            returns=sum(row.op == "ret" for row in rows),
            copied_record=copied,
            basis="Aurora emitted stack/call facts; exact object/function and linked-edge agreement",
        )
    return functions


def language_stack_functions(directory, linked, language, code, starts, bridges=(), stem="language"):
    require(set(bridges) <= language.functions.keys(), "Missing handwritten language bridge")
    for symbol in language.functions.values():
        associate_object(linked, language, symbol)
    return aurora_stack_functions(
        directory / (stem + ".stack.json"), linked.functions, code, starts, set(language.functions) - set(bridges)
    )


def compiled_stack_functions(directory, linked, language, code, starts, frames, edges, bridges=(), internal_jumps=()):
    payload = (directory / "payload.bin").read_bytes()
    require(not set(frames).intersection(language.functions), "Overlapping C++/Aurora object ownership")
    functions = cpp_stack_functions(linked.functions, code, starts, payload, frames, edges, internal_jumps)
    functions.update(language_stack_functions(directory, linked, language, code, starts, bridges))
    return functions


def verify_tail_bridge(rows, starts, target):
    require(
        len(rows) == 1 and rows[0].op == "jmp" and starts.get(target_of(rows[0])) == target,
        "Scalar bridge must tail-call its exact generated root",
    )


def assembly_stack_functions(symbols, code, starts, names):
    """Only the caller's explicit handwritten inventory may use stack decoding."""
    require(set(names) <= symbols.keys(), "Missing handwritten assembly function")
    return {name: analyze_function(symbols[name], code, starts, fault=name == "fault_common") for name in names}


def calculate(functions, root, target=None):
    """Compose selected compiler/handwritten facts; every call cycle rejects."""
    visiting, cache = set(), {}

    def peak(name):
        require(name not in visiting, "Unbounded call/control-flow cycle: " + name)
        if name in cache:
            return cache[name]
        require(name in functions, "Unknown direct callee: " + name)
        visiting.add(name)
        body = functions[name]
        best = (body["local_peak"], [name]) if target is None or name == target else None
        if name != target:
            for call in body["calls"]:
                if call["target"] is None:
                    continue
                child = peak(call["target"])
                if child is not None:
                    value = call["live_bytes"] + child[0]
                    if best is None or value > best[0]:
                        best = value, [name] + child[1]
        visiting.remove(name)
        cache[name] = best
        return best

    result = peak(root)
    require(result is not None, "Unreachable stack path: " + str(target))
    return {"peak": result[0], "path": result[1], "closure": sorted(cache)}


def private_frame_layout(body, linked):
    require(body[:2] == ["pushq %rbp", "movq %rsp, %rbp"], "Unknown generated frame prologue")
    expected = [("push", "%rbp"), ("mov", "%rsp,%rbp")]
    allocated, cursor = 0, 2
    while cursor < len(body) and (match := re.fullmatch(r"subq \$([0-9]+), %rsp", body[cursor])):
        count = int(match[1])
        require(0 < count <= 4096 and count % 16 == 0, "Unaligned or oversized generated frame probe")
        require(cursor == 2 or allocated % 4096 == 0, "Unexpected generated frame probe split")
        require(
            cursor + 1 < len(body) and body[cursor + 1] == "orq $0, (%rsp)",
            "Missing generated frame probe touch",
        )
        expected.extend((("sub", f"$0x{count:x},%rsp"), ("orq", "$0x0,(%rsp)")))
        allocated += count
        cursor += 2
    require(0 < allocated <= STACK_CAP, "Missing or excessive generated frame allocation")
    require([(row.op, row.args) for row in linked[:cursor]] == expected, "Generated source/linked frame mismatch")
    return allocated, cursor


def linked_assembly(linked, directory, name):
    """Check whole executable sections, allowing only the actual rel32 slots."""
    obj = Elf(directory / "objects" / (name + ".o"))
    names = {symbol.name: symbol for symbol in linked.symbols if symbol.section}
    evidence = []
    for index, section in enumerate(obj.sections):
        if section[1] != 1 or not section[2] & 4 or not section[5]:
            continue
        candidates = [symbol for symbol in obj.symbols if symbol.section == index and symbol.name in names]
        require(candidates, "Assembly lacks linked anchor: " + name)
        anchor = candidates[0]
        begin = names[anchor.name].address - anchor.address
        expected = bytearray(obj.section_data(index))
        installed = bytearray((directory / "payload.bin").read_bytes()[begin : begin + len(expected)])
        require(len(installed) == len(expected), "Assembly exceeds payload")
        for symbol in candidates:
            require(names[symbol.name].address == begin + symbol.address, "Assembly symbol moved: " + symbol.name)
        for target, offset, kind, _, _ in obj.relocations:
            if target == index:
                require(kind in (2, 4) and offset + 4 <= len(expected), "Unsupported assembly relocation")
                expected[offset : offset + 4] = installed[offset : offset + 4] = b"\0" * 4
        require(expected == installed, "Assembly object/link mismatch: " + name)
        evidence.append(dict(object=name + ".o", begin=begin, bytes=len(expected)))
    return evidence


def switch_shape(rows):
    """Recognize a bounded PIC table relation, independent of count/register spelling."""
    require(len(rows) == 6, "Missing switch guard")
    guard, reject, table_load, offset_load, addition, jump = rows
    registers = dict(
        zip(
            "rax rbx rcx rdx rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split(),
            "eax ebx ecx edx esi edi r8d r9d r10d r11d r12d r13d r14d r15d".split(),
        )
    )
    table = re.fullmatch(r"(-?0x[0-9a-f]+)\(%rip\),%([a-z0-9]+)", table_load.args)
    load = re.fullmatch(r"\(%([a-z0-9]+),%([a-z0-9]+),4\),%([a-z0-9]+)", offset_load.args)
    bound = re.fullmatch(r"\$(0x[0-9a-f]+|[0-9]+),%([a-z0-9]+)", guard.args)
    require(table and load and bound, "Unknown PIC switch operands")
    base, index, result = load.groups()
    require(
        base in registers and index in registers and result in registers and base not in (index, result),
        "Switch registers alias table/index or stack",
    )
    require(
        guard.op == "cmp"
        and reject.op == "ja"
        and table_load.op == "lea"
        and table[2] == base
        and offset_load.op == "movslq"
        and (addition.op, addition.args) == ("add", f"%{base},%{result}")
        and (jump.op, jump.args) == ("jmp", "*%" + result)
        and bound[2] in (index, registers[index])
        and 0 <= int(bound[1], 0) < 256,
        "Unknown indirect switch envelope",
    )
    return dict(
        table=table_load.address + table_load.size + int(table[1], 16),
        entries=int(bound[1], 0) + 1,
        base="%" + base,
        index="%" + index,
        result="%" + result,
        narrow="%" + registers[index] if bound[2] != index else None,
        offset_load=offset_load.address,
    )


def switch_envelope(rows):
    shape = switch_shape(rows)
    require(shape["narrow"] is None, "Narrow switch index lacks explicit zero extension")
    return shape["table"]


def switch_window(rows):
    """Find the six-operation relation across independent MOVs and one index zero extension."""
    position = len(rows) - 1
    core, independent = [], []
    for mnemonic in ("jmp", "add", "movslq", "lea", "ja", "cmp"):
        while position >= 0 and rows[position].op != mnemonic:
            row = rows[position]
            require(row.op == "mov", "Unsupported switch interleaving")
            independent.append(row)
            position -= 1
        require(position >= 0, "Missing switch operation: " + mnemonic)
        core.append(rows[position])
        position -= 1
    core.reverse()
    shape = switch_shape(core)
    registers = {"%" + name for name in "rax rbx rcx rdx rsi rdi rbp r8 r9 r10 r11 r12 r13 r14 r15".split()}
    extensions = []
    for row in independent:
        operands = arguments(row.args)
        if shape["narrow"] and operands == [shape["narrow"], shape["narrow"]]:
            require(
                core[1].address < row.address < shape["offset_load"], "Switch zero extension is outside guarded load"
            )
            extensions.append(row)
            continue
        require(
            len(operands) == 2
            and operands[1] in registers - {shape[key] for key in ("index", "result", "base")}
            and (operands[0] in registers or re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)?\(%rsp\)", operands[0])),
            "Interleaved move changes switch state or has unsupported operands",
        )
    require(
        len(extensions) == int(shape["narrow"] is not None), "Narrow switch index lacks one explicit zero extension"
    )
    return dict(table=shape["table"], entries=shape["entries"], guard=core[0], jump=core[-1], independent=independent)


def switch_no_bypass(body, guard, jump, targets):
    """No direct or table edge may enter the guarded envelope after its bound."""
    for target in targets:
        require(not guard.address < target <= jump.address, "Switch table target bypasses bound")
    for row in body:
        if (row.op in BRANCHES or row.op == "call") and row is not jump:
            target = target_of(row)
            require(not guard.address < target <= jump.address, "Transfer bypasses switch bound")


def bounded_switches(linked, code, frames, payload):
    """Only a guarded immutable PIC table may hide a local indirect JMP."""
    named = {row.name: row for row in linked.symbols if row.section}
    switches, internal = [], set()
    for name in frames:
        symbol = linked.functions[name]
        body = [
            row for address, row in sorted(code.items()) if symbol.address <= address < symbol.address + symbol.size
        ]
        indirect = [index for index, row in enumerate(body) if row.op == "jmp" and row.args.startswith("*")]
        if not indirect:
            continue
        require(len(indirect) == 1, "Unexpected indirect branch inventory")
        envelope = switch_window(body[: indirect[0] + 1])
        table, guard, jump = (envelope[key] for key in ("table", "guard", "jump"))
        entries = envelope["entries"]
        require(
            "__payload_text_end" in named and "__payload_read_end" in named, "Switch lacks immutable payload boundary"
        )
        require(
            named["__payload_text_end"].address <= table
            and table + entries * 4 <= min(named["__payload_read_end"].address, len(payload)),
            "Switch table is not immutable payload data",
        )
        targets = [
            table + int.from_bytes(payload[table + i * 4 : table + i * 4 + 4], "little", signed=True)
            for i in range(entries)
        ]
        require(
            all(symbol.address <= value < symbol.address + symbol.size and value in code for value in targets),
            "Switch targets leave exact function",
        )
        switch_no_bypass(body, guard, jump, targets)
        internal.add(jump.address)
        switches.append(dict(function=name, table=table, targets=targets))
    return switches, internal


def qword_push(row, payload):
    # Long-mode PUSH has a 64-bit operand unless overridden with 0x66.
    # Permit only the existing unprefixed/REX opcode families, never PUSHF.
    raw = payload[row.address : row.address + row.size]
    if raw and 0x40 <= raw[0] <= 0x4F:
        raw = raw[1:]
    require(
        row.op == "push"
        and raw
        and (
            0x50 <= raw[0] <= 0x57
            or raw[0] in (0x68, 0x6A)
            or (raw[0] == 0xFF and len(raw) >= 2 and raw[1] & 0x38 == 0x30)
        ),
        "Unsupported protected-entry push width/opcode",
    )


def protected_entry_peak(rows, payload, saved_rsp):
    """The handwritten entry is straight-line and has exactly eleven qword pushes."""
    require(rows and (rows[-1].op, rows[-1].args) == ("iretq", ""), "Runtime entry must end in IRETQ")
    pushes, saves = 0, 0
    for row in rows[:-1]:
        if row.op == "push":
            qword_push(row, payload)
            pushes += 1
        else:
            operands = arguments(row.args)
            require(
                row.op in ("mov", "xor") and len(operands) == 2 and operands[-1] not in ("%rsp", "%esp", "%sp", "%spl"),
                "Unmodeled runtime entry stack write or transfer",
            )
            destination = re.fullmatch(r"(-?0x[0-9a-f]+)\(%rip\)", operands[-1])
            if destination and row.next + int(destination[1], 16) == saved_rsp:
                require(
                    row.op == "mov" and operands[0] == "%rsp" and pushes == 6,
                    "Saved kernel RSP must follow six retained pushes",
                )
                saves += 1
    require(pushes == 11 and saves == 1, "Runtime entry save/privilege-frame contract")
    return 8 + pushes * 8


def protected_irq_frame(rows, named, payload):
    """Check the narrow saved-register/dispatch ABI before charging 40 CPU bytes."""
    registers = "rax rbx rcx rdx rbp rsi rdi r8 r9 r10 r11 r12 r13 r14 r15".split()
    prefix = [("cld", "")] + [("push", "%" + name) for name in registers]
    prefix += [
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
    prefix += [("and", "$0xfffffffffffffff0,%rsp")]
    suffix = [("mov", "%rbx,%rsp")] + [("pop", "%" + name) for name in reversed(registers)]
    suffix += [("add", "$0x10,%rsp"), ("iretq", "")]
    require(len(rows) == len(prefix) + 3 + len(suffix), "Changed protected IRQ extent")
    require(
        [(row.op, row.args) for row in rows[: len(prefix)]] == prefix
        and [(row.op, row.args) for row in rows[-len(suffix) :]] == suffix,
        "Changed protected IRQ save/alignment/restore",
    )
    call, result, leave = rows[len(prefix) : len(prefix) + 3]
    require(
        call.op == "call"
        and target_of(call) == named["aurora_exception_dispatch"].address
        and (result.op, result.args) == ("cmp", "$0x1,%rax")
        and leave.op == "je"
        and target_of(leave) == named["aurora_leave_user"].address,
        "Changed protected IRQ dispatch/return",
    )
    for row in rows:
        if row.op == "push":
            qword_push(row, payload)
    return dict(frame_bytes=40 + 16 + 8 * len(registers), alignment_bytes=15)


def protected_leave(rows, named):
    """Check the short switch back to the saved kernel stack and its six pops."""
    prefix = [("mov", "$0x10,%ax"), ("mov", "%eax,%ds"), ("mov", "%eax,%es"), ("mov", "%eax,%ss")]
    suffix = [("pop", "%" + name) for name in ("r15", "r14", "r13", "r12", "rbp", "rbx")]
    suffix += [("mov", "$0x1,%eax"), ("ret", "")]
    require(
        len(rows) == len(prefix) + 2 + len(suffix)
        and [(row.op, row.args) for row in rows[: len(prefix)]] == prefix
        and [(row.op, row.args) for row in rows[-len(suffix) :]] == suffix,
        "Changed protected saved-stack return",
    )
    restore, clear = rows[len(prefix) : len(prefix) + 2]
    source = re.fullmatch(r"(-?0x[0-9a-f]+)\(%rip\),%rsp", restore.args)
    destination = re.fullmatch(r"\$0x0,(-?0x[0-9a-f]+)\(%rip\)", clear.args)
    require(
        restore.op == "mov" and source and clear.op == "movq" and destination, "Changed saved kernel RSP restore/clear"
    )
    require(
        all(
            row.next + int(match[1], 16) == named["uefi_runtime_saved_rsp"].address
            for row, match in ((restore, source), (clear, destination))
        ),
        "Protected return uses a different saved stack",
    )


def protected_assembly(linked, directory, code, payload):
    named = {row.name: row for row in linked.symbols if row.section}

    def body(begin, end):
        rows = [row for address, row in sorted(code.items()) if begin <= address < end]
        require(
            rows
            and rows[0].address == begin
            and rows[-1].next == end
            and all(a.next == b.address for a, b in zip(rows, rows[1:])),
            "Protected assembly coverage gap",
        )
        return rows

    enter, leave, handler = (named[key] for key in ("uefi_runtime_enter", "aurora_leave_user", "uefi_runtime_handler"))
    entry_peak = protected_entry_peak(
        body(enter.address, leave.address), payload, named["uefi_runtime_saved_rsp"].address
    )
    protected_leave(body(leave.address, handler.address), named)
    obj = Elf(directory / "objects/runtime-entry.o")
    original = next(row for row in obj.symbols if row.name == handler.name)
    extent = obj.sections[original.section][5] - original.address
    linked.functions[enter.name] = Symbol(enter.name, enter.address, leave.address - enter.address, enter.section, 0)
    linked.functions[handler.name] = Symbol(handler.name, handler.address, extent, handler.section, 0)
    common = named["exception_common"].address
    irq = protected_irq_frame(body(common, named["aurora_breakpoint_probe"].address), named, payload)
    # Hardware error codes replace one synthetic qword; every vector reaches
    # the common save path with the same two-qword vector/error record.
    error_vectors = {8, 10, 11, 12, 13, 14, 17, 21, 29, 30}
    vectors = [("aurora_exception_" + str(i), i, i in error_vectors) for i in range(32)]
    vectors += [
        ("aurora_timer_interrupt", 64, False),
        ("aurora_program_return", 129, False),
        ("aurora_user_return", 128, False),
        ("aurora_unexpected_interrupt", 255, False),
    ]
    ordered = sorted((named[name].address, name, vector, error) for name, vector, error in vectors)
    for index, (address, name, vector, error) in enumerate(ordered):
        end = ordered[index + 1][0] if index + 1 < len(ordered) else common
        rows = body(address, end)
        pushes = rows if name == "aurora_unexpected_interrupt" else rows[:-1]
        expected = [vector] if error else [0, vector]
        require(len(pushes) == len(expected), "Changed protected vector/error frame")
        for row, value in zip(pushes, expected):
            qword_push(row, payload)
            require(row.args == "$0x" + format(value, "x"), "Changed protected vector/error value")
        require(
            name == "aurora_unexpected_interrupt" or (rows[-1].op == "jmp" and target_of(rows[-1]) == common),
            "Changed protected vector target",
        )
    return entry_peak, irq


def image_stack_graph(
    directory,
    objects,
    source_root=None,
    *,
    protected=False,
    bridges=(),
    noreturn=(),
    generated=True,
    payload_entry=True,
    allow_bounded=lambda _: True,
    source_callbacks=(),
):
    """One composition for exact C++/Aurora facts and the explicit assembly boundary.

    The PCI-only emission control selects generated=False, payload_entry=False;
    production profiles always retain the complete linked function inventory.
    """
    global NORETURN
    linked = Elf(directory / "payload.elf")
    require(linked.type == 2, "Expected linked payload ELF")
    code, disassembly = disassemble(linked.path)
    payload = (directory / "payload.bin").read_bytes()
    entry_peak, irq = protected_assembly(linked, directory, code, payload) if protected else (None, None)
    starts = {symbol.address: name for name, symbol in linked.functions.items()}
    require(len(starts) == len(linked.functions), "Ambiguous linked function starts")
    edges = set()
    frames, associations = cpp_frames(directory, linked, objects, edges, source_root, allow_bounded)
    callbacks = {}
    for caller, target in source_callbacks:
        caller_name = source_frame_symbol(associations, *caller)
        target_name = source_frame_symbol(associations, *target)
        require(caller_name not in callbacks, "Duplicate source-reviewed callback caller")
        callbacks[caller_name] = target_name
    switches, internal = bounded_switches(linked, code, frames, payload)
    functions = cpp_stack_functions(linked.functions, code, starts, payload, frames, edges, internal, callbacks)
    memory = Elf(directory / "objects/memory.o")
    require(
        memory.type == 1 and set(memory.functions) == {"memcpy", "memmove", "memset", "memcmp"},
        "Unexpected memory primitive inventory",
    )
    for symbol in memory.functions.values():
        associate_object(linked, memory, symbol)
    handwritten = set(memory.functions)
    if generated:
        language = Elf(directory / "objects/language.o")
        require(not set(frames).intersection(language.functions), "Overlapping C++/Aurora object ownership")
        functions.update(language_stack_functions(directory, linked, language, code, starts, bridges))
        handwritten.update(bridges)
    assembly = []
    for name in (("payload-entry",) if payload_entry else ()) + (
        ("runtime-entry", "runtime-exceptions") if protected else ()
    ):
        assembly += linked_assembly(linked, directory, name)
    if payload_entry:
        handwritten.update(("uefi_payload_entry", "uefi_payload_fault", "uefi_payload_page_fault", "fault_common"))
    if protected:
        handwritten.add("uefi_runtime_handler")
        functions["uefi_runtime_enter"] = dict(local_peak=entry_peak, calls=[], returns=1)
    require(set(linked.functions) == set(functions) | handwritten, "Unaccounted linked function/frame inventory")
    previous = NORETURN
    NORETURN = frozenset(noreturn) | frozenset(
        name for name in linked.functions if name == "uefi_payload_fail" or "4stopE" in name or "4failE" in name
    )
    try:
        functions.update(assembly_stack_functions(linked.functions, code, starts, handwritten))
    finally:
        NORETURN = previous
    require(all(not functions[name]["calls"] for name in memory.functions), "Memory primitive acquired a call")
    for name in functions:
        calculate(functions, name)
    return dict(
        linked=linked,
        functions=functions,
        compiler_frames=associations,
        bounded_switches=switches,
        assembly_objects=assembly,
        disassembly=disassembly,
        protected_irq=irq,
        runtime_entry_peak=entry_peak,
        trusted_source_callbacks=callbacks,
    )


def frame_names(records, fragment, excluded=()):
    return {
        name
        for name, rows in records.items()
        if any(fragment in row["record"] and not any(part in row["record"] for part in excluded) for row in rows)
    }


def profile_stack(
    graph, limits, *, optional=(), excluded=None, default_limit=STACK_CAP, fault_reserve=512, separated=()
):
    """Profile data selects frame ceilings and required workload roots; paths use calculate()."""
    functions, records = graph["functions"], graph["compiler_frames"]
    selected = {}
    for fragment, limit in limits.items():
        names = frame_names(records, fragment, (excluded or {}).get(fragment, ()))
        require(names or fragment in optional, "Missing profile workload frame: " + fragment)
        require(
            all(row["bytes"] <= limit for name in names for row in records[name]), "Profile frame ceiling: " + fragment
        )
        selected[fragment] = names
    covered = set().union(*selected.values())
    require(
        all(row["bytes"] <= default_limit for name, rows in records.items() if name not in covered for row in rows),
        "Unexpected large profile frame",
    )
    normal = calculate(functions, "uefi_payload_entry")
    for fragment, names in selected.items():
        require(names <= set(normal["closure"]), "Unreachable profile workload: " + fragment)
    for caller, callee in separated:
        require(
            all(not selected[callee].intersection(calculate(functions, name)["closure"]) for name in selected[caller]),
            "ACPI parser retains its frame across PCI discovery",
        )
    fault = 48 + max(calculate(functions, name)["peak"] for name in ("uefi_payload_fault", "uefi_payload_page_fault"))
    require(fault <= fault_reserve, "Synchronous fault path exceeds profile reserve")
    peak = normal["peak"] + fault_reserve
    require(peak <= STACK_CAP, "Profile stack reserve exhausted")
    irq = graph.get("protected_irq")
    dispatch = None
    if irq:
        dispatch = calculate(functions, "aurora_exception_dispatch")
        dispatch["peak_with_entry"] = irq["frame_bytes"] + irq["alignment_bytes"] + dispatch["peak"]
        require(dispatch["peak_with_entry"] + fault_reserve <= STACK_CAP, "Protected exception stack reserve exhausted")
    return dict(
        normal=normal,
        peak_with_fault_reserve=peak,
        fault_reserve=fault_reserve,
        boot_fault=fault,
        irq_dispatch=dispatch,
        stack_bytes=STACK_BYTES,
        minimum_unused=STACK_BYTES - peak,
        compiler_frames=records,
        bounded_switches=graph["bounded_switches"],
        trusted_source_callbacks=graph.get("trusted_source_callbacks", {}),
    )
