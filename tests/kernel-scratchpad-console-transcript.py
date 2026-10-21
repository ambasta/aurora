#!/usr/bin/env python3
"""Synthetic strict-oracle mutations; no guest is executed."""

import argparse
import copy
import json
from pathlib import Path
import re

import kernel_scratchpad_console_oracle as oracle


def fixtures():
    phases = oracle.phases
    fixture = next(phases.fixtures())
    metadata = copy.deepcopy(fixture[3])
    del metadata["images"]["peer"]
    metadata["images"]["clean"]["call_pc"] = phases.BASE + 70
    metadata["images"]["bounds"]["serve_pc"] = phases.BASE + oracle.LAYOUT.code_stride + 70
    prefix = fixture[2].split("AURORA_UEFI_TIMER_READY:")[0]
    text = phases.ram_receipt_fixture(metadata, prefix)
    text = text.replace("AURORA_FIXTURE_READY\n", "").replace("AURORA_UEFI_TIMER_PENDING: epoch=1\n", "")
    text = re.sub(
        r"AURORA_RAM_FILE_BEGIN: phase=0 service=1 caller=3 root=(\d+)",
        oracle.READY + r"\naurora> get\nAURORA_SCRATCHPAD_BEGIN: command=1 caller=3 service=1 root=\1",
        text,
    )
    text = text.replace(
        "AURORA_RAM_FILE_COMMAND: phase=0 exchanges=2 result=42 outcome=completed retained=1",
        "AURORA_SCRATCHPAD_SETTLED: command=1 used=4 service=1\nmissing\naurora> exit\nAURORA_CONSOLE_EXIT",
    )
    text = text.replace("AURORA_UEFI_RAM_FILE_OK:", "AURORA_RAM_SCRATCHPAD_EXIT:")
    plan = [dict(command="get", reply="missing", exchanges=2, effect="normal")]
    yield 33, text.replace("\n", "\r\n"), plan, metadata, False
    # Independent second command with a normal exact terminal return; the
    # explicit fixture transport then writes only two acknowledgement bytes.
    marker = "AURORA_SCRATCHPAD_BEGIN: command=1"
    body = text[text.index(marker) : text.index("missing\naurora> exit")]
    body = re.sub(r"epoch=([345])\b", lambda match: "epoch=" + str(int(match[1]) + 4), body)
    body = re.sub(r"transaction=([23])\b", lambda match: "transaction=" + str(int(match[1]) + 3), body)
    body = body.replace("command=1", "command=2").replace("caller=3", "caller=4")
    timeout = text[: text.index("aurora> exit")] + "aurora> put\n" + body + "sa"
    timeout = re.sub(r"(AURORA_UEFI_TIMER_READY:[^\n]*\n)", r"\1AURORA_SCRATCHPAD_FIXTURE_READY\n", timeout)
    plan = plan + [dict(command="put", reply="sa", exchanges=2, effect="timeout")]
    yield 33, timeout.replace("\n", "\r\n"), plan, metadata, True


def check(cases):
    positive = negative = 0
    for status, text, plan, metadata, fixture in cases:
        oracle.validate(status, text, plan, metadata, fixture=fixture)
        positive += 1

        def reject(changed, changed_status=status):
            nonlocal negative
            try:
                oracle.validate(changed_status, changed, plan, metadata, fixture=fixture)
            except (ValueError, IndexError, KeyError, TypeError):
                negative += 1
                return
            raise ValueError("Accepted mutated scratchpad transcript")

        lines = text.splitlines(keepends=True)
        start = next(i for i, line in enumerate(lines) if line.startswith("AURORA_UEFI_TIMER_READY:"))
        for index in range(start, len(lines)):
            for changed in (
                lines[:index] + lines[index + 1 :],
                lines[:index] + [lines[index]] + lines[index:],
                lines[:index] + ["AURORA_SCRATCHPAD_UNKNOWN: value=1\r\n"] + lines[index:],
            ):
                reject("".join(changed))
            if index + 1 < len(lines):
                reject("".join(lines[:index] + [lines[index + 1], lines[index]] + lines[index + 2 :]))
            for match in re.finditer(r"(?<==)\d+", lines[index]):
                field = lines[index][: match.start()].rsplit(" ", 1)[-1]
                value = 0 if field in ("flags=", "pc=", "frame=") else int(match[0]) + 1
                changed = lines.copy()
                changed[index] = lines[index][: match.start()] + str(value) + lines[index][match.end() :]
                reject("".join(changed))
        reject(text.replace("AURORA_UEFI_TIMER_READY:", "data: leaked\r\nAURORA_UEFI_TIMER_READY:", 1))
        for extra in ("\r", "x", "sa", "\r\n", "data: forbidden\r\n", "aurora> "):
            reject(text + extra)
        reject(text, 124)
    return positive, negative


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", action="append", type=Path, default=[])
    args = parser.parse_args()
    cases = list(fixtures())
    for directory in args.receipt:
        result = json.loads((directory / "result.json").read_text())
        cases.append(
            (
                result["exit_code"],
                (directory / "serial.log").read_bytes().decode("ascii"),
                json.loads((directory / "plan.json").read_text()),
                json.loads((directory / "metadata.json").read_text()),
                result["case"] not in {"normal", "limit"},
            )
        )
    positive, negative = check(cases)
    print(f"PASS: scratchpad transcripts {positive} positive and {negative} negative cases; no guest executed")


if __name__ == "__main__":
    main()
