#!/usr/bin/env python3
"""Validate the fixed boot contract and assemble a disposable raw disk image."""
from pathlib import Path
import subprocess


def require(condition: bool, message: str) -> None:
    # Explicit checks remain active under PYTHONOPTIMIZE / python -O.
    if not condition:
        raise ValueError(message)


def validate(boot: bytes, kernel: bytes, elf: bytes) -> None:
    require(len(boot) == 512, f"Expected 512 boot bytes, got {len(boot)}")
    require(boot[510:] == b"\x55\xaa", "Missing BIOS signature")
    require(0 < len(kernel) <= 64 * 512, "Kernel exceeds BIOS loader's 64-sector budget")
    require(len(elf) >= 64 and elf[:6] == b"\x7fELF\x02\x01", "Expected little-endian ELF64")
    require(int.from_bytes(elf[16:18], "little") == 2, "Expected executable ELF")
    require(int.from_bytes(elf[18:20], "little") == 62, "Expected x86-64 machine type")
    require(int.from_bytes(elf[24:32], "little") == 0x10000, "Unexpected kernel entry point")


def main() -> None:
    build = Path(__file__).resolve().parents[1] / "build"
    boot = (build / "boot.bin").read_bytes()
    kernel = (build / "kernel.bin").read_bytes()
    elf = (build / "kernel.elf").read_bytes()
    validate(boot, kernel, elf)
    undefined = subprocess.check_output(["nm", "-u", str(build / "kernel.elf")], text=True)
    require(not undefined.strip(), f"Unresolved runtime symbols: {undefined}")
    image = boot + kernel + bytes(64 * 512 - len(kernel))
    image += bytes(1024 * 1024 - len(image))
    (build / "aurora.img").write_bytes(image)
    # Negative controls prove invalid inputs are rejected before packaging.
    corrupted_entry = bytearray(elf)
    corrupted_entry[24:32] = bytes(8)
    for invalid in ((boot[:-1], kernel, elf), (boot[:-2] + bytes(2), kernel, elf),
                    (boot, bytes(32769), elf), (boot, b"", elf),
                    (boot, kernel, corrupted_entry), (boot, kernel, bytes(64))):
        try:
            validate(*invalid)
        except ValueError:
            continue
        raise RuntimeError("Invalid image was accepted by negative control")
    print(f"PASS: boot signature, ELF entry, zero unresolved symbols, {len(kernel)}-byte payload, 1 MiB image; 6 negative controls")


if __name__ == "__main__":
    main()
