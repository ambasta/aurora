#!/usr/bin/env python3
"""Literal-offset handwritten entry/exit probes for direct owned-field capabilities."""

import argparse
from pathlib import Path
import re
import tempfile

from integer_oracle import NativeRunner, command, require, validate_values

# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = Path(__file__).resolve().parent / "ir" / "owned-mutation-ir" / "abi.air"


WORD = 0xFEDCBA9876543210
ORIGINAL = bytes([197]) + bytes([0xAB]) * 7 + bytes([17]) + bytes([0xAB]) * 7
ORIGINAL += (0x123456789ABCDEF0).to_bytes(8, "little") + bytes([223]) + bytes([0xAB]) * 7
CHILD = bytes([204]) + bytes([0xAB]) * 7 + WORD.to_bytes(8, "little")
RECORD = ORIGINAL + CHILD


def data(label, value):
    return label + ":\n.byte " + ",".join(str(byte) for byte in value) + "\n"


def comparisons(pointer, expected):
    return "".join(f"cmpb ${byte},{index}({pointer})\njne .Lowned_fail\n" for index, byte in enumerate(expected))


def handwritten_method(mode):
    text = """movq %rsp,%rcx
andq $15,%rcx
cmpq $8,%rcx
jne .Lowned_fail
cmpb $197,-8(%r10)
jne .Lowned_fail
cmpb $223,16(%r10)
jne .Lowned_fail
cmpb $204,(%r10)
jne .Lowned_fail
"""
    text += f"movabsq ${WORD},%rcx\ncmpq %rcx,8(%r10)\njne .Lowned_fail\n"
    if mode == 2:
        # A copied Holder occupies 32 bytes; u64 follows at 32; Child starts at 40.
        text += "cmpq $42,32(%r11)\njne .Lowned_fail\n"
        for index in (0, 8, 16, 17, 18, 19, 20, 21, 22, 23, 24):
            text += f"cmpb ${ORIGINAL[index]},{index}(%r11)\njne .Lowned_fail\n"
        text += "cmpb $204,40(%r11)\njne .Lowned_fail\n"
        text += f"movabsq ${WORD},%rcx\ncmpq %rcx,48(%r11)\njne .Lowned_fail\n"
        # Result, argument record and receiver must be independently addressed.
        text += """cmpq %rax,%r10
je .Lowned_fail
cmpq %r11,%r10
je .Lowned_fail
cmpq %rax,%r11
je .Lowned_fail
movb $204,(%rax)
movq %rcx,8(%rax)
movq $42,8(%r10)
ret
"""
    elif mode == 1:
        text += """cmpq $42,%rdi
jne .Lowned_fail
cmpq %r11,%r10
je .Lowned_fail
movb $204,(%r11)
movq $42,8(%r11)
ret
"""
    else:
        text += "cmpq $42,%rdi\njne .Lowned_fail\nmovq %rdi,8(%r10)\nmovq %rdi,%rax\nret\n"
    return text


def wrapper(implicit, mode):
    name = "implicit_entry" if implicit else "local_entry"
    text = "\n.text\n.globl test\ntest:\nsubq $8,%rsp\nleaq input(%rip),%r11\n"
    if implicit:
        text += "leaq receiver(%rip),%r10\n"
        if mode:
            text += "leaq result(%rip),%rax\n"
    elif mode:
        text += "leaq result(%rip),%r10\n"
    text += f"call {name}\n"
    if mode:
        text += "leaq result(%rip),%rdi\ncmpb $204,(%rdi)\njne .Lowned_fail\n"
        value = 42 if mode == 1 else WORD
        text += f"movabsq ${value},%rcx\ncmpq %rcx,8(%rdi)\njne .Lowned_fail\n"
        text += "cmpq $99,16(%rdi)\njne .Lowned_fail\n"
    else:
        text += "cmpq $42,%rax\njne .Lowned_fail\n"
    text += "leaq input(%rip),%rdi\n" + comparisons("%rdi", RECORD)
    if implicit:
        expected = bytearray(ORIGINAL)
        expected[8] = 204
        expected[16:24] = (WORD if mode == 1 else 42).to_bytes(8, "little")
        text += "leaq receiver(%rip),%rdi\n" + comparisons("%rdi", expected)
    text += "movq $42,%rax\naddq $8,%rsp\nret\n.Lowned_fail:\nud2\n.data\n.balign 8\n"
    text += data("input", RECORD) + data("receiver", ORIGINAL)
    text += data("result", bytes([0xCD]) * 16 + (99).to_bytes(8, "little"))
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()
    count = 0
    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aurora-owned-mutation-abi-") as temporary:
        runner = NativeRunner(Path(temporary), None, 5)
        for implicit in (False, True):
            for mode in (0, 1, 2):
                assembly = command(
                    [args.fixture.resolve(), "--output", AIR, f"{'implicit' if implicit else 'local'}-{mode}"]
                ).stdout.decode()
                for handwritten in (False, True):
                    candidate = assembly
                    if handwritten:
                        symbol = ("set_word", "copy_child", "combined")[mode]
                        pattern = rf"(?m)^{symbol}:\n[\s\S]*?^\.size {symbol},[^\n]*\n"
                        candidate, replaced = re.subn(
                            pattern, f"{symbol}:\n{handwritten_method(mode)}.size {symbol}, .-{symbol}\n", assembly
                        )
                        require(replaced == 1, "one exact method body replaced")
                    name = f"{'implicit' if implicit else 'local'} mode={mode} handwritten-exit={handwritten}"
                    if args.work_dir:
                        filename = f"{'implicit' if implicit else 'local'}-{mode}-{int(handwritten)}.s"
                        (args.work_dir / filename).write_text(candidate + wrapper(implicit, mode))
                    observed, _ = runner.assemble(candidate + wrapper(implicit, mode), ["test"])
                    if args.work_dir:
                        stem = f"{'implicit' if implicit else 'local'}-{mode}-{int(handwritten)}"
                        (args.work_dir / (stem + ".elf")).write_bytes((runner.directory / "program").read_bytes())
                        (args.work_dir / (stem + ".observation")).write_text(repr(observed) + "\n")
                    validate_values(observed, [42], [name])
                    count += 1
                    print("PASS owned ABI", name, flush=True)
    print(f"PASS owned ABI: {count} literal-layout handwritten boundary cases")


if __name__ == "__main__":
    main()
