#!/usr/bin/env python3
"""Check division-specific evidence, then reuse the unchanged baseline validator."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import sys

SPEC = importlib.util.spec_from_file_location("kernel_smoke", Path(__file__).with_name("kernel-smoke.py"))
baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(baseline)
require = baseline.require
MODES = {"--division-" + name: name for name in ("zero", "remainder-zero", "overflow", "remainder-min", "kernel-trap")}
DIVISION_OK = "AURORA_DIVISION_OK: exact typed trap, clean restart, private teardown"
COMPILED_ZERO = "AURORA_COMPILED_USER_OK: arrays, loop, division_zero, overflow, clean restart"


def validate_metadata(metadata: dict, fixture: str) -> None:
    require(
        isinstance(metadata, dict)
        and (
            metadata.get("division_fixture") == fixture
            or (
                fixture == "kernel-trap"
                and metadata.get("division_fixture") == "none"
                and metadata.get("bios_fixture_family") == "ordinary"
            )
        ),
        "Division fixture does not match the linked-image receipt",
    )
    for index in range(3):
        image = metadata.get(str(index))
        require(isinstance(image, dict), "Missing division image metadata")
        require(
            all(
                type(image.get(key)) is int for key in ("base", "size", "return", "bounds", "overflow", "division_zero")
            ),
            "Malformed division image metadata",
        )
        base, size = image["base"], image["size"]
        require(
            0x1B0000 <= base < 0x1C8000 and base % 4096 == 0 and 4 <= size <= 4096,
            "Division image is not bounded to its private page",
        )
        sites = [image[key] for key in ("return", "bounds", "overflow", "division_zero")]
        require(
            len(set(sites)) == 4 and all(base <= pc <= base + size - 2 for pc in sites),
            "Missing, aliased, or out-of-image division trap authority",
        )
        require(image["return"] >= base + 2, "Invalid scalar return location")


def validate_mode(status: int, transcript: str, mode: str, metadata: dict) -> None:
    require(mode in MODES, "Unknown division smoke mode")
    fixture = MODES[mode]
    validate_metadata(metadata, fixture)
    lines = transcript.splitlines()
    fixture_line = f"AURORA_DIVISION_FIXTURE: {fixture}"
    fatal = fixture == "kernel-trap"
    expected_markers = [fixture_line] + ([] if fatal else [DIVISION_OK])
    require(
        [line for line in lines if line.startswith("AURORA_DIVISION_")] == expected_markers,
        "Missing, duplicate, or unexpected division evidence",
    )
    require(
        "AURORA_PROGRAM_ENTER: image=0" in lines
        and lines.index(fixture_line) < lines.index("AURORA_PROGRAM_ENTER: image=0"),
        "Division fixture must be identified before execution",
    )
    projected = [line for line in lines if not line.startswith("AURORA_DIVISION_")]
    linked = deepcopy(metadata)
    if fixture in ("zero", "remainder-zero"):
        faults = [line for line in lines if line.startswith("AURORA_PROGRAM_FAULT: image=1 ")]
        require(len(faults) == 1, "Division must produce exactly one terminal fault")
        match = re.fullmatch(
            r"AURORA_PROGRAM_FAULT: image=1 kind=division_zero vector=6 error=0 rip=([0-9]+) cpl=3 frame=([0-9]+)",
            faults[0],
        )
        require(match is not None, "Division requires a typed user UD2, not a hardware divide exception")
        pc, frame = map(int, match.groups())
        require(pc == metadata["1"]["division_zero"], "Division PC differs from exact linked UD2")
        require(
            0x82000 <= frame <= 0x86000 - 176 and frame % 8 == 0, "Division frame is not a complete aligned RSP0 frame"
        )
        require(lines.count(COMPILED_ZERO) == 1, "Missing typed division completion")
        # The division evidence above is strict. Only then project this one
        # terminal event onto the existing sequence/domain/restart validator.
        translations = {
            faults[0]: faults[0].replace("kind=division_zero vector=6 error=0", "kind=bounds vector=6"),
            "AURORA_PROGRAM_CONTAINED: image=1 kind=division_zero": "AURORA_PROGRAM_CONTAINED: image=1 kind=bounds",
            COMPILED_ZERO: baseline.COMPILED_OK,
        }
        projected = [translations.get(line, line) for line in projected]
        linked["1"]["bounds"] = pc
    if fatal:
        # The old fatal gate independently checks CPL0, vector6, kernel stack,
        # active-domain context, exit35, and absence of any successful return.
        linked["0"]["bounds"] = metadata["0"]["division_zero"]
        baseline.validate_mode(status, "\n".join(projected), "--program-kernel-trap", linked)
    else:
        compiled = COMPILED_ZERO if fixture in ("zero", "remainder-zero") else baseline.COMPILED_OK
        require(
            compiled in lines
            and "AURORA_BOOT_OK" in lines
            and lines.index(compiled) < lines.index(DIVISION_OK) < lines.index("AURORA_BOOT_OK"),
            "Division completed before restart/teardown or after boot success",
        )
        baseline.validate_mode(status, "\n".join(projected), "normal", linked)


if __name__ == "__main__":
    try:
        if len(sys.argv) == 5:
            validate_mode(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        else:
            sys.exit("usage: kernel-division-smoke.py EXIT_STATUS SERIAL_LOG MODE IMAGE_METADATA")
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
