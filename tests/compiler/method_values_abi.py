#!/usr/bin/env python3
"""Independent native tests for the NEW M022 hidden method ABI and old controls.

Usage: method_values_abi.py path/to/prebuilt-method-values-ir
A textual IR case supplies the IR directly, without source lowering. One boundary
side is replaced by independently authored assembly in every execution. Expected
records/offsets are literal protocol oracles, never obtained from emitter/layout
helpers. Private local symbols stay local in the same assembly translation unit;
these bootstrap adapters do not add a source-language C ABI.
"""

from pathlib import Path
import argparse
import hashlib
import re
import resource
import shutil
import subprocess
import tempfile

# Verified textual IR cases; the aurora-ir-check driver prints their assembly.
AIR = Path(__file__).resolve().parent / "ir" / "method-values-ir" / "abi.air"


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def run(command, expected_exit=0):
    completed = subprocess.run(
        [str(x) for x in command],
        capture_output=True,
        timeout=30,
        preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)),
    )
    require(
        completed.returncode == expected_exit,
        f"{command}: exit {completed.returncode}, stdout={completed.stdout!r}, stderr={completed.stderr!r}",
    )
    return completed.stdout


def q(value):
    return value.to_bytes(8, "little", signed=False)


# Literal wire model, intentionally independent of C++ layout calculation.
TINY = bytes([3, 5]) + bytes(6)
PACK = bytes([11]) + bytes(7) + q(13) + bytes([17]) + bytes(7)
MIXED = TINY + bytes([7]) + bytes(7) + bytes(8) + q(1) + PACK + q(19)
COMPOSED = bytes([3, 5]) + bytes(6) + q(1) + bytes([17]) + bytes(7)
require(len(MIXED) == 64 and len(COMPOSED) == 24, "independent protocol extent")
COUNT = 0


def data(name, contents):
    return f"{name}:\n.byte " + ",".join(str(x) for x in contents) + "\n"


def replace(assembly, name, body):
    pattern = rf"(?m)^{re.escape(name)}:\n[\s\S]*?^\.size {re.escape(name)},[^\n]*\n"
    text, count = re.subn(pattern, f"{name}:\n{body}\n.size {name}, .-{name}\n", assembly)
    require(count == 1, f"exactly one replaceable fixture {name}: {count}")
    return text


ALIGN = """movq %rsp, %rcx
andq $15, %rcx
cmpq $8, %rcx
jne .Labi_fail
"""
POISON = """movq $-101, %rdi
movq $-102, %rsi
movq $-103, %rdx
movq $-104, %rcx
movq $-105, %r8
movq $-106, %r9
movq $-107, %rax
"""
CLOBBER = """movq $-111, %r10
movq $-112, %r11
movq $-113, %rax
ret
"""


def compare_bytes(pointer, blob, size, suffix):
    return f"""xorq %rcx, %rcx
.Lcompare_{suffix}:
movzbq ({pointer},%rcx), %rsi
cmpb {blob}(%rcx), %sil
jne .Labi_fail
incq %rcx
cmpq ${size}, %rcx
jne .Lcompare_{suffix}
"""


def disjoint(a, a_size, b, b_size, suffix):
    return f"""leaq {a_size}({a}), %r8
cmpq {b}, %r8
jbe .Ldisjoint_{suffix}
leaq {b_size}({b}), %r9
cmpq {a}, %r9
ja .Labi_fail
.Ldisjoint_{suffix}:
"""


def check_record(expected, size, suffix):
    return (
        ALIGN
        + disjoint("%r10", 8, "%r11", size, suffix)
        + """cmpq $1000, (%r10)
jne .Labi_fail
"""
        + compare_bytes("%r11", expected, size, suffix)
    )


def pack_write(pointer, number=13, first=11):
    return f"movb ${first}, 0({pointer})\nmovq ${number}, 8({pointer})\nmovb $17, 16({pointer})\n"


def test(
    name,
    assembly,
    entry,
    replacements=None,
    expected=42,
    input_record=MIXED,
    result_bytes=None,
    extra_data="",
    expected_exit=0,
    result_capacity=32,
):
    global COUNT
    case = WORK / f"{COUNT:02d}-{name}"
    case.mkdir()
    code = assembly
    for symbol, body in (replacements or {}).items():
        code = replace(code, symbol, body)
    code += "\n.text\n.globl _start\n_start:\n" + entry
    code += f"""cmpq ${expected}, %rax
jne .Labi_fail
movq $60, %rax
xorq %rdi, %rdi
syscall
.Labi_fail:
movq $60, %rax
movq $91, %rdi
syscall
.data
.balign 16
receiver: .quad 1000
record_left: .quad 0x5252525252525252
"""
    code += data("input_record", input_record)
    code += "record_right: .quad 0x5353535353535353\n"
    code += data("expected_record", MIXED)
    code += data("expected_pack_record", PACK + bytes(8))
    code += data("expected_composed_record", COMPOSED + bytes(8))
    code += data("expected_empty_record", bytes(16))
    code += f"""result_left: .quad 0x6161616161616161
result: .fill {result_capacity},1,204
result_right: .quad 0x6262626262626262
"""
    if result_bytes is not None:
        code += data("expected_result", result_bytes)
    code += extra_data + '\n.section .note.GNU-stack,"",@progbits\n'
    (case / "program.s").write_text(code)
    run(["as", "--64", case / "program.s", "-o", case / "program.o"])
    symbols = run(["nm", case / "program.o"]).decode()
    # New and historical hidden conventions must stay private symbols.
    for symbol in [
        "abi_in_scalar",
        "abi_in_result",
        "abi_composed",
        "abi_empty",
        "abi_old_ordinary",
        "abi_old_constructor",
        "abi_old_result_method",
    ]:
        require(re.search(rf"\bt {symbol}$", symbols, re.M), f"{name}: {symbol} lost local binding")
    run(["ld", "-o", case / "program", case / "program.o"])
    run([case / "program"], expected_exit=expected_exit)
    COUNT += 1
    print("PASS method ABI", name, flush=True)


def check_canaries(result_tail=24):
    return f"""movabsq $0x5252525252525252, %rsi
cmpq %rsi, record_left
jne .Labi_fail
movabsq $0x5353535353535353, %rsi
cmpq %rsi, record_right
jne .Labi_fail
movabsq $0x6161616161616161, %rsi
cmpq %rsi, result_left
jne .Labi_fail
movabsq $0x6262626262626262, %rsi
cmpq %rsi, result_right
jne .Labi_fail
movabsq $0xcccccccccccccccc, %rsi
cmpq %rsi, result+{result_tail}
jne .Labi_fail
"""


def incoming_setup(target, mode="new"):
    setup = POISON + "leaq receiver, %r10\nleaq input_record, %r11\n"
    if mode == "new":
        setup += "leaq result, %rax\n"
    elif mode == "ordinary":
        setup += "leaq result, %r10\n"
    elif mode == "old_result":
        setup += "movq $13, %rdi\nleaq result, %r11\n"
    elif mode == "old_scalar":
        setup += "movq $13, %rdi\n"
    elif mode == "constructor":
        setup += "leaq result, %r10\n"
    return setup + f"call {target}\n"


def result_check(size, suffix):
    return (
        "leaq result, %rdx\n"
        + compare_bytes("%rdx", "expected_result", size, suffix)
        + check_canaries(max(size, 24))
        + "movq $42, %rax\n"
    )


def native_cases(assembly):
    clobber = (
        ALIGN
        + """movb $201, input_record
movb $202, input_record+1
movb $203, input_record+8
movq $0, input_record+24
movb $204, input_record+32
movq $205, input_record+40
movb $206, input_record+48
movq $207, input_record+56
"""
        + CLOBBER
    )
    receiver_probe = (
        ALIGN
        + """leaq receiver, %rcx
cmpq %rcx, %r10
jne .Labi_fail
"""
        + CLOBBER
    )
    nested_probe = check_record("expected_record", 8, "nested") + CLOBBER
    saved_inputs = """leaq receiver, %rsi
cmpq %rsi, -104(%rbp)
jne .Labi_fail
leaq input_record, %rsi
cmpq %rsi, -112(%rbp)
jne .Labi_fail
"""
    scalar_frame = """leaq -120(%rbp), %rsi
cmpq %rsi, %rsp
jne .Labi_fail
"""
    result_frame = """leaq result, %rsi
cmpq %rsi, -120(%rbp)
jne .Labi_fail
leaq -136(%rbp), %rsi
cmpq %rsi, %rsp
jne .Labi_fail
"""
    replacements = {
        "abi_clobber": saved_inputs + scalar_frame + clobber,
        "abi_receiver_probe": receiver_probe,
        "abi_nested_probe": nested_probe,
    }
    # Saved inputs are bound before both nested ordinary and forwarded calls
    # overwrite the original record and caller-clobbered hidden registers.
    test(
        "incoming-six-mixed-scalar-nested",
        assembly,
        incoming_setup("abi_in_scalar") + check_canaries(),
        replacements,
        expected=1075,
    )
    expected = bytes([3]) + bytes([204]) * 7 + q(1075) + bytes([17]) + bytes([204]) * 7
    test(
        "incoming-six-mixed-class-nested",
        assembly,
        incoming_setup("abi_in_result") + result_check(24, "new_result"),
        {**replacements, "abi_clobber": saved_inputs + result_frame + clobber},
        result_bytes=expected,
    )
    # Generated callers keep an unrelated operand pushed. The independently
    # written callee checks entry alignment and every byte, including padding.
    scalar_target = check_record("expected_record", 64, "out_scalar") + "movq $42, %rax\nret\n"
    test(
        "outgoing-six-mixed-scalar-odd-stack",
        assembly,
        "call abi_out_scalar\n",
        {"abi_out_target_scalar": scalar_target},
        expected=43,
    )
    result_target = (
        """testq $7, %rax
jnz .Labi_fail
cmpq %r10, %rax
je .Labi_fail
cmpq %r11, %rax
je .Labi_fail
movq %rax, %rdx
"""
        + disjoint("%rdx", 24, "%r10", 8, "result_receiver")
        + disjoint("%rdx", 24, "%r11", 64, "result_record")
        + check_record("expected_record", 64, "out_result")
        + pack_write("%rdx", 4242)
        + "xorq %rax, %rax\nret\n"
    )
    test(
        "outgoing-six-mixed-class-odd-stack",
        assembly,
        "call abi_out_result\n",
        {"abi_out_target_result": result_target},
        expected=4243,
    )
    wrong = bytearray(MIXED)
    wrong[8] = 8
    detector = check_record("deliberately_wrong_record", 64, "self_control") + "movq $42, %rax\nret\n"
    test(
        "control-detects-wrong-packed-scalar",
        assembly,
        "call abi_out_scalar\n",
        {"abi_out_target_scalar": detector},
        expected=43,
        expected_exit=91,
        extra_data=data("deliberately_wrong_record", wrong),
    )
    composed_result = bytes([3, 5]) + bytes([204]) * 6 + q(1) + bytes([17]) + bytes([204]) * 7
    test(
        "incoming-composed-enum-empty-child",
        assembly,
        incoming_setup("abi_composed") + result_check(24, "composed_in"),
        input_record=COMPOSED + bytes(8),
        result_bytes=composed_result,
    )
    composed_target = (
        "movq %rax, %rdx\n"
        + check_record("expected_composed_record", 32, "composed_out")
        + """movb $3, (%rdx)
movb $5, 1(%rdx)
movq $1, 8(%rdx)
movb $17, 16(%rdx)
xorq %rax, %rax
ret
"""
    )
    test(
        "outgoing-forwarded-composed-shape",
        assembly,
        incoming_setup("abi_relay_composed") + result_check(24, "composed_relay"),
        {"abi_composed": composed_target},
        input_record=COMPOSED + bytes(8),
        result_bytes=composed_result,
    )
    test(
        "incoming-empty-result-no-payload-store",
        assembly,
        incoming_setup("abi_empty") + result_check(24, "empty_in"),
        input_record=bytes(16),
        result_bytes=bytes([204]) * 24,
    )
    empty_target = check_record("expected_empty_record", 16, "empty_out") + "xorq %rax, %rax\nret\n"
    test(
        "outgoing-empty-record-rounded-padding",
        assembly,
        incoming_setup("abi_relay_empty") + result_check(24, "empty_relay"),
        {"abi_empty": empty_target},
        input_record=bytes(16),
        result_bytes=bytes([204]) * 24,
    )
    maximum_record = b"".join(q(i) for i in range(1, 385))
    maximum_result = b"".join(q(i) for i in range(321, 385))
    test(
        "incoming-maximum-3072-byte-scalar",
        assembly,
        incoming_setup("abi_max_scalar") + check_canaries(),
        input_record=maximum_record,
        expected=3310,
    )
    test(
        "incoming-maximum-3072-byte-class",
        assembly,
        incoming_setup("abi_max_result") + result_check(512, "maximum_in"),
        input_record=maximum_record,
        result_bytes=maximum_result,
        result_capacity=520,
    )
    max_scalar = check_record("maximum_expected", 3072, "maximum_out_scalar") + "movq $42, %rax\nret\n"
    test(
        "outgoing-maximum-3072-byte-scalar",
        assembly,
        "call abi_out_max_scalar\n",
        {"abi_max_scalar": max_scalar},
        expected=43,
        extra_data=data("maximum_expected", maximum_record),
    )
    max_result = (
        "movq %rax, %rdx\n"
        + disjoint("%rdx", 512, "%r10", 8, "max_receiver")
        + disjoint("%rdx", 512, "%r11", 3072, "max_record")
    )
    max_result += (
        check_record("maximum_expected", 3072, "maximum_out_result")
        + """xorq %rcx, %rcx
.Lwrite_max_result:
movq maximum_result(%rcx), %rsi
movq %rsi, (%rdx,%rcx)
addq $8, %rcx
cmpq $512, %rcx
jne .Lwrite_max_result
xorq %rax, %rax
ret
"""
    )
    test(
        "outgoing-maximum-3072-byte-class",
        assembly,
        "call abi_out_max_result\n",
        {"abi_max_result": max_result},
        expected=sum(range(321, 385)) + 1,
        extra_data=data("maximum_expected", maximum_record) + data("maximum_result", maximum_result),
    )
    pack_result = bytes([11]) + bytes([204]) * 7 + q(13) + bytes([17]) + bytes([204]) * 7
    for mode, symbol, record in [
        ("ordinary", "abi_old_ordinary", PACK + bytes(8)),
        ("old_result", "abi_old_result_method", bytes(16)),
        ("constructor", "abi_old_constructor", PACK + bytes(8)),
    ]:
        test(
            "incoming-control-" + mode,
            assembly,
            incoming_setup(symbol, mode) + result_check(24, "old_" + mode),
            input_record=record,
            result_bytes=pack_result,
        )
    test(
        "incoming-control-scalar-method",
        assembly,
        incoming_setup("abi_old_scalar_method", "old_scalar") + check_canaries(),
        expected=1013,
    )
    ordinary_target = (
        ALIGN
        + "movq %r10, %rdx\n"
        + compare_bytes("%r11", "expected_pack_record", 32, "old_out_ordinary")
        + pack_write("%rdx")
        + "xorq %rax, %rax\nret\n"
    )
    old_result_target = (
        ALIGN
        + """cmpq $1000, (%r10)
jne .Labi_fail
cmpq $13, %rdi
jne .Labi_fail
"""
        + pack_write("%r11")
        + "xorq %rax, %rax\nret\n"
    )
    constructor_target = (
        ALIGN
        + "movq %r10, %rdx\n"
        + compare_bytes("%r11", "expected_pack_record", 32, "old_out_constructor")
        + pack_write("%rdx")
        + "xorq %rax, %rax\nret\n"
    )
    scalar_control = (
        ALIGN
        + """cmpq $1000, (%r10)
jne .Labi_fail
cmpq $13, %rdi
jne .Labi_fail
movq $1013, %rax
ret
"""
    )
    for kind, body, expected_value in [
        ("ordinary", ordinary_target, 14),
        ("result_method", old_result_target, 14),
        ("constructor", constructor_target, 14),
        ("scalar_method", scalar_control, 1014),
    ]:
        test(
            "outgoing-control-" + kind,
            assembly,
            "call abi_out_old_" + kind + "\n",
            {"abi_old_" + kind: body},
            expected=expected_value,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    fixture = args.fixture.resolve()
    WORK = Path(tempfile.mkdtemp(prefix="aurora-method-abi-"))
    print(f"fixture sha256={hashlib.sha256(fixture.read_bytes()).hexdigest()}", flush=True)
    print(f"work directory: {WORK}", flush=True)
    try:
        assembly = run([fixture, "--output", AIR, "abi"]).decode()
        (WORK / "fixture.s").write_text(assembly)
        # Freeze hidden-slot ownership as well as observable behavior. These
        # numeric offsets are independently specified from each fixture frame.
        for symbol, required in {
            "abi_in_scalar": ["subq $112, %rsp", "movq %r10, -104(%rbp)", "movq %r11, -112(%rbp)"],
            "abi_in_result": [
                "subq $128, %rsp",
                "movq %r10, -104(%rbp)",
                "movq %r11, -112(%rbp)",
                "movq %rax, -120(%rbp)",
            ],
            "abi_empty": ["subq $48, %rsp", "movq %r10, -24(%rbp)", "movq %r11, -32(%rbp)", "movq %rax, -40(%rbp)"],
        }.items():
            body = assembly.split(symbol + ":\n", 1)[1].split(".size " + symbol + ",", 1)[0]
            for instruction in required:
                require(instruction in body, f"{symbol}: frozen hidden frame instruction missing: {instruction}")
        native_cases(assembly)
        print(f"PASS method ABI: {COUNT} independent native cases; private symbols checked in every object", flush=True)
    except Exception:
        print(f"FAIL: retained native failure artifacts in {WORK}", flush=True)
        raise
    else:
        shutil.rmtree(WORK)
