#!/usr/bin/env python3
"""Check the real three-read BIOS contract, ELF/raw layout, and final-sector I/O."""

import argparse
from contextlib import nullcontext
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kernel_image", ROOT / "tests/kernel-image.py")
IMAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMAGE)
BASE = 0x10000
CAPACITY = 254 * 512
EARLY = 0x1C000
LAST = 0x2FBF8
BOUNDARIES = (0x1FDF8, 0x1FE00, 0x1FFF8, 0x20000)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run(*command: str) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
    require(result.returncode == 0, f"{command!r}: {result.stdout}{result.stderr}")
    return result


def fixture(size: int) -> tuple[bytes, bytes]:
    """Independent ELF64/flat model with three page-separated permission segments."""
    data_address = BASE + ((size - 1) // 4096) * 4096
    data_size = size - (data_address - BASE)
    entries = (
        (5, 0x1000, BASE, bytes([0x90]) * 64, 64),
        (4, 0x2000, BASE + 4096, bytes(range(64)), 64),
        (6, 0x3000, data_address, bytes(data_size - 1) + b"\xa5", 0x31000 - data_address),
    )
    header = bytearray(64)
    header[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHIQQQIHHHHHH", header, 16, 2, 62, 1, BASE, 64, 0, 0, 64, 56, 3, 0, 0, 0)
    elf = bytearray(0x3000 + data_size)
    elf[:64] = header
    raw = bytearray(size)
    for index, (flags, offset, address, data, memory) in enumerate(entries):
        struct.pack_into("<IIQQQQQQ", elf, 64 + 56 * index, 1, flags, offset, address, address, len(data), memory, 4096)
        elf[offset : offset + len(data)] = data
        raw[address - BASE : address - BASE + len(data)] = data
    return bytes(raw), bytes(elf)


def mutate(data: bytes, offset: int, value: int, width: int) -> bytes:
    result = bytearray(data)
    result[offset : offset + width] = value.to_bytes(width, "little")
    return bytes(result)


def controls(boot: bytes, packet: int) -> int:
    require(
        IMAGE.PAYLOAD_SECTORS == 254 and IMAGE.TRANSFER_END == 0x2FC00,
        "Capacity fixture and production transport disagree",
    )
    for size in (49153, 49904, CAPACITY):
        raw, elf = fixture(size)
        disk = IMAGE.package_image(boot, raw, elf, packet)
        require(len(disk) == 1024 * 1024 and disk[:512] == boot, "Disposable disk size/boot bytes changed")
        require(
            disk[512 : 512 + size] == raw and not any(disk[512 + size :]),
            "Disk payload or fixed-read zero padding changed",
        )
    raw, elf = fixture(49904)
    bad_raw, bad_elf = fixture(CAPACITY + 1)
    invalid = [
        (boot, bad_raw, bad_elf, "capacity"),
        (boot, b"", elf, "capacity"),
        (boot, raw[:-1], elf, "outside flat"),
        (boot, raw + b"\x00", elf, "file spans disagree"),
        (boot, mutate(raw, 0, 0, 1), elf, "payload bytes"),
        (boot, mutate(raw, 0x800, 1, 1), elf, "alignment padding"),
        (boot, raw, elf[:-1], "Truncated ELF"),
        (boot, raw, mutate(elf, 64 + 2 * 56 + 24, 0x1D000, 8), "physical/virtual"),
        (boot, raw, mutate(elf, 64 + 2 * 56 + 40, 752, 8), "transfer padding"),
        (boot, raw, mutate(elf, 64 + 2 * 56 + 40, 0x6FFFF - 0x1C000, 8), "reserved stacks"),
        (boot, raw, mutate(mutate(elf, 64 + 4, 4, 4), 64 + 56 + 4, 5, 4), "executable load"),
    ]
    for count in (0, 96, 128, 255):
        invalid.append((mutate(boot, packet + 2, count, 2), raw, elf, "sector count"))
    invalid.extend(
        (
            (mutate(boot, packet + 1, 1, 1), raw, elf, "packet header"),
            (mutate(boot, packet + 6, 0x2000, 2), raw, elf, "destination"),
            (mutate(boot, packet + 8, 2, 8), raw, elf, "LBA"),
            (mutate(mutate(boot, packet + 4, 65520, 2), packet + 6, 1, 2), raw, elf, "transfer window"),
            (mutate(mutate(boot, packet + 4, 256, 2), packet + 6, 0xFF0, 2), raw, elf, "canonical"),
        )
    )
    for index in (1, 2):
        begin = packet + index * 16
        invalid.extend(
            (
                (mutate(boot, begin + 2, 127, 2), raw, elf, "sector count"),
                (mutate(boot, begin + 6, 0x1000, 2), raw, elf, "destination"),
                (mutate(boot, begin + 8, 1, 8), raw, elf, "LBA"),
            )
        )
    for bad_boot, bad_raw, bad_elf, diagnostic in invalid:
        try:
            IMAGE.package_image(bad_boot, bad_raw, bad_elf, packet)
        except ValueError as error:
            require(diagnostic in str(error), f"Wrong rejection: {error}; expected {diagnostic}")
        else:
            raise RuntimeError(f"Invalid capacity/layout accepted: {diagnostic}")
    return len(invalid)


def build_probe(work: Path, boot: bytes, packet: int) -> bytes:
    # Sentinels are initialized file bytes, not BSS: old limit, both sides of
    # every transfer boundary, and the final eight bytes. Entry uses no C++; the
    # inherited 0x90000 stack serves only bounded serial-output calls.
    source = work / "capacity.S"
    source.write_text(r"""
.section .text.entry,"ax"
.code64
.global _start
_start:
    mov $0x3f9, %dx
    xor %al, %al
    out %al, %dx
    mov $0x3fb, %dx
    mov $0x80, %al
    out %al, %dx
    mov $0x3f8, %dx
    mov $1, %al
    out %al, %dx
    mov $0x3f9, %dx
    xor %al, %al
    out %al, %dx
    mov $0x3fb, %dx
    mov $3, %al
    out %al, %dx
    mov $0x3fa, %dx
    mov $0xc7, %al
    out %al, %dx
    mov $0x3fc, %dx
    mov $0x0b, %al
    out %al, %dx
    movabs $0x1c000, %rdi
    mov (%rdi), %r8
    movabs $0x2fbf8, %rdi
    mov (%rdi), %r9
    lea observed(%rip), %rsi
    call print
    mov %r8, %r10
    call hexadecimal
    lea final_label(%rip), %rsi
    call print
    mov %r9, %r10
    call hexadecimal
    lea newline(%rip), %rsi
    call print
    movabs $0x123456789abcdef0, %rax
    cmp %rax, %r8
    jne failed_early
    movabs $0x0fedcba987654321, %rax
    cmp %rax, %r9
    jne failed_last
    lea boundaries(%rip), %r12
    mov $4, %r13d
check_boundary:
    mov (%r12), %r10
    lea boundary_label(%rip), %rsi
    call print
    call hexadecimal
    mov (%r12), %rax
    mov (%rax), %r10
    lea equals(%rip), %rsi
    call print
    call hexadecimal
    lea newline(%rip), %rsi
    call print
    mov (%r12), %rax
    mov (%rax), %rax
    movabs $0x1122334455667788, %rdx
    cmp %rax, %rdx
    jne failed_last
    add $8, %r12
    dec %r13d
    jnz check_boundary
    lea passed(%rip), %rsi
    call print
    mov $0x10, %eax
    jmp finish
failed_early:
    lea missing(%rip), %rsi
    call print
    mov $0x11, %eax
    jmp finish
failed_last:
    lea corrupt(%rip), %rsi
    call print
    mov $0x11, %eax
finish:
    out %eax, $0xf4
    cli
1:  hlt
    jmp 1b
print:
    lodsb
    test %al, %al
    jz print_done
    call putc
    jmp print
print_done:
    ret
putc:
    mov %al, %bl
1:  mov $0x3fd, %dx
    in %dx, %al
    test $0x20, %al
    jz 1b
    mov $0x3f8, %dx
    mov %bl, %al
    out %al, %dx
    ret
hexadecimal:
    mov $16, %ecx
    lea digits(%rip), %rdi
1:  rol $4, %r10
    mov %r10, %rax
    and $15, %eax
    mov (%rdi,%rax), %al
    call putc
    loop 1b
    ret
.section .rodata,"a"
observed: .asciz "AURORA_BIOS_CAPACITY_PROBE: old="
final_label: .asciz " final="
newline: .asciz "\n"
passed: .asciz "AURORA_BIOS_CAPACITY_OK\n"
missing: .asciz "AURORA_BIOS_CAPACITY_OLD_LIMIT_MISSING\n"
corrupt: .asciz "AURORA_BIOS_CAPACITY_LAST_SECTOR_BAD\n"
boundary_label: .asciz "BOUNDARY "
equals: .asciz "="
.balign 8
boundaries: .quad 0x1fdf8, 0x1fe00, 0x1fff8, 0x20000
digits: .ascii "0123456789abcdef"
.section .data,"aw"
.quad 0x123456789abcdef0
.org 0x3df8
.quad 0x1122334455667788
.quad 0x1122334455667788
.org 0x3ff8
.quad 0x1122334455667788
.quad 0x1122334455667788
.org 0x13bf8
.quad 0x0fedcba987654321
.section .bss,"aw",@nobits
.space 4096
.section .note.GNU-stack,"",@progbits
""")
    linker = work / "capacity.ld"
    linker.write_text("""
OUTPUT_FORMAT(elf64-x86-64)
ENTRY(_start)
PHDRS { code PT_LOAD FLAGS(5); rodata PT_LOAD FLAGS(4); data PT_LOAD FLAGS(6); }
SECTIONS {
 . = 0x10000; .text : { *(.text.entry) *(.text) } :code
 . = 0x11000; .rodata : { *(.rodata) } :rodata
 . = 0x1c000; .data : { *(.data) } :data
 ASSERT(. == 0x2fc00, "capacity sentinel must end at last loaded byte")
 .bss : { *(.bss) } :data
 /DISCARD/ : { *(.note*) *(.comment*) }
}
""")
    obj, elf, raw = (work / f"capacity.{suffix}" for suffix in ("o", "elf", "bin"))
    run("as", "--64", str(source), "-o", str(obj))
    run("ld", "--build-id=none", "-nostdlib", "-z", "max-page-size=0x1000", "-T", str(linker), str(obj), "-o", str(elf))
    run("objcopy", "-O", "binary", str(elf), str(raw))
    payload = raw.read_bytes()
    require(len(payload) == CAPACITY, "Probe does not fill the transport capacity")
    require(
        int.from_bytes(payload[EARLY - BASE : EARLY - BASE + 8], "little") == 0x123456789ABCDEF0,
        "Probe lost beyond-old-limit sentinel",
    )
    require(
        int.from_bytes(payload[LAST - BASE : LAST - BASE + 8], "little") == 0x0FEDCBA987654321,
        "Probe lost final-sector sentinel",
    )
    return IMAGE.package_image(boot, payload, elf.read_bytes(), packet)


def smoke(work: Path, disk: bytes, packet: int) -> list[dict]:
    qemu = os.environ.get("QEMU", "qemu-system-x86_64")
    require(shutil.which(qemu) is not None, "BLOCKED: QEMU required for actual BIOS capacity smoke")
    args = [qemu]
    if os.environ.get("QEMU_DATA"):
        args += ["-L", os.environ["QEMU_DATA"]]
    # Invalid/truncated disks bypass packaging only to exercise real loader
    # refusal and payload corruption detection, never to qualify an image.
    fixtures = (
        ("full-254", disk, 33),
        ("old-96-negative", mutate(disk, packet + 2, 96, 2), 67),
        ("truncated-first", disk[: 512 * 127], 67),
        ("truncated-second", disk[: 512 * 128], 69),
        ("truncated-third", disk[: 512 * 129], 71),
        ("last-sector-negative", mutate(disk, 512 + LAST - BASE, 0, 1), 35),
    )
    results = []
    for name, contents, expected in fixtures:
        image = work / f"{name}.img"
        image.write_bytes(contents)
        command = args + [
            "-machine",
            "pc",
            "-accel",
            "tcg",
            "-cpu",
            "qemu64",
            "-smp",
            "1",
            "-m",
            "32M",
            "-drive",
            f"file={image},format=raw,if=ide",
            "-boot",
            "c",
            "-nic",
            "none",
            "-display",
            "none",
            "-serial",
            "stdio",
            "-monitor",
            "none",
            "-no-reboot",
            "-device",
            "isa-debug-exit,iobase=0xf4,iosize=0x04",
        ]
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15, text=True
        )
        (work / f"{name}.log").write_text(result.stdout)
        require(
            result.returncode == expected,
            f"{name}: expected CPU exit {expected}, got {result.returncode}: {result.stdout}",
        )
        if name.startswith("truncated-") or name == "old-96-negative":
            require("AURORA_BIOS_CAPACITY_" not in result.stdout, f"{name}: entered payload after loader failure")
            results.append(
                {
                    "name": name,
                    "exit": result.returncode,
                    "expected": expected,
                    "image_sha256": hashlib.sha256(contents).hexdigest(),
                    "command": command,
                }
            )
            continue
        observed = re.findall(
            r"^AURORA_BIOS_CAPACITY_PROBE: old=([0-9a-f]{16}) final=([0-9a-f]{16})$", result.stdout, re.MULTILINE
        )
        require(len(observed) == 1, f"{name}: missing unique CPU-observed sentinel values")
        early, last = (int(value, 16) for value in observed[0])
        if name == "full-254":
            marker = "AURORA_BIOS_CAPACITY_OK"
            require(
                re.findall(r"^BOUNDARY ([0-9a-f]{16})=([0-9a-f]{16})$", result.stdout, re.MULTILINE)
                == [(f"{address:016x}", "1122334455667788") for address in BOUNDARIES],
                "CPU did not observe every transfer boundary sentinel",
            )
            require(
                (early, last) == (0x123456789ABCDEF0, 0x0FEDCBA987654321),
                "Full read did not observe both exact sentinel values",
            )
        else:
            marker = "AURORA_BIOS_CAPACITY_LAST_SECTOR_BAD"
            require(
                (early, last) == (0x123456789ABCDEF0, 0x0FEDCBA987654300),
                "Corruption control did not observe the exact changed final byte",
            )
        markers = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("AURORA_BIOS_CAPACITY_") and not line.startswith("AURORA_BIOS_CAPACITY_PROBE:")
        ]
        require(markers == [marker], f"{name}: wrong or duplicate runtime result markers")
        results.append(
            {
                "name": name,
                "exit": result.returncode,
                "expected": expected,
                "observed_old": observed[0][0],
                "observed_final": observed[0][1],
                "observed_boundaries": re.findall(
                    r"^BOUNDARY ([0-9a-f]{16})=([0-9a-f]{16})$", result.stdout, re.MULTILINE
                ),
                "marker": marker,
                "image_sha256": hashlib.sha256(contents).hexdigest(),
                "command": command,
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", action="store_true", help="Require actual final-sector CPU probes")
    parser.add_argument("--keep-directory", type=Path, help="Retain evidence in a new directory")
    args = parser.parse_args()
    for tool in ("as", "ld", "nm", "objcopy", "readelf"):
        require(shutil.which(tool) is not None, f"Missing dependency: {tool}")
    if args.keep_directory:
        args.keep_directory.mkdir(parents=True, exist_ok=False)
        workspace = nullcontext(str(args.keep_directory.resolve()))
    else:
        workspace = tempfile.TemporaryDirectory(prefix="aurora-capacity-")
    with workspace as directory:
        work = Path(directory)
        obj, binary = work / "boot.o", work / "boot.bin"
        run("as", "--32", str(ROOT / "kernel/boot.S"), "-o", str(obj))
        notes = [
            line.split(".note.GNU-stack", 1)[1].split()
            for line in run("readelf", "-SW", str(obj)).stdout.splitlines()
            if ".note.GNU-stack" in line
        ]
        require(
            len(notes) == 1
            and notes[0][0] == "PROGBITS"
            and int(notes[0][3], 16) == 0
            and notes[0][5:] == ["0", "0", "1"],
            "Expected one empty non-executable GNU-stack object note",
        )
        run(str(ROOT / "scripts/kernel-boot-link.sh"), str(obj), str(binary))
        boot = binary.read_bytes()
        symbols = run("nm", "-a", str(obj)).stdout.splitlines()
        packets = [int(row.split()[0], 16) for row in symbols if row.split()[-1] == "packet"]
        require(len(packets) == 1, "Missing unique DAP symbol")
        packet = packets[0]
        negatives = controls(boot, packet)
        disk = build_probe(work, boot, packet)
        results = smoke(work, disk, packet) if args.qemu else []
        receipt = {
            "capacity_bytes": CAPACITY,
            "load_begin": BASE,
            "load_end": BASE + CAPACITY,
            "positive_sizes": [49153, 49904, CAPACITY],
            "negative_cases": negatives,
            "probe_bytes": len(disk),
            "qemu": results,
        }
        (work / "results.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            f"PASS: 254-sector transport; three exact ELF/raw boundary fixtures; {negatives} rejected inputs; "
            "linked final-sector probe validates at 130,048 bytes"
        )
        if args.qemu:
            print(
                "PASS: actual BIOS final-sector read (exit 33); loader refusal/truncation "
                "and corrupted-final-sector controls"
            )


if __name__ == "__main__":
    main()
