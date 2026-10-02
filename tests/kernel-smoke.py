#!/usr/bin/env python3
"""Validate actual exception codes, origin privilege, stacks and denied addresses."""
from pathlib import Path
import sys
import re

FOUNDATIONS = (
    "AURORA_E820_OK",
    "AURORA_EXCEPTION_OK: breakpoint, 15 GPRs, direction flag",
    "AURORA_PAGES_OK: 128 frames, exhaustion, reuse, ownership, double-free",
    "AURORA_WX_OK: RX text, R-NX constants, RW-NX data, NXE, WP, guards",
)
USER_OK = "AURORA_USER_OK: ring3, own stack, TSS entry, controlled return"
# vector, error code, CPL, denied linear address, controlled user selector
FAULTS = {
    "--fault": (0, 0, 0, None, None),
    "--page-fault": (14, 0, 0, 0x400000, None),
    "--wp": (14, 3, 0, 0x10000, None),
    "--nx": (14, 17, 0, "target", None),
    "--stack": (8, 0, 0, "guard", None),
    "--user-read": (14, 5, 3, 0x10000, 1),
    "--user-write": (14, 7, 3, 0x10000, 2),
    "--user-cli": (13, 0, 3, None, 3),
    "--user-code-write": (14, 7, 3, 0x1D0000, 4),
    "--user-nx": (14, 21, 3, 0x1E0000, 5),
    "--user-io": (13, 0, 3, None, 6),
}

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(status: int, transcript: str) -> None:
    lines = transcript.splitlines()
    require(status == 33, f"QEMU exit status {status}, expected 33")
    for marker in (*FOUNDATIONS, USER_OK, "AURORA_USER_ENTER: 0", "Aurora language result: 42", "AURORA_BOOT_OK"):
        require(lines.count(marker) == 1, f"Missing or duplicated marker: {marker}")
    require("AURORA_BOOT_FAIL" not in transcript and "AURORA_EXCEPTION_FATAL" not in transcript,
            "Normal run emitted failure")


def validate_mode(status: int, transcript: str, mode: str) -> None:
    if mode == "normal":
        validate(status, transcript)
        return
    lines = transcript.splitlines()
    require(status == 35, f"Fault QEMU exit status {status}, expected 35")
    require(lines.count("AURORA_BOOT_FAIL") == 1 and "AURORA_BOOT_OK" not in transcript, "Fault did not fail-stop")
    require(USER_OK not in transcript, "Denied operation returned to success path")
    if mode == "--no-nx":
        require("Required NX capability or protected mapping validation failed" in lines, "Missing NX rejection")
        require("AURORA_WX_OK" not in transcript and "AURORA_EXCEPTION_FATAL" not in transcript, "NX absence was not rejected cleanly")
        return
    require(mode in FAULTS, "Unknown smoke mode")
    for marker in FOUNDATIONS:
        require(lines.count(marker) == 1, f"Fault happened before required foundation: {marker}")
    vector, error, cpl, denied, user_mode = FAULTS[mode]
    fatal = re.findall(r"^AURORA_EXCEPTION_FATAL: ([0-9]+) error=([0-9]+) rip=([0-9]+)\r?$", transcript, re.MULTILINE)
    require(len(fatal) == 1, "Missing or multiple fatal diagnostics")
    actual_vector, actual_error, rip = map(int, fatal[0])
    require((actual_vector, actual_error) == (vector, error), "Wrong CPU exception or error bits")
    contexts = re.findall(r"^AURORA_EXCEPTION_CONTEXT: cpl=([0-9]+) frame=([0-9]+) cr2=([0-9]+)\r?$", transcript, re.MULTILINE)
    require(len(contexts) == 1, "Missing or multiple privilege/stack contexts")
    actual_cpl, frame, cr2 = map(int, contexts[0])
    require(actual_cpl == cpl, "Wrong exception origin privilege")
    if mode == "--stack":
        require(0x7C000 <= frame < 0x80000 and "AURORA_IST_OK" in lines, "Double fault did not use emergency IST")
        require(0x87000 <= cr2 < 0x88000, "Stack fault outside guard")
    elif cpl == 3:
        require(0x82000 <= frame < 0x86000 and "AURORA_TSS_ENTRY_OK" in lines, "User exception did not use RSP0")
        require(f"AURORA_USER_ENTER: {user_mode}" in lines, "Wrong controlled user probe")
        if mode != "--user-nx":
            require(0x1D0000 <= rip < 0x1D1000, "Fault did not originate in user code")
    else:
        require(0x88000 <= frame < 0x90000, "Kernel exception used unexpected stack")
    if isinstance(denied, int):
        require(cr2 == denied, "Page fault denied the wrong address")
    elif denied == "target":
        target = re.findall(r"^AURORA_FAULT_TARGET: ([0-9]+)\r?$", transcript, re.MULTILINE)
        require(len(target) == 1 and cr2 == int(target[0]) and rip == cr2, "NX fault did not deny the requested instruction fetch")
    if mode == "--user-nx":
        require(rip == cr2, "User NX fault did not deny instruction fetch")


def validate_fault(status: int, transcript: str, vector: int = 0) -> None:
    validate_mode(status, transcript, "--fault" if vector == 0 else "--page-fault")


def self_test() -> None:
    foundation = "\n".join(FOUNDATIONS) + "\n"
    good = foundation + USER_OK + "\nAURORA_USER_ENTER: 0\nAurora language result: 42\nAURORA_BOOT_OK\n"
    validate(33, good)
    rejected = 0
    def must_reject(status: int, text: str, mode: str) -> None:
        nonlocal rejected
        try:
            validate_mode(status, text, mode)
        except ValueError:
            rejected += 1
            return
        raise RuntimeError(f"Bad transcript accepted for {mode}: {text!r}")
    for marker in (*FOUNDATIONS, USER_OK, "AURORA_USER_ENTER: 0", "Aurora language result: 42", "AURORA_BOOT_OK"):
        must_reject(33, good.replace(marker, "missing"), "normal")
    for status, text in ((0, good), (124, good), (33, good + "AURORA_BOOT_FAIL\n"),
                         (33, good + "AURORA_EXCEPTION_FATAL\n"), (33, good.replace("result: 42", "result: 420")),
                         (33, good + "AURORA_BOOT_OK\n")):
        must_reject(status, text, "normal")
    for mode, (vector, error, cpl, denied, user_mode) in FAULTS.items():
        frame = 0x7FF00 if mode == "--stack" else 0x85F00 if cpl == 3 else 0x8FF00
        cr2 = denied if isinstance(denied, int) else 0x87FF8 if denied == "guard" else 0x20000 if denied == "target" else 0
        rip = cr2 if mode in ("--nx", "--user-nx") else 0x1D0200 if cpl == 3 else 0x10500
        text = foundation
        if user_mode is not None: text += f"AURORA_USER_ENTER: {user_mode}\nAURORA_TSS_ENTRY_OK\n"
        if mode == "--stack": text += "AURORA_IST_OK\n"
        if mode == "--nx": text += f"AURORA_FAULT_TARGET: {cr2}\n"
        text += f"AURORA_EXCEPTION_FATAL: {vector} error={error} rip={rip}\n"
        text += f"AURORA_EXCEPTION_CONTEXT: cpl={cpl} frame={frame} cr2={cr2}\nAURORA_BOOT_FAIL\n"
        validate_mode(35, text, mode)
        for status, corrupted in ((33, text), (35, text + "AURORA_BOOT_OK\n"),
                                  (35, text.replace(f"error={error} ", "error=99 ")),
                                  (35, text.replace(f"cpl={cpl} ", "cpl=2 ")),
                                  (35, text.replace(f"frame={frame} ", "frame=0 ")),
                                  (35, text.replace("AURORA_BOOT_FAIL", "missing"))):
            must_reject(status, corrupted, mode)
        if denied is not None:
            must_reject(35, text.replace(f"cr2={cr2}", "cr2=9"), mode)
    absent = "Required NX capability or protected mapping validation failed\nAURORA_BOOT_FAIL\n"
    validate_mode(35, absent, "--no-nx")
    must_reject(35, absent + "AURORA_WX_OK\n", "--no-nx")
    print(f"PASS: smoke validators, 13 success cases and {rejected} failure regressions (no QEMU required)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 4:
        try:
            validate_mode(int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3])
        except ValueError as error:
            sys.exit(f"FAIL: {error}")
    else:
        sys.exit("usage: kernel-smoke.py --self-test | EXIT_STATUS SERIAL_LOG MODE")
