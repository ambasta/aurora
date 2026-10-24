"""Run one checked-in Aurora driver per storage/filesystem family over data cases.

Each family compiles its driver module once, links it once with record_host.cpp
and streams every case as a fixed-size record laid out from the compiler's own
ABI facts. Results are formatted one line per case and compared with a reviewed
golden file; `--update-golden` rewrites it for an intended, reviewed change.
Compile-time rejections are one-line sources compiled once each; their exact
diagnostics are golden too. Python here only builds inputs and compares text.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
U64 = (1 << 64) - 1


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def command(args, timeout=60):
    result = subprocess.run([str(arg) for arg in args], capture_output=True, timeout=timeout, check=False)
    return result


def crc32c(data):
    """Input construction only: repairs mutated fixtures; expectations are golden."""
    crc = U64 >> 32
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0x82F63B78 if crc & 1 else 0)
    return crc ^ (U64 >> 32)


def repair(data, offset):
    """Store the CRC32C of `data` (CRC field zeroed) little-endian at `offset`."""
    result = bytearray(data)
    result[offset : offset + 4] = bytes(4)
    result[offset : offset + 4] = crc32c(result).to_bytes(4, "little")
    return bytes(result)


def spread(prefix, data, count):
    """Split `data` over `count` consecutive 512-byte record fields prefix0..N."""
    require(len(data) <= 512 * count, f"{prefix}: {len(data)} bytes exceed {count} fields")
    return {f"{prefix}{index}": data[index * 512 : (index + 1) * 512] for index in range(count)}


def describe_sector(window, sector):
    """Name a 512-byte result as zero or as its nonzero prefix's first sector-aligned window position."""
    if not any(sector):
        return "zero"
    valid = len(sector.rstrip(b"\0"))
    for offset in range(0, len(window), 512):
        if window[offset : offset + valid] == sector[:valid]:
            return f"window@{offset}+{valid}"
    return "bytes:" + sector.hex()


def enum_codes(source):
    """Code-to-name maps read from the driver's own `if (value == E::name) { return Nu64; }` chains."""
    codes = {}
    for enum, name, code in re.findall(r"\(value == (?:\w+::)*(\w+)::(\w+)\) \{ return (\d+)u64; \}", source):
        table = codes.setdefault(enum, {})
        require(int(code) not in table, f"duplicate {enum} code {code}")
        table[int(code)] = name
    return codes


class Driver:
    """One compiled driver: `class <record> { ... auto entry(i64 slot) const -> u64; }`."""

    def __init__(self, compiler, directory, source, record, entry="entry"):
        self.directory = directory
        self.source = source.read_text()
        self.codes = enum_codes(self.source)
        assembly, facts = directory / "driver.s", directory / "abi.json"
        modules = ["--module-root", ROOT / "library"]
        result = command([compiler, *modules, source, "-o", assembly, "--abi-facts", facts], timeout=300)
        require(result.returncode == 0, f"{source.name}: compile failed: {result.stderr.decode()}")
        abi = json.loads(facts.read_text())
        records = [(name, row) for name, row in abi["records"].items() if row["source_name"] == record]
        entries = [(name, row) for name, row in abi["functions"].items() if row["source_name"] == entry]
        require(len(records) == 1 and len(entries) == 1, f"{source.name}: one {record}.{entry} in ABI facts")
        (record_symbol, layout), (symbol, method) = records[0], entries[0]
        require(
            method["receiver"] == record_symbol
            and not method["receiver_mutable"]
            and method["borrowed_root_count"] == 0
            and method["parameter_bytes"] == 8
            and method["parameters"] == [{"offset": 0, "bytes": 8, "kind": "i64"}]
            and method["result"] == {"bytes": 8, "kind": "u64"},
            f"{source.name}: entry must be a const scalar method taking one i64 slot",
        )
        require(layout["alignment"] == 8 and layout["size"] % 8 == 0, f"{record}: aligned record")
        self.size = layout["size"]
        self.fields = {field["name"]: field for field in layout["fields"]}
        for field in layout["fields"]:
            kind, count = field["kind"], field.get("array_length", 0)
            require(
                (kind == "u8" and count == field["bytes"]) or (kind in ("i64", "u64") and not count),
                f"{record}.{field['name']}: only u8 arrays and i64/u64 scalars cross the host boundary",
            )
        text = assembly.read_text()
        shim = f"\n.text\n.globl storage_invoke\nstorage_invoke:\nmovq %rdi,%r10\nmovq %rsi,%rdi\njmp {symbol}\n"
        if ".Laurora_bounds_trap:" in text:
            shim += ".globl storage_bounds_trap\n.set storage_bounds_trap, .Laurora_bounds_trap\n"
        assembly.write_text(text + shim)
        self.program = directory / "driver"
        cxx = shlex.split(os.environ.get("CXX", "g++"))
        flags = ("-std=c++23", "-Wall", "-Wextra", "-Werror")
        result = command([*cxx, *flags, HERE / "record_host.cpp", assembly, "-o", self.program], timeout=120)
        require(result.returncode == 0, f"{source.name}: host link failed: {result.stderr.decode()}")
        self.batches = 0

    def pack(self, values):
        packet = bytearray(self.size)
        for name, value in values.items():
            require(name in self.fields, f"unknown record field {name}")
            field = self.fields[name]
            offset, width = field["offset"], field["bytes"]
            if field["kind"] == "u8":
                require(len(value) <= width, f"{name}: {len(value)} bytes exceed {width}")
                packet[offset : offset + len(value)] = value
            else:
                packet[offset : offset + 8] = struct.pack("<q" if field["kind"] == "i64" else "<Q", value)
        return bytes(packet)

    def write(self, cases):
        path = self.directory / f"cases-{self.batches:03d}.bin"
        self.batches += 1
        with path.open("wb") as stream:
            stream.write(struct.pack("<Q", self.size))
            for values, slots in cases:
                stream.write(struct.pack("<Q", slots) + self.pack(values))
        return path

    def run(self, cases):
        """Return the complete u64 slot observations of every (values, slot count) case."""
        result = command([self.program, self.write(cases)], timeout=600)
        require(result.returncode == 0 and not result.stderr, f"driver failed {result.returncode}: {result.stderr!r}")
        words = struct.unpack(f"<{len(result.stdout) // 8}Q", result.stdout)
        require(len(words) == sum(slots for _, slots in cases), "complete driver observations")
        observed, cursor = [], 0
        for _, slots in cases:
            observed.append(list(words[cursor : cursor + slots]))
            cursor += slots
        return observed

    def trap(self, values, slots):
        """Run one case alone; return "bounds-trap" only for SIGILL at the exact bounds UD2."""
        result = command([self.program, self.write([(values, slots)]), 0])
        if result.returncode == 77 and result.stdout == b"bounds-trap\n":
            return "bounds-trap"
        return f"exit {result.returncode} {result.stdout.hex()} {result.stderr!r}"

    def name(self, enum, code):
        return self.codes[enum].get(code, f"?{code}")


def reject(compiler, path):
    """Compile one invalid source; return its single diagnostic without the path."""
    output = path.with_suffix(".s")
    result = command([compiler, "--module-root", ROOT / "library", path, "-o", output])
    diagnostic = result.stderr.decode(errors="replace")
    if result.returncode != 1 or output.exists() or diagnostic.count("\n") != 1:
        return f"exit {result.returncode} output={output.exists()} {diagnostic!r}"
    return diagnostic.removeprefix(f"{path}:").strip()


def rejections(compiler, directory, sources):
    """(label, source) pairs compiled concurrently; yields golden ("reject label", diagnostic) rows."""
    paths = []
    for index, (_, source) in enumerate(sources):
        paths.append(directory / f"reject-{index:03d}.au")
        paths[-1].write_text(source)
    with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 1)) as pool:
        diagnostics = list(pool.map(lambda path: reject(compiler, path), paths))
    for (label, _), diagnostic in zip(sources, diagnostics):
        yield f"reject {label}", diagnostic


def run_example(compiler, directory, source):
    """Compile a library example once and report the complete i64 its main() returns."""
    assembly, program = directory / (source.stem + ".s"), directory / source.stem
    result = command([compiler, "--module-root", ROOT / "library", source, "-o", assembly])
    if result.returncode != 0:
        return f"compile failed {result.stderr!r}"
    start = ".text\n.globl _start\n_start:\ncall main\npushq %rax\nmovq $1,%rax\nmovq $1,%rdi\nmovq %rsp,%rsi\n"
    start += "movq $8,%rdx\nsyscall\nmovq $60,%rax\nxorq %rdi,%rdi\nsyscall\n"
    assembly.write_text(assembly.read_text() + start)
    for step in (
        ["as", "--64", assembly, "-o", program.with_suffix(".o")],
        ["ld", "-o", program, program.with_suffix(".o")],
    ):
        result = command(step)
        if result.returncode != 0:
            return f"{step[0]} failed {result.stderr!r}"
    result = command([program])
    if result.returncode != 0 or len(result.stdout) != 8:
        return f"exit {result.returncode} {result.stdout!r}"
    return f"returned {struct.unpack('<q', result.stdout)[0]}"


def compare(golden, rows, update):
    lines = [f"{label}\t{result}" for label, result in rows]
    require(all("\n" not in line for line in lines), "one golden line per case")
    if update:
        golden.write_text("\n".join(lines) + "\n")
        print(f"UPDATED {golden.relative_to(ROOT)}: {len(lines)} cases", flush=True)
        return
    expected = golden.read_text().splitlines()
    differences = [
        f"  case {index}: expected {want!r}\n           observed {got!r}"
        for index, (want, got) in enumerate(zip(expected, lines))
        if want != got
    ]
    require(
        not differences and len(expected) == len(lines),
        f"{golden.name}: {len(differences)} differing cases, {len(lines)} observed vs {len(expected)} golden\n"
        + "\n".join(differences[:20]),
    )


def main(name, describe):
    """Parse the common arguments, then let `describe(compiler, directory)` yield golden rows."""
    parser = argparse.ArgumentParser()
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--update-golden", action="store_true")
    parser.add_argument("--keep", type=Path, help="retain the compiled driver and case files here")
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    print(f"compiler_sha256={hashlib.sha256(compiler.read_bytes()).hexdigest()}", flush=True)
    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix=f"aurora-{name}-") as scratch:
        directory = args.keep.resolve() if args.keep else Path(scratch)
        rows = list(describe(compiler, directory))
        compare(HERE / f"{name}.golden", rows, args.update_golden)
        rejected = sum(1 for label, _ in rows if label.startswith("reject "))
        print(f"PASS {name}: {len(rows) - rejected} cases, {rejected} rejections match {name}.golden", flush=True)
