#!/usr/bin/env python3
"""Verify linked user bytes/trap symbols and emit trusted read-only image metadata."""

from pathlib import Path
import subprocess
import sys
import json
import argparse
import os

NAMES = ("clean", "bounds", "overflow")
ROOT = Path(__file__).resolve().parents[1]
BASE = 0x1B0000
DIVISION_SYMBOL = ".Laurora_division_zero_trap"
SHIFT_SYMBOL = ".Laurora_shift_count_trap"
# Preserve the original division contract's ordering for its standalone tests.
AUTHORITY_SYMBOLS = (
    "aurora_program_entry",
    "aurora_user_main",
    "aurora_program_return_pc",
    ".Laurora_bounds_trap",
    ".Laurora_overflow_trap",
    DIVISION_SYMBOL,
)
REQUIRED_SYMBOLS = AUTHORITY_SYMBOLS[:-1]
OPTIONAL_SYMBOLS = (DIVISION_SYMBOL, SHIFT_SYMBOL)
ALL_AUTHORITY_SYMBOLS = REQUIRED_SYMBOLS + OPTIONAL_SYMBOLS
DIVISION_FIXTURES = ("none", "zero", "remainder-zero", "overflow", "remainder-min", "kernel-trap")
UNSIGNED_FIXTURES = ("none", "valid", "shift-count", "conversion-overflow", "kernel-trap")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(elf: bytes, binary: bytes, base: int, symbols: dict[str, int]) -> tuple[int, int, int, int, int]:
    require(0 < len(binary) <= 4096, "User image must fit one nonempty page")
    require(len(elf) >= 64 and elf[:6] == b"\x7fELF\x02\x01", "Expected little-endian ELF64")
    require(
        int.from_bytes(elf[16:18], "little") == 2 and int.from_bytes(elf[18:20], "little") == 62,
        "Expected x86-64 executable",
    )
    require(int.from_bytes(elf[24:32], "little") == base, "Wrong linked user entry")
    table, stride, count = (int.from_bytes(elf[a:b], "little") for a, b in ((32, 40), (54, 56), (56, 58)))
    require(stride == 56 and count == 1 and table >= 64 and table + 56 <= len(elf), "Expected one bounded load header")
    header = elf[table : table + 56]
    get = lambda a, b: int.from_bytes(header[a:b], "little")
    require(
        get(0, 4) == 1 and get(4, 8) == 5 and get(16, 24) == base, "User load segment must be RX at its fixed address"
    )
    offset, size, memory = get(8, 16), get(32, 40), get(40, 48)
    require(size == len(binary) and size == memory and offset + size <= len(elf), "Unexpected user BSS/size/truncation")
    require(elf[offset : offset + size] == binary, "Extracted bytes differ from linked load segment")
    required = REQUIRED_SYMBOLS
    require(all(name in symbols for name in required), "Missing entry/return/compiler trap metadata")
    require(symbols[required[0]] == base, "Entry symbol does not match header")
    require(base <= symbols[required[1]] < base + len(binary), "Compiled function outside image")
    ret, bounds, overflow = (symbols[name] for name in required[2:])
    division = symbols.get(DIVISION_SYMBOL, 0)
    shift = symbols.get(SHIFT_SYMBOL, 0)
    sites = (ret, bounds, overflow) + tuple(symbols[name] for name in OPTIONAL_SYMBOLS if name in symbols)
    require(len(set(sites)) == len(sites), "Return and trap sites must be distinct")
    for trap in sites:
        require(base <= trap and trap + 2 <= base + len(binary), "Trap address outside linked image")
        require(binary[trap - base : trap - base + 2] == b"\x0f\x0b", "Metadata does not point at UD2")
    require(
        ret >= base + 2 and binary[ret - base - 2 : ret - base] == b"\xcd\x81",
        "Return label is not immediately after the scalar gate",
    )
    return ret, bounds, overflow, division, shift


def parse_symbols(output: str) -> dict[str, int]:
    result = {}
    for line in output.splitlines():
        words = line.split()
        if len(words) == 3:
            require(
                words[2] not in ALL_AUTHORITY_SYMBOLS or words[2] not in result,
                "Duplicate entry/return/compiler trap metadata",
            )
            result[words[2]] = int(words[0], 16)
    return result


def symbols_for(path: Path) -> dict[str, int]:
    undefined = subprocess.check_output(["nm", "-u", str(path)], text=True)
    require(not undefined.strip(), "Unresolved user runtime symbols")
    return parse_symbols(subprocess.check_output(["nm", "-a", str(path)], text=True))


def assembly_path(path: Path) -> str:
    """Quote a resolved filename for GNU assembler without directive injection."""
    return (
        '"'
        + "".join(
            chr(byte) if 32 <= byte < 127 and byte not in (34, 92) else f"\\{byte:03o}"
            for byte in os.fsencode(path.resolve())
        )
        + '"'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="source root (default: repository root)")
    parser.add_argument("--build-dir", type=Path, help="artifact directory (default: ROOT/build)")
    parser.add_argument("--division-fixture", choices=DIVISION_FIXTURES, default="none")
    parser.add_argument("--unsigned-fixture", choices=UNSIGNED_FIXTURES, default="none")
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    build = (arguments.build_dir if arguments.build_dir is not None else root / "build").resolve()
    assembly = ['.section .rodata.user_images,"a"']
    declarations = ["// Generated by tests/kernel-user-image.py; do not edit."]
    contracts = []
    require(
        arguments.division_fixture == "none" or arguments.unsigned_fixture == "none",
        "Compiler feature gates cannot be combined",
    )
    metadata = {"division_fixture": arguments.division_fixture, "unsigned_fixture": arguments.unsigned_fixture}
    bad_count = 0
    for index, name in enumerate(NAMES):
        base = BASE + index * 4096
        elf = (build / f"user-{name}.elf").read_bytes()
        binary = (build / f"user-{name}.bin").read_bytes()
        symbols = symbols_for(build / f"user-{name}.elf")
        ret, bounds, overflow, division, shift = validate(elf, binary, base, symbols)
        require(
            arguments.division_fixture == "none" or division != 0,
            "Division gates require retained compiler division-zero metadata",
        )
        require(
            arguments.unsigned_fixture == "none" or shift != 0,
            "Unsigned gates require retained compiler shift-count metadata",
        )
        if index == 0:
            probe_begin = symbols.get("aurora_context_probe_begin", 0)
            probe_end = symbols.get("aurora_context_probe_end", 0)
            require(
                (probe_begin == probe_end == 0) or base <= probe_begin < probe_end <= base + len(binary),
                "Invalid context probe range",
            )
            assembly += [".global aurora_schedule_probe", "aurora_schedule_probe:", f".quad {probe_begin}, {probe_end}"]
        metadata[str(index)] = {
            "base": base,
            "size": len(binary),
            "return": ret,
            "bounds": bounds,
            "overflow": overflow,
            "division_zero": division,
            "shift_count": shift,
            "probe_begin": symbols.get("aurora_context_probe_begin", 0),
            "probe_end": symbols.get("aurora_context_probe_end", 0),
        }
        assembly += [
            f".global aurora_image_{name}",
            f"aurora_image_{name}:",
            f".incbin {assembly_path(build / f'user-{name}.bin')}",
        ]
        declarations += [f'extern const std::array<std::byte, {len(binary)}> image_{name} asm("aurora_image_{name}");']
        contracts += [
            "ProgramImage{image_%s, ProgramContract{%d, %d, %d, %d, %d, %d, %d}}"
            % (name, base, len(binary), ret, bounds, overflow, division, shift)
        ]
        broken_bytes = bytearray(binary)
        broken_bytes[bounds - base : bounds - base + 2] = b"\x90\x90"
        matching_broken_elf = bytearray(elf)
        segment = int.from_bytes(elf[32:40], "little")
        payload_offset = int.from_bytes(elf[segment + 8 : segment + 16], "little")
        matching_broken_elf[payload_offset + bounds - base : payload_offset + bounds - base + 2] = b"\x90\x90"
        wrong_permissions = bytearray(elf)
        table = int.from_bytes(elf[32:40], "little")
        wrong_permissions[table + 4 : table + 8] = (7).to_bytes(4, "little")
        outside = dict(symbols)
        outside[".Laurora_bounds_trap"] = base + 4096
        wrong_site = dict(symbols)
        wrong_site[".Laurora_bounds_trap"] = base
        bad_images = [
            (elf, b"", base, symbols),
            (elf, bytes(4097), base, symbols),
            (elf, binary, base + 4096, symbols),
            (elf, broken_bytes, base, symbols),
            (wrong_permissions, binary, base, symbols),
            (elf, binary, base, outside),
            (elf, binary, base, wrong_site),
            (elf, binary, base, {}),
            (matching_broken_elf, broken_bytes, base, symbols),
        ]
        if division:
            for site in (0, base - 1, base + len(binary) - 1, base + 4096, ret, bounds, overflow, base):
                bad_symbols = dict(symbols)
                bad_symbols[DIVISION_SYMBOL] = site
                bad_images.append((elf, binary, base, bad_symbols))
            bad_binary, bad_elf = bytearray(binary), bytearray(elf)
            bad_binary[division - base : division - base + 2] = b"\x90\x90"
            bad_elf[payload_offset + division - base : payload_offset + division - base + 2] = b"\x90\x90"
            bad_images.append((bad_elf, bad_binary, base, symbols))
        if shift:
            for site in (0, base - 1, base + len(binary) - 1, base + 4096, ret, bounds, overflow, division, base):
                bad_symbols = dict(symbols)
                bad_symbols[SHIFT_SYMBOL] = site
                bad_images.append((elf, binary, base, bad_symbols))
            bad_binary, bad_elf = bytearray(binary), bytearray(elf)
            bad_binary[shift - base : shift - base + 2] = b"\x90\x90"
            bad_elf[payload_offset + shift - base : payload_offset + shift - base + 2] = b"\x90\x90"
            bad_images.append((bad_elf, bad_binary, base, symbols))
        for args in bad_images:
            try:
                validate(*args)
            except ValueError:
                bad_count += 1
                continue
            raise RuntimeError("Invalid user image accepted")
    assembly += ['.section .note.GNU-stack,"",@progbits']
    declarations += ["constinit const std::array<ProgramImage, 3> images{", ",\n".join(contracts), "};"]
    (build / "user-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    (build / "kernel-user-images.S").write_text("\n".join(assembly) + "\n")
    (build / "kernel-user-images.hpp").write_text("\n".join(declarations) + "\n")
    print(f"PASS: 3 separately linked RX user images, exact return/UD2 metadata, {bad_count} negative image cases")


if __name__ == "__main__":
    try:
        main()
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
