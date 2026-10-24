#!/usr/bin/env python3
"""Validate the fixed boot contract and assemble a disposable raw disk image."""

from pathlib import Path
import argparse
import subprocess

PAYLOAD_SECTORS = 127
LOAD_ADDRESS = 0x10000
TRANSFER_END = LOAD_ADDRESS + PAYLOAD_SECTORS * 512
IMAGE_BYTES = 1024 * 1024


def require(condition: bool, message: str) -> None:
    # Explicit checks remain active under PYTHONOPTIMIZE / python -O.
    if not condition:
        raise ValueError(message)


def validate(boot: bytes, kernel: bytes, elf: bytes, packet_offset: int) -> None:
    require(len(boot) == 512, f"Expected 512 boot bytes, got {len(boot)}")
    require(boot[510:] == b"\x55\xaa", "Missing BIOS signature")
    require(packet_offset % 4 == 0, "EDD packet is not four-byte aligned")
    require(0 <= packet_offset <= 510 - 16, "Disk address packet outside boot sector")
    packet = boot[packet_offset : packet_offset + 16]
    require(packet[:2] == b"\x10\x00", "Invalid EDD packet header")
    sectors = int.from_bytes(packet[2:4], "little")
    offset = int.from_bytes(packet[4:6], "little")
    segment = int.from_bytes(packet[6:8], "little")
    require(sectors == PAYLOAD_SECTORS and 1 <= sectors <= 127, "Loader sector count disagrees with image budget")
    require(segment * 16 + offset == LOAD_ADDRESS, "Loader destination disagrees with kernel entry")
    require(offset + sectors * 512 <= 65536, "BIOS read crosses segment transfer window")
    require(segment == 0x1000 and offset == 0, "Loader destination is not canonical 1000:0000")
    require(int.from_bytes(packet[8:16], "little") == 1, "Loader LBA is not the image payload")
    require(
        0 < len(kernel) <= sectors * 512,
        f"Kernel payload {len(kernel)} bytes exceeds bounded BIOS capacity {sectors * 512} bytes",
    )
    require(len(elf) >= 64 and elf[:6] == b"\x7fELF\x02\x01", "Expected little-endian ELF64")
    require(int.from_bytes(elf[16:18], "little") == 2, "Expected executable ELF")
    require(int.from_bytes(elf[18:20], "little") == 62, "Expected x86-64 machine type")
    require(int.from_bytes(elf[24:32], "little") == 0x10000, "Unexpected kernel entry point")
    table = int.from_bytes(elf[32:40], "little")
    stride = int.from_bytes(elf[54:56], "little")
    count = int.from_bytes(elf[56:58], "little")
    require(
        stride == 56 and 1 <= count <= 16 and table >= 64 and table + stride * count <= len(elf),
        "Invalid ELF program-header table",
    )
    loads = []
    file_spans = []
    for index in range(count):
        header = elf[table + index * stride : table + (index + 1) * stride]
        if int.from_bytes(header[:4], "little") != 1:
            continue
        flags = int.from_bytes(header[4:8], "little")
        offset = int.from_bytes(header[8:16], "little")
        address = int.from_bytes(header[16:24], "little")
        physical_address = int.from_bytes(header[24:32], "little")
        file_size = int.from_bytes(header[32:40], "little")
        memory_size = int.from_bytes(header[40:48], "little")
        require(flags in (4, 5, 6), "Unexpected or writable-executable ELF segment")
        require(
            address % 4096 == 0
            and 0x10000 <= address < 0x70000
            and memory_size >= file_size
            and address + memory_size < 0x70000,
            "Invalid protected segment range",
        )
        require(physical_address == address, "ELF load physical/virtual addresses disagree")
        require(offset + file_size <= len(elf), "Truncated ELF load payload")
        require(
            file_size > 0 and address + file_size <= LOAD_ADDRESS + len(kernel),
            "ELF initialized payload lies outside flat BIOS image",
        )
        loads.append((address, address + memory_size, flags))
        file_spans.append((address, elf[offset : offset + file_size]))
    require(sorted(flags for _, _, flags in loads) == [4, 5, 6], "Expected separate RX, R and RW segments")
    loads.sort()
    for previous, current in zip(loads, loads[1:]):
        require((previous[1] + 4095) // 4096 * 4096 <= current[0], "Protection segments share a page")
    require(loads[0][0] == LOAD_ADDRESS and loads[0][2] == 5, "BIOS entry must begin the executable load segment")
    protected_end = (max(end for _, end, _ in loads) + 4095) // 4096 * 4096
    require(protected_end < 0x70000, "Aligned protected image overlaps reserved stacks")
    require(protected_end >= TRANSFER_END, "Protected image memory does not cover BIOS transfer padding")
    file_end = max(address + len(payload) for address, payload in file_spans)
    require(file_end - LOAD_ADDRESS == len(kernel), "ELF/flat initialized file spans disagree")
    expected = bytearray(len(kernel))
    for address, payload in file_spans:
        begin = address - LOAD_ADDRESS
        expected[begin : begin + len(payload)] = payload
    require(kernel == expected, "ELF/flat payload bytes or alignment padding disagree")


def package_image(boot: bytes, kernel: bytes, elf: bytes, packet_offset: int) -> bytes:
    validate(boot, kernel, elf, packet_offset)
    image = boot + kernel + bytes(PAYLOAD_SECTORS * 512 - len(kernel))
    require(len(image) <= IMAGE_BYTES, "BIOS read exceeds disposable disk size")
    return image + bytes(IMAGE_BYTES - len(image))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True, help="profile artifact directory")
    build = parser.parse_args().build_dir.resolve()
    boot = (build / "boot.bin").read_bytes()
    kernel = (build / "kernel.bin").read_bytes()
    elf = (build / "kernel.elf").read_bytes()
    boot_symbols = subprocess.check_output(["nm", "-a", str(build / "boot.o")], text=True)
    packets = [int(line.split()[0], 16) for line in boot_symbols.splitlines() if line.split()[-1] == "packet"]
    require(len(packets) == 1, "Missing unique assembler disk-packet symbol")
    (build / "aurora.img").write_bytes(package_image(boot, kernel, elf, packets[0]))


if __name__ == "__main__":
    main()
