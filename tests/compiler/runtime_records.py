"""One compiled Aurora driver per library, fed every case as a data record.

A library test supplies one AU module that defines a record class and a const
`entry(i64 field)` method returning a complete i64 or u64. The module is compiled
once, its record layout and call ABI are checked against aurorac's ABI facts,
and it is linked once with the generic host in runtime_records_host.cpp. Every
case is then a fixed-size record packed from those facts and streamed through one
process, which returns one 64-bit observation per requested field.

Expected values come from the caller: a Python standard-library reference or a
reviewed golden file. This module never computes expected library results.
Rejection sources are compiled one at a time and must fail with a diagnostic
that leaves an existing output file untouched.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MIN = -(1 << 63)
MAX = (1 << 63) - 1
U64_MAX = (1 << 64) - 1
HOST = Path(__file__).with_name("runtime_records_host.cpp")
SENTINEL = b"existing output must survive a rejection\n"
# A whole local 4096-byte owner, zero-initialized with one byte-string literal.
ZERO_OWNER = 'builtin::array<u8,4096> owner="' + "\\0" * 4096 + '";'
PACK = {"i64": "<q", "u64": "<Q", "u8": "<B", "bool": "<Q", "enum": "<Q"}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run(argv, timeout=120, **kwargs):
    try:
        return subprocess.run([str(arg) for arg in argv], capture_output=True, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"timeout after {timeout}s: {argv}") from error


def checked(argv, name, timeout=120):
    result = run(argv, timeout)
    require(
        result.returncode == 0 and not result.stderr,
        f"{name} failed ({result.returncode}): {result.stderr.decode(errors='replace')[:4000]}",
    )
    return result.stdout


# One byte from every class the package grammars distinguish, for substitution cases.
SAMPLE_BYTES = tuple(sorted(b"\0\t\n\r #-./09:@AZ_az\x7f\x80\xff"))


@contextlib.contextmanager
def scratch(name):
    """A private temporary directory, retained after a failure or on request."""
    directory = tempfile.TemporaryDirectory(prefix=f"aurora-{name}-", delete=False)
    try:
        yield Path(directory.name)
    except BaseException:
        print(f"Retained scratch: {directory.name}", file=sys.stderr, flush=True)
        raise
    if os.environ.get("AURORA_MESON_KEEP_ARTIFACTS") == "1":
        print(f"Retained scratch: {directory.name}", flush=True)
    else:
        directory.cleanup()


def byte_fields(name="data", chunks=8, width=512):
    """Declarations, constructor initializers and a reader for one chunked byte input.

    Class u8 array fields hold at most 512 bytes, so a 4096-byte input is eight
    fields. `input_byte(i)` reads byte i; `load(owner, n)` copies n bytes.
    """
    declarations = "".join(f"builtin::array<u8,{width}> {name}{i};" for i in range(chunks))
    initializers = [f"{name}{i}{{}}" for i in range(chunks)]
    reader = f"auto input_byte(i64 index) const -> u8 {{"
    for i in range(chunks - 1):
        reader += f"if(index<{width * (i + 1)}){{return {name}{i}[index-{width * i}];}}"
    reader += f"return {name}{chunks - 1}[index-{width * (chunks - 1)}];}}"
    return declarations, initializers, reader


def decode_data(value):
    """Golden byte encoding: a hex string, or a list of [hex, repeat] segments."""
    if isinstance(value, str):
        return bytes.fromhex(value)
    return b"".join(bytes.fromhex(segment) * times for segment, times in value)


def encode_data(data):
    """The inverse of decode_data, with runs of 64 or more equal bytes collapsed."""
    segments, index = [], 0
    while index < len(data):
        end = index
        while end < len(data) and data[end] == data[index]:
            end += 1
        if end - index >= 64:
            segments.append([data[index : index + 1].hex(), end - index])
        elif segments and segments[-1][1] == 1:
            segments[-1][0] += data[index:end].hex()
        else:
            segments.append([data[index:end].hex(), 1])
        index = end
    if len(segments) == 1 and segments[0][1] == 1:
        return segments[0][0]
    if not segments:
        return ""
    return segments


def load_jsonl(path):
    with open(path) as stream:
        return [json.loads(line) for line in stream if line.strip()]


class Program:
    def __init__(self, binary, record, kind):
        self.binary = binary
        self.size = record["size"]
        self.fields = {field["name"]: field for field in record["fields"]}
        self.signed = kind == "i64"
        self.segmented = False
        self.words = None
        # Chunked byte inputs: array fields <name>0, <name>1, ... of u8, or of
        # u64 holding eight little-endian bytes each, filled in offset order.
        self.groups = {}
        for name, field in self.fields.items():
            stem = name.rstrip("0123456789")
            if stem != name and field["array_length"] and field["kind"] in ("u8", "u64"):
                self.groups.setdefault(stem, []).append(field)
        for group in self.groups.values():
            group.sort(key=lambda field: field["offset"])
        self.chunks = self.groups.get("data", [])

    def pack(self, data=None, **values):
        """One record from field values; `data` (or any chunk-group name) fills its chunk fields in order."""
        packet = bytearray(self.size)
        if data is not None:
            require(self.chunks, "record has no chunked byte input")
            values = {"data": data, **values}
        for name, value in values.items():
            if name not in self.fields and name in self.groups:
                chunks = self.chunks if name == "data" else self.groups[name]
                capacity = sum(field["bytes"] for field in chunks)
                require(len(value) <= capacity, f"{name} of {len(value)} bytes exceeds its {capacity}-byte fields")
                at = 0
                for field in chunks:
                    piece = value[at : at + field["bytes"]]
                    packet[field["offset"] : field["offset"] + len(piece)] = piece
                    at += field["bytes"]
                continue
            require(name in self.fields, f"record has no field {name}")
            field = self.fields[name]
            if field["array_length"]:
                require(field["kind"] == "u8" and len(value) <= field["bytes"], f"byte field {name} extent")
                packet[field["offset"] : field["offset"] + len(value)] = value
                continue
            require(field["kind"] in PACK, f"unsupported record field kind {field['kind']}")
            if field["kind"] == "i64":
                require(MIN <= value <= MAX, f"{name} outside i64")
            else:
                require(0 <= value <= (0xFF if field["kind"] == "u8" else U64_MAX), f"{name} outside {field['kind']}")
            struct.pack_into(PACK[field["kind"]], packet, field["offset"], value)
        return bytes(packet)

    def observe(self, records, scratch):
        """Run every (packet, call_count) record once; returns the flat observations.
        In words mode each call returns its own block of words, all concatenated."""
        path = scratch / "cases.bin"
        total = 0
        with path.open("wb") as stream:
            for packet, count in records:
                require(len(packet) == self.size and 0 < count <= 65536, "record extent")
                stream.write(struct.pack("<Q", count))
                if self.segmented:
                    # Only the nonzero runs of a large, mostly empty record are sent.
                    runs = [(m.start(), m.end()) for m in re.finditer(rb"[^\0](?:[^\0]|\0{1,15}(?=[^\0]))*", packet)]
                    stream.write(struct.pack("<Q", len(runs)))
                    for start, end in runs:
                        stream.write(struct.pack("<QQ", start, end - start))
                        stream.write(packet[start:end])
                else:
                    stream.write(packet)
                total += count
        argv = [self.binary, self.size, path] + (["segments"] if self.segmented else [])
        if self.words:
            argv.append("words={}:{}".format(*self.words))
        raw = checked(argv, "driver", timeout=600)
        require(len(raw) % 8 == 0, f"driver returned {len(raw)} bytes")
        values = struct.unpack(f"<{len(raw) // 8}{'q' if self.signed else 'Q'}", raw)
        if not self.words:
            require(len(values) == total, f"driver returned {len(values)} observations for {total}")
            return list(values)
        observed, at = [], 0
        for _ in range(total):
            require(at < len(values) and 0 <= values[at] <= self.words[1], "driver word block extent")
            observed.extend(values[at + 1 : at + 1 + values[at]])
            at += 1 + values[at]
        require(at == len(values), "driver returned trailing words")
        return observed

    def check(self, cases, scratch):
        """Run (label, packet, expected[, calls]) cases; every observation must equal its
        expectation. Calls default to one per expected word; words mode passes its own."""
        cases = [case if len(case) == 4 else (*case, len(case[2])) for case in cases]
        observed = self.observe(((packet, calls) for _, packet, _, calls in cases), scratch)
        require(len(observed) == sum(len(case[2]) for case in cases), "driver observation count")
        mismatches, at = [], 0
        for label, _, expected, _ in cases:
            actual = observed[at : at + len(expected)]
            at += len(expected)
            if list(actual) != list(expected):
                mismatches.append((label, list(expected), actual))
        require(not mismatches, f"{len(mismatches)} mismatched cases, first: {mismatches[:4]}")
        return len(cases), len(observed)


class Driver:
    def __init__(self, compiler, scratch, module_root=None):
        self.compiler = Path(compiler).resolve(strict=True)
        self.scratch = Path(scratch)
        self.module_root = Path(module_root or ROOT / "library")
        self.cxx = shlex.split(os.environ.get("CXX", "g++"))
        self.rejections = self.programs = 0

    def compile(self, source, name):
        directory = self.scratch / name
        directory.mkdir()
        (directory / "input.au").write_text(source)
        checked(
            [
                self.compiler,
                "--module-root",
                self.module_root,
                directory / "input.au",
                "-o",
                directory / "compiled.s",
                "--abi-facts",
                directory / "abi.json",
            ],
            f"{name} compiler",
        )
        return directory

    def build(self, source, record_name, entry_name="entry", kind="i64", name="driver", segmented=False, words=None):
        """Compile and link one driver; returns a Program bound to its checked record layout.

        With `words` naming a u64 array field of the record, the entry is a mutable
        method that writes one block of observations there per call and returns
        the block's length, so one computation can yield many observations."""
        require(kind in ("i64", "u64"), "driver observation kind")
        directory = self.compile(source, name)
        abi = json.loads((directory / "abi.json").read_text())
        records = [(symbol, row) for symbol, row in abi["records"].items() if row["source_name"] == record_name]
        require(len(records) == 1, f"unique record {record_name}")
        record_symbol, record = records[0]
        entries = [
            (symbol, row)
            for symbol, row in abi["functions"].items()
            if row["source_name"] == entry_name and row.get("receiver") == record_symbol
        ]
        require(len(entries) == 1, f"unique {record_name}::{entry_name}")
        symbol, method = entries[0]
        require(
            record["size"] == record["reserved"]
            and record["size"] % 8 == 0
            and record["alignment"] == 8
            and all(field["offset"] + field["bytes"] <= record["size"] for field in record["fields"]),
            "driver record layout",
        )
        block = None
        if words is not None:
            fields = [field for field in record["fields"] if field["name"] == words]
            require(
                len(fields) == 1 and fields[0]["kind"] == "u64" and fields[0]["array_length"] >= 1,
                f"{record_name}::{words} is one u64 array field",
            )
            block = (fields[0]["offset"], fields[0]["array_length"])
        require(
            method["receiver_mutable"] == (words is not None)
            and method["borrowed_root_count"] == 0
            and method["parameter_bytes"] == 8
            and method["parameters"] == [{"offset": 0, "bytes": 8, "kind": "i64"}]
            and method["result"] == {"bytes": 8, "kind": "i64" if words is not None else kind},
            "driver entry ABI",
        )
        # The private method convention takes the receiver in r10 and the field in rdi.
        with (directory / "compiled.s").open("a") as stream:
            stream.write(
                "\n.text\n.globl aurora_record_entry\naurora_record_entry:\n"
                f"movq %rdi,%r10\nmovq %rsi,%rdi\njmp {symbol}\n"
            )
        checked(["as", "--64", directory / "compiled.s", "-o", directory / "program.o"], f"{name} assembler")
        require(
            not checked(["nm", "-u", directory / "program.o"], f"{name} nm").strip(),
            "driver object imports a runtime symbol",
        )
        binary = directory / "program"
        checked(
            [
                *self.cxx,
                "-std=c++23",
                "-O1",
                "-Wall",
                "-Wextra",
                "-Werror",
                HOST,
                directory / "program.o",
                "-o",
                binary,
            ],
            f"{name} link",
        )
        program = Program(binary, record, kind)
        program.segmented = segmented
        program.words = block
        return program

    def reject(self, label, source, diagnostic=None, message=None):
        """Compile one rejected source: exit 1 with exactly one compiler diagnostic,
        whose text contains `diagnostic` (case-insensitively) or equals `message`.
        Alternate rejections start with an existing output file, which must survive
        unchanged, or with none, which must not be created."""
        require((diagnostic is None) != (message is None), f"{label}: one expected diagnostic form")
        directory = self.scratch / f"reject-{self.rejections:03d}"
        directory.mkdir()
        existing = self.rejections % 2 == 0
        self.rejections += 1
        path = directory / "input.au"
        path.write_text(source)
        target = directory / "preserved.s"
        if existing:
            target.write_bytes(SENTINEL)
        result = run([self.compiler, "--module-root", self.module_root, path, "-o", target])
        error = result.stderr.decode(errors="replace")
        require(result.returncode == 1, f"{label}: compiler exit {result.returncode}: {error[:2000]}")
        require(not result.stdout, f"{label}: rejection wrote stdout")
        match = re.fullmatch(
            rf"(?:{re.escape(str(path))}:[1-9][0-9]*:[1-9][0-9]*|aurorac): error "
            r"AU(?:100[1-3]|200[123]|3001|4001): ([^\n]+)\n",
            error,
        )
        require(match is not None, f"{label}: expected one compiler diagnostic: {error[:2000]}")
        if message is not None:
            require(match[1] == message, f"{label}: expected diagnostic {message!r}; actual {error!r}")
        else:
            require(diagnostic in error.lower(), f"{label}: expected diagnostic {diagnostic!r}; actual {error!r}")
        require(path.read_text() == source, f"{label}: rejection changed its source")
        if existing:
            require(target.read_bytes() == SENTINEL, f"{label}: rejection modified existing output")
        else:
            require(not target.exists(), f"{label}: rejection created output")

    def reject_all(self, path):
        """Every rejection row of a golden JSONL file; returns their count."""
        rows = load_jsonl(path)
        for row in rows:
            self.reject(row["label"], row["source"], row.get("diagnostic"), row.get("message"))
        return len(rows)

    def run_main(self, source, symbol="test"):
        """Compile a standalone program and return the complete i64 its entry function returns."""
        self.programs += 1
        directory = self.compile(source, f"main-{self.programs:02d}")
        entry = (
            f".text\n.globl _start\n_start:\ncall {symbol}\npushq %rax\nmovq $1,%rax\nmovq $1,%rdi\n"
            "movq %rsp,%rsi\nmovq $8,%rdx\nsyscall\naddq $8,%rsp\nmovq $60,%rax\nxorq %rdi,%rdi\nsyscall\n"
            '.section .note.GNU-stack,"",@progbits\n'
        )
        (directory / "entry.s").write_text(entry)
        checked(["as", "--64", directory / "compiled.s", "-o", directory / "program.o"], "assembler")
        checked(["as", "--64", directory / "entry.s", "-o", directory / "entry.o"], "entry assembler")
        require(not checked(["nm", "-u", directory / "program.o"], "nm").strip(), "program imports a runtime symbol")
        checked(["ld", "-o", directory / "program", directory / "entry.o", directory / "program.o"], "link")
        output = checked([directory / "program"], "program")
        require(len(output) == 8, "one complete i64 result")
        return struct.unpack("<q", output)[0]
