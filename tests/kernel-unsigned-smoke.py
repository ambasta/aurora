#!/usr/bin/env python3
"""Check exact unsigned evidence, then reuse the unchanged baseline validator."""

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
MODES = {"--unsigned-" + name: name for name in ("valid", "shift-count", "conversion-overflow", "kernel-trap")}
UNSIGNED_OK = "AURORA_UNSIGNED_OK: full-width values, exact typed trap, clean restart, private teardown"
COMPILED_SHIFT = "AURORA_COMPILED_USER_OK: arrays, loop, shift_count, overflow, clean restart"


def validate_metadata(metadata: dict, fixture: str) -> None:
    require(
        isinstance(metadata, dict)
        and metadata.get("unsigned_fixture") == fixture
        and metadata.get("division_fixture") == "none",
        "Unsigned fixture does not match the linked-image receipt",
    )
    for index in range(3):
        image = metadata.get(str(index))
        require(isinstance(image, dict), "Missing unsigned image metadata")
        names = ("return", "bounds", "overflow", "division_zero", "shift_count")
        require(
            all(type(image.get(key)) is int for key in ("base", "size", *names)), "Malformed unsigned image metadata"
        )
        base, size = image["base"], image["size"]
        require(
            base == 0x1B0000 + index * 4096 and 4 <= size <= 4096, "Unsigned image is not bounded to its private page"
        )
        sites = [image[key] for key in names]
        require(
            len(set(sites)) == len(sites) and all(base <= pc <= base + size - 2 for pc in sites),
            "Missing, aliased, or out-of-image unsigned trap authority",
        )
        require(image["return"] >= base + 2, "Invalid scalar return location")


def validate_mode(status: int, transcript: str, mode: str, metadata: dict) -> None:
    require(mode in MODES, "Unknown unsigned smoke mode")
    fixture = MODES[mode]
    validate_metadata(metadata, fixture)
    lines = transcript.splitlines()
    marker = f"AURORA_UNSIGNED_FIXTURE: {fixture}"
    fatal = fixture == "kernel-trap"
    require(
        [line for line in lines if line.startswith("AURORA_UNSIGNED_")] == [marker] + ([] if fatal else [UNSIGNED_OK]),
        "Missing, duplicate, or unexpected unsigned evidence",
    )
    require(not any(line.startswith("AURORA_DIVISION_") for line in lines), "Combined feature gates are invalid")
    require(
        "AURORA_PROGRAM_ENTER: image=0" in lines and lines.index(marker) < lines.index("AURORA_PROGRAM_ENTER: image=0"),
        "Unsigned fixture must be identified before execution",
    )
    projected = [line for line in lines if not line.startswith("AURORA_UNSIGNED_")]
    linked = deepcopy(metadata)
    if fatal:
        # Existing fatal validation checks CPL0, vector/error, kernel stack,
        # active root, status 35, and absence of successful return/containment.
        linked["0"]["bounds"] = metadata["0"]["shift_count"]
        baseline.validate_mode(status, "\n".join(projected), "--program-kernel-trap", linked)
        return
    # Validate every contained event before projecting a shift event onto the
    # baseline's unchanged program/domain/restart ordering checks.
    faults = [line for line in lines if line.startswith("AURORA_PROGRAM_FAULT:")]
    require(len(faults) == 2, "Unsigned run must have exactly two terminal faults")
    first_kind = "shift_count" if fixture == "shift-count" else "bounds"
    for line, index, kind in zip(faults, (1, 2), (first_kind, "overflow")):
        error = " error=0" if kind == "shift_count" else ""
        match = re.fullmatch(
            rf"AURORA_PROGRAM_FAULT: image={index} kind={kind} vector=6{error} rip=([0-9]+) cpl=3 frame=([0-9]+)", line
        )
        require(match is not None, "Unsigned fault requires the exact typed user UD2")
        pc, frame = map(int, match.groups())
        require(pc == metadata[str(index)][kind], "Unsigned fault PC differs from exact linked UD2")
        require(
            0x82000 <= frame <= 0x86000 - 176 and frame % 8 == 0,
            "Unsigned fault frame is not a complete aligned RSP0 frame",
        )
    compiled = COMPILED_SHIFT if fixture == "shift-count" else baseline.COMPILED_OK
    require(
        lines.count(compiled) == 1
        and "AURORA_BOOT_OK" in lines
        and lines.index(compiled) < lines.index(UNSIGNED_OK) < lines.index("AURORA_BOOT_OK"),
        "Unsigned completion precedes restart/teardown or follows boot success",
    )
    if fixture == "shift-count":
        translations = {
            faults[0]: faults[0].replace("kind=shift_count vector=6 error=0", "kind=bounds vector=6"),
            "AURORA_PROGRAM_CONTAINED: image=1 kind=shift_count": "AURORA_PROGRAM_CONTAINED: image=1 kind=bounds",
            COMPILED_SHIFT: baseline.COMPILED_OK,
        }
        projected = [translations.get(line, line) for line in projected]
        linked["1"]["bounds"] = metadata["1"]["shift_count"]
    baseline.validate_mode(status, "\n".join(projected), "normal", linked)


if __name__ == "__main__":
    try:
        if len(sys.argv) == 5:
            validate_mode(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        else:
            sys.exit("usage: kernel-unsigned-smoke.py EXIT_STATUS SERIAL_LOG MODE IMAGE_METADATA")
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
