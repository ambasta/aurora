#!/usr/bin/env python3
"""Adversarial division metadata policy, including optional legacy absence."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("kernel_user_image", Path(__file__).with_name("kernel-user-image.py"))
image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(image)


def main() -> None:
    base = image.BASE
    binary = bytearray(128)
    binary[30:32] = b"\xcd\x81"
    for offset in (32, 64, 66, 68):
        binary[offset : offset + 2] = b"\x0f\x0b"
    elf = bytearray(256)
    elf[:6] = b"\x7fELF\x02\x01"
    for start, end, value in (
        (16, 18, 2),
        (18, 20, 62),
        (24, 32, base),
        (32, 40, 64),
        (54, 56, 56),
        (56, 58, 1),
        (64, 68, 1),
        (68, 72, 5),
        (72, 80, 128),
        (80, 88, base),
        (96, 104, 128),
        (104, 112, 128),
    ):
        elf[start:end] = value.to_bytes(end - start, "little")
    elf[128:] = binary
    symbols = dict(zip(image.AUTHORITY_SYMBOLS, (base, base + 4, base + 32, base + 64, base + 66, base + 68)))
    image.require(image.validate(elf, binary, base, symbols)[3] == base + 68, "Valid division site lost")
    legacy = dict(symbols)
    legacy.pop(image.DIVISION_SYMBOL)
    image.require(image.validate(elf, binary, base, legacy)[3] == 0, "Absent site gained authority")
    rejected = 0

    def reject(operation) -> None:
        nonlocal rejected
        try:
            operation()
        except ValueError:
            rejected += 1
            return
        raise RuntimeError("Malformed division metadata accepted")

    for site in (0, base - 1, base + 127, base + 4096, 2**64 - 1, base + 32, base + 64, base + 66, base + 69):
        bad = dict(symbols)
        bad[image.DIVISION_SYMBOL] = site
        reject(lambda: image.validate(elf, binary, base, bad))
    for opcode in (b"\x90\x90", b"\x0f\x90", b"\x90\x0b", b"\xf7\xf9"):
        bad_binary, bad_elf = bytearray(binary), bytearray(elf)
        bad_binary[68:70] = opcode
        bad_elf[196:198] = opcode
        reject(lambda: image.validate(bad_elf, bad_binary, base, symbols))
    nm = "\n".join(f"{pc:x} t {name}" for name, pc in symbols.items())
    image.require(image.parse_symbols(nm) == symbols, "Valid symbols changed")
    for name, pc in symbols.items():
        for duplicate in (pc, pc + 1):
            reject(lambda: image.parse_symbols(nm + f"\n{duplicate:x} t {name}"))
    for name in image.AUTHORITY_SYMBOLS[:-1]:
        bad = dict(symbols)
        bad.pop(name)
        reject(lambda: image.validate(elf, binary, base, bad))
    print(f"PASS: division image metadata, 3 positive and {rejected} negative cases")


if __name__ == "__main__":
    main()
