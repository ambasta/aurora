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


def fixture_metadata(fixture: str) -> dict:
    result = {"unsigned_fixture": fixture, "division_fixture": "none"}
    for index in range(3):
        base = 0x1B0000 + index * 4096
        result[str(index)] = {
            "base": base,
            "size": 128,
            "return": base + 32,
            "bounds": base + 64,
            "overflow": base + 66,
            "division_zero": base + 68,
            "shift_count": base + 70,
        }
    return result


def fixture_transcript(fixture: str, metadata: dict) -> tuple[int, str]:
    text = "\n".join(baseline.FOUNDATIONS) + "\n" + baseline.USER_OK + "\n"
    text += f"AURORA_UNSIGNED_FIXTURE: {fixture}\n"
    if fixture == "kernel-trap":
        text += baseline.domain_fixture() + "AURORA_DOMAIN_ENTER: image=0 root=65536\n"
        text += "AURORA_PROGRAM_ENTER: image=0\nAURORA_DOMAIN_FAULT_ROOT: root=65536\n"
        text += f"AURORA_EXCEPTION_FATAL: 6 error=0 rip={metadata['0']['shift_count']}\n"
        text += "AURORA_EXCEPTION_CONTEXT: cpl=0 frame=589568 cr2=0\nAURORA_BOOT_FAIL\n"
        return 35, text
    text += "AURORA_USER_ENTER: 0\n"
    flow = baseline.program_flow(metadata["1"]["bounds"], metadata["2"]["overflow"])
    if fixture == "shift-count":
        flow = flow.replace("image=1 kind=bounds vector=6", "image=1 kind=shift_count vector=6 error=0")
        flow = flow.replace(f"rip={metadata['1']['bounds']}", f"rip={metadata['1']['shift_count']}")
        flow = flow.replace("image=1 kind=bounds", "image=1 kind=shift_count")
        flow = flow.replace(baseline.COMPILED_OK, COMPILED_SHIFT)
    text += flow + baseline.domain_flow() + UNSIGNED_OK + "\nAurora language result: 42\nAURORA_BOOT_OK\n"
    return 33, text


def self_test() -> None:
    passed, rejected = 0, 0

    def deny(status: int, text: str, mode: str, metadata: dict) -> None:
        nonlocal rejected
        try:
            validate_mode(status, text, mode, metadata)
        except ValueError:
            rejected += 1
            return
        raise RuntimeError(f"Invalid unsigned evidence accepted: {mode}")

    for mode, fixture in MODES.items():
        metadata = fixture_metadata(fixture)
        status, good = fixture_transcript(fixture, metadata)
        validate_mode(status, good, mode, metadata)
        passed += 1
        marker = f"AURORA_UNSIGNED_FIXTURE: {fixture}"
        for text in (
            good.replace(marker, ""),
            good + marker + "\n",
            good + UNSIGNED_OK + "\n",
            good.replace(marker, "AURORA_UNSIGNED_FIXTURE: none"),
            good + "AURORA_DIVISION_FIXTURE: zero\n",
            good.replace("AURORA_DOMAIN_ENTER: image=0 root=65536", "AURORA_DOMAIN_ENTER: image=0 root=196608", 1),
        ):
            deny(status, text, mode, metadata)
        deny(0, good, mode, metadata)
        for index in range(3):
            for site in (
                0,
                metadata[str(index)]["return"],
                metadata[str(index)]["bounds"],
                metadata[str(index)]["overflow"],
                metadata[str(index)]["division_zero"],
                metadata[str(index)]["base"] - 1,
                metadata[str(index)]["base"] + 127,
                "bad",
                True,
            ):
                bad = deepcopy(metadata)
                bad[str(index)]["shift_count"] = site
                deny(status, good, mode, bad)
        for key in ("unsigned_fixture", "division_fixture"):
            bad = deepcopy(metadata)
            bad.pop(key)
            deny(status, good, mode, bad)
        bad = deepcopy(metadata)
        bad["1"].pop("shift_count")
        deny(status, good, mode, bad)
        bad = deepcopy(metadata)
        bad["division_fixture"] = "zero"
        deny(status, good, mode, bad)
        if fixture == "kernel-trap":
            for text in (
                good.replace("cpl=0", "cpl=3"),
                good.replace("FATAL: 6", "FATAL: 0"),
                good.replace("error=0", "error=1"),
                good.replace("frame=589568", "frame=548688"),
                good.replace(f"rip={metadata['0']['shift_count']}", f"rip={metadata['0']['bounds']}"),
                good.replace(f"rip={metadata['0']['shift_count']}", f"rip={metadata['0']['shift_count'] + 1}"),
                good + "AURORA_PROGRAM_CONTAINED: image=0 kind=shift_count\n",
            ):
                deny(status, text, mode, metadata)
        else:
            for text in (
                good.replace("value=42", "value=0", 1),
                good.replace("AURORA_PROGRAM_RETURN: image=0 value=42\n", "", 1),
                good.replace("AURORA_DOMAIN_RESTORED: root=196608", "AURORA_DOMAIN_RESTORED: root=65536", 1),
                good.replace(UNSIGNED_OK, ""),
                good + "AURORA_EXCEPTION_FATAL: 0 error=0 rip=0\n",
                good.replace("AURORA_PROGRAM_CONTAINED: image=2 kind=overflow", ""),
                good.replace("cpl=3", "cpl=0"),
                good.replace("frame=548688", "frame=548689"),
                good.replace("frame=548688", "frame=548864"),
                good.replace("vector=6", "vector=0"),
                good.replace(f"rip={metadata['2']['overflow']}", f"rip={metadata['2']['shift_count']}"),
            ):
                deny(status, text, mode, metadata)
        if fixture == "shift-count":
            fault = next(line for line in good.splitlines() if line.startswith("AURORA_PROGRAM_FAULT: image=1"))
            for old, new in (
                ("error=0", "error=1"),
                ("kind=shift_count", "kind=bounds"),
                (f"rip={metadata['1']['shift_count']}", f"rip={metadata['1']['bounds']}"),
            ):
                deny(status, good.replace(old, new), mode, metadata)
            deny(status, good + fault + "\n", mode, metadata)
            deny(status, good.replace("AURORA_PROGRAM_CONTAINED: image=1 kind=shift_count", ""), mode, metadata)
    print(f"PASS: unsigned smoke validators, {passed} positive and {rejected} negative cases")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--self-test"]:
            self_test()
        elif len(sys.argv) == 5:
            validate_mode(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        else:
            sys.exit("usage: kernel-unsigned-smoke.py --self-test | EXIT_STATUS SERIAL_LOG MODE IMAGE_METADATA")
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
