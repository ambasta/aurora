#!/usr/bin/env python3
"""Validate QEMU's exit and serial transcript; includes emulator-free regressions."""
from pathlib import Path
import sys
import re


def validate(status: int, transcript: str) -> None:
    lines = transcript.splitlines()
    if status != 33:
        raise ValueError(f"QEMU exit status {status}, expected 33")
    if "Aurora language result: 42" not in lines:
        raise ValueError("Missing exact language result")
    if "AURORA_BOOT_OK" not in lines:
        raise ValueError("Missing exact success marker")
    for marker in ("AURORA_E820_OK", "AURORA_EXCEPTION_OK: breakpoint, 15 GPRs, direction flag",
                   "AURORA_PAGES_OK: 128 frames, exhaustion, reuse, ownership, double-free"):
        if marker not in lines:
            raise ValueError(f"Missing kernel self-test marker: {marker}")
    if "AURORA_EXCEPTION_FATAL" in transcript:
        raise ValueError("Unexpected fatal exception")
    if "AURORA_BOOT_FAIL" in transcript:
        raise ValueError("Kernel emitted failure marker")


def validate_fault(status: int, transcript: str, vector: int = 0) -> None:
    if status != 35:
        raise ValueError(f"Fault QEMU exit status {status}, expected 35")
    if not re.search(rf"^AURORA_EXCEPTION_FATAL: {vector} error=0 rip=[0-9]+\r?$", transcript, re.MULTILINE):
        raise ValueError("Expected injected-exception diagnostic missing")
    if "AURORA_BOOT_FAIL" not in transcript.splitlines() or "AURORA_BOOT_OK" in transcript:
        raise ValueError("Fault did not fail-stop")


def self_test() -> None:
    good = "Aurora language result: 42\r\nAURORA_BOOT_OK\r\n"
    good += "AURORA_E820_OK\nAURORA_EXCEPTION_OK: breakpoint, 15 GPRs, direction flag\n"
    good += "AURORA_PAGES_OK: 128 frames, exhaustion, reuse, ownership, double-free\n"
    validate(33, good)
    bad_cases = ((33, good + "AURORA_BOOT_FAIL\r\n"), (0, good), (124, good),
                 (33, "Aurora language result: 42\n"), (33, "AURORA_BOOT_OK\n"),
                 (33, good.replace("42", "43")), (33, good.replace("42", "420")),
                 (33, good.replace("AURORA_BOOT_OK", "AURORA_BOOT_OKAY")),
                 (33, good.replace("AURORA_E820_OK", "")),
                 (33, good.replace("AURORA_EXCEPTION_OK", "MISSING")),
                 (33, good.replace("AURORA_PAGES_OK", "MISSING")),
                 (33, good + "AURORA_EXCEPTION_FATAL: 0 error=0 rip=123\n"))
    for status, transcript in bad_cases:
        try:
            validate(status, transcript)
        except ValueError:
            continue
        raise RuntimeError(f"Bad smoke transcript accepted: {status}, {transcript!r}")
    fault = "AURORA_EXCEPTION_FATAL: 0 error=0 rip=12345\r\nAURORA_BOOT_FAIL\r\n"
    validate_fault(35, fault)
    validate_fault(35, fault.replace("FATAL: 0", "FATAL: 14"), 14)
    for status, transcript in ((33, fault), (35, fault + "AURORA_BOOT_OK\n"),
                               (35, fault.replace("error=0", "error=1")),
                               (35, fault.replace("FATAL: 0", "FATAL: 14")),
                               (35, fault.replace("AURORA_BOOT_FAIL", ""))):
        try:
            validate_fault(status, transcript)
        except ValueError:
            continue
        raise RuntimeError("Invalid fault transcript accepted")
    print("PASS: smoke validators, 3 success cases and 17 failure regressions (no QEMU required)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    elif len(sys.argv) == 4:
        try:
            status, transcript = int(sys.argv[1]), Path(sys.argv[2]).read_text()
            if sys.argv[3] == "normal": validate(status, transcript)
            elif sys.argv[3] == "--fault": validate_fault(status, transcript)
            elif sys.argv[3] == "--page-fault": validate_fault(status, transcript, 14)
            else: raise ValueError("Unknown smoke mode")
        except ValueError as error:
            sys.exit(f"FAIL: {error}")
    else:
        sys.exit("usage: kernel-smoke.py --self-test | EXIT_STATUS SERIAL_LOG MODE")
