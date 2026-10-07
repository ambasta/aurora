#!/usr/bin/env python3
"""Validate the fixed boot contract and assemble a disposable raw disk image."""
from pathlib import Path
import subprocess

PAYLOAD_SECTORS = 127
LOAD_ADDRESS = 0x10000
TRANSFER_END = LOAD_ADDRESS + PAYLOAD_SECTORS * 512
IMAGE_BYTES = 1024 * 1024


def require(condition: bool, message: str) -> None:
    # Explicit checks remain active under PYTHONOPTIMIZE / python -O.
    if not condition:
        raise ValueError(message)


def validate_bios_root(bios: str, uefi: str) -> None:
    """Keep the existing BIOS value/ownership probe, without unused UEFI imports."""
    begin = uefi.index("auto aurora_kernel_value()")
    end = uefi.index("\n}\n", begin) + 3
    require(bios == "module kernel;\n\n" + uefi[begin:end],
            "BIOS Aurora root must preserve the exact value/ownership probe only")


def validate_language_symbols(symbols: str, final_image: bool = False) -> None:
    rows = [line.split() for line in symbols.splitlines() if line.strip()]
    require(rows and all(len(row) == 3 for row in rows), "Invalid defined Aurora symbol inventory")
    entries = [(row[1], row[2]) for row in rows if row[2].startswith("aurora_kernel_")]
    expected = [("T", "aurora_kernel_value")]
    if final_image:
        expected.append(("T", "aurora_kernel_main"))  # Existing C++ entry.
    require(sorted(entries) == sorted(expected), "Unexpected BIOS Aurora kernel entry set")
    forbidden = ("interrupt_budget", "round_robin", "TickDecision", "SelectionDecision",
                 "ipc_transition", "TransactionSnapshot", "TransactionDecision")
    require(not any(part in row[2] for row in rows for part in forbidden),
            "Unused UEFI policy graph linked into BIOS image")


def root_controls(bios: str, uefi: str) -> int:
    validate_bios_root(bios, uefi)
    valid = "00000000 T aurora_kernel_value\n0000004b T aurora_reflect_size\n"
    validate_language_symbols(valid)
    validate_language_symbols(valid + "000000cc T aurora_kernel_main\n", final_image=True)
    invalid_symbols = (
        "", valid + "000000cc T aurora_kernel_value\n",
        valid.replace("T aurora_kernel_value", "t aurora_kernel_value"),
        valid.replace("aurora_kernel_value", "aurora_kernel_unexpected"),
        valid + "000000cc T aurora_kernel_budget_tick\n",
        valid + "000000cc T aurora_kernel_round_robin_next\n",
        valid + "000000cc T aurora_kernel_ipc_transition\n",
        valid + "000000cc t __au_v_m2_6kernel14ipc_transition_n1_6kernel_d22transaction_transition\n",
        valid + "000000cc t __au_k_TransactionSnapshot\n",
        valid + "000000cc t __au_k_TransactionDecision\n",
        valid + "000000cc t __au_v_m2_6kernel16interrupt_budget_n1_6kernel_d14interrupt_tick\n",
        valid + "000000cc t __au_v_m2_6kernel11round_robin_n1_6kernel_d16round_robin_next\n",
        valid + "000000cc t __au_k_TickDecision\n",
        valid + "000000cc t __au_k_SelectionDecision\n",
        valid + "malformed\n",
    )
    bad_inventories = [(symbols, False) for symbols in invalid_symbols]
    bad_inventories += [(symbols + "000000cc T aurora_kernel_main\n", True)
                        for symbols in invalid_symbols]
    bad_inventories += [(valid, True), (valid + "000000cc T aurora_kernel_main\n" * 2, True)]
    for invalid, final_image in bad_inventories:
        try:
            validate_language_symbols(invalid, final_image)
        except ValueError:
            continue
        raise RuntimeError("Invalid BIOS Aurora graph accepted by negative control")
    bad_roots = (bios.replace("own(40)", "own(41)"),
                 bios.replace("module kernel;", "module kernel;\nimport kernel.round_robin;"),
                 bios + "\nauto extra() -> i64 { return 0; }\n")
    for invalid in bad_roots:
        try:
            validate_bios_root(invalid, uefi)
        except ValueError:
            continue
        raise RuntimeError("Changed BIOS value/root accepted by negative control")
    return len(bad_inventories) + len(bad_roots)


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
    require(segment * 16 + offset == LOAD_ADDRESS, "Loader destination disagrees with kernel entry")
    require(offset + sectors * 512 <= 65536, "BIOS read crosses segment transfer window")
    require(segment == 0x1000 and offset == 0, "Loader destination is not canonical 1000:0000")
    require(int.from_bytes(packet[8:16], "little") == 1, "Loader LBA is not the image payload")
    require(0 < len(kernel) <= sectors * 512,
            f"Kernel payload {len(kernel)} bytes exceeds bounded BIOS capacity {sectors * 512} bytes")
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
    file_spans = []
    for index in range(count):
        header = elf[table + index * stride:table + (index + 1) * stride]
        if int.from_bytes(header[:4], "little") != 1:
            continue
        flags = int.from_bytes(header[4:8], "little")
        offset = int.from_bytes(header[8:16], "little")
        address = int.from_bytes(header[16:24], "little")
        physical_address = int.from_bytes(header[24:32], "little")
        file_size = int.from_bytes(header[32:40], "little")
        memory_size = int.from_bytes(header[40:48], "little")
        require(flags in (4, 5, 6), "Unexpected or writable-executable ELF segment")
        require(address % 4096 == 0 and 0x10000 <= address < 0x70000
                and memory_size >= file_size and address + memory_size < 0x70000,
                "Invalid protected segment range")
        require(physical_address == address, "ELF load physical/virtual addresses disagree")
        require(offset + file_size <= len(elf), "Truncated ELF load payload")
        require(file_size > 0 and address + file_size <= LOAD_ADDRESS + len(kernel),
                "ELF initialized payload lies outside flat BIOS image")
        loads.append((address, address + memory_size, flags))
        file_spans.append((address, elf[offset:offset + file_size]))
    require(sorted(flags for _, _, flags in loads) == [4, 5, 6], "Expected separate RX, R and RW segments")
    loads.sort()
    for previous, current in zip(loads, loads[1:]):
        require((previous[1] + 4095) // 4096 * 4096 <= current[0], "Protection segments share a page")
    require(loads[0][0] == LOAD_ADDRESS and loads[0][2] == 5,
            "BIOS entry must begin the executable load segment")
    protected_end = (max(end for _, end, _ in loads) + 4095) // 4096 * 4096
    require(protected_end < 0x70000, "Aligned protected image overlaps reserved stacks")
    require(protected_end >= TRANSFER_END,
            "Protected image memory does not cover BIOS transfer padding")
    file_end = max(address + len(payload) for address, payload in file_spans)
    require(file_end - LOAD_ADDRESS == len(kernel), "ELF/flat initialized file spans disagree")
    expected = bytearray(len(kernel))
    for address, payload in file_spans:
        begin = address - LOAD_ADDRESS
        expected[begin:begin + len(payload)] = payload
    require(kernel == expected, "ELF/flat payload bytes or alignment padding disagree")


def package_image(boot: bytes, kernel: bytes, elf: bytes, packet_offset: int) -> bytes:
    validate(boot, kernel, elf, packet_offset)
    image = boot + kernel + bytes(PAYLOAD_SECTORS * 512 - len(kernel))
    require(len(image) <= IMAGE_BYTES, "BIOS read exceeds disposable disk size")
    return image + bytes(IMAGE_BYTES - len(image))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    build = root / "build"
    root_negative_controls = root_controls((root / "examples/kernel-bios.au").read_text(),
                  (root / "examples/kernel.au").read_text())
    # Check the compiled root and final image separately. The generic reflection
    # entrypoints are compiler bootstrap output; UEFI policy graphs are forbidden.
    for artifact in ("kernel-language.o", "kernel.elf"):
        validate_language_symbols(subprocess.check_output(
            ["nm", "--defined-only", str(build / artifact)], text=True),
            final_image=artifact == "kernel.elf")
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
    (build / "aurora.img").write_bytes(package_image(boot, kernel, elf, packet_offset))
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
                    (boot, bytes(PAYLOAD_SECTORS * 512 + 1), elf), (boot, b"", elf),
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

    print(f"PASS: BIOS value/ownership root unchanged; no unused UEFI policy graph; {root_negative_controls} root/symbol negative controls")


if __name__ == "__main__":
    main()
