#!/usr/bin/env python3
"""Exercise the prebuilt Aurora linker on real objects and data-only ELF edits.

The compiler is the one driver. No case compiles its own program; one host-sort
object and the compiler's own object cover calls, literals and local/global
symbols. The emitted executable and a compiler linked by itself really run.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "scripts"))
from golden import compare, flat  # noqa: E402
from kernel_volume import volume  # noqa: E402


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], capture_output=True, timeout=60, **kwargs)


def success(*args, **kwargs):
    result = run(*args, **kwargs)
    if result.returncode or result.stderr:
        raise RuntimeError(f"{args}: exit {result.returncode}: {flat(result.stderr)}")
    return result.stdout


def anchors(data):
    """Locate ELF fields for fixture edits, not an independent admission/linker."""
    word = lambda at: struct.unpack_from("<Q", data, at)[0]
    half = lambda at: struct.unpack_from("<I", data, at)[0]
    sections = word(40)
    text, rela, sym, strings = (word(sections + index * 64 + 24) for index in (1, 2, 3, 4))
    symbols = word(sections + 3 * 64 + 32) // 24
    start = next(
        sym + index * 24
        for index in range(1, symbols)
        if data[strings + half(sym + index * 24) :].split(b"\0", 1)[0] == b"_start"
    )
    return {
        "header": 0,
        "text-header": sections + 64,
        "rodata-header": sections + 7 * 64,
        "relocation-header": sections + 2 * 64,
        "symbol-header": sections + 3 * 64,
        "first-symbol": sym + 24,
        "second-symbol": sym + 48,
        "start-symbol": start,
        "start-name": strings + half(start),
        "string-end": strings + word(sections + 4 * 64 + 32) - 1,
        "rela": rela,
        "call-relocation": next(
            rela + index * 24 for index in range(word(sections + 2 * 64 + 32) // 24) if half(rela + index * 24 + 8) == 4
        ),
        "next-rela": rela + 24,
        "placeholder": text + word(rela),
        "text-size": word(sections + 64 + 32),
        "symbols": symbols,
        "first-name": half(sym + 24),
        "first-site": word(rela),
        "text-offset": text,
    }


def literal_free(original, positions):
    """Data-only ET_REL fixture: one reviewed Linux exit(42) leaf, no literals.

    Retain the real object's table framing and _start name; unused bytes are
    gaps. These instruction bytes are fixture input, never an emitted-code oracle.
    """
    data = bytearray(original)
    code = bytes.fromhex("b8 3c 00 00 00 bf 2a 00 00 00 0f 05")
    text = positions["text-offset"]
    data[text : text + len(code)] = code
    struct.pack_into("<Q", data, positions["text-header"] + 32, len(code))
    for name in ("relocation-header", "rodata-header"):
        struct.pack_into("<Q", data, positions[name] + 32, 0)
    struct.pack_into("<Q", data, positions["symbol-header"] + 32, 48)
    struct.pack_into("<I", data, positions["symbol-header"] + 44, 1)
    start, symbol = positions["start-symbol"], positions["first-symbol"]
    data[symbol : symbol + 24] = original[start : start + 24]
    struct.pack_into("<QQ", data, symbol + 8, 0, len(code))
    return data


def rejection(compiler, original, positions, key, index, directory):
    name, anchor, offset, width, value = key.split()
    source, output = directory / f"{name}.o", directory / name
    data = bytearray(original)
    if anchor == "truncate":
        del data[int(value) :]
    else:
        at = positions[anchor] + int(offset)
        replacement = positions[value] if value in positions else int(value, 0)
        data[at : at + int(width)] = replacement.to_bytes(int(width), "little")
    source.write_bytes(data)
    existing = b"existing output\n" if index % 2 else None
    if existing:
        output.write_bytes(existing)
    result = run(compiler, "--link-object", source, "-o", output)
    changed = (output.read_bytes() if output.exists() else None) != existing
    if result.returncode != 1 or result.stdout or changed:
        return f"exit {result.returncode} output-changed={changed} stdout={result.stdout!r} {flat(result.stderr)}"
    return flat(result.stderr)


def admit(driver, image, directory):
    """Use the existing kernel-policy driver and volume writer, not another ELF checker."""
    data = volume([(b"program", image.read_bytes())])
    query = b"program:6:0x40000000:program"
    bundle = directory / "admission.bundle"
    bundle.write_bytes(
        struct.pack("<I", 6)
        + b"linked"
        + struct.pack("<II", 1, len(query))
        + query
        + struct.pack("<Q", len(data))
        + data
    )
    result = success(driver, "volumes", bundle).decode()
    if (
        not result.startswith("linked: valid\n  program program -> elf=valid layout=valid entry=")
        or "malformed" in result
    ):
        raise RuntimeError("kernel rejected linked ELF: " + result)
    print("PASS kernel ELF and address-space policies admit " + image.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("sort_object", type=Path)
    parser.add_argument("compiler_object", type=Path)
    parser.add_argument("policy_driver", type=Path)
    parser.add_argument("--guest-executable", type=Path)
    args = parser.parse_args()
    compiler, sort_object, compiler_object = (
        path.resolve() for path in (args.compiler, args.sort_object, args.compiler_object)
    )
    original = sort_object.read_bytes()
    positions = anchors(original)
    with tempfile.TemporaryDirectory(prefix="aurora-static-link-") as temporary:
        directory = Path(temporary)
        linked = directory / "sort"
        success(compiler, "--link-object", sort_object, "-o", linked)
        # HostFiles deliberately creates private 0600 artifacts; executable
        # permission is a Linux caller decision, not extra guest file authority.
        admit(args.policy_driver.resolve(), linked, directory)
        if args.guest_executable:
            admit(args.policy_driver.resolve(), args.guest_executable.resolve(), directory)
        linked.chmod(0o700)
        (directory / "input").write_bytes(b"beta\na\nbeta\n\n")
        observed = success(linked, directory, directory / "sorted", "input")
        if observed != b"4 lines: 0 1 4 4\n" or (directory / "sorted").read_bytes() != b"\na\nbeta\nbeta\n":
            raise RuntimeError("linked host-sort output differs from its golden result")
        # The same compiler operation, in one process, produces those same bytes.
        emitted = directory / "emitted"
        success(compiler, "--emit-executable", ROOT / "examples/host-sort.au", "-o", emitted)
        if emitted.read_bytes() != linked.read_bytes():
            raise RuntimeError("compile-and-link differs from linking the emitted object")
        self_linked = directory / "aurorac"
        success(compiler, "--link-object", compiler_object, "-o", self_linked)
        self_linked.chmod(0o700)
        successor = directory / "successor"
        success(self_linked, "--link-object", sort_object, "-o", successor)
        if successor.read_bytes() != linked.read_bytes():
            raise RuntimeError("self-linked compiler produced different executable bytes")
        print("PASS native-linked host-sort executes and the native-linked compiler reproduces its executable")
        empty_object, empty_program = directory / "literal-free.o", directory / "literal-free"
        empty_object.write_bytes(literal_free(original, positions))
        success(compiler, "--link-object", empty_object, "-o", empty_program)
        admit(args.policy_driver.resolve(), empty_program, directory)
        empty_program.chmod(0o700)
        empty_result = run(empty_program)
        if empty_result.returncode != 42 or empty_result.stdout or empty_result.stderr:
            raise RuntimeError("literal-free executable did not exit 42")
        print("PASS literal-free native executable runs without a readonly-data segment")

        # Alias protection applies to binary input exactly as to source inputs.
        source = directory / "source.o"
        source.write_bytes(original)
        alias = directory / "alias.o"
        os.link(source, alias)
        for destination in (source, alias):
            result = run(compiler, "--link-object", source, "-o", destination)
            if result.returncode != 1 or source.read_bytes() != original:
                raise RuntimeError("static link replaced its object input")
        golden = ROOT / "tests/compiler/static_link.golden"
        keys = [line.split("\t", 1)[0] for line in golden.read_text().splitlines()]
        with ThreadPoolExecutor(len(os.sched_getaffinity(0))) as pool:
            jobs = [
                pool.submit(rejection, compiler, original, positions, key, index, directory)
                for index, key in enumerate(keys)
            ]
            compare(golden, [f"{key}\t{job.result()}" for key, job in zip(keys, jobs)])
        if list(directory.glob(".aurora-output-*.tmp")):
            raise RuntimeError("static link left uncommitted output files")


if __name__ == "__main__":
    main()
