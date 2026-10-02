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
    table = int.from_bytes(elf[32:40], "little")
    stride = int.from_bytes(elf[54:56], "little")
    count = int.from_bytes(elf[56:58], "little")
    require(stride == 56 and 1 <= count <= 16 and table >= 64
            and table + stride * count <= len(elf), "Invalid ELF program-header table")
    loads = []
    for index in range(count):
        header = elf[table + index * stride:table + (index + 1) * stride]
        if int.from_bytes(header[:4], "little") != 1:
            continue
        flags = int.from_bytes(header[4:8], "little")
        offset = int.from_bytes(header[8:16], "little")
        address = int.from_bytes(header[16:24], "little")
        file_size = int.from_bytes(header[32:40], "little")
        memory_size = int.from_bytes(header[40:48], "little")
        require(flags in (4, 5, 6), "Unexpected or writable-executable ELF segment")
        require(address % 4096 == 0 and 0x10000 <= address < 0x70000
                and memory_size >= file_size and address + memory_size < 0x70000,
                "Invalid protected segment range")
        require(offset + file_size <= len(elf), "Truncated ELF load payload")
        loads.append((address, address + memory_size, flags))
    require(sorted(flags for _, _, flags in loads) == [4, 5, 6], "Expected separate RX, R and RW segments")
    loads.sort()
    for previous, current in zip(loads, loads[1:]):
        require((previous[1] + 4095) // 4096 * 4096 <= current[0], "Protection segments share a page")


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
    corrupted_permissions = bytearray(elf)
    table = int.from_bytes(elf[32:40], "little")
    corrupted_permissions[table + 4:table + 8] = (7).to_bytes(4, "little")
    corrupted_headers = bytearray(elf)
    corrupted_headers[32:40] = (len(elf) + 1).to_bytes(8, "little")
    for invalid in ((boot[:-1], kernel, elf), (boot[:-2] + bytes(2), kernel, elf),
                    (boot, bytes(32769), elf), (boot, b"", elf),
                    (boot, kernel, corrupted_entry), (boot, kernel, bytes(64)),
                    (boot, kernel, corrupted_permissions), (boot, kernel, corrupted_headers)):
        try:
            validate(*invalid)
        except ValueError:
            continue
        raise RuntimeError("Invalid image was accepted by negative control")
    print(f"PASS: boot signature, ELF entry, zero unresolved symbols, {len(kernel)}-byte payload, 1 MiB image; 8 negative controls; separated RX/R/RW ELF segments")


if __name__ == "__main__":
    main()
