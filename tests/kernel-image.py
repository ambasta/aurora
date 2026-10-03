#!/usr/bin/env python3
"""Validate the fixed boot contract and assemble a disposable raw disk image."""
from pathlib import Path
import subprocess

PAYLOAD_SECTORS = 96


def require(condition: bool, message: str) -> None:
    # Explicit checks remain active under PYTHONOPTIMIZE / python -O.
    if not condition:
        raise ValueError(message)


def validate(boot: bytes, kernel: bytes, elf: bytes, packet_offset: int) -> None:
    require(len(boot) == 512, f"Expected 512 boot bytes, got {len(boot)}")
    require(boot[510:] == b"\x55\xaa", "Missing BIOS signature")
    require(packet_offset % 4 == 0, "EDD packet is not four-byte aligned")
    require(0 <= packet_offset <= 510 - 16, "Disk address packet outside boot sector")
    packet = boot[packet_offset:packet_offset + 16]
    require(packet[:2] == b"\x10\x00", "Invalid EDD packet header")
    sectors = int.from_bytes(packet[2:4], "little")
    offset = int.from_bytes(packet[4:6], "little")
    segment = int.from_bytes(packet[6:8], "little")
    require(sectors == PAYLOAD_SECTORS and 1 <= sectors <= 127, "Loader sector count disagrees with image budget")
    require(segment * 16 + offset == 0x10000, "Loader destination disagrees with kernel entry")
    require(offset + sectors * 512 <= 65536, "BIOS read crosses segment transfer window")
    require(int.from_bytes(packet[8:16], "little") == 1, "Loader LBA is not the image payload")
    require(0 < len(kernel) <= sectors * 512, "Kernel exceeds bounded BIOS payload budget")
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
    boot_symbols = subprocess.check_output(["nm", "-a", str(build / "boot.o")], text=True)
    packets = [int(line.split()[0], 16) for line in boot_symbols.splitlines() if line.split()[-1] == "packet"]
    require(len(packets) == 1, "Missing unique assembler disk-packet symbol")
    packet_offset = packets[0]
    validate(boot, kernel, elf, packet_offset)
    undefined = subprocess.check_output(["nm", "-u", str(build / "kernel.elf")], text=True)
    require(not undefined.strip(), f"Unresolved runtime symbols: {undefined}")
    image = boot + kernel + bytes(PAYLOAD_SECTORS * 512 - len(kernel))
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
    malformed_packets = []
    for field, value in ((2, 0), (2, 128), (4, 65520), (6, 0x2000), (8, 2)):
        malformed = bytearray(boot)
        malformed[packet_offset + field:packet_offset + field + 2] = value.to_bytes(2, "little")
        if field == 4:
            # Keep the physical destination valid while forcing a 64 KiB transfer-window crossing.
            malformed[packet_offset + 6:packet_offset + 8] = (1).to_bytes(2, "little")
        malformed_packets.append((malformed, kernel, elf))
    for invalid in ((boot[:-1], kernel, elf), (boot[:-2] + bytes(2), kernel, elf),
                    (boot, bytes(49153), elf), (boot, b"", elf),
                    (boot, kernel, corrupted_entry), (boot, kernel, bytes(64)),
                    (boot, kernel, corrupted_permissions), (boot, kernel, corrupted_headers), *malformed_packets):
        try:
            validate(*invalid, packet_offset)
        except ValueError:
            continue
        raise RuntimeError("Invalid image was accepted by negative control")
    try:
        validate(boot, kernel, elf, packet_offset + 1)
    except ValueError:
        pass
    else:
        raise RuntimeError("Unaligned BIOS packet accepted")
    print(f"PASS: boot signature, ELF entry, zero unresolved symbols, {len(kernel)}-byte payload, 1 MiB image; 14 negative controls; RX/R/RW segments and bounded BIOS packet")


if __name__ == "__main__":
    main()
