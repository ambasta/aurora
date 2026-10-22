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
            base == 0x1B0000 + index * 4096 and 4 <= size <= 4096, "Division image is not bounded to its private page"
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


def fixture_metadata(fixture: str) -> dict:
    result = {"division_fixture": fixture}
    for index in range(3):
        base = 0x1B0000 + index * 4096
        result[str(index)] = {
            "base": base,
            "size": 128,
            "return": base + 32,
            "bounds": base + 64,
            "overflow": base + 66,
            "division_zero": base + 68,
        }
    return result


def fixture_transcript(fixture: str, metadata: dict) -> tuple[int, str]:
    text = "\n".join(baseline.FOUNDATIONS) + "\n" + baseline.USER_OK + "\n"
    text += f"AURORA_DIVISION_FIXTURE: {fixture}\n"
    if fixture == "kernel-trap":
        text += baseline.domain_fixture() + "AURORA_DOMAIN_ENTER: image=0 root=65536\n"
        text += "AURORA_PROGRAM_ENTER: image=0\nAURORA_DOMAIN_FAULT_ROOT: root=65536\n"
        text += f"AURORA_EXCEPTION_FATAL: 6 error=0 rip={metadata['0']['division_zero']}\n"
        text += "AURORA_EXCEPTION_CONTEXT: cpl=0 frame=589568 cr2=0\nAURORA_BOOT_FAIL\n"
        return 35, text
    text += "AURORA_USER_ENTER: 0\n"
    flow = baseline.program_flow(metadata["1"]["bounds"], metadata["2"]["overflow"])
    if fixture in ("zero", "remainder-zero"):
        flow = flow.replace("image=1 kind=bounds vector=6", "image=1 kind=division_zero vector=6 error=0")
        flow = flow.replace(f"rip={metadata['1']['bounds']}", f"rip={metadata['1']['division_zero']}")
        flow = flow.replace("image=1 kind=bounds", "image=1 kind=division_zero")
        flow = flow.replace(baseline.COMPILED_OK, COMPILED_ZERO)
    text += flow + baseline.domain_flow() + DIVISION_OK + "\nAurora language result: 42\nAURORA_BOOT_OK\n"
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
        raise RuntimeError(f"Invalid division evidence accepted: {mode}")

    for mode, fixture in MODES.items():
        metadata = fixture_metadata(fixture)
        status, good = fixture_transcript(fixture, metadata)
        validate_mode(status, good, mode, metadata)
        passed += 1
        marker = f"AURORA_DIVISION_FIXTURE: {fixture}"
        for text in (
            good.replace(marker, ""),
            good + marker + "\n",
            good + DIVISION_OK + "\n",
            good.replace(marker, "AURORA_DIVISION_FIXTURE: none"),
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
                metadata[str(index)]["base"] - 1,
                metadata[str(index)]["base"] + 127,
                "bad",
                True,
            ):
                bad = deepcopy(metadata)
                bad[str(index)]["division_zero"] = site
                deny(status, good, mode, bad)
        bad = deepcopy(metadata)
        bad.pop("division_fixture")
        deny(status, good, mode, bad)
        bad = deepcopy(metadata)
        bad["1"].pop("division_zero")
        deny(status, good, mode, bad)
        if fixture == "kernel-trap":
            for text in (
                good.replace("cpl=0", "cpl=3"),
                good.replace("FATAL: 6", "FATAL: 0"),
                good.replace(f"rip={metadata['0']['division_zero']}", f"rip={metadata['0']['bounds']}"),
                good + "AURORA_PROGRAM_CONTAINED: image=0 kind=division_zero\n",
            ):
                deny(status, text, mode, metadata)
        else:
            for text in (
                good.replace("value=42", "value=0", 1),
                good.replace("AURORA_PROGRAM_RETURN: image=0 value=42\n", "", 1),
                good.replace("AURORA_DOMAIN_RESTORED: root=196608", "AURORA_DOMAIN_RESTORED: root=65536", 1),
                good.replace(DIVISION_OK, ""),
                good + "AURORA_EXCEPTION_FATAL: 0 error=0 rip=0\n",
                good.replace("AURORA_PROGRAM_CONTAINED: image=2 kind=overflow", ""),
            ):
                deny(status, text, mode, metadata)
        if fixture in ("zero", "remainder-zero"):
            fault = next(line for line in good.splitlines() if line.startswith("AURORA_PROGRAM_FAULT: image=1"))
            for replacement in ("vector=0", "vector=13"):
                deny(status, good.replace("vector=6 error=0", replacement + " error=0"), mode, metadata)
            for old, new in (
                ("error=0", "error=1"),
                ("cpl=3", "cpl=0"),
                ("frame=548688", "frame=548689"),
                ("frame=548688", "frame=548864"),
                ("kind=division_zero", "kind=bounds"),
                (f"rip={metadata['1']['division_zero']}", f"rip={metadata['1']['bounds']}"),
            ):
                deny(status, good.replace(old, new), mode, metadata)
            deny(status, good + fault + "\n", mode, metadata)
            deny(status, good.replace("AURORA_PROGRAM_CONTAINED: image=1 kind=division_zero", ""), mode, metadata)
        if fixture == "overflow":
            deny(status, good.replace("kind=overflow vector=6", "kind=overflow vector=0"), mode, metadata)
            deny(
                status,
                good.replace(f"rip={metadata['2']['overflow']}", f"rip={metadata['2']['division_zero']}"),
                mode,
                metadata,
            )
    metadata = fixture_metadata("kernel-trap")
    status, good = fixture_transcript("kernel-trap", metadata)
    metadata["division_fixture"] = "none"
    metadata["bios_fixture_family"] = "ordinary"
    validate_mode(status, good, "--division-kernel-trap", metadata)
    passed += 1
    for family in (None, "schedule", "unknown"):
        bad = deepcopy(metadata)
        bad["bios_fixture_family"] = family
        deny(status, good, "--division-kernel-trap", bad)
    bad = deepcopy(metadata)
    bad["0"]["division_zero"] = 0
    deny(status, good, "--division-kernel-trap", bad)
    print(f"PASS: division smoke validators, {passed} positive and {rejected} negative cases")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--self-test"]:
            self_test()
        elif len(sys.argv) == 5:
            validate_mode(
                int(sys.argv[1]), Path(sys.argv[2]).read_text(), sys.argv[3], json.loads(Path(sys.argv[4]).read_text())
            )
        else:
            sys.exit("usage: kernel-division-smoke.py --self-test | EXIT_STATUS SERIAL_LOG MODE IMAGE_METADATA")
    except ValueError as error:
        sys.exit(f"FAIL: {error}")
