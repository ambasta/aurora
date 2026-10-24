"""Minimal read-only ELF64 reader shared by the kernel image checks and guest oracles."""

from dataclasses import dataclass
from pathlib import Path
import struct

SHF_WRITE, SHF_ALLOC, SHF_EXECINSTR = 1, 2, 4
PF_X, PF_W, PF_R = 1, 2, 4


@dataclass(frozen=True)
class Symbol:
    name: str
    address: int
    size: int
    section: int
    kind: int  # STT_*: 0 NOTYPE, 1 OBJECT, 2 FUNC
    bind: int  # STB_*: 0 LOCAL, 1 GLOBAL, 2 WEAK


@dataclass(frozen=True)
class Section:
    name: str
    kind: int
    flags: int
    address: int
    offset: int
    size: int


@dataclass(frozen=True)
class Segment:
    kind: int
    flags: int
    offset: int
    address: int
    file_size: int
    memory_size: int
    alignment: int


class Elf:
    def __init__(self, path):
        self.path = Path(path)
        data = self.data = self.path.read_bytes()
        if data[:6] != b"\x7fELF\x02\x01":
            raise ValueError(f"{path}: expected little-endian ELF64")
        header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
        if header[2] != 62:
            raise ValueError(f"{path}: expected x86-64")
        self.type, self.entry = header[1], header[4]
        phoff, shoff, phentsize, phnum, shentsize, shnum, shstrndx = (
            header[5],
            header[6],
            header[9],
            header[10],
            header[11],
            header[12],
            header[13],
        )
        raw = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shentsize) for i in range(shnum)] if shoff else []
        names = raw[shstrndx] if raw else None

        def string(table, offset):
            start = table[4] + offset
            return data[start : data.index(b"\0", start)].decode()

        self.sections = [Section(string(names, s[0]), s[1], s[2], s[3], s[4], s[5]) for s in raw]
        self.segments = []
        for i in range(phnum if phoff else 0):
            kind, flags, offset, address, _, file_size, memory_size, alignment = struct.unpack_from(
                "<IIQQQQQQ", data, phoff + i * phentsize
            )
            self.segments.append(Segment(kind, flags, offset, address, file_size, memory_size, alignment))
        self.symbols = []
        self.relocations = []  # (section index, offset, type, symbol index, addend)
        for index, section in enumerate(raw):
            if section[1] == 2:  # SHT_SYMTAB
                strings = raw[section[6]]
                for pos in range(section[4] + 24, section[4] + section[5], 24):
                    name, info, _, shndx, value, size = struct.unpack_from("<IBBHQQ", data, pos)
                    self.symbols.append(Symbol(string(strings, name), value, size, shndx, info & 15, info >> 4))
            elif section[1] == 4:  # SHT_RELA
                for pos in range(section[4], section[4] + section[5], 24):
                    offset, info, addend = struct.unpack_from("<QQq", data, pos)
                    self.relocations.append((section[7], offset, info & 0xFFFFFFFF, info >> 32, addend))
        self.functions = {s.name: s for s in self.symbols if s.kind == 2 and s.section}

    def defined(self):
        return {s.name: s for s in self.symbols if s.name and s.section and s.kind != 4}

    def undefined(self):
        return {s.name for s in self.symbols if s.name and not s.section and s.kind != 4}

    def section_data(self, section):
        return self.data[section.offset : section.offset + section.size]


def image_policy(path, profile):
    """Merge every rule of the declarative image policy table that names this profile."""
    import ast
    from fnmatch import fnmatch

    tree = ast.parse(Path(path).read_text())
    rules = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and node.targets[0].id == "RULES"
    )
    merged = {}
    for rule in rules:
        if any(fnmatch(profile, pattern) for pattern in rule["profiles"]):
            for key, values in rule.items():
                if key != "profiles":
                    merged.setdefault(key, []).extend(values)
    return merged
